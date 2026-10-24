"""Offline scenarios never overwrite account evidence or manufacture coverage."""
from copy import deepcopy
import datetime as dt
import hashlib
import json
import sqlite3

import pytest

from mqlkiscanner import abonnenten_modellrechnung as model
from mqlkiscanner import config, fx_rates, parser
from mqlkiscanner.forensics import equity_rekonstruktion as er


CAPITAL = {"kapital": 1000, "waehrung": "USD", "methode": "fallback_10000",
           "basis_typ": "modell", "annahmen": ["Synthetische Testbasis"]}
HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def snapshot(tmp_path, rows=None, **entry_fields):
    rows = rows or ["2026.01.05 01:00:00;Buy;1;XAUUSD;2006.9;1;2026.01.06 22:00:00;2154;0;0;100"]
    path = tmp_path/"trades.csv"
    path.write_text(HEADER+"\n".join(rows)+"\n", encoding="utf-8")
    return {"quelle": "mql5", "id": 1, "quellen_uid": "test", "signal_ref": 12,
            "trades_path": str(path), "trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "trade_money_currency": "USD", "account_currency": "USD",
            "trade_history_complete": True, **entry_fields}


@pytest.fixture(autouse=True)
def offline_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "FX_RATES_DIR", tmp_path/"fx")
    monkeypatch.setattr(config, "load_settings", lambda: {})
    monkeypatch.setattr(fx_rates.requests, "get", lambda *a, **k: pytest.fail("No network"))
    model._offline_cache.cache_clear()
    model._offline_fx.cache_clear()


def fake_kernel(monkeypatch, points=None, **patch):
    seen = []
    def reconstruct(parsed, provider, capital, **kwargs):
        seen.append((deepcopy(parsed), capital, kwargs))
        report = {"status": "ok", "verlaesslich": True,
                  "trades_mit_kurs_und_kontrakt": len(parsed.trades),
                  "abdeckung_pct_raw": 100, "equity_dd_pct_raw": 10,
                  "equity_dd_usd": 100,
                  "_curve": points or [(100, capital, True, 0),
                                        (200, capital-100, True, 0),
                                        (300, capital+parsed.net_total, True, 0)], **patch}
        return report
    monkeypatch.setattr(er, "rekonstruiere", reconstruct)
    return seen


def test_snapshot_and_real_forensics_remain_unchanged_while_flows_are_ignored(tmp_path, monkeypatch):
    entry = snapshot(tmp_path, [
        "2026.01.04 00:00:00;Balance;;;;;;;;;1000",
        "2026.01.05 01:00:00;Buy;1;XAUUSD;2006.9;1;2026.01.06 22:00:00;2154;0;0;100",
        "2026.01.05 02:00:00;Balance;;;;;;;;;5000"],
        equity_dd_pct=67, retdd_jahr=2, forensik={"original": True})
    before = deepcopy(entry)
    raw = (tmp_path/"trades.csv").read_bytes()
    seen = fake_kernel(monkeypatch)
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert result["status"] == "berechnet", result
    assert result["nettogewinn_usd"] == 100 and result["rendite_zeitraum_pct"] == 10
    assert result["equity_dd_pct"] == 10
    assert result["retdd_jahr"] == pytest.approx(result["cagr_jahr_pct"]/10)
    assert result["ignorierte_kapitalfluesse"]["anzahl"] == 2
    assert result["annahme_kapitalfluesse"] == "keine"
    assert seen[0][0].balances == [] and seen[0][1] == 1000
    assert seen[0][2]["include_curve"] is True
    assert seen[0][2]["compute_dd"] is False  # One DD pass with the model's own pre-cost anchor.
    assert entry == before and (tmp_path/"trades.csv").read_bytes() == raw
    assert len(parser.load_export(tmp_path/"trades.csv").balances) == 2
    assert "_curve" not in result["equity"]


