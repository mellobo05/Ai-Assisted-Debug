import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

# Embeddings logging can be noisy for CLI/UI users. Gate it behind an env flag.
def _embeddings_debug_enabled() -> bool:
    return os.getenv("EMBEDDINGS_DEBUG", "false").strip().lower() == "true"


def _log(msg: str) -> None:
    if _embeddings_debug_enabled():
        print(msg)


# Optional SBERT support (loaded lazily so backend can still run without it)
_SBERT_MODEL = None

# In-process embedding cache (LRU + TTL). Optional dependency: cachetools.
_EMBEDDING_CACHE = None
_EMBEDDING_CACHE_LOCK = None

# Load environment variables from .env file (look in project root)
# Calculate project root: backend/app/services/embeddings.py -> go up 3 levels
_embeddings_file = Path(__file__).resolve()
_project_root = _embeddings_file.parent.parent.parent.parent  # backend/app/services -> project root

# Try multiple possible paths
possible_paths = [
    _project_root / '.env',  # Project root (most likely)
    Path.cwd() / '.env',  # Current working directory
    _project_root.parent / '.env',  # One level up (just in case)
]

env_loaded = False
for env_path in possible_paths:
    env_path = env_path.resolve()
    if env_path.exists():
        # Do NOT override already-set environment variables (shell should win).
        # This avoids surprising behavior like USE_MOCK_EMBEDDING from .env overriding
        # a user-supplied USE_MOCK_EMBEDDING=false in PowerShell.
        load_dotenv(dotenv_path=env_path, override=False)
        env_loaded = True
        _log(f"[EMBEDDINGS] Loaded .env from: {env_path}")
        break

if not env_loaded:
    # If .env not found, try loading from current directory
    load_dotenv(override=False)
    _log(f"[EMBEDDINGS] WARNING: .env file not found. Tried paths: {[str(p) for p in possible_paths]}")
    _log(f"[EMBEDDINGS] Current working directory: {Path.cwd()}")
    _log(f"[EMBEDDINGS] Embeddings file location: {_embeddings_file}")
    _log(f"[EMBEDDINGS] Project root calculated as: {_project_root}")

# Configure Gemini API - Get from environment variable
# Only configure if API key is available (allows mock mode)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _get_embedding_cache():
    """
    Lazy-init an in-process cache for embeddings.

    Env:
      - EMBEDDING_CACHE_ENABLED: true|false (default true)
      - EMBEDDING_CACHE_SIZE: max entries (default 256)
      - EMBEDDING_CACHE_TTL_SECONDS: TTL in seconds (default 3600)
    """
    global _EMBEDDING_CACHE, _EMBEDDING_CACHE_LOCK

    enabled = os.getenv("EMBEDDING_CACHE_ENABLED", "true").strip().lower() == "true"
    if not enabled:
        return None, None

    if _EMBEDDING_CACHE is None:
        try:
            from cachetools import TTLCache  # type: ignore
        except Exception:
            # Cache is optional; if dependency is missing, run without cache.
            return None, None

        import threading

        maxsize = int(os.getenv("EMBEDDING_CACHE_SIZE", "256"))
        ttl = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "3600"))
        _EMBEDDING_CACHE = TTLCache(maxsize=maxsize, ttl=ttl)
        _EMBEDDING_CACHE_LOCK = threading.Lock()
        _log(f"[EMBEDDINGS] Cache enabled (maxsize={maxsize}, ttl={ttl}s)")

    return _EMBEDDING_CACHE, _EMBEDDING_CACHE_LOCK


def _cache_key(*, provider: str, task_type: str, model_name: str | None, text: str) -> str:
    import hashlib

    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{provider}|{task_type}|{model_name or ''}|{h}"


def _maybe_get_cached_embedding(*, provider: str, task_type: str, model_name: str | None, text: str):
    cache, lock = _get_embedding_cache()
    if cache is None or lock is None:
        return None
    key = _cache_key(provider=provider, task_type=task_type, model_name=model_name, text=text)
    with lock:
        v = cache.get(key)
    if v is None:
        return None
    return list(v)  # stored as tuple for immutability


def _maybe_set_cached_embedding(*, provider: str, task_type: str, model_name: str | None, text: str, embedding: list[float]):
    cache, lock = _get_embedding_cache()
    if cache is None or lock is None:
        return
    key = _cache_key(provider=provider, task_type=task_type, model_name=model_name, text=text)
    with lock:
        cache[key] = tuple(float(x) for x in embedding)


def _mock_embedding(text: str, dim: int = 768) -> list[float]:
    """
    Deterministic mock embedding (useful for dev/test when providers are unavailable).
    """
    import hashlib
    import math
    import random

    # IMPORTANT:
    # Previous implementation returned the same constant value for every dimension,
    # making all embeddings colinear and cosine similarity ~ 1.0 for almost everything.
    # We instead generate a deterministic pseudo-random vector and L2-normalize it.
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) & 0xFFFFFFFF
    rng = random.Random(seed)

    vec = [rng.uniform(-1.0, 1.0) for _ in range(int(dim))]
    norm = math.sqrt(sum((x * x) for x in vec)) or 1.0
    return [float(x / norm) for x in vec]


