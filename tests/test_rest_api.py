# -*- coding: utf-8 -*-
"""Tests für das schreibgeschützte REST-Interface (MqlRealMonitor-Anbindung).

HTTP-Aufrufe gehen über stdlib urllib gegen einen lokalen Ephemer-Port —
der requests-Guard in conftest.py (keine externen Calls) bleibt unberührt.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from mqlkiscanner import rest_api
from mqlkiscanner.pipeline import ScanResult


def _result(signal_id: int, ampel: str, name: str = "", score: float | None = None) -> ScanResult:
    return ScanResult(id=signal_id, name=name, ampel=ampel, score=score)


def _get(url: str, headers: dict | None = None, method: str = "GET") -> tuple[int, dict]:
    """Lokaler HTTP-Aufruf; liefert (Statuscode, JSON-Antwort oder {})."""
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx sind hier normale Ergebnisse
        status, body = exc.code, exc.read()
    try:
        return status, json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return status, {}


# ------------------------------------------------------------------ Ampel-Mapping

def test_ampel_ascii_kennt_alle_werte_der_ergebnisansicht():
    assert rest_api.ampel_ascii("🟢") == "gruen"
    assert rest_api.ampel_ascii("🟡") == "gelb"
    assert rest_api.ampel_ascii("🟠") == "orange"
    assert rest_api.ampel_ascii("🔴") == "rot"
    assert rest_api.ampel_ascii("⚪") == "keine_daten"
    assert rest_api.ampel_ascii("⛔") == "ausgeschlossen"


def test_ampel_ascii_unbekannt_ist_leer():
    assert rest_api.ampel_ascii("") == ""
    assert rest_api.ampel_ascii(None) == ""
    assert rest_api.ampel_ascii("grün") == ""


@pytest.mark.parametrize("raw,erwartet", [
    ("gruen,gelb", {"gruen", "gelb"}),
    ("grün,gelb", {"gruen", "gelb"}),      # Umlaut-Schreibweise
    ("green, yellow", {"gruen", "gelb"}),  # Englisch + Leerzeichen
    ("🟢,🟡", {"gruen", "gelb"}),           # Emoji
    ("gruen", {"gruen"}),
])
def test_normalize_ampel_filter_akzeptiert_aliase(raw, erwartet):
    assert rest_api.normalize_ampel_filter(raw) == erwartet


def test_normalize_ampel_filter_ohne_wert_liefert_none():
    assert rest_api.normalize_ampel_filter(None) is None
    assert rest_api.normalize_ampel_filter("") is None
    assert rest_api.normalize_ampel_filter("  ") is None


def test_normalize_ampel_filter_unbekannter_wert_schlaegt_fehl():
    with pytest.raises(ValueError):
        rest_api.normalize_ampel_filter("gruen,lila")


# --------------------------------------------------------------------- Payload

def test_signal_payload_filtert_serverseitig():
    results = [
        _result(1, "🟢", "Kandidat A", 2.0),
        _result(2, "🟡", "Beobachtung B", 5.5),
        _result(3, "🔴", "Verworfen C", 8.0),
    ]
    payload = rest_api.signal_payload(results, {"gruen", "gelb"})
    assert payload["count"] == 2
    assert [z["signalId"] for z in payload["signals"]] == [1, 2]
    assert payload["signals"][0]["ampel"] == "gruen"
    assert payload["signals"][0]["ampelEmoji"] == "🟢"
    assert payload["signals"][0]["name"] == "Kandidat A"
    assert payload["signals"][1]["ampel"] == "gelb"


def test_signal_payload_ohne_filter_liefert_alle():
    results = [_result(1, "🟢"), _result(2, "🔴")]
    payload = rest_api.signal_payload(results)
    assert payload["count"] == 2
    assert payload["service"] == "mqlkiscanner"
    assert payload["generatedAt"]


def test_signal_payload_baut_url_wenn_fehlend():
    payload = rest_api.signal_payload([_result(2349227, "🟢")])
    assert payload["signals"][0]["url"] == "https://www.mql5.com/en/signals/2349227"


# ------------------------------------------------------------------ HTTP-Server

@pytest.fixture
def rest_server(monkeypatch):
    """Server auf zufälligem Port mit fester Ergebnisliste.

    Der Client-Zugriff-Zähler wird zurückgesetzt, damit Tests unabhängig
    voneinander sind.
    """
    monkeypatch.setattr(rest_api, "_client_state", {"ts": None})
    results = [
        _result(100, "🟢", "Gold Spike", 2.0),
        _result(200, "🟡", "KiraCat", 5.5),
        _result(300, "🔴", "Pure Gold", 8.0),
    ]
    server = rest_api.build_server(
        port=0, results_provider=lambda: results)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_client_status_noch_kein_zugriff(monkeypatch):
    monkeypatch.setattr(rest_api, "_client_state", {"ts": None})
    status = rest_api.client_status()
    assert status["verbunden"] is False
    assert status["letzter_abruf"] is None


def test_client_status_nach_zugriff(monkeypatch):
    import time as _time
    monkeypatch.setattr(rest_api, "_client_state", {"ts": _time.time() - 42})
    status = rest_api.client_status()
    assert status["verbunden"] is True  # Knopfdruck-Logik: Abruf zählt dauerhaft
    assert status["letzter_abruf"] is not None
    assert 40 <= status["alter_s"] <= 45


def test_signals_abruf_vermerkt_client_kontakt(rest_server):
    assert rest_api.letzter_client_zugriff() is None
    query = urllib.parse.urlencode({"ampel": "gruen,gelb"})
    _get(f"{rest_server}/api/v1/signals?{query}")
    assert rest_api.letzter_client_zugriff() is not None
    assert rest_api.client_status()["verbunden"] is True


def test_health_check_zaehlt_nicht_als_client(rest_server):
    _get(f"{rest_server}/api/v1/health")
    assert rest_api.letzter_client_zugriff() is None
    assert rest_api.client_status()["verbunden"] is False


def test_abgelehnter_zugriff_zaehlt_nicht_als_client(monkeypatch):
    monkeypatch.setattr(rest_api, "_client_state", {"ts": None})
    results = [_result(1, "🟢")]
    server = rest_api.build_server(port=0, token="geheim",
                                   results_provider=lambda: results)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _get(f"{base}/api/v1/signals")  # ohne Token -> 401
        assert rest_api.letzter_client_zugriff() is None
    finally:
        server.shutdown()


def test_health_endpunkt_antwortet(rest_server):
    status, body = _get(f"{rest_server}/api/v1/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["service"] == "mqlkiscanner"


def test_signals_endpunkt_mit_ampel_filter(rest_server):
    query = urllib.parse.urlencode({"ampel": "gruen,gelb"})
    status, body = _get(f"{rest_server}/api/v1/signals?{query}")
    assert status == 200
    assert body["count"] == 2
    ids = [s["signalId"] for s in body["signals"]]
    assert ids == [100, 200]  # rot gefiltert, Reihenfolge der DB bleibt


def test_signals_endpunkt_ohne_filter_liefert_alle(rest_server):
    status, body = _get(f"{rest_server}/api/v1/signals")
    assert status == 200
    assert body["count"] == 3


def test_signals_endpunkt_ungueltiger_filter_wird_abgelehnt(rest_server):
    query = urllib.parse.urlencode({"ampel": "lila"})
    status, body = _get(f"{rest_server}/api/v1/signals?{query}")
    assert status == 400
    assert "Unbekannter Ampel-Wert" in body["error"]


def test_unbekannter_pfad_liefert_404(rest_server):
    status, _ = _get(f"{rest_server}/api/v1/unknown")
    assert status == 404


def test_post_wird_nicht_untersetzt(rest_server):
    status, _ = _get(f"{rest_server}/api/v1/signals", method="POST")
    assert status in (405, 501)  # schreibgeschützt per Definition


def test_token_abgleich_lehnt_falschen_key_ab():
    results = [_result(1, "🟢")]
    server = rest_api.build_server(port=0, token="geheim",
                                   results_provider=lambda: results)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status_ohne, _ = _get(f"{base}/api/v1/signals")
        status_falsch, _ = _get(f"{base}/api/v1/signals",
                                headers={"X-User-Key": "falsch"})
        status_richtig, body = _get(f"{base}/api/v1/signals",
                                    headers={"X-User-Key": "geheim"})
        assert status_ohne == 401
        assert status_falsch == 401
        assert status_richtig == 200 and body["count"] == 1
    finally:
        server.shutdown()


def test_rest_api_ist_in_den_standardeinstellungen_aktiv():
    from mqlkiscanner import config
    assert config.DEFAULT_SETTINGS["rest_api_enabled"] is True
    assert config.DEFAULT_SETTINGS["rest_api_port"] == 8611
