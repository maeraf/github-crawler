"""
GitHub GraphQL API client with rate limiting and retry mechanism.
"""
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime

import requests

from .config import Config
from .models import RepositoryDTO


# GraphQL query to fetch repositories with star counts
# Uses $searchQuery variable for star range slicing
REPOS_QUERY = """
query ($cursor: String, $searchQuery: String!) {
  search(
    query: $searchQuery,
    type: REPOSITORY,
    first: 100,
    after: $cursor
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on Repository {
        id
        name
        owner { login }
        stargazerCount
      }
    }
  }
  rateLimit {
    remaining
    resetAt
  }
}
"""



@dataclass(frozen=True)
class RateLimitInfo:
    """Immutable rate limit information."""
    remaining: int
    reset_at: str


@dataclass(frozen=True)
class PageInfo:
    """Immutable pagination information."""
    has_next_page: bool
    end_cursor: Optional[str]


@dataclass(frozen=True)
class SearchResult:
    """Immutable result from a search query."""
    repositories: Tuple[RepositoryDTO, ...]
    page_info: PageInfo
    rate_limit: RateLimitInfo


class GitHubClient:
    """
    GitHub GraphQL API client with rate limiting and retry mechanism.
    
    Implements:
    - Exponential backoff on transient failures
    - Automatic sleep when rate limit is near exhaustion
    - Clean separation from business logic
    """
    
    def __init__(self, config: Config):
        self._config = config
        self._headers = {
            "Authorization": f"Bearer {config.github_token}",
            "Content-Type": "application/json",
        }
    
    def fetch_repositories(self, search_query: str, cursor: Optional[str] = None) -> SearchResult:
        """
        Fetch a page of repositories from GitHub.
        
        Args:
            search_query: GitHub search query (e.g., "stars:100..200")
            cursor: Pagination cursor from previous request
            
        Returns:
            SearchResult with repositories, pagination, and rate limit info
            
        Raises:
            RuntimeError: On unrecoverable errors
        """
        retries = 0
        
        while retries <= self._config.max_retries:
            try:
                response = self._make_request(search_query, cursor)
                return self._parse_response(response)
                
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > self._config.max_retries:
                    raise RuntimeError(f"Max retries exceeded: {e}") from e
                
                backoff = 2 ** retries
                print(f"[WARN] Request failed: {e}. Retrying in {backoff}s... ({retries}/{self._config.max_retries})")
                time.sleep(backoff)
    
    def _make_request(self, search_query: str, cursor: Optional[str]) -> dict:
        """Make GraphQL request to GitHub API."""
        payload = {
            "query": REPOS_QUERY,
            "variables": {"cursor": cursor, "searchQuery": search_query}
        }
        
        response = requests.post(
            self._config.github_api_url,
            json=payload,
            headers=self._headers,
            timeout=30
        )
        
        if response.status_code == 401:
            raise RuntimeError("Unauthorized - check your GITHUB_TOKEN")
        
        if response.status_code >= 500:
            raise requests.exceptions.RequestException(f"Server error: {response.status_code}")
        
        response.raise_for_status()
        
        data = response.json()
        
        # Check for GraphQL errors
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
            raise RuntimeError(f"GraphQL error: {error_msg}")
        
        return data
    
    def _parse_response(self, data: dict) -> SearchResult:
        """Parse GraphQL response into immutable data structures."""
        search = data["data"]["search"]
        rate = data["data"]["rateLimit"]
        
        repositories = tuple(
            RepositoryDTO.from_github_response(node)
            for node in search["nodes"]
            if node  # Filter out null nodes
        )
        
        page_info = PageInfo(
            has_next_page=search["pageInfo"]["hasNextPage"],
            end_cursor=search["pageInfo"]["endCursor"]
        )
        
        rate_limit = RateLimitInfo(
            remaining=rate["remaining"],
            reset_at=rate["resetAt"]
        )
        
        return SearchResult(
            repositories=repositories,
            page_info=page_info,
            rate_limit=rate_limit
        )
    
    def wait_for_rate_limit_reset(self, reset_at: str) -> None:
        """Sleep until rate limit resets."""
        try:
            reset_ts = time.mktime(time.strptime(reset_at, "%Y-%m-%dT%H:%M:%SZ"))
            sleep_time = max(0, reset_ts - time.time()) + 1
            print(f"[WAIT] Rate limit hit. Sleeping for {int(sleep_time)} seconds...")
            time.sleep(sleep_time)
        except ValueError:
            # Fallback if date parsing fails
            print("[WAIT] Rate limit hit. Sleeping for 60 seconds...")
            time.sleep(60)
    
    def should_wait_for_rate_limit(self, rate_limit: RateLimitInfo) -> bool:
        """Check if we're approaching rate limit."""
        return rate_limit.remaining < self._config.rate_limit_buffer
