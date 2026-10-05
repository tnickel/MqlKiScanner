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
# Nutzer-Regel 05.10. (Mindesthistorie): Unter 3 Monaten Trade-Spanne gibt
# es keine belastbare Effizienz — annualisieren bläht Kurzläufer auf
# (10-Tage-Fall: +400 USD → 12,7 %/M → RetDD 6,3 → falsches Grün; nach
# 12 realistischen Monaten läge dasselbe Signal bei 0,33).
MIN_HISTORIE_MONATE = 3.0


def _positiv_endlich(wert) -> float | None:
    try:
        zahl = float(wert)
    except (TypeError, ValueError, OverflowError):
        return None
    return zahl if math.isfinite(zahl) and zahl > 0 else None


def _teilfaktor(start: float, pnl: list[float]) -> float | None:
    """Wachstumsfaktor einer Unterperiode zwischen zwei Kapitalflüssen."""
    gewinn = math.fsum(pnl)
    if start > 0:
        return (start + gewinn) / start
    # Leeres Konto (z. B. nach Vollauszahlung): nur ohne PnL definiert.
    return 1.0 if gewinn == 0 else None


def _monatsserie(parsed, basis: float) -> dict[str, float]:
    """Lueckenloses Kalenderfenster ab erstem Open.

    Kapitalfluesse nach dem ersten Open (Copilot-Review 05.10. abends,
    Befund Hoch 1 — vorher: Zähler netto÷Startbasis OHNE Flows, Nenner
    Max-DD auf der REALEN Kurve MIT Flows): Die Monatsrendite rechnet auf
    der realen Kurve (inkl. Flows). Eine Einzahlung zaehlt damit NICHT als
    Rendite, sondern vergroessert den Nenner ab ihrem Zeitpunkt (TWR;
    MQL5-Copy-Sicht — der Kopierer erlebt Einzahlungen des Anbieters als
    proportional neutral).

    Zeitgenau (Copilot-Review 05.10. spaet, Befund Hoch 2 — vorher wirkten
    Fluesse zum MONATSANFANG: 900 USD Gewinnauszahlung am Monatsende auf
    1.000 Basis ergaben 1100 %/M statt ~100 %): Jeder Fluss schliesst eine
    Unterperiode (Faktor = Stand vor Fluss ÷ Stand bei Periodenbeginn),
    danach wird er gebucht. Die Monatsrendite ist das Produkt der
    Unterperioden-Faktoren des Monats − 1. Ohne Fluesse ist das exakt
    Monats-PnL ÷ Stand am Monatsanfang (bisheriges Verhalten)."""
    erste = min(t.open_time for t in parsed.trades)
    letzte = max(t.close_time for t in parsed.trades)
    von = erste.year * 12 + erste.month - 1
    bis = letzte.year * 12 + letzte.month - 1
    # (zeit, art, betrag); art 0 = Trade-Close, 1 = Kapitalfluss — bei
    # gleichem Zeitstempel zaehlt der Trade noch zur alten Unterperiode.
    ereignisse: list[tuple] = [(t.close_time, 0, float(t.net)) for t in parsed.trades]
    for b in getattr(parsed, "balances", []):
        if b.time <= erste:
            continue  # vor dem ersten Open: bereits Teil der Startbasis
        ereignisse.append((b.time, 1, float(b.amount)))
    ereignisse.sort(key=lambda e: (e[0], e[1]))
    je_monat: dict[int, list[tuple[int, float]]] = {}
    for zeit, art, betrag in ereignisse:
        je_monat.setdefault(zeit.year * 12 + zeit.month - 1, []).append((art, betrag))

    renditen = {}
    stand = basis
    for monat in range(von, bis + 1):
        faktor = 1.0
        start = stand
        if not math.isfinite(start) or start < 0:
            return {}  # Negativer Kontostand: keine Rendite definierbar.
        pnl: list[float] = []
        mit_fluss = False
        for art, betrag in je_monat.get(monat, []):
            if art == 0:
                pnl.append(betrag)
                continue
            mit_fluss = True
            teil = _teilfaktor(start, pnl)
            if teil is None:
                return {}  # PnL ohne positiven Nenner: Rendite undefiniert.
            faktor *= teil
            stand = start + math.fsum(pnl) + betrag
            if not math.isfinite(stand) or stand < 0:
                return {}  # Auszahlung über den Kontostand: Daten widersprüchlich.
            start, pnl = stand, []
        teil = _teilfaktor(start, pnl)
        if teil is None:
            return {}
        faktor *= teil
        gewinn = math.fsum(pnl)
        stand = start + gewinn
        jahr, index = divmod(monat, 12)
        if mit_fluss:
            rendite = (faktor - 1.0) * 100.0
        else:
            # Ohne Fluss direkt PnL ÷ Stand (kein Rundungsrest aus (1+r)−1).
            rendite = gewinn / start * 100.0 if start > 0 else 0.0
        if not math.isfinite(rendite):
            return {}
        renditen[f"{jahr:04d}-{index + 1:02d}"] = rendite
    return renditen


