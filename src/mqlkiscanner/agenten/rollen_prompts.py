# -*- coding: utf-8 -*-
"""Prompt-Vorlagen der Agenten-Rollen (config/prompts/agenten/).

Sechs Vorlagen (doc/19, Anhang A) — verwaltet wie die bestehenden
Workflow-Prompts: fehlt die Datei, wird die eingebettete Default-Vorlage
neu angelegt; Speichern/Zurücksetzen im Admin-Bereich; Änderungen sind
markierbar. Das Füllen folgt dem Zwei-Phasen-Muster aus llm.prompt_fill:
eingefügte Inhalte werden nie erneut gescannt, Vorlagen-Slots immer
ersetzt — und ein unbeversorgter Platzhalter ist ein klarer Fehler, bevor
er stumm an das Modell geht.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import config

# Schlüssel der Rollen-Vorlagen. Die Pfade werden pro Zugriff neu aus
# config.PROMPTS_DIR aufgelöst — Tests lenken das Verzeichnis um, und ein
# beim Import eingefrorener Pfad würde ins echte config/ greifen.
PROMPT_SCHLUESSEL: tuple[str, ...] = (
    "dirigent_planung",
    "markt_kontext",
    "profil_destillation",
    "betreuer_delta",
    "lagebericht",
    "meldung",
)


def prompt_datei(key: str) -> Path:
    """Dateipfad einer Vorlage — bewusst zur Laufzeit aufgelöst."""
    return config.PROMPTS_DIR / "agenten" / f"{key}.md"

DEFAULT_DIRIGENT_PLANUNG = """# Dirigent — Tagesplanung (Agentenbetrieb)

Du steuerst den Betrieb des MqlKiScanner-Agentenbetriebs. Der Ablaufplan
selbst ist Code — du entscheidest nur Randfragen. Deine Antwort ist NUR
gültig als JSON-Objekt mit dem Schlüssel "aktionen" (Liste von Strings aus
der erlaubten Menge: "delta_laufen_lassen", "delta_ueberspringen",
"markt_holen", "markt_ueberspringen", "scan_gelb_gruen", "scan_full",
"meldung_schicken") plus "begruendung" (max. 30 Wörter). Erlaube niemals
Aktionen außerhalb der Menge. Zahlen stammen ausschließlich aus den Daten.

## Lagestatus (maschinell)
{lagestatus_json}

## Zeitplan (maschinell)
{zeitplan_json}
"""

DEFAULT_MARKT_KONTEXT = """# Marktbeobachter — Marktlage je Symbol

Du bist Marktbeobachter eines MQL5-Signal-Scanners. Dir liegen ausschließlich
maschinell berechnete Kurskennzahlen vor — zitieren erlaubt, nichts
dazuerfinden, nichts selbst rechnen.

## Kurs-Kennzahlen (Code-berechnet)
{kurse_json}

## Beobachtete Symbole (Universum der Kandidaten-Signale)
{symbole_json}

## Aufgabe
Schreibe je Symbol 2–3 Sätze Marktlage (Bewegung, Volatilität, Trendlage,
besondere Ereignisse im Zeitfenster) und danach EINEN Gesamtabsatz
("Marktlage insgesamt"). Deutsch, sachlich, keine Emojis, keine
Anlageberatung. Max. 250 Wörter gesamt.
"""

DEFAULT_PROFIL_DESTILLATION = """# Profil-Destillation — Algo-Profil für {signal_name}

Du destillierst aus vorliegenden Analysen ein kompaktes, PRÜFBARES
Handelsprofil des Signals {signal_name} ({signal_url}). Das Profil wird
später täglich gegen neue Trades geprüft — formuliere Merkmale so, dass man
Abweichung erkennen kann.

## Tiefenanalyse (KI, ausführlich)
{tiefenanalyse}

## Gesamtbericht (KI)
{gesamtbericht}

## Forensik der Engine (maschinell, maßgeblich)
{forensik_json}

