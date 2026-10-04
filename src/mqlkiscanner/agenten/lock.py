# -*- coding: utf-8 -*-
"""Prozessübergreifendes Lauf-Lock (Agenten-Daemon vs. Streamlit-GUI-Scan).

Warum eine Datei und nicht die Datenbank: Das Lock muss auch dann greifen,
wenn ein Prozess gerade keine DB-Transaktion hält — der Daemon prüft es,
BEVOR er einen Lauf anstößt, und die GUI kann es später für ihre Scans
mitbenutzen (Phase E). Datei-basiert mit PID, Zeitstempel und Prozess-
Startzeit funktioniert ohne Plattform-Spezialitäten (kein fcntl/msvcrt
nötig) und heilt Prozess-Abstürze selbst:
- Halter tot (PID-Prüfung) → sofort übernehmen,
- Halter-PID lebt, aber ist ein NEUER Prozess (Windows-PID-Recycling,
  create_time-Vergleich) → sofort übernehmen,
- älter als MAX_S → garantiert übernehmen (kein Lock blockiert ewig),
- ohne psutil: älter als STALE_S → verwaist (Fallback wie bisher).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

STALE_S = 3600  # ohne psutil: ein Stunden-altes Lock gilt als verwaist
# Obergrenze NUR für Locks ohne verifizierbare Identität (kein Start-Stempel
# oder Startzeit unklar). Ein EINDEUTIG identifizierter lebender Halter
# blockiert ohne Altersgrenze (Review-Übergabe 29.09., Befund 3): MAX_S
# hätte sonst einen echten >24-h-Lauf freigegeben — Windows: Übernahme
# scheitert am offenen Handle (Lock bleibt, Anzeige sagt „verwaist"),
# POSIX: unlink gelingt → paralleler Lauf.
MAX_S = 24 * 3600


def rolle_lock_name(rolle: str) -> str:
    """Eigener Lock-Name je Rolle: Daemon-Tick, GUI-Klick und Komplettkette
    nehmen denselben Rollen-Lock (liveness-basiert) — ein lebender Lauf
    blockiert parallele Starts derselben Rolle unabhängig von Journal-
    Altersgrenzen (Review-Übergabe 29.09., Befunde 1+2)."""
    return f"rolle_{rolle}"


class LockBesetzt(RuntimeError):
    """Das Lauf-Lock hält ein anderer, lebender Prozess."""

    def __init__(self, message: str, pid: int | None = None,
                 alter_s: int | None = None, name: str = ""):
        super().__init__(message)
        self.pid = pid
        self.alter_s = alter_s
        self.name = name


def _lock_pfad(basis: Path, name: str) -> Path:
    datei = basis / f"{name}.lock"
    datei.parent.mkdir(parents=True, exist_ok=True)
    return datei


def _lese(datei: Path) -> dict:
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _prozess_start(pid: int) -> float | None:
    """Startzeit des Prozesses (psutil create_time) oder None — ohne psutil
    oder wenn der Prozess zwischenzeitlich verschwunden ist."""
    try:
        import psutil
        return psutil.Process(pid).create_time()
    except ImportError:
        return None
    except Exception:
        return None  # NoSuchProcess u. a. — als „nicht mehr derselbe" werten


def _lock_blockiert(alt: dict, alter: float) -> tuple[bool, bool]:
    """Blockiert ein vorhandenes Lock? → (blockiert, lebender_halter)

    Psutil-Versionsgeschichte (Reviews 29.09.): Erst prüfte der Code nur das
    Alter (STALE_S riss lange Scans auseinander), dann blockte ein
    psutil-verifiziert lebender PID-Wert ewig — Windows vergibt PIDs neu,
    ein Crash + Recycling sperrte das Lock für immer (Qwen-Review M1/M2).
    Jetzt:
    - psutil fehlt oder PID unlesbar/ungültig: das Alter entscheidet
      (STALE_S, wie vor dem PID-Review) — eine korrupte Datei (ts=0)
      ist damit sofort frei.
    - Halter tot: sofort übernehmen (auch frisch).
    - Halter lebt unter derselben PID, ABER mit anderer Startzeit als beim
      Erwerb eingetragen: PID recycelt → sofort übernehmen.
    - Halter lebt und ist derselbe Prozess: blockiert, aber nie über MAX_S.
    """
    try:
        pid = int(alt.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    try:
        import psutil
    except ImportError:
        return alter <= STALE_S, False
    if pid <= 0 or not psutil.pid_exists(pid):
        return False, False
    start = alt.get("start")
    if start is not None:
        try:
            selber = abs(psutil.Process(pid).create_time() - float(start)) <= 1.0
        except Exception:
            selber = None  # Prozess zwischendurch weg: konservativ unklar
        if selber is False:
            return False, False
        if selber is True:
            # Eindeutig identifiziert lebender Halter blockiert OHNE
            # Altersgrenze (Review-Übergabe 29.09., Befund 3).
            return True, True
    # Kein Start-Stempel oder Startzeit unklar: Identität nicht verifizierbar
    # → Alters-Obergrenze als Rückfallebene.
    return alter <= MAX_S, True


def _lock_ist_uns(datei: Path, info: dict) -> bool:
    """Gehört die Lock-Datei noch UNS? Nur dann darf der Besitzer sie
    entfernen (Review-Übergabe 29.09., Befund 3): Hat ein anderer Prozess
    die Datei zwischenzeitlich ersetzt (POSIX: Übernahme nach Altersgrenze),
    darf unser unlink seine Datei nicht löschen — sonst läuft ein dritter
    Prozess parallel an."""
    try:
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    try:
        gleich_ts = abs(float(inhalt.get("ts", 0) or 0)
                        - float(info.get("ts", 0) or 0)) < 0.001
    except (TypeError, ValueError):
        return False
    return (inhalt.get("pid") == info.get("pid")
            and gleich_ts
            and inhalt.get("start") == info.get("start"))


@contextmanager
def lauf_lock(basis: Path, name: str = "agenten_lauff"):
    """Lauf-Lock halten: genau ein Lauf je Lock-Name über Prozessgrenzen.

    Erwerb atomar über O_CREAT|O_EXCL. Ist die Datei vorhanden, entscheidet
    _lock_blockiert (Lebenszeichen + Startzeit-Abgleich gegen PID-Recycling;
    Alters-Obergrenze MAX_S nur für nicht verifizierbare Identität); Details
    dort. Beim Verlassen entfernt NUR der noch eingetragene Besitzer die
    Datei.
    """
    datei = _lock_pfad(basis, name)
    fd = -1
    versucht = 0
    info: dict | None = None
    while fd < 0 and versucht < 2:
        versucht += 1
        try:
            fd = os.open(str(datei), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            alt = _lese(datei)
            try:
                alter = time.time() - float(alt.get("ts", 0) or 0)
            except (TypeError, ValueError):
                # Korrupte ts (z. B. Text statt Zahl) darf den Daemon nicht
                # werfen (Review 04.10., Paket B B3a): "seit Anbeginn" alt
                # ansetzen — _lock_blockiert entscheidet dann allein am
                # lebenden PID-Besitzer, sonst gilt der Lock als überholbar.
                alter = float(time.time())
            alter_s = int(alter)
            blockiert, lebend = _lock_blockiert(alt, alter)
            if blockiert:
                raise LockBesetzt(
                    f"Lauf-Lock '{name}' wird gehalten (PID {alt.get('pid')}, "
                    f"seit {alter_s} s" + (", lebend)" if lebend else ")"),
                    pid=alt.get("pid"), alter_s=alter_s, name=name)
            # Verwaist/überholbar: toter oder recycelter Halter, korrupte
            # Datei oder (ohne Start-Stempel) älter als MAX_S.
            try:
                datei.unlink()
            except OSError:
                pass
            continue
    if fd < 0:
        raise LockBesetzt(f"Lauf-Lock '{name}' konnte nicht übernommen werden")
    try:
        info = {"pid": os.getpid(), "ts": time.time(),
                "start": _prozess_start(os.getpid())}
        os.write(fd, json.dumps(info).encode("utf-8"))
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
        if info is not None and _lock_ist_uns(datei, info):
            try:
                datei.unlink()
            except OSError:
                pass  # schon entfernt — unschön, aber ohne Folge für die Korrektheit


def lock_status(basis: Path, name: str = "agenten_lauff") -> dict:
    """Aktueller Lock-Zustand für Anzeigen (ohne Erwerb)."""
    datei = _lock_pfad(basis, name)
    if not datei.exists():
        return {"frei": True}
    info = _lese(datei)
    alter = time.time() - float(info.get("ts", 0) or 0)
    blockiert, lebend = _lock_blockiert(info, alter)
    return {"frei": False, "pid": info.get("pid"), "alter_s": int(alter),
            "verwaist": not blockiert, "lebend": lebend}
