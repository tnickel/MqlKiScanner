# -*- coding: utf-8 -*-
"""Ampel-Matrix: Kriterien-Logik, Persistenz und UI-Rendern."""
from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import ampel_matrix, config, db, pipeline
from mqlkiscanner.ampel_matrix import (GRUEN, GELB, ORANGE, ROT, KEINE_DATEN,
                                       KRITERIEN, kriterien_matrix, matrix_payload)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _result(**kwargs) -> pipeline.ScanResult:
    """Referenzsignal; für RetDD muss eine eigene Equity-Messung vorliegen."""
    base = dict(
        id=111111, name="Mustersignal", dd_equity_pct=3.8, trading_dd_pct=4.57,
        martingale_flag=False, martingale_evidenz=[], stop_evidence="direct",
        stop_nachweis="Orderbuch: 383/383 mit SL", ertrag_monat_pct=21.5,
        score=3.9, shock_usd=600.0,
        max_verlustserie=7, verlustserie_usd=-120.0, forensik_vorhanden=True,
        shock_pct_max=17.5, shock_pct_peak_time="2026-08-19 16:12:32",
        shock_pct_peak_account=1966.84,  # Kontostand in USD am Peak (kein %!)
        ertrag_monat_pct_forensik=21.5, ertrag_monat_geom_pct=21.5,
        cagr_jahr_pct=301.0,
    )
    base.update(kwargs)
    return pipeline.ScanResult(**base)


def _matrix(result, settings=None):
    return kriterien_matrix(result, settings or {})


# ------------------------------------------------------------ Kriterium fuer Kriterium

def test_referenzsignal_ist_durchweg_gruen():
    matrix = _matrix(_result(equity_dd_rekonstruiert_pct=8.11))
    assert [matrix[k.key].ampel for k in KRITERIEN] == [GRUEN] * len(KRITERIEN)


def test_dd_schranke_grenzwerte():
    f = lambda **kw: _matrix(_result(**kw))["dd_schranke"].ampel
    assert f(dd_equity_pct=30.1, trading_dd_pct=None) == ROT
    assert f(dd_equity_pct=None, trading_dd_pct=34.2) == ROT
    assert f(dd_equity_pct=28.0, trading_dd_pct=None) == GELB      # Puffer 2 Punkte
    assert f(dd_equity_pct=25.0, trading_dd_pct=None) == GRUEN     # Puffer 5 Punkte
    assert f(dd_equity_pct=None, trading_dd_pct=None) == KEINE_DATEN
    # Das MAXIMUM beider Werte entscheidet, nicht der Durchschnitt.
    matrix = _matrix(_result(dd_equity_pct=3.0, trading_dd_pct=31.0))
    assert matrix["dd_schranke"].ampel == ROT


def test_dd_detail_nennt_exakte_berechnung():
    matrix = _matrix(_result(dd_equity_pct=3.8, trading_dd_pct=28.16))
    detail = matrix["dd_schranke"].detail
    assert "max(Drawdown (Plattform) 3,80 %, Trading-DD (geschlossen) 28,16 %) = 28,16 %" in detail
    assert "hält die Schranke 30 % ein" in detail
    assert "1,84 Punkte" in detail  # Puffer


def test_martingale_drei_zustaende():
    f = lambda flag, evidenz=None: _matrix(_result(
        martingale_flag=flag, martingale_evidenz=evidenz))["martingale"]
    assert f(True, ["XAUUSD Median 1,8x"]).ampel == ROT
    assert "1,8x" in f(True, ["XAUUSD Median 1,8x"]).detail
    assert f(False).ampel == GRUEN
    assert f(None).ampel == GELB


def test_stop_nachweis_stufen():
    """Nutzer-Regel 28.09.2026: fehlender SL ist NEUTRAL (kein Warnflag) —
    nur die KI darf bei begründeter Einschätzung abwerten."""
    f = lambda stufe: _matrix(_result(stop_evidence=stufe))["stop"].ampel
    assert f("direct") == GRUEN
    assert f("cluster") == GRUEN
    assert f("partial") == GELB
    assert f("none") == KEINE_DATEN   # neutral: SL nicht übertragen
    assert f(None) == KEINE_DATEN


def test_ertrag_grenzwerte():
    f = lambda wert: _matrix(_result(ertrag_monat_geom_pct=wert))["ertrag"].ampel
    assert f(5.0) == GRUEN      # Schwelle ist inklusiv
    assert f(4.99) == GELB
    assert f(0.0) == GELB
    assert f(-1.2) == ORANGE
    assert f(None) == KEINE_DATEN  # gute Plattform-/lineare Werte helfen nicht


