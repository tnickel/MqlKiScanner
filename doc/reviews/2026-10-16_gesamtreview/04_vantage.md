> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\quellen_a`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# Vantage — unabhängiges Quellenreview

HEAD `1fe395805f29e20d2598aa37162e717769a15762`, master, Arbeitskopie vor/nach
Prüfung sauber. Source-Root `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage`.
Java-Pfade unten relativ zu `src/main/java/de/vantagemonitor` dieses Roots.
Gemeinsame Befehle/REST-Matrix/Isolation stehen in `README_REVIEW.md`.

## Datenfluss, Umfang und Anforderungsabgleich

1. `api/VantageClient.java:84–178` vereinigt fünf kuratierte topLists-Kategorien
   mit filter-signal/forWeb. Positive Kategorieantworten werden vorn eingereiht;
   danach Kopierersortierung bis min(count,250), schließlich Return-Auffüllung bis
   count. Dedupe nur auf Providerebene. Das ist kein vollständiger Plattformkatalog.
2. `api/VantageClient.java:280–304` ergänzt overview und detail/top; Update lädt
   höchstens die ersten 150 Stats nach (`update/UpdateJobRunner.java:152–169`).
   Einzelne Fehler werden nur geloggt. Fehlende Plattformwerte werden vielfach zu
   primitiver 0, einschließlich Return/Drawdown/Winrate/Copiercount.
3. `downloadTrades` verwendet lastId, Seiten mit 20 Trades, GUI/Update begrenzen auf 2000,
   genereller Client auf maximal 20000 nach Aufrufer. Offene Positionen separat
   mit Cursor und 100-Seiten-Schutz. Tages-PnL ist optional.
4. `store/TradeStore.java` hält Rohtrades/Positionen/Tageswerte plus SHA-Meta/total;
   `store/TradeListStore.java` hält zweiten CSV-/Meta-Cache und geladen.json.
   USC beim Import genau einmal/100; Drittwährungen bleiben im Rohcache.
5. REST liefert Katalog/History/Trades/Metrics/Reportsplatzhalter/Update. Default
   Katalog >=1 Kopierer, explicit minSubscribers=0 möglich. GUI kann anders filtern;
   Update lädt den gelieferten Top-N-Scope. Kein Nachweis, dass jeder Provider im
   Scope mindestens 1 hat; REST entfernt die Anbieter ohne Kopierer nachträglich.
6. Die CSV wird tatsächlich vom sauberen Scannerparser gelesen, nicht lediglich
   nach Headerstrings bewertet. Synthetischer Fehlerfall und gültige Bestandstests
   sind unten angegeben. Spätere H1-/Ampel-/Portfolioauswertung ist Hauptreviewumfang.

## Kennzahlen und Aussagegrenzen

| Größe | Herkunft / Formel | Aussagegrenze |
|---|---|---|
| Return30d / Winrate | returnRate/winRate *100 aus Ranking | standardmäßig primitiver 0 bei fehlendem Wert; Nichtvorhandensein ist damit nicht erkennbar |
| Lifetime-Return/DD/PF | overview(duration=All) und filter-signal | Stats nur für einen Teilkatalog; API-Semantik extern nicht neu belegt |
| Historienalter | months→round(months*30.44/7), lokale älteste Tages-/Tradehistorie kann Monate anheben | Alter ist kein Nachweis kompletter durchgehender Tradehistorie; unbekannt als 0 im Export |
| CSV-Profit | closeNetPnl, USC/100, sonst Konto-PnL→historischer USD-Kurs | `net` ist Feldname, vollständige Spread-/Slippage-/Kopierkosten nicht bewiesen |
| Commission/Swap | 0/leer im CSV | laut Exportmodell im net enthalten; keine separaten Cashflow-/Gebührenbuchungen rekonstruiert |
| Closing-DD | lokale kumulierte Trade-PnL / ReturnAll als Modellbasis | Teilhistorie versus Lifetime-Return; keine historische Floatingmessung; ungültige Basis siehe V-A05 |
| TradesTruncated | totalCount > geladene Zeilenzahl | Counts/SHA beweisen nicht Identität, Vollständigkeit oder Frische |
| Geldfelder mit Usd-Suffix | USC normalisiert, EUR/GBP roh in Modell/Report | Prompt nennt Originalwährung zu Beginn, mehrere Feld-/Tabellenlabels heißen dennoch USD; keine allgemeine USD-Normalisierung aller Kennzahlen |
| Historische FX | FxRates.rateFor(currency, closeDate), EZB floor, maximal 10 Tage | Rohcache unverändert, unbekannter Kurs 404. CloseDate verwendet lokale importierte Zeit; ursprünglicher Instant geht verloren. Handels-/Brokerzeitzone extern offen |

Tests bestätigen USD/USC/Drittwährungen und kein Zukunftskurs. Sie beweisen keine
Livefeldsemantik und keinen vollständigen tatsächlichen Kopierkontoverlauf.

## V-A01 — P1 — Stufe 0 friert bekannte Anbieter dauerhaft ein

- **Ort:** `VantageMonitorApp.java:376–388`, `update/UpdateJobRunner.java:191–199`,
  `store/TradeListStore.java:158–166` (`istGeladen` nur Registerpräsenz).
- **Auslöser:** Anbieter hat verifizierten CSV-/Meta-Cache und Registereintrag.
  Seitdem sind neue/geschlossene/offene Trades entstanden, lokal wurden Bytes
  aber nicht verändert. Der Katalog kann separat bereits erneuert sein.
- **Ist:** kein Plattform-Tradeabruf, keine offene Position/Tages-PnL-Aktualisierung;
  übersprungen++, Job done und datenstand=jetzt. Es existiert keine Alters- oder
  Remote-Cursorprüfung im Skipprädikat. Gleichbleibende lokale SHA ist nur Integrität.
- **Nachweis:** AuditProbe erzeugt echten TradeStore und TradeListStore, setzt
  CSV-mtime auf 2020, bewertet das identische Appprädikat und führt den tatsächlichen
  Runner mit diesen Diensten aus. `vantage_runner_old_verified_cache_skip`:
  attempts=0, done, keine Warnung. Siehe `audit/run/results.json`.
- **Impact:** neue Verluste/Exposures fehlen in späterer Forensik dauerhaft, obwohl
  Stufe 0 Aktualisierung zugesagt ist. Hauptreview bestätigt keine nachgelagerte
  Tradezeit-Frischesperre; Version/SHA-Neuberechnung heilt fehlende Remoteabrufe nicht.
- **Gegenargument:** GUI „Geladene überspringen“ ist bewusst ein Cachemodus und ein
  manueller Vollabruf bleibt möglich. Stufe 0 übernimmt diesen Modus jedoch stets
  ohne Wahl und behauptet damit einen neu aktualisierten Gesamtstand.
- **Sicherheit:** hoch, tatsächliches Prädikat+Runner reproduziert; konkrete neue
  Plattformverluste wurden nicht beobachtet/behauptet.
- **Korrekturtest:** beliebig alter valider Cache plus neuer Remote-Trade muss
  Stufe 0-Delta/Vollabgleich erzwingen; auch vorhandene Positionen aktualisieren;
  letzter erfolgreicher Abruf versus letzter Trade separat persistieren.

## V-A02 — P2 — fehlender Profit wird 0, fehlende Richtung wird Sell

- **Ort:** `api/VantageClient.java:401–430`, `rest/RestApiServer.java:486–498`.
- **Auslöser:** sonst gültiger Trade, closeNetPnl oder tradeAction fehlt/ungültig.
- **Ist:** fehlender Profit→NaN aus parseDoubleSafe→Math.round(NaN)=0; unbekannte
  Richtung→nichtBUY→Sell. Persistenz/SHA bestätigen diese erfundenen Werte.
- **Nachweis:** synthetische Strategie 970101, echte Parser→Store→REST HTTP 200→Scannerparser;
  `audit/scanner_contract_results.json`: Netto 0, Richtung Sell. Der Scanner sieht
  keinen fehlerhaften Typ mehr. Python `download_trades.py:49–54,109` ersetzt
  fehlende/ungültige Geldwerte ebenfalls mit 0.
- **Impact:** ein unbekannter Verlust kann als Break-even verschwinden; Richtung
  verfälscht Exposure und Equity-Rekonstruktion. Dass die Plattform solche Daten
  tatsächlich geliefert hat, ist nicht belegt; der Fehlerpfad ist bedingt sicher.
- **Gegenargument:** die meisten normalen API-Datensätze enthalten diese Werte.
  Das entbindet den Import nicht von einer Pflichtdatenprüfung.
- **Korrekturtest:** missing/null/blank/string-NaN/Infinity getrennt von bekannter 0;
  unbekannter Profit bleibt nullable oder verweigert Export; unbekannte Richtung
  darf keine Position werden. Bestand darf bei Fehler nicht überschrieben werden.

## V-A03 — P2 — Java-Cursorpagination akzeptiert wiederholte Trades als neue Zeilen

- **Ort:** `api/VantageClient.java:346–368`; keine seenIds-/cursorAdvancement-Prüfung.
- **Auslöser:** API/Proxy liefert auf lastId denselben Record erneut, z.B. Cursor
  wird ignoriert oder Seite wiederholt. Identität ist im JSON als id/tradeOrderId da.
- **Ist:** wiederholte Zeilen werden bis maxTrades angehängt. Repro: drei Zeilen,
  eine eindeutige TradeID, Anbieter-total=2; kein Fehler. 2000er-Update kann daraus
  einen künstlichen Bestand aufbauen und metadatenverifiziert speichern.
- **Nachweis:** FakeHttp bedient tatsächlichen downloadTrades; Ergebnis
  `vantage_repeated_cursor` einschließlich Requestfolge in `audit/run/results.json`.
- **Gegenbeleg:** Providerkatalog dedupliziert, Python `full_history` prüft
  Cursorwiederholung bereits und der zugehörige Test besteht. Das schützt den
  produktiven Java-GUI-/Updatepfad nicht. CSV hat später keine Trade-ID mehr.
- **Impact:** vervielfachtes PnL/Exposure und falsche Counts; ausgewiesene Kappung
  kann zugleich historische Lücken verdecken. Keine Behauptung aktueller API-Häufigkeit.
- **Korrekturtest:** repeated/nonadvancing cursor, überlappende Seiten, fehlende ID,
  Totaländerung und legitime verschiedene TradeIDs mit identischen Handelswerten.
  Dedupe nach stabiler Identität, nicht nach identischen CSV-Zeilen.

## V-A04 — P2 — Downloadfehler wird beim Scanner vollständiger Erfolg

- **Ort:** `update/UpdateJobRunner.java:230–260,129`; `update/UpdateJob.java:30–43`.
- **Auslöser:** einzelner Downloadfehler oder Abbruch nach fünf Serienfehlern.
- **Ist:** nur Hinweistext, keine tradelistenFehler/tradelistenAbgebrochen-Felder;
  run setzt done. Scanner interpretiert fehlende optionale Felder als 0/false.
- **Nachweis:** echter Runner mit IOException-Fakedienst und anschließende
  tatsächliche `_update_eine_quelle` des sauberen Scanner-Snapshots:
  `vantage_failed_update_in_scanner`: status=fertig, Fehlerzahl 0, Warntext vorhanden.
  DB-Persistenz/Netztransport im Scannerrepro wurden durch Stubs ersetzt.
- **Gegenargument:** Warntext bleibt für aufmerksame Nutzer sichtbar. Er ist
  jedoch kein maschinenlesbarer Teilstatus; mit_hinweisen prüft Status statt Text.
- **Impact:** Workflow-/Auditgrün für unvollständig aktualisierten Bestand.
- **Korrekturtest:** Strukturfelder analog aktuellem Pelican setzen; Einzel-/Serien-
  fehler und Scopebegrenzung unterscheiden; Scanner muss teilweise melden und
  tatsächliche Fortschrittszähler erhalten.

## V-A05 — P2 — negative implizite Kapitalbasis wird als DD 0 ausgegeben

- **Ort:** `report/SignalPayloadBuilder.java:43–50`; `model/EquityDrawdown.java:39–47`.
- **Auslöser:** positive Lifetime-Return, aber geladene Teilhistorie netto negativ
  oder 0, z.B. Return 50%, ein Verlust−25. Das ist bei beschränktem Fenster plausibel.
- **Ist:** Basis−50, Kurvenwerte−50→−75, Peak<=0 führt mathematisch undefinierten
  relativen DD auf konkrete 0 zurück. Dieser Wert wird gecacht/berichtet.
- **Nachweis:** `vantage_negative_dd_basis` zeigt implied_basis−50/returned_dd=0.
- **Gegenargument:** Plattform-DD bleibt als anderer konservativer Kanal verfügbar;
  daraus folgt aber keine gültige 0 für den unabhängigen Monitor-DD. Erst recht ist
  eine Teilhistorie nicht derselbe Zeitraum wie dieLifetime-Return.
- **Korrekturtest:** Kapitalbasis finite>0, sonst null; Gewinn 0/negativ, NaN, Teil-
  fenster und fehlende Return separat. Zeit-/Scopebindung der Basis ausweisen.

## V-A06 — P2 — Defaultprompt schreibt unbelegte DD-Ursache vor

- **Ort:** `config/LlmSettings.java:241–247`.
- **Ist:** Faktor 2-Abweichung zwischen Closing-DD und Plattform-DD soll als
  Kernbefund „gemeldeter DD glättet intra-day Rückfälle“ ausgelegt werden.
- **Warum falsch abgesichert:** Unterschiedliche Kapitalbasis, Fenster, historische
  Floatingverluste, FX und Teilbestand können Abweichungen erklären. Closing-DD
  belegt keinen Intradayverlauf. Der Prompt gibt eine Ursache vor, die Daten nicht
  beweisen, auch wenn kein Modellaufruf stattfand.
- **Gegenargument:** Prompt verlangt daneben Quellen/Unsicherheit; die ausdrücklich
  vorgeschriebene Erklärung widerspricht dieser allgemeinen Vorsicht.
- **Korrekturtest:** Promptvertrag muss Closing-/Equity-DD und alternative Ursachen
  unterscheiden; keine kausale Glättungs-/Beschönigungsbehauptung ohne Beleg.

## Auswahl, Dokumentation und weitere Grenzen

README:47 beschreibt Return-Paging als Nachfüllpfad. Tatsächlich wird zuerst
Kopierer-sortiert aufgefüllt; bei Standardziel 200 und KOPIERER_TIEFE=250 läuft
keine Return-Phase. Repro `vantage_union_default_target`: fünf leere topLists,
zwei Kopiererseiten,200 Anbieter, keine Return-Anfragen. Dies widerlegt eine
garantierte Vereinigung beider Ranglisten beim Standardziel, nicht den Erfolg
des tatsächlich implementierten Top-N-Abrufs. **P3 Dokumentation/Designklarheit:**
Ranglistenbudget explizit machen; Test für count=200/250/>250 und Überschneidungen.

Zusätzliche Grenzen: Nichtarray/fehlende orderList beendet History still; ungeprüfte
Richtung/Quantity/Preise und primitiver 0bei fehlenden Stats sind systematische
Schemaqualitätsthemen. Der verifizierte TradeStore prüft SHA, aber parsed count
wird nicht gegen Meta-count abgeglichen (`TradeStore.java:275–288`); Leser
überspringt defekte CSV-Zeilen. Ein selbst erzeugter korrekt gehashter Parseverlust
ist deshalb möglich, ohne dass ein SHA eine Fachvalidierung ersetzt.
Crossprozess-Python/Java-Writes haben keine gemeinsame Sperre, feste Tempnamen
bleiben in Vantage vorhanden. Kein Race gegen Nutzerdaten wurde ausgelöst;
konkrete Wahrscheinlichkeit/Betriebsauswirkung hier nicht reproduziert.

**Korrekturpriorität:** V-A01 zuerst, dann V-A02/A03/A04; anschließend DD-Basis/
Prompt und Parser-/Cachekohärenz. 2000er-Kappung selbst ist transparent und eine
akzeptierte Begrenzung, kein automatisch neuer Bug. Sie begrenzt dennoch die
Aussage über „beste Signale“ und Tailrisiken. Keine Rankingsvalidierung/OOS-Prognose.

**Nachweise:** 49/49 Java, 6/6 Python offline; 21 REST-Matrixfälle; synthetischer
Provider→Scannerparser; zwei konkrete Runnerszenarien. Keine Liveplattform,
kein LLM, keine Authaktion, keine tatsächliche GUI-Bedienung.
