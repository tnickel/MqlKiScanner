"""Verify audit consistency and write hashes; never opens production runtime data."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
REVIEW = OUT.parent


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def main():
    tables = read('tabelle_bestand.json')
    assert tables['mismatches'] == []
    assert tables['counts']['results_live'] + tables['counts']['additional_catalog_rows'] == tables['counts']['all_signals_rows']
    flow = read('flow_inventory.json')
    assert sum(source['normalized_candidates'] for source in flow['sources'].values()) == flow['rest_selection']['unique_candidates']
    assert sum(len(source['selected_signal_ids']) for source in flow['sources'].values()) == flow['rest_selection']['chosen']
    assert all(sum(source['selection_status_counts'].values()) == source['normalized_candidates'] for source in flow['sources'].values())
    result = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'tests': {}}
    test_ids = set()
    for name in ('persistenz_pytest.xml', 'tabelle_pytest.xml', 'kursdaten_pytest.xml', 'tabelle_audit_tests.xml'):
        root = ET.parse(OUT / name).getroot()
        cases = root.findall('.//testcase')
        failures = sum(len(case.findall('failure')) + len(case.findall('error')) for case in cases)
        skipped = sum(len(case.findall('skipped')) for case in cases)
        assert failures == skipped == 0
        test_ids.update((case.get('classname'), case.get('name')) for case in cases)
        result['tests'][name] = {'passed': len(cases), 'failures': failures, 'skipped': skipped}
    download_log = (OUT / 'downloads_tests.txt').read_text(encoding='utf-8')
    assert 'EXITCODE: 0' in download_log
    count = int(re.search(r'(\d+) passed', download_log)[1])
    result['tests']['downloads_tests.txt'] = {'passed': count, 'failures': 0}
    result['passed_total'] = sum(group['passed'] for group in result['tests'].values())
    result['unique_cases_in_xml_suites'] = len(test_ids)
    result['scanner_commit'] = git(ROOT, 'rev-parse', 'HEAD')
    result['source_projects'] = {name: git(ROOT.parent / name, 'rev-parse', 'HEAD') for name in (
        'MqlDownloader', 'PelicanTrading', 'roboforex', 'vantage', 'zulumonitor')}
    result['tracked_scanner_changes_outside_review'] = git(ROOT, 'diff', '--name-only', 'HEAD', '--', 'src', 'app_pages', 'config', 'streamlit_app.py', 'tests')
    assert not result['tracked_scanner_changes_outside_review']
    result['source_sha256'] = {}
    paths = [*sorted((ROOT / 'src').rglob('*.py')), *sorted((ROOT / 'app_pages').rglob('*.py')),
             ROOT / 'streamlit_app.py', ROOT / 'config' / 'app_settings.json']
    for path in paths:
        result['source_sha256'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result['evidence_sha256'] = {}
    for path in sorted(REVIEW.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.name == 'manifest.json':
            continue
        result['evidence_sha256'][path.relative_to(REVIEW).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result['consistency_checks'] = 'passed'
    (OUT / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed_total', 'tests', 'scanner_commit', 'tracked_scanner_changes_outside_review', 'consistency_checks')}, indent=2))


if __name__ == '__main__':
    main()
