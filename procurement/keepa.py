"""Keepa price history for Amazon offers.

Shapes from Keepa's official Java client (keepacom/api_backend):
  - Prices are integers in the smallest currency unit; -1 means no offer.
  - stats.current, stats.avg30, stats.avg90 are int arrays indexed by price type; 0 is Amazon.
  - stats.min and stats.max hold, per price type, null or [keepa_minutes, price].
  - unix seconds = (keepa_minutes + 21564000) * 60.
Not yet run against the live API: no Keepa key was available.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from procurement.config import settings
from procurement.http import LaneError, request_retry
from procurement.models import Offer

AMAZON = 0  # price type index
KEEPA_EPOCH_MINUTES = 21564000
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
MAX_ASINS = 20


def keepa_money(value: Any) -> float | None:
    """Convert a Keepa integer price to dollars. None for missing or negative values."""
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        return None
    return round(value / 100, 2)


def keepa_time_iso(minutes: Any) -> str | None:
    if not isinstance(minutes, int) or minutes < 0:
        return None
    return datetime.fromtimestamp((minutes + KEEPA_EPOCH_MINUTES) * 60, tz=UTC).isoformat()


def _amazon(series: Any) -> Any:
    return series[AMAZON] if isinstance(series, list) and len(series) > AMAZON else None  # pyright: ignore[reportUnknownVariableType]


def _extreme(series: Any) -> float | None:
    pair = _amazon(series)
    return keepa_money(pair[1]) if isinstance(pair, list) and len(pair) == 2 else None  # pyright: ignore[reportUnknownArgumentType]


def keepa_summary(product: dict[str, Any]) -> dict[str, Any] | None:
    """Summarise one Keepa product's Amazon price statistics, or None without stats."""
    stats = product.get("stats")
    if not isinstance(stats, dict):
        return None
    return {
        "source": "keepa",
        "domain_id": product.get("domainId"),
        "current_aud": keepa_money(_amazon(stats.get("current"))),  # pyright: ignore[reportUnknownMemberType]
        "avg_30d_aud": keepa_money(_amazon(stats.get("avg30"))),  # pyright: ignore[reportUnknownMemberType]
        "avg_90d_aud": keepa_money(_amazon(stats.get("avg90"))),  # pyright: ignore[reportUnknownMemberType]
        "min_aud": _extreme(stats.get("min")),  # pyright: ignore[reportUnknownMemberType]
        "max_aud": _extreme(stats.get("max")),  # pyright: ignore[reportUnknownMemberType]
    }


def keepa_series(product: dict[str, Any], days: int) -> list[dict[str, Any]]:
    """Amazon price points from csv[0], which alternates keepa_minutes and price."""
    csv = product.get("csv")
    flat = _amazon(csv)
    if not isinstance(flat, list):
        return []
    cutoff = datetime.now(UTC).timestamp() - days * 86400
    points: list[dict[str, Any]] = []
    for minutes, price in zip(flat[0::2], flat[1::2], strict=False):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        value = keepa_money(price)
        if value is None or not isinstance(minutes, int):
            continue
        if (minutes + KEEPA_EPOCH_MINUTES) * 60 >= cutoff:
            points.append({"t": keepa_time_iso(minutes), "price_aud": value})
    return points


def keepa_missing() -> str | None:
    if not settings.keepa_api_key:
        return "KEEPA_API_KEY"
    if settings.keepa_domain is None:
        return "KEEPA_DOMAIN"
    return None


async def keepa_products(
    asins: list[str], *, days: int = 90, history: bool = False
) -> dict[str, dict[str, Any]]:
    """Fetch products by ASIN. Raises LaneError when Keepa is unconfigured or fails."""
    missing = keepa_missing()
    if missing:
        raise LaneError("missing_key", f"{missing} is not set")
    params = {
        "key": settings.keepa_api_key,
        "domain": str(settings.keepa_domain),
        "asin": ",".join(asins[:MAX_ASINS]),
        "stats": str(days),
        "history": "1" if history else "0",
    }
    async with httpx.AsyncClient(timeout=settings.default_timeout_s + 2) as client:
        r = await request_retry(client, "GET", "https://api.keepa.com/product", params=params)
    if r.status_code != 200:
        raise LaneError(
            "upstream_error", f"Keepa returned HTTP {r.status_code}", {"error": r.text[:200]}
        )
    products = r.json().get("products") or []
    out: dict[str, dict[str, Any]] = {}
    for p in products:
        # A product from another locale would carry another currency; drop it.
        if p.get("asin") and p.get("domainId") in (None, settings.keepa_domain):
            out[p["asin"]] = p
    return out


def offer_asin(offer_id: str) -> str | None:
    asin = offer_id.split(":", 1)[-1].strip().upper()
    return asin if ASIN_RE.match(asin) else None


async def enrich_with_keepa(offers: list[Offer]) -> list[Offer]:
    """Attach a price-history summary to amazon_au offers. One batched call.

    Does nothing when Keepa is unconfigured. On an upstream failure the offers
    pass through without history.
    """
    if keepa_missing():
        return offers
    targets = {
        asin: o for o in offers if o.marketplace == "amazon_au" and (asin := offer_asin(o.offer_id))
    }
    if not targets:
        return offers
    try:
        products = await keepa_products(list(targets))
    except (LaneError, httpx.HTTPError):
        return offers
    for asin, offer in targets.items():
        product = products.get(asin)
        if product:
            offer.price_history = keepa_summary(product)
    return offers
