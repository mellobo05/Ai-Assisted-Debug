"""
Run a "swarm" agent locally: multiple specialist agents in parallel + aggregator.

Example (from repo root):
  python scripts/agent/run_swarm.py --issue-key SYSCROS-131125 --limit 5

With logs + optional external knowledge fallback:
  python scripts/agent/run_swarm.py --issue-key SYSCROS-131125 --logs-file logs/hevc_fatcat.txt --external-knowledge
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _setup_imports_and_env() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "backend"))

    env_path = repo_root / ".env"
    if env_path.exists():
        # Match the rest of the repo behavior: do not override shell env vars.
        load_dotenv(dotenv_path=env_path, override=False)

    # Default to mock embeddings for local runs unless explicitly disabled.
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    return repo_root


def main() -> int:
    _setup_imports_and_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-key", required=True, help="JIRA issue key (e.g., SYSCROS-131125)")
    parser.add_argument("--limit", type=int, default=5, help="Top-k similar issues to include")
    parser.add_argument("--domain", default=None, help="Optional domain hint (e.g., media)")
    parser.add_argument("--os", dest="os_name", default=None, help="Optional OS hint (e.g., Windows, ChromeOS)")
    parser.add_argument("--logs-file", default=None, help="Optional path to logs file for error signature extraction")
    parser.add_argument("--external-knowledge", action="store_true", help="Enable external web search fallback (privacy-safe)")
    parser.add_argument("--min-local-score", type=float, default=0.62, help="Trigger external search if top score < this")
    parser.add_argument("--external-max-results", type=int, default=5, help="Max external references when fallback triggers")
    parser.add_argument("--save-run", action="store_true", help="Persist analysis output to DB (jira_analysis_runs)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print full JSON output (debugging)")
    args = parser.parse_args()

    from app.agents.swarm import SwarmConfig, run_syscros_swarm

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

    if bool(args.as_json):
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    report = out.get("report") or ""
    analysis = out.get("analysis") or ""
    if isinstance(report, str) and report.strip():
        print(report, end="" if report.endswith("\n") else "\n")
    if isinstance(analysis, str) and analysis.strip():
        print(analysis, end="" if analysis.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

