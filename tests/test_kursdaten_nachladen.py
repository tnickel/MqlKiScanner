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


def test_hole_h1_probiert_vantage_alias_nach_exakt_fehlschlag(monkeypatch):
    """Am Vantage-Terminal scheitert XAUUSD (plain existiert nicht); der
    Alias XAUUSD+ wird als Kandidat gewählt und liefert die Bars."""
    monkeypatch.setattr(kursdaten.time, "sleep", lambda s: None)
    s0 = int(START.timestamp())
    gewaehlt = {}

    def select(symbol, flag):
        if symbol == "XAUUSD+":
            gewaehlt["symbol"] = symbol
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
    bars = kd.hole_h1("XAUUSD", s0, s0 + 3600)
    assert bars and bars[0]["time"] == s0
    assert gewaehlt["symbol"] == "XAUUSD+"
    assert kd.suffix_annahmen["XAUUSD"] == "XAUUSD+"
