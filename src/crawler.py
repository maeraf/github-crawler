"""
Main crawler orchestration - coordinates fetching and storing.
"""
import sys
from typing import List

from .config import Config, load_config
from .models import RepositoryDTO, create_db_engine, create_session_factory
from .github_client import GitHubClient
from .repository import RepositoryStore


def run_crawler(config: Config) -> int:
    """
    Main crawler logic - fetch repos from GitHub and store in database.
    
    Args:
        config: Immutable configuration object
        
    Returns:
        Total number of repositories collected
    """
    # Initialize components
    engine = create_db_engine(config.database_url)
    SessionFactory = create_session_factory(engine)
    github_client = GitHubClient(config)
    
    cursor = None
    total_collected = 0
    batch_buffer: List[RepositoryDTO] = []
    
    print(f"\n[INFO] Starting GitHub crawl (target: {config.repos_target:,} repos)...\n")
    
    while total_collected < config.repos_target:
        # Fetch page from GitHub
        result = github_client.fetch_repositories(cursor)
        
        # Add to batch buffer
        batch_buffer.extend(result.repositories)
        total_collected += len(result.repositories)
        
        # Log progress
        print(
            f"[OK] Fetched: {total_collected:,} repos | "
            f"Rate limit: {result.rate_limit.remaining} remaining"
        )
        
        # Commit batch to database when buffer is full
        if len(batch_buffer) >= config.batch_size:
            with SessionFactory() as session:
                store = RepositoryStore(session)
                store.upsert_batch(batch_buffer)
            print(f"[DB] Committed {len(batch_buffer):,} repos to database")
            batch_buffer = []
        
        # Check rate limit
        if github_client.should_wait_for_rate_limit(result.rate_limit):
            github_client.wait_for_rate_limit_reset(result.rate_limit.reset_at)
        
        # Check pagination
        if not result.page_info.has_next_page:
            print("[INFO] No more pages available")
            break
        
        cursor = result.page_info.end_cursor
    
    # Commit any remaining repos in buffer
    if batch_buffer:
        with SessionFactory() as session:
            store = RepositoryStore(session)
            store.upsert_batch(batch_buffer)
        print(f"[DB] Committed final {len(batch_buffer):,} repos to database")
    
    print(f"\n[DONE] Total repositories collected: {total_collected:,}")
    return total_collected


def main():
    """Entry point for the crawler."""
    try:
        config = load_config()
        run_crawler(config)
    except ValueError as e:
        print(f"[ERROR] Configuration error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"[ERROR] Runtime error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
