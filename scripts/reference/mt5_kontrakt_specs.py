# -*- coding: utf-8 -*-
"""MT5-Kontraktspezifikationen auslesen (NUR LESEND, Beleg-Helfer).

Liest je Symbol die Terminal-Spec (symbol_info) aus lokalen MT5-
Installationen: Contract Size (trade_contract_size), Gewinnwaehrung
(currency_profit), Volumen-/Tick-Details. Zweck: Belege fuer Eintraege in
data/contract_specs.json — die Spec gilt IMMER fuer den Broker des
angefragten Terminals, nie automatisch branchenweit (Oel-Falle: 1 vs 100
vs 1000 Barrel je Lot).

Terminals (Standard, alle C:\\Forex\\Mt5\\...):
  - TickmillLifeMql5   Referenzbroker der Spec-Datei (Forex/Indizes/Metalle)
  - ActiveTrades003    zweite Kursdatenquelle, hat Aktien
  - Vantage            beweist Vantage-Eintraege direkt am Broker

Terminal-Politik wie kursdaten.py: laeuft das Terminal nicht, wird es nur
mit Start-Freigabe portabel gestartet; am Ende wird es (pfadgenau) wieder
beendet — das Terminal gehoert dem Scanner (doc/19 §7.3). MT5-Python ist
pro Prozess ein Singleton: Terminals STRENG nacheinander abfragen.

Aufruf:
  python scripts/reference/mt5_kontrakt_specs.py SYMBOL [SYMBOL ...]
  python scripts/reference/mt5_kontrakt_specs.py --suche TEIL          # Gruppensuche
  python scripts/reference/mt5_kontrakt_specs.py --terminal PFAD SYMBOL
Ergebnis: Tabelle je Terminal + JSON-Evidenzdatei in tmp/.
"""
import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mqlkiscanner import config                      # noqa: E402
from mqlkiscanner.agenten.marktdata import (         # noqa: E402
    terminal_beenden, terminal_laueft)
from mqlkiscanner.symbols import (                   # noqa: E402
    alias_fuer_symbol, normalize_symbol)

DEFAULT_TERMINALS = [
    r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe",
    r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe",
    r"C:\Forex\Mt5\Vantage\terminal64.exe",
]

# Nur diese mt5-Aufrufe sind erlaubt (Whitelist-Stil wie kursdaten.py).
ERLAUBTE_MT5_AUFRUFE = frozenset((
    "initialize", "shutdown", "last_error", "symbols_get",
    "symbol_select", "symbol_info", "terminal_info",
))


def _verbinden(mt5, pfad: str) -> tuple[bool, str]:
    """Terminal verbinden; portabler Selbststart, wenn es nicht laeuft."""
    settings = config.load_settings()
    laeuft = terminal_laueft(pfad)
    if not laeuft and not settings.get("markt_start_erlauben", False):
        return False, "laeuft nicht, Selbststart nicht erlaubt (markt_start_erlauben)"
    if not Path(pfad).exists():
        return False, "Pfad existiert nicht"
    ok = bool(mt5.initialize(pfad, portable=not laeuft))
    if not ok:
        fehler = str(mt5.last_error())
        mt5.shutdown()
        return False, f"initialize fehlgeschlagen: {fehler}"
    info = mt5.terminal_info()
    broker = getattr(info, "company", "?") if info else "?"
    return True, (f"{broker} (portabel gestartet)" if not laeuft else f"{broker} (Attach)")


def _kandidaten(symbol: str, terminal_pfad: str) -> list[str]:
    """Exakt → normalisiert → Broker-Alias (wie kursdaten.hole_h1)."""
    kandidaten = [symbol.strip()]
    normalisiert = normalize_symbol(symbol)
    if normalisiert not in kandidaten:
        kandidaten.append(normalisiert)
    alias = alias_fuer_symbol(symbol, terminal_pfad,
                              config.load_settings().get("symbol_aliases"))
    if alias and alias.upper() not in [k.upper() for k in kandidaten]:
        kandidaten.append(alias)
    return kandidaten


def _symbol_lesen(mt5, symbol: str, terminal_pfad: str) -> dict | None:
    for kandidat in _kandidaten(symbol, terminal_pfad):
        if not mt5.symbol_select(kandidat, True):
            continue
        info = mt5.symbol_info(kandidat)
        if info is None:
            continue
        return {
            "symbol": info.name,
            "beschreibung": getattr(info, "description", "") or "",
            "contract_size": float(info.trade_contract_size),
            "gewinnwaehrung": (getattr(info, "currency_profit", "") or "").upper(),
            "basiswaehrung": (getattr(info, "currency_margin", "") or "").upper(),
            "volume_min": float(info.volume_min),
            "volume_step": float(info.volume_step),
            "tick_size": float(info.trade_tick_size),
            "tick_value": float(info.trade_tick_value),
            "digits": int(info.digits),
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("symbole", nargs="*", help="Symbole, z. B. ADBE USTECH ETHBCH")
    parser.add_argument("--suche", action="append", default=[],
                        help="Gruppensuche je Terminal (Teilstring, mehrfach)")
    parser.add_argument("--terminal", action="append", default=[],
                        help="Terminal-Pfad (mehrfach); Standard: 3 Referenzterminals")
    parser.add_argument("--json", default="", help="JSON-Evidenzdatei (Standard tmp/…)")
    args = parser.parse_args()
    if not args.symbole and not args.suche:
        parser.error("Mindestens ein SYMBOL oder --suche TEIL nötig.")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        print(f"MetaTrader5-Paket nicht verfügbar: {exc}")
        return 2

    terminals = args.terminal or DEFAULT_TERMINALS
    ergebnis: dict[str, dict] = {}
    for terminal_pfad in terminals:
        schluessel = Path(terminal_pfad).parent.name
        ok, msg = _verbinden(mt5, terminal_pfad)
        print(f"\n=== {schluessel}: {msg}")
        if not ok:
            ergebnis[schluessel] = {"fehler": msg}
            continue
        terminal_daten: dict = {}
        try:
            for symbol in args.symbole:
                daten = _symbol_lesen(mt5, symbol, terminal_pfad)
                terminal_daten[symbol.upper()] = daten
                if daten:
                    print(f"  {symbol.upper():<14} -> {daten['symbol']:<16} "
                          f"CS={daten['contract_size']:<10g} {daten['gewinnwaehrung']} "
                          f"| {daten['beschreibung'][:40]}")
                else:
                    print(f"  {symbol.upper():<14} -> —")
            for teil in args.suche:
                treffer = mt5.symbols_get(group=f"*{teil}*")
                namen = sorted({s.name for s in (treffer or ())})[:25]
                terminal_daten[f"suche:{teil}"] = namen
                print(f"  Suche *{teil}*: {len(namen)} Treffer "
                      f"{namen[:12]}{' …' if len(namen) > 12 else ''}")
        finally:
            mt5.shutdown()
            terminal_beenden(terminal_pfad)
        ergebnis[schluessel] = terminal_daten

    json_pfad = args.json or (Path("tmp") / f"mt5_kontrakt_specs_"
                                f"{datetime.now(timezone.utc):%Y%m%d_%H%M}.json")
    json_pfad = Path(json_pfad)
    json_pfad.parent.mkdir(parents=True, exist_ok=True)
    json_pfad.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"\nJSON-Evidenz: {json_pfad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
