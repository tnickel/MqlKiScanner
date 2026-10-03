"""Regressionen aus echten Gold-Quoteversatzen, ohne Terminal/Netz/DB."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from mqlkiscanner import equity_studie, kursdaten
from mqlkiscanner.forensics import equity_rekonstruktion as er
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


START = dt.datetime(2026, 1, 5)  # Montag


def _daten(phasen=(0, 1, 0), proben=(6, 6, 6)):
    bars = [{"time": er._epoch(START + dt.timedelta(hours=i)),
             "open": 2000 + 17 * i, "high": 2000.01 + 17 * i,
             "low": 1999.99 + 17 * i, "close": 2000 + 17 * i}
            for i in range(7 * 24 * len(phasen) + 24)]
    by_time = {b["time"]: b for b in bars}
    trades = []
    for w, (shift, anzahl) in enumerate(zip(phasen, proben)):
        for n in range(anzahl):
            offen = START + dt.timedelta(days=7 * w, hours=2 + n * 4, minutes=10)
            ende = offen + dt.timedelta(hours=1)
            entry = by_time[(er._epoch(offen) + shift * 3600) // 3600 * 3600]["close"]
            exit_ = by_time[(er._epoch(ende) + shift * 3600) // 3600 * 3600]["close"]
            trades.append(Trade(offen, ende, "Sell", .01, "XAUUSD", entry, exit_,
                                entry - exit_))
    return ParsedExport("synthetisch", "positions", trades, []), {"XAUUSD": bars}


def test_lokaler_shift_null_eins_null_entspricht_einheitlicher_referenz():
    parsed, bars = _daten()
    model = er.Zeitbasis(parsed.trades, bars, 0)
    assert [p["offset_s"] for p in model.perioden] == [0, 3600, 0]
    assert model.verlaesslich
    normal = model.normalisiere(parsed)
    observed = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000)
    reference = er.rekonstruiere(normal, kursdaten.FakeKursDaten(bars), 10000,
                                 gmt_offset_h=0)
    assert observed["equity_dd_pct_raw"] == pytest.approx(reference["equity_dd_pct_raw"])
    assert observed["end_equity_usd"] == reference["end_equity_usd"]
    assert observed["verlaesslich"]
    assert observed["zeitbasis"]["modus"] == "wochenweise"
    assert parsed.trades[6].open_time != normal.trades[6].open_time
    assert parsed.trades[6].profit == normal.trades[6].profit


def test_global_unzureichend_aber_beide_lokalen_phasen_eindeutig():
    parsed, bars = _daten((0, 1), (5, 5))
    assert er.ermittle_gmt_offset(parsed.trades, bars)["offset_s"] is None
    result = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert result["status"] == "ok"
    assert result["zeitbasis"]["global_belegt"] is False
    assert result["zeitbasis"]["verlaesslich"]
    study = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert study["status"] == "ok"
    assert study["kennzahlen"]["verlaesslich"]
    assert study["zeitbasis"]["frame"] == "referenzkurszeit"


def test_langer_trade_mappt_open_close_getrennt_und_grenzstunde_bleibt_unklar():
    parsed, bars = _daten()
    opened = START + dt.timedelta(days=6, hours=23, minutes=30)
    closed = START + dt.timedelta(days=7, hours=2, minutes=30)
    lookup = {b["time"]: b["close"] for b in bars["XAUUSD"]}
    entry = lookup[er._epoch(opened) // 3600 * 3600]
    exit_ = lookup[(er._epoch(closed) + 3600) // 3600 * 3600]
    parsed.trades.append(Trade(opened, closed, "Buy", .01, "XAUUSD", entry, exit_, exit_ - entry))
    model = er.Zeitbasis(parsed.trades, bars, 0)
    normal = model.normalisiere(parsed).trades[-1]
    assert normal.open_time == opened
    assert normal.close_time == closed + dt.timedelta(hours=1)
    assert normal.close_time >= normal.open_time
    assert model.nach_broker(er._epoch(START + dt.timedelta(days=7))) is None
    assert not model.verlaesslich
    assert model.offene_wechsel_annahmen == 1
    result = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert not result["kennzahlen"]["verlaesslich"]
    assert result["konto_studie"]["kennzahlen"]["konto_equity_dd_pct"] is None


def test_duenne_abweichende_woche_wird_nicht_global_schoengerechnet():
    parsed, bars = _daten((0, 1, 0), (6, 1, 6))
    result = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert not result["verlaesslich"]
    assert result["zeitbasis"]["perioden"][1]["belegt"] is False
    assert result["zeitbasis"]["unsichere_trade_ereignisse"] > 0
    assert result["end_equity_usd"] == pytest.approx(10000 + sum(t.net for t in parsed.trades))


def test_ein_unpassender_endpunkt_in_duenner_global_kompatibler_woche():
    parsed, bars = _daten((0, 0), (6, 1))
    parsed.trades[-1].exit_price = 999999
    model = er.Zeitbasis(parsed.trades, bars, 0)
    assert model.perioden[-1]["status"] == "global_kompatibel"
    assert not model.verlaesslich
    assert any("Open-/Close-Preis" in g for g in model.gruende)


def test_unsichere_innenwoche_eines_langtrades_verhindert_urteil():
    parsed, bars = _daten((0, 1, 0), (6, 1, 6))
    opened = START + dt.timedelta(hours=1, minutes=30)
    closed = START + dt.timedelta(days=14, hours=23, minutes=30)
    lookup = {b["time"]: b["close"] for b in bars["XAUUSD"]}
    entry = lookup[er._epoch(opened) // 3600 * 3600]
    exit_ = lookup[er._epoch(closed) // 3600 * 3600]
    parsed.trades.append(Trade(opened, closed, "Buy", .01, "XAUUSD", entry, exit_, exit_ - entry))
    model = er.Zeitbasis(parsed.trades, bars, 0)
    assert model.unsichere_innenperioden >= 1
    assert not model.verlaesslich
    result = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert not result["verlaesslich"]


def test_inverse_ruecksprung_ist_unklar_und_flowindex_bleibt_danach_unbekannt():
    parsed, bars = _daten()
    flow = START + dt.timedelta(days=13, hours=23, minutes=30)
    parsed.balances.append(BalanceRow(flow, 100))
    model = er.Zeitbasis(parsed.trades, bars, 0)
    ref = er._epoch(flow) + 3600
    assert model.nach_broker(ref) is None
    assert model.broker_tag(ref) is None
    study = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    konto = study["konto_studie"]
    assert konto["kennzahlen"]["index_abbruch_am"] == ref
    assert konto["kennzahlen"]["konto_equity_dd_pct"] is None
    assert all(p["rendite_index"] is None for p in konto["punkte"] if p["t"] >= ref)


def test_nichtmonotone_abbildung_mit_close_vor_open_wird_geskippt():
    parsed, bars = _daten()
    opened = START + dt.timedelta(days=13, hours=23, minutes=50)
    closed = START + dt.timedelta(days=14, minutes=10)
    price = next(b["close"] for b in bars["XAUUSD"]
                 if b["time"] == er._epoch(START + dt.timedelta(days=14)))
    parsed.trades.append(Trade(opened, closed, "Buy", .01, "XAUUSD", price, price, 0))
    result = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert result["status"] == "skipped"
    assert "monoton" in result["grund"]
    assert result["zeitbasis"]["monoton"] is False
    study = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert study["status"] == "skipped"


def test_fehlende_bars_verkleinern_gmt_checknenner_nicht():
    parsed, bars = _daten((0,), (5,))
    keep = {er._epoch(t.open_time) // 3600 * 3600 for t in parsed.trades}
    sparse = {"XAUUSD": [b for b in bars["XAUUSD"] if b["time"] in keep]}
    result = er.ermittle_gmt_offset(parsed.trades, sparse)
    assert result["offset_s"] is None
    assert result["trefferquote"] == .5


def test_fester_manueller_shift_hat_vorrang_vor_lokaler_autowahl():
    parsed, bars = _daten()
    result = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000,
                              gmt_offset_h=0)
    assert result["gmt_offset_h"] == 0
    assert result["zeitbasis"]["modus"] == "manuell"
    assert {p["gmt_h"] for p in result["zeitbasis"]["perioden"]} == {0}
    study = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000,
                                gmt_offset_h=0)
    assert study["zeitbasis"]["modus"] == "manuell"


def test_nicht_angewandtes_wochenmodell_meldet_tatsaechlichen_broker_frame(monkeypatch):
    parsed, bars = _daten()
    extra = copy.copy(parsed.trades[0])
    extra.symbol = "EURUSD"
    extra.volume = .00001
    parsed.trades.append(extra)
    bars["EURUSD"] = copy.deepcopy(bars["XAUUSD"])
    monkeypatch.setattr(equity_studie, "ermittle_gmt_je_symbol", lambda *_:
                        {"offsets": {"XAUUSD": 0, "EURUSD": 7200}, "befunde": []})
    result = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    assert result["zeitbasis"]["modus"] == "wochenweise"
    assert result["zeitbasis"]["frame"] == "broker"
    assert result["zeitbasis"]["angewandt"] is False
    assert result["kennzahlen"]["zeitbasis_einheitlich"] is False


@pytest.mark.parametrize("value", [True, False, .5, 15])
def test_ungueltiger_manueller_shift_wird_abgelehnt(value):
    parsed, bars = _daten()
    with pytest.raises(ValueError):
        er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10000, gmt_offset_h=value)
    with pytest.raises(ValueError):
        equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000, gmt_offset_h=value)


def test_flow_und_fx_tag_werden_in_gleicher_referenzabbildung_gehalten(monkeypatch):
    parsed, bars = _daten()
    for t in parsed.trades:
        t.symbol = "AUDCAD"
        t.volume = .00001  # 1 CAD je Preiseinheit
    bars = {"AUDCAD": bars["XAUUSD"]}
    lookup = {b["time"]: b["close"] for b in bars["AUDCAD"]}
    opened = START + dt.timedelta(days=7, hours=22, minutes=10)
    closed = START + dt.timedelta(days=8, hours=2, minutes=10)
    entry = lookup[(er._epoch(opened) + 3600) // 3600 * 3600]
    exit_ = lookup[(er._epoch(closed) + 3600) // 3600 * 3600]
    parsed.trades.append(Trade(opened, closed, "Buy", .00001, "AUDCAD", entry, exit_,
                               (exit_ - entry) * .75))
    flow = START + dt.timedelta(days=7, hours=23, minutes=30)
    parsed.balances.append(BalanceRow(flow, 100))
    tags = []
    monkeypatch.setattr(er.fx_rates, "usd_per", lambda quote, tag:
                        tags.append(tag) or {"rate": .75})
    original = copy.deepcopy(parsed)
    result = equity_studie.studie(parsed, kursdaten.FakeKursDaten(bars), 10000)
    event = result["konto_studie"]["flow_befunde"][0]
    assert event["t"] == er._epoch(flow) + 3600
    assert event["gueltig"]
    assert event["kursbasis"][0]["bar_ende"] <= event["t"]
    assert flow.date() in tags
    assert event["equity_vor_flow"] == pytest.approx(
        10000 + sum(t.net for t in original.trades if t.close_time <= flow))
    # Der Close der laufenden Referenzstunde laege 17 Preiseinheiten hoeher;
    # er darf um 00:30 noch nicht in die Flow-Equity eingehen.
    assert event["kursbasis"][0]["kurs"] == entry
    assert parsed == original  # keine Mutation des Original-Exports


def test_knappe_ausreisser_in_starker_woche_werfen_messung_nicht_weg():
    """Nutzer-Fall GS MT5 03.10.: EIN 4-Sekunden-Scalp mit Nacht-Spread-
    Ausreisserpreis (knapp ausserhalb der Toleranz) in einer STARKEN Woche
    (>= 10 Proben, >= 90 % Treffer) darf weder die Woche noch die Messung
    verwerfen — nur seine eigenen Stunden werden Luecken. Real: Abdeckung
    96 % -> 66 % nur wegen dieses einen Trades, GS MT5 verlor das Gruen."""
    parsed, bars = _daten(phasen=(0,), proben=(12,))
    # Ein zwoelfter Trade in derselben Woche, Preis ~3x Toleranz ausserhalb
    # der Bar (Spread-Ausreisser), 4 Sekunden offen.
    by_time = {b["time"]: b for b in bars["XAUUSD"]}
    offen = START + dt.timedelta(hours=5, minutes=31)
    bar = by_time[(er._epoch(offen)) // 3600 * 3600]
    entry = bar["high"] + 3 * (abs(bar["high"]) * er._PREIS_TOLERANZ)
    parsed.trades.append(Trade(offen, offen + dt.timedelta(seconds=4),
                               "Buy", .01, "XAUUSD", entry, entry, 0.0))
    model = er.Zeitbasis(parsed.trades, bars, 0)
    aktuelle_woche = model.perioden[0]
    assert aktuelle_woche["status"] == "lokal_preisbelegt"
    assert aktuelle_woche["belegt"] is True          # 12/13 >= 90 %
    assert model.verlaesslich is True                # knapp -> KEIN Verwurf
    assert model.unsichere_trade_ereignisse >= 2      # entry+exit des Scalps
    assert model.weit_draussen_ereignisse == 0
    ergebnis = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10_000.0)
    assert ergebnis["status"] == "ok"
    assert ergebnis["verlaesslich"] is True
    assert ergebnis["abdeckung_pct"] >= 95.0


def test_weit_draussen_bleibt_hart_unzuverlaessig():
    """Ein Preis um Groessenordnungen daneben (falsche Zeitzone / kaputter
    Export) widerlegt die Zeitachse weiterhin — der 999999-Gedanke der
    urspruenglichen Regel bleibt erhalten."""
    parsed, bars = _daten(phasen=(0,), proben=(12,))
    by_time = {b["time"]: b for b in bars["XAUUSD"]}
    offen = START + dt.timedelta(hours=5, minutes=31)
    bar = by_time[(er._epoch(offen)) // 3600 * 3600]
    entry = bar["high"] * 5  # Groessenordnung daneben
    parsed.trades.append(Trade(offen, offen + dt.timedelta(hours=1),
                               "Buy", .01, "XAUUSD", entry, entry, 0.0))
    model = er.Zeitbasis(parsed.trades, bars, 0)
    assert model.weit_draussen_ereignisse >= 1
    assert model.verlaesslich is False
    ergebnis = er.rekonstruiere(parsed, kursdaten.FakeKursDaten(bars), 10_000.0)
    assert ergebnis["verlaesslich"] is False
