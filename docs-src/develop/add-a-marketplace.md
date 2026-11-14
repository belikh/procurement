---
title: Add a marketplace
summary: Write a lane for a new source and register it, so that search_offers and health pick it up.
order: 20
icon: plus
audience: developers
status: draft
---

A [[term:Lane]] is two functions and one registry entry. The orchestrator in `procurement/lanes/base.py` handles the deadline, the missing key and the diagnostics.

## Steps

1. Create `procurement/lanes/example.py` with a parser. The parser maps the source's items to `Offer` objects and makes no HTTP call, so a test can feed it a recorded reply.

   ```python title="procurement/lanes/example.py"
   from typing import Any

   from procurement.common import float_or_none
   from procurement.models import Offer, Seller, Shipping


   def parse_example(items: list[dict[str, Any]], max_results: int) -> list[Offer]:
       return [
           Offer(
               offer_id=f"example:{it['id']}",
               marketplace="example",
               title=str(it["title"]),
               url=it.get("url"),
               price_aud=float_or_none(it.get("price")),
               seller=Seller(shop_name=it.get("seller")),
               shipping=Shipping(eta_days=[2, 6], method="Example post"),
           )
           for it in items[:max_results]
       ]
   ```

2. Add the search function. Raise `LaneError` with a diagnostic code for every failure you can name.

   ```python title="procurement/lanes/example.py, continued"
   import httpx

   from procurement.config import settings
   from procurement.http import LaneError, request_retry
   from procurement.lanes.base import SearchCtx


   async def search_example(ctx: SearchCtx) -> list[Offer]:
       async with httpx.AsyncClient(timeout=settings.default_timeout_s) as client:
           r = await request_retry(
               client, "GET", "https://api.example.org/search", params={"q": ctx.query}
           )
       if r.status_code != 200:
           raise LaneError("upstream_error", f"example returned HTTP {r.status_code}")
       return parse_example(r.json()["items"], ctx.max_results)
   ```

3. Register the lane in `_SPECS` of `procurement/lanes/__init__.py`.

   ```python title="procurement/lanes/__init__.py"
   LaneSpec(
       "example",
       example.search_example,
       "Example search API",
       budget_s=15,
   ),
   ```

4. If the lane needs a key, add the setting to `procurement/config.py` and to `.env.example`. Pass a `missing` function that returns the variable's name when it is unset. `tests/test_env_docs.py` fails when the two files disagree.

5. If the source does not state delivery for each offer, add a rule for the marketplace to `_RULES` in `procurement/landed.py`. Without a rule the offers get `delivery: unknown`.

6. Add a parser test to `tests/test_lanes.py`, then run the checks.

   ```sh title="Check"
   uv run ruff check . && uv run pyright procurement server.py && uv run pytest
   ```

## LaneSpec fields

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | required | The marketplace name a caller passes. |
| `run` | required | `async (SearchCtx) -> list[Offer]`. |
| `source` | required | The API or actor, as `health` shows it. |
| `missing` | no requirement | Returns the name of the unset key, or `None` when the lane can run. |
| `budget_s` | `10` | The longest the lane may run, in seconds. |
| `group` | none | Lanes with the same group share one upstream run. |
| `status` | `unverified` | `verified`, `unverified`, `degraded` or `unsupported`. |
| `reliability` | `aggregator` | `authoritative`, `aggregator` or `best_effort`. Copied to diagnostics. |

## SearchCtx fields

| Field | Meaning |
| --- | --- |
| `query`, `query_zh` | The query. `ctx.china_query` is `query_zh`, or `query` when there is none. |
| `max_results`, `sort`, `qty` | The arguments of the call. |
| `location` | The destination: `country`, `postcode`, `lat`, `lng`, `radius_km`. |
| `est_weight_kg` | The item weight, when given. |
| `ebay_auctions`, `ebay_seller_scope` | The eBay options. |
| `ctx.remaining()` | Seconds left before the search deadline. |
| `ctx.wait_s(cap)` | Seconds one upstream call may take: the cap, or the time left less 3 seconds. At least 5. |

## Apify actor lanes

Call `apify_run_sync(actor, run_input, timeout_s=ctx.wait_s(85))` from `procurement/http.py`. It sends the request once, because each call starts a paid run. It raises `LaneError` with `missing_key`, `upstream_error` or `quota`.

Set the lane to `verified` only after `scripts/live_smoke.py` returned offers for it.

:::see-also
- [[develop/verify-a-lane]]
- [[concepts/how-a-search-runs]]
:::
