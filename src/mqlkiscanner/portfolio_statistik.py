# -*- coding: utf-8 -*-
"""Portfolio-Statistik als Code-Befund für den Portfolio-Prompt (B20/B21,
Intensiv-Review 29./30.09.2026, Nachtrag der Parallel-KI).

Der Portfolio-Lauf prüfte bisher nur paarweise Rendite-Korrelation — die
Frage, die den Nutzer trifft („wie stark trifft ein gemeinsamer Schock mein
Depot?"), wurde nicht gestellt, und die Historie-Tiefe der Empfehlung
blieb unsichtbar. Dieses Modul liefert die Maschinen-Fakten, die KI deutet:

- Verlustmonat-Cluster: Monate, in denen mehrere 🟢/🟡 GLEICHZEITIG im Minus
  liegen (der schlechteste beobachtbare Monat = Stress-Szenario).
- Historie-Tiefe je Signal + gemeinsames Beobachtungsfenster (Stichproben-
  lücke sichtbar machen, z. B. Trio-Fenster 11 Monate).
- Instrument-Overlap: Paare mit hohem Symbol-Überlappung sind Klumpenrisiko
  selbst bei niedriger Korrelation (gleiche Werkstatt, gleiche Instrumente).

Basis der Monatsrenditen ist die virtuelle Kurve der Forensik
(Startkapital = tatsächlich verwendete Kapitalbasis, Monats-PnL / Balance
am Monatsanfang) — dieselbe Konvention wie Drawdown-Trading-Kurve und
Review-Nachrechnung.
"""
from __future__ import annotations

import math
from pathlib import Path

from .parser import load_export

JAHR_TAGE = 365.2425
MONAT_TAGE = JAHR_TAGE / 12.0


def _positiv_endlich(wert) -> float | None:
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return None
    return zahl if math.isfinite(zahl) and zahl > 0 else None


def _monatsserie(parsed, basis: float) -> dict[str, float]:
    """Lueckenloses Kalenderfenster ab erstem Open, ohne Geldbewegungen."""
    erste = min(t.open_time for t in parsed.trades)
    letzte = max(t.close_time for t in parsed.trades)
    von = erste.year * 12 + erste.month - 1
    bis = letzte.year * 12 + letzte.month - 1
    je_monat: dict[int, list[float]] = {}
    for trade in parsed.trades:
        zeit = trade.close_time
        monat = zeit.year * 12 + zeit.month - 1
        je_monat.setdefault(monat, []).append(trade.net)
    renditen = {}
    stand = basis
    for monat in range(von, bis + 1):
        if not math.isfinite(stand) or stand <= 0:
            return {}  # Keine Rendite mit unbekanntem/nicht positivem Nenner.
        pnl = math.fsum(je_monat.get(monat, []))
        jahr, index = divmod(monat, 12)
        rendite = pnl / stand * 100.0
        if not math.isfinite(rendite):
            return {}
        renditen[f"{jahr:04d}-{index + 1:02d}"] = rendite
        stand += pnl
    return renditen


def monatsrenditen(trades_pfad: str, startkapital: float | None
                    ) -> dict[str, float]:
    """Monatsrenditen in Prozent aus dem Trade-Export (virtuelle Kurve).

    Rückgabe {„2026-07": -1.82, …}; bei Lesefehlern oder ohne positives
    Startkapital eine leere Map (das Signal bleibt in der Statistik als
    „ohne Kurve" sichtbar, statt still zu verschwinden).
    Monate zwischen erstem Open und letztem Close OHNE Abschluesse
    bleiben mit 0 % enthalten. Die Renditen werden nicht vorgerundet.
    """
    try:
        parsed = load_export(trades_pfad)
    except Exception:
        return {}
    basis = _positiv_endlich(startkapital)
    if not parsed.trades or basis is None:
        return {}
    try:
        return _monatsserie(parsed, basis)
    except (OverflowError, ValueError):
        return {}


def _symbole_als_set(symbole: str | None) -> set[str]:
    return {s.strip().upper() for s in (symbole or "").split(",") if s.strip()}


