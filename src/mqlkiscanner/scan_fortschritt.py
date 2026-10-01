# -*- coding: utf-8 -*-
"""Scan-Fortschritt für die Agenten-Seite: ein Kanal, zwei Quellen.

Nutzer-Wunsch 30.09.2026: Während eines (autonomen) Scans soll die
Agenten-Seite einen Fortschrittsbalken mit aktuellem Schritt und
Restzeitschätzung zeigen — vorher stand nur „ein Lauf ist aktiv".

Quelle 1 (Zukunft, exakt): der Scan-Launcher schreibt nach jedem Schritt
`data/scan_fortschritt.json` (atomar) mit Station, Zähler und Startzeit.
Quelle 2 (sofort, auch für Läufe ohne Launcher-Support): DB-Puls — Signale
mit updated_at >= Laufbeginn zählen hoch, solange die Forensik arbeitet.

Die GUI (app_pages/agenten.py) liest beides und zeigt EINEN Gesamtbalken:
Stationen gewichtet ca. Forensik 30 %, KI-Berichte 55 %, Portfolio 10 %,
Rest Listen/Kandidaten/Abgleich. Restzeit aus dem bisherigen Tempo
(geglättet); solange < 2 % Fortschritt, wird noch keine Zeit geschätzt.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import config, db

def _status_datei() -> Path:
    """F9 (Fremd-Review 01.10.): Pfad ERST beim Zugriff aus der Konfiguration
    lösen — ein einmalig beim Import berechneter Pfad ließ sich in Tests
    nicht isolieren und schrieb in die Produktiv-Datei."""
    return Path(config.DATA_DIR) / "scan_fortschritt.json"

# Station -> (Start-Anteil, Ende-Anteil) am GESAMTBalken (0..1).
GEWICHTE = {
    "listen": (0.00, 0.03),
    "kandidaten": (0.03, 0.05),
    "forensik": (0.05, 0.35),
    "ki": (0.35, 0.90),
    "portfolio": (0.90, 0.99),
}


def aktualisieren(station: str, done: int, total: int, detail: str,
                  start_ts: float, modus: str, status: str = "laufend") -> None:
    """Fortschritt atomar in die Statusdatei (tmp + replace)."""
    payload = {
        "station": station, "done": int(done), "total": int(total),
        "detail": str(detail)[:160], "start_ts": float(start_ts),
        "modus": modus, "status": status, "updated_ts": time.time(),
    }
    tmp = _status_datei().with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _status_datei())


def lesen(max_alter_s: float = 120.0) -> dict | None:
    """Aktueller Fortschritt oder None (kein/veraltet/defekt)."""
    try:
        eintrag = json.loads(_status_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - float(eintrag.get("updated_ts") or 0) > max_alter_s:
        return None
    return eintrag


def loeschen() -> None:
    try:
        _status_datei().unlink(missing_ok=True)
    except OSError:
        pass


def gesamt_anteil(eintrag: dict) -> float | None:
    """Gesamtbalken 0..1 aus Stationsfortschritt; None wenn unbekannt."""
    von, bis = GEWICHTE.get(str(eintrag.get("station")), (None, None))
    if von is None:
        return None
    total = int(eintrag.get("total") or 0)
    done = max(0, int(eintrag.get("done") or 0))
    anteil_station = (done / total) if total > 0 else 0.0
    return min(0.999, max(0.001, von + (bis - von) * min(1.0, anteil_station)))


def restzeit_s(eintrag: dict) -> float | None:
    """Restschätzung aus bisherigem Tempo; None unter 2 % Fortschritt."""
    anteil = gesamt_anteil(eintrag)
    if anteil is None or anteil < 0.02:
        return None
    vergangen = max(1.0, time.time() - float(eintrag.get("start_ts") or 0))
    return vergangen / anteil * (1.0 - anteil)


def puls_aus_db(start_iso: str) -> dict | None:
    """DB-Puls: verarbeitete Signale + letztes Signal seit Laufbeginn.

    Fallback für Läufe ohne Launcher-Fortschritt (z. B. der gerade laufende
    Scan): die Forensik schreibt je Signal `signals.updated_at` — der Zähler
    steigt sichtbar, ein Total gibt es hier nicht.
    """
    if not start_iso:
        return None
    try:
        with db._connect() as con:
            zeilen = con.execute(
                "SELECT COUNT(*), MAX(name) FROM signals WHERE updated_at >= ?",
                (start_iso,)).fetchone()
        return {"erledigt": int(zeilen[0] or 0), "letztes": zeilen[1] or ""}
    except Exception:
        return None
