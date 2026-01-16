from __future__ import annotations

"""
Wrapper for migrate_jira_tables functionality.

Usage:
  python scripts/db/migrate_jira_tables.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from migrate_jira_tables import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

