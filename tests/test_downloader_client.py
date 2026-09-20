# -*- coding: utf-8 -*-
"""MqlDownloader-Anbindung: REST-Client, DB-Spiegelung und Abruf-Logik.

Alle Netzaufrufe sind gefaket — der conftest weist echte Requests ab.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests

from mqlkiscanner import app_ui, config, db, downloader_sync, secrets_store
from mqlkiscanner import downloader_client as dc


# --- URL-Normalisierung und Plattform-Zuordnung -------------------------

def test_normalize_base_url_ergaenzt_api_v1():
    assert dc.normalize_base_url("http://rechner:8089") == "http://rechner:8089/api/v1"


def test_normalize_base_url_behaelt_api_v1():
    assert dc.normalize_base_url(" http://rechner:8089/api/v1/ ") == "http://rechner:8089/api/v1"


def test_normalize_base_url_leer_ist_unKonfiguriert():
    assert dc.normalize_base_url("   ") == ""


@pytest.mark.parametrize("bad", ["rechner:8089", "ftp://rechner:8089", "/api/v1"])
def test_normalize_base_url_ungueltig(bad):
    with pytest.raises(dc.DownloaderError):
        dc.normalize_base_url(bad)


@pytest.mark.parametrize("platform, expected", [
    ("MT4", "mql4"), ("MQL4", "mql4"), ("mt5", "mql5"), ("MQL5", "mql5"),
    ("", None), ("CSV", None),
])
def test_platform_version(platform, expected):
    assert dc.platform_version(platform) == expected


# --- Fake-Transport ------------------------------------------------------

class _Antwort:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)
        self.content = content

    def json(self):
        return self._body


def _verdrahte(monkeypatch, antwort):
    """Ersetzt requests.get im Client-Modul; zeichnet Aufrufe auf."""
    aufgerufen: list = []

    def fake_get(url, params=None, headers=None, timeout=None):
        aufgerufen.append({"url": url, "params": params, "headers": headers or {}})
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    monkeypatch.setattr(dc.requests, "get", fake_get)
    return aufgerufen


def test_health_liefert_status_und_url(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={
        "status": "ok", "service": "MqlDownloader", "apiVersion": "v1",
        "providers": 176, "tokenRequired": False}))
    client = dc.DownloaderClient("http://rechner:8089")
    info = client.health()
    assert info["status"] == "ok"
    assert aufrufe[0]["url"] == "http://rechner:8089/api/v1/health"
    assert aufrufe[0]["headers"] == {}  # ohne Token kein Auth-Header


def test_token_wird_als_header_gesendet(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={"status": "ok"}))
    client = dc.DownloaderClient("http://rechner:8089", token="geheim")
    client.health()
    assert aufrufe[0]["headers"] == {"X-API-Token": "geheim"}


def test_401_ist_auth_fehler(monkeypatch):
    _verdrahte(monkeypatch, _Antwort(status=401, body={"error": "bad token"}))
    client = dc.DownloaderClient("http://rechner:8089", token="falsch")
    with pytest.raises(dc.DownloaderAuthError):
        client.health()


def test_404_ist_nicht_gefunden(monkeypatch):
    _verdrahte(monkeypatch, _Antwort(status=404, body={"error": "unknown provider"}))
    client = dc.DownloaderClient("http://rechner:8089")
    with pytest.raises(dc.DownloaderNotFound):
        client.history(123, "mql5")


def test_verbindungsfehler_wird_klar_sortiert(monkeypatch):
    _verdrahte(monkeypatch, requests.exceptions.ConnectionError("refused"))
    client = dc.DownloaderClient("http://rechner:8089")
    with pytest.raises(dc.DownloaderConnectionError):
        client.health()


def test_history_liefert_punkte(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={
        "signalId": "123", "version": "mql5", "total": 2,
        "points": [
            {"timestamp": "2026-09-01T18:00:05", "subscribers": 42, "change": 0},
            {"timestamp": "2026-09-08T18:00:10", "subscribers": 45, "change": 3},
        ]}))
    client = dc.DownloaderClient("http://rechner:8089")
    punkte = client.history(123, "mql5")
    assert [p["subscribers"] for p in punkte] == [42, 45]
    assert aufrufe[0]["url"] == "http://rechner:8089/api/v1/providers/123/mql5/history"


def test_download_report_codiert_namen(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(content=b"%PDF-1.4 test"))
    client = dc.DownloaderClient("http://rechner:8089")
    daten = client.download_report(123, "mql5", "testreport 123.pdf")
    assert daten.startswith(b"%PDF")
    assert aufrufe[0]["url"].endswith(
        "/providers/123/mql5/reports/testreport%20123.pdf")


def test_client_from_settings_ohne_base_lehnt_ab():
    with pytest.raises(dc.DownloaderNotConfigured):
        dc.client_from_settings({})


def test_client_from_settings_nimmt_token_aus_secrets_store():
    secrets_store.save_secrets(downloader_token="aus-admin")
    client = dc.client_from_settings({"downloader_base_url": "http://rechner:8089"})
    assert client.token == "aus-admin"
    assert client.base == "http://rechner:8089/api/v1"


# --- DB-Spiegelung -------------------------------------------------------

def test_history_roundtrip_und_aktualisierung():
    db.init_db()
    punkte = [
        {"timestamp": "2026-09-01T18:00:05", "subscribers": 42, "change": 0},
        {"timestamp": "2026-09-08T18:00:10", "subscribers": 45, "change": 3},
        {"timestamp": "", "subscribers": 99, "change": 0},  # ohne Zeit: übersprungen
    ]
    assert db.store_history_points(77, "mql5", punkte) == 2
    assert db.store_history_points(77, "mql5",
                                   [{"timestamp": "2026-09-08T18:00:10",
                                     "subscribers": 46, "change": 4}]) == 1
    verlauf = db.get_history(77)
    assert [(p["ts"], p["subscribers"], p["change"]) for p in verlauf] == [
        ("2026-09-01T18:00:05", 42, 0), ("2026-09-08T18:00:10", 46, 4)]
    assert db.get_history(77, version="mql4") == []
    assert db.get_history(999) == []


def test_downloader_reports_roundtrip():
    db.init_db()
    db.store_downloader_report(77, "mql5", "a.pdf", "/tmp/a.pdf",
                               size_bytes=1200, last_modified="2026-09-20T10:00:00")
    db.store_downloader_report(77, "mql4", "b.pdf", "/tmp/b.pdf", size_bytes=3)
    db.store_downloader_report(77, "mql5", "a.pdf", "/tmp/a2.pdf",
                               size_bytes=1300, last_modified="2026-09-21T10:00:00")
    berichte = db.list_downloader_reports(77)
    assert [(b["version"], b["name"], b["path"]) for b in berichte] == [
        ("mql4", "b.pdf", "/tmp/b.pdf"), ("mql5", "a.pdf", "/tmp/a2.pdf")]
    assert berichte[1]["size_bytes"] == 1300


def test_report_counts_fuer_tabellenspalte():
    db.init_db()
    db.store_downloader_report(77, "mql5", "a.pdf", "/tmp/a.pdf", size_bytes=1)
    db.store_downloader_report(77, "mql5", "b.pdf", "/tmp/b.pdf", size_bytes=1)
    db.store_downloader_report(88, "mql4", "c.pdf", "/tmp/c.pdf", size_bytes=1)
    assert db.downloader_report_counts([77, 88, 99]) == {77: 2, 88: 1}
    assert db.downloader_report_counts([]) == {}
    assert db.downloader_report_counts([0]) == {}


# --- Abruf-Logik der Detail-Ansicht --------------------------------------

@dataclass
class _Result:
    id: int = 77
    platform: str = "MT5"


class _FakeClient:
    """Antwortet nur für Signal #77; andere IDs liefern 404."""

    def __init__(self, history=None, reports=None):
        self.history_antwort = history or {}
        self.reports_antwort = reports or {}
        self.downloads: list[str] = []

    def history(self, signal_id, version):
        if signal_id != 77:
            raise dc.DownloaderNotFound("kein Eintrag")
        punkte = self.history_antwort.get(version)
        if punkte is None:
            raise dc.DownloaderNotFound("kein Eintrag")
        return punkte

    def reports(self, signal_id, version):
        if signal_id != 77:
            raise dc.DownloaderNotFound("kein Eintrag")
        items = self.reports_antwort.get(version)
        if items is None:
            raise dc.DownloaderNotFound("kein Eintrag")
        return items

    def download_report(self, signal_id, version, name):
        self.downloads.append((version, name))
        return b"%PDF-1.4 fake"


