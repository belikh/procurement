"""Woolworths, Coles and Aldi search via dromb Apify actors.

Actor output: price (regular), discount_price (special), unit_price + unit,
barcode, stock_status, brand. price_aud carries the price paid today;
regular_price_aud keeps the pre-special price.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from procurement.common import float_or_none, query_relevant
from procurement.config import settings
from procurement.http import apify_run_sync
from procurement.lanes.base import SearchCtx
from procurement.models import Offer, Seller, Shipping

ACTOR_WAIT_S = 40


def parse_grocery(
    items: list[dict[str, Any]], marketplace: str, query: str, max_results: int
) -> list[Offer]:
    offers: list[Offer] = []
    for it in items:
        attributes = it.get("attributes")
        categories: list[str] = (
            attributes.get("categories", []) if isinstance(attributes, dict) else []
        )  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        # Grocery catalogues fuzzy-match: 'milk' at Aldi returns oil and lollipops.
        if not query_relevant(query, it.get("name"), it.get("brand"), *categories):
            continue
        regular = float_or_none(it.get("price"))
        special = float_or_none(it.get("discount_price"))
        on_special = bool(special and regular and special < regular)
        unit_attrs = it.get("unit_price_attributes")
        offers.append(
            Offer(
                offer_id=f"{marketplace}:{it.get('id') or it.get('sku') or it.get('barcode') or 'unknown'}",
                marketplace=marketplace,
                title=it.get("name") or query,
                url=it.get("source_url"),
                image=it.get("image"),
                price_aud=special if on_special else regular,
                regular_price_aud=regular if on_special else None,
                unit_price_aud=float_or_none(it.get("unit_price")),
                unit=it.get("unit")
                or (unit_attrs.get("unit") if isinstance(unit_attrs, dict) else None),  # pyright: ignore[reportUnknownMemberType]
                stock=1
                if it.get("is_available") in (True, "true")
                else (0 if it.get("stock_status") == "out_of_stock" else None),
                shipping=Shipping(eta_days=[1, 5], method="Grocery pickup/delivery"),
                seller=Seller(shop_name=(it.get("brand") or marketplace.title())),
                source_reliability="best_effort",
                raw={"barcode": it.get("barcode"), "size": it.get("size")}
                if settings.include_raw
                else None,
            )
        )
        if len(offers) >= max_results:
            break
    return offers


def grocery_lane(marketplace: str) -> Callable[[SearchCtx], Awaitable[list[Offer]]]:
    async def search(ctx: SearchCtx) -> list[Offer]:
        actor: str = getattr(settings, f"{marketplace}_apify_actor")
        run_input = {"operation": "search", "query": ctx.query, "page": 1, "includeRaw": False}
        items = await apify_run_sync(actor, run_input, timeout_s=ctx.wait_s(ACTOR_WAIT_S))
        return parse_grocery(items, marketplace, ctx.query, ctx.max_results)

    return search
