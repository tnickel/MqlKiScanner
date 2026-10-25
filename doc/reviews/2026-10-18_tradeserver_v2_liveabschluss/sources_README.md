# Quellenclients und produktive Aktualisierung, 18.10.2026

Aktuelle Einordnung: Vantage hat fuenf vollstaendig erneuerte FT-Provider mit
exakter GET-only-REST-Abnahme; weitere 14 Vollhistorien laufen. Robo hat einen
zusaetzlichen kritischen Einheitenbefund: Rohgeld ist nicht pauschal USD,
gespeichertes Volumen nicht pauschal Lots. Der neue isoliert gebaute und mit
195 Tests gepruefte Vertrag sperrt daher Scanner-CSV und Closing-DD, behaelt
native Daten und korrigiert GUI-/LLM-Beschriftungen. Details unter
`sources_robo_units_README.md`. Der alte Robo-Job ist mit 20 Fehlern beendet
und append-only als teilweise dokumentiert; 17 unzulaessige MT-Altbestands-
Historien werden nach normalem Exit und verifiziertem Offlinebackup erneut
vollstaendig geladen. Drei RStocks bleiben ausdruecklich nicht unterstuetzt.
Eine erfolgreiche Rohdatenaktualisierung ist kein Einheiten-/Forensiknachweis.

Die unten beschriebenen Builds und `sources_builds.json` /
`sources_code_manifest.json` sind datierte Zwischenstaende, keine aktuellen
Aktivierungsfreigaben. Massgeblich sind die jeweiligen neuesten Quellenbelege
und `sources_current_progress.json`; fuer Robo der neue
`sources_robo_units_build_receipt.json`. MQL/Pelican/Zulu werden inzwischen
von den jeweiligen anderen Teilauftraegen mit eigenen Abschlussbelegen betreut.

Der Nutzer hat Aktualisierungen der laufenden Clients und echte Quellenupdates
ausdruecklich beauftragt. Dieses Teilpaket fuehrt weder Scannerbewertungen noch
Studien oder LLM-Aufrufe aus. Zugangsdaten, Cookies, DBs und Tradelisten bleiben
ausserhalb der Reviewdateien.

Der aktuelle Versuch je Quelle steht in `sources_current_progress.json`
(automatisch aus den neuesten Belegen aktualisiert). `sources_live_progress.json`
beschreibt weiterhin den urspruenglichen Sammellauf; spaetere Reparaturversuche
haben eigene Job-IDs und eigene unveraenderte Abschlussbelege. Ein spaeterer
Erfolg hebt einen dokumentierten frueheren Fehler nicht rueckwirkend auf.

## Aktivierter Anfangsstand

Die produktive Scannerregistry nennt fuenf lokale Quellen: MqlDownloader
`mql5:8089`, Pelican `pelik:8090`, Vantage `vant:8092`, Robo `robo:8091`, Zulu
`zulu:8093`. Alle antworteten vor dem Eingriff mit Health `ok` und Job `idle`.
MqlRealMonitor und PelicanWinnerLooser wurden nicht angefasst.

Vantage, MqlDownloader und Robo liefen in alten JVMs aus den Projektcheckouts.
Die zugehoerigen Fenster wurden gezielt geschlossen, das Prozessende wurde
bestaetigt. Danach wurden private Runtimekopien inklusive lokaler Historien,
Konfiguration und DBs angelegt. Die Belegdatei `sources_backup_receipt.json`
enthaelt nur Pfad, Dateizahlen, Groessen und Hash des privaten Manifests.
Robo liegt zusaetzlich unter demselben privaten Backupordner in `robo_data/`.

Nach `mvn test package` wurden die drei Clients per `Start-Process
-WindowStyle Hidden` mit ihren bisherigen Arbeitsverzeichnissen und Settings
gestartet. Vantage und Robo verwenden die vorherigen direkten Javaargumente;
MqlDownloader verwendet das konkret getestete Fat-JAR `0.0.35-SNAPSHOT`.
Die neuen PIDs und anschliessenden Healthbelege stehen in
`sources_restart_receipt.json` und `sources_after_restart.json`.

Die urspruengliche Buildabnahme: Vantage 88, MqlDownloader 148, Robo 185 Tests,
jeweils null Fehler. Spaetere Reparaturerweiterungen sind gesondert aufgefuehrt
und erst nach einem weiteren Neustart in der betreffenden JVM aktiv.

## Laufende Stufe 0

