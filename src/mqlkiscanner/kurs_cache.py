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

import json
import math
import re
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS h1_abrufversuche_gueltig_bis
                ON h1_abrufversuche(gueltig_bis)
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

    def vorlaeufige_barzeiten(self, feed: str, symbol: str, von: int, bis: int) -> set[int]:
        """Unbestaetigte Bars bleiben auch innerhalb alter Historie separat abrufbar."""
        von, bis = self._pruefe(feed, symbol, von, bis)
        with self._verbinden() as conn:
            return {row[0] for row in conn.execute("""
                SELECT epoch FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND epoch BETWEEN ? AND ? AND abgeschlossen = 0
            """, (feed, symbol, von, bis))}

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
            # Zwei Randabfragen nutzen den Primärschlüssel. Die kombinierte
            # MIN/MAX-Abfrage durchsucht sonst bei jeder Lücke alle Symbolbars.
            erste_bar = conn.execute("""
                SELECT epoch FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND abgeschlossen = 1
                ORDER BY epoch ASC LIMIT 1
            """, (feed, symbol)).fetchone()
            letzte_bar = conn.execute("""
                SELECT epoch FROM h1_bars
                WHERE feed = ? AND symbol = ? AND zeitrahmen = 'H1'
                  AND abgeschlossen = 1
                ORDER BY epoch DESC LIMIT 1
            """, (feed, symbol)).fetchone()
            bekannt_von = erste_bar[0] if erste_bar else None
            bekannt_bis = letzte_bar[0] if letzte_bar else None
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


def uebersicht(cache_pfad: str | Path | None = None,
               studien: Iterable[Mapping] | None = None,
               alias_pfad: str | Path | None = None) -> list[dict]:
    """Kurs-Bestand je Symbol für den Einstellungs-Tab „Kursdaten".

    Listet ALLE bekannten Symbole — auch solche, zu denen Equity-Studien
    nur „ohne Kurse/Kontrakt" meldeten (Nutzer 28.10.2026: die Tabelle
    soll zeigen, was im MetaTrader-Kursbezug noch fehlt). Bar-Bestand
    kommt aus h1_bars (Feed/Symbol-übergreifend), die Studien-Nennungen
    aus den gespeicherten Studien-JSONs. Kursose zuerst, dann alphabetisch.
    """
    from datetime import datetime, timezone

    pfad = Path(cache_pfad) if cache_pfad is not None else config.DATA_DIR / "kursdaten.db"
    bestand: dict[str, dict] = {}
    if pfad.exists():
        with sqlite3.connect(pfad, timeout=30.0) as conn:
            for symbol, bars, feeds, von, bis in conn.execute(
                    "SELECT symbol, COUNT(*), COUNT(DISTINCT feed),"
                    " MIN(epoch), MAX(epoch) FROM h1_bars GROUP BY symbol"):
                bestand[symbol] = {"bars": bars, "feeds": feeds,
                                   "von": von, "bis": bis}
    alias = _lese_alias(alias_pfad) if alias_pfad else ersetzungen()
    if studien is None:
        from . import db
        studien = db.list_equity_studien(identitaeten=True).values()
    ohne: dict[str, int] = {}
    for item in studien:
        studie = (item.get("report")
                  if isinstance(item, Mapping) and "report" in item else item)
        if not isinstance(studie, Mapping):
            continue
        gemeldet: set[str] = set()
        for schluessel in ("symbole_ohne_kurse", "symbole_ohne_kontrakt"):
            for symbol in (studie.get(schluessel) or []):
                if isinstance(symbol, str) and symbol.strip():
                    gemeldet.add(symbol)
        for symbol in gemeldet:
            ohne[symbol] = ohne.get(symbol, 0) + 1
        # „Mit Kursen" gemeldete Symbole ohne Bar-Bestand bleiben sichtbar
        for symbol in (studie.get("symbole_mit_kursen") or []):
            if (isinstance(symbol, str) and symbol.strip()
                    and symbol not in bestand and symbol not in ohne):
                ohne[symbol] = 0
    zeilen = []
    index = {raw.upper(): raw for raw, b in bestand.items() if b["bars"]}
    fmt = (lambda e: datetime.fromtimestamp(e, tz=timezone.utc)
           .strftime("%d.%m.%Y %H:%M") if e else "")
    ersatz: dict[str, str] = {}
    for symbol in sorted(set(bestand) | set(ohne)):
        b = bestand.get(symbol)
        match = None if b else _kurs_match(symbol, index, alias)
        zeilen.append({
            "Symbol": symbol,
            "Status": ("Kurse vorhanden" if b else
                       "Ersetzung" if match else "keine Kurse"),
            "Im Bestand als": match or "",
            "Bars": b["bars"] if b else 0,
            "Erster Kurs": fmt(b["von"]) if b else "",
            "Letzter Kurs": fmt(b["bis"]) if b else "",
            "Feeds": b["feeds"] if b else 0,
            "Studien ohne Kurse": ohne.get(symbol, 0),
        })
        if match:
            ersatz[symbol] = match
    # Echte Lücken zuerst, dann Ersetzungsfälle, dann eigener Bestand.
    zeilen.sort(key=lambda z: ((2 if z["Status"] == "Kurse vorhanden" else
                                (1 if z["Status"] == "Ersetzung" else 0)),
                               z["Symbol"]))
    # Ersetzungszeilen zeigen die Kurswerte ihres Ersatz-Symbols — die
    # Tabelle wirkt als Kontrolle komplett (Nutzer 28.10.2026); die Spalte
    # „Im Bestand als" nennt die Quelle, „Status" die Herkunft.
    for z in zeilen:
        if z["Status"] == "Ersetzung":
            qb = bestand[ersatz[z["Symbol"]]]
            z["Bars"] = qb["bars"]
            z["Erster Kurs"] = fmt(qb["von"])
            z["Letzter Kurs"] = fmt(qb["bis"])
            z["Feeds"] = qb["feeds"]
    return zeilen


