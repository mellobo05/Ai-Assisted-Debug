from __future__ import annotations

"""
Wrapper for clean_jira_csv functionality.

Usage:
  python scripts/jira/clean_csv.py <input.csv> [output.csv]
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from clean_jira_csv import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

