"""Regression oracles for cross-source identity, status, budgets and reports."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import config, db, ingest, client_updates, downloader_sync, pipeline
from mqlkiscanner.agenten import budget, journal, dirigent
from mqlkiscanner.llm.client import GlmClient, LlmBudgetError
from mqlkiscanner.llm.verdict_check import parse_and_validate_portfolio


def response(tokens, finish='stop', content='synthetic'):
    r = requests.Response()
    r.status_code = 200
    r._content = json.dumps({'choices':[{'message':{'content':content},'finish_reason':finish}],
                             'usage':{'total_tokens':tokens}}).encode()
    return r


def test_broker_bound_to_source_not_mt4_version():
    data = {'version':'mql4','metrics':{}}
    assert ingest.metrics_zu_stats(data, 'mql5')['broker_server'] is None
    assert ingest.metrics_zu_stats(data, 'robo')['broker_server'] == 'roboforex'
    data['metrics']['Broker'] = 'ActualBroker'
    assert ingest.metrics_zu_stats(data, 'robo')['broker_server'] == 'ActualBroker'


def test_job_id_mismatch_is_not_success(monkeypatch):
    fake = SimpleNamespace(health=lambda:{'status':'ok'},
        update_starten=lambda **kw:{'jobId':'expected'},
        update_status=lambda:{'jobId':'other','state':'done'})
    monkeypatch.setattr(client_updates.quellen,'client_fuer_quelle',lambda *a,**k:fake)
    monkeypatch.setattr(client_updates,'_persistiere',lambda z:None)
    result = client_updates._update_eine_quelle(
        {'id':1,'kuerzel':'test','base_url':'http://unused'}, settings={},log=None,
        on_fortschritt=None,gestopft=lambda:False,bereit_warten_s=0,poll_s=0,
        backoff_s=0,timeout_s=1,login_timeout_s=0)
    assert result['status'] == client_updates.FEHLER
    assert 'anderem' in result['fehler']


def test_monthly_limit_stops_dirigent_before_model(monkeypatch):
    client = Mock(has_key=True)
    monkeypatch.setattr(dirigent.llm_client,'GlmClient',Mock(return_value=client))
    monkeypatch.setattr(dirigent.journal,'schritt_protokollieren',Mock())
    lage={'tagesbudget_tokens':500000,'tokens_heute':0,
          'monatsbudget_tokens':5000000,'tokens_monat':5000000}
    assert dirigent._llm_entscheidung(lage,{},1,lambda s:None) is None
    client.chat.assert_not_called()


def test_global_budget_serializes_independent_clients():
    settings={'agenten_tagesbudget_tokens':2500,'agenten_monatsbudget_tokens':10000}
    def reserve():
        try:
            return budget.reserve(settings,1500,'synthetic','prompt')
        except LlmBudgetError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:reserve(),range(2)))
    assert len([r for r in results if r]) == 1
    ticket=next(r for r in results if r)
    budget.settle(ticket,100,'response','ok')
    assert budget.reserve(settings,1500,'synthetic','prompt')
    assert journal.tokens_heute() == journal.tokens_monat() == 100


def test_all_retry_responses_and_costs_are_recorded(monkeypatch):
    monkeypatch.setattr('mqlkiscanner.secrets_store.get_secret',lambda _: 'synthetic-key')
    monkeypatch.setattr('mqlkiscanner.llm.client.time.sleep',lambda _:None)
    post=Mock(side_effect=[response(50,'length','first truncated answer'),response(100)])
    monkeypatch.setattr('mqlkiscanner.llm.client.requests.post',post)
    journal.init_journal()
    run=journal.lauf_starten('dirigent')
    client=budget.attach(GlmClient('x','x',max_total_tokens=20000),{},run,'dirigent')
    assert client.chat('prompt',max_tokens=10) == 'synthetic'
    assert post.call_count == 2
    assert journal.tokens_heute() == journal.tokens_monat() == 150
    with db._connect() as conn:
        rows=conn.execute('SELECT tokens,antwort FROM agenten_budget_versuche ORDER BY rowid').fetchall()
    assert [r['tokens'] for r in rows] == [50,100]
    assert 'first truncated answer' in rows[0]['antwort']
    assert len([r for r in journal.list_schritte() if r['schritt']=='llm_http_versuch']) == 2


def test_shared_monthly_limit_rejects_before_http(monkeypatch):
    monkeypatch.setattr('mqlkiscanner.secrets_store.get_secret',lambda _: 'synthetic-key')
    post=Mock(return_value=response(100))
    monkeypatch.setattr('mqlkiscanner.llm.client.requests.post',post)
    client=budget.attach(GlmClient('x','x',max_total_tokens=20000),
                        {'agenten_monatsbudget_tokens':100})
    with pytest.raises(LlmBudgetError):
        client.chat('prompt',max_tokens=10)
    post.assert_not_called()


def test_unknown_and_ambiguous_portfolio_names_are_rejected():
    assert not parse_and_validate_portfolio('- Unknown — 100 % — Kern',{'Known':'🟢'})['valid']
    assert not parse_and_validate_portfolio('- Same — 100 % — Kern',{'Same':'🟢'},
                                          ambiguous_names={'same'})['valid']
    result=parse_and_validate_portfolio('- [pelik:1] Same — 100 % — Kern',{'Same':'🟡'},
        cand_ids={'pelik:1':('Same','🟢'),'zulu:1':('Same','🟡')},ambiguous_names={'same'})
    assert result['valid'] and result['allokationen'][0]['signal_key']=='pelik:1'


def test_invalid_portfolio_is_audit_only(monkeypatch):
    db.init_db()
    pipe=pipeline.ScanPipeline()
    pipe.llm=SimpleNamespace(has_key=True,usage=SimpleNamespace(total_tokens=10),
        chat=lambda *a,**k:'- Invented — 100 % — Kern')
    monkeypatch.setattr(pipeline,'refresh_report_verdict',lambda *a:None)
    monkeypatch.setattr(pipeline,'restore_current_reports',lambda *a:None)
    result=pipeline.ScanResult(id=123,name='Known',ampel='🟢',forensik_vorhanden=True)
    summary=pipe.run_portfolio([result],lambda _:None)
    assert not summary['text'] and not summary['allokationen']
    assert db.get_latest_analysis(None,'portfolio') is None
    assert db.get_latest_analysis(None,'portfolio_ungueltig')['text'].startswith('- Invented')


def test_portfolio_aliases_cannot_weight_the_same_signal_twice():
    text='- Known — 50 % — Kern\n- [pelik:1] Known — 50 % — Satellit'
    result=parse_and_validate_portfolio(text,{'Known':'🟢'},cand_ids={'pelik:1':('Known','🟢')})
    assert not result['valid']
    assert all(a['signal_key']=='pelik:1' for a in result['allokationen'])


@pytest.mark.parametrize('extra', ['- Unknown — +25 % — Extra',
                                  '- Known — -25 % — Extra',
                                  '- Unknown: 25 %', '- Unknown — NaN % — Extra'])
def test_portfolio_cannot_hide_unchecked_or_invalid_weights(extra):
    assert not parse_and_validate_portfolio('- Known — 100 % — Kern\n'+extra,{'Known':'🟢'})['valid']


def test_changed_pdf_same_size_gets_refreshed():
    db.init_db()
    class Client:
        body=b'%PDF-A1'
        modified='2026-01-01'
        def reports(self,*a):
            return [{'name':'report.pdf','sizeBytes':len(self.body),'lastModified':self.modified}]
        def download_report(self,*a): return self.body
    client=Client()
    path=downloader_sync.sync_reports(123,'pelican',client=client)[0]
    client.body=b'%PDF-B2'
    client.modified='2026-10-16'
    assert downloader_sync.sync_reports(123,'pelican',client=client)
    assert Path(path).read_bytes()==client.body


def test_parallel_cache_file_and_db_sha_agree():
    db.init_db()
    source_id=db.add_quelle('test','Test','http://unused')
    source=db.get_quelle(source_id)
    def write(n):
        fake=SimpleNamespace(trades_csv=lambda *a:str(n).encode())
        return ingest.hole_trades(source,123,'pelican',client=fake)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(write,range(12)))
    assert len(results)==12
    row=db.get_quellen_artefakt(source_id,123,'pelican','trades')
    assert row['sha256']==hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()


def test_old_study_is_retained_but_not_reused():
    db.store_equity_studie(123,'sha',{'equity_dd_pct':1,'verlaesslich':True})
    assert db.get_equity_studie(123)
    with db._connect() as conn:
        conn.execute('UPDATE equity_studien SET forensics_version=16')
    assert db.get_equity_studie(123) is None and db.list_equity_studien()=={}
    with db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM equity_studien').fetchone()[0]==1
