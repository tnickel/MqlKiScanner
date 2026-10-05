# -*- coding: utf-8 -*-
"""

Known-Limitation (L11, Review-Handoff 29.09.): Das MetaTrader5-Paket
hat keinen nativen Timeout-Parameter — ein haengendes Terminal kann
initialize()/copy_rates_range() minutenlang blockieren (GUI-Scan- bzw.
Daemon-Thread). Bewusst akzeptiert statt Thread-Timeout-Komplexität;
beenden() ist idempotent und wird von allen Scan-Wegen in finally
aufgerufen. Bei wiederkehrenden Blockaden: Entscheidung Thread-Timeout.
Historische Kursdaten für die Equity-DD-Rekonstruktion (Nutzer-Wunsch 28.09).

NUR LESEND — derselbe MT5-Whitelist-Stil wie agenten/marktdata.py (doc/19
§7.1). Der Unterschied: hier werden HISTORIEN je Symbol über den Zeitraum
der Trades geladen (copy_rates_range), nicht nur die letzten 30 Tage.

Terminal-Politik identisch zur Start-Politik des Markt-Beobachters: ohne
laufendes Terminal und ohne markt_start_erlauben wird NICHT verbunden —
die Rekonstruktion entfällt dann still (kein Malus, kein Fehler).

Zeitbasis: Laut MetaTrader5-Python-Dokumentation sind MT5-Ratenzeiten
UTC-Epochs; time bezeichnet den BAR-ANFANG (mt5copyratesrange_py).
Die Trade-CSV-Zeiten haben keinen Zeitzonenbeleg. Den noetigen Versatz
vom naiven CSV-Zeitraum zum Kursdaten-Raum ermittelt die Auto-GMT-
Erkennung (forensics/equity_rekonstruktion.ermittle_gmt_offset) per
Preisabgleich — sie liefert den Shift, der hier fuer Lookups noetig ist.
Die Rekonstruktion setzt keine unbelegte CSV-Zeitzone voraus.
"""
from __future__ import annotations

from pathlib import Path

import time

from .agenten.marktdata import broker_symbol, terminal_beenden, terminal_laueft
from .symbols import normalize_symbol

ERLAUBTE_MT5_AUFRUFE = frozenset((
    "initialize", "shutdown", "terminal_info", "last_error",
    "symbol_select", "copy_rates_range",
))

_DEFAULT_TERMINAL = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"


