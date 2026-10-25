"""Quantitative local REST selection audit; writes only into temporary storage."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from mqlkiscanner import config, db, downloader_client, fix_signale, ingest, pipeline
    inventory = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    snapshot = Path(inventory['snapshot_root']) / 'mqlkiscanner.db'
    scratch = Path(tempfile.mkdtemp(prefix='signalkiscanner_flow_'))
    with sqlite3.connect(snapshot) as source, sqlite3.connect(scratch / 'scanner.db') as target:
        source.backup(target)
    settings = config.load_settings()
    db.DB_PATH = scratch / 'scanner.db'
    config.DATA_DIR = scratch
    config.RUNS_DIR = scratch / 'runs'
    config.REPORTS_DIR = scratch / 'reports'
    output = {'observed_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'live REST inputs only; no direct MQL website crawl or new scan',
              'sources': {}, 'settings': {key: settings.get(key) for key in (
                  'listen_modus', 'top_n_export', 'min_abonnenten', 'min_wochen', 'fix_signal_ids')}}
    all_candidates = []
    seen = set()
    for source in inventory['mqlkiscanner.db']['sources']:
        if not source['aktiv']:
            continue
        client = downloader_client.DownloaderClient(source['base_url'])
        items = ingest.hole_katalog(source, client=client)
        candidates = ingest.kandidaten(source, items)
        deduplicated = []
        for candidate in candidates:
            identity = (candidate['id'], candidate['platform'])
            if identity not in seen:
                seen.add(identity)
                deduplicated.append(candidate)
        all_candidates.extend(deduplicated)
        with sqlite3.connect(snapshot) as connection:
            stored = {(str(sid), str(version)) for sid, version in connection.execute(
                'SELECT signal_id, version FROM katalog_signale WHERE quelle=?', (source['kuerzel'],))}
        identities = {(str(item.get('signalId')), str(item.get('version'))) for item in items}
        output['sources'][source['kuerzel']] = {
            'api_items': len(items), 'normalized_candidates': len(candidates),
            'after_cross_source_deduplication': len(deduplicated),
            'unknown_age': sum(candidate['wochen'] is None for candidate in candidates),
            'unknown_subscribers': sum(candidate['abonnenten'] is None for candidate in candidates),
            'new_api_identities_since_stored_catalog': sorted(identities - stored),
            'stored_identities_absent_from_api': sorted(stored - identities),
        }
    all_candidates.sort(key=lambda candidate: (-(candidate.get('abonnenten') or 0), candidate['id']))
    scanner = object.__new__(pipeline.ScanPipeline)
    scanner.settings = settings
    reasons, logs = [], []
    filtered = scanner.build_candidates(all_candidates, logs.append, begruendung=reasons)
    chosen, slots = fix_signale.waehle_fuer_export(filtered, settings['top_n_export'], settings, begruendung=reasons)
    output['rest_selection'] = {'unique_candidates': len(all_candidates), 'after_filters': len(filtered),
                              'chosen': len(chosen), 'slots': slots,
                              'configured_fix_ids_absent_from_rest': sorted(set(settings['fix_signal_ids']) - {c['id'] for c in all_candidates})}
    for source, summary in output['sources'].items():
        own = [reason for reason in reasons if reason.get('quelle') == source]
        summary['selection_status_counts'] = dict(Counter(reason.get('status') for reason in own))
        summary['selected_signal_ids'] = sorted(candidate['id'] for candidate in chosen if candidate.get('quelle_kuerzel') == source)
        summary['filter_reason_counts'] = dict(Counter(
            'unknown_age' if 'Alter unbekannt' in reason.get('grund', '') else
            'age_below_minimum' if 'Alter:' in reason.get('grund', '') else
            'subscribers_below_minimum' if 'Abonnenten:' in reason.get('grund', '') else
            reason.get('status') for reason in own))
    output['selection_reasons'] = [{key: reason.get(key) for key in ('quelle', 'id', 'status', 'grund')} for reason in reasons]
    with sqlite3.connect(snapshot) as connection:
        existing = {key: {row[0] for row in connection.execute(
            'SELECT signal_id FROM signals WHERE quelle=?', (key,))} for key in output['sources']}
        trade_ids = {row[0] for row in connection.execute('SELECT signal_id FROM trade_files')}
    output['selection_vs_existing_stock'] = {}
    for key, summary in output['sources'].items():
        selected_ids = set(summary['selected_signal_ids'])
        output['selection_vs_existing_stock'][key] = {
            'selected_existing_signals': len(selected_ids & existing[key]),
            'selected_with_any_trade_snapshot': len(selected_ids & trade_ids),
            'selected_without_signal_record_ids': sorted(selected_ids - existing[key]),
            'stored_signals_outside_current_rest_selection': len(existing[key] - selected_ids),
        }
    history = sorted((ROOT / 'data' / 'runs').glob('*/results.json'), reverse=True)
    if history:
        latest = json.loads(history[0].read_text(encoding='utf-8'))
        results = latest.get('ergebnisse', [])
        output['latest_archived_scan'] = {
            'run': history[0].parent.name, 'timestamp': latest.get('zeitstempel'),
            'results': len(results), 'source_counts': dict(Counter(row.get('quelle') for row in results)),
            'persisted_this_run': sum(bool(row.get('persisted_this_run')) for row in results),
            'forensics_complete': sum(bool(row.get('forensik_vorhanden')) for row in results),
            'errors': sum(bool(row.get('fehler')) for row in results),
        }
    (OUT / 'flow_inventory.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in output.items() if key != 'selection_reasons'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
