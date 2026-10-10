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
from mqlkiscanner import katalog as katalog_mod
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


# ------------------------------------------- Vollkatalog (08.10.2026)
def _katalog_probe_mit_quelle() -> pipeline.ScanResult:
    return pipeline.ScanResult(
        id=1286742, name="DINO Scalping", platform="vantage", quelle="vant",
        wochen=17.0, abonnenten=471.0, herkunft="Katalog",
        quelle_id=3, quelle_version="vantage", trades_path="")


def _katalog_seite(monkeypatch, proben, katalog_resultate, katalog_stats=None):
    """AppTest mit gescannten Proben + gepatchtem Katalog (ohne Netz)."""
    monkeypatch.setattr(pipeline, "results_from_db", lambda: proben)
    monkeypatch.setattr(db, "list_catalog", lambda: [
        {"signal_id": r.id, "stats": {"balance_usd": 10_000.0}} for r in proben])
    monkeypatch.setattr(db, "katalog_sync_status",
                        lambda: {"vant": {"gelaufen_am": "2026-10-08 15:00:00",
                                          "anzahl": 104, "fehler": None}})
    monkeypatch.setattr(katalog_mod, "katalog_resultate",
                        lambda: (katalog_resultate, katalog_stats or {}))
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    return at


def test_seite_zeigt_vollkatalog_und_kennzeichnet_herkunft(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    at = _katalog_seite(monkeypatch, [_probe_mit_trades(csv_pfad)],
                        [_katalog_probe_mit_quelle()])
    assert not at.exception, at.exception
    texte = " ".join(c.value for c in at.caption)
    assert "2 von 2 Signalen" in texte
    assert "1 nur Katalog" in texte
    assert "vant 104" in texte          # Katalog-Stand je Quelle sichtbar


def test_filter_herkunft_und_min_abonnenten(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    at = _katalog_seite(monkeypatch, [_probe_mit_trades(csv_pfad)],
                        [_katalog_probe_mit_quelle()])
    assert not at.exception, at.exception
    # Nur der Katalog: der gescannte Workflow-Testsignal-Zeile fällt raus
    at.radio(key="alle_signale_herkunft").set_value("Katalog (neu)")
    at.run()
    assert not at.exception, at.exception
    assert any("1 von 2 Signalen" in c.value
               and "1 nur Katalog" in c.value for c in at.caption)
    # Mindestabonnenten 500: DINO (471) fliegt ebenfalls raus → leer
    at.number_input(key="alle_signale_min_abo").set_value(500)
    at.run()
    assert not at.exception, at.exception
    assert any("Kein Signal passt" in i.value for i in at.info)


def test_katalog_zeile_laedt_daten_on_demand(tmp_path, monkeypatch):
    """Zeile ohne Trade-Cache → Lade-Button; danach läuft render_detail."""
    csv_pfad = _csv(tmp_path / "trades_dino.csv")
    probe = _katalog_probe_mit_quelle()
    geladen = []

    def _fake_laden(res):
        geladen.append(res.id)
        probe.trades_path = str(csv_pfad)
        return str(csv_pfad), True

    monkeypatch.setattr(katalog_mod, "lade_signal_daten", _fake_laden)
    at = _katalog_seite(monkeypatch, [], [probe])
    assert not at.exception, at.exception
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert any("lokalen Trade-Cache" in i.value for i in at.info)
    at.button(key="alle_signale_fetch_1286742").click()
    # Der Button-Klick sendet alle Widget-States neu (Selektion fällt auf
    # leer zurück) — dieselbe Zeile erneut setzen, wie es der Klick im
    # echten Frontend (Selektion bleibt bestehen) liefern würde.
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert geladen == [1286742]
    # Nach dem Nachladen: Detailansicht statt Lade-Hinweis
    assert not any("lokalen Trade-Cache" in i.value for i in at.info)
    assert any("DINO Scalping" in s.value for s in at.subheader)


def test_sync_button_ruft_katalog_sync(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    aufrufe = []
    monkeypatch.setattr(katalog_mod, "sync",
                        lambda log=None, kuerzel=None: aufrufe.append(kuerzel)
                        or {"quellen": {}, "gesamt": 0})
    at = _katalog_seite(monkeypatch, [_probe_mit_trades(csv_pfad)], [])
    assert not at.exception, at.exception
    at.button(key="alle_signale_sync").click()
    at.run()
    assert not at.exception, at.exception
    assert len(aufrufe) == 1 and aufrufe[0] is None


def test_erster_start_laedt_katalog_automatisch(tmp_path, monkeypatch):
    """Leerer Sync-Status → Auto-Sync (kein Netz: sync gepatcht) — und
    KEIN Retry im nächsten Rerun."""
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    aufrufe = []
    monkeypatch.setattr(katalog_mod, "sync",
                        lambda log=None, kuerzel=None: aufrufe.append(1)
                        or {"quellen": {}, "gesamt": 0})
    monkeypatch.setattr(db, "katalog_sync_status", lambda: (
        {} if not aufrufe else
        {"vant": {"gelaufen_am": "2026-10-08 15:00:00", "anzahl": 1, "fehler": None}}))
    monkeypatch.setattr(pipeline, "results_from_db", lambda: [_probe_mit_trades(csv_pfad)])
    monkeypatch.setattr(db, "list_catalog", lambda: [])
    monkeypatch.setattr(katalog_mod, "katalog_resultate", lambda: ([], {}))
    at = AppTest.from_file(str(SEITE), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert len(aufrufe) == 1
    at.run()
    assert not at.exception, at.exception
    assert len(aufrufe) == 1          # kein Retry-Loop bei Reruns


def test_filter_min_wochen(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    at = _katalog_seite(monkeypatch, [_probe_mit_trades(csv_pfad)],
                        [_katalog_probe_mit_quelle()])
    assert not at.exception, at.exception
    # DINO 17 Wochen, gescannte Probe 100 Wochen → Grenze 50 lässt nur die
    # gescannte Zeile übrig
    at.number_input(key="alle_signale_min_wochen").set_value(50.0)
    at.run()
    assert not at.exception, at.exception
    assert any("1 von 2" in c.value for c in at.caption)


def test_gescannte_zeile_ohne_trades_mit_katalogref_holt_nach(tmp_path, monkeypatch):
    """Fehlgeschlagener Scan (Quelle bekannt, kein Trade-Export): die
    Quellen-Referenz wird über das Kürzel aus dem Katalog aufgelöst —
    Button erscheint, Klick lädt und zeigt das Detail im selben Run."""
    csv_pfad = _csv(tmp_path / "t99.csv")
    db.add_quelle("vant", "VantageMonitor", "http://localhost:8092")
    db.katalog_upsert_many("vant", [
        {"signal_id": 99, "name": "Misslungener Scan", "platform": "vantage",
         "url": "u99", "version": "vantage", "abonnenten": 5.0,
         "wochen": 30.0, "risiko": None}])
    probe = pipeline.ScanResult(id=99, name="Misslungener Scan",
                                platform="vantage", quelle="vant",
                                trades_path="")
    geladen = []

    def _fake_laden(res):
        geladen.append((res.id, res.quelle_id, res.quelle_version))
        return str(csv_pfad), True

    monkeypatch.setattr(katalog_mod, "lade_signal_daten", _fake_laden)
    at = _katalog_seite(monkeypatch, [probe], [])
    assert not at.exception, at.exception
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert at.button(key="alle_signale_fetch_99") is not None
    at.button(key="alle_signale_fetch_99").click()
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    # Quelle+Version wurden über das Kürzel aufgelöst und mitgegeben
    assert geladen == [(99, db.list_quellen()[0]["id"], "vantage")]
    assert any("Misslungener Scan" in s.value for s in at.subheader)


def test_gescannte_zeile_ohne_trades_ohne_ref_zeigt_detail(tmp_path, monkeypatch):
    """Regressionsschutz: gescanntes Signal ohne Cache und ohne irgendeine
    Quellen-Referenz (reines MQL5-Direkt) zeigt weiter das Detail (KPIs „—",
    Link) statt still zu verschwinden."""
    probe = pipeline.ScanResult(id=55, name="Nur MQL5", platform="MT5",
                                quelle="mql5", trades_path="")
    at = _katalog_seite(monkeypatch, [probe], [])
    assert not at.exception, at.exception
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert not [b for b in at.button if b.key and b.key.startswith("alle_signale_fetch_")]
    assert any("Nur MQL5" in s.value for s in at.subheader)
    assert any("Kein Trade-Cache" in c.value for c in at.caption)


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


def test_kurve_unterwasser_chart_auszahlung_ist_kein_drawdown():
    """Nutzer-Fall KiraCat 05.10.: 48k Auszahlungen zeigten −97 %. Der
    dritte Kurvenwert (Fluss) senkt den Peak wie in der DD-Engine."""
    statistik = {"kurve": [["2026-01-01 10:00:00", 12_000.0, 0.0],
                           ["2026-02-01 10:00:00", 4_000.0, -8_000.0],
                           ["2026-03-01 10:00:00", 3_000.0, 0.0]]}
    unterwasser = list(kurve_unterwasser_chart(statistik).data[1].y)
    assert unterwasser[1] == 0.0
    assert unterwasser[2] == pytest.approx(-25.0)


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
    assert zeile["Geom. %/M"] is None
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
auswahl.retdd_jahr_vorbehalt = 1.32
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
    assert "TrueRetDD (Vorbehalt) ≈ 1,32" in text
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
auswahl.retdd_jahr_vorbehalt = 1.32
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



# ------------------------------------------- Nutzer-Markierungen (08.10.)
def test_markierungen_db_setzen_ueberschreiben_entfernen():
    from mqlkiscanner import db as db_mod
    db_mod.init_db()
    db_mod.setze_markierung(501, "gruen")
    db_mod.setze_markierung(502, "orange")
    assert db_mod.list_markierungen() == {501: "gruen", 502: "orange"}
    db_mod.setze_markierung(501, "gelb")          # überschreiben
    assert db_mod.list_markierungen()[501] == "gelb"
    db_mod.setze_markierung(501, None)            # entfernen
    db_mod.setze_markierung(502, None)
    assert db_mod.list_markierungen() == {}


def test_seite_markiert_zeile_und_filtert(tmp_path, monkeypatch):
    """Zeile selektieren → 🟩-Button → persistent; Markierungs-Pills filtern."""
    csv_pfad = _csv(tmp_path / "trades_m.csv")
    proben = [_probe_mit_trades(csv_pfad),            # id 42
              pipeline.ScanResult(id=43, name="Zweites", quelle="robo",
                                  wochen=40.0, abonnenten=10.0, trades_path="")]
    monkeypatch.setattr(pipeline, "results_from_db", lambda: proben)
    monkeypatch.setattr(db, "list_catalog", lambda: [])
    monkeypatch.setattr(db, "katalog_sync_status",
                        lambda: {"robo": {"gelaufen_am": "2026-10-08",
                                          "anzahl": 2, "fehler": None}})
    monkeypatch.setattr(katalog_mod, "katalog_resultate", lambda: ([], {}))

    at = AppTest.from_file(str(SEITE), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    assert "Mark." in list(at.dataframe[0].value.columns)

    # Zeile 0 (id 42) selektieren → Markierleiste → Grün
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    gruen = [b for b in at.button if b.key == "alle_signale_mark_gruen"]
    assert gruen, "Markierleiste fehlt"
    gruen[0].click()
    # Button-Klick sendet alle Widget-States neu (Selektion fällt im AppTest
    # auf leer zurück) — im echten Frontend bleibt die Zeilenauswahl bestehen.
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert db.list_markierungen() == {42: "gruen"}
    df = at.dataframe[0].value
    assert df[df["ID"] == 42]["Mark."].iloc[0] == "🟩"

    # Filter Grün: nur das grüne Signal sichtbar, das andere fällt raus
    at.pills(key="alle_signale_mark_pills").set_value(["Grün"])
    at.run()
    assert not at.exception, at.exception
    df = at.dataframe[0].value
    assert list(df["ID"]) == [42]
    assert any("1 markiert" in c.value for c in at.caption)

    # Gelb zusätzlich → beide markierten-Farben: nur 42 existiert markiert
    at.pills(key="alle_signale_mark_pills").set_value(["Grün", "Gelb", "Orange"])
    at.run()
    assert not at.exception, at.exception
    assert list(at.dataframe[0].value["ID"]) == [42]

    # Gleiche Farbe erneut klicken → abgewählt (Toggle)
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    at.button(key="alle_signale_mark_gruen").click()
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert db.list_markierungen() == {}
