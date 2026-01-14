import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path

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
        load_dotenv(dotenv_path=env_path, override=True)
        env_loaded = True
        print(f"[EMBEDDINGS] Loaded .env from: {env_path}")
        break

if not env_loaded:
    # If .env not found, try loading from current directory
    load_dotenv(override=True)
    print(f"[EMBEDDINGS] WARNING: .env file not found. Tried paths: {[str(p) for p in possible_paths]}")
    print(f"[EMBEDDINGS] Current working directory: {Path.cwd()}")
    print(f"[EMBEDDINGS] Embeddings file location: {_embeddings_file}")
    print(f"[EMBEDDINGS] Project root calculated as: {_project_root}")

# Configure Gemini API - Get from environment variable
# Only configure if API key is available (allows mock mode)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def generate_embedding(text: str, task_type: str = "retrieval_document"):
    """
    Generate embedding using Gemini embedding model
    Note: Gemini uses 'models/embedding-001' for embeddings
    Returns a 768-dimensional vector
    
    Args:
        text: The text to generate embedding for
        task_type: "retrieval_document" for storing documents, "retrieval_query" for queries
    
    Raises:
        ValueError: If GEMINI_API_KEY is not set and USE_MOCK_EMBEDDING is not enabled
    """
    # Check if API key is available
    api_key = os.getenv("GEMINI_API_KEY")
    use_mock = os.getenv("USE_MOCK_EMBEDDING", "false").lower() == "true"
    
    if not api_key and not use_mock:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Please set it in your .env file or environment, "
            "or set USE_MOCK_EMBEDDING=true for testing."
        )
    
    # If mock mode, return a mock embedding
    if use_mock or not api_key:
        print("[EMBEDDINGS] Using mock embedding (API key not available or mock mode enabled)")
        # Generate a simple mock embedding based on text hash for consistency
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        hash_int = int(hash_obj.hexdigest(), 16)
        # Create a deterministic mock vector
        mock_vector = [(hash_int % 1000) / 1000.0 for _ in range(768)]
        return mock_vector
    
    # Configure if not already configured
    if not genai.api_key:
        genai.configure(api_key=api_key)
    
    result = genai.embed_content(
        model="models/embedding-001",
        content=text,
        task_type=task_type
    )
    return result['embedding']