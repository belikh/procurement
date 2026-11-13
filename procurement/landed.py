"""Delivery status and landed cost for a buyer location.

Lanes set shipping.delivery when the source states it. annotate() fills the
rest from a per-marketplace rule and computes landed_aud for every offer.
"""

from __future__ import annotations

from procurement.config import settings
from procurement.models import Delivery, Location, Offer

CHINA_DOMESTIC = frozenset({"taobao", "tmall", "1688", "jd", "pdd"})

# Default (status, basis) for marketplaces whose source does not state delivery per offer.
_RULES: dict[str, tuple[Delivery, str]] = {
    "amazon_au": (
        "direct",
        "Amazon AU delivers Australia-wide; this item's delivery area was not checked",
    ),
    "woolworths": (
        "direct",
        "home delivery or pickup; this postcode's delivery area was not checked",
    ),
    "coles": ("direct", "home delivery or pickup; this postcode's delivery area was not checked"),
    "aldi": ("pickup", "Aldi sells in store only; the nearest store was not checked"),
    "gumtree": ("pickup", "local classified; pickup unless the seller offers postage"),
    "facebook": ("pickup", "local listing; pickup unless the seller offers shipping"),
    "cheapies": ("no", "Cheapies lists New Zealand retailers"),
}


def forwarder_landed(
    price_aud: float, qty: int, *, domestic_aud: float = 0.0, weight_kg: float | None = None
) -> tuple[float, dict[str, float]]:
    """Estimate the cost of goods bought in China and forwarded to Australia.

    freight = max(minimum charge, weight per item x qty x rate per kg)
    total   = (goods + domestic leg + freight) x (1 + forwarder fee) x (1 + GST)
    """
    weight = weight_kg if weight_kg is not None else settings.forwarder_default_weight_kg
    goods = price_aud * qty
    freight = max(
        settings.forwarder_min_charge_aud, weight * qty * settings.forwarder_rate_aud_per_kg
    )
    subtotal = goods + domestic_aud + freight
    fee = subtotal * settings.forwarder_fee_pct
    gst = (subtotal + fee) * settings.gst_rate
    parts = {
        "goods": round(goods, 2),
        "china_domestic": round(domestic_aud, 2),
        "forwarder_freight": round(freight, 2),
        "forwarder_fee": round(fee, 2),
        "gst": round(gst, 2),
    }
    return round(subtotal + fee + gst, 2), parts


def _set_delivery(o: Offer, location: Location) -> None:
    ship = o.shipping
    if o.marketplace == "cheapies" and o.currency == "NZD" and o.price_aud is not None:
        # The feed's title price is in NZD.
        o.price_native = o.price_aud
        o.price_aud = round(o.price_aud * settings.nzd_to_aud, 2)
    if ship.delivery != "unknown":
        return
    if o.marketplace in CHINA_DOMESTIC:
        ship.delivery = "via_forwarder"
        ship.delivery_basis = "ships within China only; a freight forwarder is needed"
    elif o.marketplace in _RULES:
        ship.delivery, ship.delivery_basis = _RULES[o.marketplace]
        if ship.delivery == "pickup" and o.marketplace in ("gumtree", "facebook"):
            ship.delivery_basis += f"; searched around {location.label}"
        if o.marketplace == "facebook" and ship.method and "ship" in ship.method.lower():
            ship.delivery, ship.delivery_basis = "direct", "the listing offers shipping"
    elif o.marketplace == "ozbargain" and "delivered" in o.title.lower():
        ship.delivery, ship.delivery_basis = "direct", "the deal title says Delivered"


def _set_landed(o: Offer, qty: int, weight_kg: float | None) -> None:
    if o.price_aud is None:
        return
    ship = o.shipping
    if ship.delivery == "via_forwarder":
        domestic = round((ship.domestic_cny or 0) * settings.cny_to_aud, 2)
        o.landed_aud, o.landed_breakdown = forwarder_landed(
            o.price_aud, qty, domestic_aud=domestic, weight_kg=weight_kg
        )
        o.landed_basis = "estimated"
        ship.intl_estimate_aud = o.landed_breakdown["forwarder_freight"]
        return
    goods = round(o.price_aud * qty, 2)
    if ship.cost_aud is not None:
        o.landed_aud, o.landed_basis = round(goods + ship.cost_aud, 2), "exact"
        o.landed_breakdown = {"goods": goods, "shipping": ship.cost_aud}
    elif ship.delivery == "pickup":
        o.landed_aud, o.landed_basis, o.landed_breakdown = goods, "exact", {"goods": goods}
    else:
        o.landed_aud, o.landed_basis, o.landed_breakdown = goods, "item_only", {"goods": goods}


def annotate(
    offers: list[Offer], location: Location, qty: int, weight_kg: float | None = None
) -> list[Offer]:
    """Set delivery status and landed cost on buyable offers, in place."""
    for o in offers:
        if o.kind != "offer":
            continue
        _set_delivery(o, location)
        _set_landed(o, qty, weight_kg)
    return offers
