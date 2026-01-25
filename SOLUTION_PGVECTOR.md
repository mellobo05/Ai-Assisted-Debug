# Solution: pgvector Extension Not Installed

## Problem
PostgreSQL error: `extension "vector" is not available`

## Solutions

### Option 1: Use Docker (Easiest - Recommended)

1. **Install Docker Desktop** (if not installed): https://www.docker.com/products/docker-desktop

2. **Run the script:**
   ```powershell
   .\start_postgres_docker.ps1
   ```

   Or manually:
   ```powershell
   docker run --name pgvector-db `
     -e POSTGRES_USER=postgres `
     -e POSTGRES_PASSWORD=<YOUR_PASSWORD> `
     -e POSTGRES_DB=postgres `
     -p 5432:5432 `
     -d pgvector/pgvector:pg16
   
   docker exec -it pgvector-db psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

3. **Stop your local PostgreSQL service** (to avoid port conflict):
   ```powershell
   Stop-Service postgresql-x64-18
   ```

4. **Initialize database:**
   ```powershell
   python -c "import sys; sys.path.insert(0, 'backend'); from app.db.init_db import init_db; init_db()"
   ```

### Option 2: Install pgvector on Windows (Complex)

1. **Download pgvector source:**
   - https://github.com/pgvector/pgvector/releases
   - Or clone: `git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git`

2. **Install build tools:**
   - Visual Studio with C++ build tools
   - PostgreSQL development headers

3. **Compile and install:**
   ```cmd
   cd pgvector
   make
   make install
   ```

4. **Enable extension:**
   ```sql
   CREATE EXTENSION vector;
   ```

### Option 3: Temporary Workaround (For Testing Only)

If you want to test the RAG pipeline without pgvector:

1. **Temporarily modify the model** to use JSON instead of Vector:
   - Use `debug_temp.py` model
   - Or change `Vector(768)` to `JSON` in `debug.py`

2. **Note:** This won't support vector similarity search, but will allow testing the embedding generation.

## Recommended: Use Docker

Docker is the easiest solution and ensures pgvector works correctly.
