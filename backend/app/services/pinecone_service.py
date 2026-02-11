"""
Pinecone Vector Database Service for RAG

This service handles all interactions with Pinecone for storing and retrieving
debug session embeddings.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Lazy import - Pinecone is optional
_pinecone_client = None
_pinecone_index = None


def _get_pinecone_client():
    """Initialize and return Pinecone client (lazy loading)"""
    global _pinecone_client
    
    if _pinecone_client is None:
        try:
            from pinecone import Pinecone
        except ImportError:
            raise ImportError(
                "Pinecone is not installed. Install it with: pip install pinecone-client"
            )
        
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError(
                "PINECONE_API_KEY environment variable is not set. "
                "Please set it in your .env file."
            )
        
        _pinecone_client = Pinecone(api_key=api_key)
        print("[PINECONE] Client initialized successfully")
    
    return _pinecone_client


def _get_pinecone_index():
    """Get or create Pinecone index"""
    global _pinecone_index
    
    if _pinecone_index is None:
        client = _get_pinecone_client()
        index_name = os.getenv("PINECONE_INDEX_NAME", "debug-sessions")
        
        # Get list of existing indexes
        existing_indexes = [index.name for index in client.list_indexes()]
        
        if index_name not in existing_indexes:
            print(f"[PINECONE] Index '{index_name}' not found. Please create it first.")
            print("[PINECONE] Create index at: https://app.pinecone.io/")
            print(f"[PINECONE] Index name: {index_name}")
            print(f"[PINECONE] Dimension: {os.getenv('PINECONE_DIMENSION', '768')}")
            print(f"[PINECONE] Metric: {os.getenv('PINECONE_METRIC', 'cosine')}")
            raise ValueError(
                f"Pinecone index '{index_name}' does not exist. "
                "Please create it in the Pinecone console first."
            )
        
        _pinecone_index = client.Index(index_name)
        print(f"[PINECONE] Connected to index: {index_name}")
    
    return _pinecone_index


def is_pinecone_enabled() -> bool:
    """Check if Pinecone is enabled via environment variable"""
    return os.getenv("USE_PINECONE", "false").lower() == "true"


def upsert_embedding(
    session_id: str,
    embedding: List[float],
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Store an embedding in Pinecone
    
    Args:
        session_id: Unique identifier for the debug session
        embedding: Vector embedding (list of floats)
        metadata: Optional metadata to store with the vector (domain, os, etc.)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        index = _get_pinecone_index()
        
        # Prepare metadata
        meta = metadata or {}
        meta["session_id"] = session_id
        
        # Upsert to Pinecone
        # Format: [(id, values, metadata)]
        index.upsert(
            vectors=[
                {
                    "id": session_id,
                    "values": embedding,
                    "metadata": meta
                }
            ],
            namespace=os.getenv("PINECONE_NAMESPACE", "default")
        )
        
        print(f"[PINECONE] Upserted embedding for session {session_id}")
        return True
        
    except Exception as e:
        print(f"[PINECONE] Error upserting embedding: {e}")
        import traceback
        traceback.print_exc()
        return False


def search_similar_embeddings(
    query_embedding: List[float],
    top_k: int = 5,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search for similar embeddings in Pinecone
    
    Args:
        query_embedding: Query vector embedding
        top_k: Number of results to return
        filter_metadata: Optional metadata filters (e.g., {"domain": "backend"})
    
    Returns:
        List of matches with scores and metadata
    """
    try:
        index = _get_pinecone_index()
        
        # Perform similarity search
        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            filter=filter_metadata,
            include_metadata=True,
            namespace=os.getenv("PINECONE_NAMESPACE", "default")
        )
        
        # Format results
        matches = []
        for match in results.get("matches", []):
            matches.append({
                "session_id": match["id"],
                "score": match["score"],
                "metadata": match.get("metadata", {})
            })
        
        print(f"[PINECONE] Found {len(matches)} similar embeddings")
        return matches
        
    except Exception as e:
        print(f"[PINECONE] Error searching embeddings: {e}")
        import traceback
        traceback.print_exc()
        return []


def delete_embedding(session_id: str) -> bool:
    """
    Delete an embedding from Pinecone
    
    Args:
        session_id: Session ID to delete
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        index = _get_pinecone_index()
        
        index.delete(
            ids=[session_id],
            namespace=os.getenv("PINECONE_NAMESPACE", "default")
        )
        
        print(f"[PINECONE] Deleted embedding for session {session_id}")
        return True
        
    except Exception as e:
        print(f"[PINECONE] Error deleting embedding: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_index_stats() -> Dict[str, Any]:
    """
    Get statistics about the Pinecone index
    
    Returns:
        Dictionary with index statistics
    """
    try:
        index = _get_pinecone_index()
        stats = index.describe_index_stats()
        
        print(f"[PINECONE] Index stats: {stats}")
        return stats
        
    except Exception as e:
        print(f"[PINECONE] Error getting index stats: {e}")
        return {}


def batch_upsert_embeddings(
    embeddings_data: List[Dict[str, Any]]
) -> bool:
    """
    Batch upsert multiple embeddings to Pinecone
    
    Args:
        embeddings_data: List of dicts with keys: session_id, embedding, metadata
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        index = _get_pinecone_index()
        
        # Prepare vectors for batch upsert
        vectors = []
        for data in embeddings_data:
            meta = data.get("metadata", {})
            meta["session_id"] = data["session_id"]
            
            vectors.append({
                "id": data["session_id"],
                "values": data["embedding"],
                "metadata": meta
            })
        
        # Batch upsert (Pinecone handles batching internally)
        index.upsert(
            vectors=vectors,
            namespace=os.getenv("PINECONE_NAMESPACE", "default")
        )
        
        print(f"[PINECONE] Batch upserted {len(vectors)} embeddings")
        return True
        
    except Exception as e:
        print(f"[PINECONE] Error batch upserting embeddings: {e}")
        import traceback
        traceback.print_exc()
        return False
