"""Gumtree AU via a hosted Apify actor.

Degraded since 2026-09-02: Gumtree AU sits behind Akamai Bot Manager. The
crawlerbros actor needs residential proxies, which the free Apify plan lacks
(runs succeed and return 0 items). Two ways to restore it: an Apify plan with
residential proxies, or GUMTREE_COOKIES exported from a real browser session.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import httpx

from procurement.config import settings
from procurement.http import LaneError, actor_path, split_envelopes
from procurement.lanes.base import SearchCtx
from procurement.models import Offer, Seller, Shipping

API = "https://api.apify.com/v2"
POLL_S = 2
_FINISHED = frozenset({"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"})


def missing_gumtree() -> str | None:
    return None if settings.apify_token else "APIFY_TOKEN"


def parse_gumtree(items: list[dict[str, Any]], query: str, max_results: int) -> list[Offer]:
    offers: list[Offer] = []
    for it in items[:max_results]:
        try:
            text = str(it.get("price") or it.get("price_aud") or "0")
            price_aud = float(text.replace("$", "").replace(",", "").strip() or 0) or None
        except ValueError:
            price_aud = None
        images = it.get("images")
        offers.append(
            Offer(
                offer_id=f"gumtree:{it.get('id') or it.get('url') or 'unknown'}",
                marketplace="gumtree",
                title=it.get("title") or query,
                url=it.get("url"),
                image=(images or [None])[0] if isinstance(images, list) else it.get("image"),  # pyright: ignore[reportUnknownVariableType]
                price_aud=price_aud,
                seller=Seller(shop_name=it.get("seller_name") or it.get("seller")),
                shipping=Shipping(eta_days=[2, 5], method="Gumtree local"),
                source_reliability="best_effort",
                raw=it if settings.include_raw else None,
            )
        )
    return offers


async def search_gumtree(ctx: SearchCtx) -> list[Offer]:
    if not settings.apify_token:
        raise LaneError("missing_key", "APIFY_TOKEN is not set")
    if not settings.gumtree_cookies:
        raise LaneError(
            "degraded",
            "Gumtree AU blocks the actor (Akamai). Set GUMTREE_COOKIES from a browser session, "
            "or use an Apify plan with residential proxies",
            {"degraded": True},
        )
    token = {"token": settings.apify_token}
    start_url = (
        f"https://www.gumtree.com.au/s-{ctx.query.replace(' ', '-')}/k0q0?sortByName=dateDesc"
    )
    run_id: str | None = None
    finished = False
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(
                f"{API}/acts/{actor_path(settings.gumtree_apify_actor)}/runs",
                params=token,
                json={
                    "startUrls": [{"url": start_url}],
                    "maxItems": ctx.max_results,
                    "includeListingDetails": False,
                },
            )
            if r.status_code not in (200, 201):
                raise LaneError(
                    "upstream_error",
                    f"actor start returned HTTP {r.status_code}",
                    {"error": r.text[:300]},
                )
            run = r.json().get("data") or {}
            run_id = run.get("id")
            dataset_id = run.get("defaultDatasetId")
            if not run_id:
                raise LaneError("upstream_error", "actor start returned no run id")
            status = run.get("status")
            while status not in _FINISHED:
                await asyncio.sleep(POLL_S)
                s = await client.get(f"{API}/actor-runs/{run_id}", params=token)
                s.raise_for_status()
                data = s.json().get("data") or {}
                status = data.get("status")
                dataset_id = data.get("defaultDatasetId") or dataset_id
            finished = True
            if status != "SUCCEEDED" or not dataset_id:
                raise LaneError("upstream_error", f"actor run ended with status {status}")
            d = await client.get(
                f"{API}/datasets/{dataset_id}/items", params={**token, "limit": ctx.max_results}
            )
            d.raise_for_status()
            body = d.json()
            items, actor_err = split_envelopes(
                body if isinstance(body, list) else body.get("items", [])
            )
            if not items and actor_err:
                raise LaneError("upstream_error", f"actor error: {actor_err}", {"error": actor_err})
            return parse_gumtree(items, ctx.query, ctx.max_results)
        finally:
            # A run left going after a timeout keeps spending credits.
            if run_id and not finished:
                async with httpx.AsyncClient(timeout=5) as abort_client:
                    with contextlib.suppress(httpx.HTTPError, asyncio.CancelledError):
                        await asyncio.shield(
                            abort_client.post(f"{API}/actor-runs/{run_id}/abort", params=token)
                        )
