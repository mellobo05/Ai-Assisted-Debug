# Run FastAPI server script
# This script sets up the environment and runs the server

# Set environment variable
$env:GEMINI_API_KEY = "AIzaSyC9LDy5FDQedN7O7ZJF9Qfb32fOvaFQTP4"

# Set PYTHONPATH to include backend directory
$env:PYTHONPATH = "$PWD\backend"

# Run uvicorn from project root
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
