"""
Run RAG pipeline directly
"""
import sys
import os

# Set environment variables BEFORE importing modules
os.environ['USE_MOCK_EMBEDDING'] = 'true'
os.environ['GEMINI_API_KEY'] = 'AIzaSyC9LDy5FDQedN7O7ZJF9Qfb32fOvaFQTP4'

sys.path.insert(0, 'backend')

from app.db.session import SessionLocal
from app.models.debug import DebugSession
from app.services.rag import process_rag_pipeline

print("=" * 60)
print("Running RAG Pipeline")
print("=" * 60)

# Get the most recent session
db = SessionLocal()
try:
    session = db.query(DebugSession).order_by(DebugSession.created_at.desc()).first()
    
    if not session:
        print("[ERROR] No sessions found in database")
        print("   Create a session first by calling the /debug API endpoint")
        sys.exit(1)
    
    print(f"\n[1] Found session: {session.id}")
    print(f"   Issue: {session.issue_summary}")
    print(f"   Status: {session.status}")
    
    # Check if already processed
    from app.models.debug import DebugEmbedding
    existing = db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session.id).first()
    if existing:
        print(f"\n[INFO] This session already has an embedding")
        print(f"   Status: {session.status}")
        response = input("   Process again? (y/n): ")
        if response.lower() != 'y':
            print("   Skipping...")
            sys.exit(0)
    
    print(f"\n[2] Running RAG pipeline...")
    process_rag_pipeline(str(session.id), 'true', os.environ['GEMINI_API_KEY'])
    
    # Check results
    db.refresh(session)
    embedding = db.query(DebugEmbedding).filter(DebugEmbedding.session_id == session.id).first()
    
    print(f"\n[3] Results:")
    print(f"   Session status: {session.status}")
    if embedding:
        emb_size = len(embedding.embedding) if isinstance(embedding.embedding, list) else 0
        print(f"   Embedding size: {emb_size}")
        if emb_size == 768:
            print(f"\n[SUCCESS] RAG pipeline completed successfully!")
        else:
            print(f"\n[WARNING] Embedding size is {emb_size}, expected 768")
    else:
        print(f"   [ERROR] Embedding not found")
        
except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()

print("\n" + "=" * 60)
