# Prüfung der Downloads des Datenflusses und der Tabellen

Stand: 18.10.2026. Scanner-Commit: `1bda2fa003a3be8cd924456284f7e8bd8ac048a8`.

**Der Gesamtworkflow besteht die Prüfung nicht.** Vier erhebliche Fehler betreffen die Erneuerung von Historien, die Bindung von Befunden an Trade-Dateien und die Übernahme unvollständiger Kataloge. Zwei weitere Fehler betreffen erläuternde Texte. Der vorhandene Bestand ist intern überwiegend konsistent; seine Aktualität und Vollständigkeit sind dadurch nicht belegt.

Die Spaltenzuordnung beider Tabellen besteht den automatisierten Bestandsvergleich. Leere Kennzahlen sind vielfach sachlich erforderlich: Es fehlen Trade-Dateien oder belastbare Währungs-/Kapitalnachweise, oder die Workflow-Forensik ist veraltet. Das bloße Auffüllen solcher Zellen wäre falsch.

## Umfang und Nachweise

Geprüft wurden alle fünf aktiven Quellen, ihre lokalen REST-APIs, die Scanner-Pipeline, SQLite, Artefaktdateien, H1-Kursbestand und die Ansichten „Alle Signale“ und „Ergebnisse“. Drei parallele Prüfbereiche deckten Quellen, Persistenz und Tabellen ab; die Zusammenführung enthält zusätzlich eine Mengenbilanz und eine Reproduktion fehlerhafter Pagination.

Produktive Zugriffe bestanden aus lokalen GET-Abfragen und lesenden Bestandsprüfungen. SQLite wurde mit der Backup-API einschließlich des konsistenten Datenstands gesichert. Anwendungsimporte mit möglichen Schreibzugriffen und alle Fehlerproben verwendeten zusätzliche temporäre Datenbanken. Es wurden keine produktiven Update-POSTs, neuen Plattformdownloads, Voll-/Teilscans, LLM-Aufrufe oder Terminalstarts ausgeführt. Produktivcode und fachliche Bewertungsregeln blieben unverändert. MqlRealmonitor und PelicanWinnerLooser blieben außerhalb des Auftrags.

Die Nachweise unterscheiden aktuellen Betrieb, isolierte Reproduktion und historischen Bestand. Die Schutzmechanismen und Zahlen eines vollständig neuen Plattformdownloads sind noch durch einen solchen Lauf abzunehmen; ein aktuell meldender `idle`-Status ersetzt das nicht.

## Urteil je Quelle

| Quelle | Live-Katalog | Gespeicherter Quellenkatalog | Urteil im geprüften Umfang |
|---|---:|---:|---|
| MqlDownloader `mql5` | 216 Rohzeilen, 215 gültige IDs | 215 | Fehlerhaft: Trade-Update kann innerhalb der Katalogfrist vollständig entfallen. CSV-Import in drei GET-Stichproben erfolgreich. |
| Pelican `pelik` | 640 | 640 | Lokale Pagination und drei CSV-Stichproben bestanden. Scannerdateien teilweise älter als die verfügbaren Quellenexporte; vollständiger neuer Plattformdownload nicht ausreichend belegt. |
| Vantage `vant` | 199 | 199 | Fehlerhaft: Alle 199 gelisteten Historien besitzen gesperrte Altmetadaten; normaler Erneuerungsweg ebenfalls blockiert. Vier konkrete Trade-GETs liefern 404. |
| Robo `robo` | 200 | 200 | Lokale Pagination und vier CSV-Stichproben bestanden. Scannerdateien teilweise älter als Quellenexporte; vollständiger neuer Plattformdownload nicht ausreichend belegt. |
| Zulu `zulu` | 200 | 200 | Pagination und drei CSV-Stichproben bestanden. Mindestens eine Stichprobenhistorie unvollständig; erläuternder Quellenhinweis geht beim Mapping verloren. |

Alle fünf APIs waren erreichbar. Mit Seitengröße 73 wurden ihre gemeldeten `total`-Umfänge ohne doppelte `(ID, Version)`-Identitäten gelesen. Die Differenz beim MqlDownloader ist vollständig erklärt: `test_1/mql4` ist keine numerische Signal-ID und wird korrekt verworfen. `health.providers=236` zählt zusätzlich 20 Provider ohne Abonnenten; der Standardkatalog enthält nur Provider mit Abonnenten.

