# -*- coding: utf-8 -*-
"""Prompt-Regressionstests MIT echten GLM-Modellaufrufen (Marker `llm`).

Diese Tests sichern den Prompt-MECHANISMUS — nicht einzelne Formulierungen:
Sie stellen sicher, dass glm-5.3 die bindenden Regeln der Vorlagen befolgt,
die aus dem Vorfall vom 19.09.2026 gelernt wurden (Portfolio empfahl das
ausgeschlossene Kenni-Signal und sortierte Gold Spike wegen des Schock-
szenarios aus). Sie nutzen DIESELBEN Builder wie die Produktion
(llm.prompt_fill) — getestet ist damit exakt der ausgelieferte Mechanismus.

Kosten/Ausfuehrung (pytest.ini):
    pytest            -> diese Tests sind DESELEKTIERT (keine Token-Kosten)
    pytest -m llm     -> nur diese Tests, 4 starke Modellaufrufe
Ausfuehren, wann immer an Vorlagen, Payloads, Buildern oder Ampel-Bindung
etwas geaendert wird. Ohne konfigurierten GLM-Key werden sie uebersprungen.

Die 4 Regressionsflaelle:
1. Gesamtbericht: Ausschlusslisten-Signal (Ampel ⛔) mit ansonsten Top-Zahlen
   muss ABLEHNUNG bleiben — nie WATCHLIST/EMPFEHLUNG (Kenni-Fall).
2. Gesamtbericht: ohne bewiesenen Stop niemals EMPFEHLUNG (Kernkriterium).
3. Portfolio: ausgeschlossenes Signal erhaelt NIE eine Gewichtung; das
   gruene Signal wird empfohlen; Kurzfassung und Vorschlag nennen dieselbe
   Auswahl (interne Konsistenz).
4. Portfolio: hohes Schockszenario allein ist KEIN Ablehnungsgrund — das
   sonst saubere Signal bleibt empfohlen (Gold-Spike-Fall).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Real-Zugangsdaten und Netzwerk-Zugang VOR der hermetischen conftest-
# Fixture sichern: Modul-Import passiert zur Sammelzeit, Fixtures erst
# pro Test. Danach stellen wir beides im glm_client-Fixture gezielt wieder her.
_ORIG_SESSION_REQUEST = requests.sessions.Session.request


def _real_glm_key() -> str:
    for var in ("MQLKISCANNER_GLM_KEY", "GLM_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(("GLM_API_KEY=", "MQLKISCANNER_GLM_KEY=")):
                _, _, val = line.partition("=")
                if val.strip():
                    return val.strip()
    secrets = ROOT / "config" / "secrets.local.json"
    if secrets.exists():
        try:
            return str(json.loads(secrets.read_text(encoding="utf-8"))
                       .get("glm_api_key", "") or "")
        except (json.JSONDecodeError, OSError):
            pass
    return ""


_REAL_KEY = _real_glm_key()
if _REAL_KEY:
    from mqlkiscanner import config as _real_config
    _REAL_SETTINGS = _real_config.load_settings()
else:
    _REAL_SETTINGS = {}

pytestmark = [pytest.mark.llm]


@pytest.fixture()
def glm_client(monkeypatch):
    """Echter GlmClient: echtes Netz, echter Key, reale Endpunkt-Settings."""
    if not _REAL_KEY:
        pytest.skip("Kein GLM-Key gefunden (env/.env/secrets.local.json) — "
                    "Prompt-Regressionstests uebersprungen.")
    monkeypatch.setattr(requests.sessions.Session, "request",
                        _ORIG_SESSION_REQUEST)
    monkeypatch.setenv("GLM_API_KEY", _REAL_KEY)
    from mqlkiscanner.llm.client import GlmClient
    return GlmClient(
        model_stufe1=_REAL_SETTINGS.get("model_stufe1", "glm-5.3-flash"),
        model_stufe2=_REAL_SETTINGS.get("model_stufe2", "glm-5.3"),
        max_total_tokens=1_000_000,
        base_url=_REAL_SETTINGS.get("glm_base_url"))


# ----------------------------------------------------------------- Hilfswelt

def _signal(result_id: int, name: str, **kwargs) -> "object":
    from mqlkiscanner import pipeline
    base = dict(
        id=result_id, name=name, platform="MT5",
        url=f"https://www.mql5.com/en/signals/{result_id}",
        autor="Testautor", abonnenten=42, abo_preis_usd=30.0, wochen=60,
        growth_pct=300.0, ertrag_monat_pct=21.5, pf=3.0,
        dd_equity_pct=4.2, dd_balance_pct=5.0, broker_server="Test-Live",
        symbole="XAUUSD", score=3.9, martingale_flag=False,
        stop_evidence="direct", stop_nachweis="Orderbuch: 383/383 mit SL",
        trading_dd_pct=4.6, trading_dd_usd=158.0, winrate_pct=84.0,
        max_verlustserie=13, verlustserie_usd=-155.0,
        peak_positionen=3, peak_netto_lots=0.03, shock_usd=600.0,
        shock_pct_max=17.5, shock_pct_peak_account=30.5,
        forensik_vorhanden=True,
    )
    base.update(kwargs)
    result = pipeline.ScanResult(**base)
    pipeline.refresh_report_verdict(result, {})
    return result


_STUB_TRADE = ("Trade-Analyse (Teststubs): Session-Scalper auf XAUUSD, "
               "flache 0.01-Lots, Haltedauer im Minutenbereich.")
_STUB_RISIKO = ("Risiko-Analyse (Teststubs): Drawdown gering, Stop-Nachweis "
                "vorhanden, kein Martingale.")


from bericht_parse import abschnitt as _abschnitt, aufnahmen as _aufnahmen, \
    hat_aufnahme as _hat_aufnahme, urteil as _urteil_gefunden


def _urteil(bericht: str) -> str:
    """Urteil-Zeile MIT Assertion (klare Fehlermeldung bei Formatbruch)."""
    wert = _urteil_gefunden(bericht)
    assert wert, ("Kein Urteil (EMPFEHLUNG|WATCHLIST|ABLEHNUNG) im Bericht:\n"
                  + bericht[:600])
    return wert


# ------------------------------------------------- Test 1: Ausschluss bindet

def test_gesamtbericht_ausschluss_bleibt_ablehnung(glm_client, monkeypatch):
    """Kenni-Fall: ⛔-Ampel schlaegt schoene Zahlen — Urteil ABLEHNUNG."""
    from mqlkiscanner import config, pipeline
    from mqlkiscanner.llm import prompt_fill
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 555001, "name": "Ausschluss Muster",
                            "grund": "Verlustserie und Schranke historisch verletzt"}]})
    result = _signal(555001, "Ausschluss Muster")
    assert result.ampel == "⛔", f"Vorbedingung: Ampel ⛔, nicht {result.ampel}"
    prompt = prompt_fill.build_gesamtbericht_prompt(
        result, pipeline._kriterien_text({}), _STUB_TRADE, _STUB_RISIKO)
    bericht = glm_client.chat(prompt, stufe=2, temperature=0.2, max_tokens=12288)
    assert _urteil(bericht) == "ABLEHNUNG", \
        f"Ausschlusslisten-Signal wurde nicht abgelehnt:\n{bericht[:800]}"


# --------------------------------------- Test 2: Ohne Stop-Nachweis keine EMPFEHLUNG

def test_gesamtbericht_ohne_stop_nie_empfehlung(glm_client):
    from mqlkiscanner import pipeline
    from mqlkiscanner.llm import prompt_fill
    result = _signal(555002, "Ohne Stop Muster",
                     stop_evidence="none", stop_nachweis="kein Nachweis")
    assert result.ampel == "🟡"
    prompt = prompt_fill.build_gesamtbericht_prompt(
        result, pipeline._kriterien_text({}), _STUB_TRADE, _STUB_RISIKO)
    bericht = glm_client.chat(prompt, stufe=2, temperature=0.2, max_tokens=12288)
    assert _urteil(bericht) != "EMPFEHLUNG", \
        f"Ohne bewiesenen Stop darf nie EMPFEHLUNG stehen:\n{bericht[:800]}"


# ------------------------------------- Test 3: Portfolio nimmt Ausgeschlossene nie auf

def test_portfolio_ausschluss_erhaelt_keine_gewichtung(glm_client, monkeypatch):
    from mqlkiscanner import config, pipeline
    from mqlkiscanner.llm import prompt_fill
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 555003, "name": "Rot Muster",
                            "grund": "Verlustserie und Schranke historisch verletzt"}]})
    gruen = _signal(555004, "Gruen Muster")
    rot = _signal(555003, "Rot Muster")
    assert gruen.ampel == "🟢" and rot.ampel == "⛔"
    eintraege = [{
        "kandidat": json.loads(pipeline._kandidat_json(r)),
        "forensik": json.loads(pipeline._forensik_json(r)),
        "assets": r.symbole,
        "kurzfassung": f"{r.name}: Testkurzfassung.",
        "gesamtbericht": f"Urteil-Stub {r.name}: siehe Ampel {r.ampel}.",
    } for r in (gruen, rot)]
    prompt = prompt_fill.build_portfolio_prompt(
        json.dumps(eintraege, ensure_ascii=False),
        pipeline._kriterien_text({}))
    bericht = glm_client.chat(prompt, stufe=2, temperature=0.2, max_tokens=12288)

    aufnahmen = _aufnahmen(_abschnitt(bericht, "Portfolio-Vorschlag"))
    assert aufnahmen, f"Keine Listenzeilen '- NAME — GEWICHT % — Rolle' " \
                      f"gefunden (Format-Verstoss):\n{bericht[:800]}"
    assert _hat_aufnahme(aufnahmen, "Gruen Muster"), \
        f"Das gruene Signal wurde nicht mit Gewichtung empfohlen: {aufnahmen}"
    assert not _hat_aufnahme(aufnahmen, "Rot Muster"), \
        f"Ausgeschlossenes Signal erhielt eine Gewichtung: {aufnahmen}"
    assert "Gruen Muster" in bericht.splitlines()[0], \
        f"Kurzfassung nennt nicht die empfohlene Auswahl:\n{bericht[:300]}"


# -------------------------- Test 4: Schockszenario allein ist kein Ablehnungsgrund

def test_portfolio_schock_allein_kein_ausschlussgrund(glm_client):
    """Gold-Spike-Fall: Stress-Schock begruendet Gewichtung, nicht Ablehnung."""
    from mqlkiscanner import pipeline
    from mqlkiscanner.llm import prompt_fill
    schock = _signal(555005, "Schock Muster",
                     shock_usd=1050.0, shock_pct_max=137.0,
                     shock_pct_peak_account=290.0, peak_positionen=12,
                     peak_netto_lots=0.21)
    assert schock.ampel == "🟢", "Trotz Schock bleibt alle Ampel-Logik gruen."
    eintraege = [{
        "kandidat": json.loads(pipeline._kandidat_json(schock)),
        "forensik": json.loads(pipeline._forensik_json(schock)),
        "assets": schock.symbole,
        "kurzfassung": "Schock Muster: Testkurzfassung.",
        "gesamtbericht": "Urteil-Stub Schock Muster: siehe Ampel.",
    }]
    prompt = prompt_fill.build_portfolio_prompt(
        json.dumps(eintraege, ensure_ascii=False),
        pipeline._kriterien_text({}))
    bericht = glm_client.chat(prompt, stufe=2, temperature=0.2, max_tokens=12288)

    aufnahmen = _aufnahmen(_abschnitt(bericht, "Portfolio-Vorschlag"))
    assert _hat_aufnahme(aufnahmen, "Schock Muster") and \
        any(w > 0 for n, w in aufnahmen.items() if "Schock Muster" in n), \
        (f"Signal mit Schockszenario wurde nicht mit Gewichtung empfohlen "
         f"(Schock ist kein Ablehnungsgrund): {aufnahmen}\n{bericht[:800]}")
