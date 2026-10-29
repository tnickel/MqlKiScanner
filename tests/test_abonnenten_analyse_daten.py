"""Rechercheprofil: echte Belege, Floating-Nenner und isolierte 2-Monatsregel."""
from __future__ import annotations

import copy
import datetime as dt
import json

import pytest

from mqlkiscanner import abonnenten_analyse_daten as daten
from mqlkiscanner import config, db, portfolio_statistik
from mqlkiscanner.downloader_client import DownloaderUpdateNotSupported


HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def csv_bytes(*, trades=50, days=65, deposits=False, flow=False):
    first = dt.datetime(2026, 1, 5, 10)
    lines = []
    if deposits:
        lines.append("2026.01.01 00:00:00;Balance;;;;;;;;;1000")
    for index in range(trades):
        opened = first + dt.timedelta(days=(days - 1) * index / max(1, trades - 1))
        closed = opened + dt.timedelta(hours=2)
        lines.append(f"{opened:%Y.%m.%d %H:%M:%S};Buy;0.01;XAUUSD;2000;0.01;"
                     f"{closed:%Y.%m.%d %H:%M:%S};2010;0;0;10")
        if flow and index == 20:
            at_flow = opened + dt.timedelta(hours=1)
            lines.append(f"{at_flow:%Y.%m.%d %H:%M:%S};Balance;;;;;;;;;100")
    return (HEADER + "\n".join(lines) + "\n").encode()


@pytest.fixture
def service_env(monkeypatch):
    qid = db.add_quelle("mql5", "Synthetic source", "http://synthetic-source:8199")
    quelle = db.get_quelle(qid)
    entry = dict(quelle="mql5", id=811, quelle_id=qid, quelle_version="mql5",
                 quellen_uid=quelle["quellen_uid"], signal_ref=None, platform="mt5",
                 name="Synthetic 2-month strategy", abonnenten=10)

    class Client:
        raw = csv_bytes()
        answer = {"version": "mql5", "metrics": {
            "Currency": "USD", "InitialDeposit": 1000, "Balance": 1500,
            "TradesTruncated": False, "TradesHistoryComplete": True,
            "TradeHistoryComplete": True}}

        def __init__(self):
            self.calls = []
            self.receipt = dict(providerId="811", version="mql5", jobId="our-job",
                                platformRefreshed=True, fullHistory=True,
                                refreshedAt="2026-10-23T15:00:00")

        def refresh_provider(self, sid, version, **kwargs):
            self.calls.append(("refresh", sid, version))
            assert callable(kwargs["should_stop"])
            return self.receipt

        def metrics(self, sid, version):
            self.calls.append(("metrics", sid, version))
            return copy.deepcopy(self.answer)

        def trades_csv(self, sid, version):
            self.calls.append(("trades", sid, version))
            return self.raw

    class Kurse:
        terminal_idx = 0
        starts = 0
        closes = 0

        def __init__(self, settings):
            self.settings = settings

        def starten(self):
            self.starts += 1
            return True, "synthetic connection"

        def beenden(self):
            self.closes += 1

    client = Client()
    monkeypatch.setattr(daten.quellen, "client_fuer_quelle", lambda _q: client)
    created = []

    def create(settings):
        provider = Kurse(settings)
        created.append(provider)
        return provider

    monkeypatch.setattr(daten.kursdaten, "KursDaten", create)
    # Real parser, real engine, real capital/return calculations; only the
    # external FX/spec and H1 feed boundary is replaced with explicit facts.
    exp = {key: True for key in ("contract_complete", "conversion_complete",
                                "capital_history_complete", "temporal_risk_available")}
    exp.update(flag=True, shock_pct_max=90.0)
    monkeypatch.setattr(daten.exposure, "run", lambda *a, **k: copy.deepcopy(exp))
    equity = dict(status="ok", verlaesslich=True, equity_dd_pct_raw=60.00001,
                  equity_dd_pct=60.0, equity_dd_pct_am_usd_max=2.0, trades_total=50,
                  trades_mit_kurs_und_kontrakt=50, abdeckung_pct_raw=100.0)
    monkeypatch.setattr(daten, "_rekonstruiere_mit_feed_fallback",
                        lambda *a, **k: copy.deepcopy(equity))

    def forbidden(*args, **kwargs):
        raise AssertionError("Recherche darf keine Hauptworkflow-Bewertung speichern")

    monkeypatch.setattr(db, "store_forensik", forbidden)
    monkeypatch.setattr(db, "store_equity_studie", forbidden)
    return entry, client, created, equity, exp