def monatsrenditen(trades_pfad: str, startkapital: float | None,
                   plattform_positions: float | None = None
                   ) -> dict[str, float]:
    """Monatsrenditen in Prozent aus dem Trade-Export (virtuelle Kurve).

    plattform_positions: derselbe Beweiswert wie in der Forensik
    (Signalseiten-„Trades:"), damit Rendite-Kurve und Forensik auf dem
    IDENTISCHEN Trade-Bestand rechnen (Review 04.10., Paket A A2a: ohne
    Beweis wäre RetDD/Portfolio roh, während die Forensik deduped).

    Rückgabe {„2026-07": -1.82, …}; bei Lesefehlern oder ohne positives
    Startkapital eine leere Map (das Signal bleibt in der Statistik als
    „ohne Kurve" sichtbar, statt still zu verschwinden).
    Monate zwischen erstem Open und letztem Close OHNE Abschluesse
    bleiben mit 0 % enthalten. Die Renditen werden nicht vorgerundet.
    """
    try:
        parsed = load_export(trades_pfad, plattform_positions=plattform_positions)
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
                         dd_max_pct: float | None,
                         plattform_positions: float | None = None) -> dict | None:
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
      - retdd_jahr = CAGR ÷ Max-EQUITY-DD = CALMAR — entscheidet seit
        05.10. das Grün-Gate (Setting min_calmar_jahr, Default 3,0; die
        frühere Monats-Schwelle 1,0 war aufgezinst Calmar 14-40 und
        nicht risikoneutral)
      - retdd_monat = geom %/M ÷ Max-EQUITY-DD (Anzeigewert, kein Gate)
    Ohne Equity-DD bleibt nur RetDD unbekannt, die Gewinnmessung erhalten.
    Alle Ergebniswerte bleiben ungerundet, damit 0,999... nicht die
    RetDD-Mindestschwelle 1,0 passiert. Ohne Kapitalfluesse nach Start ist
    die Kurve identisch real/virtuell; MIT Flows verkettet der Zaehler die
    TWR-Monatsrenditen der realen Kurve — derselbe Kurventyp wie der
    Max-Equity-DD (Copilot-Review 05.10. abends, Hoch 1).
    """
    if not trades_pfad or not Path(trades_pfad).exists():
        return None
    basis = _positiv_endlich(startkapital)
    if basis is None:
        return None
    try:
        parsed = load_export(trades_pfad, plattform_positions=plattform_positions)
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
        "basis_hinweis": "Geometrische Trade-Netto-Rendite auf der Kurve "
                         "ohne Kapitalfluesse; bei Fluessen nach Start wird "
                         "stattdessen TWR auf der realen Kurve gerechnet",
    }
    try:
        netto = math.fsum(t.net for t in parsed.trades)
        endkapital = basis + netto
        ergebnis["netto_gesamt_usd"] = netto
        ergebnis["endkapital_virtuell_usd"] = endkapital
        if (monate <= 0 or not math.isfinite(monate)
                or endkapital <= 0 or not math.isfinite(endkapital)):
            return ergebnis
        kapitalfluesse = ergebnis["kapitalfluesse_nach_start"]
        if kapitalfluesse:
            # Copilot-Review 05.10. abends, Befund Hoch 1: Bei Flows nach
            # Start war der Zaehler netto/basis (virtuelle Kurve), der
            # Nenner Max-DD aber reale Kurve — Gewinne auf EINGEZAHLTEM
            # Geld zaehlten als Rendite auf das kleine Startkapital und
            # konnten TrueRetDD ueber 1,0 heben (falsches Gruen). Der
            # Zaehler verkettet deshalb die TWR-Monatsrenditen der realen
            # Kurve (Einzahlung = Nenner-Erhoehung, kein Gewinn).
            serie = _monatsserie(parsed, basis)
            faktor = 1.0
            for rendite in serie.values():
                faktor *= 1.0 + rendite / 100.0
            # Copilot-Review 05.10. spaet, Mittel 3: dieselbe EXAKTE
            # Zeitspanne wie der Zweig ohne Fluesse und die Mindesthistorie
            # — nicht die Zahl angebrochener Kalendermonate (die den CAGR
            # nur bei Signalen mit Fluessen gedrueckt hat).
            if serie and faktor > 0:
                log_faktor = math.log(faktor)
                geom_pct = math.expm1(log_faktor / monate) * 100.0
                cagr_pct = math.expm1(log_faktor / jahre) * 100.0
                ergebnis["rendite_basis"] = "twr_reale_kurve_monatsverkettung"
                ergebnis["basis_hinweis"] = (
                    "TWR auf der realen Kontokurve (Einzahlungen erhoehen den "
                    "Nenner ab ihrem Zeitpunkt, zaehlen nicht als Rendite) — "
                    "konsistent zum Max-Equity-DD auf derselben Kurve; "
                    "zeitgenaue Unterperioden je Kapitalfluss")
            else:
                return ergebnis
        else:
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
    # Nutzer-Regel 05.10. (Mindesthistorie): Unter 3 Monaten Trade-Spanne
    # KEIN RetDD/Calmar (Ertragswerte bleiben als Anzeige gefüllt — sie
    # sind kein Gate-Wert mehr; pipeline.refresh_efficiency sperrt über
    # den Status "historie_zu_kurz" auch den Vorbehaltswert).
    if monate < MIN_HISTORIE_MONATE:
        retdd_monat = None
        retdd_jahr = None
        status = "historie_zu_kurz"
    else:
        status = ("ohne_equity_dd" if dd is None else "ok"
                  if retdd_monat is not None and retdd_jahr is not None
                  else "retdd_nicht_berechenbar")
    ergebnis.update({
        "ertrag_monat_geom_pct": geom_pct, "cagr_jahr_pct": cagr_pct,
        "retdd_monat": retdd_monat, "retdd_jahr": retdd_jahr,
        "effizienz_status": status,
        "min_historie_monate": MIN_HISTORIE_MONATE,
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
            kurve = monatsrenditen(
                pfad, basis,
                plattform_positions=getattr(r, "plattform_trades", None))
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
