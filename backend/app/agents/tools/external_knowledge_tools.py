from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Optional

import httpx


_DDG_RESULT_LINK_RE = re.compile(
    r"""<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_RE = re.compile(
    r"""<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    s = _TAG_RE.sub("", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def web_search(
    *,
    ctx: Dict[str, Any],
    query: str,
    max_results: int = 5,
    timeout_seconds: float = 8.0,
) -> Dict[str, Any]:
    """
    Lightweight external knowledge fetch (no API key).

    Notes:
    - This scrapes DuckDuckGo HTML results. It may be blocked in some networks.
    - Intended for *sanitized* queries (e.g. extracted error signatures), not raw logs.
    - Returns best-effort results; never raises on network errors (returns reason instead).
    """
    q = (query or "").strip()
    if not q:
        return {"query": "", "results": [], "provider": "duckduckgo_html", "error": "empty_query"}

    # Keep queries short and privacy-safe by default.
    q = q.replace("\r", " ").replace("\n", " ").strip()
    q = re.sub(r"\s+", " ", q)
    max_q = int(os.getenv("EXTERNAL_SEARCH_MAX_QUERY_CHARS", "350"))
    if len(q) > max_q:
        q = q[: max_q - 3] + "..."

    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": os.getenv(
            "EXTERNAL_SEARCH_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        )
    }

    try:
        with httpx.Client(timeout=float(timeout_seconds), headers=headers, follow_redirects=True) as client:
            resp = client.get(url, params={"q": q})
            resp.raise_for_status()
            html_text = resp.text or ""
    except Exception as e:
        # Do not break workflows/CLI; return a reason and let the pipeline continue.
        return {
            "query": q,
            "results": [],
            "provider": "duckduckgo_html",
            "error": f"{type(e).__name__}: {str(e).strip()}" if str(e).strip() else type(e).__name__,
        }

    links = list(_DDG_RESULT_LINK_RE.finditer(html_text))
    snippets = list(_DDG_SNIPPET_RE.finditer(html_text))

    results: List[Dict[str, Any]] = []
    n = min(int(max_results), 10)
    for i in range(min(len(links), n)):
        m = links[i]
        href = _strip_tags(m.group("href"))
        title = _strip_tags(m.group("title"))
        snippet = ""
        if i < len(snippets):
            snippet = _strip_tags(snippets[i].group("snippet"))

        if not title and not href:
            continue
        results.append({"title": title, "url": href, "snippet": snippet})

    return {"query": q, "results": results, "provider": "duckduckgo_html"}

