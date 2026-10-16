import hashlib
import json
from pathlib import Path

audit = Path(__file__).resolve().parent
names = ['Scanner_final3', 'MqlDownloader_round1', 'PelicanTrading_round1',
         'roboforex_round1', 'vantage_final_ui', 'zulumonitor_final_ui']
results = []
for name in names:
    manifest = json.loads((audit / (name + '.manifest.json')).read_text(encoding='utf-8'))
    repo = Path(manifest['repo'])
    checked = []
    for path, expected in manifest['overlay_sha256'].items():
        frozen = audit / name / path
        assert hashlib.sha256(frozen.read_bytes()).hexdigest() == expected, (name, path)
        if path.replace('\\', '/').startswith(('src/', 'tests/', 'app_pages/')):
            assert (repo / path).read_bytes().replace(b'\r\n', b'\n') == frozen.read_bytes().replace(b'\r\n', b'\n'), (name, path)
            checked.append(path)
    results.append({'snapshot': name, 'verified_code_test_files': len(checked)})
(audit / 'final_code_hash_check.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
