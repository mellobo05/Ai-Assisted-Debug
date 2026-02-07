# Phase 1 Confirmation Checklist

Use this checklist to confirm Phase 1 scaling improvements are working.

---

## Prerequisites

- [ ] Python virtual environment activated (or dependencies installed)
- [ ] PostgreSQL running (or Docker: `.\start_postgres_docker.ps1`)
- [ ] `.env` file configured (at least `DATABASE_URL`, optionally `REDIS_HOST`)

---

## Step 1: Start the Backend

```powershell
cd c:\Users\lobomela\.cursor\AAD
.\run_server.ps1 -NoReload
```

**Expected:** Server starts and shows something like:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

- [ ] Backend starts without errors

---

## Step 2: Health Check Endpoint

In a **new terminal** (or browser):

```powershell
# PowerShell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get

# Or in browser: http://localhost:8000/health
# Or: curl http://localhost:8000/health
```

**Expected response (example):**
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "embedding_provider": "mock"
  }
}
```

- [ ] `GET /health` returns HTTP 200
- [ ] `status` is `"healthy"`
- [ ] `checks.database` is `"ok"` (Postgres connected)
- [ ] `checks.redis` is `"ok"` or `"not_configured"` or `"error: ..."` (Redis optional)
- [ ] `checks.embedding_provider` is present

**If database is "error":** Check Postgres is running and `DATABASE_URL` in `.env`.

---

## Step 3: Connection Pooling (Database)

Pooling is configured in `backend/app/db/session.py`. Verify it's active:

```powershell
# Optional: Check pool is used (no direct API; just confirm server runs)
# Pool is used automatically when endpoints hit the DB
```

**Confirm:** Any endpoint that uses the database works (e.g. health check shows `database: ok`).

- [ ] Database operations work (health shows `database: ok`)

**Optional:** Set in `.env` and restart:
```env
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```
- [ ] (Optional) Custom pool env vars applied and server still starts

---

## Step 4: Redis Caching (Optional)

**If Redis is not installed:** Skip this; app works with `redis: "not_configured"` or `"error"`.

**If Redis is installed:**

1. Start Redis (e.g. `docker run -d -p 6379:6379 redis:7-alpine`).
2. In `.env`: `REDIS_HOST=localhost`, `REDIS_PORT=6379`.
3. Restart backend.
4. Call health again: `checks.redis` should be `"ok"`.

- [ ] Redis running and `REDIS_HOST`/`REDIS_PORT` set
- [ ] Health shows `redis: "ok"`

---

## Step 5: Caching on JIRA Analyze

This confirms the cache is used for repeated analyze requests.

**5a. First request (cache miss)**

```powershell
$body = @{
  issue_key = "TEST-PHASE1"
  summary    = "Phase 1 confirmation test"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/jira/analyze" -Method Post -Body $body -ContentType "application/json"
```

**Expected:** Response includes `"cache_hit": false` and `"analysis_status": "PROCESSING"` or `"COMPLETED"`.

- [ ] First request returns 200 and `cache_hit: false`

**5b. Second request (cache hit if Redis is ok)**

Send the **same** body again (same `issue_key` and `summary`):

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/jira/analyze" -Method Post -Body $body -ContentType "application/json"
```

**Expected (with Redis):** `"cache_hit": true`, `"analysis_status": "CACHED"`, fast response.

**Expected (without Redis):** May still get cached result from DB idempotency (also acceptable).

- [ ] Second request returns 200
- [ ] With Redis: `cache_hit: true` and fast response
- [ ] Without Redis: Either DB cache or no cache; app still works

---

## Step 6: Quick Sanity Checks

- [ ] **OpenAPI docs:** http://localhost:8000/docs — page loads
- [ ] **Health again:** `GET /health` still returns `healthy`
- [ ] No errors in backend terminal

---

## Phase 1 Confirmed When

| Check | Required |
|-------|----------|
| Backend starts | ✅ Yes |
| `GET /health` returns 200, `status: healthy` | ✅ Yes |
| `checks.database` is `ok` | ✅ Yes |
| `checks.redis` ok or not_configured/error | ✅ Yes (Redis optional) |
| `/jira/analyze` works (cache_hit true or false) | ✅ Yes |
| With Redis: repeated analyze returns cache_hit true | ✅ If Redis in use |

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| Health returns 503 or database error | Check Postgres is running and `DATABASE_URL` in `.env` |
| Redis "error" in health | Start Redis or leave optional; app works without it |
| Import error (e.g. cache) | Ensure `pip install -r requirement.txt` and PYTHONPATH includes `backend` |
| Port 8000 in use | Use `.\run_server.ps1 -NoReload -Port 8001` (or other port) |

---

## One-Line Verification (after server is running)

```powershell
# Health + basic sanity
Invoke-RestMethod -Uri "http://localhost:8000/health" | ConvertTo-Json -Depth 3
```

If this returns `"status": "healthy"` and `database: ok`, Phase 1 is confirmed.
