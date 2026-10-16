# MqlDownloader / Vantage: aktuelle Prüfung des Antigravity- und GLM-Katalogs

Stand: 16.10.2026, Basis MqlDownloader `c328b0b`, Vantage `503f34a`, jeweils HEAD-Archiv mit ausschließlich eigenen Source-/Test-/Doku-Overlays. Vollständige Basis-SHAs, Archiv-, Overlay- und Paket-SHA256 stehen in `clients_manifest.json` daneben. Eingaben: Antigravity `review_bericht_signalkiscanner_hub.md`, vollständiger `REVIEW_2026-10-16_Gesamtsystem_Befundkatalog.md` und A–G-Bericht. Deren Quellbasen `92d8f9c`/`1fe3958` sind älter; damalige Live-Beobachtungen sind kein Beleg für den heutigen Code oder einen heute gestarteten Prozess.

Nur MqlDownloader und vantage bearbeitet. Keine Produktionsdaten, Cookies oder Settings gelesen/verändert, keine Plattform-/Broker-/LLM-Aufrufe und keine Produktivinstanz gestartet. Tests liefen ausschließlich in HEAD-Archiven unter diesem Auditverzeichnis, mit synthetischen Temp-Dateien und Loopback-HTTP-Servern. Kein Git-Stage/Commit/Push. Keine neue Auswahl-, TTL- oder Delta-Politik.

## MQL: vollständige ID-Einordnung

| ID | Ergebnis am aktuellen Stand / Beleg |
|---|---|
| MDL-1 | Bereits behoben. `DownloadManager.waitForDownloadCompletion` und `ConversionManager.waitForConversionCompletion` geben Fehler weiter; die GUI-Kaskade schreibt den Vermerk und `fertig` erst nach erfolgreichen Phasen. Catch markiert Fehler. Nachgewiesener neuer Fehler hier nicht reproduziert; keine erneut behauptete Done-Fassade. |
| MDL-2 | Bereits behoben für den tatsächlichen MT5-Positionsheader. `CsvParser.parseLines` erhält doppelte Time/Volume/Price als `_1`/`_2` und Legacy-Schlüssel. `CsvParserTest.duplicateMqlHeadersHaveLosslessAliasesAndLegacyKeys`; Roh-CSV unverändert. |
| MDL-3 | Bestätigt und behoben. Synthetische H2-Baseline plus Änderung: vorher `includeUnchanged=true` count1 statt2. Jetzt Default/false nur Änderungen, true inklusive Baseline; JSON und CSV geprüft. |
| MDL-4 | Bereits behoben. `/providers` filtert standardmäßig Abonnenten>=1 vor Pagination, explizites Quell-API-min0 bleibt möglich. `SubscriberDefaultTest` prüft JSON/CSV und große Pagingwerte. Scanner-min0 bedeutet lediglich keinen zusätzlichen lokalen Filter; es erzwingt keinen unfiltrierten Quellkatalog. Kein neuer globaler Opt-out. |
| MDL-5 | Auswahl-/Beleggrenze, kein neu belegter Sortierparameter-Fix. Selenium versucht die Abonnentenordnung per Header-Klick; aus den ersten zwei Zeilen folgt kein Beweis einer vollständigen globalen Top-N-Liste. REST sortiert den lokal verfügbaren Bestand. Kein Liveabgleich/kein garantierter Plattform-Total; Vorschlag eines unbekannten URL-Sortierparameters nicht übernommen. |
| MDL-6 | Absichtlicher dokumentierter Vertrag: target/tradelisten im Update werden in diesem Downloader nicht fachlich umgesetzt. Unverändert. |
| MDL-7 | Absichtlicher Qualitätsfilter. Gemessenes 3MPDD<0.5 löscht zugehörige Dateien; NaN/unbelegte Eingaben bleiben erhalten und werden als Fehler gezählt. `MPDDDataQualityTest.unknownMpddPreservesHtmlCsvAndPreviousMetrics`. Keine Nutzerregel geändert. |
| MDL-8 | Bestätigt und behoben. Einheit aus exakt zugeordnetem Kontostandwert als `Currency` durch HTML→TXT→REST erhalten; USD/USC/EUR oder `unknown`. Legacy-TXT ohne Einheit liefert unknown. Betrag und Handels-CSV bleiben native Kontowährung; kein USC÷100/kein geratener FX-Kurs. Scanner-Gegenseite übernimmt Root. |
| MDL-9 | Bestätigt und behoben. Vorher 23.456,78/23,456.78 führten zu mehreren Dezimalpunkten; Unicode-Minus ging verloren. Jetzt beide gruppierten Formate, normale Dezimalbeträge, NBSP und Vorzeichen; Gruppierung wird geprüft, nicht beliebig wegstripped. Exaktes Label verhindert Description-Text als Balance. Kein erfundener Label-CSS-Vertrag: bestehende item/value-Struktur genügt. |
| MDL-10 | Gemischt: Ersatz-DD1 bei DD<=0 war bereits entfernt, unbekannt bleibt NaN. Der fehlende Fensterbeleg wurde ergänzt: `Average3MonthProfitMonthsIncluded` nennt tatsächlich gemittelte 0..3 Monate. Neuester exportierter Monat wird ausgeschlossen; ohne Live-Seite ist das kein Beweis für den aktuellen Kalendermonat. Keine Wins/Losses/TradesTotal aus dieser Konvertierung erfunden. |
| MDL-11 | Bereits behoben. `handleDownloadedFile` benutzt die angeforderte ID und `DownloadFiles.findDownload`; validiert Exportheader/Version. Tests `DownloadFilesTest` decken mehrdeutige/fremde Dateinamen und Version ab. Die alte private Suchmethode ist kein aktiver Kontrollpfad. |
| MDL-12 | Bestätigt und behoben. Vorher sort=typo lieferte200/Fallback; version=xyz leere200-Liste. Jetzt400 für unzulässige sort/order/format/version und Events-Boolean. Gültige mt4/mt5-Aliase, ASC, JSON/CSV und bestehende Defaults bleiben nutzbar. |
| MDL-13 | Ohne Liveabgleich nicht entscheidbar: Plattform-Seitengröße, Sortierung, Exportvollständigkeit, Profit-Semantik/offene Positionen. Synthetische versionierte Tests belegen Parser-/Konvertierungsvertrag, nicht Plattformtreue. Keine privaten Trades als Fixture veröffentlicht. |
| MDL-14 | Defensive Verträge erhalten und mit Vollsuite geprüft: Pfad-/Tokenkontrolle, Zustandsmaschine, BOM/CSV, Paging-Clamp, zusammengesetzte MQL4/MQL5-DB-Identität. Die vorhandene downloadDays-Regel bleibt unverändert. |

