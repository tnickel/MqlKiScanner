# -*- coding: utf-8 -*-
"""Regressionstests für das zweite Lauf-Review 02.10.2026 (B1–B13).

B9:  Breakeven ist kein Verlust — keine Phantom-Martingale-Signatur.
B12: Teilscan-Begründung respektiert die Slot-Grenze.
B5:  Offline-Artefakte werden nur bei intaktem SHA verwendet.
B8:  Autonomer Scan ohne eine einzige erfolgreiche Prüfung setzt keine
     Tages-/Monatsmerker.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from mqlkiscanner import config, db, fix_signale
from mqlkiscanner.models import ParsedExport, Trade
from mqlkiscanner.forensics import martingale


# -------------------------------------------------------------------- B9 —

def _trade(zeit, volume, netto) -> Trade:
    return Trade(open_time=zeit, close_time=zeit, direction="Buy",
                 volume=volume, symbol="XAUUSD", entry_price=2000.0,
                 exit_price=2010.0, profit=netto, commission=0.0, swap=0.0)


def test_b9_breakeven_ist_kein_verlust_fuer_martingale():
    """Netto [0, +2] mit Lots [0.01, 0.02]: kein Verlust -> KEINE
    Verlustnachfolge -> kein Martingale-Flag (vorher: netto <= 0 wertete
    den Break-even-Trade als Verlust und lieferte Median 2.0 = rot)."""
    trades = [
        _trade(datetime(2026, 1, 1, 10), 0.01, 0.0),
        _trade(datetime(2026, 1, 1, 11), 0.02, 2.0),
    ]
    ergebnis = martingale.run(ParsedExport(source_path="x", source_format="positions",
                                           trades=trades))
    per_symbol = ergebnis["per_symbol"]["XAUUSD"]
    assert per_symbol["n_after_loss"] == 0
    assert per_symbol["median_ratio_after_loss"] is None
    assert per_symbol["flag"] is False


# ------------------------------------------------------------------- B12 —

def _kandidat(sid, abos, quelle=None):
    c = {"id": sid, "name": f"S{sid}", "abonnenten": abos, "wochen": 40,
         "url": f"https://www.mql5.com/en/signals/{sid}"}
    if quelle:
        c["quelle_kuerzel"] = quelle
    return c


def test_b12_teilscan_beschreibt_slot_ueberschuessige_ehrlich():
    """2 Teilscan-Kandidaten (🟢/🟡), aber nur 1 Slot: der zweite bekommt
    OHNE_SLOT mit Slot-Grund — nicht „wird geprüft"."""
    cands = [_kandidat(1, 900, "pelik"), _kandidat(2, 500, "pelik")]
    begr = []
    fix_signale.waehle_fuer_export(cands, 1, {}, begruendung=begr,
                                   modus="gelbgruen")
    nach_id = {e["id"]: e for e in begr}
    assert nach_id[1]["status"] == "AUSGEWAEHLT"
    assert "wird geprüft" in nach_id[1]["grund"]
    assert nach_id[2]["status"] == "OHNE_SLOT"
    assert "Slot-Grenze" in nach_id[2]["grund"]
    assert "wird geprüft" not in nach_id[2]["grund"]


# -------------------------------------------------------------------- B5 —

def test_b5_offline_cache_mit_falschem_sha_wird_abgelehnt(tmp_path,
                                                          monkeypatch):
    """Quelle offline + gespeicherte Trade-Datei verändert (SHA weicht ab):
    ehrlicher ConnectionError statt stiller Forensik auf vergiftetem Cache."""
    db.init_db()
    qid = db.add_quelle("pelik", "PelicanTest", "http://localhost:8090",
                        aktiv=True)
    quelle = db.list_quellen(nur_aktiv=True)[0]
    datei = tmp_path / "pelican_123_trades.csv"
    datei.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;"
                     "Commission;Swap;Profit\n", encoding="utf-8")
    inhalt = datei.read_bytes()
    db.store_quellen_artefakt(qid, 123, "pelican", "trades",
                              hashlib.sha256(inhalt).hexdigest(), str(datei))
    # Datei NACH dem Vermerk verändern (Cache-Poisoning-Fall)
    datei.write_bytes(inhalt + b"2026.01.01 00:00:00;Buy;0.1;XAUUSD;1;0.1;"
                      b"2026.01.01 01:00:00;2;0;0;1000.00\n")

    from mqlkiscanner import downloader_client, ingest

    class _Offline:
        def trades_csv(self, signal_id, version):
            raise downloader_client.DownloaderConnectionError(" Quelle aus")

    with pytest.raises(downloader_client.DownloaderConnectionError) as info:
        ingest.hole_trades(quelle, 123, "pelican", client=_Offline())
    assert "SHA" in str(info.value) or "verändert" in str(info.value)


# -------------------------------------------------------------------- B8 —

def test_b8_scan_ohne_erfolgreiche_pruefung_setzt_keine_merker(monkeypatch,
                                                               tmp_path):
    """Nichtleerer Scope, alle Analysen fehlgeschlagen: Status fehler,
    Tages-/Monatsmerker bleiben OFFEN (Wiederholung beim nächsten Takt)."""
    from mqlkiscanner.agenten import scan_launcher, journal
    from mqlkiscanner import pipeline as _pipeline

    db.init_db()

    class _FehlerPipeline:
        def __init__(self, settings=None, quelle="full"):
            self.settings = settings or {}
            self.quelle = quelle
            self.llm = type("L", (), {"has_key": False})()

        def crawl(self, on_progress, log):
            return [{"id": 1, "name": "Ein"}, {"id": 2, "name": "Zwei"}]

        def build_candidates(self, signale, log, begruendung=None):
            return [{"id": s["id"], "name": s["name"]} for s in signale]

        def analyze_candidate(self, session, kandidat, log, should_stop=None):
            raise RuntimeError("Simulierter Totalausfall")

        def kursdaten_beenden(self):
            pass

    monkeypatch.setattr(_pipeline, "ScanPipeline", _FehlerPipeline)
    monkeypatch.setattr(scan_launcher, "pipeline", _pipeline)
    monkeypatch.setattr(scan_launcher.Mql5Session, "has_credentials",
                        property(lambda self: True))
    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.ensure_mql5_cookies",
                        lambda cfg, session, log=None: True)

    ergebnis = scan_launcher.starte_scan("full", quelle="test",
                                         log=lambda *_: None)
    assert ergebnis["status"] == "fehler"
    assert not scan_launcher.scan_monat_gestartet("full")
    lauf = journal.list_laeufe(rolle="dirigent")[0]
    assert lauf["status"] == "fehler"
