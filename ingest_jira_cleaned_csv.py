"""
Ingest the cleaned JIRA CSV (produced by clean_jira_csv.py) into Postgres.

Input CSV columns expected:
  - Issue key
  - Summary
  - Component
  - Description
  - Comments (JSON list of strings, oldest->newest)

This will upsert into:
  - jira_issues
  - jira_embeddings

Embeddings are generated via generate_embedding(), which supports mock mode
via USE_MOCK_EMBEDDING=true.

Run from project root:
  python ingest_jira_cleaned_csv.py "C:\\Users\\me\\Downloads\\IT_JIRA_cleaned.csv"
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


def _load_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"[INGEST-CSV] Loaded .env from: {env_path}")
    else:
        load_dotenv(override=True)
        print("[INGEST-CSV] WARNING: .env not found; using process env")


def _parse_components(s: str) -> List[str]:
    parts = [p.strip() for p in (s or "").replace(",", ";").split(";")]
    out: List[str] = []
    seen = set()
    for p in parts:
        if not p:
            continue
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _comments_to_dicts(comments: List[str]) -> List[Dict[str, Any]]:
    """
    Convert list[str] -> list[dict] in ADA-like shape.
    We don't have timestamps/authors in the CSV, so we store body + a synthetic id/order.

    We store comments most-recent-first (ADA style): latest comment at index 0.
    """
    out: List[Dict[str, Any]] = []
    # incoming is oldest->newest, so reverse it
    for i, body in enumerate(reversed(comments), 1):
        out.append({"id": f"csv-{i}", "created": None, "displayName": None, "body": body})
    return out


def _build_embedding_text_from_csv(issue_key: str, summary: str, description: str, comments: List[str], components: List[str]) -> str:
    comments_text = ""
    if comments:
        comments_text = "\n\nComments:\n" + "\n---\n".join(comments)
    return (
        f"JIRA Issue {issue_key}\n"
        f"Components: {', '.join(components)}\n"
        f"Summary: {summary}\n\n"
        f"Description:\n{description}\n"
        f"{comments_text}"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python ingest_jira_cleaned_csv.py <path-to-cleaned.csv>")
        return 2

    csv_path = Path(sys.argv[1]).expanduser().resolve()
    if not csv_path.exists():
        print(f"[INGEST-CSV] ERROR: file not found: {csv_path}")
        return 2

    _load_env()
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    print(f"[INGEST-CSV] USE_MOCK_EMBEDDING={os.getenv('USE_MOCK_EMBEDDING')}")

    # Ensure imports work
    sys.path.insert(0, str(Path(__file__).parent / "backend"))

    from app.db.session import SessionLocal
    from app.models.jira import JiraEmbedding, JiraIssue
    from app.services.embeddings import generate_embedding

    db = SessionLocal()
    ingested = 0
    embedded = 0
    try:
        with csv_path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            required = {"Issue key", "Summary", "Component", "Description", "Comments"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError(f"CSV missing required columns. Found: {reader.fieldnames}")

            for row in reader:
                issue_key = (row.get("Issue key") or "").strip()
                if not issue_key:
                    continue

                summary = (row.get("Summary") or "").strip()
                description = (row.get("Description") or "").strip()
                components = _parse_components((row.get("Component") or "").strip())

                comments_raw = (row.get("Comments") or "[]").strip()
                try:
                    comments_list = json.loads(comments_raw)
                    if not isinstance(comments_list, list):
                        comments_list = []
                    comments_list = [str(x) for x in comments_list if x is not None and str(x).strip()]
                except Exception:
                    comments_list = []

                comments_dicts = _comments_to_dicts(comments_list)

                raw: Dict[str, Any] = {
                    "_source": "cleaned_jira_csv",
                    "issue_key": issue_key,
                    "summary": summary,
                    "description": description,
                    "components": components,
                    "comments": comments_dicts,
                }

                issue = JiraIssue(
                    issue_key=issue_key,
                    jira_id=None,
                    summary=summary or issue_key,
                    description=description or None,
                    status=None,
                    priority=None,
                    assignee=None,
                    issue_type=None,
                    program_theme=None,
                    labels=None,
                    components=components or None,
                    comments=comments_dicts or None,
                    url=None,
                    raw=raw,
                )
                db.merge(issue)
                ingested += 1

                emb_text = _build_embedding_text_from_csv(issue_key, summary, description, comments_list, components)
                emb = generate_embedding(emb_text, task_type="retrieval_document")
                if isinstance(emb, list) and len(emb) > 0:
                    db.merge(JiraEmbedding(issue_key=issue_key, embedding=emb))
                    embedded += 1

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[INGEST-CSV] ERROR: {e}")
        raise
    finally:
        db.close()

    print(f"[INGEST-CSV] Done. ingested={ingested} embedded={embedded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

