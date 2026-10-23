"""Source identity survives equal external IDs, platforms and trade bytes."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import io
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import (app_ui, db, downloader_sync, katalog, pdf_reports,
                         pipeline, portfolio_statistik, rest_api, studien_batch,
                         tradeserver_client, tradeserver_sync)
from mqlkiscanner.alle_signale_ui import tabellen_zeile


@pytest.fixture
def twins(tmp_path):
    db.init_db()
    path = tmp_path / "same.csv"
    path.write_text("same synthetic bytes", encoding="utf-8")
    rows = []
    for source in ("alpha", "beta"):
        qid = db.add_quelle(source, source, "http://synthetic.invalid")
        db.upsert_signal(77, name="Same name", platform="MT5", quelle=source,
                         stats={"account_currency": "USD", "account_currency_evidence_version": 19})
        owner = db.resolve_identity(77, quelle=source)
        rows.append(pipeline.ScanResult(
            id=77, name="Same name", quelle=source, platform="MT5", account_currency="USD",
            signal_ref=owner.signal_ref, quellen_uid=owner.quellen_uid,
            quelle_id=qid, quelle_version="mql5", trades_path=str(path),
            trades_sha256="a" * 64, ampel="🟡"))
    return rows


def test_table_metadata_marks_and_notes_are_source_scoped(twins):
    now = datetime.now()
    for r, initial, current, color in zip(twins, (3, 30), (7, 41), ("gruen", "orange")):
        db.store_history_points(77, "mql5", [
            {"timestamp": (now - timedelta(days=7)).isoformat(), "subscribers": initial},
            {"timestamp": now.isoformat(), "subscribers": current}], quelle=r.quelle)
        db.setze_markierung(77, color, quelle=r.quelle)
        db.setze_kommentar(77, "note " + r.quelle, quelle=r.quelle)
    frame = app_ui.results_table_dataframe(twins, fresh_ids={twins[0].signal_key},
                                           fix_ids={twins[1].signal_key})
    assert list(frame["ID"]) == [77, 77]
    assert list(frame["Quelle"]) == ["alpha", "beta"]
    assert list(frame["Abonnenten"]) == ["7", "41"]
    assert list(frame["7 Tage"]) == ["🟢 +4", "🟢 +11"]
    assert list(frame["Stand"]) == ["NEU", ""]
    assert list(frame["Fix"]) == ["", "📌 FIX"]
    marks = db.list_markierungen(identitaeten=True)
    notes = db.list_kommentare(identitaeten=True)
    assert notes == {("alpha", 77): "note alpha", ("beta", 77): "note beta"}
    mapped = [tabellen_zeile(r, None, marks, notes, fix_ids=set()) for r in twins]
    assert [r["Mark."] for r in mapped] == ["🟩", "🟧"]
    assert all(r["Komm."] == "📋" for r in mapped)


def test_snapshot_selection_pdf_and_study_cache_separate_equal_bytes(twins):
    from mqlkiscanner.equity_studie_ui import _cache_key
    a, b = twins
    assert app_ui._result_identity(a) != app_ui._result_identity(b)
    assert _cache_key(a) != _cache_key(b)
    assert pdf_reports.result_snapshot_token(a) != pdf_reports.result_snapshot_token(b)
    specs = [pdf_reports.result_pdf_spec(r, "gesamtbericht")[0] for r in twins]
    paths = [pdf_reports.report_storage_path(s, snapshot="same") for s in specs]
    assert paths[0] != paths[1]
    renamed = replace(a, quelle="renamed")
    old_spec = pdf_reports.result_pdf_spec(a, "gesamtbericht")[0]
    new_spec = pdf_reports.result_pdf_spec(renamed, "gesamtbericht")[0]
    assert pdf_reports.report_storage_path(old_spec, snapshot="same") == pdf_reports.report_storage_path(new_spec, snapshot="same")
    assert app_ui._result_identity(a) != app_ui._result_identity(renamed)


def test_one_sources_study_does_not_fill_another_sources_gap(twins):
    a, b = twins
    study = {"trades_sha": a.trades_sha256, "basislos": False, "report": {
        "equity_dd_pct": 5, "verlaesslich": True}}
    jobs, completed = studien_batch.luecken_sammeln(
        twins, {a.signal_key: study}, trades_nachladen=False)
    assert completed == 1
    assert [r.signal_key for r in jobs] == [b.signal_key]


def test_workflow_metrics_keep_both_source_keys(twins):
    stats = katalog.workflow_stats_bulk(twins, {
        twins[0].signal_key: {"balance_usd": 100},
        twins[1].signal_key: {"balance_usd": 200}},
        katalog_rows=[], quellen_rows=[], artefakte={})
    assert stats[twins[0].signal_key]["balance_usd"] == 100
    assert stats[twins[1].signal_key]["balance_usd"] == 200


def test_catalog_artifacts_and_studies_follow_their_source_at_equal_sha(twins, tmp_path):
    for r, balance, dd in zip(twins, (100, 200), (10, 20)):
        db.katalog_upsert_many(r.quelle, [{"signal_id": 77, "name": "Same name",
                                           "platform": "mt5", "version": "mql5"}])
        raw = Path(r.trades_path).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        db.store_quellen_artefakt(r.quelle_id, 77, "mql5", "trades", sha, r.trades_path)
        metrics = tmp_path / (r.quelle + ".json")
        payload = json.dumps({"signalId": 77, "version": "mql5", "metrics": {
            "Currency": "USD", "Balance": balance}}).encode()
        metrics.write_bytes(payload)
        db.store_quellen_artefakt(r.quelle_id, 77, "mql5", "metrics",
                                  hashlib.sha256(payload).hexdigest(), str(metrics))
        db.store_equity_studie(77, sha, {"equity_dd_pct_raw": dd, "verlaesslich": True},
                               cagr_jahr_pct=60, quelle=r.quelle)
    rows, stats = katalog.katalog_resultate(gescannt=set())
    assert [r.signal_key for r in rows] == [("alpha", 77), ("beta", 77)]
    assert [r.max_drawdown_equity_pct for r in rows] == [10, 20]
    assert [stats[r.signal_key]["balance_usd"] for r in rows] == [100, 200]
    assert rows[0].trades_sha256 == rows[1].trades_sha256


def test_legacy_numeric_fresh_marker_never_spreads_between_sources(twins):
    frame = app_ui.results_to_dataframe(twins, fresh_ids={77})
    assert list(frame["Stand"]) == ["", ""]


def test_downloader_mirrors_only_the_selected_source(twins, monkeypatch):
    seen = []
    class Client:
        def __init__(self, source):
            self.source = source
        def history(self, sid, version):
            seen.append((self.source, sid, version))
            return [{"timestamp": "2026-10-01T12:00:00", "subscribers": 1 if self.source == "alpha" else 2}]
        def reports(self, sid, version):
            return [{"name": "same.pdf", "sizeBytes": 1, "lastModified": "same"}]
        def download_report(self, sid, version, name):
            return self.source.encode()
    monkeypatch.setattr(downloader_sync.quellen, "client_fuer_quelle", lambda source: Client(source["kuerzel"]))
    summary = downloader_sync.sync_many([(r.quelle, r.id, r.platform) for r in twins])
    assert summary["signale"] == 2 and not summary["abgebrochen"]
    assert seen == [("alpha", 77, "mql5"), ("beta", 77, "mql5")]
    assert db.get_history(77, quelle="alpha")[0]["subscribers"] == 1
    assert db.get_history(77, quelle="beta")[0]["subscribers"] == 2
    docs = [db.list_downloader_reports(77, quelle=r.quelle)[0] for r in twins]
    assert docs[0]["path"] != docs[1]["path"]


def test_v2_export_rejects_false_uid_before_client_or_journal(twins, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("No client or sync write before identity validation")
    monkeypatch.setattr(tradeserver_sync, "_client", forbidden)
    monkeypatch.setattr(db, "start_tradeserver_sync_run", forbidden)
    twins[1].quellen_uid = twins[0].quellen_uid
    with pytest.raises(tradeserver_client.TradeserverError, match="Quellen-UID widerspricht"):
        tradeserver_sync._sync_alle(twins)


def test_rest_keeps_external_id_and_exposes_distinct_source_keys(twins):
    rows = rest_api.signal_payload(twins, settings={})["signals"]
    assert [r["signalId"] for r in rows] == [77, 77]
    assert [r["signalKey"] for r in rows] == ["alpha:77", "beta:77"]


def test_portfolio_curves_do_not_overwrite_equal_external_ids(twins, monkeypatch):
    for r, basis in zip(twins, (-1, -2)):
        r.kapitalbasis_verwendet_usd = basis
        r.symbole = "XAUUSD EURUSD GBPUSD"
    monkeypatch.setattr(portfolio_statistik, "monatsrenditen", lambda path, basis, **kw: {"2026-01": basis})
    result = portfolio_statistik.statistik(twins)
    cluster = result["verlustmonate_cluster"]["2026-01"]
    assert cluster["n"] == 2
    assert sorted(s["pct"] for s in cluster["signale"]) == [-2, -1]
    assert {tuple(s["signal_key"]) for s in cluster["signale"]} == {("alpha", 77), ("beta", 77)}
    assert len({tuple(r["signal_key"]) for r in result["signale"]}) == 2


def test_pdf_reports_show_the_source_even_for_identical_names_and_ids(twins):
    from io import BytesIO
    from pypdf import PdfReader
    from mqlkiscanner.pdf_reports import result_pdf_spec, render_report_pdf
    for result in twins:
        result.gesamtbericht = "Identischer Befund"
        spec, _ = result_pdf_spec(result, "gesamtbericht")
        text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(render_report_pdf(spec))).pages)
        assert "Datenquelle" in text and result.quelle in text


def test_batch_currency_diagnostics_keep_same_id_sources_separate(twins):
    from mqlkiscanner.alle_signale_ui import studien_batch_unbekannte_waehrungen
    twins[0].account_currency, twins[1].account_currency = "USD", "EUR"
    errors = [f"[{r.quelle}] #77 Same name: ValueError: Kontowährung unbekannt: "
              "USD-Forensik gesperrt" for r in twins]
    rows = studien_batch_unbekannte_waehrungen(errors, twins)
    assert [(r["Quelle"], r["Aktueller Nachweis"]) for r in rows] == [("alpha", "USD"), ("beta", "EUR")]


@pytest.mark.parametrize("existing_source", [None, "alpha"])
def test_tiefen_batch_queue_and_cached_report_are_source_scoped(twins, monkeypatch, existing_source):
    import builtins
    from mqlkiscanner import tiefen_batch
    monkeypatch.setattr(builtins, tiefen_batch._BATCH_ATTR, None, raising=False)
    monkeypatch.setattr(tiefen_batch.secrets_store, "get_secret", lambda _: "synthetic-test-key")
    monkeypatch.setattr(pipeline, "report_basis_for", lambda *a: "qualified-basis")
    if existing_source:
        db.store_analysis(77, "tiefenanalyse", "test", 0, "alpha report",
                          basis="qualified-basis", quelle=existing_source)
    calls = []
    monkeypatch.setattr(tiefen_batch, "run_tiefenanalyse_einzeln",
                        lambda result, **kwargs: calls.append(result.signal_key))
    ok, message = tiefen_batch.batch_starten(twins)
    assert ok, message
    batch = tiefen_batch.aktiver_batch()
    batch["thread"].join(10)
    assert not batch["thread"].is_alive() and batch["fertig"]
    assert batch["total"] == 2 and batch["done"] == 2
    assert calls == ([("beta", 77)] if existing_source else [("alpha", 77), ("beta", 77)])
    assert batch["uebersprungen"] == int(existing_source is not None)


@pytest.mark.parametrize("conflict", ["connection", "reference", "platform"])
def test_contradicting_source_references_stop_before_cache_network_or_terminal(twins, monkeypatch, conflict):
    from mqlkiscanner import downloader_client, equity_studie_ui, ingest
    result = replace(twins[0])
    if conflict == "connection":
        result.quelle_id = twins[1].quelle_id
    elif conflict == "reference":
        result.signal_ref = twins[1].signal_ref
    else:
        result.quelle_version = "mql4"
    def forbidden(*a, **kwargs):
        raise AssertionError("Conflicting source must stop before any data access")
    monkeypatch.setattr(db, "get_quellen_artefakt", forbidden)
    monkeypatch.setattr(ingest, "hole_metrics", forbidden)
    monkeypatch.setattr(ingest, "hole_trades", forbidden)
    monkeypatch.setattr(equity_studie_ui.kursdaten, "KursDaten", forbidden)
    assert katalog.metrics_stats(result) == {}
    with pytest.raises(downloader_client.DownloaderError):
        katalog.lade_signal_daten(result)
    with pytest.raises(ValueError):
        equity_studie_ui.berechne(result, lambda *a: None)


def test_filtered_row_does_not_authorize_ambiguous_legacy_stats(twins):
    from mqlkiscanner.signal_identity import AmbiguousSignalIdentity
    with pytest.raises(AmbiguousSignalIdentity):
        katalog.workflow_stats_bulk([twins[0]], {77: {"balance_usd": 999}},
                                    katalog_rows=[], quellen_rows=[], artefakte={})


def test_removed_connection_cannot_fetch_but_keeps_scoped_cached_owner(twins, monkeypatch):
    from mqlkiscanner import downloader_client, ingest
    db.delete_quelle(twins[0].quelle_id)
    result = replace(twins[0], quelle_id=9999)
    monkeypatch.setattr(ingest, "hole_trades", lambda *a, **k: pytest.fail("Unknown connection"))
    assert katalog.quellen_referenz(result) is None
    assert katalog.metrics_stats(result) == {}
    katalog.require_eindeutige_studien_identitaet(result)
    with pytest.raises(downloader_client.DownloaderError):
        katalog.lade_signal_daten(result)


@pytest.mark.parametrize("filtered", [False, True])
def test_results_app_table_and_csv_keep_source_rows(twins, monkeypatch, filtered):
    downloads = []
    monkeypatch.setattr(rest_api, "start_background", lambda: None)
    monkeypatch.setattr(st, "download_button", lambda label, data, *a, **kw: downloads.append(data))
    twins[1].name = "Beta only"
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    at.session_state["scan_results"] = twins
    at.session_state["refreshed_signal_ids"] = [twins[0].signal_key]
    at.switch_page("app_pages/ergebnisse.py").run()
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    downloads.clear()
    at.text_input(key="results_search").set_value("Beta only" if filtered else "").run()
    assert not at.exception
    table = at.dataframe[0].value
    export = pd.read_csv(io.BytesIO(downloads[-1]), sep=";", encoding="utf-8-sig", keep_default_na=False)
    assert list(table["Quelle"]) == list(export["Quelle"]) == (["beta"] if filtered else ["alpha", "beta"])
    assert list(table["ID"]) == list(export["ID"])
