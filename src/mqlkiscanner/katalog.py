# -*- coding: utf-8 -*-
"""Vollkatalog der Datenquellen-Clients für die Übersicht „Alle Signale“.

Nutzer-Wunsch 08.10.2026: Die Übersicht soll ALLES zeigen, was die Clients
(VantageMonitor & Co.) melden — der Workflow-Vorfilter (Mindestalter,
Mindestabo) bleibt bewusst beim Scan (pipeline.build_candidates). Hier
läuft deshalb eine EIGENE Katalog-Tabelle (db.katalog_signale), unabhängig
von `signals`: Die Workflow-DB (Forensik, KI, Server-Sync) wird nicht mit
reinen Katalogzeilen überklebert.

Umfang bewusst klein: Der Sync schreibt nur die Katalog-Metadaten (Name,
Abonnenten, Wochen, Risiko). Trades und Kennzahlen werden NICHT für alle
Katalogzeilen gezogen (über 1.200 Provider × bis zu 170 KB) — die Seite
lädt sie on demand für das gerade ausgewählte Signal (hole_trades/
hole_metrics, gecacht in quellen_artefakte), sodass Detailansicht und
Equity-Studie (realer Drawdown) für JEDES gemeldete Signal laufen.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from . import db, downloader_client, ingest, pipeline, quellen
from .signal_identity import identity_key


def _normalisiere(items: list[dict]) -> list[dict]:
    """Roh-Katalogitems der Downloader-API → Zeilen für katalog_signale."""
    out = []
    for item in items:
        try:
            signal_id = int(str(item.get("signalId", "")).strip())
        except (TypeError, ValueError):
            continue
        version = str(item.get("version") or "").strip()
        out.append({
            "signal_id": signal_id,
            "name": str(item.get("signalName") or signal_id),
            "platform": ingest._PLATTFORM.get(version, ""),
            "url": str(item.get("url")
                       or f"https://www.mql5.com/en/signals/{signal_id}"),
            "version": version,
            "abonnenten": ingest._zahl(item.get("subscribers")),
            "wochen": ingest._zahl(item.get("weeks")),
            "risiko": (str(item.get("risk"))
                       if item.get("risk") is not None else None),
        })
    return out


def sync(log=None, *, kuerzel: str | None = None) -> dict:
    """Kataloge ALLER aktiven Datenquellen ziehen und in katalog_signale schreiben.

    Eine nicht erreichbare Quelle bricht den Lauf NICHT ab — der Fehler
    wird je Quelle vermerkt (db.katalog_sync_vermerken, auch mit Fehler —
    sonst würde der Auto-Sync bei jedem Seitenstart erneut versuchen) und
    im Summary geliefert. Rückgabe:
    {"quellen": {kuerzel: {"anzahl", "geloescht", "fehler", "gelaufen_am"}},
     "gesamt": int}
    Mit `kuerzel` nur eine einzige Quelle synchronisieren (Button je Quelle).
    """
    def _log(text: str) -> None:
        if log:
            log(text)

    db.init_db()
    # Parität mit kandidaten_aus_quellen: Legacy-Konfiguration (einzelner
    # Downloader vor Multi-Source) einmalig in die Quellen-Tabelle übernehmen
    # — sonst bliebe der Katalog auf Frischinstallation leer.
    quellen._ensure()
    quellen_aktiv = db.list_quellen(nur_aktiv=True)
    if kuerzel:
        kuerzel = db.kanonische_quelle(kuerzel)
        quellen_aktiv = [q for q in quellen_aktiv
                        if db.kanonische_quelle(q["kuerzel"]) == kuerzel]
    summary: dict = {"quellen": {}, "gesamt": 0}
    for quelle in quellen_aktiv:
        eintrag = {"anzahl": 0, "geloescht": 0, "fehler": None}
        try:
            # The overview includes known zero-audience providers. This
            # metadata request must not broaden the scan/trade-download scope.
            items = _normalisiere(ingest.hole_katalog(quelle, min_subscribers=0))
            gespeichert, geloescht = db.katalog_upsert_many(
                quelle["kuerzel"], items)
            eintrag["anzahl"] = gespeichert
            eintrag["geloescht"] = geloescht
            _log(f"Katalog {quelle['kuerzel']}: {gespeichert} Signale "
                 f"übernommen, {geloescht} rausgefallen.")
        except Exception as exc:  # nicht nur DownloaderError — auch kaputte
            # JSON-Antworten/DB-Fehler sollen den Sync der ANDEREN Quellen
            # nicht abbrechen und keinen Auto-Sync-Retry-Loop erzeugen.
            eintrag["fehler"] = str(exc)
            _log(f"Katalog {quelle['kuerzel']} nicht ladbar — {exc}")
        db.katalog_sync_vermerken(quelle["kuerzel"], eintrag["anzahl"],
                                  eintrag["fehler"])
        eintrag["gelaufen_am"] = db.katalog_sync_status().get(
            db.kanonische_quelle(quelle["kuerzel"]), {}).get("gelaufen_am")
        summary["quellen"][quelle["kuerzel"]] = eintrag
        summary["gesamt"] += eintrag["anzahl"]
    return summary


def signal_identitaet(result) -> tuple[str, int]:
    """Source-scoped display identity; numeric IDs are not globally unique."""
    return identity_key(result)


def mehrdeutige_ids(identitaeten) -> set[int]:
    quellen: dict[int, set[str]] = {}
    for quelle, signal_id in identitaeten:
        quellen.setdefault(int(signal_id), set()).add(str(quelle or "mql5"))
    return {sid for sid, namen in quellen.items() if len(namen) > 1}


def _transport_index(rows) -> dict:
    """Explicit UID mirrors share their owner's canonical source namespace."""
    result = {}
    # Prefer active transports, preserving DB order within each group.
    for row in sorted(rows, key=lambda q: not q.get("aktiv", True)):
        result.setdefault(db.kanonische_quelle(row["kuerzel"]), row)
    return result


