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
REPORTS_DIR = DATA_DIR / "reports"
TRADES_DIR = DATA_DIR / "trades"
STATS_DIR = DATA_DIR / "stats"
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"
DOWNLOADER_DIR = DATA_DIR / "downloader"  # je Signal-ID: {id}/reports/{version}/{name}.pdf
SETTINGS_FILE = CONFIG_DIR / "app_settings.json"
KNOWN_SIGNALS_FILE = DATA_DIR / "known_signals.json"
CONTRACT_SPECS_FILE = DATA_DIR / "contract_specs.json"
FX_RATES_DIR = DATA_DIR / "fx_rates"

MQL5_BASE = "https://www.mql5.com"

# mtime-gebundener Cache fuer load_known_signals (siehe Docstring dort).
_KNOWN_SIGNALS_CACHE: dict = {}

# LLM — GLM-Zugang. WICHTIG (gelernt aus dem elearning-Projekt):
# Es gibt zwei Endpunkte mit getrennten Kontingenten:
#   https://api.z.ai/api/coding/paas/v4   -> GLM Coding Plan (Abo-Keys)
#   https://api.z.ai/api/paas/v4          -> Pay-as-you-go API-Keys (Guthaben)
# Ein Coding-Plan-Abo-Key liefert auf dem Standard-Endpunkt Fehler 1113
# ("Insufficient balance") — deshalb ist der Coding-Endpunkt hier Default.
# Die Base-URL ist im Admin-Bereich aenderbar (glm_base_url).
GLM_BASE_URL_CODING = "https://api.z.ai/api/coding/paas/v4"
GLM_BASE_URL_API = "https://api.z.ai/api/paas/v4"
GLM_BASE_URL = GLM_BASE_URL_CODING

# LLM — Zweistufen-Modellwahl (AGENTS.md Design-Regel 5):
#   Stufe 1: Flash-Klasse fuer Massen-Profile im Scan
#   Stufe 2: starkes Modell nur fuer Finalisten (Verdict)
MODEL_STUFE1 = "glm-5.3-flash"
MODEL_STUFE2 = "glm-5.3"

# MqlDownloader-REST-API (lesend, LAN; Doku: MqlDownloader/doc/REST_API_Dokumentation.md).
# Default-Port 8089; "/api/v1" ergaenzt der Client automatisch, wenn nur Host:Port steht.
DOWNLOADER_DEFAULT_BASE = "http://localhost:8089/api/v1"

# MqlTradeMonitor-Tradeserver (Spring Boot, ROOT-WAR auf Port 8080; Doku:
# doc/06_tradeserver-sync.md). Der Sync ist ein Einmallauf: Register-
# Handshake → Tabelle + PDFs → Complete, danach keine Verbindung.
TRADESERVER_DEFAULT_BASE = "http://tradeserver.example:8080"

# Beide Einstellungsseiten verwenden dieselben Eingabegrenzen. Für Anzahl
# und Vorfilter gibt es keine fachlich begründete obere Grenze.
SCAN_INPUT_BOUNDS = {
    "listen_seiten": (1, 10),
    "top_n_export": (1, None),
    "min_wochen": (0, None),
    "min_abonnenten": (0, None),
}

