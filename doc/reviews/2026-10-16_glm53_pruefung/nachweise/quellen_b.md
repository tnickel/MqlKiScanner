# GLM5.3-Prüfung: RoboForex, Zulu und Pelican – 16.10.2026

Der angehängte Bericht beschreibt überwiegend ältere Stände. Seine zentrale Freeze-Aussage ist für die hier geprüften aktuellen Scanner-Updatepfade nicht mehr zutreffend. Bei Robo blieb allerdings ein konkreter Folgefehler: frische Historien wurden mit einem übersprungenen, alten Ratingstand erneut in Prozent-DD umgerechnet. Zusätzlich wurde ein eigenständiger MT4-Zeitachsenfehler bestätigt. Beide sind behoben und durch Regressionen abgesichert.

## Umfang und belegter Stand

Auftrag: kritische Prüfung von `61860d3b-d9d0-40f2-82f6-316422c64d05/Eingefügter Text.txt`, anschließend ausschließlich bestätigte aktuelle Fehler in RoboForex, Zulu und Pelican beheben. Keine Liveplattformen, Logins, Produktionsdaten, Cookies, Settings oder LLM-Aufrufe verändert oder verwendet. Keine Programme oder Brokerterminals gestartet; Tests verwenden lokale Testserver/Fakes. Keine Commits, Stages oder Pushes durch diesen Bearbeiter.

| Repository | HEAD vor Änderungen | Änderungen dieser Runde |
|---|---|---|
| roboforex | `99afb590a11bbe066555a35a9aa8a176f08130a3` | zwei bestätigte DD-Fehler, Provenienz, Regressionen, Doku |
| zulumonitor | `5221b4838f935abe853b0ac8204d4f7639381e93` | README und Methoden-/Ledgerdokumentation |
| PelicanTrading | `c2c4ac71a889c14896366778c1d5b77b13a0adf3` | README und API-Quotendokumentation |

Die laufenden lokalen Instanzen und ihre Buildversionen wurden hier nicht abgefragt. Ein behobener Quellstand beweist keine bereits aktualisierte laufende Instanz. Der Bericht aus dem Anhang bezeichnet dagegen Robo `42b268641ad3`, Zulu `72df0cf49aa4` und Pelican `dde77d705a67`; diese Stände sind nicht identisch mit den obigen Ausgangsständen.

## Einordnung der Fremdbefunde

| Behauptung | Ergebnis am aktuellen Stand / stärkster Gegenbeleg |
|---|---|
| S1 / ROB-1: SHA-only friert Scannerhistorien ein | Bereits behoben: Robo-Stufe0 lädt Tageslisten und Deals erneut und vereint Deals nach Identität. Die 72-Stunden-Regel betrifft den Katalog. Bekannte Historien werden nicht aufgrund zeitloser SHA-Gleichheit übersprungen. Alte GUI-Cacheoption und Scanneraktualisierung sind unterschiedliche Wege. |
| S1 / ZUL-1: `istFrisch` benötigt zwingend eine neue Altersgrenze | Für Stufe0 überholt: bekannte Historien werden aktualisiert/vereint. Die ausdrücklich dokumentierte GUI-Option „Geladene überspringen“ ist bewusst ein Cachemodus. Der historische Methodenname `istFrisch` prüft dort Integrität, keine Plattformfrische. `geladenAm` ist Bestätigungszeitpunkt auch nach Cacheanzeige; keine REST-/UI-Ausgabe dieses Ledgertimestamps als Plattformabruf gefunden. REST-`lastUpdated` stammt aus der CSV-Dateizeit. Keine neue 24h-Auswahlpolitik eingebaut. |
| S2 / ROB-3: Kontoflüsse verwässern Closing-DD | Bereits behoben: Kontobuchungen werden aus der Handelskurve ausgeschlossen; Kommission/Swap bleiben Handelskosten. Die unten beschriebene neue Basis-/Historien-Provenienzlücke war davon unabhängig. |
| S2 / ZUL-2/3: fehlende/gekappte Basis führt zu scheinbarem 0-DD | Bereits abgesichert: positive endliche ROI, vollständiger Tradecount, eindeutige IDs, valide geschlossene Positionen und positive endliche implizite Basis sind erforderlich. Sonst `null`. `zulumonitor/src/main/java/de/zulumonitor/report/TradePayloadBuilder.java:40–57`; Stufe0 verwirft DD bei Katalogskip (`update/UpdateJobRunner.java:166`). |
| ROB-5: stiller Yield≤300-Filter | Belegt ist die feste Quellanfrage `profit_percent_max=300`, jeweils für das gewählte Ratingfenster, Standard drei Monate (`api/RoboForexClient.java:96`). Tatsächliche aktuelle Plattformwirkung wurde nicht live verifiziert. Keine begründete Nutzerentscheidung für diese Grenze im Repository gefunden. README:383 legt sie als separate Quellanfrage vor Top-N/Scanner offen. Grenze nicht eigenmächtig entfernt oder als Scanner-Risikoregel ausgegeben. |
| Pelican F3: Total≈2×Positionen beweist falsche Winrate | Nicht bewiesen. Parser übernimmt `Trades.Inception.Total/Wins/Losses` (`api/PelicanClient.java:254`), Anzeige rechnet `100*Wins/Total` (`model/Provider.java:234`). Swagger beschreibt keine Deals-/Positionszählung. Die archivierten Stats und ClosedSignals haben zudem verschiedene Zeitumfänge. Eine plausible Zählhypothese ersetzt keinen Quellenvertrag. Keine Nenneränderung. |
| ROB-4/6/10 | Im zugänglichen Bericht nur IDs ohne konkrete Beschreibung. Lokale zugängliche Reviewartefakte lieferten keine belastbare zusätzliche Definition. Keine Befunde oder Fixes erfunden. |
| „Historische FX auch bei Robo korrekt bestätigt“ | Als pauschale Entlastung falsch: Robo exportiert gespeicherte Geldbeträge ohne historische FX-Umrechnung. Das ist in README:395 ausdrücklich dokumentiert. Keine neue FX-/ProCent-Skalierung erfunden. |
| „Commission=0 bei Robo-Exporten“ | Pauschal falsch: echte Kommissionen/Swaps werden im Aggregator anteilig erhalten und im CSV ausgegeben (`deals/TradeAggregator.java:93`, `rest/RestApiServer.java:545`). Ob ein einzelner Plattformdatensatz null Kosten liefert, ist eine andere Frage. |

