from __future__ import annotations

from job_radar import scan
from job_radar.schema import Job


class _FakeSource:
    """A source that returns two listings of the SAME vacancy (one duplicate)."""

    ID = "fake"

    @staticmethod
    def fetch(cfg, http):
        return [
            Job(source="fake", company="Acme", title="Data Engineer", url="https://x/1", location="Edinburgh"),
            Job(source="fake", company="Acme", title="Data Engineer", url="https://x/2", location="Edinburgh"),
        ]


def test_run_scan_completes_end_to_end(tmp_path, monkeypatch):
    # Exercises the WHOLE run_scan path — loop, http.close(), the expire step, the
    # summary, the return dict — which unit tests of Store/server never touch. This
    # is the regression guard for the post-loop `NameError` that reached prod.
    monkeypatch.setattr(scan, "REGISTRY", {"fake": _FakeSource})
    result = scan.run_scan({"sources": {"fake": {"enabled": True}}}, str(tmp_path / "db.duckdb"))

    t = result["totals"]
    assert t["found"] == 2 and t["new"] == 1 and t["dupes"] == 1  # dedup collapsed the pair
    assert t["expired"] == 0 and t["errors"] == 0  # post-loop expire step ran cleanly
    assert "notify" not in t                       # the removed counter stays gone
    assert len(result["new_jobs"]) == 1            # one vacancy to notify about


def test_run_scan_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "REGISTRY", {"fake": _FakeSource})
    db = tmp_path / "db.duckdb"
    result = scan.run_scan({"sources": {"fake": {"enabled": True}}}, str(db), dry_run=True)
    assert result["totals"]["new"] == 1
    assert not db.exists()  # dry run never opens/creates the DB
