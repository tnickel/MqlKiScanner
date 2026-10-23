# -*- coding: utf-8 -*-
"""Einmal-Sync MqlKiScanner → MqlTradeMonitor: Tabelle + Dokumente.

Grundregel (wie beim MqlDownloader-Abgleich): Der Sync überträgt
ausschließlich Daten und Anzeigen — er bewertet NIE neu und schreibt
nichts in signals/forensik/analyses. Lokal entsteht allein die
Lauf-Historie in tradeserver_sync_runs.

Ablauf des Protokolls v2 (doc/06_tradeserver-sync.md): Register-
Handshake → Tabellen-Snapshot → Dokumente (nur Änderungen, Diff über
SHA-256 gegen den gemeldeten Serverbestand) → Complete. Danach ist die
Verbindung beendet — es gibt keine Dauerverbindung. Der Sync-Button
liest die aktuell angezeigte Quelle (Datenbank/Sitzung/Archiv) und
überträgt genau diese Tabelle samt der zugehörigen PDFs.
"""
from __future__ import annotations

import base64
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

from . import config, db, tradeserver_client
from .agenten import lock
from .signal_identity import identity_key
from .pdf_reports import (PdfRenderError, materialize_portfolio_pdf,
                          materialize_result_pdfs)

# Anzeigelabels der eigenen Berichtsarten (wie das Dokumente-Panel).
_ART_LABELS = {
    "trade_analyse": "1 · Trade-Analyse",
    "risiko_analyse": "2 · Risiko-Analyse",
    "gesamtbericht": "3 · Gesamtbericht",
    "tiefenanalyse": "ℹ️ Erweiterte KI-Analyse (Tiefenanalyse)",
}

# Größenschutz: der Tradeserver (nginx-Produktionssetup) nimmt maximal
# ~10 MB Requestkörper an; Base64 bläht um ein Drittel auf. Größere
# Dateien werden übersprungen und im Sync-Bericht vermerkt.
_MAX_DOC_BYTES = 8 * 1024 * 1024


def _remote_identity(result) -> dict:
    """Only an established local namespace may own a remote signal."""
    source, external = identity_key(result)
    if external <= 0 or isinstance(result.id, bool):
        raise tradeserver_client.TradeserverError("Ungültige externe Signal-ID.")
    ref = getattr(result, "signal_ref", None)
    try:
        identity = db.resolve_identity(external, quelle=source, signal_ref=ref)
        namespace = db.source_identity(source)
    except ValueError as exc:
        raise tradeserver_client.TradeserverError(str(exc)) from exc
    if namespace is None or (ref is not None and identity is None):
        raise tradeserver_client.TradeserverError(
            f"Unbelegte Quellenidentität für {source}:{external}; Export gesperrt.")
    uid = str(namespace["quellen_uid"])
    claimed_uid = getattr(result, "quellen_uid", "")
    if claimed_uid and claimed_uid != uid:
        raise tradeserver_client.TradeserverError(
            f"Quellen-UID widerspricht dem lokalen Register: {source}:{external}.")
    return {"sourceUid": uid, "source": namespace["kuerzel"], "signalId": external}


def _document_prefix(owner: dict) -> str:
    return f"signal/{quote(owner['sourceUid'], safe='')}/{owner['signalId']}"


def _eigene_berichte_aktuell(result) -> bool:
    """Historical texts may remain visible locally but cannot become a current export."""
    return bool(getattr(result, "berichte_basis", "")
                and getattr(result, "forensik_vorhanden", False)
                and not getattr(result, "forensik_stale", False)
                and not getattr(result, "fehler", ""))


def konfiguriert() -> bool:
    """Ist überhaupt eine Tradeserver-Base-URL gespeichert?"""
    return bool(str(config.load_settings().get("tradeserver_base_url") or "").strip())


def _client() -> tradeserver_client.TradeserverClient:
    return tradeserver_client.client_from_settings(config.load_settings())


def _runden(wert: float | None, stellen: int = 2) -> float | None:
    if wert is None:
        return None
    try:
        return round(float(wert), stellen)
    except (TypeError, ValueError):
        return None


