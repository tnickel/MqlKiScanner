# -*- coding: utf-8 -*-
"""MetaTrader-Kursdaten — offizielles MetaTrader5-Paket, NUR LESEND (Phase C).

Eiserne Regel (doc/19 §7.1): Es sind AUSSCHLIESSLICH Lese-Aufrufe angebunden —
Verbindung, Status, Symbol aktivieren, Kurs/Tick-Reihen lesen, Verbindung
trennen. Order-Funktionen sind nicht verdrahtet und werden von einem
statischen Test bewacht (tests/test_agenten_phase_c.py). Das LLM erhält nur
fertig berechnete Kennzahlen, niemals Rohkurse.

Start-Politik (Nutzer-Entscheidung 22.09.2026): Standardmäßig startet der
Scanner das Terminal NICHT selbst. Mit dem Schalter markt_start_erlauben
darf er das Terminal mit /portable starten. Auch beim Verbinden mit einer
laufenden Instanz muss deren portabler Datenpfad belegt sein. Start und
Prüfung verwenden dieselbe KursDaten-Logik wie die Scan-Historien. Das
Terminal des konfigurierten Pfads
gehört dem Scanner — es wird nach jedem Lauf beendet (terminal_beenden),
auch wenn es schon vor dem Lauf lief.
"""
from __future__ import annotations

import subprocess
import logging
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Whitelist der angebundenen MT5-Aufrufe (doc/19 §7.1). Der statische Test
# prüft, dass das Modul keine anderen mt5.*-Aufrufe enthält.
ERLAUBTE_MT5_AUFRUFE = frozenset((
    "initialize", "shutdown", "terminal_info", "version", "last_error",
    "symbol_select", "symbol_info_tick", "copy_rates_from_pos",
    "copy_rates_range", "copy_ticks_from", "copy_ticks_range",
))

DEFAULT_TERMINAL = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"


def broker_symbol(symbol: str, settings: dict) -> str:
    """Kanonisches Symbol (XAUUSD) → Symbolname am EIGENEN Terminal.

    Manche Broker (z. B. Vantage je Kontoart) hängen einen Postfix an
    (XAUUSD.a) — markt_symbol_suffix wird beim Abfragen angehängt; intern
    und in allen Auswertungen bleibt der kanonische Name."""
    suffix = str(settings.get("markt_symbol_suffix") or "").strip()
    return symbol + suffix


class TerminalProzessAbfrageFehler(RuntimeError):
    """Unbekannter Prozesszustand darf nie als bestätigtes Prozessende gelten."""


def _terminalpfad(terminal_pfad: str) -> str:
    try:
        if not isinstance(terminal_pfad, str) or not terminal_pfad.strip():
            raise ValueError("Terminalpfad fehlt")
        pfad = Path(terminal_pfad).resolve()
        if pfad.name.casefold() != "terminal64.exe":
            raise ValueError("Terminalpfad bezeichnet keine terminal64.exe")
        return str(pfad).casefold()
    except (OSError, ValueError, RuntimeError) as exc:
        raise TerminalProzessAbfrageFehler(f"Terminalpfad nicht belegbar: {exc}") from exc


