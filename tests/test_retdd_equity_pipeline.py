"""RetDD und Auswahl verwenden gemessene Equity, niemals geschlossenen DD."""
import json
from dataclasses import replace

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION


def _result(**kwargs):
    values = dict(id=900009, name="Equity-Muster", forensik_vorhanden=True,
                  score=2.0, martingale_flag=False, stop_evidence="none",
                  ertrag_monat_geom_pct=12.0, cagr_jahr_pct=120.0,
                  equity_dd_rekonstruiert_pct=6.0,
                  trading_dd_pct=0.1, dd_balance_pct=10.0, dd_equity_pct=8.0,
                  retdd_monat=999.0)
    values.update(kwargs)
    return pipeline.ScanResult(**values)


def test_retdd_neuberechnung_fuer_tabelle_prompt_und_auswahl_einheitlich():
    result = _result()
    assert result.to_row()["TrueRetDD"] == 2.0
    assert result.to_row()["Gewinn %/Monat"] == 12.0
    assert pipeline.ampel_for(result, {})[0] == "🟢"
    for builder in (pipeline._kandidat_json, pipeline._forensik_json):
        payload = json.loads(builder(result))
        assert payload["retdd_monat"] == 2.0
        assert payload["retdd_jahr"] == 20.0
        assert payload["max_drawdown_equity_pct"] == 6.0
        assert payload["equity_messung_status"] == result.equity_messung_status
        assert payload["effizienz_befund"]["dd_max_equity_pct"] == 6.0


@pytest.mark.parametrize("dd", [None, 0, float("nan"), float("inf"), -1])
def test_kein_geschlossener_oder_plattform_fallback_bei_fehlender_equity(dd):
    result = _result(equity_dd_rekonstruiert_pct=dd)
    assert result.to_row()["TrueRetDD"] is None
    assert result.to_row()["Gewinn %/Monat"] == 12
    assert pipeline.ampel_for(result, {})[0] != "🟢"


def test_monitor_eq_dd_ist_nur_schrankenkanal_nicht_nenner():
    # Review 04.10.: Monitor-Closing-DD ist kein RetDD-Nenner (s. Paket D);
    # Nenner bleibt die Kurs-Rekonstruktion (6 %) -> 12/6 = 2.0.
    result = _result(monitor_trade_eq_dd_pct=20.0)
    assert result.to_row()["TrueRetDD"] == 2.0
    assert pipeline.ampel_for(result, {})[0] == "🟢"
    # Die harte Schranke sieht den Monitor weiterhin als 5. Kanal:
    result = _result(monitor_trade_eq_dd_pct=35.0)
    assert pipeline.ampel_for(result, {})[0] == "🔴"


def test_harte_schranke_bleibt_auch_bei_gutem_retdd_wirksam():
    result = _result(dd_equity_pct=34.95)
    assert result.to_row()["TrueRetDD"] == 2
    assert pipeline.ampel_for(result, {})[0] == "🔴"


def test_retdd_unter_eins_darf_nicht_zur_empfehlung_gerundet_werden():
    result = _result(ertrag_monat_geom_pct=5.99994)
    assert round(result.to_row()["TrueRetDD"], 2) == 1
    assert pipeline.ampel_for(result, {})[0] == "🟡"
    exact = replace(result, ertrag_monat_geom_pct=6.0)
    assert pipeline.ampel_for(exact, {})[0] == "🟢"


def test_ertragskriterium_nutzt_geom_und_konfigurierte_schwelle():
    result = _result(ertrag_monat_geom_pct=6.0, equity_dd_rekonstruiert_pct=3,
                     ertrag_monat_pct=50, ertrag_monat_pct_forensik=70)
    assert pipeline.ampel_for(result, {"min_ertrag_pct_monat": 7})[0] == "🟡"
    assert pipeline.ampel_for(result, {"min_ertrag_pct_monat": 5})[0] == "🟢"
    result.ertrag_monat_geom_pct = None
    assert pipeline.ampel_for(result, {})[0] == "🟡"


def test_veraltete_rendite_mit_frischem_monitor_ergibt_keinen_retdd():
    result = _result(forensik_stale=True, monitor_trade_eq_dd_pct=6)
    assert result.to_row()["Gewinn %/Monat"] is None
    assert result.to_row()["TrueRetDD"] is None
    assert result.effizienz_befund["effizienz_status"] == "veraltet"


