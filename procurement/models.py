"""Offer and its nested models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DiagCode = Literal[
    "missing_key",
    "timeout",
    "upstream_error",
    "unsupported",
    "degraded",
    "no_results",
    "quota",
    "unsubscribed",
    "not_deliverable",
]
Reliability = Literal["authoritative", "aggregator", "best_effort"]
Delivery = Literal["direct", "pickup", "via_forwarder", "no", "unknown"]

# Offer id suffix per code. Ids that existed before the codes did are kept.
_DIAG_SUFFIX: dict[str, str] = {"upstream_error": "error", "quota": "error"}


class Shipping(BaseModel):
    domestic_cny: float | None = Field(default=None, description="Domestic leg in CNY if known")
    intl_estimate_aud: float | None = Field(
        default=None, description="Estimated international shipping in AUD"
    )
    eta_days: list[int] | None = Field(default=None, description="ETA window [min, max] days")
    method: str | None = None
    delivery: Delivery = Field(
        default="unknown",
        description="direct = seller delivers to the buyer's postcode; pickup = collect in person near the buyer; via_forwarder = seller ships within China only, a freight forwarder brings it to Australia; no = cannot reach the buyer; unknown = the source does not say",
    )
    delivery_basis: str | None = Field(
        default=None, description="What the delivery status rests on"
    )
    cost_aud: float | None = Field(
        default=None,
        description="Shipping cost to the buyer stated by the source. Null means not stated, which differs from free.",
    )


class Seller(BaseModel):
    shop_name: str | None = None
    shop_id: str | None = None
    rating: float | None = None
    verified: bool | None = None


class AuctionInfo(BaseModel):
    """Live-auction metadata for eBay AUCTION-format listings.

    price_aud on the parent Offer carries the CURRENT BID (converted), not a
    fixed price — this block makes that explicit and adds the bidding state.
    """

    current_bid_aud: float | None = Field(
        default=None, description="Current bid in AUD (price_aud mirror)"
    )
    bid_count: int | None = Field(default=None, description="Number of bids so far")
    end_time: str | None = Field(default=None, description="Auction end ISO datetime (UTC)")
    time_left: str | None = Field(
        default=None, description="Humanised time remaining, e.g. '2d 4h'"
    )
    reserve_met: bool | None = Field(
        default=None, description="Whether the reserve price has been met, if eBay reports it"
    )


class CommunitySignal(BaseModel):
    """Deal-site community metadata — OzBargain / Cheapies style.

    Populated from RSS ozb:meta / Apify deal scrapes. Distinct from seller
    trust: this is *crowd vetting of the price itself* (votes, clicks), not
    merchant reputation.
    """

    votes_pos: int | None = None
    votes_neg: int | None = None
    comment_count: int | None = None
    click_count: int | None = None
    expiry: str | None = Field(
        default=None, description="Deal expiry ISO datetime, if the source sets one"
    )
    brand: str | None = None
    tags: list[str] | None = None


class Offer(BaseModel):
    offer_id: str = Field(description="Stable id marketplace:product:sku, e.g. 1688:123456:sku147")
    marketplace: str = Field(
        description="aliexpress | taobao | tmall | 1688 | jd | pdd | ebay_au | amazon_au | gumtree | facebook | ozbargain | cheapies"
    )
    title: str
    title_en: str | None = None
    url: str | None = None
    image: str | None = None
    price_cny: float | None = None
    price_aud: float | None = None
    currency: str = Field(default="AUD", description="price_aud currency")
    moq: int | None = Field(default=None, description="Minimum order quantity — 1688 wholesale")
    unit: str | None = None
    stock: int | None = None
    regular_price_aud: float | None = Field(
        default=None,
        description="Pre-special regular price (grocery specials) — price_aud carries the effective/discounted price",
    )
    unit_price_aud: float | None = Field(
        default=None,
        description="Unit price in AUD per the unit below (grocery: $/100g, $/L …) — the true cheapest comparator",
    )
    shipping: Shipping = Field(default_factory=Shipping)
    seller: Seller = Field(default_factory=Seller)
    community: CommunitySignal | None = Field(
        default=None, description="Deal-site votes/expiry/brand — OzBargain, Cheapies"
    )
    auction: AuctionInfo | None = Field(
        default=None,
        description="Live-auction metadata when the listing is AUCTION format (price_aud = current bid)",
    )
    seller_country: str | None = Field(
        default=None,
        description="Item/seller country code (eBay itemLocationCountry) when known — global searches populate this",
    )
    price_history: dict[str, Any] | None = Field(
        default=None, description="Keepa/sold-comps price-history summary"
    )
    source_reliability: Literal["authoritative", "aggregator", "best_effort"] = "aggregator"
    kind: Literal["offer", "comp", "diagnostic"] = Field(
        default="offer",
        description="offer = buyable listing; comp = past sale price, not buyable; diagnostic = why a marketplace returned nothing",
    )
    diagnostic_code: DiagCode | None = Field(
        default=None, description="Set when kind is diagnostic"
    )
    landed_aud: float | None = Field(
        default=None,
        description="Total cost in AUD for the requested quantity delivered to the buyer. See landed_basis.",
    )
    landed_basis: Literal["exact", "estimated", "item_only"] | None = Field(
        default=None,
        description="exact = item price plus stated shipping, or pickup; estimated = includes a freight forwarder estimate from an assumed weight; item_only = shipping cost not stated, so it is left out",
    )
    landed_breakdown: dict[str, float] | None = Field(
        default=None, description="The parts that sum to landed_aud"
    )
    price_native: float | None = Field(
        default=None,
        description="Price in `currency` when the source did not give AUD; price_aud is then null",
    )
    raw: dict[str, Any] | None = Field(
        default=None, description="Raw marketplace payload for debugging"
    )


class Location(BaseModel):
    """Where the buyer takes delivery."""

    country: str = "AU"
    postcode: str = "4000"
    lat: float = -27.4698
    lng: float = 153.0251
    radius_km: float = 50

    @classmethod
    def default(cls) -> Location:
        from procurement.config import settings

        return cls(
            country=settings.ship_to_country,
            postcode=settings.ship_to_postcode,
            lat=settings.ship_to_lat,
            lng=settings.ship_to_lng,
            radius_km=settings.pickup_radius_km,
        )

    @property
    def label(self) -> str:
        return f"{self.country} {self.postcode}"


class ToolFailure(BaseModel):
    """A tool call that could not produce its result."""

    error: str
    code: str
    offer_id: str | None = None


def diag(
    marketplace: str,
    code: DiagCode,
    detail: str,
    *,
    reliability: Reliability = "aggregator",
    raw: dict[str, Any] | None = None,
) -> Offer:
    """Build the one diagnostic entry a marketplace returns when it has no offers."""
    return Offer(
        offer_id=f"{marketplace}:{_DIAG_SUFFIX.get(code, code)}",
        marketplace=marketplace,
        title=f"[{marketplace}] {detail}",
        kind="diagnostic",
        diagnostic_code=code,
        source_reliability=reliability,
        raw=raw,
    )


DIAGNOSTIC_ID_SUFFIXES = frozenset(
    {
        "error",
        "timeout",
        "unsupported",
        "degraded",
        "unsubscribed",
        "not_deliverable",
        "missing_key",
        "no_results",
        "unknown",
    }
)


def is_diagnostic_id(offer_id: str) -> bool:
    """True for ids such as `jd:timeout` that name a diagnostic, not a listing."""
    return offer_id.rsplit(":", 1)[-1] in DIAGNOSTIC_ID_SUFFIXES
