"""Frozen subscriber trends from identity-bound native history GETs.

No source update, catalog refresh, scanner history or scoring is performed.
The read time is recorded separately from the native measurement timestamps.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from . import db, quellen
from .abonnenten_analyse_ki import Angehalten
from .abonnenten_analyse_store import now

SNAPSHOT_VERSION = 1
TOLERANCE_DAYS = 3


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _as_of(value):
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Trend-Stichtag muss ein Datum mit Zeitzone sein")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Trend-Stichtag benötigt eine explizite Zeitzone")
    return stamp


def _timestamp(value, assumed_timezone):
    if isinstance(value, bool):
        raise ValueError("Ungültiger nativer Messzeitpunkt")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Ungültiger nativer Messzeitpunkt")
        # Native numeric history timestamps are Unix milliseconds.
        return datetime.fromtimestamp(value / 1000, timezone.utc), False
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Nativer Messzeitpunkt fehlt")
    stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    naive = stamp.tzinfo is None or stamp.utcoffset() is None
    return (stamp.replace(tzinfo=assumed_timezone) if naive else stamp), naive


def _empty(as_of, reason):
    return {
        "as_of": as_of.isoformat(timespec="seconds"), "status": "unbekannt",
        "verified": False, "grund": reason, "aktuell": None, "aktuell_ts": None,
        "messalter_tage": None, "delta_7": None, "delta_7_pct": None,
        "delta_30": None, "delta_30_pct": None,
        "basis_7": None, "basis_7_ts": None, "basis_30": None, "basis_30_ts": None,
        "messabstand_7_tage": None, "messabstand_30_tage": None,
        "coverage": {"7_tage": False, "30_tage": False, "punkte": 0,
                     "ungueltige_punkte": 0, "zukuenftige_punkte": 0,
                     "doppelte_punkte": 0, "naive_zeitpunkte": 0},
        "zeitannahme": "Zeitpunkte ohne Zeitzone verwenden den expliziten Offset des Stichtags.",
        "punkte": [],
    }


def trend_from_points(points, as_of):
    """Compute 7/30-day differences at one fixed, timezone-aware cut-off.

    Both the baseline's distance from ``as_of - window`` and the actual
    baseline/latest measurement distance must be within three days. A stale
    latest observation therefore cannot turn two days of growth into a
    seven-day trend. Missing baselines and zero percentage denominators stay
    unknown. Numeric native timestamps are Unix milliseconds.
    """
    cut_off = _as_of(as_of)
    result = _empty(cut_off, "Keine nativen Historienmesspunkte vorhanden.")
    if not isinstance(points, list):
        result["grund"] = "Native Historie ist keine Punkteliste."
        return result
    values, identities, conflict = {}, {}, False
    for point in points:
        if not isinstance(point, Mapping):
            result["coverage"]["ungueltige_punkte"] += 1
            continue
        # An explicitly mixed response is never silently combined. The GET
        # wrapper additionally binds these optional claims to its requested ID.
        for key in ("providerId", "signalId", "version", "quelle_version", "quellen_uid", "quelle"):
            if point.get(key) is not None:
                identities.setdefault(key, set()).add(str(point[key]))
        try:
            count = point.get("subscribers")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Ungültiger Abonnentenzähler")
            stamp, naive = _timestamp(point.get("timestamp", point.get("ts")), cut_off.tzinfo)
            stamp = stamp.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            result["coverage"]["ungueltige_punkte"] += 1
            continue
        if stamp > cut_off:
            result["coverage"]["zukuenftige_punkte"] += 1
            continue
        result["coverage"]["naive_zeitpunkte"] += int(naive)
        if stamp in values:
            if values[stamp] != count:
                conflict = True
            else:
                result["coverage"]["doppelte_punkte"] += 1
        values[stamp] = count
    if conflict or any(len(claims) > 1 for claims in identities.values()):
        result["grund"] = ("Widersprüchliche Zähler zum gleichen Messzeitpunkt." if conflict else
                           "Native Historie vermischt verschiedene Anbieter, Quellen oder Versionen.")
        return result
    ordered = sorted(values.items())
    result["coverage"]["punkte"] = len(ordered)
    result["punkte"] = [{"timestamp": ts.isoformat(timespec="seconds"), "subscribers": value}
                        for ts, value in ordered]
    if not ordered:
        if result["coverage"]["ungueltige_punkte"]:
            result["grund"] = "Keine gültigen nativen Messpunkte am oder vor dem Stichtag."
        return result
    latest, current = ordered[-1]
    result.update(aktuell=current, aktuell_ts=latest.isoformat(timespec="seconds"),
                  messalter_tage=(cut_off-latest).total_seconds()/86400)
    reasons = []
    for days in (7, 30):
        target = cut_off-timedelta(days=days)
        candidates = [(stamp, count) for stamp, count in ordered
                      if stamp < latest
                      and abs((stamp-target).total_seconds()) <= TOLERANCE_DAYS*86400
                      and abs((latest-stamp).total_seconds()/86400-days) <= TOLERANCE_DAYS]
        if not candidates:
            reasons.append(f"Kein belegter {days}-Tage-Vergleich innerhalb ±{TOLERANCE_DAYS} Tagen.")
            continue
        # Earlier timestamp breaks an equidistant tie deterministically.
        baseline, count = min(candidates, key=lambda pair: (abs((pair[0]-target).total_seconds()), pair[0]))
        result.update({f"basis_{days}": count, f"basis_{days}_ts": baseline.isoformat(timespec="seconds"),
                       f"messabstand_{days}_tage": (latest-baseline).total_seconds()/86400,
                       f"delta_{days}": current-count,
                       f"delta_{days}_pct": (current-count)/count*100 if count > 0 else None})
        result["coverage"][f"{days}_tage"] = True
        if count == 0:
            reasons.append(f"{days}-Tage-Prozentänderung bei Ausgangsbestand null nicht bestimmbar.")
    if result["coverage"]["ungueltige_punkte"]:
        reasons.append("Ungültige native Messpunkte; Trendverifikation gesperrt.")
    result["verified"] = bool(result["coverage"]["7_tage"]
                              and not result["coverage"]["ungueltige_punkte"])
    windows = sum(bool(result["coverage"][f"{days}_tage"]) for days in (7, 30))
    result["status"] = "ok" if windows == 2 and not reasons else "teilweise" if windows else "unbekannt"
    result["grund"] = " ".join(reasons) or "Native Vergleichsmesspunkte für 7 und 30 Tage belegt."
    return result


def _identity(entry):
    identity = {key: entry.get(key) for key in
                ("signal_ref", "quellen_uid", "id", "quelle", "quelle_version", "platform")}
    for key in ("signal_ref", "id"):
        if isinstance(identity[key], bool) or not isinstance(identity[key], int) or identity[key] <= 0:
            raise ValueError("Native Trendabfrage ohne eindeutige Anbieteridentität")
    for key in ("quellen_uid", "quelle", "quelle_version"):
        if not isinstance(identity[key], str) or not identity[key].strip():
            raise ValueError("Native Trendabfrage ohne Quellen-/Versionsbindung")
    identity["quelle"] = db.kanonische_quelle(identity["quelle"])
    return identity


def _check_point_identity(points, identity):
    if not isinstance(points, list):
        raise ValueError("Native Historie ist keine Punkteliste")
    claims = {"providerId": str(identity["id"]), "signalId": str(identity["id"]),
              "version": identity["quelle_version"], "quelle_version": identity["quelle_version"],
              "quellen_uid": identity["quellen_uid"], "quelle": identity["quelle"]}
    for point in points:
        if not isinstance(point, Mapping):
            continue
        for key, expected in claims.items():
            if point.get(key) is not None and str(point[key]) != expected:
                raise ValueError(f"Native Historie gehört zu anderer Identität/Version ({key})")


def freeze_trends(store, run_id, entries, settings, log, stopped, *, include_all=False):
    """Freeze eligible complete entries' native histories; reuse exact snapshots.

    ``include_all=True`` explicitly includes every selected positive-counter
    identity, regardless of trade-analysis eligibility, missing data or Robo's
    separate source-profit view. The default remains the finalist scope.
    Only ``client.history(id, version)`` performs network access. An unavailable
    native response is frozen as unknown, never replaced by current catalog
    counters or scanner-generated history. Every resume keeps the first
    snapshot's cut-off and its individual finished attempts, including errors.
    """
    if type(include_all) is not bool:
        raise ValueError("include_all muss boolesch sein")
    run = store.read(run_id)
    if not run:
        raise ValueError("Unbekannter Rechercheauftrag für den Trend-Snapshot")
    snapshot = deepcopy(run.get("abo_trend_snapshot"))
    if snapshot is None:
        snapshot = {"version": SNAPSHOT_VERSION, "as_of": now(), "created_at": now(),
                    "status": "laeuft", "entries": {}}
        store.update(run_id, abo_trend_snapshot=snapshot)
    if (not isinstance(snapshot, dict) or snapshot.get("version") != SNAPSHOT_VERSION
            or not isinstance(snapshot.get("entries"), dict)):
        raise ValueError("Ungültiger nativer Trend-Snapshot")
    cut_off = _as_of(snapshot.get("as_of"))
    source_map, clients = None, {}
    for entry in entries:
        if include_all:
            count = entry.get("abonnenten")
            if type(count) is not int or count <= 0:
                continue
        elif not entry.get("data_done") or not entry.get("eligible"):
            continue
        if stopped():
            raise Angehalten("Stop angefordert; native Trend-Snapshots bleiben erhalten")
        identity = _identity(entry)
        key = str(identity["signal_ref"])
        checkpoint = snapshot["entries"].get(key)
        if checkpoint is not None:
            saved = entry.get("abo_trend")
            if (not isinstance(saved, dict) or saved.get("identitaet") != identity
                    or saved.get("as_of") != cut_off.isoformat(timespec="seconds")
                    or checkpoint.get("identitaet") != identity
                    or checkpoint.get("sha256") != _digest(saved)):
                raise ValueError(f"Nativer Trend-Snapshot für {key} verändert oder fremd")
            continue
        if source_map is None:
            source_map = {}
            for source in db.list_quellen(nur_aktiv=True):
                source_map.setdefault(db.kanonische_quelle(source["kuerzel"]), []).append(source)
        fetched_at = now()
        try:
            matches = [source for source in source_map.get(identity["quelle"], [])
                       if source.get("quellen_uid") == identity["quellen_uid"]]
            if len(matches) != 1:
                raise ValueError("Aktive native Quelle ist nicht eindeutig an die Quellen-UID gebunden")
            source = matches[0]
            client_key = identity["quellen_uid"]
            if client_key not in clients:
                clients[client_key] = quellen.client_fuer_quelle(source)
            points = clients[client_key].history(identity["id"], identity["quelle_version"])
            if stopped():
                raise Angehalten("Stop angefordert; native Trend-Snapshots bleiben erhalten")
            _check_point_identity(points, identity)
            trend = trend_from_points(points, cut_off)
        except Angehalten:
            raise
        except Exception as error:
            trend = _empty(cut_off, f"Native Historie nicht belegbar: {type(error).__name__}: {error}")
        trend.update(identitaet=identity, fetched_at=fetched_at, quelle="native_history_get",
                     endpoint=f"/providers/{identity['id']}/{identity['quelle_version']}/history",
                     messhinweis="GET-Zeit ist keine Messfrische; Zähler- und Trenddaten belegen keine Kennzahlenfrische.")
        entry["abo_trend"] = trend
        store.save_task(run_id, entry)
        snapshot["entries"][key] = {"identitaet": identity, "sha256": _digest(trend),
                                     "status": trend["status"], "verified": trend["verified"]}
        store.update(run_id, abo_trend_snapshot=deepcopy(snapshot))
        log(f"Abonnententrend {identity['quelle']}:{identity['id']}: {trend['status']}; {trend['grund']}")
    snapshot["status"] = "fertig"
    snapshot["finished_at"] = snapshot.get("finished_at") or now()
    store.update(run_id, abo_trend_snapshot=deepcopy(snapshot))
    return snapshot
