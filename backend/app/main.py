from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
from uuid import UUID

from app.db.session import SessionLocal, engine
from app.models.debug import DebugSession, DebugEmbedding
from app.services.rag import process_rag_pipeline
from app.services.search import find_similar_jira
from app.services.embeddings import generate_embedding
from app.integrations.jira.client import JiraService, build_embedding_text, extract_issue_fields
from app.models.jira import JiraIssue, JiraEmbedding
from app.models.jira_analysis import JiraAnalysisRun
from app.schemas.debug import DebugRequest, DebugStartResponse, DebugStatusResponse
from app.schemas.jira import (
    JiraSyncRequest,
    JiraSyncResponse,
    JiraIntakeRequest,
    JiraIntakeResponse,
    JiraSummarizeRequest,
    JiraSummarizeResponse,
    JiraAnalyzeRequest,
    JiraAnalyzeResponse,
)
from app.schemas.search import QueryRequest, SearchResponse, JiraSearchResult
from app.schemas.snippets import SnippetSaveRequest, SnippetSaveResponse, SnippetListResponse

app = FastAPI(title="AI Assisted Debugger")

# In-memory summarize jobs (kept simple; good enough for local dev).
_JIRA_SUMMARIZE_JOBS: dict[str, dict] = {}
_JIRA_ANALYZE_JOBS: dict[str, dict] = {}
# Map idempotency_key -> job_id (dedupe repeated clicks)
_JIRA_ANALYZE_JOB_BY_IDEM: dict[str, str] = {}

# Warm up embedding provider on startup to avoid first-request latency (esp. SBERT).
@app.on_event("startup")
async def _warmup_embeddings() -> None:
    try:
        provider = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()
        if provider == "sbert":
            # Trigger model load once at boot.
            generate_embedding("warmup", task_type="retrieval_query")
            print("[STARTUP] SBERT warmup complete")
    except Exception as e:
        # Don't block server start if warmup fails (e.g., model not downloaded yet).
        print(f"[STARTUP] Embedding warmup skipped/failed: {e}")


@app.on_event("startup")
async def _ensure_db_schema() -> None:
    """
    Best-effort schema ensure for dev (no migrations framework).

    - Create missing tables (safe)
    - Add missing columns (safe additive migrations)
    """
    try:
        # Create missing tables (does not alter existing).
        from app.db.base import Base
        from app.models import debug as _m_debug  # noqa: F401
        from app.models import jira as _m_jira  # noqa: F401
        from app.models import jira_analysis as _m_ja  # noqa: F401
        from app.models import snippets as _m_snip  # noqa: F401

        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[STARTUP] DB create_all skipped/failed: {e}")

    # Additive column migration: jira_issues.related_issue_keys
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            r = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='jira_issues'
                      AND column_name='related_issue_keys'
                    """
                )
            ).first()
            if not r:
                conn.execute(text("ALTER TABLE public.jira_issues ADD COLUMN related_issue_keys JSON NULL"))
                print("[STARTUP] DB migrated: added jira_issues.related_issue_keys")
    except Exception as e:
        print(f"[STARTUP] DB migration skipped/failed: {e}")

    # Additive column migration: jira_analysis_runs.idempotency_key
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            r = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='jira_analysis_runs'
                      AND column_name='idempotency_key'
                    """
                )
            ).first()
            if not r:
                conn.execute(text("ALTER TABLE public.jira_analysis_runs ADD COLUMN idempotency_key VARCHAR NULL"))
                print("[STARTUP] DB migrated: added jira_analysis_runs.idempotency_key")
    except Exception as e:
        print(f"[STARTUP] DB migration skipped/failed (analysis idempotency): {e}")

# Allow the React dev server to call the API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/test-background")
async def test_background(background_tasks: BackgroundTasks):
    """Test endpoint to verify background tasks work"""
    def test_task():
        print("[TEST] Background task executed!")
        import time
        time.sleep(1)
        print("[TEST] Background task completed!")
    background_tasks.add_task(test_task)
    return {"message": "Background task scheduled"}

