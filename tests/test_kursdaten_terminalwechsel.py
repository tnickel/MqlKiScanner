"""Terminalwechsel mit Fake-SDK und Fake-Prozessen, ohne echte MT5-Instanzen."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten


@pytest.fixture
def terminals(tmp_path, monkeypatch):
    pfade = []
    for name in ("Tickmill", "ActivTrades", "Vantage"):
        exe = tmp_path / name / "terminal64.exe"
        exe.parent.mkdir()
        exe.touch()
        pfade.append(str(exe))
    state = SimpleNamespace(
        pfade=pfade, running=set(), active=None, starts=[], inits=[],
        stops=[], shutdowns=[], init_fehler={}, datenpfade={}, stop_fehler=set())

    def popen(args, **kwargs):
        state.starts.append((args, kwargs))
        state.running.add(args[0])

    def initialize(pfad, **kwargs):
        state.inits.append((pfad, kwargs))
        state.active = pfad
        fehler = state.init_fehler.get(pfad)
        if isinstance(fehler, Exception):
            raise fehler
        return fehler is not False

    def info():
        return SimpleNamespace(
            data_path=state.datenpfade.get(state.active, str(Path(state.active).parent)),
            connected=True)

    def shutdown():
        state.shutdowns.append(state.active)
        state.active = None

    def stop(pfad):
        state.stops.append(pfad)
        if pfad in state.stop_fehler:
            return False
        state.running.discard(pfad)
        return True

    state.mt5 = SimpleNamespace(initialize=initialize, terminal_info=info,
                                shutdown=shutdown, last_error=lambda: (1, "fake"))
    monkeypatch.setitem(sys.modules, "MetaTrader5", state.mt5)
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda pfad: pfad in state.running)
    monkeypatch.setattr(kursdaten, "terminal_beenden", stop)
    monkeypatch.setattr(kursdaten.subprocess, "Popen", popen)
    monkeypatch.setattr(kursdaten.time, "sleep", lambda _: None)
    state.kd = kursdaten.KursDaten({"kursdaten_terminals": pfade,
                                   "markt_start_erlauben": True})
    return state


def test_quellen_werden_erst_bei_bedarf_gestartet_und_bleiben_bis_laufende_offen(terminals):
    s = terminals
    assert s.kd.starten()[0]
    assert [args[0] for args, _ in s.starts] == s.pfade[:1]
    assert s.running == {s.pfade[0]}

    assert s.kd.wechsle_terminal()[0]
    assert s.kd.wechsle_terminal()[0]
    assert s.running == set(s.pfade)
    assert s.stops == []
    assert s.shutdowns == s.pfade[:2]
    assert all(kwargs == {"portable": True} for _, kwargs in s.inits)
    assert all(args == [pfad, "/portable"] for (args, _), pfad in zip(s.starts, s.pfade))

    assert s.kd.zurueck_zum_ersten_terminal()[0]
    assert s.running == set(s.pfade)
    assert len(s.starts) == 3  # Zurückwechseln verbindet sich mit laufendem Terminal.
    assert s.stops == []

    s.kd.beenden()
    assert s.stops == s.pfade
    assert s.running == set()
    assert not s.kd._aktiv and s.kd._mt5 is None
    assert s.shutdowns == [*s.pfade, s.pfade[0]]
    s.kd.beenden()
    assert s.stops == s.pfade  # Erfolgreiche Bereinigung ist idempotent.


def test_unbenutzte_konfigurierte_terminals_werden_nicht_beendet(terminals):
    s = terminals
    s.running.add(s.pfade[2])  # Ein unbenutzter konfigurierter Prozess bleibt bestehen.
    assert s.kd.starten()[0]
    s.kd.beenden()
    assert s.stops == s.pfade[:1]
    assert s.running == {s.pfade[2]}


def test_bereits_laufende_verwendete_terminals_gehoeren_bis_zum_laufende_dem_scanner(terminals):
    s = terminals
    s.running.update(s.pfade[:2])
    assert s.kd.starten()[0]
    assert s.kd.wechsle_terminal()[0]
    assert not s.starts and not s.stops
    s.kd.beenden()
    assert s.stops == s.pfade[:2]
    assert not s.running


def test_wechsel_erhaelt_auch_leere_terminalgebundene_cache_eintraege(terminals):
    s = terminals
    cache = {"erstes-terminal|EURUSD|1|2": None,
             "erstes-terminal|XAUUSD|1|2": [{"time": 1, "close": 2.0}]}
    s.kd._cache = cache
    assert s.kd.starten()[0]
    assert s.kd.wechsle_terminal()[0]
    assert s.kd.zurueck_zum_ersten_terminal()[0]
    assert s.kd._cache is cache
    assert s.kd._cache["erstes-terminal|EURUSD|1|2"] is None


def test_fehlender_fallback_pfad_laesst_fruehere_quelle_bis_final_offen(terminals):
    s = terminals
    assert s.kd.starten()[0]
    Path(s.pfade[1]).unlink()
    ok, grund = s.kd.wechsle_terminal()
    assert not ok and "Ausweichterminal" in grund
    assert s.running == {s.pfade[0]}
    assert not s.stops
    assert s.kd.zurueck_zum_ersten_terminal()[0]
    assert len(s.starts) == 1
    s.kd.beenden()
    assert s.stops == s.pfade[:1]


def test_prozess_startfehler_laesst_fruehere_quelle_bis_final_offen(terminals, monkeypatch):
    s = terminals
    assert s.kd.starten()[0]

    def popen_fehler(*args, **kwargs):
        raise OSError("fake process failure")

    monkeypatch.setattr(kursdaten.subprocess, "Popen", popen_fehler)
    ok, grund = s.kd.wechsle_terminal()
    assert not ok and "Portable-Start fehlgeschlagen" in grund
    assert s.running == {s.pfade[0]}
    s.kd.beenden()
    assert s.stops == [s.pfade[1], s.pfade[0]]
    assert not s.running


@pytest.mark.parametrize("init_fehler", [False, RuntimeError("fake start failure")])
def test_fehlgeschlagene_sdk_verbindung_bereinigt_nur_betroffene_instanz(terminals, init_fehler):
    s = terminals
    assert s.kd.starten()[0]
    s.init_fehler[s.pfade[1]] = init_fehler
    assert not s.kd.wechsle_terminal()[0]
    assert not s.kd._aktiv and s.kd._mt5 is None
    assert s.stops == [s.pfade[1]]
    assert s.running == {s.pfade[0]}
    assert s.kd.wechsle_terminal()[0]  # Weitere Quelle bleibt nutzbar.
    assert s.running == {s.pfade[0], s.pfade[2]}
    s.kd.beenden()
    assert s.stops == [s.pfade[1], s.pfade[0], s.pfade[2]]
    assert not s.running


def test_falscher_portable_datenpfad_schliesst_nur_betroffene_quelle(terminals):
    s = terminals
    assert s.kd.starten()[0]
    s.datenpfade[s.pfade[1]] = str(Path(s.pfade[1]).parent.parent / "AppData")
    ok, grund = s.kd.wechsle_terminal()
    assert not ok and "andere Datenablage" in grund
    assert s.stops == [s.pfade[1]]
    assert s.running == {s.pfade[0]}
    s.kd.beenden()
    assert s.stops == [s.pfade[1], s.pfade[0]]


def test_ohne_startfreigabe_keine_prozesse_und_keine_finalen_stops(terminals):
    s = terminals
    s.kd.start_erlauben = False
    assert not s.kd.starten()[0]
    assert not s.kd.wechsle_terminal()[0]
    s.kd.beenden()
    assert not s.inits and not s.starts and not s.stops


def test_shutdown_fehler_verhindert_finale_prozess_bereinigung_nicht(terminals, monkeypatch):
    s = terminals
    assert s.kd.starten()[0]
    assert s.kd.wechsle_terminal()[0]

    def shutdown_fehler():
        raise RuntimeError("fake shutdown failure")

    monkeypatch.setattr(s.mt5, "shutdown", shutdown_fehler)
    s.kd.beenden()
    assert s.stops == s.pfade[:2]
    assert not s.running


def test_fehlgeschlagener_stop_wird_ohne_verlust_anderer_quellen_wiederholt(terminals):
    s = terminals
    assert s.kd.starten()[0]
    assert s.kd.wechsle_terminal()[0]
    s.stop_fehler.add(s.pfade[0])
    s.kd.beenden()
    assert s.stops == s.pfade[:2]
    assert s.running == {s.pfade[0]}
    s.stop_fehler.clear()
    s.kd.beenden()
    assert s.stops == [s.pfade[0], s.pfade[1], s.pfade[0]]
    assert not s.running


def test_fehlgeschlagene_startbereinigung_bleibt_fuer_final_vorgemerkt(terminals):
    s = terminals
    assert s.kd.starten()[0]
    s.init_fehler[s.pfade[1]] = False
    s.stop_fehler.add(s.pfade[1])
    assert not s.kd.wechsle_terminal()[0]
    assert s.running == set(s.pfade[:2])
    s.stop_fehler.clear()
    s.kd.beenden()
    assert s.stops == [s.pfade[1], s.pfade[0], s.pfade[1]]
    assert not s.running


def test_exception_beim_stop_verhindert_bereinigung_weiterer_quellen_nicht(terminals, monkeypatch):
    s = terminals
    assert s.kd.starten()[0]
    assert s.kd.wechsle_terminal()[0]
    normaler_stop = kursdaten.terminal_beenden

    def stop(pfad):
        if pfad == s.pfade[0]:
            raise OSError("fake stop failure")
        return normaler_stop(pfad)

    monkeypatch.setattr(kursdaten, "terminal_beenden", stop)
    s.kd.beenden()
    assert s.running == {s.pfade[0]}
    assert s.stops == [s.pfade[1]]
    monkeypatch.setattr(kursdaten, "terminal_beenden", normaler_stop)
    s.kd.beenden()
    assert not s.running
