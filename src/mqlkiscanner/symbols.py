"""Conservative instrument names and quote units; unknown contracts stay unknown.

Instrumente, die keine Klasse hat, koennen ueber data/contract_specs.json
belegt werden (Kontraktgroesse + Gewinnwaehrung + Quelle, z. B. Tickmill-
Contract-Specifications). Ohne Eintrag bleibt alles beim Alten: unbekannt.
"""
from __future__ import annotations

import json
from pathlib import Path
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

    # Konflikt-Regel (Lunar-Fall 06.10.2026): Gibt es fuer denselben Symbol-
    # Namen EINEN broker-spezifischen Eintrag (cross_broker=false) UND einen
    # branchenweiten (cross_broker=true), gewinnt der SPEZIFISCHE — sonst
    # waere z. B. DE40 am Futures-Broker TradeMaxGlobal (25 EUR/Punkt,
    # bewiesen aus 80 Trades) fuer immer auf der Retail-CDD-Annahme
    # (1 EUR/Punkt, Faktor 25 zu klein) gepinnt. Zwei Durchgaenge:
    # erst Broker-gebundene Treffer (exakt + Alias), dann branchenweite.
    def _finde(nur_broker_gebunden: bool) -> dict | None:
        for cand in candidates:
            entry = specs.get(cand)
            if entry is not None and applies(entry) \
                    and bool(entry.get("brokers")) == nur_broker_gebunden:
                return entry
        for cand in candidates:
            for entry in specs.values():
                if cand in [str(a).upper() for a in (entry.get("aliases") or [])] \
                        and applies(entry) \
                        and bool(entry.get("brokers")) == nur_broker_gebunden:
                    return entry
        return None

    return _finde(True) or _finde(False)


def _broker_matches(entry: dict, broker: str | None) -> bool:
    if entry.get("cross_broker", True):
        return True
    allowed = [str(b).casefold() for b in (entry.get("brokers") or [])]
    if not allowed:
        return False
    hay = (broker or "").casefold()
    return bool(hay) and any(tok in hay for tok in allowed)


# ── Broker-Ersetzungstabelle (Nutzer-Wunsch 05.10.) ─────────────────────
# Vantage-Spalte (08.10., MT5-Lesung am eingerichteten Terminal): Aktien
# heissen PLAIN (AAPL, MSFT — keine Ersetzung noetig); Indizes/Öl anders als
# bei Tickmill: NAS100 statt USTEC, SP500 statt US500, USOUSD/UKOUSD statt
# XTIUSD/BRENT; Gold als SUFFIX-Falle XAUUSD+ (plain XAUUSD existiert dort
# NICHT — XAUUSD.crp ist nur Kursumrechnung, XAUUSD247 ein 1-Unzen-Kontrakt).
SYMBOL_ALIASE_DEFAULT = {
    "DE40":  {"activetrades003": "Ger40", "vantage": "GER40"},
    "GER40": {"tickmilllifemql5": "DE40", "activetrades003": "Ger40"},
    "WTI":   {"tickmilllifemql5": "XTIUSD", "activetrades003": "LCrude",
              "vantage": "USOUSD"},
    "USOIL": {"tickmilllifemql5": "XTIUSD", "activetrades003": "LCrude",
              "vantage": "USOUSD"},
    "XTIUSD": {"vantage": "USOUSD"},
    "BRENT": {"vantage": "UKOUSD", "activetrades003": "Brent"},
    "XAUUSD": {"vantage": "XAUUSD+", "activetrades003": "GOLD"},
    # Lokales Vantage-Symbolinventar 08.10.2026 (tmp/mt5_kontrakt_specs_
    # 20261008_0714.json): Goldkreuze tragen ebenfalls das Plus-Suffix.
    "XAUAUD": {"vantage": "XAUAUD+"},
    "XAUEUR": {"vantage": "XAUEUR+"},
    "XAUJPY": {"vantage": "XAUJPY+"},
    "NAS100": {"tickmilllifemql5": "USTEC", "activetrades003": "UsaTec"},
    "US100": {"tickmilllifemql5": "USTEC", "vantage": "NAS100",
              "activetrades003": "UsaTec"},
    "USTEC": {"vantage": "NAS100", "activetrades003": "UsaTec"},
    "NASUSD": {"tickmilllifemql5": "USTEC", "vantage": "NAS100"},
    "SPX500": {"tickmilllifemql5": "US500", "activetrades003": "Usa500"},
    "US500": {"vantage": "SP500", "activetrades003": "Usa500"},
    "SP500": {"activetrades003": "Usa500"},
    "DJ30": {"activetrades003": "UsaInd"},
    "US30": {"activetrades003": "UsaInd"},
    "HK50": {"activetrades003": "HKInd"},
    "CHINA50": {"activetrades003": "ChinaA50"},
    "US500CASH": {"tickmilllifemql5": "US500"},
    "GER30CASH": {"tickmilllifemql5": "DE40"},
    "GER40-FUTURE": {"tickmilllifemql5": "DE40", "activetrades003": "Ger40"},
    "US100-FUTURE": {"tickmilllifemql5": "USTEC", "vantage": "NAS100ft"},
    "US500-FUTURE": {"tickmilllifemql5": "US500"},
    "US30-FUTURE": {"tickmilllifemql5": "US30"},
    "USOIL-FUTURE": {"tickmilllifemql5": "XTIUSD", "vantage": "USOUSD"},
    "BITCOIN": {"tickmilllifemql5": "BTCUSD"},
    # Vantage-FT-Indizes (Nutzer-Hinweis 08.10.: „GER40FT = GER40") —
    # Kursdaten-Alias auf die Tickmill-Referenznamen; Kontrakt-Sizes stehen
    # beweisbasiert in contract_specs.json (Trade-Rueckrechnung).
    "GER40FT": {"tickmilllifemql5": "DE40", "activetrades003": "Ger40"},
    "DJ30FT": {"tickmilllifemql5": "US30"},
    "NAS100FT": {"tickmilllifemql5": "USTEC"},
    "SP500FT": {"tickmilllifemql5": "US500"},
    "JPN225FT": {"tickmilllifemql5": "JP225"},
    "HK50FT": {"tickmilllifemql5": "HK50", "activetrades003": "HKInd"},
    "UK100FT": {"tickmilllifemql5": "UK100"},
    "CL-OIL": {"tickmilllifemql5": "XTIUSD", "activetrades003": "LCrude"},
    # Exact names from VantageMarkets-Live 10 symbol_info, 18.10.2026;
    # case restoration only, no cash/future proxy.
    "NIKKEI225": {"vantage": "Nikkei225"},
    "SOYBEAN-C": {"vantage": "Soybean-C"},
    # RoboForex-CASH-Indizes (Punkt-Präfix-Schreibweise, live 09.10. in
    # Skip-Gründen gesehen) — Kurs-Alias auf die Tickmill-Referenznamen.
    ".US30CASH": {"tickmilllifemql5": "US30"},
    ".USTECHCASH": {"tickmilllifemql5": "USTEC"},
    ".US500CASH": {"tickmilllifemql5": "US500"},
    ".DE40CASH": {"tickmilllifemql5": "DE40"},
    ".JP225CASH": {"tickmilllifemql5": "JP225"},
    ".UK100CASH": {"tickmilllifemql5": "UK100"},
    ".HK50CASH": {"tickmilllifemql5": "HK50"},
    "WT": {"tickmilllifemql5": "XTIUSD", "activetrades003": "LCrude"},
}

