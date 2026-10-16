# Behebung des Gesamtreviews vom 16.10.2026

Dieser Nachweis gehört zum [Ausgangsreview](REVIEW.md). Dessen Zahlen und
Repros beschreiben die damaligen Fehler; sie bleiben als historische Belege
erhalten. Die Umsetzung erfolgte anschließend auf ausdrücklichen Auftrag
des Nutzers in den sechs eigenständigen Anwendungs-Repositories sowie der
Workspace-Dokumentation. Produktive Daten, Einstellungen und laufende
Monitorprozesse wurden dabei nicht verändert.

## Scanner und Finanzkern

| Review | Korrektur | Regression / Code |
|---|---|---|
| F1 | Freigegebene Teilmessungen behalten das messbare Floating anderer Symbole. Echte Kurs-/FX-Lücken betrachtbarer Symbole bleiben Messlücken. | `equity_rekonstruktion.py`, `tests/test_finance_review_20261016.py` |
| F2 | Ein Kapitalfluss während einer offenen Exportposition erlaubt ohne belegte Preflow-Equity keine geometrische Rendite-/Calmar-Freigabe. Status `kapitalfluss_equity_unbelegt` bleibt auch beim Auffrischen erhalten; alte positive Werte werden entfernt. Flache Positionsbestände erlauben weiterhin TWR-Unterperioden. | `portfolio_statistik.py`, `ScanResult.refresh_efficiency`, Finanzregressionen |
| F3 | Typfreie Geld-/Gebührenzeilen scheitern ausdrücklich. Belegte reine Export-Leer-/Kommentarartefakte bleiben zulässig. | `parser.py`, Finanzregressionen und Parserbatterie |
| F4 | Die Kontostudie kennzeichnet bereits enthaltene Kapitalflüsse; die Diagnostik addiert sie dann kein zweites Mal. | `equity_studie.py`, `equity_kapitalfluesse.py` |
| F5 | Ungerundete DD-Prozentwerte und Kapitalbasis steuern Risiko, Ampel und weitere Rechnungen. Gerundete Felder bleiben reine Anzeige. | `drawdown.py`, `scoring.py`, `pipeline.py` |
| F6 | Ein negativer virtueller Endstand verwirft keine für die reale Flow-Kurve gültige TWR mehr. | `portfolio_statistik.py`, Finanzregressionen |
| F7 | Gleichzeitige Einlagen/Entnahmen werden zu einem Nettofluss zusammengefasst; die CSV-Reihenfolge verändert die Rendite nicht. | `portfolio_statistik.py`, Finanzregressionen |
| F8 | FX-Kurse müssen endlich und positiv sein. Ein ungültiger Download ersetzt keinen vorhandenen gültigen Cache. | `fx_rates.py`, Finanzregressionen |
| F9 / H03 | Der Portfolio-Codebefund verwendet den aktuellen konfigurierten Jahres-Calmar; die abgelöste monatliche Pflichtschwelle wird nicht mehr vorgegeben. | `portfolio_statistik.statistik(results, settings)` |
| F10 | Der Martingale-Korbleiterbefund summiert tatsächlich Netto einschließlich Kosten. | `martingale.py`, Finanzregressionen |
| F11 | Nichtendliche oder nichtpositive Kontraktfaktoren erzeugen keine vermeintlich vollständige Exposure-Messung. | `exposure.py`, Finanzregressionen |
| H01 | MQL4 ist eine Plattformversion und kein RoboForex-Brokerbeleg. Nur eine eindeutige Quelle oder ausdrückliche Brokerangabe setzt den Broker. Der alte falsche DB-Fallback wird nicht fortgeschrieben. | `ingest.py`, `pipeline.py`, `test_contract_specs.py` |
| H02 | Agenten und autonome Scans teilen pro HTTP-Versuch ein persistentes Tages-/Monatsbudget mit transaktionaler Reservierung. Unklare Transportkosten und offene Reservierungen werden konservativ behandelt. Sämtliche Retry-Antworten bleiben erhalten. Äußere Rollenprotokolle sind Kostenspiegel, keine zweite Buchung. | `agenten/budget.py`, `journal.py`, Rollen, `llm/client.py`, Hub-/Budgetregressionen |
| H04 | Unbekannte oder mehrdeutige Kandidaten, doppelte Identitäten, unprüfbare Prozentzeilen, ungültige Gewichte und positive Gewichte nichtgrüner Signale sperren das Portfolio. Ungültige Rohantworten werden gesondert archiviert, ohne Portfolio-Freigabe oder Portfolio-PDF. | `verdict_check.py`, `pipeline.run_portfolio`, `tests/test_gesamt_review_hub_fixes.py` |
| H05 | Status mit einer anderen gemeldeten Job-ID ist kein Erfolg des gestarteten Jobs. | `client_updates.py`, Hubregressionen |
| H06 | Berichtscache prüft neben Dateiname und Größe auch den gelieferten Änderungszeitpunkt und tatsächliche Dateigröße. Geänderte gleich große PDFs werden erneuert. | `downloader_sync.py`, Hubregressionen |
| H07 | Cachewrites verwenden eindeutige temporäre Dateien; Schreibvorgang und DB-Vermerk desselben Artefakts werden innerhalb des Prozesses koordiniert. | `ingest.py`, parallele Hubregression |