# Scan-Grundeinstellungen (in der GUI aenderbar, persistiert in app_settings.json)
DEFAULT_SETTINGS: dict = {
    "listen_seiten": 2,             # je Liste (MT4 + MT5): Seiten 1..N
    "listen_modus": "mql5",         # Signale holen: mql5 | quellen | beides (doc/20 §6)
    "fix_signal_ids": [],           # Fix-IDs: immer scannen, Vorfilter umgehen (fix_signale.py)
    "top_n_export": 30,             # wie viele Kandidaten bekommen Trade-Export + Forensik
    "min_abonnenten": 0,            # Vorfilter Kandidatenliste
    "min_wochen": 26,               # Vorfilter: Track-Record-Laenge
    "schranke_eq_dd_pct": 30.0,     # harte Drawdown-Schranke (AGENTS.md)
    # Nutzer-Regel 04.10. abends: KEINE absolute Ertragshuerde mehr (0 = aus) -
    # absolute %/Monat sind beim Kopieren ueber den Lot-Faktor frei waehlbar
    # (1,4 % x Faktor 10 = 14 %, DD skaliert mit, RetDD bleibt gleich);
    # messbarer positiver Ertrag bleibt ueber Calmar >= min_calmar_jahr gefordert.
    "min_ertrag_pct_monat": 0.0,
    # Nutzer-Entscheid 05.10.: Gruen-Gate = JAHRES-Calmar (CAGR ÷ gemessener
    # Max-Equity-DD inkl. Floating). Die fruehere Monats-Schwelle 1,0 war
    # aufgezinst Calmar 14-40 je nach DD — nicht risikoneutral. 3,0 gilt
    # branchenueblich als "sehr gut".
    "min_calmar_jahr": 3.0,
    "rate_min_interval_s": 2.0,     # Rate-Limit: Mindestabstand Requests (doc/02: 1-2 s)
    "rate_pause_zwischen_signalen_s": 5.0,
    "rate_backoff_429_s": 45.0,     # Wartezeit bei HTTP 429/503
    "mql5_fail_fast_after": 3,      # Abbruch nach N systemischen Export-Fehlern in Folge
    "equity_rekonstruktion": True, # Equity-DD aus Kursen nachmessen (MT5-Terminal, Auto-GMT); ohne Terminal still aus
    "llm_stufe1": True,             # Massen-Profile (Flash)
    "llm_stufe2": True,             # Verdicts fuer Finalisten (starkes Modell)
    # 05.10. nachts: 5 Mio reichten fuer Full-Scan + Portfolio nicht mehr
    # (Budget fiel genau vor dem Portfolio-Bericht auf 0) — 10 Mio.
    "llm_max_total_tokens": 10_000_000,  # Token-Budget je Lauf (Abo: grosszuegig)
    "glm_base_url": GLM_BASE_URL,   # Coding-Plan-Endpunkt (Abo); umstellbar auf API-Endpunkt
    "model_stufe1": MODEL_STUFE1,
    "model_stufe2": MODEL_STUFE2,
    "downloader_base_url": "",      # MqlDownloader-REST-Interface (leer = nicht angebunden)
    "tradeserver_base_url": "",     # MqlTradeMonitor-Sync-Ziel (leer = kein Sync möglich)
    "rest_api_enabled": True,       # schreibgeschütztes REST-Interface für MqlRealMonitor
    "rest_api_port": 8611,          # lauscht auf 127.0.0.1; Token optional (secrets_store)
    # ── Stufe 0 „Clients aktualisieren" (doc/23, Nutzer-Auftrag 07.10.) ─
    "stufe0_aktiv": True,           # Full-/Teilscan aktualisieren zuerst alle Clients
    "update_ziel_signale": 200,     # Wunsch je Client (Versuch genügt — MqlDownloader ~50)
    "update_katalog_max_alter_h": 72,  # EINE globale 3-Tage-Schranke für ALLE Clients
    "update_timeout_min": 120,      # Gesamt-Timeout je Client, danach 🟡 Weiterlauf
    "update_login_timeout_min": 10, # Warten auf manuelle Login-Eingabe (Notausgang)
    # ── Agentenbetrieb (doc/19; Phasen A–C) ──────────────────────────
    "agenten_enabled": False,       # Freigabe: darf der Daemon Läufe ausführen?
    "agenten_start_zeit": "06:30",  # täglicher Dirigent-Takt (werktags)
    "agenten_tagesbudget_tokens": 500_000,   # alle Rollen zusammen (doc/19 §10)
    "agenten_monatsbudget_tokens": 5_000_000,
    "agenten_dirigent_llm": True,   # Dirigent darf LLM-Randentscheidungen treffen
    # ── Marktdaten / MetaTrader (Phase C, doc/19 §7) ─────────────────
    "markt_terminal_pfad": r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe",
    # Nutzer-Wunsch 05.10.: MEHRERE Kursdatenquellen (MetaTrader) für die
    # Equity-Rekonstruktion — Priorität in Reihenfolge; Fallback nur für
    # Symbole, die die vorderen Quellen nicht liefern (GMT je Feed
    # unterschiedlich — Auto-GMT-Preisabgleich je Symbol behandelt das).
    # Nutzer-Wunsch 08.10.: Vantage als DRITTE Quelle (C:\Forex\Mt5\Vantage,
    # vom Nutzer eingerichtet) — liefert Aktien PLAIN (AAPL, MSFT, …: neue
    # Kursquelle fuer Aktien-Signale) und die Vantage-Namen NAS100/SP500/
    # USOUSD/UKOUSD/GER40; Gold heisst dort XAUUSD+ (Suffix-Falle, siehe
    # SYMBOL_ALIASE_DEFAULT). Start portabel wie die anderen Quellen
    # (initialize(portable=True), am Lauf-Ende pfadgenau beenden).
    "kursdaten_terminals": [
        r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe",
        r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe",
        r"C:\Forex\Mt5\Vantage\terminal64.exe",
    ],
    "markt_start_erlauben": False,  # Standard: Terminal NIE selbst starten
    "markt_symbole_manuell": "",    # zusätzliche Symbole, Komma/Leerzeichen
    "markt_lookback_tage": 30,      # Kurs-Historie je Symbol (H1+D1)
    "markt_symbol_suffix": "",      # Broker-Postfix am eigenen Terminal,
    #                                 z. B. ".a" — kanonische Symbole
    #                                 (XAUUSD) bleiben in allen Auswertungen
}

