from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class JiraAnalysisRun(Base):
    """
    Stores an analysis run (RCA + fix suggestions) for a given issue_key.

    This is used for the "new JIRA analysis intake" flow where the user provides:
      - issue_key + summary (+ optional domain/os/logs)
    and we persist both the intake and the generated analysis so it can be fetched later.
    """

    __tablename__ = "jira_analysis_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_key = Column(String, nullable=False, index=True)
    # Idempotency key for "analyze" runs (avoid storing duplicates for same input).
    idempotency_key = Column(String, nullable=True, index=True)

    domain = Column(String, nullable=True)
    os = Column(String, nullable=True)
    logs_fingerprint = Column(String, nullable=True)

    inputs = Column(JSON, nullable=True)  # sanitized/compact inputs (no gigantic raw logs)
    report = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

