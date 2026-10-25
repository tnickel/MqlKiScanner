"""Native offline imports preserve evidence and never certify cache integrity as history."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path

import pytest

from mqlkiscanner import abonnenten_native_cache_import as importer, parser


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def entry(source="mql5"):
    return {"quelle": source, "quellen_uid": "stable-source-uid", "id": 123, "signal_ref": 42,
            "quelle_version": {"mql5": "mql5", "pelik": "pelican", "zulu": "zulu"}[source],
            "trades_path": "", "trades_sha256": "", "data_done": True, "data_complete": False,
            "eligible": False, "forensik": {}, "equity_dd_pct": None,
            "quellen_stats": {}, "modell": {"status": "datenluecke"}}


def candidate(e, path):
    return {k:e[k] for k in ("quelle", "quellen_uid", "id", "signal_ref", "quelle_version")} | {
        "originalpfad": str(path), "sha256": sha(path.read_bytes()), "currency": "USD"}


def mql(tmp_path):
    e = entry()
    path = tmp_path/"native"/"mql5"/"Some_123.csv"
    path.parent.mkdir(parents=True)
    raw = (";".join(parser.POSITION_HEADER)+"\n2026.01.01 00:00:00;Balance;;;;;;;;;1000\n"
           "2026.01.05 01:00:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.06 01:00:00;2001;-1;-2;10\n").encode()
    path.write_bytes(raw)
    metrics = path.with_name("Some_123_root.txt")
    metrics.write_text("Currency=USD\nBroker=Source-Server\n", encoding="utf-8")
    c = candidate(e, path)
    c.update(tradecount=1, metricsPath=str(metrics), metrics_sha256=sha(metrics.read_bytes()))
    return e, c, raw


def native(tmp_path, source="pelik", *, zero_price=False, full=True):
    e = entry(source)
    if source == "pelik":
        base = tmp_path/"Pelican"/"data"
        path = base/"signals"/"closed"/"closed_123.csv"
        header = importer.PELICAN_HEADER
        row = ["111", "XAUUSD", "Buy", "0.01", "0" if zero_price else "2000", "2001",
               "2026-01-05 01:00:00", "2026-01-06 01:00:00", "24", "7.125", "USD", "Source-Server"]
        catalog = "Id;Waehrung;Broker\n123;USD;Source-Server\n"
    else:
        base = tmp_path/"Zulu"/"data"
        path = base/"trades"/".generations"/"123"/"01234567-0123-0123-0123-0123456789ab"/"trades.csv"
        header = importer.ZULU_HEADER
        row = ["111", "123", "EUR/USD", "SELL", "0.12", "2026-01-05 01:00:00",
               "2026-01-06 01:00:00", "24", "1.1", "1.0", "10", "9", "7.125", "1", "true", "", ""]
        catalog = "ProviderId;Waehrung;Broker\n123;USD;Source-Server\n"
    path.parent.mkdir(parents=True)
    raw = ("\ufeff"+";".join(header)+"\n"+";".join(row)+"\n").encode()
    path.write_bytes(raw)
    meta = path.with_suffix(".meta") if source == "pelik" else path.with_name("archive.meta")
    meta.write_text("version=1\n"+("requested=100\n" if source == "zulu" else "")+
                    "count=1\nsha256="+sha(raw)+"\n", encoding="utf-8")
    catalog_path = base/("providers.csv" if source == "pelik" else "traders.csv")
    catalog_path.write_text(catalog, encoding="utf-8")
    c = candidate(e, path)
    c.update(tradecount=1, metaPath=str(meta), meta_sha256=sha(meta.read_bytes()), metricsPath=str(catalog_path))
    if source == "zulu":
        receipt = path.with_name("history.receipt")
        receipt.write_text("version=1\nprovider=123\nsha256="+sha(raw)+
                           "\ntotal=1\ndownloaded=1\npages=1\ncomplete="+str(full).lower()+
                           "\nobserved=2026-01-07T00:00:00Z\n", encoding="utf-8")
        c["receiptPath"] = str(receipt)
    return e, c, raw


def test_mql_copies_original_bytes_with_flows_without_marking_history_full(tmp_path):
    e,c,raw = mql(tmp_path)
    before = deepcopy(e)
    result = importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"] == "uebernommen", result
    assert Path(result["trades_path"]).read_bytes() == raw
    assert result["trades_sha256"] == sha(raw)
    assert len(parser.load_export(result["trades_path"]).balances) == 1
    assert result["trade_history_complete"] is None and result["trades"] == 1
    assert result["netto_quellwaehrung"] == 7
    assert result["quellen_stats"]["broker_server"] == "Source-Server"
    assert e == before and Path(c["originalpfad"]).read_bytes() == raw
    assert result["modell"] == e["modell"] and result["eligible"] is False


@pytest.mark.parametrize("file_age_seconds", [0, 60])
def test_mql_matching_historical_receipt_is_separate_from_new_snapshot_sha(tmp_path, file_age_seconds):
    e,c,_ = mql(tmp_path)
    # Fix both clocks explicitly: NTFS has finer precision than datetime.now()
    # and an immediate timestamp can otherwise precede st_mtime by < 1 us.
    received = datetime(2026, 1, 7, tzinfo=timezone.utc)
    file_time = received.timestamp() - file_age_seconds
    os.utime(c["originalpfad"], (file_time, file_time))
    receipt = {"fullHistory": True, "platformRefreshed": True, "providerId": "123", "version": "mql5",
               "refreshedAt": received.isoformat()}
    e["refresh"] = receipt
    c["full_history_beleg"] = deepcopy(receipt)
    result = importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["trade_history_complete"] is True
    assert "keinen Datei-SHA" in result["native_cache_import"]["full_history_beleg"]["grund"]


@pytest.mark.parametrize("source", ["pelik", "zulu"])
def test_native_converter_preserves_every_position_lot_time_and_net(tmp_path, source):
    e,c,raw = native(tmp_path,source)
    result = importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    audit = result["native_cache_import"]
    assert audit["status"] == "uebernommen", result
    trade = parser.load_export(result["trades_path"]).trades[0]
    assert trade.net == 7.125 and trade.volume == (0.01 if source=="pelik" else .12)
    assert trade.open_time.isoformat() == "2026-01-05T01:00:00"
    assert trade.close_time.isoformat() == "2026-01-06T01:00:00"
    assert trade.symbol == ("XAUUSD" if source=="pelik" else "EURUSD")
    assert result["trade_money_currency"] == result["account_currency"] == "USD"
    assert result["trade_history_complete"] is (True if source=="zulu" else None)
    assert Path(audit["original_snapshot_path"]).read_bytes() == raw
    assert Path(c["originalpfad"]).read_bytes() == raw


def test_zulu_explicit_partial_receipt_remains_partial(tmp_path):
    e,c,_ = native(tmp_path,"zulu",full=False)
    result = importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"] == "uebernommen"
    assert result["trade_history_complete"] is False
    assert result["trade_history_status"] == "teilweise"


def test_zero_price_keeps_raw_evidence_and_cannot_drop_the_position(tmp_path):
    e,c,raw = native(tmp_path,zero_price=True)
    result = importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"] == "datenluecke"
    assert result["trades_path"] == "" and "positiv" in result["native_cache_import"]["grund"]
    assert Path(result["native_cache_import"]["original_snapshot_path"]).read_bytes() == raw


@pytest.mark.parametrize("field,value", [("quellen_uid","other"),("id",999),("signal_ref",999),
                                         ("quelle_version","mql4"),("quelle","zulu")])
def test_identity_conflicts_cannot_overwrite_entry(tmp_path,field,value):
    e,c,_=mql(tmp_path)
    c[field]=value
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="datenluecke"
    assert not (tmp_path/"snapshots").exists()
    assert result["quellen_uid"]==e["quellen_uid"] and result["trades_path"]==""


def test_existing_snapshot_and_sha_are_never_replaced(tmp_path):
    e,c,_=mql(tmp_path)
    e.update(trades_path="original.csv",trades_sha256="original-sha")
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["trades_path"]=="original.csv" and result["trades_sha256"]=="original-sha"
    assert result["native_cache_import"]["status"]=="datenluecke"


def test_stale_raw_or_meta_sha_cannot_be_imported(tmp_path):
    e,c,_=native(tmp_path)
    Path(c["metaPath"]).write_text("version=1\ncount=1\nsha256=wrong\n",encoding="utf-8")
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="datenluecke" and result["trades_path"]==""
    c["sha256"]="0"*64
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots2")
    assert "SHA-256" in result["native_cache_import"]["grund"]


def test_currency_conflict_is_not_relabelled_usd(tmp_path):
    e,c,_=native(tmp_path)
    catalog=Path(c["metricsPath"])
    catalog.write_text("Id;Waehrung;Broker\n123;EUR;Source-Server\n",encoding="utf-8")
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="datenluecke"
    assert "widerspricht" in result["native_cache_import"]["grund"] and result["trades_path"]==""


def test_false_zulu_receipt_identity_cannot_certify_full_history(tmp_path):
    e,c,_=native(tmp_path,"zulu")
    p=Path(c["receiptPath"]);p.write_text(p.read_text().replace("provider=123","provider=999"))
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="datenluecke"
    assert result["trades_path"]==""


def test_repeated_preparation_reuses_identical_content_addressed_files(tmp_path):
    e,c,_=native(tmp_path,"zulu")
    first=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    second=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert first["trades_path"]==second["trades_path"]
    assert len(list((tmp_path/"snapshots").rglob("*.csv")))==2


def test_mixed_native_currencies_preserve_all_raw_rows_but_do_not_guess_conversion(tmp_path):
    e,c,raw=native(tmp_path)
    path=Path(c["originalpfad"])
    lines=raw.decode("utf-8-sig").splitlines()
    second=lines[1].split(";");second[0]="222";second[10]="EUR"
    raw=("\ufeff"+"\n".join([*lines,";".join(second)])+"\n").encode()
    path.write_bytes(raw)
    meta=Path(c["metaPath"])
    meta.write_text("version=1\ncount=2\nsha256="+sha(raw)+"\n",encoding="utf-8")
    c.update(sha256=sha(raw),meta_sha256=sha(meta.read_bytes()),tradecount=2)
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="datenluecke"
    assert "Geldwährung" in result["native_cache_import"]["grund"]
    assert Path(result["native_cache_import"]["original_snapshot_path"]).read_bytes()==raw
    assert result["trades_path"]==""


def test_archived_pelican_provider_uses_explicit_row_currency_without_synthetic_metrics(tmp_path):
    e,c,_=native(tmp_path)
    Path(c["metricsPath"]).write_text("Id;Waehrung;Broker\n999;EUR;Other-Server\n",encoding="utf-8")
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="uebernommen"
    assert result["trade_money_currency"]=="USD"
    assert result["native_cache_import"]["metadaten"]["anbieter_im_katalog"] is False
    assert result["quellen_stats"]["broker_server"]=="Source-Server"
    assert result["trade_history_complete"] is None


def test_mql_receipt_predating_the_native_file_does_not_certify_the_file(tmp_path):
    e,c,_=mql(tmp_path)
    receipt={"fullHistory":True,"platformRefreshed":True,"providerId":"123","version":"mql5",
             "refreshedAt":"2000-01-01T00:00:00Z"}
    e["refresh"]=receipt;c["full_history_beleg"]=deepcopy(receipt)
    result=importer.prepare_candidate(e,c,out_dir=tmp_path/"snapshots")
    assert result["native_cache_import"]["status"]=="uebernommen"
    assert result["trade_history_complete"] is None
