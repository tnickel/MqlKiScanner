# -*- coding: utf-8 -*-
"""REST-Client für das gemeinsame Quellen-Interface (v1).

Der MqlDownloader läuft im LAN und hält Abonnenten-Historien und
Testreport-PDFs je Signal-ID vor (Doku:
MqlDownloader/doc/REST_API_Dokumentation.md). Dieser Client holt
Kataloge und Artefakte einschließlich Tradelisten. Explizite Update-Aufträge
erneuern Quellenbestände; der gezielte Anbieterabruf wartet auf seinen eigenen
vollständigen Plattformabruf. Bewertung findet in diesem Client nicht statt.

Konventionen der API: alle Pfade GET unter {base}/api/v1, Token optional
im Header `X-API-Token`, Fehler immer JSON `{"error": ...}` (401 falscher
Token, 404 Objekt existiert nicht — z. B. Signal nie geladen; 404 ist
kein Systemfehler).
"""
from __future__ import annotations

from urllib.parse import quote, urlsplit
import time

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


class DownloaderUpdateNotSupported(DownloaderError):
    """Client kennt POST /update nicht (HTTP 405) — älterer Build (doc/23 §8)."""


class DownloaderBusy(DownloaderError):
    """Client ist mit einer anderen Aktion beschäftigt (HTTP 409, doc/23 §4.1)."""


class DownloaderProviderBlocked(DownloaderError):
    """Gezielter Plattformabruf ist wegen fehlender Quellenbelege gesperrt."""


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
    """ScanResult-Plattform ("MT4"/"MT5") → API-Version ("mql4"/"mql5").

    „pelican“, „vantage“ und „zulu“ sind die Versions-Kürzel der gleich-
    namigen Plattform-Quellen (dasselbe REST-Protokoll, doc/20); sie
    bleiben unverändert durchgereicht."""
    value = (platform or "").strip().lower()
    if value in ("mt4", "mql4"):
        return "mql4"
    if value in ("mt5", "mql5"):
        return "mql5"
    if value in ("pelican", "vantage", "zulu"):
        return value
    return None


