# Antigravity-/GLM-Handover: Pelican, Robo und Zulu

Prüfdatum: 16.10.2026. Unabhängige Nachprüfung des vollständigen
`REVIEW_2026-10-16_Gesamtsystem_Befundkatalog.md`, des ergänzten
`REVIEW_2026-10-16_Gesamtsystem_Bericht.md` und des Antigravity-Berichts
`C:/Users/tnickel/.gemini/antigravity-ide/brain/22de581d-4dcb-48ef-aefd-6d842563d491/review_bericht_signalkiscanner_hub.md`.

Der Ausgangsstand dieser Prüfung liegt deutlich nach den alten Reviewständen.
Historische Livebeobachtungen und damalige Testzahlen werden nicht als heutiger
Laufzeitnachweis behandelt. Alle Codepfade wurden lokal gelesen; Tests verwenden
synthetische Daten, temporäre Stores und gegebenenfalls Loopback-HTTP.
Keine Plattform-/Login-/LLM-Aufrufe, keine Produktdaten- oder Settingsänderungen,
kein Stage/Commit/Push durch diesen Agenten. Im untersuchten Quellenbereich
existiert keine zusätzliche lokale AGENTS.md; die übermittelten Nutzerregeln
gelten. Andere Arbeitsbereiche werden von Root und den weiteren Agenten geprüft.

## Ergebnis

Bestätigte aktuelle Fehler wurden minimal korrigiert:

1. **ROB-6:** Stufe 0 lud teure Tageslisten/Deals auch für Anbieter ohne Abonnenten.
   Der aktive Downloadscope filtert jetzt vor beiden Phasen auf mindestens einen
   Abonnenten. Der gespeicherte Katalog, manuelle GUI- und Archivzugriffe bleiben
   erhalten. `tradelistenOhneAbonnenten` legt die ausgelassenen Einträge offen.
   Besteht der Scope nur aus solchen Einträgen, wird keine ungenutzte Session
   verlangt.
2. **Robo-REST, zusätzlicher bestätigter Randfall:** `offset + limit` konnte bei
   `offset=2147483647` überlaufen und HTTP 500 erzeugen. Addition erfolgt jetzt
   als Long; das Ergebnis ist eine leere Seite mit HTTP 200.
3. **ZUL-5, bisher zu pauschal als korrekt bewertet:** Bei überlappenden
   Katalogseiten lieferte die feste Seitenzahl weniger eindeutige Provider als
   angefordert. Jetzt wird bis zum Ziel oder einer leeren Seite nachgefüllt;
   Seiten ohne neue IDs und Einträge ohne positive gültige Provider-ID führen
   zu einem Fehler, statt einen unbemerkten Teilkatalog zu bestätigen.
4. **Zulu-Payload, zusätzlicher bestätigter Datenfehler:** Unbekanntes Alter wurde
   über den primitiven Legacy-Getter im LLM-Payload als gemessene 0 Wochen
   ausgegeben. `wochenHistorie` bleibt jetzt nullable; echte 0 bleibt 0.

Zusätzlich wird **ROB-5** im Katalogpayload mit
`sourceFilters.profit_percent_max=300` sichtbar. Dieselbe Konstante steuert
Quellanfrage und Metadatum; die bestehende Auswahlgrenze wurde nicht verändert.
Die unterschiedlichen lokalen Winrate-Definitionen aus ROB-11/ZUL-8 sind in den
READMEs ausdrücklich beschrieben. Es wurde weder eine neue Ranking-/TTL-Regel
noch eine unbelegte Währungs- oder Lotsskalierung eingeführt.

## Nachprüfung jeder Robo-ID

