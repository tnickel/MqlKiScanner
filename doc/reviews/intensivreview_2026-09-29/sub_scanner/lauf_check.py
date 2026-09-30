# -*- coding: utf-8 -*-
"""Review-Subagent Scanner: results.json, Forensik-Vollständigkeit, GMT-Statistik."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

PROJ = Path(r"D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner")
RUN = PROJ / "data/runs/2026-09-30_025355_970680_c65bf5cd/results.json"
DB = PROJ / "doc/reviews/intensivreview_2026-09-29/sub_scanner/work/workcopy.db"

payload = json.loads(RUN.read_text(encoding="utf-8"))
print("== results.json Struktur ==")
print("keys:", sorted(payload))
print("zeitstempel:", payload["zeitstempel"])
print("logs keys:", {k: len(v) for k, v in payload["logs"].items()})
res = payload["ergebnisse"]
print("ergebnisse:", len(res))
first = res[0]
print("felder je ergebnis:", len(first))
print(sorted(first))

# Abgleich Ampel/Quelle/Forensik mit DB
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
c = conn.cursor()
db_amp = {r["signal_id"]: (json.loads(r["json"] or "{}").get("ampel"),
                           json.loads(r["json"] or "{}").get("score"))
          for r in c.execute("SELECT signal_id, json FROM forensik")}

sel_ids = {2379208,2265877,2262642,2339082,2231030,2306053,2304847,2327790,2349227,
2329290,2379236,2356441,2362349,2308093,2371777,2362868,2375343,2347343,2300694,
2153920,2359404,2386939,2356872,2351091,2271402,2307342,2367701,2357156,840474,2268766,
2019435,2000028,2014074,2063644,2014076,2059368,2084818,2014626,2072334,2039057,
2016702,2041912,2048285,2074880,2041931,2048284,2000892,2021443,2012139,2049613,
2041033,2065185,2059824,2019075,2005451,2054437,2053240,2052727,2007510,2064854}
run_ids = {r["id"] for r in res}
print("\nAuswahl-Reproduktion identisch mit results.json:", run_ids == sel_ids,
      f"(results: {len(run_ids)})")

amp = Counter(r["ampel"] for r in res)
q = Counter(r.get("quelle") or "mql5" for r in res)
fehler = [r["id"] for r in res if r.get("fehler")]
print("results Ampel:", dict(amp), "Quelle:", dict(q))
print("mit Fehler:", len(fehler), fehler)
# Vergleich je Signal: results.json ampel/score vs forensik-DB (nur ziellauf-aktualisierte)
mismatch = []
for r in res:
    if r["id"] in db_amp and r["id"] in sel_ids:
        a, s = db_amp[r["id"]]
        if r["ampel"] != a or (r.get("score") or 0) != (s or 0):
            mismatch.append((r["id"], r["ampel"], r.get("score"), a, s))
print("Ampel/Score-Mismatches results vs forensik-Tabelle:", mismatch if mismatch else "keine")

# Portfolio
pf = payload.get("portfolio") or {}
print("\n== portfolio ==")
print({k: v for k, v in pf.items() if k != "text"})
print("text-anfang:", (pf.get("text") or "")[:200].replace("\n", " "))

# Forensik-Vollständigkeit der 60
print("\n== forensik-Zeilen der 60 (updated_at) ==")
rows = {r["signal_id"]: r["updated_at"] for r in c.execute("SELECT signal_id, updated_at FROM forensik")}
im_lauf = {sid: ts for sid, ts in rows.items() if sid in sel_ids and ts >= "2026-09-30 00:00"}
print("forensik im Ziellauf aktualisiert:", len(im_lauf), "(erwartet 52)")
fehlend = sel_ids - set(im_lauf)
print("nicht aktualisiert (Fails):", sorted(fehlend))
alt_davon = {sid: rows.get(sid) for sid in fehlend if sid in rows}
print("davon mit ALT-Forensik:", {k: v for k, v in sorted(alt_davon.items())[:10]})

# Feld-Vollständigkeit
print("\n== Feld-Check forensik-JSON der 52 ==")
pflicht = ["version", "vollstaendig", "trading_dd", "winrate_pct", "max_verlustserie",
           "peak_exposure", "martingale_flag", "stop_nachweis", "stop_evidence",
           "kapitalbasis", "kriterien_matrix", "ampel", "score", "equity_rekonstruktion",
           "fx_kursquelle"]
probleme = []
stat = Counter()
for r in c.execute("SELECT signal_id, json FROM forensik"):
    sid = r["signal_id"]
    if sid not in im_lauf:
        continue
    fj = json.loads(r["json"])
    fehlt = [k for k in pflicht if k not in fj]
    if fehlt:
        probleme.append((sid, fehlt))
    pe = fj.get("peak_exposure") or {}
    if pe.get("shock_pct_max") is None:
        probleme.append((sid, "shock_pct_max None"))
    kb = fj.get("kapitalbasis") or {}
    stat[kb.get("quelle")] += 1
    st = fj.get("equity_rekonstruktion")
    stat["reko_" + (st.get("status") if st else "None")] += 1
print("Probleme:", probleme if probleme else "keine")
print("kapitalbasis.quelle / reko.status:", dict(stat))

# monitor_trade_eq_dd_pct für pelik
print("\n== monitor_trade_eq_dd_pct je Quelle (stats) ==")
mon = Counter()
for r in c.execute("SELECT signal_id, stats_json FROM signals"):
    if r["signal_id"] not in sel_ids:
        continue
    st = json.loads(r["stats_json"] or "{}")
    hat = st.get("monitor_trade_eq_dd_pct") is not None
    quelle = "pelik" if 2000000 <= r["signal_id"] <= 2100000 else "mql5"
    mon[(quelle, hat)] += 1
print(dict(mon))

# GMT-Verteilung + Plateau
print("\n== Equity-Reko je Signal (52) ==")
for r in c.execute("SELECT signal_id, json FROM forensik"):
    if r["signal_id"] not in im_lauf:
        continue
    fj = json.loads(r["json"])
    st = fj.get("equity_rekonstruktion")
    if st:
        print(r["signal_id"], st.get("status"), "gmt", st.get("gmt_offset_h"),
              "q", st.get("gmt_trefferquote"), "dd", st.get("equity_dd_pct"),
              "abdeck", st.get("abdeckung_pct"), "verl", st.get("verlaesslich"),
              (st.get("grund", "")[:60] if st.get("grund") else ""))
