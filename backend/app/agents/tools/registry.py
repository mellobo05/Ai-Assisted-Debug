from __future__ import annotations

from typing import Any, Callable, Dict

from . import jira_tools


ToolFn = Callable[..., Any]


def build_default_tool_registry() -> Dict[str, ToolFn]:
    """
    Register the built-in tools available to workflows.

    Naming convention: "namespace.action"
    """
    return {
        # JIRA ingestion (live JIRA -> DB)
        "jira.sync": jira_tools.sync,
        # Similarity search (DB -> results)
        "rag.search_similar_jira": jira_tools.search_similar_jira,
        # Optional helper: pretty-print
        "report.render_similar_jira": jira_tools.render_similar_jira_report,
    }

