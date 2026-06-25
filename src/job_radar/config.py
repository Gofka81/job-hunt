from __future__ import annotations

import os
from pathlib import Path

import yaml

# repo root = three levels up from this file (src/job_radar/config.py)
ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "config.example.yml"
EXAMPLE_RUBRIC = ROOT / "analysis" / "rubric.example.md"


def config_path() -> Path:
    """Where config.yml lives. On the server this is a writable path on the data
    volume (set via JOB_RADAR_CONFIG) so the /api/config route can update it;
    locally it defaults to repo-root config.yml."""
    env = os.environ.get("JOB_RADAR_CONFIG")
    return Path(env) if env else ROOT / "config.yml"


def load_config(path: str | Path | None = None) -> dict:
    """Load config. If the chosen path doesn't exist yet (fresh server, before the
    first /api/config PUT), fall back to the baked-in example so scans still run
    with sane defaults instead of crashing."""
    p = Path(path) if path else config_path()
    if not p.exists():
        if EXAMPLE.exists():
            return yaml.safe_load(EXAMPLE.read_text()) or {}
        raise FileNotFoundError(f"{p} not found and no {EXAMPLE.name} fallback.")
    return yaml.safe_load(p.read_text()) or {}


def read_config_text(path: str | Path | None = None) -> str:
    """Raw YAML text for the /api/config editor — current config, or the example
    if none has been saved yet."""
    p = Path(path) if path else config_path()
    if p.exists():
        return p.read_text()
    return EXAMPLE.read_text() if EXAMPLE.exists() else ""


# --- triage rubric (analysis/rubric.md) -----------------------------------
# The personal candidate profile the LLM triage scores against. Kept in its own
# markdown file
# keeps the candidate profile. Lives on the server data volume (JOB_RADAR_RUBRIC),
# gitignored; the baked rubric.example.md is the fallback until one is saved.

def rubric_path() -> Path:
    env = os.environ.get("JOB_RADAR_RUBRIC")
    return Path(env) if env else ROOT / "analysis" / "rubric.md"


def load_rubric(path: str | Path | None = None) -> str:
    """The triage rubric text — the saved one, or the baked example fallback so a
    fresh server still has a (placeholder) rubric instead of crashing."""
    p = Path(path) if path else rubric_path()
    if p.exists():
        return p.read_text()
    return EXAMPLE_RUBRIC.read_text() if EXAMPLE_RUBRIC.exists() else ""


def save_rubric(text: str, path: str | Path | None = None) -> str:
    """Write the rubric atomically (so a concurrent triage never reads a partial
    file). Returns the saved text. Raises ValueError if empty."""
    if not text or not text.strip():
        raise ValueError("rubric must not be empty")
    p = Path(path) if path else rubric_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(p)
    return text


def save_config(text: str, path: str | Path | None = None) -> dict:
    """Validate YAML and write it atomically. Raises ValueError on bad content so
    the API can reject it without ever leaving a half-written config on disk."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("config must be a YAML mapping")
    for key in ("title_filter", "location_filter", "sources", "analysis"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise ValueError(f"'{key}' must be a mapping")
    p = Path(path) if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(p)  # atomic swap — a concurrent scan never reads a partial file
    return data