`sources_run_updates.py` nutzt unveraendert den produktiven
`client_updates.starte_alle_updates`-Pfad. Fuer diesen ausdruecklichen
Aktualisierungslauf wurde die Katalogfrist im lokalen Settingsabbild auf 0
gesetzt: aktueller Katalog und Trades werden angefordert. Die produktive
72-Stunden-Einstellung bleibt erhalten. Ziel ist 200, Trades sind angefordert.
Der erste Aufruf scheiterte vor jeglichem Update-POST an Windows-stdout-Encoding;
nach explizitem UTF-8 wurde der Lauf gestartet. Keine doppelt gestarteten Jobs.

`sources_live_progress.json` ist ein veraenderlicher Zwischenstand, kein
Abschlussnachweis. `sources_live_result.json` wird erst nach Ende der
Ueberwachung geschrieben. Der Scanner erhaelt auch Start-/Abschlussbelege in
seiner `client_updates`-Chronik. Ein Ueberwachungstimeout beendet keinen
laufenden Clientjob und beweist keinen frischen Datenbestand.

MqlDownloader zeigt den konfigurierten Cap 4500 pro Plattform. Produktiv ist
`subscribersOnly=true`: nach Sortierung beendet der Client die Liste beim
ersten Provider ohne Abonnenten. Das ist kein beauftragter Vollabruf von 9000
Plattformprovidern. Der bisherige lokale Katalog umfasste 236 Provider, davon
216 mit Abonnenten. Diese Zahlen sind der Stand vor dem Update.

Laufzeitgrenzen sind reale API-Arbeit: Vantage drosselte nach 100429 adaptiv
auf 2300 ms/Request; Robo laedt bereits mehr als 20.000 Deals je Provider.
Zulu hat keine Stufe-0-Trade-Kappe; der fuenfte Provider `429450` meldet im
aktuellen Katalog 6.794.903 Trades. Diese Katalogzahl ist kein Nachweis der
bereits gelieferten Historie. Thread-Dumps belegen aktive HTTP-Arbeit; der
Zulu-Adapter verwirft bisher den inneren Seitenfortschritt. Daher kann der
sichtbare Providerzaehler lange stehenbleiben. Weder Kappen noch Frische- oder
Vollstaendigkeitsregeln wurden zur Laufzeitverkuerzung aufgeweicht.

## Vantage: gezielte vollstaendige Neuerhebung

Die normale GUI/Stufe 0 hat weiterhin einen 2.000-Batchdeckel und die normale
Einzelabfrage einen 20.000-Deckel. Diese Teilbestaende werden ueber
`TradesStored`, `TradesTotalAvailable`, `TradesTruncated` kenntlich gemacht.
Ein normaler erfolgreicher Job ersetzt keinen Vollstaendigkeitsnachweis.

Der vorhandene Java-Headless-Lader wurde um `--full`, `--force`,
`--resolve-missing`, `--data-dir=...` und `--fallback-catalog-dir=...` ergaenzt.
Der explizite Vollabruf paginiert bis zum Cursorende. Eine positive gemeldete
Gesamtzahl muss mit der frischen deduplizierten Historie uebereinstimmen.
Die Store-Veröffentlichung verwendet nur diese frischen Zeilen und sichert
die alte Rohgeneration gesondert. Alte Zeilen fuellen keine Luecken auf.
Unbekannte Counts, falsche IDs oder ungueltige Daten bleiben laute Fehler.
Fehlende Ranking-IDs werden nur auf ausdrueckliche Auswahl direkt nachgeladen;
ihre Kontowaehrung wird nicht mit USD vorbelegt. Unbestaetigte neue Provider
werden nicht als neue Katalogzeilen gespeichert.

`sources_vantage_repair_plan.json` nennt die stabile Quellen-UID und die
16 bestehenden Workflowkoepfe; zusammen mit den fuenf FT-IDs sind es 19
eindeutige Reparatur-IDs. Die fuenf FT-IDs fehlen bereits im gesicherten alten
Ranking, weshalb ein blosser Rueckgriff auf dessen 200 Provider nicht genuegt.
Das explizite direkte Nachladen ist hier erforderlich.

