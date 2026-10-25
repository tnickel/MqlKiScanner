# F1: kontrollierte Erneuerung der Vantage-Altbestände

Stand 18.10.2026. Geändert wurde ausschließlich das Nachbarrepository `SIGNALDOWNLOADER/vantage`; im Scanner liegen nur diese Fixnachweise. Der Vantage-Arbeitsbaum war vor Beginn sauber. Keine Commits, keine Secrets-Ausgaben, keine Migration produktiver Dateien, keine Plattformdownloads und kein Start/Stop einer laufenden Anwendung.

## Behoben

- `TradeStore.mergeHistory` mischt nur verifizierte UTC-Generationen ein. Vorhandene v1-/SHA-ungültige Zeilen werden nicht eingelesen, umetikettiert oder als Teil der neuen Historie gezählt. Eine valide frische Lieferung kann den normalen Einzel-/Updateweg wieder durchlaufen.
- `TradeStore.saveTrades` und `TradeListStore.save` bereiten alle Ersatzdateien vor. Erst danach wird der unveränderte unverifizierte Altbestand in einem eigenen Unterverzeichnis `quarantine/<store>_<id>_<eindeutig>/` gesichert. Die Quarantäne enthält ursprüngliche CSV/Meta-Dateien, im Kernstore auch Positionen/Tagesdaten, im Displaystore auch den alten Ledger. `renewal.txt` hält fest, dass diese alten Bytes nicht Bestandteil der UTC-Historie sind.
- Veröffentlichung erfolgt mit CSVs zuerst und Verifikationsmeta/Ledger zuletzt. Bei einem Schreibfehler werden die bisherigen aktiven Bytes wiederhergestellt; eine bereits angelegte Quarantäne bleibt zusätzlich erhalten. Ungültige Lieferung oder bereits gesetzter Abbruch verändern keine Altdatei. Der Windows-Test sperrt die Meta-Datei gegen Ersetzung: Der Fehler tritt nach bereits veröffentlichten CSVs auf und der Rollback stellt den alten Bestand wieder her.
- Ein Interrupt zwischen zwei Veröffentlichungsschritten wird ebenfalls zurückgerollt. Dafür wird das Interruptflag während der NIO-Wiederherstellung vorübergehend gelöscht und anschließend wieder gesetzt. Der deterministische Test verschiebt die erste echte Datei, setzt den Interrupt und prüft alte aktive Bytes, fehlende Rollbackfehler und das erhaltene Abbruchsignal.
- Der neue aktive Vermerk enthält bei einer Erneuerung `version=2`, `timeBasis=UTC`, `renewedFromUnverified=true`, `legacyIncluded=false` und SHA/Count ausschließlich der neuen gültigen Generation. Provider-`total` bleibt gesondert. REST weist eine gekappte Erneuerung weiterhin mit `TradesTruncated=true` aus.
- Teilfehler zwischen den beiden Ablagen führen nicht mehr zu einem Erfolgseintrag im Updatezähler. „Geladene überspringen“ verlangt Ledger **und beide** verifizierten Ablagen. So kann eine nur halb erneuerte Speicherung beim Folgelauf repariert werden.
- Hat der Displaystore bereits eine neue UTC-Generation gespeichert, der Kernstore aber noch nicht, überlebt diese verifizierte Generation auch ein kleineres Folgefenster. Priorität bei gleicher Order-ID: frische API-Antwort vor gültigem Kernstore vor gültigem Displayfallback. Ungesicherte v1-Daten sind in keinem dieser Kanäle zulässig.
- Ein unterbrochener optionaler Tagesdatenabruf wird nicht mehr als bloßer optionaler Fehler verschluckt. Der Lauf speichert danach keine neuen Historien und meldet `tradelistenAbgebrochen`.
- Die Alt-Ledger-Übernahme beim Start registriert nur bereits verifizierte Kernhistorien. Bestehende v1-Dateien werden beim Start weder verändert noch zertifiziert.

## Codeorte

