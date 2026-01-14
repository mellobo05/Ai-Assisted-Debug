# Run FastAPI server script
# This script sets up the environment and runs the server
# Run this script from the project root (e.g., C:\Users\lobomela\.cursor\AI-Assistend-Debug)
# Example: .\run_server.ps1

Write-Host "Starting FastAPI server..." -ForegroundColor Green

# Set PYTHONPATH to include the backend directory (CRITICAL for imports)
$env:PYTHONPATH = "$PSScriptRoot\backend"
Write-Host "PYTHONPATH set to: $env:PYTHONPATH" -ForegroundColor Cyan

# Load GEMINI_API_KEY from .env file if it exists
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host "Loading environment variables from .env file..." -ForegroundColor Cyan
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.+)$") {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path Env:$key -Value $value
            Write-Host "  Set $key" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "WARNING: .env file not found. Ensure GEMINI_API_KEY is set in your environment." -ForegroundColor Yellow
}

# Check if GEMINI_API_KEY is set
if (-not $env:GEMINI_API_KEY) {
    Write-Host "ERROR: GEMINI_API_KEY is not set. Please set it in your .env file or environment." -ForegroundColor Red
    exit 1
} else {
    Write-Host "GEMINI_API_KEY is set." -ForegroundColor Green
}

# Run Uvicorn
# The --reload flag is important for development
Write-Host "`nStarting uvicorn server..." -ForegroundColor Green
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
