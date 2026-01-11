import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure Gemini API - Get from environment variable
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in your .env file or environment.")

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