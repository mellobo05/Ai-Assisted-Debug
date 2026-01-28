from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SwarmConfig:
    """
    Swarm = multiple specialist "agents" run in parallel + an aggregator.

    This is intentionally lightweight and reuses existing repo tools:
      - jira_tools.get_issue_from_db
      - jira_tools.search_similar_jira
      - jira_tools.render_syscros_issue_summary_report
      - log_tools.load_logs / extract_error_signals
      - external_knowledge_tools.web_search
      - llm_tools.subagent (optional; has offline fallback)
    """

    limit: int = 5
    min_local_score: float = 0.62
    external_knowledge: bool = False
    external_max_results: int = 5
    max_workers: int = 4


def _top_similarity(similar: Any) -> float:
    try:
        results = similar.get("results") if isinstance(similar, dict) else None
        if isinstance(results, list) and results:
            return float((results[0] or {}).get("similarity", 0.0))
    except Exception:
        return 0.0
    return 0.0


def _build_sources_header(*, top_sim: float, min_local_score: float, external_refs: Optional[Dict[str, Any]]) -> str:
    lines = [f"Sources: internal JIRA DB embeddings (top_score={top_sim:.3f}, threshold={float(min_local_score):.2f})"]
    if isinstance(external_refs, dict) and external_refs:
        ext_results = external_refs.get("results") if isinstance(external_refs.get("results"), list) else []
        ext_error = external_refs.get("error")
        if ext_results:
            lines.append(f"Sources: external web search used (hits={len(ext_results)})")
        elif ext_error:
            lines.append(f"Sources: external web search attempted but failed ({ext_error})")
        else:
            lines.append("Sources: external web search attempted but returned 0 results")
    else:
        lines.append("Sources: external web search skipped (not enabled or not needed)")
    return "\n".join(lines).rstrip() + "\n\n"


