from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding
from app.services.embeddings import generate_embedding
from app.services.pinecone_service import (
    is_pinecone_enabled,
    upsert_embedding,
    search_similar_embeddings
)

def process_rag_pipeline(session_id: str, use_mock_embedding: str = None, gemini_api_key: str = None):
    """Process RAG pipeline for a debug session"""
    import os
    
    # Set environment variables if provided
    if use_mock_embedding:
        os.environ["USE_MOCK_EMBEDDING"] = use_mock_embedding
    if gemini_api_key:
        os.environ["GEMINI_API_KEY"] = gemini_api_key
    
    print(f"[RAG] Starting pipeline for session {session_id}")
    print(f"[RAG] USE_MOCK_EMBEDDING: {os.getenv('USE_MOCK_EMBEDDING', 'false')}")
    
    db = SessionLocal()
    try:
        session = db.query(DebugSession).filter(DebugSession.id == session_id).first()

        if not session:
            print(f"[RAG] Session {session_id} not found")
            return

        #1.create embedding text for RAG
        embedding_text = f"""
        Issue: {session.issue_summary}
        Domain: {session.domain}
        OS: {session.os}
        Logs: {session.logs}"""

        print(f"[RAG] Generating embedding for session {session_id}...")
        
        #2.Generate embedding text
        try:
            embedding = generate_embedding(embedding_text)
            print(f"[RAG] Embedding generated, size: {len(embedding)}")
        except Exception as e:
            print(f"[RAG] Error generating embedding: {e}")
            # For testing: create a mock embedding if API fails
            if os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true":
                print("[RAG] Using mock embedding for testing...")
                # Match the main mock embedding behavior (deterministic + normalized)
                import hashlib
                import math
                import random

                provider = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()
                if provider == "sbert":
                    dim = int(os.getenv("MOCK_EMBED_DIM", "384"))
                else:
                    dim = int(os.getenv("MOCK_EMBED_DIM", "768"))

                seed = int(hashlib.md5(embedding_text.encode("utf-8")).hexdigest(), 16) & 0xFFFFFFFF
                rng = random.Random(seed)
                embedding = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
                norm = math.sqrt(sum((x * x) for x in embedding)) or 1.0
                embedding = [float(x / norm) for x in embedding]
            else:
                print(f"[RAG] Embedding generation failed and mock mode is off")
                raise

        #3.Save embedding to DB
        db_embedding = DebugEmbedding(session_id=session.id,embedding=embedding)

        db.add(db_embedding)

        #4.Save to Pinecone if enabled
        if is_pinecone_enabled():
            print(f"[RAG] Pinecone is enabled, upserting to Pinecone...")
            metadata = {
                "domain": session.domain,
                "os": session.os,
                "issue_summary": session.issue_summary[:500] if session.issue_summary else "",  # Limit size
                "status": "EMBEDDING_GENERATED"
            }
            
            pinecone_success = upsert_embedding(
                session_id=str(session.id),
                embedding=embedding,
                metadata=metadata
            )
            
            if pinecone_success:
                print(f"[RAG] Successfully stored embedding in Pinecone for session {session_id}")
            else:
                print(f"[RAG] Warning: Failed to store embedding in Pinecone (DB still has it)")
        else:
            print(f"[RAG] Pinecone is disabled (USE_PINECONE=false)")

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


def search_similar_sessions(issue_text: str, top_k: int = 5, domain_filter: str = None):
    """
    Search for similar debug sessions using Pinecone or database
    
    Args:
        issue_text: The issue description to search for
        top_k: Number of similar sessions to return
        domain_filter: Optional domain filter (e.g., "backend", "frontend")
    
    Returns:
        List of similar sessions with scores
    """
    import os
    
    print(f"[RAG] Searching for similar sessions (top_k={top_k})")
    
    # Generate embedding for the search query
    try:
        query_embedding = generate_embedding(issue_text, task_type="retrieval_query")
        print(f"[RAG] Query embedding generated, size: {len(query_embedding)}")
    except Exception as e:
        print(f"[RAG] Error generating query embedding: {e}")
        return []
    
    # Use Pinecone if enabled
    if is_pinecone_enabled():
        print("[RAG] Using Pinecone for similarity search...")
        
        # Build metadata filter
        filter_metadata = {}
        if domain_filter:
            filter_metadata["domain"] = domain_filter
        
        # Search in Pinecone
        matches = search_similar_embeddings(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_metadata=filter_metadata if filter_metadata else None
        )
        
        # Fetch full session details from database
        db = SessionLocal()
        try:
            results = []
            for match in matches:
                session = db.query(DebugSession).filter(
                    DebugSession.id == match["session_id"]
                ).first()
                
                if session:
                    results.append({
                        "session_id": session.id,
                        "similarity_score": match["score"],
                        "issue_summary": session.issue_summary,
                        "domain": session.domain,
                        "os": session.os,
                        "status": session.status,
                        "created_at": session.created_at
                    })
            
            print(f"[RAG] Found {len(results)} similar sessions via Pinecone")
            return results
            
        finally:
            db.close()
    
    else:
        # Fallback to database-based similarity search
        print("[RAG] Using database for similarity search (Pinecone disabled)...")
        db = SessionLocal()
        try:
            # Get all embeddings (this is inefficient for large datasets)
            embeddings = db.query(DebugEmbedding).all()
            
            # Calculate cosine similarity
            import numpy as np
            
            def cosine_similarity(a, b):
                a = np.array(a)
                b = np.array(b)
                return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
            
            similarities = []
            for emb in embeddings:
                session = db.query(DebugSession).filter(
                    DebugSession.id == emb.session_id
                ).first()
                
                if session:
                    # Apply domain filter if specified
                    if domain_filter and session.domain != domain_filter:
                        continue
                    
                    score = cosine_similarity(query_embedding, emb.embedding)
                    similarities.append({
                        "session_id": session.id,
                        "similarity_score": float(score),
                        "issue_summary": session.issue_summary,
                        "domain": session.domain,
                        "os": session.os,
                        "status": session.status,
                        "created_at": session.created_at
                    })
            
            # Sort by similarity score and get top_k
            similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
            results = similarities[:top_k]
            
            print(f"[RAG] Found {len(results)} similar sessions via database")
            return results
            
        finally:
            db.close()