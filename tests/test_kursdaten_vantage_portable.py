"""Portable-Start und Datenablage nur mit Fake-MT5, keine echten Terminals."""
import sys
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten


@pytest.fixture(params=["TickmillLifeMql5", "ActiveTrades003", "Vantage"])
def terminal(tmp_path, monkeypatch, request):
    exe = tmp_path / request.param / "terminal64.exe"
    exe.parent.mkdir()
    exe.touch()
    aufrufe = {"start": [], "init": [], "stop": [], "sleep": [], "shutdown": []}
    infos = [SimpleNamespace(data_path=str(exe.parent), connected=True)]

    def info():
        return infos.pop(0) if len(infos) > 1 else infos[0]

    mt5 = SimpleNamespace(
        initialize=lambda *a, **kw: aufrufe["init"].append((a, kw)) or True,
        terminal_info=info, last_error=lambda: (1, "ok"),
        shutdown=lambda: aufrufe["shutdown"].append(True))
    monkeypatch.setitem(sys.modules, "MetaTrader5", mt5)
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: False)
    monkeypatch.setattr(kursdaten, "terminal_beenden", lambda p: aufrufe["stop"].append(p) or True)
    monkeypatch.setattr(kursdaten.subprocess, "Popen",
                        lambda *a, **kw: aufrufe["start"].append((a, kw)))
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: aufrufe["sleep"].append(s))
    kd = kursdaten.KursDaten({"kursdaten_terminals": [str(exe)], "markt_start_erlauben": True})
    return kd, exe, mt5, infos, aufrufe


def test_terminal_startet_explizit_portabel_im_terminalordner(terminal):
    kd, exe, _, _, calls = terminal
    ok, grund = kd.starten()
    assert ok and "Datenpfad geprüft" in grund
    assert calls["start"] == [(([str(exe), "/portable"],), {
        "cwd": str(exe.parent),
        "creationflags": getattr(kursdaten.subprocess, "CREATE_NO_WINDOW", 0)})]
    assert calls["init"] == [((str(exe),), {"portable": True})]
    assert kd._aktiv


def test_vorgefundenes_terminal_mit_falscher_datenablage_startet_einmal_portabel_neu(terminal, monkeypatch):
    kd, exe, _, infos, calls = terminal
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: True)
    infos[:] = [SimpleNamespace(data_path=str(exe.parent.parent / "AppData"), connected=True),
                SimpleNamespace(data_path=str(exe.parent), connected=True)]

    def portabel_starten(*args, **kwargs):
        # Die alte Verbindung und Instanz müssen VOR dem Neustart beendet sein.
        assert calls["shutdown"] == [True]
        assert calls["stop"] == [str(exe)]
        calls["start"].append((args, kwargs))

    monkeypatch.setattr(kursdaten.subprocess, "Popen", portabel_starten)
    ok, grund = kd.starten()
    assert ok and "portabel neu gestartet" in grund
    assert kd._aktiv and kd._selbststart
    assert calls["start"] == [(([str(exe), "/portable"],), {
        "cwd": str(exe.parent),
        "creationflags": getattr(kursdaten.subprocess, "CREATE_NO_WINDOW", 0)})]
    assert calls["init"] == [((str(exe),), {"portable": True})] * 2
    kd.beenden()
    assert calls["stop"] == [str(exe), str(exe)]


def test_vorgefundenes_portables_terminal_braucht_keinen_neustart(terminal, monkeypatch):
    kd, _, _, _, calls = terminal
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: True)
    assert kd.starten()[0]
    assert calls["start"] == [] and calls["stop"] == []
    assert len(calls["init"]) == 1


def test_nonportable_terminal_ohne_startfreigabe_wird_nicht_neugestartet(terminal, monkeypatch):
    kd, exe, _, infos, calls = terminal
    kd.start_erlauben = False
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: True)
    infos[:] = [SimpleNamespace(data_path=str(exe.parent.parent / "AppData"), connected=True)]
    ok, grund = kd.starten()
    assert not ok and "andere Datenablage" in grund
    assert not kd._aktiv and kd._mt5 is None
    assert calls["start"] == []
    assert calls["init"][0][1] == {"portable": True}
    assert calls["stop"] == [str(exe)]
    assert calls["shutdown"] == [True]


@pytest.mark.parametrize("stop_ergebnis", [False, None])
def test_nonportable_neustart_braucht_bestaetigten_erfolgreichen_stop(terminal, monkeypatch, stop_ergebnis):
    kd, exe, _, infos, calls = terminal
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: True)
    infos[:] = [SimpleNamespace(data_path=str(exe.parent.parent / "AppData"), connected=True)]
    monkeypatch.setattr(kursdaten, "terminal_beenden",
                        lambda p: calls["stop"].append(p) or stop_ergebnis)
    ok, grund = kd.starten()
    assert not ok and "kein portabler Neustart" in grund
    assert calls["start"] == [] and len(calls["init"]) == 1
    assert calls["stop"] == [str(exe)]
    assert calls["shutdown"] == [True]
    assert not kd._aktiv and kd._mt5 is None
    assert list(kd._genutzte_terminals.values()) == [str(exe)]