# ActivTrades, portables Live-Terminal 10.10.2026:
# doc/reviews/activtrades_instrumentnamen_2026-10-10.json.
# MT5-Namen sind case-sensitiv. LCrude ist Light Crude Oil Spot,
# Brent ein anderer Rohstoff; WTI darf niemals auf Brent ausweichen.
# Die bestehenden FT→Cash-Aliase (u. a. HK50FT) sind Kursreferenzen,
# keine Behauptung gleicher Handelskontrakte. hole_h1 protokolliert die
# Ersetzung in suffix_annahmen; die Signal-Kontraktspezifikation bleibt separat.

# Live-Inventar des portablen Vantage-Terminals, 10.10.2026:
# doc/reviews/mt5_vantage_symbolnamen_2026-10-10.json. Nur belegte
# Forex+-Namen ergänzen; Aktien, Indizes und Krypto haben andere Namen.
for _fx in (
    "EURNOK EURSEK USDMXN USDZAR AUDCAD AUDCHF AUDJPY AUDUSD CADCHF CADJPY "
    "CHFJPY EURAUD EURCAD EURCHF EURGBP EURJPY EURUSD GBPAUD GBPCAD GBPCHF "
    "GBPJPY GBPUSD USDCAD USDCHF USDJPY EURCZK EURDKK EURHUF EURPLN EURTRY "
    "USDBRL USDCLP USDCOP USDCZK USDDKK USDHUF USDIDR USDINR USDKRW USDPLN "
    "USDTHB USDTRY USDTWD AUDCNH AUDNZD AUDSGD CHFSGD EURNZD EURSGD GBPNZD "
    "GBPSGD NZDCAD NZDCHF NZDJPY NZDSGD NZDUSD SGDJPY USDCNH USDHKD USDNOK "
    "USDSEK USDSGD USDILS"
).split():
    SYMBOL_ALIASE_DEFAULT.setdefault(_fx, {})["vantage"] = _fx + "+"

# MT5-Namen sind case-sensitiv: der CSV-Name DJ30FT ist nicht DJ30ft.
for _future in (
    "DJ30 FRA40 GER40 NAS100 SP500 UK100 CHINA50 HK50 JPN225 UKOUSD"
).split():
    SYMBOL_ALIASE_DEFAULT.setdefault(_future + "FT", {})["vantage"] = _future + "ft"


def terminal_key(terminal_pfad: str) -> str:
    """Terminal-Pfad → kurzer Schlüssel für die Alias-Tabelle."""
    return Path(terminal_pfad).parent.name.lower().replace(" ", "")


def alias_fuer_symbol(kanonisch: str, terminal_pfad: str,
                      aliases: dict | None = None) -> str | None:
    """Broker-spezifischer Name für ein kanonisches Symbol — oder None."""
    tabelle = aliases or SYMBOL_ALIASE_DEFAULT
    eintrag = tabelle.get(kanonisch.upper().strip())
    if not eintrag:
        return None
    key = terminal_key(terminal_pfad)
    return eintrag.get(key) or None
