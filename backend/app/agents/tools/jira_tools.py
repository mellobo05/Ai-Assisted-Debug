from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.integrations.jira.client import JiraService, build_embedding_text, extract_issue_fields
from app.models.jira_analysis import JiraAnalysisRun
from app.models.jira import JiraEmbedding, JiraIssue
from app.services.embeddings import generate_embedding
from app.services.search import find_similar_jira
from app.schemas.common import JIRA_ISSUE_KEY_RE


def _tokenize_simple(text: str) -> List[str]:
    import re

    t = (text or "").lower()
    # words + simple tokens (keep dp/hdmi)
    toks = re.findall(r"[a-z0-9][a-z0-9\-\_\.]{1,30}", t)
    return [x for x in toks if len(x) >= 2]


def _domain_keywords() -> Dict[str, List[str]]:
    # Lightweight mapping: used for component match + weak supervision for ML.
    return {
        "display": [
            "display",
            "graphics",
            "drm",
            "kms",
            "i915",
            "xe",
            "wayland",
            "x11",
            "xorg",
            "compositor",
            "monitor",
            "external display",
            "dock",
            "docked",
            "dp",
            "displayport",
            "hdmi",
            "edp",
        ],
        "media": ["media", "video", "codec", "decoder", "encode", "hevc", "h.265", "av1", "vaapi", "libva", "gstreamer"],
        "audio": ["audio", "alsa", "pulseaudio", "pipewire", "speaker", "microphone", "snd"],
        "network": ["network", "wifi", "wlan", "bluetooth", "bt", "ethernet", "iwlwifi", "rtl", "mt7921"],
        "storage": ["storage", "nvme", "ssd", "mmc", "emmc", "ufs", "sata", "ext4", "btrfs"],
        "power": ["power", "suspend", "resume", "s0ix", "hibernate", "battery", "thermal", "fan"],
        "input": ["touch", "trackpad", "keyboard", "hid", "i2c", "wacom"],
    }


def _normalize_domain(domain: Optional[str]) -> Optional[str]:
    d = str(domain or "").strip().lower()
    if not d:
        return None
    # common aliases
    if d in {"disp", "gfx", "graphic", "graphics"}:
        return "display"
    if d in {"net", "networking", "wifi"}:
        return "network"
    if d in {"vid", "video", "codec"}:
        return "media"
    return d


def resolve_component_from_db(*, ctx: Dict[str, Any], component: Optional[str]) -> Optional[str]:
    """
    Best-effort: map a user-provided component string to the closest known DB component name.
    """
    c = str(component or "").strip()
    if not c:
        return None
    c_low = c.lower()

    db = SessionLocal()
    try:
        rows = db.query(JiraIssue.components).all()
    finally:
        db.close()

    known: List[str] = []
    seen = set()
    for (comps,) in rows:
        if not isinstance(comps, list):
            continue
        for x in comps:
            s = str(x or "").strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            known.append(s)

    if not known:
        return c

    # 1) exact case-insensitive match
    for k in known:
        if k.lower() == c_low:
            return k

    # 2) substring match (prefer shortest containing string)
    subs = [k for k in known if c_low in k.lower() or k.lower() in c_low]
    if subs:
        subs.sort(key=lambda s: len(s))
        return subs[0]

    # 3) token overlap score
    c_toks = set(_tokenize_simple(c))
    if not c_toks:
        return c
    best = None
    best_score = 0.0
    for k in known:
        kt = set(_tokenize_simple(k))
        if not kt:
            continue
        inter = len(c_toks & kt)
        union = len(c_toks | kt) or 1
        score = inter / union
        if score > best_score:
            best_score = score
            best = k
    if best and best_score >= 0.25:
        return best
    return c