def katalog_resultate(*, gescannt=None, studien=None, progress=None,
                     katalog_rows=None, quellen_rows=None, artefakte=None) -> tuple[list, dict]:
    """Katalogzeilen als leichtgewichtige ScanResults für die Übersicht.

    Gescannte Signale (signals-Tabelle) GEWINNEN — sie sind hier dedupliert
    raus und erscheinen weiter über results_from_db. Dedupliziert wird
    ausschließlich dieselbe (Quelle, ID); andere Quellen bleiben sichtbar.
    Bereits gecachte
    Trades/Kennzahlen (quellen_artefakte) werden mitgeliefert — Zeilen MIT
    Trades rechnen damit sofort echte Statistiken, die anderen lassen sich
    per Button nachladen. Rückgabe (resultate, stats_je_quelle_und_id).
    """
    db.init_db()
    gescannt = ({signal_identitaet(row) for row in db.list_catalog()}
                if gescannt is None else set(gescannt))
    # Preserve the old explicitly supplied numeric exclusion interface.
    # Production callers pass source-scoped identities.
    legacy_ids = {sid for sid in gescannt if isinstance(sid, int)}
    gescannt = {key for key in gescannt if isinstance(key, tuple)}
    for sid in legacy_ids:
        owner = db.resolve_identity(sid)
        if owner is not None:
            gescannt.add(identity_key(owner))
    quellen_nach_kuerzel = _transport_index(
        db.list_quellen() if quellen_rows is None else quellen_rows)
    resultate: list = []
    stats_je_id: dict[tuple[str, int], dict] = {}
    gesehen: set[tuple[str, int]] = set()
    zeilen = db.katalog_list() if katalog_rows is None else katalog_rows
    mehrdeutig = mehrdeutige_ids(gescannt | {signal_identitaet(z) for z in zeilen})
    artefakte = db.list_quellen_artefakte() if artefakte is None else artefakte
    if progress:
        progress(0, len(zeilen))
    for nr, zeile in enumerate(zeilen, 1):
        if progress:
            progress(nr - 1, len(zeilen))
        signal_id = int(zeile["signal_id"])
        kuerzel = str(zeile.get("quelle") or "mql5")
        identitaet = (kuerzel, signal_id)
        if identitaet in gescannt or identitaet in gesehen:
            continue
        gesehen.add(identitaet)
        res = pipeline.ScanResult(
            id=signal_id,
            name=zeile.get("name") or str(signal_id),
            platform=zeile.get("platform") or "",
            url=zeile.get("url") or "",
            abonnenten=zeile.get("abonnenten"),
            wochen=zeile.get("wochen"),
            quelle=kuerzel or "mql5",
            signal_ref=zeile.get("signal_ref"),
            quellen_uid=zeile.get("quellen_uid") or "",
            herkunft="Katalog",
        )
        quelle = quellen_nach_kuerzel.get(kuerzel)
        if (quelle is not None and res.quellen_uid and quelle.get("quellen_uid")
                and quelle["quellen_uid"] != res.quellen_uid):
            quelle = None
        version = str(zeile.get("version") or "")
        if quelle is not None and version:
            res.quelle_id = int(quelle["id"])
            res.quelle_version = version
            trades = artefakte.get((int(quelle["id"]), signal_id, version, "trades"))
            if trades and trades.get("path") and Path(trades["path"]).exists():
                res.trades_path = str(trades["path"])
                res.trades_sha256 = trades.get("sha256") or ""
                metrics = artefakte.get((int(quelle["id"]), signal_id, version, "metrics"))
                if metrics and metrics.get("path") \
                        and Path(metrics["path"]).exists():
                    stats = _metrics_aus_artefakt(res, version, metrics)
                    stats_je_id[identitaet] = stats
                    res.dd_equity_pct = stats.get("dd_equity_pct")
                    res.ertrag_monat_pct = stats.get("monthly_growth_pct")
                    res.broker_server = stats.get("broker_server")
                    res.account_currency = stats.get("account_currency")
        resultate.append(res)
    # Batch-Equity-Studien („Lücken füllen", Nutzer 08.10.2026): True-DD,
    # TrueRetDD-Familie und True-DD USD in die Katalog-Zeilen mappen —
    # Forensik gibt es hier nicht, die Studie gewinnt immer (SHA-geschützt).
    studien = db.list_equity_studien(identitaeten=True) if studien is None else studien
    for res in resultate:
        pipeline.studie_anwenden(res, studien)
    if progress:
        progress(len(zeilen), len(zeilen))
    return resultate, stats_je_id


