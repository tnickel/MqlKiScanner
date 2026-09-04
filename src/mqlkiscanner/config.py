# -*- coding: utf-8 -*-
"""Zentrale Konfiguration: Pfade, Standardeinstellungen, App-Settings.

Regeln (AGENTS.md):
- Credentials NIE hier — nur via secrets_store (Umgebung > secrets.local.json).
- Diese Datei ist committbar und enthaelt keine Geheimnisse.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RUNS_DIR = DATA_DIR / "runs"
TRADES_DIR = DATA_DIR / "trades"
STATS_DIR = DATA_DIR / "stats"
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"
SETTINGS_FILE = CONFIG_DIR / "app_settings.json"
KNOWN_SIGNALS_FILE = DATA_DIR / "known_signals.json"

MQL5_BASE = "https://www.mql5.com"

# LLM — Zweistufen-Modellwahl (AGENTS.md Design-Regel 5):
#   Stufe 1: Flash-Klasse fuer Massen-Profile im Scan
#   Stufe 2: starkes Modell nur fuer Finalisten (Verdict)
GLM_BASE_URL = "https://api.z.ai/api/paas/v4"
MODEL_STUFE1 = "glm-5.3-flash"
MODEL_STUFE2 = "glm-5.3"

# Scan-Grundeinstellungen (in der GUI aenderbar, persistiert in app_settings.json)
DEFAULT_SETTINGS: dict = {
    "listen_seiten": 2,             # je Liste (MT4 + MT5): Seiten 1..N
    "top_n_export": 5,              # wie viele Kandidaten bekommen Trade-Export + Forensik
    "min_abonnenten": 0,            # Vorfilter Kandidatenliste
    "min_wochen": 26,               # Vorfilter: Track-Record-Laenge
    "schranke_eq_dd_pct": 30.0,     # harte Drawdown-Schranke (AGENTS.md)
    "min_ertrag_pct_monat": 5.0,    # Ertrag muss ueber 5 %/Monat liegen
    "rate_min_interval_s": 2.0,     # Rate-Limit: Mindestabstand Requests (doc/02: 1-2 s)
    "rate_pause_zwischen_signalen_s": 5.0,
    "rate_backoff_429_s": 45.0,     # Wartezeit bei HTTP 429/503
    "llm_stufe1": True,             # Massen-Profile (Flash)
    "llm_stufe2": True,             # Verdicts fuer Finalisten (starkes Modell)
    "llm_max_total_tokens": 200_000,  # Kosten-Budget je Lauf
    "model_stufe1": MODEL_STUFE1,
    "model_stufe2": MODEL_STUFE2,
}

for _d in (DATA_DIR, RUNS_DIR, TRADES_DIR, STATS_DIR, PROMPTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            settings.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    merged = {**DEFAULT_SETTINGS, **settings}
    SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def load_known_signals() -> dict:
    if KNOWN_SIGNALS_FILE.exists():
        return json.loads(KNOWN_SIGNALS_FILE.read_text(encoding="utf-8"))
    return {}
