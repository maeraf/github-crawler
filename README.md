# GitHub Repository Crawler

A high-performance GitHub crawler that fetches repository star counts using the GraphQL API and stores them in PostgreSQL.

## Features

- **Fast**: Batch processing with 1000-repo commits
- **Rate limit aware**: Automatic backoff and retry
- **Efficient storage**: PostgreSQL with upserts (ON CONFLICT)
- **Clean architecture**: Separation of concerns, immutable DTOs
- **Daily updates**: GitHub Actions scheduled workflow

## Architecture

```
+----------------+     +----------------+     +----------------+
|    GitHub      | --> |    Crawler     | --> |   PostgreSQL   |
|  GraphQL API   |     |    (Python)    |     |    Database    |
+----------------+     +----------------+     +----------------+
```

### Components

| Module | Responsibility |
|--------|---------------|
| `config.py` | Immutable configuration from environment |
| `models.py` | SQLAlchemy ORM + DTO anti-corruption layer |
| `github_client.py` | GraphQL client with rate limiting |
| `repository.py` | Database operations (repository pattern) |
| `crawler.py` | Main orchestration logic |

## Database Schema

```sql
CREATE TABLE repositories (
    github_id VARCHAR(255) PRIMARY KEY,  -- Stable GitHub node ID
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    star_count INTEGER NOT NULL,
    crawled_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Why this schema?**
- `github_id` as PK enables O(1) conflict detection for upserts
- `updated_at` tracks freshness for incremental crawls
- Designed for minimal row updates

## Usage

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN=your_token
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=github_crawler
export DB_USER=postgres
export DB_PASSWORD=postgres

# Setup database
python scripts/setup_db.py

# Run crawler
python -m src.crawler

# Export to CSV
python scripts/export_db.py
```

### GitHub Actions

The workflow runs automatically:
- On push to `main`
- Daily at midnight UTC
- Manual trigger via `workflow_dispatch`

No secrets required - uses the default `GITHUB_TOKEN`.

## Schema Evolution

### Adding Issues, PRs, Comments

```sql
-- Separate tables with foreign keys
CREATE TABLE issues (
    id VARCHAR(255) PRIMARY KEY,
    repo_id VARCHAR(255) REFERENCES repositories(github_id),
    number INTEGER NOT NULL,
    title TEXT,
    state VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE issue_comments (
    id VARCHAR(255) PRIMARY KEY,
    issue_id VARCHAR(255) REFERENCES issues(id),
    author VARCHAR(255),
    body TEXT,
    created_at TIMESTAMP
);

CREATE TABLE pull_requests (
    id VARCHAR(255) PRIMARY KEY,
    repo_id VARCHAR(255) REFERENCES repositories(github_id),
    number INTEGER NOT NULL,
    title TEXT,
    state VARCHAR(20),
    merged BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Efficient Updates

When a PR gets new comments:
1. Query by `pr_id` to get existing comment IDs
2. Insert only new comments using `ON CONFLICT DO NOTHING`
3. Only new rows are affected

```sql
INSERT INTO pr_comments (id, pr_id, author, body, created_at)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (id) DO NOTHING;
```

## Scaling

See [SCALING.md](SCALING.md) for details on scaling to 500M repositories.

Key strategies:
- Star range partitioning for parallel workers
- Async I/O with aiohttp + asyncpg
- Token rotation for higher rate limits
- Database sharding with Citus/TimescaleDB

## License

MIT
