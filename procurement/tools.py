"""MCP tools and the prompt."""

from __future__ import annotations

import time
from collections import Counter, OrderedDict
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, Field

from procurement import db
from procurement.common import cny_to_aud, float_or_none
from procurement.config import settings
from procurement.http import LaneError, apify_run_sync
from procurement.instance import mcp
from procurement.keepa import (
    enrich_with_keepa,
    keepa_products,
    keepa_series,
    keepa_summary,
    offer_asin,
)
from procurement.landed import annotate
from procurement.lanes import ALL_MARKETPLACES, LANES, SearchCtx, run_lanes
from procurement.lanes.deals import FEED_CAP, fetch_deals
from procurement.lanes.ebay import fetch_ebay_item
from procurement.lanes.tmapi import DETAIL_MARKETPLACES, fetch_tmapi
from procurement.models import (
    Location,
    Offer,
    Seller,
    Shipping,
    ToolFailure,
    diag,
    is_diagnostic_id,
)
from procurement.ranking import rank_offers

# Offers from recent searches, so get_offer_detail can answer for marketplaces
# that have no detail endpoint. Oldest entries drop first.
_MEMO_SIZE = 2000
_offer_memo: OrderedDict[str, Offer] = OrderedDict()

# A failed search is not cached: the next call should try the source again.
_UNCACHEABLE = frozenset({"timeout", "upstream_error", "quota"})


def _remember(offers: list[Offer]) -> None:
    for o in offers:
        if o.kind == "diagnostic":
            continue
        _offer_memo[o.offer_id] = o
        _offer_memo.move_to_end(o.offer_id)
    while len(_offer_memo) > _MEMO_SIZE:
        _offer_memo.popitem(last=False)


