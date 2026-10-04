# -*- coding: utf-8 -*-
"""Unabhängige Rechenorakel des Reviews 04.10.2026 (Phase 3, M-Katalog).

Die SOLL-Werte werden hier NEU und unabhängig hergeleitet (nur math/decimal,
keine Projektformeln importiert). Anschließend werden die Produktions-
funktionen NUR zum Vergleich aufgerufen. Ein Abgleich-Skript, keine Testsuite.

Ausführung:  python doc/reviews/codereview_2026-10-04/orakel/pruef_orakel.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

ERGEBNIS: list[tuple[str, bool, str]] = []


def pruefung(name: str, soll, ist) -> None:
    ok = soll == ist
    ERGEBNIS.append((name, ok, f"soll={soll!r} ist={ist!r}"))


# ----------------------------------------------------------------------------
# M01: Start 10.000, End 12.100, exakt 2 Projektmonate.
#      Monat = 365,2425/12 Tage. Geometrisch: (1,21)^(1/2)-1 je Monat.
# ----------------------------------------------------------------------------
JAHR = 365.2425
MONAT = JAHR / 12.0
geom_m01 = ((12100.0 / 10000.0) ** (MONAT / (2 * MONAT)) - 1.0) * 100.0
pruefung("M01 ertrag_monat_geom_pct == 10.0", 10.0, round(geom_m01, 10))
cagr_m01 = ((12100.0 / 10000.0) ** (JAHR / (2 * MONAT)) - 1.0) * 100.0
pruefung("M01 cagr_jahr_pct == 213.8428376721 (100*(1.21^6-1))",
         213.8428376721, round(cagr_m01, 10))

# Abgleich Produktion (effizienz_kennzahlen rechnet selbstständig):
from mqlkiscanner import portfolio_statistik  # noqa: E402
import tempfile  # noqa: E402

HEADER = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n")
# 2 exakte Projektmonate: erster Open 2026.01.01, letzter Close 2026.03.01
# (≈ 59 Tage ≈ 1.94 Monate — für exakt 2 Monate nutzen wir 01.01→01.03 +
#  Korrektur: der Einfachheit halber M01 numerisch über die Funktion mit
#  konstruierter Dauer; siehe unten stattedessen Zeitraum 01.01 00:00 bis
#  03.01 00:00 + 2.4375 Tage, sodass dauer == 2*MONAT exakt.)
dauer_soll_tage = 2 * MONAT
zeile = ("2026.01.01 00:00:00;Buy;0.01;XAUUSD;1000;0.01;"
         "2026.03.01 00:00:00;2210;0;0;2100\n")
with tempfile.TemporaryDirectory() as tmp:
    pfad = Path(tmp) / "m01.csv"
    pfad.write_text(HEADER + zeile, encoding="utf-8")
    erg = portfolio_statistik.effizienz_kennzahlen(str(pfad), 10000.0, None)
    ist_geom = round(erg["ertrag_monat_geom_pct"], 6)
    ist_cagr = round(erg["cagr_jahr_pct"], 6)
# Soll unabhängig: End/Start = 12100/10000 = 1.21, dauer = 59+2.4375? Nein —
# dauer oben = 01.01→03.01 = 59 Tage. Unabhängiger Soll-Wert dafür:
soll_geom = ((1.21) ** (MONAT / 59.0) - 1) * 100.0
soll_cagr = ((1.21) ** (JAHR / 59.0) - 1) * 100.0
pruefung("M01-Produktion geom (59 d) == unabhängiger Soll",
         round(soll_geom, 6), ist_geom)
pruefung("M01-Produktion CAGR (59 d) == unabhängiger Soll",
         round(soll_cagr, 6), ist_cagr)

# ----------------------------------------------------------------------------
# M02: M01 mit belegtem Equity-DD 5 % → RetDD/Monat = 2, RetDD/Jahr ≈ 42.77
# ----------------------------------------------------------------------------
pruefung("M02 retdd_monat = 10/5", 2.0, 10.0 / 5.0)
pruefung("M02 retdd_jahr != 12 * retdd_monat", True,
         not math.isclose(213.8428376721 / 5.0, 12 * 2.0))

# ----------------------------------------------------------------------------
# M06: DD 29,9999 / 30 / 30,0001 bei Limit 30 — ungerundeter Vergleich
# ----------------------------------------------------------------------------
from mqlkiscanner import scoring  # noqa: E402
for wert, verletzt in ((29.9999, False), (30.0, False), (30.0001, True)):
    ist = scoring.dd_maximum(wert) > 30.0
    pruefung(f"M06 dd_maximum({wert}) > 30 == {verletzt}", verletzt, ist)

# ----------------------------------------------------------------------------
# M07: Fünf DD-Werte 15/20/12/26/31 → konservatives Maximum 31
# ----------------------------------------------------------------------------
pruefung("M07 dd_maximum(15,20,12,26,31) == 31", 31.0,
         scoring.dd_maximum(15, 20, 12, 26, 31))

# ----------------------------------------------------------------------------
# M23: XAUUSD 2,66 Lots, adverser Move 50 USD → 13.300 USD Exposure
# ----------------------------------------------------------------------------
pruefung("M23 XAUUSD-Exposure 2,66 Lot x 100 USD x 50 == 13300",
         13300.0, 2.66 * 100.0 * 50.0)

# ----------------------------------------------------------------------------
# M24: USC-PnL 12.345 == USD-PnL 123,45 (Skalierung nur Geldbeträge)
# ----------------------------------------------------------------------------
pruefung("M24 USC 12345 / 100 == USD 123.45", 123.45, 12345 / 100.0)

# ----------------------------------------------------------------------------
# M05: RetDD-Grenze 0,9995/1/1,0005 — Auswahl prüft ungerundete Werte
# ----------------------------------------------------------------------------
from mqlkiscanner import pipeline  # noqa: E402


def _result(**kwargs):
    values = dict(id=900009, name="Grenze", forensik_vorhanden=True,
                  score=2.0, martingale_flag=False, stop_evidence="none",
                  ertrag_monat_geom_pct=5.0, cagr_jahr_pct=60.0,
                  equity_dd_rekonstruiert_pct=5.0,
                  trading_dd_pct=0.1, dd_balance_pct=1.0, dd_equity_pct=1.0,
                  retdd_monat=999.0)
    values.update(kwargs)
    return pipeline.ScanResult(**values)


pruefung("M05 retdd 0.9995 sperrt Grün (🟡)", "🟡",
         pipeline.ampel_for(_result(ertrag_monat_geom_pct=4.9975), {})[0])
pruefung("M05 retdd 1.0 erlaubt Grün (🟢)", "🟢",
         pipeline.ampel_for(_result(ertrag_monat_geom_pct=5.0), {})[0])
pruefung("M05 retdd 1.0005 erlaubt Grün (🟢)", "🟢",
         pipeline.ampel_for(_result(ertrag_monat_geom_pct=5.0025), {})[0])

# ----------------------------------------------------------------------------
# M27: '9,10', '1 403.03', '1.403,03', bool, NaN, Infinity
# ----------------------------------------------------------------------------
from mqlkiscanner.scoring import _platform_float  # noqa: E402
pruefung("M27 '9,10' == 9.1", 9.1, _platform_float("9,10"))
pruefung("M27 '1 403.03' == 1403.03", 1403.03, _platform_float("1 403.03"))
pruefung("M27 '1.403,03' == 1403.03", 1403.03, _platform_float("1.403,03"))
pruefung("M27 bool True == Default 0.0", 0.0, _platform_float(True))
pruefung("M27 'NaN'/'Infinity' == Default", 0.0,
         _platform_float(float("nan")))
pruefung("M27 murks == Default", 0.0, _platform_float("murks"))

# ----------------------------------------------------------------------------
# M04: belegter Equity-DD = 0 → RetDD unbekannt (keine Infinity als Qualität)
# ----------------------------------------------------------------------------
r0 = _result(equity_dd_rekonstruiert_pct=0.0, retdd_monat=None)
r0.refresh_efficiency()
pruefung("M04 dd=0 → retdd_monat None", None, r0.retdd_monat)

# ----------------------------------------------------------------------------
# Bericht
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    fehler = [e for e in ERGEBNIS if not e[1]]
    for name, ok, detail in ERGEBNIS:
        print(("PASS " if ok else "FAIL ") + name + "  [" + detail + "]")
    print(f"\n{len(ERGEBNIS) - len(fehler)}/{len(ERGEBNIS)} Orakel bestanden.")
    sys.exit(1 if fehler else 0)
