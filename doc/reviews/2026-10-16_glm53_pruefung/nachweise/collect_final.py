"""Publish only offline review evidence and verify the actual tested source overlays."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

audit = Path(__file__).resolve().parent
workspace = audit.parents[1]
destination = workspace / 'SignalKiScanner/doc/reviews/2026-10-16_glm53_pruefung/nachweise'
destination.mkdir(exist_ok=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_text(path):
    data = path.read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')

def relevant(name):
    name = name.replace('\\', '/')
    return name.startswith(('src/', 'tests/', 'app_pages/', 'config/prompts/')) or name in (
        'streamlit_app.py', 'pom.xml', 'requirements.txt', 'download_trades.py', '.gitattributes')

def copy(source, name=None):
    target = destination / (name or source.name)
    shutil.copyfile(source, target)
    return target.name

summary = {'scope': 'Offline synthetic tests; no production data, platform login or paid model validation', 'runs': []}
for entry in json.loads((audit / 'final_config.json').read_text(encoding='utf-8')):
    snapshot = audit / entry['snapshot']
    manifest_path = audit / entry['manifest']
    original = json.loads(read_text(manifest_path))
    if 'overlay_sha256' in original:
        repo, head, overlays = Path(original['repo']), original['head'], original['overlay_sha256']
    else:
        repo, head = workspace / original['repository'], original['headBefore']
        overlays = original['snapshotFiles']
    for name, expected in overlays.items():
        if digest(snapshot / name) != expected:
            raise SystemExit(f'Tested snapshot changed: {snapshot.name}/{name}')
    drift = [name for name in overlays if relevant(name) and
             (repo / name).read_bytes().replace(b'\r\n', b'\n') !=
             (snapshot / name).read_bytes().replace(b'\r\n', b'\n')]
    changed = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only', 'HEAD', '-z'])
    new = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--others', '--exclude-standard', '-z'])
    missing = [raw.decode() for raw in (changed + new).split(b'\0') if raw and
               relevant(raw.decode()) and not (snapshot / raw.decode()).is_file()]
    if drift or missing:
        raise SystemExit(f'Untested source: {repo.name}, drift={drift}, missing={missing}')
    xmls = [audit / entry['xml']] if 'xml' in entry else sorted((snapshot / 'target/surefire-reports').glob('TEST-*.xml'))
    if not xmls:
        raise SystemExit(f'No test reports: {snapshot}')
    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    suites = []
    for path in xmls:
        root = ET.parse(path).getroot()
        for suite in ([root] if root.tag == 'testsuite' else root.iter('testsuite')):
            record = {'name': suite.get('name'), 'time_seconds': float(suite.get('time', 0))}
            for key in totals:
                record[key] = int(suite.get(key, 0))
                totals[key] += record[key]
            record['nonpassing_cases'] = [
                {'class': case.get('classname'), 'name': case.get('name'), 'status': state.tag,
                 'reason': state.get('message', '')}
                for case in suite.findall('testcase') for state in case
                if state.tag in ('failure', 'error', 'skipped')]
            suites.append(record)
    if totals['failures'] or totals['errors']:
        raise SystemExit(f'Failed tests: {snapshot.name}, {totals}')
    logs = {}
    for kind in ('log', 'package_log', 'python_log'):
        if kind not in entry:
            continue
        source = audit / entry[kind]
        content = read_text(source)
        if (kind == 'package_log' or (kind == 'log' and entry.get('package'))) and 'BUILD SUCCESS' not in content:
            raise SystemExit(f'Missing package success: {source}')
        if kind == 'python_log' and not re.search(r'\b12 passed\b', content):
            raise SystemExit(f'Unexpected Vantage Python result: {source}')
        logs[copy(source, entry.get('evidence_prefix', '') + source.name)] = digest(source)
    copy(manifest_path, snapshot.name + '.manifest.json')
    if 'xml' in entry:
        copy(audit / entry['xml'])
    summary['runs'].append({**entry, 'baseline_commit': head, 'passed': totals['tests'] - totals['skipped'],
                            'totals': totals, 'suites': suites, 'log_sha256': logs})

for name in ('clients.md', 'quellen_a.md', 'quellen_b.md', 'quellen_a_peer_review.md', 'fin7_peer_review.md', 'robo_dd_peer_review.md',
             'fin7_peer_probe_results.json', 'fin7_peer_probe_after.json', 'fin7_peer_probe.py',
             'hub_before.log', 'hub_targeted.log', 'hub_targeted.xml',
             'clients_targeted.log', 'clients_targeted.xml', 'clients_finance_ui.log',
             'clients_finance_ui.xml', 'clients_final_delta.log', 'clients_final_delta.xml',
             'mql_pagination_before.log'):
    copy(audit / name)
for name in ('pelican_fixture_counts.json', 'robo_cached_basis_probe.log', 'final_hash_verification.json'):
    copy(audit / 'quellen_b' / name)
copy(audit / 'collect_final.py')
copy(audit / 'final_config.json')
(destination / 'test_results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
hashes = {p.relative_to(destination.parent).as_posix(): digest(p)
          for p in destination.rglob('*') if p.is_file() and p.name != 'sha256.json'}
hashes['GLM_ORIGINAL.txt'] = digest(destination.parent / 'GLM_ORIGINAL.txt')
(destination / 'sha256.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps([{'snapshot': r['snapshot'], 'passed': r['passed'], 'totals': r['totals']}
                  for r in summary['runs']], indent=2))
