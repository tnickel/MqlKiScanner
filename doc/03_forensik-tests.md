# Forensik-Test-Batterie (Pflicht vor jedem positiven Urteil)

Diese Tests sind das Herzstück des Tools. Sie entstanden aus der
Analyse-Reihe und haben dort u. a. ein verstecktes Martingale (FXtrading,
EURNZD-Korb), einen versteckten Grid-Sleeve (KiraCat/NZDCAD) und ein
hohes Exposure-Risiko (Pure Gold 2000) aufgedeckt, das die
Plattform-Kennzahlen verschwiegen.

**Regel:** Ein Kandidat bekommt keine positive Einstufung, bevor alle
vier Tests läuft und die Ergebnisse im Befund auftauchen — auch dann
nicht, wenn die Plattform-Kennzahlen gut aussehen.

---

## Test 1: Martingale-Signatur

**Frage:** Werden Positionen nach Verlusten größer?

```
Trades zuerst nach normalisiertem Instrument gruppieren.
Für jede Nachbarsequenz je Instrument (Trade i, Trade i+1), wobei i+1 nach dem
Close von i eröffnet wird:
  ratio = vol(i+1) / max(vol(i), 1e-9)
Gruppiere ratio nach: Trade i war Verlust (pnl <= 0) vs. Gewinn
Berichte: Median und Mittel je Gruppe
```

**Interpretation:**
- Median nach Verlust > 1,3x → **Martingale-Flag** (echtes Martingale: ~2x)
- Median nach Verlust <= 1,0x → keine Martingale-Eskalation
  (Beispiel Pure Gold 2000: 0,92x nach Verlust gegen 1,00x nach Gewinn)
- **Achtung:** Nur nicht-überlappende Nachfolger werten; Lots variieren
  bei balance-adaptiven Systemen ohnehin — der Median entscheidet

**Referenz:** `scripts/reference/martingale_exposure_test.py` (Test 1)

Dieser Kanal prüft die unmittelbar benachbarten Einstiege je Instrument.
Ein während der Haltedauer eröffneter Zwischentrade wird nicht übersprungen,
um den älteren Trade nachträglich mit einem beliebigen späteren Einstieg
zu paaren. Das ist die spezifizierte Grenze des Nachfolgertests, kein
Nachweis dafür, dass ein überlappendes System generell frei von Martingale
ist. Der separate Korbleiter-Test ergänzt diesen Kanal.

## Test 2: Peak-Exposure (gleichzeitige Positionen)

**Frage:** Wie groß ist die maximale aggregierte Marktposition zu einem
beliebigen Zeitpunkt — und was kostet ein Schock?

```
Events: (open_time, +vol, Richtung) und (close_time, -vol, Richtung)
Sortiere nach Zeit, kumuliere:
  offene Positionen (Anzahl), aggregiertes Volumen je Symbol, Long/Short
Zwei Peak-Masse:
  - peak_open_positions = Maximum der offenen Positions*anzahl*
  - shock_usd / peak_net_* = am Zeitpunkt des maximalen Dollar-Schocks
    (Volumen-Peak; Schock je Symbol mit eigenem Kontraktfaktor, Summe —
    kein Lot-Netting über Instrumente als Hedge)
```

**Dollar-Rechnung (zwingend angeben):**

| Symbol | Risiko je 1 USD/EUR Bewegung je Lot |
|---|---|
| XAUUSD | 100 USD |
| US30 / US100 / US500 (Projektkonvention, inklusive Aliase) | 1 USD je Punkt |
| FX-Majors | ~10 USD je Pip (4. Dezimale) |

