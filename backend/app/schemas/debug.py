from __future__ import annotations

from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import APIModel, _strip_or_none


class DebugRequest(APIModel):
    issue_summary: str = Field(min_length=1, max_length=512)
    domain: str = Field(min_length=1, max_length=128)
    os: str = Field(min_length=1, max_length=128)
    logs: str = Field(min_length=1, max_length=200_000)

    _strip_all = field_validator("issue_summary", "domain", "os", "logs", mode="before")(_strip_or_none)


class DebugStartResponse(APIModel):
    session_id: UUID
    status: str
    os: str | None = None
    domain: str | None = None
    issue_summary: str | None = None


class DebugStatusResponse(APIModel):
    session_id: UUID
    status: str
    os: str | None = None
    domain: str | None = None
    issue_summary: str | None = None
    has_embedding: bool = False

