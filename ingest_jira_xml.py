"""
Offline JIRA XML ingestion (no network / no JIRA auth needed).

Takes an XML export file, parses issues, stores them in:
  - jira_issues
  - jira_embeddings

Run from project root:
  python ingest_jira_xml.py path\\to\\export.xml

Notes:
- Parsing is best-effort because JIRA XML exports vary (RSS-like <item> vs <issue> trees).
- Embeddings use existing generate_embedding() which supports mock mode via USE_MOCK_EMBEDDING=true.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"[INGEST] Loaded .env from: {env_path}")
    else:
        load_dotenv(override=True)
        print("[INGEST] WARNING: .env not found; using process env")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python ingest_jira_xml.py <path-to-jira-export.xml>")
        return 2

    xml_path = Path(sys.argv[1]).resolve()
    if not xml_path.exists():
        print(f"[INGEST] ERROR: file not found: {xml_path}")
        return 2

    _load_env()
    # Default to mock mode unless explicitly disabled
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    print(f"[INGEST] USE_MOCK_EMBEDDING={os.getenv('USE_MOCK_EMBEDDING')}")

    # Ensure imports work
    sys.path.insert(0, str(Path(__file__).parent / "backend"))

    from app.db.session import SessionLocal
    from app.models.jira import JiraEmbedding, JiraIssue
    from app.services.embeddings import generate_embedding
    from app.services.jira_xml import build_embedding_text_from_parsed, parse_jira_xml

    xml_content = xml_path.read_text(encoding="utf-8", errors="ignore")
    issues = parse_jira_xml(xml_content)
    print(f"[INGEST] Parsed {len(issues)} issue nodes from XML")

    db = SessionLocal()
    ingested = 0
    embedded = 0
    skipped = 0
    try:
        for issue in issues:
            issue_key = issue.get("issue_key")
            if not issue_key:
                skipped += 1
                continue

            row = JiraIssue(
                issue_key=issue_key,
                summary=issue.get("summary") or "",
                description=issue.get("description"),
                status=issue.get("status"),
                priority=issue.get("priority"),
                assignee=issue.get("assignee"),
                issue_type=issue.get("issue_type"),
                url=issue.get("url"),
                raw=issue.get("raw") or {"_source": "jira_xml_export"},
            )
            db.merge(row)
            ingested += 1

            text = build_embedding_text_from_parsed(issue)
            emb = generate_embedding(text, task_type="retrieval_document")
            if isinstance(emb, list) and len(emb) > 0:
                db.merge(JiraEmbedding(issue_key=issue_key, embedding=emb))
                embedded += 1

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[INGEST] ERROR: {e}")
        raise
    finally:
        db.close()

    print(f"[INGEST] Done. ingested={ingested} embedded={embedded} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

