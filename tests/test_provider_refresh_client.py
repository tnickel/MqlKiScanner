"""Gezielter Anbieterabruf: lokale HTTP-Fakes, niemals echte Quellenzugriffe."""
from __future__ import annotations

import copy
import json

import pytest

from mqlkiscanner import downloader_client as dc


class Antwort:
    def __init__(self, body=None, code=200):
        self.status_code = code
        self.body = {} if body is None else body
        self.text = json.dumps(self.body)

    def json(self):
        return self.body


@pytest.fixture
def transport(monkeypatch):
    class Fake:
        health = {"providerRefresh": True}
        acceptance = {"jobId": "our-job", "status": "gestartet"}
        post_code = 200

        def __init__(self):
            self.calls = []
            self.sleep = []
            self.result = {"providerId": "811", "version": "mql5",
                           "platformRefreshed": True, "fullHistory": True,
                           "refreshedAt": "2026-10-23T16:00:00+02:00"}
            self.states = []

        def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            if url.endswith("/health"):
                return Antwort(self.health)
            assert url.endswith("/update/status"), "Kein lokaler GET-/Katalog-Fallback erlaubt"
            if self.states:
                return Antwort(self.states.pop(0))
            return Antwort({"jobId": "our-job", "state": "done", "ergebnis": self.result})

        def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            assert url.endswith("/providers/811/mql5/refresh"), "Kein globaler Update-Fallback erlaubt"
            return Antwort(self.acceptance, self.post_code)

    fake = Fake()
    monkeypatch.setattr(dc.requests, "get", fake.get)
    monkeypatch.setattr(dc.requests, "post", fake.post)
    monkeypatch.setattr(dc.time, "sleep", lambda delay: fake.sleep.append(delay))
    return fake


def test_refresh_bis_eigener_done_job_mit_auth_header(transport):
    transport.states = [{"jobId": "our-job", "state": "running", "phase": "trades"}]
    result = dc.DownloaderClient("http://synthetic-client:8188", token="synthetic-token").refresh_provider(811, "mql5")
    assert result == dict(transport.result, jobId="our-job")
    assert len(transport.calls) == 4
    assert len(transport.sleep) == 1
    assert [call[0] for call in transport.calls] == ["GET", "POST", "GET", "GET"]
    assert all(call[2]["headers"] == {"X-API-Token": "synthetic-token"} for call in transport.calls)
    assert transport.calls[1][2]["json"] == {}


@pytest.mark.parametrize("patch", [
    {"providerId": "999"}, {"version": "mql4"}, {"platformRefreshed": False},
    {"fullHistory": False}, {"refreshedAt": None}, {"refreshedAt": ""},
    {"tradelistenFehler": 1}, {"tradelistenAbgebrochen": 1},
])
def test_done_ohne_eindeutigen_fullrefresh_beleg_ist_fehler(transport, patch):
    transport.result.update(patch)
    with pytest.raises(dc.DownloaderError, match="vollständigen aktuellen Abruf"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")
    assert len(transport.calls) == 3


@pytest.mark.parametrize("job_id", [None, "old-job", "someone-else"])
def test_status_eines_anderen_jobs_ist_kein_nachweis(transport, job_id):
    transport.states = [{"jobId": job_id, "state": "done", "ergebnis": copy.deepcopy(transport.result)}]
    with pytest.raises(dc.DownloaderError, match="anderen Job"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")


@pytest.mark.parametrize("acceptance", [{}, [], {"jobId": "other-job", "bereitsLaufend": True}])
def test_annahme_ohne_neuen_eigenen_job_reicht_nicht(transport, acceptance):
    transport.acceptance = acceptance
    with pytest.raises(dc.DownloaderError):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")
    assert len(transport.calls) == 2


@pytest.mark.parametrize("health,cls,message", [
    ({}, dc.DownloaderUpdateNotSupported, "keinen gezielten"),
    ({"providerRefresh": False}, dc.DownloaderUpdateNotSupported, "keinen gezielten"),
    ({"providerRefresh": False, "providerRefreshReason": "Robo units_unverified"},
     dc.DownloaderProviderBlocked, "units_unverified"),
])
def test_capability_vor_post_pruefen_ohne_fallback(transport, health, cls, message):
    transport.health = health
    with pytest.raises(cls, match=message):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")
    assert len(transport.calls) == 1


@pytest.mark.parametrize("code,cls", [
    (401, dc.DownloaderAuthError), (405, dc.DownloaderUpdateNotSupported),
    (409, dc.DownloaderBusy), (422, dc.DownloaderProviderBlocked),
])
def test_http_quellenfehler_ohne_globalupdate_oder_getfallback(transport, code, cls):
    transport.post_code = code
    transport.acceptance = {"error": "synthetic source blocked"}
    with pytest.raises(cls):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")
    assert len(transport.calls) == 2


def test_login_required_beendet_warten_mit_authfehler(transport):
    transport.states = [{"jobId": "our-job", "state": "login_required", "message": "Login nötig"}]
    with pytest.raises(dc.DownloaderAuthError, match="Login nötig"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")
    assert not transport.sleep


@pytest.mark.parametrize("state", ["error", "cancelled", "aborted"])
def test_endgueltige_jobfehler_brechen_ab(transport, state):
    transport.states = [{"jobId": "our-job", "state": state, "error": "synthetic job failed"}]
    with pytest.raises(dc.DownloaderError, match="synthetic job failed"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5")


def test_async_annahme_mit_offenem_status_ist_nie_erfolg(transport):
    transport.states = [{"jobId": "our-job", "state": "running"}]
    with pytest.raises(dc.DownloaderConnectionError, match="Zeitlimit"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5", timeout_s=0)
    assert len(transport.calls) == 3
    assert not transport.sleep


def test_stop_vor_start_sendet_keinen_request(transport):
    with pytest.raises(dc.DownloaderError, match="vor dem Start abgebrochen"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5", should_stop=lambda: True)
    assert not transport.calls


def test_stop_waehrend_warten_keine_unbelegte_erfolgsmeldung(transport):
    stops = iter([False, False, True])
    with pytest.raises(dc.DownloaderError, match="Quellenjob kann noch laufen"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(811, "mql5", should_stop=lambda: next(stops))
    assert [call[0] for call in transport.calls] == ["GET", "POST"]


def test_stop_nach_health_verhindert_neuen_quellenjob(transport):
    stops = iter([False, True])
    with pytest.raises(dc.DownloaderError, match="vor dem Start abgebrochen"):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(
            811, "mql5", should_stop=lambda: next(stops))
    assert [call[0] for call in transport.calls] == ["GET"]


@pytest.mark.parametrize("sid,version", [(True, "mql5"), (0, "mql5"), (-1, "mql5"), (811, "../admin")])
def test_ungueltige_identitaet_vor_request_gesperrt(transport, sid, version):
    with pytest.raises(ValueError):
        dc.DownloaderClient("http://synthetic-client:8188").refresh_provider(sid, version)
    assert not transport.calls
