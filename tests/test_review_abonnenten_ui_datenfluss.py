"""Refresh- und Kapitalbelege müssen bis zur gerenderten Seite erhalten bleiben."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_statistik as abo
from mqlkiscanner import db, katalog, pipeline, quellen, scan_worker, signal_statistik


ROOT = Path(__file__).resolve().parents[1]


def test_refresh_behaelt_quellenkontext_bis_zum_ui_balken(monkeypatch):
    """Echter Zwei-Quellen-Sync meldet Katalog und Historie im selben UI-Stand."""
    for name in ("pelik", "zulu"):
        db.add_quelle(name, name, "http://fixture.invalid")
    monkeypatch.setattr(quellen, "_ensure", lambda: None)
    snapshots = {}

    class NativeClient:
        def __init__(self, source):
            self.source = source

        def katalog(self, *, limit, offset, min_subscribers, catalog_scope):
            snapshots[(self.source, "katalog")] = abo.refresh_zustand()
            version = {"pelik": "pelican", "zulu": "zulu"}[self.source]
            items = [dict(signalId=str(i), signalName=str(i), version=version,
                          subscribers=1) for i in range(1, 27)]
            return dict(items=items[offset:offset + limit], total=len(items),
                        offset=offset, catalogScope="full")

        def history(self, signal_id, version):
            if signal_id == 26:
                snapshots[(self.source, "historie")] = abo.refresh_zustand()
            return []

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(quellen, "client_fuer_quelle",
                        lambda source, **kwargs: NativeClient(source["kuerzel"]))
    monkeypatch.setattr(abo, "threading", SimpleNamespace(Thread=InlineThread))
    assert abo.starte_refresh(messen=False)
    finished = abo.refresh_zustand()
    assert finished["fehler"] == ""
    assert finished["summary"]["gesamt"] == 52
    history = snapshots[("pelik", "historie")]
    assert history["lesen"]["nr"] == 1
    assert history["lesen"]["von"] == 2
    assert history["lesen"]["fertig"] == 25
    next_catalog = snapshots[("zulu", "katalog")]
    assert "fertig" not in next_catalog["lesen"]
    assert "gesamt" not in next_catalog["lesen"]

    page = ROOT / "app_pages" / "abonnenten_statistik.py"
    for state, text, percent in (
        (history, "Quelle 1/2 — pelik: Historie 25/26 Anbieter", 48),
        (next_catalog, "Quelle 2/2 — zulu: Katalog laden", 50),
    ):
        monkeypatch.setattr(abo, "refresh_zustand", lambda state=state: state)
        at = AppTest.from_file(str(page), default_timeout=30).run()
        assert not at.exception, at.exception
        progress = next(element for element in at.get("progress")
                        if text in element.proto.text)
        assert progress.proto.value == percent


@pytest.mark.parametrize("active_workflow", [True, False])
def test_frischmess_button_prueft_aktiven_worker_statt_gemerkter_studie(monkeypatch, active_workflow):
    db.upsert_signal(31, name="Probe", platform="vantage", quelle="vant")
    monkeypatch.setattr(db, "katalog_sync_status", lambda: {
        "vant": {"gelaufen_am": "2026-10-25", "anzahl": 1, "fehler": None}})
    monkeypatch.setattr(katalog, "katalog_resultate", lambda **kwargs: ([], {}))
    monkeypatch.setattr(abo, "refresh_laeuft", lambda: False)
    active = SimpleNamespace(workflow={"typ": "workflow"}) if active_workflow else None
    monkeypatch.setattr(scan_worker, "active_run", lambda: active)
    page = ROOT / "app_pages" / "alle_signale.py"
    at = AppTest.from_file(str(page), default_timeout=30)
    if not active_workflow:
        at.session_state["_alle_signale_studien_run"] = SimpleNamespace(
            workflow={"typ": "studien_batch"}, thread=None,
            control={"fertig": True, "gerechnet": 1, "gesamt": 1,
                     "aktuell": 1, "summary": "beendet", "fehler": []})
    at.run()
    assert not at.exception, at.exception
    assert at.button(key="alle_signale_abo_messen").disabled is active_workflow


def test_kapitalherkunft_bleibt_in_gerenderter_tabelle_und_export(monkeypatch, tmp_path):
    path = tmp_path / "trades.csv"
    path.write_text("lokaler Trade-Snapshot", encoding="utf-8")
    details = {"quelle": "modell_fallback_10000", "modell": True,
               "unsicherheit": "Modellannahme; kein Nachweis der realen Kontogroesse"}
    probe = pipeline.ScanResult(
        id=42, name="Modellprofil", platform="pelican", quelle="pelik", account_currency="USD",
        trades_path=str(path), trades_sha256=db.file_sha256(path),
        true_dd_basis_virtuell=True, true_dd_kapitalbasis_details=details,
        true_dd_kapitalbasis_quelle="modell_fallback_10000")
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kwargs: [probe])
    monkeypatch.setattr(db, "list_catalog", lambda: [{
        "signal_id": 42, "quelle": "pelik", "stats": {}}])
    monkeypatch.setattr(db, "katalog_sync_status", lambda: {
        "pelik": {"gelaufen_am": "2026-10-25", "anzahl": 1, "fehler": None}})
    monkeypatch.setattr(katalog, "katalog_resultate", lambda **kwargs: ([], {}))
    monkeypatch.setattr(scan_worker, "active_run", lambda: None)
    monkeypatch.setattr(signal_statistik, "berechne", lambda *args, **kwargs: {
        "kapitalbasis_ok": True, "kapitalbasis_usd": 10000,
        "kapitalbasis_quelle": "modell_fallback_10000", "kapitalbasis_details": details})
    exports = {}
    original = st.download_button

    def capture_download(label, data, file_name, *args, **kwargs):
        exports[file_name] = data
        return original(label, data, file_name, *args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture_download)
    page = ROOT / "app_pages" / "alle_signale.py"
    at = AppTest.from_file(str(page), default_timeout=30).run()
    assert not at.exception, at.exception
    table = at.dataframe[0].value
    exported = pd.read_csv(BytesIO(exports["alle-signale.csv"]), sep=";")
    for frame in (table, exported):
        row = frame.iloc[0]
        assert row["Basis"] == "10k-Modell"
        assert "Modellannahme 10.000 USD" in row["Kapitalherkunft"]
        assert row["Kapitalunsicherheit"] == details["unsicherheit"]
        assert "Modellannahme 10.000 USD" in row["Studienbasis"]
        assert "Modellstudie" in row["Messstatus"]