def signal_zeilen(results: Iterable, fresh_ids: set[int] | None = None) -> list[dict]:
    """Ergebniszeilen → Protokoll-Payload (eine Zeile je Signal).

    Rein lokale Abbildung ohne Netz: alle Tabellenfelder der Ergebnis-
    ansicht plus Abonnenten-/Dokumente-Zählern aus der lokalen DB.
    """
    from . import downloader_sync  # lokal importiert: nur benötigt, wenn Zeilen gebaut werden

    results = list(results)
    fresh_ids = fresh_ids or set()
    settings = config.load_settings()
    docs_counts = db.downloader_report_counts([identity_key(r) for r in results])
    abo = downloader_sync.abo_bilanz(
        [identity_key(r) for r in results],
        platformen={identity_key(r): getattr(r, "platform", "") or "" for r in results})
    zeilen: list[dict] = []
    for r in results:
        refresh = getattr(r, "refresh_efficiency", None)
        if callable(refresh):
            refresh()
        aktuelle_berichte = _eigene_berichte_aktuell(r)
        docs_eigene = (sum(bool(getattr(r, feld, "")) for feld in
                          ("trade_analyse", "risiko_analyse", "gesamtbericht"))
                       if aktuelle_berichte else 0)
        docs_tiefen = int(aktuelle_berichte and bool(getattr(r, "tiefenanalyse", "")))
        bilanz = abo.get(identity_key(r)) or {}
        zeilen.append({
            **_remote_identity(r),
            "name": r.name or "",
            "platform": getattr(r, "platform", "") or "",
            "url": (r.url or (f"https://www.mql5.com/en/signals/{r.id}"
                              if identity_key(r)[0] == "mql5" else "")),
            "ampel": r.ampel or "⚪",
            "score": _runden(r.score),
            "urteil": r.urteil or "",
            "kurzfassung": (getattr(r, "kurzfassung", "") or "") if aktuelle_berichte else "",
            "stop": r.stop_nachweis or "",
            "stopEvidence": getattr(r, "stop_evidence", None),
            "tradingDdPct": _runden(r.trading_dd_pct),
            "ddEquityPct": _runden(r.dd_equity_pct),
            "ddBalancePct": _runden(r.dd_balance_pct),
            "maxDrawdownEquityPct": getattr(r, "max_drawdown_equity_pct", None),
            "drawdownLimitPct": settings.get("schranke_eq_dd_pct", 30.0),
            "minReturnMonthlyPct": settings.get("min_ertrag_pct_monat", 0.0),
            # Calmar-Gate seit 05.10. (Nutzer-Entscheid): Grenze ist der
            # JAHRES-Calmar, nicht mehr RetDD/Monat >= 1,0. minRetddMonthly
            # bleibt als veraltetes Feld für ältere MqlTradeMonitor-Builds.
            "minRetddMonthly": 1.0,
            "minCalmarJahr": config.min_calmar_jahr(settings),
            "ertragMonatPct": _runden(r.ertrag_monat_pct),
            # Zinseszins-wahre Ertrags- und Effizienzkennzahlen
            # (Nutzer-Wunsch 01.10.2026, MqlTradeMonitor-Anzeige):
            # ertragMonatForensikPct = linearer Ø auf eigener Basis,
            # ertragMonatGeomPct = geometrisches Monatsmittel (CAGR-Basis),
            # cagrJahrPct = annualisierter CAGR, retddMonat/retddJahr =
            # Ertrag je Prozent gemessenem Equity-DD. Rohwerte übertragen,
            # damit RetDD knapp unter 1 nicht bereits im Protokoll aufrundet.
            "ertragMonatForensikPct": _runden(
                getattr(r, "ertrag_monat_pct_forensik", None)),
            "ertragMonatGeomPct": getattr(r, "ertrag_monat_geom_pct", None),
            "cagrJahrPct": getattr(r, "cagr_jahr_pct", None),
            "retddMonat": getattr(r, "retdd_monat", None),
            "retddJahr": getattr(r, "retdd_jahr", None),
            "retddJahrVorbehalt": getattr(r, "retdd_jahr_vorbehalt", None),
            "retddVorbehaltGrund": getattr(r, "retdd_vorbehalt_grund", "") or "",
            "equityMeasurementStatus": getattr(r, "equity_messung_status", "") or "",
            "retddBasis": (getattr(r, "effizienz_befund", {}) or {}).get("retdd_basis"),
            "growthPct": _runden(r.growth_pct),
            "pf": _runden(r.pf),
            "winratePct": _runden(r.winrate_pct),
            "aboPreisUsd": _runden(r.abo_preis_usd),
            "abonnenten": _runden(r.abonnenten, 0),
            "wochen": _runden(r.wochen, 1),
            "aboDelta7": bilanz.get("tage7"),
            "aboDelta30": bilanz.get("tage30"),
            "aboStand": (bilanz.get("stand").isoformat(sep=" ", timespec="seconds")
                         if isinstance(bilanz.get("stand"), datetime) else None),
            "martingale": getattr(r, "martingale_flag", None),
            "peakPositionen": getattr(r, "peak_positionen", None),
            "peakNettoLots": _runden(getattr(r, "peak_netto_lots", None)),
            "shockUsd": _runden(getattr(r, "shock_usd", None)),
            "kapitalbasisUsd": _runden(getattr(r, "kapitalbasis_usd", None)),
            "brokerServer": getattr(r, "broker_server", None),
            "symbole": getattr(r, "symbole", "") or "",
            "berichtVom": (getattr(r, "gesamtbericht_at", "") or None)
                          if aktuelle_berichte else None,
            "docsBerichte": docs_eigene,
            "docsTiefenanalyse": docs_tiefen,
            "docsDownloader": docs_counts.get(identity_key(r), 0),
            "tradesSha256": getattr(r, "trades_sha256", "") or "",
            "stand": "NEU" if identity_key(r) in fresh_ids else "",
        })
    return zeilen


