# Workflow-Statistik und verbleibende Leerzellen · 10.10.2026

Die Bestandsprüfung las die Produktionsdatenbank ausschließlich mit SQLite `mode=ro`. Kennzahlen wurden aus vorhandenen CSVs rein lesend berechnet. [Einzelbelege und ursprünglicher Vergleich](workflow_metrics_2026-10-10.json) bleiben erhalten; die gezielte ATong-Nachmessung steht dort separat.

Die Seite teilt Quellenkatalog, Registry und Artefaktindex jetzt als Bulk-Snapshots. Frische Workflow-Kennzahlen benötigen dieselbe Quelle, Version, Plattform und tatsächlich SHA-geprüfte Tradebytes wie der Workflow-Snapshot; auch Metricsbytes und gegebenenfalls Payload-ID/Version müssen passen. Echte persistierte Initialbasis bleibt maßgeblich, gültige Quelleninitialbasis ergänzt ausschließlich `None`; CSV-Einzahlungen gewinnen weiterhin. Katalogmetadaten dürfen für dieselbe Identität aktuell sein. Eine abweichende Exportversion wird nicht still untergeschoben; Ampel und gespeicherte Studien werden nicht verändert.

Im aktuellen Bestand von **194 Workflow-Signalen** schloss dieser Datenflussfix allein keine numerische Leerzelle und änderte keine Kapitalbasis. Drei Abonnentenwerte wurden aktuell: WanChaiTrendFX 1121175: 1→2; HarbourFXPrime 1121200: 43→50; Lenore 1010186: 82→83. Keine Basis-Neuberechnung war dadurch erforderlich.

| Kennzahl | Leer vorher | Nach Bulk-Zuweisung | Nach gezieltem TWR-Fix |
|---|---:|---:|---:|
| Geom. %/M | 30 | 30 | 29 |
| RetDD/Monat | 76 | 76 | 76 |
| PF | 25 | 25 | 25 |
| Win % | 24 | 24 | 24 |
| Trades | 20 | 20 | 20 |
| Wochen | 8 | 8 | 8 |
| Abonnenten | 5 | 5 | 5 |

**Belegter Rechenfehler ATong 2327790:** Die Vollauszahlung von 1.500,05 USD am 06.09.2022 hinterließ durch Float-Arithmetik −2,7×10⁻¹¹ USD. Das wurde als echtes negatives Konto behandelt und verwarf die TWR-Reihe. `math.fsum` und ein kumuliertes ULP-Budget der tatsächlichen Beträge neutralisieren jetzt ausschließlich Maschinenrundungsreste. Positive CSV-Basis 2.000,10 USD und 81 Flows bleiben unverändert. Nachmessung: **7,6448145134 %/Monat**, CAGR 142,0568431157 %. Echte negative Restbeträge −0,001/−0,01 USD sowie PnL auf einem leeren Konto bleiben gesperrt.

Die übrigen 29 Geom-Lücken: 20 fehlende Dateien; vier Zulu-Parserblocker; vier nichtpositive Endkapitalwerte (Master Hong 504191, Rohan 178177, FinancialFreedomFX 21411352, FOMOx99 776728); SEA 1496203 ohne positive Startbasis. SEA hat vor dem ersten Trade 500 USD Einzahlungen minus 1.000 USD Auszahlung = −500 USD; Initial Deposit −461,33 USD liefert ebenfalls keine belastbare positive Basis. Diese N/A-Werte dürfen nicht aufgefüllt werden.

Die vier Zulu-Blocker sind in vorhandenen Snapshots belegt: TpTrading 430016 und Zix Power 425666 schließen vor dem Open; Money Pile 426987 enthält negative Dauer von ein/zwei Sekunden; Signal Guide 304366 enthält eine Nullvolumen-/Nullgeldzeile. Der Quellenvergleich bestätigt zwölf falsche Zeitpaare auch anhand der UTC-Epochwerte der öffentlichen API, siehe [Zulu-Quellbeleg](zulu_zeit_quellfehler_2026-10-10.json). Keine Zeitkorrektur ist belegt. Signal Guide hat inzwischen einen neueren verifizierten Export ohne alte Nullzeile; Root übernimmt dessen Nachimport.

