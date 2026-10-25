"""Reproduce the isolated persistence regression; no production operations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[3]
folder=Path(__file__).resolve().parent
tests=[
    'tests/test_source_identity_contract.py','tests/test_review10_db.py',
    'tests/test_external_review_db.py','tests/test_second_review_storage.py',
    'tests/test_forensik_trade_sha.py','tests/test_download_snapshot_integrity.py',
    'tests/test_identity_migration.py','tests/test_identity_db.py',
    'tests/test_identity_core_workflow.py','tests/test_identity_core_review.py',
    'tests/test_journal_signal_identity.py','tests/test_ui_source_identity.py',
    'tests/test_agent_budget_periods.py','tests/test_audit_identitaet_20261018.py',
    'tests/test_quellen.py',
]
sources=['src/mqlkiscanner/db.py','src/mqlkiscanner/signal_identity.py',
         'src/mqlkiscanner/identity_migration.py','src/mqlkiscanner/agenten/dossier.py',
         'src/mqlkiscanner/agenten/budget.py','src/mqlkiscanner/agenten/journal.py']
sha=lambda name:hashlib.sha256((root/name).read_bytes()).hexdigest()
command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*tests,
         '--junitxml='+str(folder/'db_regression.xml'),'--durations=8']
metadata={'command':command,'cwd':str(root),'child_environment_override':{'PYTHONIOENCODING':'utf-8'},
          'sha256_before':{name:sha(name) for name in sources+tests}}
(folder/'db_regression_command.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
started=time.time()
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
with (folder/'db_regression.log').open('w',encoding='utf8') as log:
    outcome=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
(folder/'db_regression_exit.txt').write_text(str(outcome.returncode)+'\n',encoding='ascii')
metadata['exit_code']=outcome.returncode
metadata['elapsed_seconds']=round(time.time()-started,3)
metadata['sha256_after']={name:sha(name) for name in sources+tests}
metadata['tested_files_unchanged']=metadata['sha256_before']==metadata['sha256_after']
(folder/'db_regression_command.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
print(json.dumps({'exit_code':outcome.returncode,'elapsed_seconds':metadata['elapsed_seconds'],
                  'tested_files_unchanged':metadata['tested_files_unchanged']}))
sys.exit(outcome.returncode)
