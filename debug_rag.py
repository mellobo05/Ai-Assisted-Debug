"""
Enhanced debugging script for RAG pipeline
"""
import sys
sys.path.insert(0, 'backend')

import requests
import time
import json
from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding

API_URL = "http://127.0.0.1:8000/debug"

test_request = {
    "issue_summary": "Video flicker during playback",
    "domain": "graphics",
    "os": "android",
    "logs": "E SurfaceFlinger: failed to allocate buffer"
}

def check_server():
    """Check if server is running"""
    try:
        response = requests.get("http://127.0.0.1:8000/docs", timeout=2)
        return response.status_code == 200
    except:
        return False

def test_rag_with_retry(max_wait=10, check_interval=1):
    """Test RAG pipeline with retry logic"""
    print("=" * 60)
    print("RAG Pipeline Debug Test")
    print("=" * 60)
    
    # Check server
    print("\n[1] Checking server status...")
    if not check_server():
        print("[ERROR] Server is not running!")
        print("   Start server: python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000")
        return
    print("[OK] Server is running")
    
    # Send request
    print("\n[2] Sending POST request to /debug...")
    try:
        response = requests.post(API_URL, json=test_request, timeout=10)
        if response.status_code != 200:
            print(f"[ERROR] HTTP {response.status_code}: {response.text}")
            return
        result = response.json()
        session_id = result.get("session_id")
        print(f"[OK] Request successful")
        print(f"   Session ID: {session_id}")
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        return
    
    # Wait and check database
    print(f"\n[3] Waiting for background task (checking every {check_interval}s, max {max_wait}s)...")
    db = SessionLocal()
    
    try:
        for i in range(0, max_wait, check_interval):
            time.sleep(check_interval)
            
            session = db.query(DebugSession).filter(DebugSession.id == session_id).first()
            if not session:
                print(f"   [{i+check_interval}s] Session not found in database")
                continue
            
            print(f"   [{i+check_interval}s] Session status: {session.status}")
            
            if session.status == "EMBEDDING_GENERATED":
                embedding = db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session_id).first()
                if embedding:
                    emb_data = embedding.embedding
                    emb_size = len(emb_data) if isinstance(emb_data, list) else (len(emb_data) if emb_data else 0)
                    print(f"\n[SUCCESS] RAG Pipeline completed!")
                    print(f"   Session ID: {session_id}")
                    print(f"   Status: {session.status}")
                    print(f"   Embedding size: {emb_size}")
                    print(f"   Issue: {session.issue_summary}")
                    if emb_size == 768:
                        print(f"   [OK] Embedding dimension is correct (768)")
                    else:
                        print(f"   [WARNING] Expected 768, got {emb_size}")
                    return
                else:
                    print(f"   [WARNING] Status is EMBEDDING_GENERATED but embedding not found")
            
            elif session.status == "ERROR":
                print(f"\n[ERROR] Session status is ERROR")
                print(f"   Check server logs for details")
                return
            
            elif session.status == "PROCESSING":
                print(f"   [INFO] Still processing...")
        
        # Timeout
        print(f"\n[TIMEOUT] Background task didn't complete within {max_wait} seconds")
        print(f"   Final status: {session.status if session else 'Unknown'}")
        print(f"   Check server logs for errors")
        
    except Exception as e:
        print(f"[ERROR] Database check failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_rag_with_retry(max_wait=15, check_interval=2)
