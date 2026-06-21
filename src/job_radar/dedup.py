"""Write-time deduplication.

`vacancy_key(company, title)` = normalized company + role, source- and
city-agnostic — so tracking-token variants, agency reposts, the same ad on
Adzuna+Reed, and one posting listed in many cities all collapse to one live row
(city becomes a `locations` attribute, not part of identity).

This is NOT the storage primary key. `job_id = sha1(vacancy_key|first_seen)`
(schema.make_job_id) is the per-generation row id: dedup matches vacancy_key
within a recency window, so a live sighting merges but a reappearance after expiry
gets a fresh row. Normalizers mirror career-ops `dedup-tracker.mjs`, normalized-
EXACT (not fuzzy) — prod reposts are byte-identical, fuzzy would wrongly merge
"Analytics Engineer" with "Senior Analytics Engineer".
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_COMPANY_DROP = re.compile(r"[^a-z0-9 ]")
_ROLE_DROP = re.compile(r"[^a-z0-9 /]")
_SPACES = re.compile(r"\s+")


# Tracking params dropped from the STORED clickable link. Denylist (not a blanket
# strip): some boards carry the job id in the query (`?gh_jid=`, Adzuna's signed
# `se=`), so we only remove known noise and keep everything else — the link must
# still resolve. Anything starting with `utm_` is dropped too.
_TRACKING_KEYS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
     "gh_src", "source", "ref", "referrer"}
)


def canonical_url(url: str | None) -> str:
    """Strip query string + fragment + trailing slash. Used only as the
    vacancy_key fallback when company/title are blank (can't build a role key) —
    so two blank-field listings aren't wrongly merged, and token-variants of such
    an ad still collapse. Never used for a link the user clicks."""
    if not url:
        return ""
    s = urlsplit(url.strip())
    path = s.path.rstrip("/")
    return urlunsplit((s.scheme, s.netloc, path, "", ""))


def clean_stored_url(url: str | None) -> str:
    """The clickable link we persist: drop the fragment + known tracking params
    (denylist), keep functional params so the URL still resolves. Cosmetic only —
    dedup never compares URLs (it hashes company|role)."""
    if not url:
        return ""
    s = urlsplit(url.strip())
    kept = [
        (k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS and not k.lower().startswith("utm_")
    ]
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(kept), ""))


def normalize_company(name: str | None) -> str:
    """lowercase, drop parens + punctuation, collapse spaces. Mirrors career-ops
    normalizeCompany."""
    s = (name or "").lower().replace("(", "").replace(")", "")
    s = _COMPANY_DROP.sub("", s)
    return _SPACES.sub(" ", s).strip()


def normalize_role(role: str | None) -> str:
    """lowercase, parens → space, keep '/' (e.g. "azure/power bi"), drop other
    punctuation, collapse spaces. Mirrors career-ops normalizeRole."""
    s = (role or "").lower().replace("(", " ").replace(")", " ")
    s = _ROLE_DROP.sub("", s)
    return _SPACES.sub(" ", s).strip()


def vacancy_key(company: str | None, title: str | None) -> str | None:
    """Identity of a logical vacancy: normalized company + role (city-agnostic).
    Returns None when company or title is blank — such rows have no safe key (all
    blanks would collapse together), so make_vacancy_key falls back to the URL."""
    c, r = normalize_company(company), normalize_role(title)
    if not c or not r:
        return None
    return f"{c}|{r}"
