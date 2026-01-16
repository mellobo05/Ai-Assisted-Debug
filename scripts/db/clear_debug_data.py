from __future__ import annotations

"""
Wrapper for clear_debug_data functionality.

Usage:
  python scripts/db/clear_debug_data.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from clear_debug_data import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

