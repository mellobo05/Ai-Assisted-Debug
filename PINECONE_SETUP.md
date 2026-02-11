# Pinecone Integration Setup Guide

This guide will help you set up Pinecone for your RAG (Retrieval-Augmented Generation) system.

## Why Pinecone?

Pinecone is a managed vector database optimized for similarity search. Benefits include:

- **Fast similarity search** at scale (millions of vectors)
- **Managed infrastructure** - no database management overhead
- **Metadata filtering** - filter results by domain, OS, etc.
- **Low latency** - typical queries return in milliseconds
- **Scalability** - automatically handles growing datasets

## Setup Steps

### 1. Create a Pinecone Account

1. Go to [https://app.pinecone.io/](https://app.pinecone.io/)
2. Sign up for a free account (free tier includes 100k vectors)
3. Navigate to "API Keys" and copy your API key

### 2. Create a Pinecone Index

1. In the Pinecone console, click **"Create Index"**
2. Configure the index:
   - **Name**: `debug-sessions` (or your preferred name)
   - **Dimensions**: Choose based on your embedding provider:
     - Gemini: `768`
     - SBERT (all-MiniLM-L6-v2): `384`
     - OpenAI (text-embedding-3-small): `1536`
   - **Metric**: `cosine` (recommended for semantic similarity)
   - **Cloud**: Choose your preferred region
   - **Pod Type**: `Starter` (for free tier) or `s1` (for production)

3. Click **"Create Index"**

### 3. Install Pinecone SDK

```powershell
pip install pinecone-client
```

Or update your dependencies:

```powershell
pip install -r requirement.txt
```

### 4. Configure Environment Variables

Edit your `.env` file and add:

```env
# Enable Pinecone
USE_PINECONE=true

# Pinecone API Key (from step 1)
PINECONE_API_KEY=your_api_key_here

# Index Configuration (from step 2)
PINECONE_INDEX_NAME=debug-sessions
PINECONE_DIMENSION=768
PINECONE_METRIC=cosine
PINECONE_NAMESPACE=default
```

**Important**: Make sure `PINECONE_DIMENSION` matches your embedding provider:
- If using Gemini (`EMBEDDING_PROVIDER=gemini`): use `768`
- If using SBERT (`EMBEDDING_PROVIDER=sbert`): use `384`
- If using OpenAI (`EMBEDDING_PROVIDER=openai`): use `1536`

### 5. Test Your Setup

Run the test script:

```powershell
python test_pinecone.py
```

This will:
- Connect to your Pinecone index
- Create a test embedding
- Upsert it to Pinecone
- Search for similar embeddings
- Display index statistics

## Usage

### Hybrid Approach (Recommended)

The system uses a **hybrid approach**:

1. **Database**: Stores session metadata and embeddings (backup)
2. **Pinecone**: Stores embeddings for fast similarity search

This gives you:
- Fast retrieval via Pinecone
- Data durability via PostgreSQL
- Metadata filtering capabilities

### Storing Embeddings

When you process a debug session, embeddings are automatically stored in both:
- PostgreSQL database
- Pinecone (if `USE_PINECONE=true`)

```python
from app.services.rag import process_rag_pipeline

process_rag_pipeline(session_id="your-session-id")
```

### Searching Similar Sessions

Use the search function to find similar debug sessions:

```python
from app.services.rag import search_similar_sessions

results = search_similar_sessions(
    issue_text="Application crashes on startup",
    top_k=5,
    domain_filter="backend"  # Optional
)

for result in results:
    print(f"Session: {result['session_id']}")
    print(f"Similarity: {result['similarity_score']:.4f}")
    print(f"Issue: {result['issue_summary']}")
    print(f"Domain: {result['domain']}")
    print("---")
```

## Architecture

### Before Pinecone
```
Debug Session → Generate Embedding → Store in PostgreSQL
                                    ↓
                          Slow similarity search on query
```

### With Pinecone
```
Debug Session → Generate Embedding → Store in PostgreSQL (metadata)
                                    → Store in Pinecone (vectors)
                                    ↓
                          Fast similarity search via Pinecone
```

## Fallback Behavior

If Pinecone is disabled (`USE_PINECONE=false` or API key missing):
- Embeddings are still stored in PostgreSQL
- Similarity search falls back to database queries
- Performance will be slower but system still works

## Cost Considerations

### Free Tier
- **100,000 vectors**
- **1 index**
- **1 pod**
- Good for development and small projects

### Paid Tiers
- **Starter**: $70/month for 5M vectors
- **Standard**: Starting at $0.096/hour per pod
- See [Pinecone Pricing](https://www.pinecone.io/pricing/) for details

## Troubleshooting

### Error: "Pinecone index does not exist"

**Solution**: Create the index in the Pinecone console first (see Step 2)

### Error: "PINECONE_API_KEY not set"

**Solution**: Add `PINECONE_API_KEY` to your `.env` file

### Error: "Dimension mismatch"

**Solution**: Make sure `PINECONE_DIMENSION` matches your embedding provider:
- Check `EMBEDDING_PROVIDER` in `.env`
- Update `PINECONE_DIMENSION` accordingly

### Embeddings not showing up in Pinecone

**Check**:
1. `USE_PINECONE=true` in `.env`
2. Index name matches `PINECONE_INDEX_NAME`
3. Check logs for error messages
4. Run `python test_pinecone.py` to verify connection

## Migration from Database-Only

If you have existing embeddings in the database, you can migrate them to Pinecone:

```python
# TODO: Create migration script
# scripts/migrate_to_pinecone.py
```

## Advanced Configuration

### Multiple Namespaces

Use namespaces to organize vectors by environment:

```env
# Development
PINECONE_NAMESPACE=dev

# Production
PINECONE_NAMESPACE=prod
```

### Metadata Filtering

You can filter searches by metadata:

```python
results = search_similar_sessions(
    issue_text="Database connection timeout",
    top_k=5,
    domain_filter="backend"  # Only return backend issues
)
```

Available metadata fields:
- `domain` (e.g., "backend", "frontend")
- `os` (e.g., "Windows", "Linux")
- `status` (e.g., "EMBEDDING_GENERATED")

## References

- [Pinecone Documentation](https://docs.pinecone.io/)
- [Pinecone Python SDK](https://docs.pinecone.io/docs/python-client)
- [Vector Databases Explained](https://www.pinecone.io/learn/vector-database/)

## Support

For issues with:
- **Pinecone setup**: Check [Pinecone Support](https://support.pinecone.io/)
- **Integration**: Create an issue in this repository