def dokumente_sammeln(results: Iterable, portfolio: dict | None = None) -> tuple[list[dict], list[str]]:
    """Alle übertragbaren PDFs einsammeln: eigene Berichte (werden dafür
    nötigenfalls erzeugt/gespeichert), Portfolio-Bericht und die
    gespiegelten Downloader-Testreports.

    Rückgabe (dokumente, fehler): jedes Dokument ist ein Metadaten-Dict
    mit lokalem `path` — Binärdaten liest der Sync erst beim Upload.
    """
    results = list(results)
    dokumente: list[dict] = []
    fehler: list[str] = []

    for r in results:
        owner = _remote_identity(r)
        prefix = _document_prefix(owner)
        pfade = {}
        if _eigene_berichte_aktuell(r):
            try:
                pfade = materialize_result_pdfs(r)
            except (PdfRenderError, OSError) as exc:
                fehler.append(f"#{r.id}: Bericht-PDFs nicht erzeugbar: {exc}")
        for art, path in pfade.items():
            dokumente.append({
                "docKey": f"{prefix}/{path.name}",
                **owner,
                "group": "eigene",
                "kind": art,
                "label": _ART_LABELS.get(art, path.name),
                "fileName": path.name,
                "path": path,
                "contentType": "application/pdf",
                "lastModified": getattr(r, f"{art}_at", "") or None,
            })
        for row in db.list_downloader_reports(r.id, quelle=identity_key(r)[0]):
            path = Path(row["path"])
            dokumente.append({
                "docKey": f"{prefix}/downloader/{quote(row['version'], safe='')}/{quote(row['name'], safe='')}",
                **owner,
                "group": "downloader",
                "kind": "downloader_testreport",
                "label": row["name"],
                "fileName": row["name"],
                "path": path,
                "contentType": "application/pdf",
                "lastModified": row.get("last_modified"),
            })

    if portfolio:
        try:
            path = materialize_portfolio_pdf(portfolio)
        except (PdfRenderError, OSError) as exc:
            fehler.append(f"Portfolio: PDF nicht erzeugbar: {exc}")
            path = None
        if path is not None:
            dokumente.append({
                "docKey": f"portfolio/{path.name}",
                "signalId": None,
                "sourceUid": None,
                "source": None,
                "group": "portfolio",
                "kind": "portfolio",
                "label": "Portfolio-Gesamtbericht",
                "fileName": path.name,
                "path": path,
                "contentType": "application/pdf",
                "lastModified": portfolio.get("created_at"),
            })

    vorhandene: list[dict] = []
    for doc in dokumente:
        try:
            if not doc["path"].is_file():
                fehler.append(f"{doc['docKey']}: Datei fehlt lokal, übersprungen")
                continue
            groesse = doc["path"].stat().st_size
        except OSError as exc:
            fehler.append(f"{doc['docKey']}: nicht lesbar: {exc}")
            continue
        if groesse > _MAX_DOC_BYTES:
            fehler.append(f"{doc['docKey']}: {groesse / 1024 / 1024:.1f} MB ist "
                          f"zu groß (Grenze {_MAX_DOC_BYTES // 1024 // 1024} MB)")
            continue
        doc["sizeBytes"] = groesse
        vorhandene.append(doc)
    return vorhandene, fehler


