"""
Improved database session configuration with connection pooling.
Replace the current session.py with this for better scalability.
"""
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

# Improved connection pooling configuration
# Environment variables allow runtime tuning:
# - DB_POOL_SIZE: Base pool size (default: 20)
# - DB_MAX_OVERFLOW: Max connections beyond pool_size (default: 40)
# - DB_POOL_RECYCLE: Recycle connections after N seconds (default: 3600)
# - DB_POOL_TIMEOUT: Timeout for getting connection (default: 30)

pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "40"))
pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))
pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_recycle=pool_recycle,  # Recycle connections after 1 hour
    pool_timeout=pool_timeout,  # 30 second timeout
    echo=os.getenv("DB_ECHO", "false").lower() == "true",  # SQL logging for debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Optional: Read replica support
# Set DATABASE_URL_READ for read-only queries (searches, status checks)
READ_DATABASE_URL = os.getenv("DATABASE_URL_READ", "").strip() or DATABASE_URL

if READ_DATABASE_URL != DATABASE_URL:
    # Separate engine for read operations (can have larger pool)
    read_pool_size = int(os.getenv("DB_READ_POOL_SIZE", "30"))
    read_max_overflow = int(os.getenv("DB_READ_MAX_OVERFLOW", "60"))
    
    read_engine = create_engine(
        READ_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=read_pool_size,
        max_overflow=read_max_overflow,
        pool_recycle=pool_recycle,
        pool_timeout=pool_timeout,
    )
    SessionLocalRead = sessionmaker(autocommit=False, autoflush=False, bind=read_engine)
else:
    # Use same engine if no read replica configured
    SessionLocalRead = SessionLocal


def get_read_session():
    """Get a database session for read operations (may use read replica)"""
    return SessionLocalRead()


def get_write_session():
    """Get a database session for write operations (always uses primary)"""
    return SessionLocal()
