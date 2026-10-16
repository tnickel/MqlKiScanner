> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\quellen_a`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# ZuluMonitor — unabhängiges Quellenreview

HEAD: 72df0cf49aa4f44fe0d82d9d07112091cf4d5665, Branch master. Arbeitskopie vor und
nach der Prüfung sauber. Source-Root:
D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor.
Java-Pfade unten relativ zu src/main/java/de/zulumonitor dieses Roots.
Isolation, Befehle und REST-Matrix stehen in README_REVIEW.md. Keine Plattform-,
Login-, Tokenrefresh- oder Modellaktion wurde ausgeführt.

## Datenpfad und Anforderungsabgleich

| Bereich | Implementierung | Bewertung |
|---|---|---|
| Region und Hosts | api/ZuluTradeClient.java:146–192,431–465 | detectFlavor mit EU-Fallback; mehrere Tradinghosts, Retry und Schema-Prädikat. Lokale Tests decken Hostfehler und ungültige Antworten ab; keine Livefunktionsgarantie. |
| Katalog | api/ZuluTradeClient.java:195–240 | performance/search mit 20 Tradern pro Seite, Sortierung DESC, Deduplizierung nach providerId. Nur Top-N, kein vollständiger Plattformkatalog. |
| Top-N | ZuluMonitorApp.java:377–380, Client:201–214 | Update sortiert nach Followern, GUI wählbar. Feste ceil(count/20)-Seitenzahl kann bei verschobenen Duplikaten weniger als count liefern; Istzahl wird offengelegt. |
| Katalogschema | Client:231–278 | result muss Array sein. Fehlender trader wird übersprungen; zahlreiche fehlende Zahlen werden 0, fehlender DD wird NaN. Fehlende Abonnentenzahl ist damit nicht von belegter 0 unterscheidbar. |
| Aktive Auswahl | rest/RestApiServer.java:299–333 | REST standardmäßig mindestens einen Follower; minSubscribers=0 zeigt bewusst das Archiv. GUI und Update haben eigene Scopes. |
| Closed-Historie | Client:281–383 | Seiten mit 100 Trades, last als Boolean erforderlich, leere Seite ohne Endmarkierung Fehler. Teilweise ungültige Records werden übersprungen. Kein Trade-ID-Dedupe oder Fortschrittsnachweis; Z-A03. |
| Open-Historie | Client:387–408 | Momentaufnahme separat. Bei Fehlabruf verwirft der neue Updatepfad den alten Open-Cache, statt ihn frisch anzuzeigen. Keine historische Floatingkurve. |
| Persistenz | store/DataStore.java:113–121,245–294,392–413 | CSV und Meta mit requested/count/SHA. Gelesene Anzahl, ProviderId und TradeId werden geprüft; eindeutige atomare Tempdateien. Hash beweist keine Frische. |
| Ledger | store/TradeListenStore.java:47–61, App:1255ff | Vergleich ausschließlich lokaler Hashes; keine Remoteänderungs- oder Altersprüfung. Z-A01. |
| Abonnentenhistorie | store/SubscriberDb.java, REST:376–385 | Lokale Tages-Snapshots inklusive liveFollowers, keine rückwirkende Plattformhistorie. |
| REST und FX | rest/RestApiServer.java:388–546 | Version zulu, Netto-PnL der CSV nach USD normalisiert. Historische Kurse je Schlussdatum, Metadaten offengelegt; reports ist ein leerer Platzhalter. |
| Update | update/UpdateJobRunner.java:98–196 | Katalogcache bis 72 Stunden, angeforderte Trade-Tiefe Integer.MAX_VALUE, Ledger-Skip; Teilfehlerproblem Z-A04. |

Katalog und Followerzahlen sind Snapshots, regulär bis 72 Stunden alt. Follower
und liveFollowers sind getrennte überlieferte Felder. Ihre genaue Geschäftssemantik
wurde nicht frisch gegen die Plattform geprüft.

## Kennzahlenmatrix

| Größe | Herkunft und Formel | Zeitbasis und Aussagegrenze |
|---|---|---|
| ROI/ROR/Plattform-DD | overallStats und timeframeStats 10000 | Plattformgesamtzeitraum; Feldnamen allein beweisen keine Bereinigung von Kontoflows. |
| Average3MonthProfit | ROI geteilt durch Laufzeit in Monaten aus weeks | Arithmetische Herleitung, kein gemessener 3-Monatsmittelwert und kein TWR. |
| Winrate | winTrades/trades ×100 | Katalogaggregate desselben Timeframes; genaue Semantik extern nicht neu validiert. Lokale Pips-Winrate im Bericht ist eine andere Statistik. |
| Trade-Netto | netPnl; daneben grossPnl und pips | Kontowährung; separate Gebühren und Kontobuchungen nicht rekonstruiert. Fehlendes Netto wird derzeit 0, Z-A02. |
| CSV Commission/Swap | 0/leer | Exportmodell nimmt Kosten im Netto an; kein Nachweis sämtlicher Spread-, Slippage- oder Kopierkosten. |
| Closing-DD | kumulierte Trade-Netto-PnL geteilt durch ROI/100 als implizite Basis; Peak→Tief | Modellbasis, keine belegte Einlage; Teilfenster versus Lifetime-ROI. Kein historischer Equity-DD. |
| Historische FX | USD unverändert, USC/100, sonst EZB | UTC-Schlussdatum bei erhaltenem API-Instant, Legacydatum sonst. Letzter belegter Kurs davor, maximal zehn Tage. Fehlender Kurs erzeugt 404. Preise, Lots und Rohcache bleiben unverändert. |
| Vollständigkeit | TradesStored, Katalog-TradesTotalAvailable, TradesTruncated plus Hinweis | Vergleich mit einem Katalogsnapshot. Gleiche Anzahl beweist weder Identität noch vollständige Historie. |
| Kapitalbasis | kein Balance/InitialDeposit verfügbar | amountFollowing ist Kopiererkapital, keine Providerbalance. Modellannahmen müssen als solche erkennbar bleiben. |

Fehlender Plattform-DD bleibt im Modell NaN und wird nicht pauschal als bekannte
0 behandelt. Vorhandene REST-Tests prüfen fehlende Drawdowns. Das behebt die
ungültige implizite Kapitalbasis aus Z-A05 allerdings nicht.

## Z-A01 — P1 — verifizierte Historie gilt zeitlich unbegrenzt als frisch

**Ort:** ZuluMonitorApp.java:391–399; store/TradeListenStore.java:54–61;
update/UpdateJobRunner.java:149–156.

**Auslöser:** Der lokale CSV-/Meta-Bestand deckt die angeforderte Tiefe ab und
sein Hash widerspricht dem Ledger nicht. Danach entstehen remote neue Trades
oder andere offene Positionen.

**Ist/Soll:** Der Updatepfad führt keinen Remoteabgleich durch, sondern
überspringt den Anbieter. Auch ohne Ledger-Eintrag akzeptiert istFrisch einen
vorhandenen verifizierten Hash. Weder geladenAm, CSV-mtime noch jüngster
Tradeabschluss begrenzen die Gültigkeit. Der Job endet done mit Datenstand jetzt.
Stufe 0 müsste einen neuen Abruf belegen oder den alten Datenstand kenntlich machen.

**Repro:** AuditProbe verwendet echten DataStore und Ledger, requestedMax
Integer.MAX_VALUE und CSV-mtime 2020. Das tatsächliche Appprädikat ergibt true.
Der echte Runner macht keinen Tradeabruf:
audit/run/results.json, zulumonitor_runner_old_verified_cache_skip.

**Impact/Sicherheit:** Neue Verluste und Exposures fehlen dauerhaft in späterer
Forensik. Das Hauptreview bestätigt keine nachgelagerte absolute Frischesperre.
Codeverhalten ist sicher reproduziert; ein konkreter neuer Plattformverlust
wurde nicht behauptet oder beobachtet.

**Gegenargument:** Der manuelle GUI-Modus „Geladene überspringen“ ist bewusst
vorhanden, und ein Vollabruf bleibt möglich. Stufe 0 übernimmt ihn jedoch immer
und bezeichnet den Durchlauf als Aktualisierung.

**Korrektur/Regression:** Alter Cache plus neuer Remote-Trade muss einen Abgleich
auslösen. Erfolgreicher Abrufzeitpunkt und letzter Tradezeitpunkt getrennt
persistieren; offene Positionen auch bei unverändertem Closed-SHA aktualisieren.

## Z-A02 — P2 — unbekanntes Netto und Richtung werden als 0/Sell exportiert

**Ort:** api/ZuluTradeClient.java:350–383; rest/RestApiServer.java:480–495.

**Auslöser:** TradeId, Zeiten und Lots sind vorhanden, netPnl oder tradeType
fehlen. Im synthetischen Beispiel ist grossPnl −24 bekannt, Netto unbekannt.

**Ist:** Der Validator akzeptiert den Record, parseTrade setzt netPnl 0.
Leere Richtung wird im REST zu Sell. Validator und Parser haben zudem
verschiedene Netto-Fallbacks: Nur der Validator verwendet grossPnl als Fallback.
Gross darf ohnehin nicht ungeprüft Netto ersetzen.

**Repro:** zulu_missing_pnl_validation zeigt accepted=true/pnl=0.
Tatsächlicher Store → REST HTTP200 → unveränderter Scannerparser ergibt 0/Sell:
audit/scanner_contract_results.json.

**Impact/Sicherheit:** Ein unbekannter Verlust kann als Break-even erscheinen,
Exposure und Equityrichtung werden verfälscht. Bedingtes Codeverhalten ist
bewiesen, aktuelles Auftreten auf Produktivkonten nicht.

**Gegenargument:** Normale vollständige Records funktionieren; der Scanner
verweigert strukturell ungültige CSV. Diese CSV ist bereits strukturell gültig
und enthält keine erkennbare Unbekannt-Markierung mehr.

**Korrektur/Regression:** Missing/null/ungültig/NaN/Infinity von belegter 0
trennen. Nur bekannte Richtungen exportieren; unknown erhalten oder den Export
mit Grund verweigern. Bestätigten Bestand bei Fehler erhalten.

## Z-A03 — P2 — wiederholte Historienseiten vervielfachen Trades

**Ort:** api/ZuluTradeClient.java:284–333; ZuluMonitorApp.java:298,397–399.

**Auslöser:** API oder Proxy wiederholt eine formal gültige Seite mit last=false,
etwa weil der page-Parameter ignoriert wird.

**Ist/Repro:** Der gleiche Trade wird erneut angehängt. FakeHttp im tatsächlichen
downloadTradeHistory liefert bei maxTrades=3 drei Zeilen mit einer TradeID,
ohne Fehler: zulu_repeated_pages in audit/run/results.json. Stufe 0 verwendet
Integer.MAX_VALUE; bei dauernder Wiederholung wäre die theoretische Obergrenze
extrem hoch. Große Last oder Speichererschöpfung wurde nicht ausgelöst.

**Impact:** Vervielfachtes PnL/Exposure oder sehr langer Job. Count und SHA können
die fehlerhafte Liste formal bestätigen. Im Scanner-CSV fehlt die TradeID.

**Gegenargument:** Last-Boolean und Host-Schema schützen vor fehlenden Endmarkern
und vollständig ungültigen Seiten; sie erkennen keine gültige Wiederholung.
Dedupe im Providerkatalog schützt die Trade-Pagination nicht.

**Korrektur/Regression:** SeenTradeIDs, Seitenfingerprint und begrenzter
Fortschrittsabbruch. Überlappende Seiten, dynamische Verschiebungen und verschiedene
TradeIDs mit identischen Handelswerten getrennt testen. Keine reine CSV-Zeilendedeupe.

## Z-A04 — P2 — geschlossener Trade-Downloadfehler wird Scannerstatus fertig

**Ort:** update/UpdateJobRunner.java:173–194,107.

**Auslöser:** Einzelner Tradeabruf wirft IOException oder fünf Serienfehler
brechen die Schleife ab.

**Ist/Repro:** Nur Hinweistext, keine ergebnis.tradelistenFehler oder
tradelistenAbgebrochen. Der Runner setzt done. Seine tatsächliche Antwort wurde
an die echte Scannerfunktion übergeben, Transport und DB-Schreiben wurden dabei
gestubbt: zulumonitor_failed_update_in_scanner ergibt fertig, Fehlerzahl 0,
Abbruch false. Der Warntext bleibt vorhanden.

**Impact:** Falscher maschinenlesbarer Erfolgsstatus und damit grüne
Workflow-/Auditdarstellung für nicht vollständig aktualisierte Daten.

**Gegenargument:** Offene Positionen sind ausdrücklich best effort. Der Repro
betrifft geschlossene Historie. Sichtbarer Warntext ersetzt keinen Teilstatus.

**Korrektur/Regression:** Fehlercount und Abbruchflag analog Pelican liefern;
Scanner muss teilweise melden. Open-Warnung, Scopebegrenzung und echte
Downloadfehler getrennt behandeln, Fortschrittszähler erhalten.

## Z-A05 — P2 — ungültige negative DD-Basis liefert konkrete 0

**Ort:** report/TradePayloadBuilder.java:39–46; model/EquityDrawdown.java:39–47.

**Auslöser/Repro:** Lifetime-ROI +50%, lokale Teilhistorie netto −25.
Implizite Basis −50, Kurve −50→−75. Peak<=0 erzeugt relativen DD 0.
zulu_negative_dd_basis in audit/run/results.json bestätigt das Ergebnis.

**Impact:** Scheinbar risikoloser Monitor-DD auf ungültigem Nenner. Andere
Plattform-DD-Kanäle begrenzen die praktische Wirkung, machen die Zahl nicht gültig.

**Gegenargument:** Die Basis ist nur ein Modell und kein Scanner-Calmar-Nenner.
Auch ein relatives Modellergebnis benötigt einen endlichen positiven Nenner.

**Korrektur/Regression:** Basis finite>0, sonst null. Null, 0, negative PnL, NaN
und abweichende Lebenszeit-/Teilfenster testen. DD-Cache an Datenbasis binden;
bei nicht mehr berechenbarem DD keinen veralteten gültigen Wert behaupten.

## Z-A06 — P2 — aktiver Defaultprompt bezeichnet Closing-DD als Max-EQ-DD

**Ort:** config/AppSettings.java:324–331.

Der Prompt bezeichnet die realisierte Closing-Kurve als „aus der VOLLEN
Trade-Kurve nachgemessener Max-EQ-DD“ und verlangt bei Faktor-2-Abweichung
die Erklärung, gemeldete DDs glätteten Intraday-Rückfälle.

**Gegenbeleg:** model/EquityKurve.java summiert ausschließlich realisierte PnL
beim Tradeabschluss. Historische Kurse/Floatingverluste fließen nicht ein.
Unterschiedliche Fenster, Kapitalbasis und Abtastung können die Differenz
erklären, ohne Plattformglättung zu beweisen.

**Impact/Sicherheit:** Die produktive Vorlage fordert eine nicht belegte
Risikobegründung. Kein Modell wurde aufgerufen; die erzeugten Berichte wurden
hier nicht hinsichtlich tatsächlicher Übernahme dieser Aussage geprüft.

**Gegenargument:** README und GUI benennen Closing-DD inzwischen korrekt.
Die weiterhin aktive Promptvorlage hat diese Korrektur nicht erhalten.

**Korrektur/Regression:** Promptvertrag muss Closing-, Equity- und Intrabar-DD
sowie alternative Ursachen unterscheiden. Null bedeutet auch fehlende Basis,
nicht ausschließlich „keine Trades“.

## Persistenz, Sicherheit, Dokumentation und Methodik

Die aktuelle README beschreibt lokale Abonnentenhistorie, Closing-DD und
historische FX zutreffend. Die alten „history leer/USD-only“-Aussagen in doc/20
sind historisch markiert und kein heutiger Vertrag.

JSON-POST/Status und optionaler Token sind vorhanden. Tokenheader, Bearer, Query,
fehlender Token, POST-Token und OPTIONS wurden synthetisch geprüft. Reports ist
ein leerer Platzhalter ohne beliebigen Dateizugriff.

Eindeutige atomare Tempdateien und strenge Meta-/Providerchecks schützen die
Integrität. Keine pauschale Übernahme älterer Race-/Schemafindings. CSV und Meta
werden nicht gemeinsam transaktional ersetzt; zwischen den Writes kann der
Bestand unverifiziert erscheinen, was fail-closed ist. Mehrprozesse/Abstürze
und private Legacybestände wurden nicht gegen Produktivdaten simuliert.

Follower-Top-N ist eine selektive Vorauswahl: neue oder unpopuläre Strategien
können vor der Finanzprüfung fehlen. Kurze oder unvollständige Historie,
fehlende Flows, historisches Floating und unbekannte Kopierkosten verhindern
eine belastbare Garantie „bester zukünftiger Signale“. Daraus folgt nicht,
dass jeder Followerfilter ein Implementierungsfehler sei.

**Priorität:** Z-A01 zuerst, dann Z-A02/A03/A04, danach DD und Prompt.
Gemeinsamen MaxInt-Offset-Überlauf als P3 korrigieren. Keine neue Integration
von MqlRealmonitor oder PelicanWinnerLooser.

**Nachweise und Grenzen:** 107/107 Java-Tests offline, 21 HTTP-Matrixfälle,
Anbieter970201 bis Scannerparser, echte Runner-Skip-/Fehlerrepros.
Externe Katalogvollständigkeit, Livefeldsemantik, Browserlogin, LLM-Ausgabe
und endgültige Scannerampel wurden hier nicht live verifiziert.
