"""Offline-Regressionen fuer Symbolnamen und geaenderte Aliasdateien."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import config, kurs_cache, kursdaten


@pytest.mark.parametrize("symbol", ["EURUSDT", "EURUSDXYZ", "US1000", "EURUSDXYZM"])
def test_anzeige_entfernt_keine_unbekannten_suffixe(symbol):
    assert kurs_cache._kurs_match(symbol, {"EURUSD": "EURUSD", "US100": "US100"}) is None


@pytest.mark.parametrize("symbol", ["EURUSDT", "EURUSDXYZ", "EURUSDXYZM"])
def test_reverse_match_entfernt_keine_unbekannten_suffixe(symbol):
    assert kurs_cache._kurs_match("EURUSD", {symbol: symbol}) is None


@pytest.mark.parametrize("suffix", ["M", "+", ".a", "-P", "PRO", "MICRO", "FT", "CASH", "-FUTURE", "M+"])
def test_bekannte_suffixe_in_beiden_richtungen(suffix):
    variant = "EURUSD" + suffix.upper()
    assert kurs_cache._kurs_match(variant, {"EURUSD": "EURUSD"}) == "EURUSD"
    assert kurs_cache._kurs_match("EURUSD", {variant: "EURUSD" + suffix}) == "EURUSD" + suffix


def _alias(daten):
    pfad = config.DATA_DIR / "kurs_alias.json"
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    return pfad


def _synthetischer_kurslieferant(verfuegbar):
    kd = kursdaten.KursDaten({})
    kd.terminal_pfad = r"C:\Forex\Mt5\Vantage\terminal64.exe"
    kd._aktiv = True
    kd._feed_identitaet = lambda: (kd.terminal_pfad, None)
    ausgewaehlt = []
    kd._mt5 = SimpleNamespace(symbol_select=lambda symbol, sichtbar:
                              ausgewaehlt.append(symbol) is None and symbol in verfuegbar)
    kd._hole_terminal_h1 = lambda symbol, von, bis: [
        {"time": von, "open": float(verfuegbar[symbol]),
         "high": float(verfuegbar[symbol]), "low": float(verfuegbar[symbol]),
         "close": float(verfuegbar[symbol])}]
    return kd, ausgewaehlt


def test_brokeralias_des_normalisierten_symbols_wird_verwendet():
    kd, gewaehlt = _synthetischer_kurslieferant({"AUDSGD+": 2})
    assert kd.hole_h1("AUDSGDM", 1_700_002_800, 1_700_002_800)[0]["close"] == 2
    assert gewaehlt == ["AUDSGDM", "AUDSGD", "AUDSGD+"]
    assert kd.suffix_annahmen["AUDSGDM"] == "AUDSGD+"


def test_exakter_brokername_bleibt_vorrangig():
    kd, gewaehlt = _synthetischer_kurslieferant({"AUDSGDM": 1, "AUDSGD+": 2})
    assert kd.hole_h1("AUDSGDM", 1_700_002_800, 1_700_002_800)[0]["close"] == 1
    assert gewaehlt == ["AUDSGDM"]


def test_json_ziel_schreibweise_bleibt_erhalten():
    pfad = _alias({"missing": "Ger40"})
    assert kurs_cache.ersetzungen()["MISSING"] == "Ger40"
    assert kurs_cache._lese_alias(pfad) == {"MISSING": "Ger40"}
    assert kurs_cache._kurs_match("MISSING", {"GER40": "Ger40"},
                                 kurs_cache.ersetzungen()) == "Ger40"
    kd, gewaehlt = _synthetischer_kurslieferant({"Ger40": 3})
    assert kd.hole_h1("MISSING", 1_700_002_800, 1_700_002_800)[0]["close"] == 3
    assert gewaehlt == ["MISSING", "Ger40"]


def test_aliascache_trennt_dateipfade_auch_bei_gleicher_mtime(tmp_path, monkeypatch):
    pfad = _alias({"X": "OLD"})
    assert kurs_cache.ersetzungen()["X"] == "OLD"
    anderes = tmp_path / "zweiter_ort"
    anderes.mkdir()
    neu = anderes / pfad.name
    neu.write_text('{"X": "NEW"}', encoding="utf-8")
    os.utime(neu, ns=(pfad.stat().st_atime_ns, pfad.stat().st_mtime_ns))
    monkeypatch.setattr(config, "DATA_DIR", anderes)
    assert kurs_cache.ersetzungen()["X"] == "NEW"


def test_nanosekunden_aenderung_wird_erkannt():
    pfad = _alias({"X": "OLD"})
    jetzt = 1_700_000_000_000_000_000
    os.utime(pfad, ns=(jetzt, jetzt))
    assert kurs_cache.ersetzungen()["X"] == "OLD"
    pfad.write_text('{"X": "NEW"}', encoding="utf-8")
    os.utime(pfad, ns=(jetzt + 100, jetzt + 100))
    assert kurs_cache.ersetzungen()["X"] == "NEW"


@pytest.mark.parametrize("inhalt", [None, "{kaputt", "[]"])
def test_defekte_oder_geloeschte_aliasdatei_entfernt_alte_overrides(inhalt):
    pfad = _alias({"X": "OLD"})
    assert kurs_cache.ersetzungen()["X"] == "OLD"
    if inhalt is None:
        pfad.unlink()
    else:
        pfad.write_text(inhalt, encoding="utf-8")
    assert "X" not in kurs_cache.ersetzungen()
    assert kurs_cache.ersetzungen()["BITCOIN"] == "BTCUSD"


def test_statfehler_bleibt_kontrollierter_fallback(monkeypatch):
    pfad = _alias({"X": "OLD"})
    assert kurs_cache.ersetzungen()["X"] == "OLD"
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == pfad:
            raise PermissionError("synthetische Sperre")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert "X" not in kurs_cache.ersetzungen()


def test_lesefehler_wird_bei_gleichem_dateistand_erneut_versucht(monkeypatch):
    pfad = _alias({"X": "NEW"})
    original = Path.read_text
    with monkeypatch.context() as patch:
        def lesen(path, *args, **kwargs):
            if path == pfad:
                raise PermissionError("synthetische Sperre")
            return original(path, *args, **kwargs)
        patch.setattr(Path, "read_text", lesen)
        assert "X" not in kurs_cache.ersetzungen()
    assert kurs_cache.ersetzungen()["X"] == "NEW"


def test_aliaswechsel_invalidiert_instanz_und_exaktes_ramfenster():
    _alias({"SWAP": "OLD"})
    kd, gewaehlt = _synthetischer_kurslieferant({"OLD": 1, "NEW": 2})
    assert kd.hole_h1("SWAP", 1_700_002_800, 1_700_002_800)[0]["close"] == 1
    _alias({"SWAP": "NEW"})
    assert kd.hole_h1("SWAP", 1_700_002_800, 1_700_002_800)[0]["close"] == 2
    assert gewaehlt == ["SWAP", "OLD", "SWAP", "NEW"]
    assert kd.suffix_annahmen["SWAP"] == "NEW"


def test_neuer_alias_ueberwindet_negativen_ramcache():
    kd, _ = _synthetischer_kurslieferant({"NEW": 2})
    assert kd.hole_h1("SWAP", 1_700_002_800, 1_700_002_800) is None
    _alias({"SWAP": "NEW"})
    assert kd.hole_h1("SWAP", 1_700_002_800, 1_700_002_800)[0]["close"] == 2


def test_aliaswechsel_erhaelt_herkunft_bereits_geladener_anderer_symbole():
    _alias({"A": "OLD", "B": "OTHER"})
    kd, _ = _synthetischer_kurslieferant({"OLD": 1, "NEW": 2, "OTHER": 3})
    epoch = 1_700_002_800
    assert kd.hole_h1("B", epoch, epoch)[0]["close"] == 3
    assert kd.hole_h1("A", epoch, epoch)[0]["close"] == 1
    herkunft_b = kd.terminal_herkunft["B"]
    _alias({"A": "NEW", "B": "OTHER"})
    assert kd.hole_h1("A", epoch, epoch)[0]["close"] == 2
    assert kd.suffix_annahmen["B"] == "OTHER"
    assert kd.terminal_herkunft["B"] == herkunft_b


def test_entfernte_herkunft_wird_erst_bei_fehlgeschlagenem_neuabruf_geloescht():
    _alias({"A": "OLD", "B": "OTHER"})
    kd, _ = _synthetischer_kurslieferant({"OLD": 1, "NEW": 2, "OTHER": 3})
    epoch = 1_700_002_800
    assert kd.hole_h1("B", epoch, epoch)[0]["close"] == 3
    _alias({"A": "NEW"})
    assert kd.hole_h1("A", epoch, epoch)[0]["close"] == 2
    assert kd.suffix_annahmen["B"] == "OTHER"
    assert kd.hole_h1("B", epoch, epoch) is None
    assert "B" not in kd.suffix_annahmen
    assert "B" not in kd.terminal_herkunft


def test_aliaswechsel_mischt_keine_persistierten_feeds(tmp_path):
    _alias({"SWAP": "OLD"})
    kd, _ = _synthetischer_kurslieferant({"OLD": 1, "NEW": 2})
    cache = kurs_cache.KursCache(tmp_path / "isoliert.db")
    kd._kurs_cache = cache
    feed = ["feed-A"]
    kd._feed_identitaet = lambda: (feed[0], feed[0])
    epoch = 1_700_002_800
    assert kd.hole_h1("SWAP", epoch, epoch)[0]["close"] == 1
    _alias({"SWAP": "NEW"})
    feed[0] = "feed-B"
    assert kd.hole_h1("SWAP", epoch, epoch)[0]["close"] == 2
    assert cache.lese("feed-A", "OLD", epoch, epoch)[0]["close"] == 1
    assert cache.lese("feed-A", "NEW", epoch, epoch) == []
    assert cache.lese("feed-B", "OLD", epoch, epoch) == []
