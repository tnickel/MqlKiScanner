# Analyse-Verlauf: alle untersuchten Signale und Urteile

Reihe von 6 Tiefenanalysen + 2 Marktscreenings (37 Signale gesamt),
Sep. 2026, Workspace Allgemein (Origin-Session
`sess_ff799a20-8b9b-4b1b-b605-0826e01ceffa`). PDF-Berichte: `doc/reports/`.

## Tiefanalysen (volle Forensik)

### 1. Gold Spike MT4 #2349227 / MT5 #2375480 — Dmitrii Kuropatkin
- **Urteil: Risiko-Score 4,0/10 — EMPFEHLUNG (Risikoträger)**
- Ausbruchs-Scanner auf Gold, 44 Wochen, 363 geprüfte Trades + 618 Pendings
- Einziger Orderbuch-Nachweis der Reihe: 368/368 Positionen mit SL/TP,
  161 von 186 Stop-Exits im Plus (Trailing, +1.016 USD), Verlustdeckel ~-41 USD
- EQ-DD 3,80 % (validiert), PF 3,15, Sharpe 0,33, ~22 %/Monat
- 3.116 USD Start, 3.400 USD entnommen (Startkapital draußen)
- Risiken: nur 44 Wochen, 0 Reviews, russischsprachig, RoboForex (Belize)
- MT4/MT5 = derselbe EA: 87 % der Trades sekundengenau identisch
  (`compare_mt4_mt5.py`), Abweichungen reine Ausführungsvarianz

### 2. KiraCat #2342895 — Akl Keyrouz, FP Markets — 49 USD/Monat
- **Urteil: Risiko-Score 4,7/10 — EMPFEHLUNG (Ertragsträger)**
- 100 % MANUELL: US30-Scalps (443 Trades, +18.396 USD, Median 1,1 h)
  + NZDCAD-Grid-Sleeve ab 04/2026 (101 Trades, Körbe bis 11 Positionen)
- PF 4,11 (Rekord), ~25 %/Monat, realer Trading-DD 7,9 % (validiert)
- Ernte: 48.128 USD entnommen, Konto exakt 1.000 USD
- RISIKO: kein Markt-Stop; 03.03.2026: 5-Lot-Short 48 h gegen die Rallye,
  -2.150,90 USD (~7 % des Kontos in einem Trade); danach Pause + Verkleinerung
- Bestes Broker-Umfeld der Reihe (FP-Markets-Gruppe, ASIC AFSL 286354;
  Signalkonto auf Mauritius-Tochter)

### 3. Gold Reaper New V2.2 #2265877 — Profalgo Limited, IC Trading — 35 USD
- **Urteil: Risiko-Score 4,4/10 — solide Strategie, ABER nur als EA-Kauf**
  (EA im Market: ~949 USD, 4,47/5 — Anbieter empfiehlt Kauf selbst)
- SL-System mit Pyramiding (17 größte Positionen netto +376 USD), kein Martingale
- EQ-DD 7,18 %, 97 Wochen, nie Nachschuss; 3 Verlustmonate, je Folgemonat erholt
- KILLERKRITERIUM: 8 von 14 Reviews = fehlgeschlagene Kopien
  (Kontogrößen-Mismatch 6.000- vs. 1.000-USD-Konten, Symbol-Mapping,
  Millisekunden-Pending-Orders)
- Broker: Capital Point Trading (Mauritius, FSC GB21026834),
  FSA-Japan-Warnliste

### 4. MSC Gold Stable Pro #2231030 — Bui Huy Dat, NeoTech — 40 USD
- **Urteil: Risiko-Score 5,6/10 — abgelehnt (Schranke verletzt)**
- 123 Wochen, 1.085 Trades, nur Gold; Counter-Trend-Grid-Scalper OHNE
  Martingale; FOMC-Filter nachweisbar (0 Trades an 14/19 FOMC-Tagen)
- ABER: EQ-DD 33,7 % (Juni 2025, Kriegsschock) — 30-%-Schranke verletzt
- Sekunden-Scalper: Median-Gewinn 2,50 USD → Slippage-frissig;
  2/4 Reviews beklagen Slippage/Copy-Mismatch
- Broker NeoTech (FSCA echt, aber jung, Auszahlungsbeschwerden)
- POSITIV: längster Track Record der Reihe, Schock überlebt

### 5. FXtrading #2356441 — Alexander Pavlenko, RoboForex — 30 USD
- **Urteil: Risiko-Score 5,7/10 — abgelehnt**
- Counter-Trend-Grid, 17 Paare (36 % CAD-Exposure), Martingale-Korb
  nachgewiesen (EURNZD 0,01→0,02→0,04), kein Stop-Loss
- Schwächster Ertrag der Reihe (~5 %/Monat); Mini-Konto: 203 USD Start +
  830 USD Nachschüsse; 0 Reviews; EQ-DD 6,6 % historisch ok, aber
  Grid-Tail-Risiko ohne SL