def prefilter_issue_keys_for_component(
    *,
    ctx: Dict[str, Any],
    component: Optional[str],
    max_candidates: int = 5000,
) -> Dict[str, Any]:
    """
    Component-first filter. This is the highest precision filter when the user provides a component.
    """
    c = str(component or "").strip()
    if not c:
        return {"component": None, "issue_keys": None, "reason": "no_component"}

    resolved = resolve_component_from_db(ctx=ctx, component=c)
    resolved_low = str(resolved or c).strip().lower()

    db = SessionLocal()
    try:
        rows = db.query(JiraIssue.issue_key, JiraIssue.components, JiraIssue.labels).limit(int(max_candidates)).all()
    finally:
        db.close()

    hits: List[str] = []
    for issue_key, components, labels in rows:
        k = str(issue_key or "").strip().upper()
        if not k:
            continue
        comps = " ".join([str(x) for x in (components or [])]).lower() if isinstance(components, list) else ""
        labs = " ".join([str(x) for x in (labels or [])]).lower() if isinstance(labels, list) else ""
        text = (comps + " " + labs).strip()
        if not text:
            continue
        if resolved_low in text:
            hits.append(k)

    # Dedupe preserve order
    out: List[str] = []
    seen = set()
    for k in hits:
        if k in seen:
            continue
        seen.add(k)
        out.append(k)

    return {
        "component": c,
        "resolved_component": resolved,
        "issue_keys": out or None,
        "reason": "component_match",
        "hits": len(out),
    }


def prefilter_issue_keys_for_domain(
    *,
    ctx: Dict[str, Any],
    domain: Optional[str],
    query_text: str,
    max_candidates: int = 1000,
) -> Dict[str, Any]:
    """
    ML-ish prefilter to narrow the candidate pool *before* running embedding similarity.

    - Uses DB components/labels as weak supervision to train a simple Multinomial Naive Bayes classifier.
    - Also uses direct component keyword matching for high precision.
    """
    d = _normalize_domain(domain)
    if not d:
        return {"domain": None, "issue_keys": None, "reason": "no_domain"}

    kw = _domain_keywords().get(d)
    if not kw:
        return {"domain": d, "issue_keys": None, "reason": "unknown_domain"}

    db = SessionLocal()
    try:
        rows = (
            db.query(JiraIssue.issue_key, JiraIssue.summary, JiraIssue.description, JiraIssue.components, JiraIssue.labels)
            .limit(int(max_candidates))
            .all()
        )
    finally:
        db.close()

    items: List[Dict[str, Any]] = []
    for issue_key, summary, description, components, labels in rows:
        items.append(
            {
                "issue_key": str(issue_key or "").strip().upper(),
                "summary": str(summary or ""),
                "description": str(description or ""),
                "components": components if isinstance(components, list) else [],
                "labels": labels if isinstance(labels, list) else [],
            }
        )

    def _match_components(it: Dict[str, Any]) -> bool:
        comps = " ".join([str(x) for x in (it.get("components") or [])]).lower()
        labs = " ".join([str(x) for x in (it.get("labels") or [])]).lower()
        text = comps + " " + labs
        return any(k in text for k in kw)

    component_hits = [it["issue_key"] for it in items if it["issue_key"] and _match_components(it)]

    # --- Train a tiny Naive Bayes classifier from weak labels (components -> domain) ---
    domains = list(_domain_keywords().keys())
    vocab: Dict[str, int] = {}
    label_word_counts: Dict[str, Dict[int, int]] = {dd: {} for dd in domains}
    label_totals: Dict[str, int] = {dd: 0 for dd in domains}
    label_docs: Dict[str, int] = {dd: 0 for dd in domains}

    def _infer_label(it: Dict[str, Any]) -> Optional[str]:
        # weak label: choose first domain whose keywords hit components/labels.
        comps = " ".join([str(x) for x in (it.get("components") or [])]).lower()
        labs = " ".join([str(x) for x in (it.get("labels") or [])]).lower()
        cl = (comps + " " + labs).strip()
        for dd, kws in _domain_keywords().items():
            if any(k in cl for k in kws):
                return dd
        return None

    def _text_for(it: Dict[str, Any]) -> str:
        return (str(it.get("summary") or "") + "\n" + str(it.get("description") or "")).strip()

    # Build vocab + counts
    for it in items:
        lab = _infer_label(it)
        if not lab:
            continue
        text = _text_for(it)
        toks = _tokenize_simple(text)
        if not toks:
            continue
        label_docs[lab] += 1
        for tok in toks:
            if tok not in vocab:
                vocab[tok] = len(vocab)
            tid = vocab[tok]
            label_word_counts[lab][tid] = label_word_counts[lab].get(tid, 0) + 1
            label_totals[lab] += 1

    # If not enough training signal, just return component hits (still useful).
    trained_docs = sum(label_docs.values())
    if trained_docs < 10 or len(vocab) < 50:
        keys = sorted(set(component_hits)) or None
        return {
            "domain": d,
            "issue_keys": keys,
            "reason": "weak_training_signal",
            "component_hits": len(component_hits),
            "trained_docs": trained_docs,
        }

    import math

    # Priors with Laplace smoothing
    alpha = 1.0
    total_docs = float(trained_docs)
    priors = {dd: math.log((label_docs[dd] + alpha) / (total_docs + alpha * len(domains))) for dd in domains}
    V = float(len(vocab))

    def _predict_domain(text: str) -> Dict[str, float]:
        toks = _tokenize_simple(text)
        if not toks:
            return {dd: 0.0 for dd in domains}
        # bag-of-words counts
        counts: Dict[int, int] = {}
        for tok in toks:
            tid = vocab.get(tok)
            if tid is None:
                continue
            counts[tid] = counts.get(tid, 0) + 1

        scores: Dict[str, float] = {}
        for dd in domains:
            s = priors[dd]
            denom = label_totals[dd] + alpha * V
            wc = label_word_counts[dd]
            for tid, c in counts.items():
                num = wc.get(tid, 0) + alpha
                s += c * math.log(num / denom)
            scores[dd] = s

        # softmax to probs
        m = max(scores.values())
        exps = {dd: math.exp(scores[dd] - m) for dd in domains}
        Z = sum(exps.values()) or 1.0
        return {dd: float(exps[dd] / Z) for dd in domains}

    # Predict domain for each issue and filter
    ml_hits: List[str] = []
    for it in items:
        k = it["issue_key"]
        if not k:
            continue
        probs = _predict_domain(_text_for(it))
        if probs.get(d, 0.0) >= 0.35:
            ml_hits.append(k)

    # Merge + stabilize order
    merged: List[str] = []
    seen = set()
    for k in component_hits + ml_hits:
        kk = str(k or "").strip().upper()
        if not kk or kk in seen:
            continue
        seen.add(kk)
        merged.append(kk)

    return {
        "domain": d,
        "issue_keys": merged or None,
        "reason": "component_and_ml",
        "component_hits": len(component_hits),
        "ml_hits": len(ml_hits),
        "trained_docs": trained_docs,
        "vocab": len(vocab),
    }


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
        if getattr(issue, "os", None):
            parts.append(f"OS: {getattr(issue, 'os')}")
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
            "os": getattr(issue, "os", None),
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


