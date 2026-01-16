"""
Lightweight schema migration for jira_issues / jira_embeddings tables.

Because we are not running Alembic migrations yet, existing local DBs won't
pick up new columns when models change. This script adds missing columns
using ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

Run from project root:
  python migrate_jira_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent / "backend"))

    from sqlalchemy import text

    from app.db.session import engine

    stmts = [
        # jira_issues new columns
        "ALTER TABLE IF EXISTS jira_issues ADD COLUMN IF NOT EXISTS jira_id text;",
        "ALTER TABLE IF EXISTS jira_issues ADD COLUMN IF NOT EXISTS program_theme text;",
        "ALTER TABLE IF EXISTS jira_issues ADD COLUMN IF NOT EXISTS labels json;",
        "ALTER TABLE IF EXISTS jira_issues ADD COLUMN IF NOT EXISTS components json;",
        "ALTER TABLE IF EXISTS jira_issues ADD COLUMN IF NOT EXISTS comments json;",
        # jira_embeddings already fine (issue_key, embedding, created_at)
    ]

    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))

    print("[MIGRATE] jira_issues columns ensured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

