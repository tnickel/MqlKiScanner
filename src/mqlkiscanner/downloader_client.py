# -*- coding: utf-8 -*-
"""REST-Client für das MqlDownloader-Interface (v1, rein lesend).

Der MqlDownloader läuft im LAN und hält Abonnenten-Historien und
Testreport-PDFs je Signal-ID vor (Doku:
MqlDownloader/doc/REST_API_Dokumentation.md). Dieser Client holt
ausschließlich Lesedaten — Tradelisten bleiben bewusst außen vor, denn
die Engine arbeitet mit den eigenen, verifizierten Exporten.

Konventionen der API: alle Pfade GET unter {base}/api/v1, Token optional
im Header `X-API-Token`, Fehler immer JSON `{"error": ...}` (401 falscher
Token, 404 Objekt existiert nicht — z. B. Signal nie geladen; 404 ist
kein Systemfehler).
"""
from __future__ import annotations

from urllib.parse import quote, urlsplit

import requests

from . import secrets_store

TIMEOUT_S = 8.0


class DownloaderError(RuntimeError):
    """Basisfehler der Downloader-Anbindung."""


class DownloaderNotConfigured(DownloaderError):
    """Es ist keine Base-URL gespeichert."""


class DownloaderConnectionError(DownloaderError):
    """Downloader nicht erreichbar (Netzwerk/Timeout)."""


class DownloaderAuthError(DownloaderError):
    """Token fehlt oder ist falsch (HTTP 401)."""


class DownloaderNotFound(DownloaderError):
    """Objekt existiert im Downloader nicht (HTTP 404) — kein Systemfehler."""


def normalize_base_url(url: str) -> str:
    """Base-URL vereinheitlichen: Host:Port genügt, /api/v1 wird ergänzt.

    Akzeptiert `http://host:8089`, `http://host:8089/` und
    `http://host:8089/api/v1` (auch mit Punkt am Ende). Ein eigener Pfad
    bleibt unverändert. Ungültige Eingaben (ohne http/https oder Host)
    lösen einen DownloaderError aus.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DownloaderError(
            "Base-URL muss mit http:// oder https:// und einem Host beginnen.")
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        pass
    elif path == "":
        path = "/api/v1"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def platform_version(platform: str) -> str | None:
    """ScanResult-Plattform ("MT4"/"MT5") → API-Version ("mql4"/"mql5")."""
    value = (platform or "").strip().lower()
    if value in ("mt4", "mql4"):
        return "mql4"
    if value in ("mt5", "mql5"):
        return "mql5"
    return None


class DownloaderClient:
    """Dünner GET-Wrapper um die Downloader-REST-API."""

    def __init__(self, base_url: str, token: str = "", timeout: float = TIMEOUT_S):
        self.base = normalize_base_url(base_url)
        self.token = (token or "").strip()
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"X-API-Token": self.token} if self.token else {}

    def _get(self, path: str, *, params: dict | None = None, raw: bool = False):
        """GET ausführen; Fehler klar sortieren (Netz vs. Auth vs. 404)."""
        url = f"{self.base}{path}"
        try:
            response = requests.get(url, params=params or None,
                                    headers=self._headers(), timeout=self.timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise DownloaderConnectionError(
                f"MqlDownloader unter {self.base} nicht erreichbar "
                f"({type(exc).__name__}). Läuft der Downloader und stimmen "
                "Host/Port?") from exc
        if response.status_code == 401:
            raise DownloaderAuthError(
                "Der Downloader verlangt einen anderen API-Token "
                "(HTTP 401). Gespeicherten Token im Admin-Bereich prüfen.")
        if response.status_code == 404:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = ""
            raise DownloaderNotFound(
                detail or f"Nicht gefunden: {path} (HTTP 404). "
                "Signal im Downloader möglicherweise nie geladen.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = response.text[:200]
            raise DownloaderError(
                f"HTTP {response.status_code} von {path}: {detail}")
        return response.content if raw else response.json()

    def health(self) -> dict:
        """Verbindungstest: status/service/apiVersion/providers/tokenRequired."""
        return self._get("/health")

    def provider(self, signal_id: int) -> list[dict]:
        """Provider-Objekt je Version (ein Signal kann mql4 UND mql5 sein)."""
        data = self._get(f"/providers/{int(signal_id)}")
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def history(self, signal_id: int, version: str) -> list[dict]:
        """Abonnenten-Historie: Punkte aufsteigend mit ts/subscribers/change."""
        data = self._get(f"/providers/{int(signal_id)}/{version}/history")
        points = data.get("points", [])
        return points if isinstance(points, list) else []

    def reports(self, signal_id: int, version: str) -> list[dict]:
        """Testreport-PDFs: name/sizeBytes/lastModified/href je Datei."""
        data = self._get(f"/providers/{int(signal_id)}/{version}/reports")
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def download_report(self, signal_id: int, version: str, name: str) -> bytes:
        """PDF-Binärdaten; der Name wird exakt und URL-codiert übernommen."""
        return self._get(
            f"/providers/{int(signal_id)}/{version}/reports/{quote(name, safe='')}",
            raw=True)


def client_from_settings(settings: dict) -> DownloaderClient:
    """Client aus gespeicherter Konfiguration; Token kommt aus secrets_store."""
    base = str(settings.get("downloader_base_url") or "").strip()
    if not base:
        raise DownloaderNotConfigured(
            "Kein MqlDownloader konfiguriert. Base-URL im Admin-Bereich "
            "unter „MqlDownloader“ hinterlegen.")
    return DownloaderClient(base, token=secrets_store.get_secret("downloader_token"))
