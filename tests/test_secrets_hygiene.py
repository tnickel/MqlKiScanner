# -*- coding: utf-8 -*-
"""Secret-Hygiene: nie Geheimnisse in committbare Dateien.

Festgeschriebene Nutzer-Regel: API-Keys (Tradeserver, GLM), MQL5-Zugänge
und Tokens gehören ausschließlich in den secrets_store (Umgebung > .env >
config/secrets.local.json — beide Dateien sind gitignored), nie ins
Repository, nie in app_settings.json und nie in Code. Diese Tests brechen
laut, wenn eine spätere Änderung diese Trennung aufweicht.
"""
from __future__ import annotations

import json

from mqlkiscanner import config, secrets_store


def test_settings_schluessel_sind_nie_geheimnisse():
    """DEFAULT_SETTINGS darf keinen Secret-Namen enthalten (Nur-Zahlen-
    URLs-Flags-Trennung); Geheimnisse leben nur im secrets_store."""
    verboten = set(secrets_store._SECRET_KEYS)
    ueberlapp = verboten.intersection(config.DEFAULT_SETTINGS)
    assert not ueberlapp, (
        f"Diese Schlüssel sind Geheimnisse und gehören NICHT in "
        f"DEFAULT_SETTINGS/app_settings.json: {sorted(ueberlapp)}")


def test_save_secrets_schreibt_nur_die_gitignored_datei():
    secrets_store.save_secrets(glm_api_key="g", tradeserver_api_key="t",
                               mql5_pass="p", downloader_token="d")
    secrets_inhalt = json.loads(
        secrets_store.SECRETS_FILE.read_text(encoding="utf-8"))
    assert secrets_inhalt["tradeserver_api_key"] == "t"
    # Die committbare Einstellungsdatei bleibt frei von alledem …
    config.save_settings({**config.load_settings(), "tradeserver_base_url": "http://x:1"})
    settings_roh = config.SETTINGS_FILE.read_text(encoding="utf-8")
    for schluessel in secrets_store._SECRET_KEYS:
        assert schluessel not in settings_roh, (
            f"{schluessel} ist in app_settings.json gelandet — Geheimnisse "
            "gehören nur in den secrets_store")
    # … und die beiden Dateien sind wirklich verschiedene Pfade.
    assert config.SETTINGS_FILE != config.SECRETS_FILE


def test_gitignore_schuetzt_geheimnis_dateien():
    """.env und secrets.local.json müssen im Repo-Root ignoriert sein —
    sonst reicht ein versehentliches `git add -A`, um Keys zu committen
    (Vorfall vom 20.09.2026, siehe Projektstand)."""
    ignore_datei = config.ROOT / ".gitignore"
    inhalt = ignore_datei.read_text(encoding="utf-8")
    assert ".env" in inhalt, ".gitignore deckt .env nicht mehr ab"
    assert "secrets.local.json" in inhalt, (
        ".gitignore deckt config/secrets.local.json nicht mehr ab")
