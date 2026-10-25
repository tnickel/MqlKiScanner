# Nachprüfung DEFECT-01 und DEFECT-04 — MqlDownloader

Stand: 18.10.2026, finaler Java-Testlauf 13:10 Uhr Europe/Berlin.
Prüfgegenstand ist das Fremdreview `Eingefügter Text.txt`, Abschnitte DEFECT-01
und DEFECT-04. Alle produktiven Laufzeitdateien wurden ausschließlich gelesen.
Es gab keine produktiven Downloads, API-POSTs, DB-Mutationen oder Appstarts/-stopps.
Unit-/Integrationstests verwenden temporäre Verzeichnisse und Testdatenbanken.

## Bewertung und Umsetzung

**DEFECT-01 ist ein historisch bestätigter Fehler, im aktuellen Arbeitsbaum
bereits behoben.** Die im Fremdreview zitierte alte Zweiparameter-Methode mit
bedingungslosem 72-Stunden-Frühreturn ist abgelöst. Aktuell entscheidet
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/ClientUpdateRunner.java:70`
nur bei frischem Katalog **und** `tradelisten=false` auf vollständiges Skip.
Bei angeforderten Trades führt Zeile 84 einen Download der bekannten Anbieter
je Plattform aus. Alter/fehlender Katalog führt weiterhin zur Discovery.
`src/gui/MqlDownloaderGui.java:148` nimmt den Tradeparameter entgegen und
verdrahtet den Runner; `src/gui/DownloadManager.java:121` übergibt den
Updatemodus. `src/downloader/SignalDownloader.java:64` erzwingt im Updatemodus
den Providerabruf, sodass auch der frühere lokale Fünf-Tage-Dateicache diese
Anforderung nicht verschluckt. Der bestehende Fix ist unverändert erhalten.

Regressionsbelege: 8 Fälle in `tests/gui/ClientUpdateRunnerTest.java:58` ff.
(frisch/alt, mit/ohne Trades, Teilfehler, Konvertierungsfehler, leerer Scope,
eine Plattform) sowie 6 Fälle in `tests/downloader/SignalUpdateModeTest.java:78`
ff. (echtes Ersetzen auch jüngster CSV, Metadatenmodus, neue Historie,
fehlender Export, Stop zwischen und während Exporten).

**DEFECT-04 war eine bestätigte verbleibende Integrationslücke und ist jetzt
im Quellcode behoben.** Vorher enthielten die Katalogobjekte kein `weeks`.
Der Scanner weist solche regulären Kandidaten mit unbekanntem Alter korrekt
zurück. Das Fremdreview nennt dafür eine hier nicht vorhandene
`ProvidersHandler.java`; zuständig ist `rest/RestApiServer.java`.

Der echte Altersbeleg liegt bereits in lokalen MQL-Profilseiten:
`.s-indicators__item_weeks > .s-indicators__item-wrapper > .s-indicators__item-desc_weeks > span`.
Die H2-Schemadefinition in `src/database/DatabaseManager.java:46` ff. und die
vorhandenen TXT-Metrics besitzen kein Signalgründungs-/Wochenfeld.
Für die Nachprüfung wurde keine produktive H2-Verbindung geöffnet.

Neue Codeorte im MqlDownloader:

- `src/rest/ProviderFiles.java:56`: profilspezifische HTML-Auflösung mit exakter
  Dateinamen-ID und Plattformordner; Archivzugriff behält die bestehende
  eindeutige Identitäts-/CSV-Formatprüfung.
- `src/rest/ProviderAge.java:24`: lesender, begrenzter Ergebniscache je Datei
  und Plattform, bei Zeit-/Größenänderung invalidiert.
- `src/rest/ProviderAge.java:44`: passende Signal-ID und MT-Plattform,
  widerspruchsfreier Seitentitel, genau ein kanonischer MQL-Link dieser ID
  sowie genau ein strukturierter Wochenindikator sind erforderlich.
  Fremde Empfehlungskarten, Freitextzahlen, Mehrdeutigkeit und ungültige
  Zahlen liefern unbekannt. Ein tatsächlich belegter Nullwochenwert bleibt
  ein gültiger junger Wert; unbekannt wird niemals durch Null ersetzt.
- `src/rest/RestApiServer.java:787`: JSON-Katalog und Providerdetails liefern
  `weeks` und `weeksSource=mql_profile_cached_weeks_lower_bound`; ohne
  eindeutigen Beleg sind beide Felder `null`.
- `tests/rest/ProviderAgeTest.java:29` ff.: 7 Regressionen einschließlich
  falscher/fehlender Identität, Überlauf, Mehrdeutigkeit, Dateialter,
  Cacheinvalidierung, genauer ID-Zuordnung und Archivgrenze.
- `tests/rest/RestApiServerTest.java:110`: zusätzlicher echter HTTP-Test für
  Katalog/Detail und unbekanntes Alter auf temporärer H2-Instanz.

Der gespeicherte Wochenstand ist eine konservative Untergrenze: seit dem
Download vergangene Zeit wird nicht addiert. Abonnenten-Snapshots und erste
Trades werden nicht als Signalgründung ausgegeben. Die bestehenden Scanner-
Funktionen `ingest.normalisiere_wochen`, `ingest.kandidaten` und
`ScanPipeline.build_candidates` bleiben funktional unverändert.

## Reale lokale Altersbelege und Scanner-Vertrag

`mql_age_evidence.java` ruft den neuen produktiven Java-Parser direkt auf,
liest nur den bestehenden HTML-Bestand und gibt ausschließlich Aggregate und
öffentliche Signal-IDs/Wochenwerte aus. Ausgabe: `mql_age_evidence.json`.

| Lokaler Normalordner | HTML-Dateien | eindeutige numerische IDs | belegte Wochen | unter 26 | mindestens 26 |
| --- | ---: | ---: | ---: | ---: | ---: |
| mql4 | 111 | 111 | 110 | 16 | 94 |
| mql5 | 122 | 121 | 121 | 30 | 91 |

MT4-ID 1784430 bleibt unbekannt: der HTML-Wochenindikator ist vorhanden, aber
der passende `data-id`/`data-mt`-Identitätsbeleg fehlt. Der Normalordnerbestand
ist nicht identisch mit dem nach Abonnenten gefilterten Live-Katalog; die
Tabelle ist ausdrücklich keine neue Live-Kandidatenbilanz.

Beispiele: MT4 2295882 = 87 Wochen, MT4 2381807 = 6 Wochen;
MT5 2371777 = 26 Wochen, MT5 2350211 = 35 Wochen.
`mql_scanner_contract.py` führt 13 solcher belegten/ungeklärten Fälle durch
die echten Scanner-Funktionen. 26 Assertions bestanden: bei Mindestalter 26
werden 11 aufgenommen, das junge Signal und der unbekannte Fall verworfen.
Fix-IDs sind dabei leer; alle geschriebenen Kandidatenlisten liegen im
TempDir. Ergebnis: `mql_scanner_contract.json`.

## Aktuelle Tests und Paket

- Gezielte Java-Gruppe: **43 bestanden**, Exit 0 (`mql_targeted_tests.txt`).
- Finaler normaler Lauf **`mvn test`: 148 bestanden, 0 Fehler, 0 Skips**, Exit 0
  (`mql_tests_final.txt`). Er enthält die vorhandenen 11 GUI-UnitTests.
- Vorheriger Paketbau `mvn -Djava.awt.headless=true package`: erfolgreich,
  137 bestanden/11 GUI-Skips. `mql_package.txt` ist als damaliger Bauzustand
  erhalten; der normale abschließende Testlauf oben ersetzt diese Skips als
  aktuellen Testnachweis.
- Scanner-Vertragsregression: **150 bestanden**, Exit 0, 117,81 Sekunden
  (`mql_scanner_tests.txt`). Quellenfakes und autouse-Fixture sperren externe
  Requests; Produktionsspeicher wird durch temporäre Pfade ersetzt.
- `git diff --check`: Exit 0.

Verteilbares Paket:
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar`

