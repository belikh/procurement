"""eBay AU Browse API search and application token."""

from __future__ import annotations

import base64
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from procurement.config import settings
from procurement.http import LaneError, request_retry
from procurement.lanes.base import SearchCtx
from procurement.models import AuctionInfo, Location, Offer, Seller, Shipping

# Cached eBay application token: (token, expiry_epoch). Module-level so the
# global in get_ebay_token resolves on FIRST call (a refactor dropped this
# declaration once — NameError killed the whole lane — never remove it).
_EBAY_TOKEN_CACHE: tuple[str, float] | None = None


def missing_ebay() -> str | None:
    if settings.ebay_oauth_token or (settings.ebay_app_id and settings.ebay_cert_id):
        return None
    return "EBAY_APP_ID and EBAY_CERT_ID"


async def get_ebay_token() -> str | None:
    global _EBAY_TOKEN_CACHE  # noqa: PLW0603  # pyright: ignore[reportConstantRedefinition]
    if settings.ebay_oauth_token:
        return settings.ebay_oauth_token
    if not (settings.ebay_app_id and settings.ebay_cert_id):
        return None
    if _EBAY_TOKEN_CACHE and _EBAY_TOKEN_CACHE[1] > time.time():
        return _EBAY_TOKEN_CACHE[0]
    # The endpoint is /identity/v1/oauth2/token; the legacy /oauth/token path returns 404.
    creds = base64.b64encode(f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()).decode()
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client,
            "POST",
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )
    r.raise_for_status()
    tok = r.json().get("access_token")
    exp = r.json().get("expires_in") or 0
    if tok and exp:
        _EBAY_TOKEN_CACHE = (tok, time.time() + int(exp) - 60)  # pyright: ignore[reportConstantRedefinition]
    return tok


def _money(m: Any) -> tuple[float | None, str | None]:
    if not isinstance(m, dict) or not m.get("value"):  # pyright: ignore[reportUnknownMemberType]
        return None, None
    try:
        return float(m["value"]), m.get("currency")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except (TypeError, ValueError):
        return None, None


def _time_left(end_iso: str | None) -> str | None:
    if not end_iso:
        return None
    try:
        delta = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) - datetime.now(UTC)
    except ValueError:
        return None
    if delta.total_seconds() <= 0:
        return None
    d, rem = divmod(int(delta.total_seconds()), 86400)
    h = rem // 3600
    return f"{d}d {h}h" if d else f"{h}h"


def parse_ebay_item(it: dict[str, Any], fallback_title: str = "") -> Offer:
    """Map one Browse API item (search summary or getItem) to an offer.

    price_aud is set only when eBay reports the amount in AUD. Any other
    currency goes to price_native. Shipping cost is set only when eBay states
    one; an absent cost is unknown, which differs from free.
    """
    is_auction = "AUCTION" in (it.get("buyingOptions") or [])
    bid_value, _ = _money(it.get("currentBidPrice"))
    src = it.get("currentBidPrice") if is_auction and bid_value else it.get("price")
    value, currency = _money(src)
    is_aud = currency in (None, "AUD")
    price_aud = value if is_aud else None

    ship_cost: float | None = None
    options = it.get("shippingOptions") or []
    if options:
        cost, cost_currency = _money(options[0].get("shippingCost"))
        if cost is not None and cost_currency in (None, "AUD"):
            ship_cost = cost

    thumbs = it.get("thumbnailImages") or [{}]
    return Offer(
        offer_id=f"ebay_au:{it.get('itemId') or it.get('legacyItemId') or 'unknown'}",
        marketplace="ebay_au",
        title=it.get("title") or fallback_title,
        url=it.get("itemWebUrl") or it.get("itemHref"),
        image=(it.get("image") or {}).get("imageUrl") or thumbs[0].get("imageUrl"),
        price_aud=price_aud,
        price_native=None if is_aud else value,
        currency=currency or "AUD",
        shipping=Shipping(
            cost_aud=ship_cost,
            eta_days=[3, 7],
            method="eBay AU" + (" (auction)" if is_auction else ""),
            delivery="direct" if options else "unknown",
            delivery_basis="eBay lists a shipping option for the buyer's postcode"
            if options
            else None,
        ),
        seller=Seller(shop_name=(it.get("seller") or {}).get("username")),
        auction=AuctionInfo(
            current_bid_aud=price_aud,
            bid_count=it.get("bidCount"),
            end_time=it.get("itemEndDate"),
            time_left=_time_left(it.get("itemEndDate")),
        )
        if is_auction
        else None,
        seller_country=(it.get("itemLocation") or {}).get("country"),
        source_reliability="authoritative",
        raw=it if settings.include_raw else None,
    )


def ebay_headers(token: str, location: Location, *, buyer_context: bool = True) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_AU"}
    if buyer_context:
        # With the buyer's location eBay returns shipping options and costs for that postcode.
        headers["X-EBAY-C-ENDUSERCTX"] = (
            f"contextualLocation=country={location.country},zip={location.postcode}"
        )
    return headers


async def search_ebay_au(ctx: SearchCtx) -> list[Offer]:
    """eBay AU Browse API search.

    ctx.ebay_auctions: AUCTION-format listings only (current bid, bid count, end time).
    ctx.ebay_seller_scope:
      "domestic": items located in Australia (itemLocationCountry:AU).
      "global":   no location filter and no buyer context header. World-wide
                  sellers on the AU marketplace; the pool was about 19x larger
                  in one check (23 to 2707 for "vintage synthesizer").
      "auto":     eBay default, with the AU buyer context header.
    """
    token = await get_ebay_token()
    if not token:
        raise LaneError("missing_key", "EBAY_APP_ID and EBAY_CERT_ID are not set")
    filters: list[str] = []
    if ctx.ebay_auctions:
        filters.append("buyingOptions:{AUCTION}")
    if ctx.ebay_seller_scope == "domestic":
        filters.append("itemLocationCountry:AU")
    params: dict[str, Any] = {"q": ctx.query, "limit": str(ctx.max_results), "sort": "price"}
    if filters:
        params["filter"] = ",".join(filters)
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client,
            "GET",
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers=ebay_headers(
                token, ctx.location, buyer_context=ctx.ebay_seller_scope != "global"
            ),
            params=params,
        )
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"eBay returned HTTP {r.status_code}", {"error": r.text[:300]}
        )
    items = r.json().get("itemSummaries") or []
    return [parse_ebay_item(it, ctx.query) for it in items[: ctx.max_results]]


async def fetch_ebay_item(item_id: str) -> Offer:
    token = await get_ebay_token()
    if not token:
        raise LaneError("missing_key", "EBAY_APP_ID and EBAY_CERT_ID are not set")
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client,
            "GET",
            f"https://api.ebay.com/buy/browse/v1/item/{item_id}",
            headers=ebay_headers(token, Location.default()),
        )
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"eBay returned HTTP {r.status_code}", {"error": r.text[:300]}
        )
    return parse_ebay_item(r.json(), f"ebay_au:{item_id}")