def effizienz_kennzahlen(trades_pfad: str | None, startkapital: float | None,
                         dd_max_pct: float | None) -> dict | None:
    """RetDD-Effizienz JE SIGNAL — der Produzent (B24-Fix, Lauf-Review
    02.10.: Deklaration und Verbraucher existierten seit 01.10., die
    Berechnung nie; 0/97 Signale hatten Werte).

    Virtuelle Netto-Kurve auf der verwendeten Kapitalbasis. Zeitbasis ist
    die gesamte Dauer vom ersten Open bis zum letzten Close, einschliesslich
    Monaten ohne Trades; ein Jahr hat 365,2425 Tage, ein Monat 1/12
    davon. End/Start kommt direkt aus dem UNGERUNDETEN Gesamtnetto:
      - ertrag_monat_geom_pct: GEOMETRISCHES Monatsmittel (zinseszins-wahr,
        wachsender Kontostand als Nenner; Nutzer-Regel 01.10.)
      - cagr_jahr_pct: echter Jahres-CAGR ((End/Start)^(1/Jahre) - 1)
      - retdd_monat = geom %/M ÷ uebergebenen Max-EQUITY-DD % (Schwelle 1,0 =
        Nutzer-Mindestqualität 02.10.)
      - retdd_jahr = virtueller CAGR ÷ Max-EQUITY-DD
    Ohne Equity-DD bleibt nur RetDD unbekannt, die Gewinnmessung erhalten.
    Alle Ergebniswerte bleiben ungerundet, damit 0,999... nicht die
    RetDD-Mindestschwelle 1,0 passiert. Bei spaeteren Kapitalfluessen haben
    virtuelle Rendite und Konto-Equity-DD unterschiedliche Kapitalbasen;
    diese Kennzahl ist dann kein kapitalflussneutraler Originalkonto-Calmar.
    """
    if not trades_pfad or not Path(trades_pfad).exists():
        return None
    basis = _positiv_endlich(startkapital)
    if basis is None:
        return None
    try:
        parsed = load_export(trades_pfad)
    except Exception:
        return None
    if not parsed.trades:
        return None
    erste = min(t.open_time for t in parsed.trades)
    letzte = max(t.close_time for t in parsed.trades)
    dauer_tage = (letzte - erste).total_seconds() / 86400.0
    monate = dauer_tage / MONAT_TAGE
    jahre = dauer_tage / JAHR_TAGE
    dd = _positiv_endlich(dd_max_pct)
    ergebnis = {
        "ertrag_monat_geom_pct": None, "cagr_jahr_pct": None,
        "retdd_monat": None, "retdd_jahr": None,
        "effizienz_status": "rendite_nicht_berechenbar",
        "rendite_basis": "virtuelle_trade_netto_kurve",
        "retdd_basis": "uebergebener_max_equity_dd_pct",
        "dd_max_equity_pct": dd,
        "zeit_von": erste.isoformat(), "zeit_bis": letzte.isoformat(),
        "dauer_monate": monate, "dauer_jahre": jahre,
        "kalender_monate": (letzte.year - erste.year) * 12 + letzte.month - erste.month + 1,
        "netto_gesamt_usd": None, "endkapital_virtuell_usd": None,
        "kapitalfluesse_nach_start": sum(b.time > erste for b in parsed.balances),
        "basis_hinweis": "Virtuelle Trade-Netto-Rendite ohne spaetere Kapitalfluesse; "
                          "Equity-DD hat bei Kontobewegungen eine andere Bezugsbasis",
    }
    try:
        netto = math.fsum(t.net for t in parsed.trades)
        endkapital = basis + netto
        ergebnis["netto_gesamt_usd"] = netto
        ergebnis["endkapital_virtuell_usd"] = endkapital
        if (monate <= 0 or not math.isfinite(monate)
                or endkapital <= 0 or not math.isfinite(endkapital)):
            return ergebnis
        relativer_gewinn = netto / basis
        log_faktor = (math.log1p(relativer_gewinn)
                      if math.isfinite(relativer_gewinn) and relativer_gewinn > -1
                      else math.log(endkapital) - math.log(basis))
        geom_pct = math.expm1(log_faktor / monate) * 100.0
        cagr_pct = math.expm1(log_faktor / jahre) * 100.0
        if not math.isfinite(geom_pct) or not math.isfinite(cagr_pct):
            return ergebnis
    except (OverflowError, ValueError):
        return ergebnis
    retdd_monat = geom_pct / dd if dd is not None else None
    retdd_jahr = cagr_pct / dd if dd is not None else None
    if retdd_monat is not None and not math.isfinite(retdd_monat):
        retdd_monat = None
    if retdd_jahr is not None and not math.isfinite(retdd_jahr):
        retdd_jahr = None
    status = ("ohne_equity_dd" if dd is None else "ok"
              if retdd_monat is not None and retdd_jahr is not None
              else "retdd_nicht_berechenbar")
    ergebnis.update({
        "ertrag_monat_geom_pct": geom_pct, "cagr_jahr_pct": cagr_pct,
        "retdd_monat": retdd_monat, "retdd_jahr": retdd_jahr,
        "effizienz_status": status,
    })
    return ergebnis