@pytest.mark.parametrize("monate,trades,ok", [
    (2.0, 50, True), (2.000001, 50, True), (1.999999, 49, True),
    (daten.MIN_MONATE, 25, True), (daten.MIN_MONATE, 24, False),
    (0.5, 50, False), (None, 50, False), (2.1, 24.5, False),
    (2.1, 50.5, False), (float("nan"), 50, False),
    (2.1, True, False), (2.1, float("inf"), False),
])
def test_mindestmaterial(monate, trades, ok):
    assert daten.pruefe_mindestmaterial(monate, trades)[0] is ok


def test_kriterien_keine_alten_3_monate_dd50_calmar3_oder_score_sperren():
    facts = dict(dauer_monate=2.01, trades=50, retdd_jahr=0.1,
                 equity_dd_pct=80, hard_excluded=False, score=9)
    assert daten.pruefe_kriterien(facts)[0]
    for bad in (None, 0, -1, float("nan"), float("inf")):
        assert not daten.pruefe_kriterien(dict(facts, retdd_jahr=bad))[0]
    assert not daten.pruefe_kriterien(dict(facts, hard_excluded=True))[0]


def test_effizienz_default_4_wochen_explizites_profil_bleibt_getrennt(tmp_path):
    # Nutzer 29.10.2026: Default-Mindesthistorie 4 Wochen; ein explizit
    # strengeres Profil (3 Monate) bleibt davon unberührt und umgekehrt.
    path = tmp_path / "two-months.csv"
    path.write_bytes(csv_bytes())
    normal = portfolio_statistik.effizienz_kennzahlen(str(path), 1000, 60)
    research = portfolio_statistik.effizienz_kennzahlen(str(path), 1000, 60,
                                                       min_historie_monate=3)
    assert normal["min_historie_monate"] == pytest.approx(
        portfolio_statistik.MIN_HISTORIE_MONATE)
    assert normal["effizienz_status"] == "ok"
    assert research["min_historie_monate"] == 3
    assert research["effizienz_status"] == "historie_zu_kurz"
    assert research["retdd_jahr"] is None
    assert research["dauer_monate"] < 3
    # A subsequent normal call cannot inherit the separate policy.
    assert portfolio_statistik.effizienz_kennzahlen(str(path), 1000, 60)["retdd_jahr"] is not None


@pytest.mark.parametrize("minimum", [0, -1, None, True, float("nan"), float("inf")])
def test_effizienz_invalides_profil_ist_laut(minimum):
    with pytest.raises(ValueError):
        portfolio_statistik.effizienz_kennzahlen(None, None, None,
                                                 min_historie_monate=minimum)


def test_service_vollbatterie_hoher_dd_und_h1_nenner(service_env):
    entry, client, providers, equity, exp = service_env
    with daten.AnalyseDaten({"schranke_eq_dd_pct": 1, "min_calmar_jahr": 999}) as service:
        assert providers == []  # No terminal on context creation.
        result = service.berechne(entry)
        assert result["eligible"], result["grund"]
        assert result["data_complete"]
        assert result["trades"] == 50
        assert 2 <= result["dauer_monate"] < 3
        assert result["equity_dd_pct"] == 60.00001
        assert result["retdd_jahr"] == pytest.approx(result["cagr_jahr_pct"] / 60.00001)
        assert result["retdd_zeitraum"] == pytest.approx(50 / 60.00001)
        assert result["kapitalbasis_usd"] == 1000
        assert result["account_currency"] == "USD"
        assert set(result["forensik"]["forensics"]) >= {
            "martingale", "exposure", "stops", "drawdown", "baskets", "news",
            "equity_rekonstruktion", "effizienz_recherche"}
        assert client.calls[0] == ("refresh", 811, "mql5")
        assert [call[0] for call in client.calls] == ["refresh", "metrics", "trades"]
        assert providers[0].closes == 0
        assert db.file_sha256(result["trades_path"]) == result["trades_sha256"]
        json.dumps(result, allow_nan=False)
    assert providers[0].closes == 1
    assert "offene Positionen nicht erfasst" in result["messhinweis"]


def test_batch_haelt_terminal_bis_kontextende_offen(service_env):
    entry, client, providers, _, _ = service_env
    with daten.AnalyseDaten({}) as service:
        assert service.berechne(entry)["eligible"]
        assert service.berechne(entry)["eligible"]
        assert len(providers) == 1
        assert providers[0].closes == 0
    assert providers[0].closes == 1


