"""Gemischte Handelszeiten duerfen Goldpausen nicht zu Datenloechern machen."""
from mqlkiscanner.forensics.equity_rekonstruktion import _aktive_marktpausen
import pytest


H = 3600


def test_gold_wochenende_trotz_btc_bars_ohne_btc_position():
    active = {'XAUUSD': set(range(H, 49*H, H)), 'BTCUSD': {50*H}}
    closes = {'XAUUSD': {0: 2000, 49*H: 2000},
              'BTCUSD': {t: 50000 for t in range(0, 52*H, H)}}
    pauses, evidence = _aktive_marktpausen(active, closes)
    assert pauses == active['XAUUSD']
    assert evidence == [{'symbol': 'XAUUSD', 'bar_ende_vorher': 0,
                         'bar_ende_nachher': 49*H, 'aktive_pausenstunden': 48,
                         'ausgenommene_aktive_stunden': 48}]


def test_aktive_btc_position_erhaelt_stunden_im_nenner():
    active = {'XAUUSD': set(range(H, 49*H, H)), 'BTCUSD': {5*H, 6*H}}
    closes = {'XAUUSD': {0: 2000, 49*H: 2000},
              'BTCUSD': {t: 50000 for t in range(0, 52*H, H) if t != 5*H}}
    pauses, _ = _aktive_marktpausen(active, closes)
    assert 5*H not in pauses and 6*H not in pauses
    assert len(pauses) == 46


def test_kurze_oder_unbegrenzte_kursluecke_bleibt_im_nenner():
    active = {'XAUUSD': {H, 2*H, 3*H, 100*H}}
    closes = {'XAUUSD': {0: 2000, 2*H: 2000, 4*H: 2000}}
    assert _aktive_marktpausen(active, closes)[0] == set()


def test_unbekanntes_aktives_symbol_verhindert_pausenannahme():
    active = {'XAUUSD': {H}, 'UNKNOWN': {H}}
    closes = {'XAUUSD': {0: 2000, 49*H: 2000}}
    assert _aktive_marktpausen(active, closes)[0] == set()


@pytest.mark.parametrize('pfad', ['workflow', 'manuell'])
@pytest.mark.parametrize('btc_aktiv', [False, True])
def test_reko_entfernt_nur_pausierte_goldstunden_aus_zaehler_und_nenner(monkeypatch, pfad, btc_aktiv):
    import datetime as dt
    from types import SimpleNamespace
    from mqlkiscanner.kursdaten import FakeKursDaten
    from mqlkiscanner.forensics.equity_rekonstruktion import rekonstruiere
    from mqlkiscanner import equity_studie

    monkeypatch.setattr('mqlkiscanner.forensics.equity_rekonstruktion._resolve_symbol',
                        lambda *args: dict(factor=100, quote='USD'))
    monkeypatch.setattr(equity_studie, '_resolve_symbol',
                        lambda *args: dict(factor=100, quote='USD'))
    start = dt.datetime(2026, 1, 5)
    epoch = int(start.replace(tzinfo=dt.timezone.utc).timestamp())
    def trade(symbol, a, b, price):
        return SimpleNamespace(symbol=symbol, direction='buy', volume=0.01,
                               open_time=start+dt.timedelta(seconds=a),
                               close_time=start+dt.timedelta(seconds=b),
                               entry_price=price, exit_price=price, net=0.0)
    def bar(hour, price):
        return dict(time=epoch+hour*H, open=price, high=price,
                    low=price, close=price)
    data = {'XAUUSD': [bar(h, 2000) for h in (0, 25, 26, 27, 28)],
            'BTCUSD': [bar(h, 50000) for h in range(30)]}
    parsed = SimpleNamespace(trades=[trade('XAUUSD', 600, 27*H, 2000),
                                    trade('BTCUSD', 27*H+600, 29*H, 50000)],
                             balances=[], pendings=[])
    if btc_aktiv:
        parsed.trades.append(trade('BTCUSD', 600, 27*H, 50000))
    result = (rekonstruiere(parsed, FakeKursDaten(data), 10000, gmt_offset_h=0)
              if pfad=='workflow' else
              equity_studie.studie(parsed, FakeKursDaten(data), 10000, gmt_offset_h=0)['kennzahlen'])
    assert 'marktpausen' in result, result
    assert result['marktpausen']['ausgenommene_aktive_stunden'] == (0 if btc_aktiv else 24)
    if not btc_aktiv:
        assert result['abdeckung_pct_raw'] == 100.0
    else:
        assert result['abdeckung_pct_raw'] < 95.0
    assert result['verlaesslich'] is (not btc_aktiv)
