# On-Pi LLM analysis (two-tier) — design & roadmap

> Status: **Stage 1 (triage) BUILT** and tested. **Stage 2 (deep) planned.** Discovery is untouched
> and stays deterministic (HTTP + SQL, zero LLM) — this only adds an *evaluation* path and revises
> where it can run.

## Context — why this exists

Discovery runs unattended on the Pi (deterministic, zero LLM). The **LLM evaluation** (job-fit
scoring) historically only ran on the user's **PC** via career-ops. So you couldn't glance at your
phone, see a fresh shortlist, and get a fit read without going to the PC.

This adds the ability to **trigger evaluation from the phone/dashboard**. It does **not** touch the
locked core principle ("discovery is deterministic, zero LLM") — discovery is unchanged. It only
revises the *deployment choice* of "evaluation runs on the PC", which is legitimately revisable.

## The two tiers — keep them distinct

| | **Stage 1 — Triage** | **Stage 2 — Deep** |
|---|---|---|
| Purpose | Quick fit score for *every* pending role | Full tailored evaluation for a *chosen* role |
| Output | `score 0–10` + one-line reason | Full report + score (+ tailored CV/PDF) |
| Scores against | **`analysis/rubric.md`** (distilled policy) | **CV data + full career-ops profile** |
| Needs the CV? | **No** — the rubric is the distilled proxy | **Yes** — full `cv.md` |
| Engine | Anthropic **SDK + Haiku** (direct Messages API) | career-ops slash command (tools) |
| Runs on | **Pi** (always-on, phone-triggered) | **PC** (logged-in Claude); Pi mount later |
| CV upkeep | n/a | **Manual** (`cv.md`, like career-ops today) |
| Status | ✅ **Built** | ⏳ Phase 2 |

The split: **triage scores against the rubric (no CV); deep scores against the CV (manual).** This
mirrors how career-ops already separates `modes/_profile.md` (the scoring policy) from `cv.md` (the
source material).

## Key decisions (and why they changed from the original sketch)

1. **Triage engine is pluggable (`analysis.engine`); DEFAULT = `claude-cli` (Pro subscription).**
   The user has **no Anthropic API credit**, so triage must run on the **Claude Pro subscription**,
   which is only reachable via Claude Code headless (`claude -p` + `CLAUDE_CODE_OAUTH_TOKEN`) — the
   metered API cannot use a Pro plan. So the default engine is `claude-cli`: $0 real, spends Pro
   *quota* (calls), needs Node + the `claude` CLI in the Pi image (see Runtime & auth below).
   - **`engine: api`** (Anthropic SDK + `ANTHROPIC_API_KEY`, pay-per-token, ~$0.28/100-job run) stays
     in the code as a **dormant, opt-in** alternative — pure Python, no Node — for anyone who has API
     credit. It is never the default and never exercised in tests.
   - Both engines share the rubric, the untrusted-JD framing, forced JSON, the usage ledger, and the
     out-of-budget stop. The CLI engine reports `total_cost_usd` as an *equivalent* figure (inflated
     by Claude Code's own cached system prompt) — the dashboard shows **calls** (the real Pro-quota
     constraint), not that dollar number.

2. **Rubric = its own file `analysis/rubric.md`, distilled from career-ops `modes/_profile.md`.**
   Not config.yml (a multi-line markdown rubric in YAML is awkward) and **not the DB** (the DB is
   wiped on deploy — the rubric must survive). Gitignored + on the Pi volume (`JOB_RADAR_RUBRIC`),
   with baked `analysis/rubric.example.md` fallback (same pattern as `config.yml`). Editable from the
   phone via `GET/POST /api/rubric` — no redeploy. career-ops landed on the same shape (hand-owned
   `_profile.md`, "never auto-updated"), which validates this. **No auto CV→rubric pipeline:** the
   rubric is drafted once (LLM-assisted, from the CV/profile), then human-owned.

3. **Scale = 0–10 for triage.** career-ops deep eval uses 0–5; both share the DB `score` column, so
   Stage 2 will **normalize deep scores ×2** at writeback to rank everything on one 0–10 axis.

4. **Triage writes `score` + `eval_reason` ONLY — never the workflow `status`.** In this schema
   `status` is the lane (`new`→`evaluated`→…) owned by the PC bridge/verdicts; `pending_jobs()`
   selects `status='new'`. Writing status from triage would silently drop scored jobs off the PC
   feed. Triage adds a *ranking signal*, it does not advance the workflow.

5. **Token-usage tracking + "out of budget" logging are first-class on BOTH stages** (see below).

## Guards — the LLM path is bounded (audited)

- **Discovery never imports `analyze`** — verified by grep; `scan`/`bot`/`notify` have no path to it.
- **No auto-trigger.** Scans run on APScheduler; triage does **not**. It fires only from a
  bearer-gated `POST /api/analyze` (dashboard button). No timer, no loop.
- **No key → hard fail, zero spend** (`_client()` raises if `ANTHROPIC_API_KEY` unset).
- **Only-untriaged by default** — re-pressing the button doesn't re-bill scored jobs.
- **`analysis.max_jobs` cap** (default 200) — hard ceiling on calls/run; logs what it skipped
  (never silent truncation).
