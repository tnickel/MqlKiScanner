# Unabhängige Gegenprüfung MQL/Vantage

Datum: 16.10.2026. Read-only-Prüfung der aktuellen Änderungen und des Berichts `quellen_a.md`. Keine Produktänderung, kein Stage/Commit/Push, keine Liveplattform und kein Login. Vorliegende isolierte Testberichte wurden gelesen; die Quellensuiten wurden für diese Gegenprüfung nicht erneut ausgeführt.

## Ergebnis

Keine belegte neue Regression in den untersuchten Änderungen. Die zunächst vorgeschlagene generelle Scanner-Abfrage mit `minSubscribers=0` wird ausdrücklich zurückgezogen: Sie würde die bewusst eingeführte Quellkatalogpolitik umgehen.

### MQL: Standardfilter und Fix-ID-Vertrag

`MqlDownloader/src/rest/RestApiServer.java` filtert Provider standardmäßig auf mindestens einen Abonnenten; ausdrücklich gesetztes `minSubscribers=0` erhält Archivzugriff. Der Filter greift vor Pagination. Detailzugriff auf einen gespeicherten Anbieter bleibt möglich.

Die erste Gegenprüfung sah darin eine mögliche Inkonsistenz zum Scanner-Default `min_abonnenten=0` und empfahl einen pauschalen Opt-out. Diese Einordnung war zu weitgehend: Der lokale Scannerfilter verspricht keinen ungefilterten Plattform-/Quellkatalog. Eine bewusste Quellpolitik `>=1` und ein zusätzlicher lokaler Filter von 0 sind miteinander vereinbar.

Ein unabhängig zugesagter Fix-ID-Detailpfad wird durch den neuen Standard nicht beschädigt:

- `SignalKiScanner/src/mqlkiscanner/downloader_client.py`: Die vorhandene Methode `provider()` hat keinen Aufrufer im Scanner.
- `SignalKiScanner/src/mqlkiscanner/pipeline.py`, `_ergaenze_fix_ids`: Nur in `mql5`/`beides` wird mit vorhandener MQL-Session die öffentliche Signalseite einzeln nachgeladen. Im Modus `quellen` werden im Quellkatalog fehlende Fix-IDs ausdrücklich protokolliert und übergangen; dieser Vertrag bestand bereits vor der Änderung.
- Konkreter Vertragsregressionstest: `SignalKiScanner/tests/test_fix_signale.py::test_crawl_quellen_modus_protokolliert_fehlende_fix_id` erwartet genau dieses Übergehen mit Logeintrag. `test_crawl_fehlerhafte_fix_id_wird_uebergangen` sichert außerdem den Fehlerfall beim Direktabruf.
- Neuer Quellentest: `MqlDownloader/tests/rest/SubscriberDefaultTest.java::catalogDefaultsToSubscribersButExplicitArchiveAndDetailsRemainAccessible` prüft Standard, CSV, explizites 0, leeren Parameter, großes Minimum und erhaltenen Detailzugriff.

Dokumentierbare Grenze: Fix-IDs umgehen lokale Vorfilter und Exportlimits; sie garantieren keinen Quellen-Einzelabruf für Anbieter, die der Quellkatalog nicht anbietet. Ein genereller Opt-out ist dafür keine erforderliche Korrektur. Bestehende Mindestabonnentenpolitik der anderen Monitore bleibt unberührt.

### MQL: Pagination

Die gemeinsame Parameterbegrenzung erfolgt vor dem `int`-Cast, das Seitenende wird mit `long` addiert. Dadurch sind positive `long`-Offsets und `Integer.MAX_VALUE`-Limits überlaufsicher. Negative Parameter behalten den bisherigen Clampvertrag. Filterung vor Seitenauswahl bleibt erhalten.

Testbeleg: `MqlDownloader/tests/rest/RestApiServerTest.java::largePaginationValuesCannotOverflowAnyListEndpoint` prüft Provider, Dateikatalog, Abonnentenhistorie und Trades per tatsächlichem Loopback-HTTP. Die unabhängige Codeprüfung bestätigt die Arithmetik; kein neuer Grenzfehler gefunden.

