import google.generativeai as genai
import os

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyC9LDy5FDQedN7O7ZJF9Qfb32fOvaFQTP4")
genai.configure(api_key=GEMINI_API_KEY)

def generate_embedding(text: str):
    """
    Generate embedding using Gemini embedding model
    Note: Gemini uses 'models/embedding-001' for embeddings
    Returns a 768-dimensional vector
    """
    result = genai.embed_content(
        model="models/embedding-001",
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']