def test_fetch_history_legt_punkte_ab_und_ignoriert_404(monkeypatch):
    db.init_db()
    fake = _FakeClient(history={
        "mql5": [{"timestamp": "2026-09-01T18:00:05", "subscribers": 42, "change": 0}],
        # mql4 fehlt im Downloader → 404 → Version wird übersprungen
    })
    monkeypatch.setattr(dc, "client_from_settings", lambda settings: fake)
    assert app_ui._dl_fetch_history(_Result()) == 1
    verlauf = db.get_history(77)
    assert len(verlauf) == 1 and verlauf[0]["version"] == "mql5"


def test_fetch_reports_spiegelt_pdf_und_ueberspringt_unveraenderte(monkeypatch):
    db.init_db()
    fake = _FakeClient(reports={
        "mql5": [{"name": "testreport_77.pdf", "sizeBytes": 12,
                  "lastModified": "2026-09-20T10:00:00"}],
    })
    monkeypatch.setattr(dc, "client_from_settings", lambda settings: fake)
    neu = app_ui._dl_fetch_reports(_Result())
    assert len(neu) == 1
    pfad = Path(neu[0])
    assert pfad.read_bytes() == b"%PDF-1.4 fake"
    assert config.DOWNLOADER_DIR / "77" / "reports" / "mql5" == pfad.parent
    assert db.list_downloader_reports(77)[0]["last_modified"] == "2026-09-20T10:00:00"
    # Gleicher Name + gleiche Größe → kein erneuter Download.
    assert app_ui._dl_fetch_reports(_Result()) == []
    assert len(fake.downloads) == 1


