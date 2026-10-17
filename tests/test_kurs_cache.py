# -*- coding: utf-8 -*-
"""Persistente Kursdaten ohne MetaTrader oder Zugriff auf Produktivdaten."""
from __future__ import annotations

import sqlite3

import pytest

from mqlkiscanner import config
from mqlkiscanner.kurs_cache import (
    AKTUALISIERUNG_SEKUNDEN, VERSUCH_PAUSE_SEKUNDEN, KursCache,
)

H = 3600
START = 1_760_832_000 // H * H
NOW = START + 100 * H + 900
FEED = "C:/MT5/Tickmill/terminal64.exe|Tickmill-Live"


def bar(i, close=1.125):
    return {"time": START + i * H, "open": 1.12, "high": 1.13,
            "low": 1.11, "close": close}


@pytest.fixture
def cache(tmp_path):
    return KursCache(tmp_path / "kurse" / "kursdaten.db")


def test_ueberlappende_und_enthaltene_zeitraeume_werden_wiederverwendet(cache):
    cache.speichere(FEED, "EURUSD", START, START + 5 * H,
                    [bar(i) for i in range(6)], now=NOW)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + H, START + 4 * H,
                                  now=NOW) == []
    assert cache.fehlende_bereiche(FEED, "EURUSD", START - 2 * H, START + 7 * H,
                                  now=NOW) == [
                                      (START - 2 * H, START - H),
                                      (START + 6 * H, START + 7 * H)]
    assert cache.lese(FEED, "EURUSD", START + H, START + 3 * H) == [
        bar(1), bar(2), bar(3)]


def test_partialhistorie_erklaert_keine_unbelegten_grenzen_oder_binnenluecken(cache):
    cache.speichere(FEED, "EURUSD", START, START + 7 * H,
                    [bar(2), bar(3), bar(5)], now=NOW)
    # Unbekannte Raender bleiben nur 60 Sekunden ruhig; Innenluecken einen Tag.
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + 7 * H,
                                  now=NOW + VERSUCH_PAUSE_SEKUNDEN) == [
                                      (START, START + H),
                                      (START + 6 * H, START + 7 * H)]
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + 7 * H,
                                  now=NOW + AKTUALISIERUNG_SEKUNDEN) == [
                                      (START, START + H),
                                      (START + 4 * H, START + 4 * H),
                                      (START + 6 * H, START + 7 * H)]
    assert cache.lese(FEED, "EURUSD", START, START + 7 * H) == [bar(2), bar(3), bar(5)]


def test_wochenendluecke_wird_nicht_als_belegte_historie_behandelt(cache):
    cache.speichere(FEED, "EURUSD", START, START + 72 * H,
                    [bar(0), bar(72)], now=NOW)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + 72 * H,
                                  now=NOW) == []  # Nur der Abrufversuch ist frisch.
    assert cache.lese(FEED, "EURUSD", START, START + 72 * H) == [bar(0), bar(72)]
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + 72 * H,
                                  now=NOW + AKTUALISIERUNG_SEKUNDEN) == [
                                      (START + H, START + 71 * H)]


@pytest.mark.parametrize("antwort", [None, [], [bar(0)]])
def test_leerer_oder_partieller_wochenend_retry_bleibt_tag_ruhig_raender_nur_minute(cache, antwort):
    cache.speichere(FEED, "EURUSD", START, START + 72 * H,
                    [bar(0), bar(72)], now=NOW)
    retry = NOW + AKTUALISIERUNG_SEKUNDEN
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + 72 * H,
                                  now=retry) == [(START + H, START + 71 * H)]
    cache.speichere(FEED, "EURUSD", START - 2 * H, START + 74 * H,
                    antwort, now=retry)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START - 2 * H, START + 74 * H,
                                  now=retry) == []
    # Auch ein leerer Retry verlaengert die Innenluecken-Pause auf 24 h;
    # die unbekannten Aussenraender bleiben bereits nach 60 s abrufbar.
    assert cache.fehlende_bereiche(FEED, "EURUSD", START - 2 * H, START + 74 * H,
                                  now=retry + 60) == [
                                      (START - 2 * H, START - H),
                                      (START + 73 * H, START + 74 * H)]
    assert cache.fehlende_bereiche(FEED, "EURUSD", START - 2 * H, START + 74 * H,
                                  now=retry + AKTUALISIERUNG_SEKUNDEN) == [
                                      (START - 2 * H, START - H),
                                      (START + H, START + 71 * H),
                                      (START + 73 * H, START + 74 * H)]
    assert cache.lese(FEED, "EURUSD", START - 2 * H, START + 74 * H,
                      now=retry + 60) == [bar(0), bar(72)]


