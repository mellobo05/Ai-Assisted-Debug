"""
Initialize database tables
Run this script to create all database tables
"""
from app.db.base import Base
from app.db.session import engine
from app.models import debug  # Import models to register them
from app.models import jira  # Import JIRA models to register them
from app.models import jira_analysis  # Import JIRA analysis run model to register it
from app.models import snippets  # Import code snippet model to register it

def init_db():
    """Create all database tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()