def test_nonportable_datenablage_nach_neustart_bricht_ohne_schleife_ab(terminal, monkeypatch):
    kd, exe, _, infos, calls = terminal
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda _: True)
    infos[:] = [SimpleNamespace(data_path=str(exe.parent.parent / "AppData"), connected=True)]
    ok, grund = kd.starten()
    assert not ok and "andere Datenablage" in grund
    assert len(calls["start"]) == 1 and len(calls["init"]) == 2
    assert calls["stop"] == [str(exe), str(exe)]
    assert calls["shutdown"] == [True, True]
    assert not kd._aktiv and kd._mt5 is None


def test_frisch_gestartetes_terminal_mit_falscher_datenablage_keine_neustartschleife(terminal):
    kd, exe, _, infos, calls = terminal
    infos[:] = [SimpleNamespace(data_path=str(exe.parent.parent / "AppData"), connected=True)]
    ok, grund = kd.starten()
    assert not ok and "andere Datenablage" in grund
    assert len(calls["start"]) == 1 and len(calls["init"]) == 1
    assert calls["stop"] == [str(exe)]


def test_portable_recovery_einer_quelle_laesst_vorherige_quelle_offen(terminal, monkeypatch):
    kd, exe, _, infos, calls = terminal
    assert kd.starten()[0]
    zweite_exe = exe.parent.parent / "ZweiteQuelle" / "terminal64.exe"
    zweite_exe.parent.mkdir()
    zweite_exe.touch()
    kd.terminals.append(str(zweite_exe))
    monkeypatch.setattr(kursdaten, "terminal_laueft", lambda p: p == str(zweite_exe))
    infos[:] = [SimpleNamespace(data_path=str(zweite_exe.parent.parent / "AppData"), connected=True),
                SimpleNamespace(data_path=str(zweite_exe.parent), connected=True)]
    assert kd.wechsle_terminal()[0]
    assert calls["stop"] == [str(zweite_exe)]
    assert [args[0][0] for args, _ in calls["start"]] == [str(exe), str(zweite_exe)]
    kd.beenden()
    assert calls["stop"] == [str(zweite_exe), str(exe), str(zweite_exe)]


def test_terminal_wartet_auf_verbindung_nach_bestaetigtem_datenpfad(terminal):
    kd, exe, _, infos, calls = terminal
    infos[:] = [SimpleNamespace(data_path=str(exe.parent), connected=False),
                SimpleNamespace(data_path=str(exe.parent), connected=True)]
    assert kd.starten()[0]
    assert calls["sleep"] == [1.0]


@pytest.mark.parametrize("data_path", ["", "korrekt"])
def test_terminal_ohne_datenpfad_oder_verbindung_keine_messung(terminal, data_path):
    kd, exe, _, infos, calls = terminal
    infos[:] = [SimpleNamespace(data_path=str(exe.parent) if data_path else "", connected=False)]
    ok, grund = kd.starten()
    assert not ok and "keine Kursmessung" in grund
    assert len(calls["sleep"]) == 15
    assert calls["stop"] == [str(exe)]
    assert not kd._aktiv


def test_terminal_ohne_startfreigabe_startet_nichts(terminal):
    kd, _, _, _, calls = terminal
    kd.start_erlauben = False
    assert not kd.starten()[0]
    assert not calls["start"] and not calls["init"]


def test_terminal_fehlender_pfad_keine_automatische_terminalsuche(terminal):
    kd, exe, _, _, calls = terminal
    exe.unlink()
    ok, grund = kd.starten()
    assert not ok and "Ausweichterminal" in grund
    assert not calls["start"] and not calls["init"]


def test_kontrakthelfer_nutzt_denselben_portable_start(terminal, monkeypatch):
    kd, exe, mt5, _, calls = terminal
    from mqlkiscanner import config
    monkeypatch.setattr(config, "load_settings", lambda: {"markt_start_erlauben": True})
    path = Path(__file__).resolve().parents[1] / "scripts/reference/mt5_kontrakt_specs.py"
    spec = importlib.util.spec_from_file_location("portable_specs_test", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    ok, grund = helper._verbinden(mt5, str(exe))
    assert ok and "Datenpfad geprüft" in grund
    assert calls["start"][0][0][0] == [str(exe), "/portable"]
    assert calls["init"] == [((str(exe),), {"portable": True})]
