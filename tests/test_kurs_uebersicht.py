# -*- coding: utf-8 -*-
"""Kurs-Übersicht für den Einstellungen-Tab „Kursdaten“ (Nutzer 28.10.2026).

Anforderung: ALLE bekannten Symbole in EINER Tabelle — auch solche, zu
denen Studien nur „ohne Kurse/Kontrakt“ meldeten, damit man sieht, was
im MetaTrader-Kursbezug noch fehlt.
"""
from __future__ import annotations

import sqlite3

from mqlkiscanner import kurs_cache

_SCHEMA = ("CREATE TABLE h1_bars (feed TEXT, symbol TEXT, zeitrahmen TEXT,"
           " epoch INTEGER, open REAL, high REAL, low REAL, close REAL,"
           " geladen_am TEXT, abgeschlossen INTEGER)")


def _cache_mit_eurusd(tmp_path) -> sqlite3.Connection:
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        conn.executemany("INSERT INTO h1_bars VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("feedA", "EURUSD", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
            ("feedA", "EURUSD", "H1", 1_700_003_600, 1, 1, 1, 1, "x", 1),
            ("feedB", "EURUSD", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
        ])
    return pfad


def test_uebersicht_zaehlt_bars_und_feeds_je_symbol(tmp_path):
    zeilen = kurs_cache.uebersicht(cache_pfad=_cache_mit_eurusd(tmp_path),
                                   studien=[])
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z["Symbol"] == "EURUSD"
    assert z["Bars"] == 3 and z["Feeds"] == 2
    assert z["Status"] == "Kurse vorhanden"
    assert z["Erster Kurs"] is not None and z["Letzter Kurs"] is not None


