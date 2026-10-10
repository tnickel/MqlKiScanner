# -*- coding: utf-8 -*-
"""Fix-ID-Vollanalyse (Nutzer-Auftrag 09.10.2026): Forensik + LLM + PDF.

Läuft getrennt (detached): Für ALLE Fix-IDs ohne aktuelle Forensik wird die
Engine-Analyse über den Quellen-Weg nachgeholt (Katalog → REST-Trades, keine
MQL5-Web-Session nötig), anschließend die 3-Prompt-KI-Auswertung (glm-5.3 +
Flash) für alle Fix-IDs mit Forensik aber ohne Gesamtbericht, und zum Schluss
werden die PDF-Berichte materialisiert. Vorhandene Berichte werden NICHT
neu erzeugt (Token-Schonung, gleiche Regel wie die LLM-Station des Scans).

Aufruf: python scripts/fix_llm_reports.py
Log:    data/fix_reports.log
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LOG_PFAD = ROOT / "data" / "fix_reports.log"


def log(text: str) -> None:
    zeile = time.strftime("%H:%M:%S") + " · " + text
    print(zeile, flush=True)
    with LOG_PFAD.open("a", encoding="utf-8") as f:
        f.write(zeile + "\n")


def main() -> None:
    from mqlkiscanner import config, db, fix_signale, pipeline

    settings = config.load_settings()
    pipe = pipeline.ScanPipeline(settings)
    fix_ids = sorted(fix_signale.fix_ids())
    log(f"Start: {len(fix_ids)} Fix-IDs · LLM-Key: {pipe.llm.has_key}")

    # ── 1) Forensik für Fix-IDs ohne aktuelle Forensik (Quellen-Weg) ──────
    results = {r.id: r for r in pipeline.results_from_db()}
    fehlt = [i for i in fix_ids
             if not (i in results and results[i].forensik_vorhanden)]
    if fehlt:
        log(f"Forensik nötig für {len(fehlt)}: {fehlt}")
        kat = {int(z["signal_id"]): z for z in db.katalog_list()}
        quellen = {q["kuerzel"]: q for q in db.list_quellen()}
        for i in fehlt:
            z = kat.get(i)
            quelle = quellen.get(str(z.get("quelle") or "")) if z else None
            if z is None or quelle is None:
                log(f"  #{i}: nicht im Katalog/ohne Quelle — übersprungen")
                continue
            cand = {
                "id": i,
                "name": z.get("name") or str(i),
                "platform": z.get("platform") or "",
                "url": z.get("url") or "",
                "abonnenten": z.get("abonnenten"),
                "wochen": z.get("wochen"),
                "quelle_kuerzel": z.get("quelle"),
                "quelle_id": int(quelle["id"]),
                "quelle_version": str(z.get("version") or ""),
            }
            try:
                res = pipe.analyze_candidate(None, cand, log)
                log(f"  #{i} {res.name}: Forensik "
                    f"{'OK' if res.forensik_vorhanden else 'FEHLER: ' + (res.fehler or '')[:120]}")
            except Exception as exc:
                log(f"  #{i} FEHLER {type(exc).__name__}: {exc}")

    # ── 2) LLM: 3 Prompts für Fix-IDs mit Forensik, ohne Bericht ──────────
    results = {r.id: r for r in pipeline.results_from_db()}
    jobs = [results[i] for i in fix_ids if i in results
            and results[i].forensik_vorhanden and not results[i].fehler
            and not results[i].gesamtbericht]
    if not pipe.llm.has_key:
        log("Kein LLM-Key — Analyse ohne KI-Texte beendet.")
        return
    if not jobs:
        log("Keine Fix-IDs ohne Bericht — alle Berichte vorhanden.")
    else:
        log(f"LLM-Station für {len(jobs)} Signale: "
            + ", ".join(f"#{r.id} {r.name[:18]}" for r in jobs))
        summary = pipe.run_llm(jobs, log)
        log(f"LLM fertig: {summary.get('completed')}/{summary.get('total')} gespeichert · "
            f"{summary.get('failed')} Fehler · {summary.get('reason') or 'ok'}")

    # ── 3) PDF-Berichte materialisieren ───────────────────────────────────
    from mqlkiscanner.pdf_reports import materialize_result_pdfs
    results = {r.id: r for r in pipeline.results_from_db()}
    for i in fix_ids:
        r = results.get(i)
        if r and r.gesamtbericht:
            try:
                pfade = materialize_result_pdfs(r)
                log(f"  #{i} PDF: {len(pfade)} Datei(en) "
                    f"({', '.join(str(p.name)[:48] for p in pfade.values())})")
            except Exception as exc:
                log(f"  #{i} PDF-FEHLER {type(exc).__name__}: {exc}")
    log("FERTIG")


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        log("ABBRUCH: " + repr(exc))
        traceback.print_exc()
