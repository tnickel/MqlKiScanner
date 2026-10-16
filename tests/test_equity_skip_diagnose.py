import datetime as dt
from types import SimpleNamespace

from mqlkiscanner.forensics import equity_rekonstruktion as er
from mqlkiscanner.models import ParsedExport


def test_skipped_unusable_instruments_keep_full_structured_diagnosis(monkeypatch):
    opened = dt.datetime(2026, 1, 1)
    symbols = [f"NOSPEC{i}" for i in range(7)] + ["NOPRICE"]
    parsed = ParsedExport("synthetic", "positions", trades=[
        SimpleNamespace(symbol=s, open_time=opened, close_time=opened + dt.timedelta(hours=2),
                        entry_price=100, exit_price=99, volume=1, direction="BUY", net=-1)
        for s in symbols])
    bar = {"time": int(opened.replace(tzinfo=dt.timezone.utc).timestamp()),
           "open": 100, "high": 101, "low": 99, "close": 100}
    provider = SimpleNamespace(hole_h1=lambda symbol, *a, **kw: [] if symbol == "NOPRICE" else [bar])
    monkeypatch.setattr(er, "_resolve_symbol", lambda *a: None)
    report = er.rekonstruiere(parsed, provider, 1000, broker="Original")
    assert report['status'] == 'skipped'
    assert report['verlaesslich'] is False
    assert report['symbole_ohne_kurse'] == ['NOPRICE']
    assert report['symbole_ohne_kontrakt'] == [f'NOSPEC{i}' for i in range(7)]
    assert report['trades_gesamt'] == 8 and report['trades_genutzt'] == 0
    assert 'equity_dd_pct' not in report and 'equity_dd_pct_raw' not in report
