# Kritische Prüfung des DeepSeek Reviews

Stand: 18.10.2026. Der [eingefügte DeepSeek-Text](DEEPSEEK_ORIGINAL.md) enthält einen bestätigten neuen Fehler beim Umfang des Anzeigekatalogs. Daneben vermischt er bekannte Ausroll-/Datenzustände mit Codefehlern und enthält falsche Detailaussagen. Die Gegenprüfung behebt den Katalogfehler sowie einen zusätzlich reproduzierten parallelen Dateizugriffsfehler im RoboMonitor. Bewertungsregeln, produktive Settings und bestehende Historien bleiben unverändert.

## Ergebnis je DeepSeek Befund

| Befund | Kritisches Ergebnis |
|---|---|
| F1: Alle fünf laufenden Quellenbuilds seien älter als die Fixes | Zu pauschal. Zum Beginn der Prüfung war spätere Java-Codeänderung für MQL/Vantage belegt. Für Pelican/Robo/Zulu lagen die geprüften Quell-/Classdateien vor dem gemeinsamen JVM-Start. Der Zulu-Hinweisfix liegt im Scanner. Unser zusätzlich nachfolgend behobener Robo-Lockfehler erzeugt nun auch dort einen neuen Buildstand. |
| F2: Der Scanner holt keinen Vollkatalog | Für „Alle Signale“ bestätigt und behoben. Die Übersicht erbte den Serverstandard `minSubscribers=1`. Sie fordert nun ausdrücklich `0` an. Die normale Kandidatenbeschaffung behält `1`. Ein gemeinsamer Default von `0` hätte den bisherigen Scan-/Downloadumfang verändert. |
| F3: Keine aktuelle Forensikversion im gespeicherten Workflow | Im Workflowbestand bestätigt, aber ein veralteter Datenstand ist kein neuer Berechnungsfehler. Der Schutz ist wirksam. Die pauschale Aussage „alle 194 sind `forensik_stale`“ ist falsch; Details unten. Separate Equity-Studien sind davon zu unterscheiden. |
| F4: Zulu-Vollständigkeitshinweis gehe verloren | Als früherer Scannerfehler richtig; im aktuellen Arbeitsbaum bereits behoben. `ingest.metrics_zu_stats` liest `TradesCompletenessNote` mit Legacy-Fallback. Ein Neubau des Zulu-Monitors behebt keinen alten Scanner-Pythonpfad. |

Die Aussage „Vantage 404 nur der alte Build“ ist falsch: Auch der korrigierte aktuelle REST-Handler weist unverifizierte v1-Historien zurück. Erst die belegte frische Erneuerung macht sie exportierbar. Ein Neustart allein erneuert keine Historie und belegt keine UTC-Zeitbasis. Drei HTTP-Proben sind kein vollständiger aktueller Test aller Historien. Die frühere lokale Inventur von 199 zugeordneten Legacy-Kataloghistorien ist ein anderer Nachweis. [Quellenprüfung mit Codeorten und Reichweiten](quellen_README.md).

## Neuer Katalogfix mit getrenntem Scanumfang

`DownloaderClient.katalog` bietet den Parameter `min_subscribers`, mit dem bisherigen Standard `1`. `ingest.hole_katalog` trägt den gewählten Wert durch jede Seite und prüft weiterhin Rohzeilenzahl, konstantes `total`, Offset, Dubletten und Abschluss. Ausschließlich `katalog.sync` wählt für die vollständige Metadatenübersicht den Wert `0`.

Zusätzliche Katalogzeilen erzeugen weder Workflowbefunde noch automatische Trade-/Historyabrufe. Der normale Scan und die Tradephase der Quellen bleiben unverändert. Ein vom Nutzer ausdrücklich gestarteter Studienbatch über „Alle Signale“ kann dagegen naturgemäß auch die neu sichtbaren Zeilen einschließen. Vollkatalog meint den lokalen Quellenbestand; vorgelagerte Plattform-Toplisten und andere Quellenfilter bleiben bestehen.

Die neue Regression prüft den echten Client-/Ingest-/DB-/Anzeigemodellpfad mit einem Servermodell, dessen Standard bereits 0-Abonnenten-Provider ausfiltert. Sie belegt die Null-Abonnenten-Zeilen über mehrere Seiten bis `katalog_resultate`, die unveränderte Kandidatenliste und den Schutz vor Löschung bei unvollständigem Vollkatalog. Reine Katalogabfragen dürfen im Test keine Trades oder Historien anfordern. Die Prüfung des Anzeigemodells ist kein Browserrendering.

