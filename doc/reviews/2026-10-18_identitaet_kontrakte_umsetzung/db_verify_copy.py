"""Read-only candidate/backup comparison; writes counts/hashes only."""
from collections import Counter
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def digest(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,
                                     separators=(',',':')).encode('utf8')).hexdigest()


folder=Path(__file__).resolve().parent
report_path=Path(sys.argv[1]) if len(sys.argv)>1 else folder/'db_dryrun_report.json'
output_path=Path(sys.argv[2]) if len(sys.argv)>2 else folder/'db_payload_verification.json'
report=json.loads(report_path.read_text(encoding='utf8'))
result={}
with closing(sqlite3.connect(Path(report['backup']['path']).as_uri()+'?mode=ro',uri=True)) as old:
    with closing(sqlite3.connect(Path(report['destination']).as_uri()+'?mode=ro',uri=True)) as new:
        old.row_factory=new.row_factory=sqlite3.Row
        old.execute('BEGIN');new.execute('BEGIN')
        for table,counts in report['tables'].items():
            columns=[r[1] for r in old.execute(f'PRAGMA table_info("{table}")')]
            originals=[dict(r) for r in old.execute(f'SELECT * FROM "{table}"')]
            actual=[]
            for r in new.execute(f'SELECT * FROM "{table}"'):
                row=dict(r)
                if 'signal_id' in columns:
                    ref=row.get('signal_ref')
                    row['signal_id']=(new.execute('SELECT externe_id FROM signal_identitaeten WHERE signal_ref=?',(ref,)).fetchone()[0]
                                      if ref is not None else None)
                actual.append({key:row.get(key) for key in columns})
            quarantine=[json.loads(r[0]) for r in new.execute(
                'SELECT datensatz_json FROM migration_quarantaene WHERE ursprung_tabelle=?',(table,))]
            # Two deliberate representation changes: legacy empty source labels
            # become MQL5; legacy global portfolio ID0 becomes a nullable ref.
            for row in originals:
                if table in ('signals','katalog_signale') and not str(row.get('quelle') or '').strip():
                    row['quelle']='mql5'
                if table=='analyses' and row.get('kind') in ('portfolio','portfolio_ungueltig') and row.get('signal_id')==0:
                    row['signal_id']=None
            for row in quarantine:
                if table in ('signals','katalog_signale') and not str(row.get('quelle') or '').strip(): row['quelle']='mql5'
                if table=='analyses' and row.get('kind') in ('portfolio','portfolio_ungueltig') and row.get('signal_id')==0: row['signal_id']=None
            expected=Counter(digest(r) for r in originals)
            preserved=Counter(digest(r) for r in actual+quarantine)
            result[table]={'before':len(originals),'active':len(actual),'quarantine':len(quarantine),
                           'all_original_values_preserved':expected==preserved,
                           'payload_multiset_sha256':digest(sorted(expected.items()))}
        old.rollback();new.rollback()
assert all(row['all_original_values_preserved'] for row in result.values()),result
output_path.write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps({'tables':len(result),'rows':sum(r['before'] for r in result.values()),
                  'all_original_values_preserved':True}))
