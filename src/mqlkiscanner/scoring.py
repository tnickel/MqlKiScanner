# -*- coding: utf-8 -*-
"""Risiko-Score (1-10, hoch = riskant) — 7 Dimensionen, gewichtet.

Spec: doc/03_forensik-tests.md Abschnitt "Scoring-Vorschlag". Kalibrierung
aus der Analyse-Reihe (doc/01): Gold Spike 4,0 / Gold Reaper 4,4 / KiraCat 4,7 /
MSC 5,6 / FXtrading 5,7 / World PEACE 8,0.

Regeln (AGENTS.md):
- Der Score wird NUR nach bestandener Forensik-Batterie berechnet
  (gate: forensics_complete).
- Dimensionen werden aus Engine-Metriken abgeleitet, wo das geht; Plattform-
  Fakten (Broker, Transparenz, Plattform-EQ-DD) werden als `platform`-Dict
  uebergeben und NICHT vom LLM erfunden.
- Drawdown-Schranke: EQ-DD > 30 % = harte Ablehnung unabhaengig vom Score.
"""
from __future__ import annotations

DEFAULT_WEIGHTS: dict[str, float] = {
    "drawdown": 0.25,       # Drawdown-Historie (real + Plattform-EQ)
    "structure": 0.25,      # Strukturrisiko: SL? Grid? Martingale?
    "margin": 0.15,         # Margin-/Exposure-Disziplin (Schockszenario)
    "copy": 0.15,           # Copy-/Slippage-Risiko
    "track": 0.10,          # Track-Record-Laenge
    "transparency": 0.05,   # Transparenz (Reviews, Anbieterkommunikation)
    "broker": 0.05,         # Broker-Umgebung (Regulierung)
}


