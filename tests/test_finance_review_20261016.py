"""Independent numerical regressions for F1–F11; no network/MT5/LLM."""
from datetime import date, datetime, timedelta
import csv
import io
import json
import math
from types import SimpleNamespace
import zipfile

import pytest

from mqlkiscanner import config, engine, equity_studie, fx_rates, parser, portfolio_statistik as ps, scoring
from mqlkiscanner.forensics import drawdown, equity_rekonstruktion as eq, exposure, martingale
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade
from mqlkiscanner.pipeline import ScanResult, ampel_for


A = datetime(2025, 1, 1)
Z = datetime(2025, 7, 1)
H = datetime(2025, 1, 6, 10)


def trade(open=A, close=Z, profit=0., volume=.01, symbol="XAUUSD", commission=0.):
    return Trade(open, close, "Buy", volume, symbol, 2000., 2000., profit, commission)


def parsed(trades, flows=()):
    return ParsedExport("synthetic", "positions", trades=list(trades), balances=list(flows))


def csv_export(tmp_path, data, name="finance.csv"):
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter=";")
        writer.writerow(parser.POSITION_HEADER)
        for t in data.trades:
            writer.writerow([t.open_time.strftime(parser.TIME_FMT), t.direction, t.volume,
                t.symbol, t.entry_price, t.volume, t.close_time.strftime(parser.TIME_FMT),
                t.exit_price, t.commission, t.swap, t.profit])
        for b in data.balances:
            writer.writerow([b.time.strftime(parser.TIME_FMT), "Balance", "", "", "", "", "", "", "", "", b.amount])
    return str(path)


class Bars:
    def __init__(self, values=(1999., 1998., 2000., 2000.), start=H):
        self.rows = [dict(time=eq._epoch(start+timedelta(hours=i)), open=2000.,
                         low=1800., high=2200., close=close) for i, close in enumerate(values)]

    def hole_h1(self, symbol, von, bis):
        return self.rows if symbol == "XAUUSD" else []


def test_f1_partial_measurement_keeps_known_floating_loss():
    known = [trade(H, H+timedelta(hours=3), volume=1.) for _ in range(4)]
    missing = trade(H, H+timedelta(hours=3), volume=1., symbol="US30")
    result = eq.rekonstruiere(parsed(known+[missing]), Bars(), 1000., gmt_offset_h=0)
    # Four gold lots lose 2 quote units * 100 USD/unit = 800 of 1000 USD.
    assert result["equity_dd_pct_raw"] == pytest.approx(80.)
    assert result["status"] == "ok_teilmessung"
    assert result["verlaesslich"] is True
    assert result["symbole_nicht_betrachtet"] == ["US30"]


def test_f1_missing_hour_of_known_symbol_is_still_unreliable():
    known = [trade(H, H+timedelta(hours=3), volume=1.) for _ in range(4)]
    missing = trade(H, H+timedelta(hours=3), symbol="US30")
    provider = Bars()
    del provider.rows[1]
    result = eq.rekonstruiere(parsed(known+[missing]), provider, 1000., gmt_offset_h=0)
    assert result["status"] == "unvollstaendig"
    assert result["verlaesslich"] is False


def test_f2_unknown_equity_at_flow_cannot_green_or_revive_cached_returns(tmp_path, monkeypatch):
    data = parsed([trade(profit=80.)], [BalanceRow(A,100.), BalanceRow(datetime(2025,3,1),100.)])
    result = ps.effizienz_kennzahlen(csv_export(tmp_path,data),100.,20.)
    assert result["effizienz_status"] == "kapitalfluss_equity_unbelegt"
    assert result["cagr_jahr_pct"] is None
    assert result["ertrag_monat_geom_pct"] is None
    assert ps._monatsserie(data,100.) == {}
    # Old balance-TWR falsely gave CAGR97.185/20=4.859; an equity80 flow gives
    # (80/100)*(280/180), annualized 55.472/20=2.774. Unknown must stay unknown.
    expected = math.expm1(math.log((80/100)*(280/180))/((Z-A).days/ps.JAHR_TAGE))*100
    assert expected/20 < 3
    r = ScanResult(999999, forensik_vorhanden=True, kapitalbasis_usd=100.,
        equity_dd_rekonstruiert_pct=20., ertrag_monat_geom_pct=5.82,
        cagr_jahr_pct=97.185, effizienz_befund=result)
    monkeypatch.setattr(config,"load_known_signals",lambda: {})
    assert ampel_for(r,config.DEFAULT_SETTINGS)[0] == "🟡"
    assert r.retdd_jahr is None
    assert r.effizienz_befund["effizienz_status"] == "kapitalfluss_equity_unbelegt"


