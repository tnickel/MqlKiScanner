# -*- coding: utf-8 -*-
"""Prozessweites Worker-Register: Läufe müssen Modul-Wechsel überleben.

Streamlit lädt lokale Module neu, wenn sich Dateien ändern — mitten in einem
Lauf darf ein frisches Modul den laufenden Worker weder aus dem Blick
verlieren noch einen zweiten zulassen.
"""
from __future__ import annotations

import importlib
import threading

from mqlkiscanner import scan_worker


def test_registry_survives_module_reload():
    release = threading.Event()
    run = scan_worker.start(release.wait, workflow={}, control={},
                            logs={}, results=[])
    assert run is not None
    assert scan_worker.active_run() is run

    # Simulierter Streamlit-Modul-Reload mitten im Lauf
    importlib.reload(scan_worker)
    assert scan_worker.active_run() is run, "Lauf nach Reload unsichtbar"

    # Zweiter Start wird weiterhin abgewiesen (kein Doppel-Lauf)
    zweiter = scan_worker.start(lambda: None, workflow={}, control={},
                                logs={}, results=[])
    assert zweiter is None

    release.set()
    run.thread.join(timeout=5)
    assert scan_worker.active_run() is None, "Register nach Laufende nicht frei"


def test_registry_is_shared_between_module_instances():
    release = threading.Event()
    run = scan_worker.start(release.wait, workflow={}, control={},
                            logs={}, results=[])
    alt = importlib.import_module("mqlkiscanner.scan_state")
    importlib.reload(alt)
    # Auch nachgeladene Module sehen denselben aktiven Lauf.
    assert alt.scan_worker.active_run() is run
    release.set()
    run.thread.join(timeout=5)
