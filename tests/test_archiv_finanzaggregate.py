import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import parser, signal_statistik
from mqlkiscanner.alle_signale_ui import tabellen_zeile


HEADER = ';'.join(parser.ORDERBOOK_HEADER) + '\n'
ARCHIVE = '2025.10.01 00:00:00;Buy;1.75;archived;;;;2025.10.31 23:59:59;;;;26.78;'
TRADE = '2025.11.04 16:13:25;Buy;0.04;GBPUSD;1.30537;;;2025.11.06 13:42:29;1.30928;-1;-2;15.64;'
COST = '2025.11.06 14:00:00;Commission;;;;;;;;;;-3;'


def _csv(tmp_path, rows):
    path = tmp_path / 'archive.csv'
    path.write_text(HEADER + '\n'.join(rows) + '\n')
    return str(path)


def test_finanzaggregate_sind_weder_trades_noch_flows_oder_h1_ereignisse(tmp_path):
    path = _csv(tmp_path, [ARCHIVE, TRADE, COST])
    with pytest.raises(ValueError):
        parser.load_export(path)
    parsed = parser.load_export(path, nur_finanzdaten=True)
    assert len(parsed.trades) == 1 and not parsed.balances
    assert len(parsed.archived_pnl_aggregates) == 1
    assert parsed.archived_pnl_aggregates[0].net == 26.78
    assert parsed.net_total == pytest.approx(9.64)  # individual events only
    assert len(parsed.realized_events()) == 2  # aggregate has no exact event time
    stats = signal_statistik.berechne(path, {'initial_deposit_usd': 1000})
    assert stats['netto_gesamt_usd'] == pytest.approx(36.42)
    assert stats['archivaggregate_anzahl'] == 1
    assert stats['einzeltrades_verifiziert'] == 1
    assert stats['teilstatistik_finanzdaten'] and not stats['kapitalbasis_ok']
    for key in ('trades', 'wins', 'losses', 'winrate_pct', 'profit_faktor',
                'ertrag_monat_geom_pct', 'trading_dd_pct', 'cagr_jahr_pct', 'monate_pct', 'kurve'):
        assert stats.get(key) is None
    row = tabellen_zeile(SimpleNamespace(id=1, true_max_drawdown_pct=4), stats, fix_ids=set())
    assert row['Trades'] is None and row['PF'] is None and row['True-DD %'] is None
    assert 'Archivaggregate' in row['Messstatus']


@pytest.mark.parametrize('index,value', [
    (0, '2025.10.02 00:00:00'), (7, '2025.10.31 23:59:58'),
    (7, '2025.09.30 23:59:59'), (7, 'bad'), (2, '0'), (2, '-1'),
    (2, 'NaN'), (4, '1.0'), (8, '1.1'), (5, '0'), (6, '0'),
    (11, 'NaN'), (11, ''), (9, 'inf'), (10, 'NaN'), (12, 'unknown'),
    (3, 'unmarked_archive'),
])
def test_enge_archivform_verlangt_saubere_zeiten_geldwerte_und_markierung(tmp_path, index, value):
    row = ARCHIVE.split(';')
    row[index] = value
    path = _csv(tmp_path, [';'.join(row), TRADE])
    with pytest.raises(ValueError):
        parser.load_export(path, nur_finanzdaten=True)
    assert not signal_statistik.berechne(path, {}).get('teilstatistik_finanzdaten')


def test_ueberlappende_einzelabschluesse_blockieren_moegliche_doppelzaehlung(tmp_path):
    path = _csv(tmp_path, [ARCHIVE, TRADE.replace('2025.11.', '2025.10.')])
    with pytest.raises(ValueError, match='Doppelzaehlung'):
        parser.load_export(path, nur_finanzdaten=True)


def test_mehrere_originalaggregate_gleicher_monat_bleiben_alle_erhalten(tmp_path):
    path = _csv(tmp_path, [ARCHIVE, ARCHIVE, TRADE, TRADE])
    parsed = parser.load_export(path, plattform_positions=1, nur_finanzdaten=True)
    assert len(parsed.trades) == 2 and len(parsed.archived_pnl_aggregates) == 2
    assert parsed.duplikate_entfernt == 0
    stats = signal_statistik.berechne(path, {'trades': 1})
    assert stats['netto_gesamt_usd'] == pytest.approx(2 * (26.78 + 12.64))


def test_alle_bekannten_original_archivzeilen_finanziell_vollstaendig():
    root = Path(__file__).resolve().parents[1]
    path = root / 'data/quellen/mql5/mql4_2336904_trades.csv'
    if not path.is_file():
        pytest.skip('Optionaler lokaler Originalexport')
    parsed = parser.load_export(str(path), nur_finanzdaten=True)
    assert len(parsed.archived_pnl_aggregates) == 5
    archived = math.fsum(a.net for a in parsed.archived_pnl_aggregates)
    assert archived == pytest.approx(347.03)
    stats = signal_statistik.berechne(str(path), {})
    assert stats['netto_gesamt_usd'] == pytest.approx(parsed.net_total + archived)
    assert stats['trades'] is None and stats['profit_faktor'] is None
