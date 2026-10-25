# MQL-Protokollierung im ausgelieferten Java-Paket

Die produktive Datei `log4j2.xml` fordert INFO-Ausgaben an. Trotzdem fehlten
die Anwendungslogs im gestarteten Fat-JAR. Der alte Startparameter enthielt
zusätzlich einen Windows-Pfad statt einer Datei-URI und erzeugte einen
Startfehler. Der private zukünftige Neustartweg verwendet jetzt `file:///C:/…`.

Der eigentliche Kontextfehler ist unabhängig davon reproduziert: Statische
Anwendungslogger gehören im Paket einem Classloader-Kontext. Die frühere
`Configurator.reconfigure(uri)`-Verwendung konfigurierte einen anderen
Default-Kontext. Der bereits erzeugte Anwendungslogger blieb auf ERROR.

`LoggerManager` konfiguriert und leert jetzt den Kontext seines eigenen
Loggers. Auch die Ersatzkonfiguration verwendet denselben Kontext.
Eine separate JVM mit absichtlich fehlerhafter Startkonfiguration prüft,
dass ein vor `main` erzeugter Anwendungslogger anschließend INFO schreibt.
Ein zusätzlicher isolierter Fat-JAR-Vergleich ergibt Exit 1 für den alten
Kontextaufruf und Exit 0 für die Korrektur.

Der vollständige isolierte Maven-Build hat **154 Tests ohne Fehler oder
Skips** bestanden. Quellen-/Paket-Hashes und Umfang stehen in
`root_mql_logger_build.json`; die beiden Logger-Regressionen in
`root_mql_logger_tests.xml`. Dieser Build enthält noch die zuvor geprüfte
Paginierungsfassung. Die gesonderte Live-Gegenprüfung hat inzwischen den
originalen `/list/page2`-Pfad belegt; dessen enge Korrektur wird anschließend
mit dem Loggerfix gemeinsam gebaut und im belegten Leerlauf aktiviert.

Der laufende Quellenjob wurde für diesen Loggernachweis weder abgebrochen
noch neu gestartet. Ein erfolgreicher Pakettest ersetzt keine produktive
Neustart- oder Downloadabnahme.
