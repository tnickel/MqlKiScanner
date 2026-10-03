# -*- coding: utf-8 -*-
"""Kapitalfluesse neutralisieren; niemals zukuenftige H1-Schluesse nutzen."""
import datetime as dt

import pytest

from mqlkiscanner.forensics import equity_kapitalfluesse as ek
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


START = dt.datetime(2026, 1, 5)
EPOCH = int(START.replace(tzinfo=dt.timezone.utc).timestamp())


def _trade(a=0, b=3, profit=0, symbol="XAUUSD", entry=2000):
    return Trade(START + dt.timedelta(hours=a), START + dt.timedelta(hours=b),
                 "Buy", 1.0, symbol, entry, entry, profit)


def _p(h, equity, floating=0):
    return {"t": EPOCH + int(h * 3600), "equity": equity,
            "realisiert": equity - floating if equity is not None else 1000,
            "floating": floating, "messpunkt": equity is not None}


def _flow(h, amount):
    return BalanceRow(START + dt.timedelta(hours=h), amount)


def _bar(h, close):
    return {"time": EPOCH + int(h * 3600), "open": close,
            "high": close, "low": close, "close": close}


def _run(trades, flows, points, bars=None, offsets=None):
    parsed = ParsedExport("", "positions", trades=trades, balances=flows)
    return ek.diagnostik(parsed, points, bars or {}, offsets or {}, 1000)


def test_ohne_kapitalfluesse_gleicher_equity_dd():
    r = _run([_trade(profit=1000)], [],
             [_p(0, 1000), _p(1, 600, -400), _p(2, 2000, 1000), _p(3, 2000)])
    assert r["kennzahlen"]["konto_equity_dd_pct"] == 40
    assert [p["return_index"] for p in r["punkte"]] == [1, .6, 2, 2]
    assert r["kennzahlen"]["verlaesslich"] is True


def test_auszahlung_allein_ist_kein_handelsdrawdown():
    r = _run([_trade(b=1)], [_flow(2, -500)], [_p(0, 1000), _p(1, 1000)])
    assert r["kennzahlen"]["konto_equity_dd_pct"] == 0
    assert r["punkte"][-1]["actual_equity"] == 500
    assert r["punkte"][-1]["account_balance"] == 500
    assert r["punkte"][-1]["return_index"] == 1
    assert r["kennzahlen"]["verlaesslich"] is True


def test_gleicher_verlust_nach_entnahme_prozentual_groesser():
    # Erst -500 Kapital, dann -100 Trading: 500 ->400 =20%, virtuelle
    # Kurve 1000 ->900 haette lediglich 10%.
    r = _run([_trade(b=.5), _trade(a=2, b=3, profit=-100)],
             [_flow(1, -500)], [_p(0, 1000), _p(1, 1000), _p(3, 900)])
    assert r["kennzahlen"]["konto_equity_dd_pct"] == 20
    assert r["punkte"][-1]["actual_equity"] == 400


def test_flow_offener_trade_nur_letzten_abgeschlossenen_bar_close():
    r = _run([_trade(b=3)], [_flow(1.5, -500)],
             [_p(0, 1000), _p(1, 900, -100), _p(2, 1000), _p(3, 1000)],
             {"XAUUSD": [_bar(0, 1999), _bar(1, 2100)]}, {"XAUUSD": 0})
    flow = r["flow_befunde"][0]
    assert flow["equity_vor_flow"] == 900
    assert flow["kursbasis"][0]["bar_ende"] == EPOCH + 3600
    assert flow["kursbasis"][0]["kurs"] == 1999
    assert r["kennzahlen"]["flow_preis_annahmen"] == 1
    assert r["kennzahlen"]["verlaesslich"] is False
    assert r["kennzahlen"]["konto_equity_dd_pct"] is not None


def test_fehlende_flow_kursbasis_stoppt_index_dauerhaft():
    # Nur eine laufende/zukuenftige Bar: ihr Schluss darf die Unbekannte
    # vor dem Flow um01:30 nicht rueckwirkend aufloesen.
    r = _run([_trade(b=3)], [_flow(1.5, -500)],
             [_p(0, 1000), _p(1, 1000), _p(2, 1000), _p(3, 1000)],
             {"XAUUSD": [_bar(1, 2000)]}, {"XAUUSD": 0})
    assert r["kennzahlen"]["konto_equity_dd_pct"] is None
    assert r["kennzahlen"]["konto_equity_dd_beobachtet_pct"] == 0
    assert r["kennzahlen"]["verlaesslich"] is False
    assert r["punkte"][1]["return_index"] == 1
    assert all(p["return_index"] is None for p in r["punkte"][2:])
    assert r["punkte"][-1]["actual_equity"] == 500


