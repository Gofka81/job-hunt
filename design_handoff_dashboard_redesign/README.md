# Handoff: job-hunt dashboard redesign v2 (mobile + desktop)

## Overview
A redesign of the job-hunt web dashboard (`src/job_radar/dashboard.py` — the inline HTML served at `GET /`). It keeps the app's existing colorway and rounded style, reorganizes navigation (Jobs and Tracker as tabs next to the "job-radar" brand; a Settings gear on the right), simplifies the jobs toolbar, adds a mobile bottom tab bar, and restructures Settings into separate pages.

## About the Design Files
`Job Radar v2.dc.html` is an interactive HTML prototype with mock data, NOT production code. Recreate the design inside the existing dashboard: `dashboard.py` stays a self-contained inline HTML/CSS/JS page with no build step; keep the existing `/api/*` contract exactly as-is. Only markup, CSS, and view-wiring JS change. (Ignore `Mobile Preview.dc.html` — it just embeds the app at phone widths.)

## Design tokens (from the prototype — CSS variables on :root)
Light: bg #f5f6f8 · card #ffffff · line #e3e5ea · fg #1b1e26 · muted #6b7180 · accent #2f6ef7 · pill #eef0f4 / #3a4150 · new #12924f · danger #e23b3b · score hi #d8f6e4/#0c7a3d, mid #fbefcd/#8a6800, lo #fbdede/#b32424 · shadow 0 1px 2px rgba(20,25,40,.06).
Dark theme re-declares the same variables under `[data-theme="dark"]` and under `@media (prefers-color-scheme: dark)` for the no-attribute (system) case — exact values in the prototype's <style> block.
Radii: cards 11-12px, inputs/buttons 8-9px, tags/chips pill (20px), settings menu 12px. Font: system-ui stack, 15px base.
Icons: inline Lucide SVGs (24×24 viewBox, stroke-width 2, currentColor) — copy paths from the prototype. No emoji anywhere.

## Header (all views)
Sticky, bg + 1px line bottom border; max-width 900px row: 28px rounded accent tile with radar icon + "job-radar" (17px/750), then Jobs and Tracker text tabs (active = accent text on 12% accent tint, radius 8px), spacer, 38px bordered icon buttons: refresh, settings gear (accent when active).

## Jobs view
- Toolbar: search input (icon inset) + one "Scan ▾" dropdown (Scan now / Deep scan) + primary Analyze button. Labels hide at ≤640px (icon-only).
- Lanes: segmented control in a rounded card (Inbox / Archived / All + count chips); active = solid accent.
- Sub-row: "Recent 48h (+N older)" pill toggle, ministat, Filters ghost button with active-count badge; collapsible filter card (Location, Source, Min salary £k, Sort).
- Job card: white card, 1px line border + 3px left border in score color, radius 12px. Score badge = rounded pill (green/amber/red per band: ≥7 / 5-6 / <5). Title, sparkles re-score + X hide icon buttons (undo restore in Archived), meta pills (location +N, salary, source), "Xh ago", green NEW pill (<24h), muted reason line under a divider. viewed = 55% opacity.
- Pager: rounded 38px buttons, active solid accent.

## Tracker view
3-col grid desktop / horizontal scroll-snap (84vw cols) mobile. Columns Saved / Applied / Rejected — headers colored accent/green/red + count chip. Cards same style, no reason, ghost move buttons. HTML5 drag-and-drop between columns; drop target gets accent border + 8% accent tint.

## Settings — separate pages (iOS-style)
Opening Settings shows a menu card: four rows (icon tile, title, description, chevron) — General (Theme & API token), Config, Rubric, Usage. Each row opens its own page with a "‹ Settings" back button + page title.
- **General**: theme segmented control System / Light / Dark (system = remove data-theme attr; persist localStorage `jr_theme`); API token input + Save (`jr_token`).
- **Config**: Form ↔ Raw YAML toggle. Form order: **Global filters first** (title positive/negative chip inputs — negative chips tinted red; expire hours, recent window), then **Connectors**: Adzuna, Reed, Indeed, LinkedIn, Greenhouse, Lever, Ashby, Workday, Oracle ORC — collapsible cards with icon tile, name + description, On/Off pill badge, iOS toggle. Bodies: chip inputs for queries/slugs (Enter adds, × removes); Adzuna also has location rows (city + km + delete, "+ Add location") and a fields grid; Workday/Oracle also get a Companies chip field (host | site | name) and Max pages. Sticky Save bar at the bottom. Wire to GET/POST /api/config.
- **Rubric**: Save/Reload + monospace textarea → /api/rubric.
- **Usage**: stat cards (calls/runs/scored/api $) + runs table in a rounded card → /api/usage.

## Mobile (≤640px)
Bottom tab bar (fixed, card bg, top border): Jobs / Tracker / Settings, 19px icon over 11px label, active = accent; body gets 66px bottom padding. Header keeps brand + refresh only.

## Behavior to preserve
All existing behavior: lanes client-side, debounced server search, recency toggle inbox-only, triage polling with per-card pulse spinner, scan 409 handling, optimistic viewed-marking, apply-tracking popup (Applied / Save for later / Not interested / Not now — rounded modal, stacked buttons).

## Files
- `Job Radar v2.dc.html` — the interactive prototype: all markup, styles (inline), tokens, and interaction logic to reference.
- `Mobile Preview.dc.html` — the app embedded at 390/360px widths.
