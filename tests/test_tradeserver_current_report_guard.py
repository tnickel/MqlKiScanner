"""Historical unbound own reports must not enter a current v2 snapshot."""
from __future__ import annotations

import pytest

from mqlkiscanner import config, db, tradeserver_sync as sync
from mqlkiscanner.pipeline import ScanResult


@pytest.fixture
def result():
    db.init_db()
    db.add_quelle("mql5", "MQL5", "http://synthetic.invalid")
    return ScanResult(id=77, quelle="mql5", forensik_vorhanden=True,
        berichte_basis="synthetic-current-evidence", trade_analyse="Current report",
        gesamtbericht="Old positive conclusion", gesamtbericht_at="2026-09-01",
        tiefenanalyse="Old positive depth report", kurzfassung="Old positive summary")


@pytest.mark.parametrize("changed", [{"berichte_basis": ""}, {"forensik_vorhanden": False},
    {"fehler": "new scan failed"}, {"forensik_stale": True}])
def test_historical_texts_stay_local_but_no_current_counts_summary_or_pdf(monkeypatch, result, changed):
    for field, value in changed.items():
        setattr(result, field, value)
    historical = result.tiefenanalyse
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: pytest.fail("unbound PDF materialized"))
    row = sync.signal_zeilen([result])[0]
    assert row["docsBerichte"] == row["docsTiefenanalyse"] == 0
    assert row["berichtVom"] is None and not row["kurzfassung"]
    docs, errors = sync.dokumente_sammeln([result])
    assert docs == [] and errors == []
    assert result.tiefenanalyse == historical


def test_current_bound_reports_remain_exportable(monkeypatch, tmp_path, result):
    paths = {}
    for kind in ("trade_analyse", "gesamtbericht", "tiefenanalyse"):
        path = tmp_path / f"{kind}.pdf"
        path.write_bytes(b"%PDF-1.4 current")
        paths[kind] = path
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: paths)
    row = sync.signal_zeilen([result])[0]
    assert row["docsBerichte"] == 2 and row["docsTiefenanalyse"] == 1
    docs, errors = sync.dokumente_sammeln([result])
    assert len(docs) == 3 and not errors
    assert all(d["sourceUid"] == db.source_identity("mql5")["quellen_uid"] for d in docs)


def test_separately_source_owned_downloader_original_can_still_be_mirrored(monkeypatch, result):
    result.berichte_basis = ""
    path = config.DOWNLOADER_DIR / "original.pdf"
    path.write_bytes(b"%PDF-1.4 original source report")
    db.store_downloader_report(77, "mql5", "original.pdf", str(path), quelle="mql5")
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: pytest.fail("unbound own report materialized"))
    row = sync.signal_zeilen([result])[0]
    assert row["docsBerichte"] == row["docsTiefenanalyse"] == 0 and row["docsDownloader"] == 1
    docs, errors = sync.dokumente_sammeln([result])
    assert len(docs) == 1 and docs[0]["group"] == "downloader" and not errors


def test_v2_completion_excludes_stale_inventory_keys_so_atomic_commit_removes_them(monkeypatch, result):
    result.berichte_basis = ""
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: pytest.fail("unbound own report materialized"))
    calls = {}

    class Fake:
        base = "http://synthetic.invalid"
        def register(self, signal_count):
            return {"protocolVersion": 2, "runId": 42,
                    "documents": [{"docKey": "signal/old/77/old.pdf", "sha256": "old"}]}
        def signals(self, rows):
            calls["signals"] = rows
            return {"stored": len(rows), "staged": True}
        def document(self, doc):
            pytest.fail("stale document uploaded")
        def complete(self, **stats):
            calls["complete"] = stats
            return {"stored": 1, "deleted": 0}
        def abort(self, reason):
            pytest.fail(reason)

    summary = sync.sync_alle([result], client=Fake())
    assert summary["abgebrochen"] is None and summary["dokumente"] == 0
    assert calls["complete"]["document_keys"] == []
    assert calls["signals"][0]["docsTiefenanalyse"] == 0
