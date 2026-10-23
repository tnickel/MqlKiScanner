# -*- coding: utf-8 -*-
"""

Known-Limitation (L11, Review-Handoff 29.09.): copy_rates_range() hat
keinen Timeout-Parameter; initialize() nutzt den SDK-Verbindungs-Timeout.
Eine harte Gesamtfrist fuer blockierende MT5-Aufrufe gibt es hier nicht
(GUI-Scan- bzw. Daemon-Thread). Bewusst akzeptiert statt Thread-Timeout-Komplexität;
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

import logging
import os
import json
import sqlite3
import subprocess
import time

from .agenten.marktdata import broker_symbol, terminal_beenden, terminal_laueft
from .kurs_cache import KursCache
from .symbols import alias_fuer_symbol, normalize_symbol

ERLAUBTE_MT5_AUFRUFE = frozenset((
    "initialize", "shutdown", "terminal_info", "last_error", "account_info",
    "symbol_select", "copy_rates_range",
))

_DEFAULT_TERMINAL = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"
_LOG = logging.getLogger(__name__)
_INNENLUECKEN_FENSTER_S = 31 * 86400


def _buendle_innenluecken(bereiche, bars, jetzt, vorlaeufig):
    """Nur alte, beidseitig final begrenzte Fehlstrecken gemeinsam abfragen.

    Die Originalbereiche bleiben erhalten: Brueckenbars werden weder
    uebernommen noch neu als versucht markiert. Raender und unbestaetigte
    Bars behalten ihre bisherigen einzelnen Abrufe.
    """
    finale = [b["time"] for b in bars
              if b["time"] % 3600 == 0 and b["time"] + 3600 <= jetzt]
    if len(finale) < 2:
        return [[bereich] for bereich in bereiche]
    links, rechts = min(finale), max(finale)
    gruppen, gruppe = [], []
    for anfang, ende in bereiche:
        innen = (links < anfang <= ende < rechts
                 and ende - anfang <= _INNENLUECKEN_FENSTER_S
                 and not any(anfang <= t <= ende for t in vorlaeufig))
        if gruppe and (not innen or ende - gruppe[0][0] > _INNENLUECKEN_FENSTER_S
                       or any(gruppe[0][0] <= t <= ende for t in vorlaeufig)):
            gruppen.append(gruppe)
            gruppe = []
        if innen:
            gruppe.append((anfang, ende))
        else:
            gruppen.append([(anfang, ende)])
    if gruppe:
        gruppen.append(gruppe)
    return gruppen


class KursDaten:
    """H1-Historie je Symbol — pro Scan ein Anbieter, lazy initialisiert.

    Lifespan: `starten()` verbindet (und startet bei Freigabe das Terminal
    portabel). Quellenwechsel trennen nur die SDK-Verbindung; die dabei
    verwendeten Terminals bleiben bis `beenden()` offen. Am Laufende werden
    alle verwendeten Terminals pfadgenau beendet (Nutzer-Regel: sie gehören
    dem Scanner — doc/19 §7.3). `hole_h1()` bedient Symbole aus dem Cache.
    """

    def __init__(self, settings: dict):
        self.settings = settings or {}
        # Nutzer-Wunsch 05.10.: MEHRERE Kursdatenquellen (MetaTrader).
        # Setting kursdaten_terminals = [pfad1, pfad2, ...] — Prioritaet
        # in Reihenfolge; Fallback nur fuer Symbole, die die vorderen
        # nicht liefern. Ohne das Setting gilt der alte einzelne Pfad.
        termine = self.settings.get("kursdaten_terminals")
        if isinstance(termine, list) and termine:
            self.terminals = [str(p).strip() for p in termine if str(p).strip()]
        else:
            self.terminals = [str(self.settings.get("markt_terminal_pfad")
                                  or _DEFAULT_TERMINAL)]
        self.terminal_idx = 0
        self.terminal_pfad = self.terminals[0]
        self.start_erlauben = bool(self.settings.get("markt_start_erlauben", False))
        self._mt5 = None
        self._aktiv = False
        self._selbststart = False
        self._verbindungs_nr = 0
        # Nur tatsächlich verwendete Pfade gehören zu diesem Lauf. Andere
        # konfigurierte Terminals werden weder vorsorglich gestartet noch
        # am Laufende beendet. Normierte Schlüssel vermeiden Doppel-Stops.
        self._genutzte_terminals: dict[str, str] = {}
        self._cache: dict[str, list[dict] | None] = {}
        self._cache_zeit: dict[str, float] = {}
        self._cache_bis: dict[str, float] = {}
        self._kurs_cache: KursCache | None = None
        self._cache_defekt = False
        self._feed_je_terminal: dict[str, str] = {}
        self._aufgeloeste_symbole: dict[tuple[str, str], str] = {}
        # B10: roh-Symbol → tatsächlich verwendetes Terminal-Symbol, wenn
        # das exakte (suffigierte) Symbol nicht existierte.
        self.suffix_annahmen: dict[str, str] = {}
        # 05.10.: Welches Terminal lieferte welches Symbol (Transparenz,
        # GMT je Feed unterschiedlich — Auto-GMT-Abgleich je Symbol).
        self.terminal_herkunft: dict[str, str] = {}

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
        return self._terminal_portabel(mt5, lief_schon)

    def _terminal_portabel(self, mt5, lief_schon: bool) -> tuple[bool, str]:
        """Alle Kurs-Terminals brauchen /portable und ihre lokale Datenablage."""
        try:
            exe = Path(self.terminal_pfad).resolve()
        except (OSError, ValueError):
            return False, "Terminalpfad ungültig — kein automatisches Ausweichterminal."
        name = exe.parent.name
        if not exe.is_file():
            return False, f"{name}-Terminalpfad existiert nicht — kein automatisches Ausweichterminal."

        terminal_key = os.path.normcase(os.path.realpath(str(exe)))

        def fehler(grund):
            self._trennen()
            # Nur diese fehlerhafte Instanz schließen. Frühere Quellen
            # bleiben offen und werden weiterhin beim finalen Ende erfasst.
            self._beende_terminal(terminal_key, self.terminal_pfad)
            return False, grund

        try:
            erwartet = os.path.normcase(os.path.realpath(str(exe.parent)))
            for neustart in (False, True):
                self._genutzte_terminals[terminal_key] = self.terminal_pfad
                if not lief_schon or neustart:
                    subprocess.Popen([str(exe), "/portable"], cwd=str(exe.parent),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self._mt5 = mt5
                if not mt5.initialize(str(exe), portable=True):
                    return fehler(f"{name}-MT5-Verbindung fehlgeschlagen: {mt5.last_error()}")
                falscher_datenpfad = False
                for versuch in range(16):
                    info = mt5.terminal_info()
                    datenpfad = getattr(info, "data_path", "") if info else ""
                    if datenpfad and os.path.normcase(os.path.realpath(datenpfad)) != erwartet:
                        falscher_datenpfad = True
                        break
                    if datenpfad and bool(getattr(info, "connected", False)):
                        self._aktiv = True
                        if neustart:
                            return True, "portabel neu gestartet; Datenpfad geprüft, verbunden"
                        return True, ("portabel selbstgestartet; Datenpfad geprüft, verbunden"
                                      if not lief_schon else
                                      "portabel verbunden; Datenpfad geprüft")
                    if versuch < 15:
                        time.sleep(1.0)
                if not falscher_datenpfad:
                    return fehler(f"{name}-Terminal nach 15 s nicht verbunden oder portabler Datenpfad "
                                  "nicht belegbar — keine Kursmessung.")
                if neustart or not lief_schon or not self.start_erlauben:
                    return fehler(f"{name} verwendet eine andere Datenablage statt des portablen "
                                  "Terminalordners — keine Kursmessung; betroffene Instanz beendet.")
                # portable=True stellt eine laufende Instanz nicht um. Nur
                # einen belegten Fremddatenpfad mit Startfreigabe korrigieren.
                self._trennen()
                if not self._beende_terminal(terminal_key, self.terminal_pfad):
                    return False, (f"{name} verwendet eine andere Datenablage und konnte nicht "
                                   "beendet werden — kein portabler Neustart, keine Kursmessung.")
                self._selbststart = True
        except (OSError, RuntimeError) as exc:
            return fehler(f"{name}-Portable-Start fehlgeschlagen: {type(exc).__name__}")

    def _trennen(self) -> None:
        """Nur die prozessweite MT5-SDK-Verbindung lösen, Terminal offen lassen."""
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._mt5 = None
        self._aktiv = False
        self._selbststart = False
        self._verbindungs_nr += 1

    def _beende_terminal(self, terminal_key: str, terminal_pfad: str) -> bool:
        """Einen Prozess bereinigen, ohne die übrigen Quellen zu verlieren."""
        try:
            beendet = terminal_beenden(terminal_pfad)
        except Exception as exc:
            _LOG.warning("Kursdaten-Terminal konnte nicht beendet werden (%s): %s",
                         terminal_pfad, type(exc).__name__)
            return False
        if beendet is True:
            self._genutzte_terminals.pop(terminal_key, None)
            return True
        return False

    def beenden(self) -> None:
        """Lauf abschließen und alle darin verwendeten Terminals schließen."""
        self._trennen()
        for terminal_key, terminal_pfad in list(self._genutzte_terminals.items()):
            # Fehlschläge bleiben für einen erneuten beenden()-Aufruf
            # vorgemerkt; bereits geschlossene Terminals sind idempotent.
            self._beende_terminal(terminal_key, terminal_pfad)

    # ------------------------------------------------ Multi-Terminal (05.10.)

    def hat_weiteren_terminal(self) -> bool:
        """Gibt es noch eine weitere Kursdatenquelle (MetaTrader)?"""
        return self.terminal_idx < len(self.terminals) - 1

    def wechsle_terminal(self) -> tuple[bool, str]:
        """Zur naechsten Kursdatenquelle wechseln. MT5-Python ist pro
        Prozess ein Singleton: nur die SDK-Verbindung wird umgeschaltet.
        Bereits verwendete Terminals und deren Cache bleiben erhalten."""
        if not self.hat_weiteren_terminal():
            return False, "keine weitere Quelle"
        self._trennen()
        self.terminal_idx += 1
        self.terminal_pfad = self.terminals[self.terminal_idx]
        ok, msg = self.starten()
        return ok, f"{self.terminal_pfad}: {msg}"

    def zurueck_zum_ersten_terminal(self) -> tuple[bool, str]:
        """Nach wechsle_terminal() zurueck auf Quelle 0 (08.10.2026).

        Studien-Batch: Der Fallback eines Signals (fehlende Symbole →
        naechste Quelle) darf nicht alle FOLGESIGNALE am falschen Terminal
        lassen — dort fehlen dann.plötzlich Symbole, die Quelle 0 hatte
        (Live-Befund: NAS100FT nach einem HK50FT-Signal)."""
        if self.terminal_idx == 0:
            return True, "bereits erste Quelle"
        self._trennen()
        self.terminal_idx = 0
        self.terminal_pfad = self.terminals[0]
        ok, msg = self.starten()
        return ok, f"{self.terminal_pfad}: {msg}"

    # --------------------------------------------------------------- Kursdaten

    def _feed_identitaet(self) -> tuple[str, str | None]:
        """Terminal und belegter Server; keine Kontonummer/Kontostaende speichern.

        Eine Installation kann später einen anderen Server verwenden. Deshalb
        erst nach dem Verbinden dessen Identität prüfen, bevor persistente Bars
        wiederverwendet werden. Ohne Servernachweis bleibt nur der Laufcache.
        Nach dem Trennen ist die zuletzt in diesem Lauf bestätigte ID bekannt.
        """
        terminal = os.path.normcase(os.path.realpath(self.terminal_pfad))
        if self._aktiv and self._mt5 is not None:
            konto_lesen = getattr(self._mt5, "account_info", None)
            server = ""
            if callable(konto_lesen):
                try:
                    konto = konto_lesen()
                    server = str(getattr(konto, "server", "") or "").strip()
                except (RuntimeError, OSError):
                    pass
            if server:
                self._feed_je_terminal[terminal] = json.dumps(
                    [terminal, server], ensure_ascii=False)
            else:
                self._feed_je_terminal.pop(terminal, None)
                if callable(konto_lesen):
                    # Fehlender Nachweis kann auch einen laufenden Server-
                    # wechsel bedeuten. Kein Rücksprung auf frühere schwache
                    # RAM-Einträge derselben Installation.
                    self._verbindungs_nr += 1
        return f"{terminal}|verbindung:{self._verbindungs_nr}", self._feed_je_terminal.get(terminal)

    def _cache_fehler(self, exc: Exception) -> None:
        self._cache_defekt = True
        _LOG.warning("H1-Kurscache nicht verfügbar (%s); Kurse werden direkt gelesen.",
                     type(exc).__name__)

    def _laufcache_setzen(self, key: str, bars: list[dict] | None, jetzt: float) -> None:
        # Der dauerhafte Bestand lebt in SQLite. Nur wenige exakte Fenster
        # im RAM halten, damit lange Sammelläufe keine Historien duplizieren.
        if key not in self._cache and len(self._cache) >= 8:
            alt = min(self._cache, key=lambda k: self._cache_zeit.get(k, 0))
            self._cache.pop(alt, None)
            self._cache_zeit.pop(alt, None)
            self._cache_bis.pop(alt, None)
        self._cache[key] = bars
        self._cache_zeit[key] = jetzt
        self._cache_bis[key] = min(
            [jetzt + 60, *(b["time"] + 3600 for b in (bars or [])
                            if b["time"] + 3600 > jetzt)])

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
        von_s = int(von_epoch) + int(gmt_offset_s)
        bis_s = int(bis_epoch) + int(gmt_offset_s)
        if von_s > bis_s:
            return None
        terminal_key, feed = self._feed_identitaet()
        feed_key = feed or terminal_key
        key = f"{feed_key}|{symbol}|{von_s}|{bis_s}"
        jetzt = time.time()
        aufloesung = (feed_key, symbol)
        gewaehlt = self._aufgeloeste_symbole.get(aufloesung)
        am_broker = broker_symbol(symbol, self.settings)

        def herkunft(bars):
            if bars:
                self.terminal_herkunft[symbol.upper().strip()] = self.terminal_pfad
                if gewaehlt and gewaehlt != am_broker:
                    self.suffix_annahmen[symbol] = gewaehlt
                else:
                    self.suffix_annahmen.pop(symbol, None)
            return bars

        # Kurzlebige exakte Ergebnisse sparen DB-Abfragen; Teilhistorien und
        # offene Stunden werden dadurch nicht den ganzen Lauf eingefroren.
        if (key in self._cache
                and self._cache_zeit.get(key, 0) <= jetzt < self._cache_bis.get(key, 0)):
            bars = self._cache[key]
            return herkunft(bars)

        mt5 = self._mt5
        if gewaehlt is None:
            if not self._aktiv or mt5 is None:
                return None
            normalisiert = normalize_symbol(symbol)
            kandidaten = [am_broker]
            if normalisiert != symbol.upper().strip():
                kandidaten.append(broker_symbol(normalisiert, self.settings))
            alias = alias_fuer_symbol(symbol, self.terminal_pfad,
                                      self.settings.get("symbol_aliases"))
            if alias and alias not in kandidaten:
                kandidaten.append(alias)
            gewaehlt = next((k for k in kandidaten if mt5.symbol_select(k, True)), None)
        if gewaehlt is None:
            self._laufcache_setzen(key, None, jetzt)
            return None
        self._aufgeloeste_symbole[aufloesung] = gewaehlt

        bereiche = [(von_s, bis_s)]
        abfragen = [[(von_s, bis_s)]]
        persistent = bool(feed) and not self._cache_defekt
        bars = []
        if persistent:
            try:
                if self._kurs_cache is None:
                    self._kurs_cache = KursCache()
                bars = self._kurs_cache.lese(feed, gewaehlt, von_s, bis_s, now=jetzt)
                bereiche = self._kurs_cache.fehlende_bereiche(
                    feed, gewaehlt, von_s, bis_s, now=jetzt)
                vorlaeufige_zeiten = (self._kurs_cache.vorlaeufige_barzeiten(
                    feed, gewaehlt, von_s, bis_s) if len(bereiche) > 1 else set())
                abfragen = _buendle_innenluecken(bereiche, bars, jetzt, vorlaeufige_zeiten)
            except (sqlite3.Error, OSError, ValueError) as exc:
                self._cache_fehler(exc)
                persistent = False
                bereiche = [(von_s, bis_s)]
                abfragen = [[(von_s, bis_s)]]

        if self._aktiv and mt5 is not None:
            gesammelt = {bar["time"]: bar for bar in bars}
            vorlaeufig = {b["time"] for b in bars if b["time"] + 3600 > jetzt}
            for originalbereiche in abfragen:
                abruf_start = time.time()
                antwort = self._hole_terminal_h1(
                    gewaehlt, originalbereiche[0][0], originalbereiche[-1][1])
                for anfang, ende in originalbereiche:
                    # Ausschliesslich urspruenglich fehlende Bars uebernehmen;
                    # auch eine breite SDK-Antwort darf Cache-OHLC nicht aendern.
                    neue = [b for b in antwort if anfang <= b["time"] <= ende]
                    gesammelt.update((b["time"], b) for b in neue)
                    for bar in neue:
                        if bar["time"] + 3600 > abruf_start:
                            vorlaeufig.add(bar["time"])
                        else:
                            vorlaeufig.discard(bar["time"])
                    if persistent:
                        try:
                            self._kurs_cache.speichere(
                                feed, gewaehlt, anfang, ende, neue, now=abruf_start)
                        except (sqlite3.Error, OSError, ValueError) as exc:
                            self._cache_fehler(exc)
                            persistent = False
            ende_abruf = time.time()
            bars = sorted((b for t, b in gesammelt.items()
                           if t not in vorlaeufig or t + 3600 > ende_abruf),
                          key=lambda b: b["time"])
        self._laufcache_setzen(key, bars or None, jetzt)
        return herkunft(bars or None)

    def _hole_terminal_h1(self, symbol: str, von_s: int, bis_s: int) -> list[dict]:
        """Eine fehlende Strecke lesen; MT5-Historiennachladen bleibt begrenzt."""
        mt5 = self._mt5
        import datetime as _dt
        von = _dt.datetime.fromtimestamp(von_s, tz=_dt.timezone.utc)
        bis = _dt.datetime.fromtimestamp(bis_s, tz=_dt.timezone.utc)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, von, bis)
        # MT5 laedt Historie ON DEMAND vom Server: der ERSTE Abruf kann nur
        # den bereits lokalen Teil liefern und den Download anstossen (real
        # 05.10.: GBPJPY endete mitten im Fenster, der zweite Abruf brachte
        # alles — trotz Max Bars = Unlimited). Auch ein leerer Erstabruf
        # kann den Download erst anstossen. Maximal dreimal nachfragen;
        # sobald ein Teilbestand nicht mehr waechst, behalten wir diesen.
        # Ist das angefragte Fenster (mit Wochenend-Toleranz) erreicht,
        # ist kein weiterer Abruf erforderlich.
        ziel_bis = int(bis.timestamp())
        ziel_von = int(von.timestamp())
        for _versuch in range(3):
            anzahl = len(rates) if rates is not None else 0
            fertig = (anzahl > 0
                      and int(rates[-1]["time"]) + 3600 >= ziel_bis - 3 * 86400
                      and int(rates[0]["time"]) <= ziel_von + 3 * 86400)
            if fertig:
                break
            time.sleep(2.0)
            weitere = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, von, bis)
            weitere_anzahl = len(weitere) if weitere is not None else 0
            if anzahl > 0 and weitere_anzahl <= anzahl:
                break
            if weitere_anzahl > 0:
                rates = weitere
        if rates is None or len(rates) == 0:
            return []
        bars = [{"time": int(r["time"]), "open": float(r["open"]),
                 "high": float(r["high"]), "low": float(r["low"]),
                 "close": float(r["close"])} for r in rates]
        bars.sort(key=lambda b: b["time"])
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