Zentrale MQL-Codeanker:

- [DataExtractor.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/utils/DataExtractor.java:44): native Zahl, Currency und exakte Kontostand-Zuordnung.
- [HtmlParser.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/utils/HtmlParser.java:36), [HtmlConverter.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/converter/HtmlConverter.java:211), [MetricsParser.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/rest/MetricsParser.java:62): Durchreichen und Altcache-unknown.
- [RestApiServer.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/rest/RestApiServer.java:339): Enumprüfung; Events um Zeile667.
- [ReviewFollowupRestTest.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/tests/rest/ReviewFollowupRestTest.java), [AccountMoneyReviewTest.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/tests/utils/AccountMoneyReviewTest.java): alle neuen MQL-Repros einschließlich echter synthetischer Konvertierung mit 2 statt3 Monaten.

## Vantage: vollständige ID-Einordnung

| ID | Ergebnis am aktuellen Stand / Beleg |
|---|---|
| VAN-1 | Bereits behoben. Kuratierte Listen zuerst; Restbudget geteilt zwischen Kopiererphase (max250) und Returnphase, Überschneidungen nachgefüllt. `RankingUnionTest` mit200/250/600. Keine neue Rendite- oder Qualitätsrangfolge behauptet. |
| VAN-2 | Doppelheader des MT5-Positionsformats ist korrekt und bleibt. Scanner liest positionell; kein Map-bedingter Roh-CSV-Verlust. |
| VAN-3a/b | Bereits behoben: verifizierter Total fehlt/0 oder widersprüchlich -> `TradesTruncated:null`; exaktTotal==Stored ->false, größer ->true. Genau2000 allein beweist keine Kappung. `RestApiServerTest.truncationIsUnknownWithoutVerifiedPlatformTotalAndTriStateOtherwise`. |
| VAN-4 | Bereits behoben. Jeder Update lädt Kennzahlen/Tradefenster frisch, vereinigt die verifizierte Historie und unterscheidet neu/aktualisiert/unverändert. SHA spart Schreibarbeit, nicht den API-Abruf. `UpdateJobStufe0Test`; alte Registereinträge verhindern den Abruf nicht. |
| VAN-5 | Performance-/Vertragsfrage, kein bestätigter Korrektheitsfehler. Abbruch bei erster bekannter ID wäre ohne zugesagte Immutabilität unsicher: bekannte Trades können korrigiertes PnL liefern. `TradeIntegrityTest.positiveArchiveAndCorrectionsSurviveSmallerWindows` belegt notwendige Korrekturübernahme. Keine spekulative Delta-Abbruchregel. |
| VAN-6 | Payload/Tabellencache war bereits für gekappte/unbekannte Historie gesperrt. GUI-Nebenfund bestätigt und behoben: vorher PnL100→80 wurde Plattform-DD20%, obwohl bei Kapital1000 Equity1100→1080 nur1,81818% ergibt. Unbelegter Tages-PnL-Equity-DD entfernt. GUI-Closing-DD und ROI-Kapitalmodell verwenden jetzt denselben Validierungshelper wie Payload/Export; keine 10k-Fallbackbasis als gemessener DD. Virtuelle Return-History nennt ihre Annahme weiter ausdrücklich. |
| VAN-7 | Herkunft bereits vorhanden: ddSource trennt Overview/Ranking/lokalen Closing-DD. Semantik des Plattform-DD (Fees/HWM/Intrabar) bleibt ohne Primärnachweis ungeklärt, keine Umdeutung. |
| VAN-8 | Bereits vorhandene feldweise metricsWindow-Werte und optionale persistierte CSV-Spalten verhindern die Behauptung eines Gesamtfensters für ranking-only/unknown. Das150-Overviewbudget bleibt Auswahl-/Lastregel; Tradephase lädt eigene frische Stats für verarbeitete Provider. Keine neue Netzwerkpolitik. |
| VAN-9 | Legacyname dokumentiert: Average3MonthProfit ist Rankingrendite; Request months=1 wird als1_month belegt, nicht als rechnerischer 3-Monatsmittelwert und auch nicht garantiert exakt30 Tage. Metadata bleibt additiv für alte Consumer. |
| VAN-10 | Bestehender REST-/FX-Vertrag durch Vollsuite geprüft: USD/USC-Normalisierung, Drittwährung nur historisch belegter Kurs, keine Zukunftskurse; Fehler-/Token-/Versionscodes bleiben. Keine erneute Live-Verifikation behauptet. |
| VAN-11a | Bestätigt und behoben. Vorher API1223 auf erster Rankingseite wurde erfolgreiches Listenende/Teilbestand; jetzt propagiert APIfehler. Erfolgreiches leeres Array bleibt reguläres Ende; Schema ohne Array ist Fehler. Kuratierte, ausdrücklich nicht unterstützte Kategorien bleiben separat wie bisher behandelt. |
| VAN-11b | Java-Pflichtfelder bereits validiert: fehlendes Netto-PnL ist kein Nulltrade, Identität/Zeiten/Preise/Lots werden geprüft. Python-Zeitparser zusätzlich konkret gehärtet: bool/fraction/Overflow waren als Timestamp coercierbar bzw. unkontrollierte OSError; jetzt unbelegt statt erfundene1970-Zeit. Neue8 Parameterfälle, davon3 vorher rot. |
| VAN-11c | Geschlossene Trade-CSV bereits strikt: Header/Breite/finite Pflichtwerte/Identitätsduplikate werfen IOException. Kein stiller Verlust geschlossener Trades. |
| VAN-11d | Positions-Sicherheitsdeckel bereits fail-closed: bei Überschreitung Exception, keine erfolgreiche gekappte Positionsliste. `TradeContractTest`. |
| VAN-11e | Bestätigt und behoben. Epoch2025-01-01T23:30Z wurde in Berlin2025-01-02T00:30, damit anderer FX-Schlusstag. Jetzt Java/Python UTC, Chartachsen UTC, kein Rechnerzonenbezug im Exportdatum. Beide Cachefamilien tragenversion2/timeBasisUTC; alte zonenlose Daten werden bewahrt und gesperrt, nicht still verschoben oder durch kleine Fenster ersetzt. REST liefert bei Altcache404 für Trades und unbekannten Closing-DD/TradeTimeBasis. |

