from procurement.models import Offer, Shipping, diag
from procurement.ranking import rank_offers


def offer(oid: str, price: float | None = None, **kw) -> Offer:
    return Offer(offer_id=oid, marketplace=oid.split(":", 1)[0], title=oid, price_aud=price, **kw)


def ids(offers: list[Offer]) -> list[str]:
    return [o.offer_id for o in offers]


def test_cheapest_sorts_by_price_times_qty_plus_shipping():
    a = offer("ebay_au:a", 10.0, shipping=Shipping(intl_estimate_aud=15.0))
    b = offer("ebay_au:b", 12.0)
    assert ids(rank_offers([a, b], "cheapest", 1)) == ["ebay_au:b", "ebay_au:a"]
    assert ids(rank_offers([a, b], "cheapest", 10)) == ["ebay_au:a", "ebay_au:b"]


def test_cheapest_uses_unit_price_for_grocery():
    two_litre = offer("coles:2l", 4.50, unit_price_aud=2.25)
    one_litre = offer("coles:1l", 3.10, unit_price_aud=3.10)
    assert ids(rank_offers([one_litre, two_litre], "cheapest", 1)) == ["coles:2l", "coles:1l"]


def test_fastest_sorts_by_latest_eta_then_price():
    slow = offer("1688:s", 5.0, shipping=Shipping(eta_days=[10, 25]))
    fast = offer("ebay_au:f", 50.0, shipping=Shipping(eta_days=[3, 7]))
    assert ids(rank_offers([slow, fast], "fastest", 1)) == ["ebay_au:f", "1688:s"]


def test_best_value_prefers_cheaper_at_equal_trust_and_eta():
    cheap = offer("ebay_au:c", 20.0)
    dear = offer("ebay_au:d", 150.0)
    assert ids(rank_offers([dear, cheap], "best_value", 1)) == ["ebay_au:c", "ebay_au:d"]


def test_offers_below_moq_rank_last_in_every_sort():
    wholesale = offer("1688:w", 1.0, moq=100, shipping=Shipping(eta_days=[1, 1]))
    retail = offer("ebay_au:r", 20.0, shipping=Shipping(eta_days=[3, 7]))
    for sort in ("cheapest", "fastest", "best_value"):
        assert ids(rank_offers([wholesale, retail], sort, 1)) == ["ebay_au:r", "1688:w"], sort
    assert ids(rank_offers([wholesale, retail], "cheapest", 100)) == ["1688:w", "ebay_au:r"]


def test_diagnostics_and_comps_are_not_ranked():
    real = offer("ebay_au:real", 150.0)
    comp = offer("ebay_sold:1", 5.0, kind="comp")
    for sort in ("cheapest", "fastest", "best_value"):
        assert ids(rank_offers([diag("jd", "timeout", "t"), comp, real], sort, 1)) == [
            "ebay_au:real"
        ]
