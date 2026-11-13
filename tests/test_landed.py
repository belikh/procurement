import pytest

from procurement.config import settings
from procurement.landed import annotate, forwarder_landed
from procurement.models import Location, Offer, Shipping
from procurement.ranking import rank_offers

BRISBANE = Location()


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    for name, value in {
        "forwarder_rate_aud_per_kg": 10.0,
        "forwarder_default_weight_kg": 0.5,
        "forwarder_min_charge_aud": 15.0,
        "forwarder_fee_pct": 0.05,
        "gst_rate": 0.10,
        "cny_to_aud": 0.2,
        "nzd_to_aud": 0.9,
    }.items():
        monkeypatch.setattr(settings, name, value)


def offer(mp: str, price: float | None, **kw) -> Offer:
    return Offer(
        offer_id=f"{mp}:1", marketplace=mp, title=kw.pop("title", "item"), price_aud=price, **kw
    )


def test_forwarder_estimate_uses_minimum_charge_for_light_orders():
    # goods 2 x 10 = 20; freight max(15, 0.5 x 2 x 10 = 10) = 15; subtotal 35
    # fee 5% = 1.75; GST 10% of 36.75 = 3.675; total 40.425
    total, parts = forwarder_landed(10.0, 2)
    assert total == 40.42 or total == 40.43
    assert parts == {
        "goods": 20.0,
        "china_domestic": 0.0,
        "forwarder_freight": 15.0,
        "forwarder_fee": 1.75,
        "gst": pytest.approx(3.675, abs=0.01),
    }


def test_forwarder_estimate_scales_with_weight_and_domestic_leg():
    # goods 100; domestic 4; freight 3 kg x 10 = 30; subtotal 134; fee 6.70; GST 14.07; total 154.77
    total, parts = forwarder_landed(100.0, 1, domestic_aud=4.0, weight_kg=3.0)
    assert total == 154.77
    assert parts["forwarder_freight"] == 30.0


def test_china_offers_are_via_forwarder_with_an_estimate():
    o = offer("1688", 10.0, shipping=Shipping(domestic_cny=20.0))
    annotate([o], BRISBANE, qty=2)
    assert o.shipping.delivery == "via_forwarder"
    assert o.landed_basis == "estimated"
    assert o.landed_breakdown["china_domestic"] == 4.0
    assert o.landed_aud > 20.0


def test_stated_shipping_cost_gives_an_exact_landed_cost():
    o = offer("ebay_au", 30.0, shipping=Shipping(delivery="direct", cost_aud=9.5))
    annotate([o], BRISBANE, qty=2)
    assert (o.landed_aud, o.landed_basis) == (69.5, "exact")


def test_unstated_shipping_is_item_only_and_pickup_is_exact():
    amazon, gumtree, ozb = offer("amazon_au", 30.0), offer("gumtree", 40.0), offer("ozbargain", 5.0)
    annotate([amazon, gumtree, ozb], BRISBANE, qty=1)
    assert (amazon.shipping.delivery, amazon.landed_basis) == ("direct", "item_only")
    assert (gumtree.shipping.delivery, gumtree.landed_basis) == ("pickup", "exact")
    assert "AU 4000" in gumtree.shipping.delivery_basis
    assert ozb.shipping.delivery == "unknown"


def test_ozbargain_delivered_title_counts_as_direct():
    o = offer("ozbargain", 20.0, title="Mouse $20 Delivered @ Amazon AU")
    annotate([o], BRISBANE, qty=1)
    assert o.shipping.delivery == "direct"


def test_cheapies_is_converted_from_nzd_and_marked_undeliverable():
    o = offer("cheapies", 100.0, currency="NZD")
    annotate([o], BRISBANE, qty=1)
    assert (o.price_native, o.price_aud, o.shipping.delivery) == (100.0, 90.0, "no")
    assert rank_offers([o], "cheapest", 1) == []


def test_unpriced_offer_has_no_landed_cost():
    o = offer("ebay_au", None, price_native=20.0, currency="USD")
    annotate([o], BRISBANE, qty=1)
    assert o.landed_aud is None


def test_cheapest_ranks_on_landed_cost_not_item_price():
    china = offer("1688", 5.0)  # landed (5 + 15) x 1.05 x 1.1 = 23.10
    local = offer("ebay_au", 12.0, shipping=Shipping(delivery="direct", cost_aud=0.0))
    annotate([china, local], BRISBANE, qty=1)
    assert china.landed_aud == 23.1
    assert [o.marketplace for o in rank_offers([china, local], "cheapest", 1)] == [
        "ebay_au",
        "1688",
    ]
    annotate([china, local], BRISBANE, qty=1)
    bulk_china, bulk_local = (
        offer("1688", 5.0),
        offer("ebay_au", 12.0, shipping=Shipping(cost_aud=0.0)),
    )
    annotate([bulk_china, bulk_local], BRISBANE, qty=20)
    assert [o.marketplace for o in rank_offers([bulk_china, bulk_local], "cheapest", 20)] == [
        "1688",
        "ebay_au",
    ]


def test_unknown_delivery_ranks_after_known_at_equal_cost():
    known = offer("amazon_au", 20.0)
    unknown = offer("ozbargain", 20.0)
    annotate([known, unknown], BRISBANE, qty=1)
    assert [o.marketplace for o in rank_offers([unknown, known], "cheapest", 1)] == [
        "amazon_au",
        "ozbargain",
    ]
