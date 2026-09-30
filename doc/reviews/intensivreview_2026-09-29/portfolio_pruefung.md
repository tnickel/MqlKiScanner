# Portfolio-/Diversifikationsprüfung — Ziellauf 2026-09-30

Unabhängige Prüfung der Diversifikationsbehauptung des Portfolio-Berichts
(„drei getrennte Märkte … deutlich verschiedene Haltedauern"), die im Lauf
selbst **ohne Korrelationsrechnung** getroffen wurde. Grundlage: eigene
Monats-/Wochenrenditen aus den SHA-verifizierten Trade-Rohdaten (virtuelle
Kurve je Signal, identische Konvention wie die DD-Nachrechnung), Skript
`portfolio_pruefung.py`, Vollmatrix `portfolio_korrelation.csv` (253 Paare).

## Methode

- Renditen: Monats-PnL / Balance am Monatsanfang der virtuellen Kurve (Start-
  basis = CSV-Einzahlungen bei MQL5, virtuelle 10.000 USD bei pelik). Pearson
  auf gemeinsamen Zeiträumen. Pearson ist skalierungsinvariant — bei pro Signal
  konstanter Basis ist Monatsrendite-Korrelation identisch zur PnL-Korrelation;
  die Nutzerwarnung („keine Renditekorrelation aus absoluten Trade-Gewinnen")
  betrifft Niveau-Effekte, die Pearson herausmittelt. Bei pelik ist die Basis
  virtuell (B3) — für Korrelationen unerheblich (Skaleninvarianz), für
  Renditehöhen relevant (siehe review.md B2).
- Keine Nullrenditen erfunden: Monate ohne Trades fehlen im Datensatz und
  werden aus der Schnittmenze ausgeschlossen (n sinkt entsprechend).
- Überlappung: stundenweiser Sweep der offenen Intervalle (Open→Close) über
  den gemeinsamen Zeitraum des Trios.

## Ergebnisse

### Empfehlungs-Trio des Portfolio-Berichts (Gold Spike 40 % / Lexo 30 % / PentagonForex 30 %)

| Paar | r Monatsrenditen | r Wochenrenditen | gemeinsame Monate |
|---|---|---|---|
| Gold Spike × Lexo | **+0,043** | +0,075 | 11 (2025-11–2026-09) |
| Gold Spike × PentagonForex | **+0,033** | +0,137 | 11 |
| Lexo × PentagonForex | **−0,201** | −0,121 | 11 (22 für die paarweise Schnittmenge) |

**Stunde der gemeinsamen offenen Positionen:** 3,8 % (301 von 7.868 Stunden)
mit allen drei Signalen gleichzeitig offen.

**Verlustmonat-Cluster (alle 23 🟢/🟡):** Juli 2026 ist der einzige
Community-Verlustmonat — er trifft 7 der 23 Signale, darunter beide
Gold-Grids (Gold Spike, SafeGold), Pure Gold 2000, Precise Pair, Grid King,
AccurateCopier, Gold Reaper. Von den **drei Empfohlenen ist nur Gold Spike
betroffen — mit −1,82 %** (Lexo +5,72 %, PentagonForex +1,45 %). Ein
gleichzeitiger Verlust des Trios ist im Juli 2026 also **nicht eingetreten**;
die Juli-Zahlen stützen die Empfehlung. Der Befund B20 ist damit nicht
„schwaches Trio", sondern die **Stichprobenlücke**: Juli 2026 ist ein
Ausbruchsmonat des *Sortiments* (Precise Pair −106,6 %, Gold Reaper −7,0 %),
und solche Monate sind in den **11 Monaten** Portfoliohistorie des Trios
nicht repräsentiert enthalten. (Lexo/Pentagon-Verlustmonate liegen früher und
fallen nicht mit Gold-Spike-Verlusten zusammen.)

**Historie-Tiefe:** Gold Spike hat **11**, Lexo 39, PentagonForex 22 Monate
— das **gemeinsame** Beobachtungsfenster des Trios ist daher **11 Monate
(2025-11 bis 2026-09)**, exakt das Fenster, in dem die Korrelationen oben
gemessen wurden. Über alle 23 🟢/🟡 streut die Tiefe von **3 bis 46 Monaten**.
Das Portfolio nennt keine dieser Zahlen — obwohl sie die Belastbarkeit der
Diversifikationsaussage bestimmt.

### Validierung der KI-Aussortierungen (Beleg, dass die KI-Urteile zahlenmäßig stimmen)

| Aussage des Portfolio-Berichts | Unabhängige Messung | Urteil |
|---|---|---|
| SafeGold „dupliziert Gold Spike in Asset, Strategietyp, Session" | r(Gold Spike × SafeGold) = **+0,77** (n=11) | bestätigt |
| Lemonal aussortiert (M2 46,65 %) | M2-Wert 46,65 % aus DB; eigene DD-Kurve 2,37 %/437 USD — Diskrepanz reell (Basisfrage, review.md B3) | bestätigt (mit Basisvorbehalt) |
| „Asset-Klumpen: 11× XAUUSD" | Symbolmengen der Trade-Dateien: 11 Signale mit XAU-Bezug | bestätigt |
| „kein Reko-EQ-DD für die drei Positionen" | forensik-JSON: reko None bei allen dreien | bestätigt |

### Stabilität und Grenzen

- **Stichprobengröße:** 11 gemeinsame Monate. 95-%-Konfidenzintervall für
  r=0,04 bei n=11 ≈ [−0,57; +0,62] — „unkorreliert" ist damit NICHT bewiesen,
  sondern nur „nicht widersprochen". Bei n=46 Wochen engert sich das auf ca.
  ±0,28.
- **Hälften-Stabilität (Monate):** Gold Spike×Lexo +0,18→−0,10;
  Gold Spike×Pentagon −0,22→−0,46 (stabil negativ-ish); **Lexo×Pentagon
  −0,60→+0,83** — instabil, d. h. für dieses Paar ist jede Punktschätzung
  schlecht reproduzierbar (jeweils n=5/6).
- **Basis-Verzerrung:** pelik-Renditen auf virtueller 10k-Basis — für die
  Korrelation unschädlich (skaleninvariant), für die vermutete
  Copierer-Rendite nicht (review.md B2/B3).
- **Geschlossene PnL-Reihen ≠ Equity-Renditen:** Monatsrenditen aus
  realisierten Trades unterschätzen floating-getragene Strategien (EURUSD
  Night Scalper etc.); für das Trio ist dieser Effekt laut Portfolio-Bericht
  selbst benannt (Lexo „Verluste floatend getragen"? — dort zu Pentagon:
  Trendkern bis 148 Tage gegen den Kurs). Die Korrelation auf Close-Basis
  kann gemeinsame Floating-Stressphasen systematic unterschätzen — die
  Dreifach-Exposure-Messung (3,8 %) ist der Partial-Kompromiss, kein Ersatz.
- **Chronologisch getrennte Validierung** (Selektion auf Hälfte 1,
  Validierung auf Hälfte 2) ist bei 11 Monaten nicht aussagekräftig —
  ausdrücklich als Grenze benannt, nicht durchgeführt.
- **Kopierkosten/Slippage:** nicht Teil dieser Prüfung (Portfolio-Bericht
  nennt Copy-Test als nächsten Schritt — sinnvoll).

## Voller Portfolio-Korridor (Nachtrag 30.09. 16:30, alle 23 🟢/🟡)

Die Trio-Analyse oben beantwortet nur die Frage „sind die drei Empfohlenen
untereinander divers?" — das Projektziel ist aber ein *Portfolio aus allen
verfügbaren Kandidaten*. `portfolio_check.py` misst daher den **gesamten
Kandidatenraum** (23 🟢/🟡, 253 Paare, Pearson auf Monatsrenditen, n ≥ 6
gemeinsame Monate) plus Instrument-Überschneidung und Verlustmonat-Cluster.

### 1. Monatsrenditen-Statistik aller 23

| Signal | Ampel | Basis | Monate | Verlustmon. | Ø %/M | σ | min | max |
|---|---|---|---|---|---|---|---|---|
| Lexo | 🟢 | 10 000 | 39 | 0 | +3,44 | 3,94 | +0,13 | +16,78 |
| The Holy Grail | 🟡 | 10 000 | 46 | 3 | +14,03 | 19,08 | −41,40 | +63,63 |
| Lemonal | 🟢 | 10 000 | 9 | 0 | +11,27 | 5,29 | +3,16 | +21,24 |
| PentagonForex | 🟢 | 10 000 | 22 | 0 | +2,59 | 2,63 | +0,53 | +13,98 |
| gemslime | 🟡 | 10 000 | 9 | 0 | +0,90 | 0,90 | +0,01 | +2,72 |
| AccurateCopier | 🟢 | 10 000 | 3 | 1 | +2,83 | 2,60 | −0,47 | +5,88 |
| GOLD Tokyo Scalping | 🟡 | 10 000 | 7 | 1 | +1,49 | 1,32 | −0,23 | +4,26 |
| Master H4-2 | 🟡 | 10 000 | 11 | 1 | +0,11 | 0,94 | −2,73 | +0,96 |
| Master H4-1 | 🟡 | 10 000 | 21 | 5 | +0,27 | 0,51 | −1,03 | +1,00 |
| SafeGold | 🟢 | 10 000 | 12 | 2 | +0,47 | 0,62 | −1,10 | +1,43 |
| ImpulseNet | 🟡 | 10 000 | 12 | 0 | +0,45 | 0,26 | +0,17 | +0,96 |
| Grid King $1000 | 🟡 | 10 000 | 22 | 2 | +1,44 | 1,34 | −0,78 | +5,95 |
| MicroJump | 🟡 | 10 000 | 12 | 0 | +0,12 | 0,06 | +0,04 | +0,28 |
| TKG | 🟡 | 10 000 | 8 | 0 | +0,91 | 0,88 | 0,00 | +2,60 |
| HRC Algo | 🟡 | 10 000 | 11 | 1 | +2,71 | 1,55 | −0,17 | +5,63 |
| Mr_Profit_FX | 🟢 | 10 000 | 11 | 0 | +1,05 | 0,49 | +0,45 | +2,22 |
| Gold Reaper New V2 | 🟡 | 1 615 | 24 | 4 | +13,49 | 14,15 | −8,72 | +43,18 |
| Precise Pair Trading | 🟡 | 225 | 13 | 3 | +40,70 | 58,88 | −106,59 | +122,71 |
| GoldWave signal | 🟡 | 50 | 17 | 0 | +44,55 | 29,04 | +2,44 | +116,00 |
| Gold Spike | 🟢 | 3 116 | 11 | 1 | +8,40 | 5,03 | −1,82 | +16,45 |
| Combo Profile 2026 | 🟡 | 120 | 9 | 0 | +88,84 | 16,66 | +55,97 | +111,12 |
| Pure Gold 2000 Vantage | 🟡 | 10 000 | 7 | 1 | +40,39 | 31,37 | −2,86 | +84,57 |
| EURUSD Night Scalp | 🟡 | 2 000 | 9 | 0 | +13,27 | 4,27 | +5,19 | +20,84 |

**Auffällig:** vier Signale rechnen auf einer Basis **unter 400 USD** (GoldWave 50,
Combo Profile 120, Precise Pair 225, Gold Reaper 1 615). Ihre Prozentrenditen
(44 %, 89 %, 41 %, 13 %) sind rechnerisch korrekt, aber als
Copierer-Beurteilung irreführend — siehe `kapitalbasis_pruefung.md`.

### 2. Die stärksten Korrelations-Cluster (|r| hoch, im Trio nicht sichtbar)

| Paar | r | n |
|---|---|---|
| **TKG × gemslime** | **+0,99** | 7 |
| gemslime × Lemonal | +0,93 | 8 |
| TKG × Lemonal | +0,90 | 6 |
| MicroJump × Lemonal | +0,85 | 9 |
| MicroJump × gemslime | +0,85 | 9 |
| Master H4-2 × EURUSD Night Scalp | +0,83 | 6 |
| MicroJump / PentagonForex / Holy Grail × Lemonal | +0,85 / +0,79 / +0,79 | 9 |
| Grid King × Pure Gold 2000 | +0,78 | 7 |
| **Gold Reaper × Pure Gold 2000** | **+0,87** | 7 |
| Gold Reaper × Gold Spike | +0,78 | 11 |
| GOLD Tokyo Scalping × Gold Spike | +0,72 | 7 |
| Holy Grail × Mr_Profit_FX | +0,71 | 11 |
| SafeGold × Gold Spike | +0,70 | 11 |
| Gold Spike × Pure Gold 2000 | +0,69 | 7 |
| Lexo × Mr_Profit_FX | +0,68 | 11 |
| GoldWave × Gold Spike | +0,66 | 11 |

**Kernaussage:** Die FX-Grid-/Scalper-Gruppe (TKG, gemslime, Lemonal, MicroJump,
PentagonForex, Holy Grail) bildet **einen einzigen Klumpen** — 6 der 7 höchsten
gepaarten Korrelationen liegen *innerhalb* dieser Gruppe. Wer daraus 2–3 Signale
auswählt, hält faktisch **eine** Strategie, nicht mehrere. Das vom
Portfolio-Bericht empfohlene Trio (Gold Spike / Lexo / PentagonForex) liegt
per Definition außerhalb dieses Klumpens — die Empfehlung war also richtig,
aber sie hätte **nicht** aus der Sichtbarkeit dieses Klumpens im Prompt
getroffen werden können, weil der Prompt nur die drei Empfohlenen sieht.

### 3. Instrument-Überschneidung

| Paar | Gemeinsame Symbole |
|---|---|
| **Master H4-1 × Master H4-2** | **15** (AUDCHF, AUDJPY, AUDNZD, AUDUSD, CADJPY, EURAUD, …) |
| **The Holy Grail × Master H4-1** | **13** |
| Holy Grail × PentagonForex | 5 (EURAUD, EURUSD, GBPJPY, GBPUSD, USDJPY) |
| Holy Grail × AccurateCopier | 4 |
| Grid King × Holy Grail / × Master H4-1 | 3 / 3 (AUDCAD, AUDNZD, NZDCAD) |
| PentagonForex × Master H4-1 / × H4-2 | 3 / 3 |

Master H4-1 und H4-2 sind **nicht** zwei Signale, sondern ein gemeinsames
FX-Maschennetz (15 von 15 Symbolen identisch, r = +0,26) — die niedrige
Korrelation täuscht hier, weil die Größenordnungen der Positionen
unterschiedlich skaliert sind. Die reine Symbolidentität ist das härtere
Kriterium.

### 4. Verlustmonat-Cluster

| Monat | Anzahl Signale im Minus | Betroffene |
|---|---|---|
| 2026-05 | 3 | GOLD Tokyo Scalping, Master H4-1, SafeGold |
| **2026-07** | **7** | Precise Pair (−106,6 %), Gold Reaper (−7,0 %), Pure Gold 2000 (−2,9 %), **Gold Spike (−1,8 %)**, SafeGold (−1,1 %), AccurateCopier (−0,5 %), Grid King (−0,1 %) |

**Juli 2026 ist der Systemschock des Datensatzes:** 7 von 23 Kandid fallen
gleichzeitig — darunter **beide Gold-Strategien** (Gold Spike, SafeGold) und
**alle drei Hochvolumen-Grid-Signale**. Der Portfolio-Bericht nennt keinen
solchen Monat; er empfahl Gold Spike, ohne den Juli als Argument zu führen.
Für die Kapitalallokation heißt das: **eine Juli-2026-artige Konstellation kostet
ein Gold-lastiges Portfolio gleichzeitig**.

**Was der Juli für das Trio bedeutet — und was nicht.** Von den drei
Empfohlenen ist nur **Gold Spike** im Minus, mit **−1,82 %**; Lexo (+5,72 %)
und PentagonForex (+1,45 %) waren beide im Plus. Die befürchtete
„Trio-Katastrophe" ist **nicht eingetreten**, und die Juli-Zahlen stützen die
Empfehlung sogar. Die zwei Großen des Monats (Precise Pair −106,6 %,
Gold Reaper −7,0 %) gehören zu Kandidaten, die **nicht** empfohlen wurden.
Damit ist der eigentliche Befund eine **Stichprobenlücke, keine
Empfehlungs-Schwäche:** Juli 2026 war ein Ausbruchsmonat des Sortiments, und
ein solcher Monat ist in den **11 Monaten** Beobachtungsfenster, auf denen die
Diversifikationsaussage beruht, nicht repräsentiert enthalten. Die Aussage
„diversifiziert" ist damit nicht widerlegt — aber sie ist auch nicht gegen
Ausbruchsmonate geprüft, und genau das ist der offene Punkt (B20).

### 5. Was das für die Zielaussage heißt

| Aussage | Messung | Urteil |
|---|---|---|
| „Drei getrennte Märkte" (Trio) | r = 0,03 / 0,04 / −0,20; 3,8 % Dreifach-Overlap | vertretbar |
| „Im Juli 2026 kein gemeinsamer Verlust" | Gold Spike −1,82 %, Lexo +5,72 %, PentagonForex +1,45 % | **trifft zu** — aber Juli ist der *einzige* geprüfte Stressmonat; der härteste des Datensatzes (`Precise Pair` −106,6 %) ist **nicht** im Trio |
| „Portfolio aus 3–4 Kandidaten ist möglich" | ja, aber der Kandidatenraum zerfällt in ~5 Klumpen; Auswahl = Klumpenwahl | eingeschränkt |
| „Diversifikation ist der Grund für die Empfehlung" | **nicht im Prompt geprüft** — der Prompt sieht nur die 3 Empfohlenen, nicht die 23 | Lücke |
| „Gold Spike ist unkorreliert" | vs. Gold Reaper +0,78, GOLD Tokyo +0,72, SafeGold +0,70, Pure Gold +0,69 | **relativ** unkorreliert, nicht absolut |

**Konsequenz (Maßnahme #16 im Hauptbericht):** Die Korrelation muss ein
**Code-Befund** sein, der *vor* der LLM-Portfolio-Empfehlung über **alle**
🟢/🟡 berechnet wird. Nur so sieht die KI die Klumpen. Ein Vorschlag je Position
(„r > 0,5 zu X bereits gewählten Positionen → Warnung, Diversifikation
begrenzt") plus die Verlustmonat-Überlappung („3+ Signale im selben Verlustmonat
→ Klumpenrisiko") würde die Empfehlungslogik von „3 Namen sortieren" zu
„Klumpen abdecken" ändern. Dazu die **Historie-Tiefe je Position** (3 bis 46
Monate im Bestand, 11 Monate beim gemeinsamen Fenster des Trios) — ohne diese
Zahl liest der Nutzer „diversifiziert" als belastbarer, als die Daten es
hergeben.

## Fazit

Die Diversifikationsbehauptung des Portfolio-Berichts ist nach unabhängiger
Messung **im Punkt vertretbar**: alle drei Paare liegen in einem Bereich, den
man als „nicht positiv korreliert" lesen darf, die gemeinsame Exposure ist
klein, und der stärkste Community-Stressmonat wurde vom Trio mit −1,82 %
schadenfrei überstanden. **Bewiesen** ist „wenig korreliert" mit 11 Monaten
nicht — und gerade *das* ist der offene Punkt B20: die Aussage wurde nicht
gegen einen Ausbruchsmonat geprüft und behauptet das Gegenteil auch nicht,
sondern verschweigt die Beobachtungstiefe. Der Lauf hätte die Behauptung
nicht unbelegt stehen lassen dürfen: eine
engine-seitige Korrelationsberechnung aus den Monatsrenditen der 🟢/🟡
(verfügbar wie hier gezeigt) gehört als Code-Befund in den Portfolio-Prompt
(„Code rechnet, KI deutet"). Empfehlung: `portfolio_korrelation.csv` als
Prompt-Input; Schwellen |r| > 0,5 als Warnmarker (hätte SafeGold-Lumpen
automatisch gezeigt).
