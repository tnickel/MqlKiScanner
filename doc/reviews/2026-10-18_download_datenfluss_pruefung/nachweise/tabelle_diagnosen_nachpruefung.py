"""Narrow classification of diagnosed CSVs and date-profile verification.

Reads original artifacts only; uses a private copy of the provided SQLite
snapshot for DB APIs. No broad test suite or full statistics rerun.
"""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from tabelle_bestandsaudit import ROOT, OUT, profile


def main():
    snapshot = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix='signal_table_diagnoses_') as temp:
        temp = Path(temp)
        source = sqlite3.connect(snapshot.resolve().as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(temp / 'audit.db')
        source.backup(target)
        source.close()
        target.close()
        from mqlkiscanner import config, db
        settings = config.load_settings()
        db.DB_PATH = temp / 'audit.db'
        for name in ('DATA_DIR', 'RUNS_DIR', 'REPORTS_DIR', 'TRADES_DIR', 'STATS_DIR',
                     'CONFIG_DIR', 'PROMPTS_DIR', 'DOWNLOADER_DIR', 'FX_RATES_DIR'):
            path = temp / name.lower()
            path.mkdir()
            setattr(config, name, path)
        config.SETTINGS_FILE = config.CONFIG_DIR / 'app_settings.json'
        config.SETTINGS_FILE.write_text(json.dumps(settings), encoding='utf-8')
        import requests
        def no_network(*args, **kwargs):
            raise AssertionError('No network during narrow table diagnosis')
        requests.sessions.Session.request = no_network
        from mqlkiscanner import pipeline, katalog, app_ui, signal_statistik
        from mqlkiscanner.alle_signale_ui import usd_statistik_fehler
        from mqlkiscanner.parser import load_export
        stored = db.list_catalog()
        studies = db.list_equity_studien()
        catalog = db.katalog_list()
        sources = db.list_quellen()
        artifacts = db.list_quellen_artefakte()
        workflow = [r for r in pipeline.results_from_db(catalog_rows=stored, studien=studies,
            settings=settings, materialize_pdfs=False) if r.source_kind == 'live']
        dates = profile(app_ui.results_to_dataframe(workflow, fresh_ids=set(), fix_ids=set()).to_dict('records'))['Bericht vom']
        catalog_results, catalog_stats = katalog.katalog_resultate(
            gescannt={int(r['signal_id']) for r in stored}, studien=studies,
            katalog_rows=catalog, quellen_rows=sources, artefakte=artifacts)
        statistics = katalog.workflow_stats_bulk(workflow,
            {r['signal_id']: r.get('stats') or {} for r in stored},
            katalog_rows=catalog, quellen_rows=sources, artefakte=artifacts)
        statistics.update(catalog_stats)
        diagnoses = []
        parsed_count = 0
        for row in workflow + catalog_results:
            if usd_statistik_fehler(row) or not row.trades_path or not Path(row.trades_path).exists():
                continue
            parsed_count += 1
            try:
                parsed = load_export(row.trades_path,
                    plattform_positions=statistics.get(row.id, {}).get('trades'))
                if not parsed.trades:
                    diagnoses.append({'quelle': row.quelle, 'id': row.id,
                        'diagnosis': 'keine Trades im lesbaren Export', 'display_trades': 0})
            except Exception:
                stat = signal_statistik.berechne(row.trades_path, statistics.get(row.id, {}))
                category = ('Original-Archivaggregate; nur finanzielle Teilstatistik'
                            if stat.get('archivaggregate_anzahl') else
                            'Negative Open/Close-Zeitintervalle; nur finanzielle Teilstatistik'
                            if stat.get('negative_zeitintervalle') else
                            'nicht klassifizierter Statistikfehler')
                diagnoses.append({'quelle': row.quelle, 'id': row.id,
                    'diagnosis': category, 'financial_only_partial': bool(stat.get('teilstatistik_finanzdaten')),
                    'display_trades': stat.get('trades')})
        report = json.loads((OUT / 'tabelle_bestand.json').read_text(encoding='utf-8'))
        assert len(diagnoses) == report['cache']['statistics_with_error']
        report['result_column_profile']['Bericht vom'] = dates
        report['date_profile_recheck'] = 'NaT interpreted as null; narrow remap of all 194 result rows'
        report['blank_value_reasons']['report_date'] = 'Only latest Gesamtbericht bound to current verified report_basis; stale/incomplete forensics clear current reports and timestamp while SQLite history remains'
        report['workflow_not_in_current_local_catalog'] = len({r.id for r in workflow} - {int(r['signal_id']) for r in catalog})
        report['statistics_diagnosis_categories'] = dict(Counter(r['diagnosis'] for r in diagnoses))
        (OUT / 'tabelle_bestand.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        result = {'rows_parsed_without_statistics_rerun': parsed_count,
                  'statistics_recomputed_only_for_parser_diagnoses': sum(bool(r.get('financial_only_partial')) for r in diagnoses),
                  'categories': report['statistics_diagnosis_categories'], 'diagnoses': diagnoses,
                  'result_report_date_profile': dates,
                  'workflow_not_in_current_local_catalog': report['workflow_not_in_current_local_catalog']}
        (OUT / 'tabelle_statistik_diagnosen.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'diagnoses'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
