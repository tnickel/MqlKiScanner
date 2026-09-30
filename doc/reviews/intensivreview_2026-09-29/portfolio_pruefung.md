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
AccurateCopier, Gold Reaper. **Kein Trio-Mitglied hatte im Juli 2026 einen
Verlustmonat** — der stärkste gemeinsame Stresstest im Datenfenster wurde
unvercorreliert überstanden. (Lexo/Pentagon-Verlustmonate liegen früher und
fallen nicht mit Gold-Spike-Verlusten zusammen.)

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

## Fazit

Die Diversifikationsbehauptung des Portfolio-Berichts ist nach unabhängiger
Messung **im Punkt vertretbar**: alle drei Paare liegen in einem Bereich, den
man als „nicht positiv korreliert" lesen darf, die gemeinsame Exposure ist
klein, und der einzige Community-Stressmonat wurde ohne gemeinsamen Verlust
überstanden. **Bewiesen** ist „wenig korreliert" mit 11 Monaten nicht — und
der Lauf hätte die Behauptung nicht unbelegt stehen lassen dürfen: eine
engine-seitige Korrelationsberechnung aus den Monatsrenditen der 🟢/🟡
(verfügbar wie hier gezeigt) gehört als Code-Befund in den Portfolio-Prompt
(„Code rechnet, KI deutet"). Empfehlung: `portfolio_korrelation.csv` als
Prompt-Input; Schwellen |r| > 0,5 als Warnmarker (hätte SafeGold-Lumpen
automatisch gezeigt).
