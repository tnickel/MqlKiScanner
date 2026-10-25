# -*- coding: utf-8 -*-
"""Abonnenten-Overlay in list_catalog (Nutzer-Anforderung 25.10.): Die
Übersichten zeigen den Stand des letzten Client-Laufs (katalog_signale),
nicht den alten Workflow-Scan-Stand; ohne Katalogzeile gilt der Scan-Stand
weiter als Fallback."""
from __future__ import annotations

from mqlkiscanner import db


def _seed(externe_id: int, name: str, scan_abos, katalog_abos) -> None:
    db.init_db()
    db.upsert_signal(externe_id, name=name, platform="mt5", url="",
                     wochen=30, abonnenten=scan_abos, quelle="fake")
    if katalog_abos is not None:
        db.katalog_upsert_many("fake", [{
            "signal_id": externe_id, "name": name, "platform": "mt5",
            "url": "", "version": "mt5", "abonnenten": float(katalog_abos),
            "wochen": 30.0, "risiko": None}], fehlende_loeschen=False)


def test_katalog_stand_gewinnt_ueber_workflow_scan_stand():
    _seed(5001, "Lenore", scan_abos=120, katalog_abos=122)
    zeilen = {z["signal_id"]: z for z in db.list_catalog()}
    assert zeilen[5001]["abonnenten"] == 122


def test_ohne_katalog_zeile_gilt_workflow_stand_weiter():
    _seed(5002, "NurScan", scan_abos=77, katalog_abos=None)
    zeilen = {z["signal_id"]: z for z in db.list_catalog()}
    assert zeilen[5002]["abonnenten"] == 77
