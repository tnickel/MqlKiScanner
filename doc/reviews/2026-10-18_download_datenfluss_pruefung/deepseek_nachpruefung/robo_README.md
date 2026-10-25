# RoboForex: reproduzierter Konkurrenzfehler beim Tagesdaten-Bündel

Stand: 18.10.2026. Dieses zusätzliche Arbeitspaket wurde nach dem lesenden
DeepSeek-Abgleich ausdrücklich beauftragt. Änderungen betreffen ausschließlich
`roboforex/src/main/java/de/robomonitor/store/DataStore.java` und die neue
`roboforex/src/test/java/de/robomonitor/DataStoreBundleReadLockTest.java`.
Der Robo-Arbeitsbaum war vor Beginn sauber. Bestehende Tests wurden weder
geändert noch ausgeschlossen. Keine produktiven Daten oder Einstellungen,
Plattformabrufe, laufenden Monitore oder Terminals wurden verändert.

## Vorheriger Fehler und eigene Reproduktion

Die Angabe „RoboForex 183 passed“ im fremden Text ist durch den ursprünglichen
vorliegenden Bericht nicht gedeckt: 183 Fälle bestanden aus 182 erfolgreichen
Fällen und einem ERROR in
`ReviewDataIntegrityTest.parallelDailyStoresPublishVerifiableWholeBundles`.
Die Klasse umfasste 11 Fälle. XML und Text wurden **vor jedem neuen Testlauf**
unter [robo_before_parallel.xml](robo_before_parallel.xml) und
[robo_before_parallel.txt](robo_before_parallel.txt) konserviert; ihre Hashes
stehen in [robo_before_manifest.json](robo_before_manifest.json).

Der Test startet 40 Aufgaben auf vier Threads. Jede verwendet eine eigene
DataStore-Instanz, schreibt dasselbe synthetische Tagesdaten-Bündel und prüft
es danach. Der ursprüngliche Fehler war eine `AccessDeniedException` beim
atomaren Ersetzen von `daily_1.csv` durch die temporäre Datei
(`FileTransactions.write:19`, `DataStore.saveDaily:174`). Er stammt aus dem
Testlauf vom 18.10., nicht aus einem vermischt gezählten alten Login-Test.

Die eigene isolierte Wiederholung vor dem Fix reproduzierte **denselben
ERROR**. Zusätzlich scheiterten zwei neue deterministische Tests: Während
ein Writer den gemeinsamen Tagesdatei-Lock hält und bereits die nächste CSV
veröffentlicht hat, lesen die öffentlichen Methoden `hasDaily` und
`loadSymbols` noch vor Freigabe dieses Locks. Die dazugehörige Meta-/Symboldatei
gehört in dieser gezielt angehaltenen Phase noch zum alten Bündel.

```powershell
mvn -o -q "-Dtest=ReviewDataIntegrityTest#parallelDailyStoresPublishVerifiableWholeBundles,DataStoreBundleReadLockTest" test
```

**Vor Fix: 3 Fälle, 2 FAIL, 1 ERROR, Exit 1.** Belege:
[Befehl und Eingabehashes](robo_repro_command.json), [Log](robo_repro.log),
[Paralleltest-JUnit](robo_repro_TEST-de.robomonitor.ReviewDataIntegrityTest.xml),
[neue Regressionen](robo_repro_TEST-de.robomonitor.DataStoreBundleReadLockTest.xml).

## Ursache und minimale Korrektur

`saveDaily` und `loadDaily` verwenden bereits denselben instanzübergreifenden
Pfadlock. `hasDaily` führte seine erste CSV-/Meta-/Hash-Prüfung dagegen vor
diesem Lock aus. `loadSymbols` las die gekoppelte Symboldatei ebenfalls ohne
den Tagesdatei-Lock. Diese Leser konnten die Veröffentlichung überlappen;
auf Windows reproduzierte die Konkurrenz außerdem den genannten Dateifehler.