**Zusätzlicher allgemeiner Finanzlesemodus:** Der normale Parser bleibt strikt. Ausschließlich die UI-Teilstatistik darf finanziell valide Zeilen mit negativem Zeitintervall unverändert lesen. Alle PnL bleiben enthalten; PF, Winrate, Trades und realisiertes Netto sind unabhängig von der Haltedauer. Volumen ≤0, nichtendliche Geldwerte und kaputte Zeitstempel bleiben Fehler. Geom/CAGR, DD, RetDD, Kurve und Haltedauer werden nicht freigegeben; die Tabelle unterdrückt auch etwaige alte Equity-Studienwerte für solche Teilstatistiken und zeigt eine ausdrückliche Warnung.

| ID | Signal | Trades vorher→nachher | PF vorher→nachher | Win vorher→nachher | Netto USD | Zeitfehler |
|---|---|---:|---:|---:|---:|---:|
| 425666 | Zix Power | 0→4000 | leer→1,04 | leer→64,7 % | 1.053,68 | 5 |
| 426987 | Money Pile | 0→6431 | leer→1,77 | leer→77,0 % | 10.592,07 | 6 |
| 430016 | TpTrading | 0→4091 | leer→1,38 | leer→66,4 % | 22.553,75 | 1 |

Diese gezielte RO-Nachmessung füllt sechs leere Zellen und korrigiert drei zuvor fehlerbedingt angezeigte Tradezahlen. Zusammen mit ATong sind das sieben neu gefüllte numerische Zellen und drei korrigierte Tradezahlen, ohne Signal-Guide-Nachimport mitzuzählen. Daraus folgen für denselben Ausgangsbestand PF22 und Win21 verbleibende Leerzellen; Geom29, RetDD76 und Trades20 fehlende Dateien bleiben unverändert.

PF fehlt neben 20 Dateien und vier Parserblockern bei EURUSD Night Scalper AI 2379236 korrekt: kein Verlust, daher Nenner null. Ohne positive gemessene Equity-DD bleibt RetDD unbekannt. Die Spaltenhilfen erklären diese Unterschiede. Persistenter Streamlit-Statistikcache erhält eine neue Rechenversion, damit die korrigierte ATong-Rechnung beim Neuladen sichtbar wird.

**Retry-Ursache und Fix:** Der erste Versuch einer frischen Datenbank scheiterte beim lesenden Broker-Fallback mit `no such table: signals`, bevor überhaupt ein CSV-Abruf stattfand. Erst die Fehlerpersistenz legte das Schema an; damit blieb für den eigentlichen BAD→GOOD-Download nur ein Versuch übrig. `analyze_candidate` initialisiert jetzt das Schema vor dem ersten Versuch. Der neue hermetische Test bestätigt, dass ausschließlich die temporäre DB benutzt wird und beide gemockten Abrufe stattfinden; Parser und Exportvalidierung bleiben strikt. Neuer Test plus bestehende Retry-/Ingestion-Suite: **16 Tests bestanden**.

**Historienhinweise vollständig durchgereicht:** `TradesTruncated`, `TradesTotalAvailable`, `TradesStored` und `CompletenessNote` wandern von Quellenmetrics über Statistik und Workflow-Persistenz in den Messstatus und die Detailwarnung. Der Hinweis nennt gespeicherte/insgesamt verfügbare Trades und erklärt, dass Kennzahlen auf dem gelieferten Export beruhen. Auch ein Quellenhinweis ohne gesetztes Truncated-Flag bleibt sichtbar. Keine zusätzlichen Schranken und keine Scoringänderung.

Gezielte Prüfung vor diesen Folgefixes: **107 Tests bestanden** (Katalog, Kapitalbasis, TWR, Signalstatistik, Finanzteilstatistik, Portfolio sowie Seiten-/Performance-Tests). Zahlen werden wegen Überschneidung nicht addiert. Abschließende Folgeprüfung läuft beim Root-Gesamtlauf. `git diff --check` ohne Fehler, lediglich CRLF-Hinweise.
