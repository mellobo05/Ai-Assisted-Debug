from fastapi import FastAPI,BackgroundTasks
from pydantic import BaseModel
from uuid import uuid4
import asyncio

from app.db.session import SessionLocal
from app.models.debug import DebugSession
from app.services.rag import process_rag_pipeline

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


    