@mcp.tool()
async def search_offers(
    query: Annotated[
        str,
        Field(
            description="Product keyword, e.g. 'wireless mouse'. Sent as written to every source."
        ),
    ],
    marketplaces: Annotated[
        list[str] | None,
        Field(
            description="Subset to search. Defaults to all. Valid: taobao, tmall, 1688, jd, pdd, aliexpress, "
            "ebay_au, ebay_sold (past AU sale prices, returned as kind='comp'), amazon_au, gumtree, facebook, "
            "woolworths, coles, aldi (grocery with unit pricing), ozbargain, cheapies. "
            "An unknown name returns a diagnostic entry."
        ),
    ] = None,
    sort: Annotated[
        Literal["cheapest", "fastest", "best_value"], Field(description="Ranking intent")
    ] = "best_value",
    qty: Annotated[
        int,
        Field(
            ge=1, description="Requested quantity. Offers with a larger minimum order rank last."
        ),
    ] = 1,
    ship_to: Annotated[
        str | None, Field(description="Destination country code. Default: SHIP_TO_COUNTRY (AU).")
    ] = None,
    postcode: Annotated[
        str | None,
        Field(description="Destination postcode. Default: SHIP_TO_POSTCODE (4000, Brisbane)."),
    ] = None,
    max_results: Annotated[
        int, Field(ge=1, le=50, description="Per-marketplace cap, then ranked globally")
    ] = 10,
    ebay_auctions: Annotated[
        bool,
        Field(
            description="eBay: auction listings only (current bid, bid count, end time). Default: fixed price."
        ),
    ] = False,
    ebay_seller_scope: Annotated[
        Literal["domestic", "global", "auto"],
        Field(
            description="eBay seller scope. 'domestic': items located in AU. 'global': world-wide sellers on "
            "the AU marketplace. 'auto': eBay default ranking."
        ),
    ] = "domestic",
    query_zh: Annotated[
        str | None,
        Field(
            description="The query in Chinese, e.g. 硅胶厨具. Used for taobao, tmall, 1688 and jd, which match "
            "Chinese far better than English. Translate the query yourself and pass it here."
        ),
    ] = None,
    deadline_s: Annotated[
        float | None,
        Field(
            ge=5,
            le=300,
            description="Seconds allowed for the whole search. Default: PROCUREMENT_DEADLINE_S.",
        ),
    ] = None,
    est_weight_kg: Annotated[
        float | None,
        Field(
            gt=0,
            description="Weight of one item in kg. Used for the freight forwarder estimate on taobao, tmall, "
            "1688, jd and pdd offers. Default: FORWARDER_DEFAULT_WEIGHT_KG.",
        ),
    ] = None,
    include_pickup: Annotated[
        bool,
        Field(
            description="Include listings that must be collected in person near the destination."
        ),
    ] = True,
) -> list[Offer]:
    """Search marketplaces for a product and return ranked offers.

    The result lists buyable offers first (kind='offer', ranked by `sort`), then
    past sale prices (kind='comp'), then one kind='diagnostic' entry for every
    requested marketplace that returned no offers. A diagnostic's
    diagnostic_code is one of: missing_key, timeout, upstream_error, quota,
    unsupported, degraded, unsubscribed, no_results.

    Each offer has shipping.delivery (direct, pickup, via_forwarder or unknown)
    for the destination postcode and landed_aud, the total for `qty` delivered.
    landed_basis says how firm that total is: exact, estimated (China offers,
    from a forwarder rate and an assumed weight) or item_only (shipping cost not
    stated). Offers that cannot reach the destination are left out and counted
    in a not_deliverable diagnostic.

    All marketplaces run at once under one deadline. Hosted scraper sources
    take 30 to 90 s, so a short deadline reports them as timeout.
    """
    t0 = time.time()
    requested = [m.lower().strip() for m in (marketplaces or ALL_MARKETPLACES)]
    requested = list(dict.fromkeys(requested))
    wanted = [m for m in requested if m in LANES]
    unknown = [m for m in requested if m not in LANES]

    location = Location.default()
    location = location.model_copy(
        update={
            "country": (ship_to or location.country).upper(),
            "postcode": postcode or location.postcode,
        }
    )
    ship_to = f"{location.country}:{location.postcode}"
    cache_key = db.make_cache_key(
        f"{query}|{query_zh or ''}|{est_weight_kg}|{include_pickup}",
        wanted,
        sort,
        qty,
        ship_to,
        max_results,
        ebay_auctions=ebay_auctions,
        ebay_seller_scope=ebay_seller_scope,
    )
    cached = await db.get_cached(cache_key)
    if cached is not None:
        _remember(cached)
        return cached

    ctx = SearchCtx(
        query=query,
        max_results=max_results,
        sort=sort,
        qty=qty,
        query_zh=query_zh,
        ebay_auctions=ebay_auctions,
        ebay_seller_scope=ebay_seller_scope,
        location=location,
        est_weight_kg=est_weight_kg,
        deadline=time.monotonic() + (deadline_s or settings.deadline_s),
    )
    outcomes = await run_lanes([LANES[m] for m in wanted], ctx)

    found = annotate(
        [o for outcome in outcomes.values() for o in outcome.offers], location, qty, est_weight_kg
    )
    if not include_pickup:
        found = [o for o in found if o.shipping.delivery != "pickup"]
    ranked = rank_offers(found, sort, qty)[: max_results * 2]
    ranked = await enrich_with_keepa(ranked)
    comps = [o for o in found if o.kind == "comp"]
    diagnostics = [outcome.diagnostic for outcome in outcomes.values() if outcome.diagnostic]
    undeliverable = Counter(
        o.marketplace for o in found if o.kind == "offer" and o.shipping.delivery == "no"
    )
    diagnostics += [
        diag(m, "not_deliverable", f"{n} offers left out: they do not deliver to {location.label}")
        for m, n in undeliverable.items()
    ]
    diagnostics += [
        diag(m, "unsupported", f"unknown marketplace; valid names: {', '.join(ALL_MARKETPLACES)}")
        for m in unknown
    ]
    result = ranked + comps + diagnostics

    _remember(result)
    if not any(d.diagnostic_code in _UNCACHEABLE for d in diagnostics):
        await db.set_cached(cache_key, query, wanted, sort, qty, ship_to, result)
    await db.log_search(
        query, wanted, sort, qty, ship_to, len(ranked), int((time.time() - t0) * 1000)
    )
    return result


