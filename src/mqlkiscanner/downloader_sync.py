# -*- coding: utf-8 -*-
"""Abgleich MqlKiScanner ← MqlDownloader: Verlauf + Testreport-PDFs.

Grundregel (Nutzervorgabe): Der Abgleich synchronisiert ausschließlich
Daten — er bewertet NIE neu. Ampeln, Urteile, Scores und die Tabellen
signals/forensik/analyses bleiben unberührt; frische Downloader-Daten
ändern kein Urteil. Genutzt wird der Abgleich von drei Stellen:
Workflow-Schritt 6 (nach der Analyse), dem Katalog-Button auf der
Ergebnisseite und den Detail-Buttons je Signal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from . import config, db, downloader_client


def konfiguriert() -> bool:
    """Ist überhaupt eine Downloader-Base-URL gespeichert?"""
    return bool(str(config.load_settings().get("downloader_base_url") or "").strip())


def versions(platform: str) -> list[str]:
    """API-Versionen je Plattform; ohne Angabe werden beide gefragt."""
    version = downloader_client.platform_version(platform)
    return [version] if version else ["mql4", "mql5"]


def _client() -> downloader_client.DownloaderClient:
    return downloader_client.client_from_settings(config.load_settings())


def sync_history(signal_id: int, platform: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> int:
    """Abonnenten-Verlauf je Version holen und in die DB übernehmen.

    404 zählt nicht als Fehler: Das Signal existiert im Downloader
    schlicht nicht (z. B. nie geladen) — die betroffene Version wird
    übersprungen. Rückgabe: Anzahl gesicherter Punkte.
    """
    client = client or _client()
    stored = 0
    for version in versions(platform):
        try:
            points = client.history(signal_id, version)
        except downloader_client.DownloaderNotFound:
            continue
        stored += db.store_history_points(signal_id, version, points)
    return stored


def sync_reports(signal_id: int, platform: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> list[str]:
    """Testreport-PDFs je Version nach data/downloader/{id}/ spiegeln.

    Unveränderte Dateien (gleicher Name + Größe, Datei vorhanden) werden
    nicht erneut geladen. Rückgabe: diesmal neu geschriebene Pfade.
    """
    client = client or _client()
    known = {(row["version"], row["name"]): row
             for row in db.list_downloader_reports(signal_id)}
    fresh: list[str] = []
    for version in versions(platform):
        try:
            items = client.reports(signal_id, version)
        except downloader_client.DownloaderNotFound:
            continue
        for item in items:
            name = Path(str(item.get("name") or "")).name
            if not name.lower().endswith(".pdf"):
                continue  # API liefert nur PDFs; Schutz vor unerwarteten Einträgen
            size = item.get("sizeBytes")
            row = known.get((version, name))
            if (row is not None and Path(row["path"]).exists()
                    and row["size_bytes"] is not None and size is not None
                    and int(row["size_bytes"]) == int(size)):
                continue
            target = (config.DOWNLOADER_DIR / str(signal_id) / "reports"
                      / version / name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(client.download_report(signal_id, version, name))
            db.store_downloader_report(signal_id, version, name, str(target),
                                       size_bytes=size,
                                       last_modified=item.get("lastModified"))
            fresh.append(str(target))
    return fresh


def sync_signal(signal_id: int, platform: str, *,
                client: downloader_client.DownloaderClient | None = None) -> dict:
    """Verlauf + PDFs für ein Signal; Rückgabe ist eine kleine Summe."""
    return {
        "id": signal_id,
        "verlaufspunkte": sync_history(signal_id, platform, client=client),
        "neue_pdfs": len(sync_reports(signal_id, platform, client=client)),
    }


def sync_many(entries: Iterable[tuple[int, str]], *,
              client: downloader_client.DownloaderClient | None = None,
              progress: Callable[[int, int, int], None] | None = None) -> dict:
    """Batch-Abgleich über mehrere Signale; bricht systemisch sauber ab.

    progress(done, total, signal_id) meldet den Fortschritt. 404 (Signal
    im Downloader unbekannt) ist kein Fehler. Verbindungs- und Auth-Fehler
    brechen den Restlauf ab — jede weitere Anfrage würde gleichartig
    scheitern; andere Einzelfehler werden gesammelt und der Lauf geht
    weiter. Rückgabe: {"signale" (bearbeitete Ziele, inkl. Einzelfehler),
    "verlaufspunkte", "neue_pdfs", "fehler", "abgebrochen"}.
    """
    client = client or _client()
    ziele = [(int(signal_id), str(platform)) for signal_id, platform in entries]
    summary = {"signale": 0, "verlaufspunkte": 0, "neue_pdfs": 0,
               "fehler": [], "abgebrochen": None}
    for done, (signal_id, platform) in enumerate(ziele, 1):
        if progress:
            progress(done, len(ziele), signal_id)
        try:
            result = sync_signal(signal_id, platform, client=client)
        except downloader_client.DownloaderNotFound:
            summary["signale"] += 1
            continue
        except downloader_client.DownloaderAuthError as exc:
            summary["abgebrochen"] = str(exc)
            break
        except downloader_client.DownloaderConnectionError as exc:
            summary["abgebrochen"] = str(exc)
            break
        except downloader_client.DownloaderError as exc:
            summary["fehler"].append(f"#{signal_id}: {exc}")
            summary["signale"] += 1
            continue
        summary["signale"] += 1
        summary["verlaufspunkte"] += result["verlaufspunkte"]
        summary["neue_pdfs"] += result["neue_pdfs"]
    return summary
