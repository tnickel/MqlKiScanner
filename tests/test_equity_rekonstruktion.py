# -*- coding: utf-8 -*-
"""Equity-DD-Rekonstruktion aus Kursdaten + Auto-GMT (Nutzer-Wunsch 28.09.2026).

Alles gegen synthetische Bars/Trades — kein MT5 nötig. Deckt ab:
GMT-Erkennung (Preisabgleich, eindeutig/falsch/zu wenig Proben),
Equity-Kurve mit floating PnL, DD-Berechnung, Abdeckungs-Regel (kein
Schranken-Wert unter 95 %), Schranken-Integration (refresh_report_verdict
und results_from_db) und stillen Verfall ohne Kursanbieter.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from mqlkiscanner import config, db as _db, kursdaten
from mqlkiscanner.forensics import equity_rekonstruktion as er


def _trade(symbol, direction, open_dt, close_dt, entry, exit_, lots=1.0, pnl=None):
    return SimpleNamespace(
        symbol=symbol, direction=direction,
        open_time=open_dt, close_time=close_dt,
        entry_price=entry, exit_price=exit_, volume=lots,
        net=pnl if pnl is not None else (exit_ - entry) * 100.0 * lots,
    )


def _bars(symbol, start_dt, stunden, base=2000.0, schritt=7.0):
    """Synthetische H1-Bars: je Stunde EINDEUTIGES, enges Preisband
    (close ± 0.4) — nur der korrekte Offset trifft beim Preisabgleich."""
    bars = []
    for i in range(stunden):
        t = start_dt + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = base + schritt * i
        bars.append({"time": epoch, "open": close - 0.2, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    return bars


STUNDE = 3600


class _MultiTerminalKurse:
    """Kursanbieter-Doppel mit Multi-Terminal-Schnittstelle: Quelle 0 kennt
    nur XAUUSD, Quelle 1 nur NOSUCH — der Wechsel muss am Ende wieder
    zurückgesetzt werden (Review-Befund: Terminal-Wechsel klebte)."""

    def __init__(self, bars_je_symbol_quelle0, bars_je_symbol_quelle1):
        self.quellen = [bars_je_symbol_quelle0, bars_je_symbol_quelle1]
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


def test_gmt_erkennung_findet_eindeutigen_shift():
    # Terminal-Bars ab 2026-01-01 00:00 UTC; Trades 2h VOR Terminal-Zeit
    start = dt.datetime(2026, 1, 1, 0, 0)
    bars = _bars("XAUUSD", start, 48)
    trades = []
    for i in range(6, 40, 4):
        o = start + dt.timedelta(hours=i)
        c = o + dt.timedelta(hours=1)
        entry = bars[i]["close"] - 0.1      # eindeutig in Band i
        exit_ = bars[i + 1]["close"]        # eindeutig in Band i+1
        trades.append(_trade("XAUUSD", "buy",
                             o - dt.timedelta(hours=2),
                             c - dt.timedelta(hours=2),
                             entry, exit_))
    erg = er.ermittle_gmt_offset(trades, {"XAUUSD": bars})
    assert erg["offset_s"] == 2 * STUNDE, erg
    assert erg["trefferquote"] >= 0.9


def test_gmt_erkennung_ohne_match_liefert_none():
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 48)
    # Preise weit außerhalb jeder Bar (×10)
    trades = [_trade("XAUUSD", "buy",
                     start + dt.timedelta(hours=5),
                     start + dt.timedelta(hours=6),
                     99999.0, 99999.0)]
    erg = er.ermittle_gmt_offset(trades, {"XAUUSD": bars})
    assert erg["offset_s"] is None
    assert erg["trefferquote"] < er.GMT_MIN_TREFFER


def test_rekonstruktion_misst_floating_drawdown():
    """Der Kernfall: realisiert PLUSSE, aber floating Verlust in der Mitte —
    der Trading-DD (nur geschlossene) sähe 0 %, die Rekonstruktion misst den
    echten Equity-Einbruch."""
    start = dt.datetime(2026, 1, 1)
    # Jede Stunde eindeutiges Preisband (±0.4); Einbruch bei Stunde 10 auf 1990
    bars = []
    for i in range(24):
        t = start + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = 1990.0 if i == 10 else 2000.0 + 7.0 * i
        bars.append({"time": epoch, "open": close, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    # Kauf in Bar 1 (Preis 2006.9), Schluss in Bar 22; floating tief in Bar 10:
    # 100 USD je 1 $ × (1990 − 2006.9) = −1690 USD → Equity-Tief 8310 → 16.9 %
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=22), bars[1]["close"] - 0.1,
               bars[22]["close"], lots=1.0, pnl=0.0),
    ]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    fake = kursdaten.FakeKursDaten({"XAUUSD": bars})
    erg = er.rekonstruiere(parsed, fake, startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    assert erg["verlaesslich"] is True
    assert erg["gmt_offset_h"] == 0, erg
    # Kern der Sache: Trading-DD wäre 0 % (net=0) — die Rekonstruktion MISST
    # den tiefen floating-Einbruch (Kauf 2006.9, Bar 10 notiert 1990).
    assert erg["equity_dd_pct"] > 40.0, erg
    assert erg["equity_dd_usd"] > 5_000.0, erg


def test_rekonstruktion_skip_ohne_kurse():
    start = dt.datetime(2026, 1, 1)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2001.0)]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    fake = kursdaten.FakeKursDaten({})  # kein Symbol
    erg = er.rekonstruiere(parsed, fake, startkapital=1000.0)
    assert erg["status"] == "skipped"
    assert "Kursdaten fehlen" in erg["grund"]


def test_terminal_fallback_wird_zurueckgesetzt():
    """Der Terminal-Wechsel als Fallback darf nicht kleben — nach
    rekonstruiere() muss wieder Quelle 0 aktiv sein, sonst binden die
    Kurse eines Signals alle Folgesignale ans falsche Terminal."""
    start = dt.datetime(2026, 1, 1)
    bars_a = _bars("XAUUSD", start, 24)
    bars_b = _bars("NOSUCH", start, 24)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2007.0),
              _trade("NOSUCH", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2007.0)]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    fake = _MultiTerminalKurse({"XAUUSD": bars_a}, {"NOSUCH": bars_b})
    er.rekonstruiere(parsed, fake, startkapital=1000.0)
    assert fake.wechsel >= 1, "Fallback hätte ausgelöst werden müssen"
    assert fake.terminal_idx == 0, "Terminal-Wechsel klebt"
    assert fake.zurueck >= 1, "zurueck_zum_ersten_terminal wurde nie gerufen"


def test_schranke_beruecksichtigt_reko_dd():
    from mqlkiscanner import pipeline
    res = pipeline.ScanResult(
        id=1, name="Reko-Fall", forensik_vorhanden=True,
        dd_equity_pct=5.0, trading_dd_pct=5.0, dd_balance_pct=5.0,
        equity_dd_rekonstruiert_pct=41.0, equity_rekon_gmt_h=2,
        score=4.0, ertrag_monat_pct=6.0)
    pipeline.refresh_report_verdict(res, {})
    assert res.schranke_verletzt is True
    assert res.ampel == "🔴"
    # Ohne Reko-Wert: alles 5 % — Schranke halten
    res2 = pipeline.ScanResult(
        id=2, forensik_vorhanden=True, dd_equity_pct=5.0, trading_dd_pct=5.0)
    pipeline.refresh_report_verdict(res2, {})
    assert res2.schranke_verletzt is False


def test_results_from_db_laedt_reko_felder():
    from mqlkiscanner import db, pipeline
    from mqlkiscanner.analysis_version import FORENSICS_VERSION
    db.init_db()
    forensik = {
        "version": FORENSICS_VERSION, "vollstaendig": True, "score": 4.0,
        "trading_dd": {"pct": 5.0, "usd": -500.0}, "winrate_pct": 60.0,
        "peak_exposure": {"positionen": 2, "shock_pct_max": 5.0},
        "kapitalbasis": {"usd": 1000.0, "quelle": "csv_einzahlungen"},
        "equity_rekonstruktion": {"status": "ok", "verlaesslich": True,
                                  "equity_dd_pct": 41.0, "equity_dd_usd": -4100.0,
                                  "gmt_offset_h": 2, "abdeckung_pct": 99.0},
        "kriterien_matrix": {}, "ampel": "🟡",
    }
    db.store_scan_result(777001, {
        "name": "Reko-Reload", "platform": "MT5", "url": "", "autor": "",
        "abo_preis": None, "abonnenten": 5, "wochen": 52,
        "stats": {"eq_dd_pct": 5.0, "forensik_ok": True, "forensik_version": FORENSICS_VERSION,
                    "ertrag_monat_pct": 6.0}},
        trades_path=None, forensik=forensik)
    neu = [r for r in pipeline.results_from_db() if r.id == 777001][0]
    assert neu.equity_dd_rekonstruiert_pct == 41.0
    assert neu.equity_rekon_gmt_h == 2
    assert neu.schranke_verletzt is True
    assert neu.ampel == "🔴"
    assert "Max-DD aus Kursen 41.0 %" in neu.urteil


def test_unzuverlaessige_rekonstruktion_fliesst_nicht_in_schranke():
    from mqlkiscanner import db, pipeline
    from mqlkiscanner.analysis_version import FORENSICS_VERSION
    db.init_db()
    forensik = {
        "version": FORENSICS_VERSION, "vollstaendig": True, "score": 4.0,
        "trading_dd": {"pct": 5.0, "usd": -500.0}, "winrate_pct": 60.0,
        "peak_exposure": {"positionen": 2, "shock_pct_max": 5.0},
        "kapitalbasis": {"usd": 1000.0, "quelle": "csv_einzahlungen"},
        # Abdeckung < 95 %: informativ, aber kein Schranken-Wert
        "equity_rekonstruktion": {"status": "unvollstaendig", "verlaesslich": False,
                                  "equity_dd_pct": 55.0, "abdeckung_pct": 60.0},
        "kriterien_matrix": {}, "ampel": "🟡",
    }
    db.store_scan_result(777002, {
        "name": "Reko-XX", "platform": "MT5", "url": "", "autor": "",
        "abo_preis": None, "abonnenten": 5, "wochen": 52,
        "stats": {"eq_dd_pct": 5.0, "forensik_ok": True, "forensik_version": FORENSICS_VERSION,
                    "ertrag_monat_pct": 6.0}},
        trades_path=None, forensik=forensik)
    neu = [r for r in pipeline.results_from_db() if r.id == 777002][0]
    assert neu.equity_dd_rekonstruiert_pct is None
    assert neu.schranke_verletzt is False


def test_engine_ohne_kursanbieter_unchanged():
    from mqlkiscanner import engine
    import tempfile, pathlib
    csv = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
           "2026.01.02 01:00:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.02 02:00:00;2010;0;;10\n")
    f = pathlib.Path(tempfile.mkdtemp()) / "t.csv"
    f.write_text(csv, encoding="utf-8")
    report = engine.analyze(str(f))
    assert "equity_rekonstruktion" not in report["forensics"]


# ------------------------------ Review 29.09. (fremde KI): 4 echte Fehler

def _ein_bars(stunden: int, base=2000.0, schritt=7.0):
    """Eindeutige Bänder (close ± 0.4, steigend) — genau EIN Offset trifft."""
    out = []
    for i in range(stunden):
        t = dt.datetime(2026, 1, 1) + dt.timedelta(hours=i)
        e = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        c = base + schritt * i
        out.append({"time": e, "open": c, "high": c + 0.4, "low": c - 0.4, "close": c})
    return out


def test_finaler_verlust_landet_in_der_kurve():
    """Review B1 (KRITISCH): Der Endpunkt nach dem letzten Trade-Schluss muss
    in der Kurve liegen — der break davor meldete einen 4.000-USD-Verlust als
    0 % DD mit verlaesslich=True."""
    bars = _ein_bars(14)
    start = dt.datetime(2026, 1, 1)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=12), bars[1]["close"] - 0.1,
               bars[12]["close"], pnl=1000.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=11),
               start + dt.timedelta(hours=12), bars[11]["close"] - 0.1,
               bars[12]["close"], pnl=-4000.0),
    ]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    # Punkt 11:00 verwendet den Close der Bar 10:00 (2070). Die zweite
    # Position oeffnet erst 11:00 und ist dort noch kein Floating-Messpunkt.
    # Peak = 10.000 + 100·(2070−2006,9) = 16.310; Endpunkt = 7.000.
    assert erg["equity_dd_usd"] == 9_310.0, erg
    assert erg["equity_dd_pct"] == 57.08, erg


def test_schluss_mitten_in_der_stunde_wird_nicht_doppelt_verbucht():
    """Review B2: Schluss 10:20 darf bei Rasterpunkt 10:00 NICHT gleichzeitig
    realisiert und floating zählen (sonst Fake-Peak, DD zu groß)."""
    bars = _ein_bars(14)
    start = dt.datetime(2026, 1, 1)
    t = _trade("XAUUSD", "buy", start + dt.timedelta(hours=8),
               start + dt.timedelta(hours=10, minutes=20),
               bars[8]["close"] - 0.1, bars[10]["close"], pnl=100.0)
    parsed = SimpleNamespace(trades=[t], balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    # Peak = floating bei Stunde 9 (100·(2063−2055,9) = 710) → 10.710;
    # Endpunkt = 10.100. OHNE Fix: Fake-Peak 11.510 → DD 12,25 %
    assert erg["equity_dd_usd"] == 610.0, erg
    assert erg["equity_dd_pct"] == 5.7, erg


def test_gmt_plateau_ist_mehrdeutig_und_skippt():
    """Review B3: Treffen mehrere Offsets gleich gut (breite Bänder), ist der
    Versatz NICHT bestimmbar — früher gewann der kleinste Betrag und meldete
    100 % Erkennung (systematisch Richtung 0 verzerrt)."""
    start = dt.datetime(2026, 1, 1)
    breit = []
    for i in range(24):
        t = start + dt.timedelta(hours=i)
        e = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        breit.append({"time": e, "open": 2000, "high": 2100,
                      "low": 1900, "close": 2000})
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=2),
                     start + dt.timedelta(hours=3), 2050.0, 2050.0, pnl=0.0)]
    erg = er.ermittle_gmt_offset(trades, {"XAUUSD": breit})
    assert erg["offset_s"] is None
    assert len(erg["plateau_h"]) > 1

    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    res = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": breit}),
                           startkapital=1000.0)
    assert res["status"] == "skipped"
    assert "mehrdeutig" in res["grund"]


def test_symbol_ohne_belegten_kontrakt_kein_phantom_wert():
    """Review B4: Für Symbole ohne Spec/Klassenkontrakt darf KEIN Faktor
    erfunden werden (früher still 100.000 → Phantom-Floating als verlässlich)."""
    bars = _ein_bars(8, base=2000.0)
    start = dt.datetime(2026, 1, 1)
    t = _trade("WEIRDCOIN", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=3), bars[1]["close"] - 0.1,
               bars[3]["close"], pnl=10.0)
    parsed = SimpleNamespace(trades=[t], balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"WEIRDCOIN": bars}),
                           startkapital=10_000.0)
    assert erg["status"] == "skipped", erg
    assert "Kontrakt" in erg["grund"], erg


def test_startkapital_null_skippt_statt_gruenem_null_dd():
    """Review B5: Ohne Kapitalbasis ist der Prozentwert bedeutungslos —
    früher status ok + dd 0.0 + verlaesslich=True."""
    bars = _ein_bars(6)
    start = dt.datetime(2026, 1, 1)
    t = _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=2), bars[1]["close"] - 0.1,
               bars[2]["close"], pnl=10.0)
    parsed = SimpleNamespace(trades=[t], balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=0.0)
    assert erg["status"] == "skipped"
    assert "Kapitalbasis" in erg["grund"]


def test_fehlende_trades_machen_ergebnis_unzuverlaessig():
    """B7-Regel REVIDIERT (Nutzer-Regel 04.10. nachts): Fehlt EIN Symbol
    komplett (Kurse/Kontrakt), wird das Signal NICHT abgewiesen — der Max-DD
    wird auf den betrachtbaren Symbolen gemessen (Teil-Messung, verlaesslich
    als Nenner freigegeben) und das fehlende Symbol namentlich gewarnt."""
    bars = _ein_bars(14)
    start = dt.datetime(2026, 1, 1)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=3), bars[1]["close"] - 0.1,
               bars[3]["close"], pnl=100.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=4),
               start + dt.timedelta(hours=6), bars[4]["close"] - 0.1,
               bars[6]["close"], pnl=100.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=7),
               start + dt.timedelta(hours=9), bars[7]["close"] - 0.1,
               bars[9]["close"], pnl=100.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=10),
               start + dt.timedelta(hours=12), bars[10]["close"] - 0.1,
               bars[12]["close"], pnl=100.0),
        # 5. Trade: Symbol OHNE Bars — 80 % nutzbar (>= 0.8-Schwelle)
        _trade("NOSUCH", "buy", start + dt.timedelta(hours=2),
               start + dt.timedelta(hours=4), 2000.0, 2010.0, pnl=50.0),
    ]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=10_000.0)
    assert erg["status"] == "ok_teilmessung", erg
    assert erg["verlaesslich"] is True, erg
    assert erg["teilmessung"] is True, erg
    assert erg["symbole_ohne_kurse"] == ["NOSUCH"]
    assert erg["symbole_nicht_betrachtet"] == ["NOSUCH"]
    assert "NOSUCH" in erg["teilmessung_hinweis"]
    assert erg["abdeckung_betrachtete_pct"] >= 95.0, erg
    # Teil-DD existiert und ist als Nenner nutzbar:
    assert erg["equity_dd_pct_raw"] >= 0.0


def test_datenloch_in_vorhandenem_symbol_bleibt_unvollstaendig():
    """Grenze der Teil-Messung (Nutzer-Regel 04.10.): Nur KOMPLETT fehlende
    Symbole fuehren zur Teil-Messung mit Warnung. Ein Datenloch in einem
    Symbol, das sonst Kurse liefert, bleibt eine Messqualitaets-Luecke —
    status unvollstaendig, kein Nenner."""
    bars = _ein_bars(24)
    loch = [b for b in bars if not (12 <= b["time"] // 3600 % 24 < 18)]
    if len(loch) >= len(bars) - 2:  # Fixture-Abhaengigkeit abfedern
        loch = bars[:4] + bars[20:]
    start = dt.datetime(2026, 1, 1)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=20), bars[1]["close"] - 0.1,
               bars[20]["close"], pnl=100.0),
    ]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": loch}),
                           startkapital=10_000.0)
    assert erg["status"] == "unvollstaendig", erg
    assert erg["verlaesslich"] is False, erg
    assert not erg.get("teilmessung")


def test_skip_status_ohne_leerzeichen():
    """Review B6: ' skipped' (führendes Leerzeichen) vs. 'skipped'."""
    parsed = SimpleNamespace(trades=[], balances=[], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({}), startkapital=1000.0)
    assert erg["status"] == "skipped"


def test_gleiche_stunde_trades_crashen_die_reko_nicht():
    """Live-Bug 29.09. (MCA100 #2153920): Zwei Trades mit identischer Open-
    UND Close-Stunde (Grid/Scalping) ließen sorted() die Trade-OBJEKTE
    vergleichen → TypeError ‚<' not supported' → Reko scheiterte auch im
    Retry. Die Key-Only-Sortierung muss das vertragen."""
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 48)
    # ZWEI Trades, exakt gleiche Open-/Close-Stunde, unterschiedliche Lots
    # und Preise (Grid-Legs in derselben Sekunde):
    t1 = _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                start + dt.timedelta(hours=22), bars[1]["close"] - 0.1,
                bars[22]["close"], lots=0.5, pnl=0.0)
    t2 = _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                start + dt.timedelta(hours=22), bars[1]["close"] - 0.1,
                bars[22]["close"], lots=0.5, pnl=0.0)
    parsed = SimpleNamespace(trades=[t1, t2], balances=[], pendings=[])
    fake = kursdaten.FakeKursDaten({"XAUUSD": bars})
    erg = er.rekonstruiere(parsed, fake, startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    assert erg["verlaesslich"] is True


# ----------------- Reale Kontokurve: Flows in der Kurs-DD (Nutzer 05.10.) --

def _flache_bars(start, stunden, basis=2000.0, dip_stunde=None, dip=1990.0):
    bars = []
    for i in range(stunden):
        t = start + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = dip if (dip_stunde is not None and i == dip_stunde) else basis
        bars.append({"time": epoch, "open": close, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    return bars


def test_einzahlung_hebt_kurve_dd_zaehlt_gegen_gestiegenes_konto():
    """Einzahlung +50k zur Mitte, floating -990 im Dip: Der DD zaehlt gegen
    das GESTIEGENE Konto (1,65 % statt 9,9 % — Basis 60k, nicht 10k). Der
    Betreiber vergroessert nach Einzahlung seine Lots; genau dieses
    Risiko soll die Messung zeigen (Nutzer-Regel 05.10.)."""
    start = dt.datetime(2026, 1, 1)
    bars = _flache_bars(start, 24, dip_stunde=10)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=22), 1999.9, 2000.0,
                     lots=1.0, pnl=0.0)]
    einzahlung = SimpleNamespace(time=start + dt.timedelta(hours=5),
                                 amount=50_000.0)
    parsed = SimpleNamespace(trades=trades, balances=[einzahlung], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=10_000.0, gmt_offset_h=0)
    assert erg["status"] == "ok", erg
    assert erg["end_equity_usd"] == 60_000.0     # Flow gebucht
    assert erg["equity_dd_pct"] == 1.67          # 1000 / 60.010 (nicht 9,9 % auf 10k)
    assert "reale Kontokurve" in erg["kapitalfluesse"]


def test_auszahlung_erzeugt_keinen_drawdown_in_der_kurs_dd():
    """Auszahlung -8k nach +2k Gewinn: Peak wird mitgesenkt — kein Schein-
    Drawdown aus Geld, das das Konto verlaesst (12k -> 4k ohne Anpassung
    waeren 66 %!)."""
    start = dt.datetime(2026, 1, 1)
    bars = _flache_bars(start, 24)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=6), 1999.9, 2000.0,
                     lots=1.0, pnl=2_000.0)]
    auszahlung = SimpleNamespace(time=start + dt.timedelta(hours=8),
                                 amount=-8_000.0)
    parsed = SimpleNamespace(trades=trades, balances=[auszahlung], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                           startkapital=10_000.0, gmt_offset_h=0)
    assert erg["status"] == "ok", erg
    assert erg["end_equity_usd"] == 4_000.0       # 10k + 2k Gewinn - 8k Auszahlung
    assert erg["equity_dd_pct"] == 0.0           # Peak-Anpassung greift
    assert "Auszahlungen erzeugen keinen Drawdown" in erg["kapitalfluesse"]


def test_auszahlung_in_kursluecke_erzeugt_keinen_drawdown():
    """Nutzer-Fall KiraCat 05.10.: Faellt eine Auszahlung in eine Stunde ohne
    Kurs (kein Messpunkt), wurde ihr Fluss verworfen — der Peak blieb stehen
    und die Auszahlung zaehlte am naechsten Messpunkt als Drawdown (12k ->
    4k = 66 %). Jetzt wird der Fluss am naechsten Messpunkt gebucht."""
    start = dt.datetime(2026, 1, 1)
    # XAUUSD fehlt die Bar 08:00 (Punkt 09:00); EURUSD liefert den
    # Rasterpunkt 09:00 trotzdem -> dort aktive Gold-Position ohne Kurs.
    bars = [b for i, b in enumerate(_flache_bars(start, 48)) if i != 8]
    euro = _flache_bars(start, 48, basis=1.1)
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=3), 1999.9, 2000.0,
               lots=1.0, pnl=2_000.0),
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=5),
               start + dt.timedelta(hours=40), 2000.0, 2000.0,
               lots=1.0, pnl=0.0),
        _trade("EURUSD", "buy", start + dt.timedelta(hours=5),
               start + dt.timedelta(hours=40), 1.1, 1.1,
               lots=1.0, pnl=0.0),
    ]
    auszahlung = SimpleNamespace(time=start + dt.timedelta(hours=8, minutes=30),
                                 amount=-8_000.0)
    parsed = SimpleNamespace(trades=trades, balances=[auszahlung], pendings=[])
    erg = er.rekonstruiere(parsed, kursdaten.FakeKursDaten({"XAUUSD": bars,
                                                            "EURUSD": euro}),
                           startkapital=10_000.0, gmt_offset_h=0)
    assert erg["status"] == "ok", erg
    assert erg["end_equity_usd"] == 4_000.0
    assert erg["equity_dd_pct"] == 0.0