def _tmapi_offer(offer_id: str, marketplace: str, detail: dict[str, Any]) -> Offer:
    data = detail.get("data") or detail
    price_cny = float_or_none(str(data.get("price") or "").replace("¥", ""))
    return Offer(
        offer_id=offer_id,
        marketplace=marketplace,
        title=str(data.get("title") or data.get("subject") or offer_id),
        url=data.get("url") or data.get("detail_url"),
        image=data.get("pic"),
        price_cny=price_cny,
        price_aud=cny_to_aud(price_cny),
        currency="CNY",
        moq=data.get("moq"),
        stock=data.get("stock"),
        seller=Seller(shop_name=data.get("shop_name")),
        source_reliability="aggregator",
        raw=data if settings.include_raw else None,
    )


@mcp.tool()
async def get_offer_detail(
    offer_id: Annotated[
        str,
        Field(description="Offer id from search_offers, e.g. taobao:123456 or ebay_au:v1|1234|0"),
    ],
) -> Offer | ToolFailure:
    """Fetch one offer by id.

    taobao, tmall, 1688, jd and pdd ids are fetched live from TMAPI, and ebay_au
    ids from the eBay Browse API. Other marketplaces have no detail endpoint:
    the offer is returned as it was in the most recent search that contained it.
    """
    if ":" not in offer_id:
        return ToolFailure(
            error="offer id must look like <marketplace>:<item id>",
            code="bad_id",
            offer_id=offer_id,
        )
    if is_diagnostic_id(offer_id):
        return ToolFailure(
            error="this id names a diagnostic entry, which has no detail",
            code="diagnostic_id",
            offer_id=offer_id,
        )
    marketplace, item_id = offer_id.split(":", 1)
    try:
        if marketplace in DETAIL_MARKETPLACES:
            return _tmapi_offer(
                offer_id, marketplace, await fetch_tmapi(item_id.removeprefix("jd-"), marketplace)
            )
        if marketplace == "ebay_au":
            return await fetch_ebay_item(item_id)
    except LaneError as e:
        live_error = ToolFailure(error=e.detail, code=e.code, offer_id=offer_id)
    except httpx.HTTPError as e:
        live_error = ToolFailure(
            error=f"{type(e).__name__}: {e}", code="upstream_error", offer_id=offer_id
        )
    else:
        live_error = None

    stored = _offer_memo.get(offer_id) or await db.find_offer(offer_id)
    if stored:
        return stored
    if live_error:
        return live_error
    return ToolFailure(
        error=f"{marketplace} has no detail endpoint and no recent search holds this offer; run search_offers again",
        code="not_found",
        offer_id=offer_id,
    )


@mcp.tool()
async def search_by_image(
    image_url: Annotated[
        str, Field(description="Public URL of a product photo to reverse-search (JPG/PNG)")
    ],
    destination: Annotated[
        Literal["1688", "alibaba", "aliexpress", "global"],
        Field(
            description="Where to search: 1688 = wholesale factories, alibaba = B2B, aliexpress = retail, "
            "global = Amazon, Walmart, eBay and other retail sites"
        ),
    ] = "1688",
    max_results: Annotated[int, Field(ge=1, le=50, description="Cap on matches returned")] = 10,
) -> list[Offer]:
    """Find supplier listings that match a product photo.

    Give it a photo, for example from a Gumtree or Facebook listing, and it
    returns matching listings with price, minimum order and supplier name.
    Runs a hosted Apify actor that costs about $0.10 per search.
    """
    try:
        items = await apify_run_sync(
            settings.image_search_apify_actor,
            {
                "imageUrl": image_url,
                "destination": destination,
                "language": "en",
                "currency": "AUD",
            },
            timeout_s=28,
        )
    except LaneError as e:
        return [
            diag(
                destination,
                e.code,
                f"image search: {e.detail}",
                reliability="best_effort",
                raw=e.raw,
            )
        ]
    except httpx.HTTPError as e:
        return [
            diag(
                destination,
                "upstream_error",
                f"image search: {type(e).__name__}: {e}",
                reliability="best_effort",
            )
        ]
    offers: list[Offer] = []
    for it in items[:max_results]:
        offers.append(
            Offer(
                offer_id=f"{destination}:{it.get('productUrl') or it.get('title') or 'unknown'}",
                marketplace=destination,
                title=it.get("title") or "image match",
                url=it.get("productUrl"),
                image=it.get("imageUrl"),
                price_aud=float_or_none(it.get("price")),
                currency=it.get("currency") or "AUD",
                moq=it.get("minOrderQty"),
                seller=Seller(
                    shop_name=it.get("supplierName"), verified=bool(it.get("supplierUrl"))
                ),
                shipping=Shipping(eta_days=[10, 25], method="China consolidated"),
                source_reliability="aggregator",
                raw={
                    "supplier_url": it.get("supplierUrl"),
                    "location": it.get("location"),
                    "trade_count": it.get("tradeCount"),
                }
                if settings.include_raw
                else None,
            )
        )
    if not offers:
        return [
            diag(
                destination, "no_results", "image search found no match", reliability="best_effort"
            )
        ]
    _remember(offers)
    return offers


