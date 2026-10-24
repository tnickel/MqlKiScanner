"""Capital estimates stay model evidence through gates, storage and reports."""
from copy import deepcopy
import json

import pytest

from mqlkiscanner import ampel_matrix, config, db, pdf_reports, pipeline, scoring
from mqlkiscanner.analysis_version import FORENSICS_VERSION


def decision(source="modell_lot_pnl", capital=1000):
    return {"version": 1, "kapital": capital, "injektion_usd": capital,
            "waehrung": "USD", "quelle": source, "modell": source.startswith("modell_"),
            "gueltig": capital > 0, "methode": source,
            "unsicherheit": "Kapital nur aus Lot-/Gewinnverlauf geschätzt.",
            "beleg": {"trades_sha256": "a"*64, "erster_trade": "2026-01-01T00:00:00"},
            "annahmen": ["Spätere native Kapitalflüsse bleiben erhalten."]}


def result(source="modell_lot_pnl", **changes):
    values = dict(id=987654321, name="Capital fixture", quelle="mql5", account_currency="USD",
                  forensik_vorhanden=True, martingale_flag=False, stop_evidence="none",
                  kapitalbasis_verwendet_usd=1000, kapitalbasis_verwendet_quelle=source,
                  kapitalbasis_befund=decision(source), equity_dd_rekonstruiert_pct=10,
                  ertrag_monat_geom_pct=4, cagr_jahr_pct=60, score=3,
                  trading_dd_pct=5, shock_pct_max=10, trades_sha256="a"*64)
    values.update(changes)
    return pipeline.ScanResult(**values)


@pytest.fixture(autouse=True)
def no_exclusions(monkeypatch):
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": [], "watchlist": []})


@pytest.mark.parametrize("source", ["modell_lot_pnl", "modell_lots_kalibriert", "modell_fallback_10000",
                                    "modell_closing_dd_anker", "virtuelle_annahme"])
def test_every_model_source_blocks_automatic_green(source):
    r=result(source)
    color,text=pipeline.ampel_for(r,{"schranke_eq_dd_pct":50})
    assert r.retdd_jahr==6
    assert color=="🟡" and "Kapital" in text
    assert r.kapitalbasis_ist_modell
    assert r.effizienz_befund["effizienz_status"]=="modellrechnung"
    assert r.equity_messung_status.startswith("Modellrechnung")


@pytest.mark.parametrize("changes", [{"martingale_flag":True}, {"dd_equity_pct":80},
                                     {"equity_dd_rekonstruiert_pct":80, "modellpruefung_vorhanden":True,
                                      "forensik_vorhanden":False}])
def test_model_provenance_does_not_weaken_hard_red_rules(changes):
    r=result(**changes)
    assert pipeline.ampel_for(r,{"schranke_eq_dd_pct":50})[0]=="🔴"


def test_invalid_derived_native_metadata_does_not_override_new_capital_decision():
    r=result(kapitalbasis_usd=-100)
    assert pipeline.ampel_for(r,{"schranke_eq_dd_pct":50})[0]=="🟡"
    real=decision("csv_einzahlungen")
    r=result("csv_einzahlungen",kapitalbasis_befund=real,kapitalbasis_usd=-100)
    assert pipeline.ampel_for(r,{"schranke_eq_dd_pct":50})[0]=="🟢"
    r.kapitalbasis_befund=decision("csv_einzahlungen",capital=0)
    assert pipeline.ampel_for(r,{"schranke_eq_dd_pct":50})[0]=="🔴"


def test_matrix_cannot_paint_model_percentages_as_proven_green():
    r=result()
    matrix=ampel_matrix.kriterien_matrix(r,{"schranke_eq_dd_pct":50})
    for key in ("dd_schranke","ertrag","retdd","score","schock"):
        assert matrix[key].ampel!="🟢",key
        assert "Modell" in matrix[key].kurz or "Modell" in matrix[key].detail or "geschätzt" in matrix[key].detail


def test_model_metadata_binds_prompt_and_report_basis_without_fake_account_completeness():
    r=result(modellpruefung_vorhanden=True)
    facts=json.loads(pipeline._forensik_json(r))
    assert facts["forensik_vollstaendig"] is False
    assert facts["modellpruefung_vollstaendig"] is True
    assert facts["kapitalbasis_verwendet"]["modell"] is True
    assert facts["kapitalbasis_verwendet"]["details"]==r.kapitalbasis_befund
    first=pipeline.report_basis_for(r,{})
    r.kapitalbasis_befund["unsicherheit"]="Anderer belegter Unsicherheitsbefund"
    assert pipeline.report_basis_for(r,{})!=first


