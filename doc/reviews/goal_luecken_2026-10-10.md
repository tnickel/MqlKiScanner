# Goal: Verbleibende Tabellenlücken füllen

Status: abgeschlossen im vereinbarten belegbaren Umfang. Datenübernahmen, portable Broker-Messläufe, Regressionstests und unabhängige Abschlussprüfung sind beendet. Nicht berechenbare Restfälle und die dafür benötigten Originaldaten sind dokumentiert; die Tabelle ist ausdrücklich nicht vollständig gefüllt.

Ausgangslage: 1.609 Signale und 106 ohne Trade-Export. Die erste Inventur zählte 616 bestandene H1-Prüfungen. Davon waren drei basislose Altstudien zu großzügig mitgezählt; der nach denselben strengen Kriterien korrigierte Ausgangswert beträgt 613. Der unveränderte Ausgangsbeleg steht in `goal_luecken_start_2026-10-10.json`; die ersten Studien wurden vor Änderungen separat gesichert.

## Endgültige Datenbilanz

| Quelle | Gültige H1-Prüfung vorher, korrigiert | Jetzt | Fehlender Trade-Export vorher → jetzt |
| --- | ---: | ---: | ---: |
| Vantage | 239 | 279 | 27 → 1 |
| RoboForex | 70 | 98 | 3 → 3 |
| MQL5 | 77 | 174 | 19 → 1 |
| Pelican | 217 | 438 | 4 → 0 |
| Zulu | 10 | 89 | 53 → 1 |
| Gesamt | 613 | 1.078 | 106 → 6 |

Damit sind **465 zusätzliche Signale mit gültiger H1-Prüfung** und **100 zuvor fehlende Trade-Exporte** belegt. Das sind Signalzahlen, keine Zellenzählung; ein wiederhergestellter Export ermöglicht mehrere Kennzahlen. Virtuelle Studien bleiben ausdrücklich als Annahme gekennzeichnet und ändern keine Workflow-Bewertung.

**Nicht alle Lücken sind gefüllt.** Bei 531 Signalen fehlt weiterhin eine freigegebene H1-Messung: 377 haben nur einen Rohwert mit Vorbehalt, 148 keine nutzbare H1-Messung und sechs keinen Trade-Export. Darunter sind auch sechs belegte Nullhistorien, für die eine H1-Messung mangels Trades entfällt. Weitere einzelne Tabellenzellen bleiben sachlich korrekt leer, beispielsweise Profitfaktor ohne Verlustnenner oder Rendite/Risiko-Verhältnisse ohne ausreichende Laufzeit.

Die drei basislosen Altstudien wurden auf allen drei portablen Brokern erneut auf Berechenbarkeit geprüft. Alle neun Versuche enden vor der Kursmessung wegen fehlender gültiger Kapitalbasis. Ursache sind echte CSV-Kapitalflüsse vor dem ersten exportierten Trade: Nettosaldo −112,63 USD bzw. −2,60 USD für die beiden starX-Historien und −37,0951 USD für ScalpXAU. Ein InitialDeposit=0-Platzhalter ist ausgeschlossen; das Quellfeld fehlt tatsächlich. Die virtuelle 10.000-USD-Kandidatin wird angeboten, darf aber die nachgewiesene reale CSV-Basis nicht überschreiben. Erforderlich sind vollständige Kapital-/Tradehistorien. Die alten USD-Studien werden deshalb nicht als gültige Prozentmessung gezählt. Belege: `goal_broker_matrix_basislos_2026-10-10.json`, `goal_luecken_ergebnis_2026-10-10.json` und der aktuelle Ursachenbericht.

## Allgemeine Fehlerklassen

| Ursache | Lösung und Grenze |
| --- | --- |
| Quellen sperren Exporte für andere Kontowährungen | Historische EZB-Umrechnung je Buchungs-/Abschlussdatum im Quellenadapter. Keine pauschale Gleichsetzung von Kryptowährungen mit USD. |
| Historische Kontogewinne werden mit einem heutigen Wechselkurs skaliert | Pelican erhält denselben belegten historischen Tageskursansatz wie Zulu/Vantage. Aktuelle Balance/Equity bleiben separat zum Snapshotkurs; betroffene Bestands-Exporte werden neu erzeugt und SHA-abhängig nachgemessen. |
| Lokaler MQL-Export wird nicht gefunden oder falsch zugeordnet | Exakte abschließende Signal-ID; Archivfallback nur mit eindeutiger Plattform im zugehörigen Original-HTML und passendem CSV-Format. Normale Dateisätze haben Vorrang. |
| Anbieter verschwindet aus dem Pelican-Katalog, Originalhistorie bleibt vorhanden | CSV-Zugriff aus exakt ID-gebundenem verwaltetem Archiv nur nach SHA-/Zeilenanzahl-/Schema-/Währungsprüfung. Fehlende Provider-Metrics werden nicht erfunden; deren Endpunkt bleibt 404. |
| Neue Trade-Datei, aber alter Forensik-Befund wird weiter angezeigt | Forensik an den analysierten Snapshot-SHA binden; Dateitausch macht alte Befunde veraltet. Atomarer vollständiger Scan bindet seinen neuen Befund an den neuen Snapshot. Nachmessung nimmt geänderte CSVs unabhängig von alten sichtbaren H1-Werten auf. |
| Kursfeed liefert nur Teilhistorie oder keine brauchbare Zeitachse | Weitere konfigurierte portable Broker als getrennte Messversuche. Beste vorhandene Messung bleibt bei Folgefehlern erhalten; Quellenherkunft wird protokolliert. |
| Ein bisher ausgeschlossenes Instrument erhält einen Kontraktbeleg | Gezielt erneut rechnen, auch bei zuvor bestandener Teilmessung. Maßgeblich ist der ursprüngliche Kontobroker; ein Kursreferenzterminal ersetzt dessen Identität nicht. Ein schlechter Nachversuch überschreibt keine verlässliche SHA-passende Vorstudie. |
| Einzelne Trades schließen laut Quelle vor ihrer Eröffnung | Keine erfundene Zeitkorrektur. Alle finanziell validen Datensätze bleiben in PF, Gewinnquote und realisiertem Netto erhalten; zeitabhängige Kennzahlen bleiben gesperrt. |
| Nullgeld-Metazeilen beim MT4-Hedge-Close | Nur das vollständig belegte Artefakt mit exaktem Kommentar, Volumen null, sämtlichen Geldbeträgen null und konsistenten Preisen/Zeiten wird gesondert erkannt. Ungültige echte Trades bleiben Fehler. |
| Separate Kontogebühren | Eigenes Kostenereignis statt externer Kapitalfluss; Netto, Saldo, Rendite, Equity und Exposure berücksichtigen diese Kosten. Gebühren verändern weder die Zahl echter Trades noch die Kapitalfluss-Neutralisierung. |
| MT4-Monatsarchive statt einzelner Trades | Exakt validierte Originalaggregate liefern zusammen mit Einzeltrades und Kosten das vollständige realisierte Netto. Aggregate werden niemals als Position oder Kapitalfluss erfunden; PF, vollständige Tradezahl, Rendite und H1 bleiben unbekannt. Überlappende Einzeltrades im Aggregatmonat werden wegen Doppelzählungsgefahr abgelehnt. |
| Leerer Pelican-Cache trotz positiver Handelszahlen | Widerspruch ist künftig ein konkreter Fehler und erneuter Downloadbedarf; eine leere Datei blockiert die Wiederherstellung nicht mehr dauerhaft. |
| Quellen-Handelszahlen erreichen den Nachladepfad nicht | Trades/Wins/Losses werden als getrennte, endliche, nichtnegative ganzzahlige Quellcounts durchgereicht. Positive Counts lösen genau einen erneuten Abruf aus; sie dienen nicht als Positionszahl-Beweis für Parserheuristiken. |
| Gleichnamige MQL-Anbieter kollidieren beim Umbenennen | Nur eindeutige Dateizuordnungen werden umbenannt; vorhandene Zieldateien werden niemals überschrieben. Der aktualisierte normale Launcher enthält den Fix. |
| Rundungsrest nach vollständiger Auszahlung | Begrenzte Korrektur im Rahmen des berechneten Maschinenfehlers; echte negative Salden bleiben ungültig. |
| Fülllauf beendet sich trotz verbesserbarer Bestandszeilen | Fortschritt anhand besserer Messungen und Datenstände statt nur anhand der Zahl gespeicherter Zeilen. |

## Belege

- `goal_broker_matrix_2026-10-10.json`: tatsächlich ausgeführte Broker-/Signal-Messungen und persistierte Verbesserungen.
- `workflow_metrics_2026-10-10.json`: geschützte Kapitalbasis, TWR-Rundungsfall und Finanzteilstatistiken.
- `zeitbasis_belegschutz_2026-10-10.json`: Vergleich echter Zeitbasisfälle vor/nach Korrektur.
- `mql_lokale_export_wiederherstellung_2026-10-10.json`: sechs Originalexporte mit ID-/Plattform-/SHA-Belegen.
- `zulu_fx_export_abnahme_2026-10-10.json`: 52 zusätzlich exportierbare Historien; kürzere Bestände werden ausdrücklich als solche gekennzeichnet.
- `vantage_fehlende_exporte_nachgeladen_2026-10-10.json`: tatsächlicher Nachladestand, vollständige Seitenzählung und Exportprüfung.
- `zulu_zeit_quellfehler_2026-10-10.json`: anhand der öffentlichen Quelle reproduzierte falsche Zeitpaare.

