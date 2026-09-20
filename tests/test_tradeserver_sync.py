# -*- coding: utf-8 -*-
"""Tradeserver-Sync: Payload-Aufbau, Dokumente, Protokoll-Ablauf, Invarianten.

Alle Netzaufrufe laufen über Fake-Clients — der conftest weist echte
Requests ab. Grundregel des Syncs (wie beim MqlDownloader-Abgleich): er
überträgt nur Daten und bewertet nie neu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mqlkiscanner import config, db, tradeserver_client, tradeserver_sync
from mqlkiscanner.pdf_reports import materialize_result_pdfs
from mqlkiscanner.pipeline import ScanResult


def _result(**kwargs) -> ScanResult:
    """Typischer Live-Katalogeintrag für Mapping- und Sync-Tests."""
    werte = dict(
        id=2349227, name="Gold Spike", platform="MT5",
        ampel="🟢", score=3.456, urteil="Kandidat mit bewiesenem Stop",
        stop_nachweis="bewiesen (MT4-Orderbuch)", stop_evidence="direct",
        trading_dd_pct=8.11, dd_equity_pct=3.8, ertrag_monat_pct=6.24,
        gesamtbericht="Text des Gesamtberichts", gesamtbericht_at="2026-09-20 10:00:00",
        trades_sha256="a" * 64, tiefenanalyse="", source_kind="live",
    )
    werte.update(kwargs)
    return ScanResult(**werte)


@pytest.fixture(autouse=True)
def _frische_db():
    """Schema anlegen und Sync-Cache/Caches leer halten."""
    db.init_db()
    tradeserver_sync.status_cache_leeren()
    yield


# --- Tabellen-Payload -----------------------------------------------------

def test_signal_zeilen_abbildung_und_rundung():
    zeilen = tradeserver_sync.signal_zeilen([_result()], fresh_ids={2349227})
    assert len(zeilen) == 1
    zeile = zeilen[0]
    assert zeile["signalId"] == 2349227
    assert zeile["name"] == "Gold Spike"
    assert zeile["ampel"] == "🟢"
    assert zeile["score"] == 3.46          # gerundet auf 2 Stellen
    assert zeile["stop"] == "bewiesen (MT4-Orderbuch)"
    assert zeile["stopEvidence"] == "direct"
    assert zeile["berichtVom"] == "2026-09-20 10:00:00"
    assert zeile["docsBerichte"] == 1      # nur gesamtbericht gesetzt
    assert zeile["docsTiefenanalyse"] == 0
    assert zeile["docsDownloader"] == 0
    assert zeile["url"].endswith("/signals/2349227")
    assert zeile["stand"] == "NEU"


def test_signal_zeilen_ohne_frische_ids_ohne_neu_markierung():
    zeile = tradeserver_sync.signal_zeilen([_result()])[0]
    assert zeile["stand"] == ""


def test_signal_zeilen_tiefenanalyse_zaehlt_gelb():
    zeile = tradeserver_sync.signal_zeilen(
        [_result(tiefenanalyse="Ganz lange Analyse")])[0]
    assert zeile["docsBerichte"] == 1
    assert zeile["docsTiefenanalyse"] == 1


# --- Dokumente sammeln ----------------------------------------------------

def test_dokumente_sammeln_eigene_berichte_und_downloader():
    result = _result()
    db.store_downloader_report(2349227, "mql5", "testreport.pdf",
                               str(config.DOWNLOADER_DIR / "2349227" / "reports"
                                   / "mql5" / "testreport.pdf"),
                               size_bytes=10, last_modified="2026-09-19")
    (config.DOWNLOADER_DIR / "2349227" / "reports" / "mql5").mkdir(
        parents=True, exist_ok=True)
    (config.DOWNLOADER_DIR / "2349227" / "reports" / "mql5" / "testreport.pdf"
     ).write_bytes(b"%PDF-1.4 downloader")

    dokumente, fehler = tradeserver_sync.dokumente_sammeln([result])
    keys = [d["docKey"] for d in dokumente]
    assert "signal/2349227/03-gesamtbericht.pdf" in keys
    assert "signal/2349227/downloader/mql5/testreport.pdf" in keys
    eigene = next(d for d in dokumente if d["group"] == "eigene")
    assert eigene["kind"] == "gesamtbericht"
    assert eigene["sizeBytes"] > 0
    assert Path(eigene["path"]).is_file()
    assert fehler == []


def test_dokumente_sammeln_portfolio():
    dokumente, fehler = tradeserver_sync.dokumente_sammeln(
        [], portfolio={"text": "Portfolio-Text", "created_at": "2026-09-20 11:00:00",
                       "model": "glm-5.3"})
    assert [d["docKey"] for d in dokumente] == ["portfolio/portfolio-gesamtbericht.pdf"]
    assert dokumente[0]["group"] == "portfolio"
    assert fehler == []


def test_dokumente_sammeln_uebergross_wird_vermerkt():
    gross = config.DOWNLOADER_DIR / "2349227" / "reports" / "mql5" / "gross.pdf"
    gross.parent.mkdir(parents=True, exist_ok=True)
    gross.write_bytes(b"x" * (tradeserver_sync._MAX_DOC_BYTES + 1))
    db.store_downloader_report(2349227, "mql5", "gross.pdf", str(gross))
    dokumente, fehler = tradeserver_sync.dokumente_sammeln([_result()])
    assert dokumente == [] or all("gross" not in d["docKey"] for d in dokumente)
    assert any("zu groß" in zeile for zeile in fehler)


# --- Protokoll-Ablauf mit Fake-Client -------------------------------------

class _FakeClient:
    """Zeichnet den Protokoll-Ablauf auf; Inventar steuerbar."""

    def __init__(self, inventar: dict[str, str] | None = None,
                 fehler_bei: str | None = None):
        self.inventar = inventar or {}
        self.fehler_bei = fehler_bei
        self.aufrufe: list[tuple[str, object]] = []
        self.base = "http://server:8080"

    def _vielleicht_fehler(self, schritt):
        if self.fehler_bei == schritt:
            raise tradeserver_client.TradeserverConnectionError("Server weg")

    def ping(self):
        self.aufrufe.append(("ping", None))
        return {"status": "ok", "service": "MqlTradeMonitor", "kiscannerApi": "v1"}

    def register(self, signal_count=0):
        self._vielleicht_fehler("register")
        self.aufrufe.append(("register", signal_count))
        return {"status": "ok", "runId": 42, "serverTime": "2026-09-20 12:00:00",
                "documents": [{"docKey": k, "sha256": v}
                              for k, v in self.inventar.items()],
                "signalIds": []}

    def signals(self, zeilen):
        self._vielleicht_fehler("signals")
        self.aufrufe.append(("signals", zeilen))
        return {"status": "ok", "stored": len(zeilen), "deleted": 0}

    def document(self, dokument):
        self._vielleicht_fehler("document")
        self.aufrufe.append(("document", dokument["docKey"]))
        assert dokument["contentBase64"], "Upload ohne Inhalt"
        assert "path" not in dokument, "lokaler Pfad darf nicht übertragen werden"
        return {"status": "ok", "stored": True}

    def complete(self, **statistik):
        self._vielleicht_fehler("complete")
        self.aufrufe.append(("complete", statistik))
        return {"status": "ok"}

    def abort(self, reason=""):
        self.aufrufe.append(("abort", reason))
        return {"status": "ok"}

    def schritt_namen(self):
        return [name for name, _ in self.aufrufe]


def _eigene_sha(result) -> str:
    pfade = materialize_result_pdfs(result)
    return db.file_sha256(str(pfade["gesamtbericht"]))


def test_sync_alle_happy_path_mit_diff():
    result = _result()
    client = _FakeClient(inventar={
        "signal/2349227/03-gesamtbericht.pdf": _eigene_sha(result)})
    fortschritt: list[str] = []
    summary = tradeserver_sync.sync_alle(
        [result], fresh_ids={2349227}, client=client,
        progress=lambda done, total, label: fortschritt.append(label))

    assert summary["abgebrochen"] is None
    assert summary["signale"] == 1
    assert summary["gespeichert"] == 1
    assert summary["uebersprungen"] == 1      # Gesamtbericht per SHA erkannt
    assert summary["uebertragen"] == 0
    assert client.schritt_namen()[:2] == ["register", "signals"]
    assert client.schritt_namen()[-1] == "complete"
    stats = client.aufrufe[-1][1]
    assert stats["signals"] == 1 and stats["uploaded"] == 0 and stats["skipped"] == 1
    assert fortschritt, "Fortschritt wurde nicht gemeldet"


def test_sync_alle_uebertraegt_neue_dokumente_mit_inhalt():
    client = _FakeClient()
    summary = tradeserver_sync.sync_alle([_result()], client=client)
    assert summary["uebertragen"] == 1
    assert summary["bytes"] > 0
    assert client.schritt_namen() == ["register", "signals", "document", "complete"]


def test_sync_alle_demo_signale_bleiben_draussen():
    client = _FakeClient()
    summary = tradeserver_sync.sync_alle(
        [_result(source_kind="demo")], client=client)
    assert summary["signale"] == 0
    assert client.schritt_namen() == ["register", "signals", "complete"]


def test_sync_alle_abbruch_bei_verbindungsfehler_ruft_abort():
    client = _FakeClient(fehler_bei="signals")
    summary = tradeserver_sync.sync_alle([_result()], client=client)
    assert summary["abgebrochen"]
    namen = client.schritt_namen()
    assert namen == ["register", "abort"]  # gescheiterter Schritt wird nicht gezählt


def test_sync_alle_schreibt_nur_laufhistorie():
    """Invariante: der Sync verändert keine Bewertungstabellen."""
    def _zaehle():
        with db._connect() as conn:
            return {t: conn.execute(
                f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
                for t in ("signals", "forensik", "analyses")}

    vorher = _zaehle()
    tradeserver_sync.sync_alle([_result()], client=_FakeClient())
    assert _zaehle() == vorher

    runs = db.list_tradeserver_sync_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "ok"
    assert runs[0]["summary"]["signale"] == 1

    # Abbruchlauf landet ebenfalls in der Historie — mit Status abgebrochen.
    tradeserver_sync.sync_alle([_result()], client=_FakeClient(fehler_bei="register"))
    runs = db.list_tradeserver_sync_runs()
    assert runs[0]["status"] == "abgebrochen"


# --- Verbindungs-Status mit TTL-Cache -------------------------------------

def test_verbindungs_status_nicht_konfiguriert_ohne_netz():
    tradeserver_sync.status_cache_leeren()
    wert = tradeserver_sync.verbindungs_status()
    assert wert["konfiguriert"] is False
    assert wert["ok"] is None


def test_verbindungs_status_cacht_ping_5_minuten():
    config.save_settings({**config.load_settings(),
                          "tradeserver_base_url": "http://server:8080"})
    client = _FakeClient()
    original = tradeserver_sync._client
    tradeserver_sync._client = lambda: client  # type: ignore[assignment]
    try:
        tradeserver_sync.status_cache_leeren()
        erster = tradeserver_sync.verbindungs_status()
        zweiter = tradeserver_sync.verbindungs_status()
        assert erster["ok"] is True
        assert zweiter["geprueft"] == erster["geprueft"]
        assert client.schritt_namen().count("ping") == 1  # TTL-Cache greift
    finally:
        tradeserver_sync._client = original  # type: ignore[assignment]
        tradeserver_sync.status_cache_leeren()