def test_score_grenzwerte():
    f = lambda wert: _matrix(_result(score=wert))["score"].ampel
    assert f(4.9) == GRUEN
    assert f(5.0) == GELB
    assert f(6.9) == GELB
    assert f(7.0) == ORANGE
    assert _matrix(_result(score=None))["score"].ampel == KEINE_DATEN


def test_schock_nutzt_shock_pct_max_nicht_kontostand_feld():
    """shock_pct_peak_account ist ein USD-Kontostand, kein Prozentwert —
    die Zelle darf nur shock_pct_max als Prozent interpretieren."""
    matrix = _matrix(_result(shock_pct_max=128.53, shock_pct_peak_account=466.78))
    assert matrix["schock"].ampel == ORANGE
    assert "128,5 %" in matrix["schock"].detail
    assert "466,78" not in matrix["schock"].detail  # Kontostand ist kein %
    matrix = _matrix(_result(shock_pct_max=30.5058))
    assert matrix["schock"].ampel == GELB
    assert "30,5 %" in matrix["schock"].detail
    assert "kein gemessener Verlust" in matrix["schock"].detail
    f = lambda wert: _matrix(_result(shock_pct_max=wert))["schock"].ampel
    assert f(29.9) == GRUEN
    assert f(30.0) == GELB
    assert f(100.0) == GELB
    assert f(100.1) == ORANGE
    assert _matrix(_result(shock_pct_max=None))["schock"].ampel == KEINE_DATEN


def test_verlustserie_grenzwerte():
    f = lambda n: _matrix(_result(max_verlustserie=n))["serie"].ampel
    assert f(9) == GRUEN
    assert f(10) == GELB
    assert f(19) == GELB
    assert f(20) == ORANGE
    matrix = _matrix(_result(max_verlustserie=18, verlustserie_usd=-199.39))
    assert "-199 USD" in matrix["serie"].detail


def test_listen_kriterium_ausschluss_watchlist_frei(monkeypatch):
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 1, "grund": "Grid ohne SL"}],
        "watchlist": [{"id": 2, "status": "Watchlist", "grund": "Mikrokonto"}]})
    aus = _matrix(_result(id=1))["liste"]
    assert aus.ampel == ROT and "Grid ohne SL" in aus.detail
    watch = _matrix(_result(id=2))["liste"]
    assert watch.ampel == GELB and "Mikrokonto" in watch.detail
    frei = _matrix(_result(id=3))["liste"]
    assert frei.ampel == GRUEN


def test_eigene_grenzwerte_aus_settings():
    settings = {"schranke_eq_dd_pct": 20.0, "min_ertrag_pct_monat": 15.0}
    matrix = _matrix(_result(dd_equity_pct=22.0, trading_dd_pct=None,
                             ertrag_monat_pct=12.0,
                             ertrag_monat_geom_pct=12.0), settings)
    assert matrix["dd_schranke"].ampel == ROT      # 22 > 20
    assert matrix["ertrag"].ampel == GELB          # 12 < 15
    assert "20 %" in matrix["dd_schranke"].detail
    assert "15 %" in matrix["ertrag"].detail


# ---------------------------------------------------------------- Persistenz

def test_matrix_payload_ist_json_fest_und_traegt_grenzen():
    payload = matrix_payload(_result(), {"schranke_eq_dd_pct": 25.0})
    text = json.dumps(payload, ensure_ascii=False)
    wieder = json.loads(text)
    assert wieder["grenzen"]["schranke_eq_dd_pct"] == 25.0
    assert wieder["grenzen"]["min_retdd_monat"] == 1.0
    assert set(wieder["kriterien"]) == {k.key for k in KRITERIEN}
    assert wieder["kriterien"]["stop"]["ampel"] == GRUEN
    assert "Orderbuch" in wieder["kriterien"]["stop"]["detail"]


def test_forensik_mit_matrix_roundtript_durch_die_datenbank():
    db.init_db()
    forensik = {"version": 1, "vollstaendig": True,
                "kriterien_matrix": matrix_payload(_result())}
    db.store_scan_result(999001, {"name": "Matrix-Test",
                                  "stats": {"forensik_ok": True}},
                         forensik=forensik)
    katalog = {r["signal_id"]: r for r in db.list_catalog()}
    gespeichert = katalog[999001]["forensik"]  # list_catalog parst bereits
    assert gespeichert["kriterien_matrix"]["kriterien"]["dd_schranke"]["detail"]


def test_scan_pipeline_baut_matrix_in_forensik_payload():
    """_analyze_candidate_once persistiert den Matrix-Snapshot (Unit-Sicht)."""
    quelle = pipeline.ScanPipeline._analyze_candidate_once
    import inspect
    assert "kriterien_matrix" in inspect.getsource(quelle)


