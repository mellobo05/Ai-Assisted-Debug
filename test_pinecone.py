"""
Test script for Pinecone integration

This script tests the Pinecone setup and verifies that:
1. Pinecone client can connect
2. Index exists and is accessible
3. Embeddings can be upserted
4. Similarity search works
5. Index statistics are retrievable
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_pinecone_setup():
    """Test Pinecone integration"""
    
    print("=" * 60)
    print("PINECONE INTEGRATION TEST")
    print("=" * 60)
    print()
    
    # Check if Pinecone is enabled
    use_pinecone = os.getenv("USE_PINECONE", "false").lower() == "true"
    
    if not use_pinecone:
        print("❌ Pinecone is DISABLED")
        print("   Set USE_PINECONE=true in your .env file")
        return False
    
    print("✅ Pinecone is ENABLED")
    print()
    
    # Check API key
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("❌ PINECONE_API_KEY is not set")
        print("   Add PINECONE_API_KEY to your .env file")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...")
    print()
    
    # Import Pinecone service
    try:
        from backend.app.services.pinecone_service import (
            _get_pinecone_client,
            _get_pinecone_index,
            upsert_embedding,
            search_similar_embeddings,
            get_index_stats,
            delete_embedding
        )
        print("✅ Pinecone service imported successfully")
        print()
    except Exception as e:
        print(f"❌ Failed to import Pinecone service: {e}")
        return False
    
    # Test 1: Connect to Pinecone
    print("Test 1: Connecting to Pinecone...")
    try:
        client = _get_pinecone_client()
        print("✅ Connected to Pinecone client")
        print()
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False
    
    # Test 2: Connect to index
    print("Test 2: Connecting to index...")
    try:
        index = _get_pinecone_index()
        index_name = os.getenv("PINECONE_INDEX_NAME", "debug-sessions")
        print(f"✅ Connected to index: {index_name}")
        print()
    except Exception as e:
        print(f"❌ Failed to connect to index: {e}")
        print("\nMake sure you:")
        print("1. Created the index in Pinecone console")
        print("2. Set PINECONE_INDEX_NAME in .env to match")
        return False
    
    # Test 3: Get index stats
    print("Test 3: Getting index statistics...")
    try:
        stats = get_index_stats()
        print("✅ Index statistics:")
        print(f"   Total vectors: {stats.get('total_vector_count', 0)}")
        print(f"   Dimension: {stats.get('dimension', 'N/A')}")
        print()
        
        # Check dimension matches config
        expected_dim = int(os.getenv("PINECONE_DIMENSION", "768"))
        actual_dim = stats.get("dimension", 0)
        
        if actual_dim != expected_dim and stats.get('total_vector_count', 0) > 0:
            print(f"⚠️  Warning: Dimension mismatch!")
            print(f"   Index dimension: {actual_dim}")
            print(f"   Config dimension: {expected_dim}")
            print(f"   Update PINECONE_DIMENSION in .env to {actual_dim}")
            print()
    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
        return False
    
    # Test 4: Create and upsert test embedding
    print("Test 4: Upserting test embedding...")
    try:
        # Generate a test embedding
        from backend.app.services.embeddings import generate_embedding
        
        test_text = "This is a test debug session for Pinecone integration"
        test_embedding = generate_embedding(test_text)
        
        test_session_id = "test-pinecone-integration"
        test_metadata = {
            "domain": "test",
            "os": "test",
            "issue_summary": test_text,
            "status": "TEST"
        }
        
        success = upsert_embedding(
            session_id=test_session_id,
            embedding=test_embedding,
            metadata=test_metadata
        )
        
        if success:
            print(f"✅ Test embedding upserted (ID: {test_session_id})")
            print(f"   Embedding dimension: {len(test_embedding)}")
            print()
        else:
            print("❌ Failed to upsert test embedding")
            return False
            
    except Exception as e:
        print(f"❌ Error upserting: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 5: Search for similar embeddings
    print("Test 5: Searching for similar embeddings...")
    try:
        # Create a similar query
        query_text = "Test debug session for integration testing"
        query_embedding = generate_embedding(query_text, task_type="retrieval_query")
        
        results = search_similar_embeddings(
            query_embedding=query_embedding,
            top_k=3
        )
        
        if results:
            print(f"✅ Found {len(results)} similar embeddings:")
            for i, result in enumerate(results, 1):
                print(f"\n   Result {i}:")
                print(f"   - Session ID: {result['session_id']}")
                print(f"   - Similarity Score: {result['score']:.4f}")
                print(f"   - Domain: {result['metadata'].get('domain', 'N/A')}")
                print(f"   - OS: {result['metadata'].get('os', 'N/A')}")
        else:
            print("⚠️  No results found (index might be empty)")
        print()
            
    except Exception as e:
        print(f"❌ Error searching: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 6: Clean up test data
    print("Test 6: Cleaning up test data...")
    try:
        success = delete_embedding(test_session_id)
        if success:
            print(f"✅ Test embedding deleted")
        else:
            print(f"⚠️  Failed to delete test embedding (non-critical)")
        print()
    except Exception as e:
        print(f"⚠️  Error cleaning up: {e} (non-critical)")
        print()
    
    # Summary
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Your Pinecone integration is working correctly!")
    print()
    print("Next steps:")
    print("1. Process debug sessions to generate embeddings")
    print("2. Use search_similar_sessions() to find similar issues")
    print("3. Monitor your usage in Pinecone console")
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = test_pinecone_setup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
