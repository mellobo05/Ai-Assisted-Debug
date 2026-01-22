from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import APIModel, _strip_or_none


class QueryRequest(APIModel):
    query: str = Field(min_length=1, max_length=4096)
    limit: int = Field(default=3, ge=1, le=20)

    _strip_query = field_validator("query", mode="before")(_strip_or_none)


class JiraSearchResult(APIModel):
    source: str = Field(default="jira")
    issue_key: str
    similarity: float = Field(ge=-1.0, le=1.0)
    summary: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    issue_type: str | None = None
    url: str | None = None
    program_theme: str | None = None
    labels: list[str] | None = None
    components: list[str] | None = None
    latest_comment: str | None = None

    @field_validator("labels", "components", mode="before")
    @classmethod
    def _normalize_str_lists(cls, v: Any):
        if v is None:
            return None
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip() != ""]
        return v


class SearchResponse(APIModel):
    query: str
    results_count: int
    results: list[JiraSearchResult]