def _payload_ohne_lokale_felder(doc: dict, *, mit_inhalt: bool = False) -> dict:
    payload = {
        "docKey": doc["docKey"],
        "signalId": doc.get("signalId"),
        "sourceUid": doc.get("sourceUid"),
        "source": doc.get("source"),
        "group": doc.get("group"),
        "kind": doc.get("kind"),
        "label": doc.get("label"),
        "fileName": doc.get("fileName"),
        "contentType": doc.get("contentType") or "application/pdf",
        "sha256": doc.get("sha256"),
        "sizeBytes": doc.get("sizeBytes"),
        "lastModified": doc.get("lastModified"),
    }
    if mit_inhalt:
        payload["contentBase64"] = base64.b64encode(
            doc["bytes"]).decode("ascii")
    return payload


_SYNC_LOCK = threading.Lock()


def sync_alle(results: Iterable, portfolio: dict | None = None, **kwargs) -> dict:
    """Only one sync per data directory, across sessions and processes."""
    message = "Tradeserver-Sync läuft bereits in einer anderen Sitzung."
    if _SYNC_LOCK.acquire(blocking=False):
        try:
            try:
                with lock.lauf_lock(config.DATA_DIR, name="tradeserver_sync"):
                    return _sync_alle(results, portfolio, **kwargs)
            except lock.LockBesetzt as exc:
                message = str(exc)
        finally:
            _SYNC_LOCK.release()
    return {"signale":0,"gespeichert":0,"geloescht":0,"dokumente":0,
            "uebertragen":0,"uebersprungen":0,"bytes":0,"fehler":[],
            "abgebrochen":message,"run_id":None,"server_zeit":None,"dauer_s":0.0}