class DownloaderClient:
    """Quellen-REST mit getrennten Lese- und Aktualisierungsaufträgen."""

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
        if raw:
            return response.content
        try:
            return response.json()
        except ValueError as exc:
            # Wartungsseite/HTML mit Status 200: früher entkam das als
            # requests JSONDecodeError und ließ den GESAMTEN Scan sterben,
            # obwohl nur eine Quelle streikt (Review 29.09.).
            raise DownloaderError(
                f"Antwort von {path} ist kein JSON "
                f"(Beginn: {response.text[:80]!r})") from exc

    def health(self) -> dict:
        """Verbindungstest: status/service/apiVersion/providers/tokenRequired."""
        return self._get("/health")

    def provider(self, signal_id: int) -> list[dict]:
        """Provider-Objekt je Version (ein Signal kann mql4 UND mql5 sein)."""
        data = self._get(f"/providers/{int(signal_id)}")
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def katalog(self, *, version: str | None = None, limit: int = 500,
                offset: int = 0, min_subscribers: int = 1,
                catalog_scope: str | None = None) -> dict:
        """Katalogseite im gewählten Abonnenten-Scope.

        Der bisherige Scan-Scope bleibt mindestens ein Abonnent. Die
        Vollübersicht fordert ausdrücklich ``min_subscribers=0`` an.
        """
        params: dict = {"limit": int(limit), "offset": int(offset),
                        "minSubscribers": int(min_subscribers)}
        if catalog_scope is not None:
            if catalog_scope not in {"full", "subscribers"}:
                raise ValueError("catalog_scope muss full oder subscribers sein")
            params["catalogScope"] = catalog_scope
        if version:
            params["version"] = version
        return self._get("/providers", params=params)

    @staticmethod
    def _v(version: str) -> str:
        """version URL-codiert für den Pfad — unverändert eingesetzt würde
        „../../admin" serverseitig zu /api/admin/… (Review 29.09., D)."""
        return quote(str(version), safe="")

    def metrics(self, signal_id: int, version: str) -> dict:
        """Kennzahlen-Antwort komplett: metrics{Balance, EquityDrawdown,
        MaxDDGraphic, 3MPDD …}, monthProfits, drawdown-Reihe, file."""
        data = self._get(f"/providers/{int(signal_id)}/{self._v(version)}/metrics")
        return data if isinstance(data, dict) else {}

    def trades_csv(self, signal_id: int, version: str) -> bytes:
        """Tradeliste als Original-mql5-CSV (Rohbytes, Header 1:1)."""
        return self._get(
            f"/providers/{int(signal_id)}/{self._v(version)}/trades.csv",
            raw=True)

    def history(self, signal_id: int, version: str) -> list[dict]:
        """Abonnenten-Historie: Punkte aufsteigend mit ts/subscribers/change."""
        data = self._get(f"/providers/{int(signal_id)}/{self._v(version)}/history")
        points = data.get("points", [])
        return points if isinstance(points, list) else []

    def reports(self, signal_id: int, version: str) -> list[dict]:
        """Testreport-PDFs: name/sizeBytes/lastModified/href je Datei."""
        data = self._get(f"/providers/{int(signal_id)}/{self._v(version)}/reports")
        items = data.get("items", [])
        return items if isinstance(items, list) else []

    def download_report(self, signal_id: int, version: str, name: str) -> bytes:
        """PDF-Binärdaten; Version und Name werden exakt und URL-codiert übernommen."""
        return self._get(
            f"/providers/{int(signal_id)}/{self._v(version)}/reports/{quote(name, safe='')}",
            raw=True)

    # ── Stufe 0 „Clients aktualisieren" (doc/23 §4) ────────────────────
    # Die Server sind historisch rein lesend; das Update-Job-Protokoll
    # fügt genau EINEN Schreib-Endpoint hinzu (POST /update) plus Status-
    # Abfrage. Ältere Client-Builds antworten 405 — das ist der saubere
    # „noch nicht umgestellt"-Fall, kein Verbindungsfehler.

    def _post(self, path: str, *, payload: dict | None = None):
        """POST ausführen (nur Update-Job); Fehlersortierung wie _get."""
        url = f"{self.base}{path}"
        try:
            response = requests.post(url, json=payload or {},
                                     headers=self._headers(), timeout=self.timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise DownloaderConnectionError(
                f"Client unter {self.base} nicht erreichbar "
                f"({type(exc).__name__}). Läuft der Client und stimmen Host/Port?"
            ) from exc
        if response.status_code == 401:
            raise DownloaderAuthError(
                "Der Client verlangt einen anderen API-Token (HTTP 401). "
                "Gespeicherten Token im Admin-Bereich prüfen.")
        if response.status_code == 405:
            raise DownloaderUpdateNotSupported(
                "Client-Version ohne Update-Endpoint (HTTP 405) — der Client "
                "muss auf die Stufe-0-Version aktualisiert werden.")
        if response.status_code == 409:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = ""
            raise DownloaderBusy(
                detail or "Client ist beschäftigt (HTTP 409) — z. B. läuft "
                "gerade eine andere Aktion im Fenster.")
        if response.status_code == 422:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = ""
            raise DownloaderProviderBlocked(detail or "Anbieterabruf durch die Quelle gesperrt.")
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = response.text[:200]
            raise DownloaderError(f"HTTP {response.status_code} von {path}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise DownloaderError(
                f"Antwort von {path} ist kein JSON "
                f"(Beginn: {response.text[:80]!r})") from exc

    def update_starten(self, *, target: int = 200, tradelisten: bool = True,
                       katalog_max_alter_h: int = 72, quelle: str = "signalkiscanner",
                       nur_abonnenten: bool = False) -> dict:
        """Stufe-0-Update-Job anstoßen (doc/23 §4.1). Antwort sofort:
        {"jobId": …, "status": "gestartet", "bereitsLaufend": bool}."""
        payload = {
            "target": int(target), "tradelisten": bool(tradelisten),
            "katalogMaxAlterH": int(katalog_max_alter_h), "quelle": str(quelle),
        }
        if nur_abonnenten:
            payload.update(nurAbonnenten=True, target=min(200, max(1, int(target))),
                           tradelisten=False, katalogMaxAlterH=0)
        return self._post("/update", payload=payload)

    def update_status(self) -> dict:
        """Job-Status des Clients (doc/23 §4.2): state/phase/done/total/
        message/ergebnis; state=idle wenn noch nie ein Job lief."""
        data = self._get("/update/status")
        return data if isinstance(data, dict) else {}

    def refresh_provider(self, signal_id: int, version: str, *,
                         timeout_s: float = 7200.0, poll_s: float = 1.0,
                         should_stop=None) -> dict:
        """Gezielt Plattformdaten erneuern, bis der eigene Vollabruf belegt ist.

        Ein lokales GET, ein fremder laufender Job oder eine bloße Annahme
        des Auftrags sind ausdrücklich kein Erfolgsnachweis. Alte Clients
        werden nicht auf ihren katalogweiten Updateweg zurückgestuft.
        """
        if isinstance(signal_id, bool) or int(signal_id) <= 0:
            raise ValueError("Anbieter-ID muss positiv sein.")
        sid = str(int(signal_id))
        version = str(version or "").strip().lower()
        if version not in {"mql4", "mql5", "pelican", "vantage", "zulu", "rst"}:
            raise ValueError("Unbekannte Quellenplattform.")
        if should_stop and should_stop():
            raise DownloaderError("Anbieterabruf vor dem Start abgebrochen.")
        health = self.health()
        if health.get("providerRefresh") is not True:
            reason = str(health.get("providerRefreshReason") or "")
            if reason:
                raise DownloaderProviderBlocked(reason)
            raise DownloaderUpdateNotSupported(
                "Client unterstützt keinen gezielten aktuellen Anbieterabruf; neuen Client aktivieren.")
        if should_stop and should_stop():
            raise DownloaderError("Anbieterabruf vor dem Start abgebrochen.")
        answer = self._post(f"/providers/{sid}/{self._v(version)}/refresh", payload={})
        if not isinstance(answer, dict) or answer.get("bereitsLaufend"):
            raise DownloaderBusy("Vorhandener Quellenjob ist kein neuer Anbieterabruf.")
        job_id = str(answer.get("jobId") or "")
        if not job_id:
            raise DownloaderError("Anbieterabruf ohne eindeutige Job-ID bestätigt.")
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            if should_stop and should_stop():
                raise DownloaderError("Warten auf Anbieterabruf abgebrochen; Quellenjob kann noch laufen.")
            status = self.update_status()
            if str(status.get("jobId") or "") != job_id:
                raise DownloaderError("Anbieterstatus gehört zu einem anderen Job; kein Frischenachweis.")
            state = str(status.get("state") or "")
            result = status.get("ergebnis")
            result = result if isinstance(result, dict) else {}
            if state == "done":
                if (str(result.get("providerId") or "") != sid
                        or result.get("version") != version
                        or result.get("platformRefreshed") is not True
                        or result.get("fullHistory") is not True
                        or not result.get("refreshedAt")
                        or result.get("tradelistenFehler")
                        or result.get("tradelistenAbgebrochen")):
                    raise DownloaderError("Quellenjob belegt keinen vollständigen aktuellen Abruf dieses Anbieters.")
                return dict(result, jobId=job_id)
            if state == "login_required":
                raise DownloaderAuthError(str(status.get("error") or status.get("message") or "Quellenlogin erforderlich."))
            if state in {"error", "cancelled", "aborted"}:
                raise DownloaderError(str(status.get("error") or status.get("message") or "Anbieterabruf fehlgeschlagen."))
            if time.monotonic() >= deadline:
                raise DownloaderConnectionError("Zeitlimit beim Anbieterabruf; Quellenjob kann noch laufen.")
            time.sleep(max(0.01, float(poll_s)))


def client_from_settings(settings: dict) -> DownloaderClient:
    """Client aus gespeicherter Konfiguration; Token kommt aus secrets_store."""
    base = str(settings.get("downloader_base_url") or "").strip()
    if not base:
        raise DownloaderNotConfigured(
            "Kein MqlDownloader konfiguriert. Base-URL im Admin-Bereich "
            "unter „MqlDownloader“ hinterlegen.")
    return DownloaderClient(base, token=secrets_store.get_secret("downloader_token"))
