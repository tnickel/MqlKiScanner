# -*- coding: utf-8 -*-
"""Tradeserver-Anbindung: REST-Client für das KiScanner-Sync-Protokoll v1.

Alle Netzaufrufe sind gefaket — der conftest weist echte Requests ab.
"""
from __future__ import annotations

import json

import pytest
import requests

from mqlkiscanner import config, secrets_store
from mqlkiscanner import tradeserver_client as tsc


# --- URL-Normalisierung ---------------------------------------------------

def test_normalize_base_url_behaelt_host_und_port():
    assert tsc.normalize_base_url("http://tradeserver.example:8080/") == \
        "http://tradeserver.example:8080"


def test_normalize_base_url_behaelt_kontextpfad():
    assert tsc.normalize_base_url("https://monitor.example.de/trademonitor") == \
        "https://monitor.example.de/trademonitor"


def test_normalize_base_url_leer_ist_unkonfiguriert():
    assert tsc.normalize_base_url("   ") == ""


@pytest.mark.parametrize("bad", ["tradeserver.example:8080", "ftp://host", "nur-text"])
def test_normalize_base_url_ungueltig(bad):
    with pytest.raises(tsc.TradeserverError):
        tsc.normalize_base_url(bad)


# --- Fake-Transport -------------------------------------------------------

class _Antwort:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def _verdrahte(monkeypatch, antwort):
    """Ersetzt requests.request im Client-Modul; zeichnet Aufrufe auf."""
    aufgerufen: list = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        aufgerufen.append({"method": method, "url": url, "json": json,
                           "headers": headers or {}, "timeout": timeout})
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    monkeypatch.setattr(tsc.requests, "request", fake_request)
    return aufgerufen


def test_ping_schluessel_als_header(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={
        "status": "ok", "service": "MqlTradeMonitor", "kiscannerApi": "v1"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="schluessel-1")
    info = client.ping()
    assert info["status"] == "ok"
    assert aufrufe[0]["method"] == "GET"
    assert aufrufe[0]["url"] == "http://server:8080/api/kiscanner/ping"
    assert aufrufe[0]["headers"]["X-User-Key"] == "schluessel-1"


def test_register_sendet_protokollpflichtfelder(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={
        "status": "ok", "runId": 7, "documents": [], "serverTime": "x"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    client.register(signal_count=12)
    payload = aufrufe[0]["json"]
    assert payload["client"] == "MqlKiScanner"
    assert payload["protocolVersion"] == tsc.PROTOKOLL_VERSION
    assert payload["scannerVersion"]  # Version aus dem Paket
    assert payload["signalCount"] == 12


def test_document_sendet_dokumentstruktur(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={"status": "ok", "stored": True}))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    client.document({"docKey": "signal/1/01-trade-analyse.pdf",
                     "sha256": "abc", "contentBase64": "QkFGRg=="})
    payload = aufrufe[0]["json"]
    assert payload["docKey"] == "signal/1/01-trade-analyse.pdf"
    assert payload["contentBase64"] == "QkFGRg=="
    assert aufrufe[0]["url"].endswith("/api/kiscanner/documents")


def test_complete_sendet_bilanz(monkeypatch):
    aufrufe = _verdrahte(monkeypatch, _Antwort(body={"status": "ok"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    client.complete(signals=5, documents=9, uploaded=2, skipped=7, bytes_total=1234)
    assert aufrufe[0]["json"] == {"signals": 5, "documents": 9, "uploaded": 2,
                                  "skipped": 7, "bytes": 1234}


def test_401_ist_auth_fehler(monkeypatch):
    _verdrahte(monkeypatch, _Antwort(status=401, body={"message": "Unauthorized"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="falsch")
    with pytest.raises(tsc.TradeserverAuthError):
        client.ping()


def test_400_ist_protokollfehler(monkeypatch):
    _verdrahte(monkeypatch, _Antwort(
        status=400, body={"message": "Unknown client — protocol v1 required"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    with pytest.raises(tsc.TradeserverProtocolError, match="protocol v1"):
        client.register()


def test_verbindungsfehler_wird_klar_sortiert(monkeypatch):
    _verdrahte(monkeypatch, requests.exceptions.ConnectionError("refused"))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    with pytest.raises(tsc.TradeserverConnectionError):
        client.ping()


def test_500_ist_generischer_fehler(monkeypatch):
    _verdrahte(monkeypatch, _Antwort(status=500, body={"message": "boom"}))
    client = tsc.TradeserverClient("http://server:8080", api_key="k")
    with pytest.raises(tsc.TradeserverError, match="boom"):
        client.ping()


# --- Konfiguration --------------------------------------------------------

def test_client_from_settings_ohne_base_ist_unkonfiguriert():
    with pytest.raises(tsc.TradeserverNotConfigured):
        tsc.client_from_settings(config.load_settings())


def test_client_from_settings_liefert_gespeicherten_key():
    config.save_settings({**config.load_settings(),
                          "tradeserver_base_url": "http://server:8080"})
    secrets_store.save_secrets(tradeserver_api_key="key-aus-secrets")
    client = tsc.client_from_settings(config.load_settings())
    assert client.base == "http://server:8080"
    assert client.api_key == "key-aus-secrets"
