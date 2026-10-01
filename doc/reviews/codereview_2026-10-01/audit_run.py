"""Read-only Abgleich des echten Scan-Laufs 98 mit SQLite und Dateilog.

Keine Projektimporte, keine API-Aufrufe, keine Änderungen an der Datenbank.
"""
from pathlib import Path
from collections import Counter
import json
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[3]


def audit():
    con = sqlite3.connect((ROOT / "data/mqlkiscanner.db").as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("BEGIN")
    run = dict(con.execute("SELECT * FROM agenten_laeufe WHERE id=98").fetchone())
    lines = (ROOT / "tmp/scan_full_err.log").read_text(encoding="utf-8-sig").splitlines()
    error_entries = []
    ordered_ids = []
    for line_no, line in enumerate(lines, 1):
        match = re.search(r"\[forensik (\d+)/(\d+)\] (.*?) #(\d+)", line)
        if match:
            ordered_ids.append({"id": int(match[4]), "name": match[3], "line": line_no})
        match = re.search(r"FEHLER bei (\d+): (.*)", line)
        if match:
            error_entries.append({"id": int(match[1]), "line": line_no, "message": match[2]})
    start, end = run["start"], run["ende"]
    analyses = [dict(r) for r in con.execute(
        "SELECT id,signal_id,kind,model,tokens,created_at,text FROM analyses "
        "WHERE created_at>=? AND created_at<=? ORDER BY id", (start, end))]
    grouped = Counter(r["kind"] for r in analyses)
    tokens = sum(r["tokens"] or 0 for r in analyses)
    portfolio = next(r for r in reversed(analyses) if r["kind"] == "portfolio")
    grades = Counter()
    selected = []
    for r in con.execute("SELECT s.signal_id,s.name,s.quelle,s.stats_json,f.updated_at,f.json "
                         "FROM signals s JOIN forensik f USING(signal_id) WHERE f.updated_at>=?",
                         (start,)):
        stats = json.loads(r["stats_json"] or "{}")
        facts = json.loads(r["json"])
        if not stats.get("forensik_ok") or not facts.get("vollstaendig"):
            continue
        grades[facts["ampel"]] += 1
        if facts["ampel"] == "🟢" or r["signal_id"] in (2342895, 2000028, 2014076, 2019435, 2084818):
            selected.append({"id": r["signal_id"], "name": r["name"], "source": r["quelle"],
                             "ampel": facts["ampel"], "score": facts["score"],
                             "return_pct": stats.get("ertrag_monat_pct_forensik"),
                             "capital": facts.get("kapitalbasis"),
                             "matrix": facts.get("kriterien_matrix"),
                             "equity_reconstruction": facts.get("equity_rekonstruktion")})
    con.rollback()
    con.close()
    return {"run": run, "log": "tmp/scan_full_err.log", "log_lines": len(lines),
            "scope_count": len(ordered_ids), "scope_ids": ordered_ids,
            "failed_signals": sorted({r["id"] for r in error_entries}),
            "error_entries": error_entries, "analysis_counts": dict(grouped),
            "persisted_tokens": tokens, "logged_tokens": 1866388,
            "token_difference": 1866388 - tokens, "grades": dict(grades),
            "selected_examples": selected,
            "portfolio": {k: v for k, v in portfolio.items() if k != "text"},
            "portfolio_text": portfolio["text"],
            "notes": "Nur echter Lauf 98; synthetische Testzeile 1116 gehört nicht dazu. "
                     "Forensik-Zählung bezieht sich auf den beim Audit vorhandenen neuesten Bestand."}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
