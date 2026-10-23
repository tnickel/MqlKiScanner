# -*- coding: utf-8 -*-
"""Audit regressions updated for explicit source identity, 18.10.2026.

Different sources may coexist under equal external IDs; same-owner platform
conflicts and unattributed writes still fail closed. Old failure snapshots stay
stale after a failed scan. No real network is used.
"""
from __future__ import annotations

import json

import pytest

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.signal_identity import key_for
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.mql5 import signal_stats


def _log_sammel():
    lines: list[str] = []
    return lines, lines.append


# ---------------------------------------------------------------- (a) F3 --
def test_a_upsignal_equal_external_ids_of_different_sources_coexist():
    db.upsert_signal(12345,name='MQL5 Original',platform='MT5',quelle='mql5')
    db.upsert_signal(12345,name='Pelik Independent',platform='MT5',quelle='pelik')
    assert db.get_signal(12345,quelle='mql5')['name']=='MQL5 Original'
    assert db.get_signal(12345,quelle='pelik')['name']=='Pelik Independent'
    with pytest.raises(db.AmbiguousSignalIdentity): db.get_signal(12345)


def test_a2_failed_foreign_scan_preserves_original_owner(monkeypatch):
    """An offline foreign provider persists its own error, never the MQL owner."""
    from mqlkiscanner import downloader_client, ingest
    db.init_db()
    db.upsert_signal(12345, name="MQL5 Original", platform="MT5", quelle="mql5")
    pelik_id = db.add_quelle("pelik", "PelicanMonitor", "http://localhost:1")
    monkeypatch.setattr(ingest, "hole_metrics", lambda *a, **kw: {
        "metrics": {"Currency": "USD", "EquityDrawdown": 12, "InitialDeposit": 1000},
        "version": "pelican"})
    monkeypatch.setattr(ingest, "hole_trades",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            downloader_client.DownloaderConnectionError("offline")))
    lines, log = _log_sammel()
    res = pipeline.ScanPipeline({})._analyze_candidate_once(None, {
        "id": 12345, "platform": "pelican", "name": "Pelik Konflikt",
        "quelle_kuerzel": "pelik", "quelle_id": pelik_id,
        "quelle_version": "pelican"}, log)
    assert "DownloaderConnectionError: offline" in res.fehler
    assert res.persisted_this_run
    assert db.get_signal(12345,quelle="pelik") is not None
    zeile = db.get_signal(12345,quelle="mql5")
    assert zeile["name"] == "MQL5 Original" and zeile["quelle"] == "mql5"


def test_a3_plattformwechsel_mt4_mt5_wird_vor_abruf_abgewehrt(monkeypatch):
    db.init_db()
    db.upsert_signal(12345, name="Als MT5 dokumentiert", platform="MT5", quelle="mql5")
    stats = pytest.importorskip("unittest.mock").Mock(
        side_effect=AssertionError("kein Abruf nach Kollision"))
    monkeypatch.setattr(signal_stats, "fetch_signal_stats", stats)
    lines, log = _log_sammel()
    res = pipeline.ScanPipeline({})._analyze_candidate_once(
        None, {"id": 12345, "platform": "MT4"}, log)
    assert "ID-Kollision" in res.fehler and not res.persisted_this_run
    stats.assert_not_called()
    assert db.get_signal(12345)["platform"] == "MT5"


