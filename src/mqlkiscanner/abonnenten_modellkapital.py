"""Pure, explicitly hypothetical capital models shared by all analysis paths.

No requests, storage, source mutation or solvency optimisation. Lots do not
identify capital without a sizing hypothesis; empirical reference ranges are
descriptive model uncertainty, never trading-risk limits or confidence bounds.
"""
from __future__ import annotations

import bisect
import math
import statistics
from collections import Counter, defaultdict
from .zahlen import ist_endliche_zahl as _number

VERSION = 1
FALLBACK_USD = 10_000.0
MIN_FIT_TRADES = 50
MIN_REFERENCE_PROFILES = 5


def _currency_claims(entry):
    return {str(value).strip().upper() for value in (
        entry.get("account_currency"), (entry.get("quellen_stats") or {}).get("account_currency"),
        entry.get("trade_money_currency")) if value is not None and str(value).strip()}


def _currency(entry):
    claims = _currency_claims(entry)
    return next(iter(claims)) if len(claims) == 1 else None


def _identity(entry):
    return (str(entry.get("quellen_uid") or entry.get("quelle") or ""), str(entry.get("id") or ""))


def _is_model(entry):
    model = entry.get("modellkapital")
    return (entry.get("kapitalbasis_typ") == "modell" or entry.get("kapitalbasis_modell") is True
            or entry.get("ist_modell") is True
            or isinstance(model, dict) and (model.get("basis_typ") == "modell" or model.get("modell") is True))


def _proven_capital(entry, parsed):
    if parsed is None or not parsed.trades or _currency(entry) != "USD" or _is_model(entry):
        return None
    first = min(trade.open_time for trade in parsed.trades)
    initial = [flow for flow in parsed.balances if flow.time <= first]
    costs = math.fsum(cost.amount for cost in getattr(parsed, "costs", []) if cost.time < first)
    if any(flow.amount > 0 for flow in initial):
        capital = math.fsum(flow.amount for flow in initial)
        if _number(capital) and capital > 0:
            return capital, "csv_einzahlungen_vor_handelsbeginn"
        return None
    stats = entry.get("quellen_stats") or {}
    initial_usd = stats.get("initial_deposit_usd")
    if (_number(initial_usd) and initial_usd > 0
            and str(stats.get("account_currency") or "").strip().upper() == "USD"):
        capital = initial_usd + math.fsum(flow.amount for flow in initial)
        if capital > 0:
            return capital, "native_initial_deposit_usd"
    dd = (entry.get("forensik") or {}).get("forensics", {}).get("drawdown", {})
    capital = dd.get("startkapital_raw")
    if (dd.get("startkapital_quelle") == "signalseite_initial_deposit"
            and _number(capital) and capital > 0):
        stored_costs = dd.get("kontokosten_vor_start_usd")
        if stored_costs is not None and (not _number(stored_costs)
                                         or not math.isclose(stored_costs, costs, abs_tol=1e-8)):
            return None
        capital -= costs  # forensic anchor is at first trade, model anchor precedes costs
        if capital > 0:
            return float(capital), "belegter_initial_deposit_aus_gepruefter_forensik"
    return None


def _dominant(parsed):
    if parsed is None or not parsed.trades:
        return None
    counts = Counter(trade.symbol for trade in parsed.trades)
    symbol = min(counts, key=lambda item: (-counts[item], item))
    trades = sorted((trade for trade in parsed.trades if trade.symbol == symbol), key=lambda trade: trade.open_time)
    volumes = [trade.volume for trade in trades]
    if not volumes or any(not _number(volume) or volume <= 0 for volume in volumes):
        return None
    return symbol, trades, statistics.median(volumes)


