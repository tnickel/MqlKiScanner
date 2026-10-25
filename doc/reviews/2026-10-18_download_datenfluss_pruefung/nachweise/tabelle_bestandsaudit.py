"""Read-only snapshot audit of both table pipelines; emits aggregates only.

Usage: python <this script> --snapshot <consistent SQLite snapshot>
Productive DB APIs are used only after DB_PATH and writable dirs are redirected
to another temporary backup. Original artifact paths are read, never written.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from copy import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))


def atom(value):
    if type(value).__name__ == 'NaTType':
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def same(left, right):
    if left is None and right is None:
        return True
    if isinstance(left, (float, int)) and isinstance(right, (float, int)):
        return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10)
    return left == right


def profile(rows):
    out = {}
    keys = list(rows[0]) if rows else []
    for key in keys:
        values = [atom(r.get(key)) for r in rows]
        out[key] = {
            'rows': len(values),
            'null': sum(v is None for v in values),
            'empty_text': sum(isinstance(v, str) and not v for v in values),
            'zero_numeric': sum(isinstance(v, (int, float)) and v == 0 for v in values),
            'nonempty': sum(v is not None and v != '' for v in values),
        }
    return out


def mappings():
    entries = {}
    for filename, function, variable in [
        ('src/mqlkiscanner/pipeline.py', 'to_row', None),
        ('src/mqlkiscanner/alle_signale_ui.py', 'tabellen_zeile', 'zeile'),
    ]:
        tree = ast.parse((ROOT / filename).read_text(encoding='utf-8-sig'))
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
        if variable:
            d = next(n.value for n in func.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets))
        else:
            d = next(n.value for n in func.body if isinstance(n, ast.Return))
        entries[function] = {
            key.value: {'expression': ast.unparse(value), 'file': filename, 'line': value.lineno}
            for key, value in zip(d.keys, d.values)
        }
    entries['result_table_additions'] = {
        'Stand': 'id in session.refreshed_signal_ids; persisted_this_run only for legacy session state',
        'Fix': 'id in fix_signale.fix_ids()',
        'Bericht': 'static PDF action label; selected ScanResult snapshot',
        'Studie': 'static action label; selected ScanResult snapshot',
        'Link': 'quellen.oeffnen_url(result.quelle, result.id, result.url)',
        'Abonnenten': 'downloader_sync.abo_bilanz(...).abonnenten from subscriber_history, preferred platform',
        '30 Tage': 'abo_bilanz(...).tage30 -> _abo_delta_zelle',
        '7 Tage': 'abo_bilanz(...).tage7 -> _abo_delta_zelle',
        'Dokumente': 'nonempty workflow report fields + db.downloader_report_counts; separate deep-analysis count',
    }
    entries['alle_signale_postprocessing'] = {
        'study_display': 'studie_anzeige_dd_pct overrides True-DD; current CSV CAGR/DD for >=3 months; orange if study provisional',
        'usd_or_partial_guard': 'USD proof missing / financial-only partial stats clear Trading-DD, True-DD, geom yield and RetDD cells',
        'formatting': 'pd.to_numeric(errors=coerce), df.round(2), Styler na_rep empty; no threshold decision on rounded values',
    }
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='signal_table_audit_') as temp:
        temp = Path(temp)
        with sqlite3.connect(args.snapshot.resolve().as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(temp / 'audit.db') as target:
                source.backup(target)
        source.close()
        target.close()
        from mqlkiscanner import config, db
        # Capture public product settings before relocating writable paths.
        settings = config.load_settings()
        db.DB_PATH = temp / 'audit.db'
        for name in ('DATA_DIR', 'RUNS_DIR', 'REPORTS_DIR', 'TRADES_DIR', 'STATS_DIR',
                     'CONFIG_DIR', 'PROMPTS_DIR', 'DOWNLOADER_DIR', 'FX_RATES_DIR'):
            p = temp / name.lower()
            p.mkdir()
            setattr(config, name, p)
        config.SETTINGS_FILE = config.CONFIG_DIR / 'app_settings.json'
        config.SETTINGS_FILE.write_text(json.dumps(settings), encoding='utf-8')
        # No credentials or network is needed to build either table.
        import requests
        def no_network(*args, **kwargs):
            raise AssertionError('Network forbidden in snapshot table audit')
        requests.sessions.Session.request = no_network
        from mqlkiscanner import katalog, pipeline, app_ui, signal_statistik
        from mqlkiscanner.alle_signale_ui import tabellen_zeile, usd_statistik_fehler
        from mqlkiscanner.parser import load_export

        stored = db.list_catalog()
        studies = db.list_equity_studien()
        client_catalog = db.katalog_list()
        sources = db.list_quellen()
        artifacts = db.list_quellen_artefakte()
        workflow = pipeline.results_from_db(catalog_rows=stored, studien=studies,
                                           settings=settings, materialize_pdfs=False)
        live_workflow = [r for r in workflow if r.source_kind == 'live']
        errors = []
        checked = Counter()
        stored_by_id = {int(r['signal_id']): r for r in stored}
        direct = {'Name': 'name', 'Platform': 'platform', 'Quelle': 'quelle',
                  'Abo $': 'abo_preis', 'Abos': 'abonnenten', 'Wochen': 'wochen'}
        direct_stats = {'Growth %': 'growth_pct', 'Ertrag/Monat %': 'ertrag_monat_pct',
                        'PF': 'pf', 'Drawdown % (Plattform)': 'eq_dd_pct',
                        'Balance-DD % (Plattform)': 'bal_dd_pct'}
        for res in live_workflow:
            raw = stored_by_id[res.id]
            row = res.to_row()
            for col, key in direct.items():
                expected = raw.get(key)
                if col == 'Name':
                    expected = expected or str(res.id)
                elif col == 'Platform':
                    expected = expected or ''
                elif col == 'Quelle':
                    expected = expected or 'mql5'
                checked['db_to_result_fields'] += 1
                if not same(expected, row[col]):
                    errors.append({'id': res.id, 'column': col, 'stage': 'db_to_results'})
            for col, key in direct_stats.items():
                checked['db_to_result_fields'] += 1
                if not same((raw.get('stats') or {}).get(key), row[col]):
                    errors.append({'id': res.id, 'column': col, 'stage': 'stats_to_results'})
            dd = res.max_drawdown_equity_pct
            allowed = (dd is not None and dd > 0 and res.cagr_jahr_pct is not None
                       and res.effizienz_befund.get('effizienz_status') != 'historie_zu_kurz')
            expected_retdd = res.cagr_jahr_pct / dd if allowed else None
            checked['annual_calmar'] += 1
            if not same(expected_retdd, res.retdd_jahr):
                errors.append({'id': res.id, 'column': 'retdd_jahr', 'stage': 'independent_division'})
        result_rows = app_ui.results_to_dataframe(live_workflow, fresh_ids=set(), fix_ids=set()).to_dict('records')
        fresh_rows = app_ui.results_to_dataframe(live_workflow, fresh_ids={r.id for r in live_workflow},
                                                fix_ids=set()).to_dict('records')
        assert all(r['Stand'] == '' for r in result_rows)
        assert all(r['Stand'] == 'NEU' for r in fresh_rows)

        catalog_results, catalog_stats = katalog.katalog_resultate(
            gescannt=set(stored_by_id), studien=studies, katalog_rows=client_catalog,
            quellen_rows=sources, artefakte=artifacts)
        all_rows = live_workflow + catalog_results
        statistics = katalog.workflow_stats_bulk(
            live_workflow, {r['signal_id']: r.get('stats') or {} for r in stored},
            katalog_rows=client_catalog, quellen_rows=sources, artefakte=artifacts)
        statistics.update(catalog_stats)
        for res in all_rows:
            study = studies.get(res.id) or {}
            if (study.get('virtuell') and study.get('trades_sha') and res.trades_sha256
                    and study['trades_sha'] == res.trades_sha256):
                basis = statistics.setdefault(res.id, {})
                if basis.get('initial_deposit_usd') is None and basis.get('kapitalbasis_virtual_usd') is None:
                    basis['kapitalbasis_virtual_usd'] = 10_000.0

        cache_counts = Counter()
        states = Counter()
        ui_rows = []
        bad_paths = []
        bad_shas = []
        partial_ids = []
        missing_ids = []
        for number, res in enumerate(all_rows, 1):
            if number % 250 == 0:
                print(f'Processed {number}/{len(all_rows)} table rows', flush=True)
            stat = None
            unit_error = usd_statistik_fehler(res)
            p = Path(res.trades_path) if res.trades_path else None
            if not p:
                cache_counts['no_trade_path'] += 1
                missing_ids.append(res.id)
            elif not p.exists():
                cache_counts['registered_path_missing'] += 1
                bad_paths.append(res.id)
            else:
                cache_counts['existing_trade_file'] += 1
                if not res.trades_sha256:
                    cache_counts['missing_registered_sha'] += 1
                elif hashlib.sha256(p.read_bytes()).hexdigest() != res.trades_sha256:
                    cache_counts['sha_mismatch'] += 1
                    bad_shas.append(res.id)
            if unit_error:
                cache_counts['usd_blocked'] += 1
                stat = {'fehler': unit_error, 'waehrung_gesperrt': True}
            elif p and p.exists():
                stat = signal_statistik.berechne(str(p), statistics.get(res.id, {}))
                cache_counts['statistics_computed'] += 1
                if stat and stat.get('teilstatistik_finanzdaten'):
                    partial_ids.append(res.id)
                if stat and stat.get('fehler'):
                    cache_counts['statistics_with_error'] += 1
                if stat and not stat.get('fehler'):
                    # Project winrate uses the Profit field before fees and is
                    # rounded to one decimal by stats.compute (not net > 0).
                    parsed = load_export(str(p), plattform_positions=statistics.get(res.id, {}).get('trades'))
                    positive = sum(t.profit > 0 for t in parsed.trades)
                    expected_win = round(positive / len(parsed.trades) * 100, 1) if parsed.trades else None
                    for column, expected, actual in [
                        ('Trades', len(parsed.trades), stat.get('trades')),
                        ('Win %', expected_win, stat.get('winrate_pct')),
                    ]:
                        checked['parsed_trade_statistics'] += 1
                        if not same(expected, actual):
                            errors.append({'id': res.id, 'column': column, 'stage': 'parsed_statistics'})
            row = tabellen_zeile(res, stat, {}, {}, fix_ids=set())
            ui_rows.append(row)
            states['workflow' if res.herkunft != 'Katalog' else 'catalog'] += 1
            if res.forensik_stale:
                states['stale_forensics'] += 1
            if res.forensik_vorhanden:
                states['complete_forensics'] += 1
            if getattr(res, 'true_dd_basis_virtuell', False):
                states['virtual_equity_basis'] += 1
            if getattr(res, 'studie_anzeige_dd_pct', None) is not None:
                states['independent_study_display'] += 1
            if row.get('TrueRetDD ≈') is not None:
                states['provisional_calmar'] += 1
            if stat is None:
                states['no_statistics'] += 1
            elif not stat.get('kapitalbasis_ok'):
                states['statistics_without_positive_capital_basis'] += 1
            if unit_error:
                for c in ('Trading-DD %', 'True-DD %', 'True-DD ≈', 'True-DD USD',
                          'Geom. %/M', 'TrueRetDD', 'TrueRetDD ≈', 'RetDD/Monat'):
                    if row[c] is not None:
                        errors.append({'id': res.id, 'column': c, 'stage': 'usd_guard'})

        ids = Counter(int(z['signal_id']) for z in client_catalog)
        collisions = [{'id': sid, 'sources': sorted({z['quelle'] for z in client_catalog if z['signal_id'] == sid})}
                      for sid, count in ids.items() if count > 1]
        current_source_counts = Counter(r.quelle for r in all_rows)
        report = {
            'snapshot_utc': '2026-10-18; consistent input snapshot, own temporary writable copy',
            'network': 'blocked', 'product_changes': False,
            'counts': {'db_signals': len(stored), 'results_live': len(live_workflow),
                       'source_catalog_rows': len(client_catalog), 'source_catalog_unique_ids': len(ids),
                       'additional_catalog_rows': len(catalog_results), 'all_signals_rows': len(all_rows)},
            'sources_in_all_signals': dict(current_source_counts),
            'checks': dict(checked), 'mismatches': errors,
            'cache': dict(cache_counts), 'states': dict(states),
            'missing_registered_files_ids': bad_paths, 'sha_mismatch_ids': bad_shas,
            'financial_only_partial_statistics_ids': partial_ids,
            'no_trade_path_ids': missing_ids,
            'cross_source_catalog_id_collisions': collisions,
            'result_column_profile': profile(result_rows), 'all_signals_column_profile': profile(ui_rows),
            'blank_value_reasons': {
                'no_trade_path': 'Unloaded catalogue rows or failed/missing export: no own trade statistics',
                'usd_blocked': 'Native MQL currency missing/non-USD: own USD values intentionally blank',
                'stale_forensics': 'Version, SHA or last failed run invalidates workflow equity/return/score',
                'no_positive_equity': 'No reliable positive H1 denominator: Calmar blank',
                'virtual_equity': 'Separate virtual 10000 USD basis/study display; does not grant workflow green',
                'report_date': 'Only latest Gesamtbericht bound to current verified report_basis; stale/incomplete forensics clear current reports and timestamp while SQLite history remains',
                'subscriber_history': 'Separate local mirrored history, absent/short history means blank',
            },
            'elapsed_seconds': round(time.monotonic() - started, 3),
        }
        (OUT / 'tabelle_bestand.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (OUT / 'tabelle_spaltenmapping.json').write_text(json.dumps(mappings(), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('counts', 'sources_in_all_signals', 'checks', 'cache', 'states', 'elapsed_seconds')}, ensure_ascii=False))
        print(f'Mapping mismatches: {len(errors)}; evidence written to tabelle_bestand.json', flush=True)
        if errors:
            print(json.dumps(errors[:30], ensure_ascii=False))


if __name__ == '__main__':
    main()