@pytest.mark.parametrize("patch", [
    {"platformRefreshed": False}, {"fullHistory": False}, {"providerId": "999"},
    {"version": "mql4"}, {"jobId": ""}, {"refreshedAt": ""},
])
def test_refresh_muss_eigenen_aktuellen_vollabruf_belegen(service_env, patch):
    entry, client, providers, _, _ = service_env
    client.receipt.update(patch)
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert not result["data_complete"]
    assert "vollständigen Abrufs" in result["grund"]
    assert len(client.calls) == 1
    assert not providers


def test_alter_client_kein_offline_oder_globalupdate_fallback(service_env):
    entry, client, providers, _, _ = service_env

    def unsupported(*args, **kwargs):
        raise DownloaderUpdateNotSupported("Gezielter Abruf nicht unterstützt")

    client.refresh_provider = unsupported
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert not result["data_complete"]
    assert "nicht unterstützt" in result["grund"]
    assert not client.calls and not providers


@pytest.mark.parametrize("currency", [None, "", "EUR", "USC"])
def test_keine_kurse_ohne_belegte_usd_waehrung(service_env, currency):
    entry, client, providers, _, _ = service_env
    client.answer["metrics"]["Currency"] = currency
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert "USD-Kontowährung" in result["grund"]
    assert [call[0] for call in client.calls] == ["refresh", "metrics"]
    assert not providers


def test_virtuelle_basis_wird_separat_als_modell_berechnet(service_env, monkeypatch):
    from mqlkiscanner import abonnenten_modellrechnung
    monkeypatch.setattr(abonnenten_modellrechnung, "berechne_modell",
                        lambda entry, capital, **kw: {"startkapital_usd": capital["kapital"],
                            "trade_sha256": entry["trades_sha256"], "status": "berechnet",
                            "equity_dd_pct": 8, "retdd_jahr": 2, "grund": "Synthetisches H1-Modell"})
    entry, client, providers, _, _ = service_env
    client.answer["metrics"].pop("InitialDeposit")
    client.answer["metrics"]["InitialDepositVirtual"] = 10_000
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert result["kapitalbasis_usd"] is None
    assert result["modell"]["startkapital_usd"] == 10000
    assert result["modell"]["equity_dd_pct"] == 8
    assert result["equity_dd_pct"] is result["retdd_jahr"] is None
    assert result["kapitalbasis_details"]["quelle"] == "modell_fallback_10000"
    assert providers[0].starts == providers[0].closes == 1


@pytest.mark.parametrize("reason", ["martingale", "ausschlussliste"])
def test_belegter_ausschluss_bleibt_bei_fehlendem_kapital_erhalten(service_env, monkeypatch, reason):
    entry, client, providers, _, _ = service_env
    client.answer["metrics"].pop("InitialDeposit")
    original = daten.engine.analyze

    def analyze(*args, **kwargs):
        report = original(*args, **kwargs)
        report["forensics"]["martingale"]["flag"] = reason == "martingale"
        return report

    monkeypatch.setattr(daten.engine, "analyze", analyze)
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": [
        {"quelle": "mql5", "id": 811, "grund": "Belegter Ausschluss"}
    ] if reason == "ausschlussliste" else []})
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"] and not result["data_complete"]
    assert result["hard_excluded"] is True
    assert "Martingale" in result["ausschlussgrund"] if reason == "martingale" else "Belegter Ausschluss" in result["ausschlussgrund"]
    assert result["modell"]["startkapital_usd"] == 10000
    assert result["kapitalbasis_modell"] is True
    assert result["equity_dd_pct"] is None and result["retdd_jahr"] is None
    assert not providers


def test_echte_csv_einzahlung_hat_ohne_websitebasis_beleg(service_env):
    entry, client, providers, _, _ = service_env
    client.answer["metrics"].pop("InitialDeposit")
    client.raw = csv_bytes(deposits=True)
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert result["eligible"], result["grund"]
    assert result["kapitalbasis_usd"] == 1000
    assert result["forensik"]["forensics"]["drawdown"]["startkapital_quelle"] == "csv_einzahlungen"


def test_initialdeposit_ohne_balanceabgleich_ist_kein_beleg(service_env):
    entry, client, providers, _, _ = service_env
    client.answer["metrics"]["Balance"] = 10_000
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert "Kapitalbasis unbestätigt" in result["grund"]
    assert not providers


@pytest.mark.parametrize("field", ["TradesTruncated", "TradesHistoryComplete", "TradeHistoryComplete"])
def test_unvollstaendige_historie_ist_gesperrt(service_env, field):
    entry, client, providers, _, _ = service_env
    client.answer["metrics"][field] = field == "TradesTruncated"
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert "unvollständige oder gekappte" in result["grund"]
    assert not providers