class KursDaten:
    """H1-Historie je Symbol — pro Scan ein Anbieter, lazy initialisiert.

    Lifespan: `starten()` verbindet (und startet bei Freigabe das Terminal
    portabel), `beenden()` trennt und beendet das Terminal des Pfads
    (Nutzer-Regel: es gehört dem Scanner — doc/19 §7.3). Dazwischen bedient
    `hole_h1()` alle Symbole aus dem Cache.
    """

    def __init__(self, settings: dict):
        self.settings = settings or {}
        self.terminal_pfad = str(self.settings.get("markt_terminal_pfad")
                                 or _DEFAULT_TERMINAL)
        self.start_erlauben = bool(self.settings.get("markt_start_erlauben", False))
        self._mt5 = None
        self._aktiv = False
        self._selbststart = False
        self._cache: dict[str, list[dict]] = {}
        # B10: roh-Symbol → tatsächlich verwendetes Terminal-Symbol, wenn
        # das exakte (suffigierte) Symbol nicht existierte.
        self.suffix_annahmen: dict[str, str] = {}

    # ------------------------------------------------------------ Lebenszyklus

    def starten(self) -> tuple[bool, str]:
        """Verbinden (portabler Selbststart nur mit Freigabe)."""
        if self._aktiv:
            return True, "bereits verbunden"
        lief_schon = terminal_laueft(self.terminal_pfad)
        if not lief_schon and not self.start_erlauben:
            return False, ("Terminal läuft nicht und Selbststart nicht erlaubt "
                           "(markt_start_erlauben) — Equity-Rekonstruktion entfällt.")
        self._selbststart = not lief_schon
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            return False, f"MetaTrader5-Paket nicht verfügbar: {exc}"
        pfad = self.terminal_pfad if Path(self.terminal_pfad).exists() else None
        verbunden = bool(mt5.initialize(pfad, portable=self._selbststart)) if pfad \
            else bool(mt5.initialize())
        if not verbunden:
            fehler = str(mt5.last_error())
            mt5.shutdown()
            terminal_beenden(self.terminal_pfad)
            return False, f"MT5-Verbindung fehlgeschlagen: {fehler}"
        self._mt5 = mt5
        self._aktiv = True
        return True, ("portabel selbstgestartet" if self._selbststart else "Attach")

    def beenden(self) -> None:
        if self._mt5 is not None and self._aktiv:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._mt5 = None
        self._aktiv = False
        terminal_beenden(self.terminal_pfad)

    # --------------------------------------------------------------- Kursdaten

    def hole_h1(self, symbol: str, von_epoch: int, bis_epoch: int,
                gmt_offset_s: int = 0) -> list[dict] | None:
        """H1-Bars eines Symbols im Zeitfenster (Terminal-Epoch-Raum).

        gmt_offset_s verschiebt das Fenster vom Signal-Broker- in den
        Terminal-Raum (Ergebnis der Auto-GMT-Erkennung, in Sekunden).
        Rückgabe: aufsteigend sortierte Liste [{time, open, high, low,
        close}] oder None, wenn das Symbol keine Daten liefert.

        B10 (Intensiv-Review 29./30.09.2026): Findet das eigene Terminal
        das exakte Symbol nicht (Fremdbroker-Suffixe wie AUDCADR,
        XAUUSD.F, EURUSD+, AUDCAD-ECN — im Ziellauf deshalb 8 von 28
        MQL5-Signalen ohne wirksame Equity-Reko), wird das normalisierte
        Basis-Symbol als zweiter Versuch genommen und in
        suffix_annahmen protokolliert (raw → verwendet).
        """
        if not self._aktiv or self._mt5 is None:
            return None
        key = f"{symbol}|{von_epoch}|{bis_epoch}|{gmt_offset_s}"
        if key in self._cache:
            return self._cache[key]
        mt5 = self._mt5
        normalisiert = normalize_symbol(symbol)
        am_broker = broker_symbol(symbol, self.settings)
        kandidaten = [am_broker]
        if normalisiert != symbol.upper().strip():
            kandidaten.append(broker_symbol(normalisiert, self.settings))
        gewaehlt = None
        for kandidat in kandidaten:
            if mt5.symbol_select(kandidat, True):
                gewaehlt = kandidat
                break
        if gewaehlt is None:
            self._cache[key] = None
            return None
        if gewaehlt != kandidaten[0]:
            self.suffix_annahmen[symbol] = gewaehlt
        import datetime as _dt
        von = _dt.datetime.fromtimestamp(von_epoch + gmt_offset_s, tz=_dt.timezone.utc)
        bis = _dt.datetime.fromtimestamp(bis_epoch + gmt_offset_s, tz=_dt.timezone.utc)
        rates = mt5.copy_rates_range(gewaehlt, mt5.TIMEFRAME_H1, von, bis)
        # MT5 laedt Historie ON DEMAND vom Server: der ERSTE Abruf kann nur
        # den bereits lokalen Teil liefern und den Download anstossen (real
        # 05.10.: GBPJPY endete mitten im Fenster, der zweite Abruf brachte
        # alles — trotz Max Bars = Unlimited). Erneut abfragen, solange das
        # Ergebnis WAECHST und das angefragte Fenster (mit Wochenend-
        # Toleranz) noch nicht erreicht ist; ein Teilergebnis vergiftet
        # sonst den Lauf-Cache der ganzen Pipeline.
        ziel_bis = int(bis.timestamp())
        ziel_von = int(von.timestamp())
        for _versuch in range(3):
            if rates is None or len(rates) == 0:
                break
            fertig = (int(rates[-1]["time"]) + 3600 >= ziel_bis - 3 * 86400
                      and int(rates[0]["time"]) <= ziel_von + 3 * 86400)
            if fertig:
                break
            time.sleep(2.0)
            weitere = mt5.copy_rates_range(gewaehlt, mt5.TIMEFRAME_H1, von, bis)
            if weitere is None or len(weitere) <= len(rates):
                break
            rates = weitere
        if rates is None or len(rates) == 0:
            self._cache[key] = None
            return None
        bars = [{"time": int(r["time"]), "open": float(r["open"]),
                 "high": float(r["high"]), "low": float(r["low"]),
                 "close": float(r["close"])} for r in rates]
        bars.sort(key=lambda b: b["time"])
        self._cache[key] = bars
        return bars


# -------------------------------------------------------------------- Fakes


class FakeKursDaten:
    """Test-Doppel: diktierte Bars je Symbol, kein MT5, kein Terminal."""

    def __init__(self, bars_je_symbol: dict[str, list[dict]]):
        self.bars_je_symbol = {s: sorted(b, key=lambda x: x["time"])
                               for s, b in bars_je_symbol.items()}
        self.abfragen: list[tuple[str, int, int, int]] = []

    def starten(self) -> tuple[bool, str]:
        return True, "fake"

    def beenden(self) -> None:
        return None

    def hole_h1(self, symbol: str, von_epoch: int, bis_epoch: int,
                gmt_offset_s: int = 0) -> list[dict] | None:
        self.abfragen.append((symbol, von_epoch, bis_epoch, gmt_offset_s))
        bars = [b for b in self.bars_je_symbol.get(symbol, [])
                if von_epoch + gmt_offset_s <= b["time"] <= bis_epoch + gmt_offset_s]
        return bars or None
