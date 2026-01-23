from __future__ import annotations

from typing import Any, Dict, List, Optional


def subagent(
    *,
    ctx: Dict[str, Any],
    prompts: List[str],
    input_data: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> str:
    """
    ADA/ADAG-style "subagent" step.

    If GEMINI_API_KEY is configured, this will call Gemini to produce an analysis.
    Otherwise it returns a deterministic, offline-friendly fallback summary.

    Parameters:
      - prompts: list[str] instructions (YAML-friendly)
      - input_data: optional dict payload (e.g., {"issue": {...}, "similar": {...}})
    """
    import os

    prompt_text = "\n\n".join([str(p) for p in (prompts or []) if str(p).strip()]).strip()
    payload = input_data if isinstance(input_data, dict) else {}

    def _offline_fallback(*, reason: str) -> str:
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        similar = payload.get("similar") if isinstance(payload.get("similar"), dict) else {}
        results = similar.get("results") if isinstance(similar.get("results"), list) else []

        debug_prompts = os.getenv("LLM_SUBAGENT_DEBUG", "false").strip().lower() == "true"

        lines: List[str] = []
        # Keep this output short and action-oriented (like ADAG).
        lines.append(f"Analysis: skipped LLM ({reason})")
        if issue:
            lines.append(f"Target: {issue.get('issue_key')} — {(issue.get('summary') or '').strip()}")
        if results:
            lines.append("Top matches:")
            for i, r in enumerate(results[:10], start=1):
                try:
                    sim = float(r.get("similarity", 0.0))
                except Exception:
                    sim = 0.0
                lines.append(f"{i}. {r.get('issue_key')}  score={sim*100.0:.1f}  {(r.get('summary') or '').strip()}".rstrip())

        # Optional debug: print the original instructions when explicitly requested.
        if debug_prompts and prompt_text:
            lines.append("")
            lines.append("Debug: instructions")
            lines.append(prompt_text)

        return "\n".join(lines).rstrip() + "\n"

    # Hard disable (useful for offline / corporate proxy environments)
    if os.getenv("LLM_ENABLED", "true").strip().lower() != "true":
        return _offline_fallback(reason="LLM is disabled (LLM_ENABLED!=true).")

    # Offline fallback (no API key)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _offline_fallback(reason="LLM is not configured (missing GEMINI_API_KEY).")
    # Optional fast-disable if you know your network blocks Gemini:
    #   $env:LLM_ENABLED="false"

    # Gemini path
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:
        return _offline_fallback(reason=f"LLM deps missing ({e}).")

    genai.configure(api_key=api_key)
    model_name = model or os.getenv("LLM_MODEL", "gemini-1.5-flash")
    m = genai.GenerativeModel(model_name)

    # Keep the prompt readable and structured.
    full_prompt = (
        "You are an expert debugging assistant. Follow the instructions carefully.\n\n"
        f"INSTRUCTIONS:\n{prompt_text or '(none)'}\n\n"
        f"INPUT_DATA (JSON-ish):\n{payload}\n"
    )
    try:
        # Best-effort timeout: run the call in a background thread and return fallback if it exceeds.
        # This avoids long hangs on blocked networks (Windows-friendly; no signals).
        import concurrent.futures

        try:
            timeout_s = float(os.getenv("LLM_NETWORK_TIMEOUT_SECONDS", "15"))
        except Exception:
            timeout_s = 15.0

        def _do_call() -> str:
            resp = m.generate_content(full_prompt, generation_config={"temperature": float(temperature)})
            return (getattr(resp, "text", None) or "").strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_do_call)
            text = fut.result(timeout=timeout_s)
            return (text.strip() + "\n") if text else "\n"
    except Exception as e:
        return _offline_fallback(reason=f"LLM call failed ({e}).")