Die Gegenprüfung der Umsetzung ergänzte Regressionen für gemischte
Namens-/ID-Doppelungen, ungeparste Allokationszeilen sowie den Tages- und
Monatswechsel der Budgetbuchung. Diese Fälle waren im ursprünglichen Review
noch nicht gesondert aufgeführt.

**Bewertungsversion:** `FORENSICS_VERSION=17`. Persistierte Equity-Studien
tragen ebenfalls diese Version; ältere Zeilen bleiben erhalten, werden
aber nicht als aktuelle Messung wiederverwendet. Berichts- und
Übersichtscaches sind entsprechend invalidiert. Ein bloßes Anzeigen alter
Ergebnisse ersetzt keine erneute fachliche Analyse.

## Quellenprogramme

| Review | Korrektur |
|---|---|
| P-A01 | Pelican akzeptiert keine nichtleeren Katalogarrays mit fachlich ungültigen Datensätzen als erfolgreichen leeren Katalog. Der bestehende Katalog wird dadurch nicht still geleert. |
| P-A02 | Pelican lädt die zur aktualisierten Trade-Basis nötigen Stats frisch. Ein fehlender aktueller `RealisedReturn` wird nicht durch einen alten Wert ersetzt. |
| V-A01 / Z-A01 / QB-R4 | Stufe 0 aktualisiert auch bekannte Vantage-, Zulu- und Robo-Historien. IDs dienen zur Dublettenvermeidung/Archivzusammenführung; ein SHA allein gilt nicht als zeitliche Frische. |
| V-A02 / Z-A02 / QB-R8 | Fehlender oder nichtendlicher PnL, unbekannte Richtungen/Entry-Arten und unvollständige Pflichtdaten werden nicht in gültige Null-Gewinn-/Sell-Trades umgedeutet. Semantische Prüfung gilt auch beim Cachelesen. |
| V-A03 / Z-A03 | Wiederholte Seiten werden anhand von Trade-IDs erkannt. Ein Cursor-/Seitenlauf ohne neue IDs endet mit ausdrücklichem Fehler statt duplizierten Trades oder endloser Pagination. |
| V-A04 / Z-A04 / QB-R5 | Fehler und Abbrüche sind im Update-Ergebnis strukturiert enthalten. MQL-Workerfehler werden an den Gesamtlauf zurückgegeben. `done` alleine bedeutet keinen vollständig erfolgreichen Datenstand. |
| V-A05 / Z-A05 | Nichtpositive oder zeitlich unbelegte implizite DD-Kapitalbasen erzeugen keinen konkreten DD0. Kennzahlen kennzeichnen Basis/Fenster; alte DD-Werte werden bei fehlender neuer Basis entfernt. |
| V-A06 / Z-A06 | Standardprompts behaupten weder eine unbelegte Glättungsursache noch historischen Max-Equity-DD aus Closing-Daten. Nur exakt erkannte alte Standardvorlagen werden migriert; individuelle Vorlagen bleiben erhalten. |
| QB-R1 | Robo-MT5-Verarbeitung bilanziert Teilmengen und Umkehr per FIFO. Die Restposition bleibt offen; realisierter Umkehr-Profit wird nicht nochmals als Eröffnungsgewinn gebucht. |
| QB-R2 | OUT-Deals ohne belegtes IN bekommen keine erfundenen Eröffnungszeiten/-preise. PnL bleibt in Finanzdaten/JSON erhalten; Qualitätsmetriken benennen die Lücke und der Scanner-CSV-Export scheitert ausdrücklich. |
| QB-R3 | Robo-Closing-DD behandelt Einlagen/Entnahmen nicht als Handelsgewinn. |
| QB-R6 | MQL serialisiert verschachtelte Update-Ergebnisse als JSON-Objekte. Ungültige Update-Bodies werden mit HTTP400 zurückgewiesen. |
| QB-R7 | MQL erhält Originaldateien bei fehlender MPDD-Basis und technischen Konvertierungsfehlern. Unbekannt ist nicht MPDD0. |
| QB-R9 | MQL-JSON-Trades erhalten wiederholte CSV-Header positionsbezogen, einschließlich Eröffnungs- und Schlussfeldern. |
| QB-R10 | Robo-Stores verwenden eindeutige Tempdateien und gemeinsame pfadbezogene Schreibkoordination über Storeinstanzen. |
| QB-R11 | MQL-Cacheidentität prüft die vollständige Signal-ID statt nur ein überlappendes Dateinamenspräfix. |
| QB-R12 | MQL und Robo reservieren den Updatejob atomar bereits vor dem Hintergrundstart; parallele Starts erhalten nicht zwei Erfolgszusagen. |
| Paginierungsrandfall | Die aktualisierten REST-Seitenberechnungen verwenden überlaufsichere Grenzen für große gültige Offsets. |

