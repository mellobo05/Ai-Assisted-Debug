"""
New JIRA analysis (offline-friendly):

User provides:
  - issue key (e.g., SYSCROS-XXXXX)
  - summary
  - optional domain/os
  - optional logs file

We:
  1) Upsert into local Postgres (jira_issues + jira_embeddings)
  2) Run swarm analysis (RCA + logging + fix suggestions, media-routed)
  3) Optionally save the analysis run to DB (jira_analysis_runs)

Examples (from repo root):
  python scripts/agent/run_new_jira_analysis.py --issue-key SYSCROS-999999 --summary "Video flicker on playback" --domain media --os "ChromeOS"
  python scripts/agent/run_new_jira_analysis.py --issue-key SYSCROS-999999 --summary "Video flicker" --logs-file logs/hevc_fatcat.txt --external-knowledge --save-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _setup_imports_and_env() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "backend"))

    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

    # Default to mock embeddings for local runs unless explicitly disabled.
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    return repo_root


def _read_logs_text(path: str, max_bytes: int = 2_000_000) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    data = p.read_bytes()
    if len(data) > int(max_bytes):
        data = data[-int(max_bytes) :]
    return data.decode("utf-8", errors="replace")


def main() -> int:
    _setup_imports_and_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-key", required=True, help="JIRA issue key (e.g., SYSCROS-131125)")
    parser.add_argument("--summary", required=True, help="Short summary (e.g., Video flicker)")
    parser.add_argument("--domain", default=None, help="Domain (e.g., media, audio, networking)")
    parser.add_argument("--os", dest="os_name", default=None, help="OS (e.g., Windows, ChromeOS)")
    parser.add_argument("--description", default=None, help="Optional additional description")
    parser.add_argument("--logs-file", default=None, help="Optional logs file path")
    parser.add_argument(
        "--snippets-json",
        default=None,
        help="Optional path to JSON file with code snippets to store for future runs.",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--external-knowledge", action="store_true")
    parser.add_argument("--min-local-score", type=float, default=0.62)
    parser.add_argument("--external-max-results", type=int, default=5)
    parser.add_argument("--save-run", action="store_true", help="Persist analysis output to DB (jira_analysis_runs)")
    args = parser.parse_args()

    from app.agents.swarm import SwarmConfig, run_syscros_swarm
    from app.agents.tools import jira_tools
    from app.agents.tools import snippet_tools

    logs_text = None
    if args.logs_file:
        logs_text = _read_logs_text(str(args.logs_file))

    # Optional: store user-provided code snippets for future reference
    if args.snippets_json:
        import json

        raw = json.loads(Path(str(args.snippets_json)).read_text(encoding="utf-8"))
        items = raw.get("snippets") if isinstance(raw, dict) else raw
        if isinstance(items, list):
            for sn in items[:50]:
                if not isinstance(sn, dict):
                    continue
                snippet_tools.save_snippet(
                    ctx={"inputs": {}, "steps": {}},
                    issue_key=str(args.issue_key).strip(),
                    domain=str(args.domain).strip() if args.domain else None,
                    layer=str(sn.get("layer") or "").strip(),
                    language=str(sn.get("language") or "").strip(),
                    file_path=str(sn.get("file_path") or sn.get("file") or "").strip() or None,
                    content=str(sn.get("content") or sn.get("text") or ""),
                )

    # 1) Intake (store + embed so it can be fetched later by key)
    jira_tools.intake_issue_from_user_input(
        ctx={"inputs": {}, "steps": {}},
        issue_key=str(args.issue_key).strip(),
        summary=str(args.summary).strip(),
        domain=str(args.domain).strip() if args.domain else None,
        os=str(args.os_name).strip() if args.os_name else None,
        description=str(args.description).strip() if args.description else None,
        logs=logs_text,
    )

    # 2) Swarm analysis (reads back from DB)
    out = run_syscros_swarm(
        issue_key=str(args.issue_key).strip(),
        logs_file=str(args.logs_file).strip() if args.logs_file else None,
        domain=str(args.domain).strip() if args.domain else None,
        os_name=str(args.os_name).strip() if args.os_name else None,
        save_run=bool(args.save_run),
        config=SwarmConfig(
            limit=int(args.limit),
            min_local_score=float(args.min_local_score),
            external_knowledge=bool(args.external_knowledge),
            external_max_results=int(args.external_max_results),
        ),
    )

    report = out.get("report") or ""
    analysis = out.get("analysis") or ""
    if isinstance(report, str) and report.strip():
        print(report, end="" if report.endswith("\n") else "\n")
    if isinstance(analysis, str) and analysis.strip():
        print(analysis, end="" if analysis.endswith("\n") else "\n")
    if args.save_run and out.get("saved_run"):
        saved = out.get("saved_run") or {}
        print(f"\nSaved analysis run: id={saved.get('id')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

