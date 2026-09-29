# -*- coding: utf-8 -*-
"""Prozessübergreifendes Lauf-Lock (Agenten-Daemon vs. Streamlit-GUI-Scan).

Warum eine Datei und nicht die Datenbank: Das Lock muss auch dann greifen,
wenn ein Prozess gerade keine DB-Transaktion hält — der Daemon prüft es,
BEVOR er einen Lauf anstößt, und die GUI kann es später für ihre Scans
mitbenutzen (Phase E). Datei-basiert mit PID und Zeitstempel funktioniert
ohne Plattform-Spezialitäten (kein fcntl/msvcrt nötig) und überlebt
Prozess-Abstürze über die Alters-Schwelle: Ein Lock ohne lebenden Halter
oder älter als STALE_S wird übernommen und ersetzt.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

STALE_S = 3600  # ein Stunden-altes Lock ohne Lebenszeichen gilt als verwaist


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


def _pid_lebt(pid) -> bool:
    """Lebt der Halter-Prozess? psutil (Streamlit-Dependency), sonst True.

    Bewusst konservativ: Ohne psutil gilt der Halter als lebend — ein
    toter Halter wird dann wie bisher über die Alters-Schwelle erkannt.
    (os.kill(pid, 0) ist auf Windows KEINE Option: jeder andere Signalwert
    als CTRL_* beendet den Prozess dort unconditional.)
    """
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or pid == os.getpid():
        # Eigene PID in einer fremden Datei: unwahrscheinlich, entscheidet
        # hier niemand — als lebend gelten lassen (Alter greift).
        return True
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        return True


@contextmanager
def lauf_lock(basis: Path, name: str = "agenten_lauff"):
    """Lauf-Lock halten: genau ein Lauf je Lock-Name über Prozessgrenzen.

    Erwerb atomar über O_CREAT|O_EXCL. Ist die Datei vorhanden:
    - Lebt der Halter-Prozess (PID-Prüfung, Review 29.09. — der Docstring
      versprach das bisher, implementiert war nur das Alter): LockBesetzt,
      UNABHÄNGIG vom Alter — ein echter 2-Stunden-Scan wird nicht mehr von
      einem 1-h-STALE-Riss gegen einen zweiten Scan ausgetauscht.
    - Ist der Halter tot: sofort übernehmen (auch vor STALE_S).
    - Ohne psutil gilt weiterhin: älter als STALE_S = verwaist.
    """
    datei = _lock_pfad(basis, name)
    fd = -1
    versucht = 0
    while fd < 0 and versucht < 2:
        versucht += 1
        try:
            fd = os.open(str(datei), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            alt = _lese(datei)
            alter = time.time() - float(alt.get("ts", 0) or 0)
            pid = alt.get("pid")
            alter_s = int(alter)
            # Lebender Halter und (noch) frisch: warten. Ein lebender
            # Halter MIT psutil-Nachweis blockiert auch über STALE_S hinweg
            # (Review 29.09.: lange Scans wurden sonst gegeneinander
            # ausgetauscht); ohne belastbare PID-Auskunft entscheidet das
            # Alter allein (wie bisher).
            try:
                import psutil  # noqa: F401 — Verfügbarkeit prüfen
                pid_bekannt = True
            except ImportError:
                pid_bekannt = False
            blockiert = (
                (_pid_lebt(pid) and alter <= STALE_S)
                or (pid_bekannt and _pid_lebt(pid)))
            if blockiert:
                raise LockBesetzt(
                    f"Lauf-Lock '{name}' wird gehalten (PID {pid}, "
                    f"seit {alter_s} s, lebend)",
                    pid=pid, alter_s=alter_s, name=name)
            # Verwaist: toter Halter (PID-Prüfung) oder älter als STALE_S
            # (Fallback, wenn psutil fehlt / PID unlesbar).
            try:
                datei.unlink()
            except OSError:
                pass
            continue
    if fd < 0:
        raise LockBesetzt(f"Lauf-Lock '{name}' konnte nicht übernommen werden")
    try:
        info = {"pid": os.getpid(), "ts": time.time()}
        os.write(fd, json.dumps(info).encode("utf-8"))
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
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
    return {"frei": False, "pid": info.get("pid"), "alter_s": int(alter),
            "verwaist": alter > STALE_S}
