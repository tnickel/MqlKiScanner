"""Prepare missing trade snapshots from verified, already saved native files.

No source requests, login, FX downloads, job writes or model calculation live
here. Native monetary units, position counts and local export timestamps are
preserved. Integrity and full platform-history evidence remain separate.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re

from . import config, parser

VERSION = 1
PELICAN_HEADER = ("TradeId", "Instrument", "Richtung", "Menge", "OpenPrice", "ClosePrice",
                  "Eroeffnet", "Geschlossen", "DauerH", "RealisierterProfit", "Waehrung", "Server")
ZULU_HEADER = ("TradeId", "ProviderId", "Währungspaar", "Typ", "Lots", "Eröffnet", "Geschlossen",
               "DauerStunden", "Eröffnungskurs", "Schlusskurs", "Pips", "BruttoPnL", "NettoPnL",
               "RoiProzent", "LiveTrade", "EröffnetEpochMs", "GeschlossenEpochMs")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _positive_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value or "")):
        raise ValueError("Positive kanonische Anbieter-/Referenz-ID fehlt.")
    return int(value)


def _properties(raw):
    result = {}
    for line in raw.decode("utf-8-sig").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError("Mehrfacher Schlüssel im nativen Metabeleg: " + key)
        result[key] = value.strip()
    return result


def _rows(raw, headers=None):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";")
    header = tuple(next(reader, ()))
    if headers and header not in headers:
        raise ValueError("Unbekannter nativer CSV-Kopf.")
    if len(set(header)) != len(header):
        raise ValueError("Mehrdeutiger nativer CSV-Kopf.")
    result = []
    for line, row in enumerate(reader, 2):
        if not row or all(not cell for cell in row):
            continue
        if len(row) != len(header):
            raise ValueError(f"Native CSV-Zeile {line} hat falsche Spaltenzahl.")
        result.append(dict(zip(header, row)))
    return header, result


def _number(value, *, positive=False):
    number = float(value)
    if not math.isfinite(number) or positive and number <= 0:
        raise ValueError("Native Mengen/Preise müssen positiv, Geldbeträge endlich sein.")
    return number


def _time(value):
    when = datetime.fromisoformat(value)
    if when.tzinfo is not None or when.microsecond or when.year <= 1:
        raise ValueError("Native Exportzeit nicht ohne Zeitänderung im Sekundenformat darstellbar.")
    return when


def _stamp(value):
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("Empfangsbeleg hat keine Zeitzone.")
    return when


def _snapshot(base, entry, raw, kind):
    digest = _hash(raw)
    namespace = _hash(entry["quellen_uid"].encode("utf-8"))[:20]
    target = (base/kind/namespace/entry["quelle_version"]/str(entry["id"])/(digest+".csv"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != raw:
            raise ValueError("Vorhandener unveränderlicher Importsnapshot widerspricht seinem SHA.")
    else:
        try:
            with target.open("xb") as stream:
                stream.write(raw)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise ValueError("Parallel gespeicherter Importsnapshot widerspricht seinem SHA.")
    return target.resolve(), digest


def _identity(entry, candidate):
    if entry.get("quelle") not in {"mql5", "pelik", "zulu"}:
        raise ValueError("Kein freigegebener nativer Positionsimport für diese Quelle.")
    for key in ("quelle", "quellen_uid"):
        if not isinstance(entry.get(key), str) or not entry[key] or candidate.get(key) != entry[key]:
            raise ValueError("Quellenidentität widerspricht dem Importbeleg: " + key)
    for key in ("id", "signal_ref"):
        if _positive_id(entry.get(key)) != _positive_id(candidate.get(key)):
            raise ValueError("Anbieter-/Referenz-ID widerspricht dem Importbeleg.")
    version = entry.get("quelle_version")
    if version != candidate.get("version", candidate.get("quelle_version")):
        raise ValueError("Plattformversion widerspricht dem Importbeleg.")
    allowed = {"mql5": {"mql4", "mql5"}, "pelik": {"pelican"}, "zulu": {"zulu"}}
    if version not in allowed[entry["quelle"]]:
        raise ValueError("Plattformversion passt nicht zur Quelle.")
    if entry.get("trades_path") or entry.get("trades_sha256"):
        raise ValueError("Vorhandener Scanner-Snapshot wird nicht überschrieben.")


def _source_path(entry, candidate):
    path = Path(candidate.get("originalpfad") or "")
    sid, source = str(entry["id"]), entry["quelle"]
    if source == "mql5":
        valid = path.parent.name == entry["quelle_version"] and path.name.endswith("_"+sid+".csv")
    elif source == "pelik":
        valid = path.parent.name == "closed" and path.name == "closed_"+sid+".csv"
    else:
        valid = ((path.name == "trades_"+sid+".csv" and path.parent.name == "trades")
                 or (path.name == "trades.csv" and path.parent.parent.name == sid
                     and path.parent.parent.parent.name == ".generations"
                     and re.fullmatch(r"[0-9a-f-]{36}", path.parent.name)))
    if not valid or not path.is_file() or path.is_symlink():
        raise ValueError("Nativer Dateipfad belegt Anbieter-ID/Plattform nicht.")
    raw = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("sha256") or "")) or _hash(raw) != candidate["sha256"]:
        raise ValueError("Native Datei widerspricht dem vorbereiteten SHA-256.")
    return path.resolve(), raw


def _metadata(path, candidate, raw, count, source):
    expected = (path.with_suffix(".meta") if source == "pelik" else
                path.with_name("archive.meta") if path.name == "trades.csv" else path.with_suffix(".meta"))
    supplied = candidate.get("metaPath")
    if supplied and Path(supplied).resolve() != expected.resolve():
        raise ValueError("Meta-Datei gehört nicht zum ausgewählten nativen Dateisatz.")
    meta_raw = expected.read_bytes()
    if candidate.get("meta_sha256") and _hash(meta_raw) != candidate["meta_sha256"]:
        raise ValueError("Meta-Datei hat sich gegenüber dem Importbeleg geändert.")
    meta = _properties(meta_raw)
    if meta.get("version") != "1" or meta.get("count") != str(count) or meta.get("sha256") != _hash(raw):
        raise ValueError("Nativer Version-/Anzahl-/SHA-Beleg ist ungültig.")
    if source == "zulu" and (int(meta.get("requested", "0")) <= 0 or count > int(meta["requested"])):
        raise ValueError("Zulu-Anzahl widerspricht dem nativen Anforderungsbeleg.")
    return {"path": str(expected.resolve()), "sha256": _hash(meta_raw), "werte": meta}


def _catalog(path, sid, id_column, currency_column):
    raw = path.read_bytes()
    _header, rows = _rows(raw)
    matches = [row for row in rows if row.get(id_column) == str(sid)]
    if len(matches) > 1:
        raise ValueError("Anbieter-ID ist im nativen Katalog mehrdeutig.")
    row = matches[0] if matches else None
    currency = str((row or {}).get(currency_column) or "").strip().upper()
    if currency in {"NULL", "UNKNOWN", "NONE"}:
        currency = ""
    return row, currency, {"path": str(path.resolve()), "sha256": _hash(raw),
                           "anbieter_im_katalog": row is not None}


def _mql_context(entry, candidate, source_path):
    metrics = source_path.with_name(source_path.stem+"_root.txt")
    if candidate.get("metricsPath") and Path(candidate["metricsPath"]).resolve() != metrics.resolve():
        raise ValueError("MQL-Metrics gehören zu einem anderen Dateisatz.")
    raw = metrics.read_bytes()
    if candidate.get("metrics_sha256") and _hash(raw) != candidate["metrics_sha256"]:
        raise ValueError("MQL-Metrics haben sich gegenüber dem Importbeleg geändert.")
    values = {}
    for line in raw.decode("utf-8-sig").splitlines():
        text = line.strip()
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        if not value and key != "MonthProfitProz":
            break
        values[key] = value.strip()
    currency = str(values.get("Currency") or "").upper()
    if not re.fullmatch("[A-Z]{3}", currency):
        raise ValueError("MQL-Geldwährung ist im gleichen Metrics-Dateisatz nicht belegt.")
    if candidate.get("currency") and str(candidate["currency"]).upper() != currency:
        raise ValueError("MQL-Geldwährung widerspricht dem Importbeleg.")
    return currency, values.get("Broker") or values.get("BrokerServer"), {
        "path": str(metrics.resolve()), "sha256": _hash(raw), "currency": currency,
        "broker": values.get("Broker") or values.get("BrokerServer")}


def _history(entry, candidate, source_path, digest, count):
    if entry["quelle"] == "pelik":
        return None, {"grund": "Native SHA/Anzahl belegt Dateiintegrität, keine vollständige Plattformhistorie."}
    if entry["quelle"] == "mql5":
        receipt = entry.get("refresh") or {}
        supplied = candidate.get("full_history_beleg") or {}
        valid = (receipt.get("fullHistory") is True and receipt.get("platformRefreshed") is True
                 and str(receipt.get("providerId")) == str(entry["id"])
                 and receipt.get("version") == entry["quelle_version"] and receipt == supplied)
        if valid:
            try:
                valid = source_path.stat().st_mtime <= _stamp(receipt["refreshedAt"]).timestamp()
            except (ValueError, KeyError):
                valid = False
        return (True if valid else None), {"receipt": receipt if valid else None,
            "grund": ("Historischer nativer FullHistory-Refresh mit passender ID/Version; Datei seit Empfang nicht neuer. "
                      "Der alte Receipt enthält keinen Datei-SHA; aktueller SHA wird getrennt eingefroren."
                      if valid else "Kein zur Datei passender nativer Vollhistorien-Receipt.")}
    receipt_path = (source_path.with_name("history.receipt") if source_path.name == "trades.csv"
                    else source_path.with_suffix(".history"))
    if candidate.get("receiptPath") and Path(candidate["receiptPath"]).resolve() != receipt_path.resolve():
        raise ValueError("Zulu-Empfangsbeleg gehört zu einem anderen Dateisatz.")
    if not receipt_path.is_file():
        return None, {"grund": "Kein nativer Zulu-Empfangsbeleg; SHA allein belegt keinen Vollumfang."}
    raw = receipt_path.read_bytes()
    receipt = _properties(raw)
    valid = (receipt.get("version") == "1" and receipt.get("provider") == str(entry["id"])
             and receipt.get("sha256") == digest and receipt.get("complete") in {"true", "false"}
             and -1 <= int(receipt.get("total", "-2"))
             and 0 <= int(receipt.get("downloaded", "-1")) <= count
             and int(receipt.get("pages", "0")) >= 1)
    _stamp(receipt.get("observed"))
    if not valid:
        raise ValueError("Zulu-Empfangsbeleg widerspricht ID/Datei/Anzahl.")
    complete = receipt["complete"] == "true"
    if int(receipt["total"]) > count:
        complete = False
    return complete, {"path": str(receipt_path.resolve()), "sha256": _hash(raw), "receipt": receipt,
                       "grund": "Nativer ID-/Datei-SHA-gebundener Paginationsempfang; kein neuer Abruf."}


def _positions(entry, candidate, path, raw):
    source = entry["quelle"]
    _header, rows = _rows(raw, [PELICAN_HEADER] if source == "pelik" else [ZULU_HEADER, ZULU_HEADER[:15]])
    if not rows:
        raise ValueError("Native Positionsliste ist leer.")
    meta = _metadata(path, candidate, raw, len(rows), source)
    if candidate.get("tradecount", candidate.get("rowcount")) not in (None, len(rows)):
        raise ValueError("Native Positionszahl hat sich gegenüber dem Importbeleg geändert.")
    data_dir = path.parents[2] if source == "pelik" else next(
        (p.parent for p in path.parents if p.name == "trades"), None)
    if data_dir is None:
        raise ValueError("Nativer Katalogpfad ist nicht eindeutig.")
    catalog = data_dir/("providers.csv" if source == "pelik" else "traders.csv")
    supplied = candidate.get("metricsPath")
    if supplied and Path(supplied).resolve() != catalog.resolve():
        raise ValueError("Katalog gehört nicht zum nativen Dateisatz.")
    provider, catalog_currency, metadata = _catalog(
        catalog, entry["id"], "Id" if source == "pelik" else "ProviderId", "Waehrung" if source == "pelik" else "Waehrung")
    currencies = {str(row["Waehrung"]).strip().upper() for row in rows} if source == "pelik" else {catalog_currency}
    if len(currencies) != 1 or not re.fullmatch("[A-Z]{3}", next(iter(currencies), "")):
        raise ValueError("Keine eindeutige belegte native Geldwährung; gemischte Währungen benötigen ein eigenes Umrechnungsmodell.")
    currency = next(iter(currencies))
    if catalog_currency and catalog_currency != currency:
        raise ValueError("Zeilenwährung widerspricht der gleichen nativen Anbieteridentität im Katalog.")
    if candidate.get("currency") and str(candidate["currency"]).upper() != currency:
        raise ValueError("Native Geldwährung widerspricht dem Importbeleg.")
    ids, servers = set(), set()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(parser.POSITION_HEADER)
    for index, row in enumerate(rows, 2):
        trade_id = row["TradeId"]
        if not trade_id or trade_id in ids:
            raise ValueError(f"Leere oder doppelte native Trade-ID in Zeile {index}.")
        ids.add(trade_id)
        if source == "zulu" and row["ProviderId"] != str(entry["id"]):
            raise ValueError("Zulu-Position gehört zu einer anderen Anbieter-ID.")
        symbol = row["Instrument" if source == "pelik" else "Währungspaar"]
        direction = row["Richtung" if source == "pelik" else "Typ"].casefold()
        if not symbol or any(x in symbol for x in ";\r\n") or direction not in {"buy", "sell"}:
            raise ValueError(f"Native Position in Zeile {index} hat kein belegtes Symbol/Richtung.")
        volume = row["Menge" if source == "pelik" else "Lots"]
        opened = row["Eroeffnet" if source == "pelik" else "Eröffnet"]
        closed = row["Geschlossen"]
        entry_price = row["OpenPrice" if source == "pelik" else "Eröffnungskurs"]
        exit_price = row["ClosePrice" if source == "pelik" else "Schlusskurs"]
        net = row["RealisierterProfit" if source == "pelik" else "NettoPnL"]
        for value in (volume, entry_price, exit_price):
            _number(value, positive=True)
        _number(net)
        first, last = _time(opened), _time(closed)
        if last < first:
            raise ValueError("Nativer Positionsschluss liegt vor der Eröffnung.")
        if source == "pelik" and row["Server"]:
            servers.add(row["Server"])
        # Same row order, native lots, native local seconds and supplied net.
        # Separate commission/swap are not supplied; net remains one amount.
        writer.writerow((first.strftime(parser.TIME_FMT), direction.title(), volume,
                         symbol.replace("/", "") if source == "zulu" else symbol,
                         entry_price, volume, last.strftime(parser.TIME_FMT), exit_price, "0", "0", net))
    broker = (next(iter(servers)) if len(servers) == 1 else None) if source == "pelik" else (
        (provider or {}).get("Broker") or None)
    metadata.update(currency=currency, broker=broker, broker_server_kandidaten=sorted(servers),
                    native_trade_ids_sha256=_hash("\n".join(row["TradeId"] for row in rows).encode("utf-8")))
    return output.getvalue().encode("utf-8"), len(rows), currency, broker, meta, metadata


def prepare_candidate(entry, candidate, *, out_dir=None):
    """Return an updated copy; persist only immutable local snapshot files.

    Success: ``native_cache_import.status == 'uebernommen'``. Gaps keep the
    entry's original fields and return an auditable reason. Source/store rows
    are never changed. A mixed-money export stays a gap rather than lose rows.
    """
    result = deepcopy(entry)
    audit = {"version": VERSION, "status": "datenluecke", "grund": "",
             "vorbereitet_am": datetime.now(timezone.utc).isoformat(),
             "quelle": entry.get("quelle"), "quellen_uid": entry.get("quellen_uid"),
             "signal_ref": entry.get("signal_ref"), "id": entry.get("id"),
             "quelle_version": entry.get("quelle_version"), "keine_neue_plattformfrische": True}
    result["native_cache_import"] = audit
    try:
        _identity(entry, candidate)
        source_path, raw = _source_path(entry, candidate)
        base = Path(out_dir) if out_dir is not None else config.DATA_DIR/"abonnenten_analyse"/"native_cache_import"
        original, raw_sha = _snapshot(base, entry, raw, "original")
        audit.update(originalpfad=str(source_path), original_sha256=raw_sha, original_snapshot_path=str(original),
                     sourceTimestamp=deepcopy(candidate.get("sourceTimestamp")))
        if entry["quelle"] == "mql5":
            normalized, count = raw, None
            currency, broker, metadata = _mql_context(entry, candidate, source_path)
            meta = None
            target, digest = original, raw_sha
        else:
            normalized, count, currency, broker, meta, metadata = _positions(entry, candidate, source_path, raw)
            target, digest = _snapshot(base, entry, normalized, "normalisiert")
        parsed = parser.load_export(target)
        if not parsed.trades:
            raise ValueError("Snapshot enthält keine abgeschlossenen Einzelpositionen.")
        count = len(parsed.trades) if count is None else count
        expected = candidate.get("tradecount", candidate.get("rowcount"))
        if len(parsed.trades) != count or expected not in (None, count):
            raise ValueError("Konvertierung verliert Positionen oder widerspricht der belegten Anzahl.")
        full, history = _history(entry, candidate, source_path, raw_sha, count)
        old_stats = deepcopy(entry.get("quellen_stats") or {})
        old_stats.update(account_currency=currency, broker_server=broker,
                         quelle_trade_history_complete=full, quelle_trades_history_complete=full,
                         quelle_trades_stored=count, quelle_trades_gekappt=full is False)
        result.update(trades_path=str(target), trades_sha256=digest, trades=count,
                      zeit_von=min(t.open_time for t in parsed.trades).isoformat(),
                      zeit_bis=max(t.close_time for t in parsed.trades).isoformat(),
                      trade_money_currency=currency, account_currency=currency,
                      netto_quellwaehrung=parsed.net_total, quellen_stats=old_stats,
                      trade_history_complete=full,
                      trade_history_status="vollstaendig" if full is True else "teilweise" if full is False else "unbekannt",
                      trade_history_reason=history["grund"])
        audit.update(status="uebernommen", grund="Vorhandener nativer Dateistand ohne Quellenabruf als Snapshot ergänzt.",
                     snapshot_sha256=digest, snapshot_path=str(target), tradecount=count,
                     native_geldwaehrung=currency, metadaten=metadata, native_meta=meta,
                     full_history_beleg=history, trade_history_complete=full,
                     formatkonvertierung=entry["quelle"] != "mql5", zeilenreihenfolge_unveraendert=True,
                     geldumrechnung=False,
                     netto_semantik="Geliefertes Netto unverändert; Kommission/Swap bei Pelican/Zulu nicht separat aufgeschlüsselt.")
        return result
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError, UnicodeError) as error:
        audit["grund"] = f"{type(error).__name__}: {error}"
        return result
