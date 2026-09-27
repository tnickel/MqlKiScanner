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

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from . import config, db, downloader_client, quellen


def konfiguriert() -> bool:
    """Ist mindestens eine aktive Datenquelle gespeichert?"""
    quellen._ensure()
    return bool(db.list_quellen(nur_aktiv=True))


def versions(platform: str) -> list[str]:
    """API-Versionen je Plattform; ohne Angabe werden beide gefragt."""
    version = downloader_client.platform_version(platform)
    return [version] if version else ["mql4", "mql5"]


def _ueber_quellen(fn: Callable[[downloader_client.DownloaderClient], list]) -> list:
    """fn(client) je aktiver Datenquelle ausführen (sequenziell, Stufe 1).

    Dieselbe MQL5-Signal-ID in mehreren Spiegel-Quellen ist dasselbe Signal:
    Writes sind idempotent (INSERT-OR-UPDATE), Rückgaben werden vereinigt.
    Ein Verbindungs-/Auth-Fehler EINER Quelle bricht nichts — nur wenn keine
    Quelle etwas liefern konnte, wandert der Systemfehler nach oben (damit
    Batch-Läufe wie bisher sauber abbrechen).
    """
    quellen_liste = db.list_quellen(nur_aktiv=True)
    if not quellen_liste:
        # Erst Chancen für die Legacy-Übernahme (settings → Quelle), dann Nein.
        quellen._ensure()
        quellen_liste = db.list_quellen(nur_aktiv=True)
    if not quellen_liste:
        raise downloader_client.DownloaderNotConfigured(
            "Keine Datenquelle konfiguriert. Admin → Datenquellen.")
    ergebnis: list = []
    systemic: BaseException | None = None
    for quelle in quellen_liste:
        try:
            ergebnis.extend(fn(quellen.client_fuer_quelle(quelle)))
        except downloader_client.DownloaderNotFound:
            continue  # Signal existiert in dieser Quelle nicht — keine Daten, kein Fehler
        except (downloader_client.DownloaderAuthError,
                downloader_client.DownloaderConnectionError) as exc:
            systemic = systemic or exc
    if systemic is not None and not ergebnis:
        raise systemic
    return ergebnis


def _client() -> downloader_client.DownloaderClient:
    return downloader_client.client_from_settings(config.load_settings())


def _history_via_client(client: downloader_client.DownloaderClient,
                        signal_id: int, platform: str) -> int:
    stored = 0
    for version in versions(platform):
        try:
            points = client.history(signal_id, version)
        except downloader_client.DownloaderNotFound:
            continue
        stored += db.store_history_points(signal_id, version, points)
    return stored