def test_fetch_reports_laedt_geaenderte_groesse_neu(monkeypatch):
    db.init_db()
    fake = _FakeClient(reports={
        "mql5": [{"name": "testreport_77.pdf", "sizeBytes": 12,
                  "lastModified": "2026-09-20T10:00:00"}],
    })
    monkeypatch.setattr(dc, "client_from_settings", lambda settings: fake)
    app_ui._dl_fetch_reports(_Result())
    fake.reports_antwort["mql5"][0]["sizeBytes"] = 34
    assert len(app_ui._dl_fetch_reports(_Result())) == 1
    assert len(fake.downloads) == 2


def test_versionswahl_ohne_plattformfragt_beide(monkeypatch):
    db.init_db()
    fake = _FakeClient(history={
        "mql4": [{"timestamp": "2026-09-01T18:00:05", "subscribers": 7, "change": 0}],
        "mql5": [{"timestamp": "2026-09-01T18:00:05", "subscribers": 9, "change": 0}],
    })
    monkeypatch.setattr(dc, "client_from_settings", lambda settings: fake)
    assert app_ui._dl_fetch_history(_Result(platform="")) == 2
    versionen = {row["version"] for row in db.get_history(77)}
    assert versionen == {"mql4", "mql5"}


# --- Batch-Abgleich (Workflow-Station 6 / Ergebnisseite) -----------------

def test_versions_hilfe():
    assert downloader_sync.versions("MT4") == ["mql4"]
    assert downloader_sync.versions("mql5") == ["mql5"]
    assert downloader_sync.versions("") == ["mql4", "mql5"]


def test_konfiguriert_folgt_base_url():
    assert downloader_sync.konfiguriert() is False
    config.save_settings({**config.load_settings(),
                          "downloader_base_url": "http://rechner:8089"})
    assert downloader_sync.konfiguriert() is True


def test_sync_many_sammelt_bilanz_und_toleraert_404():
    db.init_db()
    fake = _FakeClient(history={
        "mql5": [{"timestamp": "2026-09-01T18:00:05", "subscribers": 42, "change": 0}],
    }, reports={
        "mql5": [{"name": "t_77.pdf", "sizeBytes": 12, "lastModified": "2026-09-20T10:00:00"}],
    })
    summary = downloader_sync.sync_many([(77, "MT5"), (78, "MT5")], client=fake)
    assert summary["signale"] == 2          # 78 liefert 404 → trotzdem gezählt
    assert summary["verlaufspunkte"] == 1
    assert summary["neue_pdfs"] == 1
    assert summary["abgebrochen"] is None
    assert summary["fehler"] == []


def test_sync_many_bricht_bei_verbindungsfehler_ab():
    db.init_db()

    class _AbbruchClient(_FakeClient):
        def history(self, signal_id, version):
            if signal_id == 79:
                raise dc.DownloaderConnectionError("weg")
            return []

    aufgerufen: list[int] = []
    summary = downloader_sync.sync_many(
        [(78, "MT5"), (79, "MT5"), (80, "MT5")], client=_AbbruchClient(),
        progress=lambda done, total, sid: aufgerufen.append(sid))
    assert summary["abgebrochen"] == "weg"
    assert 80 not in aufgerufen  # nach dem Abbruch keine weiteren Anfragen


def test_sync_many_sammelt_einzelfehler_und_laeuft_weiter():
    db.init_db()

    class _EinzelClient(_FakeClient):
        def history(self, signal_id, version):
            if signal_id == 78:
                raise dc.DownloaderError("HTTP 500 intern")
            return []

    summary = downloader_sync.sync_many([(78, "MT5"), (79, "MT5")], client=_EinzelClient())
    assert summary["signale"] == 2
    assert len(summary["fehler"]) == 1
    assert summary["fehler"][0].startswith("#78")
    assert summary["abgebrochen"] is None


def test_abgleich_bewertet_nie_neu():
    """Grundregel: Der Sync berührt Signale, Forensik und Analysen nicht."""
    db.init_db()
    db.upsert_signal(77, name="Alt", platform="MT5", abonnenten=10)
    db.store_forensik(77, {"trading_dd_pct": 1.0})
    fake = _FakeClient(history={
        "mql5": [{"timestamp": "2026-09-02T18:00:05", "subscribers": 999, "change": 900}],
    })
    summary = downloader_sync.sync_many([(77, "MT5")], client=fake)
    assert summary["verlaufspunkte"] == 1
    signal = db.get_signal(77)
    assert signal["name"] == "Alt"
    assert signal["abonnenten"] == 10  # Plattformstand bleibt unberührt
    # Frische Downloader-Daten landen ausschließlich in subscriber_history:
    assert db.get_history(77)[0]["subscribers"] == 999