Pelican-Gegenrechnung aus versionierten, anonymisierten historischen Fixtures: `Total=30166`, `Wins=14517`, `Losses=690`; `(Wins+Losses)=15207`, Verhältnis `Total/(Wins+Losses)=1,983691720918`, nicht exakt zwei. Marktzähler summieren sich auf 29838. Die Closed-Fixture enthält 637 Zeilen vom 01.–24.09.2026, der Stats-Inception-Zeitraum beginnt am 05.12.2022. API-Statistikquote: 48,1237154412 %. Diese Zahlen beweisen keine identische Grundgesamtheit oder Positions-Winrate. Nachweis: `quellen_b/pelican_fixture_counts.json`; Swagger `PelicanTrading/research/swagger.json:2826`. README:168 und Provider-Javadoc benennen die Unsicherheit.

## Neuer bestätigter eigener Befund R-GLM-1: DD ohne zeitlich passende Ratingbasis

**Schweregrad P1; gesichert als Code-/Offline-Repro, aktuelle Plattformhäufigkeit unbekannt.**

Auslöser: Katalogphase wird wegen des 72h-Vermerks übersprungen, Tages-/Dealhistorie wird trotzdem frisch abgerufen. Der alte Yield wurde mit der neuen PnL-Summe zur Kapitalbasis verrechnet. REST, Chart und Bericht konnten denselben Fehler eigenständig erneut herstellen.

Unabhängige Gegenrechnung: zwei frische Realisierungen `+200`, `−50`, End-PnL150. Mit altem Yield10% folgt Basis1500 und DD `50/1700=2,94117647%`. Bei passendem aktuellem Yield15% folgt Basis1000 und DD `50/1200=4,16666667%`. Dies zeigt eine mögliche Unterschätzung; ohne aktuelle Basis kann keine der beiden Zahlen als tatsächlicher Konto-DD behauptet werden. Audit-Repro im alten isolierten Snapshot: `quellen_b/roboforex/src/test/java/de/robomonitor/RoboCachedBasisProbeTest.java`; Ausgabe `quellen_b/robo_cached_basis_probe.log`. Dieser Probe-Test belegt den Altfehler und gehört nicht zum Produktstand/finalen Snapshot.

**Korrektur:**

