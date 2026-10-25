# F3 behoben: MQL-Katalogfrische trennt sich von Trade-Aktualisierung

Stand: 18.10.2026, 12:43 Uhr Europe/Berlin. Zuständigkeit dieses Teilfixes ausschließlich Nachbarrepository `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader`; keine Scanner-Quelldateien geändert. Das Repository war vor diesen Änderungen sauber.

## Verhalten

| Katalog | `tradelisten` | Verhalten |
|---|---|---|
| jünger als Frist, bekannte gültige Anbieter vorhanden | true | Bestehende MT4-/MT5-Anbieter aus dem gespeicherten Katalog aktualisieren; kein erneuter Crawl der Toplisten. Providerseite und CSV werden frisch geladen. |
| jünger als Frist | false | Bekannten Katalog übernehmen, keine Downloads und keine Konvertierung. |
| alt/fehlend oder kein gültiger bekannter Scope | true | Regulärer MT4-/MT5-Listencrawl, Providerseiten und Trade-CSVs, danach Konvertierung. |
| alt/fehlend oder kein gültiger bekannter Scope | false | Regulärer Katalog-/Providerseiten-Download und Konvertierung ohne Trade-CSV-Abruf. |

Der Stufe-0-Pfad umgeht den bestehenden lokalen Dateialterscache (Default fünf Tage). Andernfalls würde auch nach Beseitigung des 72-Stunden-Gesamtskips weiterhin keine neue Historie geladen. Die manuellen GUI-Downloadbuttons behalten ihre bisherige Dateicache-Politik.

Ein Trade-Update mit frischem Katalog schreibt dessen Entdeckungszeitpunkt nicht neu. So kann eine Folge täglicher Trade-Updates die nächste Katalog-Discovery nicht unbegrenzt hinausschieben. Neue/aktualisierte CSVs werden erst nach erfolgreichem Export gezählt. Teilfehler erhalten tatsächlich abgeschlossene Zähler. Stop setzt diese Zähler nicht zurück und ein während des Exports abgebrochener Provider wird nicht als abgeschlossen gezählt. Konvertierungsfehler erzeugen weiterhin einen Fehlerjob, werden aber nicht als erfundene Tradefehler oder Tradeabbrüche gezählt.

Bekannte Anbieter werden nach numerischer Signal-ID, MQL-Version und vorhandenen Abonnenten ausgewählt. Nichtnumerische Test-IDs wie `test_1` erreichen den bekannten Exportpfad nicht. Ein bekannter Scope wird nicht nach einem Discovery-Limit abgeschnitten.

## Änderungen

- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/ClientUpdateRunner.java`: neue, isoliert testbare Stufe-0-Orchestrierung mit Katalog-Scope, booleschem Tradeauftrag, Frischevermerk und Ergebniszählern.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java:115`: wertet `tradelisten` aus und bindet den Runner an vorhandene Download-/Konvertierungsmanager und Busy-Schutz.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/DownloadManager.java:62`: Stufe-0-Einstieg für gespeicherte oder neu entdeckte Anbieter; echte Fortschritts- und CSV-Zähler; Teilresultate bleiben auch nach Fehler/Stop erhalten.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/downloader/SignalDownloader.java:64`: Stufe-0-Modus nutzt bestehenden Login-/Provider-/Exportcode, erzwingt den frischen Abruf und kann ausschließlich bekannte Anbieter verarbeiten. `tradelisten=false` greift nicht auf den CSV-Export zu.
- Zwei neue Testklassen: `tests/gui/ClientUpdateRunnerTest.java` (8 Fälle) und `tests/downloader/SignalUpdateModeTest.java` (6 Fälle).

## Validierung und verteilbares Artefakt

Arbeitsverzeichnis jeweils `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader`.

```powershell
mvn '-Dtest=ClientUpdateRunnerTest,SignalUpdateModeTest,UpdateVermerkTest,UpdateEndpointTest,DownloadFilesTest' test -q
mvn package
git diff --check
```

Maßgeblicher letzter Gesamtlauf: **140 Tests, 0 Fehler, 0 Fehlversuche, 0 übersprungen; BUILD SUCCESS, Exitcode 0**. Enthalten sind 14 neue Regressionen. Ausgabe mit Befehl/Exitcode: `fix_mql_package.txt`. Der erste gezielte grüne Lauf mit damals 26 Fällen steht in `fix_mql_targeted_tests.txt`; der Gesamtlauf enthält zusätzlich die anschließend ergänzte Stop-während-Export-Regression.

Die neuen Tests verwenden ausschließlich synthetische temporäre Daten und einen In-Memory-WebDriver. Sie prüfen tatsächlichen Dateiersatz trotz jungem Cache, den Metadatenlauf ohne CSV-Zugriff, neue/aktualisierte Zähler, alten/frischen Katalog, Ein-Versions-Scope, fehlende Exportlinks, Konvertierungsfehler, Teilfehler und Stop. Kein Browser oder externer MQL-Abruf wird dabei gestartet.

Verteilbares JAR: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar`.

- Größe: 51.256.532 Bytes.
- SHA-256: `9ADC331273FBED9CA8A5BC3830792D85D8798DBA3DDD4C27796F2B96BF4F8605`.
- Build beendet: 18.10.2026, 12:43:06 Europe/Berlin.
- Maschinenlesbar: `fix_mql_artifact.json`.

## Betriebsgrenzen

Es wurden keine laufenden Anwendungen neu gestartet oder beendet, keine Update-POSTs oder produktiven Downloads ausgeführt und keine produktiven Konfigurationen/Daten geändert. Der Fix ist gebaut, aber die bereits laufende JVM ist damit nicht als aktualisiert abgenommen. Ein kontrollierter Neustart und anschließend beobachteter echter Stufe-0-Lauf bleiben Betriebsprüfung des Hauptauftrags.

Frische Tradeupdates verursachen nun die tatsächlich angeforderten Requests. Bestehende Rate-Limits, Pausen, Login und Exportvalidierung bleiben aktiv; bei vielen bekannten Anbietern kann die reale Dauer entsprechend hoch sein. Die vorhandenen Discovery-Limits bleiben konfigurationsgeführt. Ein fehlgeschlagener CSV-Export bewahrt die alte Historie; es wird keine synthetische Vollständigkeit oder Aktualität behauptet.