def test_db_reload_ersetzt_alten_quotienten_durch_gemessene_equity_basis():
    db.init_db()
    db.store_scan_result(900009, {
        "name": "Persistenz", "platform": "MT5",
        "stats": {"forensik_ok": True, "forensik_version": FORENSICS_VERSION}},
        forensik={"version": FORENSICS_VERSION, "vollstaendig": True,
                  "score": 2, "trading_dd": {"pct": .1},
                  "ertrag_monat_geom_pct": 12, "cagr_jahr_pct": 120,
                  "retdd_monat": 120, "retdd_jahr": 1200,
                  "peak_exposure": {"shock_pct_max": 10},
                  "equity_rekonstruktion": {"equity_dd_pct": 6, "verlaesslich": True}})
    result = pipeline.results_from_db()[0]
    assert result.to_row()["TrueRetDD"] == 2
    assert result.ampel == "🟢"


def test_kriterien_payload_nennt_settings_und_equity_retdd():
    text = pipeline._kriterien_text({"min_ertrag_pct_monat": 7,
                                    "schranke_eq_dd_pct": 22,
                                    "min_wochen": 40, "min_abonnenten": 12})
    assert "22 %" in text and "7 %/Monat" in text
    assert "40 Wochen" in text and "12 Abonnenten" in text
    assert "Mindest-RetDD: 1,0" in text
    assert "ertrag_monat_geom_pct" in text and "gemessener Max-Equity" in text


@pytest.mark.parametrize("source,erwartet30", [
    ("equity_dd_rekonstruiert_pct", "🟢"),   # Kurse-Reko ist RetDD-Nenner
    ("monitor_trade_eq_dd_pct", "🟡"),       # Review 04.10.: Monitor nur Schranke,
])                                                  # ohne Kurse-Messung kein RetDD/Gruen
def test_geaenderte_schranke_aktualisiert_auch_reine_eigenmessung(source, erwartet30):
    result = _result(dd_equity_pct=None, dd_balance_pct=None, trading_dd_pct=None,
                     ertrag_monat_geom_pct=30.0, equity_dd_rekonstruiert_pct=None)
    setattr(result, source, 25.0)
    assert pipeline.ampel_for(result, {"schranke_eq_dd_pct": 20})[0] == "🔴"
    assert pipeline.ampel_for(result, {"schranke_eq_dd_pct": 30})[0] == erwartet30
    assert not result.schranke_verletzt


def test_ungerundeter_equity_dd_bleibt_nenner_beim_db_reload():
    db.init_db()
    db.store_scan_result(900009, {
        "name": "Rundungsgrenze", "platform": "MT5",
        "stats": {"forensik_ok": True, "forensik_version": FORENSICS_VERSION}},
        forensik={"version": FORENSICS_VERSION, "vollstaendig": True, "score": 2,
                  "ertrag_monat_geom_pct": 10.001,
                  "peak_exposure": {"shock_pct_max": 10},
                  "equity_rekonstruktion": {"equity_dd_pct": 10.00,
                                            "equity_dd_pct_raw": 10.004,
                                            "verlaesslich": True}})
    result = pipeline.results_from_db()[0]
    assert result.max_drawdown_equity_pct == 10.004
    assert result.to_row()["TrueRetDD"] < 1
    assert result.ampel == "🟡"


def test_tradeserver_sync_uebertraegt_retdd_und_gewinn_ungerundet():
    from mqlkiscanner.tradeserver_sync import signal_zeilen
    db.init_db()
    result = _result(ertrag_monat_geom_pct=5.99994)
    result.ampel, result.urteil = pipeline.ampel_for(result, {})
    payload = signal_zeilen([result])[0]
    assert payload["ertragMonatGeomPct"] == 5.99994
    assert payload["maxDrawdownEquityPct"] == 6
    assert payload["retddMonat"] == result.to_row()["TrueRetDD"] < 1
    assert payload["ampel"] == "🟡"


def test_tradeserver_sync_liefert_aktuelle_auswahlgrenzen(monkeypatch):
    from mqlkiscanner import config
    from mqlkiscanner.tradeserver_sync import signal_zeilen
    db.init_db()
    original = config.load_settings()
    monkeypatch.setattr(config, "load_settings", lambda: {
        **original, "schranke_eq_dd_pct": 22, "min_ertrag_pct_monat": 7})
    payload = signal_zeilen([_result()])[0]
    assert payload["drawdownLimitPct"] == 22
    assert payload["minReturnMonthlyPct"] == 7
    assert payload["minRetddMonthly"] == 1


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, True])
def test_equity_status_nennt_nur_tatsaechlich_verwendete_gueltige_quellen(invalid):
    result = _result(equity_dd_rekonstruiert_pct=invalid,
                     monitor_trade_eq_dd_pct=6)
    # Review 04.10.: Ungueltige Kursmessung + Monitor-Closing-DD -> RetDD
    # bleibt unbekannt; der Monitor taucht nie als Messquelle auf.
    assert result.to_row()["TrueRetDD"] is None
    assert "Monitor" not in result.equity_messung_status
    result = _result(monitor_trade_eq_dd_pct=invalid)
    assert result.to_row()["TrueRetDD"] == 2
    assert result.equity_messung_status == "Gemessen: Kurse (H1, virtuelle Trading-Equity)"


