"""Forensik-Test-Batterie (Spec: doc/03_forensik-tests.md).

Aus scripts/reference/ konsolidiert (Phase 1, doc/04_roadmap.md):
- martingale.py : Test 1 Lot-Eskalation nach Verlusten
- exposure.py   : Test 2 Peak-Positionen + USD-Risiko (XAUUSD: 100 USD/Lot/USD)
- stops.py      : Test 3 SL-Clustering (+ Orderbuch-Direktnachweis)
- drawdown.py   : Test 4 Rekonstruktion + Plattform-Abgleich (Anker: auf den Cent)
- baskets.py    : Basket-Exits / Grid-Indikator (Soll)
- news.py       : FOMC-Korrelation (Soll)

Referenzlogik: scripts/reference/martingale_exposure_test.py, analyze_*.py.
Regel: Kein Kandidat bekommt eine positive Einstufung, bevor alle vier
Pflicht-Tests gelaufen sind und die Ergebnisse im Befund stehen.
"""
