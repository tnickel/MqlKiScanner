> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\quellen_a`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# PelicanTrading — unabhängiges Quellenreview

HEAD `dde77d705a670b37fc0f422504e566a857527893`, master, Arbeitskopie vor/nach
Prüfung sauber. Source-Root:
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/PelicanTrading`.
Alle folgenden Java-Pfade relativ zu `src/main/java/de/pelicanmonitor` dieses
Roots; geprüfte Snapshotbytes sind identisch. Isolation, Befehle, Endpunktmatrix
und vollständige Belege: `README_REVIEW.md`, `audit/run/results.json`.

## Datenpfade und geprüfte Anforderungen

| Anforderung | Implementierung | Nachweis / Bewertung |
|---|---|---|
| Katalog laden | `api/PelicanClient.java:155–176`, `/api/discover/Strategies` | Ein unpaginiertes Array, Dedupe nach positiver Strategy.Id. Vollständigkeit des Plattformkatalogs offline nicht beweisbar. Nichtarrayantworten werden mittlerweile abgewiesen. Restlücke P-A01. |
| Details/Stats | `PelicanMonitorApp.java:442–464`, `api/PelicanClient.java:180–280` | Detail/Stats pro Anbieter; SessionException wird erneut geworfen, sonstige Einzelprobleme übergangen. Nicht geladene Werte bleiben überwiegend unbekannt; kein bewiesener Gesamt-Statsnachzug bei jedem Delta. |
| Aktive Auswahl mindestens 1 Kopierer | `PelicanMonitorApp.java:2555–2564`, REST `RestApiServer.java:348–383`, Update `update/UpdateJobRunner.java:224ff` | GUI-Auswahl sperrt <1 auch ohne optionalen Anzeigefilter; Batch verwendet sichtbare Auswahl; Update filtert nach konfiguriertem Abonnenten-/Top-N-Scope. REST Default >=1, explizites minSubscribers=0 und Detailarchiv sind bewusst möglich. |
| Rohkatalog vs Top-N | `update/UpdateJobRunner.java:109–140,224ff` | Katalog vollständig im Sinne des gelieferten Arrays; nur teure Tradelisten nach konfiguriertem Top-N. Ranking nach Abonnenten ist keine Qualitätsoptimierung; Anbieter außerhalb des Scopes können finanziell besser sein. |
| 0→1 / 1→0 | neuer Katalog und GUI/REST/Updatefilter | Änderung wird erst beim nächsten Katalogload erkannt, regulär bis 72 h; alte Historie bleibt archiviert. Kein Anspruch auf sofortige Plattformänderung. |
| Geschlossene Trades | `api/PelicanClient.java:299–352` | 31-Tage-Fenster, TradeId-Dedupe, strenge Identity/Richtung/Instrument/Quantity/Time-Prüfung; nullable Profit/ClosePrice bleibt unknown. |
| Inkrementeller Nachzug | `update/UpdateJobRunner.java:224–380`, `PelicanMonitorApp.java:497–533` | Bestehende Listen werden erneut mit überlappendem Fenster ab letztem Handelstag geladen. Heutiger Trade ist kein Skipbeweis mehr. Merge erhält ältere Daten. |
| Persistenz / Fehler | `store/SignalStore.java:40–291`, `store/DataStore.java` | Gemeinsame Pfad-/Providerlocks für Closed-Merge, strenge SHA-/Header-/Count-Prüfung, leere Datei gegen positive Plattformaktivität geprüft; echte IO-Fehler werden nicht als leerer Bestand behandelt. Atomare eindeutige Tempdateien. |
| Teilfehler | `update/UpdateJobRunner.java:311,330` | tradelistenAbgebrochen/tradelistenFehler inzwischen veröffentlicht; Scanner erkennt teilweise. Kein unveränderter Altbefund F9. |
| REST-Export | `rest/RestApiServer.java:570–716` | Pflichtdaten werden vor Export validiert, fehlender Profit erzeugt 404 statt 0/NPE; historische FX je Trade-Währung/Schlussdatum. |
| Berichte / Sicherheit | `rest/RestApiServer.java:845–906,960ff` | Whitelist lokaler PDF/MD-Namen; synthetischer Download 200 und Traversal 404. GET/POST-Token, Bearer/Query und OPTIONS getestet. |

## Kennzahlenmatrix

