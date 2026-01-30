"""
Database export script - dumps repositories to CSV.
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.models import create_db_engine, create_session_factory
from src.repository import RepositoryStore


def main():
    """Export database to CSV."""
    output_path = os.environ.get("OUTPUT_PATH", "repositories.csv")
    
    print(f"[INFO] Exporting database to {output_path}...")
    
    try:
        config = load_config()
        engine = create_db_engine(config.database_url)
        SessionFactory = create_session_factory(engine)
        
        with SessionFactory() as session:
            store = RepositoryStore(session)
            count = store.export_to_csv(output_path)
            print(f"[OK] Exported {count:,} repositories to {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to export: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
