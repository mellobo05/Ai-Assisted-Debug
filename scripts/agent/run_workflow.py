"""
Run a YAML workflow ("agent") locally.

Examples (from repo root):
  python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_debug_search.yaml --query "HDMI flicker" --limit 5
  python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_sync_and_search.yaml --issue-key SYSCROS-131125 --query "similar issues" --limit 5
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
        load_dotenv(dotenv_path=env_path, override=True)

    # Default to mock embeddings for local workflows unless explicitly disabled.
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    return repo_root


def main() -> int:
    _setup_imports_and_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, help="Path to workflow YAML")
    parser.add_argument("--query", default="", help="Search query text")
    parser.add_argument("--limit", type=int, default=5, help="Top-k results")

    parser.add_argument("--issue-key", action="append", dest="issue_keys", help="JIRA issue key (repeatable)")
    parser.add_argument("--jql", default=None, help="JQL to sync issues (optional)")
    parser.add_argument("--max-results", type=int, default=25)
    parser.add_argument("--max-comments", type=int, default=25)

    args = parser.parse_args()

    from app.agents.tools.registry import build_default_tool_registry
    from app.agents.workflow_runner import run_workflow

    tools = build_default_tool_registry()

    inputs = {
        "query": args.query,
        "limit": args.limit,
        "issue_keys": args.issue_keys,
        "jql": args.jql,
        "max_results": args.max_results,
        "max_comments": args.max_comments,
    }

    out = run_workflow(args.workflow, tools=tools, inputs=inputs)

    # If the workflow produced a rendered report in ctx.steps.report, print it.
    report = (out.get("context") or {}).get("steps", {}).get("report")
    if isinstance(report, str) and report.strip():
        print(report, end="" if report.endswith("\n") else "\n")
        return 0

    # Otherwise, print the full output (still useful for debugging).
    import json

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

