"""Exact metadata capture must not bypass the shared lock or use cash aliases."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import config
from mqlkiscanner.agenten.lock import LockBesetzt

MODULE = Path(__file__).resolve().parents[1] / "scripts/reference/ft_kontrakt_beleg.py"
spec = importlib.util.spec_from_file_location("ft_kontrakt_beleg", MODULE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def information(symbol):
    return SimpleNamespace(name=symbol, description="Exact Future", trade_contract_size=1.0,
        currency_profit="EUR" if symbol == "GER40ft" else "GBP", currency_margin="EUR",
        trade_calc_mode=3, trade_tick_size=.01, trade_tick_value=.01,
        trade_tick_value_profit=.01, trade_tick_value_loss=.01,
        volume_min=.1, volume_max=500., volume_step=.1, digits=2)


def fixtures(tmp_path, *, mismatch=False, servers=None):
    path = tmp_path / "Vantage" / "terminal64.exe"
    events = []
    servers = iter(servers or ["VantageMarkets-Live 10", "VantageMarkets-Live 10"])

    class Account:
        def __init__(self, server): self.server = server
        def __getattr__(self, name): raise AssertionError("Only account.server may be read")

    class SDK:
        def terminal_info(self):
            return SimpleNamespace(path=str(path.parent), data_path=str(path.parent),
                                   company="Vantage", connected=True)
        def account_info(self):
            events.append("account.server")
            return Account(next(servers))
        def symbol_info(self, name):
            events.append(name)
            return information("GER40" if mismatch else name)

    class Provider:
        def __init__(self, settings):
            events.append("provider")
            assert settings["kursdaten_terminals"] == [str(path)]
            self._mt5 = SDK()
        def starten(self): events.append("connect"); return True, "portable fake"
        def beenden(self): events.append("cleanup")

    @contextmanager
    def lock(basis):
        assert basis == config.DATA_DIR
        events.append("lock")
        try: yield
        finally: events.append("unlock")

    def running(_): events.append("process"); return False
    return {"kursdaten_terminals": [str(path)], "markt_start_erlauben": True}, Provider, lock, running, events


def test_locked_exact_capture_reads_only_server_and_cleans_before_unlock(tmp_path):
    settings, provider, lock, running, events = fixtures(tmp_path)
    result = helper.capture(settings, provider_factory=provider, lock_factory=lock, process_running=running)
    assert result["ok"] is True
    assert result["symbols"]["GER40ft"]["currency_profit"] == "EUR"
    assert result["symbols"]["UK100ft"]["currency_profit"] == "GBP"
    assert events == ["lock", "process", "provider", "connect", "account.server",
                      "GER40ft", "UK100ft", "account.server", "cleanup", "process", "unlock"]
    assert result["terminal"]["broker_server"] == "VantageMarkets-Live 10"
    assert result["aliases_used"] is False
    assert result["terminal_running_after_cleanup"] is False


def test_busy_lock_touches_no_terminal_or_sdk(tmp_path):
    settings, _, _, _, events = fixtures(tmp_path)
    @contextmanager
    def occupied(_):
        raise LockBesetzt("busy")
        yield
    def forbidden(*args): raise AssertionError("No terminal access before lock")
    result = helper.capture(settings, provider_factory=forbidden, lock_factory=occupied, process_running=forbidden)
    assert result["error"] == "shared_scan_lock_busy_no_terminal_access"
    assert events == []


def test_cash_alias_or_different_case_is_rejected_and_cleanup_runs(tmp_path):
    settings, provider, lock, running, events = fixtures(tmp_path, mismatch=True)
    result = helper.capture(settings, provider_factory=provider, lock_factory=lock, process_running=running)
    assert result["ok"] is False
    assert result["error"] == "exact_symbol_missing_or_different"
    assert events[-3:] == ["cleanup", "process", "unlock"]
    assert "UK100ft" not in events  # fail closed at the first mismatched symbol


def test_server_change_during_read_cannot_certify_spec(tmp_path):
    settings, provider, lock, running, _ = fixtures(tmp_path, servers=["Vantage-A", "Vantage-B"])
    result = helper.capture(settings, provider_factory=provider, lock_factory=lock, process_running=running)
    assert result["ok"] is False
    assert result["error"] == "broker_server_changed_during_capture"


@pytest.mark.parametrize("field,value", [("trade_contract_size", 0), ("trade_tick_size", float("nan")),
                                         ("volume_step", -1), ("currency_profit", "")])
def test_invalid_required_metadata_is_not_evidence(field, value):
    info = information("GER40ft")
    setattr(info, field, value)
    with pytest.raises(ValueError):
        helper.exact_spec(SimpleNamespace(symbol_info=lambda _: info), "GER40ft")
