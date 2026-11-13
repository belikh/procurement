import httpx
import pytest
import respx

from procurement import db, tools
from procurement.config import settings
from procurement.models import Offer, ToolFailure

TMAPI = "https://api.tmapi.top"


@pytest.fixture(autouse=True)
def state(monkeypatch):
    monkeypatch.setattr(settings, "tmapi_token", "test-token")
    monkeypatch.setattr(db, "enabled", False)
    tools._offer_memo.clear()


@respx.mock
async def test_tmapi_detail_maps_fields():
    route = respx.get(f"{TMAPI}/taobao/item_detail").mock(
        return_value=httpx.Response(
            200, json={"data": {"title": "锅铲", "price": "¥2.68", "shop_name": "s"}}
        )
    )
    offer = await tools.get_offer_detail("taobao:123")
    assert isinstance(offer, Offer)
    assert offer.price_cny == 2.68
    assert offer.price_aud == round(2.68 * settings.cny_to_aud, 2)
    assert route.calls[0].request.url.params["item_id"] == "123"


@respx.mock
async def test_1688_detail_uses_the_1688_endpoint_and_jd_id_loses_its_prefix():
    r1688 = respx.get(f"{TMAPI}/1688/item_detail").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    rjd = respx.get(f"{TMAPI}/jd/item_detail").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    await tools.get_offer_detail("1688:555")
    await tools.get_offer_detail("jd:jd-777")
    assert r1688.called
    assert rjd.calls[0].request.url.params["item_id"] == "777"


@pytest.mark.parametrize(
    "offer_id", ["taobao:error", "jd:timeout", "ebay_au:missing_key", "pdd:unsupported"]
)
@respx.mock
async def test_diagnostic_id_is_rejected_without_an_upstream_call(offer_id):
    route = respx.get(url__startswith=TMAPI).mock(return_value=httpx.Response(200, json={}))
    result = await tools.get_offer_detail(offer_id)
    assert isinstance(result, ToolFailure) and result.code == "diagnostic_id"
    assert not route.called


@respx.mock
async def test_tmapi_server_error_returns_a_failure():
    respx.get(f"{TMAPI}/jd/item_detail").mock(return_value=httpx.Response(500))
    result = await tools.get_offer_detail("jd:123")
    assert isinstance(result, ToolFailure) and result.code == "upstream_error"


@respx.mock
async def test_tmapi_401_reports_unsubscribed():
    respx.get(f"{TMAPI}/pdd/item_detail").mock(return_value=httpx.Response(401))
    result = await tools.get_offer_detail("pdd:123")
    assert isinstance(result, ToolFailure) and result.code == "unsubscribed"


async def test_missing_tmapi_key_is_named(monkeypatch):
    monkeypatch.setattr(settings, "tmapi_token", None)
    result = await tools.get_offer_detail("taobao:123")
    assert isinstance(result, ToolFailure) and result.code == "missing_key"


async def test_marketplace_without_detail_endpoint_returns_the_remembered_offer():
    assert (await tools.get_offer_detail("gumtree:abc")).code == "not_found"
    remembered = Offer(offer_id="gumtree:abc", marketplace="gumtree", title="desk", price_aud=40.0)
    tools._remember([remembered])
    assert await tools.get_offer_detail("gumtree:abc") == remembered


async def test_id_without_marketplace_is_rejected():
    result = await tools.get_offer_detail("12345")
    assert isinstance(result, ToolFailure) and result.code == "bad_id"
