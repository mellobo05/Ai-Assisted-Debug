## scripts/tests

Small runnable smoke tests for local development (no pytest required).

Run from project root.

### 1) API health
```powershell
python scripts/tests/test_api_health.py
```

### 2) JIRA DB counts
```powershell
python scripts/tests/test_jira_db_counts.py
```

### 3) Search against JIRA DB
```powershell
python scripts/tests/test_search_jira.py
```

### 4) Ingest sample cleaned CSV into DB (fixture)
```powershell
python scripts/tests/test_ingest_sample_jira_csv.py
```

### 5) Run the YAML agent workflow (fixture -> workflow -> report)
```powershell
python scripts/tests/test_agent_workflow_jira_debug.py
```

