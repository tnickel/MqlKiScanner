# Kritische Nachprüfung des fremden Systemreviews

Prüfdatum: 18.10.2026. Grundlage ist der vom Nutzer eingefügte [Fremdreview](FREMDREVIEW_ORIGINAL.md), SHA-256 `113a828075c28f7435d6045f44ded8db83264b2a7a42a9e76632facc9c637a6a`, gegen den aktuellen Arbeitsbaum von SignalKiScanner und MqlDownloader. Frühere Korrekturen sind im [Behebungsbericht](../BEHEBUNG.md) dokumentiert. Dieser Nachtrag bewahrt den früheren Prüfstand und dessen Manifeste.

**Der Fremdreview ist keine belastbare Gesamtfreigabe.** Er verbindet reale Architekturgrenzen mit bereits behobenen Fehlern, falschen Detailaussagen und widersprüchlichen Zählungen. Seine Patchvorschläge wurden deshalb nicht ungeprüft übernommen. Verbleibende konkrete Fehler wurden reproduziert und korrigiert.

## Bewertung der vier benannten Defects

| Fremdbefund | Kritisches Ergebnis | Änderung dieser Nachprüfung |
|---|---|---|
| DEFECT-01: Frischer MQL-Katalog verhindert Trade-Update | Historisch richtig, im aktuellen Code bereits behoben. `ClientUpdateRunner` überspringt den gesamten Abruf nur bei frischem Katalog und ausdrücklich ausgeschalteten Trades. Angeforderte Trades umgehen auch den lokalen Fünf-Tage-Dateicache. | Vorhandenen Fix bewahrt und erneut getestet; keinen zweiten, konkurrierenden Downloadpfad eingeführt. |
| DEFECT-02: `store_scan_result` ohne Quelle überschreibt Fremddaten | Für den benannten Scan-Aufruf bereits behoben. Die darunterliegende direkte API `upsert_signal` ließ diesen Fehler jedoch noch zu. Ein externer Sicherheitsangriff ist damit nicht belegt; bestätigt ist ein interner Datenintegritätsfehler. | Quellenvertrag zentral abgesichert: bestehende IDs benötigen eine explizite passende Quelle. Writerlock vor Identitätslesen verhindert konkurrierendes Überschreiben. Initiale Legacy-Neuanlagen behalten den Default `mql5`. |
| DEFECT-03: Fehlende Composite-Identität und unterdrückte Katalogzeilen | Die zentrale Architekturgrenze und die numerische Katalogdeduplizierung sind real. Die vorgeschlagene Änderung weniger Primärschlüssel wäre unvollständig: Studien, Berichte, Chronik, Markierungen und weitere Verbraucher verwenden ebenfalls numerische IDs. | Katalogdarstellung, Ausschluss bereits gescannter Zeilen und Kennzahlenmapping verwenden nun `(quelle, signal_id)`. Verschiedene Quellen bleiben sichtbar. ID-basierte Studien werden bei aktuellen Quellenkonflikten weder übernommen noch überschrieben; Studienstarts werden vor Kurszugriff gesperrt. Vollständige zentrale Composite-Migration bleibt gesondert. |
| DEFECT-04: MQL-REST-Katalog hat kein belegtes `weeks` | Bestätigte verbleibende Integrationslücke. Ein unbekanntes Alter wird vom Scanner zu Recht zurückgewiesen. Der im Review genannte `ProvidersHandler.java` existiert hier nicht; zuständig ist `rest/RestApiServer.java`. | Wochen aus eindeutig zugeordnetem gecachtem Profil-HTML in Katalog und Details ergänzt. Fehlend/mehrdeutig bleibt `null`; kein Ersatzalter, keine Hochrechnung und keine Umgehung des Mindestalterfilters. |

Ein zusätzlicher Fehlerhinweis in `forensics/exposure.py` empfahl bislang pauschal eine Brokerfreigabe. Er verlangt jetzt ausdrücklich passende Belege für Broker, Instrument, Kontraktgröße und Gewinnwährung samt Quelle. Die Registry und die Rechenregeln bleiben unverändert.

## Quellengetrennte Tabellen und konservative Studiensperre

`katalog_resultate` liefert Katalogkennzahlen nach Quelle und ID. Die Ergebnisse eines gescannten Signals verdrängen nur dieselbe Quelle/ID, nicht andere Anbieter mit derselben Nummer. Trade- und Metrics-Artefakte werden weiterhin über Quellen-ID, Signal-ID und Plattformversion zugeordnet.