Zentrale Vantage-Codeanker:

- [VantageClient.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/api/VantageClient.java:51): UTC; Rankingfehler um Zeile149.
- [SignalPayloadBuilder.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/report/SignalPayloadBuilder.java:43): gemeinsamer Equity-/Abdeckungshelper.
- [VantageMonitorApp.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:2234): UTC-Chart/validierte Closing-DD-Anzeige und gesperrter Alt-DD-Cache.
- [TradeStore.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:113), [TradeListStore.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeListStore.java:77), [download_trades.py](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/download_trades.py:42): gemeinsamer Zeitbasisbeleg, kein Legacy-Merge.
- [RestApiServer.java](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/rest/RestApiServer.java:384): alter Trade-/DD-Bestand nicht als belegt ausgegeben.

## Antigravity-/A–G-Aussagen mit Quellenbezug

- Repositoriums-/Testzahlen sind damalige Messungen; aktuelle Zahlen stehen unten. Allgemeine Behauptung fünfmal Java25/JavaFX ist für MqlDownloader falsch: Swing, Maven-Source/Target1.8, hier mit vorhandenem JDK25 kompiliert. Browserdownloads sind kein reiner HTTP-API-Client.
- MQL-Datenpfad ist konfigurierbar; DefaultC:\\Forex\\MqlAnalyzer, nicht pauschal Repository-data/download. Exakte CSV-Originalwährung wurde in der Ausgangsarchitektur unterschlagen; oben korrigiert, Scanner-Gegenstück bei Root.
- Vantage20k ist das Standardlimit des Einzel-/Pythonabrufs; Batch/Update nutzt2000. Persistentes positives Archiv kann nach mehreren Fenstern mehr Positionen enthalten. Ein pauschales absolutes20k-Limit des Gesamtarchivs ist falsch.
- SHA bestätigt Dateiintegrität, weder Netzwerkfrische noch ursprüngliche Zeitbasis oder Vollständigkeit. Neue UTC-Cachekennung berücksichtigt genau diese Unterscheidung.
- Alte Live-Freeze-Werte sind kein heutiger Laufzeitnachweis. Keine Neustarts ausgeführt; Aktivierung neuen Codes erfolgt erst beim späteren bewussten Produktivstart.

