from __future__ import annotations

from job_radar.dedup import (
    canonical_url,
    clean_stored_url,
    normalize_company,
    normalize_role,
    vacancy_key,
)
from job_radar.schema import make_vacancy_key

LDN = "https://www.adzuna.co.uk/jobs/land/ad/5760606708"


# --- canonical_url (vacancy_key fallback for blank-field rows) -------------

def test_canonical_url_strips_tracking_params():
    assert canonical_url(LDN + "?se=AAA&v=BBB&utm_source=x") == LDN
    assert canonical_url(LDN + "?se=ZZZ") == LDN


def test_canonical_url_strips_fragment_and_trailing_slash():
    assert canonical_url("https://x.io/job/1/#apply") == "https://x.io/job/1"


def test_canonical_url_blank():
    assert canonical_url(None) == ""
    assert canonical_url("") == ""


# --- clean_stored_url (the clickable link: denylist strip, keep functional) ---

def test_clean_stored_url_drops_tracking_keeps_functional():
    # utm_*/source dropped; the signed `se` token and the path are kept so the
    # link still resolves
    assert clean_stored_url(LDN + "?se=ABC&utm_source=x&ref=y") == LDN + "?se=ABC"


def test_clean_stored_url_drops_fragment():
    assert clean_stored_url("https://x.io/job/1#apply") == "https://x.io/job/1"


def test_clean_stored_url_blank():
    assert clean_stored_url(None) == ""


# --- normalizers (ported from career-ops) --------------------------------

def test_normalize_company_matches_career_ops_rules():
    assert normalize_company("Harnham - Data & Analytics Recruitment") == "harnham data analytics recruitment"
    assert normalize_company("Acme (UK) Ltd.") == "acme uk ltd"


def test_normalize_role_keeps_slash_drops_other_punct():
    assert normalize_role("BI Data Engineer (Azure/Power BI)") == "bi data engineer azure/power bi"
    assert normalize_role("Senior Analytics Engineer") == "senior analytics engineer"


# --- vacancy_key (the vacancy identity) ----------------------------------

def test_vacancy_key_combines_company_and_role():
    assert vacancy_key("Harnham", "Senior Analytics Engineer") == "harnham|senior analytics engineer"


def test_vacancy_key_none_when_company_or_title_blank():
    assert vacancy_key("", "Data Engineer") is None
    assert vacancy_key("Acme", "") is None


# --- make_vacancy_key (write-time dedup behaviour) -----------------------

def test_vacancy_key_collapses_reposts_of_same_role():
    # token variant + brand-new ad-id → same dedup key
    base = make_vacancy_key("Harnham", "Senior Analytics Engineer", LDN + "?se=A")
    variant = make_vacancy_key("Harnham", "Senior Analytics Engineer", LDN + "?se=B")
    new_adid = make_vacancy_key("Harnham", "Senior Analytics Engineer", "https://x/57013787")
    assert base == variant == new_adid


def test_vacancy_key_collapses_across_city():
    # city is NOT in the key → the same posting in two cities shares one key
    # (the cities accumulate in the row's `locations` set instead)
    ldn = make_vacancy_key("BigCorp", "Data Engineer", "https://x/1")
    edi = make_vacancy_key("BigCorp", "Data Engineer", "https://x/2")
    assert ldn == edi


def test_vacancy_key_is_source_agnostic():
    # same vacancy from different sources (Adzuna + Reed) → SAME key → one row
    assert make_vacancy_key("Harnham", "Data Engineer", "https://adzuna/1") == \
           make_vacancy_key("Harnham", "Data Engineer", "https://reed/2")


def test_vacancy_key_distinguishes_role():
    assert make_vacancy_key("Co", "Data Engineer", "u") != make_vacancy_key("Co", "Analytics Engineer", "u")


def test_vacancy_key_falls_back_to_url_when_fields_blank():
    # no role key (blank company) → identify by canonical URL, so two blank-company
    # ads at different URLs stay distinct, but token-variants of one still collapse
    a = make_vacancy_key("", "Data Engineer", "https://x/1?se=A")
    b = make_vacancy_key("", "Data Engineer", "https://x/1?se=B")
    c = make_vacancy_key("", "Data Engineer", "https://x/2")
    assert a == b != c
