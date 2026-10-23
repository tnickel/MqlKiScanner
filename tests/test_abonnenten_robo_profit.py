"""Robo-Ratingprofitabilität bleibt von unbelegter Tradeforensik getrennt."""
from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

from mqlkiscanner import abonnenten_analyse_daten as daten
from mqlkiscanner import db
from mqlkiscanner.downloader_client import DownloaderConnectionError


@pytest.fixture
def robo_env(monkeypatch):
    qid = db.add_quelle("robo", "Synthetic Robo rating", "http://synthetic-robo:8198")
    quelle = db.get_quelle(qid)
    entry = dict(quelle="robo", id=811, quelle_id=qid, quelle_version="mql5",
                 quellen_uid=quelle["quellen_uid"], signal_ref=None, name="Synthetic rating")
    forbidden_calls = []

    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("Ratingprofitabilität darf weder Trades noch Terminal/Forensik starten")

    class Client:
        def __init__(self):
            self.calls = []
            self.failure = None
            self.answer = {"signalId": "811", "version": "mql5", "metrics": {
                "ProfitUsd": 125.5, "YieldWindowPct": 12.0, "YieldWindowMonths": 6,
                "RatingBalanceUsd": 1125.5, "RatingCurrency": "USD", "Currency": None,
                "RawMoneyCurrency": "unknown", "TradeUnitStatus": "unverified",
                "TradeExportAvailable": False, "TradeHistorySupported": True,
                "EquityDrawdown": None}}

        def metrics(self, sid, version):
            self.calls.append((sid, version))
            if self.failure:
                raise self.failure
            return copy.deepcopy(self.answer)

        refresh_provider = staticmethod(forbidden)
        trades_csv = staticmethod(forbidden)

    client = Client()
    monkeypatch.setattr(daten.quellen, "client_fuer_quelle", lambda _q: client)
    monkeypatch.setattr(daten.ingest, "hole_trades", forbidden)
    monkeypatch.setattr(daten.kursdaten, "KursDaten", forbidden)
    monkeypatch.setattr(daten.engine, "analyze", forbidden)
    monkeypatch.setattr(daten, "_rekonstruiere_mit_feed_fallback", forbidden)
    monkeypatch.setattr(db, "snapshot_trade_file", forbidden)
    monkeypatch.setattr(db, "store_forensik", forbidden)
    monkeypatch.setattr(db, "store_equity_studie", forbidden)
    real_metrics = daten.ingest.hole_metrics
    metric_options = []

    def metrics(*args, **kwargs):
        metric_options.append(kwargs)
        return real_metrics(*args, **kwargs)

    monkeypatch.setattr(daten.ingest, "hole_metrics", metrics)
    yield entry, client, metric_options
    assert not forbidden_calls


def berechne(entry, **kwargs):
    with daten.AnalyseDaten({}) as service:
        return service.berechne(entry, **kwargs)


@pytest.mark.parametrize("version", ["mql4", "mql5", "rst"])
def test_robo_ratingprofit_ohne_tradefreigabe_fuer_alle_quellenplattformen(robo_env, version):
    entry, client, options = robo_env
    entry["quelle_version"] = client.answer["version"] = version
    client.answer["metrics"]["TradeHistorySupported"] = version != "rst"
    result = berechne(entry)
    assert result["auswertung_typ"] == "quellenprofitabilitaet"
    assert result["data_complete"] and not result["eligible"]
    assert result["gewinn_usd"] == 125.5
    assert result["rendite_quelle_pct"] == 12.0
    assert result["rendite_quelle_monate"] == 6
    assert result["rating_balance_usd"] == 1125.5
    assert result["profitabilitaet"] == "positiv"
    assert client.calls == [(811, version)]
    assert len(options) == 1 and options[0]["allow_offline_cache"] is False
    assert options[0]["client"] is client
    assert result["account_currency"] is None
    assert result["kapitalbasis_usd"] is None
    assert result["retdd_jahr"] is None and result["equity_dd_pct"] is None
    assert result["trades"] is None and result["dauer_monate"] is None
    assert not result["trades_path"] and not result["trades_sha256"]
    assert not result["forensik"] and not result["equity"]
    assert "refresh" not in result
    assert result["finanzdaten_stand"] is None
    assert "unbekannt" in result["messhinweis"].lower()
    read_at = dt.datetime.fromisoformat(result["daten_gelesen_am"].replace("Z", "+00:00"))
    assert abs((dt.datetime.now(tz=read_at.tzinfo) - read_at).total_seconds()) < 60


