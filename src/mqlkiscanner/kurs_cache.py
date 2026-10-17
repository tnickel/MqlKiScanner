# -*- coding: utf-8 -*-
"""Persistenter H1-Bestand je Kursfeed und tatsaechlichem Brokersymbol.

Der Cache speichert gelieferte Originalbars. Eine erfolgreiche Anfrage ist
kein Nachweis fuer deren ganzes Zeitfenster: nur vorhandene abgeschlossene
H1-Bars gelten dauerhaft als abgedeckt. Versuchsspannen halten davon
getrennt fest, wann eine Luecke zuletzt angefragt wurde: Binnenluecken
werden taeglich erneut versucht, unbekannte Raender/Leerantworten nach
60 Sekunden. Der Cache erfindet weder Kurse noch Handelskalender.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import time
from collections.abc import Iterable, Mapping
from contextlib import contextmanager

from . import config

H1_SEKUNDEN = 3600
AKTUALISIERUNG_SEKUNDEN = 24 * 3600
VERSUCH_PAUSE_SEKUNDEN = 60


class KursCache:
    """SQLite-H1-Cache, ohne persistente Verbindung oder MT5-Abhaengigkeit.

    ``feed`` muss der Aufrufer eindeutig aus Terminal und Server bilden.
    ``symbol`` ist der exakte, case-sensitive Name dieses Brokers. Eine
    Normalisierung/Alias-Aufloesung oder Verschiebung der Epochen findet
    hier ausdruecklich nicht statt. Zeitfenster sind wie copy_rates_range
    an beiden Enden inklusive und beziehen sich auf Bar-Anfangszeiten.
    """

    def __init__(self, pfad: str | Path | None = None):
        self.pfad = Path(pfad) if pfad is not None else config.DATA_DIR / "kursdaten.db"
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        with self._verbinden() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS h1_bars (
                    feed TEXT COLLATE BINARY NOT NULL,
                    symbol TEXT COLLATE BINARY NOT NULL,
                    zeitrahmen TEXT NOT NULL CHECK (zeitrahmen = 'H1'),
                    epoch INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    geladen_am REAL NOT NULL,
                    abgeschlossen INTEGER NOT NULL CHECK (abgeschlossen IN (0, 1)),
                    PRIMARY KEY (feed, symbol, zeitrahmen, epoch)
                ) WITHOUT ROWID
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS h1_abrufversuche (
                    feed TEXT COLLATE BINARY NOT NULL,
                    symbol TEXT COLLATE BINARY NOT NULL,
                    zeitrahmen TEXT NOT NULL CHECK (zeitrahmen = 'H1'),
                    von INTEGER NOT NULL,
                    bis INTEGER NOT NULL,
                    geladen_am REAL NOT NULL,
                    gueltig_bis REAL NOT NULL,
                    PRIMARY KEY (feed, symbol, zeitrahmen, von, bis)
                ) WITHOUT ROWID
            """)

    @contextmanager
    def _verbinden(self):
        conn = sqlite3.connect(self.pfad, timeout=30.0)
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _pruefe(feed: str, symbol: str, von: int, bis: int) -> tuple[int, int]:
        if not isinstance(feed, str) or not feed.strip():
            raise ValueError("Kursfeed darf nicht leer sein")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("Brokersymbol darf nicht leer sein")
        von, bis = int(von), int(bis)
        if von > bis:
            raise ValueError("Kurszeitraum: von liegt nach bis")
        return von, bis

    def lese(self, feed: str, symbol: str, von: int, bis: int,
             now: float | None = None) -> list[dict]:
        """Bestaetigte Historie und frische, noch offene Bars sortiert lesen.

        Eine vorlaeufige Bar gilt nach 60 Sekunden oder ab ihrem Stundenende
        nicht mehr als Messbasis. Sie bleibt gespeichert, bis ein finaler
        Abruf sie bestaetigt; eine Leerantwort finalisiert sie niemals.
        """
        von, bis = self._pruefe(feed, symbol, von, bis)
        jetzt = time.time() if now is None else float(now)
        with self._verbinden() as conn:
            rows = conn.execute("""
                SELECT epoch, open, high, low, close FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND epoch BETWEEN ? AND ?
                  AND (abgeschlossen = 1 OR
                       (geladen_am > ? AND geladen_am <= ? AND epoch + ? > ?))
                ORDER BY epoch
            """, (feed, symbol, von, bis, jetzt - VERSUCH_PAUSE_SEKUNDEN,
                  jetzt, H1_SEKUNDEN, jetzt)).fetchall()
        return [dict(zip(("time", "open", "high", "low", "close"), row))
                for row in rows]

    def fehlende_bereiche(self, feed: str, symbol: str, von: int, bis: int,
                          now: float | None = None) -> list[tuple[int, int]]:
        """Fehlende/veraltete H1-Bar-Anfangszeiten in gemeinsamen Bereichen.

        Tatsaechlich gelieferte abgeschlossene Bars bleiben dauerhaft
        abgedeckt. Reine Abrufversuche unterdruecken erneute Anfragen nur
        zeitweilig und erzeugen niemals Bars. Die aktuelle/offene Stunde
        wird hoechstens 60 Sekunden wiederverwendet und erst durch einen
        Abruf nach ihrem Ende als abgeschlossen bestaetigt.
        Ein Bereich mit genau einer fehlenden Bar hat identische Grenzen.
        """
        von, bis = self._pruefe(feed, symbol, von, bis)
        jetzt = time.time() if now is None else float(now)
        erste = -(-von // H1_SEKUNDEN) * H1_SEKUNDEN
        letzte = bis // H1_SEKUNDEN * H1_SEKUNDEN
        if erste > letzte:
            return []
        with self._verbinden() as conn:
            rows = conn.execute("""
                SELECT epoch FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND epoch BETWEEN ? AND ? AND abgeschlossen = 1
                ORDER BY epoch
            """, (feed, symbol, erste, letzte)).fetchall()
            vorlaeufig = conn.execute("""
                SELECT epoch FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND epoch BETWEEN ? AND ? AND abgeschlossen = 0
            """, (feed, symbol, erste, letzte)).fetchall()
            versuche = conn.execute("""
                SELECT von, bis, geladen_am FROM h1_abrufversuche
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND von <= ? AND bis >= ?
                  AND gueltig_bis > ? AND geladen_am <= ?
            """, (feed, symbol, letzte, erste, jetzt, jetzt)).fetchall()
        abgedeckt = [(epoch, epoch) for (epoch,) in rows if epoch % H1_SEKUNDEN == 0]
        for versuch_von, versuch_bis, _geladen_am in versuche:
            start = max(erste, -(-versuch_von // H1_SEKUNDEN) * H1_SEKUNDEN)
            ende = min(letzte, versuch_bis // H1_SEKUNDEN * H1_SEKUNDEN)
            if start <= ende:
                abgedeckt.append((start, ende))
        fehlend = []
        naechste = erste
        for start, ende in sorted(abgedeckt):
            if start > naechste:
                fehlend.append((naechste, start - H1_SEKUNDEN))
            naechste = max(naechste, ende + H1_SEKUNDEN)
        if naechste <= letzte:
            fehlend.append((naechste, letzte))
        # Eine alte offene Bar muss nach ihrem Ende noch final bestaetigt
        # werden. Eine spaetere Innenstrecke, die genau diese Bar nicht
        # geliefert hat, darf deren veraltete OHLC nicht fuer 24 h festhalten.
        for (epoch,) in vorlaeufig:
            if epoch % H1_SEKUNDEN == 0 and not any(
                    start <= epoch <= ende and geladen > jetzt - VERSUCH_PAUSE_SEKUNDEN
                    and (jetzt < epoch + H1_SEKUNDEN
                         or geladen >= epoch + H1_SEKUNDEN)
                    for start, ende, geladen in versuche):
                fehlend.append((epoch, epoch))
        vereinigt = []
        for start, ende in sorted(fehlend):
            if vereinigt and start <= vereinigt[-1][1] + H1_SEKUNDEN:
                vereinigt[-1] = (vereinigt[-1][0], max(vereinigt[-1][1], ende))
            else:
                vereinigt.append((start, ende))
        return vereinigt

    def speichere(self, feed: str, symbol: str, von: int, bis: int,
                 bars: Iterable[Mapping] | None, now: float | None = None) -> None:
        """Gelieferte OHLC-Bars atomar einfuegen bzw. korrigieren.

        Leer-/Fehlerantworten setzen nur einen 60-Sekunden-Abrufversuch.
        Der angefragte Teil der Innenstrecke zwischen bereits bekannten
        abgeschlossenen Bars wird fuer 24 Stunden als versucht markiert,
        auch wenn der erneute Abruf leer bleibt. Unbekannte Raender gelten
        nur fuer 60 Sekunden als versucht. Daten ausserhalb des angefragten
        Fensters werden nicht uebernommen. Fehlende Bars werden weder
        geloescht noch abgeleitet.
        """
        von, bis = self._pruefe(feed, symbol, von, bis)
        jetzt = time.time() if now is None else float(now)
        rows = []
        for bar in (() if bars is None else bars):
            epoch = int(bar["time"])
            if not von <= epoch <= bis:
                continue
            ohlc = tuple(float(bar[key]) for key in ("open", "high", "low", "close"))
            if not all(math.isfinite(value) for value in ohlc):
                raise ValueError("H1-Bar enthaelt nicht-endliche OHLC-Werte")
            final = int(epoch + H1_SEKUNDEN <= jetzt)
            rows.append((feed, symbol, "H1", epoch, *ohlc, jetzt, final))
        versuche = [(feed, symbol, "H1", von, bis, jetzt,
                     jetzt + VERSUCH_PAUSE_SEKUNDEN)]
        with self._verbinden() as conn:
            conn.executemany("""
                INSERT INTO h1_bars
                    (feed, symbol, zeitrahmen, epoch, open, high, low, close,
                     geladen_am, abgeschlossen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (feed, symbol, zeitrahmen, epoch) DO UPDATE SET
                    open = excluded.open, high = excluded.high,
                    low = excluded.low, close = excluded.close,
                    geladen_am = excluded.geladen_am,
                    abgeschlossen = MAX(h1_bars.abgeschlossen, excluded.abgeschlossen)
                WHERE excluded.geladen_am >= h1_bars.geladen_am
            """, rows)
            # Ein leerer Wochenend-Retry muss dieselbe Tagespause erhalten
            # wie die urspruengliche Abfrage. Die bekannten Grenzen sind
            # kein Beleg fuer Kurse in der Luecke, nur fuer die Innenlage
            # des tatsaechlich erneut angefragten Bereichs.
            bekannt_von, bekannt_bis = conn.execute("""
                SELECT MIN(epoch), MAX(epoch) FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND abgeschlossen = 1
            """, (feed, symbol)).fetchone()
            if bekannt_von is not None:
                innen_von = max(von, bekannt_von)
                innen_bis = min(bis, bekannt_bis + H1_SEKUNDEN - 1)
                if innen_von <= innen_bis:
                    versuche.append((feed, symbol, "H1", innen_von, innen_bis,
                                     jetzt, jetzt + AKTUALISIERUNG_SEKUNDEN))
            conn.execute("DELETE FROM h1_abrufversuche WHERE gueltig_bis <= ?", (jetzt,))
            conn.executemany("""
                INSERT INTO h1_abrufversuche
                    (feed, symbol, zeitrahmen, von, bis, geladen_am, gueltig_bis)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (feed, symbol, zeitrahmen, von, bis) DO UPDATE SET
                    geladen_am = MAX(h1_abrufversuche.geladen_am, excluded.geladen_am),
                    gueltig_bis = MAX(h1_abrufversuche.gueltig_bis, excluded.gueltig_bis)
            """, versuche)
