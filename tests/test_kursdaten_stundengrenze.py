"""Vorläufige H1-Bars brauchen einen Abruf nach Stundenende als Abschlussbeleg."""
from __future__ import annotations

from contextlib import closing
import sqlite3
from types import SimpleNamespace

import pytest

from mqlkiscanner import config, kursdaten


START = 1_735_776_000


def _bar(close=1.1):
    return {"time": START, "open": 1., "high": 2., "low": .5, "close": close}


@pytest.fixture
def anbieter(monkeypatch):
    stand = SimpleNamespace(now=START + 1800, abrufe=[], antworten=[[_bar()]])

    def laden(symbol, timeframe, von, bis):
        stand.abrufe.append((int(von.timestamp()), int(bis.timestamp())))
        antwort = stand.antworten.pop(0) if stand.antworten else []
        return antwort() if callable(antwort) else antwort

    mt5 = SimpleNamespace(
        account_info=lambda: SimpleNamespace(server="Broker-A"),
        symbol_select=lambda *_: True, TIMEFRAME_H1=1,
        copy_rates_range=laden, shutdown=lambda: None)
    stand.kd = kursdaten.KursDaten({"markt_terminal_pfad": "fake-stundengrenze"})
    stand.kd._aktiv = True
    stand.kd._mt5 = mt5
    monkeypatch.setattr(kursdaten.time, "time", lambda: stand.now)
    monkeypatch.setattr(kursdaten.time, "sleep", lambda _: None)
    return stand


@pytest.mark.parametrize("offline", [True, False])
def test_alte_vorlaeufige_bar_wird_ohne_abschlussbestaetigung_nicht_zur_historie(anbieter, offline):
    s = anbieter
    assert s.kd.hole_h1("EURUSD", START, START)[0]["close"] == 1.1
    s.now = START + 86400
    if offline:
        s.kd._trennen()
    # Bei aktiver Verbindung sind alle weiteren Antworten leer. Auch das
    # rechtfertigt keinen Rückfall auf die alte vorläufige OHLC-Messung.
    assert s.kd.hole_h1("EURUSD", START, START) is None
    assert len(s.abrufe) == (1 if offline else 5)


def test_ueber_stundenende_laufender_abruf_ist_keine_finale_bestaetigung(anbieter):
    s = anbieter
    s.now = START + 3599
    begonnen = s.now

    def antwort_von_vor_stundenende():
        # Die SDK-/Verarbeitungszeit überschreitet die Stundengrenze. Der
        # Datensatz wurde dabei noch während der offenen Stunde gemessen.
        s.now = START + 3601
        return [_bar()]

    s.antworten = [antwort_von_vor_stundenende]
    assert s.kd.hole_h1("EURUSD", START, START) is None
    with closing(sqlite3.connect(config.DATA_DIR / "kursdaten.db")) as conn:
        gespeichert = conn.execute(
            "SELECT geladen_am, abgeschlossen FROM h1_bars").fetchall()
    assert gespeichert == [(begonnen, 0)]


def test_ramcache_verfaellt_an_stundengrenze_auch_innerhalb_von_60_sekunden(anbieter):
    s = anbieter
    s.now = START + 3590
    assert s.kd.hole_h1("EURUSD", START, START)[0]["close"] == 1.1
    s.now = START + 3601  # Nur elf Sekunden später, aber die Stunde ist beendet.
    s.antworten = [[_bar(close=1.5)]]
    bestaetigt = s.kd.hole_h1("EURUSD", START, START)
    assert bestaetigt[0]["close"] == 1.5
    assert len(s.abrufe) == 2
