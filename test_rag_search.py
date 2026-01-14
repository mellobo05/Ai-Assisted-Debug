"""
Test script to verify RAG vector search functionality
Tests if the system can retrieve relevant context from vector DB based on a query
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root before importing app modules
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"[TEST] Loaded .env from: {env_path}")
    # Check if API key is set
    if os.getenv("GEMINI_API_KEY"):
        print(f"[TEST] GEMINI_API_KEY is set (length: {len(os.getenv('GEMINI_API_KEY'))})")
    else:
        print("[TEST] WARNING: GEMINI_API_KEY not found in .env")
        print("[TEST] The server will need the API key to generate embeddings")
        print("[TEST] You can set USE_MOCK_EMBEDDING=true in .env to use mock embeddings")
else:
    # Try loading from current directory
    load_dotenv(override=True)
    print("[TEST] WARNING: .env file not found in project root")
    print("[TEST] Make sure the server has GEMINI_API_KEY set in environment")

sys.path.insert(0, 'backend')

import requests
import time
import json
from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding

# API endpoints
DEBUG_API_URL = "http://127.0.0.1:8000/debug"
SEARCH_API_URL = "http://127.0.0.1:8000/search"

def test_rag_search():
    print("=" * 70)
    print("Testing RAG Vector Search - Retrieval from Vector DB".center(70))
    print("=" * 70)
    
    # Step 1: Check if we have existing data in the database
    print("\n[1] Checking existing data in vector database...")
    db = SessionLocal()
    try:
        existing_sessions = db.query(DebugSession).all()
        existing_embeddings = db.query(DebugEmbedding).all()
        
        print(f"   Found {len(existing_sessions)} sessions in database")
        print(f"   Found {len(existing_embeddings)} embeddings in database")
        
        if existing_sessions:
            print("\n   Existing sessions:")
            for session in existing_sessions:
                print(f"   - Session {session.id}:")
                print(f"     Issue: {session.issue_summary}")
                print(f"     Domain: {session.domain}")
                print(f"     OS: {session.os}")
                print(f"     Status: {session.status}")
        
        if len(existing_embeddings) == 0:
            print("\n[WARNING] No embeddings found in database!")
            print("   Creating a test session first...")
            
            # Create a test session
            test_request = {
                "issue_summary": "Video flicker during playback",
                "domain": "graphics",
                "os": "android",
                "logs": "E SurfaceFlinger: failed to allocate buffer"
            }
            
            print("\n[2] Creating test session...")
            response = requests.post(DEBUG_API_URL, json=test_request)
            
            if response.status_code != 200:
                print(f"[ERROR] Failed to create session: {response.status_code}")
                print(response.text)
                return
            
            result = response.json()
            session_id = result.get("session_id")
            print(f"[OK] Test session created: {session_id}")
            print("   Waiting for embedding generation (10 seconds)...")
            time.sleep(10)
            
            # Check database again
            existing_embeddings = db.query(DebugEmbedding).all()
            
            if len(existing_embeddings) == 0:
                print("[ERROR] Embedding still not generated. Check server logs.")
                return
    finally:
        db.close()
    
    # Step 2: Test search with related query
    print("\n" + "=" * 70)
    print("[3] Testing vector search with related query...")
    print("=" * 70)
    
    # Test queries - related to the existing data
    test_queries = [
        {
            "name": "Related domain query",
            "query": "graphics rendering issues on Android",
            "expected_domain": "graphics"
        },
        {
            "name": "Similar issue query",
            "query": "video playback problems flickering",
            "expected_domain": "graphics"
        },
        {
            "name": "Different domain query",
            "query": "network connection timeout errors",
            "expected_domain": None  # Should not match graphics domain
        }
    ]
    
    for test_case in test_queries:
        print(f"\n--- Test: {test_case['name']} ---")
        print(f"Query: \"{test_case['query']}\"")
        
        try:
            search_request = {
                "query": test_case['query'],
                "limit": 3
            }
            
            # Add timeout to prevent hanging
            response = requests.post(SEARCH_API_URL, json=search_request, timeout=30)
            
            if response.status_code != 200:
                print(f"[ERROR] Search failed: {response.status_code}")
                print(response.text)
                continue
            
            result = response.json()
            results_count = result.get("results_count", 0)
            results = result.get("results", [])
            
            print(f"\n[OK] Search completed!")
            print(f"   Found {results_count} similar session(s)")
            
            if results_count > 0:
                print("\n   Top results:")
                for i, res in enumerate(results, 1):
                    similarity = res.get("similarity", 0)
                    domain = res.get("domain", "unknown")
                    issue = res.get("issue_summary", "unknown")
                    
                    print(f"   {i}. Similarity: {similarity:.4f}")
                    print(f"      Domain: {domain}")
                    print(f"      Issue: {issue}")
                    
                    # Check if it matches expected domain
                    if test_case['expected_domain']:
                        if domain == test_case['expected_domain']:
                            print(f"      ✓ Matches expected domain!")
                        else:
                            print(f"      ✗ Does not match expected domain ({test_case['expected_domain']})")
                
                # Check if top result has good similarity score
                top_similarity = results[0].get("similarity", 0)
                if top_similarity > 0.7:
                    print(f"\n   ✓ High similarity score ({top_similarity:.4f}) - Good match!")
                elif top_similarity > 0.5:
                    print(f"\n   ⚠ Moderate similarity score ({top_similarity:.4f}) - Partial match")
                else:
                    print(f"\n   ✗ Low similarity score ({top_similarity:.4f}) - Poor match")
            else:
                print("\n   [WARNING] No results found")
                
        except requests.exceptions.ConnectionError:
            print("[ERROR] Could not connect to the API.")
            print("   Make sure the server is running:")
            print("   python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000")
            return
        except Exception as e:
            print(f"[ERROR] Error during search: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("[SUMMARY] RAG Vector Search Test Complete".center(70))
    print("=" * 70)
    print("\nThe system should retrieve relevant context from the vector database")
    print("based on semantic similarity, even with different wording in the query.")

if __name__ == "__main__":
    try:
        test_rag_search()
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
