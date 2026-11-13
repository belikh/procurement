"""eBay AU sold-price comps via a hosted Apify actor.

These are what items sold for. They are not buyable, so each is kind="comp".
"""

from __future__ import annotations

from typing import Any

from procurement.config import settings
from procurement.http import apify_run_sync
from procurement.lanes.base import SearchCtx
from procurement.models import Offer, Seller, Shipping

ACTOR_WAIT_S = 60
DEFAULT_DAYS = 30


def parse_ebay_sold(items: list[dict[str, Any]], query: str, max_results: int) -> list[Offer]:
    offers: list[Offer] = []
    for it in items[:max_results]:
        try:
            sold = round(float(it.get("soldPrice") or 0), 2) or None
        except (TypeError, ValueError):
            sold = None
        try:
            rating = (
                round(float(it["sellerPositivePercent"]), 1)
                if it.get("sellerPositivePercent")
                else None
            )
        except (TypeError, ValueError):
            rating = None
        offers.append(
            Offer(
                offer_id=f"ebay_sold:{it.get('itemId') or 'unknown'}",
                marketplace="ebay_sold",
                kind="comp",
                title=it.get("title") or query,
                url=it.get("url"),
                image=it.get("thumbnailUrl"),
                price_aud=sold,
                currency=it.get("soldCurrency") or "AUD",
                stock=0,
                shipping=Shipping(eta_days=[0, 0], method="Sold comp: listing ended"),
                seller=Seller(shop_name=it.get("sellerUsername"), rating=rating),
                price_history={
                    "source": "ebay_sold_comps",
                    "sold_price": sold,
                    "total_with_shipping": it.get("totalPrice"),
                    "ended_at": it.get("endedAt"),
                    "condition": it.get("condition"),
                    "listing_type": it.get("listingType"),
                },
                source_reliability="aggregator",
                raw=it if settings.include_raw else None,
            )
        )
    return offers


async def search_ebay_sold(ctx: SearchCtx) -> list[Offer]:
    run_input = {
        "keywords": [ctx.query],
        "ebaySite": "ebay.com.au",
        "daysToScrape": DEFAULT_DAYS,
        "count": ctx.max_results,
    }
    items = await apify_run_sync(
        settings.ebay_sold_apify_actor, run_input, timeout_s=ctx.wait_s(ACTOR_WAIT_S)
    )
    return parse_ebay_sold(items, ctx.query, ctx.max_results)
