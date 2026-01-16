from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from jira import JIRA


class JiraService:
    """
    Lightweight wrapper around python-jira.

    Auth options (pick one):
    - JIRA_EMAIL + JIRA_API_TOKEN (Jira Cloud)
    - JIRA_USERNAME + JIRA_PASSWORD (Server/DC basic auth)
    """

    def __init__(
        self,
        base_url: str,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify: bool | str = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")

        options: Dict[str, Any] = {"server": self.base_url, "verify": verify}
        if email and api_token:
            self._jira = JIRA(options=options, basic_auth=(email, api_token))
        elif username and password:
            self._jira = JIRA(options=options, basic_auth=(username, password))
        else:
            raise ValueError(
                "JIRA credentials not set. Provide either (JIRA_EMAIL + JIRA_API_TOKEN) "
                "or (JIRA_USERNAME + JIRA_PASSWORD)."
            )

    @staticmethod
    def from_env() -> "JiraService":
        base_url = os.getenv("JIRA_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("JIRA_BASE_URL is not set")

        # SSL options:
        # - JIRA_VERIFY_SSL=true/false
        # - JIRA_CA_BUNDLE=/path/to/ca.pem (overrides verify boolean)
        verify_env = os.getenv("JIRA_VERIFY_SSL", "true").strip().lower()
        ca_bundle = os.getenv("JIRA_CA_BUNDLE", "").strip() or None
        verify: bool | str = True
        if ca_bundle:
            verify = ca_bundle
        elif verify_env in {"0", "false", "no"}:
            verify = False

        return JiraService(
            base_url=base_url,
            email=os.getenv("JIRA_EMAIL"),
            api_token=os.getenv("JIRA_API_TOKEN"),
            username=os.getenv("JIRA_USERNAME"),
            password=os.getenv("JIRA_PASSWORD"),
            verify=verify,
        )

    def issue_url(self, issue_key: str) -> str:
        # Jira Cloud typically: https://<site>.atlassian.net/browse/KEY-123
        return f"{self.base_url}/browse/{issue_key}"

    def fetch_issue(self, issue_key: str) -> Dict[str, Any]:
        issue = self._jira.issue(issue_key)
        return issue.raw

    def fetch_issue_with_comments(self, issue_key: str, max_comments: int = 25) -> Dict[str, Any]:
        """
        Fetch an issue and attach the latest comments into raw['comments'].
        The returned comment list is sorted most-recent-first (ADA style).
        Each comment has: id, created, displayName, body
        """
        issue = self._jira.issue(issue_key)
        raw = issue.raw

        try:
            comments = self._jira.comments(issue)
        except Exception:
            comments = []

        # most-recent-first, keep latest max_comments
        # python-jira usually returns in chronological order; we sort by created if present
        def _created(c: Any) -> str:
            return str(getattr(c, "created", "") or "")

        comments_sorted = sorted(comments, key=_created, reverse=True)[: max_comments]
        latest_comments: List[Dict[str, Any]] = []
        for c in comments_sorted:
            author = getattr(c, "author", None)
            display_name = None
            if author is not None:
                display_name = getattr(author, "displayName", None) or getattr(author, "name", None)
            latest_comments.append(
                {
                    "id": str(getattr(c, "id", "") or ""),
                    "created": str(getattr(c, "created", "") or ""),
                    "displayName": display_name,
                    "body": str(getattr(c, "body", "") or ""),
                }
            )

        raw["comments"] = latest_comments
        return raw

    def search(self, jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
        issues = self._jira.search_issues(jql, maxResults=max_results)
        return [i.raw for i in issues]

    def search_with_comments(self, jql: str, max_results: int = 50, max_comments: int = 25) -> List[Dict[str, Any]]:
        issues = self._jira.search_issues(jql, maxResults=max_results)
        raws: List[Dict[str, Any]] = []
        for i in issues:
            key = getattr(i, "key", None) or (i.raw or {}).get("key")
            if key:
                raws.append(self.fetch_issue_with_comments(str(key), max_comments=max_comments))
            else:
                raws.append(i.raw)
        return raws


def extract_issue_fields(raw: Dict[str, Any]) -> Dict[str, Optional[str]]:
    fields = raw.get("fields") or {}

    def _safe_get(d: Dict[str, Any], *keys: str) -> Optional[str]:
        cur: Any = d
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        if cur is None:
            return None
        return str(cur)

    issue_key = raw.get("key")
    jira_id = raw.get("id")
    summary = _safe_get(fields, "summary") or ""

    # description can be rich text; keep a compact string form
    description = None
    desc = fields.get("description")
    if isinstance(desc, str):
        description = desc
    elif desc is not None:
        description = str(desc)

    status = _safe_get(fields, "status", "name")
    priority = _safe_get(fields, "priority", "name")
    assignee = _safe_get(fields, "assignee", "displayName") or _safe_get(fields, "assignee", "name")
    issue_type = _safe_get(fields, "issuetype", "name")

    # Labels / components
    labels_val = fields.get("labels")
    labels = None
    if isinstance(labels_val, list):
        labels = [str(x) for x in labels_val if x is not None]

    comps_val = fields.get("components")
    components = None
    if isinstance(comps_val, list):
        components = []
        for c in comps_val:
            if isinstance(c, dict) and c.get("name"):
                components.append(str(c.get("name")))

    # Program/Theme custom field: allow env override
    program_theme = None
    program_field = os.getenv("JIRA_PROGRAM_THEME_FIELD", "").strip()
    if program_field and program_field in fields:
        v = fields.get(program_field)
        if isinstance(v, dict) and v.get("value"):
            program_theme = str(v.get("value"))
        elif v is not None:
            program_theme = str(v)

    # Comments injected by fetch_issue_with_comments()
    comments = raw.get("comments")
    comments_list = comments if isinstance(comments, list) else None

    # Keep JSON-native objects (SQLAlchemy JSON columns can store list/dict)
    return {
        "issue_key": issue_key,
        "jira_id": str(jira_id) if jira_id is not None else None,
        "summary": summary,
        "description": description,
        "status": status,
        "priority": priority,
        "assignee": assignee,
        "issue_type": issue_type,
        "program_theme": program_theme,
        "labels": labels,  # list[str] | None
        "components": components,  # list[str] | None
        "comments": comments_list,  # list[dict] | None (latest 25, most-recent-first)
    }


def build_embedding_text(raw: Dict[str, Any]) -> str:
    """
    Build a text blob for embedding (ADA-style):
    combine summary + description + status/assignee + labels/program/theme + comment bodies.
    """
    fields = raw.get("fields") or {}
    key = raw.get("key", "")
    summary = fields.get("summary", "")
    status = (fields.get("status") or {}).get("name", "")
    priority = (fields.get("priority") or {}).get("name", "")
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    assignee = ((fields.get("assignee") or {}) or {}).get("displayName") or ""
    labels = fields.get("labels") or []

    # Program/Theme custom field: allow env override
    program_theme = ""
    program_field = os.getenv("JIRA_PROGRAM_THEME_FIELD", "").strip()
    if program_field and program_field in fields:
        v = fields.get(program_field)
        if isinstance(v, dict) and v.get("value"):
            program_theme = str(v.get("value"))
        elif v is not None:
            program_theme = str(v)

    desc = fields.get("description", "")
    if desc is None:
        desc = ""
    if not isinstance(desc, str):
        desc = str(desc)

    # Comments (prefer raw['comments'] injected by fetch_issue_with_comments)
    comment_bodies: List[str] = []
    raw_comments = raw.get("comments")
    if isinstance(raw_comments, list) and raw_comments:
        # stored as most-recent-first; for embedding include all bodies
        for c in raw_comments:
            if isinstance(c, dict) and c.get("body"):
                comment_bodies.append(str(c.get("body")))
    else:
        comment_block = (fields.get("comment") or {}).get("comments")
        if isinstance(comment_block, list) and comment_block:
            for c in comment_block[:25]:
                body = c.get("body")
                if body:
                    comment_bodies.append(str(body))

    comments_text = ""
    if comment_bodies:
        comments_text = "\n\nComments:\n" + "\n---\n".join(comment_bodies)

    return (
        f"JIRA Issue {key}\n"
        f"Type: {issue_type}\n"
        f"Status: {status}\n"
        f"Priority: {priority}\n"
        f"Assignee: {assignee}\n"
        f"Program/Theme: {program_theme}\n"
        f"Labels: {', '.join([str(x) for x in labels])}\n"
        f"Summary: {summary}\n\n"
        f"Description:\n{desc}\n"
        f"{comments_text}"
    )