@app.post("/debug", response_model=DebugStartResponse)
async def start_debug(request: DebugRequest, background_tasks: BackgroundTasks):
    try:
        #1. Save to DB 
        db = SessionLocal()

        session = DebugSession(
                issue_summary=request.issue_summary,
                domain=request.domain, 
                os=request.os, 
                logs=request.logs
                )
        db.add(session)
        db.commit()
        db.refresh(session)
         
        print(f"Saved session {session.id} with status PROCESSING")
        print(f"Starting background task for RAG pipeline...")
        # Ensure environment variables are available to background task
        import os
        use_mock = os.getenv("USE_MOCK_EMBEDDING", "false")
        api_key = os.getenv("GEMINI_API_KEY", "")
        
        # Use asyncio to run the task in background
        async def run_rag_async():
            # Run the sync function in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, process_rag_pipeline, str(session.id), use_mock, api_key)
        
        # Schedule the async task
        asyncio.create_task(run_rag_async())
        print(f"Background task scheduled for session {session.id}")
        
        return DebugStartResponse(
            session_id=session.id,
            status="PROCESSING",
            os=session.os,
            domain=session.domain,
            issue_summary=session.issue_summary,
        )
    except Exception as e:
        print(f"Error in start_debug: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if 'db' in locals():
            db.close()


@app.get("/debug/{session_id}", response_model=DebugStatusResponse)
async def get_debug_status(session_id: UUID):
    """
    Fetch the latest status for a debug session.
    Useful for UI polling since embeddings are generated asynchronously.
    """
    db = SessionLocal()
    try:
        session = db.query(DebugSession).filter(DebugSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Debug session not found")

        has_embedding = (
            db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session.id).first()
            is not None
        )

        return DebugStatusResponse(
            session_id=str(session.id),
            status=session.status or "PROCESSING",
            os=session.os,
            domain=session.domain,
            issue_summary=session.issue_summary,
            has_embedding=has_embedding,
        )
    finally:
        db.close()

@app.post("/search", response_model=SearchResponse)
async def search_similar(request: QueryRequest):
    """
    Search for similar debug sessions based on a query.
    Uses RAG to find relevant context from the vector database.
    """
    try:
        print(f"[SEARCH] Processing query: {request.query}")

        # Ensure .env is loaded (in case server started without it)
        from dotenv import load_dotenv
        from pathlib import Path

        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            # Do not override shell env vars (PowerShell should win)
            load_dotenv(dotenv_path=env_path, override=False)

        # Generate embedding (generate_embedding handles mock mode internally)
        use_mock = os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true"
        print(f"[SEARCH] USE_MOCK_EMBEDDING={use_mock}")

        try:
            query_embedding = generate_embedding(request.query, task_type="retrieval_query")
            if not isinstance(query_embedding, list) or len(query_embedding) == 0:
                raise ValueError(
                    f"Invalid embedding generated: type={type(query_embedding)}, "
                    f"length={len(query_embedding) if isinstance(query_embedding, list) else 'N/A'}"
                )
            print(f"[SEARCH] Query embedding generated, size: {len(query_embedding)}")
        except Exception as e:
            print(f"[SEARCH] Error generating query embedding: {e}")
            import traceback

            traceback.print_exc()
            print("[SEARCH] Falling back to mock embedding...")
            import hashlib
            import math
            import random

            hash_int = int(hashlib.md5(request.query.encode()).hexdigest(), 16)
            provider = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()
            # Match the most likely dimension for the chosen provider so DB comparisons work.
            if provider == "sbert":
                dim = int(os.getenv("MOCK_EMBED_DIM", "384"))
            else:
                dim = int(os.getenv("MOCK_EMBED_DIM", "768"))
            # Generate a deterministic but non-colinear mock vector; normalize for cosine similarity.
            seed = (hash_int & 0xFFFFFFFF)
            rng = random.Random(seed)
            query_embedding = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
            norm = math.sqrt(sum((x * x) for x in query_embedding)) or 1.0
            query_embedding = [float(x / norm) for x in query_embedding]
            print(f"[SEARCH] Mock embedding generated, size: {len(query_embedding)}")

        # JIRA is the retrieval source (debug_sessions removed/ignored)
        similar_jira_raw = find_similar_jira(query_embedding, limit=request.limit)
        # Validate/normalize results shape
        results = [JiraSearchResult(**r) for r in similar_jira_raw]
        return SearchResponse(query=request.query, results_count=len(results), results=results)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[SEARCH] Unexpected error in search endpoint: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error during search: {e}")


@app.post("/jira/sync", response_model=JiraSyncResponse)
async def jira_sync(request: JiraSyncRequest):
    """
    Ingest JIRA issues into Postgres + embeddings for semantic search.

    Provide either:
    - issue_keys: ["PROJ-123", "PROJ-456"]
    - jql: "project = PROJ ORDER BY updated DESC"
    """
    # Ensure .env is loaded for JIRA env vars in dev
    from dotenv import load_dotenv
    from pathlib import Path

    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        # Do not override shell env vars (PowerShell should win)
        load_dotenv(dotenv_path=env_path, override=False)

    try:
        jira = JiraService.from_env()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JIRA config error: {e}")

    # Fetch (include latest comments to support "fix/context" retrieval)
    raw_issues: list[dict] = []
    try:
        if request.issue_keys:
            for key in request.issue_keys:
                raw_issues.append(jira.fetch_issue_with_comments(key, max_comments=request.max_comments))
        else:
            raw_issues = jira.search_with_comments(
                request.jql or "",
                max_results=request.max_results,
                max_comments=request.max_comments,
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch from JIRA: {e}")

    # Store + embed
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

            # Embed
            text = build_embedding_text(raw)
            emb = generate_embedding(text, task_type="retrieval_document")
            if not isinstance(emb, list) or len(emb) == 0:
                continue

            db.merge(JiraEmbedding(issue_key=issue_key, embedding=emb))
            embedded += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to store/embed issues: {e}")
    finally:
        db.close()

    return {
        "fetched": len(raw_issues),
        "ingested": ingested,
        "embedded": embedded,
    }


@app.post("/jira/intake", response_model=JiraIntakeResponse)
async def jira_intake(request: JiraIntakeRequest):
    """
    Offline-friendly intake: store a user-provided issue key + summary (+ optional logs)
    into `jira_issues` and generate an embedding for similarity search.
    """
    from app.agents.tools import jira_tools

    out = jira_tools.intake_issue_from_user_input(
        ctx={"inputs": {}, "steps": {}},
        issue_key=request.issue_key,
        summary=request.summary,
        domain=request.domain,
        os=request.os,
        description=request.description,
        logs=request.logs,
    )
    return {"issue_key": str(out.get("issue_key") or request.issue_key), "embedded": bool(out.get("embedded"))}


@app.post("/jira/summarize", response_model=JiraSummarizeResponse)
async def jira_summarize(request: JiraSummarizeRequest):
    """
    Fetch + summarize an existing issue from the local DB (jira_issues/jira_embeddings).

    Returns a single `report + analysis` output for the UI.
    """
    import uuid

    from app.agents.swarm import SwarmConfig, run_syscros_swarm

    mode = (request.analysis_mode or "async").strip().lower()
    if mode not in {"async", "sync", "skip"}:
        mode = "async"

    cfg = SwarmConfig(
        limit=int(request.limit),
        min_local_score=float(request.min_local_score),
        external_knowledge=bool(request.external_knowledge),
        external_max_results=int(request.external_max_results),
    )

    component = str(getattr(request, "component", None) or "").strip() or None
    domain = str(getattr(request, "domain", None) or "").strip() or None

    # 1) Always compute report fast (skip LLM)
    out_report = run_syscros_swarm(
        issue_key=request.issue_key,
        logs_text=request.logs,
        domain=domain,
        component=component,
        os_name=request.os,
        save_run=False,
        do_analysis=False,
        config=cfg,
    )
    report = str(out_report.get("report") or "")

    if mode == "skip":
        return {
            "issue_key": str(request.issue_key),
            "report": report,
            "analysis": "",
            "saved_run": None,
            "analysis_status": "SKIPPED",
            "job_id": None,
        }

    if mode == "sync":
        out_full = run_syscros_swarm(
            issue_key=request.issue_key,
            logs_text=request.logs,
            domain=domain,
            component=component,
            os_name=request.os,
            save_run=bool(request.save_run),
            do_analysis=True,
            config=cfg,
        )
        return {
            "issue_key": str(request.issue_key),
            "report": str(out_full.get("report") or report),
            "analysis": str(out_full.get("analysis") or ""),
            "saved_run": out_full.get("saved_run"),
            "analysis_status": "COMPLETED",
            "job_id": None,
        }

    # mode == async: spawn background job for analysis
    job_id = uuid.uuid4().hex
    _JIRA_SUMMARIZE_JOBS[job_id] = {
        "status": "PROCESSING",
        "issue_key": str(request.issue_key),
        "report": report,
        "analysis": "",
        "error": None,
        "saved_run": None,
    }

    async def _run_analysis_job() -> None:
        try:
            # Run heavy work in threadpool (avoid blocking event loop)
            loop = asyncio.get_event_loop()

            def _do_work():
                return run_syscros_swarm(
                    issue_key=request.issue_key,
                    logs_text=request.logs,
                    domain=domain,
                    component=component,
                    os_name=request.os,
                    save_run=bool(request.save_run),
                    do_analysis=True,
                    config=cfg,
                )

            out_full = await loop.run_in_executor(None, _do_work)
            _JIRA_SUMMARIZE_JOBS[job_id] = {
                "status": "COMPLETED",
                "issue_key": str(request.issue_key),
                "report": str(out_full.get("report") or report),
                "analysis": str(out_full.get("analysis") or ""),
                "error": None,
                "saved_run": out_full.get("saved_run"),
            }
        except Exception as e:
            _JIRA_SUMMARIZE_JOBS[job_id] = {
                "status": "ERROR",
                "issue_key": str(request.issue_key),
                "report": report,
                "analysis": "",
                "error": f"{type(e).__name__}: {str(e).strip()}" if str(e).strip() else type(e).__name__,
                "saved_run": None,
            }

    asyncio.create_task(_run_analysis_job())

    return {
        "issue_key": str(request.issue_key),
        "report": report,
        "analysis": "",
        "saved_run": None,
        "analysis_status": "PROCESSING",
        "job_id": job_id,
    }


@app.get("/jira/summarize/job/{job_id}", response_model=JiraSummarizeResponse)
async def jira_summarize_job(job_id: str):
    job = _JIRA_SUMMARIZE_JOBS.get(str(job_id).strip())
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = str(job.get("status") or "PROCESSING")
    if status == "ERROR":
        # Keep response model stable; include error text inside analysis.
        err = str(job.get("error") or "Unknown error")
        return {
            "issue_key": str(job.get("issue_key") or ""),
            "report": str(job.get("report") or ""),
            "analysis": f"Analysis: failed ({err})\n",
            "saved_run": job.get("saved_run"),
            "analysis_status": "ERROR",
            "job_id": str(job_id),
        }
    return {
        "issue_key": str(job.get("issue_key") or ""),
        "report": str(job.get("report") or ""),
        "analysis": str(job.get("analysis") or ""),
        "saved_run": job.get("saved_run"),
        "analysis_status": status,
        "job_id": str(job_id),
    }


@app.post("/jira/analyze", response_model=JiraAnalyzeResponse)
async def jira_analyze(request: JiraAnalyzeRequest):
    """
    Single-input pipeline for the UI (intake + caching + related-jira tracking + summarize).
    """
    import uuid

    from app.agents.swarm import SwarmConfig, run_syscros_swarm
    from app.agents.tools import jira_tools

    import hashlib
    import json

    key = str(request.issue_key).strip().upper()
    summary = str(request.summary or "").strip()
    component_in = str(getattr(request, "component", None) or "").strip() or None
    domain_in = str(getattr(request, "domain", None) or "").strip() or None

    # Idempotency key based on the meaningful inputs.
    # This dedupes repeated clicks and prevents duplicate analysis-run rows for new issues.
    def _fp_text(s: str, n: int) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        if len(s) > n:
            s = s[-n:]
        return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:16]

    idem_payload = {
        "issue_key": key,
        "summary": summary,
        "domain": str(domain_in or "").strip().lower(),
        "component": str(component_in or "").strip().lower(),
        "os": str(request.os or "").strip().lower(),
        "logs_fp": _fp_text(str(request.logs or ""), 40000),
        "notes_fp": _fp_text(str(request.notes or ""), 20000),
        "limit": int(request.limit),
        "external_knowledge": bool(request.external_knowledge),
        "min_local_score": float(request.min_local_score),
    }
    idempotency_key = hashlib.sha256(json.dumps(idem_payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]

    mode = (request.analysis_mode or "async").strip().lower()
    if mode not in {"async", "sync", "skip"}:
        mode = "async"

    # 1) If prior analysis exists for this exact input -> return cached (idempotent)
    db = SessionLocal()
    try:
        existing = db.query(JiraIssue).filter(JiraIssue.issue_key == key).first()
        if existing and (str(existing.summary or "").strip() == summary):
            exact_run = (
                db.query(JiraAnalysisRun)
                .filter(JiraAnalysisRun.issue_key == key, JiraAnalysisRun.idempotency_key == idempotency_key)
                .order_by(JiraAnalysisRun.created_at.desc())
                .first()
            )
            if exact_run and (exact_run.analysis or "").strip():
                return {
                    "issue_key": key,
                    "summary": summary,
                    "report": str(exact_run.report or ""),
                    "analysis": str(exact_run.analysis or ""),
                    "analysis_status": "CACHED",
                    "job_id": None,
                    "related_issue_keys": existing.related_issue_keys if isinstance(existing.related_issue_keys, list) else None,
                    "cache_hit": True,
                    "saved_run": {"id": str(exact_run.id), "issue_key": key},
                }
            last_run = (
                db.query(JiraAnalysisRun)
                .filter(JiraAnalysisRun.issue_key == key)
                .order_by(JiraAnalysisRun.created_at.desc())
                .first()
            )
            if last_run and (last_run.analysis or "").strip():
                return {
                    "issue_key": key,
                    "summary": summary,
                    "report": str(last_run.report or ""),
                    "analysis": str(last_run.analysis or ""),
                    "analysis_status": "CACHED",
                    "job_id": None,
                    "related_issue_keys": existing.related_issue_keys if isinstance(existing.related_issue_keys, list) else None,
                    "cache_hit": True,
                    "saved_run": {"id": str(last_run.id), "issue_key": key} if getattr(last_run, "id", None) else None,
                }
    finally:
        db.close()

    # If an identical job is already running/completed in-memory, reuse it.
    prev_job_id = _JIRA_ANALYZE_JOB_BY_IDEM.get(idempotency_key)
    if prev_job_id:
        job = _JIRA_ANALYZE_JOBS.get(prev_job_id)
        if isinstance(job, dict):
            st = str(job.get("status") or "PROCESSING")
            if st == "PROCESSING":
                return {
                    "issue_key": str(job.get("issue_key") or key),
                    "summary": str(job.get("summary") or summary),
                    "report": str(job.get("report") or ""),
                    "analysis": "",
                    "analysis_status": "PROCESSING",
                    "job_id": str(prev_job_id),
                    "related_issue_keys": job.get("related_issue_keys"),
                    "cache_hit": False,
                    "saved_run": None,
                }
            if st == "COMPLETED":
                return {
                    "issue_key": str(job.get("issue_key") or key),
                    "summary": str(job.get("summary") or summary),
                    "report": str(job.get("report") or ""),
                    "analysis": str(job.get("analysis") or ""),
                    "analysis_status": "COMPLETED",
                    "job_id": str(prev_job_id),
                    "related_issue_keys": job.get("related_issue_keys"),
                    "cache_hit": False,
                    "saved_run": job.get("saved_run"),
                }

    # 2/3) Upsert issue (new key OR changed summary) with user input
    # Store notes as description if no description exists; and always include logs.
    description = ""
    if request.notes:
        description = str(request.notes).strip()

    resolved_component = None
    if component_in:
        try:
            resolved_component = jira_tools.resolve_component_from_db(
                ctx={"inputs": {}, "steps": {}},
                component=component_in,
            )
        except Exception:
            resolved_component = component_in

    jira_tools.intake_issue_from_user_input(
        ctx={"inputs": {}, "steps": {}},
        issue_key=key,
        summary=summary,
        domain=domain_in,
        components=[resolved_component] if resolved_component else None,
        os=request.os,
        description=description or None,
        logs=request.logs,
    )

    cfg = SwarmConfig(
        limit=int(request.limit),
        min_local_score=float(request.min_local_score),
        external_knowledge=bool(request.external_knowledge),
        external_max_results=int(request.external_max_results),
    )

    # 4) Report fast (no LLM)
    out_report = run_syscros_swarm(
        issue_key=key,
        logs_text=request.logs,
        domain=domain_in,
        component=resolved_component or component_in,
        os_name=request.os,
        save_run=False,
        do_analysis=False,
        config=cfg,
    )
    report = str(out_report.get("report") or "")

    # Related issues (preferred): live JIRA JQL text~ algorithm; fallback: local embedding top-1
    related_keys: list[str] = []
    related_source: str | None = None
    try:
        rel = jira_tools.find_related_issue_keys_using_jira_text_search(
            ctx={"inputs": {}, "steps": {}},
            issue_key=key,
            summary=summary,
            max_results=min(10, max(1, int(request.limit))),
        )
        if isinstance(rel, dict) and isinstance(rel.get("issue_keys"), list):
            related_keys = [str(x).strip().upper() for x in rel.get("issue_keys") if str(x).strip()]
            related_keys = [k for k in related_keys if k and k != key]
            if related_keys:
                related_source = "jira_jql_text"
    except Exception:
        related_keys = []
        related_source = None

    if not related_keys:
        try:
            sim = out_report.get("similar") if isinstance(out_report, dict) else None
            results = sim.get("results") if isinstance(sim, dict) else None
            if isinstance(results, list) and results:
                top = results[0] or {}
                rk = str(top.get("issue_key") or "").strip().upper()
                try:
                    score = float(top.get("similarity", 0.0))
                except Exception:
                    score = 0.0
                if rk and rk != key and score >= float(request.min_local_score):
                    related_keys = [rk]
                    related_source = "db_embeddings"
        except Exception:
            related_keys = []
            related_source = None

    if related_keys:
        db2 = SessionLocal()
        try:
            row = db2.query(JiraIssue).filter(JiraIssue.issue_key == key).first()
            if row:
                existing_list = row.related_issue_keys if isinstance(row.related_issue_keys, list) else []
                merged = []
                seen = set()
                for k in (related_keys + list(existing_list)):
                    s = str(k or "").strip().upper()
                    if not s or s in seen or s == key:
                        continue
                    seen.add(s)
                    merged.append(s)
                row.related_issue_keys = merged or None
                db2.commit()
        except Exception:
            db2.rollback()
        finally:
            db2.close()

    if mode == "skip":
        return {
            "issue_key": key,
            "summary": summary,
            "report": report,
            "analysis": "",
            "analysis_status": "SKIPPED",
            "job_id": None,
            "related_issue_keys": related_keys or None,
            "cache_hit": False,
            "saved_run": None,
        }

    if mode == "sync":
        out_full = run_syscros_swarm(
            issue_key=key,
            logs_text=request.logs,
            domain=domain_in,
            component=resolved_component or component_in,
            os_name=request.os,
            related_issue_keys=related_keys or None,
            related_source=related_source,
            analysis_idempotency_key=idempotency_key,
            save_run=bool(request.save_run),
            do_analysis=True,
            config=cfg,
        )
        return {
            "issue_key": key,
            "summary": summary,
            "report": str(out_full.get("report") or report),
            "analysis": str(out_full.get("analysis") or ""),
            "analysis_status": "COMPLETED",
            "job_id": None,
            "related_issue_keys": related_keys or None,
            "cache_hit": False,
            "saved_run": out_full.get("saved_run"),
        }

    # async: spawn analysis job
    job_id = uuid.uuid4().hex
    _JIRA_ANALYZE_JOB_BY_IDEM[idempotency_key] = job_id
    _JIRA_ANALYZE_JOBS[job_id] = {
        "status": "PROCESSING",
        "issue_key": key,
        "summary": summary,
        "report": report,
        "analysis": "",
        "error": None,
        "saved_run": None,
        "related_issue_keys": related_keys,
        "idempotency_key": idempotency_key,
    }

    async def _run_analyze_job() -> None:
        try:
            loop = asyncio.get_event_loop()

            def _do_work():
                return run_syscros_swarm(
                    issue_key=key,
                    logs_text=request.logs,
                    domain=domain_in,
                    component=resolved_component or component_in,
                    os_name=request.os,
                    related_issue_keys=related_keys or None,
                    related_source=related_source,
                    analysis_idempotency_key=idempotency_key,
                    save_run=bool(request.save_run),
                    do_analysis=True,
                    config=cfg,
                )

            out_full = await loop.run_in_executor(None, _do_work)
            _JIRA_ANALYZE_JOBS[job_id] = {
                "status": "COMPLETED",
                "issue_key": key,
                "summary": summary,
                "report": str(out_full.get("report") or report),
                "analysis": str(out_full.get("analysis") or ""),
                "error": None,
                "saved_run": out_full.get("saved_run"),
                "related_issue_keys": related_keys,
                "idempotency_key": idempotency_key,
            }
        except Exception as e:
            _JIRA_ANALYZE_JOBS[job_id] = {
                "status": "ERROR",
                "issue_key": key,
                "summary": summary,
                "report": report,
                "analysis": "",
                "error": f"{type(e).__name__}: {str(e).strip()}" if str(e).strip() else type(e).__name__,
                "saved_run": None,
                "related_issue_keys": related_keys,
                "idempotency_key": idempotency_key,
            }

    asyncio.create_task(_run_analyze_job())
    return {
        "issue_key": key,
        "summary": summary,
        "report": report,
        "analysis": "",
        "analysis_status": "PROCESSING",
        "job_id": job_id,
        "related_issue_keys": related_keys or None,
        "cache_hit": False,
        "saved_run": None,
    }


@app.get("/jira/analyze/job/{job_id}", response_model=JiraAnalyzeResponse)
async def jira_analyze_job(job_id: str):
    job = _JIRA_ANALYZE_JOBS.get(str(job_id).strip())
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = str(job.get("status") or "PROCESSING")
    if status == "ERROR":
        err = str(job.get("error") or "Unknown error")
        return {
            "issue_key": str(job.get("issue_key") or ""),
            "summary": str(job.get("summary") or ""),
            "report": str(job.get("report") or ""),
            "analysis": f"Analysis: failed ({err})\n",
            "analysis_status": "ERROR",
            "job_id": str(job_id),
            "related_issue_keys": job.get("related_issue_keys"),
            "cache_hit": False,
            "saved_run": job.get("saved_run"),
        }
    return {
        "issue_key": str(job.get("issue_key") or ""),
        "summary": str(job.get("summary") or ""),
        "report": str(job.get("report") or ""),
        "analysis": str(job.get("analysis") or ""),
        "analysis_status": status,
        "job_id": str(job_id),
        "related_issue_keys": job.get("related_issue_keys"),
        "cache_hit": False,
        "saved_run": job.get("saved_run"),
    }


@app.post("/snippets", response_model=SnippetSaveResponse)
async def save_snippet(request: SnippetSaveRequest):
    """
    Save a code snippet (kernel/userspace, c/cpp/rust) for future reference.
    """
    from app.agents.tools import snippet_tools

    out = snippet_tools.save_snippet(
        ctx={"inputs": {}, "steps": {}},
        issue_key=request.issue_key,
        domain=request.domain,
        layer=request.layer,
        language=request.language,
        file_path=request.file_path,
        content=request.content,
    )
    return out  # type: ignore[return-value]


@app.get("/snippets/{issue_key}", response_model=SnippetListResponse)
async def list_snippets(issue_key: str, limit: int = 5):
    """
    List recent code snippets stored for a JIRA issue.
    """
    from app.agents.tools import snippet_tools

    out = snippet_tools.list_snippets(ctx={"inputs": {}, "steps": {}}, issue_key=issue_key, limit=limit)
    return out  # type: ignore[return-value]

