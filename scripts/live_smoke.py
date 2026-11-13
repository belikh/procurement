"""Live smoke run: one search per marketplace against the real upstreams.

Usage:
    uv run python scripts/live_smoke.py                 # all marketplaces
    uv run python scripts/live_smoke.py ebay_au jd      # a subset
    uv run python scripts/live_smoke.py --record        # also save upstream bodies

Prints one row per marketplace: offers, diagnostics, seconds, first diagnostic.
Each Apify lane starts one actor run, which spends Apify credits.

--record writes each upstream response to tests/fixtures/<marketplace>/NN.json
and a summary to tests/fixtures/MANIFEST.json. Query strings and headers are
dropped, and any configured secret value found in a body is replaced with
"REDACTED".
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from procurement import tools  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GROCERY = {"woolworths", "coles", "aldi"}
QUERY_GENERAL = "wireless mouse"
QUERY_GROCERY = "full cream milk 2l"
DIAGNOSTIC_SUFFIXES = (
    ":error",
    ":timeout",
    ":unsupported",
    ":degraded",
    ":unsubscribed",
    ":missing_key",
    ":no_results",
)
SECRET_ENV_HINTS = ("TOKEN", "KEY", "SECRET", "CERT", "COOKIES", "DATABASE_URL")

_lane: contextvars.ContextVar[str | None] = contextvars.ContextVar("lane", default=None)
_captured: dict[str, list[dict[str, Any]]] = {}


def _secrets() -> list[str]:
    return [
        v
        for k, v in os.environ.items()
        if v and len(v) >= 8 and any(h in k for h in SECRET_ENV_HINTS)
    ]


def _scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        text = text.replace(s, "REDACTED")
    return text


def _install_recorder() -> None:
    original = httpx.AsyncClient.send
    secrets = _secrets()

    async def send(self: httpx.AsyncClient, request: httpx.Request, **kw: Any) -> httpx.Response:
        response = await original(self, request, **kw)
        lane = _lane.get()
        if lane:
            await response.aread()
            _captured.setdefault(lane, []).append(
                {
                    "method": request.method,
                    "url": str(request.url.copy_with(query=None)),
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "body": _scrub(response.text, secrets),
                }
            )
        return response

    httpx.AsyncClient.send = send  # type: ignore[method-assign]


def _is_diagnostic(offer: Any) -> bool:
    if getattr(offer, "kind", "offer") != "offer":
        return True
    return str(offer.offer_id).endswith(DIAGNOSTIC_SUFFIXES)


def _all_marketplaces() -> list[str]:
    names = getattr(tools, "ALL_MARKETPLACES", None)
    if names:
        return list(names)
    return [
        "taobao",
        "tmall",
        "1688",
        "jd",
        "pdd",
        "aliexpress",
        "ebay_au",
        "ebay_sold",
        "amazon_au",
        "gumtree",
        "facebook",
        "woolworths",
        "coles",
        "aldi",
        "ozbargain",
        "cheapies",
    ]


async def _run_lane(mp: str) -> dict[str, Any]:
    query = QUERY_GROCERY if mp in GROCERY else QUERY_GENERAL
    token = _lane.set(mp)
    t0 = time.monotonic()
    try:
        offers = await tools.search_offers(query=query, marketplaces=[mp], max_results=10)
        error = None
    except Exception as e:  # the tool should never raise; report it if it does
        offers, error = [], f"RAISED {type(e).__name__}: {e}"
    finally:
        _lane.reset(token)
    elapsed = round(time.monotonic() - t0, 1)
    diags = [o for o in offers if _is_diagnostic(o)]
    real = [o for o in offers if not _is_diagnostic(o)]
    if error:
        outcome = "raised"
    elif real:
        outcome = "offers"
    elif diags:
        outcome = "diagnostic"
    else:
        outcome = "empty"
    return {
        "marketplace": mp,
        "query": query,
        "outcome": outcome,
        "offers": len(real),
        "diagnostics": len(diags),
        "seconds": elapsed,
        "first_diagnostic": error or (diags[0].title[:120] if diags else None),
        "priced": sum(1 for o in real if o.price_aud is not None),
        "delivery": _delivery_counts(real),
    }


def _delivery_counts(offers: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in offers:
        status = getattr(o.shipping, "delivery", "n/a")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _write_fixtures(rows: list[dict[str, Any]]) -> None:
    for lane, calls in _captured.items():
        d = FIXTURES / lane
        d.mkdir(parents=True, exist_ok=True)
        for i, call in enumerate(calls):
            (d / f"{i:02d}.json").write_text(json.dumps(call, ensure_ascii=False, indent=1))
    manifest = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lanes": rows,
        "calls": {lane: len(calls) for lane, calls in _captured.items()},
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("marketplaces", nargs="*")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()

    if args.record:
        _install_recorder()
    wanted = args.marketplaces or _all_marketplaces()

    t0 = time.monotonic()
    rows = [await _run_lane(mp) for mp in wanted]
    total = round(time.monotonic() - t0, 1)

    print(
        f"{'marketplace':<16}{'outcome':<12}{'offers':>7}{'priced':>7}{'diag':>6}{'sec':>7}  note"
    )
    for r in rows:
        print(
            f"{r['marketplace']:<16}{r['outcome']:<12}{r['offers']:>7}{r['priced']:>7}"
            f"{r['diagnostics']:>6}{r['seconds']:>7}  {r['first_diagnostic'] or ''}"
        )
    with_offers = sum(1 for r in rows if r["outcome"] == "offers")
    silent = [r["marketplace"] for r in rows if r["outcome"] in ("empty", "raised")]
    print(f"\n{with_offers}/{len(rows)} marketplaces returned offers in {total}s")
    print(f"no offers and no diagnostic: {', '.join(silent) if silent else 'none'}")

    if args.record:
        _write_fixtures(rows)
        print(f"fixtures written to {FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