Alle folgenden Pfade sind relativ zu
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/roboforex/`.

| ID | Aktueller Befund | Beleg / Gegenbeleg |
| --- | --- | --- |
| ROB-1 | Bereits behoben; der SHA erzeugt keine dauerhafte Stufe-0-Sperre mehr. | `src/main/java/de/robomonitor/update/UpdateJobRunner.java:196` lädt Deals in jedem aktiven Lauf erneut; vorhandener Bestand bestimmt nur Neu-/Aktualisiert-Zähler. `UpdateJobStufe0Test.kaskadeAktualisiertAuchBekannteTageslistenUndDeals` prüft bekannte IDs. |
| ROB-2 | Bereits behoben; vorhandene Tageslisten werden aktualisiert. | `UpdateJobRunner.java:162` enthält keine Existenz-Skipprüfung mehr. Derselbe Kaskadentest erfasst alle aktiven Tageslisten. |
| ROB-3 | Bereits behoben; Balanceoperationen fließen nicht in die Deal-Kurve ein. | `model/EquityKurve.java:60` entfernt `istBalanceOperation()`. `report/SignalPayloadBuilder.java:49` verwendet diese Kurve im Ratingfenster; `closingDd:77` verlangt endliche positive Kapitalbasis. `ReviewDataIntegrityTest` enthält eine unveränderte DD-Gegenprobe mit zusätzlicher Einzahlung. |
| ROB-4 | Der konkrete 20.000-Deckel existiert nicht mehr; kein neues Truncation-Feld für einen entfernten Deckel erfunden. | `api/RoboForexClient.downloadDeals` paginiert bis `page.more=false` und prüft Fortschritt. `ReviewDataIntegrityTest.paginationDoesNotSilentlyTruncateAtOld20000Cap` lädt synthetisch 20.001 Deals. `store/DealStore.java:291` markiert alte große Bestände ohne Paginationbeleg qualitativ unvollständig; Metrics/Export geben diese Grenze weiter. |
| ROB-5 | Quellfilter ist real, schon dokumentiert; maschinenlesbarer Ausweis hier ergänzt. | `api/RoboForexClient.java:81,98` bindet `profit_percent_max` an die Konstante 300. `rest/RestApiServer.java:336` liefert `sourceFilters`; `RestApiServerTest.largeOffsetIsAnEmptyPageAndSourceFilterIsTransparent` prüft den Wert. Keine belastbare Nutzer-/Risikoherleitung dieser ursprünglichen Filterwahl gefunden; Wert nicht eigenmächtig verändert. |
| ROB-6 | Bestätigt und hier behoben. | `update/UpdateJobRunner.java:113–118` erstellt den aktiven Scope. Neue Tests `zeroSubscriberSignalsDoNotEnterDownloadPhasesEvenFromCachedCatalogue` und `emptyEligibleScopeDoesNotRequireAnUnusedSession` prüfen frischen/gecachten Katalog, erhaltenen Gesamtkatalog und fehlende ungenutzte Session. |
| ROB-7 | Bestehendes korrektes Verhalten bestätigt. | `UpdateJobRunner.parseVermerk` liest ISO-Instant sowie Altbestand ohne Zone; Writer verwendet UTC-Z. Bestehende Tests prüfen beide Formate und Katalogskip. Keine neue TTL eingeführt. |
| ROB-8 | Parser-/Aggregationspfade vorhanden; pauschale Websiteparität wird nicht daraus abgeleitet. | `api/RoboForexClient.parseMt4Deals/parseMt5Deals`, `deals/TradeAggregator` und ihre Tests behandeln Pflichtdaten, Mengen, Kosten, Teilabschlüsse und offene Reste. MT4-Closezeit/MT5-Dealzeit werden getrennt verwendet; `ClosingDdDealsTest` hat unabhängige Zeit-/DD-Orakel. Quellenfelder bleiben ohne zusätzliche Livebelege unverändert skaliert. |
| ROB-9 | Vorhandene Bereinigung und Nullbehandlung bestätigt, keine allgemeine Livegarantie. | `RoboForexClient.cleanBalanceEquity`, `carryForward` und `dateValueMap` behandeln fehlende Tageswerte und dokumentierte Ausreißer; bestehende Core-/Integritätstests laufen grün. |
| ROB-10 | Dokumentierte Grenze, kein bestätigter Codefehler. | `RestApiServer.item` benutzt bei fehlender `sourceId` die Ratingübersicht; vorhandene ID führt zum Detailprofil. Eine heutige Aussage, die Live-API liefere generell keine source_id, wurde hier nicht geprüft. Keine erfundene ID oder ungeforderter Zusatzabruf. |
| ROB-11 | Unterschiedliche deskriptive Quote, kein belegter falscher Nenner. | `deals/DealStatistik.java:79,93` verwendet Gewinner/(Gewinner+Verlierer) nach Netto-PnL. Zulus lokale Quote basiert auf Pips und allen geladenen Trades. README benennt beide Unterschiede; keine fachlich unbelegte Vereinheitlichung. |

## Nachprüfung jeder Zulu-ID

Pfade relativ zu
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor/`.

