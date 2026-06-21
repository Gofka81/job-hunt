from __future__ import annotations

from job_radar.filters import build_location_filter, build_title_filter
from job_radar.schema import Job, make_vacancy_key


def test_title_positive_and_negative():
    ok = build_title_filter({"positive": ["data engineer", "spark"], "negative": ["junior"]})
    assert ok("Senior Data Engineer")
    assert ok("Spark Platform Engineer")
    assert not ok("Junior Data Engineer")  # negative wins
    assert not ok("Frontend Developer")  # no positive


def test_title_no_positives_passes_all_but_negatives():
    ok = build_title_filter({"negative": ["manager"]})
    assert ok("Anything")
    assert not ok("Engineering Manager")


def test_location_allow_block():
    ok = build_location_filter({"allow": ["edinburgh", "remote"], "block": ["london"]})
    assert ok("Edinburgh, Scotland")
    assert ok("Remote (UK)")
    assert ok("")  # empty passes
    assert not ok("London")  # block wins
    assert not ok("Manchester")  # not in allow


def test_location_no_config_passes_all():
    ok = build_location_filter(None)
    assert ok("Anywhere")


def test_vacancy_key_is_stable_and_source_city_agnostic():
    a = make_vacancy_key("Acme", "Data Engineer", "https://x/1")
    assert a == make_vacancy_key("Acme", "Data Engineer", "https://x/1")
    # source, URL and city are NOT in the key, so a different source + URL + city
    # still hashes the same — the same role at the same company is one vacancy.
    job = Job(source="adzuna", company="Acme", title="Data Engineer", url="https://x/9", location="London, UK")
    assert job.vacancy_key == a