def metrics_stats(result) -> dict:
    """Gecachte Quellen-Kennzahlen als Stats-Formular (leer ohne Cache/Fehler).

    Workflow-Zeilen tragen oft nur das Quellen-Kuerzel. Wie beim Nachladen
    wird dann die genaue Quelle/Version aus ihrem Katalogeintrag aufgeloest.
    Kein Ersatz durch andere Quellen oder widersprechende Plattformversionen.
    """
    try:
        ref = quellen_referenz(result)
    except ValueError:
        return {}
    if ref is None:
        return {}
    quelle_id, version = ref
    bekannte_version = str(getattr(result, "quelle_version", "") or "")
    platform = str(getattr(result, "platform", "") or "").casefold()
    if not version or (bekannte_version and bekannte_version != version):
        return {}
    if platform and ingest._PLATTFORM.get(version, platform) != platform:
        return {}
    artefakt = db.get_quellen_artefakt(int(quelle_id), int(result.id),
                                       version, "metrics")
    return _metrics_aus_artefakt(result, version, artefakt)


def _metrics_aus_artefakt(result, version, artefakt) -> dict:
    """Exakte Identitaet und registrierte Bytes pruefen, ohne DB-Zugriff."""
    if not artefakt or not artefakt.get("path") \
            or not Path(artefakt["path"]).exists():
        return {}
    try:
        inhalt = Path(artefakt["path"]).read_bytes()
        if artefakt.get("sha256") != hashlib.sha256(inhalt).hexdigest():
            return {}
        antwort = json.loads(inhalt.decode("utf-8"))
        if not isinstance(antwort, dict):
            return {}
        if antwort.get("version") and str(antwort["version"]) != version:
            return {}
        if antwort.get("signalId") is not None \
                and int(antwort["signalId"]) != int(result.id):
            return {}
        return ingest.metrics_zu_stats(
            antwort,
            quelle_kuerzel=str(getattr(result, "quelle", "") or ""),
            quelle_version=version)
    except (OSError, TypeError, ValueError):
        return {}


