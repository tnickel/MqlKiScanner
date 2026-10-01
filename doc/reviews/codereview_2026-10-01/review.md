# Codereview der Signalauswahl und KI Bewertung vom 1 Oktober 2026

Das Auswahlverfahren ist nachvollziehbar, aber noch nicht zuverlässig genug, um seine Ausgabe als die besten Signale zu behandeln. Vier schwerwiegende Codefehler betreffen die Drawdown-Schranke, die Datenidentität und den autonomen Monatslauf. Zusätzlich widersprechen echte KI-Antworten den verbindlichen Bewertungsregeln. Die bekannten Korrekturen B1 bis B3 sowie B20 und B21 wirken im neuesten Lauf; die früheren falschen grünen Pelican-Signale sind deshalb nicht als aktuelle Fehler zu melden.

Geprüft wurde HEAD `a43d728`, insbesondere Pipeline, Auswahl, Forensik, Scoring, Ampel, fünf Workflow-Prompts, LLM-Client und Scan-Launcher. Drei parallele Teilreviews wurden durch Gegenproben und einen Abgleich der echten Laufdaten zusammengeführt. Es wurden keine Handelsaktionen, neuen Scans oder echten Modellaufrufe ausgeführt. Produktivcode wurde nicht geändert.

## Maßgeblicher Lauf und Belege

Der echte aktuelle Vollscan ist Agentenlauf **98**, gestartet am **30.09.2026 um 23:40:13**, beendet am **01.10.2026 um 02:43:30**, Europe/Berlin. Sein vollständiges Dateiprotokoll liegt in [scan_full_err.log](../../../tmp/scan_full_err.log). Der Name bedeutet hier Standardfehler-Ausgabekanal; diese Datei enthält auch normale INFO-Meldungen. `scan_full_out.log` ist leer. `data/scan_workflow.log` beschreibt dagegen den älteren GUI-Lauf vor den Korrekturen.

Die SQLite-Auswertung ist in [lauf_audit.json](lauf_audit.json) gespeichert. [audit_run.py](audit_run.py) wiederholt den Abgleich ausschließlich lesend. Sie berücksichtigt 162 aktuelle Einzelanalysen und das echte Portfolio 1115, nicht spätere Testartefakte.

| Station | Belegtes Ergebnis |
| --- | --- |
| Eingang | 179 MQL5 direkt und 781 Pelican, anschließend 2 nachgeladene Fix-IDs, zusammen 962 |
| Vorfilter | 106 Kandidaten, davon 72 MQL5 und 34 Pelican |
| Auswahl | 18 Ausschlüsse entfernt, 2 Fix-IDs vorne, 30 weitere MQL5 und 30 Pelican, zusammen 62 |
| Erfolgreiche Bewertungen | 54, davon 2 grün, 22 gelb, 30 rot |
| Fehlgeschlagene Bewertungen | 8 Signale, jeweils auch beim zweiten Versuch fehlgeschlagen |
| KI | 54 Trade-Analysen, 54 Risiko-Analysen, 54 Gesamtberichte, 1 Portfolio |
| Tokens laut Laufzähler | 1.866.388 |
| Tokens dauerhaft bei diesen Analysen gespeichert | 1.856.424, Differenz 9.964 |

Die 62 IDs und ihre gesamte Reihenfolge stimmen mit einer separaten Anwendung der Auswahlfunktion auf `data/candidates.json` überein. Es gibt in diesem Lauf keinen belegten Fehler in der Umsetzung der Top-N-Auswahl. Die Qualität dieses Vorfilters ist eine andere Frage.

## Schwerwiegende Codefehler

### F1 P1 Relativer Equity Drawdown wird zu niedrig ausgegeben

