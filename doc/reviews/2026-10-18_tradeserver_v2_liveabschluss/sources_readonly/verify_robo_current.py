"""Read-only native generation/REST checks after the owned Robo repair."""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import csv,hashlib,json,requests
from mqlkiscanner import db,quellen

ROOT=Path.cwd();REPO=(ROOT/'../roboforex').resolve()
HERE=ROOT/'doc/reviews/2026-10-18_tradeserver_v2_liveabschluss'
repair=json.loads((HERE/'sources_robo_repair_progress.json').read_text(encoding='utf-8-sig'))
assert repair['status'] in ('runtime_restarted_pending_rest_acceptance',
 'native_supported_scope_complete_api_gui_verified_units_unverified') and not repair['failures']
q=next(q for q in db.list_quellen(nur_aktiv=True) if q['kuerzel']=='robo')
assert q['quellen_uid']=='2267f37b-c01a-4c2f-aaf6-04bd96583606'
c=quellen.client_fuer_quelle(q,timeout=120)
catalog=c.katalog(limit=5000,min_subscribers=0)
items={int(x['signalId']):x for x in catalog['items']}
signals=list(csv.DictReader((REPO/'data/signals.csv').read_text(encoding='utf-8-sig').splitlines(),delimiter=';'))
assert len(signals)==len(items)==200
health=c.health();assert health['service']=='RoboMonitor'
original=next(s for s in json.loads((HERE/'sources_before.json').read_text(encoding='utf-8-sig'))['sources'] if s['source']=='robo')['health']
assert all(health[k]==original[k] for k in ('service','instance')),'Source service/instance changed'
initial_start=datetime(2026,10,18,16,42,tzinfo=timezone.utc)
output={'checked_utc':datetime.now(timezone.utc).isoformat(),'source_uid':q['quellen_uid'],
 'status':'verification_running','catalog_count':len(items),'health':health,'new_pid':repair['new_pid'],
 'initial_job_id':repair['initial_job_id'],'repaired_ids':repair['repair_ids'],
 'verified':[],'unsupported':[],'reports_probes':{},'verification_errors':[],'all_supported_histories_fresh':False,
 'all_providers_exportable':False,'source_download_complete':False}

def save():
 p=HERE/'sources_robo_live_acceptance.json';tmp=p.with_suffix('.json.tmp')
 output['checked_utc']=datetime.now(timezone.utc).isoformat()
 tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(p)

def D(x):return Decimal(x.replace(' ',''))
def eq(a,b):assert abs(D(str(a))-D(str(b)))<=Decimal('0.00000001'),f'numeric mismatch {a} / {b}'
def rows(raw):return list(csv.reader(raw.decode('utf-8-sig').splitlines(),delimiter=';'))
def ts(raw):return raw.replace('-','.').replace('T',' ')
def same_time(native,actual):
 if not native:return not actual
 return bool(actual) and datetime.fromisoformat(native.replace(' ','T'))==datetime.fromisoformat(actual)

