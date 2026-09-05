# -*- coding: utf-8 -*-
"""Einzelschritte im Experten-Bereich: Blink-Status und Fortsetzung.

Die Stationen 1-4 bleiben einzeln klickbar; Zwischenergebnisse (Signale,
Kandidaten) bleiben sitzungsfest. Der Crawler wird gemockt — kein Netzwerk.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

FAKE_SIGNALS = [
    {"id": 2342895, "name": "KiraCat", "platform": "MT5", "abonnenten": 40,
     "wochen": 43, "growth_pct": 300.0, "abo_preis_usd": 49, "url": "x"},
    {"id": 9990001, "name": "Zu jung", "platform": "MT5", "abonnenten": 5,
     "wochen": 4, "growth_pct": 10.0, "abo_preis_usd": 30, "url": "x"},
]


@pytest.fixture
def mocked_crawler(monkeypatch):
    from mqlkiscanner.mql5 import crawler
    monkeypatch.setattr(crawler, "crawl_lists",
                        lambda *a, **k: [dict(s) for s in FAKE_SIGNALS])


def _scan_page() -> AppTest:
    return AppTest.from_file(str(ROOT / "app_pages" / "scan.py"), default_timeout=30)


def _btn(at: AppTest, key: str):
    found = [b for b in at.button if b.key == key]
    assert found, f"Button {key} fehlt"
    return found[0]


def test_step_numbers_blink_when_pending_and_stop_when_done(mocked_crawler):
    at = _scan_page()
    at.run()
    assert not at.exception
    html = "\n".join(m.value for m in at.markdown)
    assert "mks-stepnum" in html and "mks-blink" in html, "blinkende Zahlen fehlen (idle)"
    # Schritt 1 klicken -> danach abgeschlossen, nicht mehr blinkend
    _btn(at, "step_btn_listen").click()
    at.run()
    assert not at.exception, at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["listen"]["status"] == "complete"
    assert len(at.session_state["scan_signals"]) == 2
    html = "\n".join(m.value for m in at.markdown)
    assert html.count("mks-blink") < html.count("mks-stepnum"), \
        "fertige Schritte blinken noch"


def test_step2_continues_from_step1_and_filters(mocked_crawler):
    at = _scan_page()
    at.run()
    _btn(at, "step_btn_listen").click()
    at.run()
    _btn(at, "step_btn_kandidaten").click()
    at.run()
    assert not at.exception, at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["kandidaten"]["status"] == "complete"
    cands = at.session_state["scan_candidates"]
    # Filter (min. 26 Wochen) wirft das zu junge Signal raus
    assert [c["id"] for c in cands] == [2342895]


def test_step2_without_step1_is_skipped_with_hint():
    at = _scan_page()
    at.session_state["scan_signals"] = []
    at.run()
    _btn(at, "step_btn_kandidaten").click()
    at.run()
    assert not at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["kandidaten"]["status"] == "skipped"
    assert "Station 1" in wf["steps"]["kandidaten"]["detail"]


def test_step3_without_step2_is_skipped_with_hint():
    at = _scan_page()
    at.run()
    _btn(at, "step_btn_forensik").click()
    at.run()
    assert not at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["forensik"]["status"] == "skipped"
    assert "Station 2" in wf["steps"]["forensik"]["detail"]