def sync_history(signal_id: int, platform: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> int:
    """Abonnenten-Verlauf über alle aktiven Quellen holen und übernehmen.

    404 zählt nicht als Fehler: Das Signal existiert in dieser Quelle
    schlicht nicht (z. B. nie geladen) — die betroffene Version wird
    übersprungen. Rückgabe: Anzahl vorhandener Verlaufspunkte je Signal
    und Plattform-Versionen (Spiegel liefern identische Punkte; gezählt
    wird der echte DB-Stand, nicht je Quelle doppelt).
    """
    if client is not None:
        return _history_via_client(client, signal_id, platform)
    _ueber_quellen(lambda qc: [_history_via_client(qc, signal_id, platform)])
    punkte = {(p["version"], p["ts"]) for p in db.get_history(signal_id)}
    moegliche = set(versions(platform))
    return sum(1 for version, _ts in punkte if version in moegliche)


def _reports_via_client(client: downloader_client.DownloaderClient,
                        signal_id: int, platform: str) -> list[str]:
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


def sync_reports(signal_id: int, platform: str, *,
                 client: downloader_client.DownloaderClient | None = None) -> list[str]:
    """Testreport-PDFs je Version nach data/downloader/{id}/ spiegeln.

    Unveränderte Dateien (gleicher Name + Größe, Datei vorhanden) werden
    nicht erneut geladen — auch wenn mehrere Quellen dasselbe Signal
    liefern (idempotent). Rückgabe: diesmal neu geschriebene Pfade.
    """
    if client is not None:
        return _reports_via_client(client, signal_id, platform)
    fresh = _ueber_quellen(
        lambda qc: _reports_via_client(qc, signal_id, platform))
    return list(dict.fromkeys(fresh))


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
    client_fallback = client
    ziele = [(int(signal_id), str(platform)) for signal_id, platform in entries]
    summary = {"signale": 0, "verlaufspunkte": 0, "neue_pdfs": 0,
               "fehler": [], "abgebrochen": None}
    for done, (signal_id, platform) in enumerate(ziele, 1):
        if progress:
            progress(done, len(ziele), signal_id)
        try:
            result = (sync_signal(signal_id, platform, client=client_fallback)
                      if client_fallback is not None
                      else sync_signal(signal_id, platform))
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


_TOLERANZ_TAGE = 3  # Fenster fuer den Vergleichspunkt (wie der Downloader selbst)

# TTL-Cache fuer den Verbindungs-Start-Test: Streamlit rerendert staendig —
# ohne Cache wuerde jede Seitenaktion einen REST-Aufruf ausloesen. Schluessel
# ist die Base-URL, sodass ein Konfigurationswechsel sofort neu prueft.
_STATUS_TTL_S = 300.0
_STATUS_CACHE: dict[str, tuple[datetime, dict]] = {}


def status_cache_leeren() -> None:
    """Verbindungs-Test-Cache verwerfen (z. B. nach Speichern im Admin)."""
    _STATUS_CACHE.clear()


def verbindungs_status(force: bool = False, timeout: float = 3.0) -> dict:
    """Erreichbarkeit der Datenquellen — einmal beim Programmstart, dann gecacht.

    Wird in der Sidebar (Systemstatus), auf der Scan-Seite und im Admin
    angezeigt. ok=None bedeutet „nicht konfiguriert“ (kein Netzaufruf);
    ok=True = mindestens eine Quelle erreichbar, ok=False = keine der
    aktiven Quellen antwortet. Der Cache gilt 5 Minuten je Quellen-Kombi;
    `force=True` (manueller Test) umgeht ihn.
    """
    quellen._ensure()
    aktiv = db.list_quellen(nur_aktiv=True)
    schluessel = "|".join(q["base_url"] for q in aktiv)
    jetzt = datetime.now()
    if not force:
        cached = _STATUS_CACHE.get(schluessel)
        if cached and (jetzt - cached[0]).total_seconds() < _STATUS_TTL_S:
            return cached[1]
    if not aktiv:
        wert = {"konfiguriert": False, "ok": None,
                "detail": "Nicht konfiguriert (Admin → Datenquellen)",
                "providers": None, "api_version": None, "geprueft": jetzt,
                "token_required": None}
    else:
        pruefungen = [quellen.pruefe(q, force=force, timeout=timeout) for q in aktiv]
        erreichbar = [p for p in pruefungen if p["status"] == "ok"]
        kurz = " · ".join(f"{q['kuerzel']} {quellen.status_zeichen(p)}"
                          for q, p in zip(aktiv, pruefungen))
        providers = sum(int((p.get("details") or {}).get("anbieter") or 0)
                        for p in erreichbar)
        api_version = next((str((p.get("details") or {}).get("version"))
                            for p in erreichbar
                            if (p.get("details") or {}).get("version") is not None), None)
        if erreichbar:
            detail = (f"{len(erreichbar)}/{len(aktiv)} Quellen erreichbar — {kurz}"
                      if len(erreichbar) < len(aktiv)
                      else f"Alle {len(aktiv)} Quellen erreichbar — {kurz}")
        else:
            fehler = next((p["text"] for p in pruefungen if p["text"]), "keine Antwort")
            detail = f"Keine Quelle erreichbar — {fehler}"
        wert = {"konfiguriert": True, "ok": bool(erreichbar), "detail": detail,
                "providers": providers or None, "api_version": api_version,
                "geprueft": jetzt,
                "token_required": any((p.get("details") or {}).get("token_required")
                                      for p in pruefungen)}
    _STATUS_CACHE[schluessel] = (jetzt, wert)
    return wert


def _bilanz(reihe: list[tuple[datetime, int | None]], tage: int,
            aktuell: int | None) -> int | None:
    """Differenz: neuester Punkt gegen den Punkt vor ~tagen (±Toleranz)."""
    if aktuell is None:
        return None
    ziel = datetime.now() - timedelta(days=tage)
    kandidaten = [(ts, s) for ts, s in reihe
                  if s is not None and abs((ts - ziel).total_seconds())
                  <= _TOLERANZ_TAGE * 86400]
    if not kandidaten:
        return None
    _, alt = min(kandidaten, key=lambda x: abs((x[0] - ziel).total_seconds()))
    return aktuell - alt


def abo_bilanz(signal_ids: Iterable[int],
               platformen: dict[int, str] | None = None) -> dict[int, dict]:
    """Aktuelle Abonnenten + 7-/30-Tage-Bilanz aus dem gespiegelten Verlauf.

    Quelle ist ausschließlich die lokale Tabelle subscriber_history (kein
    REST-Aufruf). Plattform-Version wird bevorzugt; ohne Angabe zählt die
    Version mit dem neuesten Messpunkt. Fehlender Vergleichspunkt (Verlauf
    zu kurz) ergibt None — kein geratener Wert.
    """
    platformen = platformen or {}
    out: dict[int, dict] = {}
    for signal_id in signal_ids:
        leer = {"abonnenten": None, "tage7": None, "tage30": None,
                "stand": None, "version": None}
        versionen: dict[str, list[tuple[datetime, int | None]]] = {}
        for p in db.get_history(signal_id):
            try:
                ts = datetime.fromisoformat(str(p["ts"]))
            except ValueError:
                continue
            versionen.setdefault(p["version"], []).append(
                (ts, p["subscribers"]))
        if not versionen:
            out[signal_id] = leer
            continue
        pref = downloader_client.platform_version(platformen.get(signal_id, ""))
        if pref not in versionen:
            pref = max(versionen,
                       key=lambda v: max(ts for ts, _ in versionen[v]))
        reihe = sorted(versionen[pref])
        aktuell_ts, aktuell = reihe[-1]
        out[signal_id] = {
            "abonnenten": aktuell,
            "tage7": _bilanz(reihe, 7, aktuell),
            "tage30": _bilanz(reihe, 30, aktuell),
            "stand": aktuell_ts,
            "version": pref,
        }
    return out
