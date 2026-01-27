from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _build_database_url() -> str:
    """
    Central DB configuration.

    Priority:
      1) DATABASE_URL (full SQLAlchemy URL)
      2) PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD (compose a URL)

    This is critical for multi-device setups: both machines must point at the same
    Postgres instance (not localhost on each device).
    """
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return url

    host = (os.getenv("PGHOST") or "localhost").strip()
    port = (os.getenv("PGPORT") or "5432").strip()
    db = (os.getenv("PGDATABASE") or "postgres").strip()
    user = (os.getenv("PGUSER") or "postgres").strip()
    pw = (os.getenv("PGPASSWORD") or "").strip()

    if pw:
        return f"postgresql://{user}:{pw}@{host}:{port}/{db}"
    return f"postgresql://{user}@{host}:{port}/{db}"


DATABASE_URL = _build_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