Die FX-Angabe gilt nur bei USD als Kurswährung. Bei JPY als Kurswährung
ist ein Pip 0,01, sonst 0,0001; das Standardszenario umfasst jeweils
500 Pips (JPY: 5,00 Preiseinheiten). Bei anderen Kurswährungen ist eine
belegte historische Umrechnung nach USD erforderlich. Ohne diese bleiben
USD-Schock und Schockanteil unbekannt, die Forensik unvollständig. Die
nativen Beträge je Symbol werden mit ihrer Kurswährung ausgegeben; sie
dürfen nicht als USD addiert oder aus späteren Tradegewinnen umgerechnet
werden. Das Projekt verwendet weiterhin die explizite USD-Konvention für
Kontostände sowie bekannte Gold-/US-Indexkontrakte; eine CSV allein beweist
die Kontowährung nicht.

Andere Indexnamen, etwa JP225, GER40, UK100 oder CHINA50, belegen weder
Kontraktgröße noch Punktwert oder Gewinnwährung. Diese Merkmale bestimmt
die [Brokerspezifikation des Symbols](https://www.metatrader5.com/en/terminal/help/trading/market_watch#specification).
Ohne solche Daten bleiben auch native Schockbeträge unbekannt; insbesondere
wird weder pauschal 1 USD noch 1 JPY/EUR je Punkt unterstellt. Die Engine
meldet `contract_complete=False`, `missing_contract_symbols` und eine
konkrete Warnung; die Bewertung bleibt unvollständig. Die Erkennung als
Index für andere Analysen bleibt davon unabhängig.

**Umsetzung seit 09/2026 (belegte statt fehlende Werte):**

- Brokerspezifikationen können in `data/contract_specs.json` hinterlegt
  werden (Quelle mit Abrufdatum je Eintrag, Stand: Tickmill; siehe
  doc/02 Abschnitt 5a). Einträge mit `cross_broker=false` — bekanntester
  Fall Öl: Tickmill 1 Barrel je Lot, andere Broker 100 — gelten nur bei
  Übereinstimmung mit dem `broker_server` des Signals; andernfalls
  verweigert die Engine mit konkreter Anleitung statt still zu rechnen.
- Die "belegte historische Umrechnung nach USD" ist realisiert: EZB-
  Referenzkurse (`fx_rates.py`, doc/02 Abschnitt 5b) je Handelstag, mit
  Kursdatum je Symbol im Befund (`fx_conversion`). Fremdwaehrungs-Symbole
  sind damit voll bewertbar; fehlt ein Kurs (offline, Kalenderlücke,
  vor 1999), bleibt die alte ehrliche Sperre mit konkretem Grund.

Der historische Schockanteil verwendet das zum jeweiligen Zeitpunkt
vorhandene Kapital. Kontobewegungen mit identischem Zeitstempel werden
als ein Nettofluss verarbeitet, weil ihre Reihenfolge innerhalb der
Zeitauflösung nicht bekannt ist. Neben dem USD-Maximum wird ein separates
Maximum des relativen Schocks mit Zeitpunkt und damaligem Kontostand
ausgegeben.

**Interpretation:**
- Beispiegelrechnung angeben: "50-USD-Schock = ±X USD" und ins
  Verhältnis zum Kontostand setzen
- Rote Flagge: Schockszenario > 30 % des Kontos
  (Beispiel Pure Gold 2000: 32 SELL-Positionen, 2,66 Lots netto,
  50-USD-Schock = -13.300 USD auf 10-30k-Konto)

**Referenz:** `scripts/reference/martingale_exposure_test.py` (Test 4)

## Test 3: SL-Clustering (Stop-Nachweis)

**Frage:** Gibt es Beweise für mechanische Stop-Losses?

**Drei Evidenzstufen (von stark zu schwach):**

1. **Orderbuch-Direktnachweis** (nur mit History-CSV inkl. S/L-Spalte):
   Jede Position mit SL? Exit-Kommentare `[sl]`/`[tp]`? Anteil der
   Stop-Auslösungen im Plus (Trailing-Nachweis)?
   (Referenzbeispiel: Gold Spike — 368/368 mit SL/TP, 161 von 186
   Stop-Exits im Plus)

   Explizite `[sl]`-/`[tp]`-Marker werden ohne Unterscheidung der
   Groß-/Kleinschreibung erkannt, auch mit einer angehängten Ticketnummer
   (z. B. `[SL] #123`). Bloße Erwähnungen in Freitext sind kein Exit-Beleg.
   Fehlende Einstiegspreise in MT4-Handelszeilen weist bereits der Parser
   als fehlendes Pflichtfeld zurück; dafür werden keine Ersatzpreise
   erfunden.
2. **Positions-Export:** Verlustdistanz je Verlusttrade berechnen:
   `(ep - xp) * (+1 Buy | -1 Sell)`. Ballen sich die Distanzen an einem
   festen Niveau (Top-Distanz deutlich dominant, z. B. alle ~20 USD)?
   → Stop-Signatur. Streuen sie über Faktor 30+ ohne Niveau? → kein Stop.
3. **Ribbon-Statistik:** Verlustserie (max. Länge, Summe) und
   schlechtester Einzeltrade ins Verhältnis zum Kontostand setzen.

**Interpretation (Nutzer-Regel 28.09.2026):**
- Fester Stop belegt → Risiko mechanisch gedeckelt (gut; bleibt Score-
  Entlastung −1,0 Struktur-Punkte)
- Kein Cluster + große Einzeldistanzen → Hinweis, dass Verluste frei laufen
  — aber **neutral, kein Nachteil**: Die meisten Broker übertragen keinen
  SL in den Exporten. Ob ein impliziter Stop plausibel ist (Cluster-
  Tendenzen, konsistente Cut-Offs, Haltedauer bei Verlusten) schätzt die
  KI-Analyse ab; nur eine dort begründete Einschätzung „wahrscheinlich ohne
  Stop-Schutz" darf negativ werten. Beispiele für freilaufende Verluste
  bleiben Fallnotizen (MSC -21 USD-Kappe ohne Level, Pure Gold Worst -152
  USD Bewegung, KiraCat -7 % in einem Trade).

Die Engine liefert formatunabhängig `stop_evidence`: `direct` (alle
Positionen mit SL), `cluster` (ausreichende Distanzsignatur), `partial`
oder `none`. Leere Orderbuchfelder oder fehlende Schlüssel liefern keine
Entlastung im Score — aber auch keine Abwertung. Ein Take-Profit ist für
den SL-Nachweis nicht nötig.

**Fehlender SL-Nachweis ist NEUTRAL**: kein Malus im Risiko-Score (die
Struktur-Dimension bleibt bei der Basis 3,0; nur `direct` senkt auf 2,0),
keine Kandidaten-Sperre, in der Ampel-Matrix eine weiße Zelle
(„neutral (nicht übertragen)”). Kandidat entscheidet sich allein über
Drawdown-Schranke, Score und Ertrag; das Urteil nennt den Stop-Kontext
nur informativ („Stop bewiesen” / „teilweise belegt” / „SL nicht
übertragen (neutral — KI schätzt ab)”). Eine vollständige Analyse ohne
Stop-Nachweis bleibt eine vollständige Analyse; sie wird deshalb nicht
erneut heruntergeladen. Drawdown- und Martingale-Ablehnungen haben
weiterhin Vorrang. Der Status wird durch Scan, Datenbank, Laufarchiv und
KI-Payload durchgereicht; Freitext gilt nicht als Ersatznachweis.
Bewertungsstand 7 verlangt für ältere Live-Befunde eine erneute Prüfung;
Archive bleiben historische Momentaufnahmen.

Beim Verlustdistanz-Clustering gilt für gleich häufige gerundete Niveaus
deterministisch das kleinere Niveau. Eine gleich starke Nullklasse verhindert
damit einen positiven Stop-Nachweis; die Reihenfolge der CSV-Zeilen darf keine
Entlastung erzeugen. Bestehende Mindesthäufigkeiten und Evidenzschwellen bleiben
unverändert. Auch die Auswahl eines repräsentativen Symbols bei Gleichstand
ist unabhängig von der CSV-Reihenfolge.

**Referenz:** `scripts/reference/analyze_goldspike_orderbook.py` (Stufe 1),
`analyze_goldreaper.py` / `analyze_kiracat.py` (Stufe 2)

## Test 4: Drawdown-Rekonstruktion + Konsistenzprüfung

**Frage:** Stimmen die Daten, und wie tief war der echte Drawdown?

```
Trades chronologisch nach Close-Zeit; Startkapital = Nettosumme aller
Kontobewegungen bis zum ersten Einstieg (Einzahlungen minus bereits
erfolgte Auszahlungen). Vor Handelsbeginn entnommenes Kapital steht für
die Handelskurve nicht zur Verfügung.
Kontobewegungen (Balance-Zeilen) an ihren Zeitpunkten einrechnen;
zusätzlich eine "virtuelle" Kurve OHNE Ein-/Auszahlungen fahren
(zeigt die Handelsleistung separat von der Kapitalentnahme).
Peak-Tracking; max. (peak - balance), absolute und prozentual.
```

Die unterstützten CSV-Header werden vollständig einschließlich ihrer
Spaltenreihenfolge geprüft. Unbekannte Anordnungen werden abgewiesen,
damit beispielsweise Take-Profit-Werte nicht als Stop-Loss gelten können.

Bei identischen Zeitstempeln werden realisierte Nettoergebnisse gemeinsam
gebucht. Die Sekundenauflösung belegt keine Reihenfolge innerhalb derselben
Sekunde; aus der CSV-Zeilenfolge werden daher keine Zwischenhochs oder
Zwischentiefs konstruiert. Die Balancekurve fasst Kontobewegungen und
Abschlüsse desselben Zeitpunkts zusammen; die Tradingkurve berücksichtigt
weiterhin nur Handelsresultate nach dem Startkapital.

Für Exposure gilt am gleichen Zeitpunkt die Reihenfolge: gemeinsame
Kontobewegungen, alle Einstiege, alle Abschlüsse samt Nettoergebnis.
Damit kann ein erst gleichzeitig realisierter Gewinn keine neuen Positionen
vorfinanzieren. Einstiege und Abschlüsse werden jeweils als Gruppe bewertet.
Das ist eine dokumentierte Rekonstruktion in Sekundenauflösung; tatsächliche
untersekündliche Risiko- und Kapitalspitzen bleiben aus diesen Daten unbekannt.

**Konsistenzprüfung (Pflicht):**
- Monatsnetto aus CSV gegen die Monats-Tabelle der Plattform
- Rekonstruierter Balance-DD gegen den Plattformwert "By Balance:"
- Deckung auf den Cent = Datenintegrität bestätigt
  (galt in allen Analysen der Reihe: MSC 76,83 USD, Reaper 319,49 USD,
  Gold Spike 157,20 USD, KiraCat 2.117,70 USD — exakt)

**Abweichung** = rote Flagge (Datenmanipulation oder unvollständiger Export).

**Referenz:** alle `analyze_*.py` in `scripts/reference/`

---

## Weitere bewährte Analysen (Soll, nicht Muss)

- **Basket-Cluster:** Trades mit identischem Close-Zeitpunkt gruppieren
  (>=2 = Basket-Exit). Anteil der Trades in Körben = Grid-Indikator.
  Körbe auf Richtung und Lot-Staffelung prüfen (Averaging? Pyramiding?)
- **Lot-Verteilung:** Bandbreite 0,01-0,73 = diskretionär/adaptive Größe;
  361/363 bei 0,01 = flach (positiv)
- **News-Korrelation:** FOMC-Termine vs. Handeltage (Filter nachweisbar?
  Beispiele: MSC handelte 0 von 14 FOMC-Tagen, Gold Spike 5 von 6)
- **Stundenprofil:** Einstiege je Serverstunde (Zeitfenster-Systeme
  erkennbar; NY-Session-Dominanz)
- **Monats-Kurve:** negative Monate zählen; Regime-Abhängigkeit
  (Ausbruchssysteme: flache Monate normal)
- **Kosten:** Commission + Swap vs. Bruttogewinn (über 10 % = Spread-Problem)

## Scoring-Vorschlag (aus der Reihe, im Tool abbilden)

Dimensionen je 1-10 (hoch = riskant), gewichtet zum Gesamt-Score:
Drawdown-Historie, Strukturrisiko (SL? Grid? Martingale?), Margin-Disziplin,
Transparenz, Track-Record-Länge, Copy-/Slippage-Risiko, Broker-Umgebung.
Kalibrierung aus der Reihe: Gold Spike 4,0 / Gold Reaper 4,4 / KiraCat 4,7 /
MSC 5,6 / FXtrading 5,7 / World PEACE 8,0.


## 5. Equity-DD-Rekonstruktion aus Kursdaten (28.09.2026, Nutzer-Wunsch)

Der Broker-„By Equity"-DD ist eine Selbstauskunft. Diese Pruefung misst
virtuelle Trading-Equity: Auf einem H1-Raster wird Equity = Startkapital + realisiert + floating
(Bar-Close je Symbol, FX-Kreuze über EZB-Kurse nach USD) geführt; der
maximale Rückfall ist der Reko-EQ-DD. H1-Close wird am BAR-ENDE ausgewertet;
Open/Close-Ereignisse behalten ihre Sekunden. Das realisierte Netto umfasst
ALLE Export-Trades, auch ohne Kurse; ihre fehlende Floating-Basis ergibt
Luecken. Spaetere Einzahlungen/Entnahmen sind in dieser virtuellen Kurve
nicht enthalten. Ein Vergleich mit Konto-Equity erfordert dieselbe Basis
und denselben Zeitraum. H1-Daten erfassen keine Intrabar-Extrema; aktuell
offene Positionen fehlen im Historien-Export. Datenabdeckung allein
belegt daher keinen tickgenauen maximalen Broker-DD (KiraCat-Pruefung 03.10.).

- **Auto-GMT:** Trade-Zeiten sind Signal-Broker-Zeit, Kurse Terminal-Zeit.
  Der Shift wird per Preisabgleich ermittelt (Open/Close in High-Low-Spanne
  der getroffenen H1-Bar; ±14 h Kandidaten, ≥ 60 % Treffer). Treffen
  MEHRERE Offsets gleich gut (Plateau — bei breiten Bändern + Preis-
  toleranz normal), ist der Versatz nicht bestimmbar → ehrlicher Skip
  (Review 29.09.: der frühere Tie-Break „kleines |Shift|" verzerrte
  systematisch Richtung 0 und meldete zugleich 100 % Erkennung).
- **Schranke:** Fließt nur bei Abdeckung ≥ 95 % der offenen H1-Punkte, ohne
  EZB-Kurslücke UND nur wenn ALLE Trades nutzbar sind (Symbole ohne
  Kurse oder ohne belegten Kontrakt — kein erfundener Faktor — machen
  das Ergebnis unzuverlässig) als viertes Maximum in die 30-%-Drawdown-
  Schranke ein; sonst informativ (Status unvollständig, kein Schranken-Wert).
- **Kapitalbasis:** Ohne Startkapital (≤ 0) entfällt die Prüfung — ein
  Prozentwert ohne Bezugsbasis wäre bedeutungslos (früher „0 % DD,
  verlässlich").
- **Still ohne Terminal:** Ohne laufendes MT5-Terminal (und ohne
  markt_start_erlauben) entfällt die Prüfung kommentarlos — kein Malus.
- Setting: `equity_rekonstruktion` (Default an). Terminal-Lebenszyklus wie
  beim Markt-Beobachter (portabler Selbststart, Beenden nach dem Lauf).
- Urteil nennt „Reko-EQ-DD X % (aus Kursen, GMT +N h)"; KI-Forensik-JSON
  enthält equity_dd_rekonstruiert_pct.

### LLM-Auswertung des Reko-EQ-DD (28.09.2026, gleicher Tag nachgerüstet)

Alle drei Prompt-Vorlagen (config/prompts/) deuten den Wert gezielt:

- **risiko_analyse.md** (Prompt 2): Punkt 1a — Vergleich gemeldeter DD vs.
  Trading-DD vs. `equity_dd_rekonstruiert_pct`; Vergleiche nur bei gleicher
  Kapitalbasis, gleichem Zeitraum und belegter Datenabdeckung. Ein hoeherer
  Reko-Wert allein belegt keine beschoenigte Meldung. Methodik und
  Abweichung mit beiden Zahlen nennen (Korrektur 03.10.2026).
- **gesamtbericht.md** (Prompt 3): Drawdown-Dreiklang; Reko über Schranke =
  hartes Ablehnungskriterium.
- **portfolio.md**: DD-Arten im Portfolioteil genannt.
- **Kriterien-Text** (pipeline._kriterien_text): erklärt das Fünffach-Maximum
  der Schranke (EQ/Bal/Trading/Reko/Monitor, s. u.) — die KI kennt die
  Engine-Regel.
- **scoring.evaluate**: `reko_eq_dd_pct` als viertes Maximum (auch bei
  eq_dd_caveat); Pipeline reicht ihn nur bei verlässlicher Rekonstruktion durch.

### Schranke, Ertrags-Basis und Kapitalbasis (30.09.2026, Intensiv-Review B1–B3)

Drei Regeländerungen aus dem End-to-End-Review des Ziellaufs
2026-09-30 (doc/reviews/intensivreview_2026-09-29/):

1. **Monitor-EQ-DD als fünftes Schranken-Maximum (B1).** Der Datenquellen-
   Monitor (Pelican etc.) misst einen floating-inclusiven Max-EQ-DD aus der
   vollen Trade-Kurve (`monitor_trade_eq_dd_pct`). Seit 30.09. gehört er in
   `scoring.dd_maximum` — an allen drei Stellen synchron (evaluate,
   dimension_inputs, refresh_report_verdict) und in der Ampel-Zelle
   dd_schranke. Grund: Bei Quellen-Signalen wurde die Kursdaten-Reko bei
   vorhandenem Monitorwert geskippt UND der Monitorwert nicht in die Schranke
   genommen — die floating-Schranke war für diese Signale wirkungslos
   (Ziellauf: Lemonal 🟢 bei 46,65 % Zweitmessung). Vorbehalt: Der Monitor
   rechnet gegen seine eigene (ggf. rückgerechnete) Basis — Werte über
   100 % überzeichnen absolut (Kennzeichnung im Zellen-Text), bleiben aber
   harte Warnmarker in Schranken-Richtung.
2. **Ertrag/Monat auf der Forensik-Basis (B2).** Neu berechnet:
   `ertrag_monat_pct_forensik` = Σ Trade-Netto / Startkapital / Monate aus
   der EIGENEN Kurve — dieselbe Basis, gegen die DD und Schock gerechnet
   werden. Dieses Kriterium ist maßgeblich für die Ertrags-Zelle und den
   Grün-Weg; der Plattformwert (`ertrag_monat_pct`, fremde Kapitalbasis)
   bleibt als gekennzeichnete Selbstauskunft daneben.
3. **Implizite Kapitalbasis vor der virtuellen Annahme (B3).** Ohne echtes
   Initial Deposit ist die erste Wahl jetzt Web-Balance − Σ Trade-Netto
   (`KAPITALBASIS_QUELLE_IMPLIZIT`, Urteil: „Kapitalbasis implizit");
   die starre 10.000-USD-Annahme (`virtuelle_annahme`) ist nur noch letzter
   Fallback. Der Cent-Abgleich überspringt die implizite Basis (sie ist per
   Konstruktion aus der Balance abgeleitet — der Abgleich wäre tautologisch).