def intake_issue_from_user_input(
    *,
    ctx: Dict[str, Any],
    issue_key: str,
    summary: str,
    domain: Optional[str] = None,
    os: Optional[str] = None,
    description: Optional[str] = None,
    logs: Optional[str] = None,
    components: Optional[List[str]] = None,
    labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create/update a JIRA issue row from *user-provided* inputs (offline-friendly).

    This supports the "new JIRA analysis" flow where you have:
      - issue_key (e.g. SYSCROS-123)
      - summary (e.g. Video flicker)
      - optional domain/os/logs (logs are stored in raw + optionally embedded text)

    We also generate/update an embedding for semantic search in `jira_embeddings`.
    """
    key = str(issue_key or "").strip().upper()
    if not key or not JIRA_ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue_key: {issue_key!r}")
    s = str(summary or "").strip()
    if not s:
        raise ValueError("summary is required")

    # Avoid storing gigantic raw logs in SQL text columns.
    def _truncate(text: Optional[str], max_chars: int) -> Optional[str]:
        t = str(text or "").strip()
        if not t:
            return None
        if len(t) <= max_chars:
            return t
        return t[: max_chars - 3] + "..."

    domain_s = str(domain or "").strip() or None
    os_s = str(os or "").strip() or None
    if not os_s:
        # Default to ChromeOS for SYSCROS intake unless explicitly provided.
        os_s = "chromeos"
    desc_s = _truncate(description, 200_000)
    logs_s = _truncate(logs, 200_000)
    components_s = [str(c).strip() for c in (components or []) if str(c).strip()] or None
    labels_s = [str(l).strip() for l in (labels or []) if str(l).strip()] or None

    # Build an embedding text blob (similar to get_issue_from_db builder).
    parts: List[str] = [f"Issue: {key}", f"Summary: {s}"]
    if desc_s:
        parts.append(f"Description: {desc_s}")
    if domain_s:
        parts.append(f"Domain: {domain_s}")
    if os_s:
        parts.append(f"OS: {os_s}")
    if components_s:
        parts.append(f"Components: {', '.join(components_s)}")
    if labels_s:
        parts.append(f"Labels: {', '.join(labels_s)}")
    if logs_s:
        # Keep logs clearly labeled so downstream prompts can treat it as evidence.
        parts.append("Logs:\n" + logs_s)
    embedding_text = "\n".join(parts).strip()

    raw = {
        "source": "user_intake",
        "issue_key": key,
        "summary": s,
        "description": desc_s,
        "domain": domain_s,
        "os": os_s,
        "components": components_s,
        "labels": labels_s,
        "logs": logs_s,
    }

    db = SessionLocal()
    try:
        issue = JiraIssue(
            issue_key=key,
            jira_id=None,
            summary=s,
            description=desc_s,
            status="NEW",
            priority=None,
            assignee=None,
            issue_type="UserIntake",
            program_theme=None,
            os=os_s,
            labels=labels_s,
            components=components_s,
            comments=None,
            url=None,
            raw=raw,
        )
        db.merge(issue)

        emb = generate_embedding(embedding_text, task_type="retrieval_document")
        if not isinstance(emb, list) or len(emb) == 0:
            raise ValueError("Failed to generate embedding for intake issue")
        db.merge(JiraEmbedding(issue_key=key, embedding=emb))

        db.commit()
        return {
            "issue_key": key,
            "summary": s,
            "domain": domain_s,
            "os": os_s,
            "embedded": True,
            "embedding_text": embedding_text,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_analysis_run(
    *,
    ctx: Dict[str, Any],
    issue_key: str,
    idempotency_key: Optional[str] = None,
    domain: Optional[str] = None,
    os: Optional[str] = None,
    logs_fingerprint: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    report: Optional[str] = None,
    analysis: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a swarm/workflow run output for later retrieval.
    """
    key = str(issue_key or "").strip().upper()
    if not key or not JIRA_ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue_key: {issue_key!r}")

    db = SessionLocal()
    try:
        idem = str(idempotency_key or "").strip() or None
        if idem:
            existing = (
                db.query(JiraAnalysisRun)
                .filter(JiraAnalysisRun.issue_key == key, JiraAnalysisRun.idempotency_key == idem)
                .order_by(JiraAnalysisRun.created_at.desc())
                .first()
            )
            if existing:
                return {"id": str(existing.id), "issue_key": key, "saved": True, "idempotent": True}

        row = JiraAnalysisRun(
            issue_key=key,
            idempotency_key=idem,
            domain=str(domain or "").strip() or None,
            os=str(os or "").strip() or None,
            logs_fingerprint=str(logs_fingerprint or "").strip() or None,
            inputs=inputs if isinstance(inputs, dict) else None,
            report=str(report or "").strip() or None,
            analysis=str(analysis or "").strip() or None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": str(row.id), "issue_key": key, "saved": True}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def find_related_issue_keys_using_jira_text_search(
    *,
    ctx: Dict[str, Any],
    issue_key: str,
    summary: str,
    max_results: int = 10,
    max_comments: int = 10,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    JIRA-native related issue search using JQL `text ~` with iterative query expansions.

    This matches the algorithm you described:
      - pass1: title cleaned (strip bracket chars but keep inner tokens)
      - pass2: platform removed (remove bracketed groups entirely)
      - pass3: LLM-shortened variants
      - pass4: LLM one-liner summaries used as queries

    Returns:
      {
        "source": "jira_jql_text",
        "queries": [ ... ],
        "issue_keys": [ ... ],
        "error": optional str
      }
    """
    import json
    import re

    from app.agents.tools import llm_tools

    key = str(issue_key or "").strip().upper()
    if not key or not JIRA_ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue_key: {issue_key!r}")
    title = str(summary or "").strip()
    if not title:
        raise ValueError("summary is required")

    proj = (str(project or "").strip().upper() or None)
    if not proj and "-" in key:
        proj = key.split("-", 1)[0].strip().upper() or None

    def _norm(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def _strip_brackets_keep_tokens(s: str) -> str:
        # "[MTL Rex][A2] Foo" -> "MTL Rex A2 Foo"
        s = s.replace("[", " ").replace("]", " ")
        return _norm(s)

    def _remove_bracketed_groups(s: str) -> str:
        # remove [...] blocks entirely
        s2 = re.sub(r"\[[^\]]*\]", " ", s or "")
        return _norm(s2)

    def _jql_quote(s: str) -> str:
        # Quote as a JQL string literal. Keep it simple: escape quotes/backslashes.
        s = (s or "").replace("\\", "\\\\").replace('"', '\\"')
        return f"\\\"{s}\\\""

    def _make_jql(q: str) -> str:
        q = _norm(q)
        if not q:
            return ""
        # Keep queries short; JIRA text~ works better with concise phrases
        if len(q) > 160:
            q = q[:160].rstrip()
        if proj:
            return f'project = {proj} AND key != "{key}" AND text ~ "{_jql_quote(q)}" ORDER BY updated DESC'
        return f'key != "{key}" AND text ~ "{_jql_quote(q)}" ORDER BY updated DESC'

    # Pass 1/2 (deterministic)
    q1 = _strip_brackets_keep_tokens(title)
    q2 = _remove_bracketed_groups(title)

    # Pass 3/4 (LLM expansions) – request JSON for robust parsing.
    llm_out = llm_tools.subagent(
        ctx=ctx,
        prompts=[
            "You generate JIRA full-text search query variants.",
            "Return STRICT JSON with keys: shortened_titles (list[str]), one_liners (list[str]).",
            "Each item must be <= 12 words, no quotes, no markdown.",
            "Do not include the JIRA key itself.",
        ],
        input_data={"summary": title},
        temperature=0.0,
    )

    shortened: list[str] = []
    one_liners: list[str] = []
    try:
        data = json.loads(str(llm_out or "").strip() or "{}")
        if isinstance(data, dict):
            if isinstance(data.get("shortened_titles"), list):
                shortened = [str(x).strip() for x in data.get("shortened_titles") if str(x).strip()]
            if isinstance(data.get("one_liners"), list):
                one_liners = [str(x).strip() for x in data.get("one_liners") if str(x).strip()]
    except Exception:
        # Offline/LLM-disabled fallback: simple variants.
        shortened = []
        one_liners = []

    queries: list[str] = []
    for q in [q1, q2] + shortened[:5] + one_liners[:5]:
        q = _norm(q)
        if not q:
            continue
        if q.lower() == title.lower():
            pass
        if q not in queries:
            queries.append(q)
        if len(queries) >= 12:
            break

    try:
        jira = JiraService.from_env()
    except Exception as e:
        return {"source": "jira_jql_text", "queries": queries, "issue_keys": [], "error": str(e)}

    found: list[str] = []
    seen = {key}
    used_jql: list[str] = []

    for q in queries:
        jql = _make_jql(q)
        if not jql:
            continue
        used_jql.append(jql)
        try:
            raws = jira.search(jql, max_results=int(max_results))
        except Exception:
            raws = []
        for raw in raws:
            k = str((raw or {}).get("key") or "").strip().upper()
            if not k or k in seen:
                continue
            seen.add(k)
            found.append(k)
            if len(found) >= int(max_results):
                break
        if len(found) >= int(max_results):
            break

    return {"source": "jira_jql_text", "queries": queries, "jql": used_jql, "issue_keys": found}


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
    include_issue_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Query -> embedding -> cosine similarity search against jira_embeddings.
    """
    query_embedding = generate_embedding(query, task_type="retrieval_query")
    results = find_similar_jira(
        query_embedding,
        limit=limit,
        exclude_issue_keys=exclude_issue_keys,
        include_issue_keys=include_issue_keys,
    )
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