for index,s in enumerate(signals,1):
 sid=int(s['Login']);pf=s['Plattform'];item=items[sid]
 try:
  assert item['sourcePlatform']==pf
  version={'mt4':'mql4','mt5':'mql5','rst':'rst'}[pf]
  assert item['version']==version
  if version not in output['reports_probes']:
   assert c.reports(sid,version)==[]
   response=requests.get(c.base+f'/providers/{sid}/{version}/reports/historical.pdf',headers=c._headers(),timeout=120)
   assert response.status_code==404
   output['reports_probes'][version]={'signal_id':sid,'reports_count':0,'direct_historical_file_status':404}
  metrics=c.metrics(sid,version)['metrics']
  assert metrics['TradingPlatform']==pf
  assert metrics['Currency'] is None and metrics['Balance'] is None
  assert metrics['RawMoneyCurrency']=='unknown' and metrics['TradeUnitStatus']=='unverified'
  assert metrics['TradeClosedDdPct'] is None and metrics['TradeEqDrawdownPct'] is None
  assert item['currencyCode'] is None and item['ratingCurrencyCode']=='USD'
  assert item['tradeExportAvailable'] is False and item['links']['tradesCsv'] is None
  if pf=='rst':
   assert item['tradeHistorySupported'] is False and item['lastUpdated'] is None
   assert item['links']['trades'] is None and item['links']['tradesCsv'] is None
   assert metrics['TradeHistorySupported'] is False and metrics['TradeHistoryAvailable'] is False
   assert metrics['TradeHistoryComplete'] is False and metrics['TradeEqDrawdownPct'] is None
   assert metrics['TradeClosedDdPct'] is None and metrics['TradeDdBasisStatus']=='unknown'
   responses=[]
   for v in ('rst','mql4','mql5'):
    for endpoint in ('trades','trades.csv'):
     try:c._get(f'/providers/{sid}/{v}/{endpoint}');raise AssertionError('Unsupported platform endpoint became available')
     except Exception as e:
      assert '404' in str(e),str(e);responses.append({'version':v,'endpoint':endpoint,'status':404})
   output['unsupported'].append({'signal_id':sid,'platform':pf,'history_unavailable':True,
                                'reason':item['tradeHistoryUnavailableReason'],'responses':responses})
  else:
   path=REPO/'data/deals'/f'deals_{sid}.csv';meta_path=path.with_suffix('.meta')
   raw=path.read_bytes();meta_raw=meta_path.read_bytes()
   text=raw.decode('utf-8-sig').replace('\r\r\n','\r\n')
   native=rows(raw);meta=dict(line.split('=',1) for line in meta_raw.decode('utf-8-sig').splitlines() if '=' in line)
   records=[r for r in native[1:] if r];ids=[r[0] for r in records]
   assert len(ids)==len(set(ids))==int(meta['count'])
   assert hashlib.sha256(text.encode()).hexdigest()==meta['sha256']
   assert meta['platform']==pf and meta['source_id']==s['SourceId']
   assert meta['pagination_complete']=='true'
   assert datetime.fromisoformat(meta['fetched_at'].replace('Z','+00:00'))>=initial_start
   assert metrics['TradeHistorySupported'] is True and metrics['TradeHistoryAvailable'] is True
   assert metrics['TradeHistoryComplete'] is False and metrics['TradeExportAvailable'] is False
   assert metrics['RawHistoryPaginationComplete'] is True and metrics['RawHistoryRows']==len(records)
   proof={'signal_id':sid,'platform':pf,'provider_source_id':s['SourceId'],'raw_rows':len(records),
          'raw_unique_ids':len(set(ids)),'native_csv_sha256':hashlib.sha256(raw).hexdigest(),
          'meta_sha256':hashlib.sha256(meta_raw).hexdigest(),'fetched_at':meta['fetched_at'],
          'fetch_id':meta['fetch_id'],'pagination_complete':True,'rest_complete':metrics['TradeHistoryComplete'],
          'quality_reasons_preview':metrics['TradeHistoryQualityReasons'][:5],
          'quality_reason_count':len(metrics['TradeHistoryQualityReasons'])}
   response=requests.get(c.base+f'/providers/{sid}/{version}/trades.csv',headers=c._headers(),timeout=120)
   assert response.status_code==404 and response.json()['code']=='unverified_trade_units'
   payload=c._get(f'/providers/{sid}/{version}/trades')
   assert int(payload['signalId'])==sid and payload['version']==version
   assert payload['rawMoneyCurrency']=='unknown' and payload['tradeUnitStatus']=='unverified'
   raw_deals=payload['rawDeals'];assert len(raw_deals)==len(records)
   assert len({r['id'] for r in raw_deals})==len(records)
   for native,actual in zip(records,raw_deals):
    assert int(native[0])==actual['id']
    if pf=='mt4':
     assert native[1]==actual['side'] and native[2]==actual['symbol']
     assert same_time(native[4],actual['time'])
     assert same_time(native[5],actual['closeTime'])
     eq(native[3],actual['storedVolume']);eq(native[8],actual['commission']);eq(native[9],actual['swap'])
     eq(native[10],actual['netPnl']);eq(D(native[10])-D(native[8])-D(native[9]),actual['profit'])
     for i,key in ((6,'openPrice'),(7,'closePrice')):
      if native[i]:eq(native[i],actual[key])
      else:assert actual[key] is None
    else:
     assert int(native[1])==actual['positionId'] and native[3]==actual['side'] and native[4]==actual['entry']
     assert native[5]==actual['symbol'] and same_time(native[2],actual['time'])
     eq(D(native[6])/100,actual['storedVolume']);eq(native[8],actual['commission']);eq(native[9],actual['swap']);eq(native[10],actual['profit'])
     eq(D(native[10])+D(native[8])+D(native[9]),actual['netPnl'])
     if native[7]:eq(native[7],actual['price'])
     else:assert actual['price'] is None
   proof.update(rest_csv_status=404,rest_csv_error='unverified_trade_units',raw_json_rows=len(raw_deals),
                native_raw_json_all_financial_fields_matched=True,money_currency='unknown',volume_unit='unverified_internal_representation')
   assert raw==path.read_bytes() and meta_raw==meta_path.read_bytes(),'GET changed native generation'
   output['verified'].append(proof)
 except Exception as e:
  output['verification_errors'].append({'signal_id':sid,'error':str(e) or type(e).__name__})
 output['done']=index;output['total']=len(signals);save()
output['all_supported_histories_fresh']=not output['verification_errors'] and len(output['verified'])==197 and len(output['unsupported'])==3
output['all_providers_exportable']=len([r for r in output['verified'] if r['rest_complete']])==200
output['source_download_complete']=output['all_supported_histories_fresh']
output['exportable_supported_count']=sum(bool(r['rest_complete']) for r in output['verified'])
output['status']='verified_supported_scope_with_explicit_unavailable' if output['source_download_complete'] else 'verification_failed'
save()
print(json.dumps({k:output[k] for k in ('status','done','total','source_download_complete','exportable_supported_count','verification_errors')}))
