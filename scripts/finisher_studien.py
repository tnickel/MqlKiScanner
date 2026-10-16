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


def studien_verbessert(vor: dict, nach: dict) -> int:
    """Fachlichen Fortschritt zaehlen; vorhandene Zeilen koennen besser werden."""
    def qualitaet(studie):
        import math
        report = studie.get("report") or {}
        dd = report.get("equity_dd_pct_raw", report.get("equity_dd_pct"))
        messbar = (isinstance(dd, (int, float)) and not isinstance(dd, bool)
                   and math.isfinite(dd) and dd >= 0)
        return (bool(report.get("verlaesslich") and messbar), messbar,
                report.get("abdeckung_pct_raw", report.get("abdeckung_pct")) or 0,
                not bool(report.get("fx_luecke")))
    return sum(1 for sid, studie in nach.items()
               if sid not in vor or qualitaet(studie) > qualitaet(vor[sid])
               or (studie.get("trades_sha") and
                   studie.get("trades_sha") != vor[sid].get("trades_sha")))


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
        rows = db.list_catalog()
        studien_vorher = db.list_equity_studien()
        resultate = [r for r in pipeline.results_from_db(
            catalog_rows=rows, studien=studien_vorher, materialize_pdfs=False)
            if getattr(r, "source_kind", "live") == "live"]
        kat_res, _ = katalog.katalog_resultate(
            gescannt={row["signal_id"] for row in rows}, studien=studien_vorher)
        vor = len(studien_vorher)
        jobs, erledigt = studien_batch.luecken_sammeln(
            resultate + kat_res, studien_vorher, trades_nachladen=True)
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
                log("  Lock belegt (UI/Scan aktiv) — warte 60 s.")
                time.sleep(60)
        run.thread.join()
        studien_nachher = db.list_equity_studien()
        nach = len(studien_nachher)
        verbessert = studien_verbessert(studien_vorher, studien_nachher)
        c = run.control
        log(f"Runde {runde} fertig: {c.get('gerechnet')} gerechnet · "
            f"{c.get('uebersprungen')} übersprungen · {len(c.get('fehler') or [])} Fehler · "
            f"Studien {vor} → {nach} · {verbessert} verbessert")
        for z in (c.get("fehler") or [])[:10]:
            log("  FEHLER " + z[:140])
        for z in (c.get("skipped_gruende") or [])[:5]:
            log("  SKIP " + z[:140])
        if not verbessert:
            log("Keine Verbesserung mehr — Finisher beendet.")
            break
    log("Finisher-Ende.")


if __name__ == "__main__":
    main()
