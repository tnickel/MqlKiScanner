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

import pytest

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


class _MultiTerminalKurse:
    """Kursanbieter-Doppel mit Multi-Terminal-Schnittstelle (siehe
    test_equity_rekonstruktion): Wechsel muss am Ende zurückgesetzt sein."""

    def __init__(self, quelle0, quelle1):
        self.quellen = [quelle0, quelle1]
        self.terminal_idx = 0
        self.wechsel = 0
        self.zurueck = 0

    def starten(self):
        return True, "fake"

    def beenden(self):
        pass

    def hole_h1(self, symbol, von, bis, gmt_offset_s=0):
        bars = self.quellen[self.terminal_idx].get(symbol, [])
        return [b for b in bars
                if von + gmt_offset_s <= b["time"] <= bis + gmt_offset_s] or None

    def hat_weiteren_terminal(self):
        return self.terminal_idx < len(self.quellen) - 1

    def wechsle_terminal(self):
        self.terminal_idx += 1
        self.wechsel += 1
        return True, "gewechselt"

    def zurueck_zum_ersten_terminal(self):
        self.terminal_idx = 0
        self.zurueck += 1
        return True, "zurueck"


def test_terminal_fallback_wird_zurueckgesetzt():
    """Terminal-Fallback darf nicht kleben — nach studie() muss wieder
    Quelle 0 aktiv sein (Workflow-Scan cached den Anbieter über den Lauf)."""
    start = dt.datetime(2026, 1, 1)
    bars_a = _bars("XAUUSD", start, 24)
    bars_b = _bars("NOSUCH", start, 24)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2007.0),
              _trade("NOSUCH", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2007.0)]
    fake = _MultiTerminalKurse({"XAUUSD": bars_a}, {"NOSUCH": bars_b})
    studie(_parsed(trades), fake, 1000)
    assert fake.wechsel >= 1, "Fallback hätte ausgelöst werden müssen"
    assert fake.terminal_idx == 0, "Terminal-Wechsel klebt"
    assert fake.zurueck >= 1, "zurueck_zum_ersten_terminal wurde nie gerufen"


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
            "kapitalfluesse_nach_start": 3,
        },
        "median_gmt_h": 3,
        "symbole_ohne_kurse": ["EURUSD"],
        "symbole_ohne_kontrakt": [],
        "meta": {"name": "Studien-Fall", "signal_id": 42, "quelle": "mql5",
                 "trades_pfad": "fake.csv",
                 "startkapital_quelle": "csv_einzahlungen"},
        "konto_studie": {"punkte": [
                {"t": basis + i * STUNDE,
                 "konto_equity": 10000 + i * 100, "konto_balance": 10000 + i * 100,
                 "rendite_index": 1.0 + i * 0.01,
                 "drawdown_pct": (0.5 if i == 2 else 0.0) if i < 5 else None}
                for i in range(4)],
            "verlaesslich": False,
            "kennzahlen": {"konto_equity_dd_pct": None,
                           "konto_equity_dd_beobachtet_pct": 38.14,
                           "index_gueltig_bis": basis + 3 * STUNDE}},
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
        "\n".join(str(el.value) for el in at.warning) + \
        "\n".join(f"{el.label} {el.value}" for el in at.metric) + \
        "\n".join(str(el.value) for el in at.info)
    # Kennzahlen, Schranken-Box (18,5 % < 30 % → im Rahmen) und die
    # Meldung des fehlenden Kurses sind sichtbar gerendert.
    assert "18.5" in text or "18,5" in text
    assert "EURUSD" in text
    # Kapitalfluss-Brücke (Nutzer-Fall ATong 04.10.): Karte + Hinweis
    # erscheinen bei Entnahmen/Flows und nennen die Website-vergleichbare
    # Prozentzahl.
    assert "38.1" in text or "38,1" in text
    assert "Ein-/Auszahlungen" in text
    # Kopier-Simulation (Nutzer-Wunsch 04.10.): 10K-Konstantkonto, Karte
    # nennt den Kopier-DD und den simulierten Rückfall in USD.
    assert "Max-Drawdown beim Kopieren" in text
    assert "3.814" in text or "3.814" in text.replace(",", ".") or "3814" in text
    assert "Kontostand heute (simuliert)" in text


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