@pytest.mark.parametrize("profit,status", [(123, "positiv"), (-5.25, "negativ"), (0, "unveraendert")])
def test_profitstatus_folgt_ausschliesslich_usd_gewinnvorzeichen(robo_env, profit, status):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"ProfitUsd": profit, "YieldWindowPct": -80, "YieldWindowMonths": 3}
    result = berechne(entry)
    assert result["data_complete"]
    assert result["gewinn_usd"] == profit
    assert result["profitabilitaet"] == status
    assert result["rendite_quelle_pct"] == -80


@pytest.mark.parametrize("bad", [None, True, "125.5", float("nan"), float("inf"), float("-inf"), {}, []])
def test_unbelegter_gewinn_wird_nicht_als_gueltige_zahl_oder_null_ausgegeben(robo_env, bad):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"ProfitUsd": bad}
    result = berechne(entry)
    assert result["gewinn_usd"] is None
    assert result["profitabilitaet"] == "unbekannt"
    assert not result["data_complete"]


@pytest.mark.parametrize("metrics,profit,status,complete", [
    ({}, None, "unbekannt", False),
    ({"ProfitUsd": None}, None, "unbekannt", False),
    ({"ProfitUsd": 0}, 0, "unveraendert", True),
])
def test_native_null_und_echte_null_bleiben_bis_zum_scanner_ergebnis_unterschieden(
        robo_env, metrics, profit, status, complete):
    entry, client, _ = robo_env
    client.answer["metrics"] = metrics
    result = berechne(entry)
    exported = json.loads(json.dumps(result, allow_nan=False))
    assert exported["gewinn_usd"] == profit
    assert exported["profitabilitaet"] == status
    assert exported["data_complete"] is complete
    assert not exported["eligible"]
    assert exported["equity_dd_pct"] is None and exported["retdd_jahr"] is None
    assert exported.get("rang") is None
    assert exported["kapitalbasis_usd"] is None


@pytest.mark.parametrize("months", [0, 3, 6, 12])
def test_rendite_allein_mit_zeitraum_ist_darstellbar_aber_kein_positiver_gewinnbeleg(robo_env, months):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"YieldWindowPct": 120, "YieldWindowMonths": months}
    result = berechne(entry)
    assert result["data_complete"]
    assert result["rendite_quelle_pct"] == 120
    assert result["rendite_quelle_monate"] == months
    assert result["gewinn_usd"] is None and result["profitabilitaet"] == "unbekannt"
    assert result["retdd_jahr"] is None and result["equity_dd_pct"] is None


@pytest.mark.parametrize("bad", [None, -1, True, "6", float("nan"), float("inf")])
def test_rendite_ohne_gueltigen_nichtnegativen_zeitraum_ist_nicht_vollstaendig(robo_env, bad):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"YieldWindowPct": 120, "YieldWindowMonths": bad}
    result = berechne(entry)
    assert not result["data_complete"]
    assert result["profitabilitaet"] == "unbekannt"


@pytest.mark.parametrize("bad", [None, True, "120", float("nan"), float("inf")])
def test_ungueltige_rendite_zaehlt_nicht_als_vollstaendiges_rating(robo_env, bad):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"YieldWindowPct": bad, "YieldWindowMonths": 6}
    result = berechne(entry)
    assert not result["data_complete"]
    assert result["rendite_quelle_pct"] is None
    assert result["profitabilitaet"] == "unbekannt"


