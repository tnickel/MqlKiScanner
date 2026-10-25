"""Strict read-only checkpoint after both exact full-history CLI batches end."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json
from mqlkiscanner import db

ROOT=Path.cwd();HERE=ROOT/'doc/reviews/2026-10-18_tradeserver_v2_liveabschluss'
DATA=(ROOT/'../vantage/data').resolve()
BASELINE=ROOT/'.tmp/source_runtime_backup/20261018T171716Z/vantage_data'
plan=json.loads((HERE/'sources_vantage_repair_plan.json').read_text(encoding='utf-8-sig'))
source=next(q for q in db.list_quellen(nur_aktiv=True) if q['kuerzel']=='vant')
assert source['quellen_uid']==plan['quellen_uid']
for name in ('ft','other'):
 end=json.loads((HERE/f'sources_vantage_{name}_record_identity_exit.json').read_text(encoding='utf-8-sig'))
 assert end['exit_code']==0,'Incomplete or failed upstream full-paging batch'
signals=list(csv.DictReader((DATA/'signals.csv').read_text(encoding='utf-8-sig').splitlines(),delimiter=';'))
catalog={int(s['StrategyId']):s for s in signals};assert len(catalog)==len(signals)
providers=[]
for sid in plan['repair_ids']:
 assert sid in catalog and catalog[sid]['Waehrung'],'Missing freshly persisted provider currency'
 entries=[];stores=[]
 for directory,prefix,opening in (('trades','trades','Eröffnet'),('tradelisten','tradeliste','Eroeffnet')):
  p=DATA/directory/f'{prefix}_{sid}.csv';m=p.with_suffix('.meta')
  raw=p.read_bytes();meta_raw=m.read_bytes();sha=hashlib.sha256(raw).hexdigest()
  meta=dict(line.split('=',1) for line in meta_raw.decode('utf-8-sig').splitlines() if '=' in line)
  data=list(csv.DictReader(raw.decode('utf-8-sig').splitlines(),delimiter=';'))
  assert meta['version']=='2' and meta['timeBasis']=='UTC' and meta['identityBasis']=='historyRecordId'
  assert meta['sha256']==sha and int(meta['count'])==len(data)>0
  ids=[int(r['HistoryRecordId']) for r in data];assert len(ids)==len(set(ids)) and min(ids)>0
  standardized=[(int(r['HistoryRecordId']),r['OrderId'],datetime.fromisoformat(r[opening]),
                 datetime.fromisoformat(r['Geschlossen']),r['Symbol'],r['BasisSymbol'],r['Richtung'],
                 float(r['Lots']),float(r['OpenPrice']),float(r['ClosePrice']),float(r['NettoPnlUsd'])) for r in data]
  entries.append(standardized)
  old=BASELINE/directory/p.name
  old_hash=None;old_meta_hash=None;archived=False
  if old.exists():
   old_hash=hashlib.sha256(old.read_bytes()).hexdigest()
   old_meta=old.with_suffix('.meta')
   if old_meta.exists():old_meta_hash=hashlib.sha256(old_meta.read_bytes()).hexdigest()
   archived=any(hashlib.sha256(a.read_bytes()).hexdigest()==old_hash
                and (old_meta_hash is None or (a.with_suffix('.meta').is_file()
                     and hashlib.sha256(a.with_suffix('.meta').read_bytes()).hexdigest()==old_meta_hash))
                for a in (DATA/directory/'quarantine').rglob(p.name))
   assert archived,'Original source bytes not found in lossless quarantine'
  proof={'store':directory,'rows':len(data),'sha256':sha,'sha_matches':True,'count_matches':True,
         'utc':True,'identity_basis':'historyRecordId','unique_record_ids':len(set(ids)),
         'missing_order_tickets':sum(not r['OrderId'] for r in data),
         'csv_mtime_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),
         'meta_sha256':hashlib.sha256(meta_raw).hexdigest(),'original_private_backup_sha256':old_hash,
         'original_private_backup_meta_sha256':old_meta_hash,
         'original_bytes_preserved_in_quarantine':archived if old.exists() else None}
  if directory=='trades':
   assert int(meta['total'])==len(data),'Fresh provider total is not exactly the new unique row count'
   proof.update(provider_total=int(meta['total']),complete=True)
  stores.append(proof)
 assert entries[0]==entries[1],'Two native stores disagree on source rows'
 providers.append({'signal_id':sid,'source_uid':source['quellen_uid'],'native_currency':catalog[sid]['Waehrung'],
                   'stores':stores,'all_native_fields_match_between_stores':True,'verified':True})
output={'checked_utc':datetime.now(timezone.utc).isoformat(),'source_uid':source['quellen_uid'],
 'upstream_full_pagination_exit':0,'verified_scope':plan['repair_ids'],'local_offered_catalog_count':len(signals),
 'api_status':'Native scope verified; REST activation/export acceptance still required',
 'full_19_native_scope_verified':True,'normal_update_complete':False,'providers':providers}
(HERE/'sources_vantage_full_scope_native_checkpoint.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps({'scope':len(providers),'local_offered_catalog_count':len(signals),'all_native_counts_owners_hashes_and_archives_verified':True}))
