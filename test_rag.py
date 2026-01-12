"""
Test script to verify RAG pipeline is working
"""
import sys
sys.path.insert(0, 'backend')

import requests
import time
import json
from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding

# API endpoint
API_URL = "http://127.0.0.1:8000/debug"

# Test data
test_request = {
    "issue_summary": "Video flicker during playback",
    "domain": "graphics",
    "os": "android",
    "logs": "E SurfaceFlinger: failed to allocate buffer"
}

def test_rag_pipeline():
    print("=" * 50)
    print("Testing RAG Pipeline")
    print("=" * 50)
    
    # Step 1: Send POST request
    print("\n1. Sending POST request to /debug endpoint...")
    response = requests.post(API_URL, json=test_request)
    
    if response.status_code != 200:
        print(f"[ERROR] Error: {response.status_code}")
        print(response.text)
        return
    
    result = response.json()
    session_id = result.get("session_id")
    status = result.get("status")
    
    print(f"[OK] Request successful!")
    print(f"   Session ID: {session_id}")
    print(f"   Status: {status}")
    
    # Step 2: Wait for background task to complete
    print("\n2. Waiting for RAG pipeline to process (5 seconds)...")
    time.sleep(5)
    
    # Step 3: Check database
    print("\n3. Checking database for results...")
    db = SessionLocal()
    
    try:
        # Check session
        session = db.query(DebugSession).filter(DebugSession.id == session_id).first()
        if session:
            print(f"[OK] Session found in database")
            print(f"   Issue: {session.issue_summary}")
            print(f"   Domain: {session.domain}")
            print(f"   OS: {session.os}")
            print(f"   Status: {session.status}")
            
            # Check embedding
            embedding = db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session_id).first()
            if embedding:
                print(f"[OK] Embedding generated successfully!")
                # Handle both JSON (list) and Vector types
                emb_data = embedding.embedding
                if isinstance(emb_data, list):
                    emb_size = len(emb_data)
                else:
                    emb_size = len(emb_data) if emb_data else 0
                print(f"   Embedding vector size: {emb_size}")
                print(f"   Expected size: 768 (Gemini embedding-001)")
                
                if emb_size == 768:
                    print("\n[SUCCESS] RAG Pipeline is working correctly!")
                else:
                    print(f"\n[WARNING] Embedding size is {emb_size}, expected 768")
            else:
                print("[ERROR] Embedding not found in database")
                print("   The RAG pipeline may still be processing or encountered an error")
        else:
            print(f"[ERROR] Session not found in database")
    except Exception as e:
        print(f"[ERROR] Error checking database: {e}")
    finally:
        db.close()
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    try:
        test_rag_pipeline()
    except requests.exceptions.ConnectionError:
        print("[ERROR] Could not connect to the API.")
        print("   Make sure the server is running:")
        print("   python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
