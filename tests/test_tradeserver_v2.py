"""V2 contracts: namespaces, run binding, immutable bytes and complete manifests."""
from dataclasses import replace
import hashlib

import pytest

from mqlkiscanner import db, pipeline, tradeserver_client as client, tradeserver_sync as sync
from test_tradeserver_client import _Antwort, _verdrahte
from test_tradeserver_sync import _FakeClient


@pytest.mark.parametrize("body", [
    {"runId": 2}, {"runId": 2, "protocolVersion": 1},
    {"runId": True, "protocolVersion": 2}, {"runId": 0, "protocolVersion": 2},
])
def test_register_requires_explicit_v2_confirmation(monkeypatch, body):
    calls = _verdrahte(monkeypatch, _Antwort(body=body))
    c = client.TradeserverClient("http://synthetic.invalid")
    with pytest.raises(client.TradeserverProtocolError):
        c.register()
    assert c.run_id is None
    assert len(calls) == 1


def test_writes_need_handshake_and_bind_run(monkeypatch):
    calls = _verdrahte(monkeypatch, _Antwort(body={"protocolVersion": 2, "runId": 41}))
    c = client.TradeserverClient("http://synthetic.invalid")
    with pytest.raises(client.TradeserverProtocolError):
        c.signals([])
    assert not calls
    c.register()
    c.signals([])
    c.document({"runId": 999, "docKey": "portfolio/x.pdf"})
    c.complete(signals=0, documents=1, uploaded=1, skipped=0, bytes_total=20,
               document_keys=["portfolio/x.pdf"])
    assert all(call["json"]["runId"] == 41 for call in calls[1:])
    assert calls[-1]["json"]["documentKeys"] == ["portfolio/x.pdf"]
    assert c.run_id is None


def test_equal_ids_different_sources_have_distinct_rows_and_documents(monkeypatch, tmp_path):
    results = []
    for source in ("first", "second"):
        db.add_quelle(source, source, "http://synthetic.invalid")
        db.upsert_signal(77, quelle=source, name=source, platform="MT5")
        owner = db.resolve_identity(77, quelle=source)
        results.append(pipeline.ScanResult(id=77, name=source, quelle=source,
                       quellen_uid=owner.quellen_uid, signal_ref=owner.signal_ref,
                       forensik_vorhanden=True, berichte_basis="synthetic-current-proof"))
    pdf = tmp_path / "same.pdf"
    pdf.write_bytes(b"%PDF-1.4 same synthetic bytes")
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: {"gesamtbericht": pdf})
    fake = _FakeClient()
    result = sync.sync_alle(results, client=fake)
    assert result["abgebrochen"] is None
    assert result["signale"] == 2 and result["uebertragen"] == 2
    rows = next(value for step, value in fake.aufrufe if step == "signals")
    assert rows[0]["signalId"] == rows[1]["signalId"] == 77
    assert rows[0]["sourceUid"] != rows[1]["sourceUid"]
    keys = [value for step, value in fake.aufrufe if step == "document"]
    assert len(set(keys)) == 2
    assert fake.aufrufe[-1][1]["document_keys"] == keys
    before = rows[0]["sourceUid"]
    q = db.list_quellen()[0]
    db.update_quelle(q["id"], kuerzel="renamed")
    row = sync.signal_zeilen([results[0]])[0]
    assert row["sourceUid"] == before and row["source"] == "renamed"


def test_inventory_wrong_owner_never_skips_equal_hash(monkeypatch, tmp_path):
    db.add_quelle("mql5", "mql5", "http://synthetic.invalid")
    r = pipeline.ScanResult(id=77, quelle="mql5", name="synthetic",
                           forensik_vorhanden=True, berichte_basis="synthetic-current-proof")
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 synthetic")
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: {"gesamtbericht": pdf})
    key = sync._document_prefix(sync._remote_identity(r)) + "/report.pdf"
    class Remote(_FakeClient):
        def register(self, signal_count=0):
            info = super().register(signal_count)
            info["documents"] = [{"docKey": key, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                   "sourceUid": "foreign", "signalId": 77}]
            return info
    report = sync.sync_alle([r], client=Remote())
    assert report["uebertragen"] == 1 and report["uebersprungen"] == 0


