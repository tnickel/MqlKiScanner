"""Markt-Terminal darf einen laufenden Scan/eine Studie nicht beenden."""
import sys

import pytest

from mqlkiscanner import config
from mqlkiscanner.agenten import __main__ as cli
from mqlkiscanner.agenten import lock, markt, melder, scheduler


@pytest.fixture(autouse=True)
def eigener_skip_guard(monkeypatch):
    monkeypatch.setattr(scheduler, "_guard_skip_vermerkt", {})


def _sperren_sind_gehalten():
    assert not lock.lock_status(config.DATA_DIR)["frei"]
    assert not lock.lock_status(
        config.DATA_DIR, lock.rolle_lock_name("markt"))["frei"]


def _sperren_sind_frei():
    assert lock.lock_status(config.DATA_DIR)["frei"]
    assert lock.lock_status(
        config.DATA_DIR, lock.rolle_lock_name("markt"))["frei"]


def test_daemon_markt_skippt_bei_scan_oder_studie(monkeypatch):
    def unerwartet(**kwargs):
        raise AssertionError("Markt darf das Terminal eines aktiven Scans nicht anfassen")

    monkeypatch.setattr(markt, "tageslauf", unerwartet)
    ergebnis = {"ausgefuehrt": []}
    with lock.lauf_lock(config.DATA_DIR):
        scheduler._rolle_ausfuehren("markt", {}, ergebnis, log=lambda *_: None)
        assert not lock.lock_status(config.DATA_DIR)["frei"]
    assert ergebnis["ausgefuehrt"][0]["status"] == "skipped"
    assert "Lauf-Lock" in ergebnis["ausgefuehrt"][0]["grund"]
    _sperren_sind_frei()


def test_daemon_markt_haelt_beide_sperren_bis_laufende(monkeypatch):
    def tageslauf(**kwargs):
        _sperren_sind_gehalten()
        return {"status": "ok"}

    monkeypatch.setattr(markt, "tageslauf", tageslauf)
    ergebnis = {"ausgefuehrt": []}
    scheduler._rolle_ausfuehren("markt", {}, ergebnis, log=lambda *_: None)
    assert ergebnis["ausgefuehrt"][0]["status"] == "ok"
    _sperren_sind_frei()


def test_daemon_markt_gibt_sperren_bei_ausnahme_frei(monkeypatch):
    def kaputt(**kwargs):
        _sperren_sind_gehalten()
        raise RuntimeError("Kursabfrage fehlgeschlagen")

    monkeypatch.setattr(markt, "tageslauf", kaputt)
    with pytest.raises(RuntimeError, match="Kursabfrage"):
        scheduler._rolle_ausfuehren("markt", {}, {"ausgefuehrt": []}, log=lambda *_: None)
    _sperren_sind_frei()


def test_cli_markt_skippt_bei_scan_oder_studie(monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", ["agenten", "--markt"])

    def unerwartet(**kwargs):
        raise AssertionError("CLI darf das Terminal eines aktiven Scans nicht anfassen")

    monkeypatch.setattr(markt, "tageslauf", unerwartet)
    with lock.lauf_lock(config.DATA_DIR):
        cli.main()
        assert not lock.lock_status(config.DATA_DIR)["frei"]
    assert "CLI-Start übersprungen (Lauf-Lock)" in caplog.text
    _sperren_sind_frei()


def test_cli_markt_haelt_beide_sperren_bis_laufende(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agenten", "--markt"])
    aufrufe = []

    def tageslauf(**kwargs):
        _sperren_sind_gehalten()
        aufrufe.append(kwargs["quelle"])
        return {"status": "ok"}

    monkeypatch.setattr(markt, "tageslauf", tageslauf)
    cli.main()
    assert aufrufe == ["cli"]
    _sperren_sind_frei()


def test_cli_markt_gibt_sperren_bei_ausnahme_frei(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agenten", "--markt"])

    def kaputt(**kwargs):
        _sperren_sind_gehalten()
        raise RuntimeError("Kursabfrage fehlgeschlagen")

    monkeypatch.setattr(markt, "tageslauf", kaputt)
    with pytest.raises(RuntimeError, match="Kursabfrage"):
        cli.main()
    _sperren_sind_frei()


@pytest.mark.parametrize("rolle", ["betreuer", "melder", "chef"])
def test_daemon_andere_rollen_bleiben_bei_scan_parallel(monkeypatch, rolle):
    aufrufe = []

    def rolle_starten(rolle_key, *args):
        aufrufe.append(rolle_key)
        return {"rolle": rolle_key, "status": "ok"}

    monkeypatch.setattr(scheduler, "_rolle_starten", rolle_starten)
    ergebnis = {"ausgefuehrt": []}
    with lock.lauf_lock(config.DATA_DIR):
        scheduler._rolle_ausfuehren(rolle, {}, ergebnis, log=lambda *_: None)
    assert aufrufe == [rolle]
    assert ergebnis["ausgefuehrt"][0]["status"] == "ok"


def test_cli_andere_rolle_bleibt_bei_scan_parallel(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agenten", "--digest"])
    aufrufe = []
    monkeypatch.setattr(melder, "tagesdigest", lambda **kwargs: (
        aufrufe.append(kwargs["quelle"]) or {"status": "ok", "meldung_id": 1}))
    with lock.lauf_lock(config.DATA_DIR):
        cli.main()
    assert aufrufe == ["cli"]
