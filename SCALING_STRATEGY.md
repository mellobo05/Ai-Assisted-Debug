# Scaling Strategy for AI-Assisted-Debug

## Current Architecture Analysis

### Identified Bottlenecks

1. **In-Memory Job Management** (`main.py:32-35`)
   - Jobs stored in dictionaries (`_JIRA_SUMMARIZE_JOBS`, `_JIRA_ANALYZE_JOBS`)
   - Not distributed across instances
   - Lost on server restart

2. **Vector Search Performance** (`services/search.py`)
   - Loads ALL embeddings into memory (O(n) complexity)
   - Cosine similarity computed in Python (not optimized)
   - No indexing for fast similarity search

3. **Database Connection Pooling** (`db/session.py:36`)
   - Basic `pool_pre_ping=True` only
   - No explicit pool size configuration
   - Single database instance

4. **Synchronous Blocking Operations**
   - Embedding generation blocks request thread
   - LLM calls are blocking (even in async endpoints)
   - Database queries not optimized for concurrency

5. **Single Instance Deployment**
   - No load balancing
   - No horizontal scaling capability
   - Single point of failure

6. **Embedding Model Loading**
   - SBERT model loaded per process (memory intensive)
   - No model serving infrastructure

---

## Scaling Strategies

### 1. **Horizontal Scaling (API Layer)**

#### Current State
- Single FastAPI instance
- No load balancer

#### Solution: Multi-Instance Deployment

**Option A: Docker Compose with Multiple Workers**
```yaml
# docker-compose.yml
services:
  api:
    build: .
    command: uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4
    environment:
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - postgres
      - redis
```

**Option B: Kubernetes Deployment**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-debug-api
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: api
        image: ai-debug-api:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
```

**Implementation Steps:**
1. Add health check endpoint (`/health`)
2. Configure reverse proxy (Nginx/Traefik)
3. Use sticky sessions only if needed (for in-memory jobs - see #2)
4. Add request ID middleware for tracing

---

### 2. **Distributed Job Queue System**

#### Current State
- In-memory dictionaries for job tracking
- Jobs lost on restart

#### Solution: Redis + Celery

**Architecture:**
```
FastAPI → Redis (Broker) → Celery Workers → Results Backend (Redis)
```

**Implementation:**

1. **Add Redis dependency:**
```python
# requirement.txt
redis==5.0.1
celery==5.3.4
```

2. **Create Celery app:**
```python
# backend/app/celery_app.py
from celery import Celery
import os

celery_app = Celery(
    "ai_debug",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
```

3. **Convert jobs to Celery tasks:**
```python
# backend/app/tasks/analysis.py
from app.celery_app import celery_app
from app.agents.swarm import run_syscros_swarm

@celery_app.task(bind=True)
def analyze_jira_task(self, issue_key, logs_text, domain, component, os_name, config_dict):
    """Async task for JIRA analysis"""
    config = SwarmConfig(**config_dict)
    return run_syscros_swarm(
        issue_key=issue_key,
        logs_text=logs_text,
        domain=domain,
        component=component,
        os_name=os_name,
        do_analysis=True,
        config=config,
    )
```

4. **Update FastAPI endpoints:**
```python
# backend/app/main.py
from app.tasks.analysis import analyze_jira_task

@app.post("/jira/analyze")
async def jira_analyze(request: JiraAnalyzeRequest):
    # ... existing code ...
    
    # Replace asyncio.create_task with Celery
    task = analyze_jira_task.delay(
        issue_key=key,
        logs_text=request.logs,
        domain=domain_in,
        component=resolved_component,
        os_name=request.os,
        config_dict=cfg.dict(),
    )
    
    return {
        "job_id": task.id,
        "analysis_status": "PROCESSING",
        # ...
    }

@app.get("/jira/analyze/job/{job_id}")
async def jira_analyze_job(job_id: str):
    task = celery_app.AsyncResult(job_id)
    
    if task.ready():
        if task.successful():
            result = task.get()
            return {
                "analysis_status": "COMPLETED",
                "analysis": result.get("analysis", ""),
                # ...
            }
        else:
            return {
                "analysis_status": "ERROR",
                "error": str(task.info),
                # ...
            }
    else:
        return {
            "analysis_status": "PROCESSING",
            # ...
        }
```

**Benefits:**
- Jobs survive server restarts
- Horizontal scaling of workers
- Better resource utilization
- Built-in retry mechanisms

---

### 3. **Vector Database Migration**

#### Current State
- JSON embeddings in Postgres
- Load all embeddings into memory for search
- O(n) cosine similarity computation

#### Solution A: pgvector Extension (Recommended)

**Advantages:**
- Native Postgres extension
- Indexed similarity search (HNSW or IVFFlat)
- Minimal code changes

**Implementation:**

1. **Enable pgvector:**
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

2. **Update schema:**
```python
# backend/app/models/jira.py
from pgvector.sqlalchemy import Vector

class JiraEmbedding(Base):
    __tablename__ = "jira_embeddings"
    
    issue_key = Column(String, primary_key=True)
    embedding = Column(Vector(768))  # or 384 for SBERT
```

3. **Update search function:**
```python
# backend/app/services/search.py
from sqlalchemy import text

def find_similar_jira(
    query_embedding: List[float],
    limit: int = 3,
    exclude_issue_keys: Optional[Iterable[str]] = None,
) -> List[Dict]:
    db = SessionLocal()
    try:
        # Convert to PostgreSQL array format
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        query = text("""
            SELECT 
                je.issue_key,
                1 - (je.embedding <=> :query_vec::vector) as similarity
            FROM jira_embeddings je
            WHERE je.embedding IS NOT NULL
            ORDER BY je.embedding <=> :query_vec::vector
            LIMIT :limit
        """)
        
        results = db.execute(
            query,
            {
                "query_vec": embedding_str,
                "limit": limit,
            }
        ).fetchall()
        
        # Create index for performance:
        # CREATE INDEX ON jira_embeddings USING hnsw (embedding vector_cosine_ops);
        
        # ... rest of processing
    finally:
        db.close()
```

**Solution B: Dedicated Vector Database (Qdrant/Pinecone/Weaviate)**

For very large scale (millions of embeddings):

```python
# backend/app/services/vector_db.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

class VectorDB:
    def __init__(self):
        self.client = QdrantClient(host="localhost", port=6333)
        self.collection_name = "jira_embeddings"
        
    def upsert(self, issue_key: str, embedding: List[float], metadata: dict):
        self.client.upsert(
            collection_name=self.collection_name,
            points=[{
                "id": hash(issue_key),
                "vector": embedding,
                "payload": {"issue_key": issue_key, **metadata}
            }]
        )
    
    def search(self, query_embedding: List[float], limit: int = 10):
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
        )
        return results
