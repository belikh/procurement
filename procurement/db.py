"""Optional Postgres cache and search log. Stateless when DATABASE_URL is unset."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from typing import Any

from procurement.config import settings
from procurement.models import Offer

# Bump when the Offer schema or ranking changes so older cached rows are not served.
CACHE_VERSION = 2

pool: Any | None = None  # asyncpg.Pool | None
enabled: bool = False
error: str | None = None

DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.search_cache (
  cache_key TEXT PRIMARY KEY,
  query TEXT NOT NULL,
  marketplaces TEXT[],
  sort TEXT,
  qty INT,
  ship_to TEXT,
  offers JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_cache_expires ON {schema}.search_cache (expires_at);
CREATE TABLE IF NOT EXISTS {schema}.search_log (
  id BIGSERIAL PRIMARY KEY,
  query TEXT NOT NULL,
  marketplaces TEXT[],
  sort TEXT,
  qty INT,
  ship_to TEXT,
  result_count INT,
  elapsed_ms INT,
  created_at TIMESTAMPTZ DEFAULT now()
);
"""


def make_cache_key(
    query: str,
    marketplaces: list[str],
    sort: str,
    qty: int,
    ship_to: str,
    max_results: int,
    ebay_auctions: bool = False,
    ebay_seller_scope: str = "domestic",
) -> str:
    raw = json.dumps(
        {
            "v": CACHE_VERSION,
            "q": query.strip().lower(),
            "mps": sorted(marketplaces),
            "sort": sort,
            "qty": qty,
            "ship_to": ship_to,
            "max": max_results,
            "ebay_auction": ebay_auctions,
            "ebay_scope": ebay_seller_scope,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def init_db() -> None:
    global pool, enabled, error
    if not settings.database_url:
        enabled = False
        return
    try:
        import asyncpg  # type: ignore[import-untyped]

        pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5, timeout=5)
        assert pool is not None
        ddl = DDL.format(schema=settings.pg_schema)
        async with pool.acquire() as conn:
            await conn.execute(ddl)
        enabled = True
        error = None
    except Exception as e:
        enabled = False
        error = str(e)


async def close_db() -> None:
    global pool
    if pool is not None:
        with contextlib.suppress(Exception):
            await pool.close()
        pool = None


async def get_cached(cache_key: str) -> list[Offer] | None:
    if not enabled or pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT offers FROM {settings.pg_schema}.search_cache WHERE cache_key=$1 AND expires_at > now()",
                cache_key,
            )
            if not row:
                return None
            data = row["offers"]
            if isinstance(data, str):
                data = json.loads(data)
            return [Offer.model_validate(o) for o in data]
    except Exception:
        return None


async def set_cached(
    cache_key: str,
    query: str,
    marketplaces: list[str],
    sort: str,
    qty: int,
    ship_to: str,
    offers: list[Offer],
) -> None:
    if not enabled or pool is None:
        return
    try:
        payload = json.dumps([o.model_dump() for o in offers])
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {settings.pg_schema}.search_cache (cache_key, query, marketplaces, sort, qty, ship_to, offers, expires_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb, now() + make_interval(secs => $8))
                ON CONFLICT (cache_key) DO UPDATE SET offers=EXCLUDED.offers, expires_at=EXCLUDED.expires_at, created_at=now()
                """,
                cache_key,
                query,
                marketplaces,
                sort,
                qty,
                ship_to,
                payload,
                settings.cache_ttl_s,
            )
    except Exception:
        # Never block a search on cache failure — but leave a breadcrumb.
        logging.getLogger("procurement").warning("search_cache put failed", exc_info=True)


async def log_search(
    query: str,
    marketplaces: list[str],
    sort: str,
    qty: int,
    ship_to: str,
    result_count: int,
    elapsed_ms: int,
) -> None:
    if not enabled or pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {settings.pg_schema}.search_log (query, marketplaces, sort, qty, ship_to, result_count, elapsed_ms) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                query,
                marketplaces,
                sort,
                qty,
                ship_to,
                result_count,
                elapsed_ms,
            )
    except Exception:
        pass


def _like(text: str) -> str:
    """Escape LIKE wildcards so the text matches literally."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def recent_searches(
    query_contains: str | None, since_hours: int, limit: int
) -> list[dict[str, Any]]:
    """Rows of the search log, newest first. Empty when the database is off."""
    if not enabled or pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, created_at, query, marketplaces, sort, qty, ship_to, result_count, elapsed_ms
            FROM {settings.pg_schema}.search_log
            WHERE created_at > now() - make_interval(hours => $1)
              AND ($2::text IS NULL OR query ILIKE $2)
            ORDER BY created_at DESC LIMIT $3
            """,
            since_hours,
            _like(query_contains) if query_contains else None,
            limit,
        )
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]


async def cached_searches(
    query_contains: str | None, since_hours: int, limit: int, include_offers: bool
) -> list[dict[str, Any]]:
    """Unexpired rows of the search cache, newest first. Empty when the database is off."""
    if not enabled or pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT cache_key, query, marketplaces, sort, created_at,
                   EXTRACT(EPOCH FROM (expires_at - now()))::float AS expires_in_s,
                   jsonb_array_length(offers) AS offer_count, offers
            FROM {settings.pg_schema}.search_cache
            WHERE expires_at > now() AND created_at > now() - make_interval(hours => $1)
              AND ($2::text IS NULL OR query ILIKE $2)
            ORDER BY created_at DESC LIMIT $3
            """,
            since_hours,
            _like(query_contains) if query_contains else None,
            limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        row = {
            k: r[k]
            for k in ("cache_key", "query", "marketplaces", "sort", "expires_in_s", "offer_count")
        }
        row["created_at"] = r["created_at"].isoformat()
        if include_offers:
            offers = r["offers"]
            row["offers"] = json.loads(offers) if isinstance(offers, str) else offers
        out.append(row)
    return out


async def find_offer(offer_id: str) -> Offer | None:
    """Look an offer up in unexpired cached searches."""
    if not enabled or pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT o AS offer FROM {settings.pg_schema}.search_cache c,
                       jsonb_array_elements(c.offers) AS o
                WHERE c.expires_at > now() AND o->>'offer_id' = $1
                ORDER BY c.created_at DESC LIMIT 1
                """,
                offer_id,
            )
    except Exception:
        return None
    if not row:
        return None
    data = row["offer"]
    return Offer.model_validate(json.loads(data) if isinstance(data, str) else data)
