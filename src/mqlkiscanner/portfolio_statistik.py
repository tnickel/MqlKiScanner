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

from pathlib import Path

from .parser import load_export


def monatsrenditen(trades_pfad: str, startkapital: float | None
                    ) -> dict[str, float]:
    """Monatsrenditen in Prozent aus dem Trade-Export (virtuelle Kurve).

    Rückgabe {„2026-07": -1.82, …}; bei Lesefehlern oder ohne positives
    Startkapital eine leere Map (das Signal bleibt in der Statistik als
    „ohne Kurve" sichtbar, statt still zu verschwinden).
    """
    try:
        parsed = load_export(trades_pfad)
    except Exception:
        return {}
    if not parsed.trades or not startkapital or startkapital <= 0:
        return {}
    monat_pnl: dict[str, float] = {}
    for t in parsed.trades:
        zeit = t.close_time or t.open_time
        monat_pnl.setdefault(zeit.strftime("%Y-%m"), 0.0)
        monat_pnl[zeit.strftime("%Y-%m")] += t.net
    renditen: dict[str, float] = {}
    stand = float(startkapital)
    for monat in sorted(monat_pnl):
        if stand > 0:
            renditen[monat] = round(100.0 * monat_pnl[monat] / stand, 2)
        stand += monat_pnl[monat]
    return renditen


def _symbole_als_set(symbole: str | None) -> set[str]:
    return {s.strip().upper() for s in (symbole or "").split(",") if s.strip()}


def effizienz_kennzahlen(trades_pfad: str | None, startkapital: float | None,
                         dd_max_pct: float | None) -> dict | None:
    """RetDD-Effizienz JE SIGNAL — der Produzent (B24-Fix, Lauf-Review
    02.10.: Deklaration und Verbraucher existierten seit 01.10., die
    Berechnung nie; 0/97 Signale hatten Werte).

    Auf derselben Kurve wie die Forensik-Erträge (monatsrenditen auf der
    verwendeten Kapitalbasis):
      - ertrag_monat_geom_pct: GEOMETRISCHES Monatsmittel (zinseszins-wahr,
        wachsender Kontostand als Nenner; Nutzer-Regel 01.10.)
      - cagr_jahr_pct: echter Jahres-CAGR ((End/Start)^(1/Jahre) - 1)
      - retdd_monat = geom %/M ÷ DD-Maximum % (Deutungsschwelle 1,0 =
        Nutzer-Mindestqualität 02.10.)
      - retdd_jahr = CAGR ÷ DD-Maximum (echter Calmar)
    None ohne belastbare Basis (keine Kurve, kein Startkapital, kein DD) —
    dann bleibt die RetDD-Ampel-Zelle ehrlich ⚪.
    """
    if not trades_pfad or not Path(trades_pfad).exists():
        return None
    if not startkapital or startkapital <= 0:
        return None
    if dd_max_pct is None or dd_max_pct <= 0:
        return None
    kurve = monatsrenditen(trades_pfad, startkapital)
    if not kurve:
        return None
    faktor = 1.0
    for monat in sorted(kurve):
        faktor *= 1.0 + kurve[monat] / 100.0
    if faktor <= 0:
        return None    # Totalverlust: geom. Mittel nicht definiert
    n = len(kurve)
    geom_pct = (faktor ** (1.0 / n) - 1.0) * 100.0
    jahre = n / 12.0
    cagr_pct = (faktor ** (1.0 / jahre) - 1.0) * 100.0 if jahre > 0 else None
    return {
        "ertrag_monat_geom_pct": round(geom_pct, 2),
        "cagr_jahr_pct": round(cagr_pct, 2) if cagr_pct is not None else None,
        "retdd_monat": round(geom_pct / float(dd_max_pct), 2),
        "retdd_jahr": (round(cagr_pct / float(dd_max_pct), 2)
                       if cagr_pct is not None else None),
    }


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