| Größe | Formel / Quelle | Einheiten / Zeit / Grenze |
|---|---|---|
| Plattformrendite | finite RealisedReturn/UnrealisedReturn *100 | kumuliert seit Inception, inklusive bzw. exklusive floating laut Feldbezeichnung; kein belegter Kopierer-Nettogewinn |
| Plattform-DD | finite MaxDrawdown/MaxDrawdownBalance *100 | API-Anteil, auch -1→-100; unbekannt bleibt null, bekannter 0 bleibt 0 |
| Balance / Equity | Balance; Balance+bekanntes UnrealisedPnl | Kontowährung, REST separat Snapshot-FX nach USD; unbekanntes floating beweist keine Equity |
| Periodenrendite | `(1+r_neu)/(1+r_alt)-1` | r ist kumulierter Anteil; Prozent erst *100. Fehlende/invalid Basis null; nach Totalverlust keine erfundene Erholung |
| Monatsstatistik | beobachtete Intervalle je Kalendergruppe mit Vorperiodenbasis | erster/letzter Teilmonat und fehlende Monatsendpunkte sind keine vollen vergleichbaren Kalendermonate. Durchschnitt ist kein TWR/CAGR über homogene Monate. |
| Closing-DD | gemergte realisierte PnL / realisierte Plattformrendite als implizite Basis; Peak→Tief, ggf. aktueller offener Endpunkt | Modellbasis, keine belegte Einlage, kein historischer Floating-DD; Basis muss endlich und positiv sein. Restliche Zeitinkonsistenz P-A02. |
| Winrate | wins/tradesTotal *100 | aktuelle Implementierung; Aggregatsemantik der Plattform nicht unabhängig belegt, deshalb kein bestätigter Nennerbug |
| CSV-Profit / Kosten | RealisedProfit je Trade; Commission 0, Swap leer | Keine gesonderten Plattform-Kosten-/Flowfelder rekonstruiert. Netto-/Bruttobedeutung unbekannt; keine Spread-/Slippagegarantie |
| Snapshot-FX | zeitlich markierter EZB-Snapshot, TTL/Offlinefallback | von historischen Trade-FX getrennt; Offlinefallback sichtbar, keine Garantie aktueller Ausführungskurse |
| Virtuelle Basis | InitialDepositVirtual=10000 | ausdrücklich Annahme, kein Plattformdeposit; Scanner darf sie nicht als belegtes Konto ausgeben |

Die früheren F4/F8-Fehler sind im aktuellen HEAD behoben und hier neu am Code
und synthetischen Fall gegengeprüft. F3 „Deals versus Positionen“ bleibt eine
Hypothese: lokale Teiltradelisten versus Lifetimecounts und Wins+Losses≠Total
beweisen diese Semantik nicht. Eine Nenneränderung ohne Primärbeleg wäre ebenfalls
unbegründet. Promptmigration nutzt jetzt vollständige bekannte SHA256-Standards;
individuelle Legacy-Erweiterungen bleiben erhalten, durch aktuelle Tests geprüft.

## P-A01 — P2 — falsche Datensätze im Katalogarray können Katalog still leeren

- **Ort:** `api/PelicanClient.java:164–176`; Speichern des Ergebnisses in
  `PelicanMonitorApp.java:474–476`, GUI entsprechend :1461/:1492–1493.
- **Auslöser:** HTTP 200 und syntaktisch korrektes, nichtleeres Array mit geändertem
  Datensatzschema, z.B. `[{"error":"schema changed"}]` statt Strategy.Id.
- **Ist:** Jeder Eintrag wird wegen Id<=0 übersprungen, Rückgabe leere Liste,
  keine Exception. Nachfolgende Katalogspeicherung ersetzt den bisherigen Bestand.
- **Soll:** Ein legitimes `[]` darf leer sein; ein nichtleeres Array ohne einen
  gültigen Strategy-Datensatz muss als Schemafehler erkennbar sein und den letzten
  gültigen Katalog erhalten. Teilweise verworfene Datensätze benötigen Qualitätszählung.
- **Nachweis:** `audit/run/results.json:pelican_nonempty_wrong_schema_catalogue`
  zeigt received_rows=1, parsed_rows=0, exception=false. Der Test läuft durch den
  öffentlichen ladeAlleProvider mit ersetztem HTTP-Transport, nicht nur eine Kopie
  des Parsealgorithmus.
- **Impact:** falscher erfolgreicher Leerstand / unbemerkte Auswahllücke; bestehende
  Tradearchive werden dadurch nicht gelöscht. Konkretes Auftreten auf der Plattform
  wurde nicht behauptet oder live geprüft.
