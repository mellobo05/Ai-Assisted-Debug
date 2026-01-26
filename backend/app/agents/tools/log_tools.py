from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_TS_PREFIX_RE = re.compile(
    r"""^(
        \[?\d{4}-\d{2}-\d{2}          # 2026-01-26
        (?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?   # optional time
        (?:Z|[+-]\d{2}:\d{2})?        # optional tz
        \]?
        |
        \[?\d{2}:\d{2}:\d{2}(?:\.\d+)?\]?      # 12:34:56(.789)
    )\s*""",
    re.VERBOSE,
)
_LEVEL_PREFIX_RE = re.compile(r"^(?:\[\w+\]|\w+)\s*[:\-]\s*", re.IGNORECASE)
_PY_TRACEBACK_RE = re.compile(r"^Traceback \(most recent call last\):\s*$")
_PY_FILE_LINE_RE = re.compile(r'^\s*File ".*?", line \d+, in .+\s*$')
_PY_EXCEPTION_LINE_RE = re.compile(r"^\s*([A-Za-z_]\w*(?:Error|Exception))(?::\s*(.*))?\s*$")
_JAVA_CAUSED_BY_RE = re.compile(r"^\s*Caused by:\s+(.+)\s*$")
_WINERROR_RE = re.compile(r"\bWinError\s*(\d+)\b", re.IGNORECASE)
_ERRNO_RE = re.compile(r"\berrno\s*[:=]?\s*(\d+)\b", re.IGNORECASE)
_HTTP_CODE_RE = re.compile(r"\b(4\d\d|5\d\d)\b")


def load_logs(
    *,
    ctx: Dict[str, Any],
    path: str,
    max_bytes: int = 2_000_000,
    tail_lines: int = 4000,
) -> Dict[str, Any]:
    """
    Load a log file from disk (safe for workflows).

    Returns:
      {
        "path": "...",
        "bytes": int,
        "truncated": bool,
        "text": "<full or truncated>",
        "tail": "<last N lines>",
      }
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        # Best-effort: allow relative paths from CWD
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        raise ValueError(f"Log file not found: {p}")

    data = p.read_bytes()
    truncated = False
    if len(data) > int(max_bytes):
        data = data[-int(max_bytes) :]
        truncated = True

    # Decode with replacement so we never crash on encoding issues.
    text = data.decode("utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-int(tail_lines) :]).rstrip() + "\n" if text else ""
    return {
        "path": str(p),
        "bytes": int(p.stat().st_size),
        "truncated": bool(truncated),
        "text": text,
        "tail": tail,
    }


def extract_error_signals(
    *,
    ctx: Dict[str, Any],
    text: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
    max_signals: int = 30,
    max_query_chars: int = 3500,
) -> Dict[str, Any]:
    """
    Convert raw logs into a compact set of high-signal "signatures" suitable for:
      - similarity search query text
      - LLM prompt context (short)
    """
    raw = ""
    if isinstance(text, str):
        raw = text
    elif isinstance(input_data, dict):
        # Accept output from load_logs
        raw = str(input_data.get("text") or input_data.get("tail") or "")

    lines = [l.rstrip("\n") for l in (raw or "").splitlines()]
    if not lines:
        return {
            "signals": [],
            "fingerprint": "",
            "query_text": "",
            "stats": {"lines": 0},
        }

    def _canon(line: str) -> str:
        s = line.strip()
        s = _TS_PREFIX_RE.sub("", s)
        s = _LEVEL_PREFIX_RE.sub("", s)
        # Collapse whitespace
        s = re.sub(r"\s+", " ", s).strip()
        # Avoid storing huge lines
        if len(s) > 400:
            s = s[:397] + "..."
        return s

    candidates: List[str] = []
    exceptions: List[str] = []
    winerrors: List[str] = []
    http_codes: List[str] = []

    in_traceback = False
    traceback_lines: List[str] = []

    for line in lines:
        s = _canon(line)
        if not s:
            continue

        if _PY_TRACEBACK_RE.match(line):
            in_traceback = True
            traceback_lines = ["Traceback (most recent call last):"]
            continue

        if in_traceback:
            if _PY_FILE_LINE_RE.match(line):
                # Keep file/line frames but canonicalize
                traceback_lines.append(_canon(line))
                continue
            m_exc = _PY_EXCEPTION_LINE_RE.match(line)
            if m_exc:
                exc_name = m_exc.group(1)
                msg = (m_exc.group(2) or "").strip()
                exceptions.append(exc_name + (f": {msg}" if msg else ""))
                traceback_lines.append(_canon(line))
                # end of traceback block
                in_traceback = False
                # Keep last few lines of traceback as a single signature
                tb_sig = " | ".join(traceback_lines[-6:])
                if tb_sig:
                    candidates.append(tb_sig)
                continue
            # Some other traceback line; keep a few
            if len(traceback_lines) < 12:
                traceback_lines.append(_canon(line))
            continue

        m_java = _JAVA_CAUSED_BY_RE.match(line)
        if m_java:
            candidates.append("Caused by: " + _canon(m_java.group(1)))

        m_we = _WINERROR_RE.search(line)
        if m_we:
            winerrors.append(f"WinError {m_we.group(1)}")

        m_errno = _ERRNO_RE.search(line)
        if m_errno:
            candidates.append(f"errno {m_errno.group(1)}")

        # Greedy but useful: "ERROR"/"FATAL"/exception-ish lines
        if any(k in s.lower() for k in ["error", "exception", "traceback", "fatal", "failed", "refused", "timeout"]):
            candidates.append(s)

        # HTTP response codes (best-effort)
        if any(k in s.lower() for k in ["http", "status", "response"]):
            m_code = _HTTP_CODE_RE.search(s)
            if m_code:
                http_codes.append(m_code.group(1))

        m_py_exc = _PY_EXCEPTION_LINE_RE.match(line)
        if m_py_exc:
            exc_name = m_py_exc.group(1)
            msg = (m_py_exc.group(2) or "").strip()
            exceptions.append(exc_name + (f": {msg}" if msg else ""))

    # Deduplicate with weighting by frequency
    counts = Counter([c for c in candidates if c])
    top = [s for s, _ in counts.most_common(max(10, int(max_signals)))]

    # Promote structured signals to the top
    def _uniq(xs: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for x in xs:
            x = (x or "").strip()
            if not x or x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    structured: List[str] = []
    structured += _uniq([e for e in exceptions])[:10]
    structured += _uniq([w for w in winerrors])[:5]
    structured += _uniq([f"HTTP {c}" for c in http_codes])[:5]

    # Merge, keep order (structured first), then most common candidates
    merged: List[str] = []
    seen = set()
    for s in structured + top:
        if s and s not in seen:
            seen.add(s)
            merged.append(s)
        if len(merged) >= int(max_signals):
            break

    query_text = "\n".join(merged).strip()
    if len(query_text) > int(max_query_chars):
        query_text = query_text[: int(max_query_chars) - 3] + "..."

    h = hashlib.sha256(query_text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    # Optional env to include hostname in fingerprint for local collisions
    host = os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or ""
    fingerprint = (h + ("-" + hashlib.sha256(host.encode("utf-8")).hexdigest()[:6] if host else "")).strip("-")

    return {
        "signals": merged,
        "fingerprint": fingerprint,
        "query_text": query_text,
        "stats": {"lines": len(lines), "candidates": len(candidates)},
    }