def test_cost_before_first_trade_keeps_original_k0_drawdown_anchor(tmp_path, monkeypatch):
    entry = snapshot(tmp_path, [
        "2026.01.04 00:00:00;Commission;;;;;;;;;-200",
        "2026.01.05 01:00:00;Buy;1;XAUUSD;2006.9;1;2026.01.06 22:00:00;2154;0;0;100"])
    seen = fake_kernel(monkeypatch, points=[(100, 800, True, 0), (200, 600, True, 0),
                                           (300, 900, True, 0)])
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert seen[0][1] == 800  # only the kernel's first-trade anchor is adjusted
    assert len(seen[0][0].costs) == 1
    assert result["startkapital_usd"] == 1000 and result["nettogewinn_usd"] == -100
    assert result["rendite_zeitraum_pct"] == -10
    assert result["equity_dd_pct"] == 40 and result["equity_dd_usd"] == 400
    assert result["closing_dd_pct"] == 20
    assert result["equity"]["min_equity_usd"] == 600
    assert result["zeit_von"] == "2026-01-04T00:00:00"


def test_intermediate_insolvency_is_not_hidden_by_positive_final_equity(tmp_path, monkeypatch):
    entry = snapshot(tmp_path)
    fake_kernel(monkeypatch, points=[(100, 1000, True, 0), (200, -200, True, 0),
                                     (300, 1100, True, 0)])
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert result["equity_dd_pct"] == 120 and result["equity"]["min_equity_usd"] == -200
    assert result["equity"]["modell_insolvent"] is True
    assert result["status"] == "eingeschraenkt" and result["rendite_zeitraum_pct"] == 10
    assert result["retdd_jahr"] is None and "insolvent" in result["retdd_grund"]


@pytest.mark.parametrize("patch", [{"status": "ok_teilmessung", "teilmessung": True},
                                  {"fx_luecke": True}, {"verlaesslich": False},
                                  {"trades_mit_kurs_und_kontrakt": 0}])
def test_partial_h1_cannot_be_promoted_to_full_model_dd(tmp_path, monkeypatch, patch):
    entry = snapshot(tmp_path)
    fake_kernel(monkeypatch, **patch)
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert result["status"] == "datenluecke"
    assert result["equity_dd_pct"] is result["retdd_jahr"] is None
    assert result["closing_dd_pct"] == 0 and result["rendite_zeitraum_pct"] == 10


def test_missing_cache_retains_honest_partial_metrics_without_creating_a_db(tmp_path):
    result = model.berechne_modell(snapshot(tmp_path), CAPITAL)
    assert result["status"] == "datenluecke" and result["equity_dd_pct"] is None
    assert result["nettogewinn_usd"] == 100 and result["closing_dd_pct"] == 0
    assert not (tmp_path/"kursdaten.db").exists()


@pytest.mark.parametrize("capital", [{"kapital": 0, "waehrung": "USD"},
                                      {"kapital": float("nan"), "waehrung": "USD"},
                                      {"kapital": 1000}, {}])
def test_invalid_capital_never_becomes_zero_drawdown(tmp_path, capital):
    result = model.berechne_modell(snapshot(tmp_path), capital)
    assert result["status"] == "datenluecke"
    assert result["equity_dd_pct"] is result["closing_dd_pct"] is None
    assert "kapital_details" in result
    json.dumps(result, allow_nan=False)


def test_zero_model_dd_does_not_manufacture_retdd(tmp_path, monkeypatch):
    fake_kernel(monkeypatch, points=[(100, 1000, True, 0), (300, 1100, True, 0)])
    result = model.berechne_modell(snapshot(tmp_path), CAPITAL, kurse=object())
    assert result["equity_dd_pct"] == 0 and result["retdd_jahr"] is None
    assert result["status"] == "eingeschraenkt"


def test_short_window_annualization_overflow_keeps_period_gain_and_dd(tmp_path, monkeypatch):
    entry = snapshot(tmp_path, ["2026.01.05 01:00:00;Buy;1;XAUUSD;2000;1;2026.01.05 01:00:01;2001;0;0;100"])
    fake_kernel(monkeypatch)
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert result["rendite_zeitraum_pct"] == 10 and result["equity_dd_pct"] == 10
    assert result["cagr_jahr_pct"] is result["retdd_jahr"] is None
    assert result["status"] == "eingeschraenkt" and "Zahlenbereich" in result["annualisierung_hinweis"]
    json.dumps(result, allow_nan=False)


