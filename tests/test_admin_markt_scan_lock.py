"""Der Admin-Verbindungstest darf keine laufenden Kursmessungen stoeren."""
import sys
from types import SimpleNamespace

import pytest

from mqlkiscanner import config, kursdaten
from mqlkiscanner.agenten import lock, marktdata


def _lock_ist_exklusiv():
    assert not lock.lock_status(config.DATA_DIR)["frei"]
    with pytest.raises(lock.LockBesetzt):
        with lock.lauf_lock(config.DATA_DIR):
            raise AssertionError("Paralleler Kurslauf durfte nicht starten")


def _lock_ist_wieder_frei():
    assert lock.lock_status(config.DATA_DIR)["frei"]
    with lock.lauf_lock(config.DATA_DIR):
        pass


def _anbieter_faken(monkeypatch, *, fehler_bei=None, fehler_typ=RuntimeError,
                    verbunden=True):
    aufrufe = []

    def aktion(name):
        _lock_ist_exklusiv()
        aufrufe.append(name)
        if name == fehler_bei:
            raise fehler_typ("synthetischer Verbindungsfehler")

    class AnbieterFake:
        def __init__(self, settings):
            aktion("init")
            assert settings["kursdaten_terminals"] == ["TestTerminal/terminal64.exe"]
            assert settings.get("markt_start_erlauben", False) is False

        def starten(self):
            aktion("start")
            return verbunden, "synthetischer Verbindungsstatus"

        def beenden(self):
            aktion("cleanup")

    def rates(*args):
        aktion("kurse")
        return [{"close": 100.0}]

    monkeypatch.setattr(kursdaten, "KursDaten", AnbieterFake)
    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: True)
    monkeypatch.setitem(sys.modules, "MetaTrader5", SimpleNamespace(
        terminal_info=lambda: SimpleNamespace(name="Fake-Terminal"),
        symbol_select=lambda *args: True,
        copy_rates_from_pos=rates,
        TIMEFRAME_H1=16385))
    return aufrufe


SETTINGS = {"markt_terminal_pfad": "TestTerminal/terminal64.exe"}


def test_admin_test_fasst_bei_lauf_lock_keinen_terminal_an(monkeypatch):
    def verboten(*args, **kwargs):
        raise AssertionError("Aktiver Scan/Studie darf weder Start noch Cleanup ausloesen")

    monkeypatch.setattr(marktdata, "terminal_laueft", verboten)
    monkeypatch.setattr(kursdaten.KursDaten, "starten", verboten)
    monkeypatch.setattr(kursdaten.KursDaten, "beenden", verboten)
    with lock.lauf_lock(config.DATA_DIR):
        ergebnis = marktdata.verbindung_testen(SETTINGS)
        assert not ergebnis["ok"]
        assert "übersprungen" in ergebnis["grund"]
        assert "aktiv" in ergebnis["grund"]
        _lock_ist_exklusiv()
    _lock_ist_wieder_frei()


def test_admin_test_haelt_lock_vor_start_bis_nach_cleanup(monkeypatch):
    aufrufe = _anbieter_faken(monkeypatch)
    ergebnis = marktdata.verbindung_testen(SETTINGS)
    assert ergebnis["ok"]
    assert aufrufe == ["init", "start", "kurse", "cleanup"]
    _lock_ist_wieder_frei()


@pytest.mark.parametrize("fehler_bei", ["init", "start", "kurse", "cleanup"])
@pytest.mark.parametrize("fehler_typ", [RuntimeError, TimeoutError])
def test_admin_test_gibt_lock_auch_nach_fehler_oder_timeout_frei(
        monkeypatch, fehler_bei, fehler_typ):
    aufrufe = _anbieter_faken(monkeypatch, fehler_bei=fehler_bei,
                              fehler_typ=fehler_typ)
    with pytest.raises(fehler_typ, match="synthetischer Verbindungsfehler"):
        marktdata.verbindung_testen(SETTINGS)
    if fehler_bei != "init":
        assert aufrufe[-1] == "cleanup"
    _lock_ist_wieder_frei()


def test_admin_test_gibt_lock_nach_abgelehnter_verbindung_frei(monkeypatch):
    aufrufe = _anbieter_faken(monkeypatch, verbunden=False)
    ergebnis = marktdata.verbindung_testen(SETTINGS)
    assert not ergebnis["ok"]
    assert aufrufe == ["init", "start", "cleanup"]
    _lock_ist_wieder_frei()


def test_admin_test_ohne_startfreigabe_startet_kein_fehlendes_terminal(monkeypatch):
    def verboten(*args, **kwargs):
        raise AssertionError("Ohne Startfreigabe darf kein Anbieter angelegt werden")

    monkeypatch.setattr(marktdata, "terminal_laueft", lambda pfad: False)
    monkeypatch.setattr(kursdaten, "KursDaten", verboten)
    ergebnis = marktdata.verbindung_testen(SETTINGS)
    assert not ergebnis["ok"]
    assert "startet es nicht selbst" in ergebnis["grund"]
    _lock_ist_wieder_frei()