@pytest.mark.parametrize("profit,status", [(-10, "negativ"), (0, "unveraendert"), (42, "positiv")])
def test_gewinn_allein_ist_trotz_fehlender_rendite_darstellbar(robo_env, profit, status):
    entry, client, _ = robo_env
    client.answer["metrics"] = {"ProfitUsd": profit}
    result = berechne(entry)
    assert result["data_complete"] and result["profitabilitaet"] == status
    assert result["gewinn_usd"] == profit
    assert result["rendite_quelle_pct"] is None and result["rendite_quelle_monate"] is None


@pytest.mark.parametrize("balance", [None, True, "1200", float("nan"), float("inf")])
def test_ungueltige_ratingbalance_wird_nicht_als_trade_kapitalbasis_verwendet(robo_env, balance):
    entry, client, _ = robo_env
    client.answer["metrics"]["RatingBalanceUsd"] = balance
    result = berechne(entry)
    assert result["data_complete"] and result["rating_balance_usd"] is None
    assert result["kapitalbasis_usd"] is None


@pytest.mark.parametrize("dd", [None, 0, -1, 20, float("nan"), float("inf")])
def test_plattform_dd_erzeugt_keinen_gemessenen_floating_jahres_retdd(robo_env, dd):
    entry, client, _ = robo_env
    client.answer["metrics"]["EquityDrawdown"] = dd
    client.answer["metrics"]["TradeEqDrawdownPct"] = 5
    result = berechne(entry)
    assert result["data_complete"]
    assert result["retdd_jahr"] is None and result["equity_dd_pct"] is None
    assert not result["eligible"]


@pytest.mark.parametrize("patch", [{"signalId": "812"}, {"providerId": "812"}, {"id": 812}, {"version": "mql4"}])
def test_fremde_metrics_identitaet_oder_version_bleibt_datenfehler(robo_env, patch):
    entry, client, _ = robo_env
    client.answer.update(patch)
    result = berechne(entry)
    assert not result["data_complete"] and not result["eligible"]
    assert client.calls == [(811, "mql5")]


@pytest.mark.parametrize("answer", [[], None, {"signalId": "811", "version": "mql5", "metrics": []}])
def test_ungueltiges_metrics_schema_ist_kein_erfolgreiches_rating(robo_env, answer):
    entry, client, _ = robo_env
    client.answer = answer
    result = berechne(entry)
    assert not result["data_complete"] and not result["eligible"]


def test_verbindungsfehler_verwendet_keinen_zuvor_gespeicherten_ratingcache(robo_env):
    entry, client, options = robo_env
    assert berechne(entry)["data_complete"]
    client.failure = DownloaderConnectionError("Synthetic source offline")
    result = berechne(entry)
    assert not result["data_complete"]
    assert "offline" in result["grund"].lower()
    assert len(client.calls) == 2
    assert all(option["allow_offline_cache"] is False for option in options)


def test_falscher_quellenbesitzer_wird_vor_metrics_get_abgewiesen(robo_env):
    entry, client, _ = robo_env
    entry["quellen_uid"] = "different-owner"
    result = berechne(entry)
    assert not result["data_complete"]
    assert not client.calls


def test_stop_vor_quellenzugriff_erzeugt_keinen_erfolgsbeleg(robo_env):
    entry, client, _ = robo_env
    result = berechne(entry, should_stop=lambda: True)
    assert result["abgebrochen"] and not result["data_complete"]
    assert not client.calls


def test_stop_nach_metrics_get_veroeffentlicht_keinen_fertigen_ratingbeleg(robo_env):
    entry, client, _ = robo_env
    result = berechne(entry, should_stop=lambda: bool(client.calls))
    assert result["abgebrochen"] and not result["data_complete"]
    assert client.calls == [(811, "mql5")]


def test_unbekannte_robo_version_wird_vor_metrics_get_abgewiesen(robo_env):
    entry, client, _ = robo_env
    entry["quelle_version"] = "unknown-platform"
    result = berechne(entry)
    assert not result["data_complete"]
    assert not client.calls
