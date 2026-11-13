"""HTTP helpers shared by the lanes: retry, Apify actor runs, error type."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from procurement.config import settings
from procurement.models import DiagCode

_PRODUCT_ID_KEYS = (
    "itemId",
    "skuId",
    "asin",
    "id",
    "sku",
    "barcode",
    "productId",
    "url",
    "productUrl",
)
_RETRY_STATUS = frozenset({429, 502, 503, 504})
_QUOTA_WORDS = ("free_tier", "quota", "exhausted", "limit exceeded", "payment", "billing")


class LaneError(Exception):
    """A lane could not return offers. The orchestrator turns it into one diagnostic."""

    def __init__(self, code: DiagCode, detail: str, raw: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.code: DiagCode = code
        self.detail = detail
        self.raw = raw


def split_envelopes(items: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Separate Apify actor error envelopes from real product items.

    Quota/billing notices arrive as {"error": ..., "message": ...} dicts
    with no product id (observed live: free_tier_exhausted from
    zen-studio/taobao-search-scraper after its 10 free runs). Returns
    (clean_items, first_error_message). Callers: no clean items + a message
    → one honest diagnostic offer; envelopes mixed with real items → skip.
    """
    if not isinstance(items, list):
        return [], None
    clean: list[dict[str, Any]] = []
    first_err: str | None = None
    for it in items:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(it, dict) and "error" in it and not any(it.get(k) for k in _PRODUCT_ID_KEYS):  # pyright: ignore[reportUnknownMemberType]
            if first_err is None:
                first_err = str(it.get("message") or it.get("error"))[:200]  # pyright: ignore[reportUnknownMemberType]
            continue
        clean.append(it)  # pyright: ignore[reportUnknownArgumentType]
    return clean, first_err


async def request_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff_s: float = 0.5,
    **kwargs: Any,
) -> httpx.Response:
    """Send a request, retrying connect errors and 429/502/503/504.

    Use it for calls that are safe to repeat. Apify run-sync POSTs start a paid
    actor run, so they go through apify_run_sync, which sends once.
    """
    attempt = 0
    while True:
        try:
            response = await client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            if attempt >= retries:
                raise
        else:
            if response.status_code not in _RETRY_STATUS or attempt >= retries:
                return response
        attempt += 1
        await asyncio.sleep(backoff_s * 2 ** (attempt - 1))


def actor_path(actor: str) -> str:
    """Apify's v2 API resolves actor names only in the `user~actor` form."""
    return actor.replace("/", "~", 1)


async def apify_run_sync(
    actor: str, run_input: dict[str, Any], *, timeout_s: float
) -> list[dict[str, Any]]:
    """Run an Apify actor and return its dataset items. Sends once.

    Raises LaneError for a missing token, a non-2xx reply, or a reply that holds
    only error envelopes.
    """
    if not settings.apify_token:
        raise LaneError("missing_key", "APIFY_TOKEN is not set")
    wait = max(5, int(timeout_s))
    async with httpx.AsyncClient(timeout=wait + 5) as client:
        r = await client.post(
            f"https://api.apify.com/v2/acts/{actor_path(actor)}/run-sync-get-dataset-items",
            params={"token": settings.apify_token, "timeout": wait},
            json=run_input,
        )
    if r.status_code not in (200, 201):
        raise LaneError(
            "upstream_error",
            f"actor {actor} returned HTTP {r.status_code}",
            {"error": r.text[:300]},
        )
    data = r.json()
    rows: Any = data if isinstance(data, list) else data.get("items", [])
    items, actor_err = split_envelopes(rows)
    if not items and actor_err:
        # The envelope's error field names the cause; its message is prose.
        text = " ".join(
            f"{row.get('error')} {row.get('message')}" for row in rows if isinstance(row, dict)
        ).lower()
        code: DiagCode = "quota" if any(w in text for w in _QUOTA_WORDS) else "upstream_error"
        raise LaneError(code, f"actor {actor}: {actor_err}", {"error": actor_err})
    return items