def test_absent_namespace_aborts_before_connecting(monkeypatch):
    monkeypatch.setattr(sync, "_client", lambda: pytest.fail("No transport before owner proof"))
    with pytest.raises(client.TradeserverError, match="Unbelegte Quellenidentität"):
        sync.sync_alle([pipeline.ScanResult(id=77, quelle="unknown")])


def test_old_server_is_reachable_but_not_compatible(monkeypatch):
    from mqlkiscanner import config
    config.save_settings({**config.load_settings(), "tradeserver_base_url": "http://synthetic.invalid"})
    class V1(_FakeClient):
        def ping(self):
            return {"status": "ok", "kiscannerApi": 1}
    monkeypatch.setattr(sync, "_client", V1)
    status = sync.verbindungs_status(force=True)
    assert status["ok"] is False
    assert "v2 erforderlich" in status["detail"]


def test_upload_sha_matches_bytes_changed_after_collection(monkeypatch, tmp_path):
    db.add_quelle("mql5", "mql5", "http://synthetic.invalid")
    r = pipeline.ScanResult(id=77, quelle="mql5", forensik_vorhanden=True,
                           berichte_basis="synthetic-current-proof")
    pdf = tmp_path / "changing.pdf"
    pdf.write_bytes(b"%PDF-1.4 before")
    monkeypatch.setattr(sync, "materialize_result_pdfs", lambda r: {"gesamtbericht": pdf})
    class Changing(_FakeClient):
        def register(self, signal_count=0):
            response = super().register(signal_count)
            pdf.write_bytes(b"%PDF-1.4 updated and longer")
            return response
        def document(self, doc):
            import base64
            actual = base64.b64decode(doc["contentBase64"])
            assert hashlib.sha256(actual).hexdigest() == doc["sha256"]
            assert len(actual) == doc["sizeBytes"]
            return super().document(doc)
    result = sync.sync_alle([r], client=Changing())
    assert result["abgebrochen"] is None
    assert result["bytes"] == len(pdf.read_bytes())


@pytest.mark.parametrize("reliable", [True, False])
def test_annual_calmar_and_provisional_measurement_are_explicit(reliable):
    from mqlkiscanner import config
    db.add_quelle("mql5", "mql5", "http://synthetic.invalid")
    config.save_settings({**config.load_settings(), "min_calmar_jahr": 4.0,
                          "schranke_eq_dd_pct": 50.0})
    r = pipeline.ScanResult(id=77, quelle="mql5", cagr_jahr_pct=60,
                           ertrag_monat_geom_pct=4, equity_dd_rekon_roh_pct=10,
                           equity_dd_rekonstruiert_pct=10 if reliable else None,
                           equity_rekon_grund="" if reliable else "Kurslücke")
    row = sync.signal_zeilen([r])[0]
    assert row["minCalmarJahr"] == 4 and row["drawdownLimitPct"] == 50
    assert row["retddJahr"] == (6 if reliable else None)
    assert row["retddJahrVorbehalt"] == (None if reliable else 6)
    assert row["equityMeasurementStatus"].startswith("Gemessen:" if reliable else "Keine belastbare")
    if not reliable:
        assert row["retddVorbehaltGrund"] == "Kurslücke"


def test_pdf_owner_paths_do_not_fold_distinct_namespace_strings():
    from mqlkiscanner.pdf_reports import PdfReport, report_storage_path
    base = PdfReport(kind="gesamtbericht", body="same", signal_id=77, signal_name="same")
    uids = ["a/b", "a b", "A B", "ä", "a", "x" * 60 + "1", "x" * 60 + "2"]
    paths = {report_storage_path(replace(base, quellen_uid=uid), snapshot="same") for uid in uids}
    assert len(paths) == len(uids)
    uid_path = report_storage_path(replace(base, quellen_uid="same"), snapshot="same")
    alias_path = report_storage_path(replace(base, quelle="same"), snapshot="same")
    assert uid_path != alias_path
