"""Keep UI tests independent of user settings, credentials and saved analyses."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import config, db, secrets_store  # noqa: E402
from mqlkiscanner.llm import prompts  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_app_storage(tmp_path, monkeypatch):
    """Use real storage code, but write exclusively inside pytest's directory."""
    for name, relative in {
        "DATA_DIR": "data",
        "RUNS_DIR": "data/runs",
        "TRADES_DIR": "data/trades",
        "STATS_DIR": "data/stats",
        "CONFIG_DIR": "config",
        "PROMPTS_DIR": "config/prompts",
    }.items():
        path = tmp_path / relative
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(config, "SETTINGS_FILE", config.CONFIG_DIR / "app_settings.json")
    monkeypatch.setattr(db, "DB_PATH", config.DATA_DIR / "mqlkiscanner.db")
    monkeypatch.setattr(secrets_store, "SECRETS_FILE", config.CONFIG_DIR / "secrets.local.json")
    monkeypatch.setattr(secrets_store, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", config.PROMPTS_DIR)
    monkeypatch.setattr(prompts, "PROMPT_FILES", {
        key: config.PROMPTS_DIR / f"{key}.md" for key in prompts.DEFAULTS
    })
    for variable in ("MQLKISCANNER_GLM_KEY", "GLM_API_KEY", "MQL5_USER", "MQL5_PASS"):
        monkeypatch.delenv(variable, raising=False)

    def reject_network(*args, **kwargs):
        raise AssertionError("UI tests must mock external MQL5 and LLM requests")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_network)
    return tmp_path
