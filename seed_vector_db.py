"""
Seed the vector DB with an additional sample DebugSession + embedding.

This script:
1) Creates a new DebugSession row
2) Runs process_rag_pipeline(session_id) synchronously to generate/store an embedding

Works even if Gemini is blocked by using USE_MOCK_EMBEDDING=true.

Run from project root:
  python seed_vector_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"[SEED] Loaded .env from: {env_path}")
    else:
        load_dotenv(override=True)
        print("[SEED] WARNING: .env not found in project root; using process env")


def main() -> int:
    # Ensure imports work
    sys.path.insert(0, str(Path(__file__).parent / "backend"))

    _load_env()

    # Default to mock mode for reliability unless user explicitly disables it
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")
    print(f"[SEED] USE_MOCK_EMBEDDING={os.getenv('USE_MOCK_EMBEDDING')}")

    from app.db.session import SessionLocal
    from app.models.debug import DebugSession
    from app.services.rag import process_rag_pipeline

    db = SessionLocal()
    try:
        # Add one more session (different domain than the existing "graphics" example)
        session = DebugSession(
            issue_summary="API requests timing out intermittently",
            domain="network",
            os="windows",
            logs="TimeoutError: request to https://example.com exceeded 30s; retrying...",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        print(f"[SEED] Created session: {session.id} (status={session.status})")

        # Generate + store embedding
        process_rag_pipeline(str(session.id), os.getenv("USE_MOCK_EMBEDDING"), os.getenv("GEMINI_API_KEY", ""))

        # Refresh status
        db.refresh(session)
        print(f"[SEED] Done. Session status now: {session.status}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

