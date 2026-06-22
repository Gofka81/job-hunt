# Triage rubric (example) — copy to analysis/rubric.md and personalise

This is the candidate profile the on-Pi LLM triage scores jobs against (0-10).
It is personal (skills, comp, right-to-work), so the real `analysis/rubric.md`
is gitignored and lives on the Pi volume; this `.example.md` is the baked fallback
`load_rubric()` returns until one is saved. Edit the real one from the phone via
`POST /api/rubric` (no redeploy) or directly on the volume.

---

# Candidate: <name> — <role> (<years> yrs)

Strong core (ideally present): <key skills>.
Strong bonus (bump score): <nice-to-haves>.
Neutral (don't penalise if absent): <adjacent tech>.
Level: <target seniority>. Penalise far-senior / lead-only roles.
Location: <target locations + remote policy>.
Right to work: <visa / right-to-work note>.

## Score 0-10
- 9-10  ideal fit — apply now
- 7-8   strong fit, minor gaps
- 5-6   adjacent / wrong level
- 3-4   weak
- 0-2   irrelevant
