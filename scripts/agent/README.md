## scripts/agent

Run YAML-defined “agent” workflows locally.

These workflows call the same internal code as the FastAPI endpoints:
- JIRA sync (live JIRA -> Postgres + embeddings)
- Similarity search (query -> embedding -> cosine similarity over `jira_embeddings`)

### 1) Search similar JIRA issues (DB only)

Run (from repo root):

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_debug_search.yaml --query "HDMI flicker after hotplug" --limit 5
```

### 2) (Optional) Sync from JIRA then search

This requires working JIRA credentials in `.env`.

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_sync_and_search.yaml --issue-key SYSCROS-131125 --query "similar issues and fix" --limit 5
```

### 3) SYSCROS issue summary agent (DB + RAG)

This uses your locally ingested `jira_issues` + `jira_embeddings` tables.

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/syscros_issue_summary.yaml --issue-key SYSCROS-131125 --limit 5
```

### 4) Re-embed JIRA issues already in DB (after provider changes)

If you changed embedding mode (or improved mock embeddings), re-embed so similarity scores become meaningful:

```powershell
python scripts/agent/run_workflow.py --workflow scripts/agent/workflows/jira_reembed_from_db.yaml --max-results 500
```

### Notes

- If Gemini is blocked, set `USE_MOCK_EMBEDDING=true` in `.env` (or it will be auto-enabled by the CLI if unset).
- For internal Intel JIRA with SSL issues, prefer offline ingestion (`scripts/jira/ingest_cleaned_csv.py`) and then run **search-only**.

