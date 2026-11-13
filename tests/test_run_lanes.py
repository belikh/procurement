"""The orchestrator, driven by fake lanes. No HTTP."""

import asyncio
import time

from procurement.http import LaneError
from procurement.lanes.base import LaneSpec, SearchCtx, run_lanes
from procurement.models import Offer, diag


def offer(mp: str, n: int = 1) -> Offer:
    return Offer(offer_id=f"{mp}:{n}", marketplace=mp, title="t", price_aud=1.0)


def ctx(deadline_s: float = 5) -> SearchCtx:
    return SearchCtx(query="mouse", deadline=time.monotonic() + deadline_s)


def lane(name: str, run, **kw) -> LaneSpec:
    return LaneSpec(name, run, "fake", **kw)


async def test_hung_lane_times_out_without_delaying_the_others():
    cancelled = asyncio.Event()

    async def hang(_):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return []

    async def quick(_):
        return [offer("fast")]

    t0 = time.monotonic()
    out = await run_lanes([lane("slow", hang), lane("fast", quick)], ctx(0.2))
    assert time.monotonic() - t0 < 0.5
    assert cancelled.is_set()
    assert out["slow"].code == "timeout" and out["slow"].offers == []
    assert out["slow"].diagnostic.offer_id == "slow:timeout"
    assert out["fast"].code == "ok" and len(out["fast"].offers) == 1


async def test_lane_budget_applies_when_shorter_than_the_deadline():
    async def hang(_):
        await asyncio.sleep(30)
        return []

    t0 = time.monotonic()
    out = await run_lanes([lane("slow", hang, budget_s=0.1)], ctx(5))
    assert time.monotonic() - t0 < 0.5
    assert out["slow"].code == "timeout"


async def test_exception_becomes_upstream_error():
    async def boom(_):
        raise ValueError("bad json")

    out = await run_lanes([lane("x", boom)], ctx())
    assert out["x"].code == "upstream_error"
    assert out["x"].diagnostic.offer_id == "x:error"
    assert "bad json" in out["x"].diagnostic.title


async def test_lane_error_keeps_its_code():
    async def quota(_):
        raise LaneError("quota", "free runs used")

    async def unsubscribed(_):
        raise LaneError("unsubscribed", "subscribe first")

    out = await run_lanes([lane("a", quota), lane("b", unsubscribed)], ctx())
    assert out["a"].code == "quota"
    assert out["b"].diagnostic.offer_id == "b:unsubscribed"


async def test_missing_key_lane_is_never_started():
    calls = []

    async def run(_):
        calls.append(1)
        return [offer("x")]

    out = await run_lanes([lane("x", run, missing=lambda: "SOME_KEY")], ctx())
    assert calls == []
    assert out["x"].code == "missing_key"
    assert "SOME_KEY" in out["x"].diagnostic.title


async def test_empty_result_becomes_no_results():
    async def nothing(_):
        return []

    out = await run_lanes([lane("x", nothing)], ctx())
    assert out["x"].code == "no_results"
    assert out["x"].diagnostic.kind == "diagnostic"


async def test_grouped_lanes_share_one_run_and_split_by_marketplace():
    calls = []

    async def shared(_):
        calls.append(1)
        return [offer("taobao", 1), offer("tmall", 2), offer("taobao", 3)]

    specs = [lane("taobao", shared, group="g"), lane("tmall", shared, group="g")]
    out = await run_lanes(specs, ctx())
    assert calls == [1]
    assert [o.offer_id for o in out["taobao"].offers] == ["taobao:1", "taobao:3"]
    assert [o.offer_id for o in out["tmall"].offers] == ["tmall:2"]


async def test_lane_supplied_diagnostic_is_used_for_its_marketplace():
    async def shared(_):
        return [offer("taobao"), diag("tmall", "unsupported", "not flagged")]

    specs = [lane("taobao", shared, group="g"), lane("tmall", shared, group="g")]
    out = await run_lanes(specs, ctx())
    assert out["taobao"].code == "ok"
    assert out["tmall"].code == "unsupported"


async def test_every_requested_lane_has_exactly_one_outcome():
    async def ok(_):
        return [offer("a")]

    async def boom(_):
        raise RuntimeError("x")

    async def nothing(_):
        return []

    specs = [lane("a", ok), lane("b", boom), lane("c", nothing), lane("d", ok, missing=lambda: "K")]
    out = await run_lanes(specs, ctx())
    assert list(out) == ["a", "b", "c", "d"]
    for outcome in out.values():
        assert bool(outcome.offers) != bool(outcome.diagnostic)
