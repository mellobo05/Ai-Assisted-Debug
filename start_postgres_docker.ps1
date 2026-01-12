# Start PostgreSQL with pgvector using Docker
Write-Host "Starting PostgreSQL with pgvector..." -ForegroundColor Cyan

# Check if container already exists
$existing = docker ps -a --filter "name=pgvector-db" --format "{{.Names}}"
if ($existing) {
    Write-Host "Container exists. Starting it..." -ForegroundColor Yellow
    docker start pgvector-db
} else {
    Write-Host "Creating new container..." -ForegroundColor Yellow
    docker run --name pgvector-db `
        -e POSTGRES_USER=postgres `
        -e POSTGRES_PASSWORD=1234567890 `
        -e POSTGRES_DB=postgres `
        -p 5432:5432 `
        -d pgvector/pgvector:pg16
}

Start-Sleep -Seconds 3

Write-Host "Enabling pgvector extension..." -ForegroundColor Yellow
docker exec -it pgvector-db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"

Write-Host "[OK] PostgreSQL with pgvector is ready!" -ForegroundColor Green
Write-Host "Connection: postgresql://postgres:1234567890@localhost:5432/postgres" -ForegroundColor Cyan
