"""OzBargain and Cheapies deal feeds (official RSS, no key)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from procurement.config import settings
from procurement.http import LaneError, request_retry
from procurement.lanes.base import SearchCtx
from procurement.models import CommunitySignal, Offer, Seller, Shipping

# The ozb: namespace both sites share (same platform software)
_OZB_NS = {"ozb": "https://www.ozbargain.com.au", "media": "http://search.yahoo.com/mrss/"}

_PRICE_RE = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def _int_attr(element: ET.Element, attr: str) -> int | None:
    value = element.get(attr)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def title_price_aud(title: str) -> float | None:
    """OzBargain embeds the price in the title, e.g. '... $267.75 Delivered @ Amazon AU'.

    First $amount wins — the site's convention puts the headline price first.
    """
    m = _PRICE_RE.search(title)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def parse_deal_feed(
    xml_text: str, marketplace: str, query: str | None, max_results: int
) -> list[Offer]:
    """Parse an OzBargain/Cheapies RSS feed into Offers.

    No scraping — this is the sites' own published feed. ozb:meta carries
    votes/clicks/expiry; <category> carries cat/tag/brand/product taxonomy.
    When `query` is set, offers are filtered client-side on title/category
    match (feeds are ~100 items; filtering locally is cheap and ToS-clean).
    """
    root = ET.fromstring(xml_text)
    offers: list[Offer] = []
    terms = list((query or "").lower().split()) if query else None

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()

        cats: list[str] = []
        brand: str | None = None
        tags: list[str] = []
        for cat in item.findall("category"):
            text = (cat.text or "").strip()
            domain = cat.get("domain") or ""
            cats.append(text)
            if "/brand/" in domain:
                brand = text
            elif "/tag/" in domain or "/cat/" in domain:
                tags.append(text)

        meta = item.find("ozb:meta", _OZB_NS)
        votes_pos = votes_neg = comment_count = click_count = None
        expiry = None
        image = None
        goto = None
        if meta is not None:
            votes_pos = _int_attr(meta, "votes-pos")
            votes_neg = _int_attr(meta, "votes-neg")
            comment_count = _int_attr(meta, "comment-count")
            click_count = _int_attr(meta, "click-count")
            expiry = meta.get("expiry")
            image = meta.get("image")
            goto = meta.get("link")  # affiliate /goto/ link

        if image is None:
            thumb = item.find("media:thumbnail", _OZB_NS)
            if thumb is not None:
                image = thumb.get("url")

        # guid isPermaLink=false carries the node id, e.g. '973515 at https://...'
        guid = (item.findtext("guid") or "").split(" at ")[0].strip()

        # client-side filter: title/categories/brand/tags must contain every term
        if terms:
            haystack = " ".join([title, *cats, brand or "", *(tags or [])]).lower()
            if not all(t in haystack for t in terms):
                continue

        offers.append(
            Offer(
                offer_id=f"{marketplace}:{guid or link}",
                marketplace=marketplace,
                title=title,
                url=link,
                image=image,
                price_aud=title_price_aud(title),
                currency="AUD" if marketplace == "ozbargain" else "NZD",
                shipping=Shipping(eta_days=[0, 0], method="Deal listing — see merchant"),
                seller=Seller(
                    shop_name=(item.findtext("{http://purl.org/dc/elements/1.1/}creator") or None)
                ),
                community=CommunitySignal(
                    votes_pos=votes_pos,
                    votes_neg=votes_neg,
                    comment_count=comment_count,
                    click_count=click_count,
                    expiry=expiry,
                    brand=brand,
                    tags=tags or None,
                ),
                source_reliability="authoritative",  # the site's own published feed
                raw={"description": description, "goto": goto} if settings.include_raw else None,
            )
        )
        if len(offers) >= max_results:
            break
    return offers


USER_AGENT = "procurement-mcp/0.1 (+https://jupiter.au)"
# Parse the whole feed (about 100 items) so callers can filter before they cut.
FEED_CAP = 500


async def fetch_deals(
    feed_url: str, marketplace: str, query: str | None, max_results: int
) -> list[Offer]:
    """Fetch and parse a deal feed. query=None returns the latest deals unfiltered."""
    async with httpx.AsyncClient(
        timeout=settings.default_timeout_s, follow_redirects=True
    ) as client:
        r = await request_retry(client, "GET", feed_url, headers={"User-Agent": USER_AGENT})
    if r.status_code != 200:
        raise LaneError("upstream_error", f"feed returned HTTP {r.status_code}")
    try:
        return parse_deal_feed(r.text, marketplace, query, max_results)
    except ET.ParseError as e:
        raise LaneError("upstream_error", f"feed is not valid XML: {e}") from e


async def search_ozbargain(ctx: SearchCtx) -> list[Offer]:
    return await fetch_deals(settings.ozbargain_feed_url, "ozbargain", ctx.query, ctx.max_results)


async def search_cheapies(ctx: SearchCtx) -> list[Offer]:
    return await fetch_deals(settings.cheapies_feed_url, "cheapies", ctx.query, ctx.max_results)
