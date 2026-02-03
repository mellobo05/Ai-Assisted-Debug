from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func

from app.db.base import Base


class JiraIssue(Base):
    """
    Stored copy of a JIRA issue (raw JSON + extracted fields).
    """

    __tablename__ = "jira_issues"

    issue_key = Column(String, primary_key=True)  # e.g. SYSCROS-129896
    jira_id = Column(String, nullable=True)  # internal JIRA id (stringified)
    summary = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    assignee = Column(String, nullable=True)
    issue_type = Column(String, nullable=True)
    program_theme = Column(String, nullable=True)
    labels = Column(JSON, nullable=True)  # list[str]
    components = Column(JSON, nullable=True)  # list[str]
    comments = Column(JSON, nullable=True)  # list[{"id","created","displayName","body"}]
    # Related issue keys discovered by similarity search (for faster access / UI hints)
    related_issue_keys = Column(JSON, nullable=True)  # list[str]

    url = Column(String, nullable=True)
    raw = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)


class JiraEmbedding(Base):
    """
    Embedding for a JIRA issue.

    Using JSON embedding for compatibility when pgvector isn't enabled.
    """

    __tablename__ = "jira_embeddings"

    issue_key = Column(String, primary_key=True)
    embedding = Column(JSON, nullable=False)  # list[float]
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