# --------------------------------------------------------------------- UI

def test_render_ampel_matrix_escaped_gefaehrliche_namen():
    """Signalnamen mit HTML duerfen nie als Markup landen."""
    boese = "<script>alert('x')</script> & \"Quote\""
    from mqlkiscanner import app_ui
    from types import SimpleNamespace
    import streamlit as st

    markdowns: list[str] = []
    orig = st.markdown

    def _fang(text, **kwargs):
        markdowns.append(text)
        return orig(text, **kwargs)

    st.markdown = _fang
    try:
        app_ui.render_ampel_matrix(
            [_result(name=boese, urteil="<b>Ungutes</b> Urteil")], {})
    finally:
        st.markdown = orig
    html_text = "\n".join(markdowns)
    assert "<script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "&#9432;" in html_text          # Kriteriums-ⓘ vorhanden
    assert "title=" in html_text            # Tooltips vorhanden
    assert "max(" in html_text              # exakte Berechnung im Tooltip


def test_ergebnisse_seite_rendert_ampel_matrix_ansicht():
    db.init_db()
    db.store_scan_result(999002, {
        "name": "Seiten-Test Signal", "platform": "MT5",
        "stats": {"forensik_ok": True, "eq_dd_pct": 3.8},
    }, forensik={
        "version": 1, "vollstaendig": True,
        "trading_dd": {"pct": 4.57, "usd": 158.0},
        "peak_exposure": {"positionen": 3, "netto_lots": 0.03,
                          "schock_usd": 600.0, "shock_pct_max": 17.5},
        "martingale_flag": False, "stop_evidence": "direct",
        "stop_nachweis": "Orderbuch: 383/383 mit SL", "score": 3.9,
        "symbole": "XAUUSD",
    })
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.session_state["results_view"] = "Ampeln"
    at.run()
    assert not at.exception, at.exception
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    inhalt = " ".join(getattr(m, "value", "") or "" for m in at.markdown)
    assert "Drawdown-Schranke" in inhalt
    assert "Seiten-Test Signal" in inhalt
    assert "Berechnung:" in inhalt


# --------------------------------------------------- Bal-DD in der Schranke

def test_dd_schranke_nimmt_hoechsten_von_eq_bal_trading():
    """Belegfall Gold Spike: By Equity 3,8 % vs. By Balance 8,11 % —
    der hoehste Wert entscheidet, nicht der guenstigste."""
    matrix = _matrix(_result(dd_equity_pct=3.8, dd_balance_pct=8.11,
                             trading_dd_pct=4.57))
    zelle = matrix["dd_schranke"]
    assert zelle.ampel == GRUEN
    assert "max(Drawdown (Plattform) 3,80 %, Balance-DD (Plattform) 8,11 %, Trading-DD (geschlossen) 4,57 %) = 8,11 %" in zelle.detail
    assert "21,9 Punkten Abstand" in zelle.detail


def test_dd_schranke_bal_dd_ueber_schranke_ist_rot():
    matrix = _matrix(_result(dd_equity_pct=3.8, dd_balance_pct=31.0,
                             trading_dd_pct=4.0))
    assert matrix["dd_schranke"].ampel == ROT
    assert "31,00 %" in matrix["dd_schranke"].detail


def test_dd_schranke_ohne_bal_wie_bisher():
    matrix = _matrix(_result(dd_equity_pct=None, dd_balance_pct=None,
                             trading_dd_pct=34.0))
    assert matrix["dd_schranke"].ampel == ROT
    assert "max(Trading-DD (geschlossen) 34,00 %)" in matrix["dd_schranke"].detail


# ------------------------- Review T1/2 29.09.: Vierfach-Maximum (M1)

def test_dd_zelle_wertet_reko_eq_dd_als_viertes_maximum():
    """M1: Die Audit-Zelle muss dasselbe Vierfach-Maximum zeigen wie die
    Engine — sonst sagt das Urteil ROT und sein eigener Nachweis GRUEN."""
    matrix = _matrix(_result(dd_equity_pct=10.0, dd_balance_pct=10.0,
                             trading_dd_pct=10.0,
                             equity_dd_rekonstruiert_pct=35.0))
    assert matrix["dd_schranke"].ampel == ROT
    assert "Max-DD (Kurse) 35,00 %" in matrix["dd_schranke"].detail

    # Der Tooltip beschreibt das Fünffach-Maximum (B1, Intensiv-Review
    # 29./30.09.2026: Monitor-EQ-DD kam als fünfte Komponente dazu):
    tooltip = next(k.beschreibung for k in KRITERIEN if k.key == "dd_schranke")
    assert "Max-Drawdown" in tooltip and "Max-DD (Monitor)" in tooltip


