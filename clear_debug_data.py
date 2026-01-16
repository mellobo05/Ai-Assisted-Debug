"""
Delete all custom debug session data so JIRA becomes the primary retrieval source.

This deletes:
  - debug_embeddings
  - debug_sessions

Run from project root:
  python clear_debug_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent / "backend"))

    from sqlalchemy import text
    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM debug_embeddings;"))
        conn.execute(text("DELETE FROM debug_sessions;"))

    print("[CLEAR] Deleted all rows from debug_embeddings and debug_sessions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