# ------------------------------------------------------- (b) Mischmodus --
def test_b_beides_gleiche_plattform_keeps_different_sources(monkeypatch):
    from mqlkiscanner import ingest
    from mqlkiscanner.mql5 import crawler
    monkeypatch.setattr(pipeline, "Mql5Session", lambda settings: object())
    monkeypatch.setattr(crawler, "crawl_lists", lambda *a, **kw: [
        {"id": 12345, "platform": "MT5", "wochen": 52, "abonnenten": 10,
         "name": "Direkt"}])
    monkeypatch.setattr(ingest, "kandidaten_aus_quellen", lambda log=None: [
        {"id": 12345, "platform": "mt5", "wochen": 52, "abonnenten": 9,
         "name": "Spiegel", "quelle_kuerzel": "pelik", "quelle_id": 1,
         "quelle_version": "pelican"}])
    lines, log = _log_sammel()
    signals = pipeline.ScanPipeline({"listen_modus": "beides"}).crawl(
        lambda *a: None, log)
    assert len(signals) == 2
    assert {key_for(k) for k in signals} == {("mql5",12345),("pelik",12345)}


def test_b2_beides_plattformkonflikt_wirft_beide_raus(monkeypatch):
    from mqlkiscanner import ingest
    from mqlkiscanner.mql5 import crawler
    monkeypatch.setattr(pipeline, "Mql5Session", lambda settings: object())
    monkeypatch.setattr(crawler, "crawl_lists", lambda *a, **kw: [
        {"id": 12345, "platform": "MT4", "wochen": 52, "abonnenten": 10}])
    monkeypatch.setattr(ingest, "kandidaten_aus_quellen", lambda log=None: [
        {"id": 12345, "platform": "mt5", "wochen": 52, "abonnenten": 9,
         "quelle_kuerzel": "mql5", "quelle_id": 1, "quelle_version": "pelican"}])
    p = pipeline.ScanPipeline({"listen_modus": "beides"})
    lines, log = _log_sammel()
    signals = p.crawl(lambda *a: None, log)   # Same source and external ID, conflicting platform claims.
    gruende: list[dict] = []
    kandidaten = p.build_candidates(signals, log, gruende)
    assert kandidaten == []                    # keine eindeutige Identität
    assert any("ID-Kollision" in g["grund"] for g in gruende)


def test_b3_quellen_mischung_keeps_source_keys():
    from mqlkiscanner import ingest
    items = [{"signalId": 12345, "version": "mql5", "signalName": "S",
              "subscribers": 5}]
    quelle = {"id": 1, "kuerzel": "mql5"}
    erste = ingest.kandidaten(quelle, items)
    zweite = ingest.kandidaten({"id": 2, "kuerzel": "pelik"}, items)
    gesehen: set = set()
    out = []
    for k in [erste[0], zweite[0]]:  # dieselbe MQL5-ID in zwei Spiegeln
        key = key_for(k)
        if key not in gesehen:
            gesehen.add(key)
            out.append(k)
    assert len(out) == 2 and {k["quelle_kuerzel"] for k in out} == {"mql5","pelik"}


