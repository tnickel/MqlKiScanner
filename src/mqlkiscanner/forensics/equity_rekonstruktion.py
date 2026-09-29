# -*- coding: utf-8 -*-
"""Equity-DD-Rekonstruktion aus Kursdaten (Nutzer-Wunsch 28.09.2026).

Der Broker-„By Equity"-Drawdown ist der wichtigste Risikowert — aber ein
SELBSTAUSKUNFTSWERT. Dieses Modul rechnet ihn aus der Trade-Historie NACH:
Auf einem H1-Raster wird die Equity-Kurve = Startkapital + realisierte
Gewinne + floating PnL der offenen Positionen (zum Bar-Close des jeweiligen
Symbols) geführt; der maximale Rückfall ist der rekonstruierte Equity-DD.

Auto-GMT (Nutzer-Idee): Trade-Zeiten sind Serverzeit des Signal-Brokers,
Kurszeiten Serverzeit des Referenz-Terminals. Der nötige Shift wird
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

    indizes = {s: _bar_index(b) for s, b in bars_je_symbol.items()}

    def _bar_fuer(symbol: str, epoch: int, shift: int) -> dict | None:
        # L4 (Review-Handoff 29.09.): Der Index ist UPPERCASE (symbole in
        # rekonstruiere sind .strip().upper()); der Aufruf kam bisher mit
        # dem ROHEN Symbol -> gemischte Schreibweise lief idx=None, die
        # Probe wurde still uebersprungen und die Auto-GMT-Erkennung konnte
        # unter die Mindest-Trefferquote rutschen -> Reko unnoetig skipped.
        idx = indizes.get(symbol.strip().upper())
        if idx is None:
            return None
        zeiten, mappe = idx
        stunde = (epoch + shift) // 3600 * 3600
        # L6: EXAKTER Lookup wie auf der Kurvenseite — bisect-1 lieferte bei
        # fehlender Stunde (Wochenende/Feiertag) die VORHERIGE Bar und
        # behandelte deren Close als Kurs dieser Stunde (verzerrte Treffer-
        # quote und Punkt-Preise).
        return mappe.get(stunde)

    quotes: dict[int, float] = {}
    for shift in GMT_KANDIDATEN_S:
        treffer = 0
        checks = 0
        for t in proben:
            bar_o = _bar_fuer(t.symbol, _epoch(t.open_time), shift)
            bar_c = _bar_fuer(t.symbol, _epoch(t.close_time), shift)
            for bar, preis in ((bar_o, t.entry_price), (bar_c, t.exit_price)):
                if bar is None or not preis:
                    continue
                checks += 1
                tol = abs(preis) * _PREIS_TOLERANZ + 1e-12
                if bar["low"] - tol <= preis <= bar["high"] + tol:
                    treffer += 1
        quotes[shift] = treffer / checks if checks else 0.0
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
                  broker: str | None = None) -> dict:
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

    gmt = ermittle_gmt_offset(nutzbare, bars_je_symbol)
    offset = gmt["offset_s"]
    if offset is None:
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

    # Raster aus dem bereits geladenen Superset-Fenster ableiten (deckt alle
    # GMT-Shifts ab) — KEIN zusaetzlicher Kursabruf. Normierung auf H1
    # (Bar-Anfangsstunde).
    raster: list[int] = sorted({(b["time"] // 3600) * 3600
                                for bars in bars_je_symbol.values() for b in bars})
    if not raster:
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "keine H1-Bars im Zeitraum"}
    closes_je_symbol: dict[str, dict[int, float]] = {}
    for s, bars in bars_je_symbol.items():
        closes_je_symbol[s] = {(b["time"] // 3600) * 3600: b["close"] for b in bars}

    # Realisierte PnL kumulieren (Close-Zeit + Offset im Terminal-Raum).
    schliessungen = sorted(
        ((  ( (_epoch(t.close_time) + offset) // 3600) * 3600, t.net) for t in nutzbare),
        key=lambda x: x[0])

    # Offene Positionen je Rasterpunkt auswerten.
    # Vorbereitung: Trades nach Open sortiert für Sliding-Window. Das Ende
    # wird AUF DIE STUNDE GERUNDET — schliessungen rundet ebenso: Ein Schluss
    # 10:20 wäre sonst bei Rasterpunkt 10:00 gleichzeitig realisiert UND
    # floating verbucht (Doppelbuchung, verfälschter Peak; Review 29.09.,
    # Befund 2).
    offen_sort = sorted(
        (( (_epoch(t.open_time) + offset) // 3600) * 3600,
         ((_epoch(t.close_time) + offset) // 3600) * 3600, t) for t in nutzbare)

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

    curve: list[tuple[int, float]] = []
    realisiert = 0.0
    schliess_idx = 0
    offen_idx = 0
    aktiv: list = []           # (end_epoch_stunde_exklusiv, trade)
    punkte_mit_kurs = 0
    punkte_ohne_kurs = 0

    for punkt in raster:
        while schliess_idx < len(schliessungen) and schliessungen[schliess_idx][0] <= punkt:
            realisiert += schliessungen[schliess_idx][1]
            schliess_idx += 1
        while offen_idx < len(offen_sort) and offen_sort[offen_idx][0] <= punkt:
            aktiv.append((offen_sort[offen_idx][1], offen_sort[offen_idx][2]))
            offen_idx += 1
        aktiv = [a for a in aktiv if a[0] > punkt]
        floating = 0.0
        kurs_da = True
        tag = dt.datetime.fromtimestamp(punkt - offset, dt.timezone.utc).date()
        for _ende, t in aktiv:
            s = t.symbol.strip().upper()
            close = closes_je_symbol.get(s, {}).get(punkt)
            if close is None or not t.entry_price:
                kurs_da = False
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
        curve.append((punkt, startkapital + realisiert + floating))
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
    if not all(math.isfinite(wert) for _t, wert in curve):
        return {"test": "equity_rekonstruktion", "status": "skipped",
                "grund": "NaN/Inf in der Equity-Kurve (Kursdaten unbrauchbar)"}

    hoch = curve[0][1]
    dd_usd = 0.0
    dd_pct = 0.0
    for _t, wert in curve:
        hoch = max(hoch, wert)
        rueckfall = hoch - wert
        if rueckfall > dd_usd:
            dd_usd = rueckfall
            dd_pct = (rueckfall / hoch * 100.0) if hoch > 0 else 0.0

    offen_gesamt = punkte_mit_kurs + punkte_ohne_kurs
    abdeckung = punkte_mit_kurs / offen_gesamt if offen_gesamt else 1.0
    # Verlässlich nur mit vollständiger Basis: Fehlen Trades (Kurse ODER
    # Kontrakt), fehlt deren PnL in Equity UND realisiert — bis zu 20 %
    # durften bisher still verschwinden, während die 95-%-Abdeckungsprüfung
    # nur Rasterpunkte offener Positionen zählte (Review 29.09., Befund 7).
    trades_vollstaendig = len(nutzbare) == len(trades)
    verlaesslich = (abdeckung >= SCHRANKE_MIN_ABDECKUNG and not fx_fehlt
                    and trades_vollstaendig)

    ergebnis = {
        "test": "equity_rekonstruktion",
        "status": "ok" if verlaesslich else "unvollstaendig",
        "gmt_offset_h": offset // 3600,
        "gmt_trefferquote": gmt["trefferquote"],
        "equity_dd_pct": round(dd_pct, 2),
        "equity_dd_usd": round(dd_usd, 2),
        "abdeckung_pct": round(abdeckung * 100, 1),
        "rasterpunkte": len(curve),
        "verlaesslich": verlaesslich,
        "symbole_mit_kursen": sorted(bars_je_symbol),
    }
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
        ergebnis["grund"] = " · ".join(gruende)
    return ergebnis