17 Trade-GETs lieferten 13 gültige CSVs und die vier genannten Vantage-404. Alle 13 Lieferungen wurden im Arbeitsspeicher mit dem produktiven Parser gelesen. Native MQL-Beträge bleiben in ihrer Kontowährung; beispielsweise ist das Netto von MQL-Signal 2379208 JPY und kein USD-Betrag.

Nachweise: [Quellenbericht](nachweise/downloads_README.md), [Live-Pagination](nachweise/downloads_live_probe.json), [Exportstichproben](nachweise/downloads_e2e_live.json), [Vantage-Bestand](nachweise/downloads_vantage_metadata.json).

## Mengenbilanz

Die folgende Auswahl wurde mit den aktuell geladenen REST-Katalogen und den produktiven Auswahlfunktionen berechnet. Sie ist eine Auswahlprobe, kein ausgeführter Scan. Der produktiv eingestellte Mischmodus ergänzt MQL5-Direktlisten; deren heutiger Umfang wurde nicht neu abgerufen.

| Quelle | Gültige Eingänge | Vorfilter bestanden einschließlich Fix | Vorfilter abgelehnt | Normale Slots | Fix zusätzlich | Ohne Slot |
|---|---:|---:|---:|---:|---:|---:|
| mql5 | 215 | 6 | 209 | 0 | 6 | 0 |
| pelik | 640 | 436 | 204 | 30 | 4 | 402 |
| vant | 199 | 67 | 132 | 30 | 2 | 35 |
| robo | 200 | 164 | 36 | 30 | 3 | 131 |
| zulu | 200 | 191 | 9 | 30 | 0 | 161 |
| Gesamt | 1454 | 864 | 590 | 120 | 15 | 729 |

Die 209 regulär abgewiesenen MQL-REST-Kandidaten haben keinen Altersbeleg `weeks`; die sechs vorhandenen Fix-IDs umgehen diesen Vorfilter. Das ist das konfigurierte Verhalten, kein nachgewiesener Verlust beim Download. Für Pelican sind 198 Kandidaten zu jung und sechs ohne Altersbeleg; bei Vantage sind es 120 beziehungsweise zwölf. Robo und Zulu werden hier ausschließlich wegen des Mindestalters abgewiesen. Die genaue Entscheidung für jede gültige Eingangs-ID steht in [flow_inventory.json](nachweise/flow_inventory.json).

Die REST-Auswahl umfasst damit 135 Signale. Ihr Verhältnis zum Altbestand ist gesondert ausgewiesen; ausgewählt bedeutet nicht neu geprüft oder gespeichert. Der letzte gespeicherte Scan vom 16.10.2026 umfasst 15 Ergebnisse, davon damals 13 vollständige Befunde und zwei Fehler. Diese historischen Erfolgsmerkmale ersetzen keine heutige Versionsprüfung.

Für die Tabellen gilt:

| Bestand oder Ansicht | Zeilen |
|---|---:|
| Quellenkatalog | 1454 |
| Gespeicherte Workflow-Signale und Ansicht „Ergebnisse“ | 194 |
| Zusätzliche Katalogzeilen ohne übernommene Workflow-ID | 1283 |
| Ansicht „Alle Signale“ | 1477 |

„Alle Signale“ vereinigt den Quellenkatalog mit gespeichertem Workflowbestand. Ältere Workflow-Signale bleiben deshalb sichtbar, auch wenn sie nicht mehr im aktuellen Quellenkatalog stehen. Es wurden im aktuellen Quellenkatalog keine quellenübergreifenden numerischen ID-Kollisionen festgestellt. Die vollständige zentrale Composite-Identität bleibt eine bekannte offene Architekturaufgabe.

## Bestätigte Fehler

### F1 Vantage kann den gesperrten Altbestand nicht erneuern

**P1, aktuelle Auswirkung und isolierte Reproduktion.** Sämtliche 199 aktuell gelisteten IDs haben vorhandene CSVs mit `version=1` und ohne `timeBasis=UTC`. Der gesamte lokale TradeStore enthält 611 solche Metavermerke. Die vier geprüften Exporte 1419494, 1286742, 1010186 und 1096166 liefern 404.

