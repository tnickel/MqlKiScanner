"""Reproduce partial HTTP-200 catalogue acceptance against temporary SQLite only."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from mqlkiscanner import config, db, ingest, katalog, quellen
    scratch = Path(tempfile.mkdtemp(prefix='signalkiscanner_pagination_repro_'))
    config.DATA_DIR = scratch
    config.SETTINGS_FILE = scratch / 'settings.json'
    db.DB_PATH = scratch / 'test.db'
    db.init_db()
    source_id = db.add_quelle('audit', 'synthetic audit', 'http://127.0.0.1:1')
    db.katalog_upsert_many('audit', [
        {'signal_id': signal_id, 'name': str(signal_id), 'version': 'mql5', 'platform': 'mt5'}
        for signal_id in (1, 2, 3)])

    class PartialClient:
        def __init__(self):
            self.calls = []

        def katalog(self, *, limit, offset):
            self.calls.append({'limit': limit, 'offset': offset})
            block = [{'signalId': value, 'version': 'mql5'} for value in (1, 2)] if offset == 0 else []
            return {'items': block, 'total': 3, 'offset': offset}

    client = PartialClient()
    with patch.object(quellen, 'client_fuer_quelle', return_value=client):
        summary = katalog.sync(kuerzel='audit')
    remaining = [row['signal_id'] for row in db.katalog_list()]
    assert summary['quellen']['audit']['fehler'] is None
    assert summary['quellen']['audit']['geloescht'] == 1
    assert remaining == [1, 2]
    capped = PartialClient()
    returned_at_cap = ingest.hole_katalog({'id': source_id}, client=capped, max_seiten=1)
    result = {
        'scope': 'synthetic isolated temporary SQLite; no production requests or writes',
        'server_reported_total': 3, 'original_catalog_signal_ids': [1, 2, 3],
        'http_200_pages': client.calls,
        'sync_summary': summary, 'remaining_signal_ids': remaining,
        'confirmed_defect': 'Premature empty page despite remaining total is accepted as complete; catalogue replacement deletes ID 3 and records success.',
        'page_cap_probe': {'max_pages': 1, 'reported_total': 3, 'returned_items': len(returned_at_cap), 'exception': None},
    }
    (OUT / 'pagination_repro.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
