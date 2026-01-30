"""
Main crawler orchestration - coordinates fetching and storing.
Uses star range slicing to bypass GitHub's 1,000 result limit per query.
Tracks actual unique count in database to reach target.
"""
import sys
from typing import List, Tuple

from .config import Config, load_config
from .models import RepositoryDTO, create_db_engine, create_session_factory
from .github_client import GitHubClient
from .repository import RepositoryStore


def generate_star_ranges() -> List[Tuple[int, int]]:
    """
    Generate star ranges for slicing the search.
    
    GitHub search API limits results to 1,000 per query.
    By searching different star ranges, we can collect more repos.
    
    Returns:
        List of (min_stars, max_stars) tuples
    """
    ranges = []
    
    # Low star repos (0-10) - each value separately for maximum coverage
    for i in range(0, 11):
        ranges.append((i, i))
    
    # 11-100 in steps of 5
    for i in range(11, 101, 5):
        ranges.append((i, i + 4))
    
    # 101-1000 in steps of 50
    for i in range(101, 1001, 50):
        ranges.append((i, i + 49))
    
    # 1001-10000 in steps of 200
    for i in range(1001, 10001, 200):
        ranges.append((i, i + 199))
    
    # 10001-100000 in steps of 2000
    for i in range(10001, 100001, 2000):
        ranges.append((i, i + 1999))
    
    # 100001+ (high star repos)
    ranges.append((100001, 500000))
    ranges.append((500001, 1000000))
    
    return ranges


def get_db_count(session_factory) -> int:
    """Get current count of unique repos in database."""
    with session_factory() as session:
        store = RepositoryStore(session)
        return store.get_count()


def crawl_star_range(
    github_client: GitHubClient,
    session_factory,
    min_stars: int,
    max_stars: int,
    config: Config,
) -> int:
    """
    Crawl repositories within a specific star range.
    
    Args:
        github_client: GitHub API client
        session_factory: Database session factory
        min_stars: Minimum star count
        max_stars: Maximum star count
        config: Configuration object
        
    Returns:
        Number of repos fetched in this range
    """
    search_query = f"stars:{min_stars}..{max_stars}"
    cursor = None
    range_fetched = 0
    batch_buffer: List[RepositoryDTO] = []
    
    while True:
        # Check if we've reached target (check DB count periodically)
        if range_fetched > 0 and range_fetched % 500 == 0:
            db_count = get_db_count(session_factory)
            if db_count >= config.repos_target:
                print(f"[INFO] Target reached: {db_count:,} unique repos in database")
                break
        
        # Fetch page from GitHub
        result = github_client.fetch_repositories(search_query, cursor)
        
        if not result.repositories:
            break
        
        # Add to batch buffer
        batch_buffer.extend(result.repositories)
        range_fetched += len(result.repositories)
        
        # Log progress
        print(
            f"[OK] Range {search_query}: +{len(result.repositories)} | "
            f"Range total: {range_fetched} | "
            f"Rate limit: {result.rate_limit.remaining}"
        )
        
        # Commit batch to database when buffer is full
        if len(batch_buffer) >= config.batch_size:
            with session_factory() as session:
                store = RepositoryStore(session)
                stored = store.upsert_batch(batch_buffer)
            print(f"[DB] Committed {stored:,} unique repos to database")
            batch_buffer = []
        
        # Check rate limit
        if github_client.should_wait_for_rate_limit(result.rate_limit):
            github_client.wait_for_rate_limit_reset(result.rate_limit.reset_at)
        
        # Check pagination - stop if no more pages
        if not result.page_info.has_next_page:
            break
        
        cursor = result.page_info.end_cursor
    
    # Commit any remaining repos in buffer
    if batch_buffer:
        with session_factory() as session:
            store = RepositoryStore(session)
            stored = store.upsert_batch(batch_buffer)
        print(f"[DB] Committed {stored:,} unique repos to database")
    
    return range_fetched


def run_crawler(config: Config) -> int:
    """
    Main crawler logic - fetch repos from GitHub and store in database.
    Uses star range slicing to bypass the 1,000 result limit.
    Continues until database has target number of unique repos.
    
    Args:
        config: Immutable configuration object
        
    Returns:
        Total number of unique repositories in database
    """
    # Initialize components
    engine = create_db_engine(config.database_url)
    SessionFactory = create_session_factory(engine)
    github_client = GitHubClient(config)
    
    # Generate star ranges for slicing
    star_ranges = generate_star_ranges()
    
    # Get initial count
    initial_count = get_db_count(SessionFactory)
    total_fetched = 0
    
    print(f"\n[INFO] Starting GitHub crawl")
    print(f"[INFO] Target: {config.repos_target:,} unique repos in database")
    print(f"[INFO] Current DB count: {initial_count:,}")
    print(f"[INFO] Using {len(star_ranges)} star ranges to bypass 1,000 result limit\n")
    
    for min_stars, max_stars in star_ranges:
        # Check current DB count before each range
        db_count = get_db_count(SessionFactory)
        if db_count >= config.repos_target:
            print(f"[INFO] Target reached: {db_count:,} unique repos in database")
            break
        
        remaining = config.repos_target - db_count
        print(f"[INFO] Crawling stars:{min_stars}..{max_stars} | DB: {db_count:,} | Need: {remaining:,} more")
        
        range_fetched = crawl_star_range(
            github_client=github_client,
            session_factory=SessionFactory,
            min_stars=min_stars,
            max_stars=max_stars,
            config=config,
        )
        
        total_fetched += range_fetched
        
        if range_fetched > 0:
            new_count = get_db_count(SessionFactory)
            print(f"[INFO] Range complete: fetched {range_fetched:,}, DB now has {new_count:,}\n")
    
    # Final count
    final_count = get_db_count(SessionFactory)
    
    print(f"\n[DONE] Crawl complete!")
    print(f"[DONE] Total API fetches: {total_fetched:,}")
    print(f"[DONE] Unique repos in database: {final_count:,}")
    
    return final_count


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
