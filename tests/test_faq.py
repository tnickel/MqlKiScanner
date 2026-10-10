# -*- coding: utf-8 -*-
"""FAQ-Seite (Nutzer-Wunsch 08.10.2026): Inhalte + App-Test.

Strukturprüfungen sichern die Erweiterbarkeit: jede Frage nicht-leer,
keine Dubletten, 10–20 Fragen (vom Nutzer als Ziel genannt). Die Seite
selbst wird per AppTest gerendert (Suche filtert, Expander tragen die
Fragen).
"""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from mqlkiscanner import faq_inhalte

ROOT = Path(__file__).resolve().parents[1]
SEITE = ROOT / "app_pages" / "faq.py"


# ------------------------------------------------------------- Inhalte
def test_faq_umfang_10_bis_20_fragen():
    anzahl = len(faq_inhalte.alle_fragen())
    assert 10 <= anzahl <= 20, f"Ziel 10–20 Fragen, aktuell {anzahl}"


def test_faq_struktur_vollstaendig_und_eindeutig():
    fragen = [f for f, _ in faq_inhalte.alle_fragen()]
    antworten = [a for _, a in faq_inhalte.alle_fragen()]
    assert all(f.strip() and f.endswith("?") for f in fragen)
    assert all(len(a.strip()) >= 80 for a in antworten), \
        "Antworten müssen substanziell sein (≥ 80 Zeichen)"
    assert len(set(fragen)) == len(fragen), "Dubletten bei den Fragen"
    assert len(faq_inhalte.FAQ_KATEGORIEN) >= 4


def test_faq_deckt_die_praxisfragen_ab():
    """Die Fragen des Nutzers (08.10.2026) müssen abgedeckt sein."""
    text = " ".join(f + " " + a for f, a in faq_inhalte.alle_fragen()).casefold()
    for stichwort in (
        "dino",                  # DINO-Fall (Vorfilter/Katalog)
        "high-watermark",        # Vantage HWM-Frage
        "start- und endzeiten",  # Trade-Zeiten-Frage
        "viele abonnenten",      # „laden wir die besten“-Definition
        "kapitalbasis",          # leere Prozentwerte
        "fix-id",                # 📌 Immer-scannen
        "pdf",                   # Speicherorte
        "trueretdd",             # Calmar-Grün-Gate
    ):
        assert stichwort in text, f"FAQ deckt „{stichwort}“ nicht ab"


# ----------------------------------------------------------------- Seite
def test_faq_seite_rendert_alle_fragen():
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    expander_fragen = " | ".join(e.label for e in at.expander)
    assert len(at.expander) == len(faq_inhalte.alle_fragen())
    assert "Warum finde ich ein bestimmtes Signal" in expander_fragen


def test_faq_suche_filtert():
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    at.text_input(key="faq_suche").set_value("High-Watermark")
    at.run()
    assert not at.exception, at.exception
    assert len(at.expander) >= 1
    assert any("High-Watermark" in e.label for e in at.expander)
    # Andere Themen sind rausgefiltert
    assert not any("PDF" in e.label for e in at.expander)
    treffer = " ".join(c.value for c in at.caption)
    assert "von" in treffer


def test_faq_suche_ohne_treffer_zeigt_hinweis():
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    at.text_input(key="faq_suche").set_value("xyzunkwort123")
    at.run()
    assert not at.exception, at.exception
    assert not at.expander
    assert any("Keine Frage passt" in i.value for i in at.info)