### Vantage: Rankingquoten

`vantage/src/main/java/de/vantagemonitor/api/VantageClient.java::downloadProviders` erhält kuratierte Priorität. Die Kopiererphase bekommt höchstens die Hälfte des Restbudgets, maximal 250 neue Plätze; Return füllt das verbleibende Gesamtziel. Die innere Seitenschleife überschreitet das jeweilige Teilziel nicht. Doppelte IDs verbrauchen keine Plätze; überlappende Returnseiten werden weiter paginiert.

Testbelege in `vantage/src/test/java/de/vantagemonitor/api/RankingUnionTest.java`:

- `bothRankingsContributeBelowAtAndAboveOldCopierCap`
- `curatedPriorityAndOverlappingReturnPagesKeepReservedPlaces`

Das ist eine nachvollziehbare Auswahlpolitik, keine statistisch validierte Qualitätsrangfolge. Sie garantiert auch keinen vollständigen Plattformkatalog.

### Vantage: CSV und REST-Metadaten

`store/DataStore.java` erhält die bisherigen 20 CSV-Spalten in unveränderter Reihenfolge und ergänzt fünf Herkunftsspalten. Alte 20-Spalten-Dateien bleiben lesbar; fehlende Herkunft wird `unknown`. Die bestehenden Python-Consumer lesen benötigte Spalten nach Namen (`csv.DictReader`) beziehungsweise erzeugen eigene Kataloge; die zusätzlichen Spalten brechen diese Leser nicht.

`rest/RestApiServer.java` ergänzt `metricsWindow` und `ddSource` neben dem bestehenden numerischen `metrics`-Objekt. Die Modelsetter normalisieren fehlende Werte auf `unknown`, daher erhalten die neuen `Map.of`-Aufrufe keine null-Werte. Rankingfenster und erfolgreiches Overviewfenster werden feldweise unterschieden. `TradesTruncated` ist bei unbekanntem oder unverifiziertem Umfang null, bei belegtem gekapptem Umfang true und bei belegter Countgleichheit false. Countgleichheit ist weiterhin kein unabhängiger Vollständigkeitsbeweis.

Testbelege:

- `api/MetricsWindowTest::oneMonthRankingAndAllOverviewKeepDistinctWindowsAcrossPersistence`
- `api/MetricsWindowTest::legacyCacheAndUnspecifiedTopListWindowStayUnknown`
- `RestApiServerTest::metricsExposeFieldSpecificWindowsWithoutInventingThreeMonths`
- `RestApiServerTest::truncationIsUnknownWithoutVerifiedPlatformTotalAndTriStateOtherwise`

Scanner-Kompatibilität: `SignalKiScanner/src/mqlkiscanner/ingest.py::metrics_zu_stats` übernimmt `TradesTruncated` ohne erzwungene Bool-Konvertierung. Die zusätzlichen Maps werden vom Scanner derzeit nicht ausgewertet. Das ist eine bestehende Integrations-/Anzeigelücke, keine durch die additive Antwortstruktur neu entstandene Regression. Aus den vorhandenen Legacy-Feldnamen darf deshalb kein vom Scanner bereits berücksichtigter Fensterbeleg abgeleitet werden.

## Gelesene Verifikation

Die finalen isolierten Logs dokumentieren erfolgreiche Builds und Tests:

- `MqlDownloader_final2.maven.log`: 116 Tests, Build einschließlich Distributions-JAR erfolgreich.
- `vantage_final.maven.log`: 65 Java-Tests, Paket erfolgreich.
- `vantage_final.python.log`: 12 Python-Tests bestanden.

Diese Zahlen stammen aus den Quellensnapshotläufen des Quellen-Agenten. Die vorliegende Gegenprüfung bestätigt Code-/Vertragskompatibilität in ihrem genannten Umfang, keinen Livezustand laufender Instanzen.
