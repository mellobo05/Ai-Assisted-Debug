from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.models.snippets import CodeSnippet
from app.schemas.common import JIRA_ISSUE_KEY_RE, _strip_or_none


def save_snippet(
    *,
    ctx: Dict[str, Any],
    layer: str,
    language: str,
    content: str,
    issue_key: Optional[str] = None,
    domain: Optional[str] = None,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save a code snippet for future reference.
    """
    key = (str(issue_key or "").strip().upper() or None)
    if key and not JIRA_ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue_key: {issue_key!r}")

    lay = str(layer or "").strip().lower()
    if lay not in {"kernel", "userspace"}:
        raise ValueError("layer must be 'kernel' or 'userspace'")

    lang = str(language or "").strip().lower()
    if not lang:
        raise ValueError("language is required")
    if lang not in {"c", "cpp", "c++", "rust", "other"}:
        # don't block usage; normalize unknowns
        lang = "other"
    if lang == "c++":
        lang = "cpp"

    text = str(content or "").rstrip()
    if not text.strip():
        raise ValueError("content is required")
    # Avoid gigantic storage (still enough for multi-function snippets)
    if len(text) > 120_000:
        text = text[: 120_000 - 3] + "..."

    dom = _strip_or_none(domain)
    dom = str(dom).strip().lower() if isinstance(dom, str) and dom.strip() else None
    fp = CodeSnippet.fingerprint_for(text)

    db = SessionLocal()
    try:
        row = CodeSnippet(
            issue_key=key,
            domain=dom,
            layer=lay,
            language=lang,
            file_path=str(file_path or "").strip() or None,
            fingerprint=fp,
            content=text,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": str(row.id), "fingerprint": fp, "saved": True}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_snippets(
    *,
    ctx: Dict[str, Any],
    issue_key: Optional[str] = None,
    domain: Optional[str] = None,
    layer: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Fetch recent snippets for an issue (or domain) to provide context to analysis.
    """
    key = (str(issue_key or "").strip().upper() or None)
    if key and not JIRA_ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue_key: {issue_key!r}")

    dom = _strip_or_none(domain)
    dom = str(dom).strip().lower() if isinstance(dom, str) and dom.strip() else None

    lay = str(layer or "").strip().lower() or None
    if lay and lay not in {"kernel", "userspace"}:
        raise ValueError("layer must be 'kernel' or 'userspace'")

    lim = max(1, min(int(limit or 5), 20))

    db = SessionLocal()
    try:
        q = db.query(CodeSnippet)
        if key:
            q = q.filter(CodeSnippet.issue_key == key)
        if dom:
            q = q.filter(CodeSnippet.domain == dom)
        if lay:
            q = q.filter(CodeSnippet.layer == lay)
        rows: List[CodeSnippet] = q.order_by(CodeSnippet.created_at.desc()).limit(lim).all()
        items: List[Dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "id": str(r.id),
                    "issue_key": r.issue_key,
                    "domain": r.domain,
                    "layer": r.layer,
                    "language": r.language,
                    "file_path": r.file_path,
                    "fingerprint": r.fingerprint,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {"count": len(items), "items": items}
    finally:
        db.close()

