# -*- coding: utf-8 -*-
"""REST-Client für das KiScanner-Sync-Protokoll v1 des MqlTradeMonitor.

Der MqlTradeMonitor (Spring-Boot-Tradeserver, Projekt
D:\\AntiGravitySoftware\\GitWorkspace\\MqlTradeMonitor) nimmt normally
MetaTrader-EAs per /api/register auf. Der MqlKiScanner ist KEIN EA und
bekommt deshalb eine Sonderbehandlung: ein eigenes Protokoll unter
{base}/api/kiscanner, das zwingend diese Reihenfolge einhält —
Register (Handshake) → Signals → Documents (je eines) → Complete. Ohne
erfolgreichen Register-Handshake nimmt der Server keine Daten an;
jeder Aufruf trägt den Server-API-Key im Header `X-User-Key`.

Der Sync ist ein Einmallauf: verbinden, alles übertragen, fertig —
danach besteht keine Verbindung mehr (zustandsloses HTTP). Doku:
doc/06_tradeserver-sync.md hier sowie Doku/MqlKiScanner_Integration.md
im Tradeserver-Projekt.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import requests

from . import __version__, secrets_store

PROTOKOLL_VERSION = 1
CLIENT_NAME = "MqlKiScanner"
TIMEOUT_S = 20.0


class TradeserverError(RuntimeError):
    """Basisfehler der Tradeserver-Anbindung."""


class TradeserverNotConfigured(TradeserverError):
    """Es ist keine Base-URL gespeichert."""


class TradeserverConnectionError(TradeserverError):
    """Tradeserver nicht erreichbar (Netzwerk/Timeout)."""


class TradeserverAuthError(TradeserverError):
    """API-Key fehlt oder ist falsch (HTTP 401)."""


class TradeserverProtocolError(TradeserverError):
    """Server lehnt das Protokoll ab (HTTP 400) — z. B. falsche Client-
    Kennung, falsche Protokollversion oder Schritte außer der Reihe."""


def normalize_base_url(url: str) -> str:
    """Base-URL vereinheitlichen: `http://host:8080` genügt, Slash-Enden
    entfallen. Ein eventueller Pfad (Kontext-Pfad) bleibt unverändert;
    `/api/kiscanner` hängt der Client selbst an. Ungültige Eingaben
    lösen einen TradeserverError aus.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise TradeserverError(
            "Base-URL muss mit http:// oder https:// und einem Host beginnen.")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class TradeserverClient:
    """Dünner Wrapper um das KiScanner-Sync-Protokoll v1 (POST-lastig)."""

    def __init__(self, base_url: str, api_key: str = "", timeout: float = TIMEOUT_S):
        self.base = normalize_base_url(base_url)
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"X-User-Key": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, path: str, *, payload: dict | None = None):
        """Request ausführen; Fehler klar sortieren (Netz vs. Auth vs. Protokoll)."""
        url = f"{self.base}/api/kiscanner{path}"
        try:
            response = requests.request(method, url, json=payload,
                                        headers=self._headers(),
                                        timeout=self.timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise TradeserverConnectionError(
                f"Tradeserver unter {self.base} nicht erreichbar "
                f"({type(exc).__name__}). Läuft der Server und stimmt die "
                "IP/URL in den Einstellungen?") from exc

        def _detail() -> str:
            try:
                body = response.json()
            except ValueError:
                return response.text[:200]
            return str(body.get("message") or body.get("error") or "")[:300]

        if response.status_code == 401:
            raise TradeserverAuthError(
                "Der Tradeserver hat den API-Key abgelehnt (HTTP 401). Key "
                "im Admin-Bereich prüfen; er muss zu einem Benutzer mit "
                "hinterlegtem API-Key im MqlTradeMonitor passen.")
        if response.status_code == 400:
            raise TradeserverProtocolError(
                f"Protokollfehler vom Tradeserver: {_detail() or 'HTTP 400'}")
        if response.status_code >= 400:
            raise TradeserverError(
                f"HTTP {response.status_code} von {path}: {_detail()}")
        try:
            return response.json()
        except ValueError as exc:
            raise TradeserverError(
                f"Unerwartete Antwort von {path} (kein JSON).") from exc

    def _get(self, path: str):
        return self._request("GET", path)

    def _post(self, path: str, payload: dict):
        return self._request("POST", path, payload=payload)

    # --- Protokollschritte (Reihenfolge ist Pflicht) ----------------------

    def ping(self) -> dict:
        """Verbindungstest: status/service/api-Version/serverTime."""
        return self._get("/ping")

    def register(self, signal_count: int = 0) -> dict:
        """Handshake: meldet den MqlKiScanner an und startet einen Sync-Lauf.

        Antwort enthält runId sowie den Serverbestand (documents mit
        sha256, signalIds) — die Grundlage für den clientseitigen Diff.
        """
        return self._post("/register", {
            "client": CLIENT_NAME,
            "protocolVersion": PROTOKOLL_VERSION,
            "scannerVersion": __version__,
            "signalCount": int(signal_count),
        })

    def signals(self, zeilen: list[dict]) -> dict:
        """Vollständiger Tabellen-Snapshot; ersetzt den Serverbestand."""
        return self._post("/signals", {"signals": zeilen})

    def document(self, dokument: dict) -> dict:
        """Ein Dokument (PDF) übertragen; sha256 gleicher Dateien bleibt unangetastet."""
        return self._post("/documents", dokument)

    def complete(self, *, signals: int, documents: int, uploaded: int,
                 skipped: int, bytes_total: int) -> dict:
        """Sync-Lauf ordnungsgemäß abschließen — danach ist die Verbindung beendet."""
        return self._post("/complete", {
            "signals": int(signals), "documents": int(documents),
            "uploaded": int(uploaded), "skipped": int(skipped),
            "bytes": int(bytes_total)})

    def abort(self, reason: str = "") -> dict:
        """Sync-Lauf im Fehlerfall abbrechen (Best-Effort, nie werfen)."""
        return self._post("/abort", {"reason": str(reason or "")[:500]})


def client_from_settings(settings: dict) -> TradeserverClient:
    """Client aus gespeicherter Konfiguration; Key kommt aus secrets_store."""
    base = str(settings.get("tradeserver_base_url") or "").strip()
    if not base:
        raise TradeserverNotConfigured(
            "Kein Tradeserver konfiguriert. Base-URL im Admin-Bereich "
            "unter „Tradeserver“ hinterlegen.")
    return TradeserverClient(base,
                             api_key=secrets_store.get_secret("tradeserver_api_key"))