Die Gegenprüfung ergänzte zwei weitere Schutzfälle: MQL-Terminalzustände
bleiben auch bei parallelen Fortschrittsmeldungen abgeschlossen; Robo
weist Mengen unterhalb seiner Aggregationsauflösung ausdrücklich zurück,
statt dazugehöriges PnL als vermeintlich leere Historie zu verlieren.
Pelican, Vantage und Zulu akzeptieren persistierte Closing-DD-Werte nur
mit Modellversion 2; unversionierte Altwerte bleiben bis zur Neuberechnung
unbekannt. Pelicans aktuelle Renditebasis wird in Initial-, Delta- und
GUI-Downloads geprüft. Historische Standardprompt-Fixtures in Vantage/Zulu
erzwingen LF-Zeilenenden, damit ihre bytegenaue Migration auch in einem
Windows-Checkout reproduzierbar bleibt.

Zu jeder Quellenänderung gehören Offline-Regressionen im betreffenden
Repository. Die Quellen-READMEs und Vertragsbeschreibungen erläutern
Frische, Teilfehler, Kennzahlengrenzen und nötige Starts.

Eine Dokumentationsbehauptung des Ausgangsreviews wurde ausdrücklich
verworfen: Robos `run.bat` war bereits im geprüften Commit getrackt, ebenso
MQLs `start.bat`. Dafür war kein neuer Launcher nötig. Die MQL-Startanleitung
nennt nun den tatsächlich vorhandenen Weg.

## Testnachweis

Der abschließende Teststand und die überprüften Dateihashes werden im
Unterverzeichnis `behebung_nachweise/` dokumentiert. Die Builds verwenden
Git-Archive mit einem protokollierten Overlay aller aktuellen Änderungen;
ein Archiv des alten HEAD allein wäre kein Nachweis der Korrekturen.
Die Tests führen keine Plattformlogins, bezahlten Modellaufrufe,
Terminalstarts oder Orders aus.

