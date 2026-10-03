# -*- coding: utf-8 -*-
"""Equity-DD-Studie: interaktive Nachmessung je Signal (Nutzer-Wunsch 03.10.2026).

Gleiche Messidee wie forensics/equity_rekonstruktion (Equity-Kurve auf H1-Raster
mit realisiertem UND floating PnL), aber als ON-DEMAND-Studie für die GUI:

- Der GMT-Abgleich läuft JE WÄHRUNGSPAAR (Nutzer-Wunsch). Eigentlich teilen
  sich alle Symbole eines Brokers dieselbe Serverzeit — die einzelne Erkennung
  ist trotzdem robuster, weil ein Symbol mit klaren Proben den Versatz auch
  dann belegt, wenn andere Symbole dünne Daten haben. Symbole mit zu wenigen
  Proben oder Mehrdeutigkeit (Plateau) bekommen den Median der erkannten
  Symbole als Fallback — offengelegt im Befund, nie still.
- Die Kurve wird STUNDENFEIN MITGEGEBEN (realisiert / floating / equity) für
  die grafische Darstellung; die produktive Reko liefert nur die Zusammen-
  fassung und bleibt hier bewusst unangetastet (Produktivpfad + Tests).
- Fehlende Kurse sind kein Abbruchkriterium: gerechnet wird für alle Symbole
  mit Kursen + belegtem Kontrakt, und JE fehlendes Symbol wird namentlich
  gemeldet (inkl. Folgehinweis, dass der DD ohne diese Symbole unterschätzt
  sein kann). Punktweise Kurslücken (Datenloch in einer einzelnen Stunde)
  unterbrechen die Equity-Spur ehrlich als Lücke; die Realisiert-Spur läuft
  durch, denn sie braucht keine Kurse.

Bewertet wird hier nichts (keine Ampel, kein Score) — die Studie misst und
zeigt; verbindlich bleibt die Engine.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

from . import fx_rates
from .forensics.equity_rekonstruktion import (
    GMT_KANDIDATEN_S,
    MARKTPAUSE_MIN_H,
    _epoch,
    ermittle_gmt_offset,
    Zeitbasis,
)
from .forensics.exposure import _resolve_symbol
from .forensics.equity_kapitalfluesse import diagnostik as konto_diagnostik

# Ein Symbol braucht so viele Trade-Proben, um seinen GMT-Versatz SELBST zu
# belegen; darunter (oder bei Mehrdeutigkeit) greift der Median der erkannten
# Symbole, offengelegt im Befund. Nutzer-Regel 03.10.: DREI stimmende,
# eindeutige Proben genügen — der Versatz wechselt nur zum Sommer-/Winterzeit-
# Termin (vorher 5; Konsistenz mit GMT_LOKAL_MIN_PROBEN der Reko).
MIN_EIGENE_PROBEN = 3


def _raster_stunde(epoch_s: int, offset_s: int) -> int:
    """Trade-Epoch + GMT-Shift, auf die volle Stunde normiert."""
    return ((epoch_s + offset_s) // 3600) * 3600


def ermittle_gmt_je_symbol(trades, bars_je_symbol: dict[str, list[dict]]) -> dict:
    """GMT-Versatz JE Symbol mit Median-Fallback für dünne/mehrdeutige Symbole.

    Ein Symbol belegt den Versatz EIGENSTÄNDIG erst mit genug Proben
    (MIN_EIGENE_PROBEN) — ein einzelner Trade kann zufällig in mehreren
    Versatz-Kandidaten liegen. Existiert mindestens ein starkes Symbol,
    bekommen dünn belegte oder mehrdeutige Symbole dessen Median (offen-
    gelegt); ohne jedes starke Symbol greift notfalls die dünne eigene
    Erkennung (besser als gar nichts, mit Hinweis).
    Rückgabe {"offsets": {symbol: sekunden}, "befunde": [ {symbol, gmt_h,
    trefferquote, status, hinweis} ]}. status: "erkannt" | "fallback_median"
    | "plateau" | "zu_wenig_proben" | "nicht_erkannt" | "keine_kurse".
    """
    je_symbol: dict[str, list] = {}
    for t in trades:
        s = t.symbol.strip().upper()
        je_symbol.setdefault(s, []).append(t)

    roh: dict[str, dict] = {}
    proben_je: dict[str, int] = {}
    ohne_bars: list[str] = []
    for s in sorted(je_symbol):
        proben = [t for t in je_symbol[s]
                  if t.entry_price and t.exit_price and t.open_time and t.close_time]
        # Proben = PREISEREIGNISSE (Open+Close, dedupliziert) — dieselbe
        # Zählweise wie die Wochenlogik der Reko (_preisproben). Nutzer-Regel
        # 03.10.: 3 stimmende Ereignisse belegen den Versatz.
        ereignisse = {(t.open_time, t.entry_price) for t in proben} \
            | {(t.close_time, t.exit_price) for t in proben}
        proben_je[s] = len(ereignisse)
        if not bars_je_symbol.get(s):
            ohne_bars.append(s)
            continue
        roh[s] = ermittle_gmt_offset(proben, {s: bars_je_symbol[s]})

    starke = {s: int(e["offset_s"]) for s, e in roh.items()
              if e.get("offset_s") is not None
              and proben_je[s] >= MIN_EIGENE_PROBEN}
    median_s = int(statistics.median(starke.values())) if starke else None

    offsets: dict[str, int] = {}
    befunde: list[dict] = []
    for s in sorted(je_symbol):
        if s in ohne_bars:
            befunde.append({"symbol": s, "gmt_h": None, "trefferquote": None,
                            "status": "keine_kurse",
                            "hinweis": "keine H1-Kurse vom Referenzterminal"})
            continue
        e = roh[s]
        quote = e.get("trefferquote")
        eigen = e.get("offset_s")
        if eigen is not None and (proben_je[s] >= MIN_EIGENE_PROBEN
                                  or median_s is None):
            offsets[s] = int(eigen)
            hinweis = (f"nur {proben_je[s]} Proben — einziger Beleg, kein "
                       "starkes Symbol vorhanden"
                       if proben_je[s] < MIN_EIGENE_PROBEN else "")
            befunde.append({"symbol": s, "gmt_h": int(eigen) // 3600,
                            "trefferquote": quote, "status": "erkannt",
                            "hinweis": hinweis})
        elif median_s is not None:
            offsets[s] = median_s
            ursache = ("mehrere Versätze treffen gleich gut" if e.get("plateau_h")
                       else f"nur {proben_je[s]} belegbare Proben"
                       if proben_je[s] < MIN_EIGENE_PROBEN
                       else "Preisabgleich unter der Mindestquote")
            befunde.append({"symbol": s, "gmt_h": median_s // 3600,
                            "trefferquote": quote, "status": "fallback_median",
                            "hinweis": (f"{ursache} — Median der erkannten "
                                        f"Symbole ({median_s // 3600:+d} h)")})
        elif e.get("plateau_h"):
            befunde.append({"symbol": s, "gmt_h": None, "trefferquote": quote,
                            "status": "plateau",
                            "hinweis": "mehrere Versätze treffen gleich gut"})
        elif proben_je[s] < MIN_EIGENE_PROBEN:
            befunde.append({"symbol": s, "gmt_h": None, "trefferquote": quote,
                            "status": "zu_wenig_proben",
                            "hinweis": f"nur {proben_je[s]} belegbare Proben"})
        else:
            befunde.append({"symbol": s, "gmt_h": None, "trefferquote": quote,
                            "status": "nicht_erkannt",
                            "hinweis": "Preisabgleich unter der Mindestquote"})
    return {"offsets": offsets, "befunde": befunde}


def studie(parsed, kurse, startkapital: float,
           broker: str | None = None, progress=None, *,
           gmt_offset_h: int | None = None) -> dict:
    """Equity-Studie mit Kurven-Punkten für die grafische Darstellung.

    kurse: Anbieter mit hole_h1(symbol, von, bis) (kursdaten.KursDaten oder
    FakeKursDaten). progress: optional callback(anteil_0_1, text).
    Rückgabe siehe Modul-Docstring; status "skipped" mit grund, wenn keine
    nutzbare Basis (keine Trades / keine Kurse an irgendeinem Symbol).
    """
    def _p(anteil: float, text: str) -> None:
        if progress is not None:
            progress(max(0.0, min(1.0, anteil)), text)

    trades = [t for t in parsed.trades if t.close_time and t.open_time]
    if not trades:
        return {"status": "skipped", "grund": "keine geschlossenen Trades",
                "punkte": [], "symbole": [], "kennzahlen": {}}
    symbole = sorted({t.symbol.strip().upper() for t in trades if t.symbol})

    von = min(_epoch(t.open_time) for t in trades)
    bis = max(_epoch(t.close_time) for t in trades) + 3600
    fenster_von = von + min(GMT_KANDIDATEN_S)
    fenster_bis = bis + max(GMT_KANDIDATEN_S)

    # Kurse je Symbol (weitestes Fenster deckt alle GMT-Kandidaten ab — ein
    # Abruf je Symbol, das Raster wird daraus abgeleitet).
    bars_je_symbol: dict[str, list[dict]] = {}
    ohne_kurse: list[str] = []
    for i, s in enumerate(symbole):
        _p(0.15 + 0.55 * i / max(1, len(symbole)),
           f"Kurse laden ({i + 1}/{len(symbole)}): {s}")
        bars = kurse.hole_h1(s, fenster_von, fenster_bis)
        if bars:
            bars_je_symbol[s] = bars
        else:
            ohne_kurse.append(s)

    # Kontrakt-/Quote-Auflösung — NUR mit Beleg (kein erfundener Faktor;
    # dieselbe Regel wie die produktive Reko, Review 29.09. Befund 4).
    aufgeloest: dict[str, dict] = {}
    ohne_kontrakt: list[str] = []
    for s in bars_je_symbol:
        spec = _resolve_symbol(s, broker)
        if spec is not None:
            aufgeloest[s] = spec
        else:
            ohne_kontrakt.append(s)

    _p(0.72, "GMT-Versatz je Währungspaar ermitteln …")
    if gmt_offset_h is not None and (isinstance(gmt_offset_h, bool)
                                    or not isinstance(gmt_offset_h, int)
                                    or gmt_offset_h * 3600 not in GMT_KANDIDATEN_S):
        raise ValueError("Manueller GMT-Versatz muss eine ganze Stunde zwischen -14 und +14 sein")
    gmt = (ermittle_gmt_je_symbol(trades, bars_je_symbol)
           if gmt_offset_h is None else {
               "offsets": {s: gmt_offset_h * 3600 for s in bars_je_symbol},
               "befunde": [{"symbol": s, "gmt_h": gmt_offset_h,
                            "trefferquote": None, "status": "manuell", "hinweis": ""}
                           for s in bars_je_symbol]})
    offsets = gmt["offsets"]
    lokale_basis = None
    if not offsets:
        lokale_basis = Zeitbasis(trades, bars_je_symbol, None)
        if lokale_basis.hat_basis:
            offsets = {s: lokale_basis.global_offset_s for s in bars_je_symbol}
            gmt["befunde"] = [{"symbol": s, "gmt_h": lokale_basis.global_offset_s // 3600,
                               "trefferquote": None, "status": "zeitabschnitte",
                               "hinweis": "Globale Erkennung unklar; lokale Preisabschnitte"}
                              for s in bars_je_symbol]

    nutzbare = [t for t in trades
                if t.symbol.strip().upper() in aufgeloest
                and t.symbol.strip().upper() in offsets]
    if not nutzbare:
        gruende = []
        if ohne_kurse:
            gruende.append("keine Kurse: " + ", ".join(ohne_kurse))
        if ohne_kontrakt:
            gruende.append("Kontrakt unbelegt: " + ", ".join(ohne_kontrakt))
        if not gruende:
            gruende.append("GMT-Versatz für kein Symbol bestimmbar")
        return {"status": "skipped",
                "grund": " · ".join(gruende),
                "punkte": [], "symbole": gmt["befunde"], "kennzahlen": {}}

    median_offset = int(statistics.median(offsets.values()))
    original_median = median_offset
    zeitbasis = (lokale_basis if lokale_basis is not None and lokale_basis.hat_basis else
                 Zeitbasis(trades, bars_je_symbol, median_offset,
                           manuell=gmt_offset_h is not None))
    if not zeitbasis.monoton:
        return {"status": "skipped", "grund": "Zeitabbildung nicht monoton/eindeutig",
                "punkte": [], "symbole": gmt["befunde"], "kennzahlen": {},
                "zeitbasis": zeitbasis.metadata()}
    gemeinsame_zeitbasis = len(set(offsets.values())) == 1
    if zeitbasis.variable and gemeinsame_zeitbasis:
        parsed = zeitbasis.normalisiere(parsed)
        trades = [t for t in parsed.trades if t.close_time and t.open_time]
        offsets = {s: 0 for s in offsets}
        median_offset = 0
    elif not gemeinsame_zeitbasis:
        zeitbasis.verlaesslich = False
        zeitbasis.gruende.append("Uneinheitliche Symbol-Zeitversaetze")

    # Ein H1-Close gilt am BAR-ENDE. Fehlende Symbole verlieren ihr
    # exportiertes Netto nicht: ohne eigenen GMT-Beleg gilt fuer die
    # Ereignisse der offengelegte Broker-Median; Floating bleibt eine Luecke.
    def _shift(t):
        return offsets.get(t.symbol.strip().upper(), median_offset)

    erste = min(_epoch(t.open_time) + _shift(t) for t in trades)
    letzte = max(_epoch(t.close_time) + _shift(t) for t in trades)
    endpunkt = ((letzte + 3599) // 3600) * 3600
    raster = sorted({(b["time"] // 3600 + 1) * 3600
                     for bars in bars_je_symbol.values() for b in bars
                     if erste < ((b["time"] // 3600 + 1) * 3600) <= endpunkt})
    if not raster:
        return {"status": "skipped", "grund": "keine H1-Bars im Trade-Zeitraum",
                "punkte": [], "symbole": gmt["befunde"], "kennzahlen": {}}

    raster = sorted(set(raster) | {endpunkt})
    closes_je_symbol = {s: {(b["time"] // 3600 + 1) * 3600: b["close"]
                            for b in bars} for s, bars in bars_je_symbol.items()}

    schliessungen = sorted(
        ((_epoch(t.close_time) + _shift(t), t.net) for t in trades),
        key=lambda x: x[0])
    offen_sort = sorted(
        ((_epoch(t.open_time) + _shift(t),
          _epoch(t.close_time) + _shift(t), t) for t in trades),
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

    _p(0.78, "Equity-Kurve je Stunde rechnen …")
    basis = float(startkapital or 0.0)
    # Anker unmittelbar vor dem ersten MESSBAREN Punkt: Hat das Referenz-
    # Terminal eine kürzere Historie als das Signal (Trades liegen vor der
    # ersten verfügbaren Bar), zöge ein Anker beim ersten Trade die Kurve
    # in einen toten Zeitbereich und die eigentliche Kurve auf einen
    # schmalen Streifen (Nutzer-Feedback 03.10.). Das realisierte Netto der
    # Vorzeit bleibt erhalten: alle Schließungen bis zum ersten Rasterpunkt
    # gehen in den Anker ein; nur ihr zwischenzeitliches Floating ist —
    # ohne Kurse ehrlich — nicht messbar.
    anker_t = erste
    anker_stand = basis
    if raster and raster[0] - erste > 2 * 24 * 3600:
        anker_t = raster[0]
        anker_stand = basis + math.fsum(
            net for zeit, net in schliessungen if zeit <= raster[0])
    punkte: list[dict] = [{"t": anker_t - median_offset, "equity": anker_stand,
                          "realisiert": anker_stand, "floating": 0.0,
                          "messpunkt": True}]
    realisiert = 0.0
    schliess_idx = 0
    offen_idx = 0
    aktiv: list = []
    punkte_mit_kurs = 0
    punkte_ohne_kurs = 0

    aktiv_laut_zeit: set[int] = set()
    for _offen, _ende, _t in offen_sort:
        aktiv_laut_zeit.update(range((_offen // 3600 + 1) * 3600, _ende, 3600))
    bar_stunden: set[int] = {r for r in raster}
    pausen: set[int] = set()
    if aktiv_laut_zeit and bar_stunden:
        stunde, luecke = min(aktiv_laut_zeit), []
        endstunde = max(aktiv_laut_zeit)
        while stunde <= endstunde:
            if stunde in bar_stunden:
                if len(luecke) >= MARKTPAUSE_MIN_H:
                    pausen.update(luecke)
                luecke = []
            elif stunde in aktiv_laut_zeit:
                luecke.append(stunde)
            stunde += 3600
        if len(luecke) >= MARKTPAUSE_MIN_H:
            pausen.update(luecke)

    # Stunden mit offener Position, aber ohne Bar (und keine Marktpause):
    # als LÜCKEN-PUNKTE ins Raster nehmen — die Equity-Spur reißt an der
    # Stelle sichtbar (equity=None), statt still über die Stunde zu
    # springen. Wochenenden sind über die Pausen-Erkennung ausgenommen.
    # NUR INNERHALB des kursbelegten Fensters: Stunden VOR der ersten oder
    # NACH der letzten Bar sind toter Bereich (Referenzterminal hat kürzere
    # Historie als das Signal) — als Lückenpunkte würden sie die Zeitachse
    # auseinanderziehen und die Kurve auf einen Streifen quetschen
    # (Nutzer-Feedback 03.10.). Ihr realisiertes Netto trägt der Anker.
    if bar_stunden:
        fenster_anfang, fenster_ende = min(bar_stunden), max(bar_stunden)
        datenluecken = sorted(
            s for s in aktiv_laut_zeit
            if fenster_anfang <= s <= fenster_ende
            and s not in bar_stunden and s not in pausen)
        if datenluecken:
            raster = sorted(bar_stunden | set(datenluecken))

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
        # Tag im Broker-Raum (Trade-Zeiten) für den EZB-Referenzkurs.
        tag = (zeitbasis.broker_tag(punkt) if zeitbasis.variable and gemeinsame_zeitbasis else
               dt.datetime.fromtimestamp(punkt - median_offset, dt.timezone.utc).date())
        if aktiv and gemeinsame_zeitbasis and not (
                zeitbasis.referenz_sicher(punkt) if zeitbasis.variable else
                zeitbasis.periode(punkt - median_offset)["belegt"]):
            kurs_da = False
        for _ende, t in aktiv:
            s = t.symbol.strip().upper()
            close = closes_je_symbol.get(s, {}).get(punkt)
            if (close is None or not t.entry_price or s not in aufgeloest or s not in offsets
                    or not getattr(t, "_zeitbasis_sicher", True) or tag is None):
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
        punkte.append({
            "t": punkt - median_offset,          # Anzeige im Broker-Raum der Trades
            "equity": basis + realisiert + floating if kurs_da else None,
            "realisiert": basis + realisiert,    # braucht keine Kurse — immer da
            "floating": floating if kurs_da else None,
            "messpunkt": kurs_da,
        })
        if not aktiv and schliess_idx >= len(schliessungen) \
                and offen_idx >= len(offen_sort):
            break

    _p(0.92, "Kennzahlen ableiten …")
    if any(p["messpunkt"] and not math.isfinite(p["equity"]) for p in punkte):
        return {"status": "skipped", "grund": "NaN/Inf in der Equity-Kurve",
                "punkte": [], "symbole": gmt["befunde"], "kennzahlen": {}}
    hoch = None
    dd_usd = 0.0
    dd_pct_am_usd_max = 0.0
    dd_pct_max_rel = 0.0
    dd_von = dd_bis = None
    dd_rel_von = dd_rel_bis = None
    dd_usd_am_rel_max = 0.0
    floating_min = 0.0
    floating_min_t = None
    floating_max = 0.0
    hoch_t = None
    unter_wasser_seit = None
    unter_wasser_max_h = 0
    for p in punkte:
        if not p["messpunkt"]:
            continue
        wert = p["equity"]
        if hoch is None or wert > hoch:
            hoch = wert
            hoch_t = p["t"]
        rueckfall = hoch - wert
        if rueckfall > dd_usd:
            dd_usd = rueckfall
            dd_pct_am_usd_max = (rueckfall / hoch * 100.0) if hoch > 0 else 0.0
            dd_von, dd_bis = hoch_t, p["t"]
        if hoch > 0:
            rel = rueckfall / hoch * 100.0
            if rel > dd_pct_max_rel:
                dd_pct_max_rel = rel
                dd_usd_am_rel_max = rueckfall
                dd_rel_von, dd_rel_bis = hoch_t, p["t"]
        # Floating-Extreme nur mit offenen Positionen bewerten (floating=0
        # ohne offene Positionen ist kein Extremwert).
        if p["floating"] is not None:
            if p["floating"] < floating_min:
                floating_min = p["floating"]
                floating_min_t = p["t"]
            if p["floating"] > floating_max:
                floating_max = p["floating"]
        # Unterwasser-Dauer: Stunden zwischen letztem Hoch und Wiedererreichen.
        if wert < hoch:
            if unter_wasser_seit is None:
                unter_wasser_seit = hoch_t
            aktuell_h = (p["t"] - unter_wasser_seit) / 3600.0
            unter_wasser_max_h = max(unter_wasser_max_h, aktuell_h)
        else:
            unter_wasser_seit = None

    offen_gesamt = punkte_mit_kurs + punkte_ohne_kurs
    soll_stunden = len(aktiv_laut_zeit) - len(pausen & aktiv_laut_zeit)
    if soll_stunden > 0 and soll_stunden > offen_gesamt:
        offen_gesamt = soll_stunden
    abdeckung = punkte_mit_kurs / offen_gesamt if offen_gesamt else 1.0

    dd_pct = max(dd_pct_am_usd_max, dd_pct_max_rel)
    kapitalbasis_ok = basis is not None and basis > 0
    kennzahlen = {
        "startkapital": round(basis, 2),
        "equity_dd_usd": round(dd_usd, 2),
        "equity_dd_pct": round(dd_pct, 2) if kapitalbasis_ok else None,
        "dd_pct_am_usd_max": round(dd_pct_am_usd_max, 2) if kapitalbasis_ok else None,
        "dd_pct_max_rel": round(dd_pct_max_rel, 2) if kapitalbasis_ok else None,
        "dd_von": dd_von,
        "dd_bis": dd_bis,
        "dd_rel_von": dd_rel_von,
        "dd_rel_bis": dd_rel_bis,
        "dd_usd_am_rel_max": round(dd_usd_am_rel_max, 2),
        "floating_min_usd": round(floating_min, 2),
        "floating_min_t": floating_min_t,
        "floating_max_usd": round(floating_max, 2),
        "unterwasser_tage_max": round(unter_wasser_max_h / 24.0, 1),
        "abdeckung_pct": round(abdeckung * 100.0, 1),
        "rasterpunkte": len(punkte),
        "messpunkte": punkte_mit_kurs,
        "punkte_mit_luecke": punkte_ohne_kurs,
        "fx_luecke": fx_fehlt,
        "trades_total": len(trades),
        "trades_genutzt": len(nutzbare),
        "trades_realisiert": len(trades),
        "trades_ohne_h1_floating_messpunkt": sum(
            1 for o, c, _ in offen_sort if (o // 3600 + 1) * 3600 >= c),
        "verlaesslich": (basis > 0 and abdeckung >= 0.95 and not fx_fehlt
                         and len(nutzbare) == len(trades)
                         and gemeinsame_zeitbasis and zeitbasis.verlaesslich),
        "zeitbasis_einheitlich": gemeinsame_zeitbasis,
        "kapitalfluesse_nach_start": sum(
            1 for b in getattr(parsed, "balances", [])
            if b.time > min(t.open_time for t in trades)),
    }

    _p(1.0, "fertig")
    return {
        "status": "ok",
        "punkte": punkte,
        "symbole": gmt["befunde"],
        "kennzahlen": kennzahlen,
        "median_gmt_h": original_median // 3600,
        "zeitbasis": dict(zeitbasis.metadata(),
                          frame="referenzkurszeit" if zeitbasis.variable and gemeinsame_zeitbasis else "broker",
                          angewandt=gemeinsame_zeitbasis),
        "symbole_ohne_kurse": ohne_kurse,
        "symbole_ohne_kontrakt": ohne_kontrakt,
        "methodik": "virtuelle Trading-Equity: Startkapital + alle realisierten Nettoergebnisse + Floating",
        "raster": "H1-Schlusskurse am Bar-Ende; keine Intrabar-Extrema",
        "kapitalfluesse": "spaetere Ein-/Auszahlungen nicht eingerechnet",
        "positionsbasis": "geschlossene Exportpositionen; aktuell offene fehlen",
        "konto_studie": konto_diagnostik(
            parsed, punkte, bars_je_symbol, offsets, basis, broker=broker,
            zeitbasis=zeitbasis),
    }
