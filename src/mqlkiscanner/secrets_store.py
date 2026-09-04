# -*- coding: utf-8 -*-
"""Geheimnis-Verwaltung: Umgebungsvariablen > .env > config/secrets.local.json.

Niemals Werte in Code oder committete Dateien schreiben (AGENTS.md).
secrets.local.json und .env sind via .gitignore aus dem Repository
ausgeschlossen; diese Datei speichert nur Pfade und Reihenfolge.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import CONFIG_DIR, ROOT

SECRETS_FILE = CONFIG_DIR / "secrets.local.json"
ENV_FILE = ROOT / ".env"

_SECRET_KEYS = ("glm_api_key", "mql5_user", "mql5_pass")
_ENV_ALIASES = {
    "glm_api_key": ("MQLKISCANNER_GLM_KEY", "GLM_API_KEY"),
    "mql5_user": ("MQL5_USER",),
    "mql5_pass": ("MQL5_PASS",),
}


def _load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def _load_local_file() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    try:
        return json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_secret(key: str) -> str:
    """Holt ein Geheimnis: Prozess-Umgebung > .env > secrets.local.json."""
    for env_name in _ENV_ALIASES.get(key, ()):
        val = os.environ.get(env_name)
        if val:
            return val
    env = _load_env_file()
    for env_name in _ENV_ALIASES.get(key, ()):
        if env.get(env_name):
            return env[env_name]
    return str(_load_local_file().get(key, "") or "")


def save_secrets(**fields: str) -> None:
    """Schreibt Geheimnisse in config/secrets.local.json (gitignored).

    Wird von der GUI (Admin-Bereich) benutzt. Existierende Felder bleiben
    erhalten, leere Strings ueberschreiben (Key entfernen = "" setzen).
    """
    local = _load_local_file()
    for key, val in fields.items():
        if key in _SECRET_KEYS:
            local[key] = val
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(
        json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        os.chmod(SECRETS_FILE, 0o600)  # best effort (Windows ignoriert teils)
    except OSError:
        pass


def secret_status() -> dict[str, bool]:
    """Booleans fuer die GUI-Anzeige (nur gesetzt ja/nein, nie der Wert)."""
    return {key: bool(get_secret(key)) for key in _SECRET_KEYS}