### 6. World PEACE Multi FX Algo #2379208 — Nobeyo-Sano, HF Markets — 30 USD
- **Urteil: Risiko-Score 8,0/10 — abgelehnt (schlechtester der Reihe)**
- Grid + Martingale (EURNZD-Korb 0,01→0,08), kein SL, 10 korrelierte Paare,
  faktisch gebündelte Short-JPY-Wette (EURJPY 365 Sell / 27 Buy)
- EQ-DD 30,6 % passiert; floating DDs >20 % wiederholt
- Positiv: Anbieter ungewöhnlich ehrlich (warnt selbst vor Totalverlust)
- Korrigierte Kontraktrechnung gilt hier ebenso: 1 Lot Gold = 100 USD/USD

## Marktscreening (ohne volle Forensik)

### 25er-Favoritenliste des Nutzers (alle gescreent)
Sieben Signale mit EQ-DD > 30 %; mehrere Namenslügen ("Low Risk" 32 % Winrate
+ 24 mögliche Verluste in Serie; "Hedge Yield" 44 % EQ-DD; HJM1 PF 1,07 mit
-21.550-USD-Einzelverlust). Details: Gesamtbericht PDF, Kapitel 4.

### Katalog-Scan Sept. 2026 (12 weitere Kandidaten + Trade-Exports)
- **GoldWave #2339082 (49 Abo):** 96,8 % Winrate, 0 negative Monate in 16,
  PF 4,42 — ABER 50-USD-Micro-Konto, 362 USD Gesamtgewinn, Median-Gewinn
  1,06 USD, Rollover-Scalper (20-23 Uhr). Watchlist, nicht kopieren.
- **NoPain MT5 #2262642 (66 Abo):** 5 Jahre, EQ-DD 20,6 % — aber 1,7 %
  Ertrag/Monat, 86 % manuell. Abgelehnt (Ertrag).
- **Multi EA Trading #2375343 (13 Abo):** EQ-DD 33,1 %, negative Monate.
  Abgelehnt (Schranke).
- **SFE Impulse #2049326 (1 Abo, 100 USD/Monat):** 157 Wochen, EQ-DD 7,9 %,
  aber Kurve 12 Monate seitwärts, PF 1,43. Vom Nutzer abgelehnt.
- **Pure Gold 2000 Vantage #2362868 (5 Abo, 30 USD):** sah im Kennzahlen-
  Screen top aus (EQ-DD 5,1 %, +26 %/Monat, PF 2,34) → Trade-Export-Forensik:
  10.000-USD-Konto, +20.731 USD in 6 Monaten, Ernte 12.000 USD — ABER:
  max. 32 gleichzeitige SELL-Positionen, 2,66 Lots netto (= 266 USD je 1 USD
  Bewegung; 50-USD-Schock ~ -13.300 USD), kein Stop-Nachweis (Verlust-
  distanzen ungebündelt, Worst -152 USD Bewegung), 19-Verluste-Serie in
  3 Tagen, nur 26 Wochen. **Vom Nutzer zu Recht als hochriskant erkannt und
  herabgestuft.** Lektion: Kennzahlen-Screen ohne Struktur-Tests genügt nicht.
- Weitere 11 abgelehnt (MagicGW 45,8 % EQ-DD; SERONGGA 49 % Bal-DD;
  Low Risk Gold 45,9 % EQ-DD; MSC SuperGold 53 % Bal-DD; OnlyUJ 35,5 %;
  GOLD HUAT 44,2 %; Goldtrade ICM 32 %; Turtle One/LUBOTFX/DiffGold/
  Lucky Cat/Ultimate Portfolio: Ertrag oder negative Monate)

## Kalibrierung des Risiko-Scores (1-10, hoch = riskant)

| Score | Signal | EQ-DD | Realer DD | Ertrag/Monat | PF | Wochen |
|---|---|---|---|---|---|---|
| 4,0 | Gold Spike | 3,8 % | 4,6 % | ~22 % | 3,15 | 44 |
| 4,4 | Gold Reaper | 7,2 % | 16,9 % Bal. | ~11 % | 2,35 | 97 |
| 4,7 | KiraCat | 20,6 %* | 7,9 % | ~25 % | 4,11 | 43 |
| 5,6 | MSC Gold | 33,7 % | 15,4 % | ~10 % | 3,24 | 123 |
| 5,7 | FXtrading | 6,6 % | 14,1 % | ~5 % | 2,71 | 67 |
| 8,0 | World PEACE | 30,6 % | 15,5 % | ~17 % | 1,99 | 78 |

* KiraCat-EQ-DD auf frühem Minikonto; real 7,9 % validiert.

Unabhängige Zweitmeinung (ChatGPT-Analysen des Nutzers): gleiche Rangfolge,
strengere Noten (Gold Reaper 7/10, MSC 8,3/10).

## Endergebnis (Stand 04.09.2026)

**Duo: Gold Spike (Risikoträger) + KiraCat (Ertragsträger).**
Nachprüf-Termine: Okt. 2026 (Automation im Allgemein-Workspace).
Wieder aufnehmen: Pure Gold 2000 nur mit Orderbuch-Stop-Nachweis;
GoldWave/SFE nur bei deutlicher Verbesserung.
