from __future__ import annotations

"""
Wrapper for ingest_jira_xml functionality.

Usage:
  python scripts/jira/ingest_xml.py <export.xml>
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest_jira_xml import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