def workflow_stats_bulk(resultate, workflow_stats, *, katalog_rows=None,
                        quellen_rows=None, artefakte=None) -> dict:
    """Frische Quellenstats nur auf identischem Trade-Snapshot ergaenzen.

    Katalogmetadaten duerfen aktuell sein. Rechenbasis und Positionsanzahl
    duerfen dagegen nie aus einem neueren/fremden Export stammen. Diese
    Anzeige aktualisiert weder Workflow-Urteil noch gespeicherte Studien.
    """
    zeilen = db.katalog_list() if katalog_rows is None else katalog_rows
    quellen_rows = db.list_quellen() if quellen_rows is None else quellen_rows
    artefakte = db.list_quellen_artefakte() if artefakte is None else artefakte
    katalog_index = {(str(z['quelle']), int(z['signal_id'])): z for z in zeilen}
    quellen_index = _transport_index(quellen_rows)
    resultate = list(resultate)
    counts = Counter(int(r.id) for r in resultate)
    out = {}
    for res in resultate:
        key = identity_key(res)
        if counts[int(res.id)] > 1 and int(res.id) in workflow_stats and key not in workflow_stats:
            raise ValueError(f"Kennzahlen für mehrdeutige ID {res.id} benötigen eine Quelle")
        if int(res.id) in workflow_stats and key not in workflow_stats:
            owner = db.resolve_identity(int(res.id))
            if owner is not None and identity_key(owner) != key:
                raise ValueError(f"Kennzahlen für ID {res.id} gehören zu einer anderen Quelle")
        # Older callers may supply ID-keyed stats only for an unambiguous row.
        old = (workflow_stats.get(int(res.id), {})
               if counts[int(res.id)] == 1 else {})
        out[key] = dict(workflow_stats.get(key, old) or {})
    for res in resultate:
        kuerzel = identity_key(res)[0]
        zeile = katalog_index.get((kuerzel, int(res.id)))
        quelle = quellen_index.get(kuerzel)
        if zeile is None or quelle is None:
            continue
        qid = int(quelle['id'])
        uid = getattr(res, 'quellen_uid', '') or ''
        same_uid = bool(uid and uid == quelle.get('quellen_uid'))
        version = str(zeile.get('version') or '')
        if (not version or (uid and quelle.get('quellen_uid') and not same_uid)
                or (res.quelle_id and int(res.quelle_id) != qid and not same_uid)
                or (res.quelle_version and res.quelle_version != version)
                or (res.platform and ingest._PLATTFORM.get(version) != res.platform.casefold())):
            continue
        for feld in ('wochen', 'abonnenten'):
            if zeile.get(feld) is not None:
                setattr(res, feld, zeile[feld])
        trades = artefakte.get((qid, int(res.id), version, 'trades')) or {}
        sha = getattr(res, 'trades_sha256', '') or ''
        if not sha or trades.get('sha256') != sha:
            continue
        try:
            # Cachepfade sind ueberschreibbar; registrierter SHA allein reicht nicht.
            pfade = {str(trades.get('path') or ''), str(res.trades_path or '')}
            if any(not pfad or hashlib.sha256(Path(pfad).read_bytes()).hexdigest() != sha
                   for pfad in pfade):
                continue
        except OSError:
            continue
        frisch = _metrics_aus_artefakt(
            res, version, artefakte.get((qid, int(res.id), version, 'metrics')))
        bisher = out.setdefault(identity_key(res), {})
        if "account_currency" in frisch:
            res.account_currency = frisch["account_currency"]
            bisher["account_currency"] = frisch["account_currency"]
            if frisch["account_currency"] != "USD":
                for feld in ("initial_deposit_usd", "balance_usd", "kapitalbasis_virtual_usd"):
                    bisher[feld] = None
        for feld, wert in frisch.items():
            if feld == 'initial_deposit_usd' and (
                    not isinstance(wert, (int, float)) or isinstance(wert, bool)
                    or not math.isfinite(wert) or wert <= 0):
                continue
            if wert is not None and (feld != 'initial_deposit_usd'
                                     or bisher.get(feld) is None):
                bisher[feld] = wert
    return out


