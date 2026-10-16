from threading import Event
from time import monotonic, sleep

from mqlkiscanner.verbindungs_monitor import VerbindungsMonitor


def warten(predicate):
    deadline = monotonic() + 3
    while not predicate():
        assert monotonic() < deadline, "Hintergrundprüfung wurde nicht fertig"
        sleep(.005)


def ziel(key, token="alt"):
    return {"id": key, "name": key, "art": "quelle", "token": token}


def test_ui_wartet_weder_auf_konfiguration_noch_auf_netz_und_prueft_parallel():
    laden_frei, netz_frei = Event(), Event()
    angekommen = {key: Event() for key in ("a", "b", "server")}

    def laden():
        assert laden_frei.wait(3)
        return [ziel(key) for key in angekommen]

    def pruefen(z):
        angekommen[z["id"]].set()
        assert netz_frei.wait(3)
        return {"ok": True}

    m = VerbindungsMonitor(laden, pruefen)
    try:
        assert m.zustand() == {"geladen": False, "fehler": False, "verbindungen": []}
        laden_frei.set()
        warten(lambda: all(e.is_set() for e in angekommen.values()))
        snapshot = m.zustand()
        assert all(v["prueft"] and v["ergebnis"] is None
                   for v in snapshot["verbindungen"])
        assert "token" not in str(snapshot)
    finally:
        laden_frei.set()
        netz_frei.set()
    warten(lambda: all(v["ergebnis"] for v in m.zustand()["verbindungen"]))


def test_ttl_kein_doppeltest_und_letzter_status_waehrend_refresh():
    zeit, aufrufe = [0.0], []
    frei = Event()
    frei.set()

    def pruefen(z):
        aufrufe.append(z["id"])
        assert frei.wait(3)
        return {"ok": True}

    m = VerbindungsMonitor(lambda: [ziel("a")], pruefen, uhr=lambda: zeit[0])
    warten(lambda: bool(m.zustand()["verbindungen"]) and
           m.zustand()["verbindungen"][0]["ergebnis"] is not None)
    for _ in range(20):
        m.zustand()
    assert len(aufrufe) == 1
    zeit[0] = 299
    m.zustand()
    assert len(aufrufe) == 1
    frei.clear()
    zeit[0] = 300
    try:
        warten(lambda: m.zustand() and len(aufrufe) == 2)
        v = m.zustand()["verbindungen"][0]
        assert v["prueft"] and v["ergebnis"]["ok"]
        for _ in range(20):
            m.zustand()
        assert len(aufrufe) == 2
    finally:
        frei.set()
    warten(lambda: not m.zustand()["verbindungen"][0]["prueft"])


def test_tokenwechsel_verwirft_spaetes_altergebnis_und_entfernen_entfernt_anzeige():
    ziele, alt_frei, alt_start, alt_fertig = [ziel("a")], Event(), Event(), Event()

    def pruefen(z):
        if z["token"] == "alt":
            alt_start.set()
            assert alt_frei.wait(3)
            alt_fertig.set()
            return {"ok": False}
        return {"ok": True}

    m = VerbindungsMonitor(lambda: list(ziele), pruefen)
    m.zustand()
    assert alt_start.wait(3)
    ziele[:] = [ziel("a", "neu")]
    try:
        warten(lambda: m.zustand()["verbindungen"][0]["ergebnis"] is not None)
        assert m.zustand()["verbindungen"][0]["ergebnis"]["ok"]
    finally:
        alt_frei.set()
    assert alt_fertig.wait(3)
    assert m.zustand()["verbindungen"][0]["ergebnis"]["ok"]
    ziele.clear()
    warten(lambda: not m.zustand()["verbindungen"])


def test_netzfehler_wird_status_ohne_geheimnisse():
    def kaputt(_):
        raise RuntimeError("secret-token")

    m = VerbindungsMonitor(lambda: [ziel("a")], kaputt)
    warten(lambda: bool(m.zustand()["verbindungen"]) and
           m.zustand()["verbindungen"][0]["ergebnis"] is not None)
    snapshot = m.zustand()
    assert snapshot["verbindungen"][0]["ergebnis"]["ok"] is False
    assert "secret-token" not in str(snapshot)


def test_konfigurationsfehler_sichtbar_und_automatisch_wiederholt():
    kaputt = [True]

    def laden():
        if kaputt[0]:
            raise OSError("secret")
        return []

    m = VerbindungsMonitor(laden, lambda _: {})
    warten(lambda: m.zustand()["fehler"])
    assert not m.zustand()["geladen"]
    kaputt[0] = False
    warten(lambda: m.zustand()["geladen"])
    assert not m.zustand()["fehler"]


def test_clients_nutzen_snapshot_zugangsdaten_und_kurzen_timeout(monkeypatch):
    from mqlkiscanner import verbindungs_monitor as modul

    aufrufe = []

    class Quelle:
        def __init__(self, base, **kwargs):
            aufrufe.append((base, kwargs))

        def health(self):
            return {"status": "ok", "tokenRequired": True, "providers": 42}

    class Server(Quelle):
        def ping(self):
            return {"status": "ok"}

    monkeypatch.setattr(modul.downloader_client, "DownloaderClient", Quelle)
    monkeypatch.setattr(modul.tradeserver_client, "TradeserverClient", Server)
    q = modul._pruefen({"art": "quelle", "base_url": "http://quelle", "token": ""})
    assert q == {"ok": True, "eingeschraenkt": True, "anbieter": 42}
    s = modul._pruefen({"art": "tradeserver", "base_url": "http://server", "token": "key"})
    assert s["ok"]
    assert aufrufe == [("http://quelle", {"token": "", "timeout": 3.0}),
                       ("http://server", {"api_key": "key", "timeout": 3.0})]


def test_echte_app_rendert_waehrend_statuskonfiguration_blockiert(monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from mqlkiscanner import verbindungs_monitor, downloader_sync, rest_api

    frei, gestartet = Event(), Event()

    def laden():
        gestartet.set()
        assert frei.wait(30)
        return []

    monitor = VerbindungsMonitor(laden, lambda _: {})
    monkeypatch.setattr(verbindungs_monitor, "zustand", monitor.zustand)
    def kein_synchroner_status(**_):
        raise AssertionError("Netzstatus darf den UI-Pfad nicht blockieren")

    monkeypatch.setattr(downloader_sync, "verbindungs_status", kein_synchroner_status)
    monkeypatch.setattr(rest_api, "start_background", lambda: None)
    try:
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] /
                                   "streamlit_app.py"), default_timeout=15).run()
        assert gestartet.is_set()
        assert not at.exception
        assert at.button(key="scan_start").label == "Full-Scan"
    finally:
        frei.set()
    warten(lambda: not monitor._liest)
