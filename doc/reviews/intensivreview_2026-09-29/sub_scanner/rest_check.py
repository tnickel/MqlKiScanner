# -*- coding: utf-8 -*-
"""Review-Subagent Scanner: REST-API-Simulation auf Arbeitskopie + FX-Details."""
import json
import sqlite3
import sys
from pathlib import Path

PROJ = Path(r"D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner")
WORK = Path(__file__).parent / "work"
sys.path.insert(0, str(PROJ / "src"))

import mqlkiscanner.db as db
db.DB_PATH = WORK / "workcopy.db"          # Arbeitskopie, nie Produktiv-DB

# PDF-Materialisierung neutralisieren (results_from_db ruft sie sonst auf)
import mqlkiscanner.pdf_reports as pr
pr.materialize_result_pdfs = lambda *a, **k: {}

from mqlkiscanner import pipeline, rest_api, config
settings = config.load_settings()
results = pipeline.results_from_db(settings)
print("results_from_db:", len(results))
from collections import Counter
print("Ampel:", dict(Counter(r.ampel for r in results)))
print("Quelle:", dict(Counter(r.quelle for r in results)))
payload = rest_api.signal_payload(results, {"gruen", "gelb"})
print("\nGET /api/v1/signals?ampel=gruen,gelb -> count:", payload["count"])
for z in payload["signals"]:
    print(f"  {z['signalId']} {z['quelle']:5s} {z['platform']:8s} {z['ampel']:6s} "
          f"score={z['score']} {z['name'][:32]}")
alle = rest_api.signal_payload(results, None)
print("\nOhne Filter: count", alle["count"],
      "davon ausgeschlossen:", sum(1 for z in alle["signals"] if z["ampel"] == "ausgeschlossen"))

# FX-Details pelik
conn = sqlite3.connect(f"file:{WORK / 'workcopy.db'}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
c = conn.cursor()
print("\n== fx_conversion je pelik-Forensik (Beispiele) ==")
n = 0
for r in c.execute("SELECT signal_id, json FROM forensik WHERE signal_id BETWEEN 2000000 AND 2100000"):
    fj = json.loads(r["json"])
    if not fj or n >= 4:
        continue
    expo = fj.get("peak_exposure") or {}
    print(r["signal_id"], "fx_kursquelle:", fj.get("fx_kursquelle"),
          "| symbole:", fj.get("symbole"))
    n += 1

# fx_rates Cache
print("\n== data/fx_rates ==")
fxdir = PROJ / "data" / "fx_rates"
if fxdir.exists():
    for f in sorted(fxdir.iterdir()):
        print(" ", f.name, f.stat().st_size, "bytes")
sys.path.insert(0, str(PROJ / "src"))
from mqlkiscanner import fx_rates
st = fx_rates.status()
print("status:", {k: st[k] for k in st if k != "waehrungen"})
print("waehrungen:", st.get("waehrungen"))
