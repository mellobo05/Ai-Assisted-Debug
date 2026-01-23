from app.db.session import SessionLocal
from app.models.debug import DebugEmbedding, DebugSession
from app.models.jira import JiraEmbedding, JiraIssue
import numpy as np
from typing import Dict, Iterable, List, Optional, Set, Tuple


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    try:
        vec1 = np.array(vec1, dtype=np.float64)
        vec2 = np.array(vec2, dtype=np.float64)
        
        # Validate dimensions match
        if len(vec1) != len(vec2):
            print(f"[SEARCH] Dimension mismatch: vec1={len(vec1)}, vec2={len(vec2)}")
            return 0.0
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = float(dot_product / (norm1 * norm2))
        # Ensure similarity is in valid range [-1, 1]
        return max(-1.0, min(1.0, similarity))
    except Exception as e:
        print(f"[SEARCH] Error calculating cosine similarity: {e}")
        return 0.0


def find_similar(query_embedding: List[float], limit: int = 3) -> List[Dict]:
    """
    Find similar sessions based on query embedding using cosine similarity.
    Since we're using JSON instead of pgvector, we calculate similarity in Python.
    
    Args:
        query_embedding: The embedding vector of the query
        limit: Maximum number of results to return
    
    Returns:
        List of dictionaries with session_id, similarity score, and session details
    """
    db = SessionLocal()
    try:
        # Get all embeddings from database
        all_embeddings = db.query(DebugEmbedding).all()
        
        if not all_embeddings:
            return []
        
        # Validate query embedding
        if not isinstance(query_embedding, list) or len(query_embedding) == 0:
            print(f"[SEARCH] Invalid query embedding: type={type(query_embedding)}, length={len(query_embedding) if isinstance(query_embedding, list) else 'N/A'}")
            return []
        
        query_dim = len(query_embedding)
        print(f"[SEARCH] Query embedding dimension: {query_dim}")
        
        # Calculate similarity for each embedding
        results = []
        for db_embedding in all_embeddings:
            stored_embedding = db_embedding.embedding
            
            # Ensure embeddings are lists
            if not isinstance(stored_embedding, list):
                print(f"[SEARCH] Skipping non-list embedding for session {db_embedding.session_id}")
                continue
            
            # Check dimension match
            if len(stored_embedding) != query_dim:
                print(f"[SEARCH] Dimension mismatch for session {db_embedding.session_id}: stored={len(stored_embedding)}, query={query_dim}")
                continue
            
            # Calculate cosine similarity
            similarity = cosine_similarity(query_embedding, stored_embedding)
            
            # Get session details
            session = db.query(DebugSession).filter(
                DebugSession.id == db_embedding.session_id
            ).first()
            
            if session:
                results.append({
                    "session_id": str(session.id),
                    "similarity": similarity,
                    "issue_summary": session.issue_summary,
                    "domain": session.domain,
                    "os": session.os,
                    "logs": session.logs,
                    "status": session.status
                })
        
        # Sort by similarity (descending) and return top results
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
        
    except Exception as e:
        print(f"[SEARCH] Error finding similar embeddings: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db.close()


def find_similar_jira(
    query_embedding: List[float],
    limit: int = 3,
    exclude_issue_keys: Optional[Iterable[str]] = None,
) -> List[Dict]:
    """
    Find similar JIRA issues based on query embedding using cosine similarity.
    JSON embeddings, so similarity is computed in Python.
    """
    db = SessionLocal()
    try:
        all_embeddings = db.query(JiraEmbedding.issue_key, JiraEmbedding.embedding).all()
        if not all_embeddings:
            return []

        if not isinstance(query_embedding, list) or len(query_embedding) == 0:
            print(
                f"[SEARCH] Invalid query embedding for JIRA: type={type(query_embedding)}, "
                f"length={len(query_embedding) if isinstance(query_embedding, list) else 'N/A'}"
            )
            return []

        query_dim = len(query_embedding)
        exclude: Set[str] = set()
        if exclude_issue_keys:
            exclude = {str(k).strip() for k in exclude_issue_keys if str(k).strip()}

        scored: List[Tuple[str, float]] = []
        for issue_key, stored_embedding in all_embeddings:
            if not isinstance(stored_embedding, list):
                continue
            if len(stored_embedding) != query_dim:
                continue

            similarity = cosine_similarity(query_embedding, stored_embedding)
            k = str(issue_key or "").strip()
            if not k or k in exclude:
                continue
            scored.append((k, similarity))

        if not scored:
            return []

        scored.sort(key=lambda t: t[1], reverse=True)
        top = scored[: int(limit)]
        top_keys = [k for k, _ in top]
        sim_by_key = {k: s for k, s in top}

        # Batch fetch issue rows (avoid N+1 queries)
        issues = db.query(JiraIssue).filter(JiraIssue.issue_key.in_(top_keys)).all()
        issue_by_key: Dict[str, JiraIssue] = {i.issue_key: i for i in issues if i and i.issue_key}

        results: List[Dict] = []
        for k in top_keys:
            issue = issue_by_key.get(k)
            if not issue:
                continue
            results.append(
                {
                    "source": "jira",
                    "issue_key": issue.issue_key,
                    "similarity": float(sim_by_key.get(k, 0.0)),
                    "summary": issue.summary,
                    "status": issue.status,
                    "priority": issue.priority,
                    "assignee": issue.assignee,
                    "issue_type": issue.issue_type,
                    "url": issue.url,
                    "program_theme": getattr(issue, "program_theme", None),
                    "labels": getattr(issue, "labels", None),
                    "components": getattr(issue, "components", None),
                    "latest_comment": (
                        (
                            issue.comments[-1].get("body")
                            if isinstance(issue.comments, list) and issue.comments and isinstance(issue.comments[-1], dict)
                            else None
                        )
                    ),
                }
            )

        return results
    except Exception as e:
        print(f"[SEARCH] Error finding similar JIRA embeddings: {e}")
        import traceback

        traceback.print_exc()
        return []
    finally:
        db.close()
