"""Neue Vertragsbelege ergaenzen Teilstudien ohne fremde Brokerfreigabe."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import config, db, pipeline, studien_batch
from mqlkiscanner.forensics import equity_rekonstruktion


ROOT = Path(__file__).resolve().parents[1]


def _res(**kwargs):
    return SimpleNamespace(id=91, name="Teil", trades_path="cached.csv",
                           trades_sha256="sha", quelle="mql5",
                           max_drawdown_equity_pct=8, **kwargs)


def _studie(**kwargs):
    report = {"verlaesslich": True, "equity_dd_pct": 8,
              "teilmessung": True, "symbole_ohne_kontrakt": ["UK100"]}
    report.update(kwargs)
    return {"trades_sha": "sha", "basislos": False, "report": report}


@pytest.mark.parametrize("broker,symbol,erwartet", [
    ("Vantage", "UK100", True), ("Vantage", "LTCUSD", True),
    ("Zulu", "LTCUSD", False), ("Tickmill", "UK100", False),
    ("Vantage", "UNBEKANNT", False),
])
def test_teilmessung_nur_mit_originalbroker_neu_versuchen(
        monkeypatch, broker, symbol, erwartet):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE", ROOT / "data/contract_specs.json")
    res = _res(broker_server=None)
    studie = _studie(original_broker=broker, symbole_ohne_kontrakt=[symbol],
                     kursdaten_terminal="Vantage/terminal64.exe")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats",
                        lambda _: pytest.fail("Originalbroker ist bereits bekannt"))
    jobs, fertig = studien_batch.luecken_sammeln(
        [res], {res.id: studie}, trades_nachladen=False)
    assert jobs == ([res] if erwartet else [])
    assert fertig == (0 if erwartet else 1)


@pytest.mark.parametrize("resbroker,metricsbroker", [("Vantage", None), (None, "Vantage")])
def test_altstudie_originalbroker_fallback(monkeypatch, resbroker, metricsbroker):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE", ROOT / "data/contract_specs.json")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats",
                        lambda _: {"broker_server": metricsbroker})
    res = _res(broker_server=resbroker)
    jobs, fertig = studien_batch.luecken_sammeln(
        [res], {91: _studie()}, trades_nachladen=False)
    assert jobs == [res] and fertig == 0


def test_referenzterminal_ersetzt_keinen_unbekannten_originalbroker(monkeypatch):
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats", lambda _: {})
    res = _res(broker_server=None)
    jobs, fertig = studien_batch.luecken_sammeln(
        [res], {91: _studie(kursdaten_terminal="Vantage")}, trades_nachladen=False)
    assert jobs == [] and fertig == 1


def test_ohne_ausgeschlossene_specs_keine_metrics_abfrage(monkeypatch):
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats", lambda _: pytest.fail("N+1"))
    res = _res(broker_server=None)
    assert studien_batch.luecken_sammeln(
        [res], {91: _studie(symbole_ohne_kontrakt=[])}, trades_nachladen=False) == ([], 1)


def test_einer_von_mehreren_kontrakten_genuegt_fuer_nachmessung(monkeypatch):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE", ROOT / "data/contract_specs.json")
    res = _res(broker_server="Vantage")
    jobs, _ = studien_batch.luecken_sammeln(
        [res], {91: _studie(symbole_ohne_kontrakt=["UNBEKANNT", "EU50"])},
        trades_nachladen=False)
    assert jobs == [res]


def test_neuer_bericht_bewahrt_originalbroker_unabhaengig_vom_feed(monkeypatch):
    monkeypatch.setattr(equity_rekonstruktion, "rekonstruiere",
                        lambda *args, **kwargs: {"verlaesslich": True, "equity_dd_pct": 5})
    report = studien_batch._rekonstruiere_mit_feed_fallback(
        SimpleNamespace(trades=[]), SimpleNamespace(terminal_pfad="Vantage"), 1000, "Zulu")
    assert report["original_broker"] == "Zulu"
    assert report["kursdaten_terminal"] == "Vantage"


def test_nachmessung_verwendet_gespeicherten_originalbroker_ohne_andere_metadaten(
        tmp_path, monkeypatch):
    path = tmp_path / "trades.csv"
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                    "2026.01.05 10:00:00;Buy;1;EURUSD;1.1;1;2026.01.05 12:00:00;1.2;0;0;100\n")
    res = pipeline.ScanResult(id=91, trades_path=str(path), trades_sha256="sha")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats",
                        lambda _: {"initial_deposit_usd": 1000})
    monkeypatch.setattr(db, "get_equity_studie", lambda _: _studie(original_broker="Vantage"))
    brokers = []
    def messen(parsed, anbieter, kapital, broker):
        brokers.append(broker)
        return {"verlaesslich": True, "equity_dd_pct": 9}
    monkeypatch.setattr(studien_batch, "_rekonstruiere_mit_feed_fallback", messen)
    monkeypatch.setattr(db, "store_equity_studie", lambda *a, **kw: None)
    assert studien_batch._rechne_ein_signal(res, {}, None, False)
    assert brokers == ["Vantage"]


@pytest.mark.parametrize("altsha,neu_verlaesslich,speichern", [
    ("sha", False, False), ("alt", False, True), ("sha", True, True),
])
def test_schlechter_nachversuch_verliert_keine_gueltige_teilmessung(
        tmp_path, monkeypatch, altsha, neu_verlaesslich, speichern):
    path = tmp_path / "trades.csv"
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                    "2026.01.05 10:00:00;Buy;1;EURUSD;1.1;1;2026.01.05 12:00:00;1.2;0;0;100\n")
    res = pipeline.ScanResult(id=91, name="Teil", trades_path=str(path), trades_sha256="sha")
    monkeypatch.setattr(studien_batch.katalog, "metrics_stats",
                        lambda _: {"initial_deposit_usd": 1000, "broker_server": "Vantage"})
    monkeypatch.setattr(studien_batch, "_rekonstruiere_mit_feed_fallback",
                        lambda *args: {"verlaesslich": neu_verlaesslich,
                                       "equity_dd_pct": 9, "grund": "Kurse fehlen"})
    vorher = _studie()
    vorher["trades_sha"] = altsha
    monkeypatch.setattr(db, "get_equity_studie", lambda _: vorher)
    gespeichert = []
    monkeypatch.setattr(db, "store_equity_studie", lambda *a, **kw: gespeichert.append(a))
    control = {"skipped_gruende": []}
    assert studien_batch._rechne_ein_signal(res, control, None, False) is speichern
    assert bool(gespeichert) is speichern
    if not speichern:
        assert "bleibt erhalten" in control["skipped_gruende"][0]
