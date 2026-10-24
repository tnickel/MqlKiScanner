# -*- coding: utf-8 -*-
"""Equity-DD-Rekonstruktion aus Kursdaten (Nutzer-Wunsch 28.09.2026).

Der Broker-„By Equity"-Drawdown ist der wichtigste Risikowert — aber ein
SELBSTAUSKUNFTSWERT. Dieses Modul rechnet ihn aus der Trade-Historie NACH:
Auf einem H1-Raster wird die Equity-Kurve = Startkapital + realisierte
Gewinne + floating PnL der offenen Positionen (zum Bar-Close des jeweiligen
Symbols) geführt; der maximale Rückfall ist der rekonstruierte Equity-DD.

Auto-GMT (Nutzer-Idee): Trade-CSV-Zeiten sind naiv ohne Zeitzonenbeleg,
Kurszeiten laut MT5-Python-Dokumentation UTC-Bar-Anfangszeiten. Der noetige Shift wird
ermittelt, indem für Kandidaten-Offsets (±14 h, halbstündig nicht nötig —
Forex-Server nutzen ganze Stunden) geprüft wird, ob Open- UND Close-Kurse
der Trades innerhalb der High-Low-Spanne der jeweils getroffenen H1-Bar
liegen. Der Offset mit der höchsten Trefferquote gewinnt; unter 60 % gilt
die Erkennung als gescheitert und die Rekonstruktion entfällt ehrlich.

Bewertung: Das Ergebnis geht — nur bei belastbarer Abdeckung — als
viertes Maximum in die Drawdown-Schranke ein (Risiko vor Ertrag). Es ist
eine Messung aus Kursen, kein Szenario wie der Schock-Wert.
"""
from __future__ import annotations

import datetime as dt
import math
import copy
import os

from .. import fx_rates
from ..symbols import normalize_symbol
from .exposure import _resolve_symbol

# Kandidaten-Shifts: ganze Stunden, wie Forex-Serverzeiten üblich.
GMT_KANDIDATEN_S = tuple(h * 3600 for h in range(-14, 15))
# Mindest-Trefferquote, damit ein Offset als erkannt gilt.
GMT_MIN_TREFFER = 0.6
# Relative Toleranz beim Preisabgleich (Spreads/Rundungen).
_PREIS_TOLERANZ = 0.001
# Ab-deckem Anteil offen gehaltener H1-Punkte mit Kursen, damit das
# Ergebnis in die Schranke eingeht (sonst nur informativ).
SCHRANKE_MIN_ABDECKUNG = 0.95
# F5 (Fremd-Review 01.10.): Globale Bar-Luecken ab dieser Stundenlaenge
# gelten als Marktpause (Wochenende/Feiertag) und zaehlen NICHT als
# Datenluecke in den Abdeckungs-Nenner. Kuerzere Luecken sind Datenloecher.
MARKTPAUSE_MIN_H = 20

# Ein lokaler Kalenderabschnitt darf den globalen Versatz mit unabhaengigen
# Preisproben ueberschreiben. Nutzer-Regel 03.10.: Der Broker-Versatz ist
# monatelang konstant und wechselt nur zum Sommer-/Winterzeit-Termin —
# DREI stimmende Proben belegen ihn. Duplizierte Grid-Opens zaehlen nur
# einmal; Open UND Close werden nach ihrem eigenen Datum geprueft. Die
# Schutz Checks bleiben: bester Shift EINDEUTIG (Plateau = mehrdeutig)
# und Trefferquote >= GMT_LOKAL_MIN_TREFFER (bei 3 Proben: alle 3).
GMT_LOKAL_MIN_PROBEN = 3
GMT_LOKAL_MIN_TREFFER = 0.9
# Abstandskala fuer einzelne Preisereignisse (03.10., Nutzer-Fall GS MT5):
# knapp ausserhalb (<= Faktor x Toleranz) = Spread-/Slippage-Ausreisser —
# nur seine Stunden werden Luecken; weit ausserhalb (> Faktor) = falsche
# Zeitzone/kaputter Export — Zeitachse unzuverlaessig.
_PREIS_AUSREISSER_FAKTOR = 10.0


def _preisproben(trades):
    return sorted({(t.symbol.strip().upper(), _epoch(zeit), float(preis))
                   for t in trades
                   for zeit, preis in ((t.open_time, t.entry_price),
                                       (t.close_time, t.exit_price))
                   if zeit and preis})