Vor der Korrektur scheiterten die sieben neuen Vertrags-/Regressionsfälle ([JUnit](scope_before.xml), [Log](scope_before.log)); danach bestanden sie. Die anschließende gemeinsame Regression umfasst **407 bestandene Tests**, einschließlich dieser sieben Fälle sowie bestehender Transport-, Quellen-, Snapshot-, SHA-, Tabellen-, Studien- und Stufe-0-Verbraucher. [Finales JUnit](scanner_regression.xml), [Log](scanner_regression.log), [genauer Befehl und getestete Quellhashes](scanner_regression_command.json). Bestehende Testdoubles wurden um das neue Keyword ergänzt; Bewertungsassertions wurden nicht gelockert.

## Lokale Quellenmengen am 18.10.2026 um 17:05 Uhr

| Quelle | `/providers` mit Standardfilter | mit `minSubscribers=0` | zusätzliche Rohzeilen |
|---|---:|---:|---:|
| MQL | 216 | 236 | 20 |
| Pelican | 640 | 2188 | 1548 |
| Robo | 200 | 200 | 0 |
| Vantage | 199 | 200 | 1 |
| Zulu | 200 | 200 | 0 |

DeepSeek übersieht die zusätzliche Vantage-Zeile. Die Gegenprobe verwendet je Anfrage `limit=1`; dies sind belegte API-Gesamtzahlen, keine neue vollständige Pagination oder neu berechnete Scannerzeilenzahl. API-Rohzeilen und gültige numerische Scanner-IDs sind weiterhin getrennt zu zählen. [Zeitgestempelte HTTP-Belege](quellen_http.json).

Ein bislang abonnentenloses Signal würde nach einem späteren Abonnentengewinn auch im bisherigen gefilterten Scope wieder erscheinen, sobald der Monitor seine Daten und der Scanner seinen regulären Katalog aktualisiert haben. Die Lücke bestand in der bis dahin unvollständigen Metadatenübersicht; daraus folgt kein generelles Unvermögen, spätere neue Abonnenten zu erkennen.

## Bestandszahlen und Tabellenbehauptungen

Eine konsistente Read-only-Transaktion bestätigt 194 Workflowzeilen, 163 Forensikzeilen, 193 Tradeverweise und 1.454 Katalogzeilen. Die Überschneidung nach Quelle und ID beträgt 171, die Vereinigungsmenge damit 1.477. Quellenübergreifende numerische Kollisionen wurden in dieser Bestandsstichprobe nicht gefunden. Das ist der unveränderte produktive Bestand, nicht das Ergebnis eines bereits ausgeführten neuen Vollkatalogimports.

Die Workflowversionen lauten: 4 ohne Version, 27 mit 7, **3 mit 11**, 10 mit 14, 104 mit 15 und 15 mit 16; keine mit 19. Die DeepSeek-Aufstellung lässt Version 11 aus und summiert sich deshalb nur auf 160 statt 163. Der reale Reload kennzeichnet **161** Zeilen als stale. Die übrigen 33 bestehen aus 31 ohne Forensik und 2 mit unvollständigem Payload; insgesamt gibt es dennoch **keinen aktuell vollständigen Workflowbefund** und kein Grün/Gelb. Score, belastbarer H1-DD und TrueRetDD sind in allen 194 Workflowzeilen leer. In der separaten Studienablage existieren dagegen 1.354 Einträge mit Version 19 und 218 mit Version 0. [Read-only-Probe und Ergebnisse](persistenz_db.json).

Weitere fachliche Präzisierungen:

- Abonnenten und 7-/30-Tage-Deltas werden beim Tabellenaufbau aus der lokalen `subscriber_history` gelesen. REST-Abruf und Spiegelung sind eigene Abläufe; die Spalten beweisen keine neue Liveabfrage.
- Ampel und erklärendes Urteil bleiben sichtbar und werden mit den aktuellen Regeln abgeleitet. Stale sperrt die aktuelle positive Freigabe und Kennzahlen, löscht aber keine eigenständigen Ausschluss-/Risikoentscheidungen.
- TrueRetDD kann neben einem belastbaren Wert einen ausdrücklich orange markierten Vorbehaltswert zeigen. „Alle Signale“ kann eine eigenständig aktuelle passende Studie anzeigen, obwohl der Workflow alt ist; daraus entsteht keine neue Engine-Freigabe. Monitor-Closing-DD bleibt ein separater Schrankenkanal und kein Calmar-Nenner.
- Lokale Speicherzeit, letzter erfolgreicher Quellenabruf und jüngster Trade sind verschiedene Datenstände. Eine Version oder ein SQL-Join allein belegt weder Messqualität noch Aktualität.

