# -*- coding: utf-8 -*-
"""Seite „Alle Signale“ — AppTest Ende-zu-Ende + reine Chart-/Zeilen-Builder.

Muster wie tests/test_equity_studie.py: echte Temp-CSV, results_from_db und
list_catalog auf der MODUL-Ebene monkeypatchen (die Seite importiert die
Module), teure Berechnung NICHT faken — signal_statistik ist schnell und
rechnet auf der kleinen CSV echt.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import db, pipeline
from mqlkiscanner.alle_signale_ui import (
    dauer_balken_chart,
    kurve_unterwasser_chart,
    monats_balken_chart,
    tabellen_zeile,
)

ROOT = Path(__file__).resolve().parents[1]
SEITE = ROOT / "app_pages" / "alle_signale.py"

KOPF = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def _csv(pfad: Path) -> str:
    zeilen = [
        "2026.01.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.05 10:10:00;1.1010;0;;100.0",
        "2026.02.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.02.05 10:10:00;1.0990;0;;-60.0",
        "2026.03.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.03.05 10:10:00;1.1012;0;;120.0",
    ]
    pfad.write_text(KOPF + "\n".join(zeilen) + "\n", encoding="utf-8-sig")
    return str(pfad)


def _probe_mit_trades(csv_pfad: str) -> pipeline.ScanResult:
    return pipeline.ScanResult(
        id=42, name="Testsignal Euro", platform="MT5", quelle="pelik",
        ampel="🟡", url="https://example.org/42", wochen=100.0, abonnenten=123.0,
        dd_equity_pct=9.9, ertrag_monat_pct=1.5,
        trades_path=csv_pfad)


def _probe_ohne_trades() -> pipeline.ScanResult:
    return pipeline.ScanResult(
        id=7, name="Nur Katalog", platform="MT4", quelle="mql5",
        ampel="⚪", wochen=51.0, abonnenten=None, trades_path="")


# --------------------------------------------------------------- App-Tests
def test_seite_rendert_mit_zwei_signalen(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    proben = [_probe_mit_trades(csv_pfad), _probe_ohne_trades()]
    monkeypatch.setattr(pipeline, "results_from_db", lambda: proben)
    monkeypatch.setattr(db, "list_catalog", lambda: [
        {"signal_id": 42, "stats": {"balance_usd": 10_000.0}},
        {"signal_id": 7, "stats": {}},
    ])
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    texte = " ".join(c.value for c in at.caption)
    text = " ".join(x.value for x in at.markdown) + " " + texte
    assert "2 von 2 Signalen" in texte
    assert "1 mit Trade-Cache" in texte
    assert "ohne KI und ohne Bewertung" in text


def test_seite_leer_ohne_signale(monkeypatch):
    monkeypatch.setattr(pipeline, "results_from_db", lambda: [])
    monkeypatch.setattr(db, "list_catalog", lambda: [])
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert any("Noch keine Signale" in i.value for i in at.info)


def test_filter_nur_mit_trades(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    proben = [_probe_mit_trades(csv_pfad), _probe_ohne_trades()]
    monkeypatch.setattr(pipeline, "results_from_db", lambda: proben)
    monkeypatch.setattr(db, "list_catalog", lambda: [
        {"signal_id": 42, "stats": {"balance_usd": 10_000.0}},
        {"signal_id": 7, "stats": {}},
    ])
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.toggle(key="alle_signale_nur_trades").set_value(True)
    at.run()
    assert not at.exception, at.exception
    assert any("1 von 2" in c.value for c in at.caption)


# ------------------------------------------------- reine Builder (ohne GUI)
def test_monats_balken_chart_farben_nach_vorzeichen():
    statistik = {"monate_pct": {"2026-01": 2.0, "2026-02": -1.0},
                 "monate_usd": {"2026-01": 20.0, "2026-02": -10.0}}
    fig = monats_balken_chart(statistik)
    assert len(fig.data) == 1
    assert list(fig.data[0].x) == ["2026-01", "2026-02"]
    # Erst positiv (grün), dann negativ (rot).
    assert fig.data[0].marker.color[0] == "#2e7d32"
    assert fig.data[0].marker.color[1] == "#d32f2f"


def test_kurve_unterwasser_chart_rechnet_rueckgang():
    statistik = {"kurve": [["2026-01-01 10:00:00", 1_000.0],
                           ["2026-02-01 10:00:00", 800.0],
                           ["2026-03-01 10:00:00", 900.0]]}
    fig = kurve_unterwasser_chart(statistik)
    unterwasser = list(fig.data[1].y)
    # Unterwasser-Konvention der Equity-Studie: NEGATIVE Werte, Kurve hängt
    # unter der Nulllinie — je tiefer, desto größer der Rückgang.
    assert unterwasser[0] == 0.0
    assert unterwasser[1] == pytest.approx(-20.0)   # 200 Rückgang auf 1000 Peak
    assert unterwasser[2] == pytest.approx(-10.0)   # 100 auf 1000 Peak
    assert max(unterwasser) <= 0.0


def test_tabellen_zeile_ohne_statistik_zeigt_striche():
    class Fake:
        id = 1
        name = "Ohne Alles"
        ampel = "⚪"
        quelle = "mql5"
        platform = ""
        wochen = None
        abonnenten = None
        dd_equity_pct = None
        ertrag_monat_pct = None
        forensik_vorhanden = False

    zeile = tabellen_zeile(Fake(), None)
    assert zeile["Gewinn %/M (geom.)"] is None
    assert zeile["Basis"] == "—"
    assert zeile["Ampel"] == "⚪"


# ------------------------------------------------ Haltezeiten (05.10.)
def test_dauer_balken_chart_markiert_gefaehrliche_rot():
    ds = {"buckets": [
        {"bucket": "<1 Min", "anzahl": 30, "anteil_pct": 15.0, "netto_usd": 90.0,
         "gefaehrlich": True},
        {"bucket": "1–4 Std", "anzahl": 50, "anteil_pct": 25.0, "netto_usd": 300.0,
         "gefaehrlich": False},
    ]}
    fig = dauer_balken_chart(ds)
    # Reihenfolge umgedreht (horizontal): oberster Bucket = letzter der Liste
    assert list(fig.data[0].y) == ["1–4 Std", "<1 Min"]
    assert tuple(fig.data[0].marker.color) == ("#1f6feb", "#d32f2f")


def test_render_detail_tradeliste_und_vorbehalt(tmp_path):
    """render_detail direkt (AppTest.from_string-Muster): Tradeliste-Button
    klappt Haltezeit-Balken + Warnung auf; RetDD-Vorbehalt erscheint orange."""
    csv_pfad = _csv(tmp_path / "t42.csv")
    ds = ("{'buckets': ["
          "{'bucket': '0 Sek', 'anzahl': 2, 'anteil_pct': 2.0, 'netto_usd': -4.0, 'gefaehrlich': True},"
          "{'bucket': '<1 Min', 'anzahl': 1, 'anteil_pct': 1.0, 'netto_usd': 3.0, 'gefaehrlich': True},"
          "{'bucket': '1–4 Std', 'anzahl': 97, 'anteil_pct': 97.0, 'netto_usd': 900.0, 'gefaehrlich': False}],"
          "'null_sek': 2, 'unter_1min': 1, 'gefaehrlich_anzahl': 3, "
          "'gefaehrlich_anteil_pct': 3.0, 'dauer_median_s': 45.0, 'dauer_max_s': 72000.0}")
    code = f"""
