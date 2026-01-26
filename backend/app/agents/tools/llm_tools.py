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

    def _format_exc(e: BaseException) -> str:
        """
        Make failures understandable even when the exception message is empty
        (common for some TimeoutError/CancelledError variants).
        """
        try:
            msg = str(e).strip()
        except Exception:
            msg = ""
        name = type(e).__name__
        return f"{name}: {msg}" if msg else name

    def _offline_fallback(*, reason: str) -> str:
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        similar = payload.get("similar") if isinstance(payload.get("similar"), dict) else {}
        results = similar.get("results") if isinstance(similar.get("results"), list) else []
        log_signals = payload.get("log_signals") if isinstance(payload.get("log_signals"), dict) else {}
        log_signal_lines = log_signals.get("signals") if isinstance(log_signals.get("signals"), list) else []
        external_refs = payload.get("external_refs") if isinstance(payload.get("external_refs"), dict) else {}
        external_results = (
            external_refs.get("results") if isinstance(external_refs.get("results"), list) else []
        )
        external_error = external_refs.get("error") if isinstance(external_refs, dict) else None
        try:
            top_sim = float(payload.get("local_top_similarity", 0.0))
        except Exception:
            top_sim = 0.0
        try:
            min_score = float(payload.get("min_local_score", 0.0))
        except Exception:
            min_score = 0.0

        debug_prompts = os.getenv("LLM_SUBAGENT_DEBUG", "false").strip().lower() == "true"

        def _snip(text: Any, n: int) -> str:
            s = (str(text or "")).strip().replace("\n", " ")
            return (s[: n - 3] + "...") if len(s) > n else s

        def _guess_hypotheses() -> list[str]:
            """
            Lightweight, offline heuristic hints. This is NOT a real LLM.
            We try to extract signals from summary/description/comments.
            """
            # Combine signals from issue + latest comment + extracted log signatures (if provided).
            s = " ".join(
                [
                    str(issue.get("summary") or ""),
                    str(issue.get("description") or ""),
                    str(issue.get("latest_comment") or ""),
                    " ".join([str(x) for x in log_signal_lines[:30]]),
                ]
            ).lower()
            hyps: list[str] = []

            # Codec / decode failures (common in media pipelines)
            if any(
                k in s
                for k in [
                    "decodererror",
                    "decode error",
                    "decoding error",
                    "cros-codecs",
                    "codec",
                    "hevc",
                    "h.265",
                    "transcoding",
                    "vaapi",
                    "v4l2",
                ]
            ):
                hyps.append(
                    "Media codec/decoder pipeline failure (e.g., cros-codecs DecoderError) — likely codec support/regression/driver/firmware issue; check decoder logs, codec capabilities, and recent media stack changes."
                )

            if any(k in s for k in ["needs enablement", "enablement", "feature flag", "flag", "server-side", "upstream"]):
                hyps.append("Feature/enablement is disabled or gated upstream (check flags, policies, remote config).")
            if any(k in s for k in ["not enabled", "disabled", "not working", "fails to", "unable to"]):
                hyps.append("Capability negotiation/config mismatch (check runtime config, codecs/features negotiated, permissions).")
            if any(k in s for k in ["timeout", "hang", "stuck", "deadlock"]):
                hyps.append("Timeout/hang likely due to blocking call or network/proxy issue (check logs, timeouts, DNS).")
            if any(k in s for k in ["crash", "segfault", "null pointer", "assert", "exception", "stack trace"]):
                hyps.append("Runtime crash/exception (look for stack traces and recent code changes/regressions).")
            if any(k in s for k in ["ssl", "certificate", "handshake", "proxy", "forbidden", "unauthorized", "auth"]):
                hyps.append("Connectivity/auth/proxy/cert issue (verify network route, cert chain, and credentials).")

            if not hyps:
                hyps.append("Insufficient evidence offline — collect logs, repro steps, and exact error messages.")
            return hyps[:3]

        lines: List[str] = []
        # Keep this output short and action-oriented (like ADAG).
        lines.append(f"Analysis: skipped LLM ({reason})")
        lines.append(
            f"Sources: internal JIRA DB embeddings (top_score={top_sim:.3f}, threshold={min_score:.2f})"
        )
        if external_refs:
            if external_results:
                lines.append(f"Sources: external web search used (hits={len(external_results)})")
            elif external_error:
                lines.append(f"Sources: external web search attempted but failed ({external_error})")
            else:
                lines.append("Sources: external web search attempted but returned 0 results")
        if issue:
            lines.append(f"Target: {issue.get('issue_key')} — {(issue.get('summary') or '').strip()}")
            comps = issue.get("components") if isinstance(issue.get("components"), list) else []
            if comps:
                lines.append(f"Components: {', '.join([str(c) for c in comps if str(c).strip()])}")
            if issue.get("latest_comment"):
                lines.append(f"Latest comment (snippet): {_snip(issue.get('latest_comment'), 220)}")

            # Surface the most important extracted signals (helps explain why a hypothesis was chosen).
            if log_signal_lines:
                lines.append(f"Log signals (top): {_snip(' | '.join([str(x) for x in log_signal_lines[:6]]), 240)}")

            lines.append("")
            lines.append("Probable root cause (offline hints):")
            for i, h in enumerate(_guess_hypotheses(), start=1):
                lines.append(f"{i}. {h}")
        if results:
            lines.append("")
            lines.append("Top matches:")
            for i, r in enumerate(results[:10], start=1):
                try:
                    sim = float(r.get("similarity", 0.0))
                except Exception:
                    sim = 0.0
                lines.append(f"{i}. {r.get('issue_key')}  score={sim*100.0:.1f}  {(r.get('summary') or '').strip()}".rstrip())
            lines.append("")
            lines.append("Next debugging steps (generic):")
            lines.append("- Reproduce with timestamps + collect relevant logs for the failing window.")
            lines.append("- Confirm environment details (OS/build/version, device, codec/feature flags, network/proxy).")
            lines.append("- Search logs for explicit errors/warnings; attach the exact first failure.")
            lines.append("- Compare against the closest historical match; diff configuration and recent changes.")

        if external_results:
            lines.append("")
            lines.append("External references (titles):")
            for i, r in enumerate(external_results[:10], start=1):
                title = (r or {}).get("title") if isinstance(r, dict) else ""
                title = (str(title or "")).strip()
                if title:
                    lines.append(f"- {title}")

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
        return _offline_fallback(reason=f"LLM call failed ({_format_exc(e)}).")