def _sbert_embedding(text: str) -> list[float]:
    """
    Sentence-Transformers embedding (local/offline-friendly once model is present).

    Env:
      - SBERT_MODEL_NAME: HF model name or local path (default: all-MiniLM-L6-v2)
    """
    global _SBERT_MODEL

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:
        raise ValueError(
            "SBERT provider selected but 'sentence-transformers' is not installed. "
            "Install it (pip install sentence-transformers) or set EMBEDDING_PROVIDER=gemini/mock."
        ) from e

    model_name = os.getenv("SBERT_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

    if _SBERT_MODEL is None:
        # Note: this may download weights on first run if not present locally.
        _SBERT_MODEL = SentenceTransformer(model_name)

    vec = _SBERT_MODEL.encode(text, normalize_embeddings=True)
    # numpy array -> python list[float]
    return [float(x) for x in vec.tolist()]


def generate_embedding(text: str, task_type: str = "retrieval_document"):
    """
    Generate embedding for RAG retrieval.

    Providers:
      - gemini: Google Gemini embeddings (models/embedding-001)
      - sbert: Sentence-Transformers (local)
      - mock: deterministic mock embeddings

    Env:
      - EMBEDDING_PROVIDER: gemini|sbert|mock (default: gemini)
      - SBERT_MODEL_NAME: model name/path for SBERT provider
      - GEMINI_API_KEY: required for gemini provider
      - USE_MOCK_EMBEDDING: if true, forces mock embeddings (provider-agnostic)
    
    Args:
        text: The text to generate embedding for
        task_type: "retrieval_document" for storing documents, "retrieval_query" for queries
    
    Raises:
        ValueError: If provider requirements are not satisfied
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()

    # Provider selection rules:
    # - If EMBEDDING_PROVIDER=mock => always mock
    # - If EMBEDDING_PROVIDER=sbert => always SBERT (ignore USE_MOCK_EMBEDDING)
    # - If EMBEDDING_PROVIDER=gemini and USE_MOCK_EMBEDDING=true => mock (offline/dev)
    force_mock = os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true"

    if provider == "mock":
        dim = int(os.getenv("MOCK_EMBED_DIM", "768"))
        cached = _maybe_get_cached_embedding(
            provider="mock",
            task_type=task_type,
            model_name=str(dim),
            text=text,
        )
        if cached is not None:
            return cached
        # Default mock dim matches Gemini; adjust via MOCK_EMBED_DIM if needed.
        _log(f"[EMBEDDINGS] Using mock embedding (provider={provider}, dim={dim})")
        emb = _mock_embedding(text, dim=dim)
        _maybe_set_cached_embedding(provider="mock", task_type=task_type, model_name=str(dim), text=text, embedding=emb)
        return emb

    if provider == "sbert":
        model_name = os.getenv("SBERT_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        cached = _maybe_get_cached_embedding(
            provider="sbert",
            task_type=task_type,
            model_name=model_name,
            text=text,
        )
        if cached is not None:
            return cached
        _log("[EMBEDDINGS] Using SBERT embedding provider")
        emb = _sbert_embedding(text)
        _maybe_set_cached_embedding(provider="sbert", task_type=task_type, model_name=model_name, text=text, embedding=emb)
        return emb

    if provider != "gemini":
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER='{provider}'. Use one of: gemini, sbert, mock."
        )

    if force_mock:
        dim = int(os.getenv("MOCK_EMBED_DIM", "768"))
        cached = _maybe_get_cached_embedding(
            provider="mock",
            task_type=task_type,
            model_name=str(dim),
            text=text,
        )
        if cached is not None:
            return cached
        _log(f"[EMBEDDINGS] Using mock embedding (provider=gemini forced-mock, dim={dim})")
        emb = _mock_embedding(text, dim=dim)
        _maybe_set_cached_embedding(provider="mock", task_type=task_type, model_name=str(dim), text=text, embedding=emb)
        return emb

    # Gemini provider
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set GEMINI_API_KEY, or set EMBEDDING_PROVIDER=sbert, or set USE_MOCK_EMBEDDING=true."
        )

    # Configure if not already configured
    if not genai.api_key:
        genai.configure(api_key=api_key)

    cached = _maybe_get_cached_embedding(
        provider="gemini",
        task_type=task_type,
        model_name="models/embedding-001",
        text=text,
    )
    if cached is not None:
        return cached

    result = genai.embed_content(
        model="models/embedding-001",
        content=text,
        task_type=task_type,
    )
    emb = result["embedding"]
    if isinstance(emb, list) and len(emb) > 0:
        _maybe_set_cached_embedding(
            provider="gemini",
            task_type=task_type,
            model_name="models/embedding-001",
            text=text,
            embedding=emb,
        )
    return emb