Die Seite „Alle Signale“ berechnet ihre Statistik mit genau diesen getrennten Metadaten. Ein tatsächlich durchlaufener Katalog-/DB-/AppTest prüft zwei Quellen mit gleicher ID und sogar identischen CSV-Bytes, aber unterschiedlichem Startkapital und Broker. Weder Kapitalbasis noch Plattform-DD oder andere Kennzahlen dürfen zwischen den Zeilen wandern. Die bisherige Probe mit einem gemockten Katalog allein hatte diesen Übergang nicht abgesichert.

Die Studienablage ist weiterhin ID-basiert. Ein gleicher Datei-SHA belegt bei zwei Quellen keine gemeinsame Broker-/Kapitalbasis. Deshalb filtern `get_equity_studie` und `list_equity_studien` aktuell mehrdeutige IDs; `store_equity_studie` weist Schreibversuche für diese IDs innerhalb derselben Schreibtransaktion ab. Bestehende Zeilen bleiben erhalten. Einzel- und Batchstudien prüfen den Konflikt vor einem Kurs-/Terminalzugriff. Die Sitzungs-Cache-ID enthält zusätzlich Quelle, Plattformversion, Plattform und Broker.

Markierungen, Kommentare und Fix-IDs gelten nach dem bisherigen Modell weiterhin für die numerische ID gemeinsam. Die Auswahlansicht weist bei Quellenkonflikten ausdrücklich darauf hin. Auch die zentrale Workflowaufnahme kann zwei fremde Quellen derselben ID noch nicht gleichzeitig speichern; sie wehrt den Konflikt ab. Diese Grenzen werden nicht als erledigte Composite-Migration ausgegeben.

Historische Studien ohne Quellenangabe beweisen zudem keine lückenlose Besitzkette: Wenn ein früherer Quellenanspruch vollständig verschwindet, kann allein ein identischer SHA dessen früheren Besitzer nicht rekonstruieren. Die aktuelle Konfliktsperre ist eine Absicherung, keine nachträgliche Erfindung solcher Metadaten.

## Sachlich falsche oder überholte Detailaussagen

| Aussage im Fremdreview | Nachprüfung |
|---|---|
| Harte allgemeine 30-%-Schranke | Überholt. Maßgeblich ist die konfigurierte DD-Grenze; lokal stehen 50,0 %. Mindest-Calmar 3,0 und absolute Monatsertragshürde 0 bleiben erhalten. |
| Drei Monate entsprechen mindestens zwölf Wochen | Falsch. Der Code verwendet 365,2425 Tage/Jahr und Jahr/12 je Monat: drei Monate = 91,310625 Tage = 13,044375 Wochen. Zwölf Wochen sind 84 Tage. |
| H1-Lücken über 1 % sperren automatisch den belastbaren Wert | Kein aktueller Codevertrag. `SCHRANKE_MIN_ABDECKUNG` beträgt 0,95; zusätzlich gelten FX-, Zeitbasis- und Tradeabdeckungsprüfungen. Die ausdrücklich erlaubte, markierte Teilmessung ist von unzuverlässigen orangefarbenen Vorbehaltswerten zu unterscheiden. |
| Jede Forensik verlangt ein ursprünglich in USD geführtes Konto | Zu pauschal. Native MQL-Exporte benötigen USD-Nachweis; dokumentierte, USD-normalisierende Quellenverträge werden gesondert anerkannt. Ein Quellenalias oder REST-Transport allein belegt keine Umrechnung. |
| Die genannten Vantage-Spezifikationen fehlen | Überholt. UKOUSD, SP500, NAS100FT, XAUAUD/XAUJPY und weitere genannte Instrumente sind vorhanden und werden für den passenden Vantage-Broker aufgelöst. |
| AxiTraderUs07Live/AxiTrader5 durch zusätzliche `brokers` freigeben | Unbegründet. Vorliegende Belege für AxiTrader2, Vantage oder RoboForex erlauben weder andere AxiTrader-Server noch deren Aktien-/Ölkontrakte. Keine Registry-Ergänzung allein zur Freischaltung. |
| CSVs von 2271995 und 2360068 sind aktuell wegen leerem Typ beziehungsweise `Commission` kaputt | Überholt. Der aktuelle Parser liest die gespeicherten Dateien erfolgreich: 2.022 Trades/11 Kapitalbewegungen beziehungsweise 1.241 Trades/138 Kostenbuchungen/34 Kapitalbewegungen. Reine Zeitstempelreste werden kontrolliert übersprungen; separate Kosten sind implementiert. Damit ist noch keine aktuelle vollständige Forensik dieser Signale behauptet. |
| `forensics/engine.py`, `exposure.calculate_exposure`, `drawdown.calculate_drawdown` sind die angegebenen Codeorte | Diese Pfade/Funktionen existieren hier nicht. Die Engine liegt unter `src/mqlkiscanner/engine.py`; die genannten Forensikmodule verwenden `run`. |