def quellen_referenz(result) -> tuple[int, str] | None:
    """(quelle_id, version) fürs on-demand-Nachladen eines ScanResults.

    Katalog-Zeilen tragen beide Felder. Persistierte Schema-2-Workflows
    loesen ihren belegten Besitzer ueber die exakte Registry-UID auf; ihre
    bekannte Plattform bestimmt die API-Version. Eine Katalogzeile ist
    dafuer nicht erforderlich. Ohne solchen Besitzerbeleg bleibt nur der
    bisherige explizite Katalogvertrag. Keine numerische Besitzervermutung.
    """
    if getattr(result, "quelle_id", None):
        quelle = db.get_quelle(int(result.quelle_id))
        key = identity_key(result)
        if quelle is not None and db.kanonische_quelle(quelle["kuerzel"]) != key[0]:
            raise ValueError("Datenquellen-Verbindung und Signalquelle widersprechen sich.")
        owner = db.resolve_identity(int(result.id), quelle=key[0],
                                    signal_ref=getattr(result, "signal_ref", None))
        uid = getattr(result, "quellen_uid", "") or (owner.quellen_uid if owner else "")
        if owner is not None and uid != owner.quellen_uid:
            raise ValueError("Quellen-UID und Signalquelle widersprechen sich.")
        if quelle is not None and uid and quelle.get("quellen_uid") != uid:
            raise ValueError("Datenquellen-Verbindung und Quellen-UID widersprechen sich.")
        if quelle is None or not quelle.get("aktiv", True):
            alternative = next((q for q in db.list_quellen(nur_aktiv=True)
                                if uid and q.get("quellen_uid") == uid), None)
            quelle = alternative or quelle
        if quelle is None:
            return None
        version = str(getattr(result, "quelle_version", "") or "")
        platform = str(getattr(result, "platform", "") or "")
        if version and platform and downloader_client.platform_version(platform) != version:
            raise ValueError("Datenquellen-Version und Signalplattform widersprechen sich.")
        return int(quelle["id"]), version
    uid = getattr(result, "quellen_uid", "") or ""
    signal_ref = getattr(result, "signal_ref", None)
    if uid or signal_ref is not None:
        key = identity_key(result)
        owner = db.resolve_identity(int(result.id), quelle=key[0], signal_ref=signal_ref)
        if owner is None:
            return None
        if uid and uid != owner.quellen_uid:
            raise ValueError("Quellen-UID und Signalquelle widersprechen sich.")
        version = downloader_client.platform_version(getattr(result, "platform", ""))
        bekannte_version = str(getattr(result, "quelle_version", "") or "")
        if version is None:
            return None
        if bekannte_version and bekannte_version != version:
            raise ValueError("Datenquellen-Version und Signalplattform widersprechen sich.")
        # Explizite Spiegel derselben UID teilen den Besitzer. Wie bisher
        # entscheidet die stabile Registry-Reihenfolge zwischen aktiven
        # Transporten; ein fremder Besitzer mit gleicher Anbieter-ID nie.
        quelle = next((q for q in db.list_quellen(nur_aktiv=True)
                       if q.get("aktiv", True) and q.get("quellen_uid") == owner.quellen_uid), None)
        if quelle is None:
            return None
        if db.kanonische_quelle(quelle["kuerzel"]) != owner.quelle:
            raise ValueError("Datenquellen-Verbindung und Signalquelle widersprechen sich.")
        return int(quelle["id"]), version
    kuerzel = identity_key(result)[0]
    if not kuerzel:
        return None
    zeile = next((z for z in db.katalog_list()
                  if z["quelle"] == kuerzel
                  and int(z["signal_id"]) == int(result.id)), None)
    quelle = _transport_index(db.list_quellen()).get(kuerzel)
    if zeile is None or quelle is None:
        return None
    return int(quelle["id"]), str(zeile.get("version") or "")


def require_eindeutige_studien_identitaet(result) -> None:
    """Validate explicit ownership; another source's equal ID is independent."""
    if not db.DB_PATH.exists():
        db.init_db()
    db.resolve_identity(int(result.id), quelle=identity_key(result)[0],
                        signal_ref=getattr(result, "signal_ref", None))
    if getattr(result, "quelle_id", None):
        quellen_referenz(result)


def require_studienwaehrung(result) -> None:
    """Fehlenden Währungsnachweis vor Kurszugriff aus der Quelle erneuern.

    Bereits belegtes USD, Demo- und konvertierte Exportverträge bleiben
    gültig. Eine unbekannte native Einheit darf dagegen frische Metrics
    nachladen, auch wenn die CSV bereits lokal liegt. Kein Offline-Ersatz
    durch einen älteren USD-Wert und keine Zuordnung über fremde Quellen.
    """
    require_eindeutige_studien_identitaet(result)
    try:
        pipeline.require_usd_account(result)
        return
    except ValueError:
        currency = str(getattr(result, "account_currency", None) or "").strip().casefold()
        if currency not in {"", "unknown", "unbekannt", "uneindeutig", "unbekannt/uneindeutig"}:
            raise

    ref = quellen_referenz(result)
    if ref is None:
        pipeline.require_usd_account(result)
        return
    quelle_id, version = ref
    quelle = db.get_quelle(quelle_id)
    platform = str(getattr(result, "platform", "") or "")
    bekannte_version = str(getattr(result, "quelle_version", "") or "")
    if (quelle is None or not quelle.get("aktiv", True)
            or db.kanonische_quelle(quelle.get("kuerzel")) != identity_key(result)[0]
            or version not in ingest._PLATTFORM
            or (bekannte_version and bekannte_version != version)
            or (platform and downloader_client.platform_version(platform) != version)):
        raise ValueError("Kontowährung nicht belegt: Quellen- oder Plattformzuordnung widersprüchlich.")

    try:
        antwort = ingest.hole_metrics(quelle, int(result.id), version,
                                      allow_offline_cache=False)
    except downloader_client.DownloaderError as exc:
        raise ValueError(
            "Kontowährung unbekannt/uneindeutig: USD-Forensik gesperrt — "
            "Währungsnachweis konnte nicht von der Quelle aktualisiert werden.") from exc
    if (not isinstance(antwort, dict)
            or (antwort.get("version") and str(antwort["version"]) != version)
            or (antwort.get("signalId") is not None
                and str(antwort["signalId"]) != str(int(result.id)))):
        raise ValueError("Kontowährung nicht belegt: Metadaten gehören zu einem anderen Signal oder einer anderen Plattform.")
    result.account_currency = ingest.metrics_zu_stats(
        antwort, str(quelle["kuerzel"]), quelle_version=version).get("account_currency")
    result.quelle_id, result.quelle_version = quelle_id, version
    pipeline.require_usd_account(result)


