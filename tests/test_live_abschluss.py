"""Live maintenance must not skip a changed SHA or reuse a failed fresh input."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from mqlkiscanner import analysis_version, config, db, downloader_client, katalog, pipeline, studien_batch


@pytest.mark.parametrize("download_fails", [False, True])
def test_study_refresh_never_skips_changed_sha_or_reuses_failed_input(monkeypatch, tmp_path, download_fails):
    script = Path(__file__).resolve().parents[1] / "scripts/reference/live_abschluss.py"
    spec = importlib.util.spec_from_file_location("live_abschluss", script)
    maintenance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maintenance)
    output = config.DATA_DIR / "runs" / "live_test"
    monkeypatch.setattr(sys, "argv", [str(script), "studies", "--live", "--expected-version",
                                     str(analysis_version.FORENSICS_VERSION), "--output", str(output)])
    result = pipeline.ScanResult(id=77, quelle="mql5", account_currency="USD",
                                 trades_sha256="old", equity_dd_rekonstruiert_pct=5)
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kw: [result])
    monkeypatch.setattr(katalog, "katalog_resultate", lambda **kw: ([], {}))
    monkeypatch.setattr(katalog, "quellen_referenz", lambda r: (1, "mql5"))
    def refresh(r, **kwargs):
        assert kwargs["allow_offline_cache"] is False
        if download_fails:
            raise downloader_client.DownloaderConnectionError("fresh download failed")
        r.quelle_id, r.quelle_version = 1, "mql5"
        return str(tmp_path / "new.csv"), True
    monkeypatch.setattr(katalog, "lade_signal_daten", refresh)
    monkeypatch.setattr(db, "get_quellen_artefakt", lambda *a: {"sha256": "new"})
    calls = []
    def start(rows, **kwargs):
        calls.append((rows, kwargs))
        return SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: False), control={"fertig": True})
    monkeypatch.setattr(studien_batch, "starten", start)
    maintenance.main()
    rows, kwargs = calls[0]
    assert kwargs["nur_luecken"] is False
    if download_fails:
        assert rows == []
        assert result.account_currency is None and not result.trades_path
    else:
        assert rows == [result] and rows[0].trades_sha256 == "new"
        # This old attached value must not cause luecken_sammeln to suppress
        # the new calculation; the maintenance path explicitly recomputes.
        assert result.max_drawdown_equity_pct == 5