def _powershell_prozesse(ziel: str, abfrage: str, label: str, timeout: int,
                        *, allow_exited=False) -> list[tuple[int, str]]:
    """A successful complete path inventory is distinct from a query failure."""
    try:
        ausgabe = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n" + abfrage],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="strict",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise TerminalProzessAbfrageFehler(f"{label}-Terminalabfrage fehlgeschlagen: {exc}") from exc
    if ausgabe.returncode != 0 or (ausgabe.stderr or "").strip():
        raise TerminalProzessAbfrageFehler(
            f"{label}-Terminalabfrage fehlgeschlagen (Exit {ausgabe.returncode}): {(ausgabe.stderr or '')[:300]}")
    roh = (ausgabe.stdout or "").strip()
    if not roh:
        return []
    import json as _json
    try:
        daten = _json.loads(roh)
    except (ValueError, TypeError) as exc:
        raise TerminalProzessAbfrageFehler(f"{label}-Terminalabfrage liefert kein gültiges JSON") from exc
    if daten is None:
        return []
    if isinstance(daten, dict):  # ConvertTo-Json liefert ein Objekt bei EINEM Prozess
        daten = [daten]
    if not isinstance(daten, list):
        raise TerminalProzessAbfrageFehler(f"{label}-Terminalabfrage liefert kein gültiges Prozessschema")
    ergebnis = []
    for eintrag in daten:
        try:
            pid = eintrag["ProcessId"]
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                raise ValueError("PID nicht belegt")
            raw_path = eintrag["ExecutablePath"]
            # A graceful close can invalidate Path after the name inventory.
            # Only the same native Process object's explicit post-read exit
            # receipt proves disappearance. Null/denied/unknown alone do not.
            if (allow_exited and raw_path in (None, "")
                    and eintrag.get("HasExited") is True):
                continue
            pfad = _terminalpfad(raw_path)
            if pfad == ziel:
                ergebnis.append((pid, pfad))
        except (KeyError, ValueError, TypeError) as exc:
            raise TerminalProzessAbfrageFehler(f"{label}-Terminalabfrage enthält einen unbelegten Prozess") from exc
    return sorted(ergebnis)


def _terminal_prozesse_cim(ziel: str) -> list[tuple[int, str]]:
    """Legacy fallback without psutil; never swallow WMI/CIM timeouts."""
    return _powershell_prozesse(ziel,
        "(Get-CimInstance Win32_Process -Filter \"Name='terminal64.exe'\" -ErrorAction Stop "
        "| Select-Object ProcessId, ExecutablePath | ConvertTo-Json -Compress)", "CIM", 20)


def _terminal_prozesse_native(ziel: str) -> list[tuple[int, str]]:
    """Independent .NET process-name inventory when psutil cannot read a name.

    Some Windows security processes have an empty psutil name. They must not
    be silently skipped or force a broken CIM query; Get-Process supplies an
    independent complete name inventory and reads paths only for terminals.
    """
    return _powershell_prozesse(ziel,
        "(Get-Process -ErrorAction Stop | Where-Object { $_.ProcessName -ieq 'terminal64' } "
        "| ForEach-Object { $prozess = $_; $exePfad = $prozess.Path; "
        "$beendet = $prozess.HasExited; "
        "[PSCustomObject]@{ProcessId=$prozess.Id;ExecutablePath=$exePfad;HasExited=$beendet} } "
        "| ConvertTo-Json -Compress)", "Get-Process", 5, allow_exited=True)


def _terminal_prozesse(terminal_pfad: str) -> list[tuple[int, str]]:
    """(PID, canonical path) for this exact terminal; unknown state raises.

    Read names first: querying every protected Windows process's executable
    is both unnecessary and prone to access errors. Only terminal64.exe needs
    a path check. A vanished process is harmless; an unreadable one is not
    proof that the configured terminal has stopped.
    """
    ziel = _terminalpfad(terminal_pfad)
    try:
        import psutil
    except ImportError:
        return _terminal_prozesse_cim(ziel)
    ergebnis = []
    try:
        for prozess in psutil.process_iter():
            try:
                name = prozess.name()
                if not isinstance(name, str) or not name:
                    raise TerminalProzessAbfrageFehler("Prozessname nicht lesbar")
                if name.casefold() != "terminal64.exe":
                    continue
                pfad = _terminalpfad(prozess.exe())
                if pfad == ziel:
                    pid = prozess.pid
                    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                        raise TerminalProzessAbfrageFehler("Terminal-PID nicht belegt")
                    ergebnis.append((pid, pfad))
            except psutil.NoSuchProcess:
                continue  # Process ended during the name/path query.
    except Exception as exc:
        try:
            return _terminal_prozesse_native(ziel)
        except TerminalProzessAbfrageFehler as fallback_error:
            raise TerminalProzessAbfrageFehler(
                f"Terminal-Prozessabfrage nicht vollständig möglich: {type(exc).__name__}: {exc}; "
                f"unabhängige Namensinventur: {fallback_error}") from fallback_error
    return sorted(ergebnis)


