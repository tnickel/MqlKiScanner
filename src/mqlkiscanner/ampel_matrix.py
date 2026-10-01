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
        "Harte Nutzervorgabe: Das MAXIMUM aus Plattform-By-Equity-DD, "
        "By-Balance-DD, aus den Trades rekonstruiertem Trading-DD, dem "
        "aus Kursdaten nachgemessenen Reko-EQ-DD (nur bei belastbarer "
        "Abdeckung) UND der floating-inclusiven Zweitmessung des "
        "Datenquellen-Monitors (Monitor-EQ-DD) darf die Schranke (Standard "
        "30 %) nicht überschreiten. Grün = mit Puffer ≥ 5 Punkten eingehalten, "
        "gelb = eingehalten, aber Puffer unter 5 Punkte, rot = verletzt. Alle "
        "Werte fehlen → grau (keine Daten). Der höchste Wert entscheidet — "
        "MQL5's By Equity kann deutlich niedriger als By Balance ausfallen, "
        "und Reko-/Monitor-EQ-DD machen floating Verluste sichtbar. "
        "Vorbehalt Monitor-EQ-DD: Der Monitor rechnet gegen seine eigene "
        "(ggf. rückgerechnete) Kapitalbasis — Werte über 100 % überzeichnen "
        "absolut, bleiben aber ein harter Warnmarker."),
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
        "Gelb = teilweise. Weiß = SL nicht übertragen — NEUTRAL, kein "
        "Nachteil (die meisten Broker übertragen keinen SL); die KI-"
        "Analyse schätzt aus dem Tradingverhalten ab, ob ein impliziter "
        "Stop plausibel ist."),
    Kriterium(
        "ertrag", "Ertrag/Monat",
        "Nutzerkriterium: über der Mindestschwelle (Standard 5 %/Monat). "
        "Maßgeblich ist der Ertrag auf der FORENSIK-Kapitalbasis (eigene "
        "Trade-Kurve, dieselbe Basis wie DD/Schock); der Plattformwert ist "
        "Zusatzinformation (Selbstauskunft mit eigener Basis). Historische "
        "Kennzahl, keine Prognose. Grün = Schwelle erreicht, gelb = positiv, "
        "aber darunter, orange = negativ, grau = unbekannt. Risiko geht vor: "
        "schöner Ertrag korrigiert keine rote Zelle."),
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
        "50-USD-Schock, ins Verhältnis zum Kontostand am Expositionspeak "
        "gesetzt. Grün = unter 30 %, gelb = 30–100 %, orange = über 100 % "
        "des Kontos. Begründet Gewichtung und Beobachtung — allein nie "
        "einen Ausschluss."),
    Kriterium(
        "serie", "Verlustserie",
        "Längste Serie aufeinanderfolgender Trades ohne positiven Profit "
        "(inkl. Null-Trades) mit Summe in USD. Zeigt Belastbarkeit im "
        "schlechten Marktregime. Grün = unter 10, gelb = 10–19, orange = "
        "ab 20 Verlusten in Folge (Information, keine harte Schranke)."),
    Kriterium(
        "retdd", "RetDD (Ertrag je DD)",
        "Nutzer-Kriterium 01.10.2026 — Rendite-Risiko-EFFIZIENZ: Niedriges "
        "Risiko allein genügt nicht, der Gewinn muss das eingegangene "
        "Risiko tragen. RetDD = Forensik-Ertrag/Monat ÷ Drawdown-Maximum "
        "(gleiche Kapitalbasis; ×12 = annualisiert, Calmar-artig). Grün = "
        "ab 0,5 (deutlich effizient), gelb = 0,167–0,5, orange = unter "
        "0,167 — die Kombination 5 %/Monat bei 30 % DD steht exakt auf "
        "0,167; wer darunter liegt, erfüllt selbst die Projektmaße nur "
        "ineffizient. Grau = ohne Forensik-Ertrag oder DD nicht messbar. "
        "Allein keine harte Sperre — aber Grün ohne Punkt hier ist ein "
        "unattraktives Grün."),
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
    # Konservativ: der HOECHSTE gemessene Drawdown entscheidet (By Equity,
    # By Balance, aus Trades rekonstruiert, Reko-EQ-DD aus Kursdaten und —
    # B1, Intensiv-Review 29./30.09.2026 — die floating-inclusive Zweit-
    # messung des Datenquellen-Monitors. Ohne sie war die Schranke fuer
    # Quellen-Signale ohne harte floating-Messung (Lemonal 🟢 bei 46,65 %,
    # AccurateCopier 🟢 bei 241 %). Gold Spike: By Equity 3,8 % vs. By
    # Balance 8,11 %.
    werte = {"EQ-DD": r.dd_equity_pct, "Bal-DD": r.dd_balance_pct,
             "Trading-DD": r.trading_dd_pct,
             "Reko-EQ-DD": getattr(r, "equity_dd_rekonstruiert_pct", None),
             "Monitor-EQ-DD": getattr(r, "monitor_trade_eq_dd_pct", None)}
    vorhanden = {k: v for k, v in werte.items() if v is not None}
    if not vorhanden:
        return Zelle(KEINE_DATEN, "keine DD-Werte",
                     "Weder Plattform-By-Equity-DD, By-Balance-DD noch "
                     "rekonstruierter Trading-DD vorhanden — Schranke "
                     "nicht prüfbar.")
    relevant = max(vorhanden.values())
    herleitung = "max(" + ", ".join(f"{k} {_num(v)} %" for k, v in vorhanden.items()) \
                 + f") = {_num(relevant)} %"
    vorbehalt = (" Monitor-EQ-DD ist eine Monitor-Zweitmessung auf dessen "
                 "eigener Kapitalbasis — über 100 % überzeichnet sie absolut."
                 if "Monitor-EQ-DD" in vorhanden
                 and vorhanden["Monitor-EQ-DD"] > 100 else "")
    if relevant > limit:
        return Zelle(ROT, f"{_num(relevant)} % > {limit:g} %",
                     f"{herleitung} liegt ÜBER der Schranke von {limit:g} % "
                     f"(harte Ablehnung).{vorbehalt}")
    puffer = limit - relevant
    if puffer < 5:
        return Zelle(GELB, f"Puffer nur {_num(puffer)} Punkte",
                     f"{herleitung} hält die Schranke {limit:g} % ein, aber "
                     f"der Puffer beträgt nur {_num(puffer)} Punkte — eine "
                     "Wiederholung des Regimes kann sie durchbrechen."
                     + vorbehalt)
    return Zelle(GRUEN, f"Puffer {_num(puffer)} Punkte",
                 f"{herleitung} hält die Schranke {limit:g} % mit "
                 f"{_num(puffer, 1)} Punkten Abstand ein." + vorbehalt)


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
                     f"Stop-Nachweis teilweise vorhanden: {nachweis}")
    if r.stop_evidence == "none":
        # Nutzer-Regel 28.09.2026: kein SL in den Daten = NEUTRAL, kein
        # Warnflag — die meisten Broker übertragen keinen SL. Abwerten darf
        # nur die KI-Analyse mit begründeter Verhaltens-Einschätzung.
        return Zelle(KEINE_DATEN, "neutral (nicht übertragen)",
                     f"SL in den Trade-Daten nicht sichtbar: {nachweis} — "
                     "neutral, kein Nachteil (viele Broker übertragen keinen "
                     "SL). Die KI-Analyse schätzt aus dem Tradingverhalten "
                     "ab, ob ein impliziter Stop plausibel ist.")
    return Zelle(KEINE_DATEN, "keine Daten",
                 "Stop-Evidenz-Stufe nicht erfasst (keine Forensik).")


