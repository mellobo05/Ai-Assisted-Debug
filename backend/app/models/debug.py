from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

from app.db.base import Base

class DebugSession(Base):
    __tablename__ = "debug_sessions"

    id = Column(UUID(as_uuid=True,primary_key=True),default=uuid.uuid4)
    issue_summary = Column(String,nullable=False)
    domain = Column(String,nullable=False)
    os = Column(String,nullable=False)
    logs = Column(String,nullable=False)
    status = Column(String,default="PROCESSING")
    created_at = Column(DateTime(timezone=True),default=func.now())

class DebugEmbedding(Base):
    __tablename__ = "debug_embeddings"

    session_id = Column(UUID(as_uuid=True),primary_key=True)
    embedding = Column(Vector(1536),nullable=False)#openai embedding size



