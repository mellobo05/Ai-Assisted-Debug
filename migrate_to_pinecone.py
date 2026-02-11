"""
Migration Script: PostgreSQL → Pinecone

This script migrates existing embeddings from your PostgreSQL database to Pinecone.
Use this if you already have debug sessions with embeddings in the database.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def migrate_embeddings_to_pinecone(batch_size=100, dry_run=False):
    """
    Migrate embeddings from PostgreSQL to Pinecone
    
    Args:
        batch_size: Number of embeddings to process in each batch
        dry_run: If True, only print what would be done without actually doing it
    """
    from backend.app.db.session import SessionLocal
    from backend.app.models.debug import DebugSession, DebugEmbedding
    from backend.app.services.pinecone_service import (
        is_pinecone_enabled,
        batch_upsert_embeddings,
        get_index_stats
    )
    
    print("=" * 60)
    print("PINECONE MIGRATION SCRIPT")
    print("=" * 60)
    print()
    
    # Check if Pinecone is enabled
    if not is_pinecone_enabled():
        print("❌ Pinecone is not enabled!")
        print("   Set USE_PINECONE=true in your .env file")
        return False
    
    print("✅ Pinecone is enabled")
    print()
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Get total count
        total_embeddings = db.query(DebugEmbedding).count()
        print(f"📊 Total embeddings in database: {total_embeddings}")
        
        if total_embeddings == 0:
            print("   No embeddings to migrate!")
            return True
        
        # Get Pinecone stats
        print()
        print("📊 Current Pinecone index stats:")
        stats = get_index_stats()
        current_vectors = stats.get('total_vector_count', 0)
        print(f"   Vectors in Pinecone: {current_vectors}")
        print()
        
        # Confirm migration
        if not dry_run:
            print(f"⚠️  This will migrate {total_embeddings} embeddings to Pinecone")
            response = input("Continue? (yes/no): ").strip().lower()
            
            if response != "yes":
                print("Migration cancelled by user")
                return False
            print()
        
        # Process in batches
        migrated = 0
        errors = 0
        
        print("🚀 Starting migration...")
        print()
        
        # Get all embeddings (with pagination)
        offset = 0
        
        while offset < total_embeddings:
            # Fetch batch
            embeddings_batch = db.query(DebugEmbedding).offset(offset).limit(batch_size).all()
            
            if not embeddings_batch:
                break
            
            # Prepare batch data
            batch_data = []
            
            for db_embedding in embeddings_batch:
                # Get associated session
                session = db.query(DebugSession).filter(
                    DebugSession.id == db_embedding.session_id
                ).first()
                
                if session:
                    metadata = {
                        "domain": session.domain or "unknown",
                        "os": session.os or "unknown",
                        "issue_summary": (session.issue_summary or "")[:500],  # Limit size
                        "status": session.status or "unknown"
                    }
                    
                    batch_data.append({
                        "session_id": str(session.id),
                        "embedding": db_embedding.embedding,
                        "metadata": metadata
                    })
            
            # Upsert batch to Pinecone
            if not dry_run and batch_data:
                try:
                    success = batch_upsert_embeddings(batch_data)
                    if success:
                        migrated += len(batch_data)
                        print(f"✅ Migrated batch {offset//batch_size + 1}: {len(batch_data)} embeddings")
                    else:
                        errors += len(batch_data)
                        print(f"❌ Failed to migrate batch {offset//batch_size + 1}")
                except Exception as e:
                    errors += len(batch_data)
                    print(f"❌ Error migrating batch {offset//batch_size + 1}: {e}")
            else:
                if dry_run:
                    print(f"🔍 Would migrate batch {offset//batch_size + 1}: {len(batch_data)} embeddings")
                    migrated += len(batch_data)
            
            offset += batch_size
        
        # Summary
        print()
        print("=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        
        if dry_run:
            print(f"🔍 DRY RUN: Would migrate {migrated} embeddings")
        else:
            print(f"✅ Successfully migrated: {migrated}")
            print(f"❌ Errors: {errors}")
            print(f"📊 Total processed: {migrated + errors}")
            
            # Verify final count
            final_stats = get_index_stats()
            final_count = final_stats.get('total_vector_count', 0)
            print()
            print(f"📊 Final Pinecone vector count: {final_count}")
        
        print("=" * 60)
        print()
        
        return errors == 0
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        db.close()


def verify_migration():
    """
    Verify that embeddings were successfully migrated
    """
    from backend.app.db.session import SessionLocal
    from backend.app.models.debug import DebugEmbedding
    from backend.app.services.pinecone_service import get_index_stats
    
    print()
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    print()
    
    db = SessionLocal()
    try:
        db_count = db.query(DebugEmbedding).count()
        print(f"📊 Embeddings in database: {db_count}")
        
        stats = get_index_stats()
        pinecone_count = stats.get('total_vector_count', 0)
        print(f"📊 Vectors in Pinecone: {pinecone_count}")
        print()
        
        if db_count == pinecone_count:
            print("✅ Counts match! Migration successful.")
        elif pinecone_count < db_count:
            print(f"⚠️  Pinecone has {db_count - pinecone_count} fewer vectors")
            print("   Some embeddings may not have been migrated")
        else:
            print(f"⚠️  Pinecone has {pinecone_count - db_count} more vectors")
            print("   This is normal if you've processed new sessions")
        
        print()
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate embeddings from PostgreSQL to Pinecone")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of embeddings to process in each batch (default: 100)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no changes will be made)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify migration (don't migrate)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.verify:
            verify_migration()
        else:
            success = migrate_embeddings_to_pinecone(
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
            
            if success and not args.dry_run:
                verify_migration()
            
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