Der UTC-Schutz ist erforderlich. Der Fehler liegt im fehlenden Erneuerungspfad: `TradeStore.mergeHistory` lehnt bestehenden unverifizierten Inhalt ab, und `saveTrades` ruft diese Prüfung erneut auf. Der reguläre Updatepfad verwendet dieselben Methoden. Gegen die tatsächlich kompilierten Klassen werfen auch gültige neue Datensätze beide Sperren; der Altbestand bleibt erhalten.

Codeorte: [TradeStore.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:129), [Speicheraufruf](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:85), [Update-Anbindung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:390).

Korrektur: Eine kontrollierte Archivierung des Altbestands und den Aufbau einer getrennten, belegten UTC-Historie ermöglichen. Alte Zeitstempel nicht lediglich als UTC umetikettieren. Nachweis: [Java-Probe](nachweise/downloads_VantageRefreshProof.java), [Laufergebnis](nachweise/downloads_vantage_freshness_runtime.txt).

### F2 Befund und gespeicherte Trade-Datei können auseinanderfallen

**P1, über echte Produktivfunktionen isoliert reproduziert; produktiver Eintritt nicht nachgewiesen.** Die Pipeline analysiert einen veränderlichen Cachepfad. Erst beim späteren Speichern erzeugt sie einen unveränderlichen Snapshot und bindet den Befund an dessen SHA. Ein manuelles Nachladen kann die Datei dazwischen ersetzen, auch während das gemeinsame Scan-Lock gehalten wird.

Die Reproduktion erzeugt einen erfolgreichen Befund über zwei Trades mit 50,0 % Winrate, speichert aber einen Export über drei Trades mit 66,7 % Winrate. Der Befund erhält den SHA der zweiten Datei und wird beim Neuladen als aktuell akzeptiert. Dadurch können Tabellenwerte und ihr gespeicherter Beleg widersprechen.

Codeorte: [Analyse](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:1795), [späteres Speichern](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:2110), [SHA-Bindung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py:395), [manuelles Nachladen](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/app_pages/alle_signale.py:662).

Korrektur: Die Eingabebytes vor der Analyse unveränderlich sichern, exakt diesen Snapshot analysieren und denselben SHA bis zur Speicherung prüfen. Den manuellen Nachladeweg zusätzlich mit den erforderlichen Lauf-/Artefaktsperren koordinieren. Nachweis: [Reproduktionsskript](nachweise/persistenz_probes.py), [Ergebnis](nachweise/persistenz_probes.json).

### F3 MqlDownloader überspringt angeforderte Tradeupdates

**P1, im kompilierten Code isoliert reproduziert; heute kein produktiver Skip ausgelöst.** Bei einem Katalogvermerk innerhalb der 72-Stunden-Frist beendet die GUI-Methode die gesamte Kaskade mit `done`. Die angeforderte Aktualisierung der Tradehistorien entfällt ebenfalls. Der Scanner sendet jedoch `tradelisten=True`; die Katalogfrist soll das Trade-Delta nicht verhindern.

Die Probe gegen die vorhandene kompilierte Methode verwendet einen eine Stunde alten Vermerk: `katalogUebersprungen=true`, `state=done`, keine Katalog- oder Tradeanforderung. Damit können auf einen Gesamtdownload folgende Tagesläufe neue Trades bis zum Ablauf der Katalogfrist übergehen.

Codeorte: [Frische-Skip](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java:151), [Scanner-Anforderung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/client_updates.py:218).

Korrektur: Katalogabruf und Aktualisierung bekannter Historien getrennt steuern. Nachweis: [Java-Probe](nachweise/downloads_MqlFreshnessProof.java), [Laufergebnis](nachweise/downloads_mql_freshness_runtime.txt).

### F4 Ein Teilkatalog wird als vollständiger Ersatz übernommen

**P1, synthetisch mit echter Ingest-/SQLite-Kette reproduziert; heute keine unvollständige API-Pagination beobachtet.** `hole_katalog` akzeptiert eine leere Seite auch dann, wenn `total` weitere Einträge erwarten lässt. Auch das Erreichen der Seitenkappe liefert die bisherige Liste ohne Unvollständigkeitskennzeichnung. `katalog.sync` behandelt diese Liste anschließend als Vollbestand und löscht daraus fehlende IDs.

