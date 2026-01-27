from __future__ import annotations

"""
Initialize database tables (wrapper).

Usage (from repo root):
  python scripts/db/init_db.py

This avoids fiddling with PYTHONPATH on Windows.
"""

from pathlib import Path
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "backend"))
    # Load .env if present (do not override shell env vars).
    env_path = repo_root / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv(dotenv_path=env_path, override=False)
        except Exception:
            pass

    from app.db.init_db import init_db  # noqa: E402

    init_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

