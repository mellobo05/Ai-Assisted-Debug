# Pinecone Quick Reference

Quick reference guide for using Pinecone with your AI-Assisted Debug system.

## Setup Checklist

- [ ] Create Pinecone account at [app.pinecone.io](https://app.pinecone.io/)
- [ ] Create index with correct dimensions (768 for Gemini, 384 for SBERT, 1536 for OpenAI)
- [ ] Install Pinecone: `pip install pinecone-client`
- [ ] Set environment variables in `.env`
- [ ] Run test: `python test_pinecone.py`

## Environment Variables

Add to your `.env` file:

```env
USE_PINECONE=true
PINECONE_API_KEY=your_api_key_here
PINECONE_INDEX_NAME=debug-sessions
PINECONE_DIMENSION=768
PINECONE_METRIC=cosine
PINECONE_NAMESPACE=default
```

**Important**: Match `PINECONE_DIMENSION` to your embedding provider:
- Gemini: `768`
- SBERT: `384`
- OpenAI: `1536`

## Common Commands

### Test Setup
```powershell
python test_pinecone.py
```

### Migrate Existing Embeddings
```powershell
# Dry run (preview)
python migrate_to_pinecone.py --dry-run

# Actual migration
python migrate_to_pinecone.py

# Verify migration
python migrate_to_pinecone.py --verify
```

### Demo Searches
```powershell
# Run predefined examples
python demo_pinecone_search.py

# Interactive custom search
python demo_pinecone_search.py --custom
```

### Process New Sessions
```powershell
# Process a debug session (auto-stores in Pinecone)
python run_rag.py
```

## Code Examples

### Import Functions
```python
from backend.app.services.rag import (
    process_rag_pipeline,
    search_similar_sessions
)
from backend.app.services.pinecone_service import (
    is_pinecone_enabled,
    upsert_embedding,
    search_similar_embeddings,
    get_index_stats
)
```

### Process Debug Session
```python
# Generate and store embedding (auto-uploads to Pinecone)
process_rag_pipeline(
    session_id="your-session-id",
    use_mock_embedding="false",
    gemini_api_key="your-api-key"
)
```

### Search for Similar Issues
```python
# Search all domains
results = search_similar_sessions(
    issue_text="Application crashes on startup",
    top_k=5
)

# Search specific domain
results = search_similar_sessions(
    issue_text="Database connection timeout",
    top_k=3,
    domain_filter="backend"
)

# Process results
for result in results:
    print(f"Session: {result['session_id']}")
    print(f"Similarity: {result['similarity_score']:.4f}")
    print(f"Issue: {result['issue_summary']}")
```

### Direct Pinecone Operations
```python
from backend.app.services.embeddings import generate_embedding

# Generate embedding
text = "Application crashes when loading files"
embedding = generate_embedding(text)

# Store in Pinecone
upsert_embedding(
    session_id="session-123",
    embedding=embedding,
    metadata={
        "domain": "backend",
        "os": "Windows",
        "issue_summary": text
    }
)

# Search Pinecone
query_embedding = generate_embedding(
    "File loading issues",
    task_type="retrieval_query"
)

matches = search_similar_embeddings(
    query_embedding=query_embedding,
    top_k=5,
    filter_metadata={"domain": "backend"}
)

# Get index stats
stats = get_index_stats()
print(f"Total vectors: {stats['total_vector_count']}")
```

## Metadata Filters

Available metadata fields for filtering:

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `domain` | string | `"backend"` | Application domain |
| `os` | string | `"Windows"` | Operating system |
| `status` | string | `"EMBEDDING_GENERATED"` | Session status |
| `session_id` | string | `"uuid-here"` | Unique session ID |

### Filter Examples

```python
# Filter by domain
filter_metadata = {"domain": "frontend"}

# Filter by OS
filter_metadata = {"os": "Linux"}

# Multiple filters (AND logic)
filter_metadata = {
    "domain": "backend",
    "os": "Windows"
}
```

## Troubleshooting

### "Index not found"
**Cause**: Index doesn't exist in Pinecone
**Fix**: Create index in Pinecone console with matching name

### "Dimension mismatch"
**Cause**: Embedding dimension doesn't match index
**Fix**: Update `PINECONE_DIMENSION` in `.env` or recreate index

### "No results found"
**Cause**: Index is empty or query doesn't match
**Fix**: 
1. Check index has vectors: `python migrate_to_pinecone.py --verify`
2. Process debug sessions to populate index
3. Adjust query or remove filters

### "Connection timeout"
**Cause**: Network issues or invalid API key
**Fix**: 
1. Verify API key in `.env`
2. Check internet connection
3. Try again (Pinecone may be experiencing issues)

### Slow searches
**Cause**: Using database fallback instead of Pinecone
**Fix**: Set `USE_PINECONE=true` in `.env`

## Performance Tips

1. **Use Pinecone for production**: Much faster than database similarity search
2. **Batch operations**: Use `batch_upsert_embeddings()` for multiple inserts
3. **Filter early**: Use metadata filters to reduce search space
4. **Cache embeddings**: Embedding cache is enabled by default (see `embeddings.py`)
5. **Monitor usage**: Check Pinecone console for usage metrics

## Architecture

```
User Query
    ↓
Generate Query Embedding (Gemini/SBERT/OpenAI)
    ↓
Search Pinecone (vector similarity)
    ↓
Get Top K Session IDs + Scores
    ↓
Fetch Full Session Data from PostgreSQL
    ↓
Return Results to User
```

## Cost Management

### Free Tier Limits
- 100,000 vectors
- 1 index
- 1 pod

### Monitoring Usage
1. Check Pinecone console: [app.pinecone.io](https://app.pinecone.io/)
2. View index stats:
   ```python
   from backend.app.services.pinecone_service import get_index_stats
   stats = get_index_stats()
   print(stats['total_vector_count'])
   ```

### Staying Within Free Tier
- Delete old/unused embeddings
- Use single namespace for all data
- Monitor vector count regularly
- Consider upgrading if you need more

## Best Practices

1. **Always test first**: Run `python test_pinecone.py` after setup
2. **Migrate in batches**: Use `--batch-size` flag for large migrations
3. **Verify migrations**: Always run `--verify` after migrating
4. **Use consistent dimensions**: Don't change embedding provider after setup
5. **Monitor performance**: Check Pinecone console for latency metrics
6. **Backup data**: Keep embeddings in PostgreSQL as backup
7. **Use namespaces**: Separate dev/prod data with different namespaces

## Resources

- **Pinecone Docs**: [docs.pinecone.io](https://docs.pinecone.io/)
- **Setup Guide**: [PINECONE_SETUP.md](PINECONE_SETUP.md)
- **Python SDK**: [docs.pinecone.io/docs/python-client](https://docs.pinecone.io/docs/python-client)
- **Pricing**: [pinecone.io/pricing](https://www.pinecone.io/pricing/)

## Support

- **Pinecone Issues**: [support.pinecone.io](https://support.pinecone.io/)
- **Integration Issues**: Create issue in this repository
- **Questions**: Check existing issues or create new one