Reproduktion: Die Datenbank enthält IDs 1, 2 und 3. Die API meldet `total=3`, liefert zunächst 1 und 2 und danach eine leere Seite. Ergebnis: ID 3 wird gelöscht, der Sync meldet zwei übernommene Einträge und keinen Fehler.

Codeorte: [Pagination](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py:71), [Übernahme](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py:79), [Löschen fehlender IDs](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py:855).

Korrektur: Abschluss und Grenzen der Pagination explizit prüfen. Unvollständige oder widersprüchliche Lieferungen dürfen keine Vollersetzung mit Löschungen auslösen. Nachweis: [Probe](nachweise/pagination_repro.py), [Ergebnis](nachweise/pagination_repro.json).

### F5 Ein Zulu Hinweis zur Historie geht verloren

**P2, tatsächliche Liveantwort gegen produktives Mapping geprüft.** Zulu liefert den Text unter `TradesCompletenessNote`; der Scanner liest ausschließlich `CompletenessNote`. Bei Signal 430306 enthält der Export 1164 Trades gegenüber einem Plattformgesamtwert von 8992. Der Quellenhinweis zur möglichen Kappung beziehungsweise zum älteren Datenstand wird zu einem leeren String. Die gesonderte Kappungsflagge bleibt erhalten.

Codeorte: [Zulu-Feld](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor/src/main/java/de/zulumonitor/rest/RestApiServer.java:418), [Scanner-Mapping](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py:408), [Tabellenhinweis](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/alle_signale_ui.py:159).

Korrektur: Den Feldvertrag vereinheitlichen oder beide belegten Feldnamen übernehmen und den Hinweis bis zur Anzeige prüfen. Nachweis: [Exportstichproben](nachweise/downloads_e2e_live.json), Abschnitt `zulu`, ID 430306.

### F6 Der Hilfetext beschreibt eine falsche Drawdownbasis

**P3, Widerspruch zwischen Anzeigehilfe und implementiertem Wert.** Die Hilfe zur Ergebnisspalte Max-Drawdown nennt Kursnachmessung oder Monitor als mögliche Basis. `_equity_messwerte` verwendet für diesen Wert ausschließlich eigene H1-Messung. Der Monitorwert ist ein Closing-DD und ein anderer Kanal der harten Schranke. Der geprüfte Zahlenwert wird dadurch nicht falsch befüllt; seine Erklärung ist falsch.

Codeorte: [Hilfetext](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/app_ui.py:503), [Wertbildung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:275).

Korrektur: Hilfe und tatsächliche H1-Messbasis in Einklang bringen; Monitor-Closing-DD weiterhin als eigenen Schrankenkanal erklären.

## Tabellenwerte und leere Zellen

Der vollständige Bestandsvergleich umfasst 2134 Prüfungen von DB-Metadaten gegen Ergebnisfelder, 194 Calmar-Prüfungen und 2232 Vergleiche geparster Trade-Statistikfelder. Dabei wurden **keine Abweichungen** gefunden. Die Prüfung berücksichtigt unter anderem fehlende Werte gegenüber echten Nullen, Rundung, Quellenzuordnung, die konkrete PF-/Winrate-Basis des Projekts und vorbehaltliche Anzeigen. Dies ist ein Daten- und AppTest-Nachweis; eine manuelle Sichtprüfung jeder gerenderten Browserzelle wurde nicht durchgeführt.

Das vollständige Spaltenmapping steht in [tabelle_spaltenmapping.md](nachweise/tabelle_spaltenmapping.md); die maschinenlesbaren Ausdrücke und Zeilennummern stehen in [tabelle_spaltenmapping.json](nachweise/tabelle_spaltenmapping.json). Null-/Nullwertprofile sämtlicher 35 Ergebnisfelder und 28 Felder der Gesamtübersicht stehen in [tabelle_bestand.json](nachweise/tabelle_bestand.json).

Belegte Gründe für fehlende oder vorbehaltliche Werte sind 128 Zeilen ohne Tradepfad, 242 USD-Sperren, 161 als veraltet erkannte Workflow-Forensiken sowie fehlende positive Kapitalbasis und Teilstatistiken. 945 Zeilen haben eine virtuelle Equity-Basis, 249 eine vorbehaltliche Calmar-Anzeige. Diese Zähler überlappen und dürfen nicht addiert werden. Registrierte Trade-Dateien der Gesamtübersicht fehlen nicht und weisen keine SHA-Abweichung auf.

