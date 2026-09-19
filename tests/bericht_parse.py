# -*- coding: utf-8 -*-
"""Parse-Hilfen fuer LLM-Berichtsformate (geteilt von Tests genutzt).

Kein Testmodul (kein test_-Praefix): enthaelt nur deterministische Parser,
die in den immer laufenden Unit-Tests UND den opt-in LLM-Regressionstests
verwendet werden. Der Portfolio-Prompt erzwingt Listenzeilen der Form
'- NAME — GEWICHT % — Rolle'; _aufnahmen liest genau diese — Ausschluss-
gruende in Prosa (mit Prozentzahlen) matchen bewusst nicht.
"""
from __future__ import annotations

import re

_LISTEN_ZEILE = re.compile(
    r"^\s*[-*]\s*\*{0,2}(?P<name>[^\n*—]+?)\*{0,2}\s*[—-]\s*"
    r"(?P<gewicht>\d+)\s*(?:%|Prozent)", re.MULTILINE)


def aufnahmen(text: str) -> dict[str, int]:
    """NAME -> Gewichtung % aus maschinenlesbaren Portfolio-Listenzeilen."""
    return {m.group("name").strip(): int(m.group("gewicht"))
            for m in _LISTEN_ZEILE.finditer(text)}


def hat_aufnahme(aufnahmen_: dict[str, int], name: str) -> bool:
    return any(name in list_name for list_name in aufnahmen_)


def urteil(bericht: str) -> str | None:
    """Verdikt aus dem Urteil-Abschnitt, tolerant gegen Gross/kleinschreibung.

    Bevorzugt wird der Abschnitt unter der letzten 'Urteil'-Ueberschrift;
    ohne solche Ueberschrift zaehlt die erste Zeile, die 'Urteil' UND ein
    Verdikt-Wort enthaelt. Zurueckgegeben wird stets GROSSGESCHRIEBEN.
    """
    headers = list(re.finditer(r"(?im)^#{1,6}[^\n]*urteil[^\n]*$", bericht))
    if headers:
        chunk = bericht[headers[-1].end():]
        next_header = re.search(r"(?im)^#{1,6}", chunk)
        if next_header:
            chunk = chunk[:next_header.start()]
        m = re.search(r"(?i)\b(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b", chunk)
        return m.group(1).upper() if m else None
    for line in bericht.splitlines():
        if "urteil" in line.lower():
            m = re.search(r"(?i)\b(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b", line)
            if m:
                return m.group(1).upper()
    return None


def abschnitt(text: str, titel: str) -> str:
    m = re.search(rf"##+ *\d*\.? *{re.escape(titel)}.*?(?=\n##+ |\Z)",
                  text, re.IGNORECASE | re.DOTALL)
    return m.group(0) if m else text
