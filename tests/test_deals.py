from procurement.common import query_relevant
from procurement.lanes.deals import parse_deal_feed, title_price_aud


def test_title_price_takes_first_dollar_amount():
    assert title_price_aud("Mouse $267.75 Delivered (was $399) @ Amazon AU") == 267.75
    assert title_price_aud("Laptop $1,299 @ JB") == 1299.0
    assert title_price_aud("Free coffee @ 7-Eleven") is None


def test_query_relevant_needs_every_term():
    assert query_relevant("full cream milk", "A2 Full Cream Milk 2L")
    assert not query_relevant("full cream milk", "Sunflower Oil")
    assert query_relevant("", "anything")


def test_recorded_ozbargain_feed_parses_to_priced_offers(recorded):
    offers = parse_deal_feed(recorded("ozbargain"), "ozbargain", None, 50)
    assert len(offers) > 5
    assert all(o.marketplace == "ozbargain" and o.offer_id.startswith("ozbargain:") for o in offers)
    assert all(o.url and o.title for o in offers)
    assert any(o.price_aud is not None for o in offers)
    assert any(o.community and o.community.votes_pos is not None for o in offers)


def test_recorded_feed_respects_max_results_and_query(recorded):
    body = recorded("ozbargain")
    assert len(parse_deal_feed(body, "ozbargain", None, 3)) == 3
    assert parse_deal_feed(body, "ozbargain", "zzzqqqxxx-no-such-product", 50) == []