Die 25 Statistikdiagnosen sind eingegrenzt: 15 gelieferte CSVs enthalten Trades mit Schlusszeit vor Öffnungszeit und werden absichtlich nur als Finanzteilstatistik ohne DD-/Renditefreigabe behandelt. Zehn weitere lesbare Exporte enthalten keine Trades; deren belegte Tradezahl ist 0. Die unplausiblen Zeitintervalle sind ein Datenproblem, dessen Ursprung diese Prüfung nicht abschließend zuordnet. Ein zusätzlicher Parserfehler ist daraus nicht nachgewiesen. Details: [Statistikdiagnosen](nachweise/tabelle_statistik_diagnosen.json).

Der aktuelle DB-Reload weist für keine der 194 Workflow-Zeilen eine aktuelle vollständige Forensik aus. Die gespeicherten Befunde haben alte oder unbekannte Versionen; alle 194 Signalstammsätze besitzen noch keinen gespeicherten aktuellen Währungsnachweis. Das führt beim aktuellen Code zu 106 roten, 70 weißen und 18 ausgeschlossenen Signalen, ohne Grün oder Gelb. Das Schutzverhalten besteht. Separat gespeicherte Equity-Studien sind ein anderer Datenkanal: 1354 haben Version 19, 218 Version 0. Die veraltete Workflow-Forensik macht diese Studien nicht pauschal veraltet.

In der Ergebnistabelle sind entsprechend Score, eigene Monatsrendite, H1-Max-DD, TrueRetDD und Berichtsdatum jeweils in allen 194 Zeilen leer. Historisch gespeicherte Gesamtberichte werden nur dann wieder als aktuelle Berichte eingebunden, wenn sie zur gültigen Forensikbasis passen. Die Gesamtübersicht kann dagegen aktuelle separate Studien und belegte Vorstufenwerte anzeigen. 23 Workflow-Signale liegen außerhalb des heutigen Quellenkatalogs und bleiben als Bestand sichtbar.

AppTest und vorhandene Tests bestätigen Filter/Sortierung, passende Zeilenauswahl, dieselbe gefilterte Zeilenmenge für Tabellen und CSV, Frischemarkierungen, Session-Übernahme sowie den Abschlussrefresh von Studien. Drei ergänzte UI-Tests prüfen Auswahlwechsel nach Filter/Quellenwechsel und das Verwerfen alter Statistik bei neuen CSV-Bytes und neuem SHA am gleichen Pfad.

## Integrität und Datenfrische

Beide SQLite-Datenbanken bestehen `quick_check`. Alle 193 gespeicherten Workflow-Trade-Dateien und 3094 Quellenartefakte stimmen mit ihren hinterlegten SHA-Werten überein. Alle 1550 Metrics-Dateien sind lesbar; Signal-ID und Version passen zu ihrer Artefaktzuordnung.

Der Kursbestand umfasst 10095805 H1-Bars aus drei getrennten Terminal-/Serverfeeds und 1852 Abrufversuche. In den Bars wurden keine Abweichungen vom Stundenraster und keine geprüften OHLC-Widersprüche gefunden. Das bestätigt den vorhandenen Bestand, nicht die Abdeckung jedes möglichen Handelsfensters. Die gezielten Kursdaten-/Locktests bestehen; neue reale Terminalabrufe waren nicht Teil dieses Laufs.

Die Scanner-Caches sind gegenüber manchen lokal verfügbaren Quellenexporten veraltet. Beispiele: Pelican 2014074 hat beim Quellen-GET 15599 gegenüber 15340 Trades im Scanner-Cache; Robo 21596244 hat 38 gegenüber 20; Zulu 402995 hat 5725 gegenüber 5717. Das ist ein aktueller Zustandsunterschied. Ohne neuen Scan beweist er keinen weiteren Cachefehler.

Drei historische Fremdschlüsselverletzungen betreffen ausschließlich Analysezeilen 36 bis 38 zur nicht vorhandenen ID 424242 vom 05.09.2026. Sie erscheinen nicht als Signalzeilen. Aktuelle Schreibtests prüfen den Fremdschlüsselschutz erfolgreich. Die Altzeilen wurden nicht bereinigt.