51.260.413 Bytes, SHA-256:
`ff97255780e833a3ef185916e31508e6cacae17adaadf4eacf3f6cd6fa983ec5`.
`mql_artifact.json` enthält den Hash, beide getrennten Teststände und den
Bytevergleich aller 9 betroffenen Laufzeitklassen mit den aktuell getesteten
`target/classes`-Dateien. Alle stimmen überein. Frühere Hashes unter
`nachweise/fix_mql_*` gehören zum damaligen Paket vor dem Altersfix.

Reproduzierbare Befehle im MqlDownloader-Repository:

```powershell
& D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd test
& D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd '-Djava.awt.headless=true' package
$mqlAudit = 'D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner\doc\reviews\2026-10-18_download_datenfluss_pruefung\fremdreview_nachpruefung'
$mqlTemp = Join-Path ([IO.Path]::GetTempPath()) ('mql_age_evidence_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $mqlTemp | Out-Null
$mqlCp = 'target\classes;target\MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
javac -encoding UTF-8 -cp $mqlCp -d $mqlTemp (Join-Path $mqlAudit 'mql_age_evidence.java')
java -cp "$mqlTemp;$mqlCp" rest.mql_age_evidence C:\Forex\MqlAnalyzer\download
```

Reproduzierbare Befehle im Scanner-Repository:

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/fremdreview_nachpruefung/mql_scanner_contract.py
python -m pytest tests/test_deepseek_weeks_validation.py tests/test_quellen.py -q -p no:cacheprovider
```

## Grenzen

Die produktive JVM wurde nicht ausgetauscht oder neu gestartet. Der neue
REST-Vertrag ist mit dem gebauten Paket und temporären HTTP-Integrationstests
belegt; ein neuer laufender Produktionsprozess und dessen erneuter
Scanner-Katalogimport sind noch kein Teil dieses Nachweises. Ohne passende
lokale Profilseite bleibt das Alter bewusst unbekannt. Änderungen des
MQL-HTML-Aufbaus können wieder einen unbekannten Wert verursachen und
benötigen dann einen nachgewiesenen Parserabgleich.
