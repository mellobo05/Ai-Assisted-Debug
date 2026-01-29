from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel, JIRA_ISSUE_KEY_RE, _strip_or_none


class SnippetSaveRequest(APIModel):
    issue_key: str | None = None
    domain: str | None = None

    layer: str = Field(..., description="kernel|userspace")
    language: str = Field(..., description="c|cpp|rust|other")
    file_path: str | None = None
    content: str = Field(..., min_length=1, max_length=120_000)

    @field_validator("issue_key", mode="before")
    @classmethod
    def _normalize_key(cls, v: Any):
        if v is None:
            return None
        s = str(v).strip().upper()
        return s or None

    _strip_domain = field_validator("domain", mode="before")(_strip_or_none)
    _strip_file = field_validator("file_path", mode="before")(_strip_or_none)

    @field_validator("issue_key")
    @classmethod
    def _validate_key(cls, v: str | None):
        if v is None:
            return v
        if not JIRA_ISSUE_KEY_RE.match(v):
            raise ValueError("Invalid JIRA issue key format")
        return v

    @field_validator("layer", mode="before")
    @classmethod
    def _normalize_layer(cls, v: Any):
        s = str(v or "").strip().lower()
        return s

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_lang(cls, v: Any):
        s = str(v or "").strip().lower()
        if s == "c++":
            s = "cpp"
        return s


class SnippetSaveResponse(APIModel):
    id: str
    fingerprint: str
    saved: bool


class SnippetListResponse(APIModel):
    count: int
    items: list[dict]

