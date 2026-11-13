"""Lane registry types and the orchestrator that runs lanes under one deadline."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from procurement.config import settings
from procurement.http import LaneError
from procurement.models import DiagCode, Location, Offer, Reliability, diag

LaneStatus = Literal["verified", "unverified", "degraded", "unsupported"]


@dataclass
class SearchCtx:
    """One search request, shared by every lane it runs."""

    query: str
    max_results: int = 10
    sort: str = "best_value"
    qty: int = 1
    query_zh: str | None = None
    ebay_auctions: bool = False
    ebay_seller_scope: str = "domestic"
    location: Location = field(default_factory=Location.default)
    est_weight_kg: float | None = None
    deadline: float = field(default_factory=lambda: time.monotonic() + settings.deadline_s)

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def wait_s(self, cap: float) -> float:
        """Seconds an upstream call may take: the cap, or what is left less a 3 s margin."""
        return max(5.0, min(cap, self.remaining() - 3))

    @property
    def china_query(self) -> str:
        return self.query_zh or self.query


def _no_requirement() -> str | None:
    return None


@dataclass(frozen=True)
class LaneSpec:
    """One marketplace a caller can request.

    missing() returns the name of the unset key, or None when the lane can run.
    Lanes with the same group share one upstream run; each offer's marketplace
    field says which lane it belongs to.
    """

    name: str
    run: Callable[[SearchCtx], Awaitable[list[Offer]]]
    source: str
    missing: Callable[[], str | None] = _no_requirement
    budget_s: float = 10
    group: str | None = None
    status: LaneStatus = "unverified"
    reliability: Reliability = "aggregator"

    @property
    def group_key(self) -> str:
        return self.group or self.name


@dataclass
class LaneOutcome:
    name: str
    offers: list[Offer]
    diagnostic: Offer | None
    elapsed_s: float

    @property
    def code(self) -> str:
        return self.diagnostic.diagnostic_code or "upstream_error" if self.diagnostic else "ok"


@dataclass
class _Attempt:
    offers: list[Offer]
    code: DiagCode | None = None
    detail: str = ""
    raw: dict[str, Any] | None = None
    elapsed_s: float = 0.0


async def _attempt(spec: LaneSpec, ctx: SearchCtx) -> _Attempt:
    t0 = time.monotonic()
    budget = min(spec.budget_s, ctx.remaining())
    result = _Attempt(offers=[])
    try:
        async with asyncio.timeout(budget):
            result.offers = await spec.run(ctx)
    except (TimeoutError, httpx.TimeoutException):
        result.code, result.detail = "timeout", f"no reply within {budget:.0f} s"
    except LaneError as e:
        result.code, result.detail, result.raw = e.code, e.detail, e.raw
    except Exception as e:
        result.code, result.detail = "upstream_error", f"{type(e).__name__}: {e}"[:300]
        result.raw = {"error": str(e)[:300]}
    result.elapsed_s = round(time.monotonic() - t0, 2)
    return result


async def run_lanes(specs: Sequence[LaneSpec], ctx: SearchCtx) -> dict[str, LaneOutcome]:
    """Run the requested lanes at once and return one outcome per lane name.

    Every outcome holds offers or exactly one diagnostic. A lane with a missing
    key is not started. A lane still running at the deadline is cancelled and
    reported as a timeout.
    """
    groups: dict[str, list[LaneSpec]] = {}
    for spec in specs:
        groups.setdefault(spec.group_key, []).append(spec)

    outcomes: dict[str, LaneOutcome] = {}
    runnable: list[list[LaneSpec]] = []
    for members in groups.values():
        missing = members[0].missing()
        if missing:
            for spec in members:
                d = diag(
                    spec.name,
                    "missing_key",
                    f"not configured: set {missing}",
                    reliability=spec.reliability,
                )
                outcomes[spec.name] = LaneOutcome(spec.name, [], d, 0.0)
        else:
            runnable.append(members)

    attempts = await asyncio.gather(*(_attempt(members[0], ctx) for members in runnable))
    for members, attempt in zip(runnable, attempts, strict=True):
        for spec in members:
            mine = [o for o in attempt.offers if o.marketplace == spec.name]
            real = [o for o in mine if o.kind != "diagnostic"]
            own_diag = next((o for o in mine if o.kind == "diagnostic"), None)
            if real:
                diagnostic = None
            elif attempt.code:
                diagnostic = diag(
                    spec.name,
                    attempt.code,
                    attempt.detail,
                    reliability=spec.reliability,
                    raw=attempt.raw,
                )
            elif own_diag:
                diagnostic = own_diag
            else:
                diagnostic = diag(
                    spec.name,
                    "no_results",
                    f"no match for {ctx.query!r}",
                    reliability=spec.reliability,
                )
            outcomes[spec.name] = LaneOutcome(spec.name, real, diagnostic, attempt.elapsed_s)
    return {spec.name: outcomes[spec.name] for spec in specs}
