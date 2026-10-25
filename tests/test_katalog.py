# -*- coding: utf-8 -*-
"""Vollkatalog der Clients (Nutzer 08.10.2026) — Sync, Resultate, Nachladen.

Herkunft: Die Seite „Alle Signale" soll ALLES zeigen, was die Clients
melden — der Workflow-Vorfilter (Mindestalter/-abo) bleibt beim Scan.
Diese Tests decken die Bausteine: DB-Schicht (katalog_signale),
Normalisierung, sync() mit Offline-Quelle, katalog_resultate() (Scan
gewinnt, Dedup, Artefakt-Bezug) und lade_signal_daten().
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog


# ------------------------------------------------------------ DB-Schicht
def test_katalog_upsert_many_insert_update_und_stale_loeschung():
    items_a = [
        {"signal_id": 1, "name": "A", "platform": "vantage", "url": "u1",
         "version": "vantage", "abonnenten": 10.0, "wochen": 4.0, "risiko": "5"},
        {"signal_id": 2, "name": "B", "platform": "vantage", "url": "u2",
         "version": "vantage", "abonnenten": 5.0, "wochen": 30.0, "risiko": None},
    ]
    gespeichert, geloescht = katalog_upsert_helfer("vant", items_a)
    assert (gespeichert, geloescht) == (2, 0)
    # Update (gleiche IDs, neuer Name) + Signal 2 fällt aus dem Katalog
    items_b = [{"signal_id": 1, "name": "A2", "platform": "vantage",
                "url": "u1", "version": "vantage", "abonnenten": 12.0,
                "wochen": 5.0, "risiko": "6"}]
    gespeichert, geloescht = katalog_upsert_helfer("vant", items_b)
    assert (gespeichert, geloescht) == (1, 1)
    zeilen = db.katalog_list()
    assert [z["signal_id"] for z in zeilen] == [1]
    assert zeilen[0]["name"] == "A2"
    assert zeilen[0]["abonnenten"] == 12.0
    # Andere Quelle unberührt — Stale-Löschung gilt nur je Quelle
    katalog_upsert_helfer("robo", [dict(items_a[0], signal_id=9)])
    assert {z["quelle"] for z in db.katalog_list()} == {"vant", "robo"}


def katalog_upsert_helfer(kuerzel, items):
    return db.katalog_upsert_many(kuerzel, items)


def test_katalog_sync_vermerken_und_status():
    db.katalog_sync_vermerken("vant", 104, None)
    db.katalog_sync_vermerken("robo", 0, "Verbindung fehlgeschlagen")
    status = db.katalog_sync_status()
    assert status["vant"]["anzahl"] == 104
    assert status["vant"]["fehler"] is None
    assert status["vant"]["gelaufen_am"]
    assert status["robo"]["anzahl"] == 0
    assert "Verbindung" in status["robo"]["fehler"]


def test_katalog_upsert_many_duplikate_und_grosser_stale_block(monkeypatch):
    """Duplikate im Payload sind harmlos; Stale-Löschung blockiert korrekt
    über mehrere DELETE-Blöcke (nur exakt berechnete Stale-IDs, andere
    Quellen unberührt)."""
    monkeypatch.setattr(db, "_KATALOG_STALE_CHUNK", 3)
    db.katalog_upsert_many("vant", [
        {"signal_id": i, "name": f"S{i}", "platform": "vantage", "url": "u",
         "version": "vantage", "abonnenten": float(i), "wochen": 1.0,
         "risiko": None} for i in range(10)])
    # Duplikate im selben Payload + 8 der 10 fallen danach raus
    gespeichert, geloescht = db.katalog_upsert_many("vant", [
        {"signal_id": 1, "name": "Bleibt", "platform": "vantage", "url": "u",
         "version": "vantage", "abonnenten": 1.0, "wochen": 2.0, "risiko": None},
        {"signal_id": 1, "name": "Bleibt (Duplikat)", "platform": "vantage",
         "url": "u", "version": "vantage", "abonnenten": 9.0,
         "wochen": 2.0, "risiko": None},
        {"signal_id": 2, "name": "Bleibt auch", "platform": "vantage",
         "url": "u", "version": "vantage", "abonnenten": 2.0,
         "wochen": 2.0, "risiko": None},
    ])
    assert (gespeichert, geloescht) == (2, 8)
    uebrig = [z["signal_id"] for z in db.katalog_list()]
    assert sorted(uebrig) == [1, 2]
    # Letzter Schreiber gewinnt beim Duplikat (ON CONFLICT DO UPDATE)
    eins = next(z for z in db.katalog_list() if z["signal_id"] == 1)
    assert eins["name"] == "Bleibt (Duplikat)"


def test_katalog_upsert_many_leerer_katalog_loescht_alles():
    db.katalog_upsert_many("robo", [
        {"signal_id": 5, "name": "X", "platform": "mt4", "url": "u",
         "version": "mql4", "abonnenten": 1.0, "wochen": 1.0, "risiko": None}])
    gespeichert, geloescht = db.katalog_upsert_many("robo", [])
    assert (gespeichert, geloescht) == (0, 1)
    assert not [z for z in db.katalog_list() if z["quelle"] == "robo"]


def test_normalisiere_stringzahlen_mit_deutschem_komma():
    zeilen = katalog._normalisiere([
        {"signalId": "11", "version": "vantage", "signalName": "Komma",
         "subscribers": "471", "weeks": "9,5", "risk": 7}])
    assert zeilen[0]["abonnenten"] == 471.0
    assert zeilen[0]["wochen"] == pytest.approx(9.5)
    assert zeilen[0]["risiko"] == "7"


# --------------------------------------------------------- Normalisierung
def test_normalisiere_mappt_und_laest_schrott_fallen():
    items = [
        {"signalId": "1286742", "version": "vantage", "signalName": "DINO Scalping",
         "subscribers": 471, "weeks": 17, "risk": "8", "url": "https://x/1"},
        {"signalId": "kein-nummer", "signalName": "kaputt"},
        {"signalId": 5, "version": "mql4", "signalName": None,
         "subscribers": "12", "weeks": None, "risk": None},
    ]
    zeilen = katalog._normalisiere(items)
    assert len(zeilen) == 2
    dino = zeilen[0]
    assert dino["signal_id"] == 1286742
    assert dino["platform"] == "vantage"
    assert dino["abonnenten"] == 471.0
    assert dino["wochen"] == 17.0
    assert dino["risiko"] == "8"
    ohne = zeilen[1]
    # Fehlende URL → MQL5-Fallback (kandidaten-Konvention), Name = ID
    assert ohne["url"].startswith("https://www.mql5.com/en/signals/5")
    assert ohne["name"] == "5"
    assert ohne["abonnenten"] == 12.0
    assert ohne["wochen"] is None


# ------------------------------------------------------------------- sync
def _fake_quelle(kuerzel: str, quelle_id: int) -> dict:
    return {"id": quelle_id, "kuerzel": kuerzel, "name": kuerzel,
            "base_url": f"http://localhost/{kuerzel}",
            "typ": "mql5-downloader-v1", "aktiv": 1,
            "angelegt_am": None, "letzte_pruefung": None}


def test_sync_holt_alle_quellen_und_vermerkt_lauf(monkeypatch):
    kataloge = {
        "vant": [{"signalId": "1286742", "version": "vantage",
                  "signalName": "DINO Scalping", "subscribers": 471,
                  "weeks": 17, "risk": "8"}],
        "robo": [{"signalId": "777", "version": "mql4",
                  "signalName": "CopyFX Sterne", "subscribers": 30,
                  "weeks": 40, "risk": "3"}],
    }
    monkeypatch.setattr(db, "list_quellen",
                        lambda nur_aktiv=False: [_fake_quelle("vant", 1),
                                                 _fake_quelle("robo", 2)])
    monkeypatch.setattr(ingest, "hole_katalog",
                        lambda quelle, *, min_subscribers=1: kataloge[quelle["kuerzel"]])
    summary = katalog.sync()
    assert summary["gesamt"] == 2
    assert summary["quellen"]["vant"]["anzahl"] == 1
    assert summary["quellen"]["robo"]["fehler"] is None
    zeilen = db.katalog_list()
    assert {z["signal_id"] for z in zeilen} == {1286742, 777}
    status = db.katalog_sync_status()
    assert status["vant"]["anzahl"] == 1


def test_sync_tolariert_offline_quelle(monkeypatch):
    monkeypatch.setattr(db, "list_quellen",
                        lambda nur_aktiv=False: [_fake_quelle("vant", 1),
                                                 _fake_quelle("robo", 2)])
    monkeypatch.setattr(ingest, "hole_katalog", lambda quelle, *, min_subscribers=1: (
        (_ for _ in ()).throw(downloader_client.DownloaderError("offline"))
        if quelle["kuerzel"] == "vant" else
        [{"signalId": "777", "version": "mql4", "signalName": "CopyFX",
          "subscribers": 30, "weeks": 40, "risk": "3"}]))
    summary = katalog.sync()
    # Offline-Quelle bricht den Lauf NICHT ab — robo wird trotzdem gezogen
    assert summary["quellen"]["vant"]["fehler"] == "offline"
    assert summary["quellen"]["robo"]["anzahl"] == 1
    assert db.katalog_sync_status()["vant"]["fehler"] == "offline"


def test_sync_toleriert_kaputte_json_antwort(monkeypatch):
    """Ein unerwarteter Fehler (z. B. ValueError aus malformed JSON) darf
    weder den Sync der anderen Quellen abbrechen noch zum Auto-Sync-Retry-
    Loop führen — er wird als Fehler notiert und der Lauf endet regulär."""
    monkeypatch.setattr(db, "list_quellen",
                        lambda nur_aktiv=False: [_fake_quelle("vant", 1),
                                                 _fake_quelle("robo", 2)])
    monkeypatch.setattr(ingest, "hole_katalog", lambda quelle, *, min_subscribers=1: (
        (_ for _ in ()).throw(ValueError("Expecting value: line 1 column 1"))
        if quelle["kuerzel"] == "vant" else
        [{"signalId": "777", "version": "mql4", "signalName": "CopyFX",
          "subscribers": 30, "weeks": 40, "risk": "3"}]))
    summary = katalog.sync()
    assert summary["quellen"]["vant"]["fehler"] is not None
    assert summary["quellen"]["robo"]["anzahl"] == 1
    # Sync wird als durchgeführt vermerkt (kein endloser Retry-Loop)
    assert db.katalog_sync_status()["vant"]["fehler"] is not None


def test_sync_nur_ein_kuerzel(monkeypatch):
    aufgerufen = []
    monkeypatch.setattr(db, "list_quellen",
                        lambda nur_aktiv=False: [_fake_quelle("vant", 1),
                                                 _fake_quelle("robo", 2)])
    monkeypatch.setattr(ingest, "hole_katalog", lambda quelle, *, min_subscribers=1: aufgerufen.append(
        quelle["kuerzel"]) or [])
    katalog.sync(kuerzel="robo")
    assert aufgerufen == ["robo"]


def test_sync_ruft_quellen_ensure(monkeypatch):
    """Parität mit kandidaten_aus_quellen: Legacy-Quellen werden übernommen,
    bevor der Katalog läuft (Frischinstallation ohne Admin-Einträge)."""
    aufgerufen = []
    monkeypatch.setattr(katalog.quellen, "_ensure", lambda: aufgerufen.append(1))
    monkeypatch.setattr(db, "list_quellen", lambda nur_aktiv=False: [])
    katalog.sync()
    assert aufgerufen == [1]


# -------------------------------------------------------- katalog_resultate
def _artefakt(quelle_id, signal_id, version, art, pfad: Path, inhalt: bytes):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(inhalt)
    db.store_quellen_artefakt(quelle_id, signal_id, version, art,
                              hashlib.sha256(inhalt).hexdigest(), str(pfad))


def test_katalog_resultate_scan_gewinnt_dedup_und_artefakte(tmp_path):
    vant_id = db.add_quelle("vant", "VantageMonitor", "http://localhost:8092")
    robo_id = db.add_quelle("robo", "RoboMonitor", "http://localhost:8091")
    # 42 ist in derselben Quelle gescannt → raus; 7 hat zwei Quellen;
    # 8 nur vant mit Cache; 9 ohne Cache
    db.upsert_signal(42, name="Gescannt", platform="vantage", quelle="vant")
    db.katalog_upsert_many("vant", [
        {"signal_id": 42, "name": "Gescannt", "platform": "vantage",
         "url": "u42", "version": "vantage", "abonnenten": 5.0,
         "wochen": 30.0, "risiko": None},
        {"signal_id": 7, "name": "DINO Scalping", "platform": "vantage",
         "url": "u7", "version": "vantage", "abonnenten": 471.0,
         "wochen": 17.0, "risiko": "8"},
        {"signal_id": 8, "name": "Mit Cache", "platform": "vantage",
         "url": "u8", "version": "vantage", "abonnenten": 100.0,
         "wochen": 40.0, "risiko": None},
        {"signal_id": 9, "name": "Ohne Cache", "platform": "vantage",
         "url": "u9", "version": "vantage", "abonnenten": 3.0,
         "wochen": 10.0, "risiko": None},
    ])
    db.katalog_upsert_many("robo", [
        {"signal_id": 7, "name": "DINO Spiegel", "platform": "mt4",
         "url": "r7", "version": "mql4", "abonnenten": 10.0,
         "wochen": 17.0, "risiko": "4"},
    ])
    _artefakt(vant_id, 8, "vantage", "trades",
              tmp_path / "q" / "vantage_8_trades.csv", b"Time;Type\n")
    _artefakt(vant_id, 8, "vantage", "metrics",
              tmp_path / "q" / "vantage_8_metrics.json",
              json.dumps({"metrics": {"EquityDrawdown": "9,10",
                                      "Average3MonthProfit": 3.5,
                                      "Broker": "VantageLT"},
                          "signalId": "8", "version": "vantage"},
                         ensure_ascii=False).encode("utf-8"))

    resultate, stats = katalog.katalog_resultate()
    ids = [r.id for r in resultate]
    # Nur dieselbe Quelle+ID ist dedupliziert; fremde ID-Kollision bleibt sichtbar.
    assert 42 not in ids
    assert ids.count(7) == 2
    dino = next(r for r in resultate if r.id == 7)
    assert dino.herkunft == "Katalog"
    assert dino.name == "DINO Scalping"          # vant-Zeile, nicht robo-Spiegel
    assert dino.quelle == "vant"
    assert dino.quelle_id == vant_id
    assert dino.quelle_version == "vantage"
    assert dino.trades_path == ""                # kein Cache → leer, Button folgt
    mit_cache = next(r for r in resultate if r.id == 8)
    assert Path(mit_cache.trades_path).exists()
    assert mit_cache.trades_sha256
    assert mit_cache.dd_equity_pct == pytest.approx(9.10)   # deutsches Komma
    assert mit_cache.ertrag_monat_pct == pytest.approx(3.5)
    assert mit_cache.broker_server == "VantageLT"
    assert stats[("vant", 8)]["dd_equity_pct"] == pytest.approx(9.10)


# ----------------------------------------------------------- metrics_stats
def _metrics_cache(tmp_path, quelle_id, signal_id, version, *, deposit=25000):
    _artefakt(quelle_id, signal_id, version, "metrics",
              tmp_path / f"{quelle_id}_{signal_id}_{version}_metrics.json",
              json.dumps({"signalId": str(signal_id), "version": version,
                          "metrics": {"InitialDeposit": deposit,
                                      "Currency": "USD",
                                      "Broker": "Provider-Live"}}).encode("utf-8"))


@pytest.mark.parametrize('initial,erwartet', [(None, 25000), (500, 500), (0, 0), (-5, -5)])
def test_workflow_bulk_basis_prioritaet_ohne_db_einzelabfragen(
        tmp_path, monkeypatch, initial, erwartet):
    qid = db.add_quelle('vant', 'Monitor', 'http://localhost:8092')
    db.katalog_upsert_many('vant', [dict(signal_id=41, version='vantage',
                                      platform='vantage', wochen=20, abonnenten=3)])
    _metrics_cache(tmp_path, qid, 41, 'vantage')
    pfad = tmp_path / 'trades.csv'
    _artefakt(qid, 41, 'vantage', 'trades', pfad, b'unchanged snapshot')
    artefakte = db.list_quellen_artefakte()
    res = katalog.pipeline.ScanResult(id=41, quelle='vant', platform='vantage',
        trades_path=str(pfad), trades_sha256=hashlib.sha256(pfad.read_bytes()).hexdigest())
    def verboten(*args, **kwargs):
        raise AssertionError('Bulk-Snapshots brauchen keine weitere DB-Abfrage')
    rows, quellen = db.katalog_list(), db.list_quellen()
    for name in ('katalog_list', 'list_quellen', 'list_quellen_artefakte',
                 'get_quellen_artefakt'):
        monkeypatch.setattr(db, name, verboten)
    alt = {('vant', 41): dict(initial_deposit_usd=initial, kapitalbasis_virtual_usd=10000)}
    neu = katalog.workflow_stats_bulk([res], alt, katalog_rows=rows,
                                     quellen_rows=quellen, artefakte=artefakte)
    assert neu[('vant', 41)]['initial_deposit_usd'] == erwartet
    assert neu[('vant', 41)]['broker_server'] == 'Provider-Live'
    assert alt[('vant', 41)]['initial_deposit_usd'] == initial
    assert res.wochen == 20 and res.abonnenten == 3


@pytest.mark.parametrize('stoerung', ['trade_sha', 'trade_bytes', 'metrics_bytes',
                                    'source', 'version', 'platform'])
def test_workflow_bulk_keine_fremden_oder_veraenderten_stats(tmp_path, stoerung):
    qid = db.add_quelle('vant', 'Monitor', 'http://localhost:8092')
    db.katalog_upsert_many('vant', [dict(signal_id=42, version='vantage', wochen=22)])
    _metrics_cache(tmp_path, qid, 42, 'vantage')
    pfad = tmp_path / 'trades.csv'
    _artefakt(qid, 42, 'vantage', 'trades', pfad, b'snapshot')
    artefakte = db.list_quellen_artefakte()
    res = katalog.pipeline.ScanResult(id=42, quelle='vant', platform='vantage',
        trades_path=str(pfad), trades_sha256=hashlib.sha256(pfad.read_bytes()).hexdigest())
    if stoerung == 'trade_sha':
        res.trades_sha256 = 'other'
    elif stoerung == 'trade_bytes':
        pfad.write_bytes(b'changed')
    elif stoerung == 'metrics_bytes':
        Path(artefakte[(qid, 42, 'vantage', 'metrics')]['path']).write_text('{}')
    elif stoerung == 'source':
        res.quelle_id = qid + 1
    elif stoerung == 'version':
        res.quelle_version = 'mql5'
    else:
        res.platform = 'mt5'
    alt = {('vant', 42): {'initial_deposit_usd': None}}
    assert katalog.workflow_stats_bulk([res], alt) == alt


@pytest.mark.parametrize('csv_flow,initial,basis,quelle', [
    (False, None, 10000, 'modell_fallback_10000'),
    (False, 500, 500, 'signalseite_initial_deposit'),
    (True, 500, 200, 'csv_einzahlungen'),
])
def test_workflow_frische_virtualbasis_respektiert_initial_und_csv(
        tmp_path, csv_flow, initial, basis, quelle):
    from mqlkiscanner import signal_statistik
    qid = db.add_quelle('vant', 'Monitor', 'http://localhost:8092')
    db.katalog_upsert_many('vant', [dict(signal_id=43, version='vantage')])
    metrics = {'signalId': 43, 'version': 'vantage',
               'metrics': {'InitialDepositVirtual': 10000}}
    _artefakt(qid, 43, 'vantage', 'metrics', tmp_path / 'metrics.json',
              json.dumps(metrics).encode())
    csv = 'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
    if csv_flow:
        csv += '2026.01.01 00:00:00;Balance;;;;;;;;;200\n'
    csv += '2026.01.05 10:00:00;Buy;0.1;EURUSD;1.1;0.1;2026.02.05 10:05:00;1.11;0;0;50\n'
    pfad = tmp_path / 'trades.csv'
    _artefakt(qid, 43, 'vantage', 'trades', pfad, csv.encode())
    res = katalog.pipeline.ScanResult(id=43, quelle='vant', platform='vantage',
        trades_path=str(pfad), trades_sha256=hashlib.sha256(pfad.read_bytes()).hexdigest())
    stats = katalog.workflow_stats_bulk([res], {('vant', 43): dict(initial_deposit_usd=initial)})
    result = signal_statistik.berechne(str(pfad), stats[('vant', 43)])
    assert result['kapitalbasis_usd'] == basis
    assert result['kapitalbasis_quelle'] == quelle
    assert result['kapitalbasis_modell'] is (quelle == 'modell_fallback_10000')
    assert result['ertrag_monat_geom_pct'] is not None
    # Ein Gewinn ohne Verlust liefert kein definiertes PF; kein Equity-DD
    # wurde gemessen, deshalb bleibt auch RetDD unbekannt.
    assert result['profit_faktor'] is None
    assert result['winrate_pct'] == 100 and result['trades'] == 1
    from mqlkiscanner.alle_signale_ui import tabellen_zeile
    assert tabellen_zeile(res, result, fix_ids=set())['RetDD/Monat'] is None


@pytest.mark.parametrize('deposit', [0, -1, float('nan'), float('inf')])
def test_workflow_bulk_unbrauchbare_neue_initialbasis_wird_nicht_echt(tmp_path, deposit):
    qid = db.add_quelle('vant', 'Monitor', 'http://localhost:8092')
    db.katalog_upsert_many('vant', [dict(signal_id=44, version='vantage')])
    _metrics_cache(tmp_path, qid, 44, 'vantage', deposit=deposit)
    pfad = tmp_path / 'trades.csv'
    _artefakt(qid, 44, 'vantage', 'trades', pfad, b'snapshot')
    res = katalog.pipeline.ScanResult(id=44, quelle='vant', platform='vantage',
        trades_path=str(pfad), trades_sha256=hashlib.sha256(pfad.read_bytes()).hexdigest())
    stats = katalog.workflow_stats_bulk([res], {('vant', 44): {'initial_deposit_usd': None}})
    assert stats[('vant', 44)]['initial_deposit_usd'] is None


@pytest.mark.parametrize("signal_id,kuerzel,version,platform", [
    (941001, "vant", "vantage", "vantage"),
    (941002, "robo", "mql4", "mt4"),
    (941009, "mql5", "mql4", "MT4"),  # Direktworkflow schreibt Grossbuchstaben.
])
def test_metrics_stats_workflow_ohne_quelle_id_nutzt_echte_basis(
        tmp_path, signal_id, kuerzel, version, platform):
    quelle_id = db.add_quelle(kuerzel, "Monitor", "http://localhost:8092")
    db.katalog_upsert_many(kuerzel, [
        {"signal_id": signal_id, "version": version, "platform": platform}])
    _metrics_cache(tmp_path, quelle_id, signal_id, version)
    result = katalog.pipeline.ScanResult(
        id=signal_id, quelle=kuerzel, platform=platform, quelle_id=None)

    stats = katalog.metrics_stats(result)

    assert stats["initial_deposit_usd"] == 25000
    assert stats["kapitalbasis_virtual_usd"] is None
    assert stats["broker_server"] == "Provider-Live"
    assert result.quelle_id is None  # Lesen veraendert die Workflow-Zeile nicht.


def test_metrics_stats_workflow_nimmt_keine_fremde_quelle(tmp_path):
    db.add_quelle("vant", "Vantage", "http://localhost:8092")
    andere_id = db.add_quelle("anderer", "Anderer Monitor", "http://localhost:8093")
    db.katalog_upsert_many("vant", [{"signal_id": 941003, "version": "vantage"}])
    db.katalog_upsert_many("anderer", [{"signal_id": 941003, "version": "vantage"}])
    _metrics_cache(tmp_path, andere_id, 941003, "vantage", deposit=99999)
    result = katalog.pipeline.ScanResult(id=941003, quelle="vant", platform="vantage")

    assert katalog.metrics_stats(result) == {}


@pytest.mark.parametrize("cache_version,result_version,platform", [
    ("mql5", "", "mt4"),       # Nur die andere Cache-Version vorhanden.
    ("mql4", "mql5", "mt4"),  # Explizite Workflow-Version widerspricht Katalog.
    ("mql4", "", "mt5"),      # Workflow-Plattform widerspricht Katalog-Version.
])
def test_metrics_stats_workflow_nimmt_keine_andere_version(
        tmp_path, cache_version, result_version, platform):
    quelle_id = db.add_quelle("robo", "Robo", "http://localhost:8091")
    db.katalog_upsert_many("robo", [{"signal_id": 941004, "version": "mql4"}])
    _metrics_cache(tmp_path, quelle_id, 941004, cache_version)
    result = katalog.pipeline.ScanResult(
        id=941004, quelle="robo", platform=platform, quelle_version=result_version)

    assert katalog.metrics_stats(result) == {}


def test_metrics_stats_workflow_ohne_passende_katalogreferenz_bleibt_leer(tmp_path):
    quelle_id = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    _metrics_cache(tmp_path, quelle_id, 941005, "vantage")
    result = katalog.pipeline.ScanResult(id=941005, quelle="vant", platform="vantage")

    assert katalog.metrics_stats(result) == {}


def test_metrics_stats_mit_referenz_braucht_keine_kataloginventur(tmp_path, monkeypatch):
    quelle_id = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    _metrics_cache(tmp_path, quelle_id, 941006, "vantage")
    result = katalog.pipeline.ScanResult(
        id=941006, quelle="vant", platform="vantage",
        quelle_id=quelle_id, quelle_version="vantage")

    def _unerwartete_inventur(*args, **kwargs):
        raise AssertionError("Bekannte Referenz braucht keine Kataloginventur")

    monkeypatch.setattr(db, "katalog_list", _unerwartete_inventur)
    monkeypatch.setattr(db, "list_quellen", _unerwartete_inventur)
    assert katalog.metrics_stats(result)["initial_deposit_usd"] == 25000


@pytest.mark.parametrize("stoerung", ["inhalt_geaendert", "sha_fehlt"])
def test_metrics_stats_verwendet_nur_sha_geprueften_cache(tmp_path, stoerung):
    quelle_id = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    _metrics_cache(tmp_path, quelle_id, 941007, "vantage")
    artefakt = db.get_quellen_artefakt(quelle_id, 941007, "vantage", "metrics")
    if stoerung == "inhalt_geaendert":
        # Weiterhin gueltiges JSON, aber nicht der registrierte Inhalt.
        pfad = Path(artefakt["path"])
        pfad.write_bytes(pfad.read_bytes().replace(b"25000", b"99000"))
    else:
        db.store_quellen_artefakt(quelle_id, 941007, "vantage", "metrics",
                                  "", artefakt["path"])
    result = katalog.pipeline.ScanResult(
        id=941007, quelle="vant", platform="vantage",
        quelle_id=quelle_id, quelle_version="vantage")

    assert katalog.metrics_stats(result) == {}


@pytest.mark.parametrize("falsches_feld,wert", [
    ("signalId", "941999"), ("version", "mql5"),
])
def test_metrics_stats_verweigert_widersprechende_payload_identitaet(
        tmp_path, falsches_feld, wert):
    quelle_id = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    antwort = {"signalId": "941008", "version": "vantage",
               "metrics": {"InitialDeposit": 25000}}
    antwort[falsches_feld] = wert
    _artefakt(quelle_id, 941008, "vantage", "metrics",
              tmp_path / "falsch.json", json.dumps(antwort).encode("utf-8"))
    result = katalog.pipeline.ScanResult(
        id=941008, quelle="vant", platform="vantage",
        quelle_id=quelle_id, quelle_version="vantage")

    assert katalog.metrics_stats(result) == {}


# ------------------------------------------------------- lade_signal_daten
def test_lade_signal_daten_holt_trades_und_toleriert_metrics_ausfall(monkeypatch):
    quelle_id = db.add_quelle("vant", "VantageMonitor", "http://localhost:8092")
    result = katalog.pipeline.ScanResult(id=99, quelle="vant",
                                         quelle_id=quelle_id,
                                         quelle_version="vantage")
    aufrufe = []
    monkeypatch.setattr(db, "get_quelle", lambda qid: _fake_quelle("vant", qid))

    def _metrics_fail(quelle, signal_id, version):
        aufrufe.append("metrics")
        raise downloader_client.DownloaderError("keine Kennzahlen")

    monkeypatch.setattr(ingest, "hole_metrics", _metrics_fail)
    monkeypatch.setattr(ingest, "hole_trades",
                        lambda quelle, sid, ver: aufrufe.append(
                            ("trades", sid, ver)) or (r"C:\tmp\t.csv", True))
    pfad, geaendert = katalog.lade_signal_daten(result)
    assert pfad == r"C:\tmp\t.csv"
    assert geaendert is True
    # Metrics-Fehler geschluckt, Trades trotzdem geladen
    assert aufrufe[0] == "metrics"
    assert aufrufe[1] == ("trades", 99, "vantage")


def test_lade_signal_daten_ohne_quelle_wirft_klar(monkeypatch):
    result = katalog.pipeline.ScanResult(id=99, quelle="weg",
                                         quelle_id=404,
                                         quelle_version="vantage")
    monkeypatch.setattr(db, "get_quelle", lambda qid: None)
    with pytest.raises(downloader_client.DownloaderError):
        katalog.lade_signal_daten(result)
