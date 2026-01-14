from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from uuid import uuid4
import asyncio
import os

from app.db.session import SessionLocal
from app.models.debug import DebugSession
from app.services.rag import process_rag_pipeline
from app.services.search import find_similar
from app.services.embeddings import generate_embedding

app = FastAPI(title="AI Assisted Debugger")

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

class DebugRequest(BaseModel):
    issue_summary: str
    domain: str
    os: str
    logs: str

class QueryRequest(BaseModel):
    query: str
    limit: int = 3

@app.post("/debug")
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
        
        return {
            "session_id": str(session.id),
            "status": "PROCESSING"
        }
    except Exception as e:
        print(f"Error in start_debug: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if 'db' in locals():
            db.close()

@app.post("/search")
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
        env_path = Path(__file__).parent.parent.parent.parent / '.env'
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
        
        # Generate embedding for the query
        use_mock = os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true"
        print(f"[SEARCH] USE_MOCK_EMBEDDING={use_mock}")
        
        # Generate embedding (generate_embedding handles mock mode internally)
        try:
            query_embedding = generate_embedding(request.query, task_type="retrieval_query")
            if not isinstance(query_embedding, list) or len(query_embedding) == 0:
                raise ValueError(f"Invalid embedding generated: type={type(query_embedding)}, length={len(query_embedding) if isinstance(query_embedding, list) else 'N/A'}")
            print(f"[SEARCH] Query embedding generated, size: {len(query_embedding)}")
        except Exception as e:
            print(f"[SEARCH] Error generating query embedding: {e}")
            import traceback
            traceback.print_exc()
            
            # Always fall back to mock if anything fails
            print("[SEARCH] Falling back to mock embedding...")
            import hashlib
            hash_obj = hashlib.md5(request.query.encode())
            hash_int = int(hash_obj.hexdigest(), 16)
            query_embedding = [(hash_int % 1000) / 1000.0 for _ in range(768)]
            print(f"[SEARCH] Mock embedding generated, size: {len(query_embedding)}")
        
        # Find similar sessions
        try:
            similar_sessions = find_similar(query_embedding, limit=request.limit)
            print(f"[SEARCH] Found {len(similar_sessions)} similar sessions")
        except Exception as e:
            print(f"[SEARCH] Error finding similar sessions: {e}")
            import traceback
            traceback.print_exc()
            # Return empty results instead of failing
            similar_sessions = []
        
        return {
            "query": request.query,
            "results_count": len(similar_sessions),
            "results": similar_sessions
        }
        
    except Exception as e:
        # If it's already an HTTPException, re-raise it
        if isinstance(e, HTTPException):
            raise
        
        print(f"[SEARCH] Unexpected error in search endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during search: {str(e)}"
        )

