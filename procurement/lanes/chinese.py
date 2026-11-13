"""Taobao/Tmall, JD and 1688 keyword search via zen-studio Apify actors.

Output shapes seen in live runs on 2026-09-02:
  taobao: itemId, url, title/titleOriginal, price (CNY str), priceCurrency
  jd:     skuId/itemId (jd- prefixed), url, title, price (CNY float)
The taobao and jd actors reject maxItems below 10.
"""

from __future__ import annotations

from typing import Any

from procurement.common import cny_to_aud, float_or_none
from procurement.config import settings
from procurement.http import LaneError, apify_run_sync
from procurement.lanes.base import SearchCtx
from procurement.lanes.tmapi import search_1688_tmapi
from procurement.models import Offer, Seller, Shipping, diag

ACTOR_WAIT_S = 85


def parse_chinese(
    items: list[dict[str, Any]], marketplace: str, query: str, max_results: int
) -> list[Offer]:
    """Map actor items to offers. Taobao items flagged isTmall are labelled tmall."""
    offers: list[Offer] = []
    for it in items[:max_results]:
        raw_price = it.get("price")
        if isinstance(raw_price, dict):  # 1688 wholesale shape: {min, max, currency}
            raw_price = raw_price.get("min") or raw_price.get("max")  # pyright: ignore[reportUnknownMemberType]
        price_cny = float_or_none(raw_price or it.get("priceFromSearch"))
        item_id = str(it.get("itemId") or it.get("skuId") or "unknown")
        mp = marketplace
        if marketplace == "jd":
            item_id = item_id.removeprefix("jd-")  # TMAPI jd/item_detail takes the bare id
        elif marketplace == "taobao" and it.get("isTmall") is True:
            mp = "tmall"
        shop = it.get("shop")
        images = it.get("images")
        offers.append(
            Offer(
                offer_id=f"{mp}:{item_id}",
                marketplace=mp,
                title=str(it.get("title") or it.get("titleOriginal") or query),
                title_en=it.get("titleEn"),
                url=it.get("url") or it.get("productUrl") or it.get("detailUrl"),
                image=it.get("image")
                or it.get("imageUrl")
                or (images.get("main") if isinstance(images, dict) else None),  # pyright: ignore[reportUnknownMemberType]
                price_cny=price_cny,
                price_aud=cny_to_aud(price_cny),
                currency="CNY",
                stock=it.get("stock") if isinstance(it.get("stock"), int) else None,
                shipping=Shipping(eta_days=[10, 25], method="China consolidated"),
                seller=Seller(
                    shop_name=it.get("shopName")
                    or (shop.get("name") if isinstance(shop, dict) else None)
                ),  # pyright: ignore[reportUnknownMemberType]
                source_reliability="best_effort",
                raw={
                    "is_tmall": it.get("isTmall"),
                    "sales": it.get("salesSignal") or it.get("sales"),
                }
                if settings.include_raw
                else None,
            )
        )
    return offers


async def _run_keyword_actor(actor: str, marketplace: str, ctx: SearchCtx) -> list[dict[str, Any]]:
    run_input = {
        "keyword": ctx.china_query,
        "maxItems": max(ctx.max_results, 10),
        "enrichWithDetails": False,
    }
    return await apify_run_sync(actor, run_input, timeout_s=ctx.wait_s(ACTOR_WAIT_S))


async def search_taobao_tmall(ctx: SearchCtx) -> list[Offer]:
    """One Taobao actor run serves both the taobao and tmall lanes."""
    items = await _run_keyword_actor(settings.taobao_apify_actor, "taobao", ctx)
    offers = parse_chinese(items, "taobao", ctx.query, ctx.max_results)
    if items and not any("isTmall" in it for it in items):
        offers.append(
            diag(
                "tmall",
                "unsupported",
                "the Taobao actor did not flag Tmall items; Tmall listings are under taobao",
                reliability="best_effort",
            )
        )
    return offers


async def search_jd(ctx: SearchCtx) -> list[Offer]:
    items = await _run_keyword_actor(settings.jd_apify_actor, "jd", ctx)
    return parse_chinese(items, "jd", ctx.query, ctx.max_results)


async def search_1688_actor(ctx: SearchCtx) -> list[Offer]:
    run_input = {
        "keywords": [ctx.china_query],
        "maxResults": ctx.max_results,
        "includeSkuDetails": False,
        "includeDescriptionHtml": False,
        "includeSupplierIntelligence": False,
    }
    items = await apify_run_sync(
        settings.ali1688_apify_actor, run_input, timeout_s=ctx.wait_s(ACTOR_WAIT_S)
    )
    return parse_chinese(items, "1688", ctx.query, ctx.max_results)


async def search_1688(ctx: SearchCtx) -> list[Offer]:
    """TMAPI when its key is set and subscribed, otherwise the Apify wholesale actor."""
    tmapi_error: LaneError | None = None
    if settings.tmapi_token:
        try:
            offers = await search_1688_tmapi(ctx.china_query, ctx.max_results)
            if offers:
                return offers
        except LaneError as e:
            tmapi_error = e
    if settings.apify_token:
        return await search_1688_actor(ctx)
    if tmapi_error:
        raise tmapi_error
    return []


def missing_1688() -> str | None:
    return None if (settings.tmapi_token or settings.apify_token) else "TMAPI_TOKEN or APIFY_TOKEN"