Regression: 91 Vantage-Tests, null Fehler. Die drei neuen Tests pruefen die
bewusste Ueberschreitung der GUI-Kappe, die Ablehnung eines falschen positiven
Gesamtcounts, die getrennte Sicherung einer alten verifizierten Generation
ohne Altdatenauffuellung und unveraenderte aktive Bytes bei fehlendem Beleg.
Liveausfuehrung und anschliessender Clientneustart stehen aus, solange der
aktuelle Vantagejob noch schreibt. Vorher keine Cachefreigabe fuer Studien.

## Robo: echter Fehler beim Liveupdate

Der alte Cache von `exactw #72166283` enthaelt 20.000 Zeilen, aber nur 19.999
eindeutige Tickets: eine exakt doppelte Zeile, kein Feldkonflikt. Seine
Bytekonsistenz beweist damit keine gueltige Dealidentitaet. Der bisherige
`mergeDeals`-Pfad brach an diesem Bestand ab und konnte eine gueltige neue
Lieferung nicht veroeffentlichen. Der aktuelle erste Job behaelt diesen
Teilfehler bei; er wird nicht nachtraeglich als fehlerfrei umetikettiert.

Der neue Erneuerungspfad prueft zuerst Besitzer und Plattform sowie saemtliche
frischen Daten. Ein inhaltlich ungueltiger Altbestand wird unveraendert unter
`deals/quarantine/` erhalten; er traegt keine Zeilen zur neuen Historie bei.
Leere oder ungueltige frische Lieferungen, unbekannte Besitzer und
Identitaetskonflikte bleiben gesperrt. Der normale API-Pfad paginiert bis zur
expliziten Endmarkierung. Inhaltsgleiche API-Seitenueberlappungen werden
dedupliziert, widerspruechliche gleiche IDs fuehren zu einem Fehler.

CSV und Meta werden gemeinsam vorbereitet und unter demselben Leser-/Writer-
Lock publiziert. Scheitert ein Teil der Veroeffentlichung oder wird sie
unterbrochen, werden alle urspruenglichen aktiven Bytes wiederhergestellt.
Fehler-Injektion nach der ersten Veroeffentlichung ist getestet.

Regression nach Erweiterung: 191 Robo-Tests, null Fehler (sechs neue Tests).
Das Update des laufenden Clients und die gezielte erneute Nachladung des
betroffenen Providers erfolgen erst nach Ende seines laufenden Jobs.
Bis zum Livebeleg bleibt Robo fuer die neue Scannerbewertung nicht freigegeben.

## MqlDownloader: echter Download-Namensfehler und erneuter Lauf

Der erste Livejob endete nach 48 MT4-Versuchen mit 48 Fehlern und keinem
uebernommenen Tradeexport. Die originalen Job-/Chronikbelege bleiben erhalten.
Die Ursache war der fruehere `DownloadFiles.findDownload`-Filter: er akzeptierte
nur `<ID>.csv`, waehrend MQL5 beim echten MT4-Abruf `<ID>.history.csv` liefert
(der gespeicherte Kopf entspricht dem erwarteten MT4-Orderbuch). Entsprechend
liefert MT5 `<ID>.positions.csv`. Der bisherige Browsertest schrieb kuenstlich
`101.csv` und hatte diese reale Benennung nicht abgedeckt.

Der Filter akzeptiert jetzt exakte ID plus passende Plattform-Endung sowie
Chromiums Duplikatzaehler unmittelbar vor `.csv`. Fremde IDs und die andere
Plattform werden nicht als Treffer angenommen; die bestehende Kopfpruefung
bleibt zusaetzlich aktiv. Der In-Memory-Exporttest schreibt nun das reale
`101.positions.csv`-Format, eine weitere Regression prueft beide Plattformen,
fremde IDs, unbekannte Versionen und `101.positions (2).csv`.

Zusaetzlich wurde eine reale Protokollierungsluecke behoben: statische Logger
legen vor `main()` einen Defaultcontext an; `Configurator.initialize` aktivierte
die vorhandene Datei dann nicht. `Configurator.reconfigure` uebernimmt jetzt
die bestehende Konfiguration. Ein Test prueft einen tatsaechlichen INFO-
Dateieintrag trotz bereits angelegtem Context. Keine neuen Logging-Settings.

150 MQL-Tests sind gruen. Nach bestaetigtem Ende des fehlgeschlagenen Jobs
wurde der getestete Build erneut gestartet (`sources_mql_fixed_restart.json`).
`sources_mql_fixed_update.py` startet ausschliesslich einen neuen MQL-Job;
die anderen Quellen werden nicht erneut ausgeloest. Er verwendet die regulaere
72-Stunden-Katalogfrist. Der echte gespeicherte Marker steht auf 11.10.2026,
also ist Discovery korrekt erforderlich. Es wurde kein Frischemarker erfunden.

