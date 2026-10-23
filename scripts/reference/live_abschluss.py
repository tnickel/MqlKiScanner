"""Explicit live maintenance stages; uses normal locks, validators and budgets.

Run only with an authorized live-update request. Detailed output belongs in an
ignored directory, never in public review attachments. Each invocation starts
fresh so model/version changes cannot be mixed inside a long-lived interpreter.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("backup", "catalog", "scan", "source-scan", "reports", "studies", "mirror", "publish", "verify"))
    parser.add_argument("--source", help="Only this already-updated source; no second update job")
    parser.add_argument("--ids", help="Known IDs explicitly requested for maintenance; requires --source, bypasses export prefilters")
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requested = {int(value) for value in args.ids.split(",")} if args.ids else None
    if requested and (not args.source or any(value <= 0 for value in requested)):
        parser.error("--ids requires --source and positive provider IDs")
    from mqlkiscanner import (analysis_version, config, db, downloader_client,
                             downloader_sync, fix_signale, ingest, katalog,
                             pipeline, studien_batch, tradeserver_sync)
    from mqlkiscanner.agenten import budget, journal, lock, scan_launcher
    if args.expected_version != analysis_version.FORENSICS_VERSION:
        raise RuntimeError("Forensikversion weicht vom freigegebenen Laufplan ab")
    output = args.output.resolve()
    allowed = (config.DATA_DIR / "runs").resolve()
    if not output.is_relative_to(allowed):
        raise RuntimeError("Live-Belege müssen im privaten data/runs-Verzeichnis liegen")
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")

    def log(message):
        print(datetime.now().strftime("%H:%M:%S"), str(message), flush=True)

    def save(name, value):
        path = output / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temp.replace(path)

    def results():
        return pipeline.results_from_db(materialize_pdfs=False)

    log(f"Phase {args.phase}, Quelle {args.source or 'alle'}, Forensikversion {args.expected_version}")
    summary = {}
    if args.phase == "backup":
        # SQLite's online backup takes a consistent database snapshot. This
        # read-only stage has no terminal access and can run while another
        # process holds the terminal/workflow lock for a metadata probe.
        backup = output / "before.sqlite"
        if backup.exists():
            raise RuntimeError("Bestehendes Backup wird nicht überschrieben")
        with sqlite3.connect(db.DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(backup) as target:
                source.backup(target)
                summary = {"integrity": target.execute("PRAGMA integrity_check").fetchone()[0],
                           "foreign_key_errors": len(target.execute("PRAGMA foreign_key_check").fetchall())}
    elif args.phase == "catalog":
        with lock.lauf_lock(config.DATA_DIR):
            summary = katalog.sync(log=log, kuerzel=args.source)
    elif args.phase == "scan":
        summary = scan_launcher.starte_scan("full", quelle="cli_liveabschluss", log=log)
    elif args.phase == "source-scan":
        if not args.source:
            raise RuntimeError("source-scan braucht eine bereits aktualisierte Quelle")
        sources = [q for q in db.list_quellen(nur_aktiv=True) if q["kuerzel"] == args.source]
        if len(sources) != 1:
            raise RuntimeError("Aktive Quellenverbindung nicht eindeutig")
        source = sources[0]
        settings = config.load_settings()
        pipe = pipeline.ScanPipeline(settings, quelle="cli_liveabschluss", allow_offline_source_cache=False)
        with lock.lauf_lock(config.DATA_DIR):
            raw = ingest.kandidaten(source, ingest.hole_katalog(source))
            claims = {}
            for candidate in raw:
                claims.setdefault(pipeline.key_for(candidate), set()).add(
                    str(candidate.get("platform") or "").upper().replace("MQL", "MT"))
            conflicts = {key for key, platforms in claims.items() if len(platforms) > 1}
            blocked = [{"source": key[0], "id": key[1], "reason": "Widersprüchliche Plattformen im aktuellen Quellenkatalog"}
                       for key in sorted(conflicts)]
            candidates = pipe.build_candidates(raw, log=log)
            selected, selection = fix_signale.waehle_fuer_export(
                candidates, int(settings.get("top_n_export", 30)), settings)
            seen = {pipeline.key_for(c) for c in selected}
            # New model version also requires rechecking existing workflow
            # heads. This maintenance step does not change the normal filters.
            for row in db.list_catalog():
                key = row["quelle"], row["signal_id"]
                if key[0] != args.source or key in seen or key in conflicts:
                    continue
                version = downloader_client.platform_version(row.get("platform") or "")
                if version is None:
                    blocked.append({"source": key[0], "id": key[1],
                                    "reason": "Alte Workflow-Plattform unbekannt; keine MQL5-Vorbelegung"})
                    continue
                selected.append({"id": row["signal_id"], "name": row.get("name"),
                    "platform": row.get("platform"), "url": row.get("url"),
                    "abonnenten": row.get("abonnenten"), "wochen": row.get("wochen"),
                    "quelle_kuerzel": args.source, "quelle_id": source["id"],
                    "quellen_uid": source["quellen_uid"], "signal_ref": row["signal_ref"],
                    "quelle_version": version})
                seen.add(key)
            if requested is not None:
                # Explicitly named maintenance providers (e.g. the five FT
                # cases) may be outside the normal top-N or age filter.
                # They still need an established source catalog identity;
                # the numerical rating gates remain in the normal engine.
                for candidate in raw:
                    key = pipeline.key_for(candidate)
                    if int(candidate["id"]) in requested and key not in seen and key not in conflicts:
                        selected.append(candidate)
                        seen.add(key)
                selected = [c for c in selected if int(c["id"]) in requested]
                for sid in sorted(requested - {int(c["id"]) for c in selected}):
                    blocked.append({"source": args.source, "id": sid,
                                    "reason": "Explizite ID nicht eindeutig in aktueller Auswahl oder Workflow belegt"})
            outcome = []
            try:
                for i, candidate in enumerate(selected, 1):
                    version = candidate.get("quelle_version")
                    if (version not in ingest._PLATTFORM
                            or downloader_client.platform_version(candidate.get("platform") or "") != version):
                        blocked.append({"source": args.source, "id": candidate["id"],
                                        "reason": "Quellenversion und Plattform sind nicht eindeutig belegt"})
                        continue
                    log(f"Forensik {args.source} {i}/{len(selected)}: #{candidate['id']}")
                    r = pipe.analyze_candidate(None, candidate, log=log)
                    outcome.append({"source": r.quelle, "id": r.id,
                                    "complete": r.forensik_vorhanden, "persisted": r.persisted_this_run,
                                    "error": r.fehler, "ampel": r.ampel,
                                    "equity_status": r.equity_rekon_status})
                    save(f"source_scan_{args.source}_progress.json", outcome)
            finally:
                pipe.kursdaten_beenden()
            summary = {"source": args.source, "selection": selection, "attempted": len(outcome),
                       "complete": sum(r["complete"] for r in outcome),
                       "persisted": sum(r["persisted"] for r in outcome), "outcomes": outcome,
                       "blocked": blocked}
    elif args.phase == "reports":
        settings = config.load_settings()
        pipe = pipeline.ScanPipeline(settings, quelle="cli_liveabschluss")
        with lock.lauf_lock(config.DATA_DIR):
            run_id = journal.lauf_starten("dirigent", quelle="cli_liveabschluss_reports")
            budget.attach(pipe.llm, settings, run_id, "dirigent")
            try:
                jobs = [r for r in results() if r.source_kind == "live" and r.forensik_vorhanden
                        and not r.fehler and (not args.source or r.quelle == args.source)
                        and (requested is None or r.id in requested)
                        and not pipeline.restore_current_reports(r, settings)]
                summary = pipe.run_llm(jobs, log=log)
                journal.lauf_abschliessen(run_id, "ok" if not summary.get("failed") else "fehler",
                                         json.dumps(summary, ensure_ascii=False))
            except BaseException as exc:
                journal.lauf_abschliessen(run_id, "fehler", str(exc))
                raise
    elif args.phase == "studies":
        # Refresh the input bytes, even if an older immutable cache already
        # exists. Current SHA guards decide which displayed studies can apply.
        with lock.lauf_lock(config.DATA_DIR):
            workflow = results()
            catalog, _ = katalog.katalog_resultate(gescannt={r.signal_key for r in workflow})
            combined = [r for r in workflow + catalog if (not args.source or r.quelle == args.source)
                        and (requested is None or r.id in requested)]
            eligible = []
            refresh = {"total": len(combined), "fetched": 0, "failed": []}
            for i, result in enumerate(combined, 1):
                try:
                    if katalog.quellen_referenz(result):
                        path, _ = katalog.lade_signal_daten(result, allow_offline_cache=False)
                        result.trades_path = path
                        artifact = db.get_quellen_artefakt(result.quelle_id, result.id,
                                                          result.quelle_version, "trades")
                        result.trades_sha256 = (artifact or {}).get("sha256") or ""
                        refresh["fetched"] += 1
                    eligible.append(result)
                except Exception as exc:
                    # Failed current unit/download proof must not reuse old
                    # source bytes in this fresh maintenance run.
                    result.trades_path = ""
                    result.trades_sha256 = ""
                    result.account_currency = None
                    refresh["failed"].append({"source": result.quelle, "id": result.id,
                                               "error": f"{type(exc).__name__}: {exc}"})
                if i % 25 == 0 or i == len(combined):
                    save("study_refresh_progress.json", {**refresh, "done": i})
                    log(f"Studieneingaben {i}/{len(combined)}; geladen {refresh['fetched']}; Fehler {len(refresh['failed'])}")
            save("study_refresh.json", refresh)
        # Refresh may have changed the SHA after old measurements were attached
        # by results_from_db. Recalculate this maintenance scope explicitly;
        # do not let an attached old DD suppress the fresh study.
        run = studien_batch.starten(eligible, nur_luecken=False, trades_nachladen=True)
        if run is None:
            raise RuntimeError("Studienbatch nicht gestartet: Lauf-Lock belegt")
        last = None
        while run.thread.is_alive():
            state = dict(run.control)
            save("study_progress.json", state)
            key = (state.get("aktuell"), state.get("phase"))
            if key != last:
                log(f"Studien {state.get('aktuell')}/{state.get('gesamt')}: {state.get('aktuelles_signal')} | {state.get('phase')}")
                last = key
            run.thread.join(timeout=5)
        summary = dict(run.control)
    elif args.phase == "mirror":
        with lock.lauf_lock(config.DATA_DIR):
            summary = downloader_sync.sync_many([(r.quelle, r.id, r.platform) for r in results()
                                                 if r.source_kind == "live"],
                         progress=lambda d, t, sid: log(f"Quellenspiegel {d}/{t}: #{sid}"))
    elif args.phase == "publish":
        current = [r for r in results() if r.source_kind == "live"]
        # A version-bound portfolio may be restored by the normal UI later;
        # never publish an old portfolio as a new assessment.
        summary = tradeserver_sync.sync_alle(current,
                        progress=lambda d, t, label: log(f"Tradeserver PDFs {d}/{t}: {label}"))
    elif args.phase == "verify":
        current = results()
        studies = db.list_equity_studien(identitaeten=True)
        catalog, _ = katalog.katalog_resultate(gescannt={r.signal_key for r in current}, studien=studies)
        all_rows = current + catalog
        with sqlite3.connect(db.DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            summary = {"integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
                       "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall())}
        summary.update(workflow_rows=len(current), catalog_only_rows=len(catalog), table_rows=len(all_rows),
                       unique_table_owners=len({(r.quellen_uid, r.id) for r in all_rows}),
                       current_forensics=sum(r.forensik_vorhanden for r in current),
                       stale_forensics=sum(r.forensik_stale for r in current),
                       studies=len(studies),
                       reliable_studies=sum((s.get("report") or {}).get("verlaesslich") is True for s in studies.values()),
                       virtual_studies=sum(bool(s.get("virtuell")) for s in studies.values()),
                       table_measured_dd=sum(r.max_drawdown_equity_pct is not None for r in all_rows),
                       ampel={color: sum(r.ampel == color for r in current) for color in ("🟢", "🟡", "🔴", "⚪", "⛔")},
                       criteria={key: config.load_settings().get(key) for key in (
                           "schranke_eq_dd_pct", "min_calmar_jahr", "min_ertrag_pct_monat", "agenten_enabled")})
        save("remaining_workflow.json", [{"source": r.quelle, "id": r.id, "version": r.forensik_version,
             "stale": r.forensik_stale, "error": r.fehler, "equity_status": r.equity_rekon_status,
             "equity_reason": r.equity_rekon_grund} for r in current if not r.forensik_vorhanden])
    receipt = {"phase": args.phase, "started": started,
               "finished": datetime.now().isoformat(timespec="seconds"),
               "forensics_version": args.expected_version, "requested_ids": sorted(requested) if requested else None,
               "result": summary}
    (output / "receipts").mkdir(exist_ok=True)
    save("receipts/" + args.phase + ("_" + args.source if args.source else "")
         + "_" + started.replace(":", "").replace("-", "") + ".json", receipt)
    save(args.phase + ("_" + args.source if args.source else "") + ".json", receipt)
    log(json.dumps(receipt, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
