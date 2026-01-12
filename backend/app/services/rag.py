from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding
from app.services.embeddings import generate_embedding

def process_rag_pipeline(session_id:str):
    db = SessionLocal()
    try:
        session = db.query(DebugSession).filter(DebugSession.id == session_id).first()

        if not session:
            print(f"Session {session_id} not found")
            return

        #1.create embedding text
        embedding_text = f"""
        Issue: {session.issue_summary}
        Domain: {session.domain}
        OS: {session.os}
        Logs: {session.logs}"""

        print(f"Generating embedding for session {session_id}...")
        
        #2.Generate embedding text
        try:
            embedding = generate_embedding(embedding_text)
            print(f"Embedding generated, size: {len(embedding)}")
        except Exception as e:
            print(f"Error generating embedding: {e}")
            # For testing: create a mock embedding if API fails
            import os
            if os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true":
                print("Using mock embedding for testing...")
                embedding = [0.0] * 768  # Mock 768-dim vector
            else:
                raise

        #3.Save embedding to DB
        db_embedding = DebugEmbedding(session_id=session.id,embedding=embedding)

        db.add(db_embedding)

        #update session status
        session.status = "EMBEDDING_GENERATED"
        db.commit()
        print(f"Embedding saved for session {session_id}")
    except Exception as e:
        print(f"Error in process_rag_pipeline: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        # Update session status to error
        if session:
            session.status = "ERROR"
            db.commit()
    finally:
        db.close()