"""Facebook Marketplace via SociaVault."""

from __future__ import annotations

from typing import Any

import httpx

from procurement.config import settings
from procurement.http import LaneError, request_retry
from procurement.lanes.base import SearchCtx
from procurement.models import Offer, Seller, Shipping


def missing_facebook() -> str | None:
    return None if settings.sociavault_api_key else "SOCIAVAULT_API_KEY"


def _listings(data: dict[str, Any]) -> list[dict[str, Any]]:
    """SociaVault returns listings as a list, or as a dict keyed "0", "1", ..."""
    listings: Any = data.get("listings") or (data.get("data") or {}).get("listings") or []
    if isinstance(listings, dict):
        keys = sorted(listings, key=lambda k: int(k) if str(k).isdigit() else 0)  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
        return [listings[k] for k in keys]  # pyright: ignore[reportUnknownVariableType]
    return listings if isinstance(listings, list) else []  # pyright: ignore[reportUnknownVariableType]


def parse_facebook(data: dict[str, Any], query: str, max_results: int) -> list[Offer]:
    offers: list[Offer] = []
    for it in _listings(data)[:max_results]:
        price = it.get("price") or {}
        amount = price.get("amount") if isinstance(price, dict) else it.get("price_aud")  # pyright: ignore[reportUnknownMemberType]
        try:
            aud = float(amount) if amount is not None else None  # pyright: ignore[reportUnknownArgumentType]
        except (TypeError, ValueError):
            aud = None
        photo = it.get("primary_photo")
        delivery_types = it.get("delivery_types")
        offers.append(
            Offer(
                offer_id=f"facebook:{it.get('id') or it.get('listing_id') or 'unknown'}",
                marketplace="facebook",
                title=it.get("title") or query,
                url=it.get("url") or it.get("listing_url"),
                image=(photo.get("url") if isinstance(photo, dict) else photo) or it.get("image"),  # pyright: ignore[reportUnknownMemberType]
                price_aud=aud,
                shipping=Shipping(
                    eta_days=[1, 4],
                    method=", ".join(delivery_types)
                    if delivery_types
                    else "Local pickup / shipping",
                ),
                seller=Seller(shop_name=it.get("seller_name") or str(it.get("seller_id") or "")),
                source_reliability="best_effort",
                raw=it if settings.include_raw else None,
            )
        )
    return offers


async def search_facebook(ctx: SearchCtx) -> list[Offer]:
    if not settings.sociavault_api_key:
        raise LaneError("missing_key", "SOCIAVAULT_API_KEY is not set")
    async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
        r = await request_retry(
            client,
            "GET",
            "https://api.sociavault.com/v1/scrape/facebook-marketplace/search",
            headers={"x-api-key": settings.sociavault_api_key},
            params={
                "query": ctx.query,
                "lat": ctx.location.lat,
                "lng": ctx.location.lng,
                "limit": ctx.max_results,
            },
        )
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"SociaVault returned HTTP {r.status_code}", {"error": r.text[:300]}
        )
    return parse_facebook(r.json(), ctx.query, ctx.max_results)
