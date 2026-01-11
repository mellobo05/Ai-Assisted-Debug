"""
Test database connection script
"""
import sys
sys.path.insert(0, 'backend')

try:
    from app.db.session import engine
    print("Testing database connection...")
    conn = engine.connect()
    print("[OK] Database connection successful!")
    conn.close()
except Exception as e:
    print(f"[ERROR] Database connection failed: {e}")
    print("\nTo fix this:")
    print("1. Ensure PostgreSQL is installed and running")
    print("2. Update credentials in backend/app/db/session.py if needed")
    print("3. Or use Docker: docker run --name pgvector-db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=1234567890 -e POSTGRES_DB=postgres -p 5432:5432 -d pgvector/pgvector:pg16")
    sys.exit(1)
