"""Create a separate, reproducible fix manifest; preserve the original audit."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


REVIEW = Path(__file__).resolve().parents[1]
SCANNER = REVIEW.parents[2]
WORKSPACE = SCANNER.parent


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def test_result(path: Path) -> dict:
    cases = list(ET.parse(path).getroot().iter('testcase'))
    failures = sum(case.find('failure') is not None for case in cases)
    errors = sum(case.find('error') is not None for case in cases)
    skipped = sum(case.find('skipped') is not None for case in cases)
    return dict(cases=len(cases), passed=len(cases) - failures - errors - skipped,
                failures=failures, errors=errors, skipped=skipped, sha256=sha(path))


def source_hashes(project: str) -> dict:
    directory = WORKSPACE / project
    paths = set()
    for arguments in (['diff', '--name-only', '--diff-filter=ACMRT'],
                      ['ls-files', '--others', '--exclude-standard']):
        result = subprocess.run(['git', '-C', str(directory), *arguments],
                                check=True, capture_output=True, text=True)
        for relative in result.stdout.splitlines():
            # Source/test changes only. Runtime settings and secrets are excluded.
            if relative.startswith(('src/', 'tests/', 'app_pages/')) or relative == 'AGENTS.md':
                paths.add(relative)
    return {path: sha(directory / path) for path in sorted(paths)
            if (directory / path).is_file()}


def main() -> None:
    original_path = REVIEW / 'nachweise/manifest.json'
    original = json.loads(original_path.read_text(encoding='utf8'))
    mismatches = [relative for relative, expected in original['evidence_sha256'].items()
                  if not (REVIEW / relative).is_file() or sha(REVIEW / relative) != expected]
    if mismatches:
        raise RuntimeError(f'Original evidence changed: {mismatches}')
    handoff = REVIEW / 'KI_UEBERGABE.md'
    document = REVIEW / 'BEHEBUNG.md'
    broken = []
    for relative in ('KI_UEBERGABE.md', 'BEHEBUNG.md'):
        for target in re.findall(r'\]\(([^)]+)\)', (REVIEW / relative).read_text(encoding='utf8')):
            if '://' in target or target.startswith('#'):
                continue
            path = target.strip('<>').split('#', 1)[0]
            path = re.sub(r':\d+$', '', path)
            candidate = Path(path) if Path(path).is_absolute() else REVIEW / path
            if not candidate.exists():
                broken.append({'file': relative, 'target': target})
    if broken:
        raise RuntimeError(f'Broken report links: {broken}')
    xml_results = {str(path.relative_to(REVIEW)).replace('\\', '/'): test_result(path)
                   for path in sorted((REVIEW / 'nachweise').glob('fix_*.xml'))}
    artifacts = [
        WORKSPACE / 'MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar',
        WORKSPACE / 'vantage/target/vantagemonitor-1.2.0.jar',
        WORKSPACE / 'vantage/target/VantageMonitor-1.2.0-utc-renewal-20261018.zip',
    ]
    manifest = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Implementation follow-up; original audit remains unchanged',
        'original_audit_manifest_sha256': sha(original_path),
        'original_review_sha256': sha(REVIEW / 'README.md'),
        'original_evidence_checked': len(original['evidence_sha256']),
        'original_evidence_hash_mismatches': mismatches,
        'handoff_sha256': sha(handoff),
        'implementation_report_sha256': sha(document),
        'broken_report_links': broken,
        'test_runs_overlap_do_not_sum': True,
        'superseded_test_run_note': 'Initial runs preserved: fix_scanner_initial_pytest.xml used one nonexistent ScanResult field; fix_tabellen_pytest_initial.xml had one incorrect expectation for a non-stale provisional raw DD. Test assumptions corrected without changing product behavior; final regression runs passed.',
        'scanner_full_suite_note': 'Full suite before additional table/Stufe-0 fixes; final consumer regressions cover subsequent changes.',
        'xml_test_runs': xml_results,
        'java_final_suites': {
            name: {
                field: sum(test_result(path)[field] for path in
                           (WORKSPACE / name / 'target/surefire-reports').glob('TEST-*.xml'))
                for field in ('cases', 'passed', 'failures', 'errors', 'skipped')
            }
            for name in ('MqlDownloader', 'vantage')
        },
        'fix_evidence_sha256': {
            str(path.relative_to(REVIEW)).replace('\\', '/'): sha(path)
            for path in sorted((REVIEW / 'nachweise').glob('fix_*')) if path.is_file()
        },
        'source_sha256': {name: source_hashes(name)
                          for name in ('SignalKiScanner', 'MqlDownloader', 'vantage')},
        'build_artifacts': [{'path': path.as_posix(), 'bytes': path.stat().st_size,
                             'sha256': sha(path)} for path in artifacts],
        'runtime_acceptance': {
            'monitor_restarts_performed': False,
            'productive_history_renewal_performed': False,
            'productive_scan_performed': False,
            'real_llm_calls_performed': False,
        },
    }
    output = REVIEW / 'BEHEBUNG.manifest.json'
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    previous = json.loads((REVIEW / 'KI_UEBERGABE.manifest.json').read_text(encoding='utf8'))
    previous.update(updated_utc=manifest['generated_utc'], handoff_sha256=sha(handoff),
                    project_instructions_sha256=sha(SCANNER / 'AGENTS.md'),
                    purpose='AI review handoff with subsequent implementation report and test manifest',
                    product_code_or_settings_changed_for_followup=True,
                    productive_settings_changed_by_this_fix=False,
                    implementation_followup='BEHEBUNG.md',
                    implementation_followup_manifest='BEHEBUNG.manifest.json')
    previous['initial_documentation_test_runs'] = previous.pop('new_test_runs', 0)
    (REVIEW / 'KI_UEBERGABE.manifest.json').write_text(
        json.dumps(previous, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'manifest': str(output), 'original_evidence_checked': len(original['evidence_sha256']),
                      'original_evidence_mismatches': mismatches, 'broken_links': broken,
                      'test_results': xml_results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