Nun hält `hasDaily` den bestehenden Tagesdatei-Lock für die gesamte Prüfung
(`DataStore.java:284`); auch `loadSymbols` liest darunter (`DataStore.java:225`).
Es gibt keine pauschalen Retries, keine neuen verschluckten I/O-Fehler und
keine Änderung von CSV-Schema oder Bewertung. Die bestehende Bool-API von
`hasDaily` bleibt erhalten. `dailyCount` und `tageOhneBewegung` verwenden die
geschützten Leser. Die Pfad-Getter selbst führen keinen Lesevorgang aus.

Die neuen Tests verwenden eine Start-Latch und prüfen den tatsächlichen
Threadzustand `BLOCKED` am richtigen Monitor mit dem richtigen Lockbesitzer.
Sie warten nicht per willkürlichem Schlaf. Nach vollständiger Veröffentlichung
und Lockfreigabe müssen die Leser das neue gültige Bündel sehen. Der
zwischenzeitlich veröffentlichte CSV-Stand wird mit dem echten
`FileTransactions.write` erzeugt.

Der Schutz gilt für die gemeinsamen DataStore-Zugriffe im selben JVM-Prozess.
Er ist keine prozessübergreifende Dateisperre und keine atomare
Dateisystemtransaktion über CSV, Symbole und Meta. Die bestehende
Integritätsprüfung und die getrennten atomaren Dateiveröffentlichungen bleiben
unverändert. Bereits eingetretene produktive Datenkorruption wurde durch diese
synthetische Reproduktion nicht nachgewiesen.

## Finale Abnahme

Alle Maven-Aufrufe liefen offline (`-o`) mit JDK 25. Die Tests verwenden
synthetische Daten und JUnit-Tempverzeichnisse; keine externen Plattformen,
Live-Logins oder produktiven Clients wurden angesteuert.

```powershell
mvn -o -q test
```

**185 bestanden, 0 Fehler, 0 übersprungen, Exit 0.** Das sind die bisherigen
183 Fälle plus zwei neue Regressionen. Wrapper-Laufzeit: 7,67 Sekunden.
[Befehl, Hashes und XML-Dateiliste](robo_full_command.json),
[Log](robo_full.log). Die vollständigen JUnit-Dateien sind unter
`robo_full_TEST-*.xml` in diesem Ordner konserviert.

Der gezielte Drei-Fälle-Aufruf von oben bestand anschließend in **fünf
getrennten Maven-/Test-JVM-Läufen** jeweils vollständig, ohne Fehler oder Skips.
Die Belege heißen `robo_repeat_1_*` bis `robo_repeat_5_*`. Diese Wiederholungen
überlappen mit der Vollsuite und werden nicht zu zusätzlichen verschiedenen
Tests addiert. Der wiederverwendbare [Runner](robo_run.py) hält Befehle,
Exitcodes, XML-Hashes sowie unveränderte Source-/Klassenhashes pro Lauf fest.
[Abschließende Verifikation](robo_verification.json).

## Paket und Betriebsgrenze

Nach den bestandenen Tests wurde ausschließlich das geänderte Robo-Projekt
normal paketiert:

```powershell
mvn -o -q -DskipTests package
```

Exit 0. [Paket-Befehl](robo_package_command.json), [Log](robo_package.log).
Ergebnis: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/roboforex/target/robomonitor-1.2.0.jar`,
313.415 Bytes, SHA-256
`75e303a14a64b7487b739462ac749912a2bd07c6f1d36b38f69662fb922d047d`.

Die enthaltene `de/robomonitor/store/DataStore.class` stimmt bytegenau mit
der in der Vollsuite und allen Wiederholungen verwendeten Klasse überein
(SHA-256 `2dca963f8e43ab079476d28d7cc01e72844729da705deec35089b3e79fe67ce8`).
[Artefaktprüfung](robo_artifact.json). Dies ist der normale Maven-Paketbau,
keine ausgeführte App-Startprüfung.

Bei Beginn der Quellenprüfung waren nur die Java-Fixes in MQL/Vantage als
Build-Drift betroffen. Der hier zusätzlich eingeführte Robo-Lockfix benötigt
nun ebenfalls den neuen Build beim nächsten geplanten Start. Es wurde kein
laufender Dienst gestartet, gestoppt oder neu geladen und kein pauschaler
Neubau aller fünf Quellen vorgenommen. Die früheren Quellen-Leseproben
beschreiben weiterhin ihren damaligen Zustand.
