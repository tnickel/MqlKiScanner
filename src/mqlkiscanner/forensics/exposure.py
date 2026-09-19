# -*- coding: utf-8 -*-
"""Forensik-Test 2: Peak-Exposure (Spec: doc/03_forensik-tests.md).

Maximal gleichzeitig offene Positionen + aggregiertes Volumen, umgerechnet
in Dollar-Risiko. Kontraktgroessen (doc/02 Abschnitt 5):
  XAUUSD: 1 Lot = 100 USD je 1 USD Kursbewegung  (der teure Lernpunkt)
  US-Indizes (Projektkonvention): 1 Lot = 1 USD je Punkt
  FX: 1 Lot = 100 000 Basiseinheiten; Gewinn zunaechst in Kurswaehrung.
  USD-Konvention des Projekts: Kontostaende und bekannte US-Indexkontrakte
  werden als USD gefuehrt. Fremdwaehrungs-Quotes (FX-Kreuze, EUR-Gold, DE40)
  werden mit den belegten EZB-Euro-Referenzkursen des jeweiligen Handelstags
  nach USD umgerechnet (Cross-Kurs ueber EUR/USD, fx_rates.py); ohne
  belegten Kurs bleiben die Werte ehrlich unbekannt.

Kontrakte ohne Klassenkonvention koennen ueber data/contract_specs.json
belegt werden (Quelle z. B. Tickmill-Contract-Specifications). Eintraege
mit cross_broker=false gelten nur fuer die gelisteten Broker (Teilstring-
Match auf `broker`) — Oel ist der bekannte Fallstrick: Tickmill 1 Barrel
je Lot, viele andere Broker 100. Ein Symbol ohne Klasse UND ohne Spec
bleibt ein harter Fehler; Klasse ohne Faktor (z. B. GER40) bleibt weich.

Schockszenario je Symbolklasse:
  Metall 50 USD Kursbewegung | Index 50 Punkte | FX 500 Pips (JPY: 5.00)
  Spec-Eintraege tragen ihre eigene stress_move in Preiseinheiten.

Zwei Peak-Masse (Spec-Frage: max. aggregierte Marktposition / Schockkosten):
  - peak_open_positions: Maximum der Positions*anzahl*
  - shock_usd / peak_net_*: am Zeitpunkt des maximalen Dollar-Schocks
    (Volumen-Peak je Symbol, kein Cross-Symbol-Lot-Netting als Hedge)

Rote Flagge: Schockszenario > 30 % des Kontos (scoring.margin / flag).
Referenz: scripts/reference/martingale_exposure_test.py (Test 4).
"""
from __future__ import annotations

from collections import defaultdict
from itertools import groupby
import math

from .. import fx_rates
from ..models import ParsedExport
from ..symbols import fx_pip_size, normalize_symbol, spec_for, symbol_class

# Kontraktfaktor je 1.00 Kurseinheit und Lot, FX in KURSwaehrung.
CONTRACT_FACTOR_PER_UNIT: dict[str, float] = {
    "METAL": 100.0,   # XAUUSD (andere Metalle via contract_specs.json)
    "INDEX": 1.0,     # nur freigegebene US-Indexkonvention, siehe unten
    "FX": 100_000.0,
}

# Die Klasse INDEX allein belegt weder Punktwert noch Gewinnwaehrung.
# US-Konvention beibehalten; fremde Indizes brauchen Brokerspezifikationen.
USD_INDEX_SYMBOLS = frozenset(("US30", "US100", "US500"))

# Stressbewegung je Symbolklasse in Preiseinheiten
STRESS_MOVE_BY_CLASS: dict[str, float] = {
    "METAL": 50.0,
    "INDEX": 50.0,
    "FX": 0.05,   # 500 Pips bei 4. Dezimale
}

_UNIT_LABEL = {"METAL": "USD Kursbewegung", "INDEX": "Punkte",
               "FX": "Preiseinheiten"}