# Rollen-Defaults je Rolle (GLM-5.3 als Standard — Nutzer-Vorgabe 22.09.2026).
# Import nach der Definition: rollen.py importiert bewusst nichts aus dem Paket.
from .agenten.rollen import rollen_defaults  # noqa: E402
DEFAULT_SETTINGS.update(rollen_defaults())

for _d in (DATA_DIR, RUNS_DIR, REPORTS_DIR, TRADES_DIR, STATS_DIR, PROMPTS_DIR,
           PROMPTS_DIR / "agenten", DOWNLOADER_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def llm_aktiv(settings: dict) -> bool:
    """Laufen KI-Berichte in diesem Lauf? llm_stufe1/llm_stufe2 wirken gemeinsam.

    Die beiden Schluessel existieren historisch einzeln, werden aber nirgends
    getrennt ausgewertet (Trade-/Risiko-Analyse und Gesamtbericht bilden eine
    Einheit). Diese Funktion macht die Eine-Schalter-Semantik explizit.
    """
    return bool(settings.get("llm_stufe1") or settings.get("llm_stufe2"))


def min_calmar_jahr(settings: dict | None) -> float:
    """Grün-Gate-Schwelle Calmar/Jahr — EINE Lesart für Ampel, Matrix,
    Kriterientext und Sync (Copilot-Review 05.10. spaet, Mittel 4: vorher
    machte `or 3.0` an zwei Stellen aus einer eingestellten 0 wieder 3,0,
    während ampel_for die 0 nutzte). Default nur bei fehlendem/ungültigem
    Wert; negative Werte werden auf 0 begrenzt."""
    default = float(DEFAULT_SETTINGS["min_calmar_jahr"])
    wert = (settings or {}).get("min_calmar_jahr")
    if wert is None or isinstance(wert, bool):
        return default
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return default
    if zahl != zahl or zahl in (float("inf"), float("-inf")):
        return default
    return max(0.0, zahl)


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
    """Ausschluss-/Watchlist-Daten mit mtime-Cache.

    ampel_for und report_basis_for rufen dies je Ergebniszeile; die Datei
    ist winzig, aber haeufige Disk-I/O ist unnoetig. Der Cache ist an
    (Pfad, mtime_ns) gebunden — Aenderungen an der Datei greifen sofort.
    """
    path = KNOWN_SIGNALS_FILE
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        _KNOWN_SIGNALS_CACHE.clear()
        return {}
    cached = _KNOWN_SIGNALS_CACHE.get(key)
    if cached is not None:
        return cached
    data = json.loads(path.read_text(encoding="utf-8"))
    _KNOWN_SIGNALS_CACHE.clear()
    _KNOWN_SIGNALS_CACHE[key] = data
    return data