@pytest.mark.parametrize("header,money", [(parser.POSITION_HEADER,8),(parser.POSITION_HEADER,9),
    (parser.ORDERBOOK_HEADER,9),(parser.ORDERBOOK_HEADER,10)])
def test_f3_typeless_fee_is_rejected(tmp_path,header,money):
    row=[""]*len(header)
    row[0]="2025.01.01 00:00:00"
    row[money]="-250"
    path=tmp_path/"bad.csv"
    path.write_text(";".join(header)+"\n"+";".join(row)+"\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Datensatz ohne Typ"):
        parser.load_export(str(path))


@pytest.mark.parametrize("amount", [-50.,100.])
def test_f4_real_study_points_do_not_count_flows_twice(amount):
    ts=[trade(H,H+timedelta(hours=1)),trade(H+timedelta(hours=4),H+timedelta(hours=5))]
    data=parsed(ts,[BalanceRow(H,100.),BalanceRow(H+timedelta(hours=2),amount)])
    result=equity_studie.studie(data,Bars([2000.]*7),100.,gmt_offset_h=0)
    diag=result["konto_studie"]
    assert diag["punkte"][-1]["actual_equity"] == 100.+amount
    assert diag["punkte"][-1]["account_balance"] == 100.+amount
    assert diag["punkte"][-1]["return_index"] == pytest.approx(1.)
    assert diag["kennzahlen"]["konto_equity_dd_pct"] == 0.
    assert diag["verlaesslich"] is True


@pytest.mark.parametrize("flows", [False, True])
def test_f5_closed_dd_gate_uses_raw_value(flows, monkeypatch):
    ts=[trade(A,A+timedelta(days=1),100.),trade(A+timedelta(days=2),A+timedelta(days=3),-330.044),
        trade(A+timedelta(days=4),Z,500.)]
    balances=[BalanceRow(A,1000.)]
    if flows:
        balances.append(BalanceRow(A+timedelta(days=90),100.))
    d=drawdown.run(parsed(ts,balances))
    assert d["trading_dd"]["dd_pct_max_rel"] == 30.  # Display remains compatible.
    assert d["trading_dd"]["dd_pct_max_rel_raw"] == pytest.approx(30.004)
    risk=scoring.evaluate({"stats":{},"forensics":{"drawdown":d}})
    assert risk["schranke_eq_dd_verletzt"] is True
    r=ScanResult(999999,forensik_vorhanden=True,kapitalbasis_usd=1000.,
        trading_dd_pct=scoring._trading_dd_for_risk(d["trading_dd"]),
        equity_dd_rekonstruiert_pct=1.,ertrag_monat_geom_pct=5.,cagr_jahr_pct=100.)
    monkeypatch.setattr(config,"load_known_signals",lambda: {})
    assert ampel_for(r,config.DEFAULT_SETTINGS)[0] == "🔴"


def test_f5_engine_passes_unrounded_capital_to_reconstruction(tmp_path, monkeypatch):
    data=parsed([trade()],[BalanceRow(A,1000.005)])
    captured={}
    monkeypatch.setattr(engine.equity_rekonstruktion,"rekonstruiere",
        lambda p,k,startkapital,broker=None: captured.update(capital=startkapital) or {})
    result=engine.analyze(csv_export(tmp_path,data),kursanbieter=object())
    assert result["forensics"]["drawdown"]["startkapital_raw"] == 1000.005
    assert captured["capital"] == 1000.005


def test_f6_real_flow_curve_can_have_nonpositive_hypothetical_end(tmp_path):
    data=parsed([trade(A,A+timedelta(days=1)),trade(datetime(2025,2,2),Z,-200.)],
        [BalanceRow(A,100.),BalanceRow(datetime(2025,2,1),1000.)])
    result=ps.effizienz_kennzahlen(csv_export(tmp_path,data),100.,10.)
    expected=math.expm1(math.log(900/1100)/((Z-A).days/ps.JAHR_TAGE))*100
    assert result["endkapital_virtuell_usd"] == -100.
    assert result["cagr_jahr_pct"] == pytest.approx(expected)
    assert result["effizienz_status"] == "ok"


