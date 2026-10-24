"""Capital scenarios are additive and cannot restart the paid research path."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, config
from mqlkiscanner.abonnenten_analyse_store import Store


def entry(ref=1, **changes):
    return {"signal_ref": ref, "id": ref, "quelle": "mql5", "quellen_uid": "source-uid",
            "name": f"S{ref}", "abonnenten": 10, "data_done": False, "eligible": False,
            "retdd_jahr": None, "equity_dd_pct": None, "trade_history_complete": True,
            "abo_trend": {"verified": True, "delta_7": 4}, **changes}


def model(retdd, **changes):
    return {"status": "berechnet", "startkapital_usd": 10000,
            "kapital_methode": "10.000-USD-Annahme", "equity_dd_pct": 20,
            "retdd_jahr": retdd, "cagr_jahr_pct": retdd * 20,
            "nettogewinn_usd": 100, **changes}


def test_model_ranking_projects_the_model_without_mutating_measurements():
    entries = [entry(1, modell=model(8), retdd_jahr=.1),
               entry(2, modell=model(2), retdd_jahr=99, data_done=True, eligible=True)]
    originals = deepcopy(entries)
    ranked = analyse.rank_datamodus(entries, weight=30)
    assert [row["id"] for row in ranked] == [1, 2]
    for actual, original in zip(entries, originals):
        for field in ("modell", "retdd_jahr", "equity_dd_pct", "eligible", "data_done"):
            assert actual[field] == original[field]


def test_model_ranking_cannot_mix_legacy_facts_in_a_partly_processed_model_run():
    entries = [entry(1, modell=model(3)), entry(2, eligible=True, data_done=True, retdd_jahr=100)]
    assert [row["id"] for row in analyse.rank_datamodus(entries)] == [1]
    assert entries[1]["rang"] is None


@pytest.mark.parametrize("changes", [
    {"hard_excluded": True}, {"trade_history_complete": False},
    {"modell": model(3, status="datenluecke")},
    {"modell": model(3, equity_dd_pct=0)},
    {"abo_trend": {"verified": False, "delta_7": 100}},
])
def test_model_ranking_retains_missing_data_and_hard_exclusions(changes):
    row = entry(modell=model(3))
    row.update(changes)
    assert analyse.rank_datamodus([row]) == []


def test_model_only_execution_does_not_construct_source_provider_or_refresh(monkeypatch):
    from mqlkiscanner import abonnenten_analyse_daten as data
    from mqlkiscanner import abonnenten_modellworkflow as workflow
    store = Store()
    run = analyse._data_run(["mql5"], 30, None)
    run.update(modell_nur_bestand=True, kapitalmodell_aktiv=True,
               snapshot_quellen={"mql5": {"status": "fertig"}})
    store.create(run)
    original = entry()
    store.save_task(run["id"], original)
    def forbidden(*args, **kwargs):
        pytest.fail("Local scenario may not refresh sources, start a terminal or call KI")
    monkeypatch.setattr(analyse, "_snapshot", forbidden)
    monkeypatch.setattr(data, "AnalyseDaten", forbidden)
    monkeypatch.setattr(analyse, "AnalyseKI", forbidden)
    monkeypatch.setattr(analyse, "_budget_settings", forbidden)
    def calculate(store, current, entries, log, stopped):
        assert current["id"] == run["id"]
        entries[0]["modell"] = model(4)
        store.save_task(current["id"], entries[0])
        store.update(current["id"], modell_abgeschlossen=True)
    monkeypatch.setattr(workflow, "berechne_bestand", calculate)
    analyse._execute(store, run["id"], config.load_settings())
    result, saved = store.read(run["id"]), store.tasks(run["id"])[0]
    assert result["modell_abgeschlossen"]
    assert result["modell_anzahl_mit_dd"] == result["modell_anzahl_mit_retdd"] == 1
    assert result["modell_anzahl_mit_startkapital"] == 1
    assert result["daten_anzahl_mit_dd"] == 0
    assert saved["retdd_jahr"] is None and saved["equity_dd_pct"] is None
    assert saved["data_done"] is False


def test_model_copy_preserves_original_source_snapshots_and_exports(monkeypatch):
    store = Store()
    run = analyse._data_run(["mql5"], 30, None)
    run.update(status="teilweise", snapshot_quellen={"mql5": {"status": "fertig", "stand": "historical"}})
    store.create(run)
    store.save_task(run["id"], entry(grund="Historical data gap", trades_path="", trades_sha256=""))
    before_run, before_entries = store.read(run["id"]), store.tasks(run["id"])
    monkeypatch.setattr(analyse, "_launch", lambda *args: pytest.fail("Prepared-only clone cannot launch"))
    copied = analyse.modell_aus_lauf(run["id"], starten=False)
    result = store.read(copied)
    assert copied != run["id"] and result["modell_nur_bestand"]
    assert result["kapitalmodell_aktiv"] and result["modell_version"] == analyse.CAPITAL_MODEL_VERSION
    assert result["snapshot_quellen"] == before_run["snapshot_quellen"]
    assert store.read(run["id"]) == before_run and store.tasks(run["id"]) == before_entries
    assert store.spent(copied) == 0


def test_model_stop_remains_stopped_without_publishing_completion(monkeypatch):
    from mqlkiscanner import abonnenten_modellworkflow as workflow
    store = Store()
    run = analyse._data_run(["mql5"], 30, None)
    run["modell_nur_bestand"] = True
    store.create(run)
    store.save_task(run["id"], entry())
    def stop(*args, **kwargs):
        raise analyse.Angehalten("User stop")
    monkeypatch.setattr(workflow, "berechne_bestand", stop)
    analyse._execute(store, run["id"], config.load_settings())
    result = store.read(run["id"])
    assert result["status"] == "angehalten"
    assert result["modell_abgeschlossen"] is False


def test_model_resume_binds_price_alias_broker_and_all_currency_claims(monkeypatch):
    from mqlkiscanner import abonnenten_modellkapital as capital
    from mqlkiscanner import abonnenten_modellrechnung as calculation
    from mqlkiscanner import abonnenten_modellworkflow as workflow
    store = Store()
    run = analyse._data_run(["mql5"], 30, None)
    store.create(run)
    entries = [entry(trades_path="verified-fixture", trades_sha256="same-sha", trades=1,
                     account_currency="USD", trade_money_currency="USD",
                     quellen_stats={"account_currency": "USD", "broker_server": "Broker A"})]
    settings, calls = {"symbol_aliases": {"X": "A"}, "markt_symbol_suffix": ""}, []
    monkeypatch.setattr(workflow.config, "load_settings", lambda: deepcopy(settings))
    monkeypatch.setattr(workflow.db, "verify_trade_file", lambda *args: None)
    monkeypatch.setattr(workflow.parser, "load_export", lambda *args: SimpleNamespace(trades=[object()]))
    monkeypatch.setattr(capital, "kalibriere", lambda *args: {"reference": "unchanged"})
    monkeypatch.setattr(capital, "schaetze_kapital", lambda *args, **kwargs: {"kapital": 10000, "waehrung": "USD"})
    def calculate(row, proposal):
        calls.append(deepcopy(row))
        return model(3)
    monkeypatch.setattr(calculation, "berechne_modell", calculate)
    def execute():
        workflow.berechne_bestand(store, run, entries, lambda text: None, lambda: False)
    execute()
    execute()
    assert len(calls) == 1
    settings["symbol_aliases"]["X"] = "B"
    execute()
    assert len(calls) == 2
    entries[0]["quellen_stats"]["broker_server"] = "Broker B"
    execute()
    assert len(calls) == 3
    entries[0]["trade_money_currency"] = "EUR"
    execute()
    assert len(calls) == 4
