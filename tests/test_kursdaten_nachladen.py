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

import pytest

from mqlkiscanner import config, kursdaten

START = dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc)

VANTAGE_PFAD = r"C:\Forex\Mt5\Vantage\terminal64.exe"
TICKMILL_PFAD = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"


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


@pytest.mark.parametrize("erstes", [None, []])
def test_leerer_erstabruf_laesst_historie_nachladen(monkeypatch, erstes):
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    voll = [_bar(s0 + i * 3600) for i in range(200)]
    abrufe = iter([erstes, voll])
    anzahl = []

    def laden(*args):
        anzahl.append(1)
        return next(abrufe)

    kd = kursdaten.KursDaten({})
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(symbol_select=lambda *a: True,
                              TIMEFRAME_H1=1, copy_rates_range=laden)
    assert len(kd.hole_h1("EURUSD", s0, s0 + 200 * 3600)) == 200
    assert len(anzahl) == 2


def test_dauerhaft_leerer_abruf_hat_maximal_drei_wiederholungen(monkeypatch):
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    anzahl = []

    def laden(*args):
        anzahl.append(1)
        return None if len(anzahl) % 2 else []

    kd = kursdaten.KursDaten({})
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(symbol_select=lambda *a: True,
                              TIMEFRAME_H1=1, copy_rates_range=laden)
    assert kd.hole_h1("EURUSD", s0, s0 + 200 * 3600) is None
    assert len(anzahl) == 4  # Erstabruf + drei begrenzte Nachladeversuche


def test_teilhistorie_bleibt_bei_leerem_nachladen_erhalten(monkeypatch):
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    teil = [_bar(s0 + i * 3600) for i in range(40)]
    abrufe = iter([teil, None])
    kd = kursdaten.KursDaten({})
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(symbol_select=lambda *a: True,
                              TIMEFRAME_H1=1,
                              copy_rates_range=lambda *a: next(abrufe))
    assert len(kd.hole_h1("EURUSD", s0, s0 + 200 * 3600)) == 40


def test_cache_trennt_broker_und_stellt_herkunft_beim_rueckwechsel_wieder_her(monkeypatch):
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    kd = kursdaten.KursDaten({})
    kd._aktiv = True
    abrufe = []

    def laden(*args):
        abrufe.append(kd.terminal_pfad)
        bar = _bar(s0)
        bar["close"] = 1.1 if kd.terminal_pfad == TICKMILL_PFAD else 1.2
        return [bar]

    kd._mt5 = SimpleNamespace(symbol_select=lambda *a: True,
                              TIMEFRAME_H1=1, copy_rates_range=laden)
    kd.terminal_pfad = TICKMILL_PFAD
    erste = kd.hole_h1("EURUSD", s0, s0 + 3600)
    kd.terminal_pfad = VANTAGE_PFAD
    zweite = kd.hole_h1("EURUSD", s0, s0 + 3600)
    assert erste[0]["close"] == 1.1
    assert zweite[0]["close"] == 1.2
    assert kd.terminal_herkunft["EURUSD"] == VANTAGE_PFAD
    kd.terminal_pfad = TICKMILL_PFAD
    assert kd.hole_h1("EURUSD", s0, s0 + 3600) is erste
    assert kd.terminal_herkunft["EURUSD"] == TICKMILL_PFAD
    assert abrufe == [TICKMILL_PFAD, VANTAGE_PFAD]


# ── Vantage als dritte Kursdatenquelle (Nutzer-Wunsch 08.10.2026) ─────────
def test_vantage_ist_dritte_standard_kursdatenquelle():
    r"""C:\Forex\Mt5\Vantage gehört zu den Standard-Terminals — der Nutzer
    hat es eingerichtet; ohne gespeicherte Override-Liste muss der Default
    greifen (app_settings.json überschreibt nur vorhandene Schlüssel)."""
    termine = config.DEFAULT_SETTINGS["kursdaten_terminals"]
    assert any(t.endswith(r"Vantage\terminal64.exe") for t in termine)
    # Priorität: Tickmill zuerst (Referenzbroker), Vantage als letzter Fallback
    assert termine[0].endswith(r"TickmillLifeMql5\terminal64.exe")
    assert len([t for t in termine if "Vantage" in t]) == 1
    assert termine[-1].endswith(r"Vantage\terminal64.exe")