def terminal_laueft(terminal_pfad: str) -> bool:
    """Läuft ein Terminal-Prozess genau DIESES Pfads? (pfadgenau, Windows).

    Nur der Prozessname reichte nicht: Ein anderes MT5-Terminal (andere
    Installation) würde sonst den Selbststart blockieren und einen Attach
    vortäuschen. Eine gescheiterte Abfrage wirft TerminalProzessAbfrageFehler;
    sie belegt weder Abwesenheit noch einen zulässigen neuen Selbststart.
    """
    return bool(_terminal_prozesse(terminal_pfad))


def terminal_beenden(terminal_pfad: str) -> bool:
    """Beendet das Terminal dieses Pfads — sanft, dann hart.

    Nutzer-Regel (22.09.2026): Das Terminal des konfigurierten Pfads gehört
    dem Scanner. Es wird nach jedem Lauf beendet — auch wenn es schon vor
    dem Lauf lief (shutdown() allein erfasst nur selbst gestartete).
    """
    def _taskkill(hart: bool) -> None:
        for pid, _pfad in _terminal_prozesse(terminal_pfad):
            befehl = ["taskkill", "/PID", str(pid)] + (["/F"] if hart else [])
            try:
                subprocess.run(
                    befehl, capture_output=True, timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                pass

    try:
        if not _terminal_prozesse(terminal_pfad):
            return True
        _taskkill(hart=False)          # WM_CLOSE — Terminal darf Logfiles schreiben
        if _terminal_prozesse(terminal_pfad):
            import time as _time
            _time.sleep(4)             # dem Terminal Zeit zum sauberen Beenden
            _taskkill(hart=True)       # nur erneut pfadgenau bestätigte PIDs
        return not _terminal_prozesse(terminal_pfad)
    except TerminalProzessAbfrageFehler as exc:
        _LOG.warning("Terminal-Cleanup nicht bestätigt (%s): %s", terminal_pfad, exc)
        return False


def kurse_holen(symbole: list[str], settings: dict) -> dict:
    """Kurs-Kennzahlen je Symbol. Rückgabe {"ok", "grund"?, "kurse"?}.

    Ohne laufendes Terminal (und ohne Start-Freigabe) wird NICHT verbunden —
    das ist der Normalfall nachts/neu gestartet: warten, nicht starten. Mit
    Start-Freigabe: Terminal PORTABEL starten, Kurse holen, am Lauf-Ende
    beenden (terminal_beendet im Ergebnis; selbststart kennzeichnet, ob der
    Scanner es gestartet hat oder vorgefunden hat).
    """
    if not symbole:
        return {"ok": False, "grund": "Keine Symbole in der Beobachtungsliste."}
    terminal_pfad = str(settings.get("markt_terminal_pfad") or DEFAULT_TERMINAL)
    start_erlauben = bool(settings.get("markt_start_erlauben", False))
    lief_schon = terminal_laueft(terminal_pfad)
    if not lief_schon and not start_erlauben:
        return {"ok": False,
                "grund": ("MetaTrader-Terminal läuft nicht und Selbststart ist "
                          "nicht erlaubt (Standard-Politik, doc/19 §7.3) — "
                          "Marktkontext entfällt für diesen Lauf.")}
    selbststart = not lief_schon
    lookback = int(settings.get("markt_lookback_tage", 30))

    # Lokaler Import: kursdaten nutzt die pfadgenauen Prozess-Helfer aus
    # diesem Modul. Ein Import auf Modulebene wäre daher zirkulär.
    from ..kursdaten import KursDaten
    anbieter = KursDaten({**settings, "kursdaten_terminals": [terminal_pfad]})
    ergebnis: dict | None = None
    try:
        verbunden, grund = anbieter.starten()
        if not verbunden:
            return {"ok": False, "grund": f"MT5-Verbindung fehlgeschlagen: {grund}"}
        selbststart = getattr(anbieter, "_selbststart", selbststart)
        import MetaTrader5 as mt5  # erst nach belegter portabler Verbindung
        info = mt5.terminal_info()
        kurse: dict[str, dict] = {}
        fehler_symbole: list[str] = []
        for symbol in symbole:
            am_broker = broker_symbol(symbol, settings)
            if not mt5.symbol_select(am_broker, True):
                fehler_symbole.append(symbol)
                continue
            h1 = mt5.copy_rates_from_pos(am_broker, mt5.TIMEFRAME_H1, 0,
                                         lookback * 24)
            # +1: die 30-Tage-Veränderung braucht 31 Closes (heute + 30).
            d1 = mt5.copy_rates_from_pos(am_broker, mt5.TIMEFRAME_D1, 0,
                                         lookback + 1)
            if h1 is None or d1 is None or len(d1) < 2:
                fehler_symbole.append(symbol)
                continue
            kurse[symbol] = kennzahlen_aus_rates(
                [_bar(b) for b in h1], [_bar(b) for b in d1])
        ergebnis = {"ok": True, "terminal": (info.name if info else "unbekannt"),
                    "selbststart": selbststart,
                    "kurse": kurse}
        if fehler_symbole:
            ergebnis["symbole_ohne_daten"] = fehler_symbole
        return ergebnis
    finally:
        anbieter.beenden()
        if ergebnis is not None:
            ergebnis["terminal_beendet"] = not terminal_laueft(terminal_pfad)


def _bar(rate) -> dict:
    """MT5-Rate-Zeile (numpy-struct) → schlichtes Dict (serialisierbar)."""
    return {"time": int(rate["time"]), "open": float(rate["open"]),
            "high": float(rate["high"]), "low": float(rate["low"]),
            "close": float(rate["close"])}


def verbindung_testen(settings: dict) -> dict:
    """Attach-Test für den Admin-Bereich: liest EINE Bar und trennt wieder.

    Mit Start-Freigabe wird ein nicht laufendes Terminal portabel gestartet.
    Das Terminal dieses Pfads wird nach dem Test grundsätzlich beendet.
    Das globale Scan-/Studien-Lock bleibt bis nach dem Terminal-Cleanup
    gehalten; bei einem aktiven Lauf wird kein Terminal angefasst.
    """
    from .. import config
    from . import lock

    try:
        with lock.lauf_lock(config.DATA_DIR):
            return _verbindung_testen_exklusiv(settings)
    except lock.LockBesetzt:
        return {"ok": False,
                "grund": ("Verbindungstest übersprungen: Ein anderer Lauf ist "
                          "aktiv (Scan, Studie oder Marktdaten). Nach dessen "
                          "Ende erneut testen.")}


def _verbindung_testen_exklusiv(settings: dict) -> dict:
    """Terminal-Lebensdauer innerhalb des vom Aufrufer gehaltenen Lauf-Locks."""
    terminal_pfad = str(settings.get("markt_terminal_pfad") or DEFAULT_TERMINAL)
    start_erlauben = bool(settings.get("markt_start_erlauben", False))
    lief_schon = terminal_laueft(terminal_pfad)
    if not lief_schon and not start_erlauben:
        return {"ok": False,
                "grund": ("Terminal läuft nicht. Standard-Politik: der Scanner "
                          "startet es nicht selbst — Terminal öffnen und erneut "
                          "testen.")}
    selbststart = not lief_schon
    from ..kursdaten import KursDaten
    anbieter = KursDaten({**settings, "kursdaten_terminals": [terminal_pfad]})
    try:
        verbunden, grund = anbieter.starten()
        if not verbunden:
            return {"ok": False, "grund": f"Verbindung fehlgeschlagen: {grund}"}
        selbststart = getattr(anbieter, "_selbststart", selbststart)
        import MetaTrader5 as mt5
        info = mt5.terminal_info()
        test_symbol = broker_symbol("XAUUSD", settings)
        mt5.symbol_select(test_symbol, True)
        bars = mt5.copy_rates_from_pos(test_symbol, mt5.TIMEFRAME_H1, 0, 2)
        if bars is None or len(bars) == 0:
            return {"ok": False,
                    "grund": f"Verbunden, aber {test_symbol} liefert "
                             "keine Kursdaten (Symbol beim Broker? "
                             "markt_symbol_suffix pruefen)"}
        hinweis = (" — portable Selbststart" if selbststart else "")
        return {"ok": True,
                "grund": f"Verbunden mit {info.name if info else 'Terminal'} — "
                         f"XAUUSD-H1-Close {float(bars[-1]['close']):.2f}"
                         f"{hinweis}, Terminal danach beendet"}
    finally:
        anbieter.beenden()


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
