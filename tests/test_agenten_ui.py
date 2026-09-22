# -*- coding: utf-8 -*-
"""UI des Agentenbetriebs: Seite „Agenten" (Live/Protokoll) und der
Admin-Bereich „Agenten" — letzterer über einen Wrapper-Frame, damit der
Tab isoliert von den übrigen Admin-Inhalten prüfbar ist. Start/Stop-Klicks
werden NICHT getestet (starten würde einen echten Prozess spawnen)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

_WRAPPER = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import streamlit as st
from mqlkiscanner import config
from mqlkiscanner.agenten import admin_tab
from mqlkiscanner.ui_design import apply_theme
apply_theme()
admin_tab.rendern(config.load_settings())
"""


@pytest.fixture
def admin_frame(tmp_path):
    datei = tmp_path / "_admin_agenten_frame.py"
    datei.write_text(_WRAPPER, encoding="utf-8")
    return datei


ROLLEN_NAMEN = ("Dirigent", "Marktbeobachter", "Signal-Betreuer",
                "Chefermittler", "Melder")


def _sichttext(at) -> str:
    return (" ".join(m.value for m in at.markdown) + " "
            + " ".join(c.value for c in at.caption) + " "
            + " ".join(e.label for e in at.expander))


def test_agenten_seite_rendert_mit_leerem_protokoll():
    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 3  # Live · Protokoll · Dossiers (Phase B)
    text = _sichttext(at)
    for name in ROLLEN_NAMEN:
        assert name in text
    # Leerer Zustand erklärt sich selbst (Hinweis auf Start per CLI).
    assert "Noch keine Läufe" in text


def test_agenten_seite_zeigt_protokollierten_llm_schritt():
    from mqlkiscanner.agenten import journal
    lauf = journal.lauf_starten("dirigent", quelle="test")
    journal.schritt_protokollieren(
        lauf, "dirigent", "llm_entscheidung",
        prompt="Vollständiger Testprompt", antwort="Vollständige Testantwort",
        modell="glm-5.3", tokens=42, dauer_s=1.0)
    at = AppTest.from_file(str(ROOT / "app_pages" / "agenten.py"),
                           default_timeout=30).run()
    assert not at.exception
    gesperrt = [t for t in at.text_area if t.disabled]
    assert any("Vollständiger Testprompt" in (t.value or "") for t in gesperrt)
    assert any("Vollständige Testantwort" in (t.value or "") for t in gesperrt)


def test_admin_tab_zeigt_rollen_budget_und_prompts(admin_frame):
    at = AppTest.from_file(str(admin_frame), default_timeout=30).run()
    assert not at.exception
    # Fünf Rollen als Karten: je Aktiv-Toggle und Modell-Auswahl.
    aktiv_toggles = [t for t in at.toggle if t.key.endswith("_aktiv_ui")]
    modell_wahl = [sb for sb in at.selectbox if "_modell_ui" in (sb.key or "")]
    assert len(aktiv_toggles) == 5
    assert len(modell_wahl) == 5
    # Standard-Modell GLM-5.3 überall vorausgewählt.
    for sb in modell_wahl:
        assert sb.value == "glm-5.3"
    # Budget und Start/Stopp vorhanden; die Default-Vorlage (dirigent_planung)
    # liegt im Editor (segmented_control selbst ist in AppTest kein selectbox).
    assert at.number_input(key="admin_agenten_budget_tag")
    assert at.number_input(key="admin_agenten_budget_monat")
    assert at.text_area(key="agenten_prompt_dirigent_planung")
    assert at.button(key="admin_agenten_start") is not None
    assert at.button(key="admin_agenten_stop") is not None


def test_admin_tab_rollen_speichern_schreibt_settings(admin_frame):
    at = AppTest.from_file(str(admin_frame), default_timeout=30).run()
    assert not at.exception
    at.button(key="admin_agenten_rollen_save").set_value(True)
    at.run()
    from mqlkiscanner import config
    settings = config.load_settings()
    # Defaults der Registry sind persistiert (glm-5.3 überall).
    for name, wert in config.DEFAULT_SETTINGS.items():
        if name.startswith("agenten_"):
            assert settings[name] == wert, name
