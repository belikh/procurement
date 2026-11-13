"""Lane parsers against response shapes taken from the code's field notes and API docs.

These shapes were not recorded from live runs: no API keys were available.
tests/fixtures/ holds recorded responses for the keyless feeds only. Replace
each sample here with a recording once scripts/live_smoke.py --record has run
with keys.
"""

from procurement.lanes.amazon import parse_amazon
from procurement.lanes.chinese import parse_chinese
from procurement.lanes.ebay import parse_ebay_item
from procurement.lanes.ebay_sold import parse_ebay_sold
from procurement.lanes.facebook import parse_facebook
from procurement.lanes.grocery import parse_grocery
from procurement.lanes.gumtree import parse_gumtree
from procurement.lanes.tmapi import parse_1688_search


def test_ebay_fixed_price_item_with_stated_shipping():
    o = parse_ebay_item(
        {
            "itemId": "v1|1|0",
            "title": "Mouse",
            "price": {"value": "25.00", "currency": "AUD"},
            "shippingOptions": [{"shippingCost": {"value": "8.95", "currency": "AUD"}}],
            "itemLocation": {"country": "AU"},
            "seller": {"username": "s"},
        }
    )
    assert (o.offer_id, o.price_aud, o.currency) == ("ebay_au:v1|1|0", 25.0, "AUD")
    assert (o.shipping.cost_aud, o.shipping.delivery, o.seller_country) == (8.95, "direct", "AU")
    assert o.auction is None


def test_ebay_free_shipping_differs_from_unstated_shipping():
    free = parse_ebay_item(
        {"itemId": "1", "price": {"value": "5", "currency": "AUD"},
         "shippingOptions": [{"shippingCost": {"value": "0.00", "currency": "AUD"}}]}
    )  # fmt: skip
    unstated = parse_ebay_item({"itemId": "2", "price": {"value": "5", "currency": "AUD"}})
    assert free.shipping.cost_aud == 0.0 and free.shipping.delivery == "direct"
    assert unstated.shipping.cost_aud is None and unstated.shipping.delivery == "unknown"


def test_ebay_foreign_currency_is_not_labelled_aud():
    o = parse_ebay_item({"itemId": "3", "price": {"value": "19.99", "currency": "USD"}})
    assert (o.price_aud, o.price_native, o.currency) == (None, 19.99, "USD")
    assert o.seller_country is None


def test_ebay_auction_uses_the_current_bid():
    o = parse_ebay_item(
        {"itemId": "4", "buyingOptions": ["AUCTION"], "bidCount": 3,
         "currentBidPrice": {"value": "12.50", "currency": "AUD"},
         "price": {"value": "1.00", "currency": "AUD"}, "itemEndDate": "2999-01-01T00:00:00Z"}
    )  # fmt: skip
    assert o.price_aud == 12.5
    assert (o.auction.bid_count, o.auction.current_bid_aud) == (3, 12.5)
    assert o.auction.time_left.endswith("h")


def test_chinese_parser_handles_taobao_jd_and_1688_shapes():
    taobao = parse_chinese(
        [{"itemId": "1", "titleOriginal": "锅铲", "price": "2.68"}], "taobao", "q", 10
    )
    jd = parse_chinese([{"skuId": "jd-100", "title": "键盘", "price": 199.0}], "jd", "q", 10)
    w = parse_chinese(
        [{"itemId": "9", "title": "批发", "price": {"min": 1.2, "max": 3.0}}], "1688", "q", 10
    )
    assert (taobao[0].offer_id, taobao[0].price_cny) == ("taobao:1", 2.68)
    assert jd[0].offer_id == "jd:100"
    assert w[0].price_cny == 1.2
    assert all(o.currency == "CNY" and o.price_aud for o in taobao + jd + w)


def test_tmapi_1688_search_reads_items_and_price_keys():
    data = {"data": {"items": [{"product_id": 7, "title": "批发", "price": "¥3.50", "moq": 50}]}}
    (o,) = parse_1688_search(data, "q", 10)
    assert (o.offer_id, o.price_cny, o.moq) == ("1688:7", 3.5, 50)


def test_amazon_drops_items_that_do_not_match_the_query():
    items = [
        {"asin": "B000000001", "title": "Wireless Mouse", "price": {"value": 19.99}, "stars": 4.5},
        {"asin": "B000000002", "title": "HDMI cable", "price": {"value": 9.0}},
        {"asin": "B000000003", "title": "Wireless Mouse Pro", "price": None},
    ]
    offers = parse_amazon(items, "wireless mouse", 10)
    assert [o.offer_id for o in offers] == ["amazon_au:B000000001", "amazon_au:B000000003"]
    assert offers[0].url == "https://www.amazon.com.au/dp/B000000001"
    assert offers[1].price_aud is None


def test_grocery_special_price_and_unit_price():
    items = [
        {"id": "1", "name": "Full Cream Milk 2L", "price": "4.50", "discount_price": "3.90",
         "unit_price": "1.95", "unit": "1L", "is_available": True},
        {"id": "2", "name": "Sunflower Oil", "price": "6.00"},
    ]  # fmt: skip
    (o,) = parse_grocery(items, "coles", "full cream milk", 10)
    assert (o.price_aud, o.regular_price_aud, o.unit_price_aud, o.unit, o.stock) == (
        3.9,
        4.5,
        1.95,
        "1L",
        1,
    )


def test_ebay_sold_rows_are_comps():
    (o,) = parse_ebay_sold([{"itemId": "5", "title": "Mouse", "soldPrice": "14.00"}], "mouse", 10)
    assert (o.kind, o.price_aud, o.stock) == ("comp", 14.0, 0)


def test_facebook_accepts_list_and_index_keyed_dict():
    row = {"id": "1", "title": "Desk", "price": {"amount": "40"}}
    assert parse_facebook({"listings": [row]}, "desk", 10)[0].price_aud == 40.0
    as_dict = parse_facebook(
        {"data": {"listings": {"1": row, "0": {**row, "id": "0"}}}}, "desk", 10
    )
    assert [o.offer_id for o in as_dict] == ["facebook:0", "facebook:1"]


def test_gumtree_price_text():
    (o,) = parse_gumtree([{"id": "8", "title": "Desk", "price": "$1,250"}], "desk", 10)
    assert o.price_aud == 1250.0