def test_beobachteter_dd_bis_abbruch_bleibt_ohne_index_neustart():
    r = _run([_trade(b=3)], [_flow(1.5, -100)],
             [_p(0, 1000), _p(1, 800, -200), _p(2, 500, -500), _p(3, 1000)],
             {"XAUUSD": [_bar(1, 2000)]}, {"XAUUSD": 0})
    k = r["kennzahlen"]
    assert k["konto_equity_dd_pct"] is None
    assert k["konto_equity_dd_beobachtet_pct"] == 20
    assert k["index_gueltig_bis"] == EPOCH + 3600
    assert k["index_abbruch_am"] == EPOCH + 5400
    assert k["index_messpunkte"] == 2
    assert all(p["rendite_index"] is None for p in r["punkte"][2:])


def test_close_exakt_zum_flow_ist_vorher_realisiert():
    r = _run([_trade(b=1, profit=100)], [_flow(1, -550)],
             [_p(0, 1000), _p(1, 1100)])
    assert r["flow_befunde"][0]["equity_vor_flow"] == 1100
    assert r["flow_befunde"][0]["offene_positionen"] == 0
    assert r["punkte"][-1]["actual_equity"] == 550
    assert r["punkte"][-1]["return_index"] == pytest.approx(1.1)
    assert r["kennzahlen"]["verlaesslich"] is True


def test_messluecke_verhindert_gesamt_dd():
    r = _run([_trade(b=3)], [], [_p(0, 1000), _p(1, None, None), _p(3, 1000)])
    assert r["kennzahlen"]["konto_equity_dd_pct"] is None
    assert r["kennzahlen"]["messluecke"] is True
    assert r["kennzahlen"]["konto_equity_dd_beobachtet_pct"] == 0
    assert r["punkte"][1]["return_index"] is None


@pytest.mark.parametrize("symbol,reason", [("EXOTIC", "Kontrakt"), ("NZDCAD", "FX-Kurs")])
def test_unbelegte_kontrakt_oder_fx_basis_kein_index(monkeypatch, symbol, reason):
    monkeypatch.setattr(ek.fx_rates, "usd_per", lambda *_args: None)
    r = _run([_trade(symbol=symbol)], [_flow(1.5, -100)],
             [_p(0, 1000), _p(1, 1000), _p(2, 1000), _p(3, 1000)],
             {symbol: [_bar(0, 2000)]}, {symbol: 0})
    assert r["kennzahlen"]["konto_equity_dd_pct"] is None
    assert any(reason in grund for grund in r["probleme"])


def test_luecke_in_letzter_abgeschlossener_stunde_kein_stiller_altkurs():
    r = _run([_trade(b=4)], [_flow(2.5, -100)],
             [_p(0, 1000), _p(1, 1000), _p(3, 1000), _p(4, 1000)],
             {"XAUUSD": [_bar(0, 2000), _bar(2, 2000)]}, {"XAUUSD": 0})
    assert r["kennzahlen"]["konto_equity_dd_pct"] is None
    assert any("Luecke" in grund for grund in r["probleme"])


def test_uneinheitliche_symbolzeiten_kein_scheinbarer_konto_vergleich():
    # Die Studie verschiebt symbolweise, aber die Kapitalflüsse haben
    # eine gemeinsame CSV-Zeit. Unterschiedliche Offsets verbieten dann
    # einen scheinbar belegten Konto-Index aus diesen Studienpunkten.
    r = _run([_trade(symbol="XAUUSD"), _trade(symbol="US30")],
             [_flow(1.5, -100)], [_p(0, 1000), _p(1, 900), _p(3, 1000)],
             offsets={"XAUUSD": 0, "US30": 3600})
    assert r["punkte"] == []
    assert r["kennzahlen"]["konto_equity_dd_pct"] is None
    assert r["kennzahlen"]["verlaesslich"] is False
    assert "gemeinsame Zeitbasis" in r["grund"]