## Repros, finale Tests und Betriebsauswirkung

Vorher-Logs: `mql_before.log` (6 neue Fälle, 3 Assertionfehler/3 Fehler), `vantage_before.log` (2/2 rot), `vantage_legacy_before.log` (alter UTC-Beleg fehlt, rot), `vantage_python_before.log` (alte Hostzeit rot), `vantage_python_schema_before.log` (3 rot/5 grün). Zusätzliche GUI-Nachrechnung ist in `DrawdownBasisTest.guiUsesSameValidatedEquityBasisRatherThanThePnlPeak` versioniert. Temporäre Zwischenlauf-Fehler (UTC-Datumsfixture und vergessener Anfangskapitalpunkt im neuen Test) sind im gezielten Nachherlog sichtbar und im finalen Vollpackage korrigiert.

Final ausschließlich Snapshot:

- MqlDownloader: `mvn -o -B package`, **124 Tests, 0 Fehler/0 Skips**, Thin-JAR und ausführbares Abhängigkeits-JAR gebaut; `mql_full_package.log`.
- Vantage: `mvn -o -B -Duser.timezone=Europe/Berlin package`, **76 Tests, 0 Fehler/0 Skips**, JAR gebaut; `vantage_full_package.log`.
- Vantage-Zonen-Gegenprobe: `ReviewFollowupTest,TradeIntegrityTest` unter America/New_York, **6 grün** (Teilmenge, nicht zur Gesamtsumme addiert); `vantage_timezone_after.log`.
- Vantage-Python: isoliert `python -m pytest -q tests`, **21 grün**; `vantage_python_after.log`.
- Beide Repository-Diffs bestehen `git diff --check`. Manifest prüft jeden geänderten/neuen Dateiinhalt gegen seinen getesteten Snapshot. Product JARs nur im Audit-Snapshot gebaut, keine Installation.

Bewusste Kompatibilitätswirkung: Nicht belegte alte Vantage-Zeitbasis wird gesperrt. Der Altbestand bleibt vollständig erhalten, Update/Merge scheitert mit Fehler statt Datenverlust. Eine sichere vollständige Migration ist ohne Originalzone/Originalepoch nicht ableitbar. Späterer vollständiger Neuaufbau muss getrennte Sicherung des Altbestands einschließen; er wurde hier nicht ausgelöst. MQL-Altkennzahlen ohne Währung sind explizit unknown und berechtigen keinen USD-Import. Diese strengeren Belegprüfungen können bisher irrtümlich verfügbare Daten sperren; das ist die beabsichtigte Korrektur.

Freeze: Alle Quell-/Test-/Dokuänderungen abgeschlossen. Veröffentlichung durch Root.

Nachtrag nach konkreter Root-Gegenhypothese: Legacy-Daily-Epoch0 unter fremder
Hostzone war zusätzlich reproduzierbar und wurde gezielt korrigiert.
Der erste Snapshot/Package-Beleg bleibt erhalten; aktueller Vantage-Stand
steht in `clients_vantage_epoch_followup.md` und `clients_manifest_final2.json`
(neuer Snapshot `vantage_final2`,78 Java- und21 Python-Tests grün).
MqlDownloader und dessen124-Test-Beleg bleiben unverändert.