def lade_signal_daten(result, log=None, *, allow_offline_cache: bool = True) -> tuple[str, bool]:
    """Trades + Kennzahlen EINES Katalog-Signals on demand vom Client holen.

    Nutzt denselben SHA-geprüften Cache wie der Scan (ingest.hole_trades/
    hole_metrics) — der zweite Klick ist gratis, und nach dem Laden läuft
    Detailansicht/Equity-Studie ohne Sonderweg. Rückgabe (pfad, geaendert).
    Wirft downloader_client.DownloaderError, wenn der Client den Provider
    nicht liefern kann (offline, unbekannt).
    """
    # Batch-Lücke 08.10.2026: gescannte Signale tragen keine quelle_id —
    # die Referenz wird hier selbst aufgelöst (Kürzel → Katalog-Zeile →
    # datenquellen-Zeile), statt mit None zu crashen (319 Signale!).
    try:
        ref = quellen_referenz(result)
    except ValueError as exc:
        raise downloader_client.DownloaderError(str(exc)) from exc
    if ref is None:
        raise downloader_client.DownloaderError(
            f"Für #{getattr(result, 'id', '?')} ist keine Quelle "
            "auflösbar (weder quelle_id noch Katalog-Eintrag zum Kürzel).")
    quelle_id, version = ref
    platform = str(getattr(result, "platform", "") or "")
    if (version not in ingest._PLATTFORM
            or (platform and downloader_client.platform_version(platform) != version)):
        raise downloader_client.DownloaderError(
            "Datenquellen-Version und Signalplattform widersprechen sich.")
    result.quelle_id, result.quelle_version = quelle_id, version
    quelle = db.get_quelle(int(result.quelle_id))
    if quelle is None:
        raise downloader_client.DownloaderError(
            f"Datenquelle {result.quelle!r} existiert nicht (mehr).")
    if not quelle.get("aktiv", True):
        raise downloader_client.DownloaderNotConfigured(
            f"Keine aktive Datenquelle für {identity_key(result)[0]}:{result.id} konfiguriert.")
    if log:
        log(f"Trades + Kennzahlen für #{result.id} von {quelle['kuerzel']} laden …")
    # A previous USD proof cannot authorize a newly downloaded native CSV if
    # its metadata fetch fails. Only known converting export versions have a
    # unit contract independent of this per-account evidence.
    result.account_currency = ingest.metrics_zu_stats(
        None, str(quelle["kuerzel"]),
        quelle_version=result.quelle_version).get("account_currency")
    try:
        antwort = ingest.hole_metrics(quelle, int(result.id), result.quelle_version,
                    **({"allow_offline_cache": False} if not allow_offline_cache else {}))
        result.account_currency = ingest.metrics_zu_stats(
            antwort, str(quelle["kuerzel"]),
            quelle_version=result.quelle_version).get("account_currency")
    except downloader_client.DownloaderError:
        if not allow_offline_cache:
            raise
        # Kennzahlen sind Zusatz — die Trades allein rechnen schon die
        # ganze Vorstufen-Statistik (Plattformspalten bleiben dann leer).
        pass
    pfad, geaendert = ingest.hole_trades(quelle, int(result.id),
                 result.quelle_version,
                 **({"allow_offline_cache": False} if not allow_offline_cache else {}))
    return pfad, geaendert
