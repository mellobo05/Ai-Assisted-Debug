### AI Assisted Debug

AI-powered **Auto Debug Assistant** that uses your locally ingested JIRA data (Postgres) plus embeddings for **similar issue retrieval** and **root-cause oriented summaries**.

### Architecture (high level)
- **Backend**: Python **FastAPI** (`backend/app/main.py`)
- **Database**: **Postgres** (tables like `jira_issues`, `jira_embeddings`)
- **Embeddings**: `gemini` / `sbert` / `mock` (`backend/app/services/embeddings.py`)
- **Frontend**: **React + TypeScript + Vite** (`frontend/`)
- **Agents**:
  - YAML workflows: `scripts/agent/workflows/*.yaml` run by `scripts/agent/run_workflow.py`
  - ADAG-style prompt runner: `agents/adag.py`

### Quick start (Windows / PowerShell)

#### 0) Create a `.env` (recommended)
Create `./.env` (repo root). **Do not commit it** (it’s gitignored).

Minimum example:

```env
DATABASE_URL=postgresql+psycopg2://postgres:<YOUR_PASSWORD>@127.0.0.1:5432/postgres
EMBEDDING_PROVIDER=mock
USE_MOCK_EMBEDDING=true
```

#### 1) Confirm Postgres is running
This repo assumes Postgres is available at:
- `postgresql://postgres:<YOUR_PASSWORD>@localhost:5432/postgres`

Configure credentials via environment variables / `.env` (recommended), or update your local `DATABASE_URL`.

If you have a local Postgres install, ensure it’s started and listening on **5432**.

#### 2) Initialize DB tables
From repo root:

```powershell
python -c "import sys; sys.path.insert(0, 'backend'); from app.db.init_db import init_db; init_db()"
```

#### 3) Ingest JIRA data (offline / from cleaned CSV)
Use your existing CSV ingestion scripts (recommended if your network blocks JIRA):

```powershell
python scripts/jira/ingest_cleaned_csv.py --csv scripts/tests/fixtures/jira_cleaned_sample.csv
```

#### 4) Start backend
```powershell
.\run_server.ps1 -NoReload
```

Backend will run on the configured port (default usually **8000** unless you changed it).

#### 5) Start frontend
```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal.

### UI: one-step “JIRA Analyze” pipeline

The UI now uses **one input form** to handle the full pipeline:

- Inputs: **JIRA ID**, **JIRA summary**, **logs**, **component**, **OS**, and optional notes
- Backend endpoint: `POST /jira/analyze`

Behavior:
- **Idempotent**: if you click Analyze twice with the same input, it reuses the same job / saved run (no duplicate records).
- If **same JIRA ID + same summary (+ same input fingerprint)** already exists and a previous analysis run is stored, the backend returns a **cached RCA** immediately.
- Otherwise it **upserts** the issue into `jira_issues` + `jira_embeddings`, computes a **fast report**, and then runs the LLM **asynchronously** (UI polls until analysis completes).
- Related issues:
  - Preferred: **live JIRA** JQL `text ~` search with iterative query expansion (requires `JIRA_BASE_URL` + credentials)
  - Fallback: local DB embedding similarity
  - If related issues are found, it stores `jira_issues.related_issue_keys` for faster access later.

Similarity filtering:
- If the user provides **component**, we first narrow candidates using DB component matches, then run embedding similarity only within that subset.
- If only **domain** is provided, we use a lightweight weakly-supervised classifier (from DB components/labels) + keyword matching as a prefilter.

Legacy endpoints still exist:
- `POST /jira/intake` (store + embed only)
- `POST /jira/summarize` (summarize an existing DB issue)

### ADAG-style “Fetch and summarize” (prompt mode)
This reads the issue from **local Postgres** (no live JIRA sync).

```powershell
cd agents
python adag.py --prompt "Fetch and summarize: SYSCROS-123559" --save_trace
```

- Prints:
  - A clean issue summary + similar issues
  - A **root-cause oriented analysis section** (via `llm.subagent`, with offline fallback)
- Trace file:
  - `agents/traces/<run_id>.md`

Disable analysis (summary + similar issues only):

```powershell
python adag.py --prompt "Fetch and summarize: SYSCROS-123559" --no-analysis
```

Run the swarm (includes fix/logging suggestions):

```powershell
python adag.py --prompt "Fetch and summarize: SYSCROS-123559" --use-swarm --domain media --save_trace
```

### Run YAML workflows (offline-friendly)
From repo root:

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/syscros_issue_summary.yaml --issue-key SYSCROS-131125 --limit 5
```

Or the ADAG-style workflow:

```powershell
python scripts/agent/run_workflow.py --workflow-file scripts/agent/workflows/jira_similar_issues_finder.yaml --workflow-params target_jira_key=SYSCROS-131125 max_results=5 similarity_threshold=60
```

### Embedding modes
Set via environment variables (PowerShell examples):

- **Mock (fast, offline):**

```powershell
$env:EMBEDDING_PROVIDER="mock"
$env:USE_MOCK_EMBEDDING="true"
```

- **SBERT (local model):**

```powershell
$env:EMBEDDING_PROVIDER="sbert"
$env:USE_MOCK_EMBEDDING="false"
```

- **OpenAI embeddings:**
Set `OPENAI_API_KEY` and:

```powershell
$env:EMBEDDING_PROVIDER="openai"
```

- **Gemini embeddings:**
Set `GEMINI_API_KEY` and:

```powershell
$env:EMBEDDING_PROVIDER="gemini"
$env:USE_MOCK_EMBEDDING="false"
```

Warmup behavior:
- SBERT warmup runs on startup but will **timeout quickly** so it doesn’t block server boot.
- You can disable warmup entirely:

```powershell
$env:EMBEDDINGS_WARMUP="false"
```

### pgAdmin: where to see your data
Connect with:
- **Host**: `localhost`
- **Port**: `5432`
- **DB**: `postgres`
- **User**: `postgres`
- **Password**: `<YOUR_PASSWORD>`

Then browse:
`Servers → <server> → Databases → postgres → Schemas → public → Tables → jira_issues`

### DB schema notes
- `jira_issues.os` exists and is backfilled to **`chromeos`** for existing rows (and populated on intake going forward).
- `jira_analysis_runs.idempotency_key` is used to avoid duplicate analysis-run rows for the same input.

### Evaluate classifier over/underfitting (quick)
This repo includes a simple evaluator for the weakly-supervised domain classifier:

```powershell
python scripts/ml/eval_issue_domain_classifier.py --max-items 500 --test-frac 0.2
```

Interpretation (rough):
- train \(\gg\) test → likely **overfitting**
- both low → likely **underfitting**

### Troubleshooting
- **pgAdmin “failed to resolve host 'postgres'”**: use host `localhost` (not `postgres`).
- **No similar issues**: ensure embeddings exist (`jira_embeddings`) and re-embed after changing providers:

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_reembed_from_db.yaml --max-results 500
```

- **Embedding debug noise**: set `EMBEDDINGS_DEBUG=true` only when needed.

