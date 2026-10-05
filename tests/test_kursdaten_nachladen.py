# -*- coding: utf-8 -*-
"""MT5-Historien-Nachladen in kursdaten.hole_h1 (Nutzer-Fall 05.10.2026):
Der ERSTE copy_rates_range-Abruf kann nur die bereits lokale Historie
liefern und den Server-Download anstossen (real: GBPJPY endete mitten im
Fenster, der zweite Abruf brachte alles — trotz Max Bars = Unlimited).
hole_h1 fragt deshalb erneut, solange das Ergebnis waechst und das Fenster
(Toleranz 3 Tage fuer Wochenenden) noch nicht erreicht ist.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from mqlkiscanner import config, kursdaten

START = dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc)


def _bar(epoch_s: int) -> dict:
    return {"time": epoch_s, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}


def _kd_mit_abrufen(monkeypatch, abrufe) -> tuple:
    """KursDaten mit gemocktem MT5: copy_rates_range liefert je Abruf die
    naechste (letzte) Historien-Version; sleep wird neutralisiert."""
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    voll = [_bar(s0 + i * 3600) for i in range(200)]
    teil = voll[:40]
    folgen = [voll if a == "voll" else teil for a in abrufe]
    stand = {"n": 0}

    def crr(symbol, tf, von, bis):
        i = min(stand["n"], len(folgen) - 1)
        stand["n"] += 1
        return folgen[i]

    mt5 = SimpleNamespace(symbol_select=lambda s, f: True,
                          copy_rates_range=crr, TIMEFRAME_H1=1)
    kd = kursdaten.KursDaten(config.load_settings())
    kd._aktiv = True
    kd._mt5 = mt5
    return kd, s0, stand


def test_erst_teilhistorie_dann_voll(monkeypatch):
    kd, s0, stand = _kd_mit_abrufen(monkeypatch, ["teil", "voll"])
    bars = kd.hole_h1("XAUUSD", s0, s0 + 200 * 3600)
    assert len(bars) == 200, len(bars)
    assert stand["n"] == 2  # Teil -> Nachladen -> voll


def test_ohne_fortschritt_keine_endlosschleife(monkeypatch):
    kd, s0, stand = _kd_mit_abrufen(monkeypatch, ["teil", "teil", "teil"])
    bars = kd.hole_h1("EURUSD", s0, s0 + 200 * 3600)
    assert len(bars) == 40  # Best-Effort: Teilergebnis statt Endlosnachladen
    assert stand["n"] <= 3


def test_vollstaendiges_ergebnis_ohne_zweitabruf(monkeypatch):
    kd, s0, stand = _kd_mit_abrufen(monkeypatch, ["voll"])
    bars = kd.hole_h1("GBPJPY", s0, s0 + 200 * 3600)
    assert len(bars) == 200
    assert stand["n"] == 1  # fertig beim ersten Mal -> kein Retry
