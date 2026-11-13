from procurement.http import split_envelopes


def test_quota_envelope_is_removed_and_reported():
    items, err = split_envelopes([{"error": "free_tier_exhausted", "message": "10 free runs used"}])
    assert items == []
    assert err == "10 free runs used"


def test_envelope_mixed_with_items_keeps_items():
    items, err = split_envelopes([{"error": "x"}, {"itemId": "1", "title": "a"}])
    assert items == [{"itemId": "1", "title": "a"}]
    assert err == "x"


def test_item_with_error_field_and_product_id_is_kept():
    item = {"error": "partial", "asin": "B000000001"}
    assert split_envelopes([item]) == ([item], None)


def test_non_list_input_gives_empty():
    assert split_envelopes({"error": "boom"}) == ([], None)
    assert split_envelopes(None) == ([], None)


def test_message_is_truncated_to_200_chars():
    _, err = split_envelopes([{"error": "e", "message": "m" * 500}])
    assert err is not None and len(err) == 200
