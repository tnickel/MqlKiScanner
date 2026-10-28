# Behebung des Scanner-/None-Reviews, 28.10.2026

Ausgangspunkt: Scanner-HEAD `853bc3a743040256e17f2333b63fbfb9e4219e13` und das unabhängige Review unter `SIGNALDOWNLOADER/waste/review_2026-10-28_scanner_none/BERICHT.md`.
Nutzerauftrag nach dem Review: „behebe die probleme“. Alle folgenden Korrekturen betreffen den lokalen Arbeitsbaum; kein Commit, Push, Deployment oder produktiver Neuberechnungslauf gehört zu diesem Abschluss.

## Umgesetzte Korrekturen

| ID | Korrektur | Regression |
|---|---|---|
| B01 | `daten_tabelle` konvertiert ausschließlich ausdrücklich benannte Messwertspalten. Namen, Text-IDs, Versionen und Hashes bleiben in Tabelle und CSV unverändert. | `00123`, `1e3`, `000` und führende Nullen in Identitäten/Versionen; echte 0 gegenüber unbekanntem Wert |
| B02 | Gemeinsamer Prozess-Lock macht Lesen und Erhöhen der pandas-Styler-Grenze atomar. Ein kleinerer paralleler Aufruf senkt die Grenze nicht mehr. | Zwei erzwungen konkurrierende Sessions; bestehender echter Streamlit-Marshallingtest |
| B03 | Brokerspezifische Aliase werden für ursprünglichen und normalisierten Symbolnamen gesucht. Der exakte Brokername behält Vorrang. | AUDSGDM findet den vorhandenen Vantage-Kandidaten AUDSGD+; exakter Name wird bevorzugt |
| B04 | JSON-Aliasschlüssel werden normalisiert, Zielnamen behalten ihre exakte Schreibweise. | `MISSING → Ger40` erreicht das case-sensitive Ziel |
| B05 | Vorwärts- und Reverse-Anzeigematching akzeptieren nur bekannte vollständige Suffixe bzw. explizite Aliase. Beliebiges Abschneiden entfällt. | EURUSDT/EURUSDXYZ/US1000 bleiben ungeklärt, bekannte Suffixe funktionieren weiter |
| B06 | Die Kurscaption zählt eigene Bars ausschließlich bei `Status=Kurse vorhanden`. Ersatzzeilen zählen als Symbole ohne eigenen Bestand und gesondert als Ersetzung. | 100 eigene Bars plus zwei Ersatzzeilen bleiben 100 statt 300 eigene Bars |
| B07 | Das Unterwasser-PNG verwendet den gemeinsamen Drawdown-Kern einschließlich Kapitalbewegungen. | Auszahlung 500 aus 1.000 ergibt 0 % statt 50 %; zusätzlicher Verlust bleibt sichtbar |
| B08 | Equity- und Unterwasserlinien werden an unbekannten Messpunkten getrennt. Fehlende Werte werden nicht zu Null-DD; isolierte Messpunkte bleiben als Punkte sichtbar. | Keine Linie über die Messlücke; ausstehende Auszahlung wird am nächsten messbaren Punkt berücksichtigt |
| B09 | Alle 15 im Review belegten nullable Dataframe-Aufrufe setzen explizit `placeholder=""`. Zahlen und fehlende Werte bleiben fachlich unverändert. Falsche Dtype-Erklärungen wurden berichtigt. | Tatsächliche AppTest-/Protobufprüfung einschließlich `HasField('placeholder')`, Daten-/Modelltabelle und Zeitdiagnose |
| B10 | Zeitlabels werden anhand ihrer tatsächlichen Bounding-Box ins Bild geklemmt. Bei identischen Zeitpunkten gibt es nur einen Tick. Auch Startkapital fließt in beide Skalengrenzen ein. | Kurze/lange Zeiträume, einzelner Zeitpunkt, konstante/leere Kurve, sechsstellige Kapitalbasis |
| B11 | Unbekannte native MQL-Währung wird im Quellen-Worker geklärt; native CSVs benötigen frische Metrics. Nach dem Download wird USD erneut geprüft. Fehlgeschlagene Vorbereitung startet kein Terminal und keinen Serien-Wiederholversuch. | None/EUR/USC nach altem USD, veralteter Metricscache, CSV-Fehler, Stop zwischen Beleg und Download; konvertierende Quellen behalten ihren separaten Cachevertrag |
| H01 | Effektive Aliasänderungen invalidieren Resolver und RAM-Fenster bestehender KursDaten-Instanzen. Herkunft bereits geladener anderer Symbole bleibt erhalten; beim erneuten Abruf wird nur der eigene Beleg erneuert/entfernt. | Aliasänderung OLD→NEW sowie Datei-/Pfad-/Fehlerfälle; Beleg von B bleibt bei Änderung von A erhalten |

