"""
Main crawler orchestration - coordinates fetching and storing.
Uses star range slicing to bypass GitHub's 1,000 result limit per query.
"""
import sys
from typing import List, Tuple

from .config import Config, load_config
from .models import RepositoryDTO, create_db_engine, create_session_factory
from .github_client import GitHubClient
from .repository import RepositoryStore


def generate_star_ranges(target: int) -> List[Tuple[int, int]]:
    """
    Generate star ranges for slicing the search.
    
    GitHub search API limits results to 1,000 per query.
    By searching different star ranges, we can collect more repos.
    
    Returns:
        List of (min_stars, max_stars) tuples
    """
    ranges = []
    
    # Low star repos (0-10) - huge pool
    for i in range(0, 11):
        ranges.append((i, i))
    
    # 11-100 in steps of 10
    for i in range(11, 101, 10):
        ranges.append((i, i + 9))
    
    # 101-1000 in steps of 100
    for i in range(101, 1001, 100):
        ranges.append((i, i + 99))
    
    # 1001-10000 in steps of 500
    for i in range(1001, 10001, 500):
        ranges.append((i, i + 499))
    
    # 10001-100000 in steps of 5000
    for i in range(10001, 100001, 5000):
        ranges.append((i, i + 4999))
    
    # 100001+ (high star repos)
    ranges.append((100001, 1000000))
    
    return ranges


def crawl_star_range(
    github_client: GitHubClient,
    session_factory,
    min_stars: int,
    max_stars: int,
    config: Config,
    current_total: int
) -> Tuple[int, int]:
    """
    Crawl repositories within a specific star range.
    
    Args:
        github_client: GitHub API client
        session_factory: Database session factory
        min_stars: Minimum star count
        max_stars: Maximum star count
        config: Configuration object
        current_total: Current total repos collected
        
    Returns:
        Tuple of (repos collected in this range, new total)
    """
    search_query = f"stars:{min_stars}..{max_stars}"
    cursor = None
    range_collected = 0
    batch_buffer: List[RepositoryDTO] = []
    
    while current_total < config.repos_target:
        # Fetch page from GitHub
        result = github_client.fetch_repositories(search_query, cursor)
        
        if not result.repositories:
            break
        
        # Add to batch buffer
        batch_buffer.extend(result.repositories)
        range_collected += len(result.repositories)
        current_total += len(result.repositories)
        
        # Log progress
        print(
            f"[OK] Range {search_query}: +{len(result.repositories)} | "
            f"Total: {current_total:,} | "
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
        
        # Check pagination - stop if no more pages or hit 1000 limit
        if not result.page_info.has_next_page:
            break
        
        cursor = result.page_info.end_cursor
    
    # Commit any remaining repos in buffer
    if batch_buffer:
        with session_factory() as session:
            store = RepositoryStore(session)
            stored = store.upsert_batch(batch_buffer)
        print(f"[DB] Committed {stored:,} unique repos to database")
    
    return range_collected, current_total


def run_crawler(config: Config) -> int:
    """
    Main crawler logic - fetch repos from GitHub and store in database.
    Uses star range slicing to bypass the 1,000 result limit.
    
    Args:
        config: Immutable configuration object
        
    Returns:
        Total number of repositories collected
    """
    # Initialize components
    engine = create_db_engine(config.database_url)
    SessionFactory = create_session_factory(engine)
    github_client = GitHubClient(config)
    
    # Generate star ranges for slicing
    star_ranges = generate_star_ranges(config.repos_target)
    
    total_collected = 0
    
    print(f"\n[INFO] Starting GitHub crawl (target: {config.repos_target:,} repos)")
    print(f"[INFO] Using {len(star_ranges)} star ranges to bypass 1,000 result limit\n")
    
    for min_stars, max_stars in star_ranges:
        if total_collected >= config.repos_target:
            break
        
        print(f"[INFO] Crawling star range: {min_stars}..{max_stars}")
        
        range_collected, total_collected = crawl_star_range(
            github_client=github_client,
            session_factory=SessionFactory,
            min_stars=min_stars,
            max_stars=max_stars,
            config=config,
            current_total=total_collected
        )
        
        if range_collected > 0:
            print(f"[INFO] Range complete: +{range_collected:,} repos\n")
    
    # Get actual count from database
    with SessionFactory() as session:
        store = RepositoryStore(session)
        db_count = store.get_count()
    
    print(f"\n[DONE] Crawl complete!")
    print(f"[DONE] Total fetched: {total_collected:,}")
    print(f"[DONE] Unique in database: {db_count:,}")
    
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
