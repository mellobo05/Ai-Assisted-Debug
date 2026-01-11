"""
Test script to verify RAG pipeline is working
"""
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
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return
    
    result = response.json()
    session_id = result.get("session_id")
    status = result.get("status")
    
    print(f"✅ Request successful!")
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
            print(f"✅ Session found in database")
            print(f"   Issue: {session.issue_summary}")
            print(f"   Domain: {session.domain}")
            print(f"   OS: {session.os}")
            print(f"   Status: {session.status}")
            
            # Check embedding
            embedding = db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session_id).first()
            if embedding:
                print(f"✅ Embedding generated successfully!")
                print(f"   Embedding vector size: {len(embedding.embedding) if embedding.embedding else 0}")
                print(f"   Expected size: 768 (Gemini embedding-001)")
                
                if len(embedding.embedding) == 768:
                    print("\n🎉 RAG Pipeline is working correctly!")
                else:
                    print(f"\n⚠️  Warning: Embedding size is {len(embedding.embedding)}, expected 768")
            else:
                print("❌ Embedding not found in database")
                print("   The RAG pipeline may still be processing or encountered an error")
        else:
            print(f"❌ Session not found in database")
    except Exception as e:
        print(f"❌ Error checking database: {e}")
    finally:
        db.close()
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    try:
        test_rag_pipeline()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the API.")
        print("   Make sure the server is running: python -m uvicorn backend.app.main:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")
