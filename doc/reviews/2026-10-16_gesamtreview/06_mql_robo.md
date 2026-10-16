> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\quellen_b`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# Unabhaengiges Quellenreview: MqlDownloader und RoboForex

Datum: 16.10.2026. Reviewer-Scope: genau diese zwei Quellen; Scanner nur bis zum lesenden CSV-Parser-Durchstich. Keine produktiven Dateien, Einstellungen oder Nutzerdaten geaendert. Keine Plattform-, Login-, LLM-, MT5-, Selenium- oder manuellen Headless-Live-Laeufe. Kein Commit/Push. Der Hauptreview prueft Hub/Agenten/DB/LLM und weitere Quellen gesondert.

## 1. Stand, Isolation und Nachweise

| Repository | Branch | Commit | Arbeitsbaum bei Archivierung | Geprueft |
|---|---|---|---|---|
| MqlDownloader | master | `92d8f9cea10bdc8f99c96782d75631b21e1714e6` | sauber | `quellen_b/MqlDownloader`, aus `git archive HEAD` |
| roboforex | master | `42b268641ad370ccae7841b6a478f9745cb57bd3` | sauber | `quellen_b/roboforex`, aus `git archive HEAD` |

Archiv-SHAs und Verzeichnisse: `manifest.json`. JDK: Eclipse Adoptium 25.0.4.101-hotspot. Maven: 3.9.6. Python fuer den Parser-Durchstich: `C:\Users\tnickel\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe`. Getesteter Scanner-Parser: aktueller Workspace `80d4692548c9`, lediglich `parser.load_export`; keine Scanner-Tests oder Pipeline gestartet.

| Befehl im jeweiligen sauberen Snapshot | Ergebnis | Beleg |
|---|---|---|
| `mvn -o test` MqlDownloader | 105 Tests, 0 Fehler, 0 Skips, BUILD SUCCESS | `maven_MqlDownloader.log` und Surefire-XMLs |
| `mvn -o test` roboforex | 147 Tests, 0 Fehler, 0 Skips, BUILD SUCCESS | `maven_roboforex.log` und Surefire-XMLs |
| `mvn -o package -DskipTests` MqlDownloader | JAR + Assembly-JAR gebaut, BUILD SUCCESS | `package_MqlDownloader.log` |
| `mvn -o package -DskipTests` roboforex | JAR gebaut, BUILD SUCCESS | `package_roboforex.log` |
| `javac`/`java` synthetische Auditprobes | unten dokumentierte Gegenbeispiele reproduziert | `ReviewMqlProbe.java`, `ReviewRoboProbe.java`, `ReviewRoboWriterProbe.java`, zugehoerige Logs |
| `python check_scanner_csv.py` | beide originalen MQL-Formate und die problematischen Robo-Exporte werden angenommen | `scanner_csv_probe.json` |

Classpath fuer die Java-Probes wird aus `target/surefire-reports/TEST-*.xml` entnommen; Details in `run_probes.ps1`. Erzeugte Probe-CSVs/DB-freie Cachedateien sind ausschliesslich synthetisch und liegen in `mql_probe_data`, `robo_probe_data`, `robo_parallel_data`. Die Probes enthalten keine Produktkorrekturen. Die Standardtests benoetigen hier keine ignorierten Research-/Kontodaten. Die manuellen `Headless*`-Programme in RoboForex sind keine JUnit-Livepruefung und wurden nicht gestartet.

**Aussagegrenze:** Gruene Tests belegen die ausgefuehrten Faelle. Aktuelle Plattformabdeckung, unverkuerzte API-Historie, Kopierbarkeit und Netto-/Waehrungssemantik sind damit nicht allgemein bestaetigt. Wirksame private Laufzeitkonfiguration und eventuell laufende alte Builds wurden nicht eingelesen oder geaendert.

## 2. Anforderungen und beobachtete Datenketten

| Anforderung | Implementierung | Test/Nachweis | Einordnung |
|---|---|---|---|
| MT4/MT5 sicher unterscheiden | MQL: Versionsordner und REST-Aliase; Robo: Plattform am Signal, MT5-Aggregator | vorhandene REST-/ProviderFiles-Tests, normaler CSV-Durchstich | normale Faelle funktionieren; Robo R1/R2 beachten |
| Keine erfundenen Pflichtdaten | MQL rohe CSV; Robo füllt OUT-ohne-IN mit Schlusszeit/-preis, fehlenden Profit mit 0 | synthetische Repros R2/R8 | verletzt im Robo-Export |
| Trades nach Update aktuell | MQL 72h Gesamtkaskaden-Skip plus 5-Tage-Dateicache default; Robo dauerhafter SHA-Ledger-Skip | Quellcode und 2020-Meta-Probe R4 | MQL dokumentierte Altersgrenze; Robo vorhandene Listen bleiben unbegrenzt alt |
| Fehler verhindern falschen Erfolg | MQL Workerfehler nur GUI/Log; Robo Fehler nur Hinweise | R5, Robo alle 11 Downloads fehlgeschlagen | DONE ist kein vollstaendiger Abrufnachweis |
| JSON-Ergebnis fuer Scanner | MQL handgeschriebener Statusserializer; Robo Jackson | R6 | MQL liefert `ergebnis` als String |
| Fehlende Kennzahlen nicht als 0/1 erfinden | MQL Monatsdaten leer -> 0; DD -> 1 | R7 | Schutz vor Loeschung bei NaN deckt diese Faelle nicht |
| Closing-DD ohne Kontofluesse | Robo `punkteAusDeals` addiert alle Deals, inklusive BALANCE | R3 | Einzahlungen werden zu Trading-PnL |
| Vollstaendiger Rohkatalog getrennt von aktiver Auswahl | MQL konfigurierbare Limits, DB kumuliert; Robo Top-target, Ratingfilter, REST >=1 | Codeinventar unten | keine Vollplattform-Zusage; Uebergaenge und Scope nicht verwechseln |
| Atomare Persistenz/Parallelitaet | MQL rohe Datei-Moves; Robo feste `.tmp`, nur DealStore-Instanzsperren | R10 | atomarer Move ist kein Transaktions-/Mehrinstanzschutz |
| Realmonitor/PWL nicht als produktiv integriert ausgeben | nicht Teil dieser zwei Quellenketten | Hauptreviewgrenze | keine neue Integration gefordert |

**MQL-Kette:** Selenium-Listen MT4/MT5 -> Subscriber-H2 und `<Name>_<id>_root.html`/CSV in Versionsordnern -> HtmlConverter mit MPDD-Vorfilter -> `_root.txt` -> REST `ProviderFiles`/`MetricsParser` bzw. originale CSV -> Scanner-Parser. Synthetisch Buy 0,1 Lots, Brutto 100, Kommission -2, Swap -1: beide CSV-Formate ergeben korrekt Netto 97, 24h Haltedauer. Der normale MT4-Orderbuchpfad behaelt SL/TP. Die REST-JSON-Variante verliert dagegen doppelte Spaltennamen (R9).

**Robo-Kette:** oeffentliches Rating (source_id+login, seitenweise) und Tagesdaten; eingeloggte Members-API MT4-Orders/MT5-Deals -> `DataStore`, `DealStore` + Meta/Ledger -> `TradeAggregator` -> REST-Positions-CSV mit Lots x10 -> Scanner-Parser. API-Volumen wird zuvor MT4 /1e6, MT5 /100 normalisiert. Regulärer CSV-Profit = `netPnl - commission - swaps`; Scanner addiert die Kosten wieder: keine systematische doppelte Kostenanrechnung in diesem aktuellen Normalpfad. R1/R2/R8 betreffen die falsch normalisierten Eingangsdaten trotz syntaktisch gueltiger CSV.

## 3. Endpointmatrix

Alle Pfade relativ `/api/v1`. Token optional: X-API-Token, Bearer oder Querytoken. Beide Server binden standardmaessig an alle lokalen Interfaces, nicht ausschliesslich Loopback. Keine TLS-Terminierung im JDK-Server. Leeres Token ist dokumentierter LAN-Modus. GET/OPTIONS lesend, POST nur Update. Authentifizierung gilt auch fuer Health. Einzelne Fehlerfaelle und Datentypen sind nicht generell streng validiert.

| MqlDownloader | Parameter/Version | Antwort und Grenzen | Scanner-Nutzung |
|---|---|---|---|
| GET `/health` | keine | Instanz, Uptime, Providerzahl, Tokenmarker | ja |
| GET `/providers` | version mql4/mql5/mt4/mt5, name, minSubscribers, sort/order, limit/offset, format | paginierte H2-Statistiken, keine automatische Default-Subscriber-Untergrenze im REST-Filter | Katalog |
| GET `/providers/{id}` | ID | alle Versionen als items; unbekannt 404 | Detail |
| GET `/providers/{id}/{version}` | Versionsalias | einzelnes Objekt; 404 wenn nicht bekannt | optional |
| GET `.../history` | days/from/since/to/until, limit/offset | aufsteigende Subscriberpunkte mit lokaler und UTC-Zeit | ja; Vollhistorienscope im Consumer separat pruefen |
| GET `.../trades` | q, limit/offset | header + Zeilenmaps; doppelte MQL-Spalten kollabieren (R9) | CSV ist der relevante Forensikpfad |
| GET `.../trades.csv` | ID/Version | originale Bytes, 404 ohne zugeordnete CSV; keine zusaetzliche aktive Inhalts-/Frischegarantie | ja |
| GET `.../metrics` | ID/Version | Parser der Root-TXT, Zahlen oder Strings, keine Broker-/Waehrungs-/Kapitalbasisfelder im normalen Converter | ja |
| GET `.../reports` / `.../reports/{name}` | ID/Version, Dateiname | PDF-Liste/Datei, direkte Kinddateien/Whitelist; Report-ID ueber Zahlengrenzenheuristik, keine Versionsbindung des PDF-Bestands | ja |
| GET `/trades` | version/id/name/limit/offset | Dateikatalog der Versionsordner | zusaetzlich |
| GET `/trades/file/{version}/{name}` | direkte Dateiliste | rohe CSV; Whitelist/Traversal-Abwehr | zusaetzlich |
| GET `/events` | Zeitfenster, limit, includeUnchanged, format | Subscriberereignisse global | zusaetzlich |
| GET `/summary` | keine | Aggregate, Topzuwachs | zusaetzlich |
| GET `/openapi.json` | keine | beschreibt Leseendpunkte, Update fehlt dokumentiert | Selbstbeschreibung |
| POST `/update` | target/tradelisten/katalogMaxAlterH | 202 neu, 200 bereits laufend, 409 GUI busy; toleranter Regexparser, reale Kaskade ignoriert target/tradelisten dokumentiert | Stufe 0 |
| GET `/update/status` | kein Job-ID-Parameter | letzter globaler Job; `ergebnis` falsch stringifiziert (R6) | Stufe 0 |

| RoboForex | Parameter/Version | Antwort und Grenzen | Scanner-Nutzung |
|---|---|---|---|
| GET `/health` | keine | aktive gespeicherte Subscriber>0, Instanz, Tokenmarker | ja |
| GET `/providers` | name/minSubscribers/sort/order/limit/offset | Default >=1, Opt-out minSubscribers=0, limit1..5000 | Katalog |
| GET `/providers/{login}` | login | Daten einer per erstem Login-Treffer gefundenen Strategie | Detail |
| GET `.../{mql4|mql5}/history` | keine wirksame Pagination | alle gespeicherten Subscriberpunkte | ja |
| GET `.../trades` | bekannte Plattform am Signal | Wrapper header/rows, aus derselben CSV | zusaetzlich |
| GET `.../trades.csv` | bekannte Plattform | MT5-Paarung, MT4 direkt, Balancezeilen, Lots x10; 404 ohne hashverifizierte Dealdatei | ja |
| GET `.../metrics` | bekannte Plattform | Balance, DD, Fenster-Yield/Monate, Closing-DD, Weeks, Currency=USD; kein echtes InitialDeposit | ja |
| GET `.../reports` | kein Downloadpfad implementiert | immer leere Liste; auch unbekannte IDs/Versionspfade koennen hier 200 leer liefern | ja, keine PDFs |
| POST `/update` | target/tradelisten/katalogMaxAlterH | JSON-Objekt geparst, Feldtypen nicht streng; 202/200/409 | Stufe 0 |
| GET `/update/status` | keine Jobbindung | letzter globaler Job; Hinweise bei Teilfehlern, kein strukturierter Fehlerzaehler | Stufe 0 |

Robo REST akzeptiert nur die zum bekannten Signal passende mql4/mql5-Version; keine MT4/MT5-Aliaszusage. `versionVon` ordnet jeden Nicht-mt5-Wert mql4 zu (`RestApiServer:563–564`), obwohl Rating auch R StocksTrader anfordert (`RoboForexClient:98`) und Members-Download diese Plattform ablehnt (`544–557`). Das ist eine Darstellung-/Scopegrenze; kein Nachweis einer falschen ausgegebenen Tradehistorie fuer RST.

## 4. Kennzahlen- und Auswahlsemantik

| Quelle/Feld | Formel/Herkunft | Zeit-/Kapitalbasis, Kosten | Aussagegrenze |
|---|---|---|---|
| MQL Subscribers | Listen-DOM -> H2, manuelle Historie | Messzeit, Version separat | fehlender DOM-Wert wird 0; SubscribersOnly kann dadurch vorzeitig stoppen |
| MQL weeks / Signalalter | im normalen REST-Katalog nicht geliefert (`RestApiServer.writeStat`, ca.813ff) | unbekannt, kein belegtes Alter | laut Hauptreview verwirft der aktive Scanner-Kandidatenfilter unbekanntes Alter bei Mindestalter26; normale Downloader-only-Anbieter erreichen dann die Analyse nicht. Im Mischmodus ergaenzt Direktabruf nur seinen eigenen Seiten-/Fix-ID-Scope. Kein Alter erraten. |
| MQL Balance, EquityDrawdown, MaxDDGraphic | HTML-Extractor | Plattform-/Chartangabe, keine unabhaengige historische Equity-Messung | kein ISO-Waehrungsvertrag; fehlende Daten koennen 0/1 werden |
| MQL Average3MonthProfit | arithmetischer Mittelwert extrahierter Monatswerte | letzte verfuegbare Monate; aktuelle Monatsbehandlung beachten | keine CAGR-/TWR-Zusage |
| MQL nMPDD | arithm. Monatsprofit / Plattform-DD | 3 Monate erlaubt kuerzere Daten; 6/9/12 benoetigen mehr | kein Scanner-Jahres-Calmar; unbekannter DD wird intern 1 |
| MQL Trade-CSV | Originalexport | Brutto-Profit und Commission/Swap separat, Balance/Kosten durch Parser | Export-Vollstaendigkeit nicht per SHA/Quellenledger belegt |
| Robo Rating | `profit_percent`, `profit_usd`, `dd_max`, `balance_usd`, Subscribers | gewaehltes Ratingfenster, default 3 Monate | fehlende numerische Werte haeufig 0; `profit_percent_max=300` ist ein fest eingebauter serverseitiger Vorfilter |
| Robo Average3MonthProfit | Fenster-Yield / Fenster-Monate; sonst /Lebensmonate | arithmetischer Durchschnitt | README behauptet stellenweise noch stets seit Start; Code kennt explizite Fenster |
| Robo EquityDrawdown | abs(Gesamt-DD), sonst abs(Fenster-DD) | Plattformwert; 0 wird null | kein gemessener historischer Floating-DD |
| Robo TradeEqDrawdownPct = TradeClosedDdPct | PnL-Kurve + implizite Basis = Fenster-PnL/(Yield/100) | Closing-/Modell-DD, keine Floatings | R3 Kontofluesse; zudem Rendite/Yield allein beweist keine wahre Kapitalbasis |
| Robo Tages-Kopiermodell | Flow=DeltaBalance-Tagesprofit; r=(Equity-Flow)/PrevEquity-1; 1000*Produkt(1+r) | Tageswerte, r auf [-95%,+200%] begrenzt | Modell, keine tatsaechlich kopierte Nettorendite; intraday Flowzeit unbekannt; Glattung/Clamping kann Tail-Risiken abschneiden |
| Robo MT4 Netto | round2(profit+commission+swap) | gespeicherte Kontoeinheiten | FX nicht normalisiert; REST markiert trotzdem USD |
| Robo MT5 Netto | Summe der Dealbeträge | Positionstransformation siehe R1 | INOUT-/Teilschliessungsfehler, fehlende Entries |
| Robo Lots | MT4 volume/1e6; MT5 round(volume)/100; CSV danach *10 | dokumentierte historische Kalibrierung | pauschale Gueltigkeit fuer alle Konten/Plattformen nicht unabhaengig belegt |
| Robo Weeks | OfferInitialDate bis LocalDate.now | Signal-/Offer-Alter | kein Beweis tatsaechlicher Trade-Historienlaenge |

**Auswahl:** MQL Defaultlimits je Version1000, Dateicache5 Tage, SubscribersOnly defaultfalse; bei aktiviertem SubscribersOnly ist MPDD-Loeschfilter aus. REST-Katalog liest die persistierte H2-Historie und ist kein aktueller Vollplattformkatalog. Robo Update laedt Top-target nach Abonnenten, festes Ratingfenster3 und Profitobergrenze300; REST liefert davon default nur Subscriber>=1. Neue Subscriber ausserhalb des Top-target werden nicht dadurch automatisch nachgeladen. Diese Deckel/Filter sind Auswahlverzerrungen, nicht per se Programmierfehler. Die Ziele anderer Quellen werden nicht aus Pelicans >=1-Regel abgeleitet.

Robo source_id+login wird im API-Request benoetigt und im Rating dedupliziert; Persistenz/REST/SubscriberDB verwenden aber weitgehend login allein. Ob login plattformuebergreifend garantiert eindeutig ist, ist ohne Quellvertrag nicht belegt. Eine reale Kollision wurde nicht behauptet. MQL H2 und Versionsordner unterscheiden MT4/MT5; die zentrale Hubidentitaet gehoert zum Hauptreview.

## 5. Priorisierte Findings

### QB-R1 — P1 — Robo MT5-Lifecycle: Restposition verschwindet, INOUT-Profit doppelt

**Anker:** `roboforex/src/main/java/de/robomonitor/deals/TradeAggregator.java:80–123,134–144`; `rest/RestApiServer.java:450–467,494–506`.

**Ausloeser/Erwartung:** Eine MT5-Position mit 1 IN-Lot und OUT0,25 bleibt 0,75 offen; eine Umkehr realisiert jeden Profit genau einmal. **Tatsaechlich:** Sobald ein OUT existiert, exportiert der Aggregator die gesamten IN-Lots als abgeschlossenen Trade und zaehlt IN-/OUT-Anzahl statt Restvolumen. Repro: offenePositionen=0, CSV zehn Lots (nach bestehender x10-Skalierung) voll geschlossen. Bei IN0, INOUT200, OUT100 werden 500 statt300 Gewinn ausgegeben: INOUT erzeugt einen separaten Trade und wird nochmals im Positionssummenloop addiert.

**Impact:** falsches realisiertes PnL, Preis-/Zeit-/Exposureverlauf, verschwindende Floating-Restposition, unzuverlaessige DD-/Rendite-/Martingale-Basis bis Scanner. **Sicherheit:** hoch fuer Codearithmetik, reale Auftretenshaeufigkeit unbekannt. **Gegenargument:** mehrere OUT werden inzwischen summiert; das loest die Volumen-/Reversalbilanz nicht. Vorhandene Tests bestaetigen vollstaendig geschlossene einfache Paare, kein Restvolumen bzw. Reversal mit nachfolgendem OUT.

**Empfehlung/Test:** Event-/Volumenbilanz pro Positionslebenslauf; realisierte Teilmengen mit ihren Zeitpunkten, verbleibende offene Menge getrennt. INOUT in schliessenden und neu eroeffnenden Anteil zerlegen, nie doppelt buchen. Tests 1IN/0,25OUT, mehrere Teilfills, Pyramide, INOUT/weiteresOUT, gleichzeitige Events. Semantik wird durch die vom Hauptreview bereitgestellte [MetaQuotes-Primärreferenz](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties) gestuetzt: INOUT ist Umkehr; Positions-ID verbindet Lebenslaufdeals; Dealvolumen ist mengenbezogen. Keine neue Plattformpruefung durch diesen Reviewer.

### QB-R2 — P1 — Robo abgeschnittene Historie erhaelt erfundene Eröffnung

**Anker:** `api/RoboForexClient.java:504,574–592`; `deals/TradeAggregator.java:106–121`; `rest/RestApiServer.java:494–507`.

Download stoppt bei20000 neuesten Deals, nur Loghinweis. OUT ohne IN wird mit OpenTime=CloseTime und OpenPrice=ClosePrice gerettet und als regulaere CSV ausgegeben. Probe: Verlust-25, Haltedauer0h, gleicher Ein-/Ausgangspreis; Scanner nimmt den Trade an. Meta/REST liefert keine belastbare Kennzeichnung als unvollstaendige Position oder abgeschnittene Lebenshistorie.

**Impact:** realisierte Zahlung bleibt erhalten, aber Halte-/Floating-/Exposuremessung erhaelt erfundene Eingaben und kann Risiko unterschaetzen. **Sicherheit:** hoch, einschliesslich Parser-Durchstich. **Staerkstes Gegenargument:** bewusst implementierter und getesteter Workaround rettet PnL und verhindert kompletten Importabbruch. Das rechtfertigt jedoch keine erfundene individuelle Eröffnung als Messdaten.

**Empfehlung/Test:** PnL erhalten, unbekannte Positionsfelder und History-Cap explizit kennzeichnen; H1-/Exposurefreigabe fuer diese Zeilen sperren oder getrennten Finanzereignispfad nutzen. Pagination bis belegtem Ende oder stabile Cutoff-/Vollstaendigkeitsmetadaten; Tests an Cap-Grenze und OUT-only, keine Erfindung von Zeit/Preis.

### QB-R3 — P1 — Robo Trade-Closing-DD rechnet Einzahlungen als Gewinn

**Anker:** `report/SignalPayloadBuilder.java:50–60,78–83`; `model/EquityKurve.java:55–70`; `RoboMonitorApp.java:416–421`; `rest/RestApiServer.java:398–399`.

Raw-Deal-Kurve addiert BALANCE-Buchungen ungefiltert; Basis wird aus dem so aufgeblasenen End-PnL/Yield abgeleitet. Repro exakt dieselben Daten: BALANCE+1000, Trade+100, Trade-50, Yield10%. DD aus Raw-Deals0,431034%; DD aus aggregierten Trades8,333333%; ohne Deposit ebenfalls8,333333%. Das ist keine Rundungsdifferenz. Der Raw-Pfad speist den Monitor-DD-Cache/REST.

**Impact:** Einzahlungen koennen die gemeldete harte Risikokennzahl verkleinern; GUI/REST und Berichtsfassung widersprechen sich. **Sicherheit:** hoch fuer die Kontaminierung und Zahlen; 8,333333% wird nicht als unabhaengig bewiesener echter Broker-DD ausgegeben, sondern als Vergleich derselben Modellrechnung ohne Fremdfluss.

**Gegenargument:** Closing-DD bleibt ein Modell; API-Yieldkapital ist nicht bewiesen. Gerade dann duerfen externe Fluesse nicht still zu Trading-PnL werden. **Empfehlung/Test:** separate Kontofluss-/Kostenklassifikation, konsistenter Raw-/Tradepfad, nachvollziehbare Kapitalbasis. Deposit-/Withdrawal-Invarianztest bei sonst identischen Trades und neutralisierter Rendite; kein Ersatz echter Floatingmessung.

### QB-R4 — P1 — Robo SHA-Ledger friert bestehende Historien dauerhaft ein

**Anker:** `store/DealStore.java:155–180`; `update/UpdateJobRunner.java:155–164,201–207`; `RoboMonitorApp.java:390–391`.

`istFrischGeladen` prueft ausschliesslich Dateiintegritaet und lokalen Ledger-SHA. `fetched_at`, Quellenzeit und neue Plattformdeals werden nicht verglichen. Probe mit korrektem Hash/Ledger und fetched_at2020: true. Stufe0 ueberspringt vorhandene Tageslisten und diese Dealdateien; frischer Katalog/Jobabschluss aktualisiert ihre Handelsdaten nicht. Selbst Update mit katalogMaxAlterH0 hebt den Tradeskip nicht auf.

**Impact:** Scanner kann dauerhaft alte ruhige Historien analysieren und spaetere Verluste uebersehen. **Sicherheit:** hoch. **Gegenargument:** manueller GUI-Modus „Alle ueberschreiben“ kann neu laden; Cache-first/Resume ist dokumentiert und sinnvoll. Das ist kein automatischer Frischenachweis fuer Stufe0.

**Empfehlung/Test:** Integritaet, Abruffrische und Datenzeit getrennt; vorhandene Listen regelmaessig/delta nachziehen und komplette Historie mergen. Fakeclock-/Newtrade-Test mit unveraendertem lokalen SHA, Alter, Neustart und Force-Update. MQL72h Gesamtskip/5Tage-Dateicache ist im Vergleich eine dokumentierte, wenn auch grosszuegige Grenze und nicht derselbe unbegrenzte Mechanismus.

### QB-R5 — P2 — Beide Quellen melden DONE trotz fehlgeschlagener Datenjobs

**Robo-Anker:** `update/UpdateJobRunner.java:125–130,155–185,221–232`. Repro6 Signale: alle5 angefragten Tageslisten schlagen fehl (Serienabbruch), anschliessend alle6 Dealabrufe ebenfalls; Endstatus done, errornull, TradelistenNeu0, Hinweise enthalten Fehler. Strukturierte `tradelistenFehler`/`tradelistenAbgebrochen` fehlen. Scanner80d4692 bewertet genau solche expliziten Felder; Hinweistext allein wird nicht gelb.

**MQL-Anker:** `gui/DownloadManager.java:174–188,300–307`, `gui/ConversionManager.java` Fehlercatch + `waitForConversionCompletion`, `gui/MqlDownloaderGui.java:193–213`. Workerfehler werden protokolliert/GUI-dialogisiert, Rueckgabewarten bestaetigt nur Threadende. Die Kaskade schreibt anschliessend Erfolgsvermerk und DONE. Einzelproviderfehler koennen sogar als Erfolg gezaehlt werden (`SignalDownloader:954–985`). MQL-GUI-/Netzfehler wurden nicht live erzeugt; der belegte Kontrollfluss ist die Evidenz.

**Impact:** falscher Erfolgs-/Frischemarker, weitere laengere Skips nach fehlgeschlagenem Abruf. **Sicherheit:** Robo dynamisch hoch, MQL statisch hoch. **Gegenargument:** Fehler sind im Log/teilweise Hinweise sichtbar; DONE kann technisch „beendet“ bedeuten. Ohne strukturierten Teilstatus bleibt der Consumer dennoch falsch entlastet.

**Empfehlung/Test:** Ergebnistransport ueber Futures/Resultobjekt, belegte Teilfehlerzaehler/Abbruch, Erfolgszeit nur fuer erfolgreich abgeschlossene Aufgaben. Tests null Erfolge, gemischte Erfolge, Serienabbruch, Conversionfehler und anschliessender Consumerstatus. Information ueber TopN/Cache allein darf nicht pauschal Fehler bedeuten.

### QB-R6 — P2 — MQL Update-Ergebnis ist String statt JSON-Objekt

**Anker:** `MqlDownloader/src/rest/RestApiServer.java:246–262,299–305`. `jsonVon` serialisiert nur Primitive; `job.statusJson().ergebnis` ist Map und faellt auf String.valueOf zurueck. Repro: `"ergebnis":"{signaleGeliefert=2, ... hinweise=[synthetic warning]}"`. Doku und Scanner erwarten ein Objekt. Scanner `_ergebnis_uebernehmen` verwirft Nichtdict.

**Impact:** Datenstand, Skipmarker, Zaehler und Hinweise gehen auf der Schnittstelle verloren; verstärkt R5. **Sicherheit:** hoch, direkter Aufruf derselben Serialisierung wie Endpoint. **Gegenargument:** state/phase/done/message bleiben korrekt; Job kann weiterhin beendet werden. **Empfehlung/Test:** echten rekursiven JSON-Serializer nutzen; REST-Test JSON parsen und ergebnis als Objekt/Listen/numeric/null pruefen, nicht nur Stringcontains(state).

### QB-R7 — P1 — MQL fehlende Monatsdaten koennen Originaldateisatz loeschen

**Anker:** `calculators/MPDDCalculator.java:82–118,166–180`; `utils/HtmlDatabase.java:26–52,65–80`; `converter/HtmlConverter.java:118–124,167–185,295–322`.

Fehlende/zu kurze Monatsreihe wird 0, fehlender DD1; daraus endlicher MPDD0. Der NaN-Schutz schuetzt nicht. Default SubscribersOnlyfalse: Converter loescht HTML, CSV und TXT als MPDD<0,5. Probe mit geaenderter DOM-Struktur ohne Monatsfelder: alle drei vorher vorhandenen Dateien danach false. Zudem loescht processDirectory bei jeder Conversionexception den Dateisatz, auch bei technischer Ursache.

**Impact:** Datenverlust und Ausschluss wegen fehlender Belege statt nachgewiesener schlechter Qualitaet. **Sicherheit:** hoch, tatsächlicher Converter mit synthetischen Dateien. **Gegenargument:** MPDD-Loeschung ist bewusstes Feature; SubscribersOnlytrue umgeht diesen Filter. Bewusste Loeschung bei berechnetem schlechtem MPDD rechtfertigt keine Loeschung bei fehlender Berechnungsbasis.

**Empfehlung/Test:** Unknown/Parseerror sauber propagieren, Originale erhalten; Quarantaene/qualitaetsmarkierter Ausschluss statt Loeschung bei Technikfehler. Tests leere/1Monat-Reihe, geaenderter DOM, fehlender DD, Schreibfehler und tatsaechlich berechenbarer MPDD<0,5 getrennt.

### QB-R8 — P2 — Robo kennt keine sichere Pflichtdaten-/Semantikvalidierung

**Anker:** `api/RoboForexClient.java:598–639`; `store/DealStore.java:245–265,271–287`; `rest/RestApiServer.java:494–507`.

Fehlender Profit wird per asDouble(0) zu belegtem Nullgewinn; fehlende/unbekannte Richtung zu BALANCE; fehlende Positions-ID zu0. Selbst hash-/anzahlkorrekte CSV wird beim Laden zeilenweise still verworfen. Probe API-MT4 ohne profit -> normalerTrade Netto0. Probe vom eigenen Writer signierter2Zeilen-Cache mit Separator in Deal.side -> hasDealstrue, nur1 geparsteZeile, REST200 mit leerer Trade-CSV (verbleibender IN). Der Hash beweist Bytes/Zeilenzahl, nicht erfolgreiche semantische Parsung.

**Impact:** Verlustdaten koennen fehlen/zu0werden, Typen koennen zu Kapitalflüssen umgedeutet werden. **Sicherheit:** hoch fuer Schema-/synthetische Fälle, aktuelle Plattforminzidenz unbekannt. **Gegenargument:** zufaellige Bitkorruption wird durch Hash normalerweise abgewehrt; semantisch ungueltige, aber signierte Writerdaten oder Schemawechsel bleiben moeglich.

**Empfehlung/Test:** Pflichtfelder/null/numeric/finite/Enums validieren; Header+Meta+geparsteAnzahl pruefen; kompletter Fehler statt Teilantwort. Buchungsarten erhalten und externe Fluesse von Kontokosten unterscheiden. Regression ohne Profit, mit explizitem0, ohne Richtungs-/Positions-ID, ungueltigerZeit, NaN, Separator und kaputter Verlustzeile.

### QB-R9 — P2 — MQL JSON-Trades verlieren die Eröffnungsfelder

**Anker:** `src/rest/CsvParser.java:55–67`; RESTproviderTrades nutzt diesen Parser. MQL-Header wiederholt Time, Price, Volume. Maps ueberschreiben die ersten Werte mit den Schlusswerten. Repro11Spalten-Header ->8Mapkeys, Time=Schlusszeit, Price=Schlusskurs; Eröffnungszeit/-kurs fehlen.

**Impact:** JSON-Consumer kann keine korrekte Haltedauer/Position rekonstruieren. **Sicherheit:** hoch. **Gegenargument:** Scanner nutzt rohe CSV, die hier korrekt97Netto und24h behaelt; kein aktueller Scanner-PnLfehler allein daraus. **Empfehlung/Test:** geordnete Zeilenarrays oder eindeutige stabile Schluessel fuer doppelte Spalten; Roundtriptest mit verschiedenen Start-/Schlusswerten. API-Schema dokumentiert anpassen.

### QB-R10 — P2 — Robo feste Tempnamen scheitern bei mehreren Storewritern

**Anker:** `store/DataStore.java:311–319`; `store/DealStore.java:61,100–120,231–240`. Instanzsynchronized schuetzt keine zweite Storeinstanz; DataStore hat keinen Pfadlock. Acht Stores am gleichen Reviewverzeichnis,320Writes:96 AccessDenied-/NoSuchFile-Fehler. Letzter Bestand war lesbar; kein unbelegter Totalverlust behauptet.

**Impact:** Speicherung/Frischevermerk kann fehlschlagen, CSV/Meta/Ledger sind keine gemeinsame Transaktion. **Sicherheit:** dynamisch hoch fuer konkurrierendeWriter; konkrete Parallelitaet im normalen einzelnen UI-Flow ist durch beginJob teilweise begrenzt. Mehrere Prozesse sind nicht koordiniert und wurden nicht gestartet.

**Empfehlung/Test:** Pfadbezogene gemeinsame Sperre + eindeutige Tempdateien; nach Failures keine Erfolgsmarker. Fuer Mehrprozessbetrieb expliziten Prozesslock oder Verbot/Kontrolle. Tests zwei Instanzen/samepath, Crash zwischenCSV/Meta, parallelReader, unveraenderterAltbestand bei Fehlschlag.

### QB-R11 — P2 — MQL Cachefrische vertraut nur Namenspraefix statt Signal-ID

**Anker:** `downloader/SignalDownloader.java:842–880`. HTML fuer Alpha101 plus frische CSV AlphaOther999 genuegt als Cachetreffer, obwohl Alpha101.csv fehlt. Reprotrue. Der spaetere REST-Dateiresolver ist inzwischen genauer, dessen Schutz hilft der vorgelagerten Skipentscheidung nicht.

**Impact:** fehlende/alte Tradehistorie eines Signals wird nicht nachgeladen. **Sicherheit:** hoch. **Gegenargument:** benoetigt Namenspraefixueberschneidung und passendesAlter; solche Anzeigenamen sind nicht eindeutig. **Empfehlung/Test:** denselben exakten ID/Versionsresolver wie REST nutzen, Format/Integritaet und zugeordneten Downloadabschluss pruefen. TestgleicherPraefix/verschiedeneIDs, gleicheNamen, umbenannteSignale, fehlendeCSV.

### QB-R12 — P2 — Update-Anlaufphase ist in beiden Apps nicht atomar reserviert

**Anker:** MQL `gui/MqlDownloaderGui.java:101–120`; Robo `RoboMonitorApp.java:287–311`. Beide pruefen nur RUNNING/busy, veroeffentlichen einen IDLE-Job und planen erst danach EDT/FX-Arbeit ein. Ein zweiter POST vor dem Eventthread kann einen neuen Job/globalenStatuszeiger erzeugen. MQL Job-ID enthaelt nur Sekunden; Robo randomSuffix reduziertIDkollision, loest Reservierung nicht.

**Impact:** ein Client beobachtet falschen letztenJob; spaeterer busyFehler kann den weiterlaufenden erstenJob verdecken. **Sicherheit:** hoher Codebeleg fuer das Zeitfenster; keine GUI-Live-Repro. **Gegenargument:** zweite Kaskade wird spaeter oft am busyGuard abgewiesen; das begrenzt doppelteDatenarbeit, nicht Jobzuordnung. **Empfehlung/Test:** Start serialisieren, reserviertenJob bereits vor Veröffentlichung als belegt markieren, UUID und jobgebundenesStatuspolling. KontrollierterTest zweiPOSTs bei blockiertemUI-Dispatcher; Consumer soll erwarteteJobID abgleichen (Hauptreview).

## 6. Aktuelle Dokumentationsabweichungen und akzeptierte Grenzen

- Robo `README.md` beschreibt Average3MonthProfit noch teils seit Start; `RestApiServer:539–550` verwendet inzwischen FensterYield/FensterMonate. Beide Begriffe unterscheiden.
- Robo `ANLEITUNG_DEALS.md` nennt /1e6 als echte Lots; REST korrigiert anschliessend x10. Die gesamte konkrete Kette und Quellenbelege getrennt fuer MT4/MT5/Kontotypen dokumentieren. Keine neue Skalierung allein auf Vermutung vornehmen.
- Robo Anleitung nennt weiter copyfx_cookie.txt, aktueller Client migriert zum session_cookie.txt. Nach Migration koennte erneutes Einspielen nur in die alte Datei unbemerkt wirkungslos sein. Footer behauptet noch rein oeffentlichesAPI/trotz implementierter Dealebene. Historische datierte Abnahmen sind keine aktuellen Plattformnachweise.
- **Korrektur bei der Umsetzung:** Die ursprüngliche Behauptung, Robos `run.bat` fehle im sauberen Archiv, war falsch. `git ls-tree 42b268641ad370ccae7841b6a478f9745cb57bd3 -- run.bat` belegt die bereits im geprüften Commit getrackte Datei. Sie ist kein offener Codefehler. MQL verwendet sein ebenfalls getracktes `start.bat`; die aktuelle Startanleitung wurde daran angeglichen.
- MQL REST-Doku Updateergebnis als Objekt stimmt nicht mit R6 ueberein; `CSV->JSON`-Beschreibung verschweigt doppelteHeader/R9.
- MQL aktuelle REST-Doku benennt hingegen targetIgnore, tradelistenIgnore, toleranteBodyerkennung, 72hGesamtskip und fehlendeUpdatepfade inOpenAPI bereits ehrlich. Das sind keine neu entdeckten Widersprueche.
- MQL Original-CSV-Archivpfade haben seit aktuellemStand eindeutigeID/Plattform-Belege und Whitelist-Schutz; normaleResolver verwenden finaleSignalID. Der PraefixCache R11 ist ein anderer Pfad.
- Robo EmptyDD->null ist konservativ hinsichtlich fehlenderMessung, aber unterscheidet echtenDD0 nicht vonunbekannt. ClosingDD ist mittlerweile korrekt alsClosingDD dokumentiert; NameTradeEqDrawdownPct bleibtlegacy, keinFalschnachweis historischerFloatingmessung.
- Quelle-Ampeln (z.B. Robo grün nur mit KI<=4) sind keine Hub-Grünregeln. QuelleMPDD0,5 und Kopierrenditeclamps sind Projektmethodik, keine statistische Freigabe fuer zukuenftigeGewinner.

## 7. Offene Vertrags-/Sicherheitsfragen, keine bestaetigten Plattformbehauptungen

1. **Waehrung/Kontotyp:** Robo REST setzt Currency=USD, normalisiert gespeicherte Trades aber nicht historisch per FX und speichert keine hinreichende Kontowaehrungsidentitaet. Die Dokumentation nennt EUR/ProCent-Beispiele. Eine allgemeine USD-Garantie fehlt; konkrete aktuelle Faktor-100-Fehler werden ohne Quellenabgleich nicht behauptet. MQL Converter liefert weder Broker noch Currency. Dies widerlegt einen Hubfallback „mql4 bedeutet RoboForex“ (an den Hauptreview gemeldet).
2. **Gross/Net/Fees:** Die aktuelle Robo-CSV trennt Profit von Commission/Swap korrekt nach ihrem internen Modell. Ob Quellfelder bereits netto sind, welche Kontoaktionen Gebuehren/Credit/Einzahlung bedeuten und ob Spread, Slippage oder Copyfee enthalten sind, ist nicht aus Feldnamen bewiesen. Alle Nicht-Buy/Sell-Aktionen werden BALANCE; unbekannte Enums fuehren nicht zu einem Fehler. Kein pauschaler Bruttobeweis.
3. **Vollstaendigkeit/Pagination:** Robo Rating paginiert und dedupliziert source_id+login; Dealpfad mit Cap20000 ohne Deal-ID-Deduplizierung. Wiederholte oder verschobene Seiten koennen Duplikate liefern; aktuelle API-Inzidenz unbekannt. Fehlendes entries-Array kann als leer gelten statt als Schemafehler. MQL DOM-Pagination, Listenlimits und Subscriberselectorfehler koennen Katalogkuerzung verursachen; kein Vollplattformabgleich durchgefuehrt.
4. **Frische/Reports:** Robo DD-Cache ist nicht an Trade-SHA/Yieldfenster gebunden; eine null-Neuberechnung entfernt alte Werte im Updatepfad nicht (`App:419`). MQL Root-TXT/Trade-CSV sind getrennte Dateien ohne gemeinsamen Snapshot. PDF-Hinweise und letzte Abrufzeit beweisen keine aktuelle Datenbasis.
5. **Auth/Netz:** LAN-Binding und optionaler Token sind dokumentierte Betriebsentscheidungen. Robo nutzt `String.equals`, MQL konstanten Bytevergleich; kein Timingexploit nachgewiesen. Querytoken kann in URLs/Logs landen; MQL Fehlerlogger nimmt RequestURI. CORS-MQL erlaubt nur GET/OPTIONS im Methods-Header trotz POST-Update. Kein Traversal-Beleg in den geprueften PDF-/CSV-Whitelistpfaden.
6. **Configfehler:** Robo `RestApiConfig:38–64` faellt bei unlesbarer Konfiguration auf enabled=true/token=leer zurueck. Beim Default-Binding an alle Interfaces kann Korruption damit Authentifizierung abschalten. Konkreter Codepfad, kein bestaetigter Vorfall. Letzten gueltigen Stand erhalten bzw. Start ablehnen.
7. **Statistische Auswahl:** TopSubscribers, feste Profitobergrenze300, MPDD-Vorfilter/Dateiloeschung, Luecken/Cap und ueberlebende Anbieter bewirken Selection-/Survivorshipbias. Historischer Modell-DD und kurze Renditereihen tragen keine Garantie der besten Signale. Reale Kopierkosten, Out-of-sample, Regimestabilitaet und Unsicherheit kleiner DD fehlen als allgemeine Validierung.

## 8. Korrekturplan ohne Produktmutation

1. **Datenintegritaet zuerst:** R7 Originaldaten bei fehlender Berechnungsbasis erhalten; R1 MT5 Volumen-/Reversalbilanz; R3 Fluesse aus Trading-DD; R2 unvollstaendige Eröffnungen kennzeichnen.
2. **Frische und Betriebsstatus:** R4 Delta-/Zeitfrische; R5 strukturierter Teilstatus/echter Workererfolg; R6 rekursives JSON; R12 atomare Jobreservierung/Jobbindung.
3. **Parser/Persistenz:** R8 Pflichtfelder und gesamter Parsevertrag; R10 eindeutige Tempdateien/Pfadtransaktion; R11 exakte Cacheidentitaet; R9 verlustfreies JSON-Schema.
4. **Vertraege und Doku:** Waehrung/Cent/Lots-Kalibrierung pro Plattform/Kontotyp unabhaengig belegen; Kontoaktionen/Fees klassifizieren; Umfang/Caps/Zeiten/Defaultfilter ausweisen. Doku gezielt korrigieren.
5. **Methodik danach:** Sensitivitaet, gemeinsame Beobachtungsfenster, Tail-/Regime-/Copykostenpruefung auf bereinigten Daten. Keine Schwellen, Waehrungsskalierungen oder neuen Integrationen auf Verdacht aendern.

Keine Produktkorrekturen vorgenommen. Befunde wurden an den Hauptreview mit Gegenargumenten und Quellankern uebergeben; fehlende Plattformbelege bleiben ausdruecklich offen.