@mcp.tool()
async def latest_deals(
    sources: Annotated[
        list[Literal["ozbargain", "cheapies"]] | None,
        Field(
            description="Deal sites to read. Default: ozbargain. cheapies is a New Zealand site priced in NZD."
        ),
    ] = None,
    query: Annotated[
        str | None,
        Field(description="Keep only deals whose title, brand or tags contain one of these words"),
    ] = None,
    min_votes: Annotated[
        int, Field(ge=0, description="Keep only deals with at least this many net votes")
    ] = 0,
    max_results: Annotated[int, Field(ge=1, le=100, description="Cap on deals returned")] = 20,
) -> list[Offer]:
    """List the newest community-posted deals, most upvoted first.

    Reads the sites' own RSS feeds, which hold about the latest 100 deals each.
    Each deal carries votes, comment count, expiry and the price parsed from
    its title. A feed that fails adds one kind='diagnostic' entry.
    """
    feeds = {"ozbargain": settings.ozbargain_feed_url, "cheapies": settings.cheapies_feed_url}
    deals: list[Offer] = []
    diagnostics: list[Offer] = []
    for source in dict.fromkeys(sources or ["ozbargain"]):
        try:
            deals += await fetch_deals(feeds[source], source, query, FEED_CAP)
        except LaneError as e:
            diagnostics.append(diag(source, e.code, e.detail, reliability="authoritative"))
        except httpx.HTTPError as e:
            diagnostics.append(
                diag(
                    source,
                    "upstream_error",
                    f"{type(e).__name__}: {e}",
                    reliability="authoritative",
                )
            )

    def net_votes(o: Offer) -> int:
        return (o.community.votes_pos or 0) - (o.community.votes_neg or 0) if o.community else 0

    kept = sorted((o for o in deals if net_votes(o) >= min_votes), key=net_votes, reverse=True)[
        :max_results
    ]
    _remember(kept)
    return kept + diagnostics


class PricePoint(BaseModel):
    t: str = Field(description="ISO datetime (UTC) when the price took effect")
    price_aud: float


class PriceHistory(BaseModel):
    asin: str
    source: str = "keepa"
    current_aud: float | None = None
    avg_30d_aud: float | None = None
    avg_90d_aud: float | None = None
    min_aud: float | None = Field(
        default=None, description="Lowest Amazon price Keepa has recorded"
    )
    max_aud: float | None = Field(
        default=None, description="Highest Amazon price Keepa has recorded"
    )
    series: list[PricePoint] | None = Field(
        default=None, description="Price changes within `days`, oldest first"
    )


@mcp.tool()
async def get_price_history(
    offer_id_or_asin: Annotated[
        str, Field(description="An amazon_au offer id (amazon_au:B0XXXXXXXX) or a bare ASIN")
    ],
    days: Annotated[int, Field(ge=1, le=365, description="Window for the price series")] = 90,
    include_series: Annotated[
        bool,
        Field(description="Also return every price change in the window. Default: summary only."),
    ] = False,
) -> PriceHistory | ToolFailure:
    """Amazon price history for one product, from Keepa.

    Returns current, 30-day and 90-day average, and all-time low and high for
    the price sold by Amazon itself. Needs KEEPA_API_KEY and KEEPA_DOMAIN.
    """
    asin = offer_asin(offer_id_or_asin)
    if not asin:
        return ToolFailure(error="expected a 10-character ASIN or amazon_au:<ASIN>", code="bad_id")
    try:
        products = await keepa_products([asin], days=days, history=include_series)
    except LaneError as e:
        return ToolFailure(error=e.detail, code=e.code)
    except httpx.HTTPError as e:
        return ToolFailure(error=f"{type(e).__name__}: {e}", code="upstream_error")
    product = products.get(asin)
    summary = keepa_summary(product) if product else None
    if not product or not summary:
        return ToolFailure(error=f"Keepa has no price data for {asin}", code="not_found")
    return PriceHistory(
        asin=asin,
        current_aud=summary["current_aud"],
        avg_30d_aud=summary["avg_30d_aud"],
        avg_90d_aud=summary["avg_90d_aud"],
        min_aud=summary["min_aud"],
        max_aud=summary["max_aud"],
        series=[PricePoint(**p) for p in keepa_series(product, days)] if include_series else None,
    )