def test_scoring_distinguishes_complete_model_from_complete_account_evidence():
    d=decision()
    report={"stats":{},"forensics":{
        "kapitalbasis":d,"drawdown":{"kapitalbasis_details":d,"startkapital_quelle":d["quelle"],
                                    "trading_dd":{"dd_pct":5}},
        "martingale":{"flag":False},"stops":{"stop_evidence":"none"},
        "exposure":{"shock_pct_max":10,"capital_history_complete":False,"model_capital_available":True,
                    "contract_complete":True,"conversion_complete":True,"temporal_risk_available":True}}}
    ev=scoring.evaluate(report)
    assert ev["forensics_complete"] is False and ev["model_forensics_complete"] is True
    assert ev["urteil_gueltig"] is False and ev["kapitalbasis_modell"] is True
    report["forensics"]["exposure"]["conversion_complete"]=False
    assert scoring.evaluate(report)["model_forensics_complete"] is False


def test_model_provenance_survives_existing_json_storage_without_schema_migration():
    d=decision()
    db.upsert_signal(987654321,name="Stored model",platform="MT5",quelle="mql5",stats={
        "forensik_ok":False,"forensik_version":FORENSICS_VERSION,"account_currency":"USD",
        "account_currency_evidence_version":FORENSICS_VERSION,"kapitalbasis_befund":d})
    db.store_forensik(987654321,{"version":FORENSICS_VERSION,"vollstaendig":False,
        "modellpruefung_vollstaendig":True,"kapitalbasis":{"usd":1000,"quelle":d["quelle"],"details":d},
        "peak_exposure":{"shock_pct_max":10},"martingale_flag":False,"score":3,
        "ertrag_monat_geom_pct":4,"cagr_jahr_pct":60,
        "equity_rekonstruktion":{"status":"ok","verlaesslich":True,"equity_dd_pct_raw":10}},quelle="mql5")
    saved=next(x for x in pipeline.results_from_db() if x.id==987654321)
    assert saved.kapitalbasis_befund==d and saved.modellpruefung_vorhanden
    assert saved.forensik_vorhanden is False and saved.ampel=="🟡"
    assert json.loads(pipeline._forensik_json(saved))["kapitalbasis_verwendet"]["details"]==d


def test_study_keeps_its_own_capital_and_returns_without_overwriting_engine_basis():
    r=result(equity_dd_rekonstruiert_pct=None,cagr_jahr_pct=80)
    engine=deepcopy(r.kapitalbasis_befund)
    d=decision("modell_lots_kalibriert",capital=2000)
    study={"trades_sha":r.trades_sha256,"virtuell":True,"dd_usd":100,"cagr_jahr_pct":50,
           "ertrag_monat_geom_pct":3,"report":{"status":"ok","verlaesslich":True,
              "equity_dd_pct_raw":5,"kapitalbasis_details":d,"kapitalbasis_usd":2000}}
    pipeline.studie_anwenden(r,{r.signal_key:study})
    assert r.true_dd_kapitalbasis_details==d and r.true_dd_kapitalbasis_usd==2000
    assert r.true_dd_cagr_jahr_pct==50 and r.retdd_virtuell_jahr==10
    assert r.kapitalbasis_befund==engine and r.cagr_jahr_pct==80
    assert r.equity_dd_rekonstruiert_pct is None


def test_different_real_study_and_engine_denominators_are_not_mixed():
    r=result("csv_einzahlungen",equity_dd_rekonstruiert_pct=None,cagr_jahr_pct=80)
    d=decision("csv_einzahlungen",capital=2000)
    study={"trades_sha":r.trades_sha256,"virtuell":False,"dd_usd":100,"cagr_jahr_pct":50,
           "report":{"status":"ok","verlaesslich":True,"equity_dd_pct_raw":5,
                     "kapitalbasis_details":d,"kapitalbasis_usd":2000}}
    pipeline.studie_anwenden(r,{r.signal_key:study})
    assert r.studie_anzeige_dd_pct==5 and r.equity_dd_rekonstruiert_pct is None
    assert r.cagr_jahr_pct==80 and r.true_dd_cagr_jahr_pct==50


def test_pdf_code_appendix_keeps_estimate_and_uncertainty_visible():
    r=result(gesamtbericht="# Bericht\n\nVorliegender KI-Text.")
    report,_=pdf_reports.result_pdf_spec(r,"gesamtbericht")
    assert "Kapitalbasis — Codebefund" in report.body
    assert "modell_lot_pnl" in report.body and "Lot-/Gewinnverlauf geschätzt" in report.body
    assert "keine automatische Grünfreigabe" in report.body
    appendix=pdf_reports._anhang_markdown([r],"",empfehlungen=[r])
    assert "Equity-DD (H1-Modellszenario)" in appendix and "Modell-RetDD" in appendix
    assert "Kapitalunsicherheit" in appendix
    r.gesamtbericht=""
    assert pdf_reports.result_pdf_spec(r,"gesamtbericht")[0].body==""


def test_capital_rule_change_has_explicit_version_boundary():
    assert FORENSICS_VERSION==22
