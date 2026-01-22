from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
from uuid import UUID

from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding
from app.services.rag import process_rag_pipeline
from app.services.search import find_similar_jira
from app.services.embeddings import generate_embedding
from app.integrations.jira.client import JiraService, build_embedding_text, extract_issue_fields
from app.models.jira import JiraIssue, JiraEmbedding
from app.schemas.debug import DebugRequest, DebugStartResponse, DebugStatusResponse
from app.schemas.jira import JiraSyncRequest, JiraSyncResponse
from app.schemas.search import QueryRequest, SearchResponse, JiraSearchResult

app = FastAPI(title="AI Assisted Debugger")

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

