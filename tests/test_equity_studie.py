# -*- coding: utf-8 -*-
"""Equity-DD-Studie (On-Demand, Nutzer-Wunsch 03.10.2026): Kurve mit
realisiertem UND offenem Betrag, GMT-Abgleich JE Währungspaar (mit
Median-Fallback), ehrliche Meldung fehlender Kurse.

Alles gegen synthetische Bars/Trades — kein MT5, kein Netz (beide
Testsymbole sind USD-quotiert, EZB-Kurse werden nie gebraucht).
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from mqlkiscanner import kursdaten
from mqlkiscanner.equity_studie import ermittle_gmt_je_symbol, studie

STUNDE = 3600


def _trade(symbol, direction, open_dt, close_dt, entry, exit_, lots=1.0, pnl=None):
    return SimpleNamespace(
        symbol=symbol, direction=direction,
        open_time=open_dt, close_time=close_dt,
        entry_price=entry, exit_price=exit_, volume=lots,
        net=pnl if pnl is not None else (exit_ - entry) * 100.0 * lots,
    )


def _bars(symbol, start_dt, stunden, base=2000.0, schritt=7.0, band=0.4):
    """Synthetische H1-Bars: je Stunde ein EINDEUTIGES enges Preisband —
    nur der korrekte GMT-Offset trifft beim Preisabgleich."""
    bars = []
    for i in range(stunden):
        t = start_dt + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = base + schritt * i
        bars.append({"time": epoch, "open": close - band / 2, "high": close + band / 2,
                     "low": close - band / 2, "close": close})
    return bars


def _parsed(trades):
    return SimpleNamespace(trades=trades, balances=[], pendings=[])


def test_studie_trennt_usd_maximum_vom_relativmaximum(monkeypatch):
    from mqlkiscanner import equity_studie as es
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 8)
    for bar, close in zip(bars, [1996, 2000, 2010, 1995, 2000, 1995, 1995, 1995]):
        bar["close"] = close
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(minutes=1),
               start + dt.timedelta(hours=2, minutes=1), 2000, 2010, pnl=1000),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=3, minutes=1),
               start + dt.timedelta(hours=5, minutes=1), 2000, 1995, pnl=-500),
    ]
    k = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}), 1000)["kennzahlen"]
    assert k["equity_dd_usd"] == 500
    assert k["dd_pct_am_usd_max"] == 25
    assert k["equity_dd_pct"] == 40
    assert k["dd_usd_am_rel_max"] == 400
    assert k["dd_bis"] != k["dd_rel_bis"]
    from mqlkiscanner.equity_studie_ui import _chart
    figur = _chart({"kennzahlen": k, "punkte": [
        {"t": k["dd_von"], "equity": 2000, "realisiert": 2000,
         "floating": 0, "messpunkt": True},
        {"t": k["dd_bis"], "equity": 1500, "realisiert": 2000,
         "floating": -500, "messpunkt": True}]}, 1000, 30)
    anker_text = [a.text for a in figur.layout.annotations if "Max-Rückfall" in a.text]
    assert "25.0 %" in anker_text[0]
    assert "40.0 %" not in anker_text[0]


def test_studie_netto_fehlender_kurse_bleibt_enthalten(monkeypatch):
    from mqlkiscanner import equity_studie as es
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 8)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(minutes=1),
                     start + dt.timedelta(hours=3, minutes=1), 2000, 2001, pnl=100)
              for _ in range(4)]
    trades.append(_trade("US100", "buy", start + dt.timedelta(minutes=1),
                         start + dt.timedelta(hours=3, minutes=1), 2000, 1995, pnl=-500))
    data = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}), 1000)
    assert data["punkte"][-1]["realisiert"] == 900
    assert data["kennzahlen"]["trades_realisiert"] == 5
    assert data["kennzahlen"]["verlaesslich"] is False


def test_studie_trennt_realisiert_und_floating():
    """Kernfall (gleiche Geometrie wie die produktive Reko): realisiert
    konstant (net=0), floating steigt erst, bricht dann ein — die Studie
    muss beide Spuren getrennt UND die Equity-Messung liefern."""
    start = dt.datetime(2026, 1, 1)
    bars = []
    for i in range(24):
        t = start + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = 1990.0 if i == 10 else 2000.0 + 7.0 * i
        bars.append({"time": epoch, "open": close, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=22), bars[1]["close"] - 0.1,
               bars[22]["close"], lots=1.0, pnl=0.0),
    ]
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}),
                 startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    k = erg["kennzahlen"]
    # Realisiert-Spur: konstant 10 000 (net=0) — braucht keine Kurse.
    assert {p["realisiert"] for p in erg["punkte"]} == {10_000.0}
    # Floating-Tief: 100 USD je 1 $ Bewegung × (1990 − 2006.9) = −1 690 USD.
    assert abs(k["floating_min_usd"] - (-1690.0)) < 1.0, k
    # Equity-DD: Peak floating ~ +5 610 (Bar 9), Tief 8 310 → Rückfall > 7 000.
    assert k["equity_dd_usd"] > 5_000.0, k
    assert k["equity_dd_pct"] > 40.0, k
    assert k["dd_von"] is not None and k["dd_bis"] is not None
    # Der Tiefpunkt der Equity-Spur liegt unter dem Startkapital.
    assert min(p["equity"] for p in erg["punkte"] if p["equity"] is not None) < 10_000.0


def test_gmt_je_symbol_eigenstaendig_erkannt():
    """Zwei Währungspaare, beide 2 h vor Terminal-Zeit — JE Symbol bekommt
    seinen eigenen erkannten Versatz (Nutzer-Wunsch 03.10.2026)."""
    start = dt.datetime(2026, 1, 1)
    bars_gold = _bars("XAUUSD", start, 48, base=2000.0, schritt=7.0, band=0.8)
    bars_eur = _bars("EURUSD", start, 48, base=1.10, schritt=0.007, band=0.0008)
    trades = []
    for i in range(6, 40, 4):
        o = start + dt.timedelta(hours=i)
        c = o + dt.timedelta(hours=1)
        # Beide Symbole handeln im selben Fenster, 2 h vor Terminal-Zeit.
        trades.append(_trade("XAUUSD", "buy", o - dt.timedelta(hours=2),
                             c - dt.timedelta(hours=2),
                             bars_gold[i]["close"] - 0.1, bars_gold[i + 1]["close"]))
        trades.append(_trade("EURUSD", "sell", o - dt.timedelta(hours=2),
                             c - dt.timedelta(hours=2),
                             bars_eur[i]["close"] - 0.0001, bars_eur[i + 1]["close"]))
    erg = studie(_parsed(trades),
                 kursdaten.FakeKursDaten({"XAUUSD": bars_gold, "EURUSD": bars_eur}),
                 startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    befunde = {b["symbol"]: b for b in erg["symbole"]}
    assert befunde["XAUUSD"]["status"] == "erkannt", befunde
    assert befunde["EURUSD"]["status"] == "erkannt", befunde
    assert befunde["XAUUSD"]["gmt_h"] == 2 and befunde["EURUSD"]["gmt_h"] == 2
    assert erg["median_gmt_h"] == 2


def test_gmt_fallback_median_fuer_duennes_symbol():
    """Ein Symbol mit nur 1 Trade belegt den Versatz nicht selbst — es
    bekommt den Median der erkannten Symbole, offengelegt im Befund."""
    start = dt.datetime(2026, 1, 1)
    bars_gold = _bars("XAUUSD", start, 48)
    bars_eur = _bars("EURUSD", start, 48, base=1.10, schritt=0.007, band=0.0008)
    trades = []
    for i in range(6, 40, 4):
        o = start + dt.timedelta(hours=i)
        trades.append(_trade("XAUUSD", "buy",
                             o - dt.timedelta(hours=2),
                             o - dt.timedelta(hours=1),
                             bars_gold[i]["close"] - 0.1,
                             bars_gold[i + 1]["close"]))
    # EURUSD: genau EIN Trade (unter MIN_EIGENE_PROBEN), Zeiten passend zu +2 h.
    o = start + dt.timedelta(hours=8)
    trades.append(_trade("EURUSD", "sell", o - dt.timedelta(hours=2),
                         o - dt.timedelta(hours=1),
                         bars_eur[8]["close"] - 0.0001, bars_eur[9]["close"]))
    gmt = ermittle_gmt_je_symbol(trades, {"XAUUSD": bars_gold, "EURUSD": bars_eur})
    befunde = {b["symbol"]: b for b in gmt["befunde"]}
    assert befunde["XAUUSD"]["status"] == "erkannt", befunde
    assert befunde["XAUUSD"]["gmt_h"] == 2
    assert befunde["EURUSD"]["status"] == "fallback_median", befunde
    assert gmt["offsets"]["EURUSD"] == 2 * STUNDE
    assert "Median" in befunde["EURUSD"]["hinweis"]


def test_einziges_duennes_symbol_noch_erkannt_mit_hinweis():
    """Nur EIN Symbol mit wenigen Proben und kein starker Partner: die
    dünne eigene Erkennung greift (mit Hinweis), statt die Studie
    komplett abzuwerfen."""
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 24)
    # EIN Trade = 2 Preisereignisse < MIN_EIGENE_PROBEN (3, Nutzer-Regel
    # 03.10.) — dünn, aber ohne jeden Partner greift die eigene Erkennung.
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=5),
               start + dt.timedelta(hours=6),
               bars[5]["close"] - 0.1, bars[6]["close"])]
    gmt = ermittle_gmt_je_symbol(trades, {"XAUUSD": bars})
    b = gmt["befunde"][0]
    assert b["status"] == "erkannt", b
    assert b["gmt_h"] == 0
    assert "einziger Beleg" in b["hinweis"]


def test_fehlendes_symbol_wird_gemeldet_rest_gerechnet():
    """Kein Kurs für ein Symbol: Study läuft für die vorhandenen Paare und
    meldet das fehlende namentlich (Nutzer-Regel 03.10.2026)."""
    start = dt.datetime(2026, 1, 1)
    bars_gold = _bars("XAUUSD", start, 24)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=5),
               bars_gold[1]["close"] - 0.1, bars_gold[5]["close"]),
        _trade("EURUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=5), 1.1050, 1.1060),
    ]
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars_gold}),
                 startkapital=5_000.0)
    assert erg["status"] == "ok", erg
    assert erg["symbole_ohne_kurse"] == ["EURUSD"]
    k = erg["kennzahlen"]
    assert k["trades_total"] == 2 and k["trades_genutzt"] == 1, k


def test_symbol_ohne_kontrakt_fliegt_raus():
    """Bars vorhanden, aber Kontraktgröße unbelegt (kein Spec, keine Klasse):
    kein erfundener Faktor — Symbol wird gemeldet statt gerechnet."""
    start = dt.datetime(2026, 1, 1)
    bars_gold = _bars("XAUUSD", start, 24)
    bars_exot = _bars("EXOTICXYZ", start, 24, base=500.0)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=5),
               bars_gold[1]["close"] - 0.1, bars_gold[5]["close"]),
        _trade("EXOTICXYZ", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=5),
               bars_exot[1]["close"] - 0.1, bars_exot[5]["close"]),
    ]
    erg = studie(_parsed(trades),
                 kursdaten.FakeKursDaten({"XAUUSD": bars_gold,
                                          "EXOTICXYZ": bars_exot}),
                 startkapital=5_000.0)
    assert erg["status"] == "ok", erg
    assert erg["symbole_ohne_kontrakt"] == ["EXOTICXYZ"], erg
    assert erg["kennzahlen"]["trades_genutzt"] == 1


def test_kursluecke_ist_kein_messpunkt_realisiert_laeuft_weiter():
    """Fehlt der Kurs in EINER Stunde (Datenloch), ist dieser Punkt keine
    Equity-Messpunkt (None, nicht interpoliert) — die Realisiert-Spur
    läuft durch, denn sie braucht keine Kurse."""
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 24)
    entry, exit_ = bars[5]["close"] - 0.1, bars[15]["close"]
    del bars[10]  # Datenloch in Stunde 10 (Liste rutscht — Preise vorher fixiert)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=5),
               start + dt.timedelta(hours=15),
               entry, exit_, pnl=500.0),
    ]
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}),
                 startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    loch = next(p for p in erg["punkte"]
                if p["t"] == bars[9]["time"] + 2 * STUNDE)
    assert loch["messpunkt"] is False
    assert loch["equity"] is None and loch["floating"] is None
    assert loch["realisiert"] == 10_000.0  # Trade schließt erst Stunde 15
    assert erg["kennzahlen"]["punkte_mit_luecke"] == 1
    assert {p["realisiert"] for p in erg["punkte"]} == {10_000.0, 10_500.0}


def test_ohne_kapitalbasis_nur_usd_kurven():
    """Startkapital 0: Prozentwerte entfallen ehrlich (None), die
    USD-Verläufe sind trotzdem exakt."""
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 24)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=10),
               bars[1]["close"] - 0.1, bars[10]["close"], pnl=200.0),
    ]
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}),
                 startkapital=0.0)
    assert erg["status"] == "ok", erg
    k = erg["kennzahlen"]
    assert k["equity_dd_pct"] is None
    assert k["equity_dd_usd"] >= 0.0
    assert any(p["equity"] is not None for p in erg["punkte"])


def test_keine_trades_ist_skipped():
    erg = studie(_parsed([]), kursdaten.FakeKursDaten({}), startkapital=1_000.0)
    assert erg["status"] == "skipped"
    assert "keine geschlossenen Trades" in erg["grund"]


def test_alle_kurse_fehlend_ist_skipped_mit_namen():
    start = dt.datetime(2026, 1, 1)
    trades = [_trade("EURUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=3), 1.1, 1.2)]
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({}), 1_000.0)
    assert erg["status"] == "skipped"
    assert "EURUSD" in erg["grund"]


# ----------------------------------------------------------- GUI (AppTest)

def _fake_studie_daten() -> dict:
    """Vollständiges Ergebnis-Dict für den GUI-Pfad (Chart, Kennzahlen,
    Risiko-Texte, Symbol-Diagnose) — ohne Terminal, ohne echte Rechnung."""
    basis = 1760000000 // 3600 * 3600
    punkte = []
    for i in range(6):
        floating = -410.0 if i == 3 else 0.0
        punkte.append({
            "t": basis + i * STUNDE,
            "equity": 10_000.0 + i * 20.0 + floating,
            "realisiert": 10_000.0 + i * 20.0,
            "floating": floating,
            "messpunkt": i != 4,
        })
    punkte[4]["equity"] = None
    punkte[4]["floating"] = None
    return {
        "status": "ok",
        "punkte": punkte,
        "symbole": [
            {"symbol": "XAUUSD", "gmt_h": 3, "trefferquote": 0.87,
             "status": "erkannt", "hinweis": ""},
            {"symbol": "EURUSD", "gmt_h": None, "trefferquote": None,
             "status": "keine_kurse", "hinweis": "keine H1-Kurse vom Referenzterminal"},
        ],
        "kennzahlen": {
            "startkapital": 10_000.0,
            "equity_dd_usd": 2_310.0,
            "equity_dd_pct": 18.5,
            "dd_pct_am_usd_max": 18.5,
            "dd_pct_max_rel": 18.5,
            "dd_von": basis + 2 * STUNDE,
            "dd_bis": basis + 3 * STUNDE,
            "floating_min_usd": -410.0,
            "floating_min_t": basis + 3 * STUNDE,
            "floating_max_usd": 120.0,
            "unterwasser_tage_max": 6.2,
            "abdeckung_pct": 99.1,
            "rasterpunkte": 6,
            "messpunkte": 4,
            "punkte_mit_luecke": 1,
            "fx_luecke": False,
            "trades_total": 9,
            "trades_genutzt": 8,
        },
        "median_gmt_h": 3,
        "symbole_ohne_kurse": ["EURUSD"],
        "symbole_ohne_kontrakt": [],
        "meta": {"name": "Studien-Fall", "signal_id": 42, "quelle": "mql5",
                 "trades_pfad": "fake.csv",
                 "startkapital_quelle": "csv_einzahlungen"},
    }


def test_equity_studie_seite_rendert_ende_zu_ende(tmp_path, monkeypatch):
    """Die eigene Seite durchspielt den kompletten GUI-Pfad: Auswahl →
    (gefake) Berechnung → Kennzahlen, Plotly-Chart, Risiko-Texte und
    Symbol-Diagnose. Die echte Messung testen die Modul-Tests oben."""
    from pathlib import Path as _Path
    from streamlit.testing.v1 import AppTest

    from mqlkiscanner import equity_studie_ui, pipeline

    csv_pfad = tmp_path / "trades.csv"
    csv_pfad.write_text("Time;…\n", encoding="utf-8")
    probe = pipeline.ScanResult(
        id=42, name="Studien-Fall", ampel="🟡", quelle="mql5",
        trades_path=str(csv_pfad), dd_equity_pct=12.0,
        martingale_flag=False, peak_positionen=7)
    monkeypatch.setattr(pipeline, "results_from_db", lambda: [probe])
    monkeypatch.setattr(equity_studie_ui, "berechne",
                        lambda result, progress: _fake_studie_daten())

    root = _Path(__file__).resolve().parents[1]
    at = AppTest.from_file(str(root / "app_pages" / "equity_studie.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    text = "\n".join(str(el.value) for el in at.markdown) + \
        "\n".join(str(el.value) for el in at.caption) + \
        "\n".join(str(el.value) for el in at.warning)
    # Kennzahlen, Schranken-Box (18,5 % < 30 % → im Rahmen) und die
    # Meldung des fehlenden Kurses sind sichtbar gerendert.
    assert "18.5" in text or "18,5" in text
    assert "EURUSD" in text


def test_anker_klemmt_an_ersten_messpunkt_bei_kuerzerer_kurshistorie():
    """Trades beginnen Monate vor der ersten verfügbaren Bar (Referenz-
    terminal hat kürzere Historie als das Signal): der Anker bleibt am
    ersten messbaren Punkt, damit die Kurve nicht in einen toten
    Zeitbereich gezogen wird (Nutzer-Feedback 03.10. — Chart zeigte die
    eigentliche Kurve nur als schmalen Streifen). Das realisierte Netto
    der Vorzeit geht in den Anker ein."""
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 24)
    frueh = dt.datetime(2025, 9, 1)
    trades = [
        # komplett vor allen Bars — realisiert, nie floating-messbar
        _trade("XAUUSD", "buy", frueh, frueh + dt.timedelta(hours=5),
               2000.0, 2000.0, pnl=400.0),
    ]
    # 6 Trades im Jan-Fenster (12 Preisproben ≥ GMT_LOKAL_MIN_PROBEN),
    # damit die Zeitbasis über die Jan-Woche belegt ist.
    for i in (2, 6, 10, 14, 18, 22):
        trades.append(_trade(
            "XAUUSD", "buy", start + dt.timedelta(hours=i),
            start + dt.timedelta(hours=i + 1),
            bars[i]["close"] - 0.1, bars[i + 1]["close"], pnl=-100.0))
    erg = studie(_parsed(trades), kursdaten.FakeKursDaten({"XAUUSD": bars}),
                 startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    erster = erg["punkte"][0]
    # Anker am ersten Bar-Ende (Jan 2026), NICHT beim Trade von Sep 2025.
    assert erster["t"] == bars[0]["time"] + STUNDE, erster
    # Realisiert der Vorzeit (+400) ist im Anker enthalten — kein
    # stiller Verlust der Vorperioden.
    assert erster["realisiert"] == 10_400.0
    assert erster["equity"] == 10_400.0
    # Die Kurve bleibt im messbaren Fenster: kein Punkt liegt vor den Bars.
    fruehester = min(p["t"] for p in erg["punkte"])
    assert fruehester >= bars[0]["time"]


def test_symbol_mit_drei_stimmenden_proben_eigenstaendig_erkannt():
    """Nutzer-Regel 03.10.: 3 stimmende, eindeutige Proben belegen den
    Symbol-Versatz selbst — 2 Trades (4 Proben) reichen, ohne Median-
    Fallback (vorher Schwelle 5)."""
    start = dt.datetime(2026, 1, 1)
    bars_gold = _bars("XAUUSD", start, 48)
    bars_eur = _bars("EURUSD", start, 48, base=1.10, schritt=0.007, band=0.0008)
    trades = []
    for i in range(6, 40, 4):
        o = start + dt.timedelta(hours=i)
        trades.append(_trade("XAUUSD", "buy", o - dt.timedelta(hours=2),
                             o - dt.timedelta(hours=1),
                             bars_gold[i]["close"] - 0.1,
                             bars_gold[i + 1]["close"]))
    # EURUSD: genau 2 Trades (4 Proben) eindeutig auf +2 h.
    for i in (8, 20):
        o = start + dt.timedelta(hours=i)
        trades.append(_trade("EURUSD", "sell", o - dt.timedelta(hours=2),
                             o - dt.timedelta(hours=1),
                             bars_eur[i]["close"] - 0.0001,
                             bars_eur[i + 1]["close"]))
    gmt = ermittle_gmt_je_symbol(trades, {"XAUUSD": bars_gold, "EURUSD": bars_eur})
    befunde = {b["symbol"]: b for b in gmt["befunde"]}
    assert befunde["EURUSD"]["status"] == "erkannt", befunde
    assert befunde["EURUSD"]["gmt_h"] == 2
