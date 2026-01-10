from app.db.session import SessionLocal
from app.models.debug import DebugEmbedding
from sqlalchemy import text


def find_similar(embeddings, limit=3):

    db = SessionLocal()
    query = text("""
    SELECT session_id, 
    FROM debug_embeddings
    ORDER BY embedding <-> :embedding
    LIMIT :limit
    """)
    results = db.execute(query, {"embedding": embeddings, "limit": limit})
    return [row[0] for row in results]
