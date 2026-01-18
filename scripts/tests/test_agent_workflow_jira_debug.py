"""
Smoke test: run the YAML "agent" workflow end-to-end using mock embeddings.

Flow:
  1) Ingest fixture CSV into DB (2 issues + embeddings)
  2) Run workflow: jira_debug_search.yaml

Run:
  python scripts/tests/test_agent_workflow_jira_debug.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    # Allow importing scripts.* as a namespace package (no __init__.py needed)
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "backend"))

    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)

    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")

    # 1) Ensure fixture is ingested
    import scripts.tests.test_ingest_sample_jira_csv as ingest_test  # type: ignore

    rc = ingest_test.main()
    if rc != 0:
        print("[FAIL] Fixture ingestion failed; cannot run workflow")
        return 1

    # 2) Run workflow
    from app.agents.tools.registry import build_default_tool_registry
    from app.agents.workflow_runner import run_workflow

    workflow = repo_root / "scripts" / "agent" / "workflows" / "jira_debug_search.yaml"
    tools = build_default_tool_registry()
    out = run_workflow(
        workflow,
        tools=tools,
        inputs={"query": "HDMI flicker after hotplug", "limit": 3},
    )

    search_out = (out.get("context") or {}).get("steps", {}).get("search") or {}
    results_count = search_out.get("results_count", 0) if isinstance(search_out, dict) else 0
    if not isinstance(results_count, int) or results_count <= 0:
        print("[FAIL] Expected workflow to return at least 1 similar issue")
        return 1

    report = (out.get("context") or {}).get("steps", {}).get("report")
    if not isinstance(report, str) or "Query:" not in report or "sim=" not in report:
        print("[FAIL] Expected a rendered report with similarity lines")
        return 1

    print("[OK] Agent workflow executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