## Zusätzlicher RoboMonitor Fehler und Testnachweise

Die vorhandenen Robo-Surefire-Berichte belegten entgegen „183 bestanden“ zunächst **182 bestandene Fälle und einen Fehler** in `parallelDailyStoresPublishVerifiableWholeBundles`. Der Fehler wurde mit dem vorhandenen Paralleltest erneut isoliert reproduziert: `AccessDeniedException` beim Ersetzen der Tages-CSV. Zwei neue deterministische Tests belegten zudem, dass `hasDaily` und `loadSymbols` die gemeinsame Sperre des CSV-/Meta-/Symbolbündels nicht einhielten.

Beide Leser verwenden jetzt denselben prozessweiten täglichen Pfadlock wie `saveDaily` und `loadDaily`. Damit sehen sie innerhalb einer Operation kein halb veröffentlichtes Bündel und konkurrieren nicht ungesperrt mit dessen Dateiersetzung. Es gibt weder einen pauschalen Wiederholungsmechanismus noch ein Verschlucken zusätzlicher IO-Fehler. Der Schutz ersetzt keine prozessübergreifende Transaktion und keine Stromausfallsicherheit.

Der neue Robo-Standardlauf besteht mit **185 Tests**, einschließlich der zwei neuen Leser-Lockfälle. Der genaue Ablauf, wiederholte Parallelprüfung und Paketnachweis stehen im [Robo-Behebungsbericht](robo_README.md). Ursprünglicher Fehlerbericht und rote Reproduktionen bleiben erhalten.

Die vorherige vollständige Scannerregression mit 2.499 Fällen ist ein älterer Stand vor den acht Legacy-Quellenfällen der vorherigen Nachprüfung und den jetzigen sieben Katalogfällen. Sie wurde hier nicht vollständig wiederholt. Die neuen 407 Scannerfälle, frühere 150 Legacy-Fälle und alte Vollsuite überlappen und werden nicht addiert. Auch die Behauptung „94 aus neun neuen Auditdateien“ passt nicht zum alten Nachweis: Die 94 damaligen Fälle stammen aus acht benannten Dateien. [Zeitlich eingeordnete Testprovenienz](persistenz_testprovenienz.json).

Bei Pelican dürfen alte Live-Login-XMLs nicht in einen aktuellen Standardlauf eingerechnet werden. Die dortige zusätzliche fehlerhafte XML stammt vom 07.10.; ihre Existenz widerlegt nicht pauschal die späteren Standardtests. Vorhandene Java-Testberichte anderer Projekte wurden gelesen, aber hier nur Robo neu getestet. [Prüfmanifest](manifest.json).

## Betriebsabnahme und verbleibende Grenzen

Neue Scanner-/Robo-Quellen sind im Arbeitsbaum korrigiert und getestet. Laufende Dienste, produktive Kataloge und Historien wurden damit nicht automatisch erneuert. Für MQL/Vantage ist die Übernahme der vorhandenen neuen Builds und anschließend die tatsächliche Historienaktualisierung weiterhin offen; der zusätzliche Robo-Fix benötigt ebenfalls die Verwendung seines neuen Builds. Ein pauschaler Neubau und Neustart aller fünf Dienste folgt aus den Befunden nicht.

Es gab in dieser Nachprüfung nur begrenzte lokale GETs, Read-only-Datenbankzugriff, synthetische Regressionen und Builds. Kein produktiver Update-POST, Plattformdownload, Scan, Terminal-/Modellaufruf oder Prozessneustart wurde ausgeführt. Die produktive Gesamtabnahme bleibt ein eigener kontrollierter Lauf. Konfigurierte DD-Grenze 50 %, Jahres-Calmar, H1-Nenner, SL-Neutralität und Forensikversion 19 wurden nicht geändert.

Vollständige Composite-Identität, Artefakt-Frischemetadaten und die bereits dokumentierten Kontraktnachweise bleiben gesonderte offene Aufgaben. MqlRealmonitor und PelicanWinnerLooser bleiben auftragsgemäß zurückgestellt.
