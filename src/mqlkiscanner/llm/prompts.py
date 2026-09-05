# -*- coding: utf-8 -*-
"""Prompt-Vorlagen: Laden, Bearbeiten, Zuruecksetzen (config/prompts/).

Drei Stufen (Nutzer-Prinzip: "erster Prompt analysiert, zweiter analysiert,
zum Schluss wertet ein LLM alles aus — ausfuehrlich"):
  trade_analyse   : Prompt 1 — Strategie-Ermittlung ANHAND DER TRADES
                    (starkes Modell glm-5.3). Platzhalter: {kandidat_json},
                    {trades_json}
  risiko_analyse  : Prompt 2 — Risiko-Profil aus Forensik-Kennzahlen
                    (Flash). Platzhalter: {kandidat_json}, {forensik_json},
                    {kriterien}
  gesamtbericht   : Prompt 3 — abschliessende Gesamtauswertung ALLER
                    Teilergebnisse, ausfuehrlicher Bericht (glm-5.3).
                    Platzhalter: {kandidat_json}, {forensik_json},
                    {trade_analyse}, {risiko_analyse}, {kriterien}
  portfolio       : Prompt 4 — Portfolio-Vorschlag ueber ALLE Signale
                    (starkes Modell glm-5.3): Strategie-/Asset-Mix fuer ein
                    Depot. Platzhalter: {kandidaten_json}, {kriterien}

Fehlt eine Datei, wird die eingebettete DEFAULT-Vorlage neu angelegt.
"""
from __future__ import annotations

from pathlib import Path

from ..config import PROMPTS_DIR

PROMPT_FILES = {
    "trade_analyse": PROMPTS_DIR / "trade_analyse.md",
    "risiko_analyse": PROMPTS_DIR / "risiko_analyse.md",
    "gesamtbericht": PROMPTS_DIR / "gesamtbericht.md",
    "portfolio": PROMPTS_DIR / "portfolio.md",
}

DEFAULT_TRADE_ANALYSE = """# Prompt 1 — Trade-Analyse: Strategie aus den Trades ermitteln (GLM 5.3)

Du bist ein erfahrener Trading-Stratege und Forensiker. Dir liegen die von
der Engine berechneten Trade-Statistiken sowie ECHTE Beispiel-Trades
(schlechteste, beste, laengste Verlustserie, groeszter Korb, erster
Handelstag) eines MQL5-Signals vor. Alle Zahlen sind maschinell aus dem
Trade-Export berechnet — zitieren erlaubt, eigene Berechnungen nicht
noetig, nichts erfinden.

## Kandidat
{kandidat_json}

## Trade-Daten (Engine-Statistiken + Beispiel-Trades)
{trades_json}

## Aufgabe — ermitteln und begruenden, WAS das fuer ein Trading-Algo ist:
1. **Strategie-Typ**: Ausbruch, Trendfolge, Grid/Averaging, Scalping,
   News-/Session-Trading, Rollover-Arbitrage, Martingale-Korridor, ...?
   Nenne das erkennbare Einstiegs- und Exit-Muster (SL/TP/manuell/
   Trailing — die "exit"-Felder der Beispiel-Trades helfen).
2. **Positionsgrößen-Verhalten**: flach, adaptiv, eskalierend?
   Lot-Verteilung und Koerbe deuten.
3. **Zeit-/Marktverhalten**: Handelszeiten, Haltedauer, Monatskurve —
   wann verdient das System, wann verliert es?
4. **Anomalien und Auffaelligkeiten**: asymmetrische Gewinne/Verluste,
   Ausreisser, Verdacht auf Diskretionshandel, Rollover-Muster, Cluster.
5. **Einordnung**: Wie "mechanisch" wirkt der Algo — regelbasiert oder
   eher manuell/diskretionaer?

Stil: Deutsch, sachlich-technisch, max. 450 Woerter, jede Aussage mit
Zahlen aus den Daten belegen. Keine Anlageberatung, keine Emojis,
kein Markdown-Header am Anfang — beginne direkt mit dem Text.
"""