def test_proven_capital_is_labelled_without_promoting_model_curve_to_real(tmp_path):
    capital = {**CAPITAL, "basis_typ": "belegt", "methode": "native_initial_deposit_usd"}
    result = model.berechne_modell(snapshot(tmp_path), capital)
    assert result["kapital_methode"] == "Belegt: ursprüngliche Einzahlung der Quelle"
    assert "Kapitalbasis belegt" in result["kapital_hinweis"]
    assert "Modellszenario" in result["kapital_hinweis"]
    assert result["kapital_details"]["methode"] == "native_initial_deposit_usd"


def test_missing_file_still_returns_capital_provenance():
    result = model.berechne_modell({"quelle": "mql5"}, CAPITAL)
    assert result["status"] == "datenluecke" and result["startkapital_usd"] == 1000
    assert result["kapital_details"] == CAPITAL and result["kapital_methode"]


def test_sha_mismatch_is_not_silently_reparsed(tmp_path):
    entry = snapshot(tmp_path)
    (tmp_path/"trades.csv").write_text(HEADER, encoding="utf-8")
    result = model.berechne_modell(entry, CAPITAL)
    assert result["status"] == "datenluecke" and "SHA-256" in result["grund"]
    assert result["nettogewinn_usd"] is None


def ecb_file(tmp_path):
    target = tmp_path/"fx"
    target.mkdir()
    (target/"eurofxref-hist.csv").write_text(
        "Date,USD,JPY,AUD\n2026-01-06,1.2,120,2.4\n2026-01-05,1.1,110,2.2\n", encoding="utf-8")


def test_known_foreign_money_is_converted_at_realization_date_from_local_ecb(tmp_path, monkeypatch):
    ecb_file(tmp_path)
    entry = snapshot(tmp_path, account_currency="EUR", trade_money_currency="EUR")
    seen = fake_kernel(monkeypatch)
    monkeypatch.setattr(fx_rates, "usd_per", lambda *a: pytest.fail("No default FX refresh"))
    result = model.berechne_modell(entry, CAPITAL, kurse=object())
    assert result["status"] == "berechnet", result
    assert result["nettogewinn_usd"] == 120 and seen[0][0].trades[0].profit == 120
    assert result["quellenwaehrung"] == "EUR" and result["waehrung"] == "USD"
    assert result["fx_belege"] == [{"waehrung": "EUR", "ereignistag": "2026-01-06",
                                    "kursdatum": "2026-01-06", "usd_je_einheit": 1.2,
                                    "quelle": "lokale ECB-Referenzkursdatei",
                                    "datei": str(tmp_path/"fx"/"eurofxref-hist.csv")}]
    # A second provider's audit register contains only its own actual lookups.
    other = model.berechne_modell(snapshot(tmp_path), CAPITAL, kurse=object())
    assert other["fx_belege"] == []


@pytest.mark.parametrize("currency", ["UST", "CNH", "EUR", ""])
def test_unknown_currency_or_absent_historical_fx_stays_a_gap(tmp_path, currency):
    entry = snapshot(tmp_path, account_currency=currency, trade_money_currency=currency)
    result = model.berechne_modell(entry, CAPITAL)
    assert result["status"] == "datenluecke" and result["nettogewinn_usd"] is None


def test_conflicting_currency_metadata_is_rejected(tmp_path):
    result = model.berechne_modell(snapshot(tmp_path, account_currency="EUR"), CAPITAL)
    assert result["status"] == "datenluecke" and "Widersprüchliche" in result["grund"]


def test_robo_source_profit_is_not_treated_as_lots_or_trade_usd(tmp_path):
    result = model.berechne_modell(snapshot(tmp_path, quelle="robo"), CAPITAL)
    assert result["status"] == "datenluecke" and "Volumeneinheiten" in result["grund"]


