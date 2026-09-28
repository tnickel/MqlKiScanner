# -*- coding: utf-8 -*-
"""Fix-IDs (Nutzer-Wunsch 28.09.2026): definierte Signal-IDs immer scannen.

Deckt die vier Bausteine ab: Persistenz (app_settings.json), Einzelabruf
fehlender Signale von der Detailseite (Crawler), Vorfilter-/Scope-Logik
(Pipeline, Teilscan) und die GUI-Markierung (Fix-Spalte in der Tabelle).
"""
from __future__ import annotations

from types import SimpleNamespace

from mqlkiscanner import config, fix_signale, pipeline
from mqlkiscanner.mql5 import crawler


# ------------------------------------------------------------------ Speicher

def test_setzen_und_lesen_rundflug():
    assert fix_signale.fix_ids() == set()
    fix_signale.setzen(2342895, True)
    fix_signale.setzen(2349227, True)
    assert fix_signale.fix_ids() == {2342895, 2349227}
    # Persistiert und sortiert in app_settings.json
    assert config.load_settings()["fix_signal_ids"] == [2342895, 2349227]
    fix_signale.setzen(2342895, False)
    assert fix_signale.fix_ids() == {2349227}
    # Erneutes Entfernen einer fehlenden ID ist unschaedlich
    fix_signale.setzen(2342895, False)
    assert fix_signale.fix_ids() == {2349227}


def test_fix_ids_robust_gegen_muell():
    assert fix_signale.fix_ids({"fix_signal_ids": ["x", None, 5, "7"]}) == {5, 7}
    assert fix_signale.fix_ids({}) == set()
    assert fix_signale.fix_ids({"fix_signal_ids": []}) == set()


# ------------------------------------------------------- Crawler-Einzelabruf

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeSession:
    def __init__(self, text: str):
        self.text = text
        self.url = None

    def get(self, url: str, extra_pause_s: float = 0.0):
        self.url = url
        return _FakeResponse(self.text)


def _detail_html(*, mt_attr: str | None, titel: str, wochen="43",
                 abonnenten="1 403") -> str:
    attr = f'<div data-mt="{mt_attr}"></div>' if mt_attr else ""
    return f"""<html><head><title>{titel}</title></head><body>{attr}
    <div class="s-list-info__item"><div class="s-list-info__label">Weeks:</div>
      <div class="s-list-info__value">{wochen}</div></div>
    <div class="s-list-info__item"><div class="s-list-info__label">Subscribers:</div>
      <div class="s-list-info__value">{abonnenten}</div></div>
    </body></html>"""


def test_fetch_signal_overview_mit_data_mt():
    html = _detail_html(
        mt_attr="5",
        titel="Copy trades of the KiraCat trading signal for MetaTrader 5 "
              "- 49 USD per month - Akl Keyrouz")
    session = _FakeSession(html)
    s = crawler.fetch_signal_overview(session, 2342895)
    assert "/en/signals/2342895" in session.url
    assert s["id"] == 2342895
    assert s["name"] == "KiraCat"
    assert s["platform"] == "MT5"
    assert s["wochen"] == 43.0
    assert s["abonnenten"] == 1403.0  # Tausender-Leerzeichen
    assert s["autor"] == "Akl Keyrouz"
    assert s["abo_preis_usd"] == 49.0
    assert s["url"].endswith("/en/signals/2342895")


def test_fetch_signal_overview_mt4_ueber_titel():
    # Ohne data-mt entscheidet der Seitentitel (Export-Pfad MT4=/history!).
    html = _detail_html(
        mt_attr=None,
        titel="Copy trades of the Gold Spike trading signal for MetaTrader 4 "
              "- 30 USD per month - Autor X")
    s = crawler.fetch_signal_overview(_FakeSession(html), 2349227)
    assert s["platform"] == "MT4"
    assert s["name"] == "Gold Spike"


