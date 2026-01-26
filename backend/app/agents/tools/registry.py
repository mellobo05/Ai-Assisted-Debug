from __future__ import annotations

from typing import Any, Callable, Dict

from . import jira_tools
from . import llm_tools
from . import log_tools


ToolFn = Callable[..., Any]


def build_default_tool_registry() -> Dict[str, ToolFn]:
    """
    Register the built-in tools available to workflows.

    Naming convention: "namespace.action"
    """
    return {
        # Offline DB fetch
        "jira.get_issue_from_db": jira_tools.get_issue_from_db,
        # Re-embed issues already stored in DB (useful after embedding provider changes)
        "jira.reembed_from_db": jira_tools.reembed_from_db,
        # JIRA ingestion (live JIRA -> DB)
        "jira.sync": jira_tools.sync,
        # Similarity search (DB -> results)
        "rag.search_similar_jira": jira_tools.search_similar_jira,
        # Optional helper: pretty-print
        "report.render_similar_jira": jira_tools.render_similar_jira_report,
        "report.render_syscros_issue_summary": jira_tools.render_syscros_issue_summary_report,
        "report.render_reembed": jira_tools.render_reembed_report,
        # Optional LLM "subagent" analysis step (falls back gracefully if no GEMINI_API_KEY)
        "llm.subagent": llm_tools.subagent,
        # Logs -> compact signatures (for similarity search + analysis)
        "log.load": log_tools.load_logs,
        "log.extract_error_signals": log_tools.extract_error_signals,
    }