Die ersten frischen Uebernahmen sind live belegt: `2306053`, `2349227` (Gold
Spike MT4) und `2327790` wurden am 18.10.2026 um 19:04:34, 19:04:46 und
19:04:57 MESZ gespeichert. Das beweist den reparierten Downloadpfad fuer diese
Provider, noch keinen Gesamtabschluss. Fortschritt und spaeteres Ergebnis
stehen getrennt in `sources_mql_fixed_update_progress.json` beziehungsweise
`sources_mql_fixed_update_result.json`. Der erste gescheiterte Lauf wird dadurch
nicht nachtraeglich fehlerfrei.

## Noch kein pauschaler Abschluss

Robo-Nachtrag zur Plattformwahrheit: Der reale Anfangslauf hat unter anderem
zwei RStocks-Provider als nicht unterstuetzt gemeldet. Die REST-Methode
`versionVon()` ordnete jedoch jede Nicht-MT5-Plattform als `mql4` ein. Der
neue getestete Code bewahrt `rst` beziehungsweise `unknown` im Katalog und
in den lesbaren Kennzahlen. Nicht unterstuetzte Tradeendpunkte bleiben mit
einem expliziten Grund gesperrt, Closing-DD unbekannt und alte MT4-/MT5-Pfade
abgewiesen. Ein Regressionstest legt dafuer absichtlich einen gueltigen alten
MT4-Cache samt DD-Bestaetigung an. 193 Maven-Tests sind gruen. Dieser Build
wird erst nach belegtem Ende des laufenden Robo-Writers aktiviert; derzeit
ist die neue Wahrheit noch nicht im laufenden alten REST-Prozess aktiv.

Nachtrag zum tatsaechlichen zweiten MQL-Lauf: 48 MT4- und 48 MT5-Exporte
wurden fehlerfrei neu geladen (0 Trade-Downloadfehler), anschliessend schlug
die globale Konvertierung bei 147 von 234 lokalen Profilen fehl. Fehlende
Monatsdaten machten den optionalen 3MPDD unbekannt; auch im aktivierten
Abonnentenmodus brach die Verarbeitung vor dem Schreiben aktueller Fakten ab.
Der getestete Fix behandelt diesen unbekannten Quotienten im Abonnentenmodus
als `NaN` und schreibt die belegten aktuellen Fakten. Im MPDD-Filtermodus
bleibt die bisherige strenge Fehlerbehandlung erhalten. 151 Maven-Tests sind
gruen, der neue Build ist als PID 1432312 aktiviert. Ein anschliessender
wirklicher lokaler Konverterlauf verarbeitete alle 234 Profile mit 0 Fehlern;
die urspruenglichen HTML-/Trade-Dateien bleiben dabei unveraendert. Der neue
regulaere REST-Updatejob wird separat unter `sources_mql_conversion_update_*`
protokolliert und muss fuer eine Gesamtfreigabe erst erfolgreich enden.

Fuer Gold Spike MT4 2349227 ist die Herkunft der frischen Rohdaten gesondert
belegt: Die am 18.10.2026 um 19:04:41 MESZ erneuerte lokale CSV und die REST-
Antwort sind bytegleich. SHA und genaue Zeilenarten stehen unter
`sources_mql_gold_spike_fresh_generation.json`. Das beweist den neuen
Tradeexport; der vorherige Konverterfehler wird dadurch nicht aufgehoben.

Die ersten vollstaendigen FT-Neuabrufe bei Vantage wurden absichtlich nicht
publiziert, weil ihre ueber Ordertickets deduplizierten Zahlen von den
Anbieterzahlen abwichen. Der nachfolgende vollständige Diagnoseabruf belegt
die konkrete Ursache: Die API-Datensatz-ID `id` ist eindeutig, das originale
`tradeOrderId` kommt mehrfach vor und fehlt bei Rohan 178177 sogar in 200
Zeilen. Alle fuenf FT-Historien erreichten mit eindeutigen Datensatz-IDs exakt
das gemeldete Total und das leere Cursorende; Details unter
`sources_vantage_history_identity_probe.json`. Unterschiedliche rohe
Datensaetze mit gleichem Orderticket sind keine Belege fuer doppelte Trades.

