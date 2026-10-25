"""Isolated, synthetic persistence probes; never opens the production database.

Run from the repository root: python <this_file>
All generated CSVs, databases and snapshots live in TemporaryDirectory.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import config, db, engine, katalog, pipeline, quellen, secrets_store
from mqlkiscanner.agenten import lock as scan_lock
from mqlkiscanner.analysis_version import FORENSICS_VERSION

HEADER = "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
BODY = (
    "2023.12.31 10:00:00;Balance;;;;;;;;;;1000;\n"
    "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n"
    "2024.01.02 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.02 11:00:00;1999;0;0;-1;\n"
)
EXTRA = "2024.05.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.05.01 11:00:00;2010;0;0;10;\n"
CSV_A, CSV_B = HEADER + BODY, HEADER + BODY + EXTRA


@contextlib.contextmanager
def isolated():
    with tempfile.TemporaryDirectory(prefix="persistenz_pruefung_") as name:
        base = Path(name)
        with contextlib.ExitStack() as stack:
            for key, relative in {
                "DATA_DIR": "data", "RUNS_DIR": "data/runs", "REPORTS_DIR": "data/reports",
                "TRADES_DIR": "data/trades", "STATS_DIR": "data/stats", "CONFIG_DIR": "config",
                "PROMPTS_DIR": "config/prompts", "DOWNLOADER_DIR": "data/downloader",
                "FX_RATES_DIR": "data/fx_rates",
            }.items():
                directory = base / relative
                directory.mkdir(parents=True, exist_ok=True)
                stack.enter_context(patch.object(config, key, directory))
            stack.enter_context(patch.object(config, "SETTINGS_FILE", base / "config/app_settings.json"))
            stack.enter_context(patch.object(config, "CONTRACT_SPECS_FILE", base / "data/specs.json"))
            stack.enter_context(patch.object(config, "load_settings", lambda: dict(config.DEFAULT_SETTINGS)))
            stack.enter_context(patch.object(config, "load_known_signals", lambda: {"ausgeschlossen": []}))
            stack.enter_context(patch.object(db, "DB_PATH", base / "data/test.db"))
            stack.enter_context(patch.object(secrets_store, "get_secret", lambda *a, **kw: None))
            stack.enter_context(patch.object(pipeline.ScanPipeline, "_kursanbieter_fuer", lambda *a: None))
            stack.enter_context(patch.object(pipeline.fx_rates, "status", lambda: {"geladen": False}))
            stack.enter_context(patch.object(pipeline.time, "sleep", lambda *a: None))
            stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No network in probe")))
            db.init_db()
            path = base / "mutable_download.csv"
            path.write_text(CSV_A, encoding="utf8")
            stack.enter_context(patch.object(pipeline.signal_stats, "fetch_signal_stats", lambda *a: {
                "account_currency": "USD", "dd_equity_pct": 5.0, "monthly_growth_pct": 10.0,
                "initial_deposit_usd": 1000.0,
            }))
            stack.enter_context(patch.object(pipeline.exporter, "export_positions", lambda *a, **kw: (str(path), False)))
            yield path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordinary_roundtrip():
    with isolated() as path:
        result = pipeline.ScanPipeline({"equity_rekonstruktion": False})._analyze_candidate_once(
            None, {"id": 987654321, "name": "Synthetic persistence probe", "platform": "MT5"}, lambda _: None)
        row = db.list_catalog()[0]
        loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
        checks = {
            "scan_succeeded": not result.fehler and result.forensik_vorhanden and result.persisted_this_run,
            "snapshot_separate_from_mutable_input": Path(result.trades_path) != path,
            "snapshot_sha_matches_input_and_db": sha(path) == result.trades_sha256 == row["trades_sha256"],
            "forensics_bound_to_snapshot_sha": row["forensik"]["trades_sha256"] == row["trades_sha256"],
            "forensics_current_after_reload": loaded.forensik_vorhanden and not loaded.forensik_stale,
            "score_winrate_dd_match_reload": (result.score, result.winrate_pct, result.trading_dd_pct)
                == (loaded.score, loaded.winrate_pct, loaded.trading_dd_pct),
        }
        assert all(checks.values()), checks
        path.write_text(CSV_B, encoding="utf8")
        checks["later_download_mutation_does_not_change_stored_snapshot"] = sha(result.trades_path) == result.trades_sha256 != sha(path)
        assert checks["later_download_mutation_does_not_change_stored_snapshot"]
        return checks


def mutation_between_analysis_and_persistence():
    with isolated() as path:
        original = pipeline.analyze_export

        def analyzed_a_then_overwrite_with_b(*a, **kw):
            report = original(*a, **kw)
            path.write_text(CSV_B, encoding="utf8")
            return report

        with patch.object(pipeline, "analyze_export", analyzed_a_then_overwrite_with_b):
            result = pipeline.ScanPipeline({"equity_rekonstruktion": False})._analyze_candidate_once(
                None, {"id": 987654321, "name": "Synthetic mutable input probe", "platform": "MT5"}, lambda _: None)
        row = db.list_catalog()[0]
        loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
        actual = engine.analyze(result.trades_path)
        checks = {
            "scan_reports_success": not result.fehler and result.forensik_vorhanden and result.persisted_this_run,
            "forensics_trade_count": row["forensik"]["trades_anzahl"],
            "stored_snapshot_trade_count": actual["stats"]["trades_anzahl"],
            "forensics_winrate": row["forensik"]["winrate_pct"],
            "stored_snapshot_winrate": actual["stats"]["winrate_pct"],
            "forensics_sha_claims_current_snapshot": row["forensik"]["trades_sha256"] == row["trades_sha256"],
            "reload_accepts_forensics_as_current": loaded.forensik_vorhanden and not loaded.forensik_stale,
        }
        assert checks["scan_reports_success"], checks
        assert checks["forensics_trade_count"] == 2 and checks["stored_snapshot_trade_count"] == 3, checks
        assert checks["forensics_sha_claims_current_snapshot"] and checks["reload_accepts_forensics_as_current"], checks
        return checks


def missing_snapshot_reload():
    with isolated():
        result = pipeline.ScanPipeline({"equity_rekonstruktion": False})._analyze_candidate_once(
            None, {"id": 987654321, "name": "Synthetic missing snapshot probe", "platform": "MT5"}, lambda _: None)
        Path(result.trades_path).unlink()
        loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
        return {
            "snapshot_exists": Path(loaded.trades_path).exists(),
            "reload_accepts_forensics_as_current": loaded.forensik_vorhanden and not loaded.forensik_stale,
            "reload_reports_error": bool(loaded.fehler),
            "recorded_sha_present": bool(loaded.trades_sha256),
        }


def catalog_reload_while_scan_lock_held():
    """Deterministic interleaving via the actual on-demand load API.

    After the scanner has analyzed A, another UI action can fetch B through
    katalog.lade_signal_daten. Holding the common scan lock does not reject
    this action; ingest's lock ends when its individual download returns.
    """
    with isolated():
        signal_id = 987654321
        source_id = db.add_quelle("synthetic", "Synthetic source", "http://example.invalid")
        manual_result = pipeline.ScanResult(id=signal_id, quelle="synthetic", quelle_id=source_id,
                                             quelle_version="mql5", platform="MT5")
        payloads = iter((CSV_A.encode(), CSV_B.encode()))

        class FakeSource:
            def metrics(self, *args):
                return {"signalId": signal_id, "version": "mql5", "metrics": {
                    "Currency": "USD", "InitialDeposit": 1000, "EquityDrawdown": 5}}

            def trades_csv(self, *args):
                return next(payloads)

        original = pipeline.analyze_export
        manual_completed = []

        def analyzed_a_then_ui_download_b(*a, **kw):
            report = original(*a, **kw)
            path, changed = katalog.lade_signal_daten(manual_result)
            manual_completed.append(changed)
            return report

        with patch.object(quellen, "client_fuer_quelle", lambda *_: FakeSource()), \
                patch.object(pipeline, "analyze_export", analyzed_a_then_ui_download_b), \
                scan_lock.lauf_lock(config.DATA_DIR):
            result = pipeline.ScanPipeline({"equity_rekonstruktion": False})._analyze_candidate_once(
                None, {"id": signal_id, "name": "Synthetic source race", "platform": "MT5",
                       "quelle_id": source_id, "quelle_kuerzel": "synthetic", "quelle_version": "mql5"}, lambda _: None)
        row = db.list_catalog()[0]
        loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
        actual = engine.analyze(result.trades_path)
        checks = {
            "manual_download_completed_despite_held_scan_lock": manual_completed == [True],
            "scan_reports_success": not result.fehler and result.forensik_vorhanden,
            "forensics_trade_count": row["forensik"]["trades_anzahl"],
            "stored_snapshot_trade_count": actual["stats"]["trades_anzahl"],
            "forensics_winrate": row["forensik"]["winrate_pct"],
            "stored_snapshot_winrate": actual["stats"]["winrate_pct"],
            "forensics_sha_claims_current_snapshot": row["forensik"]["trades_sha256"] == row["trades_sha256"],
            "reload_accepts_forensics_as_current": loaded.forensik_vorhanden and not loaded.forensik_stale,
        }
        assert checks["manual_download_completed_despite_held_scan_lock"] and checks["scan_reports_success"], checks
        assert checks["forensics_trade_count"] != checks["stored_snapshot_trade_count"], checks
        return checks


if __name__ == "__main__":
    output = {
        "scope": "Isolated synthetic probes, temporary DB/files, no production reads/writes, no network/secrets",
        "forensics_version": FORENSICS_VERSION,
        "ordinary_roundtrip": ordinary_roundtrip(),
        "mutation_between_analysis_and_persistence": mutation_between_analysis_and_persistence(),
        "catalog_reload_while_scan_lock_held": catalog_reload_while_scan_lock_held(),
        "missing_snapshot_reload": missing_snapshot_reload(),
    }
    print(json.dumps(output, ensure_ascii=True, indent=2))