def _local_contract(entry, symbol):
    """Resolve local contract metadata only, never prices or account values."""
    from .forensics.exposure import _resolve_symbol
    from .symbols import normalize_symbol, spec_for
    stats = entry.get("quellen_stats") or {}
    brokers = [value.strip() for value in (stats.get("broker_server"), entry.get("broker_server"),
                                           entry.get("original_broker")) if isinstance(value, str) and value.strip()]
    if len({value.casefold() for value in brokers}) > 1:
        return None
    broker = brokers[0] if brokers else None
    try:
        # A broker-specific exception on an otherwise familiar symbol cannot
        # be silently resolved by the generic class while its broker is unknown.
        diagnostic = spec_for(symbol, ignore_broker=True)
        if (broker is None and isinstance(diagnostic, dict)
                and diagnostic.get("cross_broker") is False):
            return None
        resolved = _resolve_symbol(symbol, broker=broker)
        if not isinstance(resolved, dict):
            return None
        factor, quote = resolved.get("factor"), resolved.get("quote")
        if not _number(factor) or factor <= 0 or not isinstance(quote, str) or not quote:
            return None
        return normalize_symbol(symbol), {"contract_factor_in_quote": factor, "quote_currency": quote}
    except (ValueError, TypeError, KeyError):
        return None


def _contract_group(entry, parsed):
    if len(_currency_claims(entry)) > 1:
        return None  # conflicting trade money cannot enter or consume a USD lot calibration
    dominant = _dominant(parsed)
    if dominant is None:
        return None
    symbol, _, median_lot = dominant
    exposure = (entry.get("forensik") or {}).get("forensics", {}).get("exposure", {})
    scenarios = exposure.get("per_symbol_scenarios") or {}
    canonical, scenario = symbol, scenarios.get(symbol)
    if scenario is None and len(scenarios) == 1 and len({trade.symbol for trade in parsed.trades}) == 1:
        canonical, scenario = next(iter(scenarios.items()))
    if scenario is None:
        local = _local_contract(entry, symbol)
        if local is not None:
            canonical, scenario = local
    if not isinstance(scenario, dict):
        return None
    factor, quote = scenario.get("contract_factor_in_quote"), scenario.get("quote_currency")
    if not _number(factor) or factor <= 0 or not isinstance(quote, str) or not quote:
        return None
    return [canonical, quote, float(factor)], median_lot


def _quantile(values, percentile):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * percentile
    lower, upper = math.floor(pos), math.ceil(pos)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def _factor(estimate, actual):
    return max(estimate / actual, actual / estimate)


def kalibriere(referenzen):
    """Build a serialisable pool from (entry, original ParsedExport) pairs.

    Only USD-proven actual starting capital and comparable documented contract
    units enter the pool. Model profiles and duplicate source identities never
    become training references. At most one compact record per strategy.
    """
    groups, seen, seen_exports = {}, set(), set()
    rejected = Counter()
    for entry, parsed in referenzen:
        if not isinstance(entry, dict):
            rejected["ungueltige_referenz"] += 1
            continue
        proven, contract = _proven_capital(entry, parsed), _contract_group(entry, parsed)
        identity = _identity(entry)
        if not proven:
            rejected["kein_belegtes_usd_startkapital"] += 1
            continue
        if not contract:
            rejected["keine_vergleichbare_belegte_loteinheit"] += 1
            continue
        if not all(identity) or identity in seen:
            rejected["fehlende_oder_doppelte_identitaet"] += 1
            continue
        export_sha = entry.get("trades_sha256")
        if export_sha and export_sha in seen_exports:
            rejected["doppelter_export"] += 1
            continue
        seen.add(identity)
        if export_sha:
            seen_exports.add(export_sha)
        key, median_lot = contract
        group = groups.setdefault(tuple(key), {"kontraktgruppe": key, "referenzen": []})
        group["referenzen"].append({"quellen_uid": identity[0], "id": identity[1],
                                    "quelle": entry.get("quelle"), "signal_ref": entry.get("signal_ref"),
                                    "kapital_usd": proven[0], "median_lot": median_lot,
                                    "usd_je_lot": proven[0] / median_lot,
                                    "trades_sha256": entry.get("trades_sha256")})
    for group in groups.values():
        values = [row["usd_je_lot"] for row in group["referenzen"]]
        group.update(n=len(values), usd_je_lot_median=statistics.median(values),
                     usd_je_lot_p10=_quantile(values, .1), usd_je_lot_p90=_quantile(values, .9))
        if len(values) >= MIN_REFERENCE_PROFILES:
            errors = [_factor(statistics.median(values[:index] + values[index + 1:]) / value, 1)
                      for index, value in enumerate(values)]
            group["leave_one_out"] = {"n": len(errors), "median_faktorfehler": statistics.median(errors),
                                       "p80_faktorfehler": _quantile(errors, .8), "max_faktorfehler": max(errors)}
    return {"version": VERSION, "basis": "ausschliesslich_belegte_usd_startkapitalien",
            "annahme": "Mediane Lots vergleichbarer Kontrakte skalieren grob mit dem Startkapital; unterschiedliche Risikostile bleiben ungemessen.",
            "referenzen_n": len(seen), "abgelehnt": dict(rejected),
            "gruppen": list(groups.values()),
            "grenze": "Deskriptive Stichprobe, kein validierter universeller Kapital-/Risikozusammenhang und kein Konfidenzintervall."}