163 vorhandene Trade-Dateien mit altem Workflowbefund wurden neu geparst. Bei 150 stimmen alle vorhandenen Vergleichsfelder überein; 13 Altbefunde unterscheiden sich von heutigen Berechnungen. Weil kein solcher Befund die aktuelle Forensikversion hat, belegen diese Differenzen keinen zusätzlichen aktuellen Berechnungsfehler.

Eine zusätzliche isolierte Robustheitsprobe zeigt: Ein nachträglich gelöschter Snapshot wird beim normalen DB-Reload nicht durch Dateiprüfung erkannt. Produktiv sind alle referenzierten Trade-Dateien vorhanden. Diese Beobachtung wird deshalb getrennt vom heutigen Bestandsurteil geführt.

## Tests und Reproduktion

| Prüfgruppe | Bestandene Tests | Nachweis |
|---|---:|---|
| Quellen, REST, Stufe 0 | 136 | [Log und Befehl](nachweise/downloads_tests.txt) |
| Pipeline, Persistenz, Währung, Retry | 173 | [Log](nachweise/persistenz_pytest.log), [JUnit](nachweise/persistenz_pytest.xml) |
| Beide Tabellen, Katalog, Refresh | 104 | [Befehl und Ergebnis](nachweise/tabelle_pytest_lauf.txt), [JUnit](nachweise/tabelle_pytest.xml) |
| Kursdaten, Locks, H1, Exportartefakte | 161 | [Log](nachweise/kursdaten_pytest.log), [Befehl](nachweise/kursdaten_pytest_command.json), [JUnit](nachweise/kursdaten_pytest.xml) |
| Zusätzliche UI-Proben | 3 | [Testcode](nachweise/tabelle_audit_tests.py), [JUnit](nachweise/tabelle_audit_tests.xml) |

Damit bestehen 574 gezielte vorhandene Tests und drei ergänzende UI-Tests. Die zusätzlichen Fehlerproben sind gezielte Reproduktionen; deren Exitcode 0 bedeutet, dass der behauptete Fehler reproduziert wurde. Die gesamte Testsuite und die kostenpflichtigen LLM-Tests wurden nicht ausgeführt.

Die beiden Teilberichte enthalten genaue Befehle und Grenzen: [Downloads](nachweise/downloads_README.md), [Persistenz](nachweise/persistenz_README.md). Der Bestandsabgleich wird über [inventory_probe.py](nachweise/inventory_probe.py), [flow_probe.py](nachweise/flow_probe.py), [persistenz_bestand.py](nachweise/persistenz_bestand.py) und [tabelle_bestandsaudit.py](nachweise/tabelle_bestandsaudit.py) reproduziert. Produktive Rohtrades, Datenbanken und Zugangsdaten gehören nicht in diese Reviewablage.

Der [Manifestnachweis](nachweise/manifest.json) enthält Testzahlen, Commitstände sowie Hashes der relevanten Scannerquellen und aller Reviewdateien. Er dokumentiert den Zustand dieses Prüfzeitpunkts.

## Temporäre Prüfkopien

Die großen konsistenten Eingangskopien liegen außerhalb des Repos im in `inventory.json` bezeichneten privaten Tempverzeichnis. Für eine erneute Bestandsprüfung kann `inventory_probe.py` neue Kopien erzeugen. Eine zusätzliche private Kopie aus einem ersten Tabellen-Prüfprototyp blieb unter `C:/Users/tnickel/AppData/Local/Temp/signal_table_audit_tfg8q1tr` zurück. Die automatische Freigabeprüfung lehnte den geprüften Löschbefehl mit `blocked by policy` ohne weitere Begründung ab. Er wurde nicht über einen anderen Löschweg umgangen. Die fertigen nachfolgenden Tabellenläufe räumten ihre eigenen Kopien auf.

## Reihenfolge der Korrekturen

Zuerst die kontrollierte Vantage-Erneuerung und die unveränderliche Analyseeingabe herstellen. Anschließend MQL-Tradeupdates von der Katalogfrist trennen und unvollständige Katalogersetzung verhindern. Danach den Vollständigkeitshinweis und den Drawdown-Hilfetext korrigieren. Erst mit diesen Änderungen sollte ein kontrollierter neuer Gesamtlauf Quellenaktualisierung, Scannerpersistenz und Tabellenfüllung gemeinsam abnehmen.
