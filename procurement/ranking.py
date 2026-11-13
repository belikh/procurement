"""Offer ranking for the cheapest, fastest and best_value sorts."""

from __future__ import annotations

from procurement.config import settings
from procurement.models import Offer

UNPRICED = 1e9


def _below_moq(o: Offer, qty: int) -> bool:
    return bool(o.moq and qty < o.moq)


def _landed(o: Offer, qty: int) -> float:
    if o.landed_aud is not None:
        return o.landed_aud
    if o.price_aud is not None:
        base = o.price_aud
    elif o.price_cny:
        base = o.price_cny * settings.cny_to_aud
    else:
        return UNPRICED
    return base * qty + (o.shipping.cost_aud or o.shipping.intl_estimate_aud or 0)


def _cheapest_key(o: Offer, qty: int) -> float:
    # Grocery offers sort on unit price: a $4.50 2 L beats a $3.10 1 L.
    return o.unit_price_aud if o.unit_price_aud is not None else _landed(o, qty)


def _latest_eta(o: Offer) -> float:
    return o.shipping.eta_days[1] if o.shipping.eta_days else 99


def _score(o: Offer, qty: int) -> float:
    # Per-unit delivered cost where known, so a cheap item with dear freight does not win.
    unit_cost = o.landed_aud / qty if o.landed_aud is not None else (o.price_aud or 50)
    price_norm = 1 - min(1, unit_cost / 200)
    eta_norm = 1 - min(1, (o.shipping.eta_days[1] if o.shipping.eta_days else 14) / 30)
    trust = 0.5
    # Deal-site votes on the price itself outrank a seller star rating.
    # Net votes, saturating at plus or minus 10.
    if o.community and (o.community.votes_pos or o.community.votes_neg):
        net = (o.community.votes_pos or 0) - (o.community.votes_neg or 0)
        trust = max(0.0, min(1.0, 0.5 + net / 20))
    elif o.seller.rating:
        trust = min(1, o.seller.rating / 5)
    elif o.source_reliability == "authoritative":
        trust = 0.85
    elif o.source_reliability == "aggregator":
        trust = 0.7
    score = 0.5 * price_norm + 0.25 * eta_norm + 0.25 * trust
    # An offer that may not reach the buyer ranks below an equal one that does.
    return score - (0.05 if o.shipping.delivery == "unknown" else 0)


def rank_offers(offers: list[Offer], sort: str, qty: int) -> list[Offer]:
    """Rank buyable offers. Comps and diagnostics are left out.

    Offers whose minimum order quantity exceeds qty sort last in every sort.
    Offers that cannot be delivered (delivery "no") are left out.
    """
    buyable = [o for o in offers if o.kind == "offer" and o.shipping.delivery != "no"]
    if sort == "cheapest":
        return sorted(
            buyable,
            key=lambda o: (
                _below_moq(o, qty),
                _cheapest_key(o, qty),
                o.shipping.delivery == "unknown",
            ),
        )
    if sort == "fastest":
        return sorted(
            buyable, key=lambda o: (_below_moq(o, qty), _latest_eta(o), o.price_aud or UNPRICED)
        )
    return sorted(buyable, key=lambda o: (_below_moq(o, qty), -_score(o, qty)))