# Ersetzungstabelle (Nutzer 28.10.2026): bekannte Umbenennungen OHNE
# gemeinsames Suffix — Ziel muss im Bestand liegen, sonst bleibt die Zeile
# eine echte Lücke. Ergänzungen/Überschreibungen: data/kurs_alias.json
# ({"SYMBOL": "BESTANDSSYMBOL"}), wird bei jedem Übersichtslesen gelesen.
_KURS_ALIAS: dict[str, str] = {
    "BITCOIN": "BTCUSD",
    "GER30CASH": "GER40",
    "DE30M": "GER40",
    "US100": "USTEC",
    "USOIL-FUTURE": "USOUSD",
    "WTI": "USOUSD",
}


_ERSATZ_CACHE: dict = {"mtime": None, "daten": {}}


def ersetzungen() -> dict[str, str]:
    """Die zentrale Ersetzungstabelle — Studien-Symbol → Bestands-Symbol.

    Genau diese Tabelle nutzt KursDaten.hole_h1 als letzte Stufe der
    Symbol-Auflösung (also JEDE Drawdown-/Studien-Berechnung) UND die
    Übersichtstabelle im Einstellungs-Tab — ein Bestand, eine Wahrheit
    (Nutzer 28.10.2026: „zentrale Komponente, von allen Funktionen
    verwendet"). data/kurs_alias.json ergänzt/überschreibt die Eingebauten
    und wird bei Dateiänderung automatisch neu gelesen.
    """
    pfad = config.DATA_DIR / "kurs_alias.json"
    mtime = pfad.stat().st_mtime if pfad.exists() else None
    if _ERSATZ_CACHE["mtime"] != mtime:
        _ERSATZ_CACHE["daten"] = _lese_alias(pfad)
        _ERSATZ_CACHE["mtime"] = mtime
    return {**_KURS_ALIAS, **_ERSATZ_CACHE["daten"]}


def _lese_alias(pfad: Path) -> dict[str, str]:
    """Nutzer-Erweiterungen der Ersetzungstabelle (robust gegen kaputte Datei)."""
    if not pfad.exists():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(daten, dict):
        return {}
    return {str(k).strip().upper(): str(v).strip().upper()
            for k, v in daten.items()
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()}


def _kurs_match(symbol: str, index: dict[str, str],
                alias: dict[str, str] | None = None) -> str | None:
    """Anzeige-Matching für den Übersichts-Tab: zu einem Symbol ohne Bars
    den vorhandenen Bestand finden, der namensmäßig dahintersteckt
    (Suffix-Varianten wie GBPUSDM, USDCAD+, US500CASH, JPN225FT).

    Ausschließlich ANZEIGE im Übersichts-Tab — die Studien-Auflösung
    bleibt beim belegten Brokersymbol (Kontraktgrößen und Feed-Nachweis
    unterscheiden sich). Mitgliedschafts-gebremst: gematcht wird nur,
    wofür tatsächlich Bars liegen; nichts wird umbenannt oder gespeichert.
    """
    alias = alias or {}
    sym = symbol.strip().upper()
    treffer = index.get(sym)
    if treffer:
        return treffer
    ziel = alias.get(sym)
    if ziel and ziel in index:
        return index[ziel]
    kandidat = re.sub(r"[.+]+$", "", sym)
    for token in ("FUTURE", "CASH", "MICRO", "PRO", "FT"):
        if kandidat.endswith(token) and len(kandidat) > len(token) + 2:
            kandidat = kandidat[:-len(token)]
            break
    ziel = alias.get(kandidat)
    if ziel and ziel in index:
        return index[ziel]
    while len(kandidat) > 3:
        if kandidat in index:
            return index[kandidat]
        kandidat = kandidat[:-1]
    # Umgekehrt: Bestand trägt das Suffix (XAUAUD ≙ XAUAUD+), Basis nicht
    for bestand_sym, raw in index.items():
        if bestand_sym.upper().startswith(sym) and len(bestand_sym) > len(sym):
            rest = bestand_sym[len(sym):]
            while rest:
                for suf in ("+", "M", "FT", "CASH", ".A", ".M", "PRO",
                            "MICRO", "-FUTURE", "-P"):
                    if rest.upper().endswith(suf):
                        rest = rest[:-len(suf)]
                        break
                else:
                    rest = ""
                    break
            else:
                return raw
    return None
