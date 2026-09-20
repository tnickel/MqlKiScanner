# -*- coding: utf-8 -*-
"""Batch-Erweiterte-KI-Analyse: Skip, Fehler, Stop, Einzelinstanz.

Die Modellaufrufe sind gefakt; der conftest weist echte Requests ab.
"""
from __future__ import annotations

import builtins
import threading
import time

import pytest

from mqlkiscanner import db, pipeline, secrets_store, tiefen_batch
from mqlkiscanner.llm import client as llm_client


@pytest.fixture(autouse=True)
def _register_bereinigen():
    yield
    if hasattr(builtins, tiefen_batch._BATCH_ATTR):
        delattr(builtins, tiefen_batch._BATCH_ATTR)


def _warte_fertig(timeout: float = 10.0) -> dict:
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        batch = tiefen_batch.aktiver_batch()
        if batch and batch["fertig"]:
            return batch
        time.sleep(0.05)
    raise AssertionError("Batch wurde nicht fertig")


def _ziel(id_: int, name: str) -> pipeline.ScanResult:
    return pipeline.ScanResult(id=id_, name=name, platform="MT5",
                               trades_path=f"snapshots/{id_}.csv")


def test_batch_ueberspringt_vorhandene_und_laeuft(monkeypatch):
    db.init_db()
    db.upsert_signal(1, name="A", platform="MT5")
    db.upsert_signal(2, name="B", platform="MT5")
    db.store_analysis(1, "tiefenanalyse", "glm-5.3", 10, "# alt")  # A bereits da
    aufrufe = []
    monkeypatch.setattr(tiefen_batch, "run_tiefenanalyse_einzeln",
                        lambda result, settings=None, log=None: aufrufe.append(result.id))
    secrets_store.save_secrets(glm_api_key="k")
    ok, meldung = tiefen_batch.batch_starten([_ziel(1, "A"), _ziel(2, "B")],
                                             settings={})
    assert ok
    batch = _warte_fertig()
    assert aufrufe == [2]                      # A uebersprungen (DB-Check)
    assert batch["uebersprungen"] == 1
    assert batch["fehler"] == 0
    assert batch["done"] == 2 and batch["fertig"]


def test_batch_zaehlt_einzelfehler_und_laeuft_weiter(monkeypatch):
    db.init_db()
    aufrufe = []

    def fake(result, settings=None, log=None):
        aufrufe.append(result.id)
        if result.id == 2:
            raise llm_client.LlmError("kaputt")

    monkeypatch.setattr(tiefen_batch, "run_tiefenanalyse_einzeln", fake)
    secrets_store.save_secrets(glm_api_key="k")
    ok, _ = tiefen_batch.batch_starten([_ziel(2, "B"), _ziel(3, "C")], settings={})
    assert ok
    batch = _warte_fertig()
    assert aufrufe == [2, 3]
    assert batch["fehler"] == 1
    assert batch["fehler_liste"][0].startswith("B (#2)")
    assert batch["fertig"] and not batch["abgebrochen"]


def test_batch_stoppt_nach_aktueller_strategie(monkeypatch):
    db.init_db()
    aufrufe = []
    freigabe = threading.Event()

    def fake(result, settings=None, log=None):
        aufrufe.append(result.id)
        freigabe.wait(5)

    monkeypatch.setattr(tiefen_batch, "run_tiefenanalyse_einzeln", fake)
    secrets_store.save_secrets(glm_api_key="k")
    ok, _ = tiefen_batch.batch_starten([_ziel(1, "A"), _ziel(2, "B")], settings={})
    assert ok
    ende = time.monotonic() + 5
    while time.monotonic() < ende and not aufrufe:
        time.sleep(0.02)
    tiefen_batch.batch_stoppen()
    freigabe.set()
    batch = _warte_fertig()
    assert aufrufe == [1]                       # B wird nicht mehr gestartet
    assert batch["abgebrochen"] is True
    assert batch["done"] == 1


def test_doppelstart_wird_abgelehnt(monkeypatch):
    db.init_db()
    freigabe = threading.Event()

    def fake(result, settings=None, log=None):
        freigabe.wait(5)

    monkeypatch.setattr(tiefen_batch, "run_tiefenanalyse_einzeln", fake)
    secrets_store.save_secrets(glm_api_key="k")
    ok, _ = tiefen_batch.batch_starten([_ziel(1, "A")], settings={})
    assert ok
    assert tiefen_batch.batch_laeuft() is True
    ok2, meldung2 = tiefen_batch.batch_starten([_ziel(2, "B")], settings={})
    assert ok2 is False
    assert "bereits" in meldung2
    tiefen_batch.batch_stoppen()
    freigabe.set()
    _warte_fertig()


def test_start_ohne_key_oder_ohne_ziele_lehnt_ab():
    ok, meldung = tiefen_batch.batch_starten([], settings={})
    assert ok is False and "GLM-Key" in meldung
    secrets_store.save_secrets(glm_api_key="k")
    ok, meldung = tiefen_batch.batch_starten([], settings={})
    assert ok is False and "Keine geeigneten Signale" in meldung
