"""
Repository pattern for database operations.
Provides clean abstraction over SQLAlchemy.
"""
from datetime import datetime
from typing import List, Sequence

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Repository, RepositoryDTO


class RepositoryStore:
    """
    Repository pattern for database operations.
    
    Implements:
    - Batch upserts using PostgreSQL ON CONFLICT
    - Minimal row updates (only changed data)
    - Clean separation from ORM details
    """
    
    def __init__(self, session: Session):
        self._session = session
    
    def upsert_batch(self, repositories: Sequence[RepositoryDTO]) -> int:
        """
        Upsert a batch of repositories efficiently.
        
        Uses PostgreSQL's INSERT ... ON CONFLICT DO UPDATE
        to minimize affected rows - only updates if data changed.
        
        Args:
            repositories: Sequence of repository DTOs to upsert
            
        Returns:
            Number of repositories processed
        """
        if not repositories:
            return 0
        
        # Prepare values for bulk insert
        values = [
            {
                "github_id": repo.github_id,
                "owner": repo.owner,
                "name": repo.name,
                "star_count": repo.star_count,
                "crawled_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            for repo in repositories
        ]
        
        # PostgreSQL upsert with ON CONFLICT
        stmt = insert(Repository).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["github_id"],
            set_={
                "owner": stmt.excluded.owner,
                "name": stmt.excluded.name,
                "star_count": stmt.excluded.star_count,
                "updated_at": datetime.utcnow(),
            }
        )
        
        self._session.execute(stmt)
        self._session.commit()
        
        return len(repositories)
    
    def get_count(self) -> int:
        """Get total count of repositories in database."""
        result = self._session.execute(
            text("SELECT COUNT(*) FROM repositories")
        )
        return result.scalar() or 0
    
    def export_to_csv(self, filepath: str) -> int:
        """
        Export all repositories to CSV file.
        
        Args:
            filepath: Path to output CSV file
            
        Returns:
            Number of rows exported
        """
        result = self._session.execute(
            text("SELECT github_id, owner, name, star_count, crawled_at, updated_at FROM repositories ORDER BY star_count DESC")
        )
        
        rows = result.fetchall()
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("github_id,owner,name,star_count,crawled_at,updated_at\n")
            for row in rows:
                # Escape commas in name/owner if present
                owner = str(row[1]).replace('"', '""')
                name = str(row[2]).replace('"', '""')
                f.write(f'{row[0]},"{owner}","{name}",{row[3]},{row[4]},{row[5]}\n')
        
        return len(rows)