def _events(parsed):
    events = defaultdict(list)
    for trade in parsed.trades:
        events[trade.close_time].append(trade.net)
    for cost in getattr(parsed, "costs", []):
        events[cost.time].append(cost.amount)
    times = sorted(events)
    cumulative, total = [], 0.0
    for timestamp in times:
        total = math.fsum((total, *events[timestamp]))
        cumulative.append(total)
    return times, cumulative


def _ols(points):
    if len(points) < 3:
        return None
    mean_x = statistics.fmean(point[0] for point in points)
    mean_y = statistics.fmean(point[1] for point in points)
    xx = math.fsum((x - mean_x) ** 2 for x, _ in points)
    yy = math.fsum((y - mean_y) ** 2 for _, y in points)
    if xx <= 0 or yy <= 1e-20:
        return None
    beta = math.fsum((x - mean_x) * (y - mean_y) for x, y in points) / xx
    alpha = mean_y - beta * mean_x
    estimate = alpha / beta if beta != 0 else None
    return {"alpha": alpha, "beta": beta, "r2": min(1.0, max(0.0, beta * beta * xx / yy)),
            "kapital": estimate if _number(estimate) else None, "n": len(points)}


def _lot_pnl_fit(entry, parsed):
    dominant = _dominant(parsed)
    if dominant is None or _currency(entry) != "USD":
        return None, {"status": "nicht_identifizierbar", "grund": "Keine USD-belegte PnL-/Lotreihe"}
    symbol, trades, _ = dominant
    times, cumulative = _events(parsed)
    points = []
    for trade in trades:
        index = bisect.bisect_left(times, trade.open_time) - 1
        points.append((cumulative[index] if index >= 0 else 0.0, trade.volume))
    fit = _ols(points)
    diagnostic = {"status": "nicht_identifizierbar", "symbol": symbol, "n": len(points), "fit": fit,
                  "hypothese": "Lot = alpha + beta * geschlossenes Netto vor Open; K0 = alpha/beta. Floating und Risikowechsel sind nicht identifiziert."}
    if fit is None:
        diagnostic["grund"] = "Konstante Lots oder zu wenig PnL-Variation; kein identifizierbarer Kapitalmassstab"
        return None, diagnostic
    if fit["beta"] <= 0 or fit["kapital"] is None or fit["kapital"] <= 0:
        diagnostic["grund"] = "Nichtpositive Steigung oder nichtpositiver Kapitalfit; nicht angepasst oder auf Mindestkapital geklemmt"
        return None, diagnostic
    first = min(trade.open_time for trade in parsed.trades)
    flows = [flow for flow in parsed.balances if flow.time > first]
    if flows:
        diagnostic["grund"] = "Explizite spaetere Kapitalfluesse widersprechen einer proportionalen No-Flow-Sizing-Identifikation"
        return None, diagnostic
    halves = [_ols(points[:len(points) // 2]), _ols(points[len(points) // 2:])]
    diagnostic["zeitliche_halbfenster"] = halves
    stable = all(half and half["beta"] > 0 and half["kapital"] and half["kapital"] > 0
                 and _factor(half["kapital"], fit["kapital"]) <= 2 for half in halves)
    if (len(points) < MIN_FIT_TRADES or len({round(trade.volume, 10) for trade in trades}) < 3
            or fit["r2"] < .95 or not stable):
        diagnostic["grund"] = "Sizing-Hypothese nicht stabil: mindestens 50 Trades/3 Lotstufen, R2>=0.95 und positive Halbfensterfits innerhalb Faktor 2 erforderlich"
        return None, diagnostic
    diagnostic.update(status="modell_fit", grund="Strenge technische Fitpruefung bestanden; keine belegte Kontogroesse")
    return fit["kapital"], diagnostic


def _dd_anchor(entry, parsed):
    anchor = entry.get("modellkapital_closing_dd_anker")
    if not isinstance(anchor, dict):
        return None, {"status": "kein_unabhaengiger_anker", "grund": "Eigene bereits kapitalbasierte DD-Prozente sind zirkulaer und werden nicht verwendet"}
    first = min(trade.open_time for trade in parsed.trades)
    if any(flow.time > first for flow in parsed.balances):
        return None, {"status": "nicht_identifizierbar",
                      "grund": "Explizite spaetere Kapitalfluesse widersprechen der No-Flow-Definition des Closing-DD-Ankers"}
    if (_currency(entry) != "USD" or anchor.get("unabhaengig") is not True
            or anchor.get("scope_bestaetigt") is not True or anchor.get("selbst_berechnet") is not False
            or anchor.get("definition") != "max_rel_closing_netto_ohne_flows"
            or anchor.get("trades_sha256") != entry.get("trades_sha256")
            or not isinstance(anchor.get("quelle"), str) or not anchor["quelle"].strip()
            or anchor.get("zeit_von") != min(trade.open_time for trade in parsed.trades).isoformat()
            or anchor.get("zeit_bis") != max(trade.close_time for trade in parsed.trades).isoformat()):
        return None, {"status": "unbestaetigter_anker", "grund": "Unabhaengigkeit, gleiche Definition und identisches Exportfenster sind nicht belegt"}
    pct = anchor.get("dd_pct_max_rel")
    if not _number(pct) or pct <= 0:
        return None, {"status": "nicht_identifizierbar", "grund": "Keine positive endliche unabhaengige Closing-DD-Prozentzahl"}
    _, cumulative = _events(parsed)
    peak, candidates = 0.0, []
    for value in cumulative:
        peak = max(peak, value)
        if peak > value:
            candidates.append((peak - value) / (pct / 100) - peak)
    estimate = max(candidates) if candidates else None
    diagnostic = {"status": "modell_anker", "kapital": estimate, "quelle": anchor["quelle"],
                  "formel": "K0=max_t((PeakPnL-PnL_t)/(DDpct/100)-PeakPnL)",
                  "grund": "Unabhaengiger prozentualer Closing-DD unter der No-Flow-Annahme invertiert; kein Equity-DD-Beweis"}
    if estimate is None or not _number(estimate) or estimate <= 0:
        diagnostic.update(status="nicht_identifizierbar", grund="Nichtpositives oder fehlendes Inversionsergebnis bleibt Diagnose, keine Solvenzanpassung")
        return None, diagnostic
    return estimate, diagnostic


def _output(entry, parsed, capital, method, *, proven=False, diagnostics=None, references=None):
    value = float(capital)
    result = {"version": VERSION, "kapital": value, "waehrung": "USD", "quellwaehrung": _currency(entry),
              "basis_typ": "belegt" if proven else "modell", "modell": not proven,
              "herkunft": method, "methode": method,
              "annahmen": [] if proven else ["Hypothetisches USD-Modellkapital, kein Nachweis der realen Kontogroesse",
                                             "Keine Ein-/Auszahlungen innerhalb des modellierten Tradefensters",
                                             "H1-Raster erfasst keine vollstaendigen Intrabar-Tiefs"],
              "belege": {"signal_ref": entry.get("signal_ref"), "trades_sha256": entry.get("trades_sha256")},
              "fitdiagnostik": diagnostics or {}, "kalibrierung": references,
              "kalibrierung_ref_n": (references or {}).get("n", 0),
              "waehrungsumrechnung": False,
              "native_pnl_als_usd_belegt": _currency(entry) == "USD"}
    if not proven:
        result["unsicherheit"] = "Modellannahme; Lot-/Kapitalbeziehungen sind zwischen Strategien stark verschieden. Kein statistisches Konfidenzintervall."
        if parsed is not None and parsed.trades and _currency(entry) == "USD":
            _, cumulative = _events(parsed)
            result["modell_min_closing_balance"] = value + min([0.0, *cumulative])
            result["solvenz_anpassung"] = False
            if result["modell_min_closing_balance"] <= 0:
                result["modell_warnung"] = "Das unveraenderte Modellkapital fuehrt im Closing-Pfad zu Null/negativer Balance; kein Kapital zum Schoenrechnen erhoeht."
    return result


def schaetze_kapital(entry, parsed, calibration=None):
    """Return proven USD capital or a labelled model in deterministic order."""
    if not isinstance(entry, dict):
        entry = {}
    if parsed is None or not parsed.trades:
        return _output(entry, parsed, FALLBACK_USD, "fallback_10000", diagnostics={"grund": "Kein auswertbarer Originalexport"})
    proven = _proven_capital(entry, parsed)
    if proven:
        return _output(entry, parsed, proven[0], proven[1], proven=True)
    diagnostics = {}
    capital, diagnostics["closing_dd_anker"] = _dd_anchor(entry, parsed)
    if capital:
        return _output(entry, parsed, capital, "komplex_closing_dd_anker", diagnostics=diagnostics)
    capital, diagnostics["lot_pnl_regression"] = _lot_pnl_fit(entry, parsed)
    if capital:
        return _output(entry, parsed, capital, "komplex_lot_pnl_regression", diagnostics=diagnostics)
    contract = _contract_group(entry, parsed)
    if isinstance(calibration, dict) and calibration.get("basis") == "ausschliesslich_belegte_usd_startkapitalien" and contract:
        key, median_lot = contract
        groups = calibration.get("gruppen")
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                continue
            if group.get("kontraktgruppe") != key:
                continue
            raw_rows = group.get("referenzen")
            if not isinstance(raw_rows, list):
                continue
            rows = [row for row in raw_rows if isinstance(row, dict)
                    and (row.get("quellen_uid"), row.get("id")) != _identity(entry)
                    and not (entry.get("trades_sha256")
                             and row.get("trades_sha256") == entry["trades_sha256"])
                    and _number(row.get("usd_je_lot")) and row["usd_je_lot"] > 0]
            if len(rows) < MIN_REFERENCE_PROFILES:
                continue
            ratios = [row["usd_je_lot"] for row in rows]
            capital = median_lot * statistics.median(ratios)
            reference = {"n": len(rows), "kontraktgruppe": key, "median_lot": median_lot,
                         "usd_je_lot_median": statistics.median(ratios),
                         "empirischer_modellbereich_p10_p90": [median_lot * _quantile(ratios, .1), median_lot * _quantile(ratios, .9)],
                         "validierung": group.get("leave_one_out"),
                         "hinweis": "Reine beobachtete Referenzspanne; unterschiedliche Risikostile und Quellen bleiben Modellunsicherheit."}
            return _output(entry, parsed, capital, "grobe_lot_kalibrierung", diagnostics=diagnostics, references=reference)
    diagnostics["lotschaetzung"] = "Keine ausreichenden vergleichbaren belegten USD-Referenzen; keine Risikoprozentregel erfunden"
    return _output(entry, parsed, FALLBACK_USD, "fallback_10000", diagnostics=diagnostics)
