"""Hub-Anzeigen folgen den Einstellungen und der aktiven Quellen-Registry."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from mqlkiscanner import config, db, quellen, rest_api, verbindungs_monitor
from mqlkiscanner.agenten import daemon


@pytest.mark.parametrize("settings, erwartete_regeln, monatshuerde", [
    ({}, ("≤ 30 % Drawdown", "Jahres-Calmar ≥ 3"), None),
    ({"schranke_eq_dd_pct": 22, "min_calmar_jahr": 4.5,
      "min_ertrag_pct_monat": 7.5},
     ("≤ 22 % Drawdown", "Jahres-Calmar ≥ 4.5"), "≥ 7.5 % Ertrag / Monat"),
    ({"min_calmar_jahr": 0}, ("Jahres-Calmar ≥ 0",), None),
])
def test_sidebar_zeigt_konfigurierte_kriterien_ohne_dienste(
        monkeypatch, settings, erwartete_regeln, monatshuerde):
    config.save_settings(settings)
    # Nur die echte Sidebar ausführen: kein REST-Server, Hintergrundmonitor
    # oder Seiten-Workflow. conftest isoliert Settings und Datenbank.
    monkeypatch.setattr(rest_api, "start_background", lambda: None)
    monkeypatch.setattr(verbindungs_monitor, "zustand",
                        lambda: {"fehler": "", "geladen": False})
    monkeypatch.setattr(daemon, "status_text", lambda: "aus")
    monkeypatch.setattr(st, "navigation", lambda *a, **kw: SimpleNamespace(run=lambda: None))
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] /
                               "streamlit_app.py"), default_timeout=30).run()
    assert not at.exception
    text = "\n".join(e.value for art in ("markdown", "caption")
                     for e in getattr(at.sidebar, art))
    for regel in erwartete_regeln:
        assert regel in text
    assert "Wochen Trade-Historie" in text
    assert "Fehlender SL-Nachweis ist neutral" in text
    assert "> 5 % Ertrag / Monat" not in text
    if monatshuerde is None:
        assert "Absolute Monats-Ertragshürde deaktiviert" in text
    else:
        assert monatshuerde in text
        assert "Absolute Monats-Ertragshürde deaktiviert" not in text


def _quellen_details() -> AppTest:
    return AppTest.from_string(
        "from mqlkiscanner.app_ui import render_downloader_section\n"
        "from mqlkiscanner.pipeline import ScanResult\n"
        "render_downloader_section(ScanResult(id=77, platform='MT5'))",
        default_timeout=30).run()


def test_quellen_details_laden_verlauf_und_pdf_ohne_legacy_url(monkeypatch):
    db.add_quelle("mql5", "Neue REST-Quelle", "http://quelle.invalid:8089")
    assert not config.load_settings().get("downloader_base_url")
    aufrufe = []

    class Client:
        def history(self, signal_id, version):
            aufrufe.append(("history", signal_id, version))
            return [{"timestamp": "2026-10-16T09:00:00", "subscribers": 42}]

        def reports(self, signal_id, version):
            aufrufe.append(("reports", signal_id, version))
            return [{"name": "test.pdf", "sizeBytes": 12}]

        def download_report(self, signal_id, version, name):
            aufrufe.append(("download", signal_id, version, name))
            return b"%PDF-1.4 fake"

    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *a, **kw: Client())
    at = _quellen_details()
    assert not at.exception
    at.button(key=f"dl_history_{('mql5', 77)}").click().run()
    assert not at.exception
    assert db.get_history(77)[0]["subscribers"] == 42
    at.button(key=f"dl_reports_{('mql5', 77)}").click().run()
    assert not at.exception
    report = db.list_downloader_reports(77)[0]
    assert Path(report["path"]).is_relative_to(config.DOWNLOADER_DIR)
    assert Path(report["path"]).read_bytes() == b"%PDF-1.4 fake"
    assert aufrufe == [("history", 77, "mql5"), ("reports", 77, "mql5"),
                       ("download", 77, "mql5", "test.pdf")]


@pytest.mark.parametrize("inaktive_quelle", [False, True])
def test_quellen_details_ohne_aktive_quelle_zeigen_einrichtung(inaktive_quelle):
    if inaktive_quelle:
        config.save_settings({"downloader_base_url": "http://alt.invalid:8089"})
        db.add_quelle("mql5", "Deaktivierte Quelle", "http://alt.invalid:8089",
                      aktiv=False)
    at = _quellen_details()
    assert not at.exception
    assert not any(b.key in (f"dl_history_{('mql5', 77)}", f"dl_reports_{('mql5', 77)}") for b in at.button)
    assert any("Keine aktive Datenquelle konfiguriert" in e.value and
               "„Datenquellen“" in e.value for e in at.info)
