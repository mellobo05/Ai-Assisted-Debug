from __future__ import annotations

"""
Wrapper for ingest_jira_cleaned_csv functionality.

Usage:
  python scripts/jira/ingest_cleaned_csv.py <cleaned.csv>
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest_jira_cleaned_csv import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