## Ausgabe (Markdown, feste Abschnitte)
1. **Strategietyp** — 1–2 Sätze
2. **Einstieg/Exit** — erkennbare Muster, Auslöser
3. **Zeiten/Sessions** — wann handelt das System (Wochentage, Stunden)
4. **Sizing** — Lot-Verhalten, Eskalation ja/nein
5. **Stop-Disziplin** — bewiesen/behauptet, typische Distanzen
6. **Erwartetes Verhalten** — DD-Band, Verlustserien-Länge, Gewinnmuster
7. **Konformitäts-Merkmale** — nummerierte Liste: woran man später erkennt,
   dass das Signal NORMAL handelt (für die Tagesprüfung)
8. **Warn-Merkmale** — nummeriert: was eine Abweichung wäre (Stilbruch-
   Indikatoren)

Nur belegte Aussagen; Widersprüche zugunsten der Engine-Forensik. Deutsch,
keine Emojis, keine Anlageberatung.
"""

DEFAULT_BETREUER_DELTA = """# Signal-Betreuer — Tagesprüfung {signal_name}

Du betreust das Signal {signal_name} und prüfst die NEUEN Trades seit dem
letzten Blick gegen das dokumentierte Algo-Profil. Alle Zahlen sind
maschinell berechnet — zitieren erlaubt, nichts dazuerfinden.

## Algo-Profil (dokumentiert)
{profil_text}

## Neue Trades / Delta-Kennzahlen (Code-berechnet)
{delta_json}

## Marktkontext (heute)
{marktkontext}

## Letzte Beobachtungen (Verlauf)
{letzte_beobachtungen}

## Aufgabe
Bewerte: Handelt das Signal im Rahmen des Profils?
Beginne mit EXAKT einer Zeile:
EINORDNUNG: KONFORM | AUFFAELLIG | STILBRUCH | KEINE_NEUEN_TRADES
Danach max. 200 Wörter Begründung mit Zahlen; bei AUFFAELLIG/STILBRUCH nenne
die verletzten Profil-Merkmale (Nummern) und den Schweregrad.
Du bewertest NIEMALS neu — Ampel/Urteil/Score sind Engine-Sache; deine
Einordnung ist Beobachtung, keine Neubewertung. Deutsch, keine Emojis,
keine Anlageberatung.
"""

DEFAULT_LAGEBERICHT = """# Chefermittler — Wochen-Lagebericht

Du bist der leitende Prüfer des MqlKiScanner-Agentenbetriebs und schreibst
den Wochen-Lagebericht über alle betreuten Signale. Alle Zahlen sind
maschinell berechnet — zitieren erlaubt, nichts dazuerfinden.

## Dossiers (kompakt, maschinell aufbereitet)
{dossiers_json}

## Marktkontext der Woche
{marktkontext_woche}

## Ampel-Wechsel der Woche (Engine-Protokoll)
{ampel_wechsel_json}

## Budget-Status
{budget_status}

## Aufgabe (Markdown, 400–700 Wörter)
1. **Kurzfassung** — max. 3 Sätze
2. **Signale im Detail** — je Kandidat: konform/auffällig, wichtigste
   Entwicklung, Dringlichkeit der nächsten Prüfung
3. **Markt und Zusammenhänge** — welche Marktlage welches Verhalten erklärt
4. **Empfehlungen** — welches Signal beim nächsten Überwachungs-Scan besonders
   genau zu prüfen ist; ob eine Tiefenanalyse-Erneuerung lohnt; welche
   Watchlist-Signale reif für den nächsten Full-Scan sind
Bindend: Du entscheidest nichts und bewertest nichts neu — Engine-Ampel und
Urteil sind maßgeblich; deine Empfehlungen sind Vorschläge an den Nutzer.
Deutsch, sachlich, keine Emojis, keine Anlageberatung.
"""

DEFAULT_MELDUNG = """# Melder — Nachricht für das Postfach