def test_ueberdeckung_klassifiziert_luecken_nach_lage_und_art():
    """Nutzer-Wunsch 05.10.: Kursueberdeckung je Symbol visualisierbar —
    die Datenfunktion klassifiziert Einzel-Wartungsstunden (<= 3 h) gegen
    fehlende Abschnitte (> 3 h) und die Lage (anfang/mitte/ende)."""
    import datetime as dt
    start = dt.datetime(2026, 1, 5)
    # 100 Bars durchgehend, dann 1h-Luecke (Wartung), dann 40 Bars,
    # dann 30h-Luecke (Abschnitt = Wochenende -> Zaehlt nicht!), danach nix.
    bars = _bars("XAUUSD", start, 100)
    bars += _bars("XAUUSD", start + dt.timedelta(hours=101), 40,
                  base=bars[-1]["close"])
    # Trades: laufen IN die 30h-Pause hoechstens 1 h rein und enden
    # 3 h nach der letzten Bar (Ende-Luecke).
    letzte_bar_ende = start + dt.timedelta(hours=141)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=2),
               start + dt.timedelta(hours=50), 2000.0, 2050.0),
        # laeuft quer durch die 1-h-Luecke zwischen den Bar-Bloecken (Mitte)
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=100),
               start + dt.timedelta(hours=103), 2600.0, 2605.0),
        # endet 3 h nach der letzten Bar -> Ende-Luecke
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=130),
               letzte_bar_ende + dt.timedelta(hours=3), 2850.0, 2855.0),
    ]
    from mqlkiscanner import equity_studie as es
    erg = es.ueberdeckung_je_symbol(trades,
                                    {"XAUUSD": bars}, {"XAUUSD": 0})
    assert len(erg) == 1
    e = erg[0]
    assert e["symbol"] == "XAUUSD"
    # 1 h Mitte-Wartung + 2 h Ende
    assert e["fehlend_h"] == 3, e
    arten = sorted(l["art"] for l in e["luecken"])
    lagen = sorted(l["lage"] for l in e["luecken"])
    assert arten == ["wartung", "wartung"], e["luecken"]   # beide <= 3 h
    assert lagen == ["ende", "mitte"], e["luecken"]
    assert e["abdeckung_pct"] is not None and e["abdeckung_pct"] < 100.0
    # Abschnitts-Fall (> 3 h) separat: 5-h-Luecke in den Bars
    bars2 = _bars("XAUUSD", start, 60) + _bars(
        "XAUUSD", start + dt.timedelta(hours=66), 20, base=3000.0)
    erg2 = es.ueberdeckung_je_symbol(
        [_trade("XAUUSD", "buy", start + dt.timedelta(hours=2),
                start + dt.timedelta(hours=80), 2000.0, 2100.0)],
        {"XAUUSD": bars2}, {"XAUUSD": 0})
    abschnitt = [l for l in erg2[0]["luecken"] if l["art"] == "abschnitt"]
    assert abschnitt and abschnitt[0]["h"] >= 5


# --------- Reale Kontokurve in der Studie: Flows + Rest-Flows (Nutzer 05.10.)
def test_studie_bucht_flows_und_rest_nach_letztem_trade(monkeypatch):
    """Einzahlung zur Handelszeit hebt Kurve/Peak; Auszahlung NACH dem
    letzten Trade (außerhalb des Rasters!) muss als finaler Punkt
    gebucht werden — sonst fehlt sie in Endwert und DD."""
    from mqlkiscanner import equity_studie as es
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 8)
    for bar, close in zip(bars, [2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000]):
        bar["close"] = close
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(minutes=1),
               start + dt.timedelta(hours=2, minutes=1), 2000, 2000, pnl=2000.0),
    ]
    parsed = SimpleNamespace(
        trades=trades,
        balances=[SimpleNamespace(time=start + dt.timedelta(hours=1),
                                  amount=50_000.0),
                  SimpleNamespace(time=start + dt.timedelta(hours=6),
                                  amount=-30_000.0)],
        pendings=[])
    erg = studie(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}), 10_000.0)
    k = erg["kennzahlen"]
    # Endwert: 10k Start + 2k Gewinn + 50k Einzahlung - 30k Auszahlung = 32k
    assert erg["punkte"][-1]["equity"] == 32_000.0
    assert k["equity_dd_pct"] == 0.0        # keine Verluste, Auszahlung mitigiert
    assert "reale Kontokurve" in erg["methodik"]


def test_studie_einzahlung_vergroessert_den_ddd_naechster_verlust_zaehlt(monkeypatch):
    """Einzahlung hebt den Peak — der NACHFOLGENDE floating-Verlust zaehlt
    gegen das gewachsene Konto (Kopierer-Perspektive, Nutzer-Regel)."""
    from mqlkiscanner import equity_studie as es
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 8)
    for bar, close in zip(bars, [2000, 2000, 2000, 2000, 1950, 2000, 2000, 2000]):
        bar["close"] = close
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(minutes=1),
               start + dt.timedelta(hours=6, minutes=1), 2000, 2000, pnl=0.0),
    ]
    parsed = SimpleNamespace(
        trades=trades,
        balances=[SimpleNamespace(time=start + dt.timedelta(hours=1),
                                  amount=40_000.0)],
        pendings=[])
    erg = studie(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}), 10_000.0)
    k = erg["kennzahlen"]
    # Peak ~50k (10k + 40k), floating-Tief Stunde 4: 1 Lot x 100 x 50 = -5k
    # DD = 5.000/50.000 = 10 % — OHNE Einzahlung waeren es 5.000/10.000 = 50 %.
    assert k["equity_dd_pct"] == 10.0


