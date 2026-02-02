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

### UI: new JIRA intake + fetch/summarize

The frontend now supports two “minimal” flows:

1) **Add new JIRA with logs** (offline intake)
- Stores a user-provided issue into `jira_issues` + `jira_embeddings`
- You can paste logs or upload a `.txt/.log` file (it’s read client-side and sent as text)
- Backend endpoint: `POST /jira/intake`

2) **Fetch & summarize existing JIRA**
- Reads the issue from local Postgres and returns a combined **report + analysis**
- You can optionally attach logs (paste or upload) to influence the RCA + fix suggestions
- Backend endpoint: `POST /jira/summarize`

### Using the UI to retrieve similar JIRA issues
1) Start **backend** + **frontend**
2) In the UI, use **JIRA Similarity Search**
3) Paste a query (or an issue key if you want to search by the issue text you provide) and click **Search**
4) Results show similar issues ranked by similarity score

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
$env:EMBEDDING_PROVIDER="gemini"
$env:USE_MOCK_EMBEDDING="true"
```

- **SBERT (local model):**

```powershell
$env:EMBEDDING_PROVIDER="sbert"
$env:USE_MOCK_EMBEDDING="false"
```

- **Gemini embeddings:**
Set `GEMINI_API_KEY` and:

```powershell
$env:EMBEDDING_PROVIDER="gemini"
$env:USE_MOCK_EMBEDDING="false"
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

### Troubleshooting
- **pgAdmin “failed to resolve host 'postgres'”**: use host `localhost` (not `postgres`).
- **No similar issues**: ensure embeddings exist (`jira_embeddings`) and re-embed after changing providers:

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_reembed_from_db.yaml --max-results 500
```

- **Embedding debug noise**: set `EMBEDDINGS_DEBUG=true` only when needed.