Du verdichtest Agenten-Journal-Einträge zu einer kurzen Klartext-Nachricht an
den Nutzer. Alle Zahlen stammen aus den Einträgen — nichts dazuerfinden.

## Typ
{typ}

## Ereignisse (maschinell)
{ereignisse_json}

## Aufgabe
Eine Nachricht, max. 120 Wörter: was ist passiert, welche Signale betroffen,
was empfiehlt sich anzusehen (Verweis auf Protokoll/Postfach genügt).
Bei Alerts (Priorität 2/3) das Wichtigste in den ersten Satz. Deutsch,
keine Emojis, keine Anlageberatung.
"""

DEFAULTS = {
    "dirigent_planung": DEFAULT_DIRIGENT_PLANUNG,
    "markt_kontext": DEFAULT_MARKT_KONTEXT,
    "profil_destillation": DEFAULT_PROFIL_DESTILLATION,
    "betreuer_delta": DEFAULT_BETREUER_DELTA,
    "lagebericht": DEFAULT_LAGEBERICHT,
    "meldung": DEFAULT_MELDUNG,
}

# Platzhalter je Vorlage — für Anzeige und Absicherung.
PLATZHALTER: dict[str, tuple[str, ...]] = {
    "dirigent_planung": ("lagestatus_json", "zeitplan_json"),
    "markt_kontext": ("kurse_json", "symbole_json"),
    "profil_destillation": ("signal_name", "signal_url", "tiefenanalyse",
                            "gesamtbericht", "forensik_json"),
    "betreuer_delta": ("signal_name", "profil_text", "delta_json",
                       "marktkontext", "letzte_beobachtungen"),
    "lagebericht": ("dossiers_json", "marktkontext_woche", "ampel_wechsel_json",
                    "budget_status"),
    "meldung": ("typ", "ereignisse_json"),
}

_SLOT_RE = re.compile(r"\{[a-z_][a-z_0-9]{1,39}\}")


def _schreibe_default(datei: Path, inhalt: str) -> None:
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(inhalt, encoding="utf-8")


def lade_vorlage(key: str) -> str:
    """Aktuelle Vorlage; legt die Default-Datei an, wenn sie fehlt."""
    datei = prompt_datei(key)
    if not datei.exists():
        _schreibe_default(datei, DEFAULTS[key])
    return datei.read_text(encoding="utf-8")


def speichere_vorlage(key: str, text: str) -> None:
    prompt_datei(key).write_text(text, encoding="utf-8")


def setze_zurueck(key: str) -> None:
    _schreibe_default(prompt_datei(key), DEFAULTS[key])


def vorlage_geaendert(key: str) -> bool:
    return lade_vorlage(key).strip() != DEFAULTS[key].strip()


def fuellung(template: str, mapping: dict[str, str]) -> str:
    """Zwei-Phasen-Füllung wie llm.prompt_fill (Inhalte werden nie gescannt).

    Mapping-Schlüssel sind Platzhalter-Namen OHNE Klammern
    ({"typ": "digest"} füllt "{typ}"). Vorher wird abgesichert, dass jeder
    platzhalterartige Ausdruck der Vorlage versorgt ist — Tippfehler in
    einer Admin-editierten Vorlage scheitern hier klar statt stumm beim
    Modell.
    """
    bekannt = {f"{{{name}}}" for name in mapping}
    for fund in _SLOT_RE.findall(template):
        if fund not in bekannt:
            raise ValueError(f"Unversorgter Platzhalter in der Vorlage: {fund}")
    tokens: dict[str, str] = {}
    out = template
    for i, (name, wert) in enumerate(mapping.items()):
        platzhalter = f"{{{name}}}"
        if platzhalter not in out:
            continue  # Vorlage darf Platzhalter bewusst nicht enthalten
        token = f"\x00AGENTEN_SLOT_{i}\x00"
        out = out.replace(platzhalter, token)
        tokens[token] = wert
    for token, wert in tokens.items():
        out = out.replace(token, wert)
    return out
