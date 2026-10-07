# -*- coding: utf-8 -*-
"""Stufe 0 „Clients aktualisieren" (doc/23): Trigger/Poll/Timeout-Logik.

Alle Netzaufrufe sind gefaket (Muster test_downloader_client.py) — der
conftest weist echte Requests ab. Die Fake-Antworten bilden das
Update-Job-Protokoll v1 ab: POST /update + GET /update/status.
"""
from __future__ import annotations

import json

import pytest
import requests

from mqlkiscanner import client_updates as cu
from mqlkiscanner import db
from mqlkiscanner import downloader_client as dc


# --- Hilfen --------------------------------------------------------------

class _Antwort:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def _quelle_an(base: str, kuerzel: str = "fake") -> dict:
    db.init_db()
    return db.get_quelle(db.add_quelle(kuerzel, f"Test {kuerzel}", base))


class _FakeTransport:
    """requests.get/post im Client-Modul ersetzt; je URL eine Sequenz.

    health: feste Antwort (oder Exception). status: Liste, pro Abruf pop(0);
    bleibt der letzte Eintrag für immer. update: Antwort für POST (oder
    Sequenz für 409-Tests). Zeichnet alle Aufrufe mit URL auf.
    """

    def __init__(self, health=None, status=None, update=None):
        self.health = health if health is not None else _Antwort(body={"status": "ok"})
        if update is None:
            update = _Antwort(body={"jobId": "job-1", "status": "gestartet"})
        self.status_seq = list(status or [])
        self.update_seq = list(update) if isinstance(update, list) else [update]
        self.aufrufe: list[str] = []

    def install(self, monkeypatch):
        transport = self

        def fake_get(url, params=None, headers=None, timeout=None):
            transport.aufrufe.append(url)
            if isinstance(transport.health, Exception) and url.endswith("/health"):
                raise transport.health
            if url.endswith("/health"):
                return transport.health
            if url.endswith("/update/status"):
                if len(transport.status_seq) > 1:
                    return transport.status_seq.pop(0)
                return transport.status_seq[0] if transport.status_seq else _Antwort(
                    body={"state": "idle"})
            raise AssertionError(f"unerwarteter GET: {url}")

        def fake_post(url, json=None, headers=None, timeout=None):
            transport.aufrufe.append(url)
            antwort = (transport.update_seq.pop(0) if len(transport.update_seq) > 1
                       else transport.update_seq[0])
            if isinstance(antwort, Exception):
                raise antwort
            return antwort

        monkeypatch.setattr(dc.requests, "get", fake_get)
        monkeypatch.setattr(dc.requests, "post", fake_post)
        return self


def _status(state, **felder):
    body = {"state": state}
    body.update(felder)
    return _Antwort(body=body)


_DONE = _status("done", ergebnis={
    "signaleGeliefert": 200, "tradelistenNeu": 12, "tradelistenAktualisiert": 188,
    "datenstand": "2026-10-07T15:41:00", "hinweise": ["Test-Hinweis"]})

_SCHNELL = dict(bereit_warten_s=0.5, poll_s=0.01, backoff_s=0.01,
                timeout_s=5.0, login_timeout_s=0.3)


# --- Happy Path ----------------------------------------------------------

