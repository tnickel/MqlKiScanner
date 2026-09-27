# -*- coding: utf-8 -*-
"""Datenquellen-Registry + Ingest + Multi-Source-Sync (Konzept doc/20, Stufe 1).

Alles gegen Fakes: die autouse-Fixture (conftest) sperrt echte Netz-Aufrufe,
diese Tests verdrahten quellen.client_fuer_quelle auf FakeClients.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mqlkiscanner import (config, db, downloader_client, downloader_sync, ingest,
                          pipeline, quellen, secrets_store)


# ------------------------------------------------------------------ Fakes
class FakeClient:
    def __init__(self, *, health=None, katalog=None, trades=b"", metrics=None,
                 history=None, fehler=None):
        self._health = health if health is not None else {
            "status": "ok", "apiVersion": "v1", "providers": 7}
        self._katalog = list(katalog or [])
        self._trades = trades
        self._metrics = metrics or {}
        self._history = list(history or [])
        self.fehler = fehler
        self.trades_aufrufe = 0
        self.history_aufrufe = 0

    def health(self):
        if self.fehler:
            raise self.fehler
        return dict(self._health)

    def katalog(self, *, version=None, limit=500, offset=0):
        if self.fehler:
            raise self.fehler
        block = self._katalog[offset:offset + limit]
        return {"total": len(self._katalog), "count": len(block),
                "offset": offset, "items": block}

    def trades_csv(self, signal_id, version):
        if self.fehler:
            raise self.fehler
        self.trades_aufrufe += 1
        return self._trades

    def metrics(self, signal_id, version):
        if self.fehler:
            raise self.fehler
        return dict(self._metrics)

    def history(self, signal_id, version):
        if self.fehler:
            raise self.fehler
        self.history_aufrufe += 1
        return list(self._history)

    def reports(self, signal_id, version):
        return []

    def download_report(self, signal_id, version, name):
        raise AssertionError("in diesen Tests nicht benötigt")


MINI_CSV = (
    "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
    "2026.09.01 22:39:54;Sell;0.01;XAUUSD;4324.98;0.01;2026.09.02 04:13:01;4319.66;-0.18;;5.32\n"
    "2026.09.01 16:12:05;Sell;0.01;XAUUSD;4326.38;0.01;2026.09.01 16:31:23;4349.51;-0.18;;-23.13\n"
    "2026.09.02 08:00:00;Buy;0.01;XAUUSD;4330.00;0.01;2026.09.02 09:00:00;4340.00;-0.18;;9.82\n"
    "2026.09.02 10:00:00;Buy;0.01;XAUUSD;4340.00;0.01;2026.09.02 11:00:00;4335.00;-0.18;;-4.18\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def _caches_leeren():
    quellen._letzte_pruefung_cache.clear()
    downloader_sync._STATUS_CACHE.clear()
    yield


def _verdrahte(monkeypatch, clients: dict[str, FakeClient]):
    """base_url -> FakeClient; unbekannte Quellen bekommen einen OK-Client."""
    def fabrik(quelle, timeout=None):
        return clients.get(quelle["base_url"], FakeClient())
    monkeypatch.setattr(quellen, "client_fuer_quelle", fabrik)


def _quelle(kuerzel="mql5", base="http://localhost:8089", aktiv=True) -> dict:
    db.init_db()
    qid = db.add_quelle(kuerzel, kuerzel, base, aktiv=aktiv)
    return db.get_quelle(qid)


# ------------------------------------------------------------------ Registry
def test_crud_und_kuerzel_eindeutig():
    qid = db.add_quelle("mql5", "Lokal", "http://a:8089")
    assert [q["kuerzel"] for q in db.list_quellen()] == ["mql5"]
    assert db.get_quelle(qid)["base_url"] == "http://a:8089"
    db.update_quelle(qid, aktiv=False, name="Anderer Name")
    eintrag = db.get_quelle(qid)
    assert eintrag["aktiv"] is False and eintrag["name"] == "Anderer Name"
    assert db.list_quellen(nur_aktiv=True) == []
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.add_quelle("mql5", "Duplikat", "http://b:8089")
    db.delete_quelle(qid)
    assert db.get_quelle(qid) is None


def test_migration_uebernimmt_legacy_einstellung():
    config.save_settings({"downloader_base_url": "http://legacy:8089/api/v1"})
    secrets_store.save_secrets(downloader_token="geheim")
    quellen._ensure()
    quellen_liste = db.list_quellen()
    assert len(quellen_liste) == 1
    assert quellen_liste[0]["kuerzel"] == "mql5"
    assert quellen_liste[0]["base_url"] == "http://legacy:8089/api/v1"
    assert secrets_store.get_secret(quellen.token_schluessel(quellen_liste[0]["id"])) == "geheim"
    quellen._ensure()  # idempotent
    assert len(db.list_quellen()) == 1


def test_migration_ohne_legacy_legt_nichts_an():
    quellen._ensure()
    assert db.list_quellen() == []


# ------------------------------------------------------------------ Prüfung
def test_pruefe_gruen_bei_ok(monkeypatch):
    quelle = _quelle()
    _verdrahte(monkeypatch, {"http://localhost:8089": FakeClient(
        health={"status": "ok", "apiVersion": "v1", "providers": 7,
                "instance": "DESKTOP-NS1MQSV"})})
    pruefung = quellen.pruefe(quelle, force=True)
    assert pruefung["status"] == "ok" and pruefung["farbe"] == "green"
    assert pruefung["details"]["anbieter"] == 7
    assert pruefung["details"]["kennung"] == "DESKTOP-NS1MQSV"
    assert quellen.status_zeichen(pruefung) == "🟢"
    # letzter Test hängt an der Quelle (Anzeige ohne neuen Aufruf)
    gespeichert = db.get_quelle(quelle["id"])["letzte_pruefung"]
    assert gespeichert["status"] == "ok"


def test_kennung_konflikt_erkennt_doppelte_instanz(monkeypatch):
    _quelle("mql5", "http://a:8089")
    _quelle("spiegel", "http://b:8089")
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(health={"status": "ok", "instance": "GLEICH"}),
        "http://b:8089": FakeClient(health={"status": "ok", "instance": "GLEICH"}),
    })
    for q in db.list_quellen(nur_aktiv=True):
        quellen.pruefe(q, force=True)
    assert quellen.kennung_konflikte() == {"GLEICH": ["mql5", "spiegel"]}
    # Verschiedene Kennungen (zwei echte Downloader) sind kein Konflikt …
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(health={"status": "ok", "instance": "EINS"}),
        "http://b:8089": FakeClient(health={"status": "ok", "instance": "ZWEI"}),
    })
    for q in db.list_quellen(nur_aktiv=True):
        quellen.pruefe(q, force=True)
    assert quellen.kennung_konflikte() == {}
    # … dieselbe Kennung unter zwei Quellen schon — deaktiviert fällt raus.
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(health={"status": "ok", "instance": "GLEICH"}),
        "http://b:8089": FakeClient(health={"status": "ok", "instance": "GLEICH"}),
    })
    for q in db.list_quellen(nur_aktiv=True):
        quellen.pruefe(q, force=True)
    assert quellen.kennung_konflikte() == {"GLEICH": ["mql5", "spiegel"]}
    db.update_quelle(db.list_quellen()[1]["id"], aktiv=False)
    assert quellen.kennung_konflikte() == {}


def test_pruefe_orange_wenn_token_fehlt(monkeypatch):
    quelle = _quelle()
    _verdrahte(monkeypatch, {"http://localhost:8089": FakeClient(
        health={"status": "ok", "tokenRequired": True})})
    pruefung = quellen.pruefe(quelle, force=True)
    assert pruefung["status"] == "eingeschraenkt" and pruefung["farbe"] == "orange"
    assert quellen.status_zeichen(pruefung) == "🟡"


def test_pruefe_rot_und_cache(monkeypatch):
    quelle = _quelle()
    client = FakeClient(fehler=downloader_client.DownloaderConnectionError("down"))
    _verdrahte(monkeypatch, {"http://localhost:8089": client})
    pruefung = quellen.pruefe(quelle, force=True)
    assert pruefung["status"] == "fehler" and pruefung["farbe"] == "red"
    assert quellen.status_zeichen(pruefung) == "🔴"
    assert quellen.pruefe(quelle) is quellen.pruefe(quelle)  # TTL-Cache, kein Aufruf


def test_verbindungs_status_aggregiert(monkeypatch):
    _verdrahte(monkeypatch, {})
    assert downloader_sync.verbindungs_status(force=True)["konfiguriert"] is False
    _quelle("mql5", "http://ok:8089")
    _quelle("pelik", "http://down:8089")
    _verdrahte(monkeypatch, {
        "http://ok:8089": FakeClient(),
        "http://down:8089": FakeClient(fehler=downloader_client.DownloaderConnectionError("x")),
    })
    status = downloader_sync.verbindungs_status(force=True)
    assert status["konfiguriert"] and status["ok"] is True
    assert "1/2 Quellen erreichbar" in status["detail"]


# ------------------------------------------------------------------ Ingest
def test_kandidaten_format_und_dedup(monkeypatch):
    _quelle("mql5", "http://a:8089")
    _quelle("spiegel", "http://b:8089")
    item = {"signalId": "2349227", "version": "mql4", "signalName": "Gold Spike",
            "subscribers": 42, "url": "https://www.mql5.com/en/signals/2349227"}
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(katalog=[item]),
        "http://b:8089": FakeClient(katalog=[item, {
            "signalId": "99", "version": "mql5", "signalName": "Nur im Spiegel"}]),
    })
    kandidaten = ingest.kandidaten_aus_quellen()
    assert len(kandidaten) == 2
    erster = kandidaten[0]
    assert erster["id"] == 2349227 and erster["platform"] == "mt4"
    assert erster["wochen"] is None and erster["abonnenten"] == 42
    assert erster["quelle_kuerzel"] == "mql5"  # erste Quelle gewinnt
    assert kandidaten[1]["quelle_kuerzel"] == "spiegel"


def test_trades_sha_cache():
    quelle = _quelle()
    client = FakeClient(trades=MINI_CSV)
    pfad, geaendert = ingest.hole_trades(quelle, 2349227, "mql5", client=client)
    assert geaendert is True and client.trades_aufrufe == 1
    # Download erfolgt immer (SHA braucht den Inhalt), die Verarbeitung/Neu-
    # Anlage des Artefakts nur bei Änderung.
    pfad2, geaendert2 = ingest.hole_trades(quelle, 2349227, "mql5", client=client)
    assert geaendert2 is False and client.trades_aufrufe == 2 and pfad2 == pfad
    client._trades = MINI_CSV + b"2026.09.03 10:00:00;Buy;0.01;XAUUSD;4330.00;0.01;2026.09.03 11:00:00;4338.00;-0.18;;7.82\n"
    _, geaendert3 = ingest.hole_trades(quelle, 2349227, "mql5", client=client)
    assert geaendert3 is True and client.trades_aufrufe == 3


def test_metrics_cache_und_mapping():
    quelle = _quelle()
    antwort = {"metrics": {"EquityDrawdown": 8.5, "Average3MonthProfit": 2.25,
                           "Balance": 1000.0, "Subscribers": 12}}
    client = FakeClient(metrics=antwort)
    erste = ingest.hole_metrics(quelle, 2349227, "mql5", client=client)
    assert erste == antwort
    stats = ingest.metrics_zu_stats(erste)
    assert stats["dd_equity_pct"] == 8.5
    assert stats["monthly_growth_pct"] == 2.25
    assert stats["initial_deposit_usd"] is None  # bis Downloader-Erweiterung
    assert ingest.metrics_zu_stats(None)["dd_equity_pct"] is None


# ------------------------------------------------------------------ Sync
def _punkt(ts, wert, change=0):
    return {"timestamp": ts, "subscribers": wert, "change": change}


def test_sync_history_ueber_zwei_quellen_ohne_doppelzaehlung(monkeypatch):
    _quelle("mql5", "http://a:8089")
    _quelle("spiegel", "http://b:8089")
    punkte = [_punkt("2026-09-01T06:45:00", 5), _punkt("2026-09-02T06:45:00", 7)]
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(history=punkte),
        "http://b:8089": FakeClient(history=punkte),  # identischer Spiegel
    })
    gespeichert = downloader_sync.sync_history(2349227, "mt4")
    assert gespeichert == 2  # dieselben Punkte zählen einfach, nicht doppelt
    assert len(db.get_history(2349227, "mql4")) == 2


def test_sync_history_teilausfall_und_gesamtausfall(monkeypatch):
    _quelle("mql5", "http://a:8089")
    _quelle("spiegel", "http://b:8089")
    down = downloader_client.DownloaderConnectionError("down")
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(fehler=down),
        "http://b:8089": FakeClient(history=[_punkt("2026-09-01T06:45:00", 3)]),
    })
    assert downloader_sync.sync_history(1, "mt4") == 1  # Quelle 2 rettet den Lauf
    _verdrahte(monkeypatch, {
        "http://a:8089": FakeClient(fehler=down),
        "http://b:8089": FakeClient(fehler=down),
    })
    with pytest.raises(downloader_client.DownloaderConnectionError):
        downloader_sync.sync_history(1, "mt4")


def test_sync_ohne_quelle_wirft_nicht_konfiguriert():
    with pytest.raises(downloader_client.DownloaderNotConfigured):
        downloader_sync.sync_history(1, "mt4")


# ------------------------------------------------------------------ Pipeline
def test_crawl_modus_quellen(monkeypatch):
    _quelle("mql5", "http://a:8089")
    _verdrahte(monkeypatch, {"http://a:8089": FakeClient(katalog=[
        {"signalId": "5", "version": "mql5", "signalName": "Aus Quelle",
         "subscribers": 9, "url": ""}])})
    pipe = pipeline.ScanPipeline(settings={"listen_modus": "quellen"})
    signale = pipe.crawl(lambda *a: None, lambda s: None)
    assert [s["id"] for s in signale] == [5]
    assert signale[0]["quelle_kuerzel"] == "mql5"


def test_analyze_kandidat_nimmt_quellen_pfad_und_persistiert(monkeypatch):
    quelle = _quelle()
    metrics = {"metrics": {"EquityDrawdown": 8.5, "Average3MonthProfit": 2.25}}
    _verdrahte(monkeypatch, {
        "http://localhost:8089": FakeClient(trades=MINI_CSV, metrics=metrics)})

    def exporter_verboten(*args, **kwargs):
        pytest.fail("exporter darf im Quellen-Modus nicht gerufen werden")
    monkeypatch.setattr(pipeline.exporter, "export_positions", exporter_verboten)

    kandidat = ingest.kandidaten(quelle, [
        {"signalId": "2349227", "version": "mql5", "signalName": "Gold Spike",
         "subscribers": 42}])[0]
    pipe = pipeline.ScanPipeline(settings={"listen_modus": "quellen"})
    log = []
    result = pipe.analyze_candidate(None, kandidat, log.append)
    assert result.quelle == "mql5"
    # Trade-Bezug kam aus dem Quellen-Cache (Artefakt registriert); der
    # Snapshot-Mechanismus hat die Datei zusätzlich unveränderbar abgelegt.
    artefakt = db.get_quellen_artefakt(quelle["id"], 2349227, "mql5", "trades")
    assert artefakt and artefakt["path"].replace("\\", "/").endswith(
        "mql5_2349227_trades.csv")
    gespeichert = db.get_signal(2349227)
    assert gespeichert["quelle"] == "mql5"


def test_kandidaten_pelican_version_und_wochen():
    """PelicanTrading (Version „pelican“): Plattform-Kennung, Signalalter aus
    dem Katalog (Wochen-Vorfilter greift) und Version-Durchreichung."""
    quelle = _quelle("pelik", "http://pelican:8090")
    items = [{"signalId": "100", "version": "pelican", "signalName": "Gold Pelican",
              "subscribers": 7, "weeks": 52, "currencyCode": "USD"}]
    kandidat = ingest.kandidaten(quelle, items)[0]
    assert kandidat["platform"] == "pelican"
    assert kandidat["wochen"] == 52
    assert kandidat["quelle_version"] == "pelican"
    assert kandidat["quelle_kuerzel"] == "pelik"
    # Detail-Sync/History fragen genau diese Version an
    assert downloader_client.platform_version("pelican") == "pelican"
    assert downloader_sync.versions("pelican") == ["pelican"]


def test_zeile_und_rest_api_zeigen_quelle():
    res = pipeline.ScanResult(id=1, name="X")
    assert res.to_row()["Quelle"] == "mql5"
    from mqlkiscanner import rest_api
    zeile = rest_api.signal_payload([SimpleNamespace(
        id=1, name="X", platform="mt5", url="", ampel="🟢", score=2.0,
        urteil="ok", kurzfassung="", quelle="pelik")])["signals"][0]
    assert zeile["quelle"] == "pelik"
