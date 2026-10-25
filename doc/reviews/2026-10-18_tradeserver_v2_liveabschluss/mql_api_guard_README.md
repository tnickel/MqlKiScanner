# MQL: historische Navigations-/Testkennungen an der API ausschließen

Die erneuerte Quelle lieferte 239 Katalogzeilen, darunter `test_1`/MT4,
`test_2`/MT5 und `page2` auf beiden Plattformen. Die beiden `page2`-Zeilen
stammen nachweislich aus den fehlerhaften Discovery-Abschlüssen des 18.10.;
die Testzeilen sind älter. Diese Datenbankzeilen werden erhalten. Sie sind
keine numerischen MQL-Signalprofile und dürfen nicht als Provider erscheinen.
Beleg: `mql_corrected_catalog_legacy_invalid.json`.

`RestApiServer` begrenzt öffentliche Provider auf kanonische positive
Dezimal-IDs `[1-9][0-9]*`. Er filtert vor Zählung, Sortierung und Paginierung;
Health, Provider-JSON/CSV und Zusammenfassung verwenden dieselbe Auswahl.
Ungültige direkte Providerpfade einschließlich History, Trades, Metrics und
Reports liefern 404. Der Dateikatalog und sein direkter Download erlauben
ebenfalls nur Dateien mit entsprechend belegbarer abschließender numerischer
ID. Daraus folgt keine Behauptung, dass ein Dateiname allein die historische
Broker-/Kontozuordnung belegt; bestehende Plattform-/Archivprüfungen bleiben
unverändert.

Events verwenden einen separaten rein lesenden Datenbankpfad. Er schließt
ungültige IDs bereits vor `LIMIT` aus, damit neuere Navigationszeilen gültige
Ereignisse nicht verdrängen. Exakte Regex-Anker `\A` und `\z` verhindern
eine Akzeptanz vor einem abschließenden Zeilenumbruch. Die bisherige rohe
Historienabfrage bleibt verfügbar. Es gibt keine Löschung oder Migration.

Vier neue HTTP-Integrationstests prüfen die öffentliche Zählung/Paginierung,
direkte Endpunkte, Dateizugriff und Event-Limitierung einschließlich
Kontrollzeichen und Unicode-Ziffern. Sie prüfen zugleich, dass Rohzeilen und
Dateien erhalten bleiben. Der isolierte Maven-Quellbau bestand mit
**163 Tests, null Fehlern und null Skips**. Veränderte Quelldateien und Hashes
stehen in `mql_api_guard_tests_summary.json`, die relevanten Testprotokolle in
`mql_api_guard_TEST-*.xml`. Der Test änderte weder das aktive `target/` noch
das laufende Fat-JAR und führte kein Packaging aus.

Eine unabhängige lesende Code-/Fixtureprüfung durch den parallel arbeitenden
Quellenagenten fand keine erkennbare Umgehung dieser ID-Sperre. Sie bestätigte
insbesondere Filter vor Paginierung beziehungsweise Event-Limit sowie den
Erhalt roher Historien. Diese Gegenprüfung führte selbst keine Tests oder
Laufzeitänderungen aus und ist kein zusätzlicher produktiver Abnahmenachweis.

Die vier tatsächlich beobachteten ungültigen Kennungen gelangen bereits mit
dem vorhandenen Scannercode weder durch `ingest.kandidaten` noch durch
`katalog._normalisiere`. Das wurde mit den tatsächlichen vier Rohkennungen,
den produktiven reinen Normalisierungsfunktionen und ohne Datenbankwrites
geprüft (`mql_api_guard_scanner_filter.json`). Der Beleg gilt für diese vier
nichtnumerischen Kennungen. Er ist keine allgemeine Zusicherung über
Null-/Negativ-IDs an jeder Scanner-Eingangsstelle.

Die produktive Instanz PID 1663784 führt währenddessen weiterhin den Job
`u-35579920-eb3d-4db4-83ef-ae6a24b934c9` mit dem vorher aktivierten
159-Tests-Build aus. Die API-Sperre wird erst nach natürlichem Jobende und
gesichertem Abschluss-/Generationsnachweis im Leerlauf aktiviert. Danach
werden vollständiger lokaler Katalog und unveränderte CSV-/Metrics-Hashes
erneut geprüft. Vorher ist die Katalogabnahme offen. Ein zusätzlicher
Download nur für diese Ausgabesperre ist nicht erforderlich.

`mql_corrected_finish.py verify-source` sichert vor dem Leerlaufneustart den
exakten erfolgreichen Jobabschluss, korrekte Folgeseiten und jede erfolgreiche
CSV-/Metrics-Generation. Die vier bekannten Altkennungen werden dabei als
noch offene Ausgabesperre dokumentiert. `after-guard PID SHA256` verlangt
anschließend die neue API-eigene PID, den erwarteten Paket-Hash, einen
untätigen Jobstatus, fehlerfreie Katalogidentitäten und unveränderte
Quellgenerationen, bevor genau ein Erfolgsabschluss angehängt wird. Die
Scanner-Neuberechnung erfolgt gesondert mit der bestehenden Wartungs-CLI
und dem gemeinsamen Lauf-Lock.