- `store/TradeDdStore.java:32`: nur ein erfolgreicher neuer Katalog-/Ratingabruf liefert eine Basisbestätigung. Eine Cacheanzeige tut dies nicht. Ein neuer Historienabruf verbraucht diese Bestätigung einmal.
- `store/TradeDdStore.java:38/64`: persistenter Nachweis in `data/trade_dd_provenance/dd_<Login>.json` mit Schema1, DD-Modell3, Basisfingerabdruck (Identität, Plattform, Yield, Fenster, Ratingcount), Bestätigungszeitpunkt, exakter Deal-SHA und Abrufgeneration. Nur valide vollständige Dealzuordnung und positive endliche Kapitalbasis erzeugen einen Nachweis. Historische `trade_dd.csv`-Werte ohne Beleg werden nicht übernommen.
- `store/DealStore.java:112`: jeder erfolgreiche Historien-Speichervorgang erzeugt eine neue `fetch_id`; unveränderte Rohbytes sind kein Beweis einer erneut bestätigten Renditebasis.
- `update/UpdateJobRunner.java:214`: Katalogskip aktualisiert Rohdaten weiter, verwirft aber den Prozent-DD. Kein Löschen der Rohhistorie.
- `RoboMonitorApp.java:370/1418/1524/1790/2535/3038`: Stufe0, GUI-Einzel-/Batchabrufe, Cacheanzeige und Start laden/erzeugen denselben gebundenen Nachweis. Kein alter Yield als automatische Ersatzbasis.
- `rest/RestApiServer.java:413/676`: beide DD-Aliasse lesen ausschließlich den Nachweis. `TradeDdBasisStatus`, `TradeDdBasisConfirmedAt`, `TradeDdModelVersion` legen ihn offen. Ohne Proof bleibt DD `null`, valide Rohtrades/CSV bleiben verfügbar.
- `report/SignalPayloadBuilder.java:108`, `report/ReportService.java`, `report/TradeCurveData.java:9`, `RoboMonitorApp.java:1731/2329`: Berichtspayload und Chart-DD verwenden denselben Proof; Geldkurve bleibt verfügbar, aber es gibt keine unbestätigte Prozentrechnung oder 10k-Ersatzbasis.

Regressionen: neun `TradeDdProvenanceTest`-Fälle (frischer Normalpfad, Neustart, Legacy, Yield/Fenster/Count, SHA, identische Rohbytes bei neuem Abruf, ungültige Basis/Modell, Berichtspayload, Chartdaten); 72h-Skip in `UpdateJobStufe0Test:202`; REST-Grenzen in `RestApiServerTest:304/323`.

Gegenposition/Grenze: Die bestehende Yield→Kapital-Rückrechnung bleibt eine methodische Annahme, kein unabhängiger historischer Kontostandsnachweis. Der Fix verhindert unbelegte Kombinationen und behauptet keine neue Plattform-/FX-Semantik. Die GUI-Cacheanzeige darf einen exakt gebundenen historischen DD-Snapshot weiterhin anzeigen; es wurde keine zusätzliche TTL eingeführt.

## Neuer bestätigter eigener Befund R-GLM-2: MT4-PnL auf Eröffnungszeit verbucht

**Schweregrad P1; gesichert durch deterministische mathematische Gegenprobe.**

Die rohe Closing-DD-Kurve nutzte für beide Plattformen `OpenTime`. Bei MT5 ist das die Dealzeit; bei MT4 ist es die Eröffnung einer später geschlossenen Order. Dadurch waren Reihenfolge und Fensterzugehörigkeit realisierter Gewinne/Verluste falsch.

Oracle: MT4-Order A öffnet Tag1, schließt Tag3 mit +200; B öffnet Tag2, schließt Tag2 mit −100. Bei End-PnL100 und Yield10% beträgt die implizite Basis1000. Richtige Schlussreihenfolge: `0 → −100 → +100`, DD10%. Alte Eröffnungsreihenfolge: `0 → +200 → +100`, DD `100/1200=8,33333333%`. Ein MT4-Abschluss im aktuellen Ratingfenster wurde zudem ausgeschlossen, wenn die Eröffnung davor lag.

Korrektur: `model/Deal.java:59` liefert bei MT4-Orders den Schlusszeitpunkt, bei MT5 weiterhin die Dealzeit. `model/EquityKurve.java:60/64` sortiert/bucht danach; `report/SignalPayloadBuilder.java:55` filtert nach derselben Ereigniszeit. Modell3 verhindert die Übernahme alter DD-Belege.

Unabhängige Tests: `ClosingDdDealsTest:97` (MT4 erwartet10%), `:111` (MT5 behält8,33333333%, abweichendes CloseTime wird ignoriert), `:125` (fixer Stichtag, drei Monate, Abschluss exakt an Untergrenze eingeschlossen; eine Nanosekunde davor ausgeschlossen; beide Plattformen ergeben `50/1100*100`). Kontobuchungen und MT5-Dealereignisse behalten ihre bisherigen Semantiken.

## Geänderte Produktdateien

Die vollständige maschinenlesbare Liste mit SHA256 steht in den Manifesten. Robo:13 bereits versionierte Dateien plus3 neue Dateien, insgesamt16 Overlays.

