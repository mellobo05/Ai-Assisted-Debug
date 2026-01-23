from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.integrations.jira.client import JiraService, build_embedding_text, extract_issue_fields
from app.models.jira import JiraEmbedding, JiraIssue
from app.services.embeddings import generate_embedding
from app.services.search import find_similar_jira


def get_issue_from_db(
    *,
    ctx: Dict[str, Any],
    issue_key: Optional[str] = None,
    issue_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Offline-friendly: fetch a JIRA issue from local Postgres (jira_issues table).

    Returns a compact dict with fields needed for reporting + an embedding-ready text
    (built from stored issue fields).
    """
    key = (issue_key or "").strip()
    if not key and issue_keys and isinstance(issue_keys, list) and len(issue_keys) > 0:
        key = str(issue_keys[0]).strip()
    if not key:
        raise ValueError("Provide issue_key (or issue_keys[0])")

    db = SessionLocal()
    try:
        issue = db.query(JiraIssue).filter(JiraIssue.issue_key == key).first()
        if not issue:
            raise ValueError(f"Issue not found in DB: {key}. Ingest/sync it first.")

        # Build a single text blob similar to live ingestion, but from stored fields.
        parts: List[str] = []
        parts.append(f"Issue: {issue.issue_key}")
        if issue.summary:
            parts.append(f"Summary: {issue.summary}")
        if issue.description:
            parts.append(f"Description: {issue.description}")
        if issue.status:
            parts.append(f"Status: {issue.status}")
        if issue.priority:
            parts.append(f"Priority: {issue.priority}")
        if issue.assignee:
            parts.append(f"Assignee: {issue.assignee}")
        if issue.issue_type:
            parts.append(f"Type: {issue.issue_type}")
        if issue.program_theme:
            parts.append(f"Program/Theme: {issue.program_theme}")
        if issue.labels:
            parts.append(f"Labels: {', '.join(issue.labels)}")
        if issue.components:
            parts.append(f"Components: {', '.join(issue.components)}")
        if issue.comments and isinstance(issue.comments, list):
            bodies = []
            for c in issue.comments:
                if isinstance(c, dict) and c.get("body"):
                    bodies.append(str(c.get("body")))
            if bodies:
                parts.append("Comments:\n" + "\n---\n".join(bodies))

        embedding_text = "\n".join(parts).strip()

        latest_comment = None
        if issue.comments and isinstance(issue.comments, list) and len(issue.comments) > 0:
            last = issue.comments[-1]
            if isinstance(last, dict):
                latest_comment = last.get("body")

        return {
            "issue_key": issue.issue_key,
            "url": issue.url,
            "summary": issue.summary,
            "description": issue.description,
            "status": issue.status,
            "priority": issue.priority,
            "assignee": issue.assignee,
            "issue_type": issue.issue_type,
            "program_theme": issue.program_theme,
            "labels": issue.labels,
            "components": issue.components,
            "latest_comment": latest_comment,
            "embedding_text": embedding_text,
        }
    finally:
        db.close()


def sync(
    *,
    ctx: Dict[str, Any],
    issue_keys: Optional[List[str]] = None,
    jql: Optional[str] = None,
    max_results: int = 25,
    max_comments: int = 25,
) -> Dict[str, Any]:
    """
    Live JIRA -> DB (jira_issues + jira_embeddings).
    Mirrors the /jira/sync endpoint but can be called from a workflow.
    """
    if not issue_keys and not jql:
        raise ValueError("Provide either issue_keys or jql")

    jira = JiraService.from_env()

    raw_issues: List[Dict[str, Any]] = []
    if issue_keys:
        for key in issue_keys:
            raw_issues.append(jira.fetch_issue_with_comments(key, max_comments=max_comments))
    else:
        raw_issues = jira.search_with_comments(
            jql or "",
            max_results=max_results,
            max_comments=max_comments,
        )

    db = SessionLocal()
    ingested = 0
    embedded = 0
    try:
        for raw in raw_issues:
            extracted = extract_issue_fields(raw)
            issue_key = extracted.get("issue_key")
            if not issue_key:
                continue

            issue = JiraIssue(
                issue_key=issue_key,
                jira_id=extracted.get("jira_id"),
                summary=extracted.get("summary") or "",
                description=extracted.get("description"),
                status=extracted.get("status"),
                priority=extracted.get("priority"),
                assignee=extracted.get("assignee"),
                issue_type=extracted.get("issue_type"),
                program_theme=extracted.get("program_theme"),
                labels=extracted.get("labels"),
                components=extracted.get("components"),
                comments=extracted.get("comments"),
                url=jira.issue_url(issue_key),
                raw=raw,
            )
            db.merge(issue)
            ingested += 1

            text = build_embedding_text(raw)
            emb = generate_embedding(text, task_type="retrieval_document")
            if not isinstance(emb, list) or len(emb) == 0:
                continue
            db.merge(JiraEmbedding(issue_key=issue_key, embedding=emb))
            embedded += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"fetched": len(raw_issues), "ingested": ingested, "embedded": embedded}


def search_similar_jira(
    *,
    ctx: Dict[str, Any],
    query: str,
    limit: int = 5,
    exclude_issue_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Query -> embedding -> cosine similarity search against jira_embeddings.
    """
    query_embedding = generate_embedding(query, task_type="retrieval_query")
    results = find_similar_jira(query_embedding, limit=limit, exclude_issue_keys=exclude_issue_keys)
    return {"query": query, "results_count": len(results), "results": results}


def render_similar_jira_report(
    *,
    ctx: Dict[str, Any],
    input_data: Dict[str, Any],
    max_items: int = 5,
) -> str:
    """
    Render a compact text report from search_similar_jira output.
    Intended for CLI display.
    """
    if not isinstance(input_data, dict):
        raise ValueError("input_data must be a dict (output from rag.search_similar_jira)")

    query = input_data.get("query", "")
    results = input_data.get("results") or []
    if not isinstance(results, list):
        results = []

    lines: List[str] = []
    lines.append(f"Query: {query}")
    lines.append(f"Matches: {min(len(results), max_items)} / {len(results)}")
    lines.append("")

    for i, r in enumerate(results[:max_items], start=1):
        issue_key = r.get("issue_key")
        sim = r.get("similarity")
        summary = r.get("summary")
        status = r.get("status")
        priority = r.get("priority")
        assignee = r.get("assignee")
        latest_comment = r.get("latest_comment")

        lines.append(f"{i}. {issue_key}  sim={sim:.4f}  [{status} | {priority}]  {summary}")
        if assignee:
            lines.append(f"   Assignee: {assignee}")
        if latest_comment:
            snippet = str(latest_comment).strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:217] + "..."
            lines.append(f"   Latest comment: {snippet}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_syscros_issue_summary_report(
    *,
    ctx: Dict[str, Any],
    issue: Dict[str, Any],
    similar: Optional[Dict[str, Any]] = None,
    max_items: int = 5,
    similarity_threshold: Optional[float] = None,
) -> str:
    """
    Render a single human-readable report:
      - SYSCROS issue summary (from DB)
      - Similar issues (from rag.search_similar_jira output)
    """
    if not isinstance(issue, dict):
        raise ValueError("issue must be a dict (output from jira.get_issue_from_db)")

    lines: List[str] = []
    lines.append(f"SYSCROS Issue: {issue.get('issue_key')}")
    if issue.get("url"):
        lines.append(f"URL: {issue.get('url')}")
    if issue.get("summary"):
        lines.append(f"Summary: {issue.get('summary')}")
    if issue.get("status") or issue.get("priority"):
        lines.append(f"Status/Priority: {issue.get('status')} / {issue.get('priority')}")
    if issue.get("assignee"):
        lines.append(f"Assignee: {issue.get('assignee')}")
    if issue.get("components"):
        lines.append(f"Components: {', '.join(issue.get('components') or [])}")
    if issue.get("program_theme"):
        lines.append(f"Program/Theme: {issue.get('program_theme')}")
    if issue.get("labels"):
        lines.append(f"Labels: {', '.join(issue.get('labels') or [])}")
    lines.append("")

    if issue.get("description"):
        desc = str(issue.get("description")).strip()
        if len(desc) > 1200:
            desc = desc[:1197] + "..."
        lines.append("Description:")
        lines.append(desc)
        lines.append("")

    if issue.get("latest_comment"):
        lc = str(issue.get("latest_comment")).strip().replace("\n", " ")
        if len(lc) > 400:
            lc = lc[:397] + "..."
        lines.append(f"Latest comment: {lc}")
        lines.append("")

    if similar and isinstance(similar, dict):
        results = similar.get("results") or []
        if isinstance(results, list) and results:
            # Optional threshold (percent 0-100). We treat similarity as cosine and scale by 100.
            original_results = list(results)
            if similarity_threshold is not None:
                try:
                    thr = float(similarity_threshold)
                except Exception:
                    thr = None
                if thr is not None:
                    filtered = []
                    for r in results:
                        try:
                            sim = float(r.get("similarity", 0.0))
                        except Exception:
                            sim = 0.0
                        if (sim * 100.0) >= thr:
                            filtered.append(r)
                    results = filtered

            if results:
                lines.append("Similar issues:")
                for i, r in enumerate(results[:max_items], start=1):
                    issue_key = r.get("issue_key")
                    sim = r.get("similarity", 0.0)
                    summary = r.get("summary") or ""
                    status = r.get("status") or ""
                    priority = r.get("priority") or ""
                    lines.append(f"{i}. {issue_key}  sim={sim:.4f}  [{status} | {priority}]  {summary}")
                lines.append("")
            else:
                # Be explicit when filtering removes everything.
                best = 0.0
                try:
                    best = max(float(r.get("similarity", 0.0)) for r in original_results)
                except Exception:
                    best = 0.0
                lines.append(
                    f"No similar issues met similarity_threshold={similarity_threshold} "
                    f"(best={best*100.0:.1f}/100)."
                )
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def reembed_from_db(
    *,
    ctx: Dict[str, Any],
    issue_keys: Optional[List[str]] = None,
    max_items: int = 500,
) -> Dict[str, Any]:
    """
    Re-generate embeddings for issues already present in jira_issues.

    This is especially useful after changing embedding providers (e.g., improving mock embeddings),
    so similarity search uses updated vectors without re-ingesting source data.
    """
    db = SessionLocal()
    embedded = 0
    fetched = 0
    try:
        q = db.query(JiraIssue)
        if issue_keys and isinstance(issue_keys, list) and len(issue_keys) > 0:
            q = q.filter(JiraIssue.issue_key.in_([str(k).strip() for k in issue_keys if str(k).strip()]))
        issues = q.limit(int(max_items)).all()
        fetched = len(issues)

        for issue in issues:
            raw = issue.raw or {}
            try:
                text = build_embedding_text(raw) if isinstance(raw, dict) else str(raw)
            except Exception:
                # Fall back to stored fields if raw is missing/invalid.
                parts: List[str] = [f"Issue: {issue.issue_key}", f"Summary: {issue.summary}"]
                if issue.description:
                    parts.append(f"Description: {issue.description}")
                if issue.status:
                    parts.append(f"Status: {issue.status}")
                if issue.priority:
                    parts.append(f"Priority: {issue.priority}")
                if issue.components:
                    parts.append(f"Components: {', '.join(issue.components)}")
                text = "\n".join(parts)

            emb = generate_embedding(text, task_type="retrieval_document")
            if not isinstance(emb, list) or len(emb) == 0:
                continue

            db.merge(JiraEmbedding(issue_key=issue.issue_key, embedding=emb))
            embedded += 1

        db.commit()
        return {"fetched": fetched, "embedded": embedded}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def render_reembed_report(
    *,
    ctx: Dict[str, Any],
    input_data: Dict[str, Any],
) -> str:
    """
    Render a short summary for jira.reembed_from_db output.
    """
    if not isinstance(input_data, dict):
        raise ValueError("input_data must be a dict (output from jira.reembed_from_db)")
    fetched = input_data.get("fetched", 0)
    embedded = input_data.get("embedded", 0)
    return f"Re-embed complete: fetched={fetched}, embedded={embedded}\n"

