"""Nichtblockierende Sidebar-Prüfungen; Threads verwenden keine Streamlit-API."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock, Thread
from time import monotonic

from . import config, db, downloader_client, quellen, secrets_store, tradeserver_client


class VerbindungsMonitor:
    """Ein Konfigleser, unabhängige Prüfungen und atomare UI-Snapshots."""

    def __init__(self, laden, pruefen, *, ttl=300.0, uhr=monotonic):
        self._laden, self._pruefen = laden, pruefen
        self._ttl, self._uhr = ttl, uhr
        self._lock = Lock()
        self._liest = False
        self._geladen = False
        self._fehler = False
        self._eintraege = {}

    def zustand(self):
        """Nur Speicher lesen und Arbeit anstoßen; niemals I/O abwarten."""
        with self._lock:
            starten = not self._liest
            if starten:
                self._liest = True
            wert = {"geladen": self._geladen, "fehler": self._fehler, "verbindungen": deepcopy([
                {"id": key, "name": e["ziel"]["name"],
                 "art": e["ziel"]["art"], "prueft": e["prueft"],
                 "ergebnis": e["ergebnis"]}
                for key, e in self._eintraege.items()])}
        if starten:
            Thread(target=self._aktualisieren, daemon=True,
                   name="sidebar-konfiguration").start()
        return wert

    def _aktualisieren(self):
        try:
            ziele = self._laden()
            starts = []
            with self._lock:
                aktuell = {}
                for ziel in ziele:
                    key = ziel["id"]
                    e = self._eintraege.get(key)
                    if e is None or e["ziel"] != ziel:
                        e = {"ziel": ziel, "prueft": False,
                             "ergebnis": None, "fertig": None}
                    aktuell[key] = e
                    if not e["prueft"] and (e["fertig"] is None or
                            self._uhr() - e["fertig"] >= self._ttl):
                        e["prueft"] = True
                        starts.append((key, e))
                self._eintraege = aktuell
                self._geladen = True
                self._fehler = False
            for key, e in starts:
                Thread(target=self._testen, args=(key, e), daemon=True,
                       name="sidebar-verbindung").start()
        except Exception:
            # Letzte Anzeige behalten; beim nächsten Fragment-Tick erneut lesen.
            with self._lock:
                self._fehler = True
        finally:
            with self._lock:
                self._liest = False

    def _testen(self, key, eintrag):
        try:
            ergebnis = self._pruefen(eintrag["ziel"])
        except Exception:
            # Keine URLs, Zugangsdaten oder fremden Antworttexte in der UI.
            ergebnis = {"ok": False, "eingeschraenkt": False}
        ergebnis = dict(ergebnis, geprueft=datetime.now())
        with self._lock:
            if self._eintraege.get(key) is eintrag:
                eintrag.update(ergebnis=ergebnis, prueft=False, fertig=self._uhr())


_initialisiert = None


def _konfiguration():
    global _initialisiert
    if _initialisiert != db.DB_PATH:
        quellen._ensure()
        _initialisiert = db.DB_PATH
    ziele = []
    for q in db.list_quellen(nur_aktiv=True):
        token = secrets_store.get_secret(quellen.token_schluessel(q["id"]))
        ziele.append({"id": f"quelle:{q['id']}", "art": "quelle",
                      "name": "Downloader" if q["kuerzel"] == "mql5" else quellen.anzeige_name(q),
                      "base_url": q["base_url"], "token": token})
    settings = config.load_settings()
    base = str(settings.get("tradeserver_base_url") or "").strip()
    if base:
        ziele.append({"id": "tradeserver", "art": "tradeserver",
                      "name": "Tradeserver", "base_url": base,
                      "token": secrets_store.get_secret("tradeserver_api_key")})
    return ziele


def _pruefen(ziel):
    if ziel["art"] == "quelle":
        info = downloader_client.DownloaderClient(
            ziel["base_url"], token=ziel["token"], timeout=3.0).health()
        eingeschraenkt = bool(info.get("tokenRequired")) and not ziel["token"]
        return {"ok": str(info.get("status", "")).lower() == "ok",
                "eingeschraenkt": eingeschraenkt, "anbieter": info.get("providers")}
    info = tradeserver_client.TradeserverClient(
        ziel["base_url"], api_key=ziel["token"], timeout=3.0).ping()
    return {"ok": str(info.get("status", "")).lower() == "ok",
            "eingeschraenkt": False}


_monitor = VerbindungsMonitor(_konfiguration, _pruefen)


def zustand():
    return _monitor.zustand()
