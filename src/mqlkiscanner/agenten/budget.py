"""Process-wide daily/monthly agent budget, reserved before each HTTP attempt.

SQLite serializes reservations across clients/processes. A transport failure may
already have incurred tokens; its reservation is conservatively charged. Crashed
inflight reservations remain reserved for their day/month rather than being
silently refunded. No API keys or headers are persisted.
"""
from __future__ import annotations

from datetime import datetime
import json
import uuid

from .. import db
from . import journal

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS agenten_budget_versuche (
    id TEXT PRIMARY KEY, tag TEXT NOT NULL, monat TEXT NOT NULL,
    reserviert INTEGER NOT NULL, tokens INTEGER NOT NULL DEFAULT 0,
    abgeschlossen INTEGER NOT NULL DEFAULT 0, modell TEXT,
    prompt TEXT, antwort TEXT, status TEXT
);
'''


def attach(client, settings: dict, lauf_id=None, rolle='agent'):
    """Also works with injected test clients; only real GlmClient uses it."""
    client.agent_budget_settings = dict(settings)
    client.agent_budget_context = (lauf_id, rolle)
    return client


def remaining(settings: dict) -> int:
    return max(0, min(int(settings.get('agenten_tagesbudget_tokens',500_000)) - journal.tokens_heute(),
                      int(settings.get('agenten_monatsbudget_tokens',5_000_000)) - journal.tokens_monat()))


def _init():
    db.init_db()
    journal.init_journal()
    with db._connect() as conn:
        conn.executescript(_SCHEMA)


def _legacy(conn, period: str) -> int:
    # Ledgergebundene Rollen-Schritte sind nur Spiegel. Ihr Abschlusszeitpunkt
    # kann in einer anderen Periode als der kostenpflichtige HTTP-Start liegen.
    return int(conn.execute('SELECT COALESCE(SUM(tokens),0) FROM agenten_schritte '
        'WHERE prompt IS NOT NULL AND ts LIKE ? AND budget_ledger=0',
        (period+'%',)).fetchone()[0])


def reserve(settings: dict, amount: int, model: str, prompt: str) -> str:
    from ..llm.client import LlmBudgetError
    _init()
    now = datetime.now()
    day, month = now.strftime('%Y-%m-%d'), now.strftime('%Y-%m')
    ticket = uuid.uuid4().hex
    with db._connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for column, period, key, default in [
            ('tag', day, 'agenten_tagesbudget_tokens', 500_000),
            ('monat', month, 'agenten_monatsbudget_tokens', 5_000_000),
        ]:
            used = _legacy(conn, period) + conn.execute(
                f'SELECT COALESCE(SUM(CASE WHEN abgeschlossen=1 THEN tokens ELSE reserviert END),0) '
                f'FROM agenten_budget_versuche WHERE {column}=?', (period,)).fetchone()[0]
            limit = max(0, int(settings.get(key, default)))
            if used + amount > limit:
                raise LlmBudgetError(f'Agenten-Budget {period} reicht nicht: '
                                     f'{used} verbraucht/reserviert, {amount} nötig, Limit {limit}.')
        conn.execute('INSERT INTO agenten_budget_versuche '
                     '(id,tag,monat,reserviert,modell,prompt) VALUES(?,?,?,?,?,?)',
                     (ticket,day,month,amount,model,prompt))
    return ticket


def settle(ticket: str, tokens: int, response: str, status: str) -> None:
    with db._connect() as conn:
        conn.execute('UPDATE agenten_budget_versuche SET tokens=?,abgeschlossen=1,antwort=?,status=? '
                     'WHERE id=? AND abgeschlossen=0',
                     (max(0,int(tokens)),response,status,ticket))


def spent(period: str) -> int:
    """Echte Legacykosten plus Ledgerkosten in ihrer HTTP-Startperiode."""
    with db._connect() as conn:
        legacy = _legacy(conn, period)
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                             "AND name='agenten_budget_versuche'").fetchone()
        if not table:
            return legacy
        column = 'tag' if len(period)==10 else 'monat'
        paid = conn.execute(f'SELECT COALESCE(SUM(tokens),0) FROM agenten_budget_versuche '
                            f'WHERE {column}=? AND abgeschlossen=1', (period,)).fetchone()[0]
    return legacy + int(paid)


def post(client, body: dict, headers: dict, meta_out=None):
    import requests
    if meta_out is not None:
        # Auch Fehler-/Transportpfade müssen ihre äußeren Journalzeilen als
        # Spiegel kennzeichnen; Kosten bleiben allein im Versuch-Ledger.
        meta_out['agent_budget_ledger'] = True
    prompt = json.dumps(body['messages'], ensure_ascii=False)
    # One token per UTF-8 byte + message framing, rather than bytes/3.
    bound = int(body['max_tokens']) + len(prompt.encode('utf-8')) + 1024
    ticket = reserve(client.agent_budget_settings, bound, body['model'], prompt)
    try:
        response = requests.post(f'{client.base_url}/chat/completions',
                                 headers=headers, data=json.dumps(body), timeout=client.timeout)
    except requests.RequestException as exc:
        settle(ticket, bound, str(exc), 'transport_kosten_unbekannt')
        raise
    try:
        payload = response.json()
        raw_tokens = (payload.get('usage') or {}).get('total_tokens')
        valid = isinstance(raw_tokens, int) and not isinstance(raw_tokens, bool) and raw_tokens >= 0
    except (ValueError, TypeError, AttributeError):
        valid, raw_tokens = False, None
    tokens = raw_tokens if valid else (0 if 400 <= response.status_code < 500 else bound)
    settle(ticket, tokens, response.text, f'http_{response.status_code}' +
           ('' if valid else '_kosten_unbekannt' if tokens else '_abgewiesen'))
    lauf_id, role = getattr(client, 'agent_budget_context', (None, 'agent'))
    if lauf_id is not None:
        journal.schritt_protokollieren(
            lauf_id, role, 'llm_http_versuch', prompt=prompt, antwort=response.text,
            modell=body['model'], tokens=0,
            budget_ledger=True,
            detail={'budget_ticket':ticket,'abgerechnete_tokens':tokens,
                    'http_status':response.status_code})
    return response
