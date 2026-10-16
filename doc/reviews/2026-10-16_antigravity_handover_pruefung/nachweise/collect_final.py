"""Verify tested overlays and copy only explicitly selected offline review evidence."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

audit = Path(__file__).resolve().parent
workspace = audit.parents[1]
destination = workspace / 'SignalKiScanner/doc/reviews/2026-10-16_antigravity_handover_pruefung/nachweise'
config = json.loads((audit / 'final_config.json').read_text(encoding='utf-8'))
destination.mkdir(parents=True, exist_ok=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    data = path.read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')

def copy(path, name=None):
    target = destination / (name or path.name)
    shutil.copyfile(path, target)
    return target.name

def relevant(name):
    name = name.replace('\\', '/')
    return name.startswith(('src/', 'tests/', 'app_pages/', 'config/prompts/')) or name in (
        'streamlit_app.py', 'pom.xml', 'requirements.txt', 'download_trades.py')

summary = {'scope': 'Offline tests, no platform logins or paid model calls', 'runs': []}
for entry in config['runs']:
    snapshot = audit / entry['snapshot']
    manifest_path = audit / entry['manifest']
    manifest = json.loads(read(manifest_path))
    if 'overlay_sha256' in manifest:
        repo, baseline, files = Path(manifest['repo']), manifest['head'], manifest['overlay_sha256']
    else:
        repo, baseline = workspace / manifest['repository'], manifest['headBefore']
        files = manifest['snapshotFiles']
    for name, expected in files.items():
        if sha(snapshot / name) != expected:
            raise SystemExit(f'Tested snapshot changed: {snapshot.name}/{name}')
        if relevant(name) and (repo / name).read_bytes().replace(b'\r\n', b'\n') != (snapshot / name).read_bytes().replace(b'\r\n', b'\n'):
            raise SystemExit(f'Untested source drift: {repo.name}/{name}')
    changed = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only', 'HEAD', '-z'], stderr=subprocess.DEVNULL)
    new = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--others', '--exclude-standard', '-z'])
    missing = [p.decode() for p in (changed + new).split(b'\0') if p and relevant(p.decode()) and not (snapshot / p.decode()).is_file()]
    if missing:
        raise SystemExit(f'Absent tested source: {repo.name}: {missing}')
    xmls = [audit / entry['xml']] if 'xml' in entry else sorted((snapshot / 'target/surefire-reports').glob('TEST-*.xml'))
    if not xmls:
        raise SystemExit(f'Missing XML reports: {snapshot}')
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
        raise SystemExit(f'Failed tests: {snapshot.name}: {totals}')
    logs = {}
    for key in ('log', 'package_log', 'python_log'):
        if key not in entry:
            continue
        path = audit / entry[key]
        content = read(path)
        if (key == 'package_log' or (key == 'log' and entry.get('package'))) and 'BUILD SUCCESS' not in content:
            raise SystemExit(f'Missing successful build: {path}')
        if key == 'python_log' and not re.search(r'\b12 passed\b', content):
            raise SystemExit(f'Unexpected Python result: {path}')
        logs[copy(path)] = sha(path)
    copy(manifest_path, snapshot.name + '.manifest.json')
    if 'xml' in entry:
        copy(audit / entry['xml'])
    summary['runs'].append({**entry, 'baseline': baseline, 'passed': totals['tests'] - totals['skipped'],
                            'totals': totals, 'suites': suites, 'log_sha256': logs})
summary['additional_runs'] = []
for run in config.get('additional_runs', []):
    content = read(audit / run['log'])
    expected = run['expected_passed']
    if run['kind'] == 'vantage_python':
        valid = re.search(r'\b' + str(expected) + r' passed\b', content)
    else:
        valid = 'BUILD SUCCESS' in content and re.search(
            r'Tests run: ' + str(expected) + r', Failures: 0, Errors: 0, Skipped: 0', content)
    if not valid:
        raise SystemExit(f"Unexpected additional test result: {run}")
    summary['additional_runs'].append({**run, 'passed': expected, 'log_sha256': sha(audit / run['log'])})
for name in config['attachments']:
    copy(audit / name)
copy(audit / 'collect_final.py')
copy(audit / 'final_config.json')
(destination / 'test_results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
hashes = {p.relative_to(destination.parent).as_posix(): sha(p) for p in destination.rglob('*')
          if p.is_file() and p.name != 'sha256.json'}
for original in destination.parent.glob('*ORIGINAL.md'):
    hashes[original.name] = sha(original)
(destination / 'sha256.json').write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps([{'snapshot': r['snapshot'], 'passed': r['passed'], 'totals': r['totals']} for r in summary['runs']], indent=2))
