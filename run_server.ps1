param(
    # Use this for a stable demo/UI run to avoid mid-request reloads.
    [switch]$NoReload,
    # Change port if 8000 is already in use.
    [int]$Port = 8000
)

# Run FastAPI server script
# This script sets up the environment and runs the server
# Run this script from the project root (e.g., C:\Users\lobomela\.cursor\AI-Assistend-Debug)
# Examples:
#   .\run_server.ps1
#   .\run_server.ps1 -NoReload

Write-Host "Starting FastAPI server..." -ForegroundColor Green

# Set PYTHONPATH to include the backend directory (CRITICAL for imports)
$env:PYTHONPATH = "$PSScriptRoot\backend"
Write-Host "PYTHONPATH set to: $env:PYTHONPATH" -ForegroundColor Cyan

# Load environment variables from .env file if it exists
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Write-Host "Loading environment variables from .env file..." -ForegroundColor Cyan
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.+)$") {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Do not override already-set environment variables (shell should win)
            if (-not (Test-Path Env:$key)) {
                Set-Item -Path Env:$key -Value $value
                Write-Host "  Set $key" -ForegroundColor Gray
            } else {
                Write-Host "  Skipped $key (already set in shell)" -ForegroundColor DarkGray
            }
        }
    }
} else {
    Write-Host "WARNING: .env file not found. Ensure required env vars are set in your environment." -ForegroundColor Yellow
}

# Provider-aware checks
$provider = "gemini"
if ($env:EMBEDDING_PROVIDER) {
    $provider = $env:EMBEDDING_PROVIDER.ToLower()
}
$useMock = (($env:USE_MOCK_EMBEDDING | ForEach-Object { $_.ToLower() }) -eq "true")

Write-Host "Embedding provider: $provider (USE_MOCK_EMBEDDING=$useMock)" -ForegroundColor Cyan

# Only require GEMINI_API_KEY when actually needed
if (($provider -eq "gemini") -and (-not $useMock) -and (-not $env:GEMINI_API_KEY)) {
    Write-Host "ERROR: GEMINI_API_KEY is not set. Set it, or set EMBEDDING_PROVIDER=sbert, or set USE_MOCK_EMBEDDING=true." -ForegroundColor Red
    exit 1
}

# Run Uvicorn
# The --reload flag is useful for development but can interrupt UI requests mid-flight.
Write-Host "`nStarting uvicorn server..." -ForegroundColor Green
if ($NoReload) {
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
} else {
    python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $Port
}