def _ertrag_zelle(r, settings) -> Zelle:
    minimum = float(settings.get("min_ertrag_pct_monat", 5.0))
    # B2 (Intensiv-Review 29./30.09.2026): Maßgeblich ist der Ertrag auf der
    # FORENSIK-Kapitalbasis (eigene Kurve, dieselbe Basis wie DD/Schock).
    # Der Plattformwert ist eine Selbstauskunft mit fremder Basis — er steht
    # im Detail daneben, entscheidet aber nicht mehr.
    wert = getattr(r, "ertrag_monat_pct_forensik", None)
    plattform = r.ertrag_monat_pct
    if wert is None and plattform is None:
        return Zelle(KEINE_DATEN, "unbekannt",
                     "Ertrag/Monat nicht erfasst — Schwelle nicht prüfbar.")
    basis_hinweis = ""
    if wert is not None and plattform is not None:
        basis_hinweis = (f" Forensik-Basis {(_num(wert, 1))} %/Monat "
                         f"(Plattform meldet {_num(plattform, 1)} %/Monat auf "
                         "eigener Kapitalbasis — Selbstauskunft, nicht "
                         "maßgeblich).")
    if wert is None:
        wert = plattform
        basis_hinweis = (" Nur der Plattformwert vorhanden (keine eigene "
                         "Forensik-Kurve) — Selbstauskunft.")
    if wert >= minimum:
        return Zelle(GRUEN, f"{_num(wert, 1)} %/Monat",
                     f"{_num(wert, 1)} %/Monat ≥ Mindestschwelle "
                     f"{minimum:g} %/Monat (Forensik-Basis).{basis_hinweis}")
    if wert >= 0:
        return Zelle(GELB, f"{_num(wert, 1)} % < {minimum:g} %",
                     f"{_num(wert, 1)} %/Monat liegt unter der Mindest-"
                     f"schwelle von {minimum:g} %/Monat (positive Werte, "
                     f"aber zu wenig; Forensik-Basis).{basis_hinweis}")
    return Zelle(ORANGE, f"{_num(wert, 1)} % (negativ)",
                 f"Ertrag {(_num(wert, 1))} %/Monat ist negativ — das "
                 f"Kriterium {minimum:g} %/Monat ist klar verfehlt."
                 f"{basis_hinweis}")


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
    # shock_pct_max = Schock in % des Kontos am Expositionspeak (die Felder
    # shock_pct_peak_account/-usd sind USD-Betraege am Peak, keine Prozent!).
    wert = r.shock_pct_max
    if wert is None:
        return Zelle(KEINE_DATEN, "kein Schockwert",
                     "Schockszenario nicht berechnet (Exposure- oder "
                     "Kontodaten unvollständig).")
    zeit = (f"am {r.shock_pct_peak_time}" if r.shock_pct_peak_time
            else "am Expositionspeak")
    kontext = (f"50-USD-Schock über Peak-Netto-Lots ≈ {_num(r.shock_usd, 0)} USD "
               f"= {_num(wert, 1)} % des Kontos {zeit}")
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


