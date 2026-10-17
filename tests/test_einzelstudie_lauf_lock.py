"""Einzelstudie, Admin-Test und Scan duerfen kein gemeinsames MT5 stoeren."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import config, equity_studie_ui, kursdaten, pipeline
from mqlkiscanner.agenten import lock, marktdata


@pytest.fixture
def study_setup(tmp_path, monkeypatch):
    csv = tmp_path / "synthetic.csv"
    csv.write_text("synthetic", encoding="utf-8")
    result = pipeline.ScanResult(id=123, quelle="mql5", account_currency="USD",
                                  kapitalbasis_usd=1000, trades_path=str(csv))
    monkeypatch.setattr(equity_studie_ui.parser, "load_export",
                        lambda *a, **kw: SimpleNamespace(trades=[], costs=[]))
    monkeypatch.setattr(equity_studie_ui.drawdown, "run",
                        lambda *a, **kw: {"startkapital": 1000})
    provider = Mock()

    def assert_held():
        with pytest.raises(lock.LockBesetzt):
            with lock.lauf_lock(config.DATA_DIR):
                pytest.fail("Lauf-Sperre wurde zu frueh freigegeben")

    def start():
        assert_held()
        return True, "synthetic"

    provider.starten.side_effect = start
    provider.beenden.side_effect = assert_held
    factory = Mock(return_value=provider)
    monkeypatch.setattr(kursdaten, "KursDaten", factory)

    def calculate(*args, **kwargs):
        assert_held()
        return {"status": "ok"}

    calculation = Mock(side_effect=calculate)
    monkeypatch.setattr(equity_studie_ui, "studie", calculation)
    return result, provider, factory, calculation, assert_held


def test_busy_run_blocks_study_before_parser_or_terminal(study_setup):
    result, provider, factory, calculation, _ = study_setup
    with lock.lauf_lock(config.DATA_DIR):
        with pytest.raises(RuntimeError, match="bereits aktiv"):
            equity_studie_ui.berechne(result, lambda *_: None)
        assert not lock.lock_status(config.DATA_DIR)["frei"]
    factory.assert_not_called()
    provider.beenden.assert_not_called()
    calculation.assert_not_called()
    assert lock.lock_status(config.DATA_DIR)["frei"]


def test_study_holds_lock_through_start_measurement_and_cleanup(study_setup):
    result, provider, _, calculation, _ = study_setup
    assert equity_studie_ui.berechne(result, lambda *_: None)["status"] == "ok"
    provider.starten.assert_called_once()
    calculation.assert_called_once()
    provider.beenden.assert_called_once()
    assert lock.lock_status(config.DATA_DIR)["frei"]


def test_admin_test_cannot_touch_terminal_during_single_study(study_setup, monkeypatch):
    result, provider, factory, calculation, assert_held = study_setup
    terminal_probe = Mock(side_effect=AssertionError("Admin must not inspect an active study terminal"))
    monkeypatch.setattr(marktdata, "terminal_laueft", terminal_probe)

    def calculate(*args, **kwargs):
        assert_held()
        admin = marktdata.verbindung_testen({"markt_start_erlauben": True})
        assert admin["ok"] is False
        assert "aktiv" in admin["grund"] or "Lauf" in admin["grund"]
        return {"status": "ok"}

    calculation.side_effect = calculate
    equity_studie_ui.berechne(result, lambda *_: None)
    terminal_probe.assert_not_called()
    factory.assert_called_once()
    provider.beenden.assert_called_once()
    assert lock.lock_status(config.DATA_DIR)["frei"]


@pytest.mark.parametrize("phase", ["start", "measurement", "cleanup"])
def test_failure_releases_lock_after_cleanup(study_setup, phase):
    result, provider, _, calculation, assert_held = study_setup

    def fail(*args, **kwargs):
        assert_held()
        raise TimeoutError("synthetic timeout")

    if phase == "start":
        provider.starten.side_effect = fail
    elif phase == "measurement":
        calculation.side_effect = fail
    else:
        provider.beenden.side_effect = fail
    with pytest.raises(TimeoutError, match="synthetic timeout"):
        equity_studie_ui.berechne(result, lambda *_: None)
    provider.beenden.assert_called_once()
    assert lock.lock_status(config.DATA_DIR)["frei"]


def test_failed_connection_cleans_up_before_releasing_lock(study_setup):
    result, provider, _, calculation, assert_held = study_setup

    def refused():
        assert_held()
        return False, "synthetic connection failure"

    provider.starten.side_effect = refused
    with pytest.raises(RuntimeError, match="synthetic connection failure"):
        equity_studie_ui.berechne(result, lambda *_: None)
    provider.beenden.assert_called_once()
    calculation.assert_not_called()
    assert lock.lock_status(config.DATA_DIR)["frei"]


def test_failure_before_terminal_start_does_not_leave_lock_held(study_setup):
    result, provider, factory, _, _ = study_setup
    result.trades_path = ""
    with pytest.raises(RuntimeError, match="Trade-Datei fehlt"):
        equity_studie_ui.berechne(result, lambda *_: None)
    factory.assert_not_called()
    provider.beenden.assert_not_called()
    assert lock.lock_status(config.DATA_DIR)["frei"]
