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
import statistics

from . import fx_rates
from .forensics.equity_rekonstruktion import (
    GMT_KANDIDATEN_S,
    MARKTPAUSE_MIN_H,
    _epoch,
    ermittle_gmt_offset,
)
from .forensics.exposure import _resolve_symbol

# Ein Symbol braucht mindestens so viele Trade-Proben, um seinen GMT-Versatz
# SELBST zu belegen; darunter (oder bei Mehrdeutigkeit) greift der Median der
# erkannten Symbole, offengelegt im Befund.
MIN_EIGENE_PROBEN = 5


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
        proben_je[s] = len(proben)
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
           broker: str | None = None, progress=None) -> dict:
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
    gmt = ermittle_gmt_je_symbol(trades, bars_je_symbol)
    offsets = gmt["offsets"]

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

    # Raster: gemeinsame Bar-Stunden aller genutzten Symbole im Trade-Fenster.
    erste = min(_raster_stunde(_epoch(t.open_time), offsets[t.symbol.strip().upper()])
                for t in nutzbare)
    letzte = max(_raster_stunde(_epoch(t.close_time), offsets[t.symbol.strip().upper()])
                 for t in nutzbare)
    raster = sorted({(b["time"] // 3600) * 3600
                     for bars in bars_je_symbol.values() for b in bars
                     if erste <= ((b["time"] // 3600) * 3600) <= letzte + 3600})
    if not raster:
        return {"status": "skipped", "grund": "keine H1-Bars im Trade-Zeitraum",
                "punkte": [], "symbole": gmt["befunde"], "kennzahlen": {}}

    closes_je_symbol = {s: {(b["time"] // 3600) * 3600: b["close"]
                            for b in bars} for s, bars in bars_je_symbol.items()}

    schliessungen = sorted(
        ((_raster_stunde(_epoch(t.close_time), offsets[t.symbol.strip().upper()]),
          t.net) for t in nutzbare), key=lambda x: x[0])
    offen_sort = sorted(
        ((_raster_stunde(_epoch(t.open_time), offsets[t.symbol.strip().upper()]),
          _raster_stunde(_epoch(t.close_time), offsets[t.symbol.strip().upper()]),
          t) for t in nutzbare), key=lambda x: (x[0], x[1]))

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
    punkte: list[dict] = []
    realisiert = 0.0
    schliess_idx = 0
    offen_idx = 0
    aktiv: list = []
    punkte_mit_kurs = 0
    punkte_ohne_kurs = 0

    aktiv_laut_zeit: set[int] = set()
    for _offen, _ende, _t in offen_sort:
        aktiv_laut_zeit.update(range(_offen, _ende, 3600))
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
    datenluecken = sorted(s for s in aktiv_laut_zeit
                          if s not in bar_stunden and s not in pausen)
    if datenluecken:
        raster = sorted(bar_stunden | set(datenluecken))

    basis = float(startkapital or 0.0)
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
        # Tag im Broker-Raum (Trade-Zeiten) für den EZB-Referenzkurs.
        tag = dt.datetime.fromtimestamp(punkt - median_offset, dt.timezone.utc).date()
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
    hoch = None
    dd_usd = 0.0
    dd_pct_am_usd_max = 0.0
    dd_pct_max_rel = 0.0
    dd_von = dd_bis = None
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
    }

    _p(1.0, "fertig")
    return {
        "status": "ok",
        "punkte": punkte,
        "symbole": gmt["befunde"],
        "kennzahlen": kennzahlen,
        "median_gmt_h": median_offset // 3600,
        "symbole_ohne_kurse": ohne_kurse,
        "symbole_ohne_kontrakt": ohne_kontrakt,
    }