def test_fetch_signal_overview_ohne_plattform_bleibt_leer():
    html = _detail_html(mt_attr=None, titel="Irgendeine MQL5-Seite ohne Muster")
    s = crawler.fetch_signal_overview(_FakeSession(html), 123)
    assert s["platform"] == ""
    assert s["name"] == "Signal 123"  # Fallback statt erfundem Namen


# ------------------------------------------------------------------ Pipeline

def _pipe(**overrides) -> pipeline.ScanPipeline:
    einstellungen = {"fix_signal_ids": [], "min_wochen": 26, "min_abonnenten": 0}
    einstellungen.update(overrides)
    return pipeline.ScanPipeline(einstellungen)


def test_build_candidates_fix_umgeht_vorfilter():
    pipe = _pipe(fix_signal_ids=[2342895])
    signals = [
        {"id": 2342895, "name": "KiraCat", "wochen": 5, "abonnenten": 2},
        {"id": 111, "name": "Zu kurz", "wochen": 3, "abonnenten": 100},
        {"id": 222, "name": "Ok", "wochen": 40, "abonnenten": 100},
    ]
    logs: list[str] = []
    kandidaten = pipe.build_candidates(signals, logs.append)
    assert [k["id"] for k in kandidaten] == [2342895, 222]
    assert any("1 Fix-ID(s) ohne Vorfilter" in z for z in logs)


def test_crawl_laedt_fehlende_fix_id_von_der_detailseite(monkeypatch):
    pipe = _pipe(fix_signal_ids=[2342895])
    monkeypatch.setattr(
        pipeline.crawler, "crawl_lists",
        lambda session, seiten_pro_liste=2, on_progress=None: [
            {"id": 1, "name": "Aus Liste", "platform": "MT5",
             "wochen": 60, "abonnenten": 500}])
    overview = {"id": 2342895, "name": "KiraCat", "platform": "MT5",
                "wochen": 43, "abonnenten": 409, "url": "u"}
    monkeypatch.setattr(
        pipeline.crawler, "fetch_signal_overview",
        lambda session, sid: dict(overview) if sid == 2342895 else None)
    logs: list[str] = []
    signals = pipe.crawl(on_progress=lambda *a: None, log=logs.append)
    assert {s["id"] for s in signals} == {1, 2342895}
    assert any("einzeln von der Signalseite geladen" in z for z in logs)


def test_crawl_vorhandene_fix_id_wird_nicht_doppelt_geladen(monkeypatch):
    pipe = _pipe(fix_signal_ids=[2342895])
    monkeypatch.setattr(
        pipeline.crawler, "crawl_lists",
        lambda session, seiten_pro_liste=2, on_progress=None: [
            {"id": 2342895, "name": "KiraCat", "platform": "MT5",
             "wochen": 43, "abonnenten": 409}])

    def _darf_nicht_passieren(session, sid):
        raise AssertionError("vorhandene Fix-ID darf nicht einzeln geladen werden")

    monkeypatch.setattr(pipeline.crawler, "fetch_signal_overview", _darf_nicht_passieren)
    logs: list[str] = []
    signals = pipe.crawl(on_progress=lambda *a: None, log=logs.append)
    assert [s["id"] for s in signals] == [2342895]
    assert any("bereits in der Liste" in z for z in logs)


def test_crawl_quellen_modus_protokolliert_fehlende_fix_id(monkeypatch):
    import mqlkiscanner.ingest as ingest
    pipe = _pipe(fix_signal_ids=[999], listen_modus="quellen")
    monkeypatch.setattr(
        ingest, "kandidaten_aus_quellen", lambda log: [
            {"id": 5, "name": "Quell-Signal", "platform": "MT5",
             "wochen": 60, "abonnenten": 10}])
    logs: list[str] = []
    signals = pipe.crawl(on_progress=lambda *a: None, log=logs.append)
    assert [s["id"] for s in signals] == [5]  # Lauf läuft weiter, kein Abbruch
    assert any("999" in z and "übergangen" in z for z in logs)


