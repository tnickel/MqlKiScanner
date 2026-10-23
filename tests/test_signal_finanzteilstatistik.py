"""Finanzsummen trotz belegter negativer Dauer, ohne Zeit-/Equity-Freigabe."""
from types import SimpleNamespace
import hashlib
import json
import pytest
from mqlkiscanner import db, ingest, katalog, parser, signal_statistik
from mqlkiscanner.alle_signale_ui import tabellen_zeile

HEADER = 'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'


def csv(tmp_path, inverted=False):
    path = tmp_path / ('inverted.csv' if inverted else 'normal.csv')
    rows = []
    for day, profit, commission in [(5,100,-1),(6,-30,0),(7,0,-2),(8,20,-3)]:
        close = '09:59:59' if inverted and day == 5 else '10:05:00'
        rows.append(f'2026.01.{day:02} 10:00:00;Buy;0.1;EURUSD;1.1;0.1;'
                    f'2026.01.{day:02} {close};1.11;{commission};0;{profit}')
    path.write_text(HEADER + '\n'.join(rows) + '\n')
    return str(path)


def test_zeitinversion_behaelt_alle_finanzwerte_default_parser_strikt(tmp_path):
    good, bad = csv(tmp_path), csv(tmp_path, True)
    with pytest.raises(ValueError):
        parser.load_export(bad)
    parsed = parser.load_export(bad, nur_finanzdaten=True)
    assert parsed.trades[0].close_time < parsed.trades[0].open_time
    assert len(parsed.trades) == 4 and sum(t.net for t in parsed.trades) == 84
    normal = signal_statistik.berechne(good, {'initial_deposit_usd':1000})
    partial = signal_statistik.berechne(bad, {'initial_deposit_usd':1000})
    for key in ('trades','wins','losses','winrate_pct','profit_faktor','netto_gesamt_usd'):
        assert partial[key] == normal[key]
    assert partial['winrate_pct'] == 50 and partial['profit_faktor'] == 4
    assert partial['teilstatistik_finanzdaten'] and partial['negative_zeitintervalle'] == 1
    for key in ('ertrag_monat_geom_pct','cagr_jahr_pct','trading_dd_pct',
                'trading_dd_usd','kurve','dauer_statistik','monate_pct'):
        assert partial.get(key) is None
    res = SimpleNamespace(id=1, true_max_drawdown_pct=15, true_retdd_monat=2,
                              true_retdd_jahr=30, true_dd_usd=150)
    row = tabellen_zeile(res, partial, fix_ids=set())
    assert row['PF'] == 4 and row['Trades'] == 4
    assert 'Teilstatistik' in row['Messstatus']
    for col in ('True-DD %','True-DD ≈','True-DD USD','TrueRetDD','RetDD/Monat','Geom. %/M'):
        assert row[col] is None


@pytest.mark.parametrize('field,value', [(2,'0'),(2,'-0.1'),(2,'NaN'),
    (4,'NaN'),(8,'NaN'),(10,'NaN'),(6,'bad timestamp')])
def test_finanzlesemodus_blockiert_defekte_geldwerte_volumen_zeiten(tmp_path, field, value):
    path = csv(tmp_path, True)
    rows = open(path).read().splitlines()
    fields = rows[2].split(';'); fields[field] = value
    rows[2] = ';'.join(fields)
    with open(path,'w') as stream:
        stream.write('\n'.join(rows)+'\n')
    with pytest.raises(ValueError):
        parser.load_export(path, nur_finanzdaten=True)
    partial = signal_statistik.berechne(path, {'initial_deposit_usd':1000})
    assert partial['fehler'] and not partial.get('teilstatistik_finanzdaten')
    assert partial.get('profit_faktor') is None


@pytest.mark.parametrize('inverted', [False, True])
def test_quellenhistorie_gekappt_als_hinweis_ohne_rechenoder_scoringaenderung(tmp_path, inverted):
    path = csv(tmp_path, inverted)
    plain = signal_statistik.berechne(path, {'initial_deposit_usd':1000})
    hinted = signal_statistik.berechne(path, {'initial_deposit_usd':1000,
        'quelle_trades_gekappt':True, 'quelle_trades_total_available':42000})
    for key in ('trades','profit_faktor','winrate_pct','netto_gesamt_usd',
                'ertrag_monat_geom_pct','trading_dd_pct'):
        assert plain.get(key) == hinted.get(key)
    res = SimpleNamespace(id=1)
    row = tabellen_zeile(res, hinted, fix_ids=set())
    assert 'Historie gekappt' in row['Messstatus']
    assert '42000 Trades insgesamt verfügbar' in row['Messstatus']
    assert 'gelieferten Export' in row['Messstatus']
    hinted['quelle_trades_gekappt'] = 'false'
    assert 'Historie gekappt' not in tabellen_zeile(res, hinted, fix_ids=set())['Messstatus']


def test_katalog_sha_metrics_bis_tabellenhistorienhinweis(tmp_path):
    qid=db.add_quelle('vant','Vantage','http://localhost:8092')
    db.katalog_upsert_many('vant',[dict(signal_id=43,version='vantage',platform='vantage')])
    path=csv(tmp_path)
    payload={'signalId':43,'version':'vantage','metrics':{
        'InitialDepositVirtual':10000,'TradesTruncated':True,
        'TradesTotalAvailable':42000,'TradesStored':2000,
        'CompletenessNote':'Gespeicherte Historie ist gekappt'}}
    metrics=tmp_path/'metrics.json'; metrics.write_text(json.dumps(payload))
    from pathlib import Path
    for art,pfad in [('trades',Path(path)),('metrics',metrics)]:
        db.store_quellen_artefakt(qid,43,'vantage',art,
                                  hashlib.sha256(pfad.read_bytes()).hexdigest(),str(pfad))
    results,stats=katalog.katalog_resultate(gescannt=set(),studien={})
    computed=signal_statistik.berechne(results[0].trades_path,stats[("vant",43)])
    row=tabellen_zeile(results[0],computed,fix_ids=set())
    assert 'Historie gekappt' in row['Messstatus']
    assert '2000.0 Trades gespeichert, 42000 insgesamt verfügbar' in row['Messstatus']
    assert 'Gespeicherte Historie ist gekappt' in row['Messstatus']
    assert row['PF']==4 and row['Trades']==4


def test_completeness_note_ohne_truncated_flag_bleibt_sichtbar():
    stats=ingest.metrics_zu_stats({'metrics':{'TradesTruncated':False,
        'TradesStored':250,'CompletenessNote':'Nur verifizierte Downloads'}})
    row=tabellen_zeile(SimpleNamespace(id=1),stats,fix_ids=set())
    assert 'Historie gekappt' not in row['Messstatus']
    assert 'Nur verifizierte Downloads' in row['Messstatus']

@pytest.mark.parametrize('reason',['Keine Trades im Export','ungueltiges Volumen oder Handelszeitraum'])
def test_strict_statistics_failure_is_visible_in_table(reason):
    row=tabellen_zeile(SimpleNamespace(id=1),{'fehler':reason,'trades':0},fix_ids=set())
    assert reason in row['Messstatus']
    assert row['True-DD %'] is None
