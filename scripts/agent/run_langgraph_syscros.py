"""
LangChain/LangGraph-based agent runner for the SYSCROS issue summary workflow.

This uses the existing repo tools (app.agents.tools.jira_tools) but orchestrates
them using LangGraph state transitions instead of the custom YAML runner.

Example:
  python scripts/agent/run_langgraph_syscros.py --issue-key SYSCROS-131125 --limit 5
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

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


class SyscrosState(TypedDict, total=False):
    issue_key: str
    limit: int
    # ctx compatible with existing tools signature
    ctx: Dict[str, Any]
    issue: Dict[str, Any]
    search: Dict[str, Any]
    report: str


def _build_tools():
    # Import lazily after PYTHONPATH is set.
    from langchain_core.tools import tool

    from app.agents.tools import jira_tools

    @tool("jira.get_issue_from_db")
    def get_issue_from_db(*, issue_key: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch a JIRA issue from local Postgres and return a compact dict + embedding_text."""
        return jira_tools.get_issue_from_db(ctx=ctx, issue_key=issue_key)

    @tool("rag.search_similar_jira")
    def search_similar_jira(
        *,
        query: str,
        limit: int,
        exclude_issue_keys: Optional[list[str]] = None,
        ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Search similar JIRA issues from DB using embeddings."""
        return jira_tools.search_similar_jira(ctx=ctx, query=query, limit=limit, exclude_issue_keys=exclude_issue_keys)

    @tool("report.render_syscros_issue_summary")
    def render_syscros_issue_summary(*, issue: Dict[str, Any], similar: Dict[str, Any] | None, max_items: int, ctx: Dict[str, Any]) -> str:
        """Render the SYSCROS report from the issue dict and similarity results."""
        return jira_tools.render_syscros_issue_summary_report(ctx=ctx, issue=issue, similar=similar, max_items=max_items)

    return {"get_issue": get_issue_from_db, "search_similar": search_similar_jira, "render_report": render_syscros_issue_summary}


def main() -> int:
    _setup_imports_and_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-key", required=True, help="JIRA issue key (e.g., SYSCROS-131125)")
    parser.add_argument("--limit", type=int, default=5, help="Top-k similar issues to include")
    args = parser.parse_args()

    # Import after deps are present.
    from langgraph.graph import END, StateGraph

    tools = _build_tools()

    def node_init(state: SyscrosState) -> SyscrosState:
        issue_key = str(state.get("issue_key") or "").strip()
        limit = int(state.get("limit") or 5)
        return {
            "issue_key": issue_key,
            "limit": limit,
            "ctx": {"inputs": {"issue_keys": [issue_key], "limit": limit}, "steps": {}},
        }

    def node_get_issue(state: SyscrosState) -> SyscrosState:
        out = tools["get_issue"].invoke({"issue_key": state["issue_key"], "ctx": state["ctx"]})
        state["ctx"]["steps"]["issue"] = out
        return {"issue": out, "ctx": state["ctx"]}

    def node_search(state: SyscrosState) -> SyscrosState:
        query = (state.get("issue") or {}).get("embedding_text") or ""
        out = tools["search_similar"].invoke(
            {
                "query": query,
                "limit": state["limit"],
                "exclude_issue_keys": [state["issue_key"]],
                "ctx": state["ctx"],
            }
        )
        state["ctx"]["steps"]["search"] = out
        return {"search": out, "ctx": state["ctx"]}

    def node_render(state: SyscrosState) -> SyscrosState:
        out = tools["render_report"].invoke(
            {
                "issue": state.get("issue") or {},
                "similar": state.get("search"),
                "max_items": state["limit"],
                "ctx": state["ctx"],
            }
        )
        state["ctx"]["steps"]["report"] = out
        return {"report": out, "ctx": state["ctx"]}

    g = StateGraph(SyscrosState)
    g.add_node("init", node_init)
    g.add_node("get_issue", node_get_issue)
    # NOTE: LangGraph disallows node names that collide with state keys.
    # Our state includes keys like "search" and "report", so keep node names distinct.
    g.add_node("do_search", node_search)
    g.add_node("do_render", node_render)

    g.set_entry_point("init")
    g.add_edge("init", "get_issue")
    g.add_edge("get_issue", "do_search")
    g.add_edge("do_search", "do_render")
    g.add_edge("do_render", END)

    app = g.compile()
    try:
        final: SyscrosState = app.invoke({"issue_key": str(args.issue_key).strip(), "limit": int(args.limit)})
    except Exception as e:
        print(f"[ERROR] LangGraph run failed: {e}")
        print("If you see 'Issue not found in DB', ingest/sync the issue first into Postgres.")
        return 2

    report = final.get("report")
    if report:
        print(report, end="" if str(report).endswith("\n") else "\n")
        return 0

    print("No report generated.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

