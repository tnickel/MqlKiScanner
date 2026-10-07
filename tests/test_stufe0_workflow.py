# -*- coding: utf-8 -*-
"""Stufe 0 im GESAMTEN Workflow (doc/23-Review 07.10.2026): Der Ein-Knopf-
Pfad (Full-Scan) läuft Stufe 0 VOR Station 1; alle-roten Clients brechen den
Lauf ab; der autonome Launcher stößt Stufe 0 genauso an."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import warte_auf_lauf
from mqlkiscanner import client_updates, config, db, pipeline
from mqlkiscanner.agenten import scan_launcher
from mqlkiscanner.agenten import journal

import pytest

ROOT = Path(__file__).resolve().parents[1]

_LAUF_SETTINGS = {
    "listen_modus": "beides", "stufe0_aktiv": True,
    "llm_stufe1": False, "llm_stufe2": False,
    "listen_seiten": 1, "top_n_export": 5,
    "fix_signal_ids": [],
}


def _quelle_anlegen() -> dict:
    db.init_db()
    return db.get_quelle(db.add_quelle("fake", "Fake-Quelle", "http://rechner:8199"))


def _zustand(quelle: dict, status: str) -> dict:
    z = client_updates._neuer_zustand(quelle)
    z["status"] = status
    return z


def _scan_seite() -> AppTest:
    return AppTest.from_file(str(ROOT / "app_pages" / "scan.py"), default_timeout=60)


def test_fullscan_laueft_stufe0_vor_station_1(monkeypatch):
    """Ein-Knopf-Versprechen: Scan-Start stößt ZUERST die Client-Updates an;
    erst danach Station 1 (Signale holen)."""
    quelle = _quelle_anlegen()
    reihenfolge: list[str] = []

    def fake_updates(settings, *, log=None, on_fortschritt=None, gestopft=None, **_):
        reihenfolge.append("stufe0")
        zustand = _zustand(quelle, client_updates.FERTIG)
        zustand["signale_geliefert"] = 200
        if on_fortschritt:
            on_fortschritt(zustand)
        return {quelle["kuerzel"]: zustand}

    def fake_crawl(self, on_progress=None, log=None):
        reihenfolge.append("listen")
        return []

    monkeypatch.setattr(client_updates, "starte_alle_updates", fake_updates)
    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", fake_crawl)

    at = _scan_seite()
    at.run()
    assert not at.exception
    at.session_state["scan_command"] = {"mode": "scan", "settings": dict(_LAUF_SETTINGS)}
    at.run()
    warte_auf_lauf(at, timeout_s=90)
    assert not at.exception, at.exception
    workflow = at.session_state["scan_workflow"]
    assert workflow["steps"]["clients"]["status"] == "complete"
    assert workflow["steps"]["listen"]["status"] == "complete"
    assert reihenfolge[:2] == ["stufe0", "listen"]
    # Endstand für den Dialog ist die RÜCKGABE (Review-Fund: nie aus live lesen)
    live = at.session_state["scan_control"]["client_updates"]
    assert live["fake"]["status"] == client_updates.FERTIG
    assert live["fake"]["signale_geliefert"] == 200


def test_fullscan_alle_clients_rot_bricht_vor_station1_ab(monkeypatch):
    """Sind ALLE Clients endgültig 🔴 (Fehler oder offline), wäre der Scan
    reine Alt-Daten-Verarbeitung — Abbruch mit klarer Meldung (doc/23 §6.2)."""
    quelle = _quelle_anlegen()

    def fake_updates(settings, *, log=None, on_fortschritt=None, gestopft=None, **_):
        zustand = _zustand(quelle, client_updates.FEHLER)
        zustand["fehler"] = "Plattform down"
        if on_fortschritt:
            on_fortschritt(zustand)
        return {quelle["kuerzel"]: zustand}

    def fake_crawl(self, on_progress=None, log=None):
        raise AssertionError("Station 1 darf nach Total-Ausfall NICHT laufen")

    monkeypatch.setattr(client_updates, "starte_alle_updates", fake_updates)
    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", fake_crawl)

    at = _scan_seite()
    at.run()
    at.session_state["scan_command"] = {"mode": "scan", "settings": dict(_LAUF_SETTINGS)}
    at.run()
    warte_auf_lauf(at, timeout_s=90)
    assert not at.exception, at.exception
    workflow = at.session_state["scan_workflow"]
    assert workflow["steps"]["clients"]["status"] == "error"
    assert workflow["steps"]["listen"]["status"] == "skipped"
    assert workflow["status"] == "error"


def test_fullscan_mql5_modus_ohne_stufe0(monkeypatch):
    """listen_modus=mql5: Der Scanner lädt selbst — Stufe 0 wird übersprungen,
    Station 1 läuft sofort."""
    aufgerufen = []
    monkeypatch.setattr(client_updates, "starte_alle_updates",
                        lambda *a, **k: aufgerufen.append(a) or {})

    def fake_crawl(self, on_progress=None, log=None):
        return []

    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", fake_crawl)
    _quelle_anlegen()

    at = _scan_seite()
    at.run()
    at.session_state["scan_command"] = {"mode": "scan",
                                        "settings": {**_LAUF_SETTINGS,
                                                     "listen_modus": "mql5"}}
    at.run()
    warte_auf_lauf(at, timeout_s=90)
    assert not at.exception, at.exception
    workflow = at.session_state["scan_workflow"]
    assert workflow["steps"]["clients"]["status"] == "skipped"
    assert workflow["steps"]["listen"]["status"] == "complete"
    assert not aufgerufen


# --- Autonomer Launcher ----------------------------------------------------

class _FakeResult:
    def __init__(self, sid, name):
        self.id, self.name = sid, name
        self.forensik_vorhanden = True
        self.fehler = ""
        self.source_kind = "live"


class _FakePipeline:
    """Orchestrierungs-Stub wie in test_agenten_phase_e — nur die Teile,
    die der Launcher bis Station 2 braucht."""
    aufrufe: list[str] = []

    def __init__(self, settings=None, quelle="full"):
        self.settings = settings or {}
        self.quelle = quelle
        self.llm = type("L", (), {"has_key": False})()

    def crawl(self, on_progress, log):
        _FakePipeline.aufrufe.append("crawl")
        return [{"id": 2349227, "name": "Gold Spike"}, {"id": 2, "name": "Rot"}]

    def build_candidates(self, signale, log, begruendung=None):
        _FakePipeline.aufrufe.append("kandidaten")
        if begruendung is not None:
            for s in signale:
                begruendung.append({"id": s["id"], "name": s["name"],
                                    "quelle": "mql5", "status": "KANDIDAT",
                                    "grund": "Fake"})
        return [{"id": s["id"], "name": s["name"]} for s in signale]

    def analyze_candidate(self, session, kandidat, log, should_stop=None):
        _FakePipeline.aufrufe.append(f"analyze:{kandidat['id']}")
        return _FakeResult(kandidat["id"], kandidat["name"])

    def run_llm(self, results, log, on_progress=None, should_stop=None):
        _FakePipeline.aufrufe.append("llm")
        return {"completed": 0}

    def kursdaten_beenden(self):
        _FakePipeline.aufrufe.append("kursdaten_beenden")

    def run_portfolio(self, results, log, on_progress=None, should_stop=None):
        _FakePipeline.aufrufe.append("portfolio")
        return {"text": "Portfolio"}


@pytest.fixture
def fake_pipeline(monkeypatch):
    _FakePipeline.aufrufe = []
    monkeypatch.setattr(pipeline, "ScanPipeline", _FakePipeline)
    monkeypatch.setattr(scan_launcher, "pipeline", pipeline)
    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.ensure_mql5_cookies",
                        lambda cfg, session, log=None: True)
    monkeypatch.setattr(scan_launcher.Mql5Session, "has_credentials",
                        property(lambda self: True))
    return _FakePipeline


def _merker_zuruecksetzen():
    """Tages-/Monats-Merker des Launchers auf 'lange her' setzen — sonst
    skippt starte_scan den zweiten vollen Lauf im selben Testtag."""
    journal.steuerung_setzen("scan_full_letzter", "2000-01-01")
    journal.steuerung_setzen("scan_full_monat", "2000-01")
    journal.steuerung_setzen("scan_full_versuche", "2000-01-01|0")


def test_launcher_stoesst_stufe0_an(fake_pipeline, monkeypatch):
    """Der autonome Scan (Sonntag/Monat) läuft Stufe 0 vor dem Crawl —
    mit den konfigurierten Regeln (Ziel/Friste aus den Settings)."""
    _merker_zuruecksetzen()
    _quelle_anlegen()
    config.save_settings({"listen_modus": "beides", "stufe0_aktiv": True})
    aufgerufen: list[dict] = []

    def fake_updates(settings, *, log=None, on_fortschritt=None, gestopft=None, **_):
        aufgerufen.append(dict(settings))
        return {}

    monkeypatch.setattr(scan_launcher.client_updates, "starte_alle_updates",
                        fake_updates)
    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    assert len(aufgerufen) == 1
    assert aufgerufen[0]["listen_modus"] == "beides"
    assert "crawl" in fake_pipeline.aufrufe


def test_launcher_alle_kritisch_bricht_ab(fake_pipeline, monkeypatch):
    _merker_zuruecksetzen()
    _quelle_anlegen()
    config.save_settings({"listen_modus": "beides", "stufe0_aktiv": True})

    def fake_updates(settings, *, log=None, on_fortschritt=None, gestopft=None, **_):
        quelle = db.list_quellen(nur_aktiv=True)[0]
        return {quelle["kuerzel"]: _zustand(quelle, client_updates.FEHLER)}

    monkeypatch.setattr(scan_launcher.client_updates, "starte_alle_updates",
                        fake_updates)
    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "fehler"
    assert "Stufe 0" in ergebnis["grund"]
    assert "crawl" not in fake_pipeline.aufrufe
