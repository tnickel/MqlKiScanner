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

import json
from pathlib import Path

from . import db, downloader_client, ingest, pipeline, quellen


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
        quellen_aktiv = [q for q in quellen_aktiv if q["kuerzel"] == kuerzel]
    summary: dict = {"quellen": {}, "gesamt": 0}
    for quelle in quellen_aktiv:
        eintrag = {"anzahl": 0, "geloescht": 0, "fehler": None}
        try:
            items = _normalisiere(ingest.hole_katalog(quelle))
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
            quelle["kuerzel"], {}).get("gelaufen_am")
        summary["quellen"][quelle["kuerzel"]] = eintrag
        summary["gesamt"] += eintrag["anzahl"]
    return summary


def katalog_resultate() -> tuple[list, dict]:
    """Katalogzeilen als leichtgewichtige ScanResults für die Übersicht.

    Gescannte Signale (signals-Tabelle) GEWINNEN — sie sind hier dedupliert
    raus und erscheinen weiter über results_from_db. Doppelte signal_id
    über Quellen: erste Zeile gewinnt (katalog_list sortiert Abonnenten
    absteigend — der interessanteste Eintrag gewinnt). Bereits gecachte
    Trades/Kennzahlen (quellen_artefakte) werden mitgeliefert — Zeilen MIT
    Trades rechnen damit sofort echte Statistiken, die anderen lassen sich
    per Button nachladen. Rückgabe (resultate, stats_je_id).
    """
    db.init_db()
    gescannt = db.known_signal_ids()
    quellen_nach_kuerzel = {str(q["kuerzel"]): q for q in db.list_quellen()}
    resultate: list = []
    stats_je_id: dict[int, dict] = {}
    gesehen: set[int] = set()
    for zeile in db.katalog_list():
        signal_id = int(zeile["signal_id"])
        kuerzel = str(zeile.get("quelle") or "")
        if signal_id in gescannt or signal_id in gesehen:
            continue
        gesehen.add(signal_id)
        res = pipeline.ScanResult(
            id=signal_id,
            name=zeile.get("name") or str(signal_id),
            platform=zeile.get("platform") or "",
            url=zeile.get("url") or "",
            abonnenten=zeile.get("abonnenten"),
            wochen=zeile.get("wochen"),
            quelle=kuerzel or "mql5",
            herkunft="Katalog",
        )
        quelle = quellen_nach_kuerzel.get(kuerzel)
        version = str(zeile.get("version") or "")
        if quelle is not None and version:
            res.quelle_id = int(quelle["id"])
            res.quelle_version = version
            trades = db.get_quellen_artefakt(int(quelle["id"]), signal_id,
                                             version, "trades")
            if trades and trades.get("path") and Path(trades["path"]).exists():
                res.trades_path = str(trades["path"])
                res.trades_sha256 = trades.get("sha256") or ""
                metrics = db.get_quellen_artefakt(int(quelle["id"]), signal_id,
                                                  version, "metrics")
                if metrics and metrics.get("path") \
                        and Path(metrics["path"]).exists():
                    try:
                        stats = ingest.metrics_zu_stats(
                            json.loads(Path(metrics["path"]).read_text(
                                encoding="utf-8")),
                            quelle_kuerzel=kuerzel)
                    except (OSError, ValueError):
                        stats = {}
                    stats_je_id[signal_id] = stats
                    res.dd_equity_pct = stats.get("dd_equity_pct")
                    res.ertrag_monat_pct = stats.get("monthly_growth_pct")
                    res.broker_server = stats.get("broker_server")
        resultate.append(res)
    # Batch-Equity-Studien („Lücken füllen", Nutzer 08.10.2026): True-DD,
    # TrueRetDD-Familie und True-DD USD in die Katalog-Zeilen mappen —
    # Forensik gibt es hier nicht, die Studie gewinnt immer (SHA-geschützt).
    studien = db.list_equity_studien()
    for res in resultate:
        pipeline.studie_anwenden(res, studien)
    return resultate, stats_je_id


def metrics_stats(result) -> dict:
    """Gecachte Kennzahlen eines Katalog-Signals als Stats-Formular (leer ohne
    Cache/Fehler) — für Statistik- und Batch-Berechnungen ohne Scan."""
    quelle_id = getattr(result, "quelle_id", None)
    if not quelle_id:
        return {}
    artefakt = db.get_quellen_artefakt(int(quelle_id), int(result.id),
                                       str(getattr(result, "quelle_version", "") or ""),
                                       "metrics")
    if not artefakt or not artefakt.get("path") \
            or not Path(artefakt["path"]).exists():
        return {}
    try:
        return ingest.metrics_zu_stats(
            json.loads(Path(artefakt["path"]).read_text(encoding="utf-8")),
            quelle_kuerzel=str(getattr(result, "quelle", "") or ""))
    except (OSError, ValueError):
        return {}


def quellen_referenz(result) -> tuple[int, str] | None:
    """(quelle_id, version) fürs on-demand-Nachladen eines ScanResults.

    Katalog-Zeilen tragen beide Felder; gescannte Signale nur das Kürzel —
    dort wird die Version über die Katalog-Zeile des gleichen
    (Kürzel, Signal-ID)-Paars aufgelöst (z. B. fehlgeschlagener Scan:
    Quelle bekannt, Trade-Export nie angekommen). None ohne jede Referenz
    (reines MQL5-Direkt-Signal).
    """
    if getattr(result, "quelle_id", None):
        return int(result.quelle_id), str(getattr(result, "quelle_version", "") or "")
    kuerzel = str(getattr(result, "quelle", "") or "")
    if not kuerzel:
        return None
    zeile = next((z for z in db.katalog_list()
                  if z["quelle"] == kuerzel
                  and int(z["signal_id"]) == int(result.id)), None)
    quelle = next((q for q in db.list_quellen() if q["kuerzel"] == kuerzel), None)
    if zeile is None or quelle is None:
        return None
    return int(quelle["id"]), str(zeile.get("version") or "")


def lade_signal_daten(result, log=None) -> tuple[str, bool]:
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
    if getattr(result, "quelle_id", None) is None:
        ref = quellen_referenz(result)
        if ref is None:
            raise downloader_client.DownloaderError(
                f"Für #{getattr(result, 'id', '?')} ist keine Quelle "
                "auflösbar (weder quelle_id noch Katalog-Eintrag zum Kürzel).")
        result.quelle_id, result.quelle_version = ref
    quelle = db.get_quelle(int(result.quelle_id))
    if quelle is None:
        raise downloader_client.DownloaderError(
            f"Datenquelle {result.quelle!r} existiert nicht (mehr).")
    if log:
        log(f"Trades + Kennzahlen für #{result.id} von {quelle['kuerzel']} laden …")
    try:
        ingest.hole_metrics(quelle, int(result.id), result.quelle_version)
    except downloader_client.DownloaderError:
        # Kennzahlen sind Zusatz — die Trades allein rechnen schon die
        # ganze Vorstufen-Statistik (Plattformspalten bleiben dann leer).
        pass
    pfad, geaendert = ingest.hole_trades(quelle, int(result.id),
                                         result.quelle_version)
    return pfad, geaendert
