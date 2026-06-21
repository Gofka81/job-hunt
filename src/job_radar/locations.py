"""Deterministic location normalisation. Maps a raw free-text job location
("Farringdon, Central London", "Glasgow, Scotland") to a canonical UK city
("London", "Glasgow") using an offline GB city reference from geonamescache —
no API, no LLM. Falls back to Remote / region / UK / Unknown.

clean_location() is the only thing callers need; the reference is built once
and cached.
"""

from __future__ import annotations

import re
from functools import lru_cache

# User's priority cities — chosen over any other city if both appear in a string
# (e.g. "Cardiff or Edinburgh" -> Edinburgh) and shown first in a multi-city
# posting's preview. Single source of truth; config `priority_locations` overrides
# it via set_priority() at scan startup, so the dashboard needs no list of its own.
DEFAULT_PRIORITY = ("edinburgh", "glasgow", "london")
_priority: tuple[str, ...] = DEFAULT_PRIORITY


def set_priority(cities) -> None:
    """Override the priority cities from config (`priority_locations`). Falsy/empty
    keeps the default. Stored lowercased for matching."""
    global _priority
    _priority = tuple(c.lower().strip() for c in cities if c and c.strip()) or DEFAULT_PRIORITY


def order_by_priority(cities: list[str]) -> list[str]:
    """Sort a posting's canonical cities: priority cities first (in priority
    order), then the rest alphabetically — so locations[0] is the best preview."""
    pri = {c: i for i, c in enumerate(_priority)}
    return sorted(cities, key=lambda c: (pri.get(c.lower(), len(pri)), c))

# Region / nation fallbacks when no specific city matches.
REGIONS = (
    ("northern ireland", "Northern Ireland"),
    ("scotland", "Scotland"),
    ("wales", "Wales"),
    ("england", "England"),
)

UNKNOWN = "Unknown"


@lru_cache(maxsize=1)
def _gb_cities() -> dict[str, str]:
    """{lowercase name: canonical name} for all GB cities geonamescache knows."""
    from geonamescache import GeonamesCache

    gc = GeonamesCache()
    return {
        c["name"].lower(): c["name"]
        for c in gc.get_cities().values()
        if c.get("countrycode") == "GB"
    }


@lru_cache(maxsize=1)
def _city_regex() -> re.Pattern[str]:
    """Word-bounded alternation of all city names, longest first so multi-word
    names ("Newcastle upon Tyne") win over their prefixes ("Newcastle")."""
    names = sorted(_gb_cities(), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")


def clean_location(raw: str | None) -> str:
    """Best canonical UK city for a raw location string, else a sensible bucket."""
    if not raw or not raw.strip():
        return UNKNOWN
    low = raw.lower()
    cities = _gb_cities()

    matches = [m.group(0) for m in _city_regex().finditer(low)]
    if matches:
        for target in _priority:  # user's priority cities win
            if target in matches:
                return cities[target]
        best = max(matches, key=len)  # else the most specific (longest) match
        return cities.get(best, best.title())

    if "remote" in low:
        return "Remote"
    for needle, label in REGIONS:
        if needle in low:
            return label
    if "united kingdom" in low or re.search(r"\buk\b", low):
        return "UK"
    return UNKNOWN
