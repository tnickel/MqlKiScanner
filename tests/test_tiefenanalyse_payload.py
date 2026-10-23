# -*- coding: utf-8 -*-
"""Erweiterte Trade-Payload + neue Tiefenanalyse-Vorlage (Nutzer-Prompt
20.10., angepasst): Korb-Rekonstruktion, Verlustkorb-Befund, Zeitverteilung,
vollständige Liste bei kleinen Exporten."""
from __future__ import annotations

from datetime import datetime, timedelta

from mqlkiscanner.models import ParsedExport, Trade
from mqlkiscanner.trade_data import (
    _rekonstruiere_koerbe,
    _verlustkorb_befund,
    build_trade_payload,
)


def _t(minuten, dauer_h, symbol="EURUSD", direction="Buy", profit=-10.0):
    basis = datetime(2026, 1, 5, 10, 0)
    o = basis + timedelta(minutes=minuten)
    return Trade(open_time=o, close_time=o + timedelta(hours=dauer_h),
                 direction=direction, volume=0.1, symbol=symbol,
                 entry_price=1.1, exit_price=1.09, profit=profit)


def _parsed(trades):
    return ParsedExport(source_path="synthetik.csv",
                        source_format="positions", trades=trades)


def test_korb_rekonstruktion_trennt_overlap_und_symbol():
    koerbe = _rekonstruiere_koerbe([
        _t(0, 2), _t(30, 2, profit=-5), _t(60, 2, profit=-15),  # Korb A
        _t(480, 3, profit=25.0, direction="Sell"),              # Korb B
        _t(0, 2, symbol="XAUUSD", profit=3.0),                  # Korb C (anderes Symbol)
    ])
    assert len(koerbe) == 3
    korb_a = next(k for k in koerbe if len(k["trades"]) == 3)
    assert korb_a["ende"].hour == 13  # Union der Haltezeiten


def test_verlustkorb_befund_summary_und_tabelle():
    befund = _verlustkorb_befund(_rekonstruiere_koerbe([
        _t(0, 2, profit=-30.0), _t(480, 2, profit=25.0),
        _t(2000, 2, profit=-12.5), _t(3000, 2, profit=-7.5)]))
    s = befund["zusammenfassung"]
    assert s["koerbe_gesamt"] == 4 and s["koerbe_verlierend"] == 3
    assert s["verlust_max_usd"] == -30.0
    assert s["verlust_median_usd"] == -12.5
    assert [e["netto"] for e in befund["tabelle_schlimmste_30"]] == [-30.0, -12.5, -7.5]


def test_payload_zeitverteilung_und_verlustkoerbe():
    payload = build_trade_payload(_parsed([_t(0, 2, profit=-5.0),
                                           _t(480, 1, profit=8.0)]))
    zv = payload["zeitverteilung"]
    assert zv["long"] == 2 and zv["short"] == 0
    assert sum(zv["wochentage_mo_bis_so"]) == 2
    assert payload["verlustkoerbe"]["zusammenfassung"]["koerbe_verlierend"] == 1


def test_payload_volle_liste_nur_bei_kleinen_exports():
    klein = [_t(i * 10, 1, profit=1.0) for i in range(100)]
    payload_klein = build_trade_payload(_parsed(klein),
                                        volle_liste_max_trades=250)
    assert payload_klein["volle_tradeliste"] is not None
    assert len(payload_klein["volle_tradeliste"]) == 100
    assert "2026-01-05 10:00 B 0.1 EURUSD" in payload_klein["volle_tradeliste"][0]
    # Grenze überschritten → None (Aggregate decken ab); Default bleibt aus
    gross = [_t(i * 10, 1, profit=1.0) for i in range(251)]
    payload_gross = build_trade_payload(_parsed(gross),
                                        volle_liste_max_trades=250)
    assert payload_gross["volle_tradeliste"] is None
    payload_default = build_trade_payload(_parsed(klein))
    assert payload_default["volle_tradeliste"] is None


def test_neue_vorlage_traegt_alle_abschnitte_und_regeln():
    from mqlkiscanner.llm import prompts
    text = prompts.load_prompt("tiefenanalyse")
    flach = " ".join(text.split())
    for anker in ("Korb-Verlustforensik", "35-%-Abschaltung",
                  "53,85", "Abo-Eignung", "11 minus B",
                  "{regeln_sl}", "{regeln_fremdtext}",
                  "KEIN Browsing", "Ampel, Score und Urteil des")[:9]:
        assert anker in flach, anker