```

**Performance Comparison:**
- Current: O(n) - loads all embeddings
- pgvector: O(log n) with HNSW index
- Dedicated vector DB: O(log n) + distributed search

---

### 4. **Database Scaling**

#### Connection Pooling

**Current:**
```python
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

**Improved:**
```python
# backend/app/db/session.py
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,          # Base pool size
    max_overflow=40,        # Max connections beyond pool_size
    pool_recycle=3600,      # Recycle connections after 1 hour
    pool_timeout=30,        # Timeout for getting connection
    echo=False,             # Set to True for SQL debugging
)
```

#### Read Replicas

For read-heavy workloads (searches, status checks):

```python
# backend/app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Write database (primary)
write_engine = create_engine(
    os.getenv("DATABASE_URL_WRITE", DATABASE_URL),
    pool_size=10,
    max_overflow=20,
)

# Read database (replica)
read_engine = create_engine(
    os.getenv("DATABASE_URL_READ", DATABASE_URL),
    pool_size=20,
    max_overflow=40,
)

SessionLocalWrite = sessionmaker(bind=write_engine)
SessionLocalRead = sessionmaker(bind=read_engine)

# Use read session for queries
def get_read_session():
    return SessionLocalRead()

# Use write session for mutations
def get_write_session():
    return SessionLocalWrite()
```

**Usage:**
```python
# For searches (read-only)
db = get_read_session()

# For inserts/updates (write)
db = get_write_session()
```

---

### 5. **Caching Layer**

#### Redis Caching

**For frequently accessed data:**

```python
# backend/app/services/cache.py
import redis
import json
import hashlib

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True,
)

def cache_key(prefix: str, **kwargs) -> str:
    """Generate cache key from parameters"""
    key_str = json.dumps(kwargs, sort_keys=True)
    hash_str = hashlib.md5(key_str.encode()).hexdigest()
    return f"{prefix}:{hash_str}"

def get_cached_analysis(issue_key: str, idempotency_key: str):
    key = cache_key("analysis", issue_key=issue_key, idem=idempotency_key)
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

def set_cached_analysis(issue_key: str, idempotency_key: str, result: dict, ttl: int = 3600):
    key = cache_key("analysis", issue_key=issue_key, idem=idempotency_key)
    redis_client.setex(key, ttl, json.dumps(result))
```

**Update endpoints:**
```python
@app.post("/jira/analyze")
async def jira_analyze(request: JiraAnalyzeRequest):
    # Check cache first
    cached = get_cached_analysis(key, idempotency_key)
    if cached:
        return {**cached, "cache_hit": True}
    
    # ... process request ...
    
    # Cache result
    set_cached_analysis(key, idempotency_key, result_dict)
```

---

### 6. **Embedding Service Separation**

#### Current State
- Embedding generation in same process as API
- Model loaded per worker process

#### Solution: Separate Embedding Service

**Architecture:**
```
FastAPI API → Embedding Service (gRPC/HTTP) → Model Serving
```