def test_crawl_fehlerhafte_fix_id_wird_uebergangen(monkeypatch):
    pipe = _pipe(fix_signal_ids=[4711])

    def _kaputt(session, sid):
        raise RuntimeError("Seite nicht erreichbar")

    monkeypatch.setattr(pipeline.crawler, "crawl_lists",
                        lambda session, seiten_pro_liste=2, on_progress=None: [])
    monkeypatch.setattr(pipeline.crawler, "fetch_signal_overview", _kaputt)
    logs: list[str] = []
    signals = pipe.crawl(on_progress=lambda *a: None, log=logs.append)
    assert signals == []
    assert any("4711" in z and "übergangen" in z for z in logs)


# ------------------------------------------------------- Scope-Helfer

def test_ordne_fix_vorne():
    fix_signale.setzen(2, True)
    cands = [{"id": 1}, {"id": 2}, {"id": 3}]
    vorne, rest = fix_signale.ordne_fix_vorne(cands, {"fix_signal_ids": [2]})
    assert [c["id"] for c in vorne] == [2]
    assert [c["id"] for c in rest] == [1, 3]
    # Begrenzung trifft nur den Rest:
    assert [c["id"] for c in (vorne + rest)[:1]] == [2]


def test_teilscan_ziel_ids_verbindet_gelbgruen_mit_fix():
    alt = [
        SimpleNamespace(id=1, ampel="🟢", source_kind="live"),
        SimpleNamespace(id=2, ampel="🔴", source_kind="live"),
        SimpleNamespace(id=3, ampel="🟡", source_kind="demo"),   # Demo nie
        SimpleNamespace(id=4, ampel="⚪", source_kind="live"),
    ]
    ziel = fix_signale.teilscan_ziel_ids(alt, {"fix_signal_ids": [2, 99]})
    assert ziel == {1, 2, 99}


# ------------------------------------------------------------------ GUI-Markierung

def test_tabelle_zeigt_fix_spalte_nur_auf_wunsch():
    from mqlkiscanner.app_ui import results_to_dataframe
    res = pipeline.ScanResult(id=2349227, name="Gold Spike")
    ohne = results_to_dataframe([res])
    assert "Fix" not in ohne.columns
    mit = results_to_dataframe([res], fix_ids={2349227})
    assert list(mit.columns[:1]) == ["Fix"]
    assert mit.loc[0, "Fix"] == "📌 FIX"
    anderer = results_to_dataframe([res], fix_ids={111})
    assert anderer.loc[0, "Fix"] == ""


# ------------------------------------------------------------------ GUI-Seite

def test_ergebnisse_seite_zeigt_fix_verwaltung_und_markierung():
    """Fix-IDs-Verwaltung ist ohne Ergebnisse erreichbar; die ID-Eingabe
    setzt eine Fix-ID, und die Tabelle zeigt anschließend 📌 FIX."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from mqlkiscanner import fix_signale as fs

    assert fs.fix_ids() == set()
    app_pfad = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    at = AppTest.from_file(app_pfad, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    body = "\n".join(m.value for m in list(at.markdown) + list(at.subheader)) + \
        "\n".join(c.value for c in at.caption)
    assert "Fix-IDs · immer scannen" in body

    at.text_input(key="fix_neue_id").set_value("2342895").run()
    assert not at.exception, at.exception
    at.button(key="fix_hinzu").click().run()
    assert not at.exception, at.exception
    assert fs.fix_ids() == {2342895}
    # Persistiert für den nächsten Scan:
    assert config.load_settings()["fix_signal_ids"] == [2342895]

    # Tabelle mit Fix-Markierung: Sitzungsergebnis mit der gesetzten ID.
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=2342895, name="KiraCat"),
        pipeline.ScanResult(id=111, name="Ohne Fix"),
    ]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception, at.exception
    assert at.dataframe, "Result table is missing"
    frame = at.dataframe[0].value
    assert "Fix" in frame.columns
    fix_zellen = dict(zip(frame["ID"], frame["Fix"]))
    assert fix_zellen[2342895] == "📌 FIX"
    assert fix_zellen[111] == ""