# ------------------------------------------------------ (c) MDL-1-Kette --
def _gruenen_befund_speichern(signal_id: int) -> None:
    forensik = {
        "version": FORENSICS_VERSION, "vollstaendig": True,
        "trades_sha256": "abc123",
        "trading_dd": {"pct": 4.0, "usd": 400.0}, "winrate_pct": 70.0,
        "trades_anzahl": 120, "duplikate_entfernt": 0,
        "identische_tradezeilen": 0, "plattform_trades": 120,
        "ertrag_monat_geom_pct": 2.0, "cagr_jahr_pct": 24.0,
        "retdd_monat": 0.4, "retdd_jahr": 4.8, "effizienz_befund": {},
        "max_verlustserie": 4, "verlustserie_usd": -80.0,
        "peak_exposure": {"positionen": 3, "netto_lots": 1.5,
                          "schock_usd": 900.0, "shock_pct_max": 9.0,
                          "shock_pct_peak_time": None,
                          "shock_pct_peak_account": None,
                          "shock_pct_peak_usd": None},
        "martingale_flag": False, "martingale_evidenz": [],
        "stop_nachweis": "", "stop_evidence": None, "stop_befund": None,
        "symbole": "EURUSD",
        "kapitalbasis": {"usd": 10000.0, "quelle": "signalseite",
                         "end_balance_real": 12400.0, "webseite_balance_usd": 12400.0},
        "equity_rekonstruktion": {"verlaesslich": True, "status": "ok",
                                  "equity_dd_pct": 5.0, "equity_dd_pct_raw": 5.0,
                                  "equity_dd_usd": 500.0, "abdeckung_pct": 99.0,
                                  "gmt_offset_h": 0},
        "fx_kursquelle": None, "score": 6.0, "kriterien_matrix": {},
        "ampel": "🟢",
    }
    stats = {
        "eq_dd_pct": 6.0, "bal_dd_pct": None, "ertrag_monat_pct": 1.8,
        "pf": 1.9, "forensik_ok": True, "forensik_version": FORENSICS_VERSION,
        "account_currency": "USD",
        "account_currency_evidence_version": FORENSICS_VERSION,
        "initial_deposit_usd": 10000.0, "balance_usd": 12400.0,
        "broker_server": "TestServer-MT5", "monitor_trade_eq_dd_pct": None,
        "last_fehler": None,
    }
    db.store_scan_result(signal_id, {
        "name": "Ehemals Gruen", "platform": "MT5",
        "url": "https://example/s", "autor": "A", "abo_preis": 30.0,
        "abonnenten": 12.0, "wochen": 60.0, "stats": stats,
        "quelle": "mql5"}, forensik=forensik)


def test_c_fehlgeschlagener_neu_lauf_verdeckt_alten_gruenen_befund_nicht(
        monkeypatch):
    """MDL-1-Regression: neuer Fehlerlauf ⇒ alter 🟢-Befund ist veraltet/⚪."""
    from unittest.mock import Mock
    db.init_db()
    _gruenen_befund_speichern(23456)
    alt = pipeline.results_from_db(materialize_pdfs=False)
    assert [r for r in alt if r.id == 23456][0].ampel == "🟢"

    monkeypatch.setattr(signal_stats, "fetch_signal_stats",
                        Mock(side_effect=TimeoutError("Session abgelaufen")))
    lines, log = _log_sammel()
    res = pipeline.ScanPipeline({})._analyze_candidate_once(
        None, {"id": 23456, "platform": "MT5", "name": "Ehemals Gruen"}, log)
    assert res.fehler and res.ampel == "⚪"
    gespeichert = json.loads(db.get_signal(23456)["stats_json"])
    assert gespeichert["forensik_ok"] is False
    assert gespeichert["last_fehler"]

    geladen = [r for r in pipeline.results_from_db(materialize_pdfs=False)
               if r.id == 23456][0]
    assert geladen.forensik_stale is True
    assert geladen.ampel == "⚪"
    assert "Forensik veraltet" in geladen.urteil and geladen.fehler


# ------------------------------------------------- (d) LÜCKE — erwartet ROT --
def test_d_luecke_store_scan_result_ohne_quelle_ueberschreibt_fremde_id():
    """Regressionsschutz für die am 18.10. geschlossene Lücke (Audit-Fund).

    db.store_scan_result verlangt seit der Nacharbeit für ein BESTEHENDES
    Signal eine explizite nichtleere `quelle` (ValueError sonst) und öffnet
    die Transaktion mit BEGIN IMMEDIATE — ein Update ohne Quellenangabe
    kann dokumentierte Bestandsinhalte nicht mehr still überschreiben.
    Das Audit hatte die Lücke ursprünglich als ROT dokumentiert
    (upsert_signal prüfte nur im Zweig `quelle is not None`).
    """
    db.init_db()
    db.upsert_signal(777, name="MQL5 Dokumentiert", platform="MT5", quelle="mql5")
    with pytest.raises(ValueError, match="ID-Kollision abgewehrt"):
        db.store_scan_result(777, {          # ohne Schlüssel "quelle"
            "name": "Pelik Inhalt", "platform": "MT5", "stats": {}},
            forensik=None)