**Ort:** [equity_rekonstruktion.py Zeile 316](../../../src/mqlkiscanner/forensics/equity_rekonstruktion.py#L316), Bereich 310 bis 318.

`dd_pct` wird nur aktualisiert, wenn der Rückfall einen neuen Höchstwert in USD erreicht. Nach Kontowachstum kann deshalb ein früherer größerer relativer Verlust durch einen späteren niedrigeren Prozentverlust ersetzt werden.

**Gegenprobe:** Equity `1000 → 600 → 2000 → 1500`. Der maximale relative Drawdown ist **40 %**. Der Code meldet **25 %**, `verlaesslich=true`; dieser Wert lässt die 30-Prozent-Schranke unverletzt. Die echte Auto-GMT-Erkennung findet in der synthetischen Probe eindeutig Offset 0.

**Korrektur:** Dollarmaximum und relatives Maximum getrennt führen, wie es `drawdown._max_drawdown` bereits tut. Das relative Maximum muss in Schranke, Score und Bericht gelangen.

### F2 P1 Ein fehlender Kurs erzeugt einen erfundenen Equity Verlust

**Ort:** [equity_rekonstruktion.py Zeile 272](../../../src/mqlkiscanner/forensics/equity_rekonstruktion.py#L272), insbesondere 272 bis 289 und 327 bis 328.

Fehlt der Kurs eines offenen Trades, setzt der Code ein Unvollständigkeitsflag, lässt dessen Floating-PnL weg und schreibt trotzdem den unvollständigen Kontowert in die Equity-Kurve. Bei mindestens 95 % Abdeckung wird der dadurch veränderte Drawdown als verlässlich verwendet.

**Gegenprobe:** XAUUSD hat 50 Stunden konstant **+500 USD** Floating-PnL; eine einzelne XAUUSD-Bar fehlt, während ein zweites Symbol an dieser Stunde Daten liefert. Die tatsächliche synthetische Equity hat **0 % Drawdown**. Der Code erzeugt einen Rückfall von 1500 auf 1000 und meldet **33,33 % DD**, **98 % Abdeckung**, `verlaesslich=true`. Damit kann ein geeignetes Signal fälschlich an der harten Schranke scheitern. Fehlende Verlust-PnL kann umgekehrt Risiken verdecken.

**Korrektur:** Unvollständige Equity-Punkte nicht als vollständige Messwerte buchen. Die verbleibende Kurve und ihre Abdeckung müssen eine dokumentierte Lückenpolitik erhalten.

### F3 P1 Der Kollisionsschutz schützt nur das Quellenlabel

**Ort:** [db.py Zeile 221](../../../src/mqlkiscanner/db.py#L221), UPSERT 239 bis 253 und `store_scan_result` 313 bis 317; Direktpfad in [pipeline.py Zeile 1250](../../../src/mqlkiscanner/pipeline.py#L1250).

Bei identischer numerischer ID aus einer anderen Quelle loggt `upsert_signal` „ID-Kollision abgewehrt“, setzt lediglich `quelle` auf die bisherige Quelle zurück und überschreibt anschließend Name, Plattform und Kennzahlen. `store_scan_result` ersetzt zudem Forensik und Trade-Snapshot. Der Direktpfad übergibt kein Quellenfeld und umgeht dadurch die Prüfung in der Gegenrichtung.

**Temp-DB-Gegenprobe:** Zuerst MQL5 ID 123, dann unabhängiges Pelican-Signal ID 123. Danach stehen Pelican-Name, Pelican-Plattform und Pelican-Forensik unter dem Label `mql5`. In der Gegenrichtung erhält ein Pelican-Datensatz MQL5-Inhalte unter seinem alten Pelican-Label.

**Korrektur:** Bei Konflikt die gesamte Transaktion zurückweisen oder konsequent die Identität `(Quelle, Signal-ID)` verwenden. Ein unverändertes Quellenlabel allein ist kein Kollisionsschutz. Die frühere Aussage, R1 sei vollständig behoben, ist durch diese Gegenprobe widerlegt.

### F4 P1 Ein Login Abbruch verbraucht den Monatstermin

**Ort:** [scan_launcher.py Zeile 69](../../../src/mqlkiscanner/agenten/scan_launcher.py#L69), 69 bis 79 und 157 bis 170; Monatsprüfung in `scheduler.py` 170 bis 172.

Bei fehlendem oder fehlgeschlagenem MQL5-Login liefert `_scan_innerhalb` ein normales Ergebnis mit null Prüfungen. `starte_scan` meldet trotzdem `status=ok`, schreibt „durchgeführt“ ins Journal und setzt den Monatsmerker. Der Scheduler behandelt den Full-Scan danach als diesen Monat bereits erledigt.

**Isolierte Gegenprobe:** Ergebnistext „MQL5-Login fehlgeschlagen“, null Prüfungen, aber erfolgreicher Journaleintrag sowie Tages- und Monatsmerker. Der vorhandene Test `test_agenten_phase_e.py` 156 bis 163 bestätigt derzeit sogar dieses Verhalten.

**Korrektur:** Abbruch, leerer Scope und erfolgreiche Ausführung strukturiert unterscheiden. Den Monatsabschluss nur für einen tatsächlich erfolgreich ausgeführten Lauf setzen; Erfolgsmeldungen müssen Ausfälle und den geprüften Anteil nennen.

Die Fehler F1 und F2 sind vollständig durch [equity_probes.py](equity_probes.py) reproduzierbar; Ergebnisse stehen in [equity_probe_results.json](equity_probe_results.json). **Eine Auswirkung dieser Rekonstruktionsfehler auf die beiden aktuell grünen Signale ist nicht bewiesen.** Die damaligen H1-Kursreihen sind nicht dauerhaft gespeichert und können aus den vorhandenen Zusammenfassungen nicht korrigiert nachgerechnet werden.

## Weitere bestätigte Codefehler

### F5 P2 Die Kursabdeckung zählt vollständig fehlende Stunden nicht

**Ort:** [equity_rekonstruktion.py Zeile 207](../../../src/mqlkiscanner/forensics/equity_rekonstruktion.py#L207), Raster 207 bis 208, Nenner 320 bis 328.

Das Raster besteht ausschließlich aus vorhandenen Barzeiten. Stunden ohne Bars irgendeines Symbols verschwinden damit aus dem Abdeckungsnenner. Eine synthetische Gegenprobe mit acht offenen H1-Stunden und nur drei verfügbaren Stunden meldet **100 %** und `verlaesslich=true`; tatsächlich sind **37,5 %** belegt. Auch diese Probe verwendet die echte GMT-Erkennung. Der Nenner muss aus einem unabhängig definierten Handelszeitraum stammen; reguläre Marktpausen sind dabei ausdrücklich zu behandeln.

### F6 P2 Reine Quellen Scans verlangen einen MQL5 Login

**Ort:** [scan_launcher.py Zeile 156](../../../src/mqlkiscanner/agenten/scan_launcher.py#L156), GUI `app_pages/scan.py` 749 bis 763.

Der autonome Pfad erzwingt MQL5-Credentials und Browser-Anmeldung auch für ausschließlich gültige REST-Kandidaten. Ohne Credentials erhält ein reiner Quellenlauf null Bewertungen. In der GUI reicht ebenfalls ein vorhandener, aber fehlgeschlagener MQL5-Login, um REST-Kandidaten zu blockieren. Die Anmeldung ist nur für tatsächlich benötigte Direkt-Exporte erforderlich. Zusammen mit F4 kann dies den autonomen Quellen-Monatslauf vollständig unterdrücken.

### F7 P2 Die Doppelungsbereinigung vergleicht unterschiedliche Schreibweisen

**Ort:** [pipeline.py Zeile 810](../../../src/mqlkiscanner/pipeline.py#L810), Crawler liefert `MT5` beziehungsweise `MT4`, Ingest liefert `mt5` beziehungsweise `mt4`.

Der Vergleich `(ID, Plattform)` normalisiert die Plattform nicht. Derselbe MQL5-Eintrag direkt und im Downloader-Spiegel wird dadurch zweimal als Kandidat aufgenommen. Die isolierte Gegenprobe liefert für ID 123 beide Varianten, obwohl die dokumentierte Regel „MQL5-Direkt gewinnt“ lautet. Slots und KI-Aufrufe können doppelt verbraucht werden. Im geprüften Lauf ist dieser Fall wegen des nicht erreichbaren Downloaders nicht aufgetreten. Die Normalisierung muss MQL5-Spiegel berücksichtigen und unabhängige Börsenidentitäten weiterhin getrennt halten.

### F8 P2 Bezahlte Wiederholungen fehlen im dauerhaften Tokenverbrauch

**Ort:** [llm/client.py Zeile 198](../../../src/mqlkiscanner/llm/client.py#L198), Metadatenersetzung 198 bis 199, Length-Retry 206 bis 225; Speicherung in `llm_runner.py` 193 bis 196 und Agentenjournal.

Ein bezahlter, abgeschnittener Modellaufruf wird bei erfolgreicher Wiederholung im Laufzähler gezählt, seine Metadaten werden aber durch den letzten Versuch ersetzt. Der dauerhaft gespeicherte Tokenwert enthält nur diesen letzten Versuch.

**Offline-Gegenprobe mit Original-Clientcode:** Erster Versuch 10 Tokens, erfolgreicher Retry 20 Tokens. Laufzähler **30**, `meta_out.total_tokens` **20**. Das Agentenbudget summiert die gespeicherten Journalwerte und kann dadurch zu viel Restbudget ausweisen. Der normale Scan-Laufzähler zählt korrekt weiter.

Die beobachtete Differenz von **9.964 Tokens** im Lauf 98 passt zu diesem Fehler. Die genaue Zuordnung zu einem bestimmten Modellaufruf ist **nicht rekonstruierbar**; die Erklärung der Laufdifferenz ist eine begründete Einschätzung, während der Clientfehler unabhängig reproduziert ist. Alle Versuche eines logischen Aufrufs müssen abgerechnet und einzeln nachvollziehbar gespeichert werden.

### F9 P2 Die Testisolation erreicht nicht alle Module und Dateien

**Ort:** [tests/conftest.py Zeile 58](../../../tests/conftest.py#L58), [test_portfolio_statistik.py Zeile 16](../../../tests/test_portfolio_statistik.py#L16), [scan_fortschritt.py Zeile 27](../../../src/mqlkiscanner/scan_fortschritt.py#L27).

Die Fixture isoliert `mqlkiscanner`, einige neuere Tests importieren aber `src.mqlkiscanner`. Python lädt dadurch unterschiedliche Modulobjekte. Die zweite Datenbankkonfiguration bleibt produktiv. Zusätzlich wird `STATUS_DATEI` einmalig aus `DATA_DIR` berechnet; ein späteres Patchen der Konfiguration isoliert diesen Pfad nicht.

**Tatsächlicher Beleg während dieses Reviews:** Der Portfolio-Test erzeugte am 01.10. um 10:20:14 in der produktiven DB Analyse **1116**, Text `Portfolio ok`, Tokens 0, sowie eine PDF. Launcher-Tests überschrieben die produktive Fortschrittsdatei mit einem synthetischen laufenden Scan. Die Testzeile wurde nach Prüfung ihrer vollständigen Identität entfernt, die Test-PDF in `.tmp/review_20261001_quarantine` verschoben und der Fortschritt auf den tatsächlich abgeschlossenen Lauf 98 zurückgesetzt. Die ursprünglichen Mikrosekunden der Fortschrittsdatei sind nicht erhalten; der wiederhergestellte Inhalt bezeichnet den realen Abschluss. Belege stehen in `test_isolation_evidence.json` und `test_progress_evidence.json`. Das echte letzte Portfolio ist weiterhin **1115**.

**Korrektur:** Einheitlichen Paketimport verwenden und jeden Speicherpfad explizit isolieren oder erst beim Zugriff aus der Konfiguration auflösen. Ein grüner Testlauf beweist derzeit keine vollständige Isolation.

## Fehler in echten KI Antworten

### K1 P2 Die KI erfindet zusätzliche Pflichtprüfungen

**Ort:** [pipeline.py Zeile 512](../../../src/mqlkiscanner/pipeline.py#L512), Payload 512 bis 557, besonders Kapitalbasis 544 bis 547.

Das Forensik-JSON enthält weder den tatsächlichen Vollständigkeitsstatus noch die einzelnen Pflichtprüfungsstatus. Belegte CSV-Kapitalbasis wird sogar bewusst als `kapitalbasis_verwendet=null` übergeben; nur virtuelle und implizite Basis werden genannt. Optionale Reko- und Monitorfelder können ebenfalls null sein.

In **18 der 54 aktuellen Gesamtberichte** erklärt die KI daraus die Pflichtbatterie fälschlich für unvollständig, obwohl die Engine `vollstaendig=true` gespeichert hat. SolarFlare, Bericht **1018**, fordert sowohl Rekonstruktion als auch Monitor-DD als Voraussetzung für eine positive Einstufung. HRC Algo, Bericht **1108**, verlangt zusätzlich die fehlende Rekonstruktion trotz vorhandenem Monitorwert. KiraCat, Bericht **955**, behandelt auch den nullwertigen Payload der tatsächlich vorhandenen CSV-Basis als fehlende Kapitalbasis.

Die gelben Engine-Farben können wegen Score oder Ertrag trotzdem korrekt sein. **Falsch sind die zusätzlichen Sperrgründe und die daraus abgeleiteten Nachprüfungen.** Fehlende optionale Kurse dürfen nach Projektregel neutral bleiben. Tatsächliche Basis und Vollständigkeit müssen in jedem Payload enthalten sein; optionale Messungen brauchen einen ausdrücklichen Status.

### K2 P2 Die Portfolio Aufnahme widerspricht den Einzelurteilen

**Ort:** [pipeline.py Zeile 1355](../../../src/mqlkiscanner/pipeline.py#L1355), Aufnahme 1355 bis 1357, Einzelberichte nur als Freitext 1373 bis 1378, Completion-Speicherung 1407 und 1420 bis 1422.

Gold Spike MT5 wird im frischen Gesamtbericht **958** als **WATCHLIST**, KI-Risikoscore **6 von 10**, eingestuft. Gold Spike MT4 wird in Bericht **970** ebenfalls als **WATCHLIST**, KI-Risikoscore **5 von 10**, eingestuft. Das finale Portfolio **1115** empfiehlt trotzdem ausdrücklich „kopieren“, mit **60 % MT4 und 40 % MT5**. Eine begründete Aufhebung der vorherigen Vorbehalte fehlt.

Die stärkste Gegenposition: Nach aktivem Prompt gelten die Engine-Felder als bindend, die Einzelberichte sind qualitative Interpretation. Ein Stage-3-WATCHLIST-Gate ist aktuell **nicht** implementiert; daher ist dies kein Verstoß gegen eine bereits bestehende technische Sperre. Es bleibt aber ein belegter Widerspruch der für den Nutzer sichtbaren Auswahl. Ein strukturiertes KI-Urteil mit Bedingungen oder eine ausdrückliche Auflösung solcher Widersprüche ist erforderlich.

### K3 P2 Die KI verletzt die SL Neutralitätsregel

**Ort:** aktive Regeln in [portfolio.md Zeile 65](../../../config/prompts/portfolio.md#L65) und `gesamtbericht.md` 75; fehlende Ergebnisvalidierung im Portfolio-Pfad.

Gold-Spike-Bericht **970** fordert Ablehnung bei Wegfall des **SL-Nachweises**. Das finale Portfolio **1115** fordert sogar sofortigen Abverkauf beider Positionen bei Wegfall des SL-Nachweises beim MT4-Signal. Die Nutzerregel unterscheidet jedoch fehlende Datenübertragung von tatsächlichem Verlust des Stop-Schutzes; nur Ersteres ist neutral. Ein technischer Nachweisverlust allein darf diese Handlung nicht auslösen.

Das Portfolio verkürzt zudem den Sferica-Ausschluss auf „0/296 SL“. Der Einzelbericht enthält eine begründete negative Verhaltenseinschätzung; diese zulässige Begründung wird im finalen Kurzurteil durch das unzulässige reine Nichtvorliegen ersetzt. Die Engine wird dadurch nicht geändert, aber die dem Nutzer vorgelegte Handlungslogik verletzt seine feste Vorgabe. Prompt-Härtung allein genügt hier nachweislich nicht.

## Genau geprüfte Logprobleme

| Signal | Endgültiger Fehler | Beleg im aktuellen Log |
| --- | --- | --- |
| MySingalStart 2, 840474 | CSV-Pflichtfeld fehlt, Zeile 9227 | 205 und 216 |
| MySingalStart 3, 1760039 | CSV-Pflichtfeld fehlt, Zeile 12115 | 332 und 343 |
| BTC One Shot, 2368681 | Keine belegte Kontraktgröße für DE30M und XCUUSDM | 282 und 294 |
| AIT FX, 2019435 | USOIL-Kontraktspec nicht für AxiTrader2 anwendbar | 423 und 435 |
| Mtrader2, 2000892 | USOIL-Kontraktspec nicht für AxiTraderUs07Live anwendbar | 633 und 645 |
| Mtrader Holy, 2005451 | Dieselbe USOIL-Sperre | 779 und 791 |
| Yu Trading Club, 2007510 | USOIL-Kontraktspec nicht für AxiTrader5 anwendbar | 857 und 869 |
| TradeSystem, 2019075 | Rekonstruierter Kontostand bei offenen Positionen nicht positiv | 740 und 746 |

Diese Fehler wurden laut Log abgefangen und sind im DB-Feld `last_fehler` nachvollziehbar. Kein positiver aktueller Forensikstatus wurde für diese acht Signale bestätigt. **Die Datenabwehr ist hier überwiegend korrekt.** USOIL darf ohne belegte brokerbezogene Kontraktgröße nicht pauschal freigeschaltet werden. Die vier im Log genannten temporären CSV-Dateien wurden bereits gelöscht; ob die beiden CSV-Probleme abgeschnittene Downloads oder ein bislang unbekanntes Zeilenformat waren, lässt sich aus diesen Logs allein nicht entscheiden.

Der Quellenkatalog `mql5` unter `localhost:8089` war nicht erreichbar, während die Einzelkonfiguration `downloader_base_url` auf `192.168.178.164:8089` zeigt. Pelican antwortete mit 781 Einträgen, MQL5-Direkt funktionierte. Dies ist eine belegte Konfigurationsabweichung und fehlende Quellenabdeckung, kein kompletter Scanabbruch. Die jüngste gespeicherte Quellenprüfung am 01.10. um 10:13 bestätigt denselben Erreichbarkeitszustand; während dieses Reviews wurde kein neuer Verbindungstest ausgelöst.

Zwei weitere Meldungen sind konkret falsch:

- Quellen-Logs vertauschen **Cache** und **neu geladen**: `ingest.hole_trades` liefert `(Pfad, geändert)`, `pipeline.py` 972 und 995 bis 996 interpretiert das Flag als `from_cache`. Die verwendeten Bytes bleiben richtig; die Herkunftsmeldung ist falsch.
- Grid King, Bericht **1090**, Kurzfassung im Log **1110**, nennt **70,64 %** als Verletzung der **30-%-Schranke um Faktor 18**. Tatsächlich ist `70,64 / 30 = 2,35`. Faktor etwa 18 gehört zum Vergleich mit der Anbieterangabe **3,94 %**. Die rote Ampel und die ausführliche Erklärung bleiben korrekt.

Die endgültige Erfolgsmeldung „54 Signale geprüft“ nennt weder die 62 Versuche noch die acht dauerhaften Ausfälle. Sie ist als Abschluss einer teilweise erfolgreichen Ausführung verständlich, vermittelt aber ohne das vollständige Log keine vollständige Abdeckung. Zwei ältere CLI-Journaleinträge, **95 und 97**, stehen weiterhin auf `laeuft` ohne Abschluss. Das beweist keinen noch laufenden Prozess; der Journalstatus ist unbereinigt.

## Bewertung des Verfahrens für die besten Signale

**Gesicherter Fakt:** Die Vorauswahl sortiert nach Abonnentenzahl, siehe `fix_signale.py` 98 bis 100. Von 88 grundsätzlich zulässigen Kandidaten bleiben **26 ungeprüft**: 22 MQL5 und vier Pelican. Weitere Signale fallen bereits durch den Listen- und Altersfilter. Belegt sind damit geeignete Kandidaten **im untersuchten Ausschnitt**, keine global besten Handelssignale.

**Stärkste Gegenposition:** Top-N je Quelle begrenzt Kosten und Laufzeit und verhindert, dass eine Quelle alle Slots belegt. Fix-IDs sichern die Beobachtung bekannter Kandidaten. Diese Betriebsentscheidung ist vertretbar; sie liefert aber keinen Qualitätsbeweis für populäre Signale und keinen Nachweis einer optimalen Auswahl.

Im neuesten Lauf erfüllen nur folgende Signale den aktuellen grünen Engine-Weg:

| Signal | Engine-Score | Maßgeblicher DD laut Bestand | Forensischer Monatswert | Besonderheit |
| --- | --- | --- | --- | --- |
| Gold Spike MT4, 2349227 | 4,1 | 8,11 % | 8,71 % | SL im Orderbuch für 393 von 393 Positionen belegt |
| Gold Spike MT5, 2375480 | 4,9 | 9,17 % | 20,85 % | SL-Nachweis neutral, gemeinsames Instrument XAUUSD |
| KiraCat, 2342895 | 6,3, gelb | 25,98 % | 21,55 % | Hoher Schockwert, zuletzt schwache Monatskurve |

Die beiden grünen Varianten sind **keine Diversifikation**: gleiches Instrument, gleicher Autorenname und Strategiecharakter. Der neue Portfolio-Bericht sagt dies selbst ausdrücklich und nennt nur **fünf gemeinsame beobachtete Monate**. Die Gewichte 60/40 sind eine qualitative LLM-Entscheidung; im Code gibt es keinen berechneten Portfolio-Stressverlust oder mathematischen Nachweis, dass diese Gewichtung optimal ist. Ein kleiner historischer DD kann keine zukünftige maximale Verlustgrenze garantieren.

Die B2-Renditerechnung ist arithmetisch richtig, bedeutet jedoch **linearer Nettoertrag bezogen auf das ursprüngliche Startkapital je historischem Monat**. Sie ist weder zeitgewichtet noch eine geometrische Monatsrendite. Besonders KiraCat erhielt nach Handelsbeginn weitere positive Kontobewegungen von rund 17.858,56 USD. Seine 21,55 % sind deshalb kein belegter vergleichbarer monatlicher ROI für heutiges Kopierkapital und keine Widerlegung der Plattformangabe 3,46 %. Unterschiedliche Kapitalbasis, Messfenster und Definition sind offenzulegen.

Zur Nachrechnung: KiraCat Netto 21.737,55 USD / Basis 9.535,48 USD / 10,578 historische Monate ergibt 21,55 %. Gold Spike MT4 2.933,58 / 3.116,00 / 10,808 ergibt 8,71 %. Gold Spike MT5 1.069,21 / 1.246,00 / 4,116 ergibt 20,85 %. KiraCats virtuelle Kalender-Monatskurve fällt zuletzt auf 0,79 %, 0,68 % und 0,04 % für Juli bis September. Ein Lebenszeitdurchschnitt verdeckt diese jüngste Leistung.

Die Pflicht-Konsistenzprüfung aus `doc/03` ist außerdem nur teilweise automatisiert: Es fehlt ein Plattform-Abgleich der Monatsnettos und DD-USD. Der Endbalance-Abgleich läuft nur bei externer echter Initial-Deposit-Basis; CSV-, implizite und virtuelle Basen sind ausgenommen. „Forensik vollständig“ belegt hier ausgeführte, berechenbare Module und bestimmte Datenvoraussetzungen, nicht die gesamte in der Spezifikation beschriebene Integritätsprüfung. Ein Cent-Abgleich auf einer aus genau dieser Endbalance zurückgerechneten impliziten Basis wäre ohnehin kein unabhängiger Nachweis.

`portfolio_statistik.py` liefert Verlustmonate, Beobachtungsfenster und Symbol-Overlap, **keine numerische Rendite-Korrelation**. Zwei reine Goldsignale fallen wegen der Schwelle mindestens drei gemeinsamer Symbole nicht als Overlap-Paar in dieser Tabelle auf. Numerisch geringe Korrelation kann aus dem aktuellen Payload nicht begründet werden. Im echten neuen Portfolio wurde dieser Schluss nicht behauptet.

## Verifizierte Korrekturen und Prüfgrenzen

- B1 wirkt: Lemonal, AccurateCopier und Master H4-1 sind im neuesten Lauf rot; der Monitor-DD ist in der Schranke enthalten.
- B2 und B3 wirken: Lexo und PentagonForex sind mit 1,86 beziehungsweise 1,12 % auf impliziter Basis gelb. Die Plattformrendite ist nicht mehr der maßgebliche Grün-Weg.
- B20 und B21 wirken in der echten Antwort: Portfolio 1115 nennt den Juli-Verlustcluster mit sieben Namen und Werten, das Gesamtfenster von zwei Monaten und das ausgewählte Paarfenster von fünf Monaten. Es behauptet für die Gold-Spike-Kombination keine Diversifikation.
- Alle 30 aktuellen roten Gesamtberichte enthalten ABLEHNUNG. Im finalen Portfolio wird kein rotes Signal aufgenommen.
- Die fünf protokollierten Agenten-LLM-Fehler mit `finish_reason=length` stammen vom 22.09.; keine jüngeren solchen Fehler wurden in den Journalzeilen gefunden.
- **158 ausgewählte bestehende Regressionstests bestanden in 37,46 Sekunden.** Ein paralleler Prüflauf mit Auswahl-, Quellen- und Launcher-Tests bestand **62 Tests in 210,08 Sekunden**; die Mengen überschneiden sich. Es wurde kein neuer Gesamtsuite-Lauf und kein echter Modell-Regressionstest ausgeführt. Die aufgefundenen Fälle sind von diesen bestehenden Tests nicht korrekt abgesichert.

Die Aussagen zu ausgeführten historischen Prompts bleiben begrenzt: Antworten, Fakten und aktive Vorlagen liegen vor; vollständige historische Workflow-Prompts werden weiterhin nicht persistiert. Diese bekannte Audit-Lücke bestand bereits im vorherigen Review. Statische Prompt-Härtung und grüne Unit-Tests ersetzen keine inhaltliche Prüfung der tatsächlichen Antworten.

Die sachlich begründete Reihenfolge für weitere Arbeit lautet: zuerst F1 bis F4, anschließend Kursabdeckung und Testisolation, dann strukturierte KI-Ergebnisprüfung und die Quellen-Doppelung. Danach müssen die davon betroffenen Kandidaten erneut geprüft werden. Die aktuelle Empfehlung ist bis zu diesen Nachweisen eine vorläufige Kandidatenauswahl, keine belastbar abgesicherte Auswahl der besten Signale.
