from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.sql import func
import uuid

from app.db.base import Base

class DebugSession(Base):
    __tablename__ = "debug_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_summary = Column(String,nullable=False)
    domain = Column(String,nullable=False)
    os = Column(String,nullable=False)
    logs = Column(String,nullable=False)
    status = Column(String,default="PROCESSING")
    created_at = Column(DateTime(timezone=True),default=func.now())

class DebugEmbedding(Base):
    __tablename__ = "debug_embeddings"

    session_id = Column(UUID(as_uuid=True),primary_key=True)
    # Using JSON instead of Vector for compatibility without pgvector extension
    # TODO: Switch back to Vector(768) when pgvector is installed
    embedding = Column(JSON,nullable=False)  # gemini embedding-001 size (768 dimensions)