def _resolve_symbol(symbol: str, broker: str | None = None) -> dict | None:
    """Aufgeloester Kontrakt je Symbol oder None (kein belegter Kontrakt).

    Spec-Eintrag (data/contract_specs.json) gewinnt gegenueber der
    Klassenkonvention; `broker` schraenkt cross_broker=false-Eintraege ein.
    """
    spec = spec_for(symbol, broker=broker)
    sclass = symbol_class(symbol)
    if spec is not None and spec.get("contract_size") is not None:
        pip = fx_pip_size(symbol)
        if spec.get("stress_move") is not None:
            move = float(spec["stress_move"])
        elif pip is not None:
            move = 500 * pip
        else:
            move = STRESS_MOVE_BY_CLASS.get(sclass, 0.0)
        return {
            "factor": float(spec["contract_size"]),
            "quote": str(spec.get("quote_currency") or "USD").upper(),
            "move": move,
            "unit": str(spec.get("unit_label") or _UNIT_LABEL.get(sclass, "Preiseinheiten")),
            "source": str(spec.get("source") or "contract_specs.json"),
            "spec": True,
        }
    if sclass == "INDEX" and normalize_symbol(symbol) not in USD_INDEX_SYMBOLS:
        return None
    factor = CONTRACT_FACTOR_PER_UNIT.get(sclass)
    if factor is None:
        return None
    pip = fx_pip_size(symbol)
    move = 500 * pip if pip is not None else STRESS_MOVE_BY_CLASS[sclass]
    quote = normalize_symbol(symbol)[-3:] if sclass == "FX" else "USD"
    return {"factor": factor, "quote": quote, "move": move,
            "unit": _UNIT_LABEL[sclass], "source": "klassenkonvention",
            "spec": False}


def _contract_factor(symbol: str, broker: str | None = None) -> float | None:
    resolved = _resolve_symbol(symbol, broker)
    return resolved["factor"] if resolved else None


def _quote_currency(symbol: str, broker: str | None = None) -> str | None:
    resolved = _resolve_symbol(symbol, broker)
    return resolved["quote"] if resolved else None


def _stress_move(symbol: str, override: float | None = None,
                 broker: str | None = None) -> float:
    if override is not None:
        return override
    resolved = _resolve_symbol(symbol, broker)
    if resolved:
        return resolved["move"]
    # Nur erreichbar fuer Spec-freie Symbole mit Klasse aber ohne Faktor
    # (fremder Index): Szenario in Punkten, auch ohne USD-Schock nutzbar.
    pip = fx_pip_size(symbol)
    if pip is not None:
        return 500 * pip
    return STRESS_MOVE_BY_CLASS.get(symbol_class(symbol), 50.0)


def shock_usd(net_lots: float, move: float, symbol: str,
              broker: str | None = None) -> float | None:
    """Dollar-Risiko einer Gegenbewegung `move` Preiseinheiten bei `net_lots`.

    Kein belegter Kontrakt: Klasse UNKNOWN -> harter Fehler; bekannte Klasse
    ohne Faktor (fremder Index) -> None, wie bei fehlender USD-Umrechnung.
    """
    resolved = _resolve_symbol(symbol, broker)
    if resolved is None:
        if symbol_class(symbol) == "UNKNOWN":
            raise ValueError(f"Unbekanntes Instrument {symbol!r}: Kontraktgroesse nicht belegt")
        return None
    if resolved["quote"] != "USD":
        return None
    return abs(net_lots) * move * resolved["factor"]


def _portfolio_shock(net_by_symbol: dict[str, float],
                     stress_move: float | None = None,
                     resolutions: dict | None = None,
                     broker: str | None = None,
                     when=None,
                     fx_state: dict | None = None) -> tuple[float | None, str]:
    """Schock je Symbol mit eigenem Kontrakt, dann summieren (kein Cross-Hedge).

    Fremdwaehrungs-Quotes (EUR-Gold, FX-Kreuze, DE40) werden mit dem
    EZB-Referenzkurs des Handelstags nach USD umgerechnet; fehlt der Kurs,
    bleibt der Gesamtschock unbekannt (fx_state zeichnet den Grund auf).
    """
    total = 0.0
    dominant = ""
    dominant_abs = 0.0
    complete = True
    for sym, net in net_by_symbol.items():
        if abs(net) < 1e-12:
            continue
        resolved = (resolutions or {}).get(sym) or _resolve_symbol(sym, broker)
        move = _stress_move(sym, stress_move, broker)
        if resolved is None:
            amount = None
        else:
            native = abs(net) * move * resolved["factor"]
            if resolved["quote"] == "USD":
                amount = native
            else:
                fx = fx_rates.usd_per(resolved["quote"], when.date()) if when else None
                amount = native * fx["rate"] if fx else None
                if fx is None and fx_state is not None:
                    fx_state["complete"] = False
                    fx_state["missing"].add(f"{sym} ({resolved['quote']})")
        if amount is None:
            complete = False
        else:
            total += amount
        if abs(net) >= dominant_abs:
            dominant_abs = abs(net)
            dominant = sym
    return (total if complete else None), dominant


