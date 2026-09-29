# -*- coding: utf-8 -*-
"""TEMPORAER — verifiziert: verwaister Lauf, Lock-Spam, Schritte-Scan."""
import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
tmp = Path(tempfile.mkdtemp())
(tmp / "t.sqlite").touch()

from mqlkiscanner import db, config  # noqa: E402
db.DB_PATH = tmp / "t.sqlite"
config.DATA_DIR = tmp  # Lock-Dateien ins Temp-Verzeichnis
db.init_db()

from mqlkiscanner.agenten import journal, lock, markt, marktdata, scheduler, dirigent  # noqa: E402

journal.init_journal()

print("== 1) markt.tageslauf mit Exception in kurse_holen ==")
def _kaputt(*a, **k):
    raise RuntimeError("MetaTrader5 nicht installiert / symbol_select-Fehler")
marktdata.kurse_holen = _kaputt
try:
    markt.tageslauf(quelle="daemon", log=lambda m: None, settings={"markt_symbole_manuell": "XAUUSD"})
except Exception as exc:
    print("   Exception entkam tageslauf:", exc)
print("   verwaiste 'laeuft'-Zeilen:", journal.aktive_laeufe("markt"))

print("== 2) Ein Lock-Halter blockiert die Rollen: Journal-Wachstum ==")
with lock.lauf_lock(config.DATA_DIR, "testlock"):
    for i in range(5):
        dirigent.tageslauf(quelle="daemon", log=lambda m: None)
with db._connect() as conn:
    n_laeufe = conn.execute("SELECT COUNT(*) c FROM agenten_laeufe").fetchone()["c"]
    n_schritte = conn.execute("SELECT COUNT(*) c FROM agenten_schritte").fetchone()["c"]
print(f"   5 vergebliche Dirigent-Versuche -> {n_laeufe} Laeufe, {n_schritte} Schritte")
print("   lauf_heute_erfolgreich('dirigent','daemon'):",
      journal.lauf_heute_erfolgreich("dirigent", "daemon"))

print("== 3) Kosten von lauf_heute_erfolgreich bei wachsender Schritte-Tabelle ==")
journal.schritt_protokollieren(0, "test", "gross", prompt="x" * 20000,
                               antwort="y" * 20000, tokens=1000)
n = 2000
with db._connect() as conn:
    rows = [(0, "2026-09-29 12:00:00", "test", "bulk", "ok", "p" * 20000,
             "a" * 20000, "glm", 500, 1.0, "{}")] * n
    conn.executemany(
        "INSERT INTO agenten_schritte (lauf_id, ts, rolle, schritt, status, prompt, "
        "antwort, modell, tokens, dauer_s, detail_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
print("   Zeilen in agenten_schritte:", n + 1)
t0 = time.perf_counter()
for _ in range(5):
    journal.lauf_heute_erfolgreich("test", "daemon")
t1 = time.perf_counter()
journal.tokens_heute()
t2 = time.perf_counter()
print(f"   5x lauf_heute_erfolgreich: {t1-t0:.3f}s ; 1x tokens_heute: {t2-t1:.3f}s")
with db._connect() as conn:
    print("   Plan tokens_heute:",
          [r["detail"] for r in conn.execute(
              "EXPLAIN QUERY PLAN SELECT COALESCE(SUM(tokens),0) FROM agenten_schritte "
              "WHERE tokens IS NOT NULL AND ts LIKE '2026-09%' AND prompt IS NOT NULL")])
