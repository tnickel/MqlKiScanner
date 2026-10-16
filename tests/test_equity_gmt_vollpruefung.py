"""Ein Stichproben-Plateau darf vorhandene Preisbelege nicht auslassen."""
import datetime as dt

from mqlkiscanner.forensics import equity_rekonstruktion as er
from mqlkiscanner.kursdaten import FakeKursDaten
from mqlkiscanner.models import ParsedExport, Trade


START = dt.datetime(2026, 1, 5)


def daten(count=101, ausschliesslich_null=None, fehlende=None):
    trades, bars = [], []
    for i in range(count):
        time = START + dt.timedelta(hours=4*i)
        price = 1000 + 17*i
        trades.append(Trade(time + dt.timedelta(minutes=10),
            time + dt.timedelta(minutes=40), "Buy", .01, "XAUUSD", price, price, 0))
        if fehlende and i in fehlende:
            continue
        for shift in (0, 1):
            if shift == 1 and ausschliesslich_null and i in ausschliesslich_null:
                continue
            bars.append(dict(time=er._epoch(time) + shift*3600,
                             open=price, close=price, high=price+.01, low=price-.01))
    return trades, {"XAUUSD": bars}


def test_ausgelassene_probe_loest_plateau_mit_unveraenderter_schwelle_auf():
    # Index2 fehlt in der uniformen 60-aus-101-Stichprobe.
    trades, bars = daten(ausschliesslich_null={2})
    result = er.ermittle_gmt_offset(trades, bars)
    assert result["offset_s"] == 0
    assert result["trefferquote"] == 1
    assert result["proben"] == 101
    assert result["preisereignisse"] == 202
    assert result["vollpruefung_nach_stichprobe"] is True
    report = er.rekonstruiere(ParsedExport("synthetisch", "positions", trades, []),
                             FakeKursDaten(bars), 10000)
    assert report["gmt_pruefung"] == result


def test_echtes_plateau_bleibt_auch_nach_alle_preise_pruefen_unbekannt():
    trades, bars = daten()
    result = er.ermittle_gmt_offset(trades, bars)
    assert result["offset_s"] is None
    assert result["plateau_h"] == [0, 1]
    assert result["vollpruefung_nach_stichprobe"] is True


def test_duenne_stichprobe_ohne_bars_darf_vollstaendige_belege_nicht_verwerfen():
    trades, bars = daten(count=10, ausschliesslich_null=set(range(10)), fehlende={0, 5})
    result = er.ermittle_gmt_offset(trades, bars, max_proben=2)
    assert result["offset_s"] == 0
    assert result["trefferquote"] == .8
    assert result["proben"] == 10
    assert result["vollpruefung_nach_stichprobe"] is True


def test_unzureichende_vollbelege_bleiben_gesperrt():
    trades, bars = daten(count=10, ausschliesslich_null=set(range(10)), fehlende=set(range(6)))
    result = er.ermittle_gmt_offset(trades, bars, max_proben=2)
    assert result["offset_s"] is None
    assert result["trefferquote"] == .4


def test_eindeutige_stichprobe_behaelt_schnellen_pfad():
    trades, bars = daten(ausschliesslich_null=set(range(101)))
    result = er.ermittle_gmt_offset(trades, bars)
    assert result["offset_s"] == 0
    assert result["proben"] == 60
    assert result["vollpruefung_nach_stichprobe"] is False
