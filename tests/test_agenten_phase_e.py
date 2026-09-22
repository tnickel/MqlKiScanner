# -*- coding: utf-8 -*-
"""Phase E: Chefermittler (Lagebericht) und autonome Scan-Anstöße.

Der Scan-Launcher wird mit einer Fake-Pipeline getestet: Die Orchestrierung
(Listen → Kandidaten → Gelb/Grün-Scope → Forensik → KI → Portfolio →
Postfach-Meldung) ist der Prüfgegenstand — die echte Pipeline hat ihre
eigenen Tests und wäre hier nur langsam und teuer.
"""
from datetime import date, datetime

import pytest

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.agenten import chef, dossier, journal, melder, rollen
from mqlkiscanner.agenten import scan_launcher, scheduler


# ── Chefermittler ──────────────────────────────────────────────────

def test_lagebericht_verschiebt_bei_laufendem_scan():
    journal.lauf_starten("dirigent", quelle="daemon")  # bleibt 'laeuft'
    ergebnis = chef.lagebericht(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "skipped"
    assert "Scan-Lauf" in ergebnis["grund"]


def test_lagebericht_ins_postfach_mit_llm(monkeypatch):
    db.init_db()
    db.upsert_signal(2349227, name="Gold Spike", stats={})
    db.store_forensik(2349227, {"ampel": "🟢"})
    dossier.profil_speichern(2349227, "Profil", "glm-5.3", {})
    dossier.beobachtung_speichern(2349227, "KONFORM", "Alles normal.")
    monkeypatch.setattr(chef, "_llm_bericht",
                        lambda *a, **k: "## Lage\nAlles ruhig, eine Empfehlung.")
    ergebnis = chef.lagebericht(quelle="test", log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    bericht = journal.meldungen_lesen(typ="lagebericht")[0]
    assert "Alles ruhig" in bericht["text"]
    assert bericht["prioritaet"] == 1


def test_lagebericht_grundlage_und_code_fallback(monkeypatch):
    db.init_db()
    db.upsert_signal(1, name="A", stats={})
    db.store_forensik(1, {"ampel": "🟡"})
    db.store_ampel_wechsel(1, "2026-09-21 10:00:00", "daemon", "🟢", "🟡",
                           True, "verschlechterung", gruende=[], name="A")
    monkeypatch.setattr(chef, "_llm_bericht", lambda *a, **k: None)
    ergebnis = chef.lagebericht(quelle="test", log=lambda *_: None)
    text = ergebnis["text"]
    assert "maschinelle Fassung" in text
    assert "A" in text


def test_dossiers_kompakt_zaehlt_wochenbeobachtungen(monkeypatch):
    from mqlkiscanner.agenten import betreuer
    db.init_db()
    db.upsert_signal(2, name="B", stats={})
    db.store_forensik(2, {"ampel": "🟢"})
    dossier.beobachtung_speichern(2, "STILBRUCH", "Nächtliche Trades.")
    monkeypatch.setattr(betreuer, "kandidaten",
                        lambda settings=None: [{"id": 2, "name": "B",
                                                "platform": "", "ampel": "🟢"}])
    kompakt = chef.dossiers_kompakt()
    assert kompakt[0]["signal"] == "B"
    assert kompakt[0]["beobachtungen_7t"]["STILBRUCH"] == 1
    assert len(kompakt[0]["stilbrueche_7t"]) == 1


# ── Scan-Launcher (Fake-Pipeline) ──────────────────────────────────

class _FakeResult:
    def __init__(self, sid, name):
        self.id, self.name = sid, name
        self.forensik_vorhanden = True
        self.fehler = ""
        self.source_kind = "live"


class _FakePipeline:
    """Orchestrierungs-Stub: gleiche Methoden wie ScanPipeline."""
    aufrufe: list[str] = []

    def __init__(self, settings=None, quelle="full"):
        self.settings = settings or {}
        self.quelle = quelle
        self.llm = type("L", (), {"has_key": False})()

    def crawl(self, on_progress, log):
        _FakePipeline.aufrufe.append("crawl")
        return [{"id": 2349227, "name": "Gold Spike"},
                {"id": 2, "name": "Rot"}]

    def build_candidates(self, signale, log):
        _FakePipeline.aufrufe.append("kandidaten")
        return [{"id": s["id"], "name": s["name"]} for s in signale]

    def analyze_candidate(self, session, kandidat, log, should_stop=None):
        _FakePipeline.aufrufe.append(f"analyze:{kandidat['id']}")
        return _FakeResult(kandidat["id"], kandidat["name"])

    def run_llm(self, results, log, on_progress=None, should_stop=None):
        _FakePipeline.aufrufe.append("llm")
        return {"completed": 3 * len(results)}

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


def test_scan_full_orchestrierung_und_meldung(fake_pipeline):
    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "ok"
    assert fake_pipeline.aufrufe[:3] == ["crawl", "kandidaten", "analyze:2349227"]
    assert "analyze:2" in fake_pipeline.aufrufe
    assert ergebnis["geprueft"] == 2
    meldung = journal.meldungen_lesen(typ="scan")[0]
    assert "full" in meldung["titel"]
    assert meldung["prioritaet"] == 1
    lauf = journal.list_laeufe(rolle="dirigent")[0]
    assert lauf["status"] == "ok"
    # Monats-Merker gesetzt: kein zweiter Full-Scan im selben Monat.
    assert scan_launcher.scan_monat_gestartet("full")


def test_scan_gelbgruen_nur_gruen_gelb(fake_pipeline, monkeypatch):
    db.init_db()
    db.upsert_signal(2349227, name="Gold Spike", stats={})
    db.store_forensik(2349227, {"ampel": "🟢"})
    monkeypatch.setattr(pipeline, "results_from_db",
                        lambda settings=None: [
                            type("R", (), {"id": 2349227, "ampel": "🟢",
                                           "source_kind": "live"})()])
    ergebnis = scan_launcher.starte_scan("gelbgruen", quelle="test",
                                         log=lambda *_: None)
    assert fake_pipeline.aufrufe.count("analyze:2") == 0  # rotes Signal ignoriert
    assert "analyze:2349227" in fake_pipeline.aufrufe
    assert ergebnis["geprueft"] == 1


def test_scan_ohne_mql5_login_abbrechend(fake_pipeline, monkeypatch):
    monkeypatch.setattr(scan_launcher.Mql5Session, "has_credentials",
                        property(lambda self: False))
    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "ok"  # Lauf sauber abgeschlossen …
    assert "Kein MQL5-Login" in ergebnis["zusammenfassung"]  # … mit klarem Grund
    assert "analyze" not in str(fake_pipeline.aufrufe)


def test_scan_lock_belegt_wird_uebersprungen(fake_pipeline, monkeypatch):
    from mqlkiscanner.agenten import lock
    with lock.lauf_lock(config.DATA_DIR, "agenten_lauff"):
        ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                             log=lambda *_: None)
    assert ergebnis["status"] == "skipped"
    assert "Lauf-Lock" in ergebnis["grund"]


# ── Scheduler-Takte (Phase E) ──────────────────────────────────────

def test_sonntag_gelbgruen_scan_faellig():
    settings = config.load_settings()
    assert scheduler.faellige_scans(datetime(2026, 9, 27, 12, 0), settings) == \
        ["gelbgruen"]
    assert scheduler.faellige_scans(datetime(2026, 9, 27, 11, 0), settings) == []
    # Nach dem Start hält der Tages-Merker den zweiten Anstoß zurück.
    journal.steuerung_setzen("scan_gelbgruen_letzter", "2026-09-27")
    assert scheduler.faellige_scans(datetime(2026, 9, 27, 13, 0), settings) == []


def test_monatserster_werktag_full_scan_faellig():
    settings = config.load_settings()
    # 1.10.2026 ist ein Donnerstag; erst ab Startzeit + 60.
    assert scheduler.faellige_scans(datetime(2026, 10, 1, 6, 0), settings) == []
    assert scheduler.faellige_scans(datetime(2026, 10, 1, 7, 30), settings) == \
        ["full"]
    # Merker auf den künstlichen Monat/Tag setzen (Vermerker schreibt real
    # heute — die Takt-Prüfung fragt den Kontext-Zeitpunkt ab).
    journal.steuerung_setzen("scan_full_monat", "2026-10")
    journal.steuerung_setzen("scan_full_letzter", "2026-10-01")
    assert scheduler.faellige_scans(datetime(2026, 10, 2, 7, 30), settings) == []
    assert scheduler.faellige_scans(datetime(2026, 11, 5, 7, 30), settings) == \
        ["full"]


def test_chef_faellig_sonntag_abends_und_nach_full_scan():
    settings = config.load_settings()
    # Sonntag 19:00 — Chef fällig (kein Scan aktiv).
    assert "chef" in scheduler.faellige_rollen(datetime(2026, 9, 27, 19, 0),
                                               settings)
    assert "chef" not in scheduler.faellige_rollen(datetime(2026, 9, 27, 17, 0),
                                                   settings)
    # Am Full-Scan-Tag ab Startzeit + 150 — aber nicht, während der Scan läuft.
    journal.steuerung_setzen("scan_full_monat", "2026-10")
    journal.steuerung_setzen("scan_full_letzter", "2026-10-01")
    journal.lauf_starten("dirigent", quelle="daemon")
    assert "chef" not in scheduler.faellige_rollen(datetime(2026, 10, 1, 9, 0),
                                                   settings)
    journal.lauf_abschliessen(journal.list_laeufe(rolle="dirigent")[0]["id"],
                              "ok")
    assert "chef" in scheduler.faellige_rollen(datetime(2026, 10, 1, 9, 0),
                                               settings)


def test_rollen_phase_e_alle_aktiv():
    assert rollen.AKTUELLE_PHASE == "E"
    for rolle in rollen.ROLLEN:
        assert rollen.phase_aktiv(rolle, "E"), rolle.key
