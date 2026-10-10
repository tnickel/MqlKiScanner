# -*- coding: utf-8 -*-
"""Studien-Batch „Lücken füllen“ (Nutzer 08.10.2026) — Rechenkern + Persistenz.

Der Terminal-Teil wird per Fake-Anbieter ersetzt (wie test_equity_rekonstruktion):
studien_batch._laufe bekommt den Anbieter über die KursDaten-Schnittstelle —
die Tests rufen _laufe/_rechne_ein_signal direkt mit einem Fake auf und prüfen
Lückenerkennung, Persistenz, basislos-Pfad und Abbruch.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mqlkiscanner import db, pipeline, studien_batch
from mqlkiscanner.parser import load_export

ROOT = Path(__file__).resolve().parents[1]

KOPF = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def _csv(pfad: Path) -> str:
    zeilen = [
        "2026.01.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.05 10:10:00;1.1000;0;;100.0",
        "2026.01.12 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.12 10:10:00;1.1000;0;;-200.0",
        "2026.01.20 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.20 10:10:00;1.1000;0;;300.0",
    ]
    pfad.write_text(KOPF + "\n".join(zeilen) + "\n", encoding="utf-8-sig")
    return str(pfad)


class _FakeKurse:
    """Minimaler Kursanbieter (interface wie kursdaten.KursDaten)."""

    def hole_h1(self, symbol, von, bis, gmt_offset_s=0):
        # Feldnamen wie KursDaten (time epoch, open/high/low/close). Das
        # Muster läuft über die WOCHE (168 h — Broker-Rhythmus): Die
        # Trade-Preise (1.1000) treffen nur in der Basis-Stunde je Woche,
        # also GENAU EINEN GMT-Offset zu 100 % (andere 0 %) — die Auto-GMT-
        # Erkennung wird eindeutig (konstante Kurse wären mehrdeutig).
        basis = (von // 3600) % 168
        return [{"time": von + i * 3600,
                 "open": wert, "high": wert, "low": wert, "close": wert}
                for i in range(0, max(30, (bis - von) // 3600))
                for wert in (1.1 if ((von // 3600 + i) % 168) == basis else 1.5,)]

    def hat_weiteren_terminal(self):
        return False

    def beenden(self):
        pass


# ---------------------------------------------------- Lückenerkennung
def test_luecken_sammeln_trennt_belegt_luecke_und_rechenbar(tmp_path):
    csv_pfad = _csv(tmp_path / "t1.csv")
    mit_messung = pipeline.ScanResult(id=1, name="Belegt", quelle="vant",
                                      trades_path=csv_pfad,
                                      equity_dd_rekonstruiert_pct=12.0)
    ohne_alles = pipeline.ScanResult(id=2, name="Lücke mit Quelle", quelle="vant",
                                     quelle_id=7, quelle_version="vantage",
                                     trades_path="")
    ohne_quelle = pipeline.ScanResult(id=3, name="MQL5 ohne Cache", quelle="mql5",
                                      trades_path="")
    jobs, erledigt = studien_batch.luecken_sammeln(
        [mit_messung, ohne_alles, ohne_quelle], {}, trades_nachladen=True)
    ids = {r.id for r in jobs}
    assert ids == {2}                       # 1 belegt, 3 ohne Quelle nicht rechenbar
    assert erledigt == 1
    # Ohne Nachladen ist auch 2 nicht rechenbar (kein Cache)
    jobs2, _ = studien_batch.luecken_sammeln(
        [mit_messung, ohne_alles, ohne_quelle], {}, trades_nachladen=False)
    assert jobs2 == []


def test_luecken_sammeln_gueltige_studie_ist_keine_luecke_mehr():
    res = pipeline.ScanResult(id=9, name="Hat Studie", quelle="vant", trades_path="")
    # Gültig = SHA passt UND ein Drawdown-Wert existiert. Eine Studie ohne
    # dd (z. B. "Kursdaten fehlen") ist KEINE gefüllte Lücke mehr (09.10.).
    studien = {9: {"trades_sha": "", "dd_usd": 5.0, "basislos": 0,
                   "cagr_jahr_pct": None, "ertrag_monat_geom_pct": None,
                   "report": {"equity_dd_pct": 7.5}}}
    leere_studie = {9: {"trades_sha": "", "basislos": 0, "report": {}}}
    jobs_leer, erledigt_leer = studien_batch.luecken_sammeln(
        [res], leere_studie, trades_nachladen=False)
    assert erledigt_leer == 0          # ohne dd-Wert gilt sie als Lücke
    jobs, erledigt = studien_batch.luecken_sammeln([res], studien,
                                                   trades_nachladen=True)
    assert jobs == [] and erledigt == 1
    # Abweichender SHA → Studie veraltet → Lücke bleibt (mit Quelle, die
    # den Trade-Nachladen ermöglichen kann)
    res.trades_sha256 = "neu"
    res.quelle = "vant"
    res.quelle_id = 7
    res.quelle_version = "vantage"
    studien[9]["trades_sha"] = "alt"
    jobs2, erledigt2 = studien_batch.luecken_sammeln([res], studien,
                                                     trades_nachladen=True)
    assert len(jobs2) == 1 and erledigt2 == 0


# --------------------------------- Rechenkern mit Fake-Kursen (kein Terminal)
def test_rechne_ein_signal_mit_basis_persistiert_studie(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "t5.csv")
    res = pipeline.ScanResult(id=5, name="Mit Basis", quelle="vant", trades_path=csv_pfad,
                              trades_sha256="sha5")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats",
                        lambda r: {"kapitalbasis_virtual_usd": 10_000.0,
                                   "initial_deposit_usd": None})
    control = {"uebersprungen": 0}
    anbieter = _FakeKurse()
    studien_batch._rechne_ein_signal(res, control, anbieter, False)
    zeile = db.get_equity_studie(5)
    assert zeile is not None
    assert zeile["basislos"] in (0, False)
    assert zeile["cagr_jahr_pct"] is not None or zeile["ertrag_monat_geom_pct"] is not None
    report = zeile["report"]
    assert report.get("test") == "equity_rekonstruktion"


def test_rechne_ein_signal_ohne_basis_nimmt_virtuelle_10k(tmp_path, monkeypatch):
    """Nutzer 08.10.: Keine Kontobasis → VIRTUELLE 10.000-USD-Annahme
    (klar markiert) statt leerer Spalten — Prozente füllen die Tabelle."""
    csv_pfad = _csv(tmp_path / "t6.csv")
    res = pipeline.ScanResult(id=6, name="Basislos", quelle="vant",
                              trades_path=csv_pfad, trades_sha256="sha6")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats", lambda r: {})
    control = {"uebersprungen": 0}
    assert studien_batch._rechne_ein_signal(res, control, _FakeKurse(), False) is True
    zeile = db.get_equity_studie(6)
    assert zeile is not None
    assert zeile["virtuell"] in (1, True)
    assert zeile["basislos"] in (0, False)
    assert zeile["dd_usd"] is not None
    # studie_anwenden: virtuelle Prozente nur in ANZEIGE-Felder — niemals
    # in die Workflow-Schranken (equity_dd_rekonstruiert_pct bleibt frei)
    pipeline.studie_anwenden(res, {6: zeile})
    assert res.true_dd_usd is not None
    assert res.true_dd_virtuell_pct is not None
    assert res.true_dd_basis_virtuell is True
    assert res.max_drawdown_equity_pct is None
    assert res.equity_dd_rekonstruiert_pct is None
    assert res.equity_dd_rekon_roh_pct is None
    assert res.retdd_jahr is None          # nicht im Workflow-Gate
    if zeile.get("cagr_jahr_pct"):
        assert res.retdd_virtuell_jahr is not None


def test_rechne_ein_signal_ohne_trades_pfad_ist_uebersprungen_und_zaehlt_einmal():
    """Rückgabewert False = übersprungen; der Zähler läuft nur in _laufe —
    _rechne_ein_signal darf nicht zusätzlich zählen (Doppelcount, Review)."""
    res = pipeline.ScanResult(id=8, name="Ohne Trades", quelle="vant",
                              trades_path="", trades_sha256="")
    control = {"uebersprungen": 0, "skipped_gruende": []}
    ok = studien_batch._rechne_ein_signal(res, control, _FakeKurse(), False)
    assert ok is False
    # _rechne_ein_signal zählt selbst NICHT — nur _laufe zählt bei False.
    assert control["uebersprungen"] == 0


def test_luecken_sammeln_alte_nur_usd_studien_werden_neu_gerechnet():
    res = pipeline.ScanResult(id=15, name="Alt nur-USD", quelle="vant",
                              trades_path="t.csv", trades_sha256="s")
    studien = {15: {"trades_sha": "s", "basislos": 1, "virtuell": 0,
                    "report": {}, "dd_usd": 5.0}}
    jobs, erledigt = studien_batch.luecken_sammeln([res], studien,
                                                   trades_nachladen=True)
    assert len(jobs) == 1 and erledigt == 0   # wird als virtuell neu gerechnet


def test_studie_anwenden_fuellt_luecke_mit_verlaesslicher_messung():
    res = pipeline.ScanResult(id=11, name="Studie belastbar", quelle="vant",
                              trades_sha256="abc")
    studien = {11: {
        "trades_sha": "abc", "basislos": 0,
        "cagr_jahr_pct": 36.0, "ertrag_monat_geom_pct": 2.6,
        "dd_usd": 1_200.0,
        "report": {"test": "equity_rekonstruktion", "verlaesslich": True,
                   "equity_dd_pct": 12.0, "equity_dd_pct_raw": 12.0,
                   "equity_dd_usd": 1_200.0, "gmt_offset_h": 2,
                   "status": "ok", "grund": "", "abdeckung_pct": 99.0,
                   "methodik": "m", "zeitbasis": {},
                   "symbole_ohne_kurse": [], "symbole_ohne_kontrakt": []}}}
    pipeline.studie_anwenden(res, studien)
    assert res.max_drawdown_equity_pct == pytest.approx(12.0)
    assert res.equity_dd_rekonstruiert_pct == pytest.approx(12.0)
    assert res.true_dd_usd == pytest.approx(1_200.0)
    # TrueRetDD-Familie wie refresh_efficiency: CAGR ÷ gemessener DD
    assert res.retdd_jahr == pytest.approx(3.0)
    assert res.retdd_monat == pytest.approx(2.6 / 12.0)


def test_studie_anwenden_vorbehalt_wenn_nicht_verlaesslich():
    res = pipeline.ScanResult(id=12, name="Studie roh", quelle="vant",
                              trades_sha256="abc")
    studien = {12: {
        "trades_sha": "abc", "basislos": 0,
        "cagr_jahr_pct": 36.0, "ertrag_monat_geom_pct": 2.0, "dd_usd": None,
        "report": {"verlaesslich": False, "equity_dd_pct_raw": 18.0,
                   "equity_dd_pct": 18.0, "grund": "Wechselgrenze",
                   "status": "roh", "gmt_offset_h": None, "abdeckung_pct": None,
                   "methodik": "", "zeitbasis": {}, "symbole_ohne_kurse": [],
                   "symbole_ohne_kontrakt": []}}}
    pipeline.studie_anwenden(res, studien)
    assert res.max_drawdown_equity_pct is None
    assert res.equity_dd_rekon_roh_pct == pytest.approx(18.0)
    assert res.retdd_jahr is None
    assert res.retdd_jahr_vorbehalt == pytest.approx(2.0)


def test_studie_anwenden_forensik_gewinnt_und_sha_schuetzt():
    # Forensik-Wert vorhanden → Studie wird NICHT angewendet
    res = pipeline.ScanResult(id=13, name="Forensik",
                              equity_dd_rekonstruiert_pct=5.0, trades_sha256="x")
    studien = {13: {"trades_sha": "x", "basislos": 0, "dd_usd": 9.0,
                    "report": {"verlaesslich": True, "equity_dd_pct": 99.0}}}
    pipeline.studie_anwenden(res, studien)
    assert res.equity_dd_rekonstruiert_pct == 5.0
    assert res.true_dd_usd is None
    # SHA weicht ab → veraltete Studie wird nicht angewendet
    res2 = pipeline.ScanResult(id=14, name="Alt", trades_sha256="neu")
    studien2 = {14: {"trades_sha": "alt", "basislos": 0, "dd_usd": 1.0,
                     "report": {"verlaesslich": True, "equity_dd_pct": 7.0}}}
    pipeline.studie_anwenden(res2, studien2)
    assert res2.max_drawdown_equity_pct is None


def test_results_from_db_bezieht_studien_ein(tmp_path):
    db.init_db()
    csv_pfad = _csv(tmp_path / "t21.csv")
    db.upsert_signal(21, name="Nur Studie", platform="vantage", quelle="vant")
    db.store_equity_studie(21, "", {"verlaesslich": True, "equity_dd_pct": 9.0,
                                    "equity_dd_pct_raw": 9.0, "equity_dd_usd": 800.0,
                                    "test": "equity_rekonstruktion"},
                           cagr_jahr_pct=27.0, ertrag_monat_geom_pct=2.0,
                           dd_usd=800.0, basislos=False)
    ergebnisse = pipeline.results_from_db()
    res = next(r for r in ergebnisse if r.id == 21)
    assert res.max_drawdown_equity_pct == pytest.approx(9.0)
    assert res.true_dd_usd == pytest.approx(800.0)
    assert res.retdd_jahr == pytest.approx(3.0)


# ------------------------------------------------------------------ UI-Flow
def test_seite_zeigt_batch_button_panel_und_usd_spalte(tmp_path, monkeypatch):
    """Button → Panel (Zählung + Optionen) → Start ruft studien_batch.starten;
    die Tabelle trägt die Spalte True-DD USD mit Studien-Werten."""
    from streamlit.testing.v1 import AppTest
    from mqlkiscanner import katalog as katalog_mod
    from mqlkiscanner import alle_signale_ui as ui

    csv_pfad = _csv(tmp_path / "t31.csv")
    db.init_db()
    db.store_equity_studie(31, "", {"verlaesslich": True, "equity_dd_pct": 10.0,
                                    "equity_dd_pct_raw": 10.0, "equity_dd_usd": 777.0},
                           dd_usd=777.0, basislos=False)
    probe = pipeline.ScanResult(id=31, name="Mit Studie", quelle="vant",
                                trades_path=csv_pfad)
    pipeline.studie_anwenden(probe, {31: db.get_equity_studie(31)})
    monkeypatch.setattr(pipeline, "results_from_db", lambda: [probe])
    monkeypatch.setattr(db, "list_catalog", lambda: [])
    monkeypatch.setattr(db, "katalog_sync_status",
                        lambda: {"vant": {"gelaufen_am": "2026-10-08", "anzahl": 1,
                                          "fehler": None}})
    monkeypatch.setattr(katalog_mod, "katalog_resultate", lambda: ([], {}))
    aufrufe = []
    monkeypatch.setattr(studien_batch, "starten",
                        lambda resultate, nur_luecken=True, trades_nachladen=True:
                        aufrufe.append((nur_luecken, trades_nachladen)) or object())

    at = AppTest.from_file(str(ROOT / "app_pages" / "alle_signale.py"),
                           default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    df = at.dataframe[0].value
    assert "True-DD USD" in list(df.columns)
    assert abs(df[df["Name"] == "Mit Studie"]["True-DD USD"].iloc[0] - 777.0) < 0.01

    knopf = [b for b in at.button if b.key == "alle_signale_batch"]
    assert knopf, "Batch-Button fehlt"
    knopf[0].click()
    at.run()
    assert not at.exception, at.exception
    assert any("noch keinen echten Drawdown" in m.value for m in at.markdown)
    # Checkbox default: nur Lücken füllen
    assert at.checkbox(key="alle_signale_batch_nur_luecken").value is True
    at.button(key="alle_signale_batch_start").click()
    at.run()
    assert not at.exception, at.exception
    assert aufrufe == [(True, True)]