def statistik(results: list) -> dict:
    """Code-Befund für den Portfolio-Prompt aus den 🟢/🟡-Ergebnissen.

    results: ScanResult-Liste (nur live/forensik-vollständig erwartet, aber
    defensiv gefiltert). Kompakt gehalten für das Token-Budget: Cluster nur
    ab 2 Verlierern, Instrument-Overlap nur Paare mit >= 3 gemeinsamen
    Symbolen und Jaccard >= 0.3, max. 12 Paare.
    """
    kurven: dict[int, dict[str, float]] = {}
    zeilen: list[dict] = []
    symbole: dict[int, set[str]] = {}
    for r in results:
        if getattr(r, "source_kind", "live") != "live":
            continue
        refresh = getattr(r, "refresh_efficiency", None)
        if callable(refresh):
            refresh()
        kurve: dict[str, float] = {}
        pfad = getattr(r, "trades_path", None)
        basis = getattr(r, "kapitalbasis_verwendet_usd", None)
        if pfad and Path(pfad).exists():
            kurve = monatsrenditen(pfad, basis)
        kurven[r.id] = kurve
        symbole[r.id] = _symbole_als_set(getattr(r, "symbole", None))
        negativ = sorted(m for m, v in kurve.items() if v < 0)
        zeilen.append({
            "id": r.id, "name": r.name,
            # RetDD (Nutzer 01.10.): Ertrag je Prozent DD — Effizienz für
            # die Priorisierung im Portfolio (gleiche Rendite bei halbem
            # Drawdown ist doppelt so gut).
            "retdd_monat": getattr(r, "retdd_monat", None),
            "retdd_jahr": getattr(r, "retdd_jahr", None),
            "ertrag_monat_geom_pct": getattr(r, "ertrag_monat_geom_pct", None),
            "max_drawdown_equity_pct": getattr(r, "max_drawdown_equity_pct", None),
            "effizienz_befund": getattr(r, "effizienz_befund", None),
            "monate": len(kurve),
            "erste": min(kurve) if kurve else None,
            "letzte": max(kurve) if kurve else None,
            "schlechtester_monat": (min(kurve, key=kurve.get)
                                    if negativ else None),
            "schlechtester_wert_pct": (min(kurve.values()) if negativ else None),
            "verlustmonate": negativ,
        })

    # Verlustmonat-Cluster: Monat -> [(name, rendite_pct), …]
    je_monat: dict[str, list[tuple[str, float]]] = {}
    for eintrag in zeilen:
        kurve = kurven[eintrag["id"]]
        for monat in eintrag["verlustmonate"]:
            je_monat.setdefault(monat, []).append(
                (eintrag["name"], kurve[monat]))
    cluster = {monat: {"n": len(paar),
                       "signale": [{"name": n, "pct": v} for n, v in
                                   sorted(paar, key=lambda x: x[1])]}
               for monat, paar in sorted(je_monat.items()) if len(paar) >= 2}

    # Gemeinsames Beobachtungsfenster über alle Signale MIT Kurve.
    fenster: dict = {"signale_mit_kurve": 0, "von": None, "bis": None,
                     "monate": 0}
    mengen = [set(kurve) for kurve in kurven.values() if kurve]
    if mengen:
        schnitt = set.intersection(*mengen)
        fenster = {"signale_mit_kurve": len(mengen),
                   "von": min(schnitt) if schnitt else None,
                   "bis": max(schnitt) if schnitt else None,
                   "monate": len(schnitt)}

    # Instrument-Overlap (B21): gemeinsame Symbole trotz niedriger
    # Rendite-Korrelation = gemeinsames Klumpenrisiko.
    ids = [e["id"] for e in zeilen if symbole.get(e["id"])]
    namen = {e["id"]: e["name"] for e in zeilen}
    paare = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            gemeinsam = symbole[a] & symbole[b]
            union = symbole[a] | symbole[b] or {""}
            jaccard = round(len(gemeinsam) / len(union), 2)
            if len(gemeinsam) >= 3 and jaccard >= 0.3:
                paare.append({"a": namen[a], "b": namen[b],
                              "gemeinsame_symbole": sorted(gemeinsam),
                              "n_gemeinsam": len(gemeinsam),
                              "jaccard": jaccard})
    paare.sort(key=lambda p: (-p["jaccard"], -p["n_gemeinsam"]))

    return {
        "hinweis": (
            "Maschinenbefund (Code rechnet, KI deutet): Rendite-Korrelation "
            "ALLEIN ist KEIN Diversifikationsnachweis. Prüfe zusätzlich: "
            "(1) Verlustmonat-Cluster = gemeinsame Schocks — der schlechteste "
            "beobachtbare Monat ist das Stress-Szenario und MUSS mit Namen "
            "und Werten im Bericht stehen; (2) Historie-Tiefe je Position und "
            "gemeinsames Fenster — unter ~24 gemeinsamen Monaten ist jede "
            "Diversifikationsaussage schwach belegt und als solche zu nennen; "
            "(3) Instrument-Overlap — Paare mit vielen gemeinsamen Symbolen "
            "tragen gemeinsames Risiko selbst bei r nahe 0 (gleiche "
            "Werkstatt, gleiche Instrumente). "
            "(4) RetDD je Signal (retdd_monat/retdd_jahr) — priorisiere "
            "Effizienz: gleiche Rendite bei halbem Drawdown ist doppelt so "
            "gut. Mindestqualität ist 1,0 je Prozent DD (Nutzer-Regel "
            "02.10.: retdd=1 minimum) — Signale mit retdd_monat < 1,0 "
            "nicht empfehlen, auch wenn Einzelkriterien grün sind."),
        "signale": zeilen,
        "verlustmonate_cluster": cluster,
        "gemeinsames_fenster": fenster,
        "instrument_overlap": paare[:12],
    }
