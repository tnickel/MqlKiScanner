"""ID-freie FX-/Pausenregeln gelten fuer Workflow und manuelle Studie."""
import datetime as dt
from types import SimpleNamespace

import pytest

from mqlkiscanner import equity_studie
from mqlkiscanner.forensics import equity_rekonstruktion as er
from mqlkiscanner.kursdaten import FakeKursDaten


@pytest.mark.parametrize('pfad', ['workflow', 'manuell'])
@pytest.mark.parametrize('quote,symbol', [('BCH', 'XRPBCH'), ('ETH', 'SOLETH'), ('CNH', 'USDCNH')])
@pytest.mark.parametrize('fehlt', [False, True])
def test_direkte_umrechnung_beliebiger_instrumente_mehrere_trades(
        monkeypatch, pfad, quote, symbol, fehlt):
    monkeypatch.setattr(er.fx_rates, 'usd_per', lambda *_: None)
    for module in (er, equity_studie):
        monkeypatch.setattr(module, '_resolve_symbol', lambda *_: dict(factor=10, quote=quote))
    start = dt.datetime(2026, 2, 2)
    epoch = int(start.replace(tzinfo=dt.timezone.utc).timestamp())
    def bars(values):
        return [dict(time=epoch+i*3600, open=v, close=v, high=max(7, v), low=min(3, v))
                for i, v in enumerate(values) if v is not None]
    def trade(direction, opened, closed, entry):
        return SimpleNamespace(symbol=symbol, direction=direction, volume=0.01,
                               open_time=start+dt.timedelta(minutes=opened),
                               close_time=start+dt.timedelta(minutes=closed),
                               entry_price=entry, exit_price=7, net=0)
    parsed = SimpleNamespace(trades=[trade('buy', 10, 240, 7), trade('sell', 70, 190, 6)],
                             balances=[], pendings=[])
    data = {symbol: bars([7, 6, None if fehlt and quote=='CNH' else 3, 7, 7])}
    if quote!='CNH':
        data[quote+'USD'] = bars([100, 200, None if fehlt else 500, 100, 100])
    class Feed(FakeKursDaten):
        terminal_pfad = 'parity-test-feed'
        def __init__(self):
            super().__init__(data)
            self.terminal_herkunft = {}
        def hole_h1(self, symbol, *args, **kwargs):
            result = super().hole_h1(symbol, *args, **kwargs)
            if result:
                self.terminal_herkunft[symbol] = self.terminal_pfad
            return result
    if pfad=='workflow':
        result = er.rekonstruiere(parsed, Feed(), 10000, gmt_offset_h=0)
        dd = result['equity_dd_usd']
    else:
        study = equity_studie.studie(parsed, Feed(), 10000, gmt_offset_h=0)
        result = study['kennzahlen']
        dd = result['equity_dd_usd']
    assert result['verlaesslich'] is (not fehlt)
    if not fehlt:
        # At hour3 the two opposite positions sum to -0.1 quote units.
        assert dd == (0.03 if quote=='CNH' else 50.0)
    provenance = result['fx_umrechnungen'][0]
    assert provenance['instrument']==symbol
    assert provenance['quote']==quote
    assert provenance['umrechnungssymbol']==(symbol if quote=='CNH' else quote+'USD')
    if fehlt:
        assert epoch+3*3600 not in provenance['verfuegbare_zeitpunkte']