import sys
sys.path.insert(0, r"{ROOT / 'src'}")
import streamlit as st
from mqlkiscanner.alle_signale_ui import render_detail
from mqlkiscanner.pipeline import ScanResult
auswahl = ScanResult(id=42, name="Vorbehalt Detail", ampel="🟡", quelle="pelik",
                     trades_path=r"{csv_pfad}", trades_sha256="abc123")
auswahl.retdd_monat_vorbehalt = 0.1032
auswahl.retdd_vorbehalt_grund = "Offene Position über Wechselgrenze"
auswahl.equity_dd_rekon_roh_pct = 13.83
render_detail(auswahl, {{"dauer_statistik": {ds}, "monate_pct": {{}},
                         "monate_usd": {{}}, "kurve": [], "trades": 100,
                         "kapitalbasis_ok": True,
                         "kapitalbasis_usd": 1713.0,
                         "kapitalbasis_quelle": "implizit_aus_balance"}},
              key_prefix="x")
"""
    at = AppTest.from_string(code, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.button(key="x_tradeliste_button").click()
    at.run()
    assert not at.exception, at.exception
    warn_text = " ".join(w.value for w in at.warning)
    assert "0 Sekunden oder unter einer Minute" in warn_text
    text = " ".join(x.value for x in at.markdown)
    assert "TrueRetDD (Vorbehalt) ≈ 0,10" in text
    assert "Wechselgrenze" in text
    assert any("Median-Haltezeit" in c.value for c in at.caption)


def test_formel_dialog_oeffnet_mit_formel_rechnung_erklaerung(tmp_path):
    """Nutzer-Wunsch 05.10.: Klick auf das ? der TrueRetDD-Karte öffnet ein
    Fenster mit Formel, ausgerechneter Rechnung und Erklärung."""
    csv_pfad = _csv(tmp_path / "t43.csv")
    code = f"""
import sys
sys.path.insert(0, r"{ROOT / 'src'}")
import streamlit as st
from mqlkiscanner.alle_signale_ui import render_detail
from mqlkiscanner.pipeline import ScanResult
auswahl = ScanResult(id=43, name="Formel Detail", ampel="🟡", quelle="pelik",
                     trades_path=r"{csv_pfad}", trades_sha256="abc123")
auswahl.retdd_monat_vorbehalt = 0.1032
auswahl.retdd_vorbehalt_grund = "Offene Position über Wechselgrenze"
auswahl.equity_dd_rekon_roh_pct = 13.83
render_detail(auswahl, {{"monate_pct": {{}}, "monate_usd": {{}}, "kurve": [],
                         "trades": 100, "kapitalbasis_ok": True,
                         "kapitalbasis_usd": 1713.0,
                         "kapitalbasis_quelle": "virtuell",
                         "ertrag_monat_geom_pct": 1.43,
                         "trading_dd_pct": 0.15,
                         "ertrag_je_close_dd": 9.51}},
              key_prefix="f")
"""
    at = AppTest.from_string(code, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.button(key="f_trueretdd_formel_btn").click()
    at.run()
    assert not at.exception, at.exception
    text = " ".join(x.value for x in at.markdown)
    assert "TrueRetDD" in text
    assert "÷" in text
    assert "Wechselgrenze" in text
    code_texts = " ".join(c.value for c in at.code)
    assert "Max-Drawdown" in code_texts
    assert any("Formel" in c.value for c in at.caption)

