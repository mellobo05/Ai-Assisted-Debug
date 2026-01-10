from app.db.session import SessionLocal
from app.models.debug import DebugSession, DebugEmbedding
from app.services.embeddings import generate_embedding

def process_rag_pipeline(session_id:str):
    db = SessionLocal()

    session = db.query(DebugSession).filter(DebugSession.id == session_id).first()

    if not session:
        return

    #1.create embedding text
    embedding_text = f"""
    Issue: {session.issue_summary}
    Domain: {session.domain}
    OS: {session.os}
    Logs: {session.logs}"""

    #2.Generate embedding text
    embedding = generate_embedding(embedding_text)

    #3.Save embedding to DB
    db_embedding = DebugEmbedding(session_id=session.id,embedding=embedding)

    db.add(db_embedding)

    #update session status
    session.status = "EMBEDDING_GENERATED"
    db.commit()