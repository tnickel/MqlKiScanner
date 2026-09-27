# -*- coding: utf-8 -*-
"""Datenquellen-Registry des Multi-Source-Hubs (Konzept doc/20).

Eine Datenquelle ist ein REST-Anbieter (Typ `mql5-downloader-v1`: der
MqlDownloader), der Katalog, Tradelisten, Kennzahlen, Abonnenten-Verlauf und
Testreport-PDFs liefert. Der Scanner kann beliebig viele Quellen haben —
jede mit einem eindeutigen Kürzel, das in der Ergebnisliste die Herkunft
der Signale zeigt.

Dieses Modul verwaltet die Registry (Tabelle `datenquellen`) und prüft
Verbindungen (Ampel 🟢 erreichbar / 🟡 eingeschränkt / 🔴 Fehler). Daten
WERDEN hier nicht bewertet und nicht gespiegelt — dafür sind ingest.py
(Katalog/Trades/Metrics) und downloader_sync.py (Verlauf/PDFs) zuständig.
"""
from __future__ import annotations

from datetime import datetime

from . import config, db, downloader_client, secrets_store

# Token je Quelle im Secrets-Speicher (nie in der DB, nie im Repo).
def token_schluessel(quelle_id: int) -> str:
    return f"datenquelle_{int(quelle_id)}_token"


_letzte_pruefung_cache: dict[int, tuple[datetime, dict]] = {}
_PRUEF_TTL_S = 30.0  # Rerun-Schutz; der manuelle Test umgeht mit force=True


def _ensure() -> None:
    """Schema + einmalige Übernahme der alten Einzel-Downloader-Konfiguration.

    Stand bisher nur `downloader_base_url` in den Settings (Vor-Multi-Source),
    wird genau eine Quelle mit Kürzel `mql5` daraus — Token inklusive.
    """
    db.init_db()
    if db.list_quellen():
        return
    legacy = str(config.load_settings().get("downloader_base_url") or "").strip()
    if not legacy:
        return
    quelle_id = db.add_quelle(
        "mql5", "MqlDownloader (übernommen)", legacy,
        typ="mql5-downloader-v1", aktiv=True)
    alt = secrets_store.get_secret("downloader_token")
    if alt:
        secrets_store.save_secrets(**{token_schluessel(quelle_id): alt})


def client_fuer_quelle(quelle: dict,
                       timeout: float | None = None) -> downloader_client.DownloaderClient:
    """REST-Client für eine Quellen-Zeile aus list_quellen()."""
    client = downloader_client.DownloaderClient(
        quelle["base_url"],
        token=secrets_store.get_secret(token_schluessel(quelle["id"])))
    if timeout is not None:
        client.timeout = timeout
    return client


def quellen_definiert() -> bool:
    _ensure()
    return bool(db.list_quellen())


def pruefe(quelle: dict, *, force: bool = False,
           timeout: float = 5.0) -> dict:
    """Connection-Test einer Quelle mit Ampel-Status.

    Rückgabe: {"status": "ok"|"eingeschraenkt"|"fehler", "farbe", "text",
    "details": {version, anbieter, latenz_s, fehler}, "geprueft": datetime}.
    🟡 eingeschränkt = erreichbar, aber z. B. Token gefordert und keiner
    hinterlegt. Das Ergebnis wird je Quelle in der DB festgehalten, damit
    die Übersicht ohne neuen Aufruf den letzten Stand zeigen kann.
    """
    _ensure()
    jetzt = datetime.now()
    quelle_id = int(quelle["id"])
    # Cache-Schlüssel inkl. base_url: zieht eine Quelle um, wird neu geprüft.
    cache_schluessel = (quelle_id, str(quelle.get("base_url") or ""))
    if not force:
        cache = _letzte_pruefung_cache.get(cache_schluessel)
        if cache and (jetzt - cache[0]).total_seconds() < _PRUEF_TTL_S:
            return cache[1]
    base = {
        "status": "fehler", "farbe": "red",
        "text": "Nicht erreichbar", "details": {},
        "geprueft": jetzt,
    }
    try:
        start = datetime.now()
        info = client_fuer_quelle(quelle, timeout=timeout).health()
        latenz = round((datetime.now() - start).total_seconds(), 2)
        ok = str(info.get("status", "")).lower() == "ok"
        token_noch_noetig = bool(info.get("tokenRequired")) and not \
            secrets_store.get_secret(token_schluessel(quelle_id))
        if ok and token_noch_noetig:
            base.update(status="eingeschraenkt", farbe="orange",
                        text="Erreichbar — Token erforderlich, aber keiner hinterlegt")
        elif ok:
            base.update(status="ok", farbe="green",
                        text="Erreichbar",
                        details={"version": info.get("apiVersion"),
                                 "anbieter": info.get("providers")})
        else:
            base.update(text=f"Unerwarteter Status: {info.get('status')!r}")
        base["details"]["latenz_s"] = latenz
        base["details"]["token_required"] = bool(info.get("tokenRequired"))
    except downloader_client.DownloaderError as exc:
        base["text"] = str(exc)
        base["details"]["fehler"] = str(exc)
    except Exception as exc:  # Netzwerk-Fehler dieser Seite sind Auskunft, kein Crash
        base["text"] = f"{type(exc).__name__}: {exc}"
        base["details"]["fehler"] = base["text"]
    _letzte_pruefung_cache[cache_schluessel] = (jetzt, base)
    db.store_quell_pruefung(quelle_id, {
        "status": base["status"], "farbe": base["farbe"], "text": base["text"],
        "details": base["details"], "geprueft": base["geprueft"].isoformat(
            sep=" ", timespec="seconds")})
    return base


def pruefe_alle(*, force: bool = False, timeout: float = 5.0) -> dict[int, dict]:
    """Alle Quellen testen (Admin „Alle Quellen testen“)."""
    _ensure()
    return {int(q["id"]): pruefe(q, force=force, timeout=timeout)
            for q in db.list_quellen() if q["aktiv"]}


def status_zeichen(pruefung: dict | None) -> str:
    """Ampel-Kurzzeichen für Tabellen/Badges (🟢/🟡/🔴/⚪ nie geprüft)."""
    farbe = str((pruefung or {}).get("farbe") or "")
    return {"green": "🟢", "orange": "🟡", "red": "🔴"}.get(farbe, "⚪")
