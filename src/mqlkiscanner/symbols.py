"""Conservative instrument names and quote units; unknown contracts stay unknown.

Instrumente, die keine Klasse hat, koennen ueber data/contract_specs.json
belegt werden (Kontraktgroesse + Gewinnwaehrung + Quelle, z. B. Tickmill-
Contract-Specifications). Ohne Eintrag bleibt alles beim Alten: unbekannt.
"""
from __future__ import annotations

import json
import re

from . import config


_CURRENCIES = frozenset((
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SGD", "HKD",
    "CNH", "CNY", "NOK", "SEK", "DKK", "ZAR", "MXN", "TRY", "PLN", "HUF",
    "CZK", "RUB",
))
_INDEX_ALIASES = {
    "US30": "US30", "US500": "US500", "SPX500": "US500", "SPX": "US500",
    "US100": "US100", "NAS100": "US100", "NDX": "US100",
    "GER40": "GER40", "UK100": "UK100", "JP225": "JP225", "CHINA50": "CHINA50",
}
_KNOWN = tuple(sorted({"XAUUSD", *_INDEX_ALIASES}, key=len, reverse=True))
_BROKER_SUFFIX = re.compile(r"(?:[._+\-][A-Z0-9._+\-]*|M|R|C|PRO|RAW|ECN|MICRO|CENT)?$")


def normalize_symbol(symbol: str) -> str:
    """Remove explicit broker suffixes only from recognized instruments.

    Arbitrary prefixes/substrings are deliberately not treated as instruments:
    e.g. EURUSDT must not silently become EURUSD.
    """
    value = (symbol or "").strip().upper()
    if (len(value) >= 6 and value[:3] in _CURRENCIES
            and value[3:6] in _CURRENCIES and value[:3] != value[3:6]
            and _BROKER_SUFFIX.fullmatch(value[6:])):
        return value[:6]
    for core in _KNOWN:
        if value.startswith(core) and _BROKER_SUFFIX.fullmatch(value[len(core):]):
            return _INDEX_ALIASES.get(core, core)
    # Contract specs extend the set of explicitly recognized instruments.
    # Preserve an alias as the canonical display key because several
    # broker-specific specs may intentionally share it (e.g. USOUSD).
    for spec_name, entry in load_specs().items():
        for known_name in (spec_name, *(entry.get("aliases") or [])):
            known = str(known_name).upper()
            if value.startswith(known) and _BROKER_SUFFIX.fullmatch(value[len(known):]):
                return known
    return value


def fx_pip_size(symbol: str) -> float | None:
    value = normalize_symbol(symbol)
    if (len(value) == 6 and value[:3] in _CURRENCIES and value[3:] in _CURRENCIES
            and value[:3] != value[3:]):
        return 0.01 if value[3:] == "JPY" else 0.0001
    return None


def symbol_class(symbol: str) -> str:
    value = normalize_symbol(symbol)
    if value == "XAUUSD":
        return "METAL"
    if value in _INDEX_ALIASES.values():
        return "INDEX"
    if fx_pip_size(value) is not None:
        return "FX"
    return "UNKNOWN"


# --------------------------------------------------------------- Spec-Datei
# Cache je (Pfad, mtime): Der Exposure-Test loest Symbole pro Snapshot auf
# (tausende Aufrufe je Lauf), die JSON ist aber winzig — Schluessel mit
# mtime, damit Tests/Edits sofort greifen und keine alten Werte kleben.
_SPECS_CACHE: dict = {}


def load_specs() -> dict[str, dict]:
    """Inhalt von data/contract_specs.json -> {symbol: eintrag}."""
    path = config.CONTRACT_SPECS_FILE
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if key not in _SPECS_CACHE:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        entry_map = data.get("symbols") if isinstance(data, dict) else None
        _SPECS_CACHE.clear()
        _SPECS_CACHE[key] = {
            name.upper(): entry for name, entry in (entry_map or {}).items()
            if isinstance(entry, dict)
        }
    return _SPECS_CACHE[key]


def spec_for(symbol: str, broker: str | None = None,
             *, ignore_broker: bool = False) -> dict | None:
    """Belegter Spec-Eintrag fuer ein Symbol, sonst None.

    Matching: exakter Name, Broker-Suffix bereinigt ("USOUSD-ECN" ->
    "USOUSD") und Alias-Namen aus der Spec-Datei. Eintraege mit
    cross_broker=false gelten nur, wenn `broker` einen der gelisteten
    Broker-Namen enthaelt (Teilstring-Match). Mit ignore_broker=True
    entfaellt die Broker-Pruefung — nur fuer Diagnose-/Fehlermeldungen,
    nie fuer die Schockrechnung.
    """
    specs = load_specs()
    if not specs:
        return None
    value = (symbol or "").strip().upper()
    candidates = [value]
    stripped = re.split(r"[._+\-]", value, maxsplit=1)[0]
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    normalized = normalize_symbol(value)
    if normalized not in candidates:
        candidates.append(normalized)

    def applies(entry: dict) -> bool:
        return ignore_broker or _broker_matches(entry, broker)

    for cand in candidates:
        entry = specs.get(cand)
        if entry is not None and applies(entry):
            return entry
    for cand in candidates:
        for entry in specs.values():
            if cand in [str(a).upper() for a in (entry.get("aliases") or [])] \
                    and applies(entry):
                return entry
    return None


def _broker_matches(entry: dict, broker: str | None) -> bool:
    if entry.get("cross_broker", True):
        return True
    allowed = [str(b).casefold() for b in (entry.get("brokers") or [])]
    if not allowed:
        return False
    hay = (broker or "").casefold()
    return bool(hay) and any(tok in hay for tok in allowed)
