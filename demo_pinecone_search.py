"""
Demo: Pinecone-Powered Similarity Search

This script demonstrates how to use Pinecone to search for similar debug sessions.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def demo_search():
    """
    Demonstrate searching for similar debug sessions
    """
    from backend.app.services.rag import search_similar_sessions
    from backend.app.services.pinecone_service import is_pinecone_enabled
    
    print("=" * 60)
    print("PINECONE SIMILARITY SEARCH DEMO")
    print("=" * 60)
    print()
    
    # Check if Pinecone is enabled
    if is_pinecone_enabled():
        print("✅ Using Pinecone for fast similarity search")
    else:
        print("⚠️  Pinecone disabled - using database fallback")
        print("   (This will be slower for large datasets)")
    
    print()
    print("-" * 60)
    
    # Example 1: Search for backend issues
    print("\n📋 Example 1: Finding similar backend issues")
    print("-" * 60)
    
    query1 = """
    Application fails to start on Windows 10.
    Error message: 'Database connection timeout'
    Backend service using PostgreSQL.
    """
    
    print(f"Query: {query1.strip()}")
    print()
    
    results1 = search_similar_sessions(
        issue_text=query1,
        top_k=3,
        domain_filter="backend"  # Only search backend issues
    )
    
    if results1:
        print(f"Found {len(results1)} similar sessions:\n")
        for i, result in enumerate(results1, 1):
            print(f"  {i}. Session ID: {result['session_id']}")
            print(f"     Similarity: {result['similarity_score']:.4f}")
            print(f"     Domain: {result['domain']}")
            print(f"     OS: {result['os']}")
            print(f"     Issue: {result['issue_summary'][:100]}...")
            print()
    else:
        print("   No similar sessions found.")
        print("   (Index might be empty - process some sessions first)")
    
    # Example 2: Search without domain filter
    print("\n📋 Example 2: Finding similar issues (all domains)")
    print("-" * 60)
    
    query2 = "Application crashes when loading large files"
    
    print(f"Query: {query2}")
    print()
    
    results2 = search_similar_sessions(
        issue_text=query2,
        top_k=5
        # No domain filter - search all
    )
    
    if results2:
        print(f"Found {len(results2)} similar sessions:\n")
        for i, result in enumerate(results2, 1):
            print(f"  {i}. [{result['domain']}] {result['issue_summary'][:80]}...")
            print(f"     Similarity: {result['similarity_score']:.4f}")
            print()
    else:
        print("   No similar sessions found.")
    
    # Example 3: Search for frontend issues
    print("\n📋 Example 3: Finding similar frontend issues")
    print("-" * 60)
    
    query3 = "UI is not responsive on mobile devices"
    
    print(f"Query: {query3}")
    print()
    
    results3 = search_similar_sessions(
        issue_text=query3,
        top_k=3,
        domain_filter="frontend"
    )
    
    if results3:
        print(f"Found {len(results3)} similar sessions:\n")
        for i, result in enumerate(results3, 1):
            print(f"  {i}. {result['issue_summary'][:80]}...")
            print(f"     Similarity: {result['similarity_score']:.4f}")
            print(f"     OS: {result['os']}")
            print()
    else:
        print("   No similar frontend sessions found.")
    
    print("=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("Tips:")
    print("• Higher similarity scores (closer to 1.0) mean better matches")
    print("• Use domain filters to narrow results to specific areas")
    print("• Process more debug sessions to improve search quality")
    print("• Enable Pinecone (USE_PINECONE=true) for faster searches")
    print()


def demo_with_custom_query():
    """
    Interactive demo - search with user's own query
    """
    from backend.app.services.rag import search_similar_sessions
    
    print("=" * 60)
    print("CUSTOM SEARCH QUERY")
    print("=" * 60)
    print()
    
    # Get user input
    print("Enter your debug issue description:")
    query = input("> ").strip()
    
    if not query:
        print("No query provided. Exiting.")
        return
    
    print()
    print("Domain filter (optional, press Enter to skip):")
    print("  Options: backend, frontend, database, network, etc.")
    domain = input("> ").strip() or None
    
    print()
    print("Number of results (default: 5):")
    try:
        top_k = int(input("> ").strip() or "5")
    except ValueError:
        top_k = 5
    
    print()
    print(f"Searching for: '{query}'")
    if domain:
        print(f"Domain filter: {domain}")
    print(f"Top {top_k} results")
    print()
    print("Searching...")
    print()
    
    # Perform search
    results = search_similar_sessions(
        issue_text=query,
        top_k=top_k,
        domain_filter=domain
    )
    
    if results:
        print(f"✅ Found {len(results)} similar sessions:\n")
        print("=" * 60)
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. SESSION: {result['session_id']}")
            print(f"   Similarity: {result['similarity_score']:.4f}")
            print(f"   Domain: {result['domain']}")
            print(f"   OS: {result['os']}")
            print(f"   Status: {result['status']}")
            print(f"   Created: {result['created_at']}")
            print(f"\n   Issue:")
            print(f"   {result['issue_summary']}")
            print("-" * 60)
        
    else:
        print("❌ No similar sessions found.")
        print()
        print("Possible reasons:")
        print("• No sessions in the database yet")
        print("• No sessions match your query")
        print("• Domain filter is too restrictive")
    
    print()


if __name__ == "__main__":
    import sys
    
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--custom":
            demo_with_custom_query()
        else:
            demo_search()
            
            print()
            print("Want to try your own query?")
            print("Run: python demo_pinecone_search.py --custom")
            print()
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
