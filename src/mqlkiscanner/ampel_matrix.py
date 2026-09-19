# -*- coding: utf-8 -*-
"""Ampel-Matrix: je Signal eine Ampel je Testkriterium (Nachvollziehbarkeit).

Der Nutzer will auf einen Blick sehen, WELCHE Bedingung eines Signals
rot/gelb/orange ist — nicht nur das Gesamturteil. Dieses Modul leitet aus
den gespeicherten Engine-Werten (Forensik + Plattform-Kennzahlen) fuer
jedes Kriterium eine Zellen-Ampel her und liefert den EXAKTEN
Berechnungstext ("rot, weil max(EQ-DD, Trading-DD) = 34,2 % > 30 %").

Farb-Semantik (einheitlich, in Tooltips und Hilfe erklaert):
  grün  = Kriterium erfüllt / bewiesen
  gelb  = teilweise erfüllt, knapp oder unabgeklärt (Beobachtung)
  orange= Warnflag: nicht erfüllt, ohne harte Verletzung
  rot   = harte Verletzung / nachgewiesen falsch
  ⚪     = keine Daten — entlastet nicht

Die Matrix ist rein (keine Seiteneffekte) und wird zweimal berechnet:
beim Scan landet sie als Audit-Snapshots im Forensik-JSON der Datenbank,
die Anzeige rechnet sie aus den gespeicherten Werten mit den aktuellen
Einstellungen neu (identisch zur Gesamt-Ampel, die ebenfalls aktuell
neu berechnet wird).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config

GRUEN, GELB, ORANGE, ROT, KEINE_DATEN = "🟢", "🟡", "🟠", "🔴", "⚪"

LABELS = {GRUEN: "GRÜN (erfüllt)", GELB: "GELB (Beobachtung)",
          ORANGE: "ORANGE (Warnflag)", ROT: "ROT (verletzt)",
          KEINE_DATEN: "KEINE DATEN"}


@dataclass(frozen=True)
class Kriterium:
    key: str
    titel: str        # Spaltenkopf
    beschreibung: str # ⓘ-Tooltip im Spaltenkopf


@dataclass(frozen=True)
class Zelle:
    ampel: str
    kurz: str    # Kurzzustand (z. B. "Puffer 1,8 Punkte")
    detail: str  # exakte Berechnung fuer den Zell-Tooltip


def _num(wert: float | None, nachkommastellen: int = 2) -> str:
    if wert is None:
        return "—"
    return f"{wert:.{nachkommastellen}f}".replace(".", ",")


KRITERIEN: list[Kriterium] = [
    Kriterium(
        "dd_schranke", "Drawdown-Schranke",
        "Harte Nutzervorgabe: Das Maximum aus Plattform-Equity-DD und aus "
        "den Trades rekonstruiertem Trading-DD darf die Schranke (Standard "
        "30 %) nicht überschreiten. Grün = mit Puffer ≥ 5 Punkten eingehalten, "
        "gelb = eingehalten, aber Puffer unter 5 Punkte, rot = verletzt. "
        "Beide Werte fehlen → grau (keine Daten)."),
    Kriterium(
        "martingale", "Martingale",
        "Forensik-Test a) aus doc/03: Systematische Lot-Vergrößerung nach "
        "Verlusten (Median-Faktor > 1,3x) oder charakteristische Korb-"
        "Muster. Rot = Signatur nachgewiesen (Ablehnung), grün = keine "
        "Signatur erkannt, gelb = ohne Forensik unbekannt."),
    Kriterium(
        "stop", "Stop-Nachweis",
        "Kernfrage des Projekts: Ist der Stop-Loss bewiesen oder nur "
        "behauptet? Grün = direkt (Orderbuch mit S/L-Spalte bzw. [sl]-"
        "Kommentaren) oder Cluster-Signatur (Regelabstand der Verluste). "
        "Gelb = teilweise, orange = kein Nachweis — das entlastet nicht, "
        "sperrt aber allein nicht die harte Schranke."),
    Kriterium(
        "ertrag", "Ertrag/Monat",
        "Nutzerkriterium: über der Mindestschwelle (Standard 5 %/Monat). "
        "Historische Kennzahl, keine Prognose. Grün = Schwelle erreicht, "
        "gelb = positiv, aber darunter, orange = negativ, grau = unbekannt. "
        "Risiko geht vor: schöner Ertrag korrigiert keine rote Zelle."),
    Kriterium(
        "score", "Risiko-Score",
        "Aggregierte Engine-Bewertung 1–10 aus der Forensik-Batterie "
        "(kleiner = weniger erkannte Risiken, keine Wahrscheinlichkeit). "
        "Gesamt-Ampel Grün verlangt Score < 5. Grün = < 5, gelb = 5 bis "
        "unter 7, orange = ≥ 7, grau = ohne vollständige Forensik nicht "
        "berechnet."),
    Kriterium(
        "schock", "Schock vs. Konto",
        "Stress-Szenario, KEIN gemessener Verlust: Peak-Netto-Exposure im "
        "50-USD-Schock, bezogen auf die Konto-Referenz zum Spitzenzeitpunkt "
        "(Peak-Konto, falls vorhanden). Grün = unter 30 %, gelb = 30–100 %, "
        "orange = über 100 % des Referenzkontos. Begründet Gewichtung und "
        "Beobachtung — allein nie einen Ausschluss."),
    Kriterium(
        "serie", "Verlustserie",
        "Längste Serie aufeinanderfolgender Trades ohne positiven Profit "
        "(inkl. Null-Trades) mit Summe in USD. Zeigt Belastbarkeit im "
        "schlechten Marktregime. Grün = unter 10, gelb = 10–19, orange = "
        "ab 20 Verlusten in Folge (Information, keine harte Schranke)."),
    Kriterium(
        "liste", "Ausschlussliste",
        "Manuell kuratierte Liste (data/known_signals.json) aus der "
        "Analyse-Reihe: rot = ausgeschlossen (Grund im Tooltip; überschreibt "
        "alles), gelb = Watchlist/Beobachtung, grün = nicht gelistet. "
        "Regelwerk der Kriterien (Schranke, Martingale/Grid, Ertrag, "
        "Qualität, grenznahe Kombination, Copy-Fragilität) siehe "
        "Ergebnisse-Seite, Abschnitt „Regelwerk · Ausschlussliste“."),
]


def _dd_zelle(r, settings) -> Zelle:
    limit = float(settings.get("schranke_eq_dd_pct", 30.0))
    werte = {"EQ-DD": r.dd_equity_pct, "Trading-DD": r.trading_dd_pct}
    vorhanden = {k: v for k, v in werte.items() if v is not None}
    if not vorhanden:
        return Zelle(KEINE_DATEN, "keine DD-Werte",
                     "Weder Plattform-EQ-DD noch rekonstruierter Trading-DD "
                     "vorhanden — Schranke nicht prüfbar.")
    relevant = max(vorhanden.values())
    herleitung = "max(" + ", ".join(f"{k} {_num(v)} %" for k, v in vorhanden.items()) \
                 + f") = {_num(relevant)} %"
    if relevant > limit:
        return Zelle(ROT, f"{_num(relevant)} % > {limit:g} %",
                     f"{herleitung} liegt ÜBER der Schranke von {limit:g} % "
                     "(harte Ablehnung).")
    puffer = limit - relevant
    if puffer < 5:
        return Zelle(GELB, f"Puffer nur {_num(puffer)} Punkte",
                     f"{herleitung} hält die Schranke {limit:g} % ein, aber "
                     f"der Puffer beträgt nur {_num(puffer)} Punkte — eine "
                     "Wiederholung des Regimes kann sie durchbrechen.")
    return Zelle(GRUEN, f"Puffer {_num(puffer)} Punkte",
                 f"{herleitung} hält die Schranke {limit:g} % mit "
                 f"{_num(puffer, 1)} Punkten Abstand ein.")


def _martingale_zelle(r) -> Zelle:
    if r.martingale_flag is None:
        return Zelle(GELB, "unbekannt",
                     "Kein Trade-Export ausgewertet — Martingale-Signatur "
                     "nicht prüfbar (keine Entlastung).")
    if r.martingale_flag:
        evidenz = "; ".join(r.martingale_evidenz or []) or "Signatur erkannt"
        return Zelle(ROT, "Signatur nachgewiesen",
                     f"Martingale-Signatur nachgewiesen (Ablehnung). "
                     f"Evidenz: {evidenz}")
    return Zelle(GRUEN, "keine Signatur",
                 "Keine Lot-Eskalation nach Verlusten und kein Korb-Muster "
                 "erkannt (Median-Faktor-Schwelle 1,3x nicht überschritten).")


def _stop_zelle(r) -> Zelle:
    nachweis = r.stop_nachweis or "kein Nachweistext"
    if r.stop_evidence == "direct":
        return Zelle(GRUEN, "bewiesen (Orderbuch)",
                     f"Stop direkt belegt: {nachweis}")
    if r.stop_evidence == "cluster":
        return Zelle(GRUEN, "bewiesen (Cluster)",
                     f"Stop über Cluster-Signatur belegt (Verlustdistanzen "
                     f"ballen sich an einem Niveau): {nachweis}")
    if r.stop_evidence == "partial":
        return Zelle(GELB, "teilweise",
                     f"Stop-Nachweis nur teilweise vorhanden: {nachweis}")
    if r.stop_evidence == "none":
        return Zelle(ORANGE, "kein Nachweis",
                     f"Kein belastbarer Stop-Nachweis: {nachweis} — fehlende "
                     "Evidenz entlastet nicht; keine Empfehlung möglich.")
    return Zelle(KEINE_DATEN, "keine Daten",
                 "Stop-Evidenz-Stufe nicht erfasst (keine Forensik).")


def _ertrag_zelle(r, settings) -> Zelle:
    minimum = float(settings.get("min_ertrag_pct_monat", 5.0))
    if r.ertrag_monat_pct is None:
        return Zelle(KEINE_DATEN, "unbekannt",
                     "Ertrag/Monat nicht erfasst — Schwelle nicht prüfbar.")
    wert = r.ertrag_monat_pct
    if wert >= minimum:
        return Zelle(GRUEN, f"{_num(wert, 1)} %/Monat",
                     f"{_num(wert, 1)} %/Monat ≥ Mindestschwelle "
                     f"{minimum:g} %/Monat.")
    if wert >= 0:
        return Zelle(GELB, f"{_num(wert, 1)} % < {minimum:g} %",
                     f"{_num(wert, 1)} %/Monat liegt unter der Mindest-"
                     f"schwelle von {minimum:g} %/Monat (positive Werte, "
                     "aber zu wenig).")
    return Zelle(ORANGE, f"{_num(wert, 1)} % (negativ)",
                 f"Ertrag {(_num(wert, 1))} %/Monat ist negativ — das "
                 f"Kriterium {minimum:g} %/Monat ist klar verfehlt.")


def _score_zelle(r) -> Zelle:
    if r.score is None:
        return Zelle(KEINE_DATEN, "kein Score",
                     "Risiko-Score nicht berechnet — vollständige Forensik-"
                     "Batterie fehlt (kein Score vor bestandener Batterie).")
    if r.score < 5.0:
        return Zelle(GRUEN, f"Score {_num(r.score, 1)}",
                     f"Engine-Risiko-Score {_num(r.score, 1)} von 10 — "
                     "unter der Kandidaten-Schwelle 5.")
    if r.score < 7.0:
        return Zelle(GELB, f"Score {_num(r.score, 1)}",
                     f"Engine-Risiko-Score {_num(r.score, 1)} von 10 — "
                     "Kandidaten-Schwelle 5 überschritten (kein Kandidat).")
    return Zelle(ORANGE, f"Score {_num(r.score, 1)}",
                 f"Engine-Risiko-Score {_num(r.score, 1)} von 10 — "
                 "erheblich erhöhtes Risikoprofil.")


def _schock_zelle(r) -> Zelle:
    basis = ("Peak-Konto" if r.shock_pct_peak_account is not None
             else ("Maximum" if r.shock_pct_max is not None else None))
    wert = r.shock_pct_peak_account if r.shock_pct_peak_account is not None \
        else r.shock_pct_max
    if wert is None:
        return Zelle(KEINE_DATEN, "kein Schockwert",
                     "Schockszenario nicht berechnet (Exposure- oder "
                     "Kontodaten unvollständig).")
    kontext = (f"50-USD-Schock über Peak-Netto-Lots ≈ {_num(r.shock_usd, 0)} USD "
               f"≈ {_num(wert, 1)} % der Konto-Referenz ({basis}-Bezug)")
    if wert < 30:
        return Zelle(GRUEN, f"{_num(wert, 1)} %",
                     f"{kontext} — beherrschbar. Stress-Szenario, kein "
                     "gemessener Verlust.")
    if wert <= 100:
        return Zelle(GELB, f"{_num(wert, 1)} %",
                     f"{kontext} — erhebliche Stress-Belastung. Stress-"
                     "Szenario, kein gemessener Verlust; begründet "
                     "Gewichtung, nicht allein die Ablehnung.")
    return Zelle(ORANGE, f"{_num(wert, 1)} %",
                 f"{kontext} — übersteigt die Konto-Referenz rechnerisch. "
                 "Stress-Szenario, kein gemessener Verlust; begründet "
                 "Gewichtung und Beobachtung, nicht allein die Ablehnung.")


def _serie_zelle(r) -> Zelle:
    if r.max_verlustserie is None:
        return Zelle(KEINE_DATEN, "unbekannt",
                     "Verlustserie nicht erfasst (keine Trade-Forensik).")
    n = r.max_verlustserie
    summe = (f", Summe {_num(r.verlustserie_usd, 0)} USD"
             if r.verlustserie_usd is not None else "")
    if n < 10:
        return Zelle(GRUEN, f"{n} in Folge",
                     f"Längste Verlustserie: {n} Trades{summe}.")
    if n < 20:
        return Zelle(GELB, f"{n} in Folge",
                     f"Längste Verlustserie: {n} Trades{summe} — deutliche "
                     "Regime-Belastung.")
    return Zelle(ORANGE, f"{n} in Folge",
                 f"Längste Verlustserie: {n} Trades{summe} — extreme "
                 "Serie; Strukturmerkmal, das die Schranke gefährden kann.")


def _listen_zelle(r) -> Zelle:
    known = config.load_known_signals()
    for eintrag in known.get("ausgeschlossen", []):
        if eintrag.get("id") == r.id:
            grund = eintrag.get("grund", "ohne Begründung")
            return Zelle(ROT, "ausgeschlossen",
                         f"Steht auf der Ausschlussliste (known_signals.json): "
                         f"{grund}")
    for eintrag in known.get("watchlist", []):
        if eintrag.get("id") == r.id:
            status = eintrag.get("status", "Watchlist")
            grund = eintrag.get("grund", "")
            return Zelle(GELB, status,
                         f"Watchlist-Eintrag ({status})"
                         + (f": {grund}" if grund else ""))
    return Zelle(GRUEN, "nicht gelistet",
                 "Signal steht weder auf der Ausschlussliste noch auf der "
                 "Watchlist (known_signals.json).")


_BERECHNER = {
    "dd_schranke": lambda r, s: _dd_zelle(r, s),
    "martingale": lambda r, s: _martingale_zelle(r),
    "stop": lambda r, s: _stop_zelle(r),
    "ertrag": lambda r, s: _ertrag_zelle(r, s),
    "score": lambda r, s: _score_zelle(r),
    "schock": lambda r, s: _schock_zelle(r),
    "serie": lambda r, s: _serie_zelle(r),
    "liste": lambda r, s: _listen_zelle(r),
}


def kriterien_matrix(result, settings: dict | None = None) -> dict[str, Zelle]:
    """Je Kriterium (in KRITERIEN-Reihenfolge) die Zellen-Ampel."""
    settings = settings or {}
    return {k.key: _BERECHNER[k.key](result, settings) for k in KRITERIEN}


def matrix_payload(result, settings: dict | None = None) -> dict:
    """JSON-feste Form fuer die Datenbank (Audit-Snapshot beim Scan).

    Enthaelt die Grenzwerte, mit denen gerechnet wurde, damit der Snapshot
    auch nach spaeteren Einstellungs-Aenderungen lesbar bleibt.
    """
    settings = settings or {}
    return {
        "grenzen": {"schranke_eq_dd_pct": settings.get("schranke_eq_dd_pct", 30.0),
                    "min_ertrag_pct_monat": settings.get("min_ertrag_pct_monat", 5.0)},
        "kriterien": {key: {"ampel": z.ampel, "kurz": z.kurz, "detail": z.detail}
                      for key, z in kriterien_matrix(result, settings).items()},
    }
