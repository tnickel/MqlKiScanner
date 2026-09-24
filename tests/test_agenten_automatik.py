# -*- coding: utf-8 -*-
"""Automatik-Seite: konfigurierbare Takte (Tag + Zeit je Job) und UI.

Muster Goldscanner: Der Zeitplan liegt in den Settings
(agenten_{job}_tag/_zeit) und wird je Daemon-Tick neu gelesen. Ohne
explizite Keys gilt das bisherige Verhalten — die Bestands-Tests in
test_agenten_lock_und_scheduler.py und test_agenten_phase_e.py decken
das ab; hier kommen die Abweichungen dazu.
"""
from __future__ import annotations

from datetime import datetime, time

from streamlit.testing.v1 import AppTest

from mqlkiscanner import config
from mqlkiscanner.agenten import scheduler

import pytest

ROOT_PRIO = 0  # Reihenfolge der Rollenliste bleibt: dirigent zuerst


def _settings(**overrides):
    werte = config.load_settings()
    werte.update(overrides)
    return werte


# ── job_termin: Auflösung der Settings ────────────────────────────────

def test_defaults_entsprechen_bisherigem_takt():
    settings = _settings(agenten_start_zeit="06:30")
    assert scheduler.job_termin(settings, "dirigent") == ("werktags", 390)
    assert scheduler.job_termin(settings, "markt") == ("werktags", 395)
    assert scheduler.job_termin(settings, "betreuer") == ("werktags", 405)
    assert scheduler.job_termin(settings, "melder") == ("werktags", 430)
    assert scheduler.job_termin(settings, "chef") == ("sonntag", 1080)
    assert scheduler.job_termin(settings, "teilscan") == ("sonntag", 720)
    assert scheduler.job_termin(settings, "fullscan") == ("monatserster", 450)


def test_expliziter_tag_und_zeit_überschreiben():
    settings = _settings(agenten_betreuer_tag="Dienstag",
                         agenten_betreuer_zeit="09:00")
    dienstag = datetime(2026, 9, 22, 9, 1)
    fällig = scheduler.faellige_rollen(dienstag, settings)
    assert "betreuer" in fällig
    montag = datetime(2026, 9, 21, 9, 1)
    assert "betreuer" not in scheduler.faellige_rollen(montag, settings)


def test_taeglicher_job_läuft_am_wochenende():
    settings = _settings(agenten_dirigent_tag="Täglich")
    sonntag = datetime(2026, 9, 27, 7, 0)
    assert scheduler.faellige_rollen(sonntag, settings) == ["dirigent"]


def test_ungueltige_werte_fallen_auf_default():
    settings = _settings(agenten_markt_zeit="kaputt",
                         agenten_chef_tag="irgendwas")
    assert scheduler.job_termin(settings, "markt") == ("werktags", 395)
    assert scheduler.job_termin(settings, "chef")[0] == "sonntag"


def test_umlaut_taeglich_wird_erkannt():
    assert scheduler.job_termin(
        _settings(agenten_markt_tag="Täglich"), "markt")[0] == "taeglich"


# ── Scans und Chef mit eigenen Takten ─────────────────────────────────

def test_teilscan_an_anderem_tag():
    settings = _settings(agenten_teilscan_tag="Samstag",
                         agenten_teilscan_zeit="10:00")
    assert scheduler.faellige_scans(
        datetime(2026, 9, 26, 10, 30), settings) == ["gelbgruen"]
    assert scheduler.faellige_scans(
        datetime(2026, 9, 26, 9, 0), settings) == []
    # Sonntag (alter Default-Tag) bleibt leer — der Samstag hat übernommen.
    assert scheduler.faellige_scans(
        datetime(2026, 9, 27, 13, 0), settings) == []


def test_chef_zeit_verschiebbar():
    settings = _settings(agenten_chef_zeit="20:30")
    assert "chef" not in scheduler.faellige_rollen(
        datetime(2026, 9, 27, 20, 0), settings)
    assert "chef" in scheduler.faellige_rollen(
        datetime(2026, 9, 27, 21, 0), settings)


def test_chef_anderer_wochentag():
    settings = _settings(agenten_chef_tag="Samstag")
    assert "chef" in scheduler.faellige_rollen(
        datetime(2026, 9, 26, 19, 0), settings)
    assert "chef" not in scheduler.faellige_rollen(
        datetime(2026, 9, 27, 19, 0), settings)


def test_fullscan_zeit_verschiebbar_tag_fest():
    settings = _settings(agenten_fullscan_zeit="08:00",
                         agenten_start_zeit="06:30")
    # 1.10.2026 ist ein Donnerstag: fällig AB 08:00 (statt Default 07:30).
    assert scheduler.faellige_scans(
        datetime(2026, 10, 1, 7, 45), settings) == []
    assert scheduler.faellige_scans(
        datetime(2026, 10, 1, 8, 15), settings) == ["full"]


# ── Seite ─────────────────────────────────────────────────────────────

def _seite(timeout: int = 60) -> AppTest:
    at = AppTest.from_file(str(
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "streamlit_app.py"), default_timeout=timeout)
    at.run()
    assert not at.exception, at.exception
    at.switch_page("app_pages/automatik.py").run()
    assert not at.exception, at.exception
    return at


def _body(at: AppTest) -> str:
    teile = [e.value for e in at.markdown]
    teile += [e.value for e in at.subheader]
    return "\n".join(teile)


def test_automatik_seite_zeigt_daemon_und_zeitplan():
    at = _seite()
    body = _body(at)
    assert "Daemon" in body and "Zeitplan" in body
    assert "Dirigent" in body and "Chefermittler" in body
    assert "1. Werktag im Monat" in body  # Full-Scan-Tag fest
    # Ohne Änderung gibt es keinen Speichern-Knopf (Muster Goldscanner).
    with pytest.raises(KeyError):
        at.button(key="automatik_speichern")


def test_automatik_seite_speichert_tag_und_zeit():
    at = _seite()
    at.selectbox(key="automatik_tag_chef").set_value("Samstag").run()
    at.time_input(key="automatik_zeit_chef").set_value(time(20, 30)).run()
    at.button(key="automatik_speichern").click().run()
    assert not at.exception, at.exception
    settings = config.load_settings()
    assert settings["agenten_chef_tag"] == "Samstag"
    assert settings["agenten_chef_zeit"] == "20:30"


def test_automatik_seite_ohne_aenderung_schreibt_nichts():
    at = _seite()
    # Kein Widget verändert: keine Ungespeichert-Meldung, nichts gespeichert.
    body = _body(at)
    assert "Ungespeicherte Änderungen" not in body
    assert "agenten_chef_tag" not in config.load_settings()
