# job-hunt — Pi image (arm64 Raspberry Pi 64-bit OS, also amd64). One process:
# the FastAPI server, which also owns scheduling (APScheduler) + on-demand scans.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOB_RADAR_HOST=0.0.0.0 \
    JOB_RADAR_PORT=8000 \
    JOB_RADAR_CONFIG=/app/data/config.yml \
    JOB_RADAR_RUBRIC=/app/data/rubric.md \
    TZ=Europe/London

# tzdata so the in-process cron schedule honours TZ (e.g. Europe/London);
# ca-certificates for outbound HTTPS to the job sources.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

# Node + Claude Code CLI — required by the DEFAULT triage engine
# (analysis.engine: claude-cli), which spawns `claude -p` on your Pro subscription.
# Auth is the CLAUDE_CODE_OAUTH_TOKEN env var (Portainer; read by the CLI, not our
# Python). Own cached layer so it only rebuilds when this line changes. Skip it only
# if you switch to analysis.engine: api (Anthropic SDK, no Node).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first for layer caching; editable install keeps ROOT=/app so the baked
# example fallbacks resolve at /app (config.example.yml + analysis/rubric.example.md).
# Only the .example files are copied — the personal config.yml / rubric.md live on
# the data volume (gitignored, written via /api/config and /api/rubric).
COPY pyproject.toml README.md config.example.yml ./
COPY analysis/rubric.example.md ./analysis/rubric.example.md
COPY src ./src
RUN pip install -e .

# Non-root. The named volume at /app/data inherits this ownership; it holds the
# DuckDB and the live config.yml (written via POST /api/config).
RUN useradd -m -u 1000 app && mkdir -p /app/data && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["job-serve"]
