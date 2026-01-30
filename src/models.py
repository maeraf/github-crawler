"""
Database models - SQLAlchemy ORM definitions.
Anti-corruption layer between GitHub API and our domain.
"""
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Index, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Repository(Base):
    """
    Repository model - stores GitHub repository metadata.
    
    Schema designed for:
    - Efficient upserts via github_id primary key
    - Incremental updates using updated_at timestamp
    - Future expansion with additional columns
    """
    __tablename__ = "repositories"
    
    # GitHub node ID - stable unique identifier
    github_id = Column(String(255), primary_key=True)
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    star_count = Column(Integer, nullable=False)
    
    # Timestamps for tracking freshness
    crawled_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes for common queries
    __table_args__ = (
        Index("idx_owner_name", "owner", "name"),
        Index("idx_star_count", "star_count"),
        Index("idx_updated_at", "updated_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Repository {self.owner}/{self.name} ⭐{self.star_count}>"


@dataclass(frozen=True)
class RepositoryDTO:
    """
    Immutable data transfer object for repository data.
    Used to transfer data between layers without coupling to ORM.
    """
    github_id: str
    owner: str
    name: str
    star_count: int
    
    @classmethod
    def from_github_response(cls, node: dict) -> "RepositoryDTO":
        """Create DTO from GitHub GraphQL response node."""
        return cls(
            github_id=node["id"],
            owner=node["owner"]["login"],
            name=node["name"],
            star_count=node["stargazerCount"],
        )


def create_db_engine(database_url: str):
    """Create SQLAlchemy engine."""
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine):
    """Create session factory."""
    return sessionmaker(bind=engine)


def create_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)