def run_syscros_swarm(
    *,
    issue_key: str,
    logs_file: Optional[str] = None,
    config: Optional[SwarmConfig] = None,
) -> Dict[str, Any]:
    """
    Swarm runner for the common "SYSCROS issue summary + root cause" flow.

    Returns a structured dict:
      {
        "issue": {...},
        "log_signals": {...} | None,
        "similar": {...} | None,
        "external_refs": {...} | None,
        "report": "...",
        "analysis": "...",
        "meta": {...}
      }
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.agents.tools import external_knowledge_tools, jira_tools, llm_tools, log_tools

    cfg = config or SwarmConfig()
    key = str(issue_key or "").strip()
    if not key:
        raise ValueError("issue_key is required")

    ctx: Dict[str, Any] = {"inputs": {"issue_key": key, "limit": int(cfg.limit), "logs_file": logs_file}, "steps": {}}

    def agent_fetch_issue() -> Dict[str, Any]:
        issue = jira_tools.get_issue_from_db(ctx=ctx, issue_key=key)
        ctx["steps"]["issue"] = issue
        return issue

    def agent_logs_signals() -> Optional[Dict[str, Any]]:
        if not logs_file:
            return None
        loaded = log_tools.load_logs(ctx=ctx, path=str(logs_file))
        signals = log_tools.extract_error_signals(ctx=ctx, input_data=loaded)
        # Keep a short tail for prompting/inspection
        signals["logs_tail"] = str(loaded.get("tail") or "")
        ctx["steps"]["log_signals"] = signals
        return signals

    # Stage 1: independent specialists (parallel)
    with ThreadPoolExecutor(max_workers=int(cfg.max_workers)) as ex:
        fut_issue = ex.submit(agent_fetch_issue)
        fut_logs = ex.submit(agent_logs_signals)
        issue = fut_issue.result()
        log_signals = fut_logs.result()

        # Stage 2: similarity (depends on issue + optional logs)
        def agent_similarity() -> Dict[str, Any]:
            query_text = str(issue.get("embedding_text") or "").strip()
            if isinstance(log_signals, dict):
                sig_q = str(log_signals.get("query_text") or "").strip()
                if sig_q:
                    query_text = (query_text + "\n\nLOG_ERROR_SIGNATURES:\n" + sig_q).strip()
            similar = jira_tools.search_similar_jira(
                ctx=ctx,
                query=query_text,
                limit=int(cfg.limit),
                exclude_issue_keys=[key],
            )
            ctx["steps"]["similar"] = similar
            return similar

        fut_sim = ex.submit(agent_similarity)
        similar = fut_sim.result()

        # Stage 3: external knowledge (optional; depends on similarity)
        external_refs: Optional[Dict[str, Any]] = None
        top_sim = _top_similarity(similar)
        should_external = bool(cfg.external_knowledge) and (top_sim < float(cfg.min_local_score))
        if should_external:

            def agent_external() -> Dict[str, Any]:
                q = ""
                if isinstance(log_signals, dict):
                    q = str(log_signals.get("query_text") or "").strip()
                if not q:
                    q = " ".join(str(issue.get("embedding_text") or "").split())[:300]
                return external_knowledge_tools.web_search(
                    ctx=ctx,
                    query=q,
                    max_results=int(cfg.external_max_results),
                )

            external_refs = ex.submit(agent_external).result()
            ctx["steps"]["external_refs"] = external_refs

    # Aggregation: report + analysis
    report = jira_tools.render_syscros_issue_summary_report(
        ctx=ctx,
        issue=issue,
        similar=similar,
        max_items=int(cfg.limit),
    )
    ctx["steps"]["report"] = report

    sources_header = _build_sources_header(
        top_sim=_top_similarity(similar),
        min_local_score=float(cfg.min_local_score),
        external_refs=external_refs,
    )

    # Keep prompt size controlled: logs tail + compact signatures
    logs_tail = ""
    if isinstance(log_signals, dict):
        logs_tail = "\n".join(str(log_signals.get("logs_tail") or "").splitlines()[-400:]).rstrip() + "\n"

    analysis = llm_tools.subagent(
        ctx=ctx,
        prompts=[
            "Start your output with the provided Sources lines (do not omit them).",
            "You are an expert debugging assistant. Produce a root-cause oriented summary for the target issue.",
            f"Target issue key: {key}. Use the target issue fields, log signals, and the similar issues list as evidence. Do not invent details.",
            "If logs/signatures are provided, treat them as the primary evidence for what failed and why.",
            "If external references are provided, use them only as supporting context and clearly label them as external (not confirmed).",
            "Output (concise):",
            "Probable root cause (ranked hypotheses + confidence 0-100)",
            "Evidence (quotes/snippets from issue/comments)",
            "Log evidence (specific error lines / exception names / error codes)",
            "External references (titles only)",
            "Next debugging steps (5-8)",
            "Suggested fix/mitigation",
        ],
        input_data={
            "sources_header": sources_header.strip(),
            "issue": issue,
            "similar": similar,
            "log_signals": log_signals,
            "logs_tail": logs_tail if logs_tail else None,
            "external_refs": external_refs,
            "local_top_similarity": float(_top_similarity(similar)),
            "min_local_score": float(cfg.min_local_score),
        },
    )
    if isinstance(analysis, str) and analysis.strip() and not analysis.lstrip().startswith("Sources:"):
        analysis = sources_header + analysis.lstrip()
    ctx["steps"]["analysis"] = analysis

    return {
        "issue": issue,
        "log_signals": log_signals,
        "similar": similar,
        "external_refs": external_refs,
        "report": report,
        "analysis": analysis,
        "meta": {
            "issue_key": key,
            "limit": int(cfg.limit),
            "min_local_score": float(cfg.min_local_score),
            "external_knowledge": bool(cfg.external_knowledge),
            "external_max_results": int(cfg.external_max_results),
        },
    }