| ID | Aktueller Befund | Beleg / Gegenbeleg |
| --- | --- | --- |
| ZUL-1 | Bereits behoben; Stufe 0 aktualisiert auch bekannte Historien. | `src/main/java/de/zulumonitor/update/UpdateJobRunner.java:149–163`: Ledger wird für Zähler gelesen, danach folgt der Download ohne SHA-Skip. Bestehende Updatejob-Tests prüfen erneuten Abruf und Zusammenführung. Eine historische alte Laufzeitinstanz beweist keinen aktuellen Sourcefehler. |
| ZUL-2 | Bereits behoben; gekappte/inkonsistente Historie ergibt keinen DD. | `report/TradePayloadBuilder.java:39` verlangt positive endliche ROI, eindeutige gültige Trades und `history.size()==t.getTrades()`. GUI `ZuluMonitorApp.berechneTradeDd` entfernt bei null den Cacheeintrag. `report/DrawdownBasisTest.invalidCapitalAndMismatchedLifetimeScopeRemainUnknown` prüft fehlenden Umfang, doppelte IDs und ein unabhängiges DD-Orakel. |
| ZUL-3 | Bereits behoben; PnL 0 oder Verlustnetto beweist bei positiver ROI keine positive Kapitalbasis. | Derselbe Helper prüft `basis <= 0` und nichtendliche Werte. Eine flache Null-PnL-Kurve führt damit null statt DD 0. Bestehende Regression prüft invalides Kapital; keine positive Basis geschätzt. |
| ZUL-4 | Historische FX-Kette im aktuellen Code bestätigt. | `rest/FxRates.java:23–92` enthält historische EZB-Kurse, USC/100 und begrenzten Rücklauf ohne Zukunftskurs. `RestApiServer.java:468` verwendet den Trade-Schlusstag; vorhandene REST-/FX-Tests nutzen injizierte Kurse, keine Live-EZB. Fehlt ein belegter Kurs, scheitert der Export ehrlich. |
| ZUL-5 | Abonnenten-/REST-Regel bestätigt; Paginationbehauptung hatte eine reale Lücke, hier korrigiert. | `ZuluTradeClient.parseTrader` liest followers und bevorzugt liveFollowersNew für den separaten Livezähler; REST filtert standardmäßig mindestens einen follower. `downloadTopTraders:201` füllt jetzt nach ID-Deduplizierung nach; `providerId:283` und Suchparser lehnen ungültige Identitäten ab. `api/CataloguePaginationTest` prüft Überschneidung, Wiederholung und fehlende/0-ID. Unbekannter Zuwachs bleibt weiterhin null. |
| ZUL-6 | Bestehende Trade-Schema-/Fortschritts- und Hostfallbackprüfungen bestätigt. | `ZuluTradeClient.downloadTradeHistory`, `gueltigerTradeDatensatz`, `getTradingJson`; `api/ClosedTradeContractTest` prüft fehlende/nonfinite Pflichtfelder, überlappende Trade-IDs und wiederholte Seiten. Neue Katalogprüfung ergänzt diese vorhandenen Tradeprüfungen. Kein heutiger Plattformabruf belegt. |
| ZUL-7 | Vorhandene Betriebslogik bestätigt, kein Auth-Livetest. | Client unterstützt optionalen JWT/Refresh. `ZuluMonitorApp.java:410–430` verwirft bei fehlgeschlagenem Open-Download den alten Cache und markiert stale; Job meldet den Hinweis separat. Unterbrechung wird weitergereicht. Keine Login-/OAuth-Aktion durchgeführt. |
| ZUL-8 | Beschreibende Quote mit anderem Nenner und anderer Erfolgsbasis als Robo. | `TradePayloadBuilder` zählt Pips > 0 / alle geladenen Trades inklusive Pips=0; README erklärt dies nun ausdrücklich. Das ist keine belegte falsche Plattformquote. Keine Änderung der Berechnung. |
| ZUL-9 | Vollhistorienumfang ist eine bewusste Kosten-/Vollständigkeitsgrenze. | Die Stufe-0-App verwendet Integer.MAX_VALUE, der Parser beendet anhand der API-Pagination. Die Aussage „genau einmal teuer“ ist nach ZUL-1-Fix veraltet: aktive Updates laden erneut. Keine willkürliche Kürzung oder TTL eingeführt. |

