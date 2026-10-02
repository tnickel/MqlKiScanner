"""Read-only production snapshot and isolated source/report regressions.

Run from the repository root. No init_db, network, LLM or MT5 calls.
Production SQLite uses URI mode=ro. All reproduction mutations use an
in-memory database, mocks or TemporaryDirectory. Output is JSON on stdout.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import config, db, downloader_client, ingest, llm_runner, pdf_reports, pipeline


def isolated_probes():
    out = {}
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE signals (signal_id INTEGER PRIMARY KEY, name TEXT, "
                     "platform TEXT, url TEXT, autor TEXT, abo_preis REAL, abonnenten REAL, "
                     "wochen REAL, stats_json TEXT, updated_at TEXT, quelle TEXT DEFAULT 'mql5')")
        db.upsert_signal(123, name="Pelican 123", platform="pelican", quelle="pelik", _connection=conn)
        db.upsert_signal(123, name="Direct MQL5 123", platform="mt5", _connection=conn)
        direct = dict(conn.execute("SELECT name,platform,quelle FROM signals").fetchone())
        assert direct == {"name": "Direct MQL5 123", "platform": "mt5", "quelle": "pelik"}
        out["direct_source_collision"] = direct
        try:
            db.upsert_signal(123, name="Explicit MQL5", quelle="mql5", _connection=conn)
        except ValueError:
            out["explicit_source_guard"] = "blocked correctly"
        else:
            raise AssertionError("Explicit source conflict must be blocked")

    with tempfile.TemporaryDirectory(prefix="scanner-readonly-review-") as directory:
        path = Path(directory) / "trades.csv"
        original = b"Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0;10\n"
        changed = original.replace(b";0;0;10\n", b";0;0;1000\n")
        path.write_bytes(changed)
        recorded = {"path": str(path), "sha256": hashlib.sha256(original).hexdigest()}
        offline = SimpleNamespace(trades_csv=lambda *_: (_ for _ in ()).throw(
            downloader_client.DownloaderConnectionError("offline")))
        with patch.object(db, "get_quellen_artefakt", return_value=recorded):
            selected, modified = ingest.hole_trades({"id": 2}, 123, "pelican", client=offline)
        assert Path(selected).read_bytes() == changed and modified is False
        assert hashlib.sha256(path.read_bytes()).hexdigest() != recorded["sha256"]
        out["offline_cache_sha_bypass"] = {"modified_reported": modified,
                                            "original_profit": 10, "used_profit": 1000}

    result = pipeline.ScanResult(id=999001, name="Same basis retry", forensik_vorhanden=True,
                                 trade_analyse="old trade", risiko_analyse="old risk",
                                 gesamtbericht="old total", kurzfassung="old summary",
                                 gesamtbericht_at="2026-10-01 08:00:00", berichte_basis="same")
    def fake_chat(prompt, **kwargs):
        if prompt == "risk prompt":
            raise RuntimeError("risk prompt failed")
        return "new trade"
    client = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=0), chat=fake_chat)
    pipe = SimpleNamespace(settings={}, llm=client)
    with patch.object(pipeline, "refresh_report_verdict"), \
            patch.object(pipeline, "report_basis_for", return_value="same"), \
            patch.object(llm_runner.prompt_fill, "build_trade_prompt", return_value="trade prompt"), \
            patch.object(llm_runner.prompt_fill, "build_risk_prompt", return_value="risk prompt"), \
            patch.object(db, "store_analysis", return_value="2026-10-02 12:00:00"):
        status = llm_runner.run_llm(pipe, [result], lambda _: None)
    assert result.trade_analyse == "new trade" and result.risiko_analyse == "old risk"
    assert result.gesamtbericht == "old total" and status["failed"] == 1
    out["same_basis_retry_mixture"] = {"trade": result.trade_analyse, "risk": result.risiko_analyse,
                                       "total": result.gesamtbericht, "summary": result.kurzfassung,
                                       "status": status}
    return out


def production_snapshot():
    with sqlite3.connect((ROOT / "data/mqlkiscanner.db").as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        rows = []
        for row in conn.execute("SELECT s.signal_id,s.name,s.platform,s.url,s.autor,s.abo_preis,"
                                "s.abonnenten,s.wochen,s.quelle,s.stats_json,s.updated_at signal_updated,"
                                "t.path trades_path,t.sha256 trades_sha256,t.fetched_at trades_fetched,"
                                "f.json forensik_json,f.updated_at forensik_updated FROM signals s "
                                "LEFT JOIN trade_files t ON t.signal_id=s.signal_id "
                                "LEFT JOIN forensik f ON f.signal_id=s.signal_id"):
            row = dict(row)
            row["stats"] = json.loads(row.pop("stats_json") or "{}")
            row["forensik"] = json.loads(row.pop("forensik_json") or "null")
            for kind, prefix in (("trade_analyse", "trade"), ("risiko_analyse", "risiko"),
                                 ("gesamtbericht", "gesamt"), ("tiefenanalyse", "tiefe")):
                latest = conn.execute("SELECT * FROM analyses WHERE signal_id=? AND kind=? "
                                      "ORDER BY id DESC LIMIT 1", (row["signal_id"], kind)).fetchone()
                row[kind] = latest["text"] if latest else ""
                row[prefix + "_at"] = latest["created_at"] if latest else ""
                row[prefix + "_model"] = latest["model"] if latest else ""
            rows.append(row)

        def latest(signal_id, kind, *, basis=None):
            row = conn.execute("SELECT * FROM analyses WHERE signal_id IS ? AND kind=? "
                               "AND (? IS NULL OR basis=?) ORDER BY id DESC LIMIT 1",
                               (signal_id, kind, basis, basis)).fetchone()
            return dict(row) if row else None
        with patch.object(db, "list_catalog", return_value=rows), \
                patch.object(db, "get_latest_analysis", side_effect=latest), \
                patch.object(pdf_reports, "materialize_result_pdfs", return_value={}):
            results = pipeline.results_from_db(config.load_settings())

        deep_stale = []
        mismatched_restored = []
        report_phases = []
        for r in results:
            for kind in ("trade_analyse", "risiko_analyse", "gesamtbericht"):
                if getattr(r, kind):
                    current = latest(r.id, kind, basis=r.berichte_basis)
                    if not current or current["text"] != getattr(r, kind):
                        mismatched_restored.append([r.id, kind])
            if r.tiefenanalyse:
                a = latest(r.id, "tiefenanalyse")
                if a["basis"] != r.berichte_basis:
                    deep_stale.append({"id": r.id, "name": r.name, "created_at": a["created_at"],
                                       "saved_basis": a["basis"], "current_basis": r.berichte_basis})
            if r.forensik_aktualisiert.startswith("2026-10-02 11:09") or r.forensik_aktualisiert.startswith("2026-10-02 11:10"):
                report_phases.append({"id": r.id, "name": r.name, "quelle": r.quelle,
                                      "ampel": r.ampel, "trade_at": r.trade_analyse_at,
                                      "risk_at": r.risiko_analyse_at, "total_at": r.gesamtbericht_at,
                                      "basis": r.berichte_basis,
                                      "basis_source": r.kapitalbasis_verwendet_quelle,
                                      "basis_usd": r.kapitalbasis_verwendet_usd,
                                      "ertrag_forensik": r.ertrag_monat_pct_forensik})
        excerpts = []
        for sid in (2375480, 2059368, 2039057):
            a = latest(sid, "gesamtbericht")
            excerpts.append({"signal_id": sid, "analysis_id": a["id"], "created_at": a["created_at"],
                             "paragraphs": [p for p in a["text"].split("\n\n")
                                            if any(s in p for s in ("ohne nachweisbaren Einzelpositions", "Hilfsrechnung", "Näherung über lineare"))]})
        return {"signals": len(results), "current_report_basis_mismatches": mismatched_restored,
                "restored_stale_deep_analyses": deep_stale, "current_scan_phases": report_phases,
                "report_excerpts": excerpts}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"isolated": isolated_probes(), "production_readonly": production_snapshot()},
                     ensure_ascii=False, indent=2))
