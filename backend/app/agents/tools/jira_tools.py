from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.integrations.jira.client import JiraService, build_embedding_text, extract_issue_fields
from app.models.jira import JiraEmbedding, JiraIssue
from app.services.embeddings import generate_embedding
from app.services.search import find_similar_jira


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
) -> Dict[str, Any]:
    """
    Query -> embedding -> cosine similarity search against jira_embeddings.
    """
    query_embedding = generate_embedding(query, task_type="retrieval_query")
    results = find_similar_jira(query_embedding, limit=limit)
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

