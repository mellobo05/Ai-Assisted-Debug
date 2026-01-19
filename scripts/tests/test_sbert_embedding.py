"""
Smoke test for SBERT embedding mode (no server required).

Usage (PowerShell):
  $env:PYTHONPATH="$PWD\\backend"
  $env:EMBEDDING_PROVIDER="sbert"
  $env:USE_MOCK_EMBEDDING="false"  # recommended; SBERT ignores it, but keep env consistent
  $env:SBERT_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"  # optional
  python scripts/tests/test_sbert_embedding.py
"""

import os
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    import sys

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> None:
    _ensure_project_root_on_path()

    os.environ.setdefault("EMBEDDING_PROVIDER", "sbert")

    from backend.app.services.embeddings import generate_embedding

    text = "Screen flicker after resume; happens on PTL RVP; fixed by updating i915 firmware."
    emb = generate_embedding(text, task_type="retrieval_document")

    assert isinstance(emb, list) and len(emb) > 0, f"Invalid embedding: type={type(emb)}, len={len(emb) if isinstance(emb, list) else 'N/A'}"
    assert all(isinstance(x, (int, float)) for x in emb[:10]), "Embedding does not look numeric"

    print(
        f"[OK] provider={os.getenv('EMBEDDING_PROVIDER')} "
        f"use_mock={os.getenv('USE_MOCK_EMBEDDING')} "
        f"dim={len(emb)} first3={emb[:3]}"
    )


if __name__ == "__main__":
    main()