@mcp.tool()
async def search_history(
    source: Annotated[
        Literal["log", "cache"],
        Field(
            description="log: every past search with its result count and time. cache: unexpired cached results."
        ),
    ] = "log",
    query_contains: Annotated[
        str | None, Field(description="Keep only searches whose query contains this text")
    ] = None,
    since_hours: Annotated[int, Field(ge=1, le=2160, description="How far back to look")] = 168,
    limit: Annotated[int, Field(ge=1, le=200, description="Cap on rows returned")] = 20,
    include_offers: Annotated[
        bool,
        Field(
            description="cache only: include the cached offers in each row. Default: counts only."
        ),
    ] = False,
) -> list[dict[str, Any]] | ToolFailure:
    """Read past searches from the Postgres search log or cache, newest first.

    Needs DATABASE_URL. Without a database the server keeps no history.
    """
    if not db.enabled:
        reason = db.error or "DATABASE_URL is not set"
        return ToolFailure(error=f"search history needs the database: {reason}", code="db_disabled")
    try:
        if source == "cache":
            return await db.cached_searches(query_contains, since_hours, limit, include_offers)
        return await db.recent_searches(query_contains, since_hours, limit)
    except Exception as e:
        return ToolFailure(error=f"{type(e).__name__}: {e}", code="upstream_error")


@mcp.tool()
def health() -> dict[str, Any]:
    """Report which marketplaces can run, with no secrets.

    Each marketplace has: ready (its key is set), missing (the unset key),
    source (the API or actor it calls) and status. Status is verified (a live
    run matched the parser), unverified (written from docs), degraded (returns
    nothing without extra setup) or unsupported (no source yet).
    """
    lanes: dict[str, dict[str, Any]] = {}
    for name, spec in LANES.items():
        missing = spec.missing()
        lanes[name] = {
            "ready": missing is None and spec.status not in ("unsupported", "degraded"),
            "missing": missing,
            "source": spec.source,
            "status": spec.status,
        }
    return {
        "status": "ok",
        "marketplaces": lanes,
        "ready_count": sum(1 for lane in lanes.values() if lane["ready"]),
        "image_search": {
            "ready": bool(settings.apify_token),
            "missing": None if settings.apify_token else "APIFY_TOKEN",
        },
        "price_history": {
            "ready": bool(settings.keepa_api_key and settings.keepa_domain is not None),
            "missing": [
                name
                for name, value in (
                    ("KEEPA_API_KEY", settings.keepa_api_key),
                    ("KEEPA_DOMAIN", settings.keepa_domain),
                )
                if value is None
            ],
        },
        "ship_to": Location.default().model_dump(),
        "forwarder_estimate": {
            "rate_aud_per_kg": settings.forwarder_rate_aud_per_kg,
            "default_weight_kg": settings.forwarder_default_weight_kg,
            "min_charge_aud": settings.forwarder_min_charge_aud,
            "fee_pct": settings.forwarder_fee_pct,
            "gst_rate": settings.gst_rate,
        },
        "deadline_s": settings.deadline_s,
        "cny_to_aud": settings.cny_to_aud,
        "database": {
            "configured": bool(settings.database_url),
            "schema": settings.pg_schema,
            "enabled": db.enabled,
            "error": db.error,
            "cache_ttl_s": settings.cache_ttl_s,
        },
    }


@mcp.prompt()
def procurement_brief(query: str) -> str:
    return (
        f"You are a procurement assistant for {query}. Use search_offers(query='{query}', sort='best_value') "
        "then compare landed_aud with its landed_basis, shipping.delivery, ETA and seller rating. "
        "Explain cheapest vs fastest vs best value and flag MOQ issues for 1688 wholesale. "
        "Entries with kind='diagnostic' are sources that returned nothing; report them separately."
    )
