# -*- coding: utf-8 -*-
"""Zeit-/Positionsbasis der H1-Nachmessung (KiraCat-Pruefung 03.10.)."""
from datetime import datetime, timedelta, timezone

import pytest

from mqlkiscanner import kursdaten
from mqlkiscanner.forensics import equity_rekonstruktion as er
from mqlkiscanner.models import ParsedExport, Trade


START = datetime(2026, 1, 5)


def _trade(symbol="XAUUSD", *, minute_open=1, minute_close=179,
           entry=2000.0, exit_=2000.0, profit=0.0, volume=1.0):
    return Trade(START + timedelta(minutes=minute_open),
                 START + timedelta(minutes=minute_close), "Buy", volume,
                 symbol, entry, exit_, profit)


def _bars(closes, low=None):
    return [{"time": int((START + timedelta(hours=h)).replace(
        tzinfo=timezone.utc).timestamp()), "open": close, "high": close + 1,
        "low": close - 1 if low is None else low, "close": close}
        for h, close in enumerate(closes)]


@pytest.fixture(autouse=True)
def _gmt(monkeypatch):
    # Tests isolate accounting; Auto-GMT has independent regression tests.
    monkeypatch.setattr(er, "ermittle_gmt_offset", lambda *_args, **_kwargs:
                        {"offset_s": 0, "trefferquote": 1.0, "proben": 10})


def test_alle_gleichzeitig_offenen_positionen_werden_summiert():
    trades = [_trade(entry=preis) for preis in (2000, 1995, 1990)]
    parsed = ParsedExport("", "positions", trades=trades)
    result = er.rekonstruiere(parsed,
        kursdaten.FakeKursDaten({"XAUUSD": _bars([1990, 2000, 2000])}),
        startkapital=10000)
    # Erster H1-Schluss: -1000 -500 +0 = -1500; Start-Anker 10000.
    assert result["equity_dd_pct"] == 15.0
    assert result["equity_dd_usd"] == 1500.0


def test_realisiert_enthält_auch_positionen_ohne_kurse():
    trades = [_trade(minute_close=370, profit=100) for _ in range(4)]
    trades.append(_trade("US100", minute_close=370, profit=-500))
    parsed = ParsedExport("", "positions", trades=trades)
    result = er.rekonstruiere(parsed,
        kursdaten.FakeKursDaten({"XAUUSD": _bars([2000] * 9)}),
        startkapital=1000)
    assert result["end_equity_usd"] == 900.0
    assert result["equity_dd_usd"] == 100.0
    assert result["verlaesslich"] is False
    assert result["status"] == "unvollstaendig"
    assert result["trades_total"] == 5
    assert result["trades_mit_kurs_und_kontrakt"] == 4


def test_bar_close_wird_erst_am_bar_ende_verwendet():
    # 01:00-Bar endet 02:00, NACH dem Trade-Schluss um 01:20. Ihr
    # hoher Close darf deshalb keinen Floating-Peak dieses Trades erzeugen.
    t = _trade(minute_open=60, minute_close=80, profit=0)
    result = er.rekonstruiere(ParsedExport("", "positions", trades=[t]),
        kursdaten.FakeKursDaten({"XAUUSD": _bars([2000, 2100, 2000])}),
        startkapital=1000)
    assert result["equity_dd_usd"] == 0.0
    assert result["trades_ohne_h1_floating_messpunkt"] == 1


def test_intrabar_tief_ist_kein_belegter_h1_maximaldrawdown():
    t = _trade(minute_open=5, minute_close=55, profit=100, exit_=2001)
    result = er.rekonstruiere(ParsedExport("", "positions", trades=[t]),
        kursdaten.FakeKursDaten({"XAUUSD": _bars([2001, 2001], low=1965)}),
        startkapital=10000)
    # Die H1-Nachmessung sieht trotz Low -3500 nur das realisierte +100.
    # Der Zeitpunkt des Low ist aus OHLC fuer diesen Teilstunden-Trade
    # nicht bekannt; es darf weder ignorierend als exakter DD ausgegeben
    # noch still als bewiesener 35%-Verlust verbucht werden.
    assert result["equity_dd_pct"] == 0.0
    assert result["trades_ohne_h1_floating_messpunkt"] == 1
    assert "keine Intrabar-Extrema" in result["raster"]
    assert "aktuell offene fehlen" in result["positionsbasis"]
    assert "spaetere Ein-/Auszahlungen nicht eingerechnet" in result["kapitalfluesse"]