def test_f7_same_second_net_flows_are_order_invariant(tmp_path):
    at=datetime(2025,3,1)
    data=parsed([trade(profit=100.)],[BalanceRow(A,100.),BalanceRow(at,-200.),BalanceRow(at,200.)])
    reverse=parsed(data.trades,list(reversed(data.balances)))
    a=ps._monatsserie(data,100.)
    b=ps._monatsserie(reverse,100.)
    assert a == b
    assert math.prod(1+r/100 for r in a.values()) == pytest.approx(2.)
    result=ps.effizienz_kennzahlen(csv_export(tmp_path,data),100.,10.)
    assert result["kapitalfluesse_nach_start"] == 0
    assert result["effizienz_status"] == "ok"


@pytest.mark.parametrize("bad", ["NaN","Infinity","-Infinity","0","-1"])
def test_f8_bad_fx_cannot_be_complete(bad,monkeypatch):
    table=fx_rates._parse_csv(f"Date,USD,JPY\n2025-01-06,1.1,{bad}\n")
    monkeypatch.setattr(fx_rates,"load",lambda: table)
    assert fx_rates.usd_per("JPY",date(2025,1,6)) is None
    # Also protect consumers against invalid factors returned by older caches.
    monkeypatch.setattr(fx_rates,"usd_per",lambda *a: {"rate":float(bad),"date":"2025-01-06"})
    result=exposure.run(parsed([trade(H,H+timedelta(hours=3),symbol="EURJPY")]),kapitalbasis_usd=1000.)
    assert result["conversion_complete"] is False
    assert result["temporal_risk_available"] is False
    assert result["shock_pct_max"] is None


def test_f8_bad_download_preserves_previous_cache(tmp_path, monkeypatch):
    config.FX_RATES_DIR.mkdir(parents=True)
    path=config.FX_RATES_DIR/fx_rates.CSV_NAME
    old=b"Date,USD,JPY\n2025-01-06,1.1,160\n"
    path.write_bytes(old)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as archive:
        archive.writestr("eurofxref-hist.csv","Date,USD,JPY\n2026-10-16,1.1,NaN\n")
    monkeypatch.setattr(fx_rates.requests,"get",lambda *a,**kw: SimpleNamespace(
        content=stream.getvalue(),raise_for_status=lambda: None))
    fx_rates._refresh(force=True)
    assert path.read_bytes() == old
    assert not list(path.parent.glob("*.tmp"))
    assert fx_rates._parse_csv("Date,USD\nnot-a-date,1.2\n") == {}


def test_f9_portfolio_hint_obeys_current_annual_setting():
    text=ps.statistik([],{"min_calmar_jahr":4.25})["hinweis"]
    assert "Jahres-Calmar >= 4.25" in text
    assert "retdd_monat < 1" not in text
    assert "ohne eigenes Mindest-Gate" in text


def test_f10_basket_net_includes_commission_and_swap():
    ts=[trade(H+timedelta(minutes=i),H+timedelta(hours=3),1.,v,commission=-10.)
        for i,v in enumerate((.01,.02,.04))]
    ts[0].swap=-2.
    result=martingale.run(parsed(ts))
    assert result["basket_ladder"]["examples"][0]["net"] == -29.


@pytest.mark.parametrize("field,bad", [("contract_size",-100.),("contract_size",0.),
    ("contract_size",float("nan")),("contract_size",float("inf")),("contract_size",True),
    ("stress_move",-50.),("stress_move",0.),("stress_move",float("inf")),("stress_move_pct",float("nan"))])
def test_f11_invalid_contract_or_stress_is_rejected(field,bad,monkeypatch):
    spec={"contract_size":100.,"quote_currency":"USD","stress_move":50.,field:bad}
    monkeypatch.setattr(exposure,"spec_for",lambda *a,**kw: spec)
    with pytest.raises(ValueError,match="endlich und positiv"):
        exposure.run(parsed([trade(H,H+timedelta(hours=3))]),kapitalbasis_usd=1000.)
