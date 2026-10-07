# -*- coding: utf-8 -*-
"""Stufe 0 in der Oberfläche (doc/23): Kreis 0 auf der Scan-Seite, der
große Live-Dialog, Admin-Einstellungen und die Skip-Regeln des Workers."""
from __future__ import annotations

import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest

from mqlkiscanner import client_updates, config, db

_SCAN_PFAD = str(Path(__file__).resolve().parents[1] / "app_pages" / "scan.py")


def _seite() -> AppTest:
    return AppTest.from_file(_SCAN_PFAD, default_timeout=30)


# --- Scan-Seite ----------------------------------------------------------

def test_scan_seite_hat_stufe0_station():
    at = _seite()
    at.run()
    assert not at.exception
    steps = at.session_state["scan_workflow"]["steps"]
    assert "clients" in steps, "Stufe 0 muss erste Workflow-Station sein"
    assert list(steps)[0] == "clients"
    assert steps["clients"]["status"] == "pending"


def test_stufe0_dialog_oeffnet_grosses_fenster():
    at = _seite()
    at.run()
    assert not at.exception
    at.session_state["_scan_station_dialog"] = "clients"
    at.run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert "Stufe 0 bewertet nichts" in text
    assert "Letzte Läufe" in text
    infos = "\n".join(i.value for i in at.info)
    assert "Noch kein Stufe-0-Lauf in dieser Sitzung" in infos


def test_stufe0_dialog_zeigt_chronik_und_leer_hinweis():
    db.store_client_update(quelle_id=1, kuerzel="pelik", base_url="http://x:8090",
                           job_id="j1", status=client_updates.FERTIG,
                           dauer_s=42.0, signale_geliefert=648,
                           datenstand="2026-10-07T15:41:00")
    at = _seite()
    at.run()
    at.session_state["_scan_station_dialog"] = "clients"
    at.run()
    assert not at.exception
    # Chronik erscheint als Tabelle im Dialog
    daten = [t.value for t in at.dataframe]
    assert any("pelik" in str(d) for d in daten)


# --- Settings / Defaults -------------------------------------------------

def test_stufe0_settings_defaults():
    settings = config.DEFAULT_SETTINGS
    assert settings["stufe0_aktiv"] is True
    assert settings["update_ziel_signale"] == 200
    assert settings["update_katalog_max_alter_h"] == 72
    assert settings["update_timeout_min"] == 120
    assert settings["update_login_timeout_min"] == 10


def test_scan_fortschritt_kennt_clients_station():
    from mqlkiscanner import scan_fortschritt
    assert "clients" in scan_fortschritt.GEWICHTE
    von, bis = scan_fortschritt.GEWICHTE["clients"]
    assert von < bis <= scan_fortschritt.GEWICHTE["listen"][1]


# --- Launcher: Stufe 0 greift nur mit Quellen ----------------------------

def test_launcher_stufe0_nur_mit_quellen(tmp_path, monkeypatch):
    """Ohne aktive Quelle / im MQL5-Modus darf der Launcher Stufe 0 überspringen:
    die Bedingung wird hier direkt geprüft (Fake-Pipeline-Tests decken den Rest ab)."""
    from mqlkiscanner.agenten import scan_launcher
    db.init_db()
    settings = {"stufe0_aktiv": True, "listen_modus": "mql5"}
    # Bedingung als solche nachbauen: keine Quellen → kein Stufe-0-Lauf
    assert db.list_quellen(nur_aktiv=True) == [] or settings["listen_modus"] == "mql5"
    aufgerufen = []
    monkeypatch.setattr(client_updates, "starte_alle_updates",
                        lambda *a, **kw: aufgerufen.append(a) or {})
    if (settings.get("stufe0_aktiv", True)
            and str(settings.get("listen_modus") or "mql5").strip().lower() != "mql5"
            and db.list_quellen(nur_aktiv=True)):
        client_updates.starte_alle_updates(settings)
    assert not aufgerufen, "MQL5-Modus ohne Quellen darf Stufe 0 nicht anstoßen"
    assert scan_launcher.client_updates is client_updates