## Prüfstand

**457 Tests bestanden, 0 fehlgeschlagen**, gemeinsamer gezielter Lauf über 22 betroffene Testdateien, **119,85 Sekunden**. Darin sind **64 neue Regressionsfälle** enthalten (32 Symbolauflösung, 14 Trade-Vorbereitung, 8 UI-Fälle, 9 PNG-Fälle und ein zusätzlicher Styler-Parallelitätsfall). Es wurde keine Vollsuite und kein bezahlter KI-Test ausgeführt.

Die getrennten Vorprüfungen sind Teilmengen und werden nicht auf 457 addiert: Root 42, Kursbereich 149, Prefetch 53 und UI 236 bestanden. Frühere Fehlerreproduktionen und das ursprüngliche Review bleiben unverändert als historische Belege erhalten. Eine zunächst falsch benannte Testdatei im gemeinsamen Aufruf führte vor der Sammlung zu „no tests ran“; der korrigierte abschließende Aufruf ist vollständig protokolliert.

Alle Tests laufen mit `PYTHONDONTWRITEBYTECODE=1`, deaktiviertem pytest-Cache und getrenntem temporärem Testbestand. `tests/conftest.py` isoliert Settings, DBs, Prompts, Trades und Secrets und blockiert externe Requests. Native Kurs-/Clientpfade werden mit synthetischen Stubs geprüft. Die korrigierte Auszahlungsdarstellung wurde zusätzlich als PNG visuell kontrolliert.

Nachweise und Dateihashes liegen in `nachweise/` und `abschluss.json`. Die endgültigen Testergebnisse sind in `nachweise/combined-tests.log` sowie `nachweise/combined-tests.xml` gespeichert. Der ursprüngliche Nachweisstand wird durch diese Dateien nicht umgeschrieben.

## Daten- und Betriebsgrenzen

- Fehlende Finanzwerte werden leer angezeigt, nicht erfunden. Die 318 im damaligen Datenauftrag fehlenden Modell-Nettogewinne werden durch diese Codeänderung nicht nachgerechnet oder mit 0 aufgefüllt.
- Es wurden keine pauschalen F40-/Kupfer-/Futureszuordnungen ergänzt. AUDSGDMs vorhandener Brokeralias wird korrekt versucht; eine vollständige historische Kursabdeckung ist separat nachzuweisen.
- Persistierte Kursbars bleiben nach Feed und exaktem Brokersymbol getrennt; die Aliasbehebung schreibt keine vorhandenen Kursreihen um.
- Laufende App, MT5-Terminals, Plattformen und KI-Dienste wurden nicht bedient oder neu gestartet; historische Studien/PDFs werden nicht automatisch neu erzeugt. Bereits laufende Worker können ihren zuvor geladenen Code behalten.
- Vorhandene Nutzeränderungen und fremde untracked Dateien bleiben erhalten. Die Änderungen sind lokal und uncommittet.

Keine neue Freigabe ungeklärter Instrumentgleichheit, kein geänderter Risiko-/Rankingmaßstab und kein Nachweis künftig bester Signale wird aus diesen Korrekturen abgeleitet.