Die ausführlichen Resolver-/Regelprüfungen stehen in [kontrakte_README.md](kontrakte_README.md); die Parserproben in [parser_bestaende.json](parser_bestaende.json), Pfad- und Zeitrechnungen in [code_fakten.json](code_fakten.json).

Bei GER40FT/UK100FT verbleibt eine gesonderte Belegfrage: Brokergebundene Vantage-USD-Medianmodelle und ungebundene EUR-/GBP-Angaben unterscheiden sich. Die Brokerpriorität des Resolvers ist beabsichtigt. Aus den geprüften lokalen Belegen lässt sich kein neuer, sicher richtiger Ersatzfaktor ableiten. Diese beiden Modelle wurden deshalb nicht als neu verifiziert oder ohne Nachweis geändert.

Die ergänzend geprüften offiziellen Quellen lösen diese Belegfrage ebenfalls nicht auf: Der [Vantage-Produktprospekt](https://partners.vantagemarkets.com/pdf/Vantage_Introducing_Broker_Prospectus.pdf) nennt GER40ft und UK100ft in seiner Produktliste, gibt dort aber keine zugehörigen Punktwerte und Gewinnwährungen an. Die [Vantage-Indexseite](https://www.vantagemarkets.com/en-ng/indices-trading/) beschreibt GER40 als Cash-CFD in EUR und UK100 als Cash-CFD in GBP. **Schlussfolgerung:** Diese Cash-Angaben sind kein hinreichender Beleg für die konkreten historischen FT-Kontrakte des Signalanbieters. Abgerufen am 18.10.2026; es wurde daraus kein neuer Registryfaktor übernommen.

## Mengenbilanz und Betriebszustand

Read-only-SQL am 18.10.2026 bestätigt 194 Workflowzeilen, 163 gespeicherte Forensikzeilen, 1.454 Katalogzeilen und 193 Tradeverweise. Aktuell wurden keine gleichen numerischen IDs aus mehreren Katalogquellen gefunden; die Kollisionsfehler sind reproduzierbare Randfälle und kein Nachweis bereits eingetretener produktiver Datenkorruption.

**163 Forensikzeilen bedeuten nicht 163 vollständige aktuelle Prüfungen.** Im gelesenen Bestand haben 122 Zeilen das historische Vollständigkeitsflag `true`, 32 `false` und 9 kein solches Flag. Die Versionsverteilung ist 4 ohne Version, 27 mit Version 7, 3 mit 11, 10 mit 14, 104 mit 15 und 15 mit 16. Keine dieser Zeilen hat die aktuelle Version 19. Ein `forensik`-Join allein darf daraus keine aktuelle Freigabe ableiten.

Der Fremdreview ist außerdem intern widersprüchlich:

- Seine Zulu-Währungsliste enthält 13 IDs, obwohl er von 10 Währungsfällen spricht. Mit den übrigen aufgezählten Gruppen ergibt das 21 statt der behaupteten 18 Zulu-Fälle. „Zu 100 % lückenlos belegt“ trägt diese Aufstellung nicht.
- Seine Quellenzahlen in der Zeile „Alle Signale“ summieren sich auf 1.454, der Gesamtwert lautet jedoch 1.477. Die Fußnotenformel `194 + 1454 − 171 = 1477` stimmt, aber die Einzelspalten zählen Kataloge und bilden diese Vereinigungsmenge nicht ab.
- Eine hohe Testzahl beweist nicht automatisch alle mathematischen Regeln oder die Aktualität produktiver Daten. Die im fremden Text genannten historischen 2.412/2.413 Tests sind kein aktueller Laufnachweis dieser Nachprüfung.

Die lokale HTTP-Gegenprobe verwendet ausschließlich GET: Der laufende MQL-Dienst liefert noch einen Katalogdatensatz ohne Wochenwert. Vantage meldet `idle`, liefert für das tatsächlich im aktuellen 199er-Katalog enthaltene Signal 1419494 aber HTTP 404 bei `trades.csv`. Die zuerst zusätzlich geprüfte alte ID 178177 ist nicht mehr im aktuellen Katalog; deren 404 allein wäre kein Beleg für ein Exportproblem gelisteter Kandidaten. Die geprüfte aktuelle Stichprobe belegt es dagegen. Das entspricht nicht einer pauschalen produktiven Freigabe „Vantage PASSED“.

Aggregierte SQL-Belege: [bestandsabgleich.json](bestandsabgleich.json). HTTP-Stichproben mit Zeitstempel und genauer Reichweite: [runtime_gets.json](runtime_gets.json). Diese wenigen GETs sind kein neuer Gesamtscan.

## Tests, Build und nächste Betriebsabnahme

Der erste projektweite Scannerlauf ist unter [scanner_full.log](scanner_full.log) und [scanner_full.xml](scanner_full.xml) dokumentiert: 2.498 bestanden, ein älterer Test scheiterte am nun ausdrücklich vorgeschriebenen Quellenparameter. Das Fixture in `test_review18_pipeline.py` nennt nun die bekannte Quelle `mql5`; seine Assertions zur Veraltung alter Messwerte bleiben unverändert. Die Windows-Rohausgabe ist unter `scanner_full_windows_raw.log` erhalten; das lesbare Log wurde nach UTF-8 transkodiert.

Die abschließende vollständige Wiederholung verwendet drei disjunkte Dateigruppen in getrennten pytest-Prozessen. [scanner_shards.json](scanner_shards.json) hält die Auswahl fest; die JUnit-Berichte `scanner_shard_0.xml`, `scanner_shard_1.xml` und `scanner_shard_2.xml` belegen die Ergebnisse. Das [Manifest](manifest.json) prüft, dass alle 2.499 ausgewählten Testidentitäten der ursprünglichen vollständigen Sammlung genau wiederkehren. Kostenpflichtige `llm`-Tests sind gemäß `pytest.ini` im Standardlauf abgewählt. Zusätzlich genannte fokussierte Testgruppen überlappen mit der Vollregression; ihre Zahlen werden nicht addiert.

**Final: 2.499 Scanner-Tests bestanden, 0 Fehler, 0 übersprungen; 4 LLM-Fälle standardmäßig abgewählt.** Die drei Teilgruppen bestehen aus 916, 828 und 755 Fällen. Kein Fall aus der vollständigen Sammlung wurde entfernt; das Manifest prüft die genaue Übereinstimmung einschließlich Parametrisierungen. Alle Quell- und Testdateien blieben während dieser abschließenden Läufe unverändert.

- DB-/Quellen-/Studienregression: 142 bestanden; [identitaet_bewertung.md](identitaet_bewertung.md).
- Kontrakt-/Währungsregression: 189 bestanden; [kontrakte_tests.json](kontrakte_tests.json).
- Neuer MQL-Altersvertrag: 148 Java-Tests bestanden, 0 übersprungen; zusätzlich 150 Scanner-Vertragstests bestanden. [mql_README.md](mql_README.md) trennt den vorherigen Paketbau mit GUI-Skips vom finalen vollständigen Testlauf ohne Skips.
- Neue Katalogtests prüfen reale Katalogdarstellung, getrennte Kapitalbasen/Quellen, identische CSVs, Studienblock vor Terminalzugriff und Quellen-/Brokerabgrenzung des Sitzungscaches. Bestehende Katalogtest-Konsumenten wurden dem neuen Tuple-Schlüssel angepasst; keine Bewertungserwartung wurde gelockert.

Das neue [MqlDownloader-JAR](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar) wurde gebaut und gegen die getesteten Klassen abgeglichen. Hash und Dateigröße stehen in [mql_artifact.json](mql_artifact.json). Frühere Paket-Hashes unter `../nachweise/fix_mql_*` gehören zum Build vor dem Altersfix.

Keine produktiven Datenbanken, Historien, Terminalprozesse oder laufenden Monitore wurden geändert; kein Quellen-POST und kein kostenpflichtiger Modellaufruf wurde ausgeführt. Nach Verwendung der neuen Builds sind Quellenaktualisierung, Katalogimport und ein kontrollierter Neuscan erforderlich, um die produktive Aktualität und Tabellenfüllung gemeinsam abzunehmen. Der Codefix schreibt keine fehlenden Prüfwerte und hebt keine historischen Ausschlüsse auf.
