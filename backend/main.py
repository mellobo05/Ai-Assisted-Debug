from fastapi import FastAPI,BackgroundTasks
from uuid import uuid4

app = FastAPI()

@app.post("/debug")
def start_debug(background_tasks:BackgroundTasks):
    session_id = str(uuid4())
    #1. Save to DB 

    #2. Run analysis in background
    background_tasks.add_task(run_debug_analysis,session_id)
    return {
            "session_id":session_id,
            "status":"Processing"
            }

def run_debug_analysis(session_id:str):
    #TODO: 
    #-Fetch logs from DB
    #-Run AI
    #-Store results in DB
    print(f"Starting debug analysis for session {session_id}")

    

