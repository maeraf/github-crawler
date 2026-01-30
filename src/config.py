"""
Configuration module - immutable settings loaded from environment.
"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Config:
    """Immutable configuration for the crawler."""
    
    # GitHub API
    github_token: str
    github_api_url: str = "https://api.github.com/graphql"
    
    # Crawl settings
    repos_target: int = 100_000
    page_size: int = 100
    max_retries: int = 5
    rate_limit_buffer: int = 50
    
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "github_crawler"
    db_user: str = "postgres"
    db_password: str = "postgres"
    
    # Batch settings
    batch_size: int = 1000  # Commit to DB every N repos
    
    @property
    def database_url(self) -> str:
        """Generate SQLAlchemy database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

def load_config() -> Config:
    """Load configuration from environment variables."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is required")
    
    # Get API URL from environment or use default
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com/graphql")
    
    # Ensure the URL points to the GraphQL endpoint to avoid 404 errors
    if not api_url.endswith("/graphql"):
        api_url = api_url.rstrip("/") + "/graphql"
    
    return Config(
        github_token=token,
        github_api_url=api_url,
        repos_target=int(os.environ.get("REPOS_TARGET", "100000")),
        page_size=int(os.environ.get("PAGE_SIZE", "100")),
        max_retries=int(os.environ.get("MAX_RETRIES", "5")),
        rate_limit_buffer=int(os.environ.get("RATE_LIMIT_BUFFER", "50")),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_name=os.environ.get("DB_NAME", "github_crawler"),
        db_user=os.environ.get("DB_USER", "postgres"),
        db_password=os.environ.get("DB_PASSWORD", "postgres"),
        batch_size=int(os.environ.get("BATCH_SIZE", "1000")),
    )
