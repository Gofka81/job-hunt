from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from .locations import clean_location, order_by_priority
from .schema import Job, make_job_id

logger = logging.getLogger("job_radar.store")

# Single-table schema, created on open. No migration framework: this is a
# development project that re-scrapes freely, so we evolve the schema by editing
# this DDL and re-running scans rather than carrying ordered migrations + backfills.
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id           VARCHAR PRIMARY KEY,   -- sha1(vacancy_key | first_seen): per-generation row id
    vacancy_key      VARCHAR,               -- sha1(company|role): dedup identity (NOT unique)
    source           VARCHAR,
    company          VARCHAR,
    title            VARCHAR,
    url              VARCHAR,               -- cleaned clickable link (tracking params stripped)
    location         VARCHAR,               -- raw first-seen location string
    locations        JSON,                  -- set of canonical UK cities this posting lists
    description      VARCHAR,               -- plain-text JD (for tech-stack search)
    posted_at        DATE,
    salary_min       DOUBLE,
    salary_max       DOUBLE,
    currency         VARCHAR,
    remote           BOOLEAN,
    status           VARCHAR DEFAULT 'new',
    score            DOUBLE,
    report_num       INTEGER,
    first_seen       TIMESTAMP,
    last_seen        TIMESTAMP,
    raw              JSON
);
CREATE INDEX IF NOT EXISTS idx_jobs_vacancy ON jobs(vacancy_key);
CREATE TABLE IF NOT EXISTS scan_runs (
    run_id       VARCHAR,
    started_at   TIMESTAMP,
    finished_at  TIMESTAMP,
    source       VARCHAR,
    found        INTEGER,
    new          INTEGER,
    dupes        INTEGER,
    filtered     INTEGER,
    errors       INTEGER,
    error_detail VARCHAR
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str | Path, *, retries: int = 20, retry_delay: float = 0.5):
        # DuckDB allows only one read-write connection to a file at a time. The
        # server opens a short-lived connection per request (~5ms; fine at our
        # traffic — see the connection-strategy note in the README/PLAN), and the
        # in-process scan opens its own while writing. A brief overlap (a dashboard
        # hit mid-scan) can hit the lock, so wait and retry rather than error — the
        # scan holds the file only for seconds.
        self.con = self._connect(path, retries, retry_delay)
        self.con.execute(SCHEMA)  # idempotent (IF NOT EXISTS)

    @staticmethod
    def _connect(path: str | Path, retries: int, retry_delay: float):
        last: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                return duckdb.connect(str(path))
            except duckdb.IOException as exc:  # file locked by the other process
                last = exc
                if attempt < retries - 1:
                    time.sleep(retry_delay)
        raise last  # type: ignore[misc]

    def upsert(self, job: Job, expire_hours: int = 24) -> bool:
        """Merge `job` into the live row for its vacancy, or insert a new one.

        Dedup identity is `vacancy_key` (company+role, source/city-agnostic). We
        look for an existing row with the same vacancy_key seen within the last
        `expire_hours` — i.e. still live. If found, this is the same vacancy
        (a repost, a cross-source dupe, or the same posting in another city): bump
        last_seen and UNION the city into `locations`; content is first-seen-wins.
        Returns False (merged).

        If none is live, this is a fresh vacancy (a brand-new role, or one that
        expired and is now relisted): INSERT a new row with a per-generation
        job_id and status='new'. Any old expired row for the same vacancy_key is
        left untouched as history. Returns True (newly inserted)."""
        now = _now()
        vkey = job.vacancy_key
        city = clean_location(job.location)
        cutoff = now - timedelta(hours=max(0, expire_hours))
        live = self.con.execute(
            """SELECT job_id, locations FROM jobs
               WHERE vacancy_key = ? AND last_seen >= ?
               ORDER BY last_seen DESC LIMIT 1""",
            [vkey, cutoff],
        ).fetchone()
        if live:
            job_id, locs_json = live
            locs = json.loads(locs_json) if locs_json else []
            if city not in locs:
                locs = order_by_priority([*locs, city])
            self.con.execute(
                "UPDATE jobs SET last_seen = ?, locations = ? WHERE job_id = ?",
                [now, json.dumps(locs), job_id],
            )
            # Off by default; flip to DEBUG to trace why a listing didn't get its
            # own row (e.g. a job that never appears on the dashboard).
            logger.debug(
                "merged %s (%s, %s) into %s [%s]",
                job.stored_url, job.source, city, job_id, vkey,
            )
            return False
        self.con.execute(
            """INSERT INTO jobs
               (job_id, vacancy_key, source, company, title, url, location, locations,
                description, posted_at, salary_min, salary_max, currency, remote, status,
                first_seen, last_seen, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new', ?, ?, ?)""",
            [
                make_job_id(vkey, now), vkey, job.source, job.company, job.title,
                job.stored_url, job.location, json.dumps([city]), job.description,
                job.posted_at, job.salary_min, job.salary_max, job.currency, job.remote,
                now, now, json.dumps(job.raw, default=str),
            ],
        )
        return True

    # --- API sync (Pi <-> PC) ---------------------------------------------
    # A job is "pending" (needs evaluation) while status='new'. Verdicts from
    # the PC move it to evaluated/applied/rejected/archived and drop it off the
    # /api/pending feed. The Pi is the only writer of this table.
    PENDING_COLS = (
        "job_id", "url", "company", "title", "location", "source",
        "posted_at", "salary_min", "salary_max", "currency", "remote",
    )

    def pending_jobs(self) -> list[dict]:
        """Jobs still awaiting evaluation (status='new'), newest first. This is
        the Pi -> PC shortlist payload. No phantom dedup needed — job_id is
        canonical-URL based, so each ad is already a single row."""
        rows = self.con.execute(
            f"""SELECT {", ".join(self.PENDING_COLS)}
                FROM jobs WHERE status = 'new'
                ORDER BY first_seen DESC"""
        ).fetchall()
        return [dict(zip(self.PENDING_COLS, r)) for r in rows]

    def mark_results(self, results: list[dict]) -> int:
        """Apply PC -> Pi verdicts. Each result is keyed by `url` (preferred,
        since the PC works in URLs) or `job_id`, plus optional score/status/
        report_num. Unknown jobs are skipped. Returns rows updated."""
        updated = 0
        for r in results:
            jid = r.get("job_id")
            url = r.get("url")
            if not jid and url:
                row = self.con.execute(
                    "SELECT job_id FROM jobs WHERE url = ?", [url]
                ).fetchone()
                jid = row[0] if row else None
            if not jid or not self.con.execute(
                "SELECT 1 FROM jobs WHERE job_id = ?", [jid]
            ).fetchone():
                continue
            self.con.execute(
                "UPDATE jobs SET status = ?, score = ?, report_num = ? WHERE job_id = ?",
                [r.get("status") or "evaluated", r.get("score"), r.get("report_num"), jid],
            )
            updated += 1
        return updated

    LIST_COLS = (
        "job_id", "source", "company", "title", "url", "location", "locations",
        "status", "score", "salary_min", "salary_max", "currency", "first_seen", "last_seen",
    )

    def list_jobs(self, limit: int = 500, q: str | None = None) -> list[dict]:
        """All jobs, newest-discovered first, with timestamps + status — for the
        dashboard. `first_seen` = when a scan first found it; `last_seen` = the
        most recent scan that still saw it (a stale value ≈ the posting is gone).

        `q` is a free-text search matched (case-insensitive substring) against
        title + company + description, so tech-stack terms in the JD (e.g.
        "spark") are searchable even when they're not in the title. The bulky
        `description` is searched server-side but not returned in the payload."""
        where, params = "", []
        if q and q.strip():
            where = """WHERE lower(coalesce(title,'') || ' ' || coalesce(company,'')
                              || ' ' || coalesce(description,'')) LIKE ?"""
            params.append(f"%{q.strip().lower()}%")
        params.append(limit)
        rows = self.con.execute(
            f"""SELECT {", ".join(self.LIST_COLS)}
                FROM jobs {where} ORDER BY first_seen DESC LIMIT ?""",
            params,
        ).fetchall()
        out = [dict(zip(self.LIST_COLS, r)) for r in rows]
        for d in out:  # locations stored as a JSON string → hand back a list
            d["locations"] = json.loads(d["locations"]) if d["locations"] else []
        return out

    def expire_stale(self, max_age_hours: int, sources: list[str]) -> int:
        """Mark still-`new` jobs not seen for `max_age_hours` as `expired` — they've
        dropped off their source's listing, so the posting is closed/filled. We mark
        (not delete) so the row stays for history + is filterable, and reappears as
        `new` if it's listed again (see upsert). Guards: only `status='new'` (never
        touch a human verdict) and only the given `sources` (pass those that scanned
        OK this run, so a source outage can't expire everything). Returns rows marked.

        Active views (`/api/pending`, `/jobs`, the dashboard's new filter) select
        `status='new'`, so expired jobs drop off them automatically."""
        if not sources or max_age_hours <= 0:
            return 0
        cutoff = _now() - timedelta(hours=max_age_hours)
        marks = ",".join("?" * len(sources))
        where = f"status = 'new' AND last_seen < ? AND source IN ({marks})"
        params = [cutoff, *sources]
        n = self.con.execute(f"SELECT count(*) FROM jobs WHERE {where}", params).fetchone()[0]
        if n:
            self.con.execute(f"UPDATE jobs SET status = 'expired' WHERE {where}", params)
        return n

    def funnel(self) -> dict[str, int]:
        """Counts for the dashboard funnel: total discovered + per-status."""
        total = self.con.execute("SELECT count(*) FROM jobs").fetchone()[0]
        by_status = dict(
            self.con.execute("SELECT status, count(*) FROM jobs GROUP BY status").fetchall()
        )
        return {"total": total, **{str(k): v for k, v in by_status.items()}}

    def record_run(
        self,
        run_id: str,
        started: datetime,
        source: str,
        found: int,
        new: int,
        dupes: int,
        filtered: int,
        errors: int,
        error_detail: str = "",
    ) -> None:
        self.con.execute(
            """INSERT INTO scan_runs
               (run_id, started_at, finished_at, source, found, new, dupes,
                filtered, errors, error_detail)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [run_id, started, _now(), source, found, new, dupes, filtered, errors, error_detail],
        )

    def close(self) -> None:
        self.con.close()