def _retdd_zelle(r) -> Zelle:
    """RetDD = Forensik-Ertrag/Monat je Prozent DD-Maximum (Nutzer 01.10.:
    Gewinn muss das Risiko tragen — niedriges Risiko allein bringt es
    nicht). Schwellen: 0.5 / 0.167 (5 %/M bei 30 % DD = exakt 0.167)."""
    wert = getattr(r, "retdd_monat", None)
    if wert is None:
        return Zelle(KEINE_DATEN, "unbekannt",
                     "RetDD ohne Forensik-Ertrag oder DD-Maximum nicht "
                     "berechenbar (kein Rendite-Risiko-Urteil möglich).")
    jahr = getattr(r, "retdd_jahr", None)
    jahres_text = f" (annualisiert {jahr:g})" if jahr is not None else ""
    if wert >= 0.5:
        return Zelle(GRUEN, f"{wert:g} / Monat",
                     f"RetDD {wert:g} je Prozent Drawdown{jahres_text} — der "
                     "Ertrag trägt das Risiko deutlich (Schwelle 0,5).")
    if wert >= 0.167:
        return Zelle(GELB, f"{wert:g} / Monat",
                     f"RetDD {wert:g} je Prozent Drawdown{jahres_text} — "
                     "effizient genug für die Projektmaße (0,167 = exakt "
                     "5 %/M bei 30 % DD), aber Reserve dünn.")
    return Zelle(ORANGE, f"{wert:g} / Monat",
                 f"RetDD {wert:g} je Prozent Drawdown{jahres_text} — selbst "
                 "für die Projektmaße ineffizient: das eingegangene Risiko "
                 "wird nicht angemessen bezahlt. Grün-Empfehlungen mit "
                 "diesem Wert sind unattraktiv.")


_BERECHNER = {
    "dd_schranke": lambda r, s: _dd_zelle(r, s),
    "martingale": lambda r, s: _martingale_zelle(r),
    "stop": lambda r, s: _stop_zelle(r),
    "ertrag": lambda r, s: _ertrag_zelle(r, s),
    "retdd": lambda r, s: _retdd_zelle(r),
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