@pytest.mark.parametrize("leer", [None, []])
def test_leerantwort_blockiert_nachladen_nicht_und_loescht_keinen_bestand(cache, leer):
    cache.speichere(FEED, "EURUSD", START, START + H, [bar(0)], now=NOW)
    cache.speichere(FEED, "EURUSD", START, START + H, leer, now=NOW)
    assert cache.lese(FEED, "EURUSD", START, START + H) == [bar(0)]
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + H,
                                  now=NOW) == []
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START + H,
                                  now=NOW + VERSUCH_PAUSE_SEKUNDEN) == [
                                      (START + H, START + H)]


def test_aktuelle_stunde_wird_erneut_abgerufen_und_abschluss_kann_korrigiert_werden(cache):
    cache.speichere(FEED, "EURUSD", START + 99 * H, START + 100 * H,
                    [bar(99), bar(100)], now=NOW)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 99 * H, START + 100 * H,
                                  now=NOW) == []
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 99 * H, START + 100 * H,
                                  now=NOW + VERSUCH_PAUSE_SEKUNDEN) == [
                                      (START + 100 * H, START + 100 * H)]
    # Die frueher offene Bar wird durch blossen Zeitablauf nicht final.
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 100 * H, START + 100 * H,
                                  now=NOW + H) == [(START + 100 * H, START + 100 * H)]
    cache.speichere(FEED, "EURUSD", START + 100 * H, START + 100 * H,
                    [bar(100, close=1.126)], now=NOW + H)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 99 * H, START + 100 * H,
                                  now=NOW + H) == []
    assert cache.lese(FEED, "EURUSD", START + 100 * H,
                      START + 100 * H) == [bar(100, close=1.126)]


def test_vorlaeufige_offene_bar_ist_nur_60_sekunden_lesbar(cache):
    epoch = START + 100 * H
    cache.speichere(FEED, "EURUSD", epoch, epoch, [bar(100)], now=NOW)
    assert cache.lese(FEED, "EURUSD", epoch, epoch, now=NOW) == [bar(100)]
    assert cache.lese(FEED, "EURUSD", epoch, epoch, now=NOW + 59) == [bar(100)]
    assert cache.lese(FEED, "EURUSD", epoch, epoch, now=NOW + 60) == []
    with sqlite3.connect(cache.pfad) as conn:
        assert conn.execute("SELECT COUNT(*) FROM h1_bars").fetchone()[0] == 1


def test_stundengrenze_entzieht_auch_frischer_vorlaeufiger_bar_die_messbasis(cache):
    kurz_vor_schluss = START + H - 20
    cache.speichere(FEED, "EURUSD", START, START, [bar(0)], now=kurz_vor_schluss)
    assert cache.lese(FEED, "EURUSD", START, START, now=START + H - 1) == [bar(0)]
    assert cache.lese(FEED, "EURUSD", START, START, now=START + H) == []


@pytest.mark.parametrize("leer", [None, []])
def test_nur_erfolgreicher_finaler_abruf_macht_vorlaeufige_bar_wieder_lesbar(cache, leer):
    cache.speichere(FEED, "EURUSD", START, START, [bar(0)], now=START + H - 10)
    cache.speichere(FEED, "EURUSD", START, START, leer, now=START + H + 1)
    assert cache.lese(FEED, "EURUSD", START, START, now=START + H + 1) == []
    assert cache.lese(FEED, "EURUSD", START, START, now=START + 2 * H) == []
    cache.speichere(FEED, "EURUSD", START, START, [bar(0, close=1.126)],
                    now=START + 2 * H)
    assert cache.lese(FEED, "EURUSD", START, START, now=START + 2 * H) == [
        bar(0, close=1.126)]
    assert cache.lese(FEED, "EURUSD", START, START, now=START + 2000 * H) == [
        bar(0, close=1.126)]


def test_abgeschlossene_bars_bleiben_dauerhaft_lesbar_und_muessen_nicht_neu_geladen_werden(cache):
    cache.speichere(FEED, "EURUSD", START, START, [bar(0)], now=NOW)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START,
                                  now=NOW + AKTUALISIERUNG_SEKUNDEN - 1) == []
    assert cache.fehlende_bereiche(FEED, "EURUSD", START, START,
                                  now=NOW + 365 * AKTUALISIERUNG_SEKUNDEN) == []
    assert cache.lese(FEED, "EURUSD", START, START) == [bar(0)]


