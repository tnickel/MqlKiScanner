# -*- coding: utf-8 -*-
"""Review-Subagent Scanner: Identitäts-/Persistenz-Spurensuche auf einer
eigenen Arbeitskopie der Review-DB-Kopie (niemals Produktiv-DB)."""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

PROJ = Path(r"D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner")
WORK = Path(__file__).parent / "work"
WORK.mkdir(exist_ok=True)
DB = WORK / "workcopy.db"
shutil.copyfile(PROJ / "doc/reviews/intensivreview_2026-09-29/tmp/review_copy.db", DB)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

MQL5_ID = 2349227   # Gold Spike (MT4, Empfehlung)
PELIK_ID = 2000028  # Lexo (pelik, laut LLM-Log Engine-Grün)


def sig_row(sid):
    return c.execute("SELECT * FROM signals WHERE signal_id=?", (sid,)).fetchone()


def show(title, rows):
    print(f"\n== {title} ==")
    for r in rows:
        print(dict(r))


for label, sid in (("MQL5", MQL5_ID), ("PELIK", PELIK_ID)):
    print("#" * 70)
    print(f"### {label} {sid}")
    s = sig_row(sid)
    if s:
        print("signals:", {k: s[k] for k in
                           ("signal_id", "name", "platform", "url", "abonnenten",
                            "wochen", "quelle", "updated_at")})
        stats = json.loads(s["stats_json"] or "{}")
        print("stats keys:", sorted(stats))
        print("stats:", {k: stats[k] for k in
                         ("eq_dd_pct", "bal_dd_pct", "ertrag_monat_pct", "pf",
                          "forensik_ok", "forensik_version", "initial_deposit_usd",
                          "kapitalbasis_virtual_usd", "monitor_trade_eq_dd_pct",
                          "last_fehler", "broker_server") if k in stats})
    tf = c.execute("SELECT path, sha256, fetched_at FROM trade_files WHERE signal_id=?",
                   (sid,)).fetchone()
    print("trade_files:", dict(tf) if tf else None)
    f = c.execute("SELECT updated_at, json FROM forensik WHERE signal_id=?",
                  (sid,)).fetchone()
    if f:
        fj = json.loads(f["json"])
        print("forensik.updated_at:", f["updated_at"])
        print("forensik keys:", sorted(fj))
        for k in ("version", "vollstaendig", "score", "ampel", "winrate_pct",
                  "stop_evidence", "martingale_flag", "symbole"):
            print(f"  {k}:", fj.get(k))
        print("  trading_dd:", fj.get("trading_dd"))
        print("  peak_exposure:", {k: fj.get("peak_exposure", {}).get(k) for k in
                                   ("positionen", "netto_lots", "schock_usd",
                                    "shock_pct_max")})
        print("  kapitalbasis:", fj.get("kapitalbasis"))
        reko = fj.get("equity_rekonstruktion")
        print("  equity_rekonstruktion:", json.dumps(reko, ensure_ascii=False)[:300]
              if reko else None)
        km = fj.get("kriterien_matrix")
        if km:
            print("  matrix dd_zelle:", km["kriterien"]["dd_schranke"])
    an = c.execute(
        "SELECT kind, model, tokens, created_at, basis IS NOT NULL AS hat_basis, "
        "length(text) AS zeichen FROM analyses WHERE signal_id=? ORDER BY id", (sid,)
    ).fetchall()
    show(f"analyses {sid}", an)
    qa = c.execute(
        "SELECT q.kuerzel, a.version, a.art, a.sha256, a.path, a.fetched_at "
        "FROM quellen_artefakte a JOIN datenquellen q ON q.id=a.quelle_id "
        "WHERE a.signal_id=?", (sid,)).fetchall()
    show(f"quellen_artefakte {sid}", qa)

# Pfade physisch prüfen
print("\n== Datei-Existenz ==")
for sid in (MQL5_ID, PELIK_ID):
    tf = c.execute("SELECT path FROM trade_files WHERE signal_id=?", (sid,)).fetchone()
    if tf:
        p = Path(tf["path"])
        print(sid, "trade_file exists:", p.exists(), p)

# quellen-artefakt vs trade_files SHA-Abgleich (pelik)
print("\n== SHA-Abgleich quellen_artefakte vs trade_files (pelik) ==")
rows = c.execute(
    "SELECT a.signal_id, a.sha256 AS qa_sha, t.sha256 AS tf_sha, a.path AS qa_path, "
    "t.path AS tf_path FROM quellen_artefakte a "
    "JOIN datenquellen q ON q.id=a.quelle_id AND q.kuerzel='pelik' AND a.art='trades' "
    "LEFT JOIN trade_files t ON t.signal_id=a.signal_id").fetchall()
mismatch = [dict(r) for r in rows if r["qa_sha"] != (r["tf_sha"] or "")]
print("Artefakte:", len(rows), "SHA-Mismatches:", len(mismatch))
for m in mismatch[:5]:
    print(" ", m)

# reports-Verzeichnis
print("\n== data/reports ==")
rep = PROJ / "data" / "reports"
if rep.exists():
    for sid in (MQL5_ID, PELIK_ID):
        treffer = sorted(rep.glob(f"*{sid}*"))
        print(sid, [t.name for t in treffer])
    print("gesamt Dateien:", len(list(rep.iterdir())))
else:
    print("kein data/reports")

# ampel_verlauf Ziellauf
print("\n== ampel_verlauf Zeitfenster 29.09.23:30 - 30.09.02:54 ==")
rows = c.execute(
    "SELECT ts, quelle, ampel, COUNT(*) n FROM ampel_verlauf "
    "WHERE ts >= '2026-09-29 23:00' GROUP BY ts, quelle, ampel ORDER BY ts").fetchall()
for r in rows:
    print(dict(r))
tot = c.execute(
    "SELECT ampel, COUNT(*) FROM ampel_verlauf WHERE ts >= '2026-09-30 00:00' "
    "GROUP BY ampel").fetchall()
print("ab 00:00:", [tuple(r) for r in tot])
tot2 = c.execute(
    "SELECT ampel, COUNT(*) FROM ampel_verlauf WHERE ts >= '2026-09-29 23:00' "
    "GROUP BY ampel").fetchall()
print("ab 23:00 (inkl. Vorgänger):", [tuple(r) for r in tot2])

# analyses Übersicht Ziellauf
print("\n== analyses je kind (30.09. 00:00-03:00) ==")
rows = c.execute(
    "SELECT kind, COUNT(*) n, SUM(tokens) tok FROM analyses "
    "WHERE created_at >= '2026-09-30 00:00' AND created_at < '2026-09-30 03:00' "
    "GROUP BY kind").fetchall()
for r in rows:
    print(dict(r))
print("portfolio-Zeile:",
      [dict(r) for r in c.execute(
          "SELECT signal_id, kind, model, tokens, created_at, length(text) zeichen "
          "FROM analyses WHERE kind='portfolio' ORDER BY id DESC LIMIT 2")])

# tradeserver_sync_runs
print("\n== tradeserver_sync_runs (letzte 5) ==")
for r in c.execute("SELECT * FROM tradeserver_sync_runs ORDER BY id DESC LIMIT 5"):
    print(dict(r))

# misslungene Signale des Ziellaufs: last_fehler in stats
print("\n== signals mit last_fehler (Ziellauf-Fails) ==")
rows = c.execute("SELECT signal_id, quelle, stats_json FROM signals").fetchall()
for r in rows:
    st = json.loads(r["stats_json"] or "{}")
    if st.get("last_fehler"):
        print(r["signal_id"], r["quelle"], str(st["last_fehler"])[:110])
