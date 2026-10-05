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

from .. import fx_rates
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
        for von in range(erste, letzte, 7 * 86400):
            lokal = gruppen.get(von, [])
            counts, _ = _preis_scores(lokal, bars_je_symbol, maps)
            best = max(counts.values()) if lokal else 0
            kandidaten = {s for s, n in counts.items() if n == best} if lokal else set()
            quote = best / len(lokal) if lokal else None
            stark = (len(lokal) >= GMT_LOKAL_MIN_PROBEN and len(kandidaten) == 1
                     and quote >= GMT_LOKAL_MIN_TREFFER)
            belegt = self.global_belegt
            shift = self.global_offset_s
            status = "global_kompatibel"
            if manuell:
                status = "manuell"
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
            elif lokal or previous != self.global_offset_s:
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
                belegt = True
            self.perioden.append({"von_t": von, "bis_t": von + 7 * 86400,
                                  "offset_s": shift, "belegt": belegt,
                                  "preisproben": len(lokal), "trefferquote": quote,
                                  "status": status})
            previous = shift
        self.variable = len({p["offset_s"] for p in self.perioden}) > 1
        events = sorted({_epoch(zeit) for t in trades
                         for zeit in (t.open_time, t.close_time)})
        mapped = [self.nach_referenz(zeit) for zeit in events]
        self.monoton = all(a <= b for a, b in zip(mapped, mapped[1:]))
        if not self.monoton:
            self.gruende.append("Ereignisabbildung nicht monoton/eindeutig")
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
        return result

    def metadata(self):
        return {
            "modus": "manuell" if self.manuell else "wochenweise" if self.variable else "konstant",
            "frame": "referenzkurszeit" if self.variable else "broker",
            "global_gmt_h": self.global_offset_s // 3600,
            "global_belegt": self.global_belegt,
            "verlaesslich": self.verlaesslich,
            "monoton": self.monoton,
            "offene_wechsel_annahmen": self.offene_wechsel_annahmen,
            "unsichere_innenperioden": self.unsichere_innenperioden,
            "annahme": "Kalenderwochengrenzen sind Modellgrenzen, kein exakter DST-Beleg",
            "unsichere_trade_ereignisse": self.unsichere_trade_ereignisse,
            "gruende": list(dict.fromkeys(self.gruende)),
            "perioden": [{"von_t": p["von_t"], "bis_t": p["bis_t"],
                           "von": dt.datetime.fromtimestamp(p["von_t"], dt.timezone.utc).isoformat(),
                           "bis": dt.datetime.fromtimestamp(p["bis_t"], dt.timezone.utc).isoformat(),
                           "gmt_h": p["offset_s"] // 3600, "belegt": p["belegt"],
                           "preisproben": p["preisproben"],
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


def ermittle_gmt_offset(trades, bars_je_symbol: dict[str, list[dict]],
                        max_proben: int = 60) -> dict:
    """Shift Signal-Broker → Referenz-Terminal per Preisabgleich.

    trades: Objekte mit open_time/close_time (naiv), entry_price/exit_price,
    symbol. Rückgabe {"offset_s", "trefferquote", "proben"} — offset_s None,
    wenn unter GMT_MIN_TREFFER.
    """
    proben = [t for t in trades
              if t.entry_price and t.exit_price and t.open_time and t.close_time]
    if len(proben) > max_proben:
        schritt = len(proben) / max_proben
        proben = [proben[int(i * schritt)] for i in range(max_proben)]
    if not proben:
        return {"offset_s": None, "trefferquote": 0.0, "proben": 0}

    events = _preisproben(proben)
    counts, _maps = _preis_scores(events, bars_je_symbol)
    quotes = {shift: count / len(events) if events else 0.0
              for shift, count in counts.items()}
    if not quotes or max(quotes.values()) < GMT_MIN_TREFFER:
        return {"offset_s": None,
                "trefferquote": round(max(quotes.values()), 3) if quotes else 0.0,
                "proben": len(proben)}
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
                "plateau_h": [s // 3600 for s in plateau], "proben": len(proben)}
    bester_shift = plateau[0]
    return {"offset_s": bester_shift, "trefferquote": round(beste, 3),
            "proben": len(proben)}


def rekonstruiere(parsed, kurse, startkapital: float,
                  broker: str | None = None, *, gmt_offset_h: int | None = None) -> dict:
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
    for s in symbole:
        bars = kurse.hole_h1(s, fenster_von, fenster_bis)
        if bars:
            bars_je_symbol[s] = bars
        else:
            fehlende_symbole.append(s)

    # Nutzer-Wunsch 05.10.: ZWEITE Kursdatenquelle (MetaTrader) als Fallback.
    # MT5-Python ist pro Prozess ein Singleton — erst ALLE Symbole von der
    # primaeren Quelle laden, dann Terminal wechseln und NUR die fehlenden
    # Symbole erneut versuchen. Der Auto-GMT-Preisabgleich je Symbol stellt
    # den korrekten Zeitversatz DESSEN Feeds sicher (jeder MT5-Broker hat
    # seinen eigenen Server-Zeitversatz; die Kurse eines Symbols kommen
    # konsistent aus EINEM Feed — kein Mischbestand).
    if fehlende_symbole and hasattr(kurse, 'hat_weiteren_terminal')             and kurse.hat_weiteren_terminal():
        ok, msg = kurse.wechsle_terminal()
        if ok:
            noch_fehlend = []
            for s in fehlende_symbole:
                bars = kurse.hole_h1(s, fenster_von, fenster_bis)
                if bars:
                    bars_je_symbol[s] = bars
                else:
                    noch_fehlend.append(s)
            fehlende_symbole = noch_fehlend

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
                "verlaesslich": False, "grund": "Zeitabbildung nicht monoton/eindeutig",
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
        ((_epoch(t.close_time) + offset, t.net) for t in trades),
        key=lambda x: x[0])

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

    fx_cache: dict[tuple[str, dt.date], float | None] = {}
    fx_fehlt = False

    def _usd_faktor(quote: str, tag: dt.date) -> float | None:
        if quote == "USD":
            return 1.0
        key = (quote, tag)
        if key not in fx_cache:
            kurs = fx_rates.usd_per(quote, tag)
            fx_cache[key] = kurs["rate"] if kurs else None
        return fx_cache[key]

    # Expliziter Anker vor dem ersten Handelsereignis: auch ein erster
    # Floating-Verlust darf nicht selbst zum Anfangshoch werden.
    curve: list[tuple[int, float, bool]] = [(anfang, float(startkapital), True)]
    realisiert = 0.0
    schliess_idx = 0
    offen_idx = 0
    aktiv: list = []           # (close_epoch_exklusiv, trade)
    punkte_mit_kurs = 0
    punkte_ohne_kurs = 0
    punkte_teil_mit_kurs = 0
    punkte_teil_ohne_kurs = 0
    # F5 (Fremd-Review 01.10.): Der Abdeckungs-Nenner darf nicht nur aus
    # vorhandenen Bar-Stunden bestehen — sonst verschwinden Datenlöcher
    # still aus der Rechnung (Probe: 8 offene Stunden, 3 mit Bars -> 100 %).
    # Nenner: jede volle Stunde, in der laut Trade-Zeiten eine Position
    # aktiv wäre, MINUS erkannte Marktpausen (globale Bar-Luecken >= 20 h,
    # klassisch Wochenende/Feiertag — solche Stunden sind keine Datenlücke).
    aktiv_laut_zeit: set[int] = set()
    aktiv_laut_zeit_betrachtet: set[int] = set()
    for _offen, _ende, _t in offen_sort:
        _stunden = set(range((_offen // 3600 + 1) * 3600, _ende, 3600))
        aktiv_laut_zeit.update(_stunden)
        if _t.symbol.strip().upper() in closes_je_symbol                 and _t.symbol.strip().upper() in aufgeloest:
            aktiv_laut_zeit_betrachtet.update(_stunden)
    bar_stunden: set[int] = set(raster)
    pausen: set[int] = set()
    if aktiv_laut_zeit and bar_stunden:
        erste = min(aktiv_laut_zeit)
        letzte = max(aktiv_laut_zeit)
        stunde = erste
        luecke: list[int] = []
        while stunde <= letzte:
            if stunde in bar_stunden:
                if len(luecke) >= MARKTPAUSE_MIN_H:
                    pausen.update(luecke)
                luecke = []
            elif stunde in aktiv_laut_zeit:
                luecke.append(stunde)
            stunde += 3600
        if len(luecke) >= MARKTPAUSE_MIN_H:
            pausen.update(luecke)

    for punkt in raster:
        while schliess_idx < len(schliessungen) and schliessungen[schliess_idx][0] <= punkt:
            realisiert += schliessungen[schliess_idx][1]
            schliess_idx += 1
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
            fx = _usd_faktor(res["quote"], tag)
            if fx is None:
                kurs_da = False
                fx_fehlt = True
                continue
            floating += pnl_quote * fx
        if aktiv:
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
        curve.append((punkt, startkapital + realisiert + floating, kurs_da))
        # Abbruch ERST NACH dem Anhängen: Der letzte Punkt (alles realisiert,
        # nichts mehr offen) trägt den Endkontostand — exakt dort entsteht der
        # finale Verlust. Der frühere break davor ließ echte Schlussverluste
        # als 0 % DD durchgehen (Review 29.09., Befund 1).
        if not aktiv and schliess_idx >= len(schliessungen) \
                and offen_idx >= len(offen_sort):
            break

    if len(curve) < 2:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "zu wenige Rasterpunkte mit Kursen"}

    # L14 (Review-Handoff 29.09.): Ein NaN/Inf in der Kurve (Kursdaten-
    # Fehler) wuerde den Rueckfallvergleich still falsch machen und am Ende
    # "0 % DD" melden — ohne dass verlaesslich es abfingt. Nicht endliche
    # Werte = Reko unbrauchbar -> ehrlich skippen statt Schoenrechnen.
    if not all(math.isfinite(wert) for _t, wert, _m in curve):
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
    for _t, wert, messpunkt in curve:
        if not messpunkt:
            continue   # F2: unvollstaendige Punkte sind keine Messpunkte
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
    # (globale Bar-Luecken >= MARKTPAUSE_MIN_H). Der bisherige Nenner
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
        "zeitbasis": zeitbasis.metadata(),
        # Bewertungs-/RetDD-Nenner ohne Anzeige-Rundung: 10,004 % darf
        # nicht als 10,00 % eine Effizienz von 10,001/10,00 >= 1 erzeugen.
        "equity_dd_pct_raw": max(dd_pct, dd_pct_max),
        "equity_dd_pct": round(max(dd_pct, dd_pct_max), 2),
        "equity_dd_pct_am_usd_max": round(dd_pct, 2),
        "equity_dd_pct_max_rel": round(dd_pct_max, 2),
        "equity_dd_usd": round(dd_usd, 2),
        "abdeckung_pct": round(abdeckung * 100, 1),
        "rasterpunkte": len(curve),
        "verlaesslich": verlaesslich,
        "symbole_mit_kursen": sorted(bars_je_symbol),
        "methodik": "virtuelle_trading_equity_h1_schlusskurse",
        "raster": "H1-Bar-Schluss (Bar-Ende), keine Intrabar-Extrema",
        "kapitalfluesse": "Startkapital; spaetere Ein-/Auszahlungen nicht eingerechnet",
        "positionsbasis": "nur abgeschlossene Positionen des Exports; aktuell offene fehlen",
        "end_equity_usd": round(curve[-1][1], 2),
        "trades_total": len(trades),
        "trades_mit_kurs_und_kontrakt": len(nutzbare),
        "trades_ohne_h1_floating_messpunkt": sum(
            (_offen // 3600 + 1) * 3600 >= _schluss
            for _offen, _schluss, _trade in offen_sort),
    }
    if teilmessung:
        ergebnis["teilmessung"] = True
        ergebnis["symbole_nicht_betrachtet"] = symbole_nicht_betrachtet
        ergebnis["abdeckung_betrachtete_pct"] = round(abdeckung_teil * 100, 1)
        ergebnis["teilmessung_hinweis"] = (
            "Max-Drawdown nur aus Symbolen MIT Kursen berechnet; nicht "
            "betrachtet: " + ", ".join(symbole_nicht_betrachtet)
            + " — DD kann unterschätzt sein.")
    if fehlende_symbole:
        ergebnis["symbole_ohne_kurse"] = fehlende_symbole
    if symbole_ohne_kontrakt:
        ergebnis["symbole_ohne_kontrakt"] = symbole_ohne_kontrakt
    if fx_fehlt:
        ergebnis["fx_luecke"] = True
    if not verlaesslich:
        gruende = []
        if abdeckung < SCHRANKE_MIN_ABDECKUNG:
            gruende.append(f"Abdeckung {abdeckung:.0%} < {SCHRANKE_MIN_ABDECKUNG:.0%}")
        if fx_fehlt:
            gruende.append("EZB-Kurslücke")
        if not trades_vollstaendig:
            gruende.append(f"Kursdaten fehlen für {len(trades) - len(nutzbare)} "
                           f"von {len(trades)} Trades")
        if not zeitbasis.verlaesslich:
            gruende.extend(zeitbasis.metadata()["gruende"])
        ergebnis["grund"] = " · ".join(gruende)
    return ergebnis