def test_vantage_symbol_ersetzungen_suffix_und_namen():
    """Vantage-Namen (MT5-Lesung 08.10.): Gold nur als XAUUSD+ (plain
    existiert nicht — Suffix-Falle), S&P SP500 (nicht US500/SPX500 — SPX
    ist dort die Spirax-AKTIE in GBX!), Nasdaq NAS100 (nicht USTEC),
    WTI USOUSD, Brent UKOUSD, DAX GER40. Aktien (AAPL, MSFT, …) sind
    plain und brauchen keine Ersetzung."""
    from mqlkiscanner.symbols import alias_fuer_symbol, normalize_symbol
    assert alias_fuer_symbol("XAUUSD", VANTAGE_PFAD) == "XAUUSD+"
    assert alias_fuer_symbol("US500", VANTAGE_PFAD) == "SP500"
    assert alias_fuer_symbol("USTEC", VANTAGE_PFAD) == "NAS100"
    assert alias_fuer_symbol("US100", VANTAGE_PFAD) == "NAS100"
    assert alias_fuer_symbol("USOIL", VANTAGE_PFAD) == "USOUSD"
    assert alias_fuer_symbol("XTIUSD", VANTAGE_PFAD) == "USOUSD"
    assert alias_fuer_symbol("BRENT", VANTAGE_PFAD) == "UKOUSD"
    assert alias_fuer_symbol("DE40", VANTAGE_PFAD) == "GER40"
    assert alias_fuer_symbol("AAPL", VANTAGE_PFAD) is None  # plain
    # XAUUSD+ bleibt kanonisch XAUUSD in allen Auswertungen
    assert normalize_symbol("XAUUSD+") == "XAUUSD"
    # Tickmill/ActiveTrades unverändert
    assert alias_fuer_symbol("XAUUSD", TICKMILL_PFAD) is None
    assert alias_fuer_symbol("US500", TICKMILL_PFAD) is None


@pytest.mark.parametrize("symbol", ["XAUUSD", "XAUAUD", "XAUEUR", "XAUJPY"])
def test_hole_h1_probiert_vantage_alias_nach_exakt_fehlschlag(monkeypatch, symbol):
    """Am Vantage-Terminal scheitert XAUUSD (plain existiert nicht); der
    Alias XAUUSD+ wird als Kandidat gewählt und liefert die Bars."""
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    gewaehlt = {}

    def select(kandidat, flag):
        if kandidat == symbol + "+":
            gewaehlt["symbol"] = kandidat
            return True
        return False

    mt5 = SimpleNamespace(
        symbol_select=select,
        copy_rates_range=lambda s, tf, von, bis: [_bar(s0)],
        TIMEFRAME_H1=1)
    kd = kursdaten.KursDaten({})  # leer -> Default-Einzelterminal
    kd.terminal_pfad = VANTAGE_PFAD
    kd._aktiv = True
    kd._mt5 = mt5
    bars = kd.hole_h1(symbol, s0, s0 + 3600)
    assert bars and bars[0]["time"] == s0
    assert gewaehlt["symbol"] == symbol + "+"
    assert kd.suffix_annahmen[symbol] == symbol + "+"


@pytest.mark.parametrize("symbol", ["XAUAUD", "XAUEUR", "XAUJPY"])
def test_goldkreuz_plus_alias_nur_fuer_vantage(symbol):
    from mqlkiscanner.symbols import alias_fuer_symbol
    assert alias_fuer_symbol(symbol, VANTAGE_PFAD) == symbol + "+"
    assert alias_fuer_symbol(symbol, TICKMILL_PFAD) is None
    assert alias_fuer_symbol(symbol, r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe") is None
    assert alias_fuer_symbol(symbol, r"C:\Forex\Mt5\AndererBroker\terminal64.exe") is None
    assert alias_fuer_symbol("EURUSD", VANTAGE_PFAD) == "EURUSD+"


@pytest.mark.parametrize("symbol,terminal_name", [
    ("GBPAUD", "GBPAUD+"), ("NZDCAD", "NZDCAD+"),
    ("NZDCHF", "NZDCHF+"), ("USDCHF", "USDCHF+"),
    ("DJ30FT", "DJ30ft"), ("NAS100FT", "NAS100ft"),
])
def test_vantage_belegte_forex_und_case_sensitive_futures(symbol, terminal_name):
    from mqlkiscanner.symbols import alias_fuer_symbol
    assert alias_fuer_symbol(symbol, VANTAGE_PFAD) == terminal_name
    selected = []
    def select(candidate, flag):
        selected.append(candidate)
        return candidate == terminal_name
    epoch = int(START.timestamp())
    kd = kursdaten.KursDaten({})
    kd.terminal_pfad = VANTAGE_PFAD
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(
        symbol_select=select, TIMEFRAME_H1=1,
        copy_rates_range=lambda s, tf, von, bis: [_bar(epoch)])
    assert kd.hole_h1(symbol, epoch, epoch + 3600)
    assert terminal_name in selected
    assert kd.suffix_annahmen[symbol] == terminal_name
    # Broker-spezifische FX-Suffixe dürfen andere Terminals nicht ändern.
    if not symbol.endswith("FT"):
        assert alias_fuer_symbol(symbol, TICKMILL_PFAD) is None
    assert alias_fuer_symbol("DJ30", VANTAGE_PFAD) is None
    assert alias_fuer_symbol("BTCUSD", VANTAGE_PFAD) is None
