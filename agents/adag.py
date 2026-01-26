"""
ADAG-style CLI wrapper for this repo.

Goal
----
Support a simple command like:

  cd agents
  python adag.py --prompt "Fetch and summarize: SYSCROS-123559" --save_trace

This is intentionally *offline-friendly*:
- It fetches the issue from local Postgres (jira_issues table), not from live JIRA.
- It can run with mock or SBERT embeddings (controlled by env vars).

What it does (flow)
-------------------
1) Parse CLI args
   - Reads --prompt
   - Enables trace-to-file if --save_trace is set
2) Build runtime + env
   - Adds repo /backend to sys.path so `from app...` imports work when running from `agents/`
   - Loads `.env` with override=False (shell vars win)
3) Route to "prompt agent" mode
   - Detects the JIRA key in the prompt (e.g., SYSCROS-123559)
   - Runs deterministic tool calls (no LLM tool-calling loop needed):
       jira.get_issue_from_db
       rag.search_similar_jira
       report.render_syscros_issue_summary
4) Print the final report (clean summary)
5) If --save_trace, write a markdown trace:
   - agents/traces/<run_id>.md

Notes
-----
If Gemini network/API is blocked, keep:
  $env:LLM_ENABLED="false"
or simply omit GEMINI_API_KEY; this prompt flow does not require the LLM.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


@dataclass
class TraceWriter:
    enabled: bool
    path: Optional[Path] = None

    def event(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled or not self.path:
            return
        payload = payload if isinstance(payload, dict) else {}
        ts = datetime.now(timezone.utc).isoformat()
        block = {
            "ts": ts,
            "event": name,
            "payload": payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"\n## {name}\n\n")
            f.write("```json\n")
            f.write(json.dumps(block, indent=2, ensure_ascii=False))
            f.write("\n```\n")


def _repo_root() -> Path:
    # agents/adag.py -> repo root is one level up from agents/
    return Path(__file__).resolve().parents[1]


def _setup_imports_and_env(repo_root: Path) -> None:
    # Make `from app...` work even when running from `agents/`.
    sys.path.insert(0, str(repo_root / "backend"))

    env_path = repo_root / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_path, override=False)
        except Exception:
            # If python-dotenv isn't installed, continue (env vars can be set in shell).
            pass


def _extract_jira_key(prompt: str) -> str:
    m = JIRA_KEY_RE.search(prompt or "")
    if not m:
        raise SystemExit(
            "Could not find a JIRA key in --prompt. Example: "
            '--prompt "Fetch and summarize: SYSCROS-123559"'
        )
    return m.group(0)


def _read_text_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        raise SystemExit(f"--logs-file not found: {p}")
    # Be robust to encoding issues; logs often contain mixed encodings.
    return p.read_text(encoding="utf-8", errors="replace")


def _run_fetch_and_summarize(*, issue_key: str, limit: int, trace: TraceWriter) -> str:
    """
    Deterministic "agent" that produces a clean summary.
    """
    from app.agents.tools import jira_tools

    ctx: Dict[str, Any] = {"inputs": {"issue_key": issue_key, "limit": limit}, "steps": {}}

    trace.event("tool_call", {"tool": "jira.get_issue_from_db", "issue_key": issue_key})
    issue = jira_tools.get_issue_from_db(ctx=ctx, issue_key=issue_key)
    ctx["steps"]["issue"] = issue

    # Similarity search is optional but cheap when embeddings are cached and stored locally.
    trace.event(
        "tool_call",
        {"tool": "rag.search_similar_jira", "limit": limit, "exclude_issue_keys": [issue_key]},
    )
    similar = jira_tools.search_similar_jira(
        ctx=ctx,
        query=str(issue.get("embedding_text") or ""),
        limit=int(limit),
        exclude_issue_keys=[issue_key],
    )
    ctx["steps"]["search"] = similar

    trace.event(
        "tool_call",
        {"tool": "report.render_syscros_issue_summary", "max_items": limit},
    )
    report = jira_tools.render_syscros_issue_summary_report(
        ctx=ctx, issue=issue, similar=similar, max_items=int(limit)
    )
    ctx["steps"]["report"] = report
    return report


def main() -> int:
    repo_root = _repo_root()
    _setup_imports_and_env(repo_root)

    parser = argparse.ArgumentParser(description="ADAG-style prompt runner (offline-friendly).")
    parser.add_argument("--prompt", required=True, help='Example: "Fetch and summarize: SYSCROS-123559"')
    parser.add_argument("--save_trace", action="store_true", help="Write a markdown trace under agents/traces/")
    parser.add_argument(
        "--logs-file",
        default=None,
        help="Optional path to logs.txt/.log. We extract error signatures for similarity search + root-cause summary.",
    )
    parser.add_argument("--limit", type=int, default=5, help="How many similar issues to show")
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Disable the root-cause analysis section (llm.subagent).",
    )
    args = parser.parse_args()

    run_id = uuid.uuid4().hex
    trace_path = repo_root / "agents" / "traces" / f"{run_id}.md"
    trace = TraceWriter(enabled=bool(args.save_trace), path=trace_path if args.save_trace else None)

    issue_key = _extract_jira_key(args.prompt)
    logs_text = ""
    log_signals: Dict[str, Any] = {}
    archived_logs_path: Optional[Path] = None
    if args.logs_file:
        logs_text = _read_text_file(str(args.logs_file))
        try:
            from app.agents.tools import log_tools

            log_signals = log_tools.extract_error_signals(ctx={"inputs": {}, "steps": {}}, text=logs_text)
        except Exception as e:
            log_signals = {"signals": [], "fingerprint": "", "query_text": "", "stats": {}, "error": str(e)}

        # Archive logs next to the trace (ignored by .gitignore) for local future reference
        if trace.enabled:
            archived_logs_path = repo_root / "agents" / "traces" / f"{run_id}.logs.txt"
            try:
                archived_logs_path.parent.mkdir(parents=True, exist_ok=True)
                # Avoid gigantic trace artifacts: keep up to 2MB from the end (typically contains the failure).
                max_bytes = 2_000_000
                data = logs_text.encode("utf-8", errors="replace")
                if len(data) > max_bytes:
                    data = data[-max_bytes:]
                archived_logs_path.write_bytes(data)
            except Exception:
                archived_logs_path = None

    trace.event(
        "run_start",
        {
            "run_id": run_id,
            "cwd": str(Path.cwd()),
            "prompt": args.prompt,
            "issue_key": issue_key,
            "limit": int(args.limit),
            "logs_file": str(args.logs_file) if args.logs_file else None,
            "log_fingerprint": (log_signals or {}).get("fingerprint") if args.logs_file else None,
            "env": {
                "EMBEDDING_PROVIDER": os.getenv("EMBEDDING_PROVIDER"),
                "USE_MOCK_EMBEDDING": os.getenv("USE_MOCK_EMBEDDING"),
                "EMBEDDING_CACHE_ENABLED": os.getenv("EMBEDDING_CACHE_ENABLED"),
                "LLM_ENABLED": os.getenv("LLM_ENABLED"),
            },
        },
    )

    # Step 1: fetch + similar + report
    report = _run_fetch_and_summarize(issue_key=issue_key, limit=int(args.limit), trace=trace)

    analysis = ""
    if not bool(args.no_analysis):
        try:
            from app.agents.tools import jira_tools, llm_tools

            # Re-run the deterministic steps, but keep data local so we can pass structured input.
            # (We avoid refactoring too much here; correctness > DRY for this small CLI.)
            ctx: Dict[str, Any] = {"inputs": {"issue_key": issue_key, "limit": int(args.limit)}, "steps": {}}
            issue = jira_tools.get_issue_from_db(ctx=ctx, issue_key=issue_key)

            query_text = str(issue.get("embedding_text") or "")
            if args.logs_file and isinstance(log_signals, dict):
                sig_q = str(log_signals.get("query_text") or "").strip()
                if sig_q:
                    query_text = (query_text + "\n\nLOG_ERROR_SIGNATURES:\n" + sig_q).strip()

            similar = jira_tools.search_similar_jira(
                ctx=ctx,
                query=query_text,
                limit=int(args.limit),
                exclude_issue_keys=[issue_key],
            )
            trace.event("tool_call", {"tool": "llm.subagent", "mode": "root_cause_summary"})
            analysis = llm_tools.subagent(
                ctx=ctx,
                prompts=[
                    "You are an expert debugging assistant. Produce a root-cause oriented summary for the target issue.",
                    f"Target issue key: {issue_key}. Use the target issue fields and the similar issues list as evidence. Do not invent details.",
                    "If logs/signatures are provided, treat them as the primary evidence for what failed and why.",
                    "Output (concise):",
                    "Probable root cause (ranked hypotheses + confidence 0-100)",
                    "Evidence (quotes/snippets from issue/comments)",
                    "Log evidence (specific error lines / exception names / error codes)",
                    "Next debugging steps (5-8)",
                    "Suggested fix/mitigation",
                ],
                input_data={
                    "issue": issue,
                    "similar": similar,
                    "log_signals": log_signals if args.logs_file else None,
                    # Tail only (avoid gigantic prompts even if LLM is enabled)
                    "logs_tail": "\n".join((logs_text or "").splitlines()[-400:]).rstrip() + "\n" if args.logs_file else None,
                },
            )
        except Exception as e:
            # Keep the CLI resilient; report is still useful even if analysis fails.
            trace.event("analysis_error", {"error": str(e)})
            analysis = ""

    trace.event(
        "run_complete",
        {"run_id": run_id, "report_chars": len(report or ""), "analysis_chars": len(analysis or "")},
    )

    print(report, end="" if report.endswith("\n") else "\n")
    if isinstance(analysis, str) and analysis.strip():
        print(analysis, end="" if analysis.endswith("\n") else "\n")
    if trace.enabled and trace.path:
        print(f"\n[trace] {trace.path}\n")
        if archived_logs_path:
            print(f"[logs]  {archived_logs_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

