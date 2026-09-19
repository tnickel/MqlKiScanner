# -*- coding: utf-8 -*-
"""Regelwerk der Ausschlussliste: Kriterien + Anzeige-Markdown.

Die Ausschlussliste (data/known_signals.json) ist MANUELL kuratiert —
aus der forensischen Analyse-Reihe (Workspace Allgemein, Stand 04.09.2026).
Es gab bisher kein explizites Regelwerk-Dokument: Jeder Eintrag traegt
seinen eigenen, gemessenen Grund, aber die Kategorien dahinter waren
implizit. Dieses Modul macht sie explizit und erzeugt das anzuzeigende
Markdown (Ergebnisse-Seite + Signal-Detail bei ⛔).

Wichtig zur Ehrlichkeit: Die Liste ist keine reine Automatik. Die harten
Regeln (Schranke, Martingale) urteilt die Engine auch ohne Liste; die
Liste bewahrt zusätzlich kuratierte Urteile (z. B. grenznahe Risiko-
kombinationen), die eine Neuberechnung sonst verwischen wuerde.
"""
from __future__ import annotations

import html

from . import config

# Kuratierte Kategorien hinter den Grund-Texten der Liste. Ein Signal
# kommt auf die Liste, wenn mindestens eine Kategorie klar erfuellt ist.
KATEGORIEN: list[tuple[str, str]] = [
    ("Drawdown-Schranke verletzt",
     "Equity- oder Balance-Drawdown über der harten Schranke (Standard "
     "30 %). Größte Gruppe der Liste — z. B. EQ-DD 45,9 % bei „Low Risk "
     "Gold“: Der Name lügt, der Drawdown zählt."),
    ("Martingale/Grid ohne bewiesenen Stop",
     "Positions-Eskalation oder Grid-Struktur, deren Verluste ohne "
     "belegten Stop frei laufen. Kapitalvernichtungsstruktur — binärer "
     "Ausschluss unabhängig von den Ertragszahlen."),
    ("Ertrag dauerhaft unter der Schwelle",
     "Monatsertrag unter 5 % oder negativ. Risiko vor Ertrag: Wer im "
     "Guten schon kaum verdient, kompensiert keine Risiken."),
    ("Schwache Handelsqualität",
     "Profit-Faktor, Sharpe oder Winrate so schwach, dass die Historie "
     "keinen belastbaren Edge belegt (z. B. PF 1,17, Sharpe 0,07, "
     "Reliability 76 %, 25 Verluste an einem Tag)."),
    ("Grenznahe Risikokombination",
     "Diskretionskategorie der Analyse-Reihe: Drawdown formal unter der "
     "Schranke, aber nahe dran UND eine tiefe Verlustserie oder eine "
     "weitere Schwäche — die nächste Regimewiederholung würde die "
     "Schranke durchbrechen (Beispiel: Kenni Trades Gold Breakout, "
     "EQ-DD 23,1 % + Balance-DD 27,9 % + 18 Verluste in Serie)."),
    ("Copy-Fragilität oder Kurzlebigkeit",
     "Mini-Konten mit Nachschüssen, Pfennig-Jagd, dominanter Manuellein-"
     "fluss (86 % manuell) oder Track-Records ab 25 Wochen ohne "
     "Aussagekraft — beim Kopieren nicht übertragbar."),
]

HARTREGELN: list[tuple[str, str]] = [
    ("⛔ Ausgeschlossen (Liste)",
     "Signal steht in data/known_signals.json. Überschreibt alles — auch "
     "besser aussehende aktuelle Werte, bis der Eintrag entfernt wird."),
    ("🔴 Drawdown-Schranke verletzt",
     "max(Equity-DD, Trading-DD) über der Schranke — harte Ablehnung."),
    ("🔴 Martingale-Signatur nachgewiesen",
     "Lot-Eskalation nach Verlusten (Median > 1,3x) oder Korb-Muster aus "
     "der Trade-Forensik — harte Ablehnung."),
    ("🟡 Ohne bewiesenen Stop kein Kandidat",
     "Stop-Nachweis nur teilweise oder fehlend — nie Grün, unabhängig "
     "von Score und Ertrag."),
    ("🟡 Score oder Ertrag reichen nicht",
     "Risiko-Score ≥ 5 oder Ertrag unter der Mindestschwelle — nur "
     "Beobachtung."),
]


def ausgeschlossen_eintrag(signal_id: int) -> dict | None:
    """Listen-Eintrag eines Signals (mit Grund) oder None."""
    for eintrag in config.load_known_signals().get("ausgeschlossen", []):
        if eintrag.get("id") == signal_id:
            return eintrag
    return None


def _zelle(text: str) -> str:
    return html.escape(str(text), quote=False).replace("|", "/")


def regelwerk_markdown(settings: dict | None = None) -> str:
    """Vollständiges Regelwerk als Markdown (inkl. aktueller Liste)."""
    settings = settings or {}
    schranke = float(settings.get("schranke_eq_dd_pct", 30.0))
    min_ertrag = float(settings.get("min_ertrag_pct_monat", 5.0))
    known = config.load_known_signals()
    liste = known.get("ausgeschlossen", [])

    zeilen = [
        "## Harte Regeln (urteilt die Engine automatisch)",
        "",
        "Diese Regeln greifen bei jedem Lauf unabhängig von der Liste:",
        "",
    ]
    zeilen += [f"- **{titel}** — {text}" for titel, text in HARTREGELN]
    zeilen += [
        "",
        f"Aktuelle Grenzwerte: Schranke {schranke:g} % Drawdown, "
        f"Mindest-Ertrag {min_ertrag:g} %/Monat, Risiko vor Ertrag, "
        "Stop-Loss muss bewiesen sein (Orderbuch oder Cluster-Signatur), "
        "nicht nur behauptet.",
        "",
        "## Wann kommt ein Signal auf die Ausschlussliste?",
        "",
        "Die Liste wird manuell aus der forensischen Analyse-Reihe "
        "gepflegt (Stand 04.09.2026). Ein Signal wird ausgeschlossen, "
        "wenn mindestens eines dieser Kriterien klar erfüllt ist:",
        "",
    ]
    zeilen += [f"1. **{titel}** — {text}"
               for titel, text in KATEGORIEN]
    zeilen += [
        "",
        "Jeder Listen-Eintrag trägt seinen konkreten, gemessenen Grund "
        "(Tabelle unten und Tooltip in der Ampel-Matrix). Die Liste "
        "bleibt wirksam, bis sie gepflegt wird: Eine bessere aktuelle "
        "Kennzahl hebt den Ausschluss NICHT automatisch auf.",
        "",
        "**Wiederaufnahme:** Nur wenn neue Forensik den Grund entkräftet "
        "(z. B. Orderbuch-Stop-Nachweis, drawdownarmer Lauf über "
        "mehrere Monate) UND der Eintrag aus `data/known_signals.json` "
        "entfernt wird. Danach bewertet die Engine wieder frei.",
    ]
    if liste:
        zeilen += ["", f"## Aktuelle Ausschlüsse ({len(liste)})", "",
                   "| ID | Name | Grund |", "|---|---|---|"]
        for eintrag in liste:
            link = f"[#{eintrag.get('id')}](https://www.mql5.com/en/signals/{eintrag.get('id')})"
            zeilen.append(f"| {_zelle(link)} | {_zelle(eintrag.get('name', ''))} "
                          f"| {_zelle(eintrag.get('grund', ''))} |")
    else:
        zeilen += ["", "Keine Signale ausgeschlossen."]
    return "\n".join(zeilen)
