from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from .dedup import canonical_url, clean_stored_url, vacancy_key


def make_vacancy_key(company: str, title: str, url: str) -> str:
    """16-char dedup key = sha1(vacancy_key). SOURCE- and CITY-AGNOSTIC: a role at
    a company hashes to one key regardless of source or city, so cross-source
    dupes, reposts, token variants, and multi-city listings all share it. Falls
    back to the canonical URL when company or title is blank (no safe key)."""
    key = vacancy_key(company, title) or canonical_url(url)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def make_job_id(vkey: str, first_seen: datetime) -> str:
    """Per-generation storage primary key = sha1(vacancy_key | first_seen). Unique
    per row: dedup is by `vkey` (a recency-windowed lookup in Store.upsert), while
    this id distinguishes generations — a relisted-after-expiry posting gets a new
    first_seen → a new id → a fresh row, leaving the expired one as history."""
    return hashlib.sha1(f"{vkey}|{first_seen.isoformat()}".encode()).hexdigest()[:16]


class Job(BaseModel):
    """Normalised job posting. Every connector maps its raw payload into this."""

    source: str
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""  # plain-text JD (for tech-stack search); not part of job_id
    posted_at: date | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    remote: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def vacancy_key(self) -> str:
        # Dedup identity (company+role, source/city-agnostic). The storage row id
        # (job_id) is assigned in Store.upsert from this + first_seen.
        return make_vacancy_key(self.company, self.title, self.url)

    @property
    def stored_url(self) -> str:
        # Cleaned clickable link (tracking params dropped, functional ones kept).
        return clean_stored_url(self.url)
