"""Robo-Ratingwerte als Zusatzbeleg — Werterfassung bleibt streng geprüft.

Nutzer-Freigabe 29.10.2026: Robo läuft im Datenpfad durch Refresh/Metrics/
Trades wie jede Quelle (Integrationstest in test_abonnenten_analyse_daten).
``robo_quellenwerte`` bleibt der Werterfassung-Kern für alte gesperrte Aufgaben
(Resume) und die Zusatzbeleg-Felder; diese Datei prüft ihn direkt.
"""
from __future__ import annotations

import json

import pytest

from mqlkiscanner import abonnenten_analyse_daten as daten


def werte(metrics, *, sid=811, version="mql5", signal_id=None):
    roh = {"signalId": signal_id if signal_id is not None else str(sid),
           "version": version, "metrics": metrics}
    return daten.robo_quellenwerte(roh, sid, version)


def test_ratingwerte_werden_vollstaendig_und_ehrlich_gemappt():
    result = werte({"ProfitUsd": 125.5, "YieldWindowPct": 12.0,
                    "YieldWindowMonths": 6, "RatingBalanceUsd": 1125.5,
                    "RatingCurrency": "USD"})
    assert result["auswertung_typ"] == "quellenprofitabilitaet"
    assert result["data_complete"] and not result["eligible"]
    assert result["gewinn_usd"] == 125.5
    assert result["rendite_quelle_pct"] == 12.0
    assert result["rendite_quelle_monate"] == 6
    assert result["rating_balance_usd"] == 1125.5
    assert result["profitabilitaet"] == "positiv"
    assert result["trades"] is None
    assert result["retdd_jahr"] is None and result["equity_dd_pct"] is None
    assert result["finanzdaten_stand"] is None
    assert "unbekannt" in result["messhinweis"].lower()
    json.loads(json.dumps(result, allow_nan=False))


@pytest.mark.parametrize("version", ["mql4", "mql5", "rst"])
def test_werterfassung_gilt_fuer_alle_quellenplattformen(version):
    result = werte({"ProfitUsd": 5.0}, version=version)
    assert result["gewinn_usd"] == 5.0


@pytest.mark.parametrize("profit,status", [(123, "positiv"), (-5.25, "negativ"), (0, "unveraendert")])
def test_profitstatus_folgt_ausschliesslich_usd_gewinnvorzeichen(profit, status):
    result = werte({"ProfitUsd": profit, "YieldWindowPct": -80, "YieldWindowMonths": 3})
    assert result["data_complete"]
    assert result["gewinn_usd"] == profit
    assert result["profitabilitaet"] == status
    assert result["rendite_quelle_pct"] == -80


@pytest.mark.parametrize("bad", [None, True, "125.5", float("nan"), float("inf"), float("-inf"), {}, []])
def test_unbelegter_gewinn_wird_nicht_als_gueltige_zahl_oder_null_ausgegeben(bad):
    result = werte({"ProfitUsd": bad})
    assert result["gewinn_usd"] is None
    assert result["profitabilitaet"] == "unbekannt"
    assert not result["data_complete"]


@pytest.mark.parametrize("metrics,profit,status,complete", [
    ({}, None, "unbekannt", False),
    ({"ProfitUsd": None}, None, "unbekannt", False),
    ({"ProfitUsd": 0}, 0, "unveraendert", True),
])
def test_native_null_und_echte_null_bleiben_unterschieden(metrics, profit, status, complete):
    result = werte(metrics)
    exported = json.loads(json.dumps(result, allow_nan=False))
    assert exported["gewinn_usd"] == profit
    assert exported["profitabilitaet"] == status
    assert exported["data_complete"] is complete
    assert not exported["eligible"]
    assert exported["equity_dd_pct"] is None and exported["retdd_jahr"] is None


@pytest.mark.parametrize("months", [0, 3, 6, 12])
def test_rendite_allein_mit_zeitraum_ist_darstellbar_aber_kein_gewinnbeleg(months):
    result = werte({"YieldWindowPct": 120, "YieldWindowMonths": months})
    assert result["data_complete"]
    assert result["rendite_quelle_pct"] == 120
    assert result["rendite_quelle_monate"] == months
    assert result["gewinn_usd"] is None and result["profitabilitaet"] == "unbekannt"


@pytest.mark.parametrize("bad", [None, -1, True, "6", float("nan"), float("inf")])
def test_rendite_ohne_gueltigen_nichtnegativen_zeitraum_ist_nicht_vollstaendig(bad):
    result = werte({"YieldWindowPct": 120, "YieldWindowMonths": bad})
    assert not result["data_complete"]
    assert result["profitabilitaet"] == "unbekannt"


@pytest.mark.parametrize("bad", [None, True, "120", float("nan"), float("inf")])
def test_ungueltige_rendite_zaehlt_nicht_als_vollstaendiges_rating(bad):
    result = werte({"YieldWindowPct": bad, "YieldWindowMonths": 6})
    assert not result["data_complete"]
    assert result["rendite_quelle_pct"] is None
    assert result["profitabilitaet"] == "unbekannt"


@pytest.mark.parametrize("profit,status", [(-10, "negativ"), (0, "unveraendert"), (42, "positiv")])
def test_gewinn_allein_ist_trotz_fehlender_rendite_darstellbar(profit, status):
    result = werte({"ProfitUsd": profit})
    assert result["data_complete"] and result["profitabilitaet"] == status
    assert result["gewinn_usd"] == profit
    assert result["rendite_quelle_pct"] is None and result["rendite_quelle_monate"] is None


@pytest.mark.parametrize("balance", [None, True, "1200", float("nan"), float("inf")])
def test_ungueltige_ratingbalance_wird_nicht_als_kapitalbasis_verwendet(balance):
    result = werte({"ProfitUsd": 10, "RatingBalanceUsd": balance})
    assert result["data_complete"] and result["rating_balance_usd"] is None


@pytest.mark.parametrize("dd", [None, 0, -1, 20, float("nan"), float("inf")])
def test_plattform_dd_erzeugt_keinen_gemessenen_floating_retdd(dd):
    result = werte({"ProfitUsd": 10, "EquityDrawdown": dd, "TradeEqDrawdownPct": 5})
    assert result["data_complete"]
    assert result["retdd_jahr"] is None and result["equity_dd_pct"] is None
    assert not result["eligible"]


@pytest.mark.parametrize("signal_id", ["812", 812])
def test_fremde_metrics_identitaet_ist_ein_lauter_fehler(signal_id):
    with pytest.raises(ValueError):
        werte({"ProfitUsd": 10}, signal_id=signal_id)


@pytest.mark.parametrize("antwort", [[], None, {"signalId": "811", "version": "mql5", "metrics": []}])
def test_ungueltiges_metrics_schema_ist_kein_erfolgreiches_rating(antwort):
    with pytest.raises((ValueError, TypeError)):
        daten.robo_quellenwerte(antwort, 811, "mql5")
