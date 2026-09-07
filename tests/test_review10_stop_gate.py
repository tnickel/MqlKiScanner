"""Stop evidence must survive the real CSV, scoring and persistence paths."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION


def write_history(tmp_path, evidence):
    orderbook = evidence in {"direct", "partial", "none_orderbook"}
    header = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment"
              if orderbook else
              "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit")
    rows = [header]
    width = 13 if orderbook else 11
    balance = [""] * width
    balance[0:2] = ["2023.12.31 10:00:00", "Balance"]
    balance[11 if orderbook else 10] = "10000"
    rows.append(";".join(balance))
    # Positive returns, long history, constant lots and small exposure: a low
    # score is legitimate even when the export contains no stop evidence.
    profits = [1000] * 26 + ([-20] * 8 if evidence == "cluster" else [])
    for index, profit in enumerate(profits):
        opened = datetime(2024, 1, 1) + timedelta(days=30 * index)
        closed = opened + timedelta(hours=1)
        row = [opened.strftime("%Y.%m.%d %H:%M:%S"), "Buy", "0.1", "XAUUSD", "2000"]
        if orderbook:
            row += ["1998" if evidence == "direct" or (evidence == "partial" and index == 0)
                    else "", ""]
        else:
            row += ["0.1"]
        row += [closed.strftime("%Y.%m.%d %H:%M:%S"), str(2000 + profit / 10),
                "0", "0", str(profit)]
        if orderbook:
            row += [""]
        rows.append(";".join(row))
    path = tmp_path / "9000123_history.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("evidence,expected", [
    ("none_orderbook", "🟡"), ("none", "🟡"), ("partial", "🟡"),
    ("direct", "🟢"), ("cluster", "🟢"),
])
def test_real_history_stop_gate_survives_database_archive_and_llm_payload(
        tmp_path, monkeypatch, evidence, expected):
    path = write_history(tmp_path, evidence)
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", Mock(return_value={
        "dd_equity_pct": 1, "monthly_growth_pct": 6, "weeks": 110,
    }))
    download = Mock(return_value=(str(path), False))
    monkeypatch.setattr(pipeline.exporter, "export_positions", download)
    result = pipeline.ScanPipeline().analyze_candidate(
        None, {"id": 9000123, "name": "Stop regression", "platform": "MT4"}, lambda _: None)
    assert not result.fehler
    assert result.forensik_vorhanden and result.score < 5
    assert not result.martingale_flag and not result.schranke_verletzt
    assert result.ampel == expected
    assert result.stop_evidence == ("none" if evidence == "none_orderbook" else evidence)
    download.assert_called_once()  # Missing stop evidence is not a request failure.
    if expected == "🟡":
        assert "Stop-Nachweis" in result.urteil
    loaded = pipeline.results_from_db()[0]
    archive = pipeline.ScanPipeline.save_run([result], {})
    restored = pipeline.ScanResult(**json.loads(Path(archive).read_text(encoding="utf-8"))["ergebnisse"][0])
    for row in (loaded, restored):
        assert row.stop_evidence == result.stop_evidence
        assert row.ampel == expected
        assert row.score == result.score
        assert json.loads(pipeline._forensik_json(row))["stop_evidence"] == result.stop_evidence


@pytest.mark.parametrize("evidence", [None, "", "none", "partial", "unknown"])
def test_free_text_cannot_replace_structured_evidence(evidence):
    result = pipeline.ScanResult(id=9000123, score=2, ertrag_monat_pct=6,
                                 forensik_vorhanden=True, stop_nachweis="BEWIESEN: Schutz vorhanden")
    result.stop_evidence = evidence
    assert pipeline.ampel_for(result, {})[0] == "🟡"


@pytest.mark.parametrize("flags,expected", [
    ({"schranke_verletzt": True}, "🔴"), ({"martingale_flag": True}, "🔴"),
    ({"fehler": "storage failure"}, "⚪"), ({"forensik_vorhanden": False}, "⚪"),
])
def test_stop_gate_preserves_existing_risk_and_failure_priorities(flags, expected):
    result = pipeline.ScanResult(id=9000123, score=2, ertrag_monat_pct=6,
                                 forensik_vorhanden=True)
    for key, value in flags.items():
        setattr(result, key, value)
    assert pipeline.ampel_for(result, {})[0] == expected


def test_previous_version_cannot_reuse_green_without_evidence():
    db.init_db()
    old_version = FORENSICS_VERSION - 1
    db.upsert_signal(9000123, stats={"forensik_ok": True, "forensik_version": old_version,
                                    "ertrag_monat_pct": 6})
    db.store_forensik(9000123, {"version": old_version, "score": 2, "ampel": "🟢",
                               "stop_nachweis": "behaupteter Schutz",
                               "peak_exposure": {"shock_pct_max": 1}})
    loaded = pipeline.results_from_db()[0]
    assert not loaded.forensik_vorhanden and loaded.score is None
    assert loaded.ampel == "⚪"
    assert "erneute Prüfung" in loaded.urteil


def test_local_analysis_keeps_structured_stop_evidence(tmp_path):
    path = write_history(tmp_path, "direct")
    result = pipeline.ScanPipeline.analyze_local_files([str(path)])[0]
    assert result.forensik_vorhanden and result.stop_evidence == "direct"
    assert result.source_kind == "demo"