Vantage, Tickmill und ActivTrades werden ausschließlich lesend und explizit portabel verwendet. Die Anzahl bekannter Signale ergibt keine exakte Restzeit: historische Brokerdateien werden beim ersten Zugriff teilweise erst nachgeladen; Anzahl und Alter der Instrumente unterscheiden sich erheblich.

## Noch nicht gelöste Datenzugänge

Pelican antwortete mit der vorhandenen Session HTTP 401; der erste offizielle automatische Login endete ohne bestätigte Verbindung. Das normale Anmeldeformular im vorhandenen Chrome lieferte anschließend eine bestätigte API-Verbindung. Der dauerhafte Chrome-Login mit API-Erfolgskontrolle ist implementiert, getestet und gebaut. Die 159 leeren und vier fehlenden Historien wurden geprüft: Aus 160 datierbaren Fenstern wurden mit 3.618 Monatsabrufen 156 Historien und 113.880 Originaltrades wiederhergestellt. Drei Jahr-1-Platzhalter besitzen weder einen gültigen Beginn noch datierte Tageshistorie; ein allgemeiner Platzhalterdatumschutz verhindert Anfragen über 2.000 Jahre. Vier weiterhin leere API-Historien widersprechen positiven Aggregaten und werden ausdrücklich nicht als vollständiger Export behandelt.

Die anschließende historische FX-Korrektur wurde für alle 636 sichtbaren Pelican-Identitäten durchgeführt: 628 reguläre CSVs mit 310.330 Trades sind unabhängig gegen die Originaldateien und die offizielle historische EZB-Tabelle nachgerechnet. Alle 31.483 FX-Datumsbelege verwenden keinen zukünftigen Kurs und höchstens zehn Kalendertage Rückgriff. Vier zusätzliche kataloglose Originalarchive liefern 8.913 USD-Trades über den geprüften Archivresolver; ihre fehlenden Metrics bleiben 404. Zusammen wurden 632 CSVs mit 319.243 Trades in den Scanner übernommen; alle gespeicherten Bytes und SHAs wurden unabhängig geprüft. Geänderte Exporte wurden nachgemessen. Ein Fehler beim Schreiben einer Diagnose-Datei wurde durch atomaren Dateitausch behoben; nur die beiden noch fehlenden Importdatensätze wurden anschließend separat fortgesetzt. Die unveränderten Erstbelege und Sicherungen bleiben erhalten. Abnahme: `goal_pelican_final_import_2026-10-10.json`, unabhängige Gegenprüfung: `pelican_final_import_unabhaengig_2026-10-10.json`.

Robo-StocksTrader gehört nicht zum vorhandenen MT4-/MT5-Dealadapter; die offizielle StocksTrader-API benötigt einen gesonderten Kontozugang. Beim fehlenden Zulu-Export liefert die öffentliche API Datensätze ohne Eröffnungs-/Schlusszeiten und Preise. Solche Felder werden nicht geschätzt. Eine Vantage-Historie bezeichnet ihre Währung lediglich als `UST`; die Gleichsetzung mit USDT ist bislang nicht belegt. Ohne belegte Währungsidentität und gegebenenfalls historischen Umrechnungskurs wird sie nicht pauschal als USD behandelt.

Die sechs Einträge ohne Trade-Export sind vollständig zugeordnet:

| Quelle / ID | Ursache und erforderlicher Nachweis |
| --- | --- |
| Robo / 93128696, 93019895, 93156209 | StocksTrader statt MT4/MT5. Verifizierter StocksTrader-Historienzugang und allgemeiner Adapter erforderlich. |
| Zulu / 426712 | Öffentliche Datensätze ohne Handelszeiten und Preise. Vollständige Originalpositionen erforderlich. |
| Vantage / 1159789 | Währungskennung UST nicht belastbar identifiziert. Offizielle Kontowährungszuordnung und gegebenenfalls historischer FX-Kurs erforderlich. |
| MQL / 1 | Synthetischer Testeintrag, kein nachgewiesener realer Signal-Anbieter. Es wird kein fremder Export mit derselben Ziffer im Namen zugeordnet. |

## Konkrete verbleibende Zellen