def _preis_scores(proben, bars_je_symbol, maps=None):
    """Gleicher Nenner fuer jeden Shift; fehlende Bars sind Nichttreffer."""
    if maps is None:
        maps = {s.strip().upper(): {int(b["time"]) // 3600 * 3600: b for b in bars}
                for s, bars in bars_je_symbol.items()}
    counts = {}
    for shift in GMT_KANDIDATEN_S:
        treffer = 0
        for symbol, zeit, preis in proben:
            bar = maps.get(symbol, {}).get((zeit + shift) // 3600 * 3600)
            tol = abs(preis) * _PREIS_TOLERANZ + 1e-12
            if bar is not None and bar["low"] - tol <= preis <= bar["high"] + tol:
                treffer += 1
        counts[shift] = treffer
    return counts, maps


def _wochenbeginn(zeit):
    tag = dt.datetime.fromtimestamp(zeit, dt.timezone.utc)
    monday = (tag - dt.timedelta(days=tag.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


class Zeitbasis:
    """Preisbelegte Ereignisabbildung; Wochen sind Modell-, keine DST-Grenzen.

    Der globale Shift bleibt fuer kompatible duenne Abschnitte erhalten.
    Abweichende duenne Abschnitte werden als unsicher markiert. Ein
    Nachbar-Shift darf dort nur eine offengelegte diagnostische Spur liefern.
    Nicht eindeutige inverse Zeiten werden niemals als Broker-Tag erfunden.
    """

    def __init__(self, trades, bars_je_symbol, global_offset_s, manuell=False):
        self.manuell = manuell
        proben = _preisproben(trades)
        maps = _preis_scores([], bars_je_symbol)[1]
        self.perioden = []
        self.gruende = []
        self.unsichere_trade_ereignisse = 0
        gruppen = {}
        for p in proben:
            gruppen.setdefault(_wochenbeginn(p[1]), []).append(p)
        self.global_belegt = global_offset_s is not None
        self.hat_basis = self.global_belegt
        if global_offset_s is None:
            # Gleich lange Phasen mit verschiedenen Shifts koennen global
            # ein Plateau/<60% erzeugen, obwohl JE Phase eindeutig belegt ist.
            starke = {}
            for lokal in gruppen.values():
                counts, _ = _preis_scores(lokal, bars_je_symbol, maps)
                best = max(counts.values())
                kandidaten = [s for s, n in counts.items() if n == best]
                if (len(lokal) >= GMT_LOKAL_MIN_PROBEN and len(kandidaten) == 1
                        and best / len(lokal) >= GMT_LOKAL_MIN_TREFFER):
                    s = kandidaten[0]
                    starke[s] = starke.get(s, 0) + len(lokal)
            self.hat_basis = bool(starke)
            global_offset_s = (max(starke, key=lambda s: (starke[s], -abs(s), -s))
                               if starke else 0)
        self.global_offset_s = int(global_offset_s)
        erste = _wochenbeginn(min(_epoch(t.open_time) for t in trades))
        letzte = _wochenbeginn(max(_epoch(t.close_time) for t in trades)) + 7 * 86400
        previous = self.global_offset_s
        previous_belegt = self.global_belegt
        for von in range(erste, letzte, 7 * 86400):
            lokal = gruppen.get(von, [])
            counts, _ = _preis_scores(lokal, bars_je_symbol, maps)
            best = max(counts.values()) if lokal else 0
            kandidaten = {s for s, n in counts.items() if n == best} if lokal else set()
            quote = best / len(lokal) if lokal else None
            stark = (len(lokal) >= GMT_LOKAL_MIN_PROBEN and len(kandidaten) == 1
                     and quote >= GMT_LOKAL_MIN_TREFFER)
            bekannte_quote = counts[previous] / len(lokal) if lokal else None
            bekannten_behalten = (previous_belegt and stark
                                  and next(iter(kandidaten)) != previous
                                  and bekannte_quote >= GMT_LOKAL_MIN_TREFFER)
            belegt = self.global_belegt
            shift = self.global_offset_s
            status = "global_kompatibel"
            if manuell:
                status = "manuell"
                belegt = True
            elif bekannten_behalten:
                # Ein etwas besserer Wochengewinner widerlegt keinen
                # bereits belegten, weiterhin >=90% kompatiblen Shift.
                # Einzelne Nichttreffer werden unten weiterhin Luecken.
                shift = previous
                status = "bekannter_shift_weiter_preiskompatibel"
                belegt = True
            elif stark:
                shift = next(iter(kandidaten))
                status = "lokal_preisbelegt"
                # Nutzer-Fall 03.10. (GS MT5): EIN 4-Sekunden-Scalp mit
                # Nacht-Spread-Ausreisserpreis verfehlte die Toleranz — bei
                # 100-%-Anforderung fiel die GESAMTE Woche auf unbelegt und
                # mit ihr 1/3 der aktiven Stunden (Grid-Positionen laufen
                # tagelang): Abdeckung 96 % -> 66 %, Messung verworfen.
                # Semantik jetzt: >= GMT_LOKAL_MIN_TREFFER (90 %) belegt die
                # WOCHE; einzelne Nichttreffer markieren nur ihren EIGENEN
                # Trade unsicher — dessen Stunden werden Lücken, und die
                # 95-%-Abdeckungsregel entscheidet, ob die MESSUNG belastbar
                # bleibt. Massenhafte Nichttreffer (< 90 %) erben (siehe
                # unten) statt zu verwerfen.
                belegt = True
            elif lokal or previous_belegt or previous != self.global_offset_s:
                # Nutzer-Regel 03.10.: „GMT merken — nicht ermittelbar heißt
                # LETZTEN BEKANNTEN nehmen, das reicht." Wochen, die ihren
                # Versatz nicht selbst belegen können (dünn, mehrdeutig oder
                # mit abweichenden Proben), übernehmen den zuletzt belegten
                # Versatz (previous; Startwoche: global) statt die Messung zu
                # verwerfen. Ein echter DST-Wechsel wird erkannt, sobald eine
                # Folgewoche ihn selbst belegt (ab 3 stimmenden Proben);
                # bis dahin bleibt die Woche auf dem alten Versatz — die
                # betroffenen Trade-Preise fallen dann aus der Bar und werden
                # über den Ereignis-Check zu ehrlichen Lücken. Status
                # unterscheidet nur noch informativ, ob geerbt wurde.
                shift = previous
                status = ("geerbt_letzter_bekannter"
                          if previous != self.global_offset_s else
                          "global_kompatibel")
                belegt = previous_belegt
            self.perioden.append({"von_t": von, "bis_t": von + 7 * 86400,
                                  "offset_s": shift, "belegt": belegt,
                                  "preisproben": len(lokal), "trefferquote": quote,
                                  "bekannter_gmt_h": previous // 3600 if previous_belegt else None,
                                  "bekannter_trefferquote": bekannte_quote if previous_belegt else None,
                                  "lokal_beste_gmt_h": sorted(s // 3600 for s in kandidaten),
                                  "status": status})
            previous = shift
            previous_belegt = belegt
        self.variable = len({p["offset_s"] for p in self.perioden}) > 1
        events = sorted({_epoch(zeit) for t in trades
                         for zeit in (t.open_time, t.close_time)})
        mapped = [self.nach_referenz(zeit) for zeit in events]
        self.monoton = all(a <= b for a, b in zip(mapped, mapped[1:]))
        self.nichtmonotones_beispiel = None
        self.nichtmonoton_grund = "Zeitabbildung nicht monoton/eindeutig"
        if not self.monoton:
            self.gruende.append("Ereignisabbildung nicht monoton/eindeutig")
            for i, (a, b) in enumerate(zip(mapped, mapped[1:])):
                if a <= b:
                    continue
                def beschreibe(original, referenz):
                    return {
                        "csvzeit": dt.datetime.fromtimestamp(original, dt.timezone.utc).replace(tzinfo=None).isoformat(),
                        "offset_s": self.periode(original)["offset_s"],
                        "referenzzeit": dt.datetime.fromtimestamp(referenz, dt.timezone.utc).replace(tzinfo=None).isoformat(),
                    }
                vorher = beschreibe(events[i], a)
                nachher = beschreibe(events[i + 1], b)
                self.nichtmonotones_beispiel = {
                    "vorher": vorher, "nachher": nachher,
                    "umkehr_s": a - b,
                }
                self.nichtmonoton_grund += (
                    f": CSV {vorher['csvzeit']} ({vorher['offset_s'] / 3600:+g} h)"
                    f" -> {vorher['referenzzeit']}; danach CSV {nachher['csvzeit']}"
                    f" ({nachher['offset_s'] / 3600:+g} h) -> {nachher['referenzzeit']}"
                    f"; Reihenfolge um {a - b} Sekunden umgekehrt")
                break
        self.mehrdeutige_intervalle = []
        for links, rechts in zip(self.perioden, self.perioden[1:]):
            a = links["bis_t"] + links["offset_s"]
            b = rechts["von_t"] + rechts["offset_s"]
            if a != b:
                self.mehrdeutige_intervalle.append((min(a, b), max(a, b)))
        self._trade_sicher = {}
        self.offene_wechsel_annahmen = 0
        self.unsichere_innenperioden = 0
        self.weit_draussen_ereignisse = 0
        for t in trades:
            sicher = True
            for zeit, preis in ((t.open_time, t.entry_price), (t.close_time, t.exit_price)):
                e = _epoch(zeit)
                p = self.periode(e)
                if not p["belegt"]:
                    sicher = False
                    self.unsichere_trade_ereignisse += 1
                if not manuell and preis:
                    symbol = t.symbol.strip().upper()
                    bar = maps.get(symbol, {}).get(
                        self.nach_referenz(e) // 3600 * 3600)
                    tol = abs(preis) * _PREIS_TOLERANZ + 1e-12
                    if bar is None:
                        # Keine Bar zu dieser Stunde (Datenlücke): nur der
                        # Trade wird unsicher, seine Stunden bleiben Lücken.
                        sicher = False
                        self.unsichere_trade_ereignisse += 1
                        continue
                    abstand = max(bar["low"] - preis, preis - bar["high"], 0.0)
                    if abstand <= tol:
                        continue
                    sicher = False
                    self.unsichere_trade_ereignisse += 1
                    if abstand > _PREIS_AUSREISSER_FAKTOR * tol:
                        # Nutzer-Fall GS MT5 vs. Kaputt-Daten: Spread-/
                        # Slippage-Ausreisser liegen um WENIG ausserhalb
                        # der Toleranz (realer Fall: ~1,5x) und machen nur
                        # ihre Stunden zu Luecken; ein Preis um GROESSEN-
                        # ordnungen daneben (falsche Zeitzone/kaputter
                        # Export) widerlegt die Zeitachse hart.
                        self.weit_draussen_ereignisse += 1
                        self.gruende.append(
                            "Open-/Close-Preis passt nicht zur lokalen Referenzbar "
                            "(weit außerhalb — Zeitachse nicht belastbar)")
            if self.nach_referenz(_epoch(t.close_time)) < self.nach_referenz(_epoch(t.open_time)):
                sicher = False
                self.gruende.append("Ereignisabbildung ergibt Close vor Open")
            if any(self.nach_referenz(_epoch(t.open_time)) < ende
                   and self.nach_referenz(_epoch(t.close_time)) > anfang
                   for anfang, ende in self.mehrdeutige_intervalle):
                self.offene_wechsel_annahmen += 1
                self.gruende.append("Offene Position ueber nicht eindeutig belegter Zeitwechselgrenze")
            if any(not p["belegt"] and _epoch(t.open_time) < p["bis_t"]
                   and _epoch(t.close_time) > p["von_t"] for p in self.perioden):
                self.unsichere_innenperioden += 1
                self.gruende.append("Offene Position in lokal unbelegtem Zeitabschnitt")
            self._trade_sicher[id(t)] = sicher
        # Verlaesslich = STRUKTURELL belastbare Zeitachse: eindeutige
        # Ereignisabbildung, keine offenen Positionen ueber unsichere
        # Wechselgrenzen, keine aktiven Positionen in unbelegten Innenwochen
        # und kein Preisereignis um GROESSENordnungen ausserhalb seiner Bar
        # (Zeitzonen-/Datenmull). EINZELNE knappe Ausreisser (Spread, realer
        # Fall GS MT5 03.10.: 96 % -> 66 % Abdeckung nur wegen EINES
        # 4-Sekunden-Scalps) verwerfen die Messung nicht mehr ganz — ihre
        # Stunden sind Luecken, die 95-%-Abdeckungsregel entscheidet.
        self.verlaesslich = (self.hat_basis and self.monoton
                            and not self.offene_wechsel_annahmen
                            and not self.unsichere_innenperioden
                            and not self.weit_draussen_ereignisse)
        if not self.verlaesslich:
            self.gruende.append("Lokale Zeitbasis nicht fuer alle Trade-Ereignisse belegt")
        if self.unsichere_trade_ereignisse:
            self.gruende.append(
                f"{self.unsichere_trade_ereignisse} einzelne Preisereignisse "
                "knapp ausserhalb der Referenzbar (Spread/Ausreisser) — diese "
                "Stunden bleiben Lücken; die Abdeckungsregel entscheidet")

    def periode(self, zeit):
        for p in self.perioden:
            if p["von_t"] <= zeit < p["bis_t"]:
                return p
        return {"offset_s": self.global_offset_s, "belegt": True,
                "status": "global_ausserhalb_tradezeitraum"}

    def nach_referenz(self, zeit):
        return int(zeit) + self.periode(int(zeit))["offset_s"]

    def nach_broker(self, zeit):
        moegliche = [int(zeit) - p["offset_s"] for p in self.perioden
                     if p["von_t"] <= int(zeit) - p["offset_s"] < p["bis_t"]]
        if len(moegliche) == 1:
            return moegliche[0]
        if not moegliche:
            kandidat = int(zeit) - self.global_offset_s
            if kandidat < self.perioden[0]["von_t"] or kandidat >= self.perioden[-1]["bis_t"]:
                return kandidat
        return None

    def referenz_sicher(self, zeit):
        original = self.nach_broker(zeit)
        return original is not None and self.periode(original)["belegt"]

    def broker_tag(self, zeit):
        original = self.nach_broker(zeit)
        return (dt.datetime.fromtimestamp(original, dt.timezone.utc).date()
                if original is not None else None)

    def normalisiere(self, parsed):
        """Nur eine Analyse-Kopie; originales Export/sonstige Forensik unberuehrt."""
        result = copy.copy(parsed)
        result.trades = []
        for t in parsed.trades:
            neu = copy.copy(t)
            neu.open_time = dt.datetime.fromtimestamp(
                self.nach_referenz(_epoch(t.open_time)), dt.timezone.utc).replace(tzinfo=None)
            neu.close_time = dt.datetime.fromtimestamp(
                self.nach_referenz(_epoch(t.close_time)), dt.timezone.utc).replace(tzinfo=None)
            neu._zeitbasis_sicher = self._trade_sicher.get(id(t), False)
            result.trades.append(neu)
        result.balances = []
        for b in getattr(parsed, "balances", []):
            neu = copy.copy(b)
            neu.time = dt.datetime.fromtimestamp(
                self.nach_referenz(_epoch(b.time)), dt.timezone.utc).replace(tzinfo=None)
            result.balances.append(neu)
        result.costs = []
        for c in getattr(parsed, "costs", []):
            neu = copy.copy(c)
            neu.time = dt.datetime.fromtimestamp(
                self.nach_referenz(_epoch(c.time)), dt.timezone.utc).replace(tzinfo=None)
            result.costs.append(neu)
        return result

    def metadata(self):
        return {
            "modus": "manuell" if self.manuell else "wochenweise" if self.variable else "konstant",
            "frame": "referenzkurszeit" if self.variable else "broker",
            "global_gmt_h": self.global_offset_s // 3600,
            "global_belegt": self.global_belegt,
            "verlaesslich": self.verlaesslich,
            "monoton": self.monoton,
            "nichtmonotones_beispiel": self.nichtmonotones_beispiel,
            "offene_wechsel_annahmen": self.offene_wechsel_annahmen,
            "unsichere_innenperioden": self.unsichere_innenperioden,
            "annahme": "Kalenderwochengrenzen sind Modellgrenzen, kein exakter DST-Beleg",
            "belegregel": "Bekannten Shift bei eigener lokaler Trefferquote >=90% beibehalten; "
                          "neuer Shift braucht mindestens 3 Proben, eindeutigen Gewinner und >=90%. "
                          "Ohne bekannte Basis kein Kompatibilitaetsbeleg; Einzelereignisse bleiben geprueft.",
            "unsichere_trade_ereignisse": self.unsichere_trade_ereignisse,
            "gruende": list(dict.fromkeys(self.gruende)),
            "perioden": [{"von_t": p["von_t"], "bis_t": p["bis_t"],
                           "von": dt.datetime.fromtimestamp(p["von_t"], dt.timezone.utc).isoformat(),
                           "bis": dt.datetime.fromtimestamp(p["bis_t"], dt.timezone.utc).isoformat(),
                           "gmt_h": p["offset_s"] // 3600, "belegt": p["belegt"],
                           "preisproben": p["preisproben"],
                           "bekannter_gmt_h": p["bekannter_gmt_h"],
                           "bekannter_trefferquote": p["bekannter_trefferquote"],
                           "lokal_beste_gmt_h": p["lokal_beste_gmt_h"],
                           "trefferquote": round(p["trefferquote"], 3)
                               if p["trefferquote"] is not None else None,
                           "status": p["status"]} for p in self.perioden],
        }


def _epoch(naive: dt.datetime) -> int:
    """Naive Trade-Zeit → Epoch, als wäre sie UTC (Serverzeit-Trick)."""
    return int(naive.replace(tzinfo=dt.timezone.utc).timestamp())


def _bar_index(bars: list[dict]) -> tuple[list[int], dict[int, dict]]:
    zeiten = [b["time"] for b in bars]
    mappe = {b["time"]: b for b in bars}
    return zeiten, mappe


def _aktive_marktpausen(aktiv_je_symbol, closes_je_symbol):
    """Bestehende >=20h-Heuristik, begrenzt durch reale Bars je Symbol.

    Eine Stunde wird nur ausgenommen, wenn ALLE dort offenen Symbole
    pausieren. Fremde 24/7-Bars belegen keine Handelszeit fuer Gold.
    Lange Datenloecher und echte Handelspausen bleiben ohne Sessiondaten
    prinzipiell ununterscheidbar; kurze/ungegrenzte Loecher bleiben drin.
    """
    aktiv_gesamt, nicht_pausiert = set(), set()
    belege = []
    for symbol, aktiv in aktiv_je_symbol.items():
        aktiv_gesamt.update(aktiv)
        symbol_pausen = set()
        punkte = sorted(closes_je_symbol.get(symbol, {}))
        for vorher, nachher in zip(punkte, punkte[1:]):
            if nachher - vorher < (MARKTPAUSE_MIN_H + 1) * 3600:
                continue
            betroffen = aktiv.intersection(range(vorher + 3600, nachher, 3600))
            if betroffen:
                symbol_pausen.update(betroffen)
                belege.append({"symbol": symbol, "bar_ende_vorher": vorher,
                               "bar_ende_nachher": nachher,
                               "aktive_pausenstunden": len(betroffen)})
        nicht_pausiert.update(aktiv - symbol_pausen)
    pausen = aktiv_gesamt - nicht_pausiert
    for beleg in belege:
        beleg["ausgenommene_aktive_stunden"] = len(
            pausen & aktiv_je_symbol[beleg["symbol"]]
            & set(range(beleg["bar_ende_vorher"] + 3600,
                        beleg["bar_ende_nachher"], 3600)))
    return pausen, belege


class H1UsdUmrechnung:
    """Gemeinsamer Kursloader/Faktor fuer Workflow und manuelle Studie.

    EZB-Kurse behalten ihren Tagescache. Direkte Crypto-Kurse gelten nur
    fuer denselben belegten Feed und exakt denselben H1-Bar-Endpunkt.
    Der USDCNH-Kehrwert stammt ausschliesslich aus der eigenen Handelsbar.
    """

    def __init__(self, kurse, von, bis, broker=None, resolve_symbol=None, *, fx_lookup=None):
        self.kurse, self.von, self.bis = kurse, von, bis
        self.broker = broker
        self.resolve_symbol = resolve_symbol or _resolve_symbol
        self.fx_lookup = fx_rates.usd_per if fx_lookup is None else fx_lookup
        self.closes, self.fx_closes, self.feeds = {}, {}, {}
        self.tages_cache, self.h1_cache, self.quotes = {}, {}, {}

    @staticmethod
    def _feed_key(value):
        return os.path.normcase(os.path.realpath(str(value))) if value else ""

    @staticmethod
    def _closes(bars):
        return {(b["time"] // 3600 + 1) * 3600: b["close"] for b in bars}

    def hole_handelsbars(self, symbol):
        bars = self.kurse.hole_h1(symbol, self.von, self.bis)
        if not bars:
            return bars
        self.closes[symbol] = self._closes(bars)
        spec = self.resolve_symbol(symbol, self.broker)
        if spec is None or spec["quote"] not in {"BCH", "ETH"}:
            return bars
        fx_symbol = spec["quote"] + "USD"
        feed = self._feed_key(getattr(self.kurse, "terminal_pfad", None))
        herkunft = getattr(self.kurse, "terminal_herkunft", {})
        if not feed or self._feed_key(herkunft.get(symbol)) != feed:
            return bars
        fx_bars = self.kurse.hole_h1(fx_symbol, self.von, self.bis)
        herkunft = getattr(self.kurse, "terminal_herkunft", {})
        if (fx_bars and self._feed_key(getattr(self.kurse, "terminal_pfad", None)) == feed
                and self._feed_key(herkunft.get(symbol)) == feed
                and self._feed_key(herkunft.get(fx_symbol)) == feed):
            self.fx_closes[symbol] = self._closes(fx_bars)
            self.feeds[symbol] = str(getattr(self.kurse, "terminal_pfad"))
        return bars

    def faktor(self, quote, tag, punkt, symbol):
        if quote == "USD":
            return 1.0
        key = (quote, tag)
        if key not in self.tages_cache:
            kurs = self.fx_lookup(quote, tag)
            self.tages_cache[key] = kurs["rate"] if kurs else None
        if self.tages_cache[key] is not None:
            return self.tages_cache[key]
        intraday_key = (symbol, punkt)
        if intraday_key in self.h1_cache:
            return self.h1_cache[intraday_key]
        rate = None
        if quote == "CNH" and normalize_symbol(symbol) == "USDCNH":
            close = self.closes.get(symbol, {}).get(punkt)
            if (isinstance(close, (int, float)) and not isinstance(close, bool)
                    and math.isfinite(close) and close > 0):
                rate = 1.0 / close
        elif quote in {"BCH", "ETH"}:
            rate = self.fx_closes.get(symbol, {}).get(punkt)
        if (isinstance(rate, (int, float)) and not isinstance(rate, bool)
                and math.isfinite(rate) and rate > 0):
            self.h1_cache[intraday_key] = rate
            self.quotes[symbol] = quote
            return rate
        return None

    def provenienz(self):
        return [{"instrument": s, "quote": quote, "ziel": "USD",
                 "formel": ("1 / USDCNH-H1-Close (CNH je USD)" if quote == "CNH"
                            else f"{quote}USD-H1-Close (USD je {quote})"),
                 "feed": "Handelsbars desselben Symbols" if quote == "CNH" else self.feeds[s],
                 "umrechnungssymbol": s if quote == "CNH" else quote + "USD",
                 "zeitbasis": "exakt gleicher H1-Bar-Endpunkt wie Floating-Kurs",
                 "verfuegbare_zeitpunkte": sorted(p for symbol, p in self.h1_cache if symbol == s)}
                for s, quote in sorted(self.quotes.items())]


def ermittle_gmt_offset(trades, bars_je_symbol: dict[str, list[dict]],
                        max_proben: int = 60) -> dict:
    """Shift Signal-Broker → Referenz-Terminal per Preisabgleich.

    trades: Objekte mit open_time/close_time (naiv), entry_price/exit_price,
    symbol. Rückgabe {"offset_s", "trefferquote", "proben"} — offset_s None,
    wenn unter GMT_MIN_TREFFER.
    """
    alle_proben = [t for t in trades
              if t.entry_price and t.exit_price and t.open_time and t.close_time]
    proben = alle_proben
    if len(proben) > max_proben:
        schritt = len(proben) / max_proben
        proben = [proben[int(i * schritt)] for i in range(max_proben)]
    if not proben:
        return {"offset_s": None, "trefferquote": 0.0, "proben": 0}

    events = _preisproben(proben)
    counts, _maps = _preis_scores(events, bars_je_symbol)
    quotes = {shift: count / len(events) if events else 0.0
              for shift, count in counts.items()}
    vollpruefung = False
    if len(proben) < len(alle_proben):
        beste_stichprobe = max(quotes.values(), default=0.0)
        plateau_stichprobe = [s for s, q in quotes.items()
                             if q >= beste_stichprobe - 1e-9]
        if beste_stichprobe < GMT_MIN_TREFFER or len(plateau_stichprobe) > 1:
            # Eine kleine Stichprobe darf diskriminierende Ereignisse
            # nicht auslassen. Alle vorhandenen Preise nachpruefen;
            # Schwelle und Eindeutigkeitsanforderung bleiben identisch.
            proben = alle_proben
            events = _preisproben(proben)
            counts, _ = _preis_scores(events, bars_je_symbol, _maps)
            quotes = {shift: count / len(events) if events else 0.0
                      for shift, count in counts.items()}
            vollpruefung = True
    belege = {"proben": len(proben), "preisereignisse": len(events),
              "vollpruefung_nach_stichprobe": vollpruefung}
    if not quotes or max(quotes.values()) < GMT_MIN_TREFFER:
        return {"offset_s": None,
                "trefferquote": round(max(quotes.values()), 3) if quotes else 0.0,
                **belege}
    beste = max(quotes.values())
    # Plateau-Prüfung (Review 29.09.): Erreichen MEHRERE Shifts dieselbe beste
    # Quote, ist der Versatz nicht eindeutig bestimmbar — breite H1-Bänder
    # (plus Preis-Toleranz) treffen oft für benachbarte Offsets gleich gut,
    # und der frühere Tie-Break „kleinster Betrag" verzerrte systematisch
    # Richtung 0 h, während er 100 % Erkennung meldete. Mehrdeutig = ehrlich
    # überspringen statt eine falsche Zahl mit Vollerkennung liefern
    # (Projektregel: kein Nachweis = neutral, nichts erfinden).
    plateau = sorted(s for s, q in quotes.items() if q >= beste - 1e-9)
    if len(plateau) > 1:
        return {"offset_s": None, "trefferquote": round(beste, 3),
                "plateau_h": [s // 3600 for s in plateau], **belege}
    bester_shift = plateau[0]
    return {"offset_s": bester_shift, "trefferquote": round(beste, 3),
            **belege}


def rekonstruiere(parsed, kurse, startkapital: float,
                  broker: str | None = None, *, gmt_offset_h: int | None = None,
                  fx_lookup=None, include_curve: bool = False) -> dict:
    """Equity-Kurve auf H1-Raster + maximaler Equity-Drawdown.

    kurse: Anbieter mit hole_h1(symbol, von, bis, gmt_offset_s) (kursdaten.
    KursDaten oder Fake). Rückgabe mit equity_dd_pct/dd_usd nur bei
    ausreichender Abdeckung; sonst Grund im Feld "grund".
    """
    trades = [t for t in parsed.trades if t.close_time and t.open_time]
    if not trades:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "keine geschlossenen Trades"}
    # Ohne belastbare Kapitalbasis ist der PROZENTwert bedeutungslos —
    # sonst hieße „0 % DD" gesund, obwohl gar keine Bezugsbasis existiert
    # (Review 29.09., Befund 5).
    if startkapital is None or startkapital <= 0:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "keine belastbare Kapitalbasis "
                         "(Startkapital fehlt oder ≤ 0) — Prozentwert nicht aussagekräftig"}
    symbole = sorted({t.symbol.strip().upper() for t in trades if t.symbol})

    von = min(_epoch(t.open_time) for t in trades)
    bis = max(_epoch(t.close_time) for t in trades)
    bis += 3600

    # GMT-Erkennung braucht erst einmal Bars im WEITESTEN Fenster.
    bars_je_symbol: dict[str, list[dict]] = {}
    fenster_von = von + min(GMT_KANDIDATEN_S)
    fenster_bis = bis + max(GMT_KANDIDATEN_S)
    fehlende_symbole: list[str] = []
    umrechnung = H1UsdUmrechnung(kurse, fenster_von, fenster_bis, broker,
                               fx_lookup=fx_lookup)
    _hole_handelsbars = umrechnung.hole_handelsbars

    for s in symbole:
        bars = _hole_handelsbars(s)
        if bars:
            bars_je_symbol[s] = bars
        else:
            fehlende_symbole.append(s)

    # Nutzer-Wunsch 05.10.: ZWEITE Kursdatenquelle (MetaTrader) als Fallback.
    # MT5-Python ist pro Prozess ein Singleton — erst ALLE Symbole von der
    # primaeren Quelle laden, dann Terminal wechseln und NUR die fehlenden
    # Symbole erneut versuchen. Die Bars eines Symbols bleiben aus EINEM
    # Feed. Gemeinsamer Preisabgleich und lokale Zeitbasis muessen die
    # Zuordnung danach belegen; verschiedene Feeds garantieren keinen
    # gemeinsamen Zeitversatz und koennen unzuverlaessig bleiben.
    # Nutzer-Logik 08.10.2026: SO LANGE durch die Quellen/Broker probieren,
    # bis die Kurse da sind — nicht nur ein einziger Fallback. Jede Quelle
    # (Terminal) hat ein anderes Symbol-Angebot (Tickmill: FX-Kreuze +
    # Cash-Indizes; Vantage: XAUUSD+/CL-OIL/VIX/CHINA50 nativ; …); erst wenn
    # KEINE Quelle mehr übrig ist, gilt ein Symbol als ohne Kurse.
    while fehlende_symbole and hasattr(kurse, 'hat_weiteren_terminal')             and kurse.hat_weiteren_terminal():
        ok, msg = kurse.wechsle_terminal()
        if not ok:
            break
        noch_fehlend = []
        for s in fehlende_symbole:
            bars = _hole_handelsbars(s)
            if bars:
                bars_je_symbol[s] = bars
            else:
                noch_fehlend.append(s)
        fehlende_symbole = noch_fehlend

    # Der Fallback-Wechsel darf NICHT kleben: Nach der Rekonstruktion wieder
    # auf Quelle 0 zurück — sonst binden die Kurse eines Signals alle Folge-
    # signale ans falsche Terminal (08.10., NAS100FT-Fall). Gilt auch für den
    # Workflow-Scan, der den Anbieter über den ganzen Lauf cached.
    if hasattr(kurse, 'zurueck_zum_ersten_terminal')             and getattr(kurse, 'terminal_idx', 0) != 0:
        kurse.zurueck_zum_ersten_terminal()

    # Kontrakt-/Quote-Auflösung je Symbol (einmalig) — NUR mit Beleg. Ohne
    # Spec/Klassenkontrakt wäre jeder Faktor erfunden (der frühere stille
    # 100-000-Default erzeugte Phantom-Floating und meldete es als
    # verlässlich; Review 29.09., Befund 4): solche Symbole fliegen aus
    # der Kurve, genau wie Symbole ohne Kurse.
    aufgeloest: dict[str, dict] = {}
    symbole_ohne_kontrakt: list[str] = []
    for s in bars_je_symbol:
        spec = _resolve_symbol(s, broker)
        if spec is not None:
            aufgeloest[s] = spec
        else:
            symbole_ohne_kontrakt.append(s)

    def _nutzbar(t) -> bool:
        s = t.symbol.strip().upper()
        return s in bars_je_symbol and s in aufgeloest

    nutzbare = [t for t in trades if _nutzbar(t)]
    if len(nutzbare) < 0.8 * len(trades):
        fehlend = len(trades) - len(nutzbare)
        detail = []
        if fehlende_symbole:
            detail.append(f"Kurse: {', '.join(fehlende_symbole[:5])}")
        if symbole_ohne_kontrakt:
            detail.append(f"Kontrakt unbelegt: {', '.join(symbole_ohne_kontrakt[:5])}")
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "verlaesslich": False,
                "symbole_ohne_kurse": sorted(fehlende_symbole),
                "symbole_ohne_kontrakt": sorted(symbole_ohne_kontrakt),
                "trades_gesamt": len(trades), "trades_genutzt": len(nutzbare),
                "grund": f"Kursdaten fehlen für {fehlend} "
                         f"von {len(trades)} Trades ({' · '.join(detail)})"}

    if gmt_offset_h is not None and (isinstance(gmt_offset_h, bool)
                                    or not isinstance(gmt_offset_h, int)
                                    or gmt_offset_h * 3600 not in GMT_KANDIDATEN_S):
        raise ValueError("Manueller GMT-Versatz muss eine ganze Stunde zwischen -14 und +14 sein")
    gmt = (ermittle_gmt_offset(nutzbare, bars_je_symbol)
           if gmt_offset_h is None else
           {"offset_s": gmt_offset_h * 3600, "trefferquote": None})
    offset = gmt["offset_s"]
    zeitbasis = Zeitbasis(trades, bars_je_symbol, offset,
                         manuell=gmt_offset_h is not None)
    if offset is None and not zeitbasis.hat_basis:
        if gmt.get("plateau_h"):
            return {"test": "equity_rekonstruktion", "status": "skipped",
                    "grund": f"Auto-GMT mehrdeutig — mehrere Offsets "
                             f"({', '.join(f'{h:+d} h' for h in gmt['plateau_h'][:6])}) "
                             f"treffen zu {gmt['trefferquote']:.0%}; Zeitversatz "
                             f"nicht eindeutig bestimmbar."}
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": f"Auto-GMT ohne eindeutiges Ergebnis "
                         f"(Trefferquote {gmt['trefferquote']:.0%} < "
                         f"{GMT_MIN_TREFFER:.0%}) — Zeitversatz nicht belastbar."}

    if not zeitbasis.monoton:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "verlaesslich": False, "grund": zeitbasis.nichtmonoton_grund,
                "zeitbasis": zeitbasis.metadata()}
    original_offset = zeitbasis.global_offset_s
    offset = original_offset
    if zeitbasis.variable:
        parsed = zeitbasis.normalisiere(parsed)
        trades = [t for t in parsed.trades if t.close_time and t.open_time]
        offset = 0

    # MT5 time bezeichnet den BAR-ANFANG. Der Close-Kurs gehoert an das
    # Ende dieses Intervalls, nicht eine Stunde davor. Trade-Ereignisse
    # behalten ihre Sekunden: Schluss 10:20 wird erst im Punkt 11:00
    # realisiert, waehrend der Close der Bar 09:00 im Punkt 10:00 gilt.
    anfang = min(_epoch(t.open_time) + offset for t in trades)
    ende = max(_epoch(t.close_time) + offset for t in trades)
    endpunkt = ((ende + 3599) // 3600) * 3600
    raster: list[int] = sorted({(b["time"] // 3600 + 1) * 3600
                                for bars in bars_je_symbol.values() for b in bars
                                if anfang < (b["time"] // 3600 + 1) * 3600 <= endpunkt})
    if not raster:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "keine H1-Bars im Zeitraum"}
    closes_je_symbol: dict[str, dict[int, float]] = {}
    for s, bars in bars_je_symbol.items():
        closes_je_symbol[s] = {(b["time"] // 3600 + 1) * 3600: b["close"] for b in bars}
    # Das Endkonto braucht keine Kurse: selbst wenn am Schluss eine Bar
    # fehlt, muss das Netto ALLER abgeschlossenen Positionen enthalten sein.
    raster = sorted(set(raster) | {endpunkt})

    # Realisierte PnL kumulieren (Close-Zeit + Offset im Terminal-Raum).
    schliessungen = sorted(
        [(_epoch(t.close_time) + offset, t.net) for t in trades]
        + [(_epoch(c.time) + offset, c.amount) for c in getattr(parsed, "costs", [])
           if _epoch(c.time) + offset >= anfang],
        key=lambda x: x[0])
    # Kosten bei sicher flachem Konto sind ohne Kurse messbar. Bei offenen
    # Trades bleibt das unveraenderte H1-Raster: kein Kurs wird vorgezogen;
    # der naechste Rasterpunkt enthaelt das realisierte Kostenergebnis.
    raster = sorted(set(raster) | {_epoch(c.time) + offset
        for c in getattr(parsed, "costs", []) if _epoch(c.time) + offset >= anfang
        and not any(_epoch(t.open_time) + offset <= _epoch(c.time) + offset
                    < _epoch(t.close_time) + offset for t in trades)})

    # ALLE Positionen fuer den Aktivstatus verwenden. Fehlende Kurse
    # verhindern eine Floating-Messung, aber nie die Realisierung ihres
    # exportierten Nettos. Keine Rundung der Open-/Close-Ereignisse.
    # Key-ONLY-Sortierung (Live-Bug 29.09., MCA100 #2153920): Das Tupel
    # enthaelt das Trade-Objekt — hatten zwei Trades dieselbe Open- UND
    # Close-Stunde (Grid/Scalping), verglich Python die Objekte und warf
    # „'<' not supported between instances of 'Trade' and 'Trade'" → die
    # Equity-Reko scheiterte zweimal (auch im Retry) und das Signal bekam
    # keine Kursdaten-Nachmessung.
    offen_sort = sorted(
        ((_epoch(t.open_time) + offset,
          _epoch(t.close_time) + offset, t) for t in trades),
        key=lambda x: (x[0], x[1]))

    fx_fehlt = False
    _usd_faktor = umrechnung.faktor

    # Expliziter Anker vor dem ersten Handelsereignis: auch ein erster
    # Floating-Verlust darf nicht selbst zum Anfangshoch werden.
    curve: list[tuple[int, float, bool, float]] = [(anfang, float(startkapital), True, 0.0)]
    realisiert = 0.0
    schliess_idx = 0
    offen_idx = 0
    aktiv: list = []           # (close_epoch_exklusiv, trade)
    # Nutzer-Regel 05.10.2026: Die Kurs-Kurve reitet auf der REALEN Konto-
    # kurve — Ein-/Auszahlungen NACH Handelsbeginn bleiben drin (Einzahlung
    # => Betreiber erhöht Lots => Drawdowns wachsen). Auszahlungen senken
    # den Peak um ihren Betrag und erzeugen so KEINEN Drawdown. Flows vor
    # dem ersten Trade stecken bereits im Startkapital (drawdown.run).
    erste_open_epoch = min(_epoch(t.open_time) for t in trades) + offset
    flows_sort = sorted(
        ((_epoch(b.time) + offset, float(b.amount))
         for b in getattr(parsed, "balances", [])
         if _epoch(b.time) + offset > erste_open_epoch),
        key=lambda f: f[0])
    flows_kumulativ = 0.0
    flow_idx = 0
    punkte_mit_kurs = 0
    punkte_ohne_kurs = 0
    punkte_teil_mit_kurs = 0
    punkte_teil_ohne_kurs = 0
    # F5 (Fremd-Review 01.10.): Der Abdeckungs-Nenner darf nicht nur aus
    # vorhandenen Bar-Stunden bestehen — sonst verschwinden Datenlöcher
    # still aus der Rechnung (Probe: 8 offene Stunden, 3 mit Bars -> 100 %).
    # Nenner: jede volle Stunde, in der laut Trade-Zeiten eine Position
    # aktiv wäre, MINUS erkannte Marktpausen (symbolweise Bar-Luecken >= 20 h,
    # klassisch Wochenende/Feiertag — solche Stunden sind keine Datenlücke).
    aktiv_laut_zeit: set[int] = set()
    aktiv_laut_zeit_betrachtet: set[int] = set()
    aktiv_je_symbol: dict[str, set[int]] = {}
    for _offen, _ende, _t in offen_sort:
        _stunden = set(range((_offen // 3600 + 1) * 3600, _ende, 3600))
        aktiv_laut_zeit.update(_stunden)
        aktiv_je_symbol.setdefault(_t.symbol.strip().upper(), set()).update(_stunden)
        if _t.symbol.strip().upper() in closes_je_symbol                 and _t.symbol.strip().upper() in aufgeloest:
            aktiv_laut_zeit_betrachtet.update(_stunden)
    pausen, pausen_belege = _aktive_marktpausen(aktiv_je_symbol, closes_je_symbol)

    for punkt in raster:
        while schliess_idx < len(schliessungen) and schliessungen[schliess_idx][0] <= punkt:
            realisiert += schliessungen[schliess_idx][1]
            schliess_idx += 1
        flow_delta = 0.0
        while flow_idx < len(flows_sort) and flows_sort[flow_idx][0] <= punkt:
            flow_delta += flows_sort[flow_idx][1]
            flows_kumulativ += flows_sort[flow_idx][1]
            flow_idx += 1
        while offen_idx < len(offen_sort) and offen_sort[offen_idx][0] < punkt:
            aktiv.append((offen_sort[offen_idx][1], offen_sort[offen_idx][2]))
            offen_idx += 1
        aktiv = [a for a in aktiv if a[0] > punkt]
        floating = 0.0
        kurs_da = True
        kurs_da_betrachtet = True   # Teil-Messung (Nutzer-Regel 04.10. nachts):
                                    # Positionen OHNE beschaffbare Kurse (Symbol
                                    # fehlt komplett) lassen den Punkt fuer die
                                    # Teil-Abdeckung zaehlen; nur echte Daten-
                                    # loecher BETRACHTBARER Symbole zaehlen dagegen.
        unbetrachtbar_aktiv = False
        tag = (zeitbasis.broker_tag(punkt) if zeitbasis.variable else
               dt.datetime.fromtimestamp(punkt - offset, dt.timezone.utc).date())
        if aktiv and not (zeitbasis.referenz_sicher(punkt) if zeitbasis.variable else
                          zeitbasis.periode(punkt - offset)["belegt"]):
            kurs_da = False
            kurs_da_betrachtet = False
        for _ende, t in aktiv:
            s = t.symbol.strip().upper()
            hat_bars = s in closes_je_symbol
            if not hat_bars or s not in aufgeloest:
                # Symbol ueberhaupt nicht messbar (keine Kurse/kein Kontrakt):
                # nicht Teil der Messung — namentliche Warnung am Ergebnis.
                unbetrachtbar_aktiv = True
                kurs_da = False
                continue
            close = closes_je_symbol.get(s, {}).get(punkt)
            if (close is None or not t.entry_price
                    or not getattr(t, "_zeitbasis_sicher", True) or tag is None):
                kurs_da = False
                kurs_da_betrachtet = False
                continue
            res = aufgeloest[s]
            richtung = 1.0 if t.direction.lower() == "buy" else -1.0
            pnl_quote = richtung * t.volume * res["factor"] * (close - t.entry_price)
            fx = _usd_faktor(res["quote"], tag, punkt, s)
            if fx is None:
                kurs_da = False
                kurs_da_betrachtet = False
                fx_fehlt = True
                continue
            floating += pnl_quote * fx
        if aktiv and punkt not in pausen:
            if kurs_da:
                punkte_mit_kurs += 1
            else:
                punkte_ohne_kurs += 1
            # Teil-Messung: zaehlt Punkte, deren BETRACHTBARE Positionen
            # vollstaendig gemessen wurden (unbetrachtbare ausgenommen).
            if kurs_da_betrachtet:
                punkte_teil_mit_kurs += 1
            else:
                punkte_teil_ohne_kurs += 1
        # F2 (Fremd-Review 01.10.): Ein Punkt mit AKTIVER Position, aber
        # unvollstaendigem Floating ist kein Messpunkt — sein fehlendes PnL
        # wuerde sonst einen erfundenen Rueckfall (oder eine verdeckte
        # Belastung) erzeugen. Stunden ohne offene Position bleiben
        # Messpunkte (floating=0 ist dort korrekt — der finale
        # Schlussverlust, B1-Fix 29.09., muss messbar bleiben).
        # Realisiert laeuft kumulativ weiter, spaeter vollstaendige Punkte
        # bleiben korrekt; die DD-Messung ueberspringt die Luecke.
        # Eine erlaubte Teilmessung enthält das bekannte Floating auch dann,
        # wenn ein vollständig unbetrachtbares Symbol zeitgleich offen ist.
        # Echte Kurs-/FX-Lücken der betrachtbaren Symbole bleiben Lücken.
        messpunkt = kurs_da or (unbetrachtbar_aktiv and kurs_da_betrachtet)
        curve.append((punkt, startkapital + realisiert + flows_kumulativ + floating,
                      messpunkt, flow_delta))
        # Abbruch ERST NACH dem Anhängen: Der letzte Punkt (alles realisiert,
        # nichts mehr offen) trägt den Endkontostand — exakt dort entsteht der
        # finale Verlust. Der frühere break davor ließ echte Schlussverluste
        # als 0 % DD durchgehen (Review 29.09., Befund 1).
        if not aktiv and schliess_idx >= len(schliessungen) \
                and offen_idx >= len(offen_sort):
            break

    # Kontobewegungen NACH dem letzten Trade-Ende liegen außerhalb des
    # Rasters — als finalen Kurvenpunkt buchen, sonst fehlen sie in Kurve
    # und Endkontostand (Nutzer-Regel 05.10.: reale Kontokurve komplett).
    if flow_idx < len(flows_sort):
        rest_flows = math.fsum(b for _t, b in flows_sort[flow_idx:])
        curve.append((flows_sort[-1][0], curve[-1][1] + rest_flows, True, rest_flows))
        flows_kumulativ += rest_flows
        flow_idx = len(flows_sort)

    if len(curve) < 2:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "zu wenige Rasterpunkte mit Kursen"}

    # L14 (Review-Handoff 29.09.): Ein NaN/Inf in der Kurve (Kursdaten-
    # Fehler) wuerde den Rueckfallvergleich still falsch machen und am Ende
    # "0 % DD" melden — ohne dass verlaesslich es abfingt. Nicht endliche
    # Werte = Reko unbrauchbar -> ehrlich skippen statt Schoenrechnen.
    if not all(math.isfinite(wert) for _t, wert, _m, _f in curve):
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "NaN/Inf in der Equity-Kurve (Kursdaten unbrauchbar)"}

    hoch = curve[0][1]
    dd_usd = 0.0
    dd_pct = 0.0      # relative Groesse am USD-Maximum (Anker)
    dd_pct_max = 0.0  # F1 (Fremd-Review 01.10.): MAXIMALES RELATIVES DD —
                      # getrennt fuehren wie drawdown._max_drawdown. Vorher
                      # ersetzte ein spaeterer groesserer USD-Rueckfall bei
                      # gewachsenem Konto einen frueheren groesseren
                      # PROZENTVerlust (1000->600->2000->1500 meldete 25 %
                      # statt 40 %) — genau die Zahl, die in die Schranke geht.
    offener_fluss = 0.0
    for _t, wert, messpunkt, flow_delta in curve:
        if not messpunkt:
            # F2: unvollstaendige Punkte sind keine Messpunkte — ihr Fluss
            # wird aber am naechsten Messpunkt gebucht (sonst zaehlte eine
            # Auszahlung in einer Kursluecke als Drawdown).
            offener_fluss += flow_delta
            continue
        flow_delta += offener_fluss
        offener_fluss = 0.0
        # Nutzer-Regel 05.10.2026: Auszahlungen sind keine Verluste — der
        # Peak wird um den Auszahlungsbetrag gesenkt (nie unter den Stand),
        # BEVOR der Rueckfall gezaehlt wird. Einzahlungen heben die Kurve
        # und damit den Peak ganz natuerlich.
        if flow_delta < 0:
            hoch = max(wert, hoch + flow_delta)
        if wert > hoch:
            hoch = wert
        rueckfall = hoch - wert
        if rueckfall > dd_usd:
            dd_usd = rueckfall
            dd_pct = (rueckfall / hoch * 100.0) if hoch > 0 else 0.0
        if hoch > 0:
            rel = rueckfall / hoch * 100.0
            if rel > dd_pct_max:
                dd_pct_max = rel

    offen_gesamt = punkte_mit_kurs + punkte_ohne_kurs
    # F5: Nenner = aktive Stunden laut Trade-Zeiten abzueglich Marktpausen
    # (bounded Bar-Luecken >= MARKTPAUSE_MIN_H fuer alle aktiven Symbole).
    # Der bisherige Nenner
    # (Bar-Stunden mit Aktivitaet) liess Datenloecher still verschwinden.
    soll_stunden = len(aktiv_laut_zeit) - len(pausen & aktiv_laut_zeit)
    if soll_stunden > 0 and soll_stunden > offen_gesamt:
        offen_gesamt = soll_stunden
    abdeckung = punkte_mit_kurs / offen_gesamt if offen_gesamt else 1.0
    # Verlaesslich nur mit vollstaendiger Floating-Basis: fehlende Kurse
    # oder Kontrakte lassen das realisierte Netto zwar erhalten, aber
    # deren offene Belastung ist nicht belegt. Bis zu 20 % der Trades
    # durften frueher still verschwinden, waehrend die 95-%-Abdeckungspruefung
    # nur Rasterpunkte offener Positionen zählte (Review 29.09., Befund 7).
    trades_vollstaendig = len(nutzbare) == len(trades)
    verlaesslich = (abdeckung >= SCHRANKE_MIN_ABDECKUNG and not fx_fehlt
                    and trades_vollstaendig and zeitbasis.verlaesslich)

    # Nutzer-Regel 04.10. nachts: Fehlende Kurse EINZELNER Symbole werfen
    # das Signal nicht mehr aus der Max-Drawdown-Bewertung — gemessen wird
    # auf den betrachtbaren Symbolen (Teil-Messung), die fehlenden werden
    # namentlich als Warnung gefuehrt (DD kann unterschaetzt sein). Hart
    # bleibt: FX-Luecke, Datenluecher betrachtbarer Symbole unter 95 %
    # Teil-Abdeckung und unzuverlaessige Zeitbasis.
    offen_teil = punkte_teil_mit_kurs + punkte_teil_ohne_kurs
    soll_teil = len(aktiv_laut_zeit_betrachtet) - len(pausen & aktiv_laut_zeit_betrachtet)
    if soll_teil > 0 and soll_teil > offen_teil:
        offen_teil = soll_teil
    abdeckung_teil = punkte_teil_mit_kurs / offen_teil if offen_teil else 1.0
    symbole_nicht_betrachtet = sorted(
        set(fehlende_symbole or []) | set(symbole_ohne_kontrakt or []))
    teilmessung = (not verlaesslich and bool(symbole_nicht_betrachtet)
                   and not fx_fehlt and abdeckung_teil >= SCHRANKE_MIN_ABDECKUNG
                   and zeitbasis.verlaesslich)
    if teilmessung:
        verlaesslich = True  # Nenner-freigabe; Kennzeichnung siehe unten

    ergebnis = {
        "test": "equity_rekonstruktion",
        "status": ("ok" if verlaesslich and trades_vollstaendig
                   and not teilmessung else
                   "ok_teilmessung" if teilmessung else "unvollstaendig"),
        "gmt_offset_h": original_offset // 3600,
        "gmt_trefferquote": gmt["trefferquote"],
        "gmt_pruefung": dict(gmt),
        "zeitbasis": zeitbasis.metadata(),
        # Bewertungs-/RetDD-Nenner ohne Anzeige-Rundung: 10,004 % darf
        # nicht als 10,00 % eine Effizienz von 10,001/10,00 >= 1 erzeugen.
        "equity_dd_pct_raw": max(dd_pct, dd_pct_max),
        "equity_dd_pct": round(max(dd_pct, dd_pct_max), 2),
        "equity_dd_pct_am_usd_max": round(dd_pct, 2),
        "equity_dd_pct_max_rel": round(dd_pct_max, 2),
        "equity_dd_usd": round(dd_usd, 2),
        "abdeckung_pct": round(abdeckung * 100, 1),
        "abdeckung_pct_raw": abdeckung * 100,
        "rasterpunkte": len(curve),
        "verlaesslich": verlaesslich,
        "symbole_mit_kursen": sorted(bars_je_symbol),
        "methodik": "virtuelle_trading_equity_h1_schlusskurse",
        "raster": "H1-Bar-Schluss (Bar-Ende), keine Intrabar-Extrema",
        "kapitalfluesse": ("reale Kontokurve: Ein-/Auszahlungen eingerechnet "
                           "(Auszahlungen erzeugen keinen Drawdown — Peak-Anpassung)"
                           if flows_sort else
                           "Startkapital; keine Kontobewegungen im Export "
                           "(virtuelle Kurve, klar markiert)"),
        "positionsbasis": "nur abgeschlossene Positionen des Exports; aktuell offene fehlen",
        "end_equity_usd": round(curve[-1][1], 2),
        "trades_total": len(trades),
        "trades_mit_kurs_und_kontrakt": len(nutzbare),
        "trades_ohne_h1_floating_messpunkt": sum(
            (_offen // 3600 + 1) * 3600 >= _schluss
            for _offen, _schluss, _trade in offen_sort),
        "marktpausen": {"heuristik": "symbolweise >=20h zwischen realen H1-Bars; alle aktiven Symbole pausiert",
                        "ausgenommene_aktive_stunden": len(pausen),
                        "belege": pausen_belege},
    }
    if teilmessung:
        ergebnis["teilmessung"] = True
        ergebnis["symbole_nicht_betrachtet"] = symbole_nicht_betrachtet
        ergebnis["abdeckung_betrachtete_pct"] = round(abdeckung_teil * 100, 1)
        ergebnis["teilmessung_hinweis"] = (
            "Max-Drawdown nur aus Symbolen MIT Kursen berechnet; nicht "
            "betrachtet: " + ", ".join(symbole_nicht_betrachtet)
            + " — DD kann unterschätzt sein.")
    if umrechnung.h1_cache:
        ergebnis["fx_umrechnungen"] = umrechnung.provenienz()
    if fehlende_symbole:
        ergebnis["symbole_ohne_kurse"] = fehlende_symbole
    if symbole_ohne_kontrakt:
        ergebnis["symbole_ohne_kontrakt"] = symbole_ohne_kontrakt
    if fx_fehlt:
        ergebnis["fx_luecke"] = True
    if not verlaesslich:
        gruende = []
        if abdeckung < SCHRANKE_MIN_ABDECKUNG:
            gruende.append(f"Abdeckung < {SCHRANKE_MIN_ABDECKUNG:.0%} "
                           f"(gerundet {abdeckung:.1%})")
        if fx_fehlt:
            gruende.append("EZB-Kurslücke")
        if not trades_vollstaendig:
            gruende.append(f"Kursdaten fehlen für {len(trades) - len(nutzbare)} "
                           f"von {len(trades)} Trades")
        if not zeitbasis.verlaesslich:
            gruende.extend(zeitbasis.metadata()["gruende"])
        ergebnis["grund"] = " · ".join(gruende)
    if include_curve:
        # Explicit opt-in for the separate no-flow model. Default reports and
        # their persisted forensic schema remain unchanged.
        ergebnis["_curve"] = curve
    return ergebnis
