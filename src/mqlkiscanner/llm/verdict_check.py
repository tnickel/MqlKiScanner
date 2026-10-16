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
import math


_URTEIL_RE = re.compile(
    r"(?:Urteilszeile|Urteil)\s*(?:\([^)]*\))?\s*[:：\-–—]\s*(?:\*\*)?\s*(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b",
    re.IGNORECASE,
)
_FALLBACK_URTEIL_RE = re.compile(
    r"\b(EMPFEHLUNG|WATCHLIST|ABLEHNUNG)\b",
)

_PORTFOLIO_ROW_RE = re.compile(
    r"^\s*[-*]\s+(?P<name>.+?)\s+[—–\-]+\s+(?P<pct>[+-]?\d+(?:[.,]\d+)?)\s*%\s+[—–\-]+\s+(?P<rolle>.+?)\s*$",
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
        # ALLE Urteilszeilen anpassen (nicht nur die erste) — sonst bleibt
        # ein zweites, widersprüchliches Urteil im Bericht stehen (Review).
        text_out = _URTEIL_RE.sub(
            lambda m: m.group(0).replace(m.group(1), korrigiert),
            text_out,
        )
        text_out += hinweis

    return text_out, korrigiert, warnungen


def parse_and_validate_portfolio(
    portfolio_text: str,
    cand_ampeln: dict[str, str] | None = None,
    *, cand_ids: dict[str, tuple[str, str]] | None = None,
    ambiguous_names: set[str] | None = None,
) -> dict:
    """Parst Allokationszeilen `- NAME — GEWICHT % — Rolle` und validiert sie.

    cand_ampeln: optionales Mapping {name: ampel} aller geprueften Signale.
    """
    allokationen: list[dict] = []
    warnungen: list[str] = []

    if not portfolio_text:
        return {"allokationen": [], "summe_gewicht": 0.0,
                "warnungen": ["Kein Portfolio-Text vorhanden."], 'valid': False}

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

    # Never publish allocation-looking lines that bypass the strict parser.
    for line in portfolio_text.splitlines():
        if re.match(r'^\s*[-*]\s+', line) and '%' in line and not _PORTFOLIO_ROW_RE.fullmatch(line):
            warnungen.append(f"Nicht prüfbare Allokationszeile: {line.strip()}")

    for a in allokationen:
        if not math.isfinite(a['gewicht_pct']) or not 0 <= a['gewicht_pct'] <= 100:
            warnungen.append(f"Ungültiges Gewicht für '{a['name']}'.")

    summe = sum(a["gewicht_pct"] for a in allokationen)

    # 1. Pruefung: Nicht-Gruene Signale gewichtet?
    if cand_ampeln is not None:
        # Normalisierter Match
        lookup = {k.strip().lower(): (k, v) for k, v in cand_ampeln.items()}
        seen = set()
        for a in allokationen:
            key = a["name"].strip().lower()
            identity = re.match(r'^\[([A-Za-z0-9_-]+:\d+)\]\s*(.*)$', a['name'])
            if identity:
                token, supplied_name = identity.groups()
                match = (cand_ids or {}).get(token)
                if match and supplied_name.strip().casefold() == match[0].strip().casefold():
                    a['signal_key'] = token
                    a['name'] = match[0]
                    key = match[0].strip().lower()
                    ampel = match[1]
                else:
                    warnungen.append(f"Unbekannte oder widersprüchliche Signalidentität '{token}'.")
                    continue
                known = True
            else:
                known = key in lookup and key not in (ambiguous_names or set())
                ampel = lookup[key][1] if known else None
                identities = [token for token, (name, _) in (cand_ids or {}).items()
                              if name.strip().lower() == key]
                if known and len(identities) == 1:
                    a['signal_key'] = identities[0]
            if not known:
                warnungen.append(f"Signal '{a['name']}' ist unbekannt oder mehrdeutig; keine Freigabe.")
                continue
            unique = a.get('signal_key', key)
            if unique in seen:
                warnungen.append(f"Signal '{a['name']}' wurde mehrfach gewichtet.")
            seen.add(unique)
            if ampel != '🟢' and a['gewicht_pct'] > 0:
                warnungen.append(f"Signal '{a['name']}' hat Ampel {ampel}, wurde aber mit "
                                  f"{a['gewicht_pct']} % gewichtet (nur 🟢-Kandidaten erlaubt).")

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
        "valid": not warnungen,
    }