def _sync_alle(results: Iterable, portfolio: dict | None = None, *,
              fresh_ids: set[int] | None = None,
              client: tradeserver_client.TradeserverClient | None = None,
              progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Kompletter Einmal-Sync zum Tradeserver; Rückgabe ist die Bilanz.

    Fortschritt via progress(done, total, label). Ein abgebrochener Lauf
    (Verbindung/Auth/Protokoll) ruft bestmöglich abort auf dem Server
    und landet mit status='abgebrochen' in der lokaren Historie.
    """
    start = time.monotonic()
    results = [r for r in results if getattr(r, "source_kind", "live") == "live"]
    # Validate every owner before creating a client or a journal entry.
    gesehen: set[tuple[str, int]] = set()
    unique: list = []
    for r in results:
        owner = _remote_identity(r)
        key = owner["sourceUid"], owner["signalId"]
        if key not in gesehen:
            gesehen.add(key)
            unique.append(r)

    summary = {
        "signale": 0, "gespeichert": 0, "geloescht": 0,
        "dokumente": 0, "uebertragen": 0, "uebersprungen": 0,
        "bytes": 0, "fehler": [], "abgebrochen": None,
        "run_id": None, "server_zeit": None, "dauer_s": None,
    }
    client = client or _client()
    local_run_id = db.start_tradeserver_sync_run(client.base)
    run_offen = False
    try:
        zeilen = signal_zeilen(unique, fresh_ids=fresh_ids)
        dokumente, fehler = dokumente_sammeln(unique, portfolio)
        summary.update(signale=len(zeilen), dokumente=len(dokumente), fehler=fehler)
        if fehler:
            # v2 is a complete mirror: silently omitting a failed local PDF
            # would delete its previously committed remote document.
            raise tradeserver_client.TradeserverError(
                "Dokumentensammlung unvollständig; Serverbestand bleibt erhalten: "
                + "; ".join(fehler))
        info = client.register(signal_count=len(zeilen))
        summary["run_id"] = info.get("runId")
        summary["server_zeit"] = info.get("serverTime")
        run_offen = True
        bestand = info.get("documents") or []
        bekannt = {str(e.get("docKey")): e
                   for e in bestand if isinstance(e, dict)}

        ergebnis = client.signals(zeilen)
        summary["gespeichert"] = int(ergebnis.get("stored") or 0)
        summary["geloescht"] = int(ergebnis.get("deleted") or 0)

        for done, doc in enumerate(dokumente, 1):
            if progress:
                progress(done, len(dokumente), str(doc.get("label") or doc["docKey"]))
            # Hash the same immutable bytes that are uploaded, not a prior read.
            doc["bytes"] = doc["path"].read_bytes()
            if len(doc["bytes"]) > _MAX_DOC_BYTES:
                raise tradeserver_client.TradeserverError(
                    f"{doc['docKey']}: PDF überschreitet nach Sammlung die Größengrenze.")
            import hashlib
            doc["sha256"] = hashlib.sha256(doc["bytes"]).hexdigest()
            doc["sizeBytes"] = len(doc["bytes"])
            remote = bekannt.get(doc["docKey"]) or {}
            if (remote.get("sha256") == doc["sha256"]
                    and remote.get("sourceUid") == doc.get("sourceUid")
                    and remote.get("signalId") == doc.get("signalId")):
                summary["uebersprungen"] += 1
                continue
            client.document(_payload_ohne_lokale_felder(doc, mit_inhalt=True))
            summary["uebertragen"] += 1
            summary["bytes"] += int(doc.get("sizeBytes") or 0)

        completed = client.complete(
            signals=summary["signale"], documents=summary["dokumente"],
            uploaded=summary["uebertragen"], skipped=summary["uebersprungen"],
            bytes_total=summary["bytes"],
            document_keys=[doc["docKey"] for doc in dokumente])
        if "deleted" in completed:
            summary["geloescht"] = int(completed["deleted"] or 0)
        run_offen = False
    except tradeserver_client.TradeserverError as exc:
        summary["abgebrochen"] = str(exc)
        if run_offen:
            try:
                client.abort(str(exc))
            except tradeserver_client.TradeserverError:
                pass  # Best-Effort: Server markiert den Lauf sonst beim Timeout.
    except Exception as exc:  # gelöschte PDF (OSError), Netzwerk-Deko & Co.
        # Früher entkam das: Der finally-Block schrieb status='ok', obwohl
        # der Server den Signal-Snapshot hatte und nur TEIL der Dokumente —
        # ein Retry übersprang dann alles (Review 29.09.).
        summary["abgebrochen"] = f"{type(exc).__name__}: {exc}"
        if run_offen:
            try:
                client.abort(summary["abgebrochen"])
            except tradeserver_client.TradeserverError:
                pass  # Best-Effort: Server markiert den Lauf sonst beim Timeout.
    finally:
        summary["dauer_s"] = round(time.monotonic() - start, 1)
        db.finish_tradeserver_sync_run(local_run_id,
            "abgebrochen" if summary["abgebrochen"] else "ok", summary)
    return summary


# TTL-Cache für den Verbindungs-Start-Test (wie beim MqlDownloader):
# Streamlit rerendert ständig — ohne Cache würde jede Seitenaktion einen
# REST-Aufruf auslösen. Schlüssel ist die Base-URL, sodass ein
# Konfigurationswechsel sofort neu prüft.
_STATUS_TTL_S = 300.0
_STATUS_CACHE: dict[str, tuple[datetime, dict]] = {}


def status_cache_leeren() -> None:
    """Verbindungs-Test-Cache verwerfen (z. B. nach Speichern im Admin)."""
    _STATUS_CACHE.clear()


def verbindungs_status(force: bool = False, timeout: float = 3.0) -> dict:
    """Erreichbarkeit des Tradeservers — 5 Minuten gecacht je Base-URL.

    ok=None heißt „nicht konfiguriert“ (kein Netzaufruf); ok=True/False
    ist das Ergebnis des letzten /ping-Tests inklusive Key-Prüfung.
    """
    base = str(config.load_settings().get("tradeserver_base_url") or "")
    jetzt = datetime.now()
    if not force:
        cached = _STATUS_CACHE.get(base)
        if cached and (jetzt - cached[0]).total_seconds() < _STATUS_TTL_S:
            return cached[1]
    if not base:
        wert = {"konfiguriert": False, "ok": None,
                "detail": "Nicht konfiguriert (Admin → Tradeserver)",
                "service": None, "api_version": None, "geprueft": jetzt}
    else:
        try:
            client = _client()
            client.timeout = timeout
            info = client.ping()
            reachable = str(info.get("status", "")).lower() == "ok"
            compatible = (2 in (info.get("supportedProtocolVersions") or [])
                          or info.get("kiscannerApi") in (2, "2", "v2"))
            ok = reachable and compatible
            wert = {"konfiguriert": True, "ok": ok,
                    "detail": ("Verbindung ok, Protokoll v2 und API-Key akzeptiert" if ok else
                               "Tradeserver aktualisieren: Protokoll v2 erforderlich."
                               if reachable else f"Unerwarteter Status: {info.get('status')!r}"),
                    "service": info.get("service"),
                    "api_version": info.get("kiscannerApi"),
                    "geprueft": jetzt}
        except tradeserver_client.TradeserverError as exc:
            wert = {"konfiguriert": True, "ok": False, "detail": str(exc),
                    "service": None, "api_version": None, "geprueft": jetzt}
    _STATUS_CACHE[base] = (jetzt, wert)
    return wert