| Lauf | Ergebnis |
|---|---|
| Scanner-Vollsuite auf eingefrorenem Fixstand | 1.953 bestanden, 4 optionale private Originalexporte übersprungen, 4 LLM-Tests abgewählt; 571,49 s |
| Scanner-Abschluss nach Portfolio-/Budgetgegenprüfung | 354 bestanden, 4 LLM-Tests abgewählt; 235,55 s. Enthält alle danach geänderten Budget-, Rollen-, Portfolio-, LLM- und Quellenvertragspfade einschließlich UI. |
| Pelican: finale Offline-Suite und Package | 179 bestanden, keine Fehler/Skips |
| Zulu: frischer Windows-Checkout und Package | 116 bestanden, keine Fehler/Skips |
| Vantage: frischer Windows-Checkout und Package | 59 Java-Tests und 12 Python-Tests bestanden, keine Fehler/Skips |
| MqlDownloader: finale Offline-Suite und Package | 114 bestanden, keine Fehler/Skips; anschließendes Package ohne erneuten Testlauf erfolgreich |
| RoboForex: finale Offline-Suite und Package | 164 bestanden, keine Fehler/Skips; anschließendes Package ohne erneuten Testlauf erfolgreich |

Die beiden Scannerläufe überlappen sich; ihre Zahlen dürfen nicht zu einer
Gesamtzahl verschiedener Tests addiert werden. Die 12 nach dem Vollsnapshot
ergänzten Regressionen (fünf Portfolio-, sieben Budgetfälle) bestehen im
Abschlusslauf. Eine SyntaxWarning des Vollsnapshots betraf einen Teststring
mit Windows-Pfad; dieser verwendet inzwischen einen identischen Raw-String
und ist im Abschlusslauf ohne Warnung geprüft.

## Betrieb und verbleibende Grenzen

**Zusätzliche Abhängigkeitskorrektur:** Beim ersten MQL-Push meldete GitHub
acht konkrete Sicherheitsmeldungen. WebDriverManager wurde auf 6.1.0,
jsoup auf 1.23.2 und Log4j API/Core gemeinsam auf 2.25.5 aktualisiert.
Alle 114 MQL-Tests und der vollständige Paketbau bestanden erneut; die
Versionen sind auch im Distributions-JAR nachgewiesen. Details, Advisory-
Primärbelege und Java-Kompatibilitätsgrenzen stehen im
[gesonderten Nachweis](behebung_nachweise/dependabot_mql/RESULT.md).
Dies belegt behobene verwundbare Paketversionen, keinen zuvor ausgeführten
Angriff auf die Anwendung und keine generelle Sicherheitsgarantie.
Nach Push von `908c69088a1fc8c36f20c3bffec7b3f9338bb987` meldete die
GitHub-API am 16.10.2026 alle acht Alerts als `fixed` und keinen offenen
Dependabot-Alert für MqlDownloader; der API-Beleg liegt unter
`behebung_nachweise/dependabot_mql/alerts_after.json`.

1. Die geänderten Quellen neu bauen und deren laufende Programme neu starten;
   auch den Scanner neu starten. Ein laufender alter Prozess übernimmt keinen
   gepushten Quellcode automatisch.
2. Betroffene Historien mit den korrigierten Quellen erneut aktualisieren,
   anschließend Signale im Scanner neu laden und analysieren. Diese Arbeit
   wurde bewusst nicht auf den produktiven Datenbanken ausgeführt.
3. Bereits erzeugte historische PDFs bleiben historische Artefakte; erst neu
   erzeugte Berichte verwenden die neue fachliche Grundlage.

Die vollständige Composite-Identität in der zentralen Signaltabelle und die
Betreuung nicht-MQL5-basierter Signale bleiben dokumentierte Ausbaupunkte.
H1-Schlusskurse belegen keine Intrabar-Tiefs. Nicht beobachtete aktuelle
offene Positionen, ungeklärte Plattform-Währungs-/Gebührensemantik sowie
reale Kopierslippage können durch Offline-Tests nicht bewiesen werden.
Statistische Schwellenkalibrierung, Walk-forward-Validierung und die
Behauptung künftiger bester Signale bleiben außerhalb dieser Bugkorrektur.
MqlRealmonitor und PelicanWinnerLooser bleiben wie vereinbart unintegriert.
