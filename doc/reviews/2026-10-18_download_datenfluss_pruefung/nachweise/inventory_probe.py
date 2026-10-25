"""Read-only production inventory; SQLite backups remain outside the repository."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def connect_ro(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', timeout=15, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def rows(connection, query, args=()):
    return [dict(row) for row in connection.execute(query, args)]


def decode(value):
    try:
        return json.loads(value or '{}')
    except (TypeError, ValueError):
        return {}


def main():
    temp = Path(tempfile.mkdtemp(prefix='signalkiscanner_download_audit_'))
    result = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'snapshot_root': str(temp)}
    for name in ('mqlkiscanner.db', 'kursdaten.db'):
        original = ROOT / 'data' / name
        with connect_ro(original) as source, sqlite3.connect(temp / name) as target:
            source.backup(target)
        with connect_ro(temp / name) as connection:
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            result[name] = {
                'quick_check': [row[0] for row in connection.execute('PRAGMA quick_check')],
                'foreign_key_check_count': len(connection.execute('PRAGMA foreign_key_check').fetchall()),
                'counts': {table: connection.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] for table in tables},
                'columns': {table: [row[1] for row in connection.execute('PRAGMA table_info("' + table + '")')] for table in tables},
            }
    with connect_ro(temp / 'mqlkiscanner.db') as connection:
        main_db = result['mqlkiscanner.db']
        sources = rows(connection, 'SELECT id, kuerzel, name, base_url, typ, aktiv FROM datenquellen ORDER BY id')
        for source in sources:
            parsed = urlsplit(source['base_url'])
            source['base_url'] = f'{parsed.scheme}://{parsed.hostname}' + (f':{parsed.port}' if parsed.port else '') + parsed.path
        main_db['sources'] = sources
        main_db['signals_by_source'] = rows(connection, 'SELECT quelle, count(*) AS count, min(updated_at) AS oldest_update, max(updated_at) AS newest_update FROM signals GROUP BY quelle')
        main_db['catalog_by_source'] = rows(connection, 'SELECT quelle, count(*) AS count, min(updated_at) AS oldest_update, max(updated_at) AS newest_update FROM katalog_signale GROUP BY quelle')
        main_db['artifacts_by_source'] = rows(connection, 'SELECT quelle_id, art, count(*) AS count, min(fetched_at) AS oldest_fetch, max(fetched_at) AS newest_fetch FROM quellen_artefakte GROUP BY quelle_id, art')
        main_db['catalog_sync'] = rows(connection, 'SELECT quelle, gelaufen_am, anzahl, CASE WHEN coalesce(fehler, \'\') = \'\' THEN 0 ELSE 1 END AS has_error FROM katalog_sync')
        main_db['recent_client_updates'] = rows(connection, 'SELECT id, ts, quelle_id, kuerzel, job_id, status, dauer_s, signale_geliefert, tradelisten_neu, tradelisten_aktualisiert, datenstand, CASE WHEN coalesce(fehler, \'\') = \'\' THEN 0 ELSE 1 END AS has_error FROM client_updates ORDER BY id DESC LIMIT 30')
        main_db['cross_source_catalog_ids'] = rows(connection, 'SELECT signal_id, count(DISTINCT quelle) AS sources FROM katalog_signale GROUP BY signal_id HAVING count(DISTINCT quelle)>1')
        main_db['orphan_counts'] = {table: connection.execute(f'SELECT count(*) FROM {table} a LEFT JOIN signals s ON a.signal_id=s.signal_id WHERE s.signal_id IS NULL').fetchone()[0] for table in ('forensik', 'trade_files')}
        main_db['signal_stats_keys'] = dict(Counter(key for row in connection.execute('SELECT stats_json FROM signals') for key in decode(row[0])))
        main_db['forensic_keys'] = dict(Counter(key for row in connection.execute('SELECT json FROM forensik') for key in decode(row[0])))
        integrity = []
        for table, query in (
            ('trade_files', 'SELECT signal_id, path, sha256 FROM trade_files'),
            ('quellen_artefakte', 'SELECT quelle_id, signal_id, version, art, path, sha256 FROM quellen_artefakte'),
        ):
            counts = Counter()
            errors = []
            for row in rows(connection, query):
                path = Path(row.pop('path') or '')
                expected = row.pop('sha256')
                counts['total'] += 1
                try:
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    counts['missing_or_unreadable'] += 1
                    errors.append({**row, 'status': 'missing_or_unreadable'})
                else:
                    status = 'hash_ok' if expected == actual else 'hash_mismatch'
                    counts[status] += 1
                    if status != 'hash_ok':
                        errors.append({**row, 'status': status})
            integrity.append({'table': table, 'counts': dict(counts), 'errors': errors})
        main_db['artifact_integrity'] = integrity
    with connect_ro(temp / 'kursdaten.db') as connection:
        result['kursdaten.db']['feed_inventory'] = rows(connection, 'SELECT feed, count(DISTINCT symbol) AS symbols, count(*) AS bars, min(epoch) AS first_epoch, max(epoch) AS last_epoch, sum(CASE WHEN abgeschlossen=0 THEN 1 ELSE 0 END) AS preliminary_bars FROM h1_bars GROUP BY feed')
        result['kursdaten.db']['invalid_bar_counts'] = rows(connection, 'SELECT sum(CASE WHEN epoch % 3600 != 0 THEN 1 ELSE 0 END) AS unaligned, sum(CASE WHEN high < low OR high < open OR high < close OR low > open OR low > close THEN 1 ELSE 0 END) AS invalid_ohlc FROM h1_bars')
    (OUT / 'inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'snapshot_root': str(temp),
        'counts': {name: result[name]['counts'] for name in ('mqlkiscanner.db', 'kursdaten.db')},
        'sources': result['mqlkiscanner.db']['sources'],
        'signals_by_source': result['mqlkiscanner.db']['signals_by_source'],
        'catalog_by_source': result['mqlkiscanner.db']['catalog_by_source'],
        'artifact_integrity': result['mqlkiscanner.db']['artifact_integrity'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
