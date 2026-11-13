"""TMAPI: 1688 keyword search and item detail for the China marketplaces.

Endpoint map from the tmapi.top docs (read 2026-11-13, not yet run with a key):
  1688:         GET /1688/search/items?keyword=  and  GET /1688/item_detail?item_id=
  taobao/tmall: GET /taobao/item_detail?item_id=   (no keyword search)
  jd:           GET /jd/item_detail?item_id=       (no keyword search)
  pdd:          GET /pdd/item_detail?item_id=      (no keyword search)
/alibaba/... is Alibaba.com (international, USD) and is not used here.

The docs pass the key as an `apikey` header. Earlier code passed it as an
`apiToken` query parameter. Both are sent until one is confirmed with a key.
"""

from __future__ import annotations

from typing import Any

import httpx

from procurement.common import cny_to_aud
from procurement.config import settings
from procurement.http import LaneError, request_retry
from procurement.models import Offer, Seller

BASE = "https://api.tmapi.top"
_DETAIL_PATH = {
    "taobao": "taobao/item_detail",
    "tmall": "taobao/item_detail",
    "1688": "1688/item_detail",
    "pdd": "pdd/item_detail",
    "jd": "jd/item_detail",
}
DETAIL_MARKETPLACES = frozenset(_DETAIL_PATH)


def _auth() -> tuple[dict[str, str], dict[str, str]]:
    """Return (headers, query params) carrying the key."""
    if not settings.tmapi_token:
        raise LaneError("missing_key", "TMAPI_TOKEN is not set")
    return {"apikey": settings.tmapi_token}, {"apiToken": settings.tmapi_token}


async def fetch_tmapi(item_id: str, marketplace: str) -> dict[str, Any]:
    """Item detail by id. Raises LaneError when the call cannot return a detail."""
    headers, auth = _auth()
    path = _DETAIL_PATH.get(marketplace)
    if not path:
        raise LaneError("unsupported", f"TMAPI has no detail endpoint for {marketplace}")
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client, "GET", f"{BASE}/{path}", headers=headers, params={**auth, "item_id": item_id}
        )
    if r.status_code == 401:
        raise LaneError(
            "unsubscribed",
            "TMAPI error 4013: API not subscribed; subscribe at console.tmapi.io, APIs List",
        )
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"TMAPI returned HTTP {r.status_code}", {"error": r.text[:200]}
        )
    return r.json()


def parse_1688_search(data: dict[str, Any], query: str, max_results: int) -> list[Offer]:
    body = data.get("data") or {}
    items = body.get("products") or body.get("items") or []
    offers: list[Offer] = []
    for it in items[:max_results]:
        price_cny = None
        for k in ("price", "min_price", "price_range_min"):
            v = it.get(k)
            if v is None:
                continue
            try:
                price_cny = round(float(str(v).replace("¥", "").strip() or 0), 2) or None
            except ValueError:
                continue
            if price_cny:
                break
        offers.append(
            Offer(
                offer_id=f"1688:{it.get('product_id') or it.get('id') or 'unknown'}",
                marketplace="1688",
                title=str(it.get("title") or it.get("subject") or it.get("product_name") or query),
                url=it.get("detail_url") or it.get("product_url") or it.get("url"),
                image=it.get("image") or it.get("pic") or (it.get("images") or [None])[0],
                price_cny=price_cny,
                price_aud=cny_to_aud(price_cny),
                moq=it.get("min_order") or it.get("moq"),
                seller=Seller(shop_name=it.get("company_name") or it.get("supplier_name")),
                source_reliability="aggregator",
                raw=it if settings.include_raw else None,
            )
        )
    return offers


async def search_1688_tmapi(query: str, max_results: int) -> list[Offer]:
    headers, auth = _auth()
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client,
            "GET",
            f"{BASE}/1688/search/items",
            headers=headers,
            params={
                **auth,
                "keyword": query,
                "page": 1,
                "page_size": min(max_results, 20),
                "sort": "default",
            },
        )
    if r.status_code == 401:
        raise LaneError(
            "unsubscribed",
            "TMAPI error 4013: API not subscribed; subscribe at console.tmapi.io, APIs List",
        )
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"TMAPI returned HTTP {r.status_code}", {"error": r.text[:200]}
        )
    return parse_1688_search(r.json(), query, max_results)