def _snapshot(net_by_symbol: dict[str, float], long_vol: float, short_vol: float,
              time, stress_move: float | None, resolutions: dict | None = None,
              broker: str | None = None, fx_state: dict | None = None) -> dict:
    by_sym = {s: v for s, v in net_by_symbol.items() if abs(v) > 1e-12}
    shock, peak_symbol = _portfolio_shock(by_sym, stress_move, resolutions,
                                          broker, when=time, fx_state=fx_state)
    return {
        "time": time,
        "long": long_vol,
        "short": short_vol,
        "by_sym": by_sym,
        "shock": shock,
        "peak_symbol": peak_symbol,
    }


def run(parsed: ParsedExport, stress_move: float | None = None,
        broker: str | None = None, kapitalbasis_usd: float | None = None,
        kapitalbasis_quelle: str | None = None) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "exposure", "flag": False, "temporal_risk_available": False}
    if stress_move is not None and (not math.isfinite(stress_move) or stress_move < 0):
        raise ValueError("Schockbewegung muss endlich und nicht negativ sein")
    symbols = sorted({normalize_symbol(t.symbol) for t in trades})
    resolutions = {sym: _resolve_symbol(sym, broker) for sym in symbols}

    # Klasse UNKNOWN und kein belegter Kontrakt: harter Fehler. Gibt es zwar
    # einen Spec-Eintrag, der aber wegen cross_broker=false nicht greift,
    # sagt die Meldung das explizit (statt nur "unbekannt").
    unknown = [sym for sym in symbols
               if symbol_class(sym) == "UNKNOWN" and resolutions[sym] is None]
    if unknown:
        # Spec vorhanden (mit Kontraktgroesse), gilt aber nicht fuer diesen
        # Broker -> gezielte Meldung; alles andere bleibt "unbekannt".
        scoped = [sym for sym in unknown
                  if (entry := spec_for(sym, ignore_broker=True)) is not None
                  and entry.get("contract_size") is not None]
        if scoped:
            broker_note = (f"Broker des Signals ({broker!r})" if broker
                           else "Broker des Signals UNBEKANNT (Kennzahlen-Seite "
                                "lieferte keine Server-Kennung — Signal-Seite "
                                "manuell ansehen)")
            raise ValueError(
                "Keine anwendbare Kontraktspec (cross_broker=false, "
                f"{broker_note} nicht freigegeben): " + ", ".join(scoped)
                + " — Broker in data/contract_specs.json freigeben "
                "(Eintrag 'brokers' ergänzen), dann erneut prüfen.")
        raise ValueError(
            "Unbekannte Instrumente ohne belegte Kontraktgroesse: " + ", ".join(unknown)
            + " — in data/contract_specs.json eintragen (Kontraktgroesse, "
            "Gewinnwaehrung, Quelle), dann erneut pruefen.")

    missing_contract = [sym for sym in symbols if resolutions[sym] is None]
    # Symbole mit Fremdwaehrungs-Quote: der Schock faellt dort zunaechst in
    # EUR/CAD/JPY an und wird pro Snapshot mit dem EZB-Kurs des Handelstags
    # nach USD umgerechnet (fx_rates). Ohne belegten Kurs bleibt es gesperrt.
    foreign_quote = [sym for sym in symbols
                     if resolutions[sym] is not None
                     and resolutions[sym]["quote"] != "USD"]
    fx_state: dict = {"complete": True, "missing": set()}
    warnings: list[str] = []
    if missing_contract:
        warnings.append("Keine belegte Brokerspezifikation fuer: " + ", ".join(missing_contract)
                        + " (Kontraktgroesse/Punktwert und Gewinnwaehrung fehlen). "
                        "Weder native Schockbetraege noch USD-Werte sind verfuegbar.")
    conversion_complete = not missing_contract
    events: list[tuple] = []
    for t in trades:
        events.append((t.open_time, 1, 1, t))
        events.append((t.close_time, 2, -1, t))
    # Gleiche Zeitauflosung liefert keine Reihenfolge innerhalb der Sekunde.
    # Kontobewegungen deshalb als einen Nettofluss pro Zeitstempel behandeln.
    flows_by_time: dict = defaultdict(list)
    for flow in parsed.balances:
        flows_by_time[flow.time].append(flow.amount)
    for time, amounts in flows_by_time.items():
        events.append((time, 0, 0, math.fsum(amounts)))
    # Kontobewegungen vor Opens, Opens vor Closes derselben Sekunde.
    # Gleiche Ereignisarten werden gemeinsam gebucht: weder die Reihenfolge
    # paralleler Eroeffnungen noch zeitgleicher Korb-Exits ist im CSV belegt.
    # Ein Close verbucht sein Netto erst beim Entfernen der Position; damit
    # kann spaeterer Gewinn die historische Belastung nicht verkleinern.
    first_open = min(t.open_time for t in trades)
    # Externe Kapitalbasis (Signalseite "Initial Deposit"): greift NUR, wenn
    # der Export keine Einzahlung vor dem ersten Trade enthaelt. Sie wird als
    # Buchung VOR dem ersten Open gefuehrt (kind 0 schlaegt kind 1), damit
    # Schock-in-Prozent gegen das reale Konto gerechnet wird.
    startkapital_quelle = "csv_einzahlungen"
    if kapitalbasis_usd is not None and kapitalbasis_usd > 0 \
            and not any(b.amount > 0 and b.time <= first_open for b in parsed.balances):
        events.append((first_open, 0, 0, float(kapitalbasis_usd)))
        startkapital_quelle = kapitalbasis_quelle or "extern"
    events.sort(key=lambda e: (e[0], e[1]))

    open_count = 0
    long_vol = short_vol = 0.0
    net_by_symbol: dict[str, float] = defaultdict(float)
    peak_count = 0
    count_snap: dict | None = None
    risk_snap: dict | None = None
    relative_snap: dict | None = None
    account = 0.0
    initial_capital = math.fsum(b.amount for b in parsed.balances if b.time <= first_open)
    if startkapital_quelle != "csv_einzahlungen":
        initial_capital += float(kapitalbasis_usd)
    capital_history_complete = initial_capital > 0
    temporal_risk_available = capital_history_complete and conversion_complete
    account_dipped_negative = False

    for (time, kind), grouped in groupby(events, key=lambda e: (e[0], e[1])):
        batch = list(grouped)
        if kind == 0:
            account += math.fsum(item for _, _, _, item in batch)
        else:
            delta = 1 if kind == 1 else -1
            trades_batch = [item for _, _, _, item in batch]
            open_count += delta * len(trades_batch)
            if delta == -1:
                account += math.fsum(t.net for t in trades_batch)
            long_vol += delta * math.fsum(t.volume for t in trades_batch if t.direction == "Buy")
            short_vol += delta * math.fsum(t.volume for t in trades_batch if t.direction == "Sell")
            symbol_deltas: dict[str, list[float]] = defaultdict(list)
            for t in trades_batch:
                symbol_deltas[normalize_symbol(t.symbol)].append(delta * t.volume * t.sign)
            for sym in sorted(symbol_deltas):
                net_by_symbol[sym] += math.fsum(symbol_deltas[sym])
        snap = _snapshot(net_by_symbol, long_vol, short_vol, time, stress_move,
                         resolutions, broker, fx_state)
        snap["account"] = account
        if snap["shock"] is not None and snap["shock"] > 0 and account <= 0:
            temporal_risk_available = False
            account_dipped_negative = True
        if open_count > 0 and account > 0 and snap["shock"] is not None:
            snap["shock_pct"] = snap["shock"] / account * 100
            if relative_snap is None or snap["shock_pct"] > relative_snap["shock_pct"]:
                relative_snap = snap
        if open_count > peak_count:
            peak_count = open_count
            count_snap = snap
        # A zero-risk hedge still has actual long/short positions. Do not let
        # an earlier deposit-only snapshot win the zero-shock tie.
        if open_count > 0 and snap["shock"] is not None and (
                risk_snap is None or snap["shock"] > risk_snap["shock"]):
            risk_snap = snap

    assert count_snap is not None
    # Kapitalbasis-Diagnose: konkreter Grund statt Sammel-Meldung. Ohne
    # belastbares Konto ist der Schock-in-Prozent (30-%-Regel) nicht berechenbar.
    if not capital_history_complete:
        warnings.append(
            "Kapitalbasis unbekannt: keine Einzahlungen vor dem ersten Trade im "
            f"Export (Startkapital {initial_capital:+.2f} — z. B. Historie gekuerzt "
            "oder Auszahlung vor Handelsbeginn). Schockanteil in Prozent und die "
            "30-%-Schranke sind nicht berechenbar; Crawling-Ergebnis bleibt Vorprüfung.")
    elif account_dipped_negative:
        warnings.append(
            "Kontostand war bei offenen Positionen <= 0 (z. B. Auszahlung mitten "
            "im Handel): kein belastbarer Bezugswert — Schockanteil in Prozent "
            "und die 30-%-Schranke sind nicht berechenbar.")
    # Fremdwaehrungs-Quotes: complete nur, wenn jeder Snapshot einen belegten
    # EZB-Kurs fand. Sonst Warnung mit konkretem Grund (Datei fehlt/Luecke).
    ezb = fx_rates.status()
    if foreign_quote and not fx_state["complete"]:
        conversion_complete = False
        if not ezb.get("geladen"):
            warnings.append(
                "Keine belegte historische Umrechnung nach USD fuer: "
                + ", ".join(sorted(fx_state["missing"]))
                + ". EZB-Referenzkurse nicht verfuegbar (keine Datei in "
                + ezb["ordner"] + " und Download nicht moeglich).")
        else:
            warnings.append(
                "Keine belegte historische Umrechnung nach USD fuer: "
                + ", ".join(sorted(fx_state["missing"]))
                + ". Kein EZB-Kurs im 10-Tage-Fenster zum Handelstag "
                "(Kalenderdeckung der Kursdatei: bis "
                + str(ezb.get("letzte_kursdatum")) + ").")
    if not conversion_complete:
        # Nachtraeglich herabgestuft (fehlender EZB-Kurs): das Flag ist an
        # conversion_complete gekoppelt und darf nicht am alten Wert haengen.
        temporal_risk_available = False
    # Ohne vollstaendige Umrechnung gibt es kein vergleichbares USD-Maximum.
    # Der Anzahl-Peak bleibt als reine Positionsdiagnostik vorhanden.
    if not conversion_complete or risk_snap is None:
        risk_snap = count_snap
    peak_net_by_symbol = risk_snap["by_sym"]
    shock = risk_snap["shock"] if conversion_complete else None
    peak_symbol = risk_snap["peak_symbol"]
    peak_long, peak_short = risk_snap["long"], risk_snap["short"]
    peak_time = risk_snap["time"]
    gross = peak_long + peak_short
    signed_peak_net = sum(peak_net_by_symbol.values())
    abs_lots = sum(abs(v) for v in peak_net_by_symbol.values())
    # Cross-Symbol-Lot-Netting als "0 Lots" waere irrefuehrend (Schock bleibt hoch).
    if peak_net_by_symbol and abs(signed_peak_net) + 1e-12 < abs_lots * 0.5:
        headline_net = max(peak_net_by_symbol.values(), key=abs)
    else:
        headline_net = signed_peak_net

    sym = peak_symbol or symbols[0]
    sclass = symbol_class(sym) if sym else "FX"
    headline_resolved = resolutions.get(sym) or _resolve_symbol(sym, broker)
    move = _stress_move(sym, stress_move, broker)
    unit = (headline_resolved["unit"] if headline_resolved
            else _UNIT_LABEL.get(sclass, "Preiseinheiten"))

    temporal_risk_available = temporal_risk_available and relative_snap is not None
    spec_sources = sorted({r["source"] for r in resolutions.values()
                           if r is not None and r["spec"]})
    # Provenienz der Umrechnung: welche EZB-Kurse flossen am Flag-Peak ein.
    fx_prov: dict = {}
    if foreign_quote and relative_snap and relative_snap.get("time"):
        for held_sym in relative_snap["by_sym"]:
            held_res = resolutions.get(held_sym)
            if held_res and held_res["quote"] != "USD":
                fx = fx_rates.usd_per(held_res["quote"], relative_snap["time"].date())
                if fx:
                    fx_prov[held_sym] = {"quote": held_res["quote"],
                                         "usd_pro_einheit": round(fx["rate"], 8),
                                         "ezb_kursdatum": fx["date"]}
    result: dict = {
        "test": "exposure",
        "startkapital": round(initial_capital, 2),
        "startkapital_quelle": startkapital_quelle,
        "peak_open_positions": peak_count,
        "peak_count_time": (count_snap["time"].isoformat(sep=" ")
                            if count_snap["time"] else None),
        "peak_count_net_by_symbol": {
            k: round(v, 2) for k, v in sorted(count_snap["by_sym"].items())},
        "peak_count_shock_usd": round(count_snap["shock"], 2) if count_snap["shock"] is not None else None,
        "peak_time": peak_time.isoformat(sep=" ") if peak_time and conversion_complete else None,
        "peak_long_lots": round(peak_long, 2) if conversion_complete else None,
        "peak_short_lots": round(peak_short, 2) if conversion_complete else None,
        "peak_net_lots": round(headline_net, 2) if conversion_complete else None,
        "peak_net_lots_signed_sum": round(signed_peak_net, 2) if conversion_complete else None,
        "peak_gross_lots": round(gross, 2) if conversion_complete else None,
        "peak_net_by_symbol": {k: round(v, 2) for k, v in sorted(peak_net_by_symbol.items())} if conversion_complete else {},
        "symbol_class": sclass,
        "usd_per_unit_per_lot": (_contract_factor(sym, broker)
                                 if _quote_currency(sym, broker) == "USD" else None),
        "stress_move": move,
        "stress_move_unit": unit,
        "shock_usd": round(shock, 2) if shock is not None else None,
        "account_at_shock_peak": round(risk_snap["account"], 2) if conversion_complete else None,
        "account_currency": "USD",
        "account_currency_basis": "USD-Konvention des Projekts; CSV enthaelt keine Kontowaehrung",
        "conversion_complete": conversion_complete,
        "contract_complete": not missing_contract,
        "missing_contract_symbols": missing_contract,
        "foreign_quote_symbols": foreign_quote,
        "fx_conversion": {"quelle": ("EZB-Euro-Referenzkurse (eurofxref-hist), "
                                     "Cross-Kurs ueber EUR/USD am Handelstag")
                          if fx_prov else None,
                          "letzte_kursdatum": ezb.get("letzte_kursdatum"),
                          "kurse_am_flag_peak": fx_prov},
        "spec_sources": spec_sources,
        "warnings": warnings,
        "per_symbol_scenarios": {
            symbol: {"quote_currency": (_quote_currency(symbol, broker)),
                     "contract_factor_in_quote": _contract_factor(symbol, broker),
                     "contract_source": (resolutions[symbol]["source"]
                                         if resolutions[symbol] else None),
                     "pip_size": fx_pip_size(symbol),
                     "stress_move": _stress_move(symbol, stress_move, broker),
                     "stress_pips": (_stress_move(symbol, stress_move, broker) / fx_pip_size(symbol)
                                     if fx_pip_size(symbol) else None),
                     "stress_quote_per_lot": (_stress_move(symbol, stress_move, broker) * _contract_factor(symbol, broker)
                                               if _contract_factor(symbol, broker) is not None else None),
                     "usd_conversion_available": (
                         _quote_currency(symbol, broker) == "USD"
                         or (_quote_currency(symbol, broker) is not None
                             and fx_rates.can_convert(_quote_currency(symbol, broker))))}
            for symbol in symbols},
        "capital_history_complete": capital_history_complete,
        "temporal_risk_available": temporal_risk_available,
        "shock_pct_max": round(relative_snap["shock_pct"], 4) if temporal_risk_available else None,
        "shock_pct_peak_time": relative_snap["time"].isoformat(sep=" ") if temporal_risk_available else None,
        "shock_pct_peak_account": round(relative_snap["account"], 2) if temporal_risk_available else None,
        "shock_pct_peak_usd": round(relative_snap["shock"], 2) if temporal_risk_available else None,
        "unknown_symbols": [],
        "shock_formula": (
            "USD-Schock nicht verfuegbar: Brokerspezifikation oder historische Waehrungsumrechnung fehlt"
            if shock is None else
            f"Summe je Symbol am Volumen-/Schock-Peak = {shock:,.2f} USD"
            if len(peak_net_by_symbol) > 1 else
            f"{abs(headline_net):.2f} Lots x {move:g} {unit} x "
            f"{headline_resolved['factor']:g} = {shock:,.2f} USD"
            if headline_resolved else
            f"Summe am Peak = {shock:,.2f} USD"),
        "flag": not temporal_risk_available or relative_snap["shock_pct"] > 30.0,
    }
    if sclass == "FX" and len(peak_net_by_symbol) <= 1:
        pip_factor = fx_pip_size(sym)
        pip_usd = shock_usd(headline_net, pip_factor * 10, sym, broker)  # 10 Pips
        result["fx_pips_10_usd"] = round(pip_usd, 2) if pip_usd is not None else None
    return result