- **Sicherheit:** hoch für bedingtes Codeverhalten; unbekannt für Plattformhäufigkeit.
- **Stärkster Gegenbeleg:** aktuelle Nichtarrayprüfung verhindert den häufigeren
  Error-Objektfall; positive-ID-Prüfung filtert ungültige Einzelrecords sinnvoll.
  Sie verhindert den beschriebenen vollständig invaliden Arrayfall nicht.
- **Korrekturtest:** erst gültigen Katalog speichern, dann nonempty-invalid-array
  liefern, Fehler plus unveränderter Snapshot; `[]` und teilweise valide Arrays
  separat definieren und testen.

## P-A02 — P2 — Delta-Trades und bis 72 h alte Stats werden als gemeinsame DD-Basis genutzt

- **Ort:** `PelicanMonitorApp.java:518–533`; `update/UpdateJobRunner.java:205–212`
  (Katalogskip); `report/ReportService.java:52–90`.
- **Auslöser:** bestehende Liste, Katalog aufgrund der 72-h-Regel übersprungen; danach
  neue realisierte Gewinne/Verluste per Delta laden. Das Providerobjekt behält die
  alte RealisedReturn, aktualisiereTradeliste holt keine neuen Stats.
- **Ist:** Kommentar :523 behauptet frische Stats aus derselben Katalogphase,
  obwohl diese ausgelassen sein kann. DD-Basis teilt frisches Gesamt-PnL durch
  alte kumulierte Rendite. Dadurch ändern sich Prozentwerte ohne konsistente Basis.
- **Unabhängiges Zahlenmodell:** echte konstante Modellbasis 1000, aktuelle Trades
  +250/−50, aktuelles PnL 200 / Return 20%. Closing-DD: 50 / 1250 = 4%.
  Alte Return 10% liefert implizit 2000; Code-DD: 50 / 2250 = 2,2222%.
- **Nachweis:** `audit/run/results.json:pelican_cached_stats_fresh_trades_dd`,
  beide Werte mit aktuellem ReportService berechnet; tatsächlicher fehlender Stats-
  Aufruf und Katalogskip sind im angegebenen Codepfad belegt. Es handelt sich nicht
  um einen beobachteten konkreten Plattformkontoausfall.
- **Impact:** ein Kanal der DD-Schranke und Monitor-/LLM-Anzeige kann zu niedrig
  werden. Scanner-Calmar verwendet richtigerweise eine andere H1-Messung.
- **Gegenargument:** diese Basis ist ausdrücklich nur eine implizite Modellbasis;
  selbst frische Lifetime-Return und unvollständige Trades garantieren keine echte
  Einlage. Das erklärt die übrige Modellunsicherheit, nicht die vermeidbare
  Mischung unterschiedlicher Datenstände.
- **Korrekturtest:** Katalog frisch/skip, bestehender Provider mit r_alt, frisches
  Delta; Stats neu laden oder Berechnung bis zur zeitkonsistenten Basis auf null
  setzen. Herkunft/Zeitbezug im DD-Cache binden.

## Dokumentation, Grenzen und Korrekturplan

README beschreibt aktuelle Version, REST-POST, Closing-DD, sanitizierte Fixtures
und historische FX zutreffend. doc/20 enthält ausdrücklich historische Aussagen
über leere Reports/einheitliche FX, die nicht als aktuelle Zusage gelten dürfen.

Noch offen, ohne bestätigten Bug: Katalogvollständigkeit/Rankings extern, API-
Fensterinklusion und verspätete Korrekturen vor dem Deltaüberlapp, Enabled-/Demo-
Policy, exakte Fee-/Profitsemantik, Sessionverhalten live, Archivabruf bei 0 Kopierern.
Das aktuelle bis 72 h verzögerte Erkennen von Abonnentenänderungen ist dokumentierte
Cachepolitik. Vollständige Lebenszeithistorie ist auch bei gleichen Counts unbewiesen.

Akut P-A01/P-A02 korrigieren; danach Schemas/Teilfehler für Detail-/Statsabrufe
sichtbar machen und Zeit-/Scopebindung von DD verbessern. Den gemeinsamen
MaxInt-Offset mit HTTP 500 als niedrige Priorität beheben. Keine Änderung des Winrate-Nenners
ohne Beleg. Keine neue MqlRealmonitor-/PWL-Integration.

**Tests:** sauberer Checkout 176/176 JUnit grün, 23 REST-Matrixfälle und synthetischer
Anbieter bis unverändertem Scannerparser. Kein Live-/LLM-/Konto-/GUI-Bedienlauf.