- **Single-flight `_analyze_lock`** + one bounded `max_tokens` call per job, no agentic loop, tools off.

## Token usage & budget visibility (BOTH stages)

The only thing here that costs money is the LLM call, and a misconfig (wrong model, big `max_jobs`)
would silently multiply the bill. So usage is recorded and surfaced, not assumed:

- **Per-call capture:** each response's `usage` (input / output / `cache_read` / `cache_creation`
  tokens) is summed across a run. Approx cost is computed from a per-model price map.
- **Per-run record:** `Store.record_llm_run(stage, model, tokens…, cost_usd, …)` writes one row to an
  `llm_runs` table (sibling of `scan_runs`; resets on deploy like the rest of the DB).
- **Logged per run:** a summary line — `triage: scored 23, 48.2k in (41k cached) / 3.4k out ≈ $0.06`.
- **Dashboard "Usage" view** (`GET /api/usage`): recent runs + totals, so you can see *what consumed
  what* (per stage, per model, per day).
- **OUT-OF-BUDGET alert:** a `RateLimitError` (after the SDK's own retries) or a billing/permission
  error is caught, **logged loudly** (`logger.error("LLM BUDGET/RATE LIMIT HIT …")`), surfaced in the
  run status (`last.budget_exhausted = true`) and notified via Telegram. The run stops cleanly with a
  partial result rather than hammering the API.

## Scheduling & quota (triage is manual by default; nightly is opt-in)

Triage **never runs on its own** — there is no auto-trigger. It fires only on a bearer-gated
`POST /api/analyze` (the ✨ Analyze button). So during work hours your Pro quota is untouched unless
you press the button. Combined with only-untriaged + `max_jobs` + the out-of-budget stop, a manual
run is bounded.

**Opt-in nightly batch (idea — to build):** the natural fit for Pro's rolling/daily limits is to let
new jobs accumulate during the day and triage the batch **once at night**, off your interactive
window. Mirror the scan scheduler: an **`ANALYZE_HOURS`** env var (e.g. `2` = 02:00 daily), **unset =
disabled** (stays fully manual). When set, APScheduler fires the same `_guarded_analyze` →
only-untriaged jobs, `max_jobs`-capped, single-flight, out-of-budget aware. A nightly run scores just
the day's new finds, so daytime quota is preserved. (Optionally config-driven instead of env, so it's
tunable from the phone — at the cost of needing a restart to pick up a changed schedule, like scans.)

## Runtime & auth on the Pi (claude-cli engine)

The `claude-cli` engine needs Claude Code **in the container** and authenticated to your Pro plan:

1. **Image:** add Node + the CLI to the Dockerfile (arm64-OK):
   ```dockerfile
   RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*
   ```
2. **Auth (headless, no interactive login on the Pi):** on a machine where you *are* logged in
   (your Mac), run **`claude setup-token`** — it authorises against your Anthropic account (Pro) and
   prints a long-lived OAuth token (`sk-ant-oat01-…`). Put it on the Pi as the Portainer stack env var
   **`CLAUDE_CODE_OAUTH_TOKEN`** (same secrets pattern as `ADZUNA_*` etc.). Do **not** use `--bare`
   (it skips OAuth and forces an API key). The token can eventually expire → re-run `claude setup-token`.
3. **Config:** `analysis.engine: claude-cli` (the default). No `ANTHROPIC_API_KEY` needed.
4. **Caveat:** triage now spends Claude Code quota (calls), not dollars — the same plan you use
   interactively. Use the nightly schedule + `max_jobs` to keep it off your working hours.