# ------------- Intensiv-Review 29./30.09.2026: B1 Monitor-Zweitmessung -------

def test_dd_zelle_wertet_monitor_eq_dd_als_fuenftes_maximum():
    """B1: Die Monitor-Zweitmessung (floating-inclusive) muss in der Audit-
    Zelle dieselbe harte Schranke reißen wie in der Engine — Lemonal blieb
    im Ziellauf 🟢 bei 46,65 % Zweitmessung."""
    matrix = _matrix(_result(dd_equity_pct=8.56, dd_balance_pct=None,
                             trading_dd_pct=2.37,
                             equity_dd_rekonstruiert_pct=None,
                             monitor_trade_eq_dd_pct=46.65))
    assert matrix["dd_schranke"].ampel == ROT
    assert "Max-DD (Monitor) 46,65 %" in matrix["dd_schranke"].detail
    assert "46,65 % > 30 %" in matrix["dd_schranke"].kurz


def test_dd_zelle_monitor_ueber_100_prozent_bekommt_vorbehalt():
    """Werte über 100 % überzeichnen absolut (Monitor-Basis) — die Zelle
    bleibt ROT, der Detail-Text nennt den Basis-Vorbehalt."""
    matrix = _matrix(_result(dd_equity_pct=16.77, trading_dd_pct=2.89,
                             monitor_trade_eq_dd_pct=241.3))
    assert matrix["dd_schranke"].ampel == ROT
    assert "überzeichnet" in matrix["dd_schranke"].detail


def test_dd_zelle_ohne_monitor_unveraendert():
    """Ohne Monitorwert bleibt die Zelle bei den bisherigen Werten."""
    matrix = _matrix(_result(dd_equity_pct=3.8, trading_dd_pct=28.16,
                             equity_dd_rekonstruiert_pct=None,
                             monitor_trade_eq_dd_pct=None))
    assert "max(Drawdown (Plattform) 3,80 %, Trading-DD (geschlossen) 28,16 %) = 28,16 %" \
        in matrix["dd_schranke"].detail


def test_dd_zelle_ohne_reko_unveraendert():
    """Reko nicht vorhanden (None) darf die bestehende Zelle nicht ändern."""
    matrix = _matrix(_result(dd_equity_pct=3.8, trading_dd_pct=28.16,
                             equity_dd_rekonstruiert_pct=None))
    assert "max(Drawdown (Plattform) 3,80 %, Trading-DD (geschlossen) 28,16 %) = 28,16 %" \
        in matrix["dd_schranke"].detail


# ------------- Intensiv-Review 29./30.09.2026: B2 Ertrag auf Forensik-Basis --

def test_ertrag_zelle_massgeblich_ist_geometrische_rendite():
    """B2: Plattform meldet 6,46 %/Monat, die eigene Kurve auf der DD-Basis
    liefert 0,5 %/Monat (Fall SafeGold) — die Zelle muss GELB zeigen und
    beide Werte im Detail nennen."""
    matrix = _matrix(_result(ertrag_monat_pct=6.46,
                             ertrag_monat_pct_forensik=8.0,
                             ertrag_monat_geom_pct=0.5))
    assert matrix["ertrag"].ampel == GELB
    assert "0,5 % < 5 %" in matrix["ertrag"].kurz
    assert "Plattform meldet 6,5 %/Monat" in matrix["ertrag"].detail
    assert "nicht maßgeblich" in matrix["ertrag"].detail


def test_ertrag_zelle_forensik_ueber_schwelle_bleibt_gruen():
    """Forensik-Basis über der Schwelle bleibt GRÜN (Fall Gold Spike:
    8,6 %/Monat auf eigener Basis)."""
    matrix = _matrix(_result(ertrag_monat_pct=24.54,
                             ertrag_monat_pct_forensik=12.0,
                             ertrag_monat_geom_pct=8.6))
    assert matrix["ertrag"].ampel == GRUEN
    assert "8,6 %/Monat" in matrix["ertrag"].kurz


def test_ertrag_zelle_ohne_geometrische_rendite_kein_fallback():
    """Lineare und gemeldete Rendite ersetzen die Auswahlbasis nicht."""
    matrix = _matrix(_result(ertrag_monat_pct=21.5,
                             ertrag_monat_pct_forensik=21.5,
                             ertrag_monat_geom_pct=None))
    assert matrix["ertrag"].ampel == KEINE_DATEN
    assert "ersetzen sie nicht" in matrix["ertrag"].detail