| Datei | Funktion |
|---|---|
| `vantage/src/main/java/de/vantagemonitor/store/HistoryFiles.java` | Staging, Quarantäne, Veröffentlichung, Rollback und Interruptprüfung |
| `vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:80` | Normales Speichern und Erneuerung |
| `vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:139` | Getrenntes UTC-Merge mit verifiziertem Fallback |
| `vantage/src/main/java/de/vantagemonitor/store/TradeListStore.java:77` | Displaygeneration und Ledger gemeinsam veröffentlichen |
| `vantage/src/main/java/de/vantagemonitor/store/TradeListStore.java:189` | Ausschließlich verifizierte Displayhistorie als Fallback |
| `vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:376` | Updateadapter und Cache-Skip |
| `vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:2032` | Einzel-/GUI-Batch-Erneuerung |
| `vantage/src/main/java/de/vantagemonitor/update/UpdateJobRunner.java:195` | Erfolgszählung nach vollständigem Speichern; Abbruchweitergabe |

## Verifikation

Der abschließende vollständige Lauf `mvn -q test` nach dem Interruptfix beendet sich mit **Exit 0: 88 Tests, 0 Fehler, 0 Fehlschläge, 0 übersprungen**. Die zuvor gesondert geprüften 55 betroffenen Store-/Recovery-/Update-/REST-Fälle sind darin enthalten, einschließlich des Interrupts zwischen zwei Veröffentlichungen. Die genauen Befehle, geprüften Fälle und einzelnen Suitezahlen stehen in `fix_vantage_tests_build.json` (ohne Maven-Systemproperties oder Laufzeitsecrets). Der abschließende Testlauf änderte nur Build-/Testreports; das bereits gebaute Paket und seine unten genannten Hashes blieben unverändert.

Neue beziehungsweise erweiterte Regressionen:

- `TradeIntegrityTest`: bytegenaue Quarantäne von v1-/ungültigem Bestand, keine stille UTC-Rezertifizierung, frisches Count/Total, Duplikat-/Leerlieferung, Abbruch, I/O-Stagingfehler, fehlgeschlagener Ledger, Priorität gültiger Archive, echter Windows-Meta-Publishfehler mit Rollback.
- `LegacyHistoryRenewalTest`: vollständiger normaler Updatepfad mit echten Stores und altem Ledger; Downloadfehler; Teilfehler zwischen Stores plus Folgefenster; Abbruch im optionalen Tagesabruf.
- `RestApiServerTest.legacyTradeTimesCannotBeExportedAsVerifiedUtc`: alter Bestand liefert weiterhin 404; nach normalem frischem Speichern liefern beide Trade-Endpunkte 200, Zeitbasis UTC, genau ein frisch gelieferter Trade und Provider-Total 99 mit korrekter Kappungsanzeige.
- Bestehende Alters-, Store-, API-, Update-, Statistik-/Berichts- und übrige Maven-Tests bleiben erfolgreich.

## Build und verteilbares Paket

Build: `mvn -q -DskipTests package dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/utc-renewal-dependencies`, Exit 0.

- JAR: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/target/vantagemonitor-1.2.0.jar`
- Paket: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/target/VantageMonitor-1.2.0-utc-renewal-20261018.zip`
- Größe: 27.308.167 Bytes.
- ZIP-SHA256: `CB1E7F51E51F4F604712CD459498BD8B1C389477B9C4A45685A455827D906C33`
- JAR-SHA256: `07FABCACF4F2EF779FECDD7DA945CD22F65605ADAD9EE06B1CE6A5FFB68C7BE7`

Das ZIP enthält das JAR, erforderliche Laufzeitbibliotheken, die Windows-JavaFX-Module und `run.cmd`; Java 25 wird vorausgesetzt. Es enthält **keine** Daten-/Config-/Secretsdateien. `java --dry-run` mit dem tatsächlich gepackten JAR, Classpath und JavaFX-Modulpfad war erfolgreich (Exit 0); dabei wurde keine Anwendung gestartet.

**Betriebsabnahme bleibt offen:** Ein erfolgreicher Build erneuert weder die laufende JVM noch die 199 zuvor gelisteten v1-Historien. Erst nach separat koordiniertem Neustart und einem normalen erfolgreichen Abruf kann der produktive UTC-Neubestand samt HTTP-Export und Quarantäne geprüft werden. Diese produktiven Schritte wurden hier nicht ausgeführt.
