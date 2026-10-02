"""Stop facts survive the real scan, persistence, archive and prompt path."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.llm import prompt_fill


def history(tmp_path, orderbook):
    header = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment"
              if orderbook else
              "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit")
    rows = [header]
    balance = [""] * (13 if orderbook else 11)
    balance[:2] = ["2026.01.01 00:00:00", "Balance"]
    balance[11 if orderbook else 10] = "10000"
    rows.append(";".join(balance))
    for day in range(4):
        close = datetime(2026, 1, 2, 12) + timedelta(days=day)
        for leg in range(3):
            entry = 2010 + day*7 + leg*3
            row = [(close-timedelta(hours=2, minutes=leg)).strftime("%Y.%m.%d %H:%M:%S"),
                   "Buy", "0.01", "XAUUSD", str(entry)]
            row += [str(entry-2), ""] if orderbook else ["0.01"]
            row += [(close+timedelta(seconds=leg)).strftime("%Y.%m.%d %H:%M:%S"),
                    "2000", "-0.10", "0", str(2000-entry)]
            if orderbook:
                row += ["[sl]"]
            rows.append(";".join(row))
    target = tmp_path / "9000191.csv"
    target.write_text("\n".join(rows)+"\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("orderbook", [False, True])
def test_stop_facts_are_persisted_and_bound_to_report_basis(tmp_path, monkeypatch, orderbook):
    path = history(tmp_path, orderbook)
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        lambda *_: {"dd_equity_pct": 4, "weeks": 52, "monthly_growth_pct": 7})
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **k: (str(path), True))
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False})
    settings = {"equity_rekonstruktion": False, "llm_stufe1": False, "llm_stufe2": False}
    scanned = pipeline.ScanPipeline(settings)._analyze_candidate_once(
        None, {"id": 9000191, "name": "Stop contract", "platform": "MT4" if orderbook else "MT5"},
        lambda _: None)
    assert not scanned.fehler and scanned.forensik_vorhanden
    assert scanned.stop_evidence == ("direct" if orderbook else "none")
    assert scanned.stop_befund["schutzsignatur"]["qualifizierte_verlustgruppen"] == 4
    assert scanned.stop_befund["schutzsignatur"]["status"] == "plausibel"
    if orderbook:
        assert scanned.stop_befund["positions_with_sl"] == 12
        assert scanned.stop_befund["exits_sl"] == 12
    stored = db.list_catalog()[0]["forensik"]
    assert stored["stop_befund"] == scanned.stop_befund
    reloaded = pipeline.results_from_db(settings)[0]
    archive = pipeline.ScanPipeline.save_run([scanned], {})
    restored = pipeline.ScanResult(**json.loads(Path(archive).read_text(encoding="utf-8"))["ergebnisse"][0])
    basis = pipeline.report_basis_for(scanned, settings)
    for result in (reloaded, restored):
        assert result.stop_befund == scanned.stop_befund
        assert result.stop_evidence == scanned.stop_evidence
        assert result.score == scanned.score and result.ampel == scanned.ampel
        assert pipeline.report_basis_for(result, settings) == basis
        facts = pipeline._forensik_json(result)
        assert json.loads(facts)["stop_befund"] == scanned.stop_befund
        assert facts in prompt_fill.build_risk_prompt(result, "criteria")
    # Changing the new evidence must invalidate a report based on old facts.
    reloaded.stop_befund = dict(reloaded.stop_befund, schutzsignatur={"status": "hinweis"})
    assert pipeline.report_basis_for(reloaded, settings) != basis


def test_legacy_stop_payload_does_not_invent_behavioural_evidence():
    old = pipeline.ScanResult(id=9000192, stop_evidence="none")
    assert "stop_befund" not in json.loads(pipeline._forensik_json(old))
    assert old.stop_befund is None
