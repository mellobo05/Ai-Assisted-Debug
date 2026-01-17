"""
Smoke test: verify jira_issues and jira_embeddings have data.

Run:
  python scripts/tests/test_jira_db_counts.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as c:
        issues = c.execute(text("select count(*) from jira_issues")).scalar() or 0
        embs = c.execute(text("select count(*) from jira_embeddings")).scalar() or 0

    print(f"[INFO] jira_issues={issues} jira_embeddings={embs}")
    if issues == 0 or embs == 0:
        print("[FAIL] JIRA tables are empty. Ingest data first.")
        print("Example: python ingest_jira_cleaned_csv.py <path-to-cleaned.csv>")
        return 1

    print("[OK] JIRA tables contain data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

