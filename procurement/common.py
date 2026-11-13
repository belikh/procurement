"""Small helpers shared by the lanes."""

from __future__ import annotations

from typing import Any

from procurement.config import settings


def has_any_key(keys: list[str | None]) -> bool:
    return any(k for k in keys if k)


def cny_to_aud(cny: float | None) -> float | None:
    if cny is None:
        return None
    return round(cny * settings.cny_to_aud, 2)


def float_or_none(v: Any) -> float | None:
    try:
        return round(float(str(v).replace("$", "").replace(",", "").strip()), 2) or None
    except (TypeError, ValueError):
        return None


def query_relevant(query: str, *texts: str | None) -> bool:
    """Loose relevance gate for search lanes whose upstream search can drift
    (grocery catalogues fuzzy-match, Amazon pads generic terms).

    Every whitespace term of the query must appear in at least ONE of the
    candidate texts (title/brand/category). 'full cream milk' accepts
    'Full Cream Milk 2L' and 'A2 Full Cream Milk' but rejects
    'Sunflower Oil' or 'Mega Roulette'. A bare single term ('milk') just
    needs that substring present. Case-insensitive substring, not
    token-exact — grocery titles carry pack sizes and descriptors.
    """
    if not query:
        return True
    terms = [t.lower() for t in query.split() if t]
    if not terms:
        return True
    haystack = " ".join((t or "").lower() for t in texts)
    return all(t in haystack for t in terms)
