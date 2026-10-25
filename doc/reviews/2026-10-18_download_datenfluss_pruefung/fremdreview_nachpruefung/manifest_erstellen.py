"""Record this follow-up separately; never rewrite the preceding audit manifests."""
from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

REPORT = Path(__file__).resolve().parent
SCANNER = REPORT.parents[3]
WORKSPACE = SCANNER.parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cases(path):
    rows = list(ET.parse(path).getroot().iter('testcase'))
    failed = sum(row.find('failure') is not None for row in rows)
    errors = sum(row.find('error') is not None for row in rows)
    skipped = sum(row.find('skipped') is not None for row in rows)
    return dict(tests=len(rows), passed=len(rows)-failed-errors-skipped,
                failures=failed, errors=errors, skipped=skipped)


def git(project, *args):
    return subprocess.run(['git', '-c', 'core.quotepath=false', '-C',
                           str(WORKSPACE / project), *args], check=True,
                          capture_output=True, text=True).stdout


def source_files(project):
    paths = set(git(project, 'diff', '--name-only', '--diff-filter=ACMRT').splitlines())
    paths.update(git(project, 'ls-files', '--others', '--exclude-standard').splitlines())
    return {name: sha(WORKSPACE / project / name) for name in sorted(paths)
            if name.startswith(('src/', 'app_pages/', 'tests/')) or name == 'AGENTS.md'}


def shard_metadata(index, kind):
    path = REPORT / f'scanner_shard_{index}_{kind}'
    return path if path.exists() else REPORT / f'scanner_shard_{index}.{kind}'


def main():
    original = REPORT / 'FREMDREVIEW_ORIGINAL.md'
    original_sha = sha(original)
    assert original_sha == '113a828075c28f7435d6045f44ded8db83264b2a7a42a9e76632facc9c637a6a'
    previous = REPORT.parent / 'BEHEBUNG.manifest.json'
    baseline_path = REPORT.parent / 'nachweise/manifest.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf8'))
    mismatches = [name for name, expected in baseline['evidence_sha256'].items()
                  if sha(REPORT.parent / name) != expected]
    assert not mismatches, mismatches
    broken = []
    for document in ('README.md', 'mql_README.md', 'kontrakte_README.md', 'identitaet_bewertung.md'):
        for target in re.findall(r'\]\(([^)]+)\)', (REPORT / document).read_text(encoding='utf8')):
            if '://' in target or target.startswith('#') or target == 'manifest.json':
                continue
            path = re.sub(r':\d+$', '', target.strip('<>').split('#')[0])
            candidate = Path(path) if Path(path).is_absolute() else REPORT / path
            if not candidate.exists():
                broken.append([document, target])
    assert not broken, broken
    full = REPORT / 'scanner_full.xml'
    shards = [REPORT / f'scanner_shard_{index}.xml' for index in range(3)]
    shard_results = [cases(path) for path in shards]
    for index, result in enumerate(shard_results):
        assert result['failures'] == result['errors'] == result['skipped'] == 0
        assert shard_metadata(index, 'exit.txt').read_text(encoding='utf8').strip() == '0'
    final_suite = {key: sum(result[key] for result in shard_results)
                   for key in ('tests', 'passed', 'failures', 'errors', 'skipped')}
    def selected_cases(path):
        return Counter((row.get('classname'), row.get('name'))
                       for row in ET.parse(path).getroot().iter('testcase'))
    expected = selected_cases(full)
    actual = sum((selected_cases(path) for path in shards), Counter())
    assert actual == expected and final_suite['passed'] == 2499
    projects = ('SignalKiScanner', 'MqlDownloader', 'vantage')
    sources = {project: source_files(project) for project in projects}
    start = min(shard_metadata(index, 'command.json').stat().st_mtime
                for index in range(3))
    late = [path for path in sources['SignalKiScanner'] if path != 'AGENTS.md'
            and (SCANNER / path).stat().st_mtime > start]
    assert not late, f'Source changed during the complete suite: {late}'
    artifact = json.loads((REPORT / 'mql_artifact.json').read_text(encoding='utf8'))
    assert sha(artifact['path']) == artifact['sha256']
    assert all(data['matchesTestedClasses'] for data in artifact['classes'].values())
    with zipfile.ZipFile(artifact['path']) as jar:
        assert all(jar.read(name) == (WORKSPACE / 'MqlDownloader/target/classes' / name).read_bytes()
                   for name in artifact['classes'])
    java_reports = list((WORKSPACE / 'MqlDownloader/target/surefire-reports').glob('TEST-*.xml'))
    java = {key: sum(cases(path)[key] for path in java_reports)
            for key in ('tests', 'passed', 'failures', 'errors', 'skipped')}
    assert java['passed'] == java['tests'] == 148 and java['skipped'] == 0
    for project in projects:
        git(project, 'diff', '--check')
    manifest = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'foreign_review_sha256': original_sha,
        'report_sha256': sha(REPORT / 'README.md'),
        'previous_fix_manifest_sha256': sha(previous),
        'original_audit_manifest_sha256': sha(baseline_path),
        'original_audit_evidence_verified': len(baseline['evidence_sha256']),
        'original_audit_evidence_mismatches': mismatches,
        'broken_report_links': broken,
        'scanner_full_final': final_suite,
        'scanner_final_shards': shard_results,
        'scanner_final_cases_match_initial_full_collection': actual == expected,
        'mql_full_final': java,
        'test_groups_overlap_do_not_sum': True,
        'intermediate_test_runs': {
            'scanner_full.xml': '2498 passed; one pre-existing test updated an existing identity without its now-required source. Fixture explicitly names mql5; all 2499 cases subsequently repeated in three isolated processes.',
            'katalog_initial.xml': 'One new test erroneously compared NaN to itself; corrected before the final complete suite.',
            'identitaet_final.xml': 'Earlier catalogue numeric-dedup expectation changed while a parallel run was active; final complete suite uses source identity.',
            'kontrakte_tests_intermediate.xml': 'Four caller fixtures still used integer stats keys during the tuple-key transition; final consumer tests updated.'},
        'xml_test_runs': {path.name: cases(path) for path in sorted(REPORT.glob('*.xml'))},
        'heads': {project: git(project, 'rev-parse', 'HEAD').strip() for project in projects},
        'source_sha256': sources,
        'scanner_sources_changed_after_suite_start': late,
        'contract_registry_sha256': sha(SCANNER / 'data/contract_specs.json'),
        'mql_artifact': artifact,
        'production_mutations_performed': False,
        'monitor_restarts_performed': False,
        'full_productive_scan_performed': False,
        'real_llm_calls_performed': False,
        'evidence_sha256': {path.name: sha(path) for path in sorted(REPORT.iterdir())
                            if path.is_file() and path.name != 'manifest.json'},
    }
    (REPORT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({key: manifest[key] for key in ('scanner_full_final', 'mql_full_final',
                     'original_audit_evidence_verified', 'broken_report_links',
                     'scanner_sources_changed_after_suite_start',
                     'scanner_final_cases_match_initial_full_collection')}, indent=2))


if __name__ == '__main__':
    main()