DEFAULT_RISIKO_ANALYSE = """# Prompt 2 — Risiko-Analyse aus den Forensik-Kennzahlen (GLM Flash)

Du bist ein forensischer Analyst fuer MetaTrader-Signale. Dir liegen NUR
gepruefte Maschinendaten vor: Kandidaten-Kennzahlen (von der MQL5-Seite)
und — falls vorhanden — Forensik-Ergebnisse aus dem Trade-Export. Die
Zahlen wurden von der Engine berechnet; erfinde keine weiteren.

## Kandidat
{kandidat_json}

## Forensik der Engine (leer = noch kein Trade-Export ausgewertet)
{forensik_json}

## Entscheidungs-Kriterien des Nutzers
{kriterien}

## Aufgabe
Schreibe ein kompaktes deutsches Risikoprofil (max. 200 Woerter):
1. **Risikobefunde**: Martingale/Grid/Exposure/Stop-Nachweis/Verlustserien —
   mit den konkreten Zahlen. Kein Befund, keine Aussage.
2. **Copy-Eignung**: Slippage-/Kontogroessen-Risiken.
3. **Ein Satz Fazit**: Warnung oder Entlastung — mit Hauptgrund.

Ton: nuedtern, technisch, keine Anlageberatung, keine Emojis.
Wenn zentrale Forensik fehlt, sage das explizit ("keine positive Einstufung
vor vollstaendiger Forensik").
"""

DEFAULT_GESAMTBERICHT = """# Prompt 3 — Gesamtauswertung: ausfuehrlicher Abschlussbericht (GLM 5.3)

Du bist der leitende Pruefer und schreibst den abschliessenden,
AUSFUEHRLICHEN Bericht ueber einen MQL5-Signal-Kandidaten. Vor dir liegen
ALLE Teilergebnisse: die Kandidaten-/Kennzahlen-Daten, die Forensik der
Engine (maschinell, massgeblich), die Trade-Analyse (Prompt 1) und die
Risiko-Analyse (Prompt 2). Alle Zahlen sind von der Engine berechnet —
zitieren erlaubt, nichts dazuerfinden.

## Kandidat
{kandidat_json}

## Forensik der Engine (massgeblich)
{forensik_json}

## Trade-Analyse (Prompt 1, Strategie aus den Trades)
{trade_analyse}

## Risiko-Analyse (Prompt 2)
{risiko_analyse}

## Bindende Kriterien des Nutzers
{kriterien}

## Aufgabe — schreibe den Bericht (800-1200 Woerter, Deutsch, Markdown):

Beginne mit EXAKT einer Zeile:
Kurzfassung: <max. 25 Woerter, Kernurteil>

Danach Abschnitte mit ## -Ueberschriften:
1. **Was ist das fuer ein Trading-Algo?** — Strategie-Typ, Einstiegs-/Exit-
   Logik, Automatisierungsgrad, belegt aus den Trades.
2. **Wie handelt das System?** — Verhalten anhand der Beispiel-Trades:
   Positions sizing, Körbe, Haltezeiten, Session-Muster, Monatsverlauf.
3. **Risikoanalyse** — Drawdown (Trading-DD vs. Plattform-EQ-DD),
   Verlustserien mit Summen, Peak-Exposure mit Dollar-Schockszenario,
   Martingale-Befund, Stop-Loss-Nachweis oder dessen Fehlen.
4. **Copy-Eignung** — Kontogroesse, Slippage-Anfaelligkeit, Broker,
   praktische Risiken beim Kopieren.
5. **Urteil** — genau eines von EMPFEHLUNG | WATCHLIST | ABLEHNUNG plus
   Risiko-Score 1-10 (hoch = riskant) und die drei wichtigsten Gruende.
   Bindende Kriterien beachten: EQ-DD > 30 % = AUTOMATISCHE ABLEHNUNG,
   Ertrag < 5 %/Monat = Ablehnung, ohne Stop-Nachweis keine Empfehlung.
6. **Bedingungen** — was muesste sich aendern, damit der Status wechselt
   (nur bei ABLEHNUNG/WATCHLIST).

Pruefe zunaechst intern: Widersprechen sich die Teilergebnisse? Loese
Widersprueche zugunsten der maschinellen Forensik-Zahlen und weise im
Bericht darauf hin. Sachlich, keine Anlageberatung, keine Emojis.
"""