@pytest.mark.parametrize("patch", [
    {"status": "ok_teilmessung", "teilmessung": True},
    {"verlaesslich": False}, {"trades_mit_kurs_und_kontrakt": 49},
    {"fx_luecke": True}, {"equity_dd_pct_raw": float("nan")},
    {"equity_dd_pct_raw": 0}, {"symbole_nicht_betrachtet": ["UNKNOWN"]},
])
def test_keine_teilmessung_kein_closingdd_ersatz(service_env, patch):
    entry, client, providers, equity, _ = service_env
    equity.update(patch)
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert result["equity_dd_pct"] is None
    assert result["retdd_jahr"] is None
    json.dumps(result, allow_nan=False)
    assert providers[0].closes == 1


def test_kapitalfluss_bei_offenem_trade_keine_balance_twr(service_env):
    entry, client, providers, _, _ = service_env
    client.raw = csv_bytes(flow=True)
    client.answer["metrics"]["Balance"] = 1600
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert "kapitalfluss_equity_unbelegt" in result["grund"]
    assert result["retdd_jahr"] is None


def test_bestatigte_martingale_signatur_bleibt_harter_ausschluss(service_env, monkeypatch):
    entry, client, providers, _, _ = service_env
    monkeypatch.setattr(daten.engine.martingale, "run", lambda parsed: {"flag": True})
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"] and result["hard_excluded"]
    assert result["retdd_jahr"] > 0
    assert "Martingale" in result["grund"]


def test_explizite_quellengebundene_ausschlussliste(service_env, monkeypatch):
    entry, client, providers, _, _ = service_env
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"quelle": "mql5", "id": 811, "grund": "Belegter Ausschluss"}]})
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert result["hard_excluded"] and not result["eligible"]
    assert "Belegter Ausschluss" in result["grund"]


def test_stop_vor_erster_quellenaktion(service_env):
    entry, client, providers, _, _ = service_env
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry, should_stop=lambda: True)
    assert not result["eligible"] and result["abgebrochen"]
    assert not result["data_complete"]
    assert not providers and not client.calls


def test_falscher_eigentuemer_vor_quellenaktion_gesperrt(service_env):
    entry, client, providers, _, _ = service_env
    entry["quellen_uid"] = "another-owner"
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert "Quellenidentität" in result["grund"]
    assert not providers and not client.calls


def test_robo_nimmt_standardpfad_mit_rating_zusatzbeleg(service_env):
    # Nutzer-Freigabe 29.10.2026: Robo läuft durch Refresh/Metrics/Trades wie
    # jede Quelle; die Ratingwerte bleiben als Zusatzbeleg erhalten.
    entry, client, providers, _, _ = service_env
    qid = db.add_quelle("robo", "Released robo", "http://synthetic-robo:8198")
    entry.update(quelle="robo", quelle_id=qid, quellen_uid=db.get_quelle(qid)["quellen_uid"])
    client.answer["metrics"].update(
        {"RatingCurrency": "USD", "ProfitUsd": 123.4, "YieldWindowPct": 5.0})
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert ("refresh", 811, "mql5") in client.calls
    assert ("trades", 811, "mql5") in client.calls
    assert result["quellen_profitabilitaet"]["ProfitUsd"] == 123.4
    assert result["account_currency"] == "USD"
    assert result["data_complete"] is True


def test_unzureichendes_mindestmaterial_startet_kein_terminal(service_env):
    # 4-Wochen-Regel (29.10.2026): unter 28 Tagen kein Terminalstart.
    entry, client, providers, _, _ = service_env
    client.raw = csv_bytes(days=20)
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"]
    assert result["data_complete"]
    assert "unter 4 Wochen" in result["grund"]
    assert result["forensik"]["forensics"]["martingale"]
    assert not providers


@pytest.mark.parametrize("patch", [{"version": "mql4"}, {"providerId": "another-provider"}])
def test_metrics_fremde_identitaet_vor_tradeabruf_gesperrt(service_env, patch):
    entry, client, providers, _, _ = service_env
    client.answer.update(patch)
    with daten.AnalyseDaten({}) as service:
        result = service.berechne(entry)
    assert not result["eligible"] and not result["data_complete"]
    assert "anderen" in result["grund"]
    assert [call[0] for call in client.calls] == ["refresh", "metrics"]
    assert not providers
