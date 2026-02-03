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


class JiraIntakeRequest(APIModel):
    """
    Offline-friendly intake: user supplies a new issue key + summary (+ optional logs).

    This stores the issue into `jira_issues` and generates an embedding in `jira_embeddings`
    so it can be searched/summarized later like a normal ingested JIRA.
    """

    issue_key: str = Field(..., min_length=3, max_length=50)
    summary: str = Field(..., min_length=1, max_length=300)

    domain: str | None = Field(default=None, max_length=80)
    component: str | None = Field(default=None, max_length=120)
    os: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=200_000)
    logs: str | None = Field(default=None, max_length=200_000)

    @field_validator("issue_key", mode="before")
    @classmethod
    def _normalize_issue_key(cls, v: Any):
        if v is None:
            return v
        s = str(v).strip().upper()
        return s

    _strip_domain = field_validator("domain", mode="before")(_strip_or_none)
    _strip_component = field_validator("component", mode="before")(_strip_or_none)
    _strip_os = field_validator("os", mode="before")(_strip_or_none)
    _strip_description = field_validator("description", mode="before")(_strip_or_none)
    _strip_logs = field_validator("logs", mode="before")(_strip_or_none)

    @field_validator("issue_key")
    @classmethod
    def _validate_issue_key(cls, v: str):
        if not JIRA_ISSUE_KEY_RE.match(v or ""):
            raise ValueError("Invalid JIRA issue key format")
        return v


class JiraIntakeResponse(APIModel):
    issue_key: str
    embedded: bool


class JiraSummarizeRequest(APIModel):
    """
    Fetch + summarize (RCA + fix suggestions) for an existing issue in the local DB.

    This uses the swarm runner and can optionally take pasted logs text.
    """

    issue_key: str = Field(..., min_length=3, max_length=50)
    domain: str | None = Field(default=None, max_length=80)
    component: str | None = Field(default=None, max_length=120)
    os: str | None = Field(default=None, max_length=80)
    logs: str | None = Field(default=None, max_length=200_000)

    limit: int = Field(default=5, ge=1, le=20)
    external_knowledge: bool = False
    min_local_score: float = Field(default=0.62, ge=0.0, le=1.0)
    external_max_results: int = Field(default=5, ge=1, le=10)
    save_run: bool = False
    analysis_mode: str = Field(default="async", description="async|sync|skip")

    @field_validator("issue_key", mode="before")
    @classmethod
    def _normalize_issue_key(cls, v: Any):
        if v is None:
            return v
        s = str(v).strip().upper()
        return s

    _strip_domain = field_validator("domain", mode="before")(_strip_or_none)
    _strip_component = field_validator("component", mode="before")(_strip_or_none)
    _strip_os = field_validator("os", mode="before")(_strip_or_none)
    _strip_logs = field_validator("logs", mode="before")(_strip_or_none)

    @field_validator("issue_key")
    @classmethod
    def _validate_issue_key(cls, v: str):
        if not JIRA_ISSUE_KEY_RE.match(v or ""):
            raise ValueError("Invalid JIRA issue key format")
        return v


class JiraSummarizeResponse(APIModel):
    issue_key: str
    report: str
    analysis: str
    saved_run: dict | None = None
    analysis_status: str | None = None  # PROCESSING|COMPLETED|SKIPPED|ERROR
    job_id: str | None = None


class JiraAnalyzeRequest(APIModel):
    """
    Single-input pipeline for the UI.

    Inputs:
      - issue_key + summary (+ optional domain/os/logs/notes)

    Behavior:
      1) If issue_key exists AND summary matches AND a previous analysis exists -> return cached analysis
      2) Else upsert the issue (store + embed)
      3) Compute report fast (no LLM)
      4) Optionally run LLM analysis async/sync/skip
      5) Track related_issue_keys for faster access
    """

    issue_key: str = Field(..., min_length=3, max_length=50)
    summary: str = Field(..., min_length=1, max_length=300)
    domain: str | None = Field(default=None, max_length=80)
    component: str | None = Field(default=None, max_length=120)
    os: str | None = Field(default=None, max_length=80)
    logs: str | None = Field(default=None, max_length=200_000)
    notes: str | None = Field(default=None, max_length=50_000)

    limit: int = Field(default=5, ge=1, le=20)
    external_knowledge: bool = False
    min_local_score: float = Field(default=0.62, ge=0.0, le=1.0)
    external_max_results: int = Field(default=5, ge=1, le=10)
    save_run: bool = True
    analysis_mode: str = Field(default="async", description="async|sync|skip")

    @field_validator("issue_key", mode="before")
    @classmethod
    def _normalize_issue_key(cls, v: Any):
        if v is None:
            return v
        return str(v).strip().upper()

    _strip_summary = field_validator("summary", mode="before")(_strip_or_none)
    _strip_domain = field_validator("domain", mode="before")(_strip_or_none)
    _strip_component = field_validator("component", mode="before")(_strip_or_none)
    _strip_os = field_validator("os", mode="before")(_strip_or_none)
    _strip_logs = field_validator("logs", mode="before")(_strip_or_none)
    _strip_notes = field_validator("notes", mode="before")(_strip_or_none)

    @field_validator("issue_key")
    @classmethod
    def _validate_issue_key(cls, v: str):
        if not JIRA_ISSUE_KEY_RE.match(v or ""):
            raise ValueError("Invalid JIRA issue key format")
        return v


class JiraAnalyzeResponse(APIModel):
    issue_key: str
    summary: str
    report: str
    analysis: str
    analysis_status: str | None = None  # PROCESSING|COMPLETED|SKIPPED|ERROR|CACHED
    job_id: str | None = None
    related_issue_keys: list[str] | None = None
    cache_hit: bool = False
    saved_run: dict | None = None