def test_ueberlappende_versuchsspannen_verschmelzen_ohne_fiktive_bars(cache):
    cache.speichere(FEED, "EURUSD", START, START + 3 * H,
                    [bar(0), bar(3)], now=NOW)
    cache.speichere(FEED, "EURUSD", START + 2 * H, START + 5 * H,
                    [bar(2), bar(5)], now=NOW)
    erneut = KursCache(cache.pfad)
    assert erneut.fehlende_bereiche(FEED, "EURUSD", START, START + 5 * H,
                                    now=NOW + 60) == []
    assert erneut.lese(FEED, "EURUSD", START, START + 5 * H) == [
        bar(0), bar(2), bar(3), bar(5)]
    assert erneut.fehlende_bereiche(FEED, "EURUSD", START, START + 5 * H,
                                    now=NOW + AKTUALISIERUNG_SEKUNDEN) == [
                                        (START + H, START + H),
                                        (START + 4 * H, START + 4 * H)]


def test_ausgelassene_finale_bar_bleibt_trotz_neuer_innenstrecke_nachzuladen(cache):
    cache.speichere(FEED, "EURUSD", START + 99 * H, START + 100 * H,
                    [bar(99), bar(100)], now=NOW)
    # Zwei Stunden spaeter liefert der Server die frueher offene Bar nicht.
    spaeter = NOW + 2 * H
    cache.speichere(FEED, "EURUSD", START + 99 * H, START + 102 * H,
                    [bar(99), bar(101), bar(102)], now=spaeter)
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 99 * H, START + 102 * H,
                                  now=spaeter) == []
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 99 * H, START + 102 * H,
                                  now=spaeter + 60) == [
                                      (START + 100 * H, START + 100 * H),
                                      (START + 102 * H, START + 102 * H)]


def test_feed_server_und_exakte_brokersymbole_bleiben_getrennt(cache):
    keys = [(FEED, "EURUSD"), (FEED + "2", "EURUSD"),
            (FEED, "eurusd"), (FEED, "EURUSD+"),
            ("C:/MT5/Vantage/terminal64.exe|Vantage-Live", "EURUSD")]
    for i, (feed, symbol) in enumerate(keys):
        cache.speichere(feed, symbol, START, START, [bar(0, close=1 + i / 10)], now=NOW)
    for i, (feed, symbol) in enumerate(keys):
        assert cache.lese(feed, symbol, START, START) == [bar(0, close=1 + i / 10)]
    assert cache.lese(FEED.replace("Live", "Demo"), "EURUSD", START, START) == []


def test_wiederoeffnen_upsert_und_verbindung_wal(cache):
    cache.speichere(FEED, "EURUSD", START, START + H, [bar(1), bar(0)], now=NOW)
    erneut = KursCache(cache.pfad)
    erneut.speichere(FEED, "EURUSD", START, START, [bar(0, close=1.127)], now=NOW + 1)
    assert erneut.lese(FEED, "EURUSD", START, START + H) == [bar(0, close=1.127), bar(1)]
    with sqlite3.connect(cache.pfad) as conn:
        assert conn.execute("SELECT COUNT(*) FROM h1_bars").fetchone()[0] == 2
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_inklusive_grenzen_und_nicht_stundengenaue_anfrage(cache):
    cache.speichere(FEED, "EURUSD", START, START + 4 * H,
                    [bar(i) for i in range(5)], now=NOW)
    assert cache.lese(FEED, "EURUSD", START + 1, START + 3 * H - 1) == [bar(1), bar(2)]
    assert cache.fehlende_bereiche(FEED, "EURUSD", START + 1, START + 3 * H - 1,
                                  now=NOW) == []
    assert cache.fehlende_bereiche(FEED, "UNBEKANNT", START + 1, START + 3 * H - 1,
                                  now=NOW + AKTUALISIERUNG_SEKUNDEN) == [
                                      (START + H, START + 2 * H)]
    assert cache.fehlende_bereiche(FEED, "UNBEKANNT", START + 1, START + H - 1,
                                  now=NOW) == []


def test_keine_epoch_verschiebung_oder_uebernahme_ausserhalb_des_fensters(cache):
    original = dict(bar(1), time=START + H + 900)
    cache.speichere(FEED, "DJ30ft", START + H, START + 2 * H,
                    [bar(0), original, bar(3)], now=NOW)
    assert cache.lese(FEED, "DJ30ft", START, START + 3 * H) == [original]
    assert cache.fehlende_bereiche(FEED, "DJ30ft", START + H, START + 2 * H,
                                  now=NOW + AKTUALISIERUNG_SEKUNDEN) == [
                                      (START + H, START + 2 * H)]


def test_defaultpfad_verwendet_aktuelles_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "separate-daten")
    cache = KursCache()
    assert cache.pfad == tmp_path / "separate-daten" / "kursdaten.db"
    assert cache.pfad.is_file()


def test_fehlerhafte_bars_schreiben_keinen_halben_batch(cache):
    with pytest.raises(ValueError, match="OHLC"):
        cache.speichere(FEED, "EURUSD", START, START + H,
                        [bar(0), bar(1, close=float("nan"))], now=NOW)
    assert cache.lese(FEED, "EURUSD", START, START + H) == []
