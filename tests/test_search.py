"""search_offers end to end, with HTTP mocked."""

import httpx
import pytest
import respx

from procurement import db, tools
from procurement.config import settings
from procurement.lanes import ALL_MARKETPLACES

APIFY = "https://api.apify.com/v2/acts"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(db, "enabled", False)
    tools._offer_memo.clear()


def codes(offers):
    return {o.marketplace: o.diagnostic_code for o in offers if o.kind == "diagnostic"}


@respx.mock
async def test_with_no_keys_every_marketplace_answers():
    respx.get(settings.ozbargain_feed_url).mock(return_value=httpx.Response(503))
    respx.get(settings.cheapies_feed_url).mock(return_value=httpx.Response(503))
    offers = await tools.search_offers(query="mouse")
    got = codes(offers)
    assert set(got) == set(ALL_MARKETPLACES)
    assert got["ebay_au"] == "missing_key"
    assert got["amazon_au"] == "missing_key"
    assert got["tmall"] == "missing_key"
    assert got["aliexpress"] == "unsupported"
    assert got["pdd"] == "unsupported"
    assert got["ozbargain"] == "upstream_error"


async def test_unknown_marketplace_gets_a_diagnostic():
    offers = await tools.search_offers(query="mouse", marketplaces=["bunnings", "pdd"])
    assert codes(offers) == {"bunnings": "unsupported", "pdd": "unsupported"}


@respx.mock
async def test_gumtree_reports_degraded_without_cookies(monkeypatch):
    monkeypatch.setattr(settings, "apify_token", "t")
    offers = await tools.search_offers(query="mouse", marketplaces=["gumtree"])
    assert [o.offer_id for o in offers] == ["gumtree:degraded"]


@respx.mock
async def test_offers_come_first_then_comps_then_diagnostics(monkeypatch):
    monkeypatch.setattr(settings, "apify_token", "t")
    respx.post(f"{APIFY}/junglee~free-amazon-product-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            201,
            json=[
                {
                    "asin": "B000000001",
                    "title": "Wireless Mouse",
                    "price": {"value": 19.99, "currency": "AUD"},
                },
                {"asin": "B000000002", "title": "USB cable", "price": {"value": 5.0}},
            ],
        )
    )
    respx.post(f"{APIFY}/caffein.dev~ebay-sold-listings/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200, json=[{"itemId": "9", "title": "mouse", "soldPrice": "12.5"}]
        )
    )
    respx.post(f"{APIFY}/zen-studio~jd-com-search-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200, json=[{"error": "free_tier_exhausted", "message": "10 free runs used"}]
        )
    )
    offers = await tools.search_offers(
        query="wireless mouse", marketplaces=["jd", "ebay_sold", "amazon_au"]
    )
    assert [(o.offer_id, o.kind) for o in offers] == [
        ("amazon_au:B000000001", "offer"),
        ("ebay_sold:9", "comp"),
        ("jd:error", "diagnostic"),
    ]
    assert offers[-1].diagnostic_code == "quota"
    assert offers[0].price_aud == 19.99


@respx.mock
async def test_taobao_run_is_shared_and_tmall_items_are_labelled(monkeypatch):
    monkeypatch.setattr(settings, "apify_token", "t")
    route = respx.post(f"{APIFY}/zen-studio~taobao-search-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"itemId": "1", "title": "锅铲", "price": "2.68", "isTmall": False},
                {"itemId": "2", "title": "锅铲", "price": "9.90", "isTmall": True},
            ],
        )
    )
    offers = await tools.search_offers(
        query="spatula", query_zh="锅铲", marketplaces=["taobao", "tmall"]
    )
    assert route.call_count == 1
    assert (
        b"\\u9505\\u94f2" in route.calls[0].request.content
        or "锅铲".encode() in route.calls[0].request.content
    )
    assert sorted(o.offer_id for o in offers) == ["taobao:1", "tmall:2"]
    assert all(o.currency == "CNY" and o.price_aud for o in offers)


@respx.mock
async def test_failed_search_is_not_cached_and_good_search_is(monkeypatch):
    saved = []

    async def fake_set(*args):
        saved.append(args)

    monkeypatch.setattr(db, "set_cached", fake_set)
    respx.get(settings.ozbargain_feed_url).mock(return_value=httpx.Response(503))
    await tools.search_offers(query="mouse", marketplaces=["ozbargain"])
    assert saved == []
    await tools.search_offers(query="mouse", marketplaces=["pdd"])
    assert len(saved) == 1


def test_cache_key_changes_with_inputs():
    base = db.make_cache_key("mouse", ["ebay_au"], "cheapest", 1, "AU", 10)
    assert base == db.make_cache_key(" Mouse ", ["ebay_au"], "cheapest", 1, "AU", 10)
    assert base != db.make_cache_key("mouse", ["ebay_au"], "fastest", 1, "AU", 10)
    assert base != db.make_cache_key(
        "mouse", ["ebay_au"], "cheapest", 1, "AU", 10, ebay_auctions=True
    )