```text
roboforex/README.md
roboforex/src/main/java/de/robomonitor/RoboMonitorApp.java
roboforex/src/main/java/de/robomonitor/api/RoboForexClient.java
roboforex/src/main/java/de/robomonitor/model/Deal.java
roboforex/src/main/java/de/robomonitor/model/EquityKurve.java
roboforex/src/main/java/de/robomonitor/report/ReportService.java
roboforex/src/main/java/de/robomonitor/report/SignalPayloadBuilder.java
roboforex/src/main/java/de/robomonitor/report/TradeCurveData.java                 [neu]
roboforex/src/main/java/de/robomonitor/rest/RestApiServer.java
roboforex/src/main/java/de/robomonitor/store/DealStore.java
roboforex/src/main/java/de/robomonitor/store/TradeDdStore.java                   [neu]
roboforex/src/main/java/de/robomonitor/update/UpdateJobRunner.java
roboforex/src/test/java/de/robomonitor/ClosingDdDealsTest.java
roboforex/src/test/java/de/robomonitor/RestApiServerTest.java
roboforex/src/test/java/de/robomonitor/TradeDdProvenanceTest.java                [neu]
roboforex/src/test/java/de/robomonitor/UpdateJobStufe0Test.java
zulumonitor/README.md
zulumonitor/src/main/java/de/zulumonitor/store/TradeListenStore.java
PelicanTrading/README.md
PelicanTrading/src/main/java/de/pelicanmonitor/model/Provider.java
```

## Abschließende isolierte Validierung und Freeze

Alle Snapshots sind `git archive HEAD` plus die zugelassenen aktuellen Änderungen, keine unmodifizierten Altstände. Keine ignorierten Produktions-/Laufzeitdateien als Overlay übernommen. Bei Pelican sind bereits versionierte historische Datenassets des Git-Archivs enthalten; das ist nicht mit aktuellen privaten Laufzeitdaten gleichzusetzen.

Basisordner: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\glm53_review_pruefung_2026-10-16\quellen_b`.

| Repository / finaler Snapshot | Befehl | Ergebnis |
|---|---|---|
| `roboforex_fixed` | `mvn -o clean test` | **179 Tests,0 Fehler,0 Errors,0 Skips** |
| `roboforex_fixed` | `mvn -o -DskipTests package` | **Exit0 / BUILD SUCCESS** |
| `PelicanTrading` | `mvn -o test "-Dtest=FixtureParseTest,CoreRegressionTest,UpdateJobStufe0Test"` | **46 gezielte Tests grün** |
| `PelicanTrading` | `mvn -o -DskipTests package` | **Exit0 / BUILD SUCCESS** |
| `zulumonitor` | `mvn -o test "-Dtest=TradeListenStoreTest,DrawdownBasisTest,UpdateJobStufe0Test"` | **18 gezielte Tests grün** |
| `zulumonitor` | `mvn -o -DskipTests package` | **Exit0 / BUILD SUCCESS** |

Robo-Lognamen: `roboforex_fixed_test.log`, `roboforex_fixed_package.log`, `roboforex_fixed_result.json`. Pelican/Zulu analog mit Repositorynamen. Endgültiger Robo-Paketbau: `roboforex_fixed/target/robomonitor-1.2.0.jar`. Die älteren Ordner/Logs `roboforex`/`roboforex_test.log` dokumentieren den Vor-Provenienzstand und sind ausdrücklich **kein finaler Robo-Validierungsnachweis**.

Manifeste: `roboforex_fixed_manifest.json`, `PelicanTrading_manifest.json`, `zulumonitor_manifest.json`. Format: `repository`, `headBefore`, `overlay:[{path,liveSha256,snapshotSha256}]`, `snapshotFiles:{relativerPfad:sha256}`; das Robo-Manifest enthält zusätzlich den absoluten `snapshot`-Pfad. Der finale Abgleich `final_hash_verification.json` prüft alle ursprünglichen Snapshotdateien nach Maven sowie alle Live-Overlaydateien gegen die jeweiligen Manifeste: **keine Abweichungen** (Robo66 Dateien/16 Overlays; Zulu56/2; Pelican98/2). Generierte Maven-Zielartefakte sind nicht Teil des ursprünglichen Quellmanifests.

Stand für Root zur Publikation eingefroren. Es bleiben bewusst offene Plattformsemantiken (Pelican-Positionszählung, Robo300%-Auswahlbegründung, universelle Lots-/Währungsnormalisierung); dafür wurden keine scheinbaren Fixes erfunden. MqlRealmonitor/PelicanWinnerLooser wurden nicht integriert.