def cached_prices(tmp_path, items):
    path = tmp_path/"kursdaten.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE h1_bars(feed TEXT,symbol TEXT,zeitrahmen TEXT,epoch INTEGER,"
                     "open REAL,high REAL,low REAL,close REAL,abgeschlossen INTEGER)")
        conn.executemany("INSERT INTO h1_bars VALUES(?,?,?,?,?,?,?,?,?)", items)
    return path


def test_cache_reads_only_exact_feed_and_final_bars_and_does_not_merge_feeds(tmp_path):
    one = json.dumps(["C:/test/a/terminal64.exe", "server-a"])
    two = json.dumps(["C:/test/b/terminal64.exe", "server-b"])
    path = cached_prices(tmp_path, [(one, "XAUUSD", "H1", 3600, 10, 11, 9, 10, 1),
                                    (one, "XAUUSD", "H1", 7200, 12, 13, 11, 12, 0),
                                    (two, "EURUSD", "H1", 3600, 1, 1, 1, 1, 1),
                                    ("unknown-feed", "XAUUSD", "H1", 3600, 999, 999, 999, 999, 1)])
    before = path.read_bytes()
    providers = model.OfflineH1Cache(path, settings={}).providers({})
    assert len(providers) == 2
    assert providers[0].hole_h1("XAUUSD", 0, 10000) == [
        {"time": 3600, "open": 10, "high": 11, "low": 9, "close": 10}]
    assert providers[0].hole_h1("EURUSD", 0, 10000) is None
    assert providers[1].hole_h1("XAUUSD", 0, 10000) is None
    assert path.read_bytes() == before


@pytest.mark.parametrize("wrong_feed_first", [False, True])
def test_real_kernel_uses_h1_prices_and_returns_negative_equity_evidence(tmp_path, wrong_feed_first):
    start = dt.datetime(2026, 1, 5)
    feed = json.dumps(["C:/test/a/terminal64.exe", "server-a"])
    items = []
    for hour in range(24):
        close = 1990 if hour == 10 else 2000+7*hour
        epoch = int((start+dt.timedelta(hours=hour)).replace(tzinfo=dt.timezone.utc).timestamp())
        items.append((feed, "XAUUSD", "H1", epoch, close, close+.4, close-.4, close, 1))
    if wrong_feed_first:
        wrong = json.dumps(["C:/test/0-wrong/terminal64.exe", "server-wrong"])
        items += [(wrong, symbol, tf, epoch, 999, 999.4, 998.6, 999, final)
                  for _feed, symbol, tf, epoch, _o, _h, _l, _c, final in list(items)]
    path = cached_prices(tmp_path, items)
    entry = snapshot(tmp_path, ["2026.01.05 01:00:00;Buy;1;XAUUSD;2006.9;1;2026.01.05 22:00:00;2154;0;0;0"])
    result = model.berechne_modell(entry, CAPITAL, model.OfflineH1Cache(path, settings={}))
    assert result["equity"]["status"] == "ok", result
    assert result["equity"]["gmt_offset_h"] == 0
    assert result["equity"]["cache_feed"] == feed
    assert len(result["equity"]["kursquellen_versuche"]) == (2 if wrong_feed_first else 1)
    assert result["equity_dd_pct"] > 100 and result["equity"]["min_equity_usd"] < 0
    assert result["equity"]["end_equity_usd"] == 1000  # recovered, not silently healthy
    assert result["status"] == "eingeschraenkt"
    assert "_curve" not in result["equity"]


def test_optional_fx_injection_leaves_legacy_helper_default_unchanged(monkeypatch):
    seen = []
    monkeypatch.setattr(fx_rates, "usd_per", lambda c, d: seen.append((c, d)) or {"rate": 2})
    old = er.H1UsdUmrechnung(None, 0, 1)
    custom = er.H1UsdUmrechnung(None, 0, 1, fx_lookup=lambda c, d: {"rate": 3})
    day = dt.date(2026, 1, 5)
    assert old.faktor("EUR", day, 0, "XAUEUR") == 2
    assert custom.faktor("EUR", day, 0, "XAUEUR") == 3
    assert seen == [("EUR", day)]
