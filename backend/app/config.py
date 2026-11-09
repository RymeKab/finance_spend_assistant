"""
Settings for the backend.

What this file does
-------------------
Collects every setting the app needs in one place: the Claude API key, which
Claude model to use, timeouts, and where the data files live.

Where the values come from (later sources win)
----------------------------------------------
1. The defaults written below.
2. The file `backend/.env`, if it exists (copy `backend/.env.example` to create it).
3. Real environment variables set in your shell.

The Claude API key
------------------
The key is called `key_1` everywhere in the code. Put it in `backend/.env` as:

    key_1=sk-ant-...

The key is never logged, never returned by the API, and never sent anywhere except
to the Anthropic API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Folder layout: <repo>/backend/app/config.py
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass(frozen=True)
class Settings:
    """All runtime settings. Created once at startup by `load_settings()`."""

    # The Claude API key. `None` means "not configured": /ask then returns 503
    # with a clear message, while /summary keeps working.
    key_1: str | None = field(default=None, repr=False)  # repr=False keeps it out of logs

    # Which Claude model answers questions, and how it is called.
    anthropic_model: str = DEFAULT_MODEL
    # How much the model thinks before answering ("low", "medium", "high"). None = model default.
    llm_effort: str | None = "medium"
    # Current models reject sampling parameters, so temperature is only sent if you set one.
    llm_temperature: float | None = None
    llm_timeout_seconds: float = 60.0  # per call to Claude
    ask_deadline_seconds: float = 120.0  # for the whole question, all calls included
    llm_max_tokens: int = 8000  # per reply, thinking included
    max_tool_rounds: int = 4  # how many times Claude may ask for data per question

    # Where the source files are read from and where the audit log is written.
    data_dir: Path = REPO_ROOT / "data"
    log_dir: Path = BACKEND_DIR / "logs"

    # Which web pages may call this API from a browser (the Vite dev server).
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @property
    def llm_configured(self) -> bool:
        """True when a Claude API key is available."""
        return bool(self.key_1)


def _read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines from a .env file. Blank lines and # comments are ignored."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_settings(env_file: Path | None = BACKEND_DIR / ".env") -> Settings:
    """Build the Settings object from defaults, the .env file and environment variables."""
    file_values = _read_env_file(env_file) if env_file else {}

    def get(*names: str) -> str | None:
        # Environment variables win over the .env file. Names are checked in order,
        # so both `key_1` and `KEY_1` work.
        for name in names:
            if os.environ.get(name):
                return os.environ[name]
        for name in names:
            if file_values.get(name):
                return file_values[name]
        return None

    temperature = get("LLM_TEMPERATURE")
    effort = get("LLM_EFFORT")
    origins = get("CORS_ORIGINS")
    data_dir = get("DATA_DIR")
    log_dir = get("LOG_DIR")

    return Settings(
        key_1=get("key_1", "KEY_1"),
        anthropic_model=get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
        # "none" (or leaving it empty) means: don't send the setting at all.
        llm_effort=None if (effort or "").lower() == "none" else (effort or Settings.llm_effort),
        llm_temperature=None if (temperature or "none").lower() == "none" else float(temperature),
        llm_timeout_seconds=float(get("LLM_TIMEOUT_SECONDS") or Settings.llm_timeout_seconds),
        ask_deadline_seconds=float(get("ASK_DEADLINE_SECONDS") or Settings.ask_deadline_seconds),
        llm_max_tokens=int(get("LLM_MAX_TOKENS") or Settings.llm_max_tokens),
        max_tool_rounds=int(get("MAX_TOOL_ROUNDS") or Settings.max_tool_rounds),
        data_dir=(BACKEND_DIR / data_dir).resolve() if data_dir else REPO_ROOT / "data",
        log_dir=(BACKEND_DIR / log_dir).resolve() if log_dir else BACKEND_DIR / "logs",
        cors_origins=tuple(o.strip() for o in origins.split(",")) if origins else Settings.cors_origins,
    )
