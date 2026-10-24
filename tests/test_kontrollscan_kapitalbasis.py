"""The active offline control script uses the same labelled capital anchor."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from mqlkiscanner import kapitalbasis
from mqlkiscanner.models import AccountCostRow, BalanceRow, ParsedExport, Trade
from scripts import kontrollscan_bericht as control
from scripts import kontrollscan_pdf as pdf

START = datetime(2026, 1, 1, 12)


def export(profits=(10, 10, 10), lots=None, balances=(), costs=()):
    lots = lots or [.01] * len(profits)
    trades = [Trade(START + timedelta(days=i), START + timedelta(days=i, hours=1),
                    "Buy", lot, "XAUUSD", 2000, 2001, profit)
              for i, (lot, profit) in enumerate(zip(lots, profits))]
    return ParsedExport("control.csv", "positions", trades=trades, balances=list(balances), costs=list(costs))


def assessed(parsed, **kwargs):
    result = control.eigene_analyse(parsed, **kwargs)
    result["meta"] = {"name": "Synthetic model", "externe_id": 42, "quelle": "mql5", "platform": "MT5"}
    result["fetched_at"] = "2026-01-04"
    return control.bewerte(result, {"ausgeschlossen": set()}, 42,
                           max(t.close_time for t in parsed.trades) + timedelta(hours=1))


def test_control_delegates_to_shared_regression_and_keeps_model_identity():
    parsed = export([10] * 100, [(1000 + i * 10) * .0001 for i in range(100)])
    before = deepcopy(parsed)
    result = assessed(parsed, stats={"account_currency": "USD"},
                      kontext={"signal_ref": 42, "trades_sha256": "a" * 64})
    assert result["startkapital"] == pytest.approx(1000)
    assert result["kapitalbasis_quelle"] == "modell_lot_pnl"
    assert result["kapitalbasis_modell"] and result["basis_verwendbar"] and not result["basis_bekannt"]
    assert result["pruefbar"] and result["kapitalbasis_details"]["beleg"]["trades_sha256"] == "a" * 64
    assert parsed == before


def test_real_source_initial_is_not_replaced_by_fallback():
    result = control.eigene_analyse(export(), stats={"account_currency": "USD", "initial_deposit_usd": 500})
    assert result["startkapital"] == 500 and result["basis_bekannt"]
    assert not result["kapitalbasis_modell"]


def test_costs_are_pnl_once_and_not_neutralized_as_external_cashflows():
    parsed = export([100], balances=[BalanceRow(START - timedelta(days=1), 1000)], costs=[
        AccountCostRow(START - timedelta(hours=1), -10, "fee"),
        AccountCostRow(START, -20, "fee"),
        AccountCostRow(START + timedelta(minutes=30), -30, "fee"),
    ])
    result = control.eigene_analyse(parsed)
    assert result["startkapital"] == 990
    assert result["netto_gesamt"] == 40
    assert result["max_dd_usd"] == 50
    assert result["max_dd_pct"] == pytest.approx(50 / 990)
    assert result["monatsrenditen"]["2026-01"] == pytest.approx(50 / 990)


def test_known_nonpositive_csv_base_stays_nonpositive_without_model_replacement():
    result = assessed(export(balances=[BalanceRow(START, 1000), BalanceRow(START, -1000)]))
    assert result["startkapital"] == 0
    assert not result["basis_verwendbar"] and not result["pruefbar"]
    assert not result["kapitalbasis_modell"] and result["cagr"] is None


def test_explicit_currency_conflict_stays_a_data_gap():
    with pytest.raises(ValueError, match="Widerspruechliche"):
        control.eigene_analyse(export(), stats={"account_currency": "USD"}, kontext={"trade_money_currency": "EUR"})


def test_precomputed_decision_must_match_csv_flows():
    parsed = export(balances=[BalanceRow(START, 1000)])
    decision = kapitalbasis.aufloesen(parsed)
    decision["injektion_usd"] = 1000
    with pytest.raises(ValueError, match="Vorstartbuchungen"):
        control.eigene_analyse(parsed, kapitalentscheidung=decision)


def test_metadata_loading_is_read_only_and_excludes_stored_engine_results(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "config" / "app_settings.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "known_signals.json").write_text("{}", encoding="utf-8")
    database = tmp_path / "control.sqlite"
    con = sqlite3.connect(database)
    con.executescript("""
        CREATE TABLE trade_files(signal_ref,path,fetched_at,sha256);
        CREATE TABLE signal_identitaeten(signal_ref,externe_id,quellen_uid);
        CREATE TABLE katalog_signale(signal_ref,name,quelle,platform,url,abonnenten,wochen);
        CREATE TABLE signals(signal_ref,name,quelle,platform,url,abonnenten,wochen,stats_json);
    """)
    con.execute("INSERT INTO trade_files VALUES(?,?,?,?)", (42, "snapshot.csv", "2026-01-04", "a" * 64))
    con.execute("INSERT INTO signal_identitaeten VALUES(?,?,?)", (42, 123456, "native-mql"))
    con.execute("INSERT INTO katalog_signale VALUES(?,?,?,?,?,?,?)", (42, "Native name", "mql5", "MT5", "", 10, 50))
    stats = {"account_currency": "USD", "initial_deposit_usd": 500, "broker_server": "OriginalBroker",
             "retdd_jahr": 999, "forensik": {"secret_rating": "engine"}, "kapitalbasis_virtual_usd": 10_000}
    con.execute("INSERT INTO signals VALUES(?,?,?,?,?,?,?,?)", (42, "Engine name", "mql5", "MT5", "", 10, 50, json.dumps(stats)))
    con.commit()
    con.close()
    before = database.read_bytes()
    monkeypatch.setattr(control, "ROOT", tmp_path)
    monkeypatch.setattr(control, "DB_PFAD", database)
    basis = control.lade_grundlagen()
    assert basis["meta"][42]["quellen_stats"] == {key: stats[key] for key in ("account_currency", "initial_deposit_usd", "broker_server")}
    assert basis["meta"][42]["externe_id"] == 123456
    assert basis["meta"][42]["quellen_uid"] == "native-mql"
    assert basis["meta"][42]["name"] == "Native name"
    assert basis["trade_shas"][42] == "a" * 64
    assert database.read_bytes() == before


@pytest.mark.parametrize("fault", [None, "currency", "sha"])
def test_main_stays_offline_and_presents_model_candidates_with_explicit_stage_m(tmp_path, monkeypatch, fault):
    from mqlkiscanner import parser
    path = tmp_path / "snapshot.csv"
    path.write_bytes(b"Original immutable source bytes")
    parsed = export()
    stats = {"account_currency": "USD"} if fault != "currency" else {}
    basis = {"files": {42: (str(path), "2026-01-04")}, "trade_shas": {42: "wrong" if fault == "sha" else sha256(path.read_bytes()).hexdigest()},
             "meta": {42: {"name": "Synthetic model", "quelle": "mql5", "externe_id": 123456,
                            "quellen_uid": "native-mql", "quellen_stats": stats}},
             "ausgeschlossen": set(), "dd_schranke": 50, "min_calmar": 3}
    monkeypatch.setattr(control, "lade_grundlagen", lambda: basis)
    monkeypatch.setattr(control, "CacheKursDaten", lambda: object())
    monkeypatch.setattr(control, "engine_werte", lambda: {})
    monkeypatch.setattr(parser, "load_export", lambda _: parsed)
    monkeypatch.setattr(control, "INAKTIV_TAGE", 99999)
    monkeypatch.setattr(control, "h1_max_dd", lambda *a, **k: {"h1_status": "ok", "h1_dd_pct_raw": 1})
    monkeypatch.setattr(control, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(control, "REPORT_DIR", tmp_path / "reports")
    received = []
    monkeypatch.setitem(sys.modules, "kontrollscan_pdf", SimpleNamespace(baue_pdf=lambda **kw: received.append(kw) or 1))
    control.main()
    rendered = received[0]
    if fault:
        assert 42 in rendered["fehler"] and not rendered["roh"]
    else:
        assert rendered["ranking"][0]["stufe"] == "M"
        assert rendered["ranking"][0]["kapitalbasis_modell"]
        dump = json.loads((tmp_path / "tmp" / "kontrollscan_ergebnis.json").read_text(encoding="utf-8"))
        assert dump["ranking"][0]["kapitalbasis_details"]["quelle"] == "modell_fallback_10000"
    assert path.read_bytes() == b"Original immutable source bytes"


def test_synthetic_pdf_distinguishes_model_basis_and_contains_auditable_origin(tmp_path, monkeypatch):
    result = assessed(export(), stats={"account_currency": "USD"}, kontext={"trades_sha256": "a" * 64})
    result.update(h1_status="ok", h1_dd_pct_raw=1, retdd_jahr_h1=5, retdd_monat_h1=.1,
                  stufe="M", bewertbar=True)
    monkeypatch.setattr(pdf, "TMP", tmp_path / "charts")
    path = tmp_path / "synthetic_control.pdf"
    pages = pdf.baue_pdf(pdf_pfad=path, heute=START, datenstand="Synthetic fixture", grund={"dd_schranke": 50, "min_calmar": 3, "meta": {}},
                        roh={42: result}, fehler={}, engine={}, shortlist=[result],
                        gruen_zweifelhaft=[], uebersehen=[], dd_abweichungen=[], unbewertbar_basis=[],
                        kurz_liste=[result], bewertbar=[result], h1_unvollstaendig=[], ranking=[result])
    assert pages >= 6
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    assert "MODELL-VORAUSWAHL" in text
    assert "Kapitalherkunft" in text and "Modellannahme 10.000 USD" in text
    assert "Trade-SHA" in text and "aaaa" in text
    assert "kein 10.000-USD-Modell" not in text and "Echte Kapitalbasis" not in text
    print("PDF_QA_PATH=" + str(path))
