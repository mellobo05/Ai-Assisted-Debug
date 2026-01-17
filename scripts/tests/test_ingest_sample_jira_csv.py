"""
Smoke test: ingest a tiny cleaned JIRA CSV fixture into the DB.

This is useful on a fresh DB to validate:
- CSV parsing
- jira_issues insert/upsert
- jira_embeddings insert/upsert

Run:
  python scripts/tests/test_ingest_sample_jira_csv.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "backend"))

    # Load env (so DB URL + mock mode are available)
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)

    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")

    fixture = Path(__file__).parent / "fixtures" / "jira_cleaned_sample.csv"
    if not fixture.exists():
        print(f"[FAIL] Missing fixture: {fixture}")
        return 1

    # Use the existing ingestion script logic
    import ingest_jira_cleaned_csv  # type: ignore

    # Simulate CLI invocation
    sys.argv = ["ingest_jira_cleaned_csv.py", str(fixture)]
    rc = ingest_jira_cleaned_csv.main()
    if rc != 0:
        print("[FAIL] Ingestion script returned non-zero")
        return 1

    # Verify counts for the two keys
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as c:
        n = c.execute(
            text(
                "select count(*) from jira_issues where issue_key in ('SYSCROS-TEST-1','SYSCROS-TEST-2')"
            )
        ).scalar()
        e = c.execute(
            text(
                "select count(*) from jira_embeddings where issue_key in ('SYSCROS-TEST-1','SYSCROS-TEST-2')"
            )
        ).scalar()

    print(f"[INFO] inserted issues={n} embeddings={e}")
    if (n or 0) < 2 or (e or 0) < 2:
        print("[FAIL] Expected 2 issues and 2 embeddings from fixture")
        return 1

    print("[OK] Fixture ingested and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