def test_studie_auszahlung_in_kursluecke_erzeugt_keinen_drawdown(monkeypatch):
    """Nutzer-Fall KiraCat 05.10.: Auszahlung in einer Stunde ohne Kurs
    (kein Messpunkt) darf nicht verworfen werden, sonst zaehlt sie am
    naechsten Messpunkt als Drawdown."""
    from mqlkiscanner import equity_studie as es
    monkeypatch.setattr(es, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0}, "befunde": []})
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 12)
    for bar in bars:
        bar["close"] = 2000
    del bars[6]
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(minutes=1),
               start + dt.timedelta(hours=2, minutes=1), 2000, 2000, pnl=2000.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=4, minutes=1),
               start + dt.timedelta(hours=10, minutes=1), 2000, 2000, pnl=0.0),
    ]
    parsed = SimpleNamespace(
        trades=trades,
        balances=[SimpleNamespace(time=start + dt.timedelta(hours=6, minutes=30),
                                  amount=-8_000.0)],
        pendings=[])
    erg = es.studie(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}), 10_000.0)
    k = erg["kennzahlen"]
    assert any(not p["messpunkt"] and p["flow_delta"] < 0 for p in erg["punkte"])
    assert erg["punkte"][-1]["realisiert"] == 4_000.0
    assert k["equity_dd_pct"] == 0.0


def test_chart_unterwasser_senkt_peak_bei_auszahlung():
    """Unterwasser-Grafik nach der Engine-Regel (KiraCat: −97 % aus 48k
    Auszahlungen). Fluss an einem Nicht-Messpunkt wird mitgefuehrt."""
    from mqlkiscanner.equity_studie_ui import _chart
    punkte = [
        {"t": 0, "equity": 12_000.0, "messpunkt": True, "flow_delta": 0.0},
        {"t": 3600, "equity": None, "messpunkt": False, "flow_delta": -8_000.0},
        {"t": 7200, "equity": 4_000.0, "messpunkt": True, "flow_delta": 0.0},
        {"t": 10800, "equity": 3_000.0, "messpunkt": True, "flow_delta": 0.0},
    ]
    fig = _chart({"kennzahlen": {}, "punkte": punkte}, 10_000.0, 30)
    unterwasser = list(fig.data[2].y)
    assert fig.data[2].visible == "legendonly"
    assert unterwasser[0] == 0.0
    assert unterwasser[1] is None
    assert unterwasser[2] == 0.0
    assert unterwasser[3] == pytest.approx(-25.0)


def test_chart_equity_dd_wie_mql5_offener_verlust_durch_balance():
    """Nutzer-Wunsch KiraCat 05.10.: unten wie die MQL5-Signalseite —
    (Equity − Balance) / Balance, ohne offene Position 0 %. Realisierte
    Verluste und Auszahlungen erzeugen dort keinen Drawdown."""
    from mqlkiscanner.equity_studie_ui import _chart
    punkte = [
        {"t": 0, "equity": 10_000.0, "realisiert": 10_000.0, "floating": 0.0,
         "messpunkt": True},
        {"t": 3600, "equity": 8_000.0, "realisiert": 10_000.0, "floating": -2_000.0,
         "messpunkt": True},
        {"t": 7200, "equity": None, "realisiert": 10_000.0, "floating": None,
         "messpunkt": False},
        {"t": 10800, "equity": 7_000.0, "realisiert": 7_000.0, "floating": 0.0,
         "messpunkt": True},
        {"t": 14400, "equity": 1_200.0, "realisiert": 1_500.0, "floating": -300.0,
         "messpunkt": True, "flow_delta": -5_000.0},
    ]
    fig = _chart({"kennzahlen": {}, "punkte": punkte}, 10_000.0, 30)
    dd = list(fig.data[1].y)
    assert dd[0] == 0.0
    assert dd[1] == pytest.approx(-20.0)
    assert dd[2] is None
    assert dd[3] == 0.0                       # realisierter Verlust: 0 wie MQL5
    assert dd[4] == pytest.approx(-20.0)      # 300 offen auf 1.500 Balance
    assert "max 20,0 %" in fig.layout.annotations[1].text
