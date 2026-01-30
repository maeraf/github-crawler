# Scaling to 500 Million Repositories

This document outlines the changes required to scale from 100K to 500M repositories.

## Current Limitations

1. **Single-threaded** - One cursor, sequential processing
2. **Single token** - 5,000 requests/hour rate limit
3. **In-memory buffering** - Limited by RAM
4. **Single database** - PostgreSQL on one node

---

## 1. Parallel Crawling

### Star Range Partitioning
Split the search space by star count ranges:
```
Worker 1: stars:0..10
Worker 2: stars:11..100
Worker 3: stars:101..1000
Worker 4: stars:1001..10000
Worker 5: stars:>10000
```

Each worker operates independently with its own cursor.

### Implementation
```python
# Define partitions
STAR_RANGES = [
    (0, 10),
    (11, 100),
    (101, 1000),
    (1001, 10000),
    (10001, None),  # No upper bound
]

# Run workers in parallel
async def parallel_crawl():
    tasks = [
        crawl_range(f"stars:{low}..{high if high else ''}")
        for low, high in STAR_RANGES
    ]
    await asyncio.gather(*tasks)
```

---

## 2. Async I/O

Replace `requests` with `aiohttp` for concurrent API calls:

```python
import aiohttp
import asyncpg

async def fetch_page(session, cursor):
    async with session.post(API_URL, json=payload) as resp:
        return await resp.json()

async def batch_insert(pool, repos):
    async with pool.acquire() as conn:
        await conn.executemany(INSERT_QUERY, repos)
```

### Benefits
- 10-100x throughput improvement
- Better utilization of rate limits
- Non-blocking database writes

---

## 3. Token Rotation

Use multiple GitHub tokens to multiply rate limits:

```python
class TokenRotator:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.current = 0
    
    def get_token(self) -> str:
        token = self.tokens[self.current]
        self.current = (self.current + 1) % len(self.tokens)
        return token
```

With 10 tokens: 50,000 requests/hour → ~50M repos/day

---

## 4. Database Scaling

### Option A: Sharding
Partition by `github_id` hash:

```sql
CREATE TABLE repositories (
    github_id VARCHAR(255),
    ...
) PARTITION BY HASH (github_id);

CREATE TABLE repositories_0 PARTITION OF repositories
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);
-- ... repeat for shards 1, 2, 3
```

### Option B: TimescaleDB
For time-series analysis of star history:

```sql
SELECT create_hypertable('repository_history', 'crawled_at');
```

### Option C: Distributed PostgreSQL
- **Citus** for horizontal scaling
- **CockroachDB** for global distribution

---

## 5. Architecture Changes

### Message Queue
Decouple crawling from storage:

```
GitHub API → Crawler → Kafka → Consumer → PostgreSQL
```

Benefits:
- Backpressure handling
- Retry capabilities
- Multiple consumers

### Checkpointing
Save cursor state for resumability:

```python
class CrawlState:
    def save(self, partition: str, cursor: str):
        redis.set(f"cursor:{partition}", cursor)
    
    def load(self, partition: str) -> str:
        return redis.get(f"cursor:{partition}")
```

---

## 6. Infrastructure

| Component | 100K Scale | 500M Scale |
|-----------|-----------|------------|
| Workers | 1 | 20+ distributed |
| Tokens | 1 | 10-50 |
| Database | Single node | Sharded cluster |
| Storage | ~10 MB | ~50 GB |
| Crawl time | ~20 min | ~1 week |

---

## 7. Monitoring

Essential metrics at scale:
- Requests/second per worker
- Rate limit consumption
- Database write latency
- Cursor progress per partition
- Error rates

Tools: Prometheus, Grafana, Sentry

---

## Summary

| Change | Impact |
|--------|--------|
| Star range partitioning | 5x parallelism |
| Async I/O | 10-100x throughput |
| Token rotation | Nx rate limits |
| Database sharding | Horizontal scale |
| Message queue | Reliability |
| Checkpointing | Resumability |