Zusätzlicher Datenfehler: `TradePayloadBuilder` verwendete für
`kennzahlen.wochenHistorie` den Legacy-Getter `getWeeks()`. Der neue Test
`DrawdownBasisTest.unknownAgeRemainsUnknownInLlmPayloadRatherThanLookingLikeMeasuredZero`
prüft null, echte 0 und 26; null bleibt nun null wie in REST/UI.

## Nachprüfung jeder Pelican-ID

Pfade relativ zu
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/PelicanTrading/`.
**Keine Produktänderung in diesem Repository nötig.**

| ID | Aktueller Befund | Beleg / Gegenbeleg |
| --- | --- | --- |
| F-1 | Bereits behoben. | `src/main/java/de/pelicanmonitor/store/DataStore.java:192` synchronisiert pro normalisiertem Ziel und verwendet eigene Tempdateien. `SignalStore.mergeClosed:77` sperrt pro Provider; GUI besitzt einen AtomicBoolean-Batchschutz. Bestehende AtomicWrite-/Merge-/UI-Tests bestanden. |
| F-2 | Bereits behoben. | `SignalStore.loadClosed:144` behandelt nur gleichzeitig fehlende CSV und Meta als legitimen leeren Neustart. I/O-, Hash-, Kopf- oder Countfehler brechen Merge ab; `SignalStoreIntegrityTest` und `SignalStoreMergeTest` schützen Altbestand. |
| F-3 | Plattformsemantik weiterhin nicht belastbar bewiesen; keine Nenneränderung. | `model/Provider.java:238` berechnet ausdrücklich 100*Wins/Total. README dokumentiert diese API-Statistikquote und die andere Quote geladener Positionen. Lokale Swaggerdefinitionen geben keine Deals-/Positionssemantik des Nenners her. Ungefähr Faktor 2 zu einem Positionsausschnitt beweist weder eine falsche Quote noch Wins/(Wins+Losses) als korrekte Plattformdefinition. Ein zeitlich/inhaltlich passender Website-/API-Abgleich wäre erforderlich; hier untersagt. |
| F-4 | Bereits behoben. | `report/ReportService.periodenRendite:94` verwendet (1+r_neu)/(1+r_alt)-1 mit gültiger Kapitalbasis; strukturierter Payload skaliert Anteile genau einmal. `ReportFinancialUnitsTest` prüft 0 -> 0,1 -> 0,21 als zweimal 10 % und 1.000 -> 1.210, Lücken, Fenster und Totalverlust. |
| F-5 | Bewusste Trennung bestätigt, kein neuer Ausschluss. | Regulärer Update-/GUI-Auswahlscope verlangt standardmäßig Abonnenten. Einzel-/Archivzugriffe bleiben möglich; explizite Opt-outs sind dokumentiert. Keine zusätzliche Sperre nachträglich eingeführt. |
| F-6 | Kein belegter Fehler; Enabled=false allein rechtfertigt keinen ungeforderten Ausschluss. | Providerstatus bleibt Datenfeld; mindestens ein vorhandener Abonnent kann trotz Status relevant sein. Keine neue Auswahlpolitik. |
| F-7 | Bereits behoben, Spot-/historische FX nicht verwechselt. | `rest/FxRates.java:40,115,160` hat 24-h-TTL, ursprüngliche Abrufzeit je Eintrag und sichtbaren Offlinefallback. `FxRatesSnapshotTest` prüft Cachegrenzen; historische Trade-FX liegen in `HistoricalFxRates` und werden separat getestet. |
| F-8 | Bereits behoben. | `api/PelicanClient.anteilZuProzent:478` skaliert API-Anteil eindeutig, auch -1 -> -100 %. Null-Geld wird nicht als 0 erfunden; `ProviderUncertaintyTest`/`FinancialUnitsTest` prüfen die Unterscheidung. Effektiver nullable DD-Helper bewahrt gemessene 0 und verwirft NaN. |
| F-9 | Vertragsgrenzen und Teilfehler aktuell explizit, kein ungeforderter target-Deckel. | REST validiert Boolean und vorhandene numerische Updateoptionen. `target` wird laut README bewusst ignoriert; Discover lädt die Anbieter, der Tradelistenscope besitzt eigene dokumentierte Optionen. Bereits laufender eigener Job liefert kompatibel 200+bereitsLaufend; echter Busy-Konflikt kann 409 liefern. Updatejob meldet Fehler/Abbruch strukturiert; vorhandene REST-/Updatejob-Tests bestanden. |
| F-10 | Bereits behoben bzw. inzwischen strenger abgesichert. | `PelicanClient.parseDiscoverItems:160` verlangt Array und positive Strategy-ID in jedem Datensatz. `parseClosedResponse:338` verwirft fehlende Trade-ID/Pflichtdaten. Storemerge erhält alte Zeilen ohne stabile ID getrennt, der REST-Export validiert sie gesondert. Schema-/Merge-/ClosedTrade-Tests bestanden. |

Die Bemerkung über einen alten laufenden Prozess im ursprünglichen Review ist
historische Betriebsinformation. Diese Prüfung startet keine Apps und bestätigt
deshalb weder den heutigen laufenden Buildstand noch einen Plattformdatenstand.

## Kritischer Abgleich der Antigravity-Quellenbeschreibung

| Behauptung im Antigravity-Bericht | Aktueller lokaler Gegenbeleg / Einordnung |
| --- | --- |
| Pelican verwendet `https://api.pelicantrading.com`. | `PelicanTrading/.../api/PelicanClient.java:43` hat als aktuellen Default `https://pelican.copy-trade.io`; konfigurierbarer Basis-URL bleibt möglich. Keine Aussage über Erreichbarkeit der genannten fremden Domain gemacht. |
| Pelican authentifiziert im Quellclient über einen API-Token. | `PelicanClient.java:99` sendet einen Session-Cookie. Dieser Plattformzugang ist vom optionalen Token der lokalen REST-Schnittstelle zu unterscheiden. Es wurde kein Cookieinhalt gelesen oder ausgegeben. |
| Pelican persistiert H2 / `data/pelican.mv.db`; Architekturdiagramm nennt auch Zulu H2. | `PelicanTrading/.../store/CopierDb.java:52`, LiveDataStore und StrategieDb verwenden SQLite; Tradelisten sind CSV+Meta. `zulumonitor/.../store/SubscriberDb.java:48` verwendet SQLite `abonnenten.db`, Trades ebenfalls CSV+Meta. Eine H2-Speicherung wird durch diesen Code nicht gestützt. |
| Pelican-EZB-Code heißt `EcbRates.java`. | Aktuelle Implementierungen heißen `rest/HistoricalFxRates.java` für Trade-Schlusstage und `rest/FxRates.java` für Snapshotwerte. Die fachliche historische FX-Aussage ist im Kern richtig, die Codezuordnung falsch. |
| Zulu `trades.csv` ist ausschließlich USD; Nicht-USD liefert pauschal 404. | `RestApiServer.java:468` normalisiert je Trade mit historischen FX. Vorhandene EUR/HKD/USC-REST-Tests liefern bei belegtem Kurs korrekte USD-Exporte. 404 gilt bei fehlenden Pflichtdaten/Kursen, nicht pauschal für jede Fremdwährung. |
| Zulu verwendet Version `zulu`. | Bestätigt: `RestApiServer.VERSION` ist exakt `zulu`. Eine frühere Zwischenmeldung dieses Agenten mit `zulu3` war falsch und wurde korrigiert; kein Produktfehler. |
| Die angegebenen alten Testzahlen und Live-Prozessstände repräsentieren den heutigen Code. | Nicht zulässig. Der Bericht nennt alte Commitstände; die untenstehenden Läufe gelten ausschließlich für die finalen neuen Snapshots. Laufende Apps wurden nicht inspiziert oder neu gestartet. |
| Katalogauswahl besteht allgemein aus den ersten zwei Webseiten. | Für diese drei Quellen pauschal falsch: Pelican Discover-Array, Robo getRating-Pagination mit konfiguriertem target/Filter, Zulu paginierte Top-N-Suche. Selektion und begrenzte Grundgesamtheit sind reale methodische Grenzen; daraus folgt ohne Datennachweis keine universelle Zwei-Seiten-Regel. |

