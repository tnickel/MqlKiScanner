# -*- coding: utf-8 -*-
"""Lesende Konto-Equity-Diagnostik neben der virtuellen H1-Trading-Kurve.

Kapitalfluesse veraendern die gehaltenen Anteile, nicht deren Kurs. Zur
Neutralisierung eines Flows wird die Equity unmittelbar DAVOR benoetigt.
Bei offenen Positionen ist sie aus H1-Schlusskursen nur approximativ
bekannt: ausschliesslich bereits abgeschlossene Bars, niemals Lookahead.
Diese Diagnostik darf einen virtuellen Schrankenwert nicht verkleinern.
"""
from __future__ import annotations

import bisect
import datetime as dt
import math
from itertools import groupby

from .. import fx_rates
from .equity_rekonstruktion import _epoch
from .exposure import _resolve_symbol


def diagnostik(parsed, punkte: list[dict], bars_je_symbol: dict[str, list[dict]],
               offsets: dict[str, int], startkapital: float,
               broker: str | None = None, *, zeitbasis=None) -> dict:
    """Konto-Kurve + kapitalflussneutraler Index (Startwert 1).

``punkte.t`` ist Epoch im Broker-Raum; ``equity`` ist virtuelle Equity
ohne spaetere Flows. ``offsets`` verschiebt Broker-Zeit in den jeweiligen
Kursdaten-Raum. ``bars.time`` bezeichnet den Anfang einer H1-Bar.

Bei unbekannter Flow-Equity ist die Anteilzahl ab diesem Flow unbekannt;
spaetere Indexpunkte bleiben None. Andere Messluecken bleiben None und
verhindern ebenfalls eine vollstaendige DD-Kennzahl. Offene Positionen
beim Flow machen auch eine vollstaendige Rechnung unzuverlaessig.
"""
    trades = [t for t in parsed.trades if t.open_time and t.close_time]
    basis = float(startkapital or 0)
    shifts = {s.strip().upper(): value for s, value in offsets.items()}
    verwendete_shifts = {shifts[t.symbol.strip().upper()] for t in trades
                         if t.symbol.strip().upper() in shifts}
    zeitbasis_unsicher = len(verwendete_shifts) > 1
    if not trades or not punkte or not math.isfinite(basis) or basis <= 0 or zeitbasis_unsicher:
        return {"status": "skipped", "punkte": [], "verlaesslich": False, "kennzahlen": {
            "konto_equity_dd_pct": None, "konto_equity_dd_beobachtet_pct": None,
            "flow_preis_annahmen": 0,
            "index_gueltig_bis": None, "index_abbruch_am": None, "index_messpunkte": 0,
            "verlaesslich": False}, "grund": (
                "Uneinheitliche Symbol-Zeitversätze: Studienpunkte und Kapitalflüsse "
                "haben keine belegte gemeinsame Zeitbasis"
                if zeitbasis_unsicher else "keine positive Kapital-/Trade-/Kurvenbasis")}

    first_open = min(_epoch(t.open_time) for t in trades)
    closes = sorted((_epoch(t.close_time), t.net) for t in trades)
    # Die Basis enthaelt bereits die Kontobewegungen bis zum Handelsbeginn.
    # Buchungen gleicher Sekunde bilden ein Ereignis ohne erfundene Reihenfolge.
    flows = [(zeit, math.fsum(b.amount for b in gruppe))
             for zeit, gruppe in groupby(
                 sorted((b for b in parsed.balances if _epoch(b.time) > first_open),
                        key=lambda b: _epoch(b.time)), key=lambda b: _epoch(b.time))]
    flows = [(zeit, betrag) for zeit, betrag in flows if betrag != 0]

    bars = {s.strip().upper(): sorted(bs, key=lambda b: b["time"])
            for s, bs in bars_je_symbol.items()}
    bar_enden = {s: [int(b["time"]) + 3600 for b in bs]
                 for s, bs in bars.items()}
    specs = {t.symbol.strip().upper(): _resolve_symbol(t.symbol, broker) for t in trades}
    fx_cache = {}
    probleme: list[str] = []
    flow_befunde: list[dict] = []
    units = basis
    kum_flows = 0.0
    flow_idx = 0
    index_gueltig = True
    messluecke = False
    flow_preis_annahmen = 0
    index_abbruch_am = None

    def _realisiert(zeit):
        # Alle Close-Ereignisse derselben Sekunde gelten vor dem Flow.
        return math.fsum(net for geschlossen, net in closes if geschlossen <= zeit)

    def _flow_equity(zeit):
        aktive = [t for t in trades if _epoch(t.open_time) <= zeit < _epoch(t.close_time)]
        floating = []
        kursbasis = []
        fehler = []
        if zeitbasis is not None:
            sicher = (zeitbasis.referenz_sicher(zeit) if zeitbasis.variable else
                      zeitbasis.periode(zeit)["belegt"])
            if not sicher:
                fehler.append("Zeitbasis am Kapitalfluss nicht eindeutig/preisbelegt")
        for t in aktive:
            s = t.symbol.strip().upper()
            spec = specs.get(s)
            if spec is None:
                fehler.append(f"{s}: Kontrakt unbelegt")
                continue
            if s not in shifts:
                fehler.append(f"{s}: Zeitversatz unbekannt")
                continue
            if not getattr(t, "_zeitbasis_sicher", True):
                fehler.append(f"{s}: lokale Open-/Close-Zeitbasis unbelegt")
                continue
            terminal_zeit = zeit + shifts[s]
            position = bisect.bisect_right(bar_enden.get(s, []), terminal_zeit) - 1
            if position < 0:
                fehler.append(f"{s}: kein bereits abgeschlossener H1-Kurs")
                continue
            bar = bars[s][position]
            bar_ende = bar_enden[s][position]
            # Ein Loch in der letzten vollstaendigen H1-Stunde darf nicht
            # durch einen beliebig alten Kurs still geschlossen werden.
            if bar_ende != terminal_zeit // 3600 * 3600:
                fehler.append(f"{s}: Luecke im letzten abgeschlossenen H1-Kurs")
                continue
            close = float(bar["close"])
            if not t.entry_price or not math.isfinite(close):
                fehler.append(f"{s}: Kurs/Einstand unbrauchbar")
                continue
            quote = spec["quote"]
            tag = (zeitbasis.broker_tag(zeit)
                   if zeitbasis is not None and zeitbasis.variable else
                   dt.datetime.fromtimestamp(zeit, dt.timezone.utc).date())
            if tag is None:
                fehler.append(f"{s}: Broker-Handelstag nicht eindeutig")
                continue
            key = (quote, tag)
            if key not in fx_cache:
                kurs = {"rate": 1.0} if quote == "USD" else fx_rates.usd_per(quote, tag)
                fx_cache[key] = kurs["rate"] if kurs else None
            fx = fx_cache[key]
            if fx is None or not math.isfinite(fx) or fx <= 0:
                fehler.append(f"{s}: FX-Kurs fehlt/unbrauchbar ({quote})")
                continue
            richtung = 1.0 if t.direction.lower() == "buy" else -1.0
            wert = richtung * t.volume * spec["factor"] * (close - t.entry_price) * fx
            if not math.isfinite(wert):
                fehler.append(f"{s}: Floating nicht endlich")
                continue
            floating.append(wert)
            kursbasis.append({"symbol": s, "bar_ende": bar_ende - shifts[s],
                              "kurs": close})
        equity = basis + _realisiert(zeit) + kum_flows + math.fsum(floating)
        return (None if fehler else equity), aktive, kursbasis, fehler

    # Kontobewegungen nach dem letzten Trade gehoeren ebenfalls zum Konto.
    # Dort ist Floating sicher null; ein zusaetzlicher Ereignispunkt braucht
    # weder neue Kursdaten noch eine Preisannahme.
    messpunkte = list(punkte)
    letzte_messung = max(int(p["t"]) for p in messpunkte)
    letzter_schluss = max(zeit for zeit, _net in closes)
    for zeit, _betrag in flows:
        if zeit > letzte_messung and zeit >= letzter_schluss:
            virtual = basis + _realisiert(zeit)
            messpunkte.append({"t": zeit, "equity": virtual,
                               "realisiert": virtual, "floating": 0.0, "messpunkt": True})
    if min(int(p["t"]) for p in messpunkte) > first_open:
        messpunkte.append({"t": first_open, "equity": basis,
                           "realisiert": basis, "floating": 0.0, "messpunkt": True})

    neue_punkte = []
    peak = 1.0
    dd_max = 0.0
    index_messpunkte = 0
    index_gueltig_bis = None
    for p in sorted(messpunkte, key=lambda p: p["t"]):
        zeit = int(p["t"])
        while flow_idx < len(flows) and flows[flow_idx][0] <= zeit:
            flow_zeit, amount = flows[flow_idx]
            vor_flow, aktive, kursbasis, fehler = _flow_equity(flow_zeit)
            if aktive:
                flow_preis_annahmen += 1
            gueltig = (index_gueltig and vor_flow is not None
                       and math.isfinite(vor_flow) and vor_flow > 0
                       and math.isfinite(amount) and vor_flow + amount > 0)
            if gueltig:
                units *= (vor_flow + amount) / vor_flow
                gueltig = math.isfinite(units) and units > 0
            if not gueltig:
                if index_gueltig and index_abbruch_am is None:
                    index_abbruch_am = flow_zeit
                index_gueltig = False
                if not fehler:
                    fehler = ["Anteilbasis ungueltig/Equity vor oder nach Flow nicht positiv"]
                probleme.extend(fehler)
            flow_befunde.append({
                "t": flow_zeit, "betrag": amount, "equity_vor_flow": vor_flow,
                "offene_positionen": len(aktive), "approximativ": bool(aktive),
                "kursbasis": kursbasis, "gueltig": gueltig, "probleme": fehler,
            })
            kum_flows += amount
            flow_idx += 1

        wert = p.get("equity")
        messpunkt = (p.get("messpunkt") is not False and wert is not None
                     and math.isfinite(wert)
                     and ("floating" not in p or p["floating"] is not None))
        actual_equity = float(wert) + kum_flows if messpunkt else None
        account_balance = basis + _realisiert(zeit) + kum_flows
        if not messpunkt:
            messluecke = True
        index = actual_equity / units if messpunkt and index_gueltig else None
        dd_pct = None
        if index is not None and math.isfinite(index):
            index_messpunkte += 1
            index_gueltig_bis = zeit
            peak = max(peak, index)
            dd_pct = (peak - index) / peak * 100
            dd_max = max(dd_max, dd_pct)
        elif index is not None:
            if index_abbruch_am is None:
                index_abbruch_am = zeit
            index_gueltig = False
            index = None
            probleme.append("Renditeindex nicht endlich")
        neue_punkte.append({"t": zeit, "actual_equity": actual_equity,
                            "account_balance": account_balance,
                            "return_index": index, "dd_pct": dd_pct,
                            "konto_equity": actual_equity, "konto_balance": account_balance,
                            "rendite_index": index, "drawdown_pct": dd_pct})

    zeitbasis_belegt = zeitbasis is None or zeitbasis.verlaesslich
    vollstaendig = index_gueltig and not messluecke and zeitbasis_belegt
    verlaesslich = vollstaendig and flow_preis_annahmen == 0
    gruende = list(sorted(set(probleme)))
    if messluecke:
        gruende.append("Messluecken: kein vollstaendiger Renditeindex-Drawdown bestimmbar")
    if not zeitbasis_belegt:
        gruende.append("Lokale Zeitbasis nicht vollstaendig belegt; kein Gesamtzeitraum-DD")
    if flow_preis_annahmen:
        gruende.append(f"{flow_preis_annahmen} Kapitalfluss-Ereignisse bei offenen Positionen: "
                       "Equity vor Flow nur approximativ aus abgeschlossenen H1-Schluessen")
    return {
        "status": "ok" if vollstaendig else "unvollstaendig",
        "verlaesslich": verlaesslich,
        "grund": " · ".join(gruende),
        "punkte": neue_punkte,
        "flow_befunde": flow_befunde,
        "kennzahlen": {
            "konto_equity_dd_pct": round(dd_max, 2) if vollstaendig else None,
            # Nur der Rueckfall an vorhandenen gueltigen Messpunkten BIS
            # zum Abbruch. Nach unbekanntem Flow reaktivieren spaetere
            # bekannte Equity-Werte den Index niemals. Kein Gesamt-DD.
            "konto_equity_dd_beobachtet_pct": round(dd_max, 2)
                if index_messpunkte else None,
            "index_gueltig_bis": index_gueltig_bis,
            "index_abbruch_am": index_abbruch_am,
            "index_messpunkte": index_messpunkte,
            "flow_preis_annahmen": flow_preis_annahmen,
            "flows_verarbeitet": len(flow_befunde),
            "index_vollstaendig": vollstaendig,
            "verlaesslich": verlaesslich,
            "messluecke": messluecke,
            "zeitbasis_verlaesslich": zeitbasis_belegt,
        },
        "probleme": sorted(set(probleme)),
        "methodik": "Kapitalflussneutraler Renditeindex; Flows bei offenen Positionen "
                    "nur approximativ aus dem letzten abgeschlossenen H1-Schluss",
        "bewertung": "Nur Diagnostik; darf die virtuelle Drawdown-Schranke nicht verkleinern",
    }
