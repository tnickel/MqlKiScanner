# -*- coding: utf-8 -*-
"""Lauf-Verifikation der Fixes B1/B2/B3 gegen den LIVE-PelicanMonitor (:8090).

ERGEBNIS (30.09. abends, Monitor neu gestartet mit cd9612f):
  Lemonal 🔴 (46,65 % Schranke) · AccurateCopier 🔴 (241,3 %) ·
  Lexo 🟡 (1,86 %/M) · SafeGold 🟡 (11,55 %/M, Score) ·
  PentagonForex 🟡 (1,12 %/M) · Mr_Profit_FX 🟡 (3,33 %/M) —
  alle sechs mit impliziter Kapitalbasis statt 10k-Annahme.

Isoliert: schreibt NICHTS in die Produktiv-DB (Trades in Tempdatei), ruft
KEIN LLM, bewertet nichts neu in der DB — reine Gegenprobe der Ampel-Logik
auf dem Weg, den ein echter Scan nimmt (ingest-Metrics live, Forensik auf
den echten Trades, scoring/ampel mit den neuen Regeln).

Erwartung (aus dem Intensiv-Review):
  Lemonal (2063644)      Monitor-TDD 46,65 %  -> Schranke -> 🔴
  AccurateCopier (2084818) Monitor-TDD 241,3 % -> Schranke -> 🔴
  Mr_Profit_FX (2052727)  Monitor-TDD 22,73 %  -> unter Schranke -> 🟡 (Ertrag)
  SafeGold (2048285)     Ertrag forensik ~0,5 %/M -> 🟡
  PentagonForex (2014076) Ertrag forensik ~2,7 %/M -> 🟡
  Lexo (2000028)         Ertrag forensik ~3,5 %/M -> 🟡
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from mqlkiscanner import config, db, pipeline, quellen  # noqa: E402
from mqlkiscanner.engine import analyze as analyze_export  # noqa: E402
from mqlkiscanner.ingest import metrics_zu_stats  # noqa: E402
from mqlkiscanner import scoring  # noqa: E402

SIGNALS = [
    (2000028, "Lexo"),
    (2063644, "Lemonal"),
    (2084818, "AccurateCopier"),
    (2048285, "SafeGold"),
    (2014076, "PentagonForex"),
    (2052727, "Mr_Profit_FX"),
]


def main() -> int:
    quelle = next(q for q in db.list_quellen(nur_aktiv=True) if q.get("kuerzel") == "pelik")
    cli = quellen.client_fuer_quelle(quelle)
    settings = config.load_settings()
    fehler = 0
    for sid, name in SIGNALS:
        antwort = cli.metrics(sid, "pelican")
        stats = metrics_zu_stats(antwort)
        roh = cli.trades_csv(sid, "pelican")
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        tmp.write(roh)
        tmp.close()
        kapitalbasis = stats.get("initial_deposit_usd")
        quelle_kb = "signalseite_initial_deposit"
        if kapitalbasis is None:
            implizit = pipeline._implizite_kapitalbasis(
                stats.get("balance_usd"), tmp.name)
            if implizit is not None:
                kapitalbasis, quelle_kb = implizit, pipeline.KAPITALBASIS_QUELLE_IMPLIZIT
        if kapitalbasis is None:
            virtuell = pipeline._virtuelle_kapitalbasis(
                stats.get("kapitalbasis_virtual_usd"))
            if virtuell is not None:
                kapitalbasis, quelle_kb = virtuell, pipeline.KAPITALBASIS_QUELLE_VIRTUELL
        report = analyze_export(tmp.name, broker=stats.get("broker_server"),
                                kapitalbasis_usd=kapitalbasis,
                                kapitalbasis_quelle=quelle_kb, kursanbieter=None)
        fx = report["forensics"]
        dd = fx["drawdown"]
        st = report["stats"]
        monitor = stats.get("monitor_trade_eq_dd_pct")
        platform = {"eq_dd_pct": stats.get("dd_equity_pct") or 0,
                    "bal_dd_pct": stats.get("dd_balance_pct") or 0,
                    "monitor_trade_eq_dd_pct": monitor or 0,
                    "weeks": None, "broker_risk": 5.0, "transparency_risk": 5.0}
        ev = scoring.evaluate(report, platform=platform,
                              schranke_eq_dd_pct=settings.get("schranke_eq_dd_pct", 30.0))
        span = float(st.get("span_weeks") or 0)
        netto = dd.get("net_total")
        start = dd.get("startkapital")
        ertrag_f = (round(100.0 * netto / start / (span * 7.0 / 30.44), 2)
                    if netto is not None and start and span > 0 else None)
        res = pipeline.ScanResult(
            id=sid, name=name, quelle="pelik", platform="pelican",
            dd_equity_pct=stats.get("dd_equity_pct"),
            trading_dd_pct=(fx["drawdown"]["trading_dd"].get("dd_pct_max_rel")
                            or fx["drawdown"]["trading_dd"].get("dd_pct")),
            ertrag_monat_pct=stats.get("monthly_growth_pct"),
            ertrag_monat_pct_forensik=ertrag_f,
            martingale_flag=fx["martingale"].get("flag"),
            stop_evidence=fx["stops"].get("stop_evidence"),
            monitor_trade_eq_dd_pct=monitor,
            kapitalbasis_verwendet_quelle=dd.get("startkapital_quelle") or "",
            kapitalbasis_verwendet_usd=start,
            score=ev["score"],
            schranke_verletzt=bool(ev["schranke_eq_dd_verletzt"]),
            forensik_vorhanden=True)
        pipeline.refresh_report_verdict(res, settings)
        print(f"{name:<16} #{sid} | Schranke-Max {ev['schranke_dd_pct']:>6.2f} % "
              f"(verletzt: {bool(ev['schranke_eq_dd_verletzt'])!s:<5}) | "
              f"Ertrag F {ertrag_f if ertrag_f is not None else '—':>6} %/M "
              f"(Plattform {stats.get('monthly_growth_pct')}) | "
              f"Basis {start} ({dd.get('startkapital_quelle')}) | "
              f"Ampel NEU: {res.ampel}")
        Path(tmp.name).unlink(missing_ok=True)
    print("\nBewertet wurde isoliert im Speicher — keine DB-Schreibzugriffe, kein LLM.")
    return fehler


if __name__ == "__main__":
    sys.exit(main())
