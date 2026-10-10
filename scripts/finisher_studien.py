# -*- coding: utf-8 -*-
"""Finisher für das Ziel „Vantage komplett" (09.10.2026, Nutzer-Auftrag).

Läuft getrennt (detached) neben dem HeadlessTradelistenLoad-Job:
1. Wartet, bis der Loader-Prozess (PID als Argument) beendet ist.
2. Läuft dann Runden: Studien-Batch über ALLE Lücken (nur Lücken, mit
   Trade-Nachladen) — solange, bis eine Runde nichts mehr verbessert.
   Über scan_worker.start mit Datei-Lock: UI/Scan bleiben geschützt.
3. Schreibt Fortschritt nach data/studien_finisher.log.

Aufruf: python finisher_studien.py <loader_pid>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LOG = ROOT / "data" / "studien_finisher.log"


def log(text: str) -> None:
    zeile = time.strftime("%H:%M:%S") + " · " + text
    print(zeile, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(zeile + "\n")


def pid_lebt(pid: int) -> bool:
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    except Exception:
        return False


def main() -> None:
    from mqlkiscanner import db, katalog, pipeline, studien_batch

    loader_pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    log(f"Finisher gestartet (Loader-PID {loader_pid})")
    while loader_pid and pid_lebt(loader_pid):
        time.sleep(60)

    log("Loader beendet — Studien-Runden beginnen.")
    runde = 0
    while runde < 12:                      # Sicherheitsdeckel
        runde += 1
        resultate = [r for r in pipeline.results_from_db()
                     if getattr(r, "source_kind", "live") == "live"]
        kat_res, _ = katalog.katalog_resultate()
        vor = len(db.list_equity_studien())
        jobs, erledigt = studien_batch.luecken_sammeln(
            resultate + kat_res, db.list_equity_studien(), trades_nachladen=True)
        if not jobs:
            log(f"Runde {runde}: keine Lücken mehr — ZIEL ERREICHT "
                f"({erledigt} belegt).")
            break
        log(f"Runde {runde}: {len(jobs)} Lücken, {erledigt} belegt — Batch startet.")
        run = None
        while run is None:
            run = studien_batch.starten(resultate + kat_res,
                                        nur_luecken=True, trades_nachladen=True)
            if run is None:
                log("  Lock belegt (UI/Scan aktiv) — warte 120 s.")
                time.sleep(120)
        run.thread.join()
        nach = len(db.list_equity_studien())
        c = run.control
        log(f"Runde {runde} fertig: {c.get('gerechnet')} gerechnet · "
            f"{c.get('uebersprungen')} übersprungen · {len(c.get('fehler') or [])} Fehler · "
            f"Studien {vor} → {nach}")
        for z in (c.get("fehler") or [])[:10]:
            log("  FEHLER " + z[:140])
        for z in (c.get("skipped_gruende") or [])[:5]:
            log("  SKIP " + z[:140])
        if nach <= vor:
            log("Keine Verbesserung mehr — Finisher beendet.")
            break
    log("Finisher-Ende.")


if __name__ == "__main__":
    main()
