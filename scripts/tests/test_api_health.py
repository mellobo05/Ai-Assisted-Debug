"""
Smoke test: check the FastAPI server is up.

Run:
  python scripts/tests/test_api_health.py
"""

from __future__ import annotations

import sys

import httpx


API_BASE = "http://127.0.0.1:8000"


def main() -> int:
    try:
        r = httpx.get(f"{API_BASE}/docs", timeout=5)
        if r.status_code != 200:
            print(f"[FAIL] /docs returned {r.status_code}")
            return 1
        print("[OK] API is up (/docs 200)")
        return 0
    except Exception as e:
        print(f"[FAIL] Could not reach API at {API_BASE}: {e}")
        print("Start it with: .\\run_server.ps1")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

