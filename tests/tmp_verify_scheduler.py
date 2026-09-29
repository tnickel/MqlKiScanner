# -*- coding: utf-8 -*-
"""TEMPORAER — verifiziert Scheduler-Befunde."""
import sys, tempfile, os
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

tmp = Path(tempfile.mkdtemp())
(tmp / "t.sqlite").touch()

from mqlkiscanner import db  # noqa: E402
db.DB_PATH = tmp / "t.sqlite"
db.init_db()

from mqlkiscanner.agenten import journal, scheduler, scan_launcher  # noqa: E402

journal.init_journal()
jetzt = datetime.now()
heute = journal._heute()

print("== A) Wiederholung nach 'skipped' ==")
journal.lauf_starten("markt", quelle="daemon")
journal.lauf_abschliessen(1, "skipped", "Terminal laeuft nicht")
settings = {"agenten_enabled": True, "agenten_start_zeit": "06:30"}
faellig = scheduler.faellige_rollen(jetzt.replace(hour=8, minute=0), settings)
print("faellig nach einem skipped-Lauf um 08:00:", faellig)

print("== B) Wiederholung nach 'fehler' (Betreuer, alle Signale fehlgeschlagen) ==")
journal.lauf_starten("betreuer", quelle="daemon")
journal.lauf_abschliessen(2, "fehler", "Export HTTP 500")
print("faellig:", scheduler.faellige_rollen(jetzt.replace(hour=8, minute=0), settings))

print("== C) Spaete Startzeit ==")
s = {"agenten_enabled": True, "agenten_start_zeit": "23:00"}
for job in ("dirigent", "markt", "betreuer", "melder", "chef", "teilscan", "fullscan"):
    print("  ", job, scheduler.job_termin(s, job))
print("faellig 23:59:", scheduler.faellige_rollen(jetzt.replace(hour=23, minute=59), s))
print("faellig 00:30 (Folgetag-Modus):", scheduler.faellige_rollen(jetzt.replace(hour=0, minute=30), s))

print("== D) Monatsanfang-Logik fullscan ==")
for tag in (1, 2, 3, 6, 7, 8):
    d = datetime(2026, 11, tag)
    print("  ", d.strftime("%Y-%m-%d %a"), "faellig_scans:",
          scheduler.faellige_scans(d.replace(hour=9), {"agenten_start_zeit": "06:30"}))

print("== E) 'heute gefahren'-Marker: Lauf am Vortag 23:59 endet heute ==")
journal.lauf_starten("dirigent", quelle="daemon")
with db._connect() as conn:
    conn.execute("UPDATE agenten_laeufe SET start=?, status='ok' WHERE id=?",
                 ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), 3))
print("  lauf_heute_erfolgreich:", journal.lauf_heute_erfolgreich("dirigent", "daemon"))

print("== F) LIKE-Präfix-Nutzung des Index (Query Plan) ==")
with db._connect() as conn:
    for q in ("SELECT COUNT(*) FROM agenten_laeufe WHERE rolle='x' AND quelle='y' AND status='ok' AND start LIKE '2026-09-29%'",
              "SELECT COALESCE(SUM(tokens),0) FROM agenten_schritte WHERE tokens IS NOT NULL AND ts LIKE '2026-09%' AND prompt IS NOT NULL"):
        for row in conn.execute("EXPLAIN QUERY PLAN " + q):
            print("  ", row["detail"])
        print("   ---")

print("== G) zerlege_lauf Substring 'lock' ==")
for z in ("Export blockiert, weil Lockdown", "Betreuer blockiert (MT5 laeuft)",
          "Lauf-Lock belegt", "Marktkontext blockiert"):
    a, r = journal.zerlege_lauf("betreuer", "skipped", z, "daemon")
    print(f"   {z!r} -> {r!r}")

print("== H) verwaister Lauf blockiert Chef/Scans dauerhaft ==")
journal.lauf_starten("dirigent", quelle="daemon")
print("   aktive_laeufe:", journal.aktive_laeufe("dirigent"))
print("   _aktiver_scan():", scheduler._aktiver_scan())
print("   aktive_rollen() (Anzeige, 90-min-Grenze):", journal.aktive_rollen())
print("   faellige_rollen am Sonntag 18:30 mit aktivem Scan:",
      scheduler.faellige_rollen(datetime(2026, 10, 4, 18, 30), settings))