def test_studien_symbole_ohne_kurse_bleiben_sichtbar(tmp_path):
    pfad = _cache_mit_eurusd(tmp_path)
    studien = [{"report": {"symbole_mit_kursen": ["EURUSD", "XAUUSD"],
                           "symbole_ohne_kurse": ["BITCOIN", "UKOUSD"],
                           "symbole_ohne_kontrakt": ["DE30M", "BITCOIN"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien)
    zeile = {z["Symbol"]: z for z in zeilen}
    assert set(zeile) == {"EURUSD", "XAUUSD", "BITCOIN", "UKOUSD", "DE30M"}
    assert zeile["BITCOIN"]["Bars"] == 0
    assert zeile["BITCOIN"]["Studien ohne Kurse"] == 1  # eine Studie zählt einmal
    assert zeile["XAUUSD"]["Bars"] == 0
    assert zeile["XAUUSD"]["Status"] == "keine Kurse"  # „mit Kursen“, aber nie gespeichert
    # kursose zuerst, dann alphabetisch — EURUSD (mit Bars) steht zuletzt
    assert all(z["Bars"] == 0 for z in zeilen[:4])
    assert zeilen[-1]["Symbol"] == "EURUSD"


def test_ohne_angabe_liefert_studien_aus_der_db(tmp_path, monkeypatch):
    from mqlkiscanner import db as db_mod
    monkeypatch.setattr(db_mod, "list_equity_studien", lambda **kw: {
        ("zulu", 1): {"report": {"symbole_ohne_kurse": ["FOO"]}}})
    zeilen = kurs_cache.uebersicht(cache_pfad=tmp_path / "fehlt.db")
    assert [z["Symbol"] for z in zeilen] == ["FOO"]
    assert zeilen[0]["Studien ohne Kurse"] == 1


def test_suffix_varianten_werden_auf_bestand_gematcht(tmp_path):
    """Nutzer 28.10.: GBPUSDM ist GBPUSD mit Suffix — die Tabelle soll den
    vorhandenen Bestand zeigen (nur Anzeige, keine Umbenennung)."""
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        conn.executemany("INSERT INTO h1_bars VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("feedA", "GBPUSD", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
            ("feedA", "JPN225", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
            ("feedA", "US500", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
        ])
    studien = [{"report": {"symbole_ohne_kurse": [
        "GBPUSDM", "JPN225FT", "US500-FUTURE", "NZDUSD+", "US100"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien)
    zeile = {z["Symbol"]: z for z in zeilen}
    assert zeile["GBPUSDM"]["Im Bestand als"] == "GBPUSD"
    assert zeile["JPN225FT"]["Im Bestand als"] == "JPN225"
    assert zeile["US500-FUTURE"]["Im Bestand als"] == "US500"
    assert zeile["NZDUSD+"]["Im Bestand als"] == ""   # NZDUSD hat keine Bars
    assert zeile["US100"]["Im Bestand als"] == ""     # kein Namens-Match
    # Sortierung: echte Lücken (ohne Match) zuerst, dann Match-Fälle, dann Bestand
    reihenfolge = [z["Symbol"] for z in zeilen]
    assert reihenfolge.index("US100") < reihenfolge.index("GBPUSDM") < \
        reihenfolge.index("GBPUSD")


def test_ersetzungstabelle_matcht_umbenennungen_in_bestand(tmp_path):
    """Nutzer 28.10.: Ersetzungstabelle — BITCOIN ≙ BTCUSD usw. Ziel ohne
    Bars bleibt eine echte Lücke (kein Schein-Match)."""
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        for symbol in ("BTCUSD", "USTEC", "USOUSD"):
            conn.execute("INSERT INTO h1_bars VALUES "
                         "('f',?,'H1',1,1,1,1,1,'x',1)", (symbol,))
    studien = [{"report": {"symbole_ohne_kurse": ["BITCOIN", "US100", "WTI"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien)
    zeile = {z["Symbol"]: z for z in zeilen}
    assert zeile["BITCOIN"]["Im Bestand als"] == "BTCUSD"
    assert zeile["US100"]["Im Bestand als"] == "USTEC"
    assert zeile["WTI"]["Im Bestand als"] == "USOUSD"
    # Ziel ohne Bars bleibt echte Lücke (kein Schein-Match)


def test_alias_ohne_bestand_bleibt_luecke(tmp_path):
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        conn.execute("INSERT INTO h1_bars VALUES "
                     "('f','BTCUSD','H1',1,1,1,1,1,'x',1)")
    studien = [{"report": {"symbole_ohne_kurse": ["US100"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien)
    assert zeilen[0]["Im Bestand als"] == ""  # USTEC fehlt im Bestand


def test_json_ueberschreibt_ersetzungstabelle(tmp_path):
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        conn.execute("INSERT INTO h1_bars VALUES "
                     "('f','EURUSD','H1',1,1,1,1,1,'x',1)")
    alias = tmp_path / "kurs_alias.json"
    alias.write_text('{"EURUSDK": "EURUSD"}', encoding="utf-8")
    studien = [{"report": {"symbole_ohne_kurse": ["EURUSDK"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien,
                                   alias_pfad=alias)
    assert zeilen[0]["Im Bestand als"] == "EURUSD"


def test_reverse_match_bestand_traegt_suffix_und_keine_nones(tmp_path):
    """Nutzer 28.10., zweiter Nachschub: XAUAUD hat keine Bars, XAUAUD+
    schon — die Basis bekommt den Bestand per Reverse-Match. Und: Zeilen
    zeigen nie den Text „None" (Streamlit rendert None in Textspalten)."""
    pfad = tmp_path / "kursdaten.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute(_SCHEMA)
        conn.executemany("INSERT INTO h1_bars VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("f", "XAUAUD+", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
            ("f", "AUDNZD", "H1", 1_700_000_000, 1, 1, 1, 1, "x", 1),
        ])
    studien = [{"report": {"symbole_ohne_kurse": ["XAUAUD"]}}]
    zeilen = kurs_cache.uebersicht(cache_pfad=pfad, studien=studien)
    zeile = {z["Symbol"]: z for z in zeilen}
    assert zeile["XAUAUD"]["Im Bestand als"] == "XAUAUD+"
    # Zeile MIT Bars: Spalte bleibt leer statt None
    assert zeile["AUDNZD"]["Im Bestand als"] == ""
    assert zeile["AUDNZD"]["Status"] == "Kurse vorhanden"


def test_zentrale_ersetzung_treibt_die_kursberechnung(tmp_path, monkeypatch):
    """Nutzer 28.10.: Die Ersetzungstabelle ist ZENTRAL — KursDaten.hole_h1
    (der Weg aller Drawdown-Berechnungen) löst BITCOIN über dieselbe Tabelle
    zu BTCUSD auf, genau wie die Übersichtstabelle sie anzeigt."""
    from types import SimpleNamespace

    from mqlkiscanner import kursdaten

    gewaehlt = []
    bar = {"time": 1_770_001_200, "open": 1., "high": 1., "low": 1., "close": 1.}

    def select(candidate, visible):
        gewaehlt.append(candidate)
        return candidate == "BTCUSD"  # Broker kennt BITCOIN nicht, nur BTCUSD

    kd = kursdaten.KursDaten({})
    kd.terminal_pfad = r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe"
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(symbol_select=select, TIMEFRAME_H1=1,
                              copy_rates_range=lambda *args: [bar])
    ergebnis = kd.hole_h1("BITCOIN", bar["time"], bar["time"] + 3600)
    assert ergebnis == [bar]
    assert "BTCUSD" in gewaehlt            # über die Ersetzungstabelle erreicht
    assert kd.suffix_annahmen["BITCOIN"] == "BTCUSD"  # transparent protokolliert