# ------------------- Vorbehaltlicher RetDD (Nutzer-Wunsch 05.10.2026) ----
def test_vorbehalt_retdd_bei_unzuverlaessiger_kursmessung():
    """„Besser als nix": Kurs-Messung existiert (roh), besteht die
    Verlässlichkeitsprüfung aber nicht -> vorbehaltlicher Wert rechnet,
    belastbarer RetDD bleibt None und sperrt Grün weiter zu."""
    result = _result(equity_dd_rekonstruiert_pct=None,
                     equity_dd_rekon_roh_pct=13.83,
                     equity_rekon_grund="Offene Position über Wechselgrenze",
                     ertrag_monat_geom_pct=1.4269, cagr_jahr_pct=18.2)
    row = result.to_row()
    # TrueRetDD (Nutzer 05.10.): EINE Spalte — der Vorbehaltswert fuellt sie,
    # der Marker steht in der Vorbehalt-Spalte.
    assert row["TrueRetDD"] == pytest.approx(1.4269 / 13.83)
    assert row["TrueRetDD (Vorbehalt)"] == pytest.approx(1.4269 / 13.83)
    # Grün bleibt gesperrt (Nutzer-Regel: RetDD nur mit belastbarer Messung).
    ampel, urteil = pipeline.ampel_for(result, {})
    assert ampel != "🟢"
    # Matrix-Zelle: ORANGE mit Vorbehalt-Erklärung.
    from mqlkiscanner.ampel_matrix import _retdd_zelle
    zelle = _retdd_zelle(result)
    assert zelle.ampel == "🟠"
    assert "VORBEHALT" in zelle.detail
    assert "Wechselgrenze" in zelle.detail


def test_vorbehalt_retdd_leer_wenn_belastbare_messung_vorliegt():
    result = _result(equity_dd_rekonstruiert_pct=6.0,
                     equity_dd_rekon_roh_pct=13.83)
    assert result.to_row()["TrueRetDD"] == 2.0
    assert result.to_row()["TrueRetDD (Vorbehalt)"] is None


def test_vorbehalt_retdd_ohne_rohe_messung_leer():
    result = _result(equity_dd_rekonstruiert_pct=None,
                     equity_dd_rekon_roh_pct=None,
                     equity_rekon_grund="keine Kurse")
    assert result.to_row()["TrueRetDD (Vorbehalt)"] is None


def test_vorbehalt_retdd_db_rundtrip_ohne_rescan():
    """Der rohe DD liegt bereits in alten Forensik-Snapshots — der
    vorbehaltliche RetDD entsteht beim DB-Laden, ganz ohne Neu-Scan."""
    db.init_db()
    db.store_scan_result(
        900123,
        {"name": "Vorbehalt Muster", "stats": {
            "forensik_ok": True, "forensik_version": FORENSICS_VERSION}},
        forensik={
            "version": FORENSICS_VERSION, "vollstaendig": True,
            "ertrag_monat_geom_pct": 1.4269, "cagr_jahr_pct": 18.2,
            "kapitalbasis": {"usd": 18560.36, "quelle": "implizit_aus_balance"},
            "peak_exposure": {"shock_pct_max": 12.0},
            "equity_rekonstruktion": {
                "status": "unvollstaendig", "verlaesslich": False,
                "equity_dd_pct": 13.83,
                "gruende": ["Offene Position über Wechselgrenze"]},
        })
    treffer = [r for r in pipeline.results_from_db() if r.id == 900123]
    assert treffer, "Signal muss im Bestand liegen"
    r = treffer[0]
    assert r.retdd_monat is None
    assert r.retdd_monat_vorbehalt == pytest.approx(1.4269 / 13.83)
    assert "RetDD ≈ 0.10/M" in (r.urteil or "")
    assert "Vorbehalt" in (r.urteil or "")
