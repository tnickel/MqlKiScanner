# -*- coding: utf-8 -*-
"""Abonnentenstatistik (doc/24): Sync, eigene Messpunkte, Bilanz-Zeilen,
Stufe-B-Variante von client_updates und die Seite als AppTest.

Alle Netzaufrufe sind gefaket (Muster tests/test_client_updates.py); der
conftest weist echte Requests ab und isoliert die Storage in tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_statistik as abo
from mqlkiscanner import client_updates as cu
from mqlkiscanner import db, downloader_client as dc

ROOT = Path(__file__).resolve().parents[1]
SEITE = ROOT / "app_pages" / "abonnenten_statistik.py"


# --- Hilfen ---------------------------------------------------------------

class _FakeClient:
    """DownloaderClient-Fake: Katalog (Paginierung wie /providers) + History."""

    def __init__(self, items, history=None):
        self.items = list(items)
        self.history_map = dict(history or {})
        self.katalog_aufrufe: list[dict] = []

    def katalog(self, *, version=None, limit=500, offset=0, min_subscribers=1, catalog_scope=None):
        self.katalog_aufrufe.append({"limit": limit, "offset": offset,
                                      "minSubscribers": min_subscribers})
        return {"items": self.items[offset:offset + limit],
                "total": len(self.items), "offset": offset, "catalogScope": "full"}

    def history(self, signal_id, version):
        punkte = self.history_map.get((int(signal_id), str(version)))
        if punkte is None:
            raise dc.DownloaderNotFound("kein Verlauf")
        return punkte


def _item(signal_id, name="Signal", version="mql5", subs=6, weeks=None):
    return {"signalId": str(signal_id), "signalName": name, "version": version,
            "url": "", "weeks": weeks, "subscribers": subs,
            "risk": None, "lastUpdated": "2026-10-19T00:00:00"}


def _punkt(vor_tagen: float, subs: int, change=None):
    ts = datetime.now() - timedelta(days=vor_tagen)
    return {"timestamp": ts.isoformat(timespec="seconds"),
            "subscribers": subs, "change": change}


def _quelle(kuerzel: str = "fake") -> dict:
    db.init_db()
    return db.get_quelle(db.add_quelle(kuerzel, f"Test {kuerzel}",
                                       "http://rechner:8199"))


@pytest.fixture
def fake_client(monkeypatch):
    """client_fuer_quelle durch einen Fake ersetzen; Client-Objekt liefern."""
    halter = {}

    def _install(client: _FakeClient):
        halter["client"] = client

        def _fake_client_fuer_quelle(quelle, timeout=None):
            return client
        monkeypatch.setattr(abo.quellen, "client_fuer_quelle",
                            _fake_client_fuer_quelle)
        return client
    return _install


# --- sync_quelle: Spiegelung + eigene Messpunkte --------------------------

def test_sync_quelle_spiegelt_katalog_und_historie(fake_client):
    quelle = _quelle()
    client = fake_client(_FakeClient(
        [_item(1, "Alpha", subs=8), _item(2, "Beta", subs=3)],
        history={(1, "mql5"): [_punkt(30, 5), _punkt(7, 7)]}))
    ergebnis = abo.sync_quelle(quelle)
    assert ergebnis["anzahl"] == 2
    assert ergebnis["abgebrochen"] is None
    # Vollständigkeit gefordert: Übersicht fragt ausdrücklich 0 an.
    assert client.katalog_aufrufe[0]["minSubscribers"] == 0
    reihe = db.get_history(1, "mql5", quelle="fake")
    # Nur die zwei tatsächlich datierten Client-Punkte; Katalogzahl8 belegt
    # keinen zusätzlichen Messzeitpunkt.
    assert len(reihe) == 2 and ergebnis["messpunkte"] == 0
    assert reihe[-1]["subscribers"] == 7
    # Signal 2 hat KEINEN Verlauf beim Client (404) → weiter unbekannt.
    reihe2 = db.get_history(2, "mql5", quelle="fake")
    assert reihe2 == []
    # Katalog-Zeilen stehen der „Alle Signale“-Übersicht zur Verfügung
    katalog_refs = {z["signal_id"] for z in db.katalog_list()}
    assert katalog_refs == {1, 2}


def test_sync_quelle_dedupe_identischer_wert(fake_client):
    quelle = _quelle()
    fake_client(_FakeClient([_item(1, subs=8)],
                            history={(1, "mql5"): [_punkt(2, 8)]}))
    abo.sync_quelle(quelle)
    stand_nach_eins = len(db.get_history(1, "mql5", quelle="fake"))
    abo.sync_quelle(quelle)  # identischer Wert unmittelbar danach
    assert len(db.get_history(1, "mql5", quelle="fake")) == stand_nach_eins


def test_sync_quelle_verbindungstod_bricht_quelle_ab(fake_client):
    quelle = _quelle()
    client = _FakeClient([_item(1, subs=8)])
    original = client.history

    def _history_tot(signal_id, version):
        raise dc.DownloaderConnectionError("Client weg")
    client.history = _history_tot
    fake_client(client)
    ergebnis = abo.sync_quelle(quelle)
    assert ergebnis["abgebrochen"] and "Client weg" in ergebnis["abgebrochen"]
    # Katalog wurde noch übernommen; eigener Messpunkt fehlt (Abbruch vorher)
    assert ergebnis["anzahl"] == 1 and ergebnis["messpunkte"] == 0


def test_sync_teilmenge_und_quellenausfall(fake_client, monkeypatch):
    _quelle("fake")
    db.init_db()
    db.add_quelle("tot", "Offline", "http://rechner:1")  # zweitaktiv, offline
    fake_client(_FakeClient([_item(5, "NurFake", subs=2)]))
    original = abo.quellen.client_fuer_quelle

    def _dispatch(q, timeout=None):
        if db.kanonische_quelle(q["kuerzel"]) == "tot":
            raise dc.DownloaderError("kein Client")
        return original(q, timeout)
    monkeypatch.setattr(abo.quellen, "client_fuer_quelle", _dispatch)
    summary = abo.sync(kuerzels=["fake", "tot"])
    assert set(summary["quellen"]) == {"fake", "tot"}
    assert summary["quellen"]["fake"]["anzahl"] == 1
    assert summary["quellen"]["tot"]["abgebrochen"]


def test_sync_meldet_fortschritt_fuer_ui_balken(fake_client):
    """Nutzer-Wunsch 25.10.: Der Lesephase-Refresh meldet Quelle x/y und
    Historie-Fortschritt an einen Callback (Grundlage für st.progress)."""
    quelle = _quelle("fake")
    fake_client(_FakeClient(
        [_item(i, f"S{i}", subs=i) for i in range(1, 61)],
        history={(i, "mql5"): [_punkt(2, i)] for i in range(1, 61)}))
    meldungen: list[dict] = []
    summary = abo.sync(kuerzels=[quelle["kuerzel"]],
                       on_fortschritt=meldungen.append)
    assert summary["quellen"]["fake"]["anzahl"] == 60
    quellen_meldung = [m for m in meldungen if m["phase"] == "quelle"]
    assert quellen_meldung == [{"phase": "quelle", "kuerzel": "fake",
                                "nr": 1, "von": 1}]
    historie = [m for m in meldungen if m["phase"] == "historie"]
    assert historie[0] == {"phase": "historie", "kuerzel": "fake",
                           "gesamt": 60, "fertig": 0}
    assert historie[-1]["fertig"] == 60
    # In 25er-Schritten plus Endstand: 0, 25, 50, 60
    assert [m["fertig"] for m in historie] == [0, 25, 50, 60]


# --- zeilen(): Bilanz über die vereinte Messreihe --------------------------

def _reihe_seed(quelle="fake"):
    db.store_history_points(1, "mql5", [
        _punkt(31, 4), _punkt(30, 5), _punkt(7, 7), _punkt(0.1, 8)],
        quelle=quelle)
    db.katalog_upsert_many(quelle, [{
        "signal_id": 1, "name": "Alpha", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 8.0, "wochen": 40.0, "risiko": None}])


def test_zeilen_bilanz_und_niemals_falsche_null():
    _reihe_seed()
    zeilen = abo.zeilen()
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z["signal_id"] == 1 and z["name"] == "Alpha"
    assert z["abonnenten"] == 8
    assert z["delta_letzt"] == 1          # 8 - 7 (vorletzter Punkt)
    assert z["delta_7"] == 1              # 8 - 7 (Punkt vor ~7 Tagen)
    assert z["delta_30"] == 3             # 8 - 5 (Punkt vor ~30 Tagen)
    assert z["messpunkte"] == 4 and z["ampel"] is None


def test_zeilen_ein_punkt_ohne_delta_und_nur_katalog():
    db.katalog_upsert_many("fake", [{
        "signal_id": 9, "name": "OhneHistorie", "platform": "mt4", "url": "",
        "version": "mql4", "abonnenten": 2.0, "wochen": None, "risiko": None}])
    zeilen = abo.zeilen()
    z = next(ze for ze in zeilen if ze["signal_id"] == 9)
    assert z["abonnenten"] == 2 and z["delta_letzt"] is None
    assert z["delta_7"] is None and z["delta_30"] is None


def test_zeilen_ampel_nur_anzeige():
    _reihe_seed()
    identity = db.resolve_identity(1, quelle="fake")
    db.store_ampel_verlauf(1, "2026-10-19 10:00:00", "fake", "🟡", 5.0,
                           "Testurteil", None, signal_quelle="fake")
    ampeln = db.letzte_ampeln_je_signal()
    assert ampeln[identity.signal_ref]["ampel"] == "🟡"
    assert abo.zeilen(ampeln=ampeln)[0]["ampel"] == "🟡"


def test_zeilen_messreihe_ohne_metadaten():
    db.store_history_points(77, "pelican", [_punkt(1, 3)], quelle="fake")
    zeilen = abo.zeilen()
    z = next(ze for ze in zeilen if ze["signal_id"] == 77)
    assert z["quelle"] == "fake" and z["abonnenten"] == 3
    assert z["name"]  # Minimalname aus der ID, nie leer


# --- Stufe B: client_updates-Variante ohne Tradelisten ---------------------

class _Antwort:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


@pytest.fixture
def update_transport(monkeypatch):
    """POST-/GET-Fake mit Payload-Capture für die Stufe-B-Parameter."""
    payloads: list[dict] = []

    def _install(status_seq, *, capability=True, post_job="job-1"):
        status_seq = [dict(item) for item in status_seq]
        for item in status_seq:
            item.setdefault("jobId", post_job)

        def fake_get(url, params=None, headers=None, timeout=None):
            if url.endswith("/health"):
                return _Antwort(body={"status": "ok", "abonnentenRefresh": capability})
            if url.endswith("/update/status"):
                return _Antwort(body=status_seq.pop(0)
                                if status_seq else {"state": "idle"})
            raise AssertionError(f"unerwarteter GET: {url}")

        def fake_post(url, json=None, headers=None, timeout=None):
            payloads.append(json or {})
            return _Antwort(body={"jobId": post_job, "status": "gestartet"})
        monkeypatch.setattr(dc.requests, "get", fake_get)
        monkeypatch.setattr(dc.requests, "post", fake_post)
        return payloads
    return _install


def test_starte_alle_updates_abonnenten_variante(update_transport):
    _quelle("fake")
    db.init_db()
    db.add_quelle("andere", "Andere", "http://rechner:8198")
    payloads = update_transport([{"state": "done", "ergebnis": {
        "nurAbonnenten": True, "signaleGeliefert": 10, "tradelistenNeu": 0,
        "tradelistenAktualisiert": 0, "tradelistenFehler": 0,
        "datenstand": "2026-10-20T11:00:00", "hinweise": []}}])
    zustaende = cu.starte_alle_updates(
        {}, log=None, on_fortschritt=None, gestopft=lambda: False,
        bereit_warten_s=0.1, poll_s=0.01, backoff_s=0.01, timeout_s=5.0,
        login_timeout_s=0.3,
        tradelisten=False, katalog_max_alter_h=0.0,
        quellen_filter=["fake"], modus="abonnenten")
    # Nur die gewählte Quelle lief; POST ohne Tradelisten + erzwingend.
    assert set(zustaende) == {"fake"}
    assert zustaende["fake"]["status"] == cu.TEILWEISE
    assert zustaende["fake"]["abonnenten_auswahl_unbestaetigt"] is True
    assert payloads and payloads[0]["tradelisten"] is False
    assert payloads[0]["katalogMaxAlterH"] == 0
    assert payloads[0]["nurAbonnenten"] is True
    assert payloads[0]["target"] == 200
    # Chronik: Modus-Kennzeichnung als erster Hinweis.
    eintrag = db.list_client_updates(limit=5)[0]
    assert eintrag["kuerzel"] == "fake"
    assert eintrag["hinweise"][0] == "Modus: abonnenten"


def test_starte_alle_updates_scan_default_unveraendert(update_transport):
    _quelle("fake")
    payloads = update_transport([{"state": "done", "ergebnis": {
        "signaleGeliefert": 10, "tradelistenNeu": 3,
        "tradelistenAktualisiert": 7, "tradelistenFehler": 0,
        "datenstand": "2026-10-20T11:00:00", "hinweise": []}}])
    cu.starte_alle_updates({"update_katalog_max_alter_h": 48},
                           log=None, on_fortschritt=None,
                           gestopft=lambda: False, bereit_warten_s=0.1,
                           poll_s=0.01, backoff_s=0.01, timeout_s=5.0,
                           login_timeout_s=0.3)
    assert payloads[0]["tradelisten"] is True
    assert payloads[0]["katalogMaxAlterH"] == 48
    eintrag = db.list_client_updates(limit=5)[0]
    assert all(h != "Modus: scan" for h in eintrag["hinweise"])


def _warte_auf_refresh(timeout_s: float = 15.0) -> dict:
    """Bis der Refresh-Thread endgültig fertig ist (wie conftest.warte_auf_lauf)."""
    import time
    ende = time.monotonic() + timeout_s
    while time.monotonic() < ende:
        zustand = abo.refresh_zustand()
        if zustand.get("fertig") and not zustand.get("laeuft"):
            return zustand
        time.sleep(0.05)
    raise AssertionError("Refresh-Thread wurde nicht rechtzeitig fertig")


def test_refresh_runner_stufe_a_liest_und_beendet(fake_client):
    _quelle()
    fake_client(_FakeClient([_item(1, "Alpha", subs=8)],
                            history={(1, "mql5"): [_punkt(3, 6)]}))
    assert abo.starte_refresh(messen=False) is True
    assert abo.refresh_laeuft() is True
    zustand = _warte_auf_refresh()
    assert not abo.refresh_laeuft()
    assert zustand["fehler"] == ""
    assert zustand["summary"]["quellen"]["fake"]["anzahl"] == 1
    assert len(db.get_history(1, "mql5", quelle="fake")) == 1
    assert zustand["lauf_id"].startswith("abo-")
    assert datetime.fromisoformat(zustand["gestartet"]).tzinfo is not None
    assert datetime.fromisoformat(zustand["beendet"]).tzinfo is not None


def test_refresh_laufkennung_erneuert_sich_ohne_alten_fehler_mitzunehmen(monkeypatch):
    monkeypatch.setattr(abo, "sync", lambda **kw: {"quellen": {}, "gesamt": 0})
    assert abo.starte_refresh(messen=False)
    first = _warte_auf_refresh()
    assert abo.starte_refresh(messen=False)
    second = _warte_auf_refresh()
    assert first["lauf_id"] != second["lauf_id"]
    assert second["fehler"] == ""


def test_refresh_anzeige_unterscheidet_datierten_altbeleg_und_frischen_fehler():
    now = datetime.now().astimezone()
    old = {"fertig": True, "laeuft": False, "lauf_id": "abo-old",
           "gestartet": (now - timedelta(hours=3)).isoformat(),
           "beendet": (now - timedelta(hours=2)).isoformat(),
           "summary": {"quellen": {"vant": {"fehler": ["Alter Clientfehler"]}}}}
    archived = abo.refresh_anzeige(old, jetzt=now)
    assert archived["frisch"] is False
    assert archived["kennung"] == "abo-old"
    assert archived["status"] == "mit Fehlern beendet"
    assert archived["beendet"] == old["beendet"]
    current = abo.refresh_anzeige({**old, "lauf_id": "abo-new", "beendet": now.isoformat()}, jetzt=now)
    assert current["frisch"] is True
    assert current["status"] == "mit Fehlern beendet"
    assert abo.refresh_anzeige({"fertig": True, "fehler": "Ohne Zeitbeleg"})["frisch"] is True
    assert abo.refresh_anzeige({"fertig": True, "stopp": True})["status"] == "abgebrochen"
    assert abo.refresh_anzeige({"fertig": True})["status"] == "ohne Ergebnisbeleg beendet"


@pytest.mark.parametrize("age_minutes,expanded", [(120, False), (0, True)])
def test_refresh_abschluss_zeigt_zeit_job_und_historischen_kontext(monkeypatch, age_minutes, expanded):
    now = datetime.now().astimezone()
    finished = (now - timedelta(minutes=age_minutes)).isoformat(timespec="seconds")
    state = {"laeuft": False, "fertig": True, "lauf_id": "abo-historisch",
             "gestartet": finished, "beendet": finished,
             "summary": {"quellen": {"vant": {"anzahl": 200, "fehler": ["Fehler im damaligen Job"]}}},
             "quellen": {"vant": {"job_id": "native-vant-old", "status": "fehler", "geaendert": finished}},
             "logs": ["Historischer Abruf"]}
    monkeypatch.setattr(abo, "refresh_zustand", lambda: state)
    monkeypatch.setattr(abo, "sync", lambda **kw: {})
    at = AppTest.from_file(SEITE, default_timeout=30).run()
    assert not at.exception, at.exception
    body = "\n".join(x.value for kind in ("caption", "warning") for x in getattr(at, kind))
    assert "Abgeschlossener Abonnenten-Refresh" in body
    assert finished in body and "abo-historisch" in body
    assert "native-vant-old" in body
    assert "keine Liveaussage" in body
    assert "FEHLER IN DIESEM LAUF" in body
    result = next(x for x in at.expander if "Ergebnis des abgeschlossenen Refreshs" in x.label)
    assert result.proto.expanded is expanded


def test_refresh_runner_kein_doppelter_start(fake_client):
    _quelle()
    fake_client(_FakeClient([_item(1, subs=1)]))
    assert abo.starte_refresh(messen=False) is True
    assert abo.starte_refresh(messen=False) is False
    _warte_auf_refresh()


# --- Seite (AppTest, nur Render — Auswahl/Refresh bleiben draußen) ---------

def test_seite_leerzustand():
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    info = " ".join(i.value for i in at.info)
    assert "Noch keine Abonnenten-Daten" in info


def test_seite_zeigt_tabelle_tabs_und_filter():
    _reihe_seed()
    db.katalog_upsert_many("fake", [{
        "signal_id": 9, "name": "OhneHistorie", "platform": "mt4", "url": "",
        "version": "mql4", "abonnenten": 2.0, "wochen": None, "risiko": None},
        {"signal_id": 10, "name": "NullAbo", "platform": "mt4", "url": "",
         "version": "mql4", "abonnenten": 0.0, "wochen": None, "risiko": None}])
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 3  # Beobachten + Alle + Quelle fake
    tabelle = at.dataframe(key="abonnenten_tabelle_alle")
    df = tabelle.value
    # Nutzer-Vorgabe: mindestens 1 Abonnent — die 0-Abonnenten-Zeile ist raus.
    assert set(df["ID"].tolist()) == {1, 9}
    assert df.iloc[0]["Δ 30 Tage"] == 3
    assert at.dataframe(key="abonnenten_tabelle_fake") is not None
    assert at.text_input(key="abonnenten_suche") is not None
    assert at.number_input(key="abonnenten_min_abo") is not None


def test_seite_zeilenauswahl_zeigt_verlauf():
    """Userentwicklung (MqlDownloader-Verlaufsfenster-Äquivalent): Zeilen-
    auswahl öffnet Chart + Messpunkte. Programmatische Selektion ist der
    offizielle Weg (siehe _ausgewaehlte_zeile-Docstring)."""
    _reihe_seed()
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception
    # Zeile 0 = Alpha (höchster Δ30): Unterzeile + Chart + Messpunkte-Tabelle
    koerper = " ".join(s.value for s in at.subheader)
    assert "Alpha" in koerper
    assert len(at.get("plotly_chart")) == 1  # Verlaufs-Chart der Entwicklung
    expander_titel = [e.label for e in at.expander]
    assert any("Messpunkte" in (t or "") for t in expander_titel)


# --- Sparkline „Verlauf 30 T" (Nutzer-Wunsch 20.10., wie MqlDownloader) ----

def test_sparkline_png_grundregeln():
    assert abo.sparkline_png([5], trend=1) is None            # 1 Punkt: keine Kurve
    assert abo.sparkline_png([], trend=0) is None
    steigt = abo.sparkline_png([1, 2, 3, 4], trend=1)
    faellt = abo.sparkline_png([4, 3, 2, 1], trend=-1)
    flach = abo.sparkline_png([3, 3, 3], trend=0)
    for bild in (steigt, faellt, flach):
        assert bild is not None and bild[:8] == b"\x89PNG\r\n\x1a\n"  # PNG-Magic
    assert steigt != faellt != flach                          # Trend färbt die Kurve


def test_zeilen_verlauf30_fenster_relativ_zum_neuesten_punkt():
    # Punkte vor 40/20/10/0,1 Tagen: Fenster = neuester Punkt − 30 Tage
    # → der 40-Tage-Punkt fällt raus, die übrigen drei bleiben.
    db.store_history_points(3, "mql5", [
        _punkt(40, 4), _punkt(20, 5), _punkt(10, 7), _punkt(0.1, 8)],
        quelle="fake")
    db.katalog_upsert_many("fake", [{
        "signal_id": 3, "name": "Fenster", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 8.0, "wochen": None, "risiko": None}])
    z = next(ze for ze in abo.zeilen() if ze["signal_id"] == 3)
    werte = [wert for _, wert in z["verlauf30"]]
    assert werte == [5, 7, 8]


def test_seite_hat_sparkline_spalte():
    _reihe_seed()
    db.katalog_upsert_many("fake", [{
        "signal_id": 9, "name": "OhneHistorie", "platform": "mt4", "url": "",
        "version": "mql4", "abonnenten": 2.0, "wochen": None, "risiko": None}])
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    df = at.dataframe(key="abonnenten_tabelle_alle").value
    assert "Verlauf 30 T" in df.columns
    alpha = df[df["ID"] == 1].iloc[0]
    assert str(alpha["Verlauf 30 T"]).startswith("data:image/png;base64,")
    ohne = df[df["ID"] == 9].iloc[0]
    assert ohne["Verlauf 30 T"] is None or pd.isna(ohne["Verlauf 30 T"])


# --- Δ 7 Tage % (Nutzer-Wunsch 20.10.: Relative statt nur absolute) --------

def test_zeilen_delta7_prozent():
    # Basis 8 (Punkt vor ~7 Tagen), aktuell 12 → +4 = +50,0 %
    db.store_history_points(4, "mql5", [_punkt(9, 8), _punkt(0.1, 12)],
                            quelle="fake")
    # Basis 0: Prozentwert bewusst undefiniert (aus 0 wachsen)
    db.store_history_points(5, "mql5", [_punkt(7, 0), _punkt(0.1, 5)],
                            quelle="fake")
    db.katalog_upsert_many("fake", [
        {"signal_id": 4, "name": "Prozent", "platform": "mt5", "url": "",
         "version": "mql5", "abonnenten": 12.0, "wochen": None, "risiko": None},
        {"signal_id": 5, "name": "VonNull", "platform": "mt5", "url": "",
         "version": "mql5", "abonnenten": 5.0, "wochen": None, "risiko": None}])
    zeilen = {z["signal_id"]: z for z in abo.zeilen()}
    assert zeilen[4]["delta_7"] == 4
    assert zeilen[4]["delta_7_pct"] == 50.0
    assert zeilen[5]["delta_7"] == 5
    assert zeilen[5]["delta_7_pct"] is None  # Basis 0 — nie geteilt durch 0
    # Konsistenz mit der etablierten _bilanz-Regel (gleicher Vergleichspunkt)
    assert zeilen[4]["delta_7"] / 8 * 100 == pytest.approx(zeilen[4]["delta_7_pct"])


def test_seite_hat_delta7_prozent_spalte():
    _reihe_seed()  # 7-Tage-Basis 7, aktuell 8 → +1 = +14,3 %
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    df = at.dataframe(key="abonnenten_tabelle_alle").value
    assert "Δ 7 Tage %" in df.columns
    alpha = df[df["ID"] == 1].iloc[0]
    assert alpha["Δ 7 Tage %"] == pytest.approx(14.3)


# --- Zuwachs-Ampel je Broker (Nutzer-Wunsch 20.10.: broker-relativ) --------

def _ampel_zeile(quelle, abonnenten, delta_7_pct):
    return {"quelle": quelle, "abonnenten": abonnenten, "delta_7_pct": delta_7_pct}


def test_zuwachs_stufen_trimmt_ausreisser_und_trennt_quellen():
    # vant: 20 Werte 0..9 % + EIN Ausreisser +1000 % -> gestutztes Ø ≈ Ø ohne ihn
    zeilen = ([_ampel_zeile("vant", 10, float(i)) for i in range(10)]
              + [_ampel_zeile("vant", 10, 1000.0)]
              + [_ampel_zeile("mql5", 5, -20.0), _ampel_zeile("mql5", 5, 1.0)])
    zeilen += [_ampel_zeile("vant", 0, 50.0)]  # 0 Abonnenten zaehlt NICHT
    stufen = abo.zuwachs_stufen(zeilen)
    assert stufen["vant"]["anzahl"] == 11
    assert stufen["vant"]["durchschnitt_pct"] == pytest.approx(
        sum(range(10)) / 10, abs=0.01)  # Ausreisser +1000 gekappt
    assert stufen["mql5"]["durchschnitt_pct"] < 0


def test_zuwachs_ampel_grenzen_und_mql5_fall():
    # positiver Ø (Pelican-artig): gruen ab Ø, gelb darunter
    assert abo.zuwachs_ampel(20.0, 19.7) == "gruen"
    assert abo.zuwachs_ampel(19.6, 19.7) == "gelb"
    assert abo.zuwachs_ampel(0.5, 19.7) == "gelb"
    # negativer Ø (MQL5-artig): Wachstum ist gruen, NIEMALS Verlierer gruen
    assert abo.zuwachs_ampel(1.0, -8.0) == "gruen"
    assert abo.zuwachs_ampel(-5.0, -8.0) == "orange"  # "ueber Ø" aber Verlust
    # Verluststufen und Neutralitaet
    assert abo.zuwachs_ampel(-10.0, 19.7) == "orange"
    assert abo.zuwachs_ampel(-10.1, 19.7) == "rot"
    assert abo.zuwachs_ampel(0.0, 19.7) is None      # unverändert
    assert abo.zuwachs_ampel(None, 19.7) is None     # kein Vergleichspunkt


def test_mit_zuwachs_ampel_reichert_zeilen_an():
    # 4 Werte [50, 40, 10, 1]: 5%-Stutzen kappt den Top-Wert → Ø = (40+10+1)/3 = 17
    zeilen = [_ampel_zeile("pelik", 100, 50.0), _ampel_zeile("pelik", 100, 40.0),
              _ampel_zeile("pelik", 100, 10.0), _ampel_zeile("pelik", 100, 1.0),
              _ampel_zeile("pelik", 100, None)]
    stufen = abo.mit_zuwachs_ampel(zeilen)
    assert zeilen[0]["zuwachs_ampel"] == "gruen"   # 50 >= Ø (17.0)
    assert zeilen[0]["quelle_durchschnitt_pct"] == pytest.approx(17.0)
    assert zeilen[2]["zuwachs_ampel"] == "gelb"    # 10 < Ø, aber wachsend
    assert zeilen[4]["zuwachs_ampel"] is None
    assert stufen["pelik"]["anzahl"] == 4


def test_seite_hat_zuwachs_ampel_spalte():
    _reihe_seed()  # Alpha: delta_7=1, Basis 7 → +14,3 %
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    df = at.dataframe(key="abonnenten_tabelle_alle").value
    assert "Ampel (Zuwachs)" in df.columns
    alpha = df[df["ID"] == 1].iloc[0]
    assert alpha["Ampel (Zuwachs)"] == "🟢"  # einziges positives Signal = über Ø


# --- Beobachtungsliste (Nutzer-Wunsch 20.10.) ------------------------------

def test_beobachtung_db_und_quellentrennung():
    ident = db.resolve_identity(1, quelle="fake", create=True)
    db.setze_beobachtung(1, True, quelle="fake")
    assert ident.signal_ref in db.list_beobachtungen()
    db.setze_beobachtung(1, False, quelle="fake")
    assert ident.signal_ref not in db.list_beobachtungen()
    # Gleiche externe ID in anderer Quelle ist eine UNABHÄNGIGE Identität
    db.add_quelle("zwei", "Zweite", "http://rechner:8299")
    db.setze_beobachtung(1, True, quelle="fake")
    db.setze_beobachtung(1, True, quelle="zwei")
    refs = db.list_beobachtungen()
    assert db.resolve_identity(1, quelle="fake").signal_ref in refs
    assert db.resolve_identity(1, quelle="zwei").signal_ref in refs
    db.setze_beobachtung(1, False, quelle="fake")
    assert db.resolve_identity(1, quelle="zwei").signal_ref in db.list_beobachtungen()


def test_seite_beobachten_tab_zeigt_auch_0_abonnenten():
    _reihe_seed()
    db.katalog_upsert_many("fake", [{
        "signal_id": 10, "name": "NullAbo", "platform": "mt4", "url": "",
        "version": "mql4", "abonnenten": 0.0, "wochen": None, "risiko": None}])
    db.setze_beobachtung(10, True, quelle="fake")
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 3  # Beobachten + Alle + fake
    df_beob = at.dataframe(key="abonnenten_tabelle_beobachten").value
    # 0-Abonnent-Signal ist im Beobachten-Tab sichtbar (Filter bewusst aus)
    assert set(df_beob["ID"].tolist()) == {10}
    assert df_beob.iloc[0]["Beob."] == "👁"
    # ... aber wie gefordert NICHT im Alle-Tab (Min.-Abonnenten-Default 1)
    df_alle = at.dataframe(key="abonnenten_tabelle_alle").value
    assert 10 not in set(df_alle["ID"].tolist())


def test_seite_beobachten_button_ueber_detail():
    _reihe_seed()
    ident = db.resolve_identity(1, quelle="fake", create=True)
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception
    knopf = at.button(key=f"abonnenten_beob_{ident.signal_ref}_0")
    knopf.click().run()
    assert ident.signal_ref in db.list_beobachtungen()


# --- Mehrfachauswahl → Sammel-Beobachten (Nutzer-Wunsch 20.10. abends) -----

def test_seite_mehrfachauswahl_sammel_beobachten():
    _reihe_seed()  # Alpha (ID 1) ist Zeile 0 der Sortierung
    db.katalog_upsert_many("fake", [{
        "signal_id": 11, "name": "Beta", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 3.0, "wochen": None, "risiko": None}])
    refs = {sid: db.resolve_identity(sid, quelle="fake", create=True).signal_ref
            for sid in (1, 11)}
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0, 1]}}
    at.run()
    assert not at.exception
    # Keine Einzel-Detailansicht bei Mehrfachauswahl, sondern Sammelleiste
    assert not any("Beta" in s.value for s in at.subheader)
    at.button(key="abonnenten_beob_bulk_add").click().run()
    beobachtet = db.list_beobachtungen()
    assert refs[1] in beobachtet and refs[11] in beobachtet
    # Gemischte Auswahl: nur die bereits beobachteten entfernen
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0, 1]}}
    at.run()
    at.button(key="abonnenten_beob_bulk_del").click().run()
    assert db.list_beobachtungen() == set()


def test_zeilen_erhalten_berichte_aber_datenseite_blendet_sie_aus():
    # workflow_zeilen tragen die Analyse-Felder (list_catalog-Form) + ref
    ident = db.resolve_identity(77, quelle="fake", create=True)
    zeilen = abo.zeilen(workflow_zeilen=[{
        "signal_ref": ident.signal_ref, "signal_id": 77, "quelle": "fake",
        "name": "Mit", "platform": "mt5", "version": "mql5", "url": "",
        "abonnenten": 5.0, "gesamtbericht": "x", "trade_analyse": "y"}],
        katalog_zeilen=[], history_punkte=[], ampeln={})
    assert zeilen[0]["berichte"] == 2
    # Seite: Katalogzeile + Historie säen, damit die Tabelle rendert
    db.katalog_upsert_many("fake", [{
        "signal_id": 77, "name": "Mit", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 5.0, "wochen": None, "risiko": None}])
    db.store_history_points(77, "mql5", [_punkt(2, 4), _punkt(0.1, 5)],
                            quelle="fake")
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    df = at.dataframe(key="abonnenten_tabelle_alle").value
    assert "Ber." not in df.columns
    assert set(df["ID"].tolist()) == {77}


def test_dokumente_ausgeblendet_und_delta_spalten_weiterhin_numerisch(tmp_path):
    """Datenseite blendet erhaltene PDFs aus; unbekannte Δ-Werte bleiben leer."""
    db.store_downloader_report(1, "mql5", "mqlki-test.pdf", str(tmp_path / "r.pdf"),
                               quelle="fake")
    (tmp_path / "r.pdf").write_bytes(b"%PDF-1.4 test")
    _reihe_seed()
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    df = at.dataframe(key="abonnenten_tabelle_alle").value
    assert "Doku" not in df.columns
    assert (tmp_path / "r.pdf").exists()
    # None-Fix: Δ 30 Tage ist float (NaN → leere Zelle), nicht Int64
    assert str(df["Δ 30 Tage"].dtype) != "Int64"
    assert df["Δ 30 Tage"].isna().all() or (df["Δ 30 Tage"] == 3).any()
    # Zeilenauswahl öffnet keine historischen Dokumente mehr.
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    expander = [e.label for e in at.expander]
    assert not any("Dokumente" in (t or "") for t in expander)


def test_hilfsspalten_sind_alle_ausgeblendet():
    """Interne Referenz/Stilmarker bleiben verborgen; Dokumenten-JSON entfällt."""
    _reihe_seed()
    seiten_quelle = SEITE.read_text(encoding="utf-8")
    for hilfs in ("'_ref': None", "'_ampel': None"):
        assert hilfs in seiten_quelle
    assert "'_doku':" not in seiten_quelle
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception


def test_dokumente_auch_bei_zeilenauswahl_verborgen_und_dateien_erhalten(tmp_path):
    """Historische Dateien bleiben erhalten, ohne PDF-Bedienung auf Stufe 1."""
    pdf = tmp_path / "rep.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    # ZWEI Signale; Doku NUR bei Signal 1 (NICHT die letzte Zeile)
    db.store_downloader_report(1, "mql5", "mqlki-signal1.pdf", str(pdf),
                               quelle="fake")
    _reihe_seed()
    db.katalog_upsert_many("fake", [{
        "signal_id": 3, "name": "OhneDoku", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 4.0, "wochen": None, "risiko": None}])
    db.store_history_points(3, "mql5", [_punkt(2, 3), _punkt(0.1, 4)],
                            quelle="fake")
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not at.exception
    # Zeile 0 in der Sortierung = OhneDoku (höchster Δ30 fehlt … Alpha #1
    # hat Δ30=3, OhneDoku None → Alpha ist Zeile 0)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception
    expander = [e.label for e in at.expander]
    dok = [t for t in expander if "Dokumente" in (t or "")]
    assert not dok, expander
    assert pdf.exists(), "Historical artifacts remain saved"
    assert not any(str(button.key).startswith("abonnenten_doku_") for button in at.button)


def test_datenseite_bietet_keinen_dokumenten_download(monkeypatch):
    _reihe_seed()
    ident = db.resolve_identity(1, quelle="fake", create=True)
    import mqlkiscanner.downloader_sync as dsync
    aufgerufen = []
    monkeypatch.setattr(dsync, "sync_reports",
                        lambda sid, platform, **kw: aufgerufen.append(
                            (sid, platform, kw)) or ["/x/neu.pdf"])
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not any(str(button.key).startswith("abonnenten_doku_") for button in at.button)
    assert aufgerufen == []


def test_beobachten_ohne_dokumenten_batch(monkeypatch):
    _reihe_seed()
    db.setze_beobachtung(1, True, quelle="fake")
    import mqlkiscanner.downloader_sync as dsync
    aufgerufen = []
    monkeypatch.setattr(dsync, "sync_reports",
                        lambda sid, platform, **kw: aufgerufen.append(sid) or [])
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.run()
    assert not any(button.key == "abonnenten_doku_batch" for button in at.button)
    assert aufgerufen == []


def test_berichte_mergen_bei_katalog_und_workflow_zeile():
    """Regression (Nutzer-Befund 20.10.): Gescannte Signale haben Katalog-
    UND Workflow-Zeile — die Katalogzeile trägt keine Analyse-Felder, sie
    dürfen die Workflow-Analysen nicht überdecken („Ber." blieb leer)."""
    db.katalog_upsert_many("fake", [{
        "signal_id": 1, "name": "Alpha", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 8.0, "wochen": None, "risiko": None}])
    db.store_history_points(1, "mql5", [_punkt(2, 7), _punkt(0.1, 8)],
                            quelle="fake")
    ident = db.resolve_identity(1, quelle="fake", create=True)
    zeilen = abo.zeilen(workflow_zeilen=[{
        "signal_ref": ident.signal_ref, "signal_id": 1, "quelle": "fake",
        "name": "Alpha", "platform": "mt5", "version": "mql5", "url": "",
        "abonnenten": 8.0, "gesamtbericht": "x", "tiefenanalyse": "y"}])
    z = zeilen[0]
    assert z["berichte"] == 2
    assert z["name"] == "Alpha" and z["abonnenten"] == 8  # Rest unangetastet


def test_trades_csv_export_button(tmp_path, monkeypatch):
    """Nutzer-Wunsch 20.10.: Detail → „Trades als CSV“ — Lade-Klick füllt
    den Cache-Pfad, danach erscheint der Download-Button."""
    import mqlkiscanner.katalog as katalog_mod
    _reihe_seed()
    ident = db.resolve_identity(1, quelle="fake", create=True)
    csv_pfad = tmp_path / "trades.csv"
    csv_pfad.write_text("Time;Type;Volume\n", encoding="utf-8")
    monkeypatch.setattr(katalog_mod, "lade_signal_daten",
                        lambda result, log=None, **kw:
                        (str(csv_pfad), True))
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception
    expander = [e.label for e in at.expander]
    assert any("Trades als CSV" in (t or "") for t in expander)
    at.button(key=f"abonnenten_trades_laden_{ident.signal_ref}").click()
    # Falle 28: Injizierte Selection überlebt nur bis zur Materialisierung —
    # für den Rerun erneut setzen (im Browser hält Streamlit sie selbst).
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception
    # AppTest-SessionState hat in 1.63 kein .get — subscript mit KeyError.
    try:
        st_pfad = at.session_state[f"abonnenten_trades_pfad_{ident.signal_ref}"]
    except KeyError:
        st_pfad = None
    assert st_pfad and Path(st_pfad).exists()
    # st.download_button ist ein EIGENER AppTest-Elementtyp (nicht at.button)
    dl_keys = [str(x.key) for x in at.get("download_button")]
    assert f"abonnenten_trades_dl_{ident.signal_ref}" in dl_keys


def test_trades_csv_export_fehler_ehrlich(tmp_path, monkeypatch):
    import mqlkiscanner.katalog as katalog_mod
    from mqlkiscanner import downloader_client as _dc
    _reihe_seed()
    ident = db.resolve_identity(1, quelle="fake", create=True)

    def _fail(result, log=None, **kw):
        raise _dc.DownloaderNotFound("Quelle liefert keine Trades")
    monkeypatch.setattr(katalog_mod, "lade_signal_daten", _fail)
    at = AppTest.from_file(SEITE, default_timeout=30)
    at.session_state["abonnenten_tabelle_alle"] = {"selection": {"rows": [0]}}
    at.run()
    at.button(key=f"abonnenten_trades_laden_{ident.signal_ref}").click().run()
    assert not at.exception
    assert any("Trades nicht ladbar" in w.value for w in at.warning)


def test_berichte_zaehler_unabhaengig_von_signals_zeile():
    """Regression (Nutzer-Befund 20.10., „nichts refreshed"): Batch-
    Tiefenanalysen von KATALOG-Signalen (ohne signals-Zeile) müssen in der
    Ber.-Spalte sichtbar sein — analyses_zaehler_alle liest ohne JOIN."""
    # Katalog + Historie, aber KEINE signals-Zeile, KEINE Workflow-Zeile:
    db.katalog_upsert_many("fake", [{
        "signal_id": 88, "name": "NurKatalog", "platform": "mt5", "url": "",
        "version": "mql5", "abonnenten": 5.0, "wochen": None, "risiko": None}])
    db.store_history_points(88, "mql5", [_punkt(2, 4), _punkt(0.1, 5)],
                            quelle="fake")
    ident = db.resolve_identity(88, quelle="fake", create=True)
    # Analysen-Eintrag direkt (wie store_analysis ihn anlegt):
    with __import__("contextlib").closing(
            __import__("sqlite3").connect(
                __import__("mqlkiscanner.config", fromlist=["DATA_DIR"]).DATA_DIR
                / "mqlkiscanner.db")) as conn:
        conn.execute("INSERT INTO analyses (signal_ref, kind, model, tokens, "
                     "text, created_at, basis) VALUES (?,?,?,?,?,?,?)",
                     (ident.signal_ref, "tiefenanalyse", "glm-5.3", 40000,
                      "Analysetext", "2026-10-20 15:00:00", "basis"))
        conn.commit()
    zaehler = db.analyses_zaehler_alle()
    assert zaehler[ident.signal_ref].get("tiefenanalyse")
    zeilen = abo.zeilen(berichte_zaehler=zaehler, workflow_zeilen=[])
    z = next(ze for ze in zeilen if ze["signal_id"] == 88)
    assert z["berichte"] == 1


def test_ki_batch_verweigert_bei_fehlender_vorlage(monkeypatch):
    """Nutzer-Regel 20.10.: Fehlende Berichtsvorlage → SOFORTiges Hinweis-
    Fenster (False + Pfad), kein stiller Default-Ersatz, kein Lauf."""
    from mqlkiscanner.llm import prompts as llm_prompts
    _quelle()
    monkeypatch.setattr(llm_prompts, "PROMPT_FILES", {
        "tiefenanalyse": llm_prompts.PROMPTS_DIR / "fehlt" / "tiefenanalyse.md"})
    from mqlkiscanner import tiefen_batch
    ok, meldung = tiefen_batch.batch_starten([])
    assert ok is False
    assert "Berichtsvorlage(n) fehlen" in meldung
    assert "tiefenanalyse.md" in meldung and "Zurücksetzen" in meldung


def test_zaehlerrefresh_alter_client_startet_keinen_grossen_lauf(update_transport):
    _quelle("fake")
    payloads = update_transport([], capability=False)
    result = cu.starte_alle_updates({}, bereit_warten_s=0.1, poll_s=0.01,
        tradelisten=False, katalog_max_alter_h=0, modus="abonnenten")
    assert payloads == []
    assert result["fake"]["status"] == cu.NICHT_UNTERSTUETZT


@pytest.mark.parametrize("ergebnis", [
    {"signaleGeliefert": 200},
    {"nurAbonnenten": True, "signaleGeliefert": 201},
    {"nurAbonnenten": True, "signaleGeliefert": 200, "katalogUebersprungen": True},
])
def test_zaehlerrefresh_lehnt_falschen_abschluss_ab(update_transport, ergebnis):
    _quelle("fake")
    update_transport([{"state": "done", "ergebnis": ergebnis}])
    result = cu.starte_alle_updates({}, bereit_warten_s=0.1, poll_s=0.01,
        tradelisten=False, katalog_max_alter_h=0, modus="abonnenten")
    assert result["fake"]["status"] == cu.FEHLER


def test_refresh_fehlende_frischmessung_bleibt_im_endergebnis(monkeypatch):
    _quelle("fake")
    monkeypatch.setattr(cu, "starte_alle_updates", lambda *a, **kw: {
        "fake": {"status": cu.NICHT_UNTERSTUETZT, "fehler": "Client aktualisieren"}})
    monkeypatch.setattr(abo, "sync", lambda **kw: {
        "quellen": {"fake": {"anzahl": 200, "fehler": []}}, "gesamt": 200})
    assert abo.starte_refresh(messen=True)
    result = _warte_auf_refresh()
    assert result["summary"]["quellen"]["fake"]["fehler"] == [
        "Frischmessung fehlgeschlagen: Client aktualisieren"]


def test_refresh_ausnahme_beendet_thread_ohne_lock_deadlock(monkeypatch):
    def broken(**kw):
        raise RuntimeError("Testfehler")
    monkeypatch.setattr(abo, "sync", broken)
    assert abo.starte_refresh(messen=False)
    result = _warte_auf_refresh(timeout_s=2)
    assert "Testfehler" in result["fehler"]


@pytest.mark.parametrize("post_job,status_job", [("", "job-1"), ("job-1", ""), ("job-1", "other-job")])
def test_zaehlerrefresh_braucht_identische_job_id(update_transport, post_job, status_job):
    _quelle("fake")
    update_transport([{"jobId": status_job, "state": "done", "ergebnis": {
        "nurAbonnenten": True, "signaleGeliefert": 200}}], post_job=post_job)
    result = cu.starte_alle_updates({}, bereit_warten_s=0.1, poll_s=0.01,
        tradelisten=False, katalog_max_alter_h=0, modus="abonnenten")
    assert result["fake"]["status"] == cu.FEHLER
