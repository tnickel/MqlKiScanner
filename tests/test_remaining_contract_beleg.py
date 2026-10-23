"""Remaining contract capture uses exact case-normalized names and shared lock."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner.agenten.lock import LockBesetzt

MODULE = Path(__file__).resolve().parents[1] / "scripts/reference/remaining_contract_beleg.py"
spec = importlib.util.spec_from_file_location("remaining_contract_beleg", MODULE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def test_exact_case_lookup_and_cleanup_are_inside_shared_lock(tmp_path, monkeypatch):
    path = tmp_path / "Vantage" / "terminal64.exe"
    events = []
    class Account:
        server = "VantageMarkets-Live 10"
        def __getattr__(self, field):
            raise AssertionError("Only server may be read")
    class SDK:
        def terminal_info(self):
            return SimpleNamespace(path=str(path.parent), data_path=str(path.parent), company="Vantage", connected=True)
        def account_info(self):
            return Account()
        def symbols_get(self):
            return [SimpleNamespace(name=s) for s in ("Nikkei225", "JPN225ft", "Soybean-C")]
    class Provider:
        _mt5 = SDK()
        def __init__(self, _): events.append("provider")
        def starten(self): events.append("connect"); return True, "portable fake"
        def beenden(self): events.append("cleanup")
    @contextmanager
    def lock(_):
        events.append("lock")
        yield
        events.append("unlock")
    def exact(sdk, name):
        events.append(name)
        return {"name": name}
    monkeypatch.setattr(helper, "exact_spec", exact)
    result = helper.capture({"kursdaten_terminals": [str(path)]}, provider_factory=Provider,
                            lock_factory=lock, process_running=lambda _: False)
    assert result["ok"] is True
    assert result["symbols"]["NIKKEI225"]["name"] == "Nikkei225"
    assert result["symbols"]["SOYBEAN-C"]["name"] == "Soybean-C"
    assert events == ["lock", "provider", "connect", "Nikkei225", "Soybean-C", "cleanup", "unlock"]


def test_busy_lock_makes_no_terminal_or_process_call(tmp_path):
    @contextmanager
    def busy(_):
        raise LockBesetzt("busy")
        yield
    def forbidden(*args):
        raise AssertionError("No terminal access")
    result = helper.capture({"kursdaten_terminals": [str(tmp_path / "Vantage" / "terminal64.exe")]},
        lock_factory=busy, provider_factory=forbidden, process_running=forbidden)
    assert result["error"] == "shared_scan_lock_busy_no_terminal_access"
