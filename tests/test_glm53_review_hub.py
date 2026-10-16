"""Production prompt/REST regressions independently raised by the GLM review."""
import json
import re
import threading
import urllib.request
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline, rest_api
from mqlkiscanner.llm import prompt_fill


@pytest.mark.parametrize('kind', ['risiko', 'gesamt', 'portfolio'])
def test_green_high_score_candidate_has_no_contradicting_prompt_gate(kind):
    result = pipeline.ScanResult(
        id=123, name='Synthetic high score', forensik_vorhanden=True, score=7.2,
        ertrag_monat_geom_pct=6.5, cagr_jahr_pct=112.0,
        martingale_flag=False, equity_dd_rekonstruiert_pct=4.0)
    result.ampel, result.urteil = pipeline.ampel_for(result, {})
    assert result.ampel == '🟢'
    if kind == 'risiko':
        prompt = prompt_fill.build_risk_prompt(result, 'Aktuelle Kriterien')
    elif kind == 'gesamt':
        prompt = prompt_fill.build_gesamtbericht_prompt(result, 'Aktuelle Kriterien', '', '')
    else:
        prompt = prompt_fill.build_portfolio_prompt(
            json.dumps([{'name':result.name,'ampel':result.ampel,'score':result.score}]),
            'Aktuelle Kriterien')
    assert not re.search(r'Risiko.Score\s+unter\s+5\b', prompt)
    assert 'Score' in prompt  # Context remains visible; only the invented gate disappears.


def test_default_rest_signals_does_not_materialize_reports(monkeypatch):
    db.init_db()
    monkeypatch.setattr(db, 'list_catalog', lambda:[{
        'signal_id':123, 'name':'Synthetic', 'stats':{}, 'forensik':{},
        'gesamtbericht':'Existing synthetic report'}])
    pdf = Mock()
    monkeypatch.setattr('mqlkiscanner.pdf_reports.materialize_result_pdfs', pdf)
    # Exercise the real default provider and HTTP route, rather than a fake result list.
    server = rest_api.build_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f'http://127.0.0.1:{server.server_address[1]}/api/v1/signals',timeout=5) as response:
            payload=json.load(response)
        assert payload['count'] == 1
        assert payload['signals'][0]['signalId'] == 123
        pdf.assert_not_called()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