def _clamp(x: float, lo: float = 1.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    """Stueckweise lineare Abbildung x -> Risiko-Dimension (1-10)."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


DD_MAP = [(0, 1.0), (5, 3.0), (10, 4.5), (15, 5.5), (20, 6.5), (25, 7.5), (30, 9.0), (50, 10.0)]
SHOCK_MAP = [(0, 1.0), (5, 2.0), (10, 3.5), (30, 6.0), (50, 8.0), (100, 10.0)]  # Schock in % des Kontos
AVG_WIN_MAP = [(2, 8.0), (4, 6.5), (8, 5.0), (15, 5.0), (40, 4.0), (100, 3.0)]  # Slippage-empfindlich
WEEKS_MAP = [(8, 9.0), (26, 7.0), (40, 5.5), (52, 4.5), (78, 3.0), (104, 2.5), (156, 2.0)]


def dimension_inputs(report: dict, platform: dict | None = None) -> dict[str, float]:
    """7 Dimensionen (1-10, hoch = riskant) aus Engine-Report + Plattform-Fakten.

    platform (alle optional, aus der Signalseite, NICHT aus dem LLM):
      eq_dd_pct, weeks, broker_risk (1-10), transparency_risk (1-10),
      correlated_pairs (>1 = Grid ueber korrelierte Paare)
    """
    platform = platform or {}
    f = report.get("forensics", {})
    s = report.get("stats", {})

    # 1) Drawdown: realer Trading-DD vs. Plattform-EQ-DD — der schlimmere zaehlt.
    #    Vorbehalt (eq_dd_caveat): Plattform-EQ-DD aus der Fruehphase auf einem
    #    Minikonto (Fall KiraCat, doc/01-Fusznote) — dann nur realer Trading-DD.
    real_dd = f.get("drawdown", {}).get("trading_dd", {}).get("dd_pct", 0.0)
    eq_dd = float(platform.get("eq_dd_pct") or 0.0)
    dd_reference = real_dd if platform.get("eq_dd_caveat") else max(real_dd, eq_dd)
    dd_dim = _interp(dd_reference, DD_MAP)

    # 2) Struktur: Stop-Nachweis, Martingale (Nachfolger + Korb-Leiter), Grid
    stops = f.get("stops", {})
    mart = f.get("martingale", {})
    bask = f.get("baskets", {})
    stop_proven = stops.get("evidence_level") == 1 and stops.get("positions_with_sl_tp_pct", 0) >= 99.0
    struct = 3.0
    struct -= 1.0 if stop_proven else 0.0
    struct += 3.0 if mart.get("flag") else 0.0
    struct += 2.0 if not stop_proven and stops.get("clustered") is False else 0.0
    struct += 1.5 if (bask.get("grid_indicator_pct") or 0) > 30 else 0.0
    struct += 1.0 if (platform.get("correlated_pairs") or 1) >= 5 else 0.0
    struct_dim = _clamp(struct)

    # 3) Margin: Schockszenario in % des rekonstruierten Kontos
    expo = f.get("exposure", {})
    ddinfo = f.get("drawdown", {})
    account = max(ddinfo.get("trading_dd", {}).get("peak_balance") or 0.0, 100.0)
    shock = abs(expo.get("shock_usd") or 0.0)
    margin_dim = _interp(shock / account * 100, SHOCK_MAP)

    # 4) Copy/Slippage: kleine Durchschnittsgewinne + Grid-Exits kopieren schlecht
    avg_win = s.get("avg_win") or 0.0
    copy_dim = _interp(avg_win, AVG_WIN_MAP)
    if (bask.get("trades_in_baskets_pct") or 0) > 40:
        copy_dim = _clamp(copy_dim + 1.0)

    # 5) Track-Record
    weeks = float(platform.get("weeks") or s.get("span_weeks") or 0)
    track_dim = _interp(weeks, WEEKS_MAP)

    # 6+7) Transparenz und Broker: Plattform-Fakten, Default 5 (offshore-ueblich)
    transp_dim = _clamp(float(platform.get("transparency_risk", 5.0)))
    broker_dim = _clamp(float(platform.get("broker_risk", 5.0)))

    return {
        "drawdown": round(dd_dim, 2),
        "structure": round(struct_dim, 2),
        "margin": round(margin_dim, 2),
        "copy": round(copy_dim, 2),
        "track": round(track_dim, 2),
        "transparency": round(transp_dim, 2),
        "broker": round(broker_dim, 2),
    }


def score(dims: dict[str, float], weights: dict[str, float] | None = None) -> float:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)
    total = sum(w[k] * dims[k] for k in w)
    hard_block = dims.get("_schranke_verletzt", False)
    return round(_clamp(total), 1)


def evaluate(report: dict, platform: dict | None = None,
             weights: dict[str, float] | None = None) -> dict:
    """Score + Gate. Schranke: EQ-DD > 30 % (AGENTS.md: Risiko vor Ertrag)."""
    platform = platform or {}
    dims = dimension_inputs(report, platform)
    eq_dd = float(platform.get("eq_dd_pct") or 0.0)
    barrier = eq_dd > 30.0
    return {
        "dimensions": dims,
        "weights": {**DEFAULT_WEIGHTS, **(weights or {})},
        "score": score(dims, weights),
        "schranke_eq_dd_verletzt": barrier,
        "forensics_complete": _forensics_complete(report),
        "urteil_gueltig": _forensics_complete(report) and not barrier,
    }


def _forensics_complete(report: dict) -> bool:
    f = report.get("forensics", {})
    return all(k in f and f[k] for k in ("martingale", "exposure", "stops", "drawdown"))


# --------------------------------------------------------------- Kalibrierung
# Plattform-Fakten aus doc/01_analysen-verlauf.md (Tiefanalysen 1-6)
CALIBRATION_CASES: dict[str, dict] = {
    "Gold Spike": dict(target=4.0, eq_dd_pct=3.8, weeks=44,
                       broker_risk=5.0, transparency_risk=6.0),
    "Gold Reaper": dict(target=4.4, eq_dd_pct=7.18, weeks=97,
                        broker_risk=5.0, transparency_risk=3.0),
    "KiraCat": dict(target=4.7, eq_dd_pct=20.55, weeks=43, eq_dd_caveat=True,
                    broker_risk=2.0, transparency_risk=5.0),
    "MSC Gold": dict(target=5.6, eq_dd_pct=33.7, weeks=123,
                     broker_risk=6.0, transparency_risk=5.0),
    "FXtrading": dict(target=5.7, eq_dd_pct=6.6, weeks=67,
                      broker_risk=5.0, transparency_risk=6.0),
    "World PEACE": dict(target=8.0, eq_dd_pct=30.6, weeks=78,
                        broker_risk=3.0, transparency_risk=3.0, correlated_pairs=10),
}


def calibrate(reports: dict[str, dict]) -> list[dict]:
    """Rechne die 6 Kalibrierfaelle der Reihe durch und liefere Soll/Ist."""
    rows = []
    for name, case in CALIBRATION_CASES.items():
        rep = reports.get(name)
        if rep is None:
            continue
        ev = evaluate(rep, platform=case)
        ist = ev["score"]
        rows.append({"signal": name, "soll": case["target"], "ist": ist,
                     "delta": round(ist - case["target"], 1),
                     "schranke": ev["schranke_eq_dd_verletzt"],
                     "dims": ev["dimensions"]})
    return rows