def test_happy_path_laeuft_bis_fertig(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    transport = _FakeTransport(
        status=[_status("running", phase="katalog", done=2, total=200,
                        message="Katalog 2/200"),
                _status("running", phase="tradelisten", done=100, total=200,
                        message="Tradelisten 100/200"),
                _DONE],
    ).install(monkeypatch)
    meldungen: list[dict] = []

    z = cu._update_eine_quelle(
        quelle, settings={}, log=None,
        on_fortschritt=lambda m: meldungen.append(m),
        gestopft=lambda: False, **_SCHNELL)

    assert z["status"] == cu.FERTIG
    assert z["job_id"] == "job-1"
    assert z["signale_geliefert"] == 200
    assert z["tradelisten_neu"] == 12
    assert z["datenstand"] == "2026-10-07T15:41:00"
    assert z["hinweise"] == ["Test-Hinweis"]
    assert meldungen, "Live-Callback muss gefeuert haben"
    assert any("Tradelisten 100/200" in m["detail"] for m in meldungen)
    # Chronik in der DB (append-only)
    eintraege = db.list_client_updates(limit=5)
    assert any(e["kuerzel"] == "fake" and e["status"] == cu.FERTIG
               and e["signale_geliefert"] == 200 for e in eintraege)


def test_katalog_uebersprungen_wird_gemeldet(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    done = _status("done", ergebnis={"signaleGeliefert": 648,
                                     "katalogUebersprungen": True,
                                     "datenstand": "2026-10-06T09:00:00"})
    _FakeTransport(status=[done]).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.FERTIG
    assert z["katalog_uebersprungen"] is True
    assert "3-Tage-Regel" in z["detail"]


# --- login_required ------------------------------------------------------

def test_login_kurzes_warten_wird_ueberstanden(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(status=[
        _status("login_required", message="Login-Fenster offen"),
        _status("running", phase="katalog", done=1, total=200),
        _DONE,
    ]).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.FERTIG


def test_login_timeout_weiter_mit_hinweis(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(status=[_status("login_required", message="Login nötig")]).install(
        monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               login_timeout_s=0.05, bereit_warten_s=0.5,
                               poll_s=0.01, backoff_s=0.01, timeout_s=5.0)
    assert z["status"] == cu.TIMEOUT
    assert "Login" in z["fehler"]


# --- 409 Busy / 405 alt / offline / Stop ---------------------------------

def test_busy_409_dann_erfolg(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(
        status=[_DONE],
        update=[_Antwort(status=409, body={"error": "beschaeftigt"}),
                _Antwort(body={"jobId": "job-2", "status": "gestartet"})],
    ).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.FERTIG
    assert z["job_id"] == "job-2"


def test_busy_409_dreimal_wird_timeout(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(
        status=[_DONE],
        update=_Antwort(status=409, body={"error": "beschaeftigt"}),
    ).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.TIMEOUT
    assert "409" in z["fehler"]


def test_405_ist_nicht_unterstuetzt(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(
        status=[_DONE],
        update=_Antwort(status=405, body={}),
    ).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.NICHT_UNTERSTUETZT
    assert "aktualisiert werden" in z["fehler"]


def test_nie_erreichbar_ist_offline(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(
        health=requests.exceptions.ConnectionError("refused"),
        status=[_DONE],
    ).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               bereit_warten_s=0.1, poll_s=0.01, backoff_s=0.01,
                               timeout_s=5.0, login_timeout_s=0.3)
    assert z["status"] == cu.OFFLINE


def test_stop_button_bricht_ab(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(status=[_status("running", done=1, total=200)]).install(monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: True,
                               **_SCHNELL)
    assert z["status"] == cu.ABGEBROCHEN


def test_job_error_wird_fehler(monkeypatch):
    quelle = _quelle_an("http://rechner:8199")
    _FakeTransport(status=[_status("error", error="Plattform down")]).install(
        monkeypatch)
    z = cu._update_eine_quelle(quelle, settings={}, log=None,
                               on_fortschritt=None, gestopft=lambda: False,
                               **_SCHNELL)
    assert z["status"] == cu.FEHLER
    assert "Plattform down" in z["fehler"]


# --- Aggregat/Regel-Helfer ----------------------------------------------

def test_alle_kritisch_nur_wenn_alles_rot():
    assert cu.alle_kritisch({"a": {"status": cu.FEHLER},
                             "b": {"status": cu.OFFLINE}})
    assert not cu.alle_kritisch({"a": {"status": cu.FEHLER},
                                 "b": {"status": cu.FERTIG}})
    assert not cu.alle_kritisch({})


def test_mit_hinweisen_und_aggregat_text():
    z = {"a": {"status": cu.FERTIG}, "b": {"status": cu.TIMEOUT}}
    assert cu.mit_hinweisen(z) is True
    assert cu.mit_hinweisen({"a": {"status": cu.FERTIG}}) is False
    text = cu.aggregat_text(z)
    assert "1 fertig" in text and "1 mit Hinweis" in text


# --- starte_alle_updates (parallel, gemischt) ----------------------------

def test_starte_alle_updates_mischlagen(monkeypatch):
    db.init_db()
    db.add_quelle("gut", "Gut", "http://rechner:8200")
    db.add_quelle("alt", "Alt", "http://rechner:8201")

    def fake_client_fuer_quelle(quelle, timeout=None):
        kuerzel = quelle["kuerzel"]
        if kuerzel == "alt":
            client = dc.DownloaderClient(quelle["base_url"])
            monkeypatch.setattr(
                client, "health",
                lambda: {"status": "ok"})
            monkeypatch.setattr(
                client, "update_starten",
                lambda **kw: (_ for _ in ()).throw(
                    dc.DownloaderUpdateNotSupported("405")))
            return client
        client = dc.DownloaderClient(quelle["base_url"])
        monkeypatch.setattr(client, "health", lambda: {"status": "ok"})
        monkeypatch.setattr(
            client, "update_starten",
            lambda **kw: {"jobId": "j", "status": "gestartet"})
        monkeypatch.setattr(client, "update_status", lambda: {
            "state": "done",
            "ergebnis": {"signaleGeliefert": 200, "datenstand": "heute"}})
        return client

    monkeypatch.setattr(cu.quellen, "client_fuer_quelle", fake_client_fuer_quelle)
    ergebnis = cu.starte_alle_updates({}, bereit_warten_s=0.2, poll_s=0.01,
                                      backoff_s=0.01)
    assert set(ergebnis) == {"gut", "alt"}
    assert ergebnis["gut"]["status"] == cu.FERTIG
    assert ergebnis["alt"]["status"] == cu.NICHT_UNTERSTUETZT
    assert cu.mit_hinweisen(ergebnis) is True
    assert cu.alle_kritisch(ergebnis) is False


def test_starte_alle_updates_ohne_quellen():
    ergebnis = cu.starte_alle_updates({}, bereit_warten_s=0.1)
    assert ergebnis == {}


# --- REST-Client: POST-Methoden ------------------------------------------

def test_update_starten_und_status(monkeypatch):
    client = dc.DownloaderClient("http://rechner:8089")
    posts: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        posts.append({"url": url, "json": json})
        return _Antwort(body={"jobId": "u-1", "status": "gestartet",
                              "bereitsLaufend": False})

    monkeypatch.setattr(dc.requests, "post", fake_post)
    antwort = client.update_starten(target=200, tradelisten=True,
                                    katalog_max_alter_h=72)
    assert antwort["jobId"] == "u-1"
    assert posts[0]["url"].endswith("/update")
    assert posts[0]["json"] == {"target": 200, "tradelisten": True,
                                "katalogMaxAlterH": 72,
                                "quelle": "signalkiscanner"}


def test_post_405_und_409_fehlerklasse(monkeypatch):
    client = dc.DownloaderClient("http://rechner:8089")
    monkeypatch.setattr(dc.requests, "post",
                        lambda *a, **kw: _Antwort(status=405, body={}))
    with pytest.raises(dc.DownloaderUpdateNotSupported):
        client.update_starten()
    monkeypatch.setattr(dc.requests, "post",
                        lambda *a, **kw: _Antwort(status=409, body={}))
    with pytest.raises(dc.DownloaderBusy):
        client.update_starten()


# --- DB-Chronik ----------------------------------------------------------

def test_letzte_client_updates_je_quelle():
    db.store_client_update(quelle_id=1, kuerzel="pelik", status=cu.FERTIG,
                           dauer_s=12.0, signale_geliefert=648,
                           datenstand="2026-10-07 10:00")
    db.store_client_update(quelle_id=2, kuerzel="robo", status=cu.FEHLER,
                           fehler="Plattform down")
    db.store_client_update(quelle_id=1, kuerzel="pelik", status=cu.FEHLER,
                           fehler="danach kaputt")
    neueste = db.letzte_client_updates_je_quelle()
    assert neueste["pelik"]["status"] == cu.FEHLER  # zweiter Eintrag gewinnt
    assert neueste["robo"]["fehler"] == "Plattform down"


def test_zahl_aus_settings_null_ist_gueltig():
    assert cu._zahl_aus_settings({"update_login_timeout_min": 0}, "x", 10) == 10
    assert cu._zahl_aus_settings({"update_login_timeout_min": 0},
                                 "update_login_timeout_min", 10) == 0.0
    assert cu._zahl_aus_settings({}, "update_timeout_min", 120) == 120
    assert cu._zahl_aus_settings({"update_timeout_min": "x"}, "update_timeout_min",
                                 120) == 120