@pytest.mark.parametrize("wert,farbe", [
    (1.0, GRUEN), (0.9995, GELB), (0.5, GELB), (0.4999, ORANGE),
])
def test_retdd_grenzen_auf_gemessener_equity_ohne_rundung(wert, farbe):
    r = _result(ertrag_monat_geom_pct=10 * wert,
                equity_dd_rekonstruiert_pct=10.0,
                dd_equity_pct=20.0, dd_balance_pct=18.0,
                trading_dd_pct=0.1, retdd_monat=999.0)
    zelle = _matrix(r)["retdd"]
    assert zelle.ampel == farbe
    assert r.retdd_monat == pytest.approx(wert)
    assert "gemessener Max-Equity-Drawdown 10,00 %" in zelle.detail
    assert "Kurse (H1, virtuelle Trading-Equity)" in zelle.detail
    assert "Calmar/Jahr" in zelle.detail


def test_retdd_ohne_eigene_equity_loescht_alten_quotienten():
    r = _result(retdd_monat=9.0, retdd_jahr=108.0,
                dd_equity_pct=1.0, dd_balance_pct=2.0, trading_dd_pct=0.1)
    zelle = _matrix(r)["retdd"]
    assert zelle.ampel == KEINE_DATEN
    assert r.retdd_monat is None and r.retdd_jahr is None
    assert "kein Ersatznenner" in zelle.detail


def test_retdd_waehlt_hoechste_belastbare_floating_messung():
    r = _result(ertrag_monat_geom_pct=15.0, cagr_jahr_pct=120.0,
                equity_dd_rekonstruiert_pct=10.0,
                monitor_trade_eq_dd_pct=20.0, trading_dd_pct=1.0)
    zelle = _matrix(r)["retdd"]
    assert zelle.ampel == GELB
    assert r.retdd_monat == 0.75 and r.retdd_jahr == 6.0
    assert r.retdd_jahr != r.retdd_monat * 12


def test_veraltete_rendite_und_equity_erlauben_keine_gruene_zelle():
    r = _result(forensik_stale=True, equity_dd_rekonstruiert_pct=1.0,
                retdd_monat=999.0)
    matrix = _matrix(r)
    assert matrix["ertrag"].ampel == KEINE_DATEN
    assert matrix["retdd"].ampel == KEINE_DATEN
    assert "veraltet" in matrix["retdd"].detail


def test_retdd_null_drawdown_ist_undefiniert_statt_unendlich():
    zelle = _matrix(_result(equity_dd_rekonstruiert_pct=0.0))["retdd"]
    assert zelle.ampel == KEINE_DATEN
    assert "nicht definiert" in zelle.detail


def test_score_gate_entfernt_hrc_fall_wird_gruen():
    """Nutzer-Entscheidung 04.10.: Das versteckte Score-Gate (< 5,0) ist
    entfernt — realer Fall HRC Algo (pelik): DD 2,0 %, Ertrag 10,1 %/M,
    RetDD 5,1, aber Score 5,8 (Default-Dimensionen Broker/Transparenz 5,0)
    blieb Gelb. Grün entscheiden Schranke/Martingale/Ausschlussliste plus
    Ertrag und RetDD; der Score bleibt sichtbare Zahl."""
    res = pipeline.ScanResult(
        id=1, name="HRC-Fall", forensik_vorhanden=True, score=5.8,
        ertrag_monat_geom_pct=10.08, retdd_monat=5.13,
        trading_dd_pct=2.0, equity_dd_rekonstruiert_pct=2.0,
        martingale_flag=False, stop_evidence="none")
    ampel, urteil = pipeline.ampel_for(res, {})
    assert ampel == "🟢"
    # RetDD wird live nachgerechnet (10.08 / DD 2.0): ~5.0
    assert "RetDD 5.0" in urteil and "Risiko-Score 5.8" in urteil


def test_score_7_sperriert_gruen_nicht_mehr():
    res = pipeline.ScanResult(
        id=2, name="Hoher-Score-Fall", forensik_vorhanden=True, score=7.2,
        ertrag_monat_geom_pct=6.5, retdd_monat=1.4, martingale_flag=False,
        equity_dd_rekonstruiert_pct=4.0)
    assert pipeline.ampel_for(res, {})[0] == "🟢"
    # Harte Regeln greifen weiterhin VOR dem Grün:
    res2 = pipeline.ScanResult(
        id=3, forensik_vorhanden=True, score=1.2, martingale_flag=True,
        ertrag_monat_geom_pct=9.0, retdd_monat=2.0)
    assert pipeline.ampel_for(res2, {})[0] == "🔴"