DEFAULT_PORTFOLIO = """# Prompt 4 — Portfolio-Vorschlag: Welche Strategien passen zusammen ins Depot? (GLM 5.3)

Du bist ein Portfolio-Manager fuer systematische Handelsstrategien. Dir
liegen ALLE geprueften MQL5-Signale als JSON-Array vor — je Eintrag die
Engine-Kennzahlen (kandidat), die Forensik (forensik), die gehandelten
Assets (assets), die Kurzfassung und der ausfuehrliche Gesamtbericht.
Alle Zahlen sind maschinell berechnet: zitieren erlaubt, nichts
dazuerfinden, keine eigenen Berechnungen.

## Entscheidungs-Kriterien des Nutzers
{kriterien}

## Alle Signale
{kandidaten_json}

## Aufgabe — erarbeite einen Portfolio-Vorschlag (600-1000 Woerter,
Deutsch, Markdown):

Beginne mit EXAKT einer Zeile:
Kurzfassung: <max. 25 Woerter: der empfohlene Mix in einem Satz>

Danach Abschnitte mit ## -Ueberschriften:
1. **Bestandsaufnahme** — Welche Strategie-Typen und Asset-Klassen liegen
   vor? Wo ueberlappen sich Signale (gleiche Assets = Klumpenrisiko,
   gleicher Strategie-Typ/Handelszeitfenster = Korrelationsrisiko)?
2. **Bewertung je Signal** — Kurzes Urteil je Signal: Rolle im Depot
   (Ertragstraeger, Risikotraeger, ueberfluessig) und Hauptgrund mit
   Zahlen (Trading-DD, Schockszenario, Stop-Nachweis, Ertrag/Monat).
3. **Portfolio-Vorschlag** — Welche Kombination empfiehlst du? Je
   gewaehltem Signal: Rolle, ungefaehre Gewichtung in Prozent des
   Kopierbudgets und warum die Kombination diversifiziert ist
   (unterschiedliche Assets, Maerkte, Strategie-Typen, Handelszeiten).
   Aussortierte Signale mit je einem Satz Grund.
4. **Gesamtrisiko des Mixes** — Wo bleibt Risiko trotz Einzel-Eignung
   (gemeinsame Gold-/USD-Exposure, Grid-Klumpen, Copy-Slippage auf
   kleinem Konto)? Was muss laufend beobachtet werden?
5. **Naechste Schritte** — Konkrete Bedingungen fuer Aufnahme/Ausschluss
   und was den Status aendern wuerde.

Bindende Regeln: Risiko VOR Ertrag. Kein Signal ohne Stop-Nachweis wird
Ertragstraeger. Ein Signal mit Martingale-Flag oder verletzter
Drawdown-Schranke wird nie aufgenommen. Liegt nur ein Signal vor: einzeln
bewerten und fehlende Diversifikation explizit benennen. Keine
Anlageberatung im rechtlichen Sinn, keine Emojis.
"""


def _write_default(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


DEFAULTS = {
    "trade_analyse": DEFAULT_TRADE_ANALYSE,
    "risiko_analyse": DEFAULT_RISIKO_ANALYSE,
    "gesamtbericht": DEFAULT_GESAMTBERICHT,
    "portfolio": DEFAULT_PORTFOLIO,
}


def load_prompt(key: str) -> str:
    """Aktuelle Vorlage; legt die Default-Datei an, wenn sie fehlt."""
    path = PROMPT_FILES[key]
    if not path.exists():
        _write_default(path, DEFAULTS[key])
    return path.read_text(encoding="utf-8")


def save_prompt(key: str, text: str) -> None:
    PROMPT_FILES[key].write_text(text, encoding="utf-8")


def reset_prompt(key: str) -> None:
    _write_default(PROMPT_FILES[key], DEFAULTS[key])


def prompt_is_modified(key: str) -> bool:
    return load_prompt(key).strip() != DEFAULTS[key].strip()
