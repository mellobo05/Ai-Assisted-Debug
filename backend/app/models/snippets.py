from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base


def _fingerprint(text: str) -> str:
    s = (text or "").strip()
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:16]


class CodeSnippet(Base):
    """
    Stored code snippets pasted by users during analysis.

    Purpose:
      - Persist "kernel/userspace" context for an issue
      - Reuse snippets for future runs (better fix/logging suggestions)
    """

    __tablename__ = "code_snippets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    issue_key = Column(String, nullable=True, index=True)  # e.g. SYSCROS-123 (optional)
    domain = Column(String, nullable=True, index=True)  # e.g. media
    layer = Column(String, nullable=False)  # kernel|userspace
    language = Column(String, nullable=False)  # c|cpp|rust|other
    file_path = Column(String, nullable=True)

    fingerprint = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    @staticmethod
    def fingerprint_for(content: str) -> str:
        return _fingerprint(content)

