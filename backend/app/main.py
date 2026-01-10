from fastapi import FastAPI,BackgroundTasks
from pydantic import BaseModel
from uuid import uuid4

from app.db.session import SessionLocal
from app.models.debug import DebugSession
from app.services.rag import process_rag_pipeline

app = FastAPI(title="AI Assisted Debugger")

class DebugRequest(BaseModel):
    issue_summary: str
    domain: str
    os: str
    logs: str

@app.post("/debug")
async def start_debug(request: DebugRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid4())
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
     
    background_tasks.add_task(process_rag_pipeline, session.id)

    return {
        "session_id": str(session.id),
        "status": "PROCESSING"
    }
    print(f"Saved session {session_id} with status processing")
    
    #2. Run analysis in background
    background_tasks.add_task(run_debug_analysis, request, session_id)
    return {
            "session_id":session_id,
            "status":"Processing"
            }

def run_debug_analysis(request:DebugRequest,session_id:str):
    print(f"Starting debug analysis for session {session_id}")
    print(f"Issue:{request.issue_summary}")
    print(f"Domain:{request.domain}, OS:{request.os}")
     #TODO: 
    #-Fetch logs from DB
    #-Run AI
    #-Store results in DB


    

