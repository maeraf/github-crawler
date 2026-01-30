"""
Database setup script - creates tables and schema.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.models import create_db_engine, create_tables


def main():
    """Create database tables."""
    print("[INFO] Setting up database schema...")
    
    try:
        config = load_config()
        engine = create_db_engine(config.database_url)
        create_tables(engine)
        print("[OK] Database schema created successfully!")
    except Exception as e:
        print(f"[ERROR] Failed to create schema: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
