"""Amazon AU search via a hosted Apify actor.

The actor scrapes a full search page and takes about 40 to 60 s per run.
Item shape seen live: price{value,currency}, imageUrl, stars, reviewsCount, asin.
"""

from __future__ import annotations

from typing import Any

from procurement.common import query_relevant
from procurement.config import settings
from procurement.http import apify_run_sync
from procurement.lanes.base import SearchCtx
from procurement.models import Offer, Seller, Shipping

ACTOR_WAIT_S = 70


def parse_amazon(items: list[dict[str, Any]], query: str, max_results: int) -> list[Offer]:
    offers: list[Offer] = []
    for it in items[:max_results]:
        # Amazon pads generic searches with sponsored items that do not match.
        if not query_relevant(query, it.get("title")):
            continue
        price = it.get("price") or {}
        try:
            value = round(float(price["value"]), 2) if price.get("value") else None
        except (TypeError, ValueError, KeyError):
            value = None
        asin = it.get("asin")
        offers.append(
            Offer(
                offer_id=f"amazon_au:{asin}" if asin else f"amazon_au:{it.get('url') or 'unknown'}",
                marketplace="amazon_au",
                title=it.get("title") or query,
                url=f"https://www.amazon.com.au/dp/{asin}" if asin else it.get("url"),
                image=it.get("imageUrl"),
                price_aud=value,
                shipping=Shipping(eta_days=[2, 7], method="Amazon AU"),
                seller=Seller(shop_name="Amazon AU", rating=it.get("stars")),
                source_reliability="best_effort",
                raw={"reviews": it.get("reviewsCount"), "sponsored": it.get("isSponsored")}
                if settings.include_raw
                else None,
            )
        )
    return offers


async def search_amazon_au(ctx: SearchCtx) -> list[Offer]:
    run_input = {
        "categoryUrls": [{"url": f"https://www.amazon.com.au/s?k={ctx.query.replace(' ', '+')}"}],
        "maxItemsPerStartUrl": ctx.max_results,
        "maxSearchPagesPerStartUrl": 1,
        "scrapeProductDetails": False,
    }
    items = await apify_run_sync(
        settings.amazon_apify_actor, run_input, timeout_s=ctx.wait_s(ACTOR_WAIT_S)
    )
    return parse_amazon(items, ctx.query, ctx.max_results)
