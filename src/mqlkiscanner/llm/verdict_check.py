# -*- coding: utf-8 -*-
"""Validierung von LLM-Urteilen und Portfolio-Gewichtungen (AGENTS.md Design-Regeln).

Kernprinzipien:
1. Code rechnet und setzt harte Schranken; das LLM darf die Engine-Ampel nie aufwerten.
   - Ampel 🔴 oder ⛔ -> Nur ABLEHNUNG zulaessig.
   - Ampel 🟡 -> Nur WATCHLIST oder ABLEHNUNG zulaessig (keine EMPFEHLUNG).
   - Ampel 🟢 -> EMPFEHLUNG, WATCHLIST oder ABLEHNUNG zulaessig.
2. Im Portfolio-Mix duerfen ausschliesslich 🟢-Kandidaten gewichtet werden.
   Summe der Allokationen sollte ca. 100 % betragen.
"""
from __future__ import annotations

import re


_URTEIL_RE = re.compile(
    r"(?:Urteilszeile|Urteil)\s*(?:\([^)]*\))?\s*[:：\-—]\s*(?:\*\*)?\s*(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b",
    re.IGNORECASE,
)
_FALLBACK_URTEIL_RE = re.compile(
    r"\b(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b",
)

_PORTFOLIO_ROW_RE = re.compile(
    r"^\s*[-*]\s+(?P<name>.+?)\s+[—–\-]+\s+(?P<pct>\d+(?:[.,]\d+)?)\s*%\s+[—–\-]+\s+(?P<rolle>.+?)\s*$",
    re.MULTILINE,
)


def extract_llm_urteil(gesamtbericht: str) -> str | None:
    """Sucht das explizite Urteil (EMPFEHLUNG / WATCHLIST / ABLEHNUNG) im Gesamtbericht."""
    if not gesamtbericht:
        return None
    # 1. Bevorzugt: Suche nach Urteilszeile oder Abschnitt Urteil
    m = _URTEIL_RE.search(gesamtbericht)
    if m:
        return m.group(1).upper()
    # 2. Suche in den letzten 3000 Zeichen (wo Urteil/Fazit typischerweise steht)
    tail = gesamtbericht[-3000:]
    matches = _FALLBACK_URTEIL_RE.findall(tail)
    if matches:
        return matches[-1].upper()
    return None


def validate_and_sanitize_verdict(
    gesamtbericht: str,
    ampel: str,
) -> tuple[str, str | None, list[str]]:
    """Prueft das Urteil des Gesamtberichts gegen die Engine-Ampel.

    Rueckgabe: (bereinigter_bericht, erkanntes_urteil, warnungen)
    Falls das LLM gegen harte Ampel-Vorgaben verstoesst, wird das Urteil
    im Text korrigiert und eine Warnung erzeugt.
    """
    warnungen: list[str] = []
    if not gesamtbericht:
        return gesamtbericht, None, warnungen

    urteil = extract_llm_urteil(gesamtbericht)
    korrigiert = urteil
    meldung = ""

    if ampel in ("🔴", "⛔"):
        if urteil in ("EMPFEHLUNG", "WATCHLIST"):
            korrigiert = "ABLEHNUNG"
            meldung = (
                f"Modell-Urteil '{urteil}' widerspricht harter Engine-Ampel {ampel}. "
                "Automatisch auf ABLEHNUNG korrigiert (AGENTS.md Kriterienbindung)."
            )
            warnungen.append(meldung)
    elif ampel == "🟡":
        if urteil == "EMPFEHLUNG":
            korrigiert = "WATCHLIST"
            meldung = (
                "Modell-Urteil 'EMPFEHLUNG' widerspricht Beobachtungs-Ampel 🟡. "
                "Automatisch auf WATCHLIST korrigiert (AGENTS.md Kriterienbindung)."
            )
            warnungen.append(meldung)

    if not urteil:
        warnungen.append("Kein klares Urteil (EMPFEHLUNG/WATCHLIST/ABLEHNUNG) im Gesamtbericht erkannt.")

    # Text anpassen, falls korrigiert werden musste
    text_out = gesamtbericht
    if meldung and korrigiert and urteil:
        hinweis = f"\n\n> [!WARNING]\n> **Korrektur durch Scanner-Regelwerk:** {meldung}\n"
        # Falls eine spezifische Urteilszeile existiert, ersetzen
        text_out = _URTEIL_RE.sub(
            lambda m: m.group(0).replace(m.group(1), korrigiert),
            text_out,
            count=1,
        )
        text_out += hinweis

    return text_out, korrigiert, warnungen


def parse_and_validate_portfolio(
    portfolio_text: str,
    cand_ampeln: dict[str, str] | None = None,
) -> dict:
    """Parst Allokationszeilen `- NAME — GEWICHT % — Rolle` und validiert sie.

    cand_ampeln: optionales Mapping {name: ampel} aller geprueften Signale.
    """
    allokationen: list[dict] = []
    warnungen: list[str] = []

    if not portfolio_text:
        return {"allokationen": [], "summe_gewicht": 0.0, "warnungen": ["Kein Portfolio-Text vorhanden."]}

    for m in _PORTFOLIO_ROW_RE.finditer(portfolio_text):
        name = m.group("name").strip().strip("*")
        raw_pct = m.group("pct").replace(",", ".")
        try:
            pct = float(raw_pct)
        except ValueError:
            continue
        rolle = m.group("rolle").strip().strip("*")
        allokationen.append({
            "name": name,
            "gewicht_pct": pct,
            "rolle": rolle,
        })

    summe = sum(a["gewicht_pct"] for a in allokationen)

    # 1. Pruefung: Nicht-Gruene Signale gewichtet?
    if cand_ampeln:
        # Normalisierter Match
        lookup = {k.strip().lower(): (k, v) for k, v in cand_ampeln.items()}
        for a in allokationen:
            key = a["name"].lower()
            if key in lookup:
                orig_name, ampel = lookup[key]
                if ampel != "🟢" and a["gewicht_pct"] > 0:
                    warnungen.append(
                        f"Signal '{orig_name}' hat Ampel {ampel}, wurde aber mit "
                        f"{a['gewicht_pct']} % gewichtet (nur 🟢-Kandidaten erlaubt)."
                    )

    # 2. Pruefung: Gesamtsumme
    if allokationen:
        if abs(summe - 100.0) > 10.0:
            warnungen.append(
                f"Die Summe der Portfolio-Gewichte beträgt {summe:.1f} % (erwartet: ca. 100 %)."
            )
    else:
        warnungen.append(
            "Keine formatierten Allokationszeilen ('- NAME — GEWICHT % — Rolle') im Portfolio-Vorschlag gefunden."
        )

    return {
        "allokationen": allokationen,
        "summe_gewicht": round(summe, 2),
        "warnungen": warnungen,
    }