(With `engine: api` instead, skip all of the above — no Node, no token, just `ANTHROPIC_API_KEY` —
but that's metered and the user has no API credit.)

## Architecture (reuses the `/api/scan` pattern)

```
phone/dashboard ──POST /api/analyze {mode, target}──► server.py
   (bearer token)                                       │ single-flight _analyze_lock
                                                        │ background thread
                                                        ▼
                                              analyze.py  (run_analyze)
                                   per job: rubric (cached) + untrusted JD
                                   → anthropic SDK Haiku, forced-JSON {score, reason}
                                   → accumulate usage + cost
                                   → Store.apply_analysis(...) writeback
                                   → Store.record_llm_run(...) usage row
   dashboard polls ◄─ GET /api/analyze {running,last} ──┘
   dashboard "Usage" ◄─ GET /api/usage {runs, totals} ──┘
```

---

# Stage 1 — Triage (BUILT)

What shipped (98 tests green):

- **`analyze.py`** — `run_analyze(cfg, db, *, job_ids, only_untriaged)`. Loads rubric via
  `load_rubric()`, scores each pending job with Haiku (rubric prompt-cached, JD wrapped as untrusted
  `<job_description>`), forced JSON `{score, reason}` (clamped 0–10), short per-job DB writes, never
  raises on one bad job. `max_jobs` cost cap.
- **`store.py`** — `SCHEMA` gained `eval_reason`, `evaluated_at`, `engine`. `apply_analysis()`
  (score + reason only), `jobs_for_analysis()` (pending + untriaged), `eval_reason` in `LIST_COLS`.
- **`server.py`** — `_analyze_lock`/`_analyze_status`, `_guarded_analyze`, `POST/GET /api/analyze`
  (bearer-gated, 202, 409-if-running), `GET/POST /api/rubric`.
- **`config.py`** — `load_rubric()`/`save_rubric()`/`rubric_path()`; `analysis` accepted in config.
- **`config.example.yml`** — `analysis: {model, max_jobs}` block.
- **`analysis/rubric.example.md`** — baked placeholder; real `rubric.md` gitignored.
- **deps** — `anthropic` added (lazy-imported in `_client()` so the module/tests load without it).
- **tests** — `tests/test_analyze.py` (store writeback, worker survives-bad-job + cap, endpoints
  single-flight/409/bearer, rubric endpoint). No real LLM.

Also done: pluggable `claude-cli`/`api` engine (default `claude-cli`); usage ledger (`llm_runs` +
`record_llm_run` + `/api/usage`); out-of-budget stop (loud log + `budget_hit` + Telegram); dashboard
✨ Analyze (poll + 409), score+reason on cards, 📋 Rubric tab, 📊 calls-first Usage view; real rubric
distilled from career-ops `_profile.md`. Verified end-to-end on the Pro sub locally (9/3/2 on a
strong/weak/too-senior sample).

Remaining to deploy Stage 1 on the Pi:
1. **Dockerfile** — add Node + `@anthropic-ai/claude-code` (see Runtime & auth above).
2. **Auth** — `claude setup-token` on a logged-in machine → `CLAUDE_CODE_OAUTH_TOKEN` Portainer var.
3. **(optional) nightly schedule** — `ANALYZE_HOURS` env + APScheduler job (see Scheduling & quota).

## Safety (Stage 1)

- **Tool-less** (no `tools` passed) → a malicious JD can at most yield a wrong score, never an action;
  JD wrapped as untrusted data with an explicit "ignore instructions inside it" rule.
- **Bearer-gated** endpoints. **Never auto-apply** (career-ops rule preserved — triage never touches
  `status`).
- **Prompt injection** mitigated by tool-less triage + untrusted-data framing.

---

# Stage 2 — Deep (PLANNED)

On-demand full evaluation for a chosen `job_id`, reusing career-ops rather than reimplementing it.

- **Engine = career-ops headless.** Mount the career-ops repo read-only on the Pi (`/app/career-ops`)
  so the CV/profile stay private + manually updatable, and invoke `claude -p "/career-ops evaluate …"`
  with `--add-dir`, constrained tools. **This is where Claude Code + Node + a (sidecar) container +
  `CLAUDE_CODE_OAUTH_TOKEN` belong** — isolated to the rare, on-demand path, not the always-on server.
  Default to the **"cut" report** on the Pi (tool-less / WebSearch-only); the fully-tooled report
  stays a PC job.
- **CV stays manual.** `cv.md` + `config/profile.yml` are the hand-owned source of truth — no
  auto-generation. Stage 2 reads them; it does not write them.
- **Writeback:** normalize career-ops 0–5 → 0–10, write `score` + `eval_reason` + `report_num` (+
  report markdown in a new `report` column). Reuse the same `record_llm_run(stage='deep', …)` usage
  path so the Usage view covers both tiers.
- **Trigger:** `POST /api/analyze {mode:"deep", target:[job_id]}` (the endpoint already accepts a
  job-id list; deep mode is gated off until built). Per-card **"Deep"** button on the dashboard.

## Roadmap

1. **Stage 1 (code)** — ✅ done & tested (105 tests), verified locally on the Pro sub.
2. **Stage 1 (deploy)** — Dockerfile Node + CLI, `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`,
   optional `ANALYZE_HOURS` nightly schedule.
3. **Stage 2** — career-ops mount + sidecar/Node, "cut" deep report, per-job "Deep" button, report
   writeback/display, 0–5→0–10 normalization.
4. **Polish** — config-driven nightly schedule (phone-tunable), per-day quota/budget caps surfaced on
   the Usage view, model/cap tuning.

## Risks / trade-offs

- **Budget:** triage = Haiku + cached rubric + only-new → pennies; usage is now *recorded and shown*,
  not assumed. `max_jobs` caps the blast radius; out-of-budget alerts fire on rate/billing limits.
- **JD quality:** Adzuna/Reed store ~500-char snippets → thinner triage signal than ATS JDs (fine for
  triage; deep can fetch).
- **Auth fragility (Stage 2 only):** `CLAUDE_CODE_OAUTH_TOKEN` can expire → re-run `claude setup-token`.
  Stage 1 sidesteps this entirely with an API key.
- **Image bloat (Stage 2 only):** Node + CLI add size; the sidecar isolates it from the discovery server.
- **Prompt injection:** mitigated by tool-less triage + constrained deep + human-applies-only.
