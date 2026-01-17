"""
Smoke test: call /search and ensure we get at least 1 JIRA result.

Run:
  python scripts/tests/test_search_jira.py
"""

from __future__ import annotations

import httpx


API_BASE = "http://127.0.0.1:8000"


def main() -> int:
    query = "video flicker external display"
    payload = {"query": query, "limit": 5}

    try:
        r = httpx.post(f"{API_BASE}/search", json=payload, timeout=30)
    except Exception as e:
        print(f"[FAIL] Could not call /search: {e}")
        print("Start backend with: .\\run_server.ps1")
        return 1

    if r.status_code != 200:
        print(f"[FAIL] /search returned {r.status_code}: {r.text}")
        return 1

    data = r.json()
    results = data.get("results") or []
    print(f"[INFO] results_count={data.get('results_count')} query='{query}'")

    if not results:
        print("[FAIL] No results returned. Ensure JIRA issues were ingested.")
        return 1

    top = results[0]
    print(f"[OK] Top result: {top.get('issue_key')} score={top.get('similarity')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

