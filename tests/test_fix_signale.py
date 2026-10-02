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


# ── Nutzer-Wunsch 29.09.: „30 von jedem" — Top-N je Quelle ────────

def _k(id_, abonnenten, quelle=None):
    c = {"id": id_, "abonnenten": abonnenten}
    if quelle:
        c["quelle_kuerzel"] = quelle
    return c


def test_export_auswahl_nimmt_top_n_je_quelle():
    """30 von jedem: 40 MQL5- + 40 Pelican-Kandidaten bei top_n=30 liefern
    30+30 — die große Quelle verdrängt die kleine nicht mehr."""
    mql5 = [_k(1000 + i, 1000 - i) for i in range(40)]        # ohne quelle_kuerzel = mql5
    peli = [_k(2000 + i, 900 - i, "pelik") for i in range(40)]
    auswahl, infos = fix_signale.waehle_fuer_export(mql5 + peli, 30, {})
    mql5_ids = [c["id"] for c in auswahl if not c.get("quelle_kuerzel")]
    peli_ids = [c["id"] for c in auswahl if c.get("quelle_kuerzel") == "pelik"]
    assert len(mql5_ids) == 30 and len(peli_ids) == 30
    # Innerhalb jeder Quelle die abonnentenstärksten:
    assert mql5_ids == [1000 + i for i in range(30)]
    assert peli_ids == [2000 + i for i in range(30)]
    assert {i["quelle"]: (i["angeboten"], i["genommen"]) for i in infos} == {
        "mql5": (40, 30), "pelik": (40, 30)}


def test_export_auswahl_fix_ids_nie_geschnitten_ohne_slot_verbrauch():
    """Fix-IDs kommen IMMER dazu und verbrauchen keine Quellen-Slots —
    selbst wenn beide Quellen voll sind."""
    mql5 = [_k(1000 + i, 1000 - i) for i in range(35)]
    peli = [_k(2000 + i, 900 - i, "pelik") for i in range(35)]
    fix_id = 1005  # läge mitten in den MQL5-Top-35
    auswahl, _ = fix_signale.waehle_fuer_export(
        mql5 + peli, 30, {"fix_signal_ids": [fix_id]})
    ids = [c["id"] for c in auswahl]
    assert fix_id in ids
    mql5_ohne_fix = [c for c in auswahl
                     if not c.get("quelle_kuerzel") and c["id"] != fix_id]
    peli_count = sum(1 for c in auswahl if c.get("quelle_kuerzel") == "pelik")
    assert len(mql5_ohne_fix) == 30, "Fix-ID verbraucht keinen MQL5-Slot"
    assert peli_count == 30
    assert len(auswahl) == 61


def test_export_auswahl_ohne_quelle_kuerzel_zaehlt_als_mql5():
    cands = [_k(i, i) for i in range(5)]
    auswahl, infos = fix_signale.waehle_fuer_export(cands, 30, {})
    assert len(auswahl) == 5
    assert infos == [{"quelle": "mql5", "angeboten": 5, "genommen": 5}]


# ---------------- Auswahl-Nachvollziehbarkeit (Nutzer-Wunsch 02.10.2026) —

def _beg(cands, status="KANDIDAT"):
    return fix_signale.begruendungseintrag(cands, status, "grund")


def test_begruendung_upsert_verhindert_duplikate():
    """Vorfilter setzt KANDIDAT, die Slot-Entscheidung präzisiert denselben
    Eintrag — am Ende steht jedes Signal GENAU EINMAL in der Liste."""
    cand = _k(1001, 50)
    begr = []
    fix_signale.begruendung_upsert(begr, _beg(cand))
    fix_signale.begruendung_upsert(
        begr, fix_signale.begruendungseintrag(cand, "AUSGEWAEHLT", "Slot 1"))
    assert len(begr) == 1
    assert begr[0]["status"] == "AUSGEWAEHLT"
    # Verschiedene Quellen mit derselben ID bleiben getrennt (IDs sind nur
    # je Quelle eindeutig).
    cand_pelik = _k(1001, 50, "pelik")
    fix_signale.begruendung_upsert(begr, _beg(cand_pelik, "OHNE_SLOT"))
    assert len(begr) == 2


def test_begruendungseintrag_uebernimmt_url_und_quelle():
    cand = _k(4711, 10, "vant")
    cand["url"] = ("https://secure.vantagemarkets.com/copyTrading/visitor/"
                   "discover/discoverDetail?strategyId=4711&mode=visitor")
    eintrag = _beg(cand)
    assert eintrag["url"] == cand["url"]
    assert eintrag["quelle"] == "vant"


def test_export_auswahl_teilscan_modus_begruendet_scope_statt_rang():
    """Im Teilscan sind die Kandidaten vorab schon auf 🟢/🟡/Fix gefiltert —
    der Grund darf dann nicht vom Abonnenten-Rang reden."""
    cands = [_k(1000 + i, 1000 - i) for i in range(3)]
    begr = []
    fix_signale.waehle_fuer_export(cands, 30, {}, begruendung=begr,
                                   modus="gelbgruen")
    assert len(begr) == 3
    assert all(e["status"] == "AUSGEWAEHLT" for e in begr)
    assert all("Teilscan-Scope" in e["grund"] for e in begr)
    assert not any("Rang 1 in Quelle" in e["grund"] for e in begr)


def test_export_auswahl_updatet_kandidat_eintraege_ohne_doppelte():
    """build_candidates hat KANDIDAT-Einträge gesetzt — die Slot-Entscheidung
    ersetzt sie (keine Doppel-Zeilen mehr in auswahl_begruendung.json)."""
    cands = [_k(1000 + i, 1000 - i) for i in range(5)]
    begr = [_beg(c) for c in cands]
    fix_signale.waehle_fuer_export(cands, 2, {}, begruendung=begr)
    ids = [e["id"] for e in begr]
    assert len(ids) == len(set(ids)) == 5
    status = {e["id"]: e["status"] for e in begr}
    assert sum(1 for s in status.values() if s == "AUSGEWAEHLT") == 2
    assert sum(1 for s in status.values() if s == "OHNE_SLOT") == 3


class _AltResult:
    """Minimaler ScanResult-Stub für teilscan-Statusquen."""

    def __init__(self, sid, ampel, name=""):
        self.id = sid
        self.ampel = ampel
        self.name = name


def test_begruende_teilscan_scope_nennt_ampel_und_neuheit():
    cands = [_k(1001, 50), _k(1002, 50), _k(1003, 50)]
    alt = [_AltResult(1001, "🟢", "Gruen"), _AltResult(1002, "🔴", "Rot")]
    begr = [_beg(c) for c in cands]
    fix_signale.begruende_teilscan_scope(begr, cands, {1001}, alt)
    by_id = {e["id"]: e for e in begr}
    assert by_id[1001]["status"] == "KANDIDAT"          # im Scope — Slot folgt
    assert by_id[1002]["status"] == "NICHT_IM_SCOPE"
    assert "🔴" in by_id[1002]["grund"] and "Teilscan" in by_id[1002]["grund"]
    assert by_id[1002]["name"] == "Rot"                 # DB-Name gewinnt
    assert by_id[1003]["status"] == "NICHT_IM_SCOPE"
    assert "noch nie bewertet" in by_id[1003]["grund"]