Der unabhängige Abschlussbericht `verbleibende_messluecken_aktueller_sha_2026-10-10.md` dokumentiert **47 unterschiedliche Signal-/Quellenidentitäten mit betroffenen Spalten, konkreter Ursache und benötigtem Nachweis**. Damit ist die verlangte Untersuchung von mindestens 30 fehlerhaften Zellen überschritten. Die darunterliegende JSON-Datei enthält 472 aktuelle byte-/SHA-geprüfte Problembefunde aus ihrem ausgewiesenen Inventarscope; Kategorien überschneiden sich und sind keine zusätzliche globale Signalzahl.

Die häufigsten belegten Hindernisse sind eine nicht ausreichend belegte Zeitbasis, weniger als 95 Prozent gemessene aktive Abdeckung, fehlende exakte Symbolkurse und unbekannte Originalbroker-Spezifikationen. Der Bericht trennt 17 Signale mit negativen Quellintervallen, fünf ungültige Kapitalbasen und ein monatliches Archivaggregatproblem. 163 frühere Parser-/Leerexportfälle enthalten jetzt parsbare Trades. Sechs belegte Nullhistorien und weitere korrekt undefinierte Einzelkennzahlen stehen separat als N/A.

Für weitere Füllungen werden zusätzliche Originaldaten benötigt: eindeutige UTC-/Serverzeitbelege, die konkret fehlenden Kursfenster oder feinere verfügbare Kurse, Originalbroker-Kontraktbelege, korrigierte Quellintervalle sowie vollständige Trade-/Kapitalhistorien. Alle heute neu auflösbaren Specs wurden bereits nachgemessen. Aus dem Abschlussinventar ist kein weiterer sicherer Produktivcodefix ohne solche zusätzlichen Belege ableitbar.

## Verifikation während der Umsetzung

Die konsolidierte Scanner-Prüfung über 31 Testdateien ergab zunächst 406 bestandene Fälle und genau eine veraltete Erwartung an die bewusst erhöhte Studien-Cacheversion. Die Erwartung wurde korrigiert; alle acht Tests dieser Datei bestanden danach. Weitere 156 Tests zu Gebühren-Consumern, Kontrakten, Symbolnamen, Exposure, virtueller Messanzeige, Katalog und PDF-Wiederverwendung bestanden.

Nach Ergänzung der Quellcounts bestanden 137 Tests zu Leercache-Recovery, Quellen, Zahlenformaten und Ingest-Regressionen. Der unabhängige Integrationsreview bestätigte die Trennung von Download-Indiz und Parser-Positionszahl. Die verschiedenen Läufe überlappen; ihre Fallzahlen werden nicht als unabhängige Gesamtzahl addiert.

Nach Ergänzung der elf live belegten Vantage-Specs und der gezielten Nachmessung bestanden 109 Tests zu Specs, Fülllauf, Leercache, Feedfallback und Anzeige unabhängiger Studien. Die direkte portable Terminalabfrage steht in `vantage_restspecs_live_2026-10-10.json`; Cash- und Futureinstrumente bleiben getrennt.

Nach Ergänzung der Forensik-SHA-Bindung bestanden 154 gemeinsame Tests zu Datenbank/SHA, unabhängiger Studienanzeige, Fülllauf/Feedfallback/Spec-Nachmessung, Katalog, Tabellenanzeige/Performance und Export-Retry. Atomarer Vollscan, unveränderte Dateien, geänderte Dateien, alte ungebundene Befunde und Rollback sind abgedeckt. Fehlende Kurs-/Kontraktdiagnosen werden auch beim frühen Abbruch vollständig strukturiert gespeichert; Qualitätsschwellen bleiben unverändert. Der finale Pelican-Build bestand 116 Java-Tests.

Nach Ergänzung der finanziellen Archivaggregate bestanden 112 gemeinsame Tests zu Archivschema, Finanzteilstatistik, Hedge-/Export-Artefakten, Kontokosten und Tabellenanzeige/Performance. MQLDownloader bestand 105, Vantage 49 und Zulu 107 Java-Tests. Die Diff-Prüfung der vier bearbeiteten Quellenprojekte und des Scanners fand keine Formatfehler.

Virtuelle Kapitalbasis, ausgeschlossene Instrumente und unvollständige Historie bleiben sichtbar gekennzeichnet. H1-Messungen sind Messungen auf dem gelieferten Zeitraster und keine Garantie für vollständige Intrastunden- oder laufende Kontorisiken. Es wurden keine positiven Anlageurteile aus den zusätzlich gefüllten Tabellenzellen abgeleitet.
