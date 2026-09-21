# -*- coding: utf-8 -*-
"""Schreibgeschütztes REST-Interface für den MqlRealMonitor (Java-Client).

Konvention wie beim MqlDownloader: alle Pfade GET unter {base}/api/v1,
Token optional (Header `X-User-Key`, gespeichert im secrets_store —
Einstellungen bleiben geheimnisfrei, siehe Secret-Hygiene-Test).

Endpunkte:
  GET /api/v1/health    -> Statusmeldung (Version, Dienst)
  GET /api/v1/signals   -> Signalliste mit Gesamt-Ampel je Signal
                           Query-Parameter `ampel` (Kommaliste) filtert
                           serverseitig, z. B. ?ampel=gruen,gelb

Grundregeln (wie beim Tradeserver-Sync): Der Server liest ausschließlich
die SQLite-Datenbank und bewertet NIE neu — die Ampel wird mit
pipeline.ampel_for aus den gespeicherten Werten und den aktuellen
Einstellungen abgeleitet, exakt wie die Ergebnisse-Seite. Es gibt keine
Dauerverbindung: Der MqlRealMonitor holt sich die Liste, wenn der Nutzer
den KiScanner-Button drückt.

Der Server lauscht standardmäßig nur auf 127.0.0.1 (kein Fernzugriff),
läuft als Daemon-Thread neben der Streamlit-App und ist auch standalone
startbar:  python -m mqlkiscanner.rest_api
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from . import __version__, config, pipeline, secrets_store

log = logging.getLogger(__name__)

SERVICE_NAME = "mqlkiscanner"
API_PREFIX = "/api/v1"
DEFAULT_PORT = 8611
DEFAULT_BIND = "127.0.0.1"  # nur lokal; Fernzugriff bewusst nicht vorgesehen

# Gilt ein Client noch als "verbunden"? Der MqlRealMonitor fragt bewusst
# NUR auf Knopfdruck ab (kein periodischer Ping) — deshalb zeigt die Sidebar
# nicht "gerade aktiv", sondern "zuletzt um HH:MM" (grün, sobald jemals
# abgerufen wurde).

# Laufzeit-State: letzter erfolgreicher (authentifizierter) Client-Abruf.
# Modul-global, damit der Server-Thread schreibt und die Streamlit-UI liest.
_client_state = {"ts": None}
_client_lock = threading.Lock()


def notiere_client_zugriff() -> None:
    """Server-Thread: erfolgreichen Client-Kontakt vermerken."""
    with _client_lock:
        _client_state["ts"] = time.time()
    log.info("REST-Client-Kontakt: %s",
             datetime.now().strftime("%H:%M:%S"))


def letzter_client_zugriff() -> datetime | None:
    """Wann erreichte den Server zuletzt ein Client? (None = nie)"""
    with _client_lock:
        ts = _client_state["ts"]
    return datetime.fromtimestamp(ts) if ts else None


def client_status() -> dict:
    """Verbindungsstatus für die Sidebar: hat der Client schon abgerufen?

    Der MqlRealMonitor holt die Signalliste nur auf Knopfdruck — der Status
    ist deshalb "verbunden" (grün), sobald mindestens ein Abruf erfolgt ist;
    `letzter_abruf` zeigt wann. /health-Checks zählen nicht (Server-Test,
    kein Client-Abruf).
    """
    with _client_lock:
        ts = _client_state["ts"]
    if ts is None:
        return {"verbunden": False, "letzter_abruf": None, "alter_s": None}
    return {"verbunden": True,
            "letzter_abruf": datetime.fromtimestamp(ts),
            "alter_s": int(time.time() - ts)}

# Gesamt-Ampel (ampel_for) → ASCII-Kürzel für Maschinen-Clients.
AMPEL_ASCII = {
    "🟢": "gruen",
    "🟡": "gelb",
    "🟠": "orange",
    "🔴": "rot",
    "⚪": "keine_daten",
    "⛔": "ausgeschlossen",
}

# Normalisierung des Filter-Parameters: Emoji, deutsche Schreibweisen
# (auch mit Umlaut) und englische Namen sind zulässig.
_AMPEL_ALIASES = {
    "gruen": "gruen", "grün": "gruen", "green": "gruen", "🟢": "gruen",
    "gelb": "gelb", "yellow": "gelb", "🟡": "gelb",
    "orange": "orange", "🟠": "orange",
    "rot": "rot", "red": "rot", "🔴": "rot",
    "keine_daten": "keine_daten", "keine daten": "keine_daten",
    "no_data": "keine_daten", "⚪": "keine_daten",
    "ausgeschlossen": "ausgeschlossen", "excluded": "ausgeschlossen", "⛔": "ausgeschlossen",
}


def ampel_ascii(ampel: str | None) -> str:
    """Emoji-Ampel → ASCII-Kürzel; Unbekanntes wird leer geliefert."""
    return AMPEL_ASCII.get(ampel or "", "")


def normalize_ampel_filter(raw: str | None) -> set[str] | None:
    """Filter-Parameter (`?ampel=gruen,gelb`) in Kürzel-Menge umsetzen.

    None/leer → None (= kein Filter, alle Signale). Unbekannte Begriffe
    lösen ValueError aus — still ignorieren würde einen Filter
    vortäuschen, der nichts filtert.
    """
    if raw is None or not raw.strip():
        return None
    result: set[str] = set()
    for token in raw.split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key not in _AMPEL_ALIASES:
            raise ValueError(f"Unbekannter Ampel-Wert: {token.strip()!r}")
        result.add(_AMPEL_ALIASES[key])
    return result or None


def signal_payload(results, ampel_filter: set[str] | None = None) -> dict:
    """ScanResult-Liste → REST-Payload (eine Zeile je Signal).

    Feldnamen folgen dem Tradeserver-Protokoll v1 (camelCase); `ampel`
    ist das ASCII-Kürzel, `ampelEmoji` das Original der Ergebnis-Ansicht.
    """
    zeilen = []
    for r in results:
        kurz = ampel_ascii(getattr(r, "ampel", ""))
        if ampel_filter is not None and kurz not in ampel_filter:
            continue
        zeilen.append({
            "signalId": int(r.id),
            "name": r.name or "",
            "platform": getattr(r, "platform", "") or "",
            "url": r.url or (f"https://www.mql5.com/en/signals/{r.id}" if r.id else ""),
            "ampel": kurz,
            "ampelEmoji": getattr(r, "ampel", "") or "",
            "score": r.score,
            "urteil": r.urteil or "",
            "kurzfassung": getattr(r, "kurzfassung", "") or "",
        })
    return {
        "service": SERVICE_NAME,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "count": len(zeilen),
        "signals": zeilen,
    }


class _RestApiHandler(BaseHTTPRequestHandler):
    """Nur GET; jede Antwort ist JSON mit klarem Content-Type."""

    server_version = f"MqlKiScannerREST/{__version__}"

    # Injiziert über build_server(): () -> list[ScanResult], token: str
    results_provider: Callable = staticmethod(lambda: [])
    token: str = ""

    def do_GET(self):  # noqa: N802 (http.server-Konvention)
        parsed = urlsplit(self.path)
        if parsed.path not in (f"{API_PREFIX}/health", f"{API_PREFIX}/signals"):
            self._send_json(404, {"error": "unbekannter Pfad",
                                  "pfad": parsed.path})
            return
        if self.token and not self._token_ok():
            self._send_json(401, {"error": "Token fehlt oder ist falsch "
                                           "(Header X-User-Key)"})
            return
        try:
            if parsed.path.endswith("/health"):
                self._send_json(200, {"status": "ok", "service": SERVICE_NAME,
                                      "version": __version__,
                                      "restApi": "v1"})
            else:
                params = parse_qs(parsed.query)
                try:
                    ampel_filter = normalize_ampel_filter(
                        (params.get("ampel") or [None])[0])
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                # NEU: Client-Kontakt für die Sidebar-Anzeige vermerken
                # (erst nach bestandenem Token-Check)
                notiere_client_zugriff()
                payload = signal_payload(self.results_provider(), ampel_filter)
                self._send_json(200, payload)
        except Exception as exc:  # Datenbank-/Lesefehler sauber melden
            log.exception("REST-Request fehlgeschlagen: %s", self.path)
            self._send_json(500, {"error": f"interner Fehler: {exc}"})

    def _token_ok(self) -> bool:
        gegeben = self.headers.get("X-User-Key", "")
        return hmac.compare_digest(gegeben.strip(), self.token)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args):  # stderr-Log → logging umbiegen
        log.debug("%s - %s", self.address_string(), fmt % args)


def build_server(port: int = DEFAULT_PORT, bind: str = DEFAULT_BIND,
                 token: str = "",
                 results_provider: Callable | None = None) -> ThreadingHTTPServer:
    """Server bauen (gebunden, noch nicht gestartet) — für Tests und standalone."""
    handler = type("MqlKiScannerRestHandler", (_RestApiHandler,), {
        "results_provider": staticmethod(results_provider
                                         or _results_aus_db),
        "token": (token or "").strip(),
    })
    return ThreadingHTTPServer((bind, port), handler)


def _results_aus_db():
    """Standard-Datenquelle: gespeicherte Signale, Ampel wie Ergebnis-Ansicht."""
    return pipeline.results_from_db()


def konfiguriert(settings: dict | None = None) -> bool:
    """Ist die REST-API in den Einstellungen eingeschaltet?"""
    settings = settings if settings is not None else config.load_settings()
    return bool(settings.get("rest_api_enabled", True))


def start_background(settings: dict | None = None) -> ThreadingHTTPServer | None:
    """REST-Server als Daemon-Thread neben der Streamlit-App starten.

    Liefert None, wenn die API deaktiviert ist oder der Port belegt ist
    (z. B. läuft bereits eine Instanz) — die App läuft dann ohne weiter.
    """
    settings = settings if settings is not None else config.load_settings()
    if not konfiguriert(settings):
        log.info("REST-API deaktiviert (Einstellung rest_api_enabled)")
        return None
    port = int(settings.get("rest_api_port") or DEFAULT_PORT)
    token = secrets_store.get_secret("rest_api_token")
    try:
        server = build_server(port=port, token=token)
    except OSError as exc:
        log.warning("REST-API nicht gestartet (Port %s belegt oder gesperrt): %s",
                    port, exc)
        return None
    import threading
    threading.Thread(target=server.serve_forever, name="mqlkiscanner-rest",
                     daemon=True).start()
    log.info("REST-API läuft auf http://%s:%s%s (Token %s)",
             DEFAULT_BIND, port, API_PREFIX, "aktiv" if token else "aus")
    return server


def main() -> None:
    """Standalone-Betrieb ohne Streamlit: python -m mqlkiscanner.rest_api"""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = config.load_settings()
    server = start_background(settings)
    if server is None:
        raise SystemExit("REST-API konnte nicht gestartet werden "
                         "(deaktiviert oder Port belegt).")
    bind, port = server.server_address[:2]
    print(f"MqlKiScanner REST-API: http://{bind}:{port}{API_PREFIX}/signals"
          "  (Beenden mit Strg+C)")
    try:
        import threading
        threading.Event().wait()  # endlos warten (Daemon-Thread arbeitet)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