**Option A: Simple HTTP Service**
```python
# embedding_service/main.py
from fastapi import FastAPI
from app.services.embeddings import generate_embedding

app = FastAPI()

@app.post("/embed")
async def embed(text: str, task_type: str = "retrieval_document"):
    embedding = generate_embedding(text, task_type)
    return {"embedding": embedding}
```

**Option B: Model Server (TorchServe/Triton)**
- Better for GPU acceleration
- Batch processing
- Model versioning

**Update API to call service:**
```python
# backend/app/services/embeddings.py
import httpx

async def generate_embedding_async(text: str, task_type: str = "retrieval_document"):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8001/embed"),
            json={"text": text, "task_type": task_type},
            timeout=30.0,
        )
        return response.json()["embedding"]
```

---

### 7. **Async Improvements**

#### Current Issues
- Some blocking operations in async endpoints
- Database queries not fully async

#### Solution: Async Database Access

```python
# backend/app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async_engine = create_async_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=20,
    max_overflow=40,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Dependency for FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

**Update endpoints:**
```python
from sqlalchemy import select
from app.db.session import get_db

@app.post("/jira/analyze")
async def jira_analyze(request: JiraAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    # Async query
    result = await db.execute(
        select(JiraIssue).where(JiraIssue.issue_key == key)
    )
    existing = result.scalar_one_or_none()
    
    # Async embedding generation
    embedding = await generate_embedding_async(text, task_type)
    
    # Async commit
    await db.commit()
```

---

### 8. **Frontend Scaling**

#### Current State
- Vite dev server
- No CDN/static hosting

#### Solutions

**Option A: Static Build + CDN**
```bash
cd frontend
npm run build
# Deploy dist/ to S3/CloudFront, Vercel, or Netlify
```

**Option B: Nginx Serving**
```nginx
# nginx.conf
server {
    listen 80;
    server_name api.example.com;
    
    location / {
        proxy_pass http://api-backend;
        proxy_set_header Host $host;
    }
}

server {
    listen 80;
    server_name app.example.com;
    
    root /var/www/frontend/dist;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 weeks)
1. ✅ Add connection pooling configuration
2. ✅ Implement Redis caching for analysis results
3. ✅ Add health check endpoint
4. ✅ Optimize vector search (pgvector)

### Phase 2: Job Queue (2-3 weeks)
1. ✅ Set up Redis + Celery
2. ✅ Migrate in-memory jobs to Celery tasks
3. ✅ Add worker monitoring (Flower)

### Phase 3: Database Scaling (3-4 weeks)
1. ✅ Migrate to pgvector
2. ✅ Set up read replicas
3. ✅ Add database monitoring

### Phase 4: Service Separation (4-6 weeks)
1. ✅ Separate embedding service
2. ✅ Containerize services
3. ✅ Set up orchestration (Docker Compose/K8s)

### Phase 5: Advanced (6+ weeks)
1. ✅ Full async database access
2. ✅ Dedicated vector database (if needed)
3. ✅ Auto-scaling configuration
4. ✅ Monitoring & observability (Prometheus/Grafana)

---

## Monitoring & Observability

### Metrics to Track
- Request latency (p50, p95, p99)
- Database connection pool usage
- Embedding generation time
- Vector search latency
- Job queue depth
- Error rates

### Tools
- **APM**: Datadog, New Relic, or OpenTelemetry
- **Logging**: Structured logging with correlation IDs
- **Metrics**: Prometheus + Grafana
- **Tracing**: Jaeger or Zipkin

---

## Cost Estimates

### Current (Single Instance)
- 1x API server: ~$50-100/month
- 1x Postgres: ~$50-100/month
- **Total: ~$100-200/month**

### Scaled (Production)
- 3x API servers (load balanced): ~$150-300/month
- Postgres (managed, with replicas): ~$200-400/month
- Redis: ~$50-100/month
- Vector DB (if separate): ~$100-200/month
- CDN: ~$20-50/month
- **Total: ~$520-1050/month**

---

## Testing Scalability

### Load Testing
```bash
# Install k6
brew install k6  # or download from k6.io

# Run load test
k6 run load_test.js
```

**Example load test:**
```javascript
// load_test.js
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // Ramp up
    { duration: '1m', target: 100 },  // Stay at 100 users
    { duration: '30s', target: 0 },   // Ramp down
  ],
};

export default function () {
  const response = http.post('http://localhost:8000/jira/analyze', JSON.stringify({
    issue_key: 'TEST-123',
    summary: 'Test issue',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });
  
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 2s': (r) => r.timings.duration < 2000,
  });
}
```

---

## Summary

**Immediate Actions:**
1. Add connection pooling
2. Implement Redis caching
3. Migrate to pgvector for vector search

**Medium-term:**
1. Set up Celery for distributed job processing
2. Add read replicas for database
3. Containerize application

**Long-term:**
1. Separate embedding service
2. Full async database access
3. Kubernetes deployment
4. Comprehensive monitoring

This scaling strategy will allow the system to handle **10-100x** more traffic with proper infrastructure.
