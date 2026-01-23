"""
Run a YAML workflow ("agent") locally.

Examples (from repo root):
  python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_debug_search.yaml --query "HDMI flicker" --limit 5
  python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_sync_and_search.yaml --issue-key SYSCROS-131125 --query "similar issues" --limit 5
  python scripts/agent/run_workflow.py --workflow-file scripts/agent/workflows/jira_similar_issues_finder.yaml --workflow-params target_jira_key=SYSCROS-131125 project=SYSCROS search_days=365 max_results=20 similarity_threshold=60
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
        # Match the rest of the repo behavior: do not override shell env vars.
        load_dotenv(dotenv_path=env_path, override=False)

    # Default to mock embeddings for local workflows unless explicitly disabled.
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    return repo_root


def main() -> int:
    _setup_imports_and_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", help="Path to workflow YAML (legacy flag; use --workflow-file)")
    parser.add_argument("--workflow-file", dest="workflow_file", help="Path to workflow YAML")
    parser.add_argument(
        "--workflow-params",
        nargs="*",
        default=[],
        help="Workflow params as key=value pairs (ADAG-style). Example: target_jira_key=SYSCROS-1 search_days=365",
    )
    parser.add_argument("--query", default="", help="Search query text")
    parser.add_argument("--limit", type=int, default=5, help="Top-k results")

    parser.add_argument("--issue-key", action="append", dest="issue_keys", help="JIRA issue key (repeatable)")
    parser.add_argument("--jql", default=None, help="JQL to sync issues (optional)")
    parser.add_argument("--max-results", type=int, default=25)
    parser.add_argument("--max-comments", type=int, default=25)

    args = parser.parse_args()
    workflow_path = args.workflow_file or args.workflow
    if not workflow_path:
        raise SystemExit("Provide --workflow-file (preferred) or --workflow")

    workflow_params = {}
    for kv in args.workflow_params or []:
        if "=" not in str(kv):
            raise SystemExit(f"Invalid --workflow-params entry '{kv}'. Expected key=value.")
        k, v = str(kv).split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        # Best-effort scalar parsing (int/float/bool); otherwise keep string.
        if v.lower() in {"true", "false"}:
            workflow_params[k] = (v.lower() == "true")
        else:
            try:
                workflow_params[k] = int(v)
            except Exception:
                try:
                    workflow_params[k] = float(v)
                except Exception:
                    workflow_params[k] = v

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
    # ADAG-style: merge workflow params into inputs so YAML can reference ${target_jira_key}, ${project}, etc.
    inputs.update(workflow_params)

    out = run_workflow(workflow_path, tools=tools, inputs=inputs)

    # Print common outputs if present (ADAG-like).
    steps = (out.get("context") or {}).get("steps", {}) or {}
    report = steps.get("report")
    analysis = steps.get("analysis")
    if isinstance(report, str) and report.strip():
        print(report, end="" if report.endswith("\n") else "\n")
    if isinstance(analysis, str) and analysis.strip():
        # Separate sections so it reads like ADAG output.
        print(analysis, end="" if analysis.endswith("\n") else "\n")
    if (isinstance(report, str) and report.strip()) or (isinstance(analysis, str) and analysis.strip()):
        return 0

    # Otherwise, print the full output (still useful for debugging).
    import json

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

