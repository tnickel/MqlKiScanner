"""Kreuzpruefung: gespeicherte KI-Antworten des Ziellaufs gegen die Forensik-Zahlen.

Read-only auf die Produktiv-DB (SELECT). Prueft fuer jedes der 60 Signale:
  A) Wird ein USD-Betrag ohne Einheitenmarker als Prozent zitiert?  (B11)
  B) Nennt die KI eine Ertrags-%/Monat-Zahl, die von der Engine abweicht? (B2/B3)
  C) Veraendert eine Antwort die Ampelfarbe? (Engine ist bindend)
  D) Nennt die KI "Stop-Loss fehlt" als Ausschlussgrund? (SL-Neutralitaet)
  E) Nennt die KI Abonnenten als Qualitaetsmerkmal? (Design-Regel 4)
"""
import json
import re
import sqlite3
from collections import defaultdict

DB = "data/mqlkiscanner.db"
LAUF = "data/runs/2026-09-30_025355_970680_c65bf5cd/results.json"

PCT_RE = re.compile(r"(-?\d[\d\s.]*)\s*(?:%|Prozent)")
USDFELD_RE = re.compile(r"(shock_pct_peak_account|shock_usd|peak_shock[a-z_]*)\D{0,40}?(\d[\d\s.]*)\s*%")


def zahl(s):
    s = (s or "").replace("\u00a0", "").replace(" ", "").replace("%", "")
    s = s.replace(".", "", 1) if s.count(",") and s.count(".") else s
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def main():
    res = json.load(open(LAUF, encoding="utf-8"))
    erg = res["ergebnisse"]
    con = sqlite3.connect(DB)
    foren = {}
    for sid, j in con.execute("SELECT signal_id, json FROM forensik"):
        try:
            foren[sid] = json.loads(j)
        except Exception:
            pass
    # Antworten des Laufs: die juengsten je (signal, kind) mit created_at am Lauftag
    ant = defaultdict(list)
    for sid, kind, txt, ts in con.execute(
            "SELECT signal_id, kind, text, created_at FROM analyses "
            "WHERE created_at >= '2026-09-30 00:00:00' ORDER BY created_at"):
        ant[(sid, kind)].append((ts, txt or ""))
    amp = {x["id"]: x.get("ampel") for x in erg}
    con.close()

    print("Signale im Lauf:", len(erg))
    print("Signale mit >=1 Antwort am Lauftag:", len({k[0] for k in ant}))
    nach_art = defaultdict(int)
    for (sid, kind) in ant:
        nach_art[kind] += 1
    print("Antworten je Art:", dict(nach_art))

    # Portfolio-Antwort des Laufs
    port = [t for (sid, kind), v in ant.items() if kind == "portfolio" for _, t in v]
    print("\n== Portfolio-Antwort ==")
    for t in port:
        print(t[:1800].replace("\n", " ")[:1800])
        print("...")

    # Ampel-Abgleich: nennt eine gesamtbericht-Antwort eine andere Farbe?
    print("\n== Ampel-Bindung (Stufe 2 gesamtbericht) ==")
    AMPEL = {"\U0001F534": "rot", "\U0001F6E0": "kein", "\U0001F7E2": "gruen",
             "\U0001F7E1": "gelb", "\U0001F6D1": "ausschluss"}
    wort2amp = {v: k for k, v in AMPEL.items()}
    abw = 0
    for (sid, kind), v in ant.items():
        if kind != "gesamtbericht":
            continue
        t = v[-1][1]
        g = amp.get(sid)
        if g not in wort2amp:
            continue
        soll = wort2amp[g]
        genannt = set(re.findall(r"[\U0001F534\U0001F6E0\U0001F7E2\U0001F7E1\U0001F6D1]", t))
        # zaehle positive Veroeffentlichungen ("Ampel gruen", "bewertet als gruen")
        positiv = {a for a in genannt
                   if re.search(r"(empfehl|bewertet|einstuf|urteil|ampel)[^.]{0,40}" + a, t)}
        if positiv and soll not in positiv:
            abw += 1
            print("  ABWEICHUNG %s: soll %s, genannt %s" % (sid, g, positiv))
    print("  Abweichungen:", abw)

    # B) Ertragsabweichung gegen Engine
    print("\n== Ertrags-%/Monat: KI vs. Engine ==")
    n = geprueft = abweichend = 0
    treffer = []
    for (sid, kind), v in ant.items():
        if kind not in ("gesamtbericht", "risiko_analyse"):
            continue
        t = v[-1][1]
        prod = next((x for x in erg if x["id"] == sid), None)
        if not prod:
            continue
        pe = prod.get("ertrag_monat_pct")
        for m in PCT_RE.finditer(t):
            wert = zahl(m.group(1))
            if wert is None or abs(wert) > 200:
                continue
            if not re.search(r"(ertrag|rendite|monat|%/?m|pro monat)", t[max(0, m.start() - 120):m.start()], re.I):
                continue
            n += 1
            if pe is None:
                continue
            geprueft += 1
            if abs(wert - pe) > max(0.5, abs(pe) * 0.25):
                abweichend += 1
                treffer.append((sid, prod.get("name", "")[:22], pe, wert))
    print("  Ertragszahlen gefunden:", n, " mit Engine-Vergleich:", geprueft,
          " abweichend:", abweichend)
    for t in treffer[:25]:
        print("   %s %-22s Engine %6.2f  KI %8.2f" % t)

    # A) USD-Feld als Prozent zitiert (B11)
    print("\n== B11: USD-Betrag als Prozent zitiert ==")
    treffer = []
    for (sid, kind), v in ant.items():
        t = v[-1][1]
        for m in USDFELD_RE.finditer(t):
            wert = zahl(m.group(2))
            if wert is None:
                continue
            if wert > 2000:      # Schock-USD ist zweistellig/ dreistellig
                treffer.append((sid, kind, m.group(1), wert))
    for x in treffer[:20]:
        print("  ", x)
    print("  Treffer:", len(treffer))

    # D) SL als Ausschluss
    print("\n== SL-Neutralitaet ==")
    sl_verbot = []
    for (sid, kind), v in ant.items():
        t = v[-1][1].lower()
        for m in re.finditer(r"(stop-?loss|stop|sl)[^.]{0,120}", t):
            seg = m.group(0)
            if re.search(r"(ausschluss|verwirf|disqualif|kein stop|ohne stop)", seg) \
                    and re.search(r"(stop|sl)", seg):
                sl_verbot.append((sid, kind, seg[:110]))
    for x in sl_verbot[:15]:
        print("  ", x)
    print("  Treffer:", len(sl_verbot))

    # E) Abonnenten als Qualitaet
    print("\n== Abonnenten als Qualitaetsmerkmal ==")
    ab = 0
    for (sid, kind), v in ant.items():
        t = v[-1][1]
        for m in re.finditer(r"[^.]{0,140}abonnenten[^.]{0,140}", t, re.I):
            if re.search(r"(qual|gut|best|stark|vertrau|empfehl|beweis)", m.group(0), re.I) \
                    and not re.search(r"(kein|keine|nicht|unabh.ngig)", m.group(0), re.I):
                ab += 1
                if ab <= 12:
                    print("  ", sid, kind, m.group(0)[:150].replace("\n", " "))
    print("  Treffer:", ab)


if __name__ == "__main__":
    main()
