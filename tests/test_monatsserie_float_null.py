"""Vollauszahlungen: Maschinenrundung von realem negativen Kapital trennen."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from mqlkiscanner import portfolio_statistik


def _parsed(*, rest=0, pnl_auf_leerem_konto=0):
    def trade(tag, pnl):
        return SimpleNamespace(open_time=datetime.fromisoformat(tag),
                               close_time=datetime.fromisoformat(tag), net=pnl)
    def flow(tag, wert):
        return SimpleNamespace(time=datetime.fromisoformat(tag), amount=wert)
    # Dezimalzahlen, die binaer nicht exakt darstellbar sind. Die einzelnen
    # 0.01-Gewinne werden vor mehreren Kapitalfluessen im Saldo aufaddiert.
    trades = [trade('2026-01-01', 0)]
    flows = []
    for tag in range(2, 22):
        trades.append(trade(f'2026-01-{tag:02d}', 0.01))
        flows.append(flow(f'2026-01-{tag:02d}T12:00:00', 0.0))
    flows.extend([flow('2026-01-22', -1500.05-rest),
                  flow('2026-03-01', 100)])
    if pnl_auf_leerem_konto:
        trades.append(trade('2026-02-15', pnl_auf_leerem_konto))
    trades.append(trade('2026-03-15', 10))
    return SimpleNamespace(trades=trades, balances=flows)


def test_vollauszahlung_leermonat_wiedereinzahlung_kein_nullnenner():
    result = portfolio_statistik._monatsserie(_parsed(), 1499.85)
    assert result['2026-01'] == pytest.approx(0.20 / 1499.85 * 100)
    assert result['2026-02'] == 0
    assert result['2026-03'] == pytest.approx(10)


@pytest.mark.parametrize('rest', [0.001, 0.01, 1])
def test_reale_ueberauszahlung_bleibt_undefiniert(rest):
    assert portfolio_statistik._monatsserie(_parsed(rest=rest), 1499.85) == {}


@pytest.mark.parametrize('pnl', [-0.001, 0.001, 1])
def test_pnl_ohne_positive_basis_wird_nicht_erfunden(pnl):
    assert portfolio_statistik._monatsserie(
        _parsed(pnl_auf_leerem_konto=pnl), 1499.85) == {}
