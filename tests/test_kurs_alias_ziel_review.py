"""Terminalalias nach zentraler Ersetzung und verlustfreier Case-Lookup."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from mqlkiscanner import config, kurs_cache, kursdaten


def _lieferant(verfuegbar, settings=None):
    kd = kursdaten.KursDaten(settings or {})
    kd.terminal_pfad = r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe"
    kd._aktiv = True
    kd._feed_identitaet = lambda: ("synthetisch", None)
    versuche = []

    def auswahl(symbol, sichtbar):
        versuche.append(symbol)
        return symbol in verfuegbar

    kd._mt5 = SimpleNamespace(symbol_select=auswahl)
    kd._hole_terminal_h1 = lambda symbol, von, bis: [
        dict(time=von, open=1., high=1., low=1., close=1.)]
    return kd, versuche


def test_zentrale_ersetzung_erreicht_terminalalias_und_bewahrt_herkunft():
    kd, versuche = _lieferant({"Ger40"})
    assert kd.hole_h1("DE30M", 1_700_002_800, 1_700_002_800)
    assert versuche == ["DE30M", "GER40", "Ger40"]
    assert kd.symbol_herkunft["DE30M"] == {
        "terminal": kd.terminal_pfad, "broker_symbol": "Ger40"}
    assert kd.suffix_annahmen["DE30M"] == "Ger40"


@pytest.mark.parametrize("verfuegbar,erwartet", [
    ({"DE30M", "GER40", "Ger40"}, ["DE30M"]),
    ({"GER40", "Ger40"}, ["DE30M", "GER40"]),
])
def test_exakte_namen_gehen_terminalalias_vor(verfuegbar, erwartet):
    kd, versuche = _lieferant(verfuegbar)
    assert kd.hole_h1("DE30M", 1_700_002_800, 1_700_002_800)
    assert versuche == erwartet


def test_aliaszyklus_wird_nicht_rekursiv_verfolgt_oder_doppelt_abgefragt():
    (config.DATA_DIR / "kurs_alias.json").write_text(
        json.dumps({"A": "B", "B": "A"}), encoding="utf8")
    kd, versuche = _lieferant(set(), {
        "symbol_aliases": {"B": {"activetrades003": "A"}}})
    assert kd.hole_h1("A", 1_700_002_800, 1_700_002_800) is None
    assert versuche == ["A", "B"]


def test_keine_blinde_normalisierung_des_exakten_ersatzziels():
    (config.DATA_DIR / "kurs_alias.json").write_text(
        json.dumps({"A": "EURUSDT"}), encoding="utf8")
    kd, versuche = _lieferant({"EURUSD"})
    assert kd.hole_h1("A", 1_700_002_800, 1_700_002_800) is None
    assert versuche == ["A", "EURUSDT"]


@pytest.mark.parametrize("ziel", ["GER40", "Ger40"])
def test_uebersicht_erhaelt_casezeilen_und_waehlt_exaktes_aliasziel(tmp_path, ziel):
    pfad = tmp_path / "bestand.db"
    with sqlite3.connect(pfad) as conn:
        conn.execute("CREATE TABLE h1_bars(feed TEXT,symbol TEXT,epoch INTEGER)")
        conn.executemany("INSERT INTO h1_bars VALUES(?,?,?)", [
            ("feed1", "GER40", 1_700_000_000),
            ("feed2", "Ger40", 1_700_003_600),
            ("feed2", "Ger40", 1_700_007_200)])
    alias = tmp_path / "kurs_alias.json"
    alias.write_text(json.dumps({"A": ziel}), encoding="utf8")
    rows = {r["Symbol"]: r for r in kurs_cache.uebersicht(
        pfad, [{"report": {"symbole_ohne_kurse": ["A"]}}], alias)}
    assert rows["GER40"]["Bars"] == 1
    assert rows["Ger40"]["Bars"] == 2
    assert rows["GER40"]["Feeds"] == rows["Ger40"]["Feeds"] == 1
    assert rows["A"]["Im Bestand als"] == ziel
    assert rows["A"]["Bars"] == rows[ziel]["Bars"]


@pytest.mark.parametrize("ziel,erwartet", [("GER40", "GER40"), ("Ger40", "Ger40"), ("ger40", None)])
def test_case_lookup_verliert_keine_variante_und_raet_nicht(ziel, erwartet):
    index = {"GER40": "GER40", "Ger40": "Ger40"}
    assert kurs_cache._kurs_match("A", index, {"A": ziel}) == erwartet


def test_case_insensitiver_lookup_bleibt_bei_eindeutigem_bestand_moeglich():
    assert kurs_cache._kurs_match("ger40", {"GER40": "Ger40"}) == "Ger40"


@pytest.mark.parametrize("symbol,erwartet", [("GER40M", "GER40"), ("Ger40M", "Ger40"), ("ger40M", None)])
def test_suffix_case_lookup_bevorzugt_exakte_basis(symbol, erwartet):
    assert kurs_cache._kurs_match(symbol, {"GER40": "GER40", "Ger40": "Ger40"}) == erwartet


@pytest.mark.parametrize("symbol,erwartet", [("GER40", "GER40+"), ("Ger40", "Ger40+"), ("ger40", None)])
def test_reverse_case_lookup_bevorzugt_exakte_basis(symbol, erwartet):
    assert kurs_cache._kurs_match(symbol, {"GER40+": "GER40+", "Ger40+": "Ger40+"}) == erwartet