Der neue Client, beide Stores, der Closing-DD-Eingang und der Python-Lader
verwenden deshalb `HistoryRecordId`. Das originale Orderticket bleibt separat
erhalten; fehlende Tickets bleiben leer. Widerspruechliche Daten derselben
Historien-ID brechen den Abruf ab. Ein neuer Metadatenvermerk
`identityBasis=historyRecordId` verhindert, dass alte UTC-Caches ohne belegte
Zeilenidentitaet still mit neuen Daten vermischt werden. Die Tests pruefen
mehrfache/fehlende Ordertickets, beide Store-Roundtrips, den Merge nach echter
Datensatz-ID sowie die Quarantaene alter Generationen. 94 Maven- und 23
Python-Tests sind gruen. Der vollstaendige Neuerhebungslauf startet zuerst
die fuenf FT-Provider und danach die 14 weiteren source-scoped Workflow-IDs;
GUI/REST 8092 bleiben bis zum Writer-Ende geschlossen. Noch kein Liveabschluss.

Die Buildabnahmen und Restart-Healths sind belegt. Die vollstaendige erneute
Lieferung aller Quellen und die beiden gezielten Reparaturen sind nur dann
abgeschlossen, wenn die jeweiligen Abschluss-/Verifikationsbelege vorliegen.
Dieser Text dokumentiert den Zwischenstand und darf laufende oder teilweise
fehlgeschlagene Aktualisierungen nicht als erledigt darstellen.

## Freigegebener FT-Teilscope und temporaerer GET-Server (20:17 MESZ)

Die fuenf FT-Provider `178177`, `1231244`, `504191`, `692325`, `762452`
sind inzwischen mit der korrigierten Historien-ID vollstaendig neu geladen.
Die Zeilenzahlen 1091, 254, 1503, 279 und 196 entsprechen jeweils exakt dem
frischen Provider-Total; alle Cursorenden sind erreicht. Das ist eine Freigabe
dieser fuenf Historien, noch keine Freigabe aller 19 Reparaturprovider oder
des normalen Top-200-Laufs. Die anderen 14 Vollhistorien laufen weiter.

Um die bereits fertigen FT-Provider zu lesen, laeuft voruebergehend nur der
vorhandene `RestApiServer` ohne GUI und ohne `UpdateStarter` auf Port 8092.
Der Java-Launcher liegt nachvollziehbar unter
`sources_readonly/ReadOnlyVantageServer.java`. Er verwendet unveraenderte
Instanz-/REST-Settings und erzeugt keinen zweiten Trade- oder Katalogwriter.
`POST /api/v1/update` antwortet mit 405; `GET /api/v1/update/status` mit 404.
Das selbstaendige Fixture prueft auch einen parallelen Writer fuer eine andere
Provider-ID, die Sperre einer manipulierten CSV/Meta-Kombination und das normale
Stopfile-Ende mit freiem Port (`sources_vantage_readonly_fixture_v2.json`).

`sources_vantage_ft_readonly_acceptance.json` vergleicht jede ausgegebene Zeile
der fuenf Provider mit der erneuerten nativen CSV, prueft Quellen-UID,
Service/Instanz, Total, UTC, Truncation und SHA. Die HKD-Historie `504191`
wird im REST-USD-Export anhand des jeweiligen historischen EZB-Kurstags
geprueft. Native Trade-/Metadaten, Providerkatalog und Abonnentendatenbank
blieben bei diesen GETs bytegleich. Historische FX-Cache-Nachladungen sind
moeglich; der Launcher selbst schreibt keine Provider- oder Tradehistorien.

Der temporaere Listener endet ausschliesslich regulaer durch die private
Stopdatei `.tmp/sources_vantage_readonly.stop`. Vor einem spaeteren normalen
GUI-Start muessen Prozessende und freier Port 8092 bestaetigt sein. Der
aktuelle volle Reparatur-CLI-Writer betrifft andere IDs und wird nicht beendet.

Der aktuelle Quellenueberblick steht in `sources_current_progress.json`;
`sources_live_progress.json` bewahrt den urspruenglichen Versuch. Nach dem
unerwarteten Ende der alten WindowsStore-Python-Beobachter wurde nur der
lesende Beobachter mit dem gebuendelten Python neu gestartet. Die Java-
Quellenjobs liefen unabhaengig weiter. MQL- und Zulu-Folgearbeiten haben eigene
Besitzer und Belege; alte Fehlerjobs bleiben erhalten.
