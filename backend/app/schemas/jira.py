from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import APIModel, JIRA_ISSUE_KEY_RE, _strip_or_none, _uniq_preserve_order


class JiraSyncRequest(APIModel):
    issue_keys: list[str] | None = None
    jql: str | None = None
    max_results: int = Field(default=25, ge=1, le=500)
    max_comments: int = Field(default=25, ge=0, le=200)

    @field_validator("issue_keys", mode="before")
    @classmethod
    def _normalize_issue_keys(cls, v: Any):
        if v is None:
            return None
        if not isinstance(v, list):
            return v
        cleaned: list[str] = []
        for x in v:
            if x is None:
                continue
            s = str(x).strip().upper()
            if s:
                cleaned.append(s)
        cleaned = _uniq_preserve_order(cleaned)
        return cleaned or None

    _strip_jql = field_validator("jql", mode="before")(_strip_or_none)

    @field_validator("issue_keys")
    @classmethod
    def _validate_issue_keys(cls, v: list[str] | None):
        if v is None:
            return v
        bad = [k for k in v if not JIRA_ISSUE_KEY_RE.match(k)]
        if bad:
            raise ValueError(f"Invalid JIRA issue keys: {bad[:10]}")
        return v

    @model_validator(mode="after")
    def _validate_one_of_issue_keys_or_jql(self):
        if (not self.issue_keys) and (not self.jql):
            raise ValueError("Provide either issue_keys or jql")
        return self


class JiraSyncResponse(APIModel):
    fetched: int
    ingested: int
    embedded: int

