# -*- coding: utf-8 -*-
"""MetaTrader-Kursdaten — offizielles MetaTrader5-Paket, NUR LESEND (Phase C).

Eiserne Regel (doc/19 §7.1): Es sind AUSSCHLIESSLICH Lese-Aufrufe angebunden —
Verbindung, Status, Symbol aktivieren, Kurs/Tick-Reihen lesen, Verbindung
trennen. Order-Funktionen sind nicht verdrahtet und werden von einem
statischen Test bewacht (tests/test_agenten_phase_c.py). Das LLM erhält nur
fertig berechnete Kennzahlen, niemals Rohkurse.

Start-Politik (Nutzer-Entscheidung): initialize() würde ein ausgeschaltetes
Terminal STARTEN. Standardmäßig ist das verboten — läuft kein Terminal,
wartet der Marktbeobachter bis zum nächsten Intervall. Ob der Daemon das
Terminal selbst starten darf, ist der Schalter markt_start_erlauben.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Whitelist der angebundenen MT5-Aufrufe (doc/19 §7.1). Der statische Test
# prüft, dass das Modul keine anderen mt5.*-Aufrufe enthält.
ERLAUBTE_MT5_AUFRUFE = frozenset((
    "initialize", "shutdown", "terminal_info", "version", "last_error",
    "symbol_select", "symbol_info_tick", "copy_rates_from_pos",
    "copy_rates_range", "copy_ticks_from", "copy_ticks_range",
))

DEFAULT_TERMINAL = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"


def terminal_laueft(terminal_pfad: str) -> bool:
    """Läuft ein Terminal-Prozess dieses Pfads? (tasklist, Windows-only).

    Bewusst ohne Prozess-API-Hacks: initialize() startet sonst ein Terminal,
    das gar nicht laufen soll — deshalb wird der Zustand VOR jedem Verbindung
    sauber geprüft.
    """
    exe = Path(terminal_pfad).name or "terminal64.exe"
    try:
        ausgabe = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return exe.lower() in (ausgabe.stdout or "").lower()


def kurse_holen(symbole: list[str], settings: dict) -> dict:
    """Kurs-Kennzahlen je Symbol. Rückgabe {"ok", "grund"?, "kurse"?}.

    Ohne laufendes Terminal (und ohne Start-Freigabe) wird NICHT verbunden —
    das ist der Normalfall nachts/neu gestartet: warten, nicht starten.
    """
    if not symbole:
        return {"ok": False, "grund": "Keine Symbole in der Beobachtungsliste."}
    terminal_pfad = str(settings.get("markt_terminal_pfad") or DEFAULT_TERMINAL)
    start_erlauben = bool(settings.get("markt_start_erlauben", False))
    if not terminal_laueft(terminal_pfad) and not start_erlauben:
        return {"ok": False,
                "grund": ("MetaTrader-Terminal läuft nicht und Selbststart ist "
                          "nicht erlaubt (Standard-Politik, doc/19 §7.3) — "
                          "Marktkontext entfällt für diesen Lauf.")}
    lookback = int(settings.get("markt_lookback_tage", 30))

    import MetaTrader5 as mt5  # spät: nur wenn wirklich verbunden wird

    def _verbinden() -> bool:
        pfad = terminal_pfad if Path(terminal_pfad).exists() else None
        return bool(mt5.initialize(pfad) if pfad else mt5.initialize())

    if not _verbinden():
        fehler = str(mt5.last_error())
        mt5.shutdown()
        return {"ok": False, "grund": f"MT5-Verbindung fehlgeschlagen: {fehler}"}
    try:
        info = mt5.terminal_info()
        kurse: dict[str, dict] = {}
        fehler_symbole: list[str] = []
        for symbol in symbole:
            if not mt5.symbol_select(symbol, True):
                fehler_symbole.append(symbol)
                continue
            h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0,
                                         lookback * 24)
            d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, lookback)
            if h1 is None or d1 is None or len(d1) < 2:
                fehler_symbole.append(symbol)
                continue
            kurse[symbol] = kennzahlen_aus_rates(
                [_bar(b) for b in h1], [_bar(b) for b in d1])
        ergebnis = {"ok": True, "terminal": (info.name if info else "unbekannt"),
                    "kurse": kurse}
        if fehler_symbole:
            ergebnis["symbole_ohne_daten"] = fehler_symbole
        return ergebnis
    finally:
        mt5.shutdown()


def _bar(rate) -> dict:
    """MT5-Rate-Zeile (numpy-struct) → schlichtes Dict (serialisierbar)."""
    return {"time": int(rate["time"]), "open": float(rate["open"]),
            "high": float(rate["high"]), "low": float(rate["low"]),
            "close": float(rate["close"])}


def verbindung_testen(settings: dict) -> dict:
    """Attach-Test für den Admin-Bereich: liest EINE Bar und trennt wieder."""
    terminal_pfad = str(settings.get("markt_terminal_pfad") or DEFAULT_TERMINAL)
    if not terminal_laueft(terminal_pfad):
        return {"ok": False,
                "grund": ("Terminal läuft nicht. Standard-Politik: der Scanner "
                          "startet es nicht selbst — Terminal öffnen und erneut "
                          "testen.")}
    import MetaTrader5 as mt5
    pfad = terminal_pfad if Path(terminal_pfad).exists() else None
    if not bool(mt5.initialize(pfad) if pfad else mt5.initialize()):
        fehler = str(mt5.last_error())
        mt5.shutdown()
        return {"ok": False, "grund": f"Verbindung fehlgeschlagen: {fehler}"}
    try:
        info = mt5.terminal_info()
        mt5.symbol_select("XAUUSD", True)
        bars = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 2)
        if bars is None or len(bars) == 0:
            return {"ok": False, "grund": "Verbunden, aber XAUUSD liefert "
                                          "keine Kursdaten (Symbol beim Broker?)"}
        return {"ok": True,
                "grund": f"Verbunden mit {info.name if info else 'Terminal'} — "
                         f"XAUUSD-H1-Close {float(bars[-1]['close']):.2f}"}
    finally:
        mt5.shutdown()


# ── Kennzahlen (reiner Code — das LLM zitiert sie nur) ─────────────

def kennzahlen_aus_rates(h1: list[dict], d1: list[dict]) -> dict:
    """Maschinelle Kurs-Kennzahlen aus H1- und D1-Bars.

    Bewegung (heute/7 T/30 T), Distanz zu 30-Tage-Hoch/-Tief, ATR(14) auf
    H1, aktueller Tagesrange und Trendlage (Close vs. 10-Tage-Schnitt).
    """
    closes = [b["close"] for b in d1]
    letzter = closes[-1]

    def _pct_vor(n: int) -> float | None:
        if len(closes) <= n:
            return None
        basis = closes[-1 - n]
        return round((letzter / basis - 1) * 100, 2) if basis else None

    hoch, tief = max(closes), min(closes)
    sma10 = sum(closes[-10:]) / min(10, len(closes))
    atr = _atr14(h1)
    letzte_d1 = d1[-1]
    return {
        "close": round(letzter, 2),
        "veraenderung_pct": {"heute": _pct_vor(1), "7t": _pct_vor(7),
                             "30t": _pct_vor(30)},
        "distanz_30t_hoch_pct": round((letzter / hoch - 1) * 100, 2) if hoch else None,
        "distanz_30t_tief_pct": round((letzter / tief - 1) * 100, 2) if tief else None,
        "tagesrange_pct": (round((letzte_d1["high"] - letzte_d1["low"])
                                 / letzte_d1["close"] * 100, 2)
                           if letzte_d1["close"] else None),
        "atr14_h1": round(atr, 2) if atr is not None else None,
        "trend_close_vs_sma10_pct": round((letzter / sma10 - 1) * 100, 2) if sma10 else None,
    }


def _atr14(h1: list[dict]) -> float | None:
    """Durchschnittliche True Range der letzten 14 abgeschlossenen H1-Bars."""
    if len(h1) < 15:
        return None
    true_ranges = []
    for vorher, aktuell in zip(h1[-15:-1], h1[-14:]):
        pc = vorher["close"]
        true_ranges.append(max(aktuell["high"] - aktuell["low"],
                               abs(aktuell["high"] - pc),
                               abs(aktuell["low"] - pc)))
    return sum(true_ranges) / len(true_ranges)