Antigravity E-1 bis E-6 betreffen Scanner/Agenten, nicht diese exklusiv geprüften
Quellen. Ihre aktuelle Nachprüfung übernimmt Root/der zuständige Agent.
MqlRealmonitor und PelicanWinnerLooser bleiben außerhalb dieses Auftrags;
keine Integration wurde vorgenommen.

## Reproduzierbare Regressionen gegen unveränderten Ausgangscode

Baselines wurden per `git archive HEAD` isoliert; anschließend wurden nur die
neuen Testdateien aus der Arbeitskopie überlagert, kein korrigierter Produktcode.
Alle Dateien liegen unter
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/antigravity_handover_pruefung_2026-10-16/`.

| Probe | Ergebnis auf altem Produktcode |
| --- | --- |
| `roboforex_baseline_probe`, Log `roboforex_baseline_probe.maven.log` | 3 Tests, 3 erwartete Failures: MaxInt-Offset ergibt 500 statt 200; aktive Downloads enthalten ID 2 mit 0 Abonnenten; ausschließlich 0-Abonnenten verlangt unnötig LOGIN_REQUIRED statt DONE. |
| `zulumonitor_baseline_probe`, Log `zulumonitor_baseline_probe.maven.log` | 1 Test, 1 erwartete Failure: 40 angeforderte Provider ergeben nur 39 eindeutige nach überlappenden Seiten. |
| derselbe Baselineordner, Log `zulumonitor_payload_baseline_probe.maven.log` | 1 Test, 1 erwartete Failure: unbekannte Wochen werden als 0 statt JSON null geliefert. |

Gezielte Befehle in den jeweiligen Probeordnern:

```text
mvn -o -B -Dtest=UpdateJobStufe0Test#zeroSubscriberSignalsDoNotEnterDownloadPhasesEvenFromCachedCatalogue+emptyEligibleScopeDoesNotRequireAnUnusedSession,RestApiServerTest#largeOffsetIsAnEmptyPageAndSourceFilterIsTransparent test
mvn -o -B -Dtest=CataloguePaginationTest test
mvn -o -B -Dtest=DrawdownBasisTest#unknownAgeRemainsUnknownInLlmPayloadRatherThanLookingLikeMeasuredZero test
```

Die Zulu-Katalogregression prüft mit korrigiertem Code auch wiederholte Seiten
ohne neue IDs, Einträge ohne Trader und Provider-ID 0. Diese Varianten brechen
mit IOException ab, während drei überlappende Seiten das Ziel 40 erreichen.

## Finale Snapshots, vollständige Tests und Bytebelege

Snapshotverfahren:
`waste/gesamt_review_fixes_2026-10-16/audit/snapshot.py` archiviert HEAD und
überlagert die aktuellen geänderten sowie neuen nicht ignorierten Dateien.
Private Laufzeitcaches werden nicht kopiert. Die folgenden Snapshots enthalten
die tatsächlich aktuellen Korrekturen; es sind keine bloßen alten HEAD-Archive.

| Repo | HEAD vor Overlay | Finaler Snapshot | Overlay | Tests / Package |
| --- | --- | --- | ---: | --- |
| roboforex | `96ca0a7b8b34bc11e6bf587c548b308ce5c0092c` | `roboforex_final` | 6 | 183 bestanden; package erfolgreich |
| zulumonitor | `3eb92b582f91107f7f7227f21d5518a2ce0b5730` | `zulumonitor_final2` | 5 | 120 bestanden; package erfolgreich |
| PelicanTrading | `ff883d625e36fe192d4a8ef220a891b12f84e790` | `PelicanTrading_final` | 0 | 180 bestanden; package erfolgreich |

Insgesamt **483 Java-Tests**, 0 Failures, 0 Errors, 0 Skips. Zulu `*_final`
ohne Suffix 2 ist ein Zwischenstand; ausschließlich `zulumonitor_final2` enthält
auch die abschließende nullable-Payloadkorrektur.

Je finalem Namen liegen `<Name>.manifest.json` und `<Name>.maven.log` im
übergeordneten Auditordner. SHA-256 je Overlaydatei und Ausgangs-HEAD stehen in
den Manifesten. Abschließender Hashabgleich Arbeitskopie und Snapshot gegen
alle Manifestwerte: **jeweils 0 Abweichungen**. `git diff --check` ohne Fehler.

SHA-256 der finalen Manifeste:

```text
roboforex_final      0a2bd44e0c68d593e1301b0272df4ebbd4278e7d5536ac001de6783df1ce6c11
zulumonitor_final2   6007d0abe1f55ee5352d0ef8332bdda78ccf1e9fb1b617fd21fa64b3931428f0
PelicanTrading_final b8316a5b7f1c156a189abdaca8a926b0e5c911da49590dbea4ce9d7c1c159cc4
```

In jedem finalen Snapshot: `mvn -o -B package`, mit
JAVA_HOME `C:/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot` und Maven
`D:/DevelopmentTools/apache-maven-3.9.6/bin/mvn.cmd`. Snapshothelper-Python:
`C:/Users/tnickel/AppData/Local/Programs/Python/Python312/python.exe`.
Keine Maven-/Pythonpakete wurden nachinstalliert.

## Geänderte Produktdateien und Übergabe

Robo: README, `api/RoboForexClient.java`, `rest/RestApiServer.java`,
`update/UpdateJobRunner.java`, `RestApiServerTest.java`, `UpdateJobStufe0Test.java`.

Zulu: README, `api/ZuluTradeClient.java`, `report/TradePayloadBuilder.java`,
neue `api/CataloguePaginationTest.java`, `report/DrawdownBasisTest.java`.
Die neue Katalogtestdatei ist untracked und muss bei der Übergabe mitgenommen
werden; sie ist im finalen Snapshot und dessen Hashmanifest enthalten.

Pelican: keine Änderung. Alle drei Quellen sind nach den finalen Läufen
eingefroren; Stage/Commit/Push und eventuelle Neustarts übernimmt Root/Nutzer.
Die lokalen Tests belegen Parser-, Scope-, Store- und REST-Verhalten, keine
heutige Websiteparität, Plattformvollständigkeit oder aktuelle laufende Builds.
