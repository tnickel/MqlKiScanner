# -*- coding: utf-8 -*-
"""Fail-Fast und Login-Pfad: systemische MQL5-Fehler stoppen die Pipeline."""
from __future__ import annotations

import pytest

from mqlkiscanner.mql5.ratelimit import Mql5HardStopError, Mql5ThrottleError, is_hard_mql5_failure
from mqlkiscanner.mql5.session import Mql5Session
from mqlkiscanner.pipeline import ScanPipeline


def test_is_hard_mql5_failure_detects_throttle_and_login_html():
    assert is_hard_mql5_failure(Mql5ThrottleError("drosselt weiter"))
    assert is_hard_mql5_failure(RuntimeError("Export lieferte kein CSV — auth_login"))
    assert is_hard_mql5_failure("HTTP 403 Forbidden")
    assert not is_hard_mql5_failure(ValueError("kaputtes CSV-Format"))


def test_fail_fast_stops_after_consecutive_hard_failures():
    pipe = ScanPipeline({"mql5_fail_fast_after": 2})
    pipe._register_mql5_outcome(ok=False, exc=Mql5ThrottleError("drosselt weiter 1"))
    with pytest.raises(Mql5HardStopError) as caught:
        pipe._register_mql5_outcome(ok=False, exc=Mql5ThrottleError("drosselt weiter 2"))
    assert "Fail-Fast" in str(caught.value)
    assert pipe._mql5_hard_fails == 2


def test_soft_failure_does_not_trigger_fail_fast():
    pipe = ScanPipeline({"mql5_fail_fast_after": 2})
    pipe._register_mql5_outcome(ok=False, exc=ValueError("parse"))
    pipe._register_mql5_outcome(ok=False, exc=ValueError("parse again"))
    assert pipe._mql5_hard_fails == 0


def test_success_resets_hard_fail_counter():
    pipe = ScanPipeline({"mql5_fail_fast_after": 3})
    pipe._register_mql5_outcome(ok=False, exc=Mql5ThrottleError("drosselt weiter"))
    assert pipe._mql5_hard_fails == 1
    pipe._register_mql5_outcome(ok=True)
    assert pipe._mql5_hard_fails == 0


def test_http_form_login_removed_from_session():
    assert not hasattr(Mql5Session, "login")


def test_ensure_session_uses_browser_not_http_login(monkeypatch):
    from mqlkiscanner.mql5 import session as sess_mod

    calls = []

    def fake_ensure(settings, session, force_browser_login=False, log=None):
        calls.append("browser")
        session.logged_in = True
        return True

    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.ensure_mql5_cookies", fake_ensure)
    monkeypatch.setattr(sess_mod.secrets_store, "get_secret",
                        lambda k: "user" if "user" in k else "pass")

    s = Mql5Session({})
    s.logged_in = False
    monkeypatch.setattr(s, "is_logged_in", lambda: False)
    s.ensure_session_for_export()
    assert calls == ["browser"]
    assert s.logged_in is True


def test_export_kinds_mt4_prefers_history():
    from mqlkiscanner.mql5.session import export_kinds_for_platform
    assert export_kinds_for_platform("MT4")[0] == "history"
    assert export_kinds_for_platform("MT5")[0] == "positions"


def test_mt4_export_uses_history_not_positions(monkeypatch):
    """MT4: /export/positions → 404; /export/history → CSV Orderbuch."""
    from mqlkiscanner.mql5 import session as sess_mod

    s = Mql5Session({})
    s.logged_in = True
    monkeypatch.setattr(s, "ensure_session_for_export", lambda: None)

    calls: list[str] = []

    class FakeResp:
        def __init__(self, status, text):
            self.status_code = status
            self.text = text

    def fake_get(path, extra_pause_s=0.0, allow_http_statuses=()):
        calls.append(path)
        if path.endswith("/positions"):
            return FakeResp(404, "[NotFound]")
        if path.endswith("/history"):
            return FakeResp(
                200,
                "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
                "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n")
        return FakeResp(500, "nope")

    monkeypatch.setattr(s, "get", fake_get)
    text = s.export_positions_csv(2349227, platform="MT4")
    assert text.lstrip().startswith("Time;")
    assert any(p.endswith("/history") for p in calls)
    assert calls[0].endswith("/history")
