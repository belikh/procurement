"""The lane registry: every marketplace a caller can request.

A lane's status says how far its upstream contract has been checked:
  verified     a live run returned offers and the parser matched them
  unverified   written from documentation or an earlier unrecorded run
  degraded     known to return nothing without extra setup
  unsupported  no source exists yet
"""

from __future__ import annotations

from procurement.config import settings
from procurement.http import LaneError
from procurement.lanes import amazon, chinese, deals, ebay, ebay_sold, facebook, grocery, gumtree
from procurement.lanes.base import LaneOutcome, LaneSpec, SearchCtx, run_lanes
from procurement.models import Offer


def _apify() -> str | None:
    return None if settings.apify_token else "APIFY_TOKEN"


async def _no_source(ctx: SearchCtx) -> list[Offer]:
    raise LaneError("unsupported", "no keyword-search source is wired for this marketplace yet")


async def _pdd(ctx: SearchCtx) -> list[Offer]:
    raise LaneError(
        "unsupported",
        "no keyword-search source exists for PDD (TMAPI is detail-only); "
        "use get_offer_detail with a pdd:<item id>",
    )


_SPECS = [
    LaneSpec(
        "taobao",
        chinese.search_taobao_tmall,
        "Apify zen-studio/taobao-search-scraper",
        _apify,
        budget_s=95,
        group="taobao_tmall",
        reliability="best_effort",
    ),
    LaneSpec(
        "tmall",
        chinese.search_taobao_tmall,
        "Apify zen-studio/taobao-search-scraper",
        _apify,
        budget_s=95,
        group="taobao_tmall",
        reliability="best_effort",
    ),
    LaneSpec(
        "1688",
        chinese.search_1688,
        "TMAPI /1688/search/items, else Apify zen-studio/1688-wholesale-scraper",
        chinese.missing_1688,
        budget_s=95,
    ),
    LaneSpec(
        "jd",
        chinese.search_jd,
        "Apify zen-studio/jd-com-search-scraper",
        _apify,
        budget_s=95,
        reliability="best_effort",
    ),
    LaneSpec("pdd", _pdd, "none", status="unsupported"),
    LaneSpec("aliexpress", _no_source, "none", status="unsupported"),
    LaneSpec(
        "ebay_au",
        ebay.search_ebay_au,
        "eBay Browse API",
        ebay.missing_ebay,
        budget_s=15,
        reliability="authoritative",
    ),
    LaneSpec(
        "ebay_sold",
        ebay_sold.search_ebay_sold,
        "Apify caffein.dev/ebay-sold-listings",
        _apify,
        budget_s=65,
    ),
    LaneSpec(
        "amazon_au",
        amazon.search_amazon_au,
        "Apify junglee/free-amazon-product-scraper",
        _apify,
        budget_s=75,
        reliability="best_effort",
    ),
    LaneSpec(
        "gumtree",
        gumtree.search_gumtree,
        "Apify crawlerbros/gumtree-scraper",
        gumtree.missing_gumtree,
        budget_s=60,
        status="degraded",
        reliability="best_effort",
    ),
    LaneSpec(
        "facebook",
        facebook.search_facebook,
        "SociaVault",
        facebook.missing_facebook,
        budget_s=15,
        reliability="best_effort",
    ),
    LaneSpec(
        "woolworths",
        grocery.grocery_lane("woolworths"),
        "Apify dromb Woolworths actor",
        _apify,
        budget_s=45,
        reliability="best_effort",
    ),
    LaneSpec(
        "coles",
        grocery.grocery_lane("coles"),
        "Apify dromb Coles actor",
        _apify,
        budget_s=45,
        reliability="best_effort",
    ),
    LaneSpec(
        "aldi",
        grocery.grocery_lane("aldi"),
        "Apify dromb Aldi actor",
        _apify,
        budget_s=45,
        reliability="best_effort",
    ),
    LaneSpec(
        "ozbargain",
        deals.search_ozbargain,
        "OzBargain RSS feed",
        budget_s=12,
        status="verified",
        reliability="authoritative",
    ),
    LaneSpec(
        "cheapies",
        deals.search_cheapies,
        "Cheapies RSS feed",
        budget_s=12,
        status="verified",
        reliability="authoritative",
    ),
]

LANES: dict[str, LaneSpec] = {spec.name: spec for spec in _SPECS}
ALL_MARKETPLACES: tuple[str, ...] = tuple(LANES)

__all__ = ["ALL_MARKETPLACES", "LANES", "LaneOutcome", "LaneSpec", "SearchCtx", "run_lanes"]
