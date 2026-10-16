> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\quellen_a`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# Teilreview Quellen A — PelicanTrading, Vantage, Zulu

Prüfung: 16.10.2026. Review, keine Produktkorrektur. Verantwortlicher Teilumfang:
Quellabruf, lokale Daten, Berechnungen, REST und Updatejobs dieser drei Quellen.
Die abschließende Scannerbewertung, Portfolioauswahl und übrigen Quellen werden
vom Hauptreview zusammengeführt. MqlRealmonitor und PelicanWinnerLooser sind
ausdrücklich nicht produktiv integriert und wurden nicht integriert.

## Untersuchte Stände und Isolation

| Repository | Branch | Vollständiger HEAD | Zustand vor/nach Review | Snapshot |
|---|---|---|---|---|
| PelicanTrading | master | dde77d705a670b37fc0f422504e566a857527893 | sauber/sauber | `quellen_a/PelicanTrading` |
| vantage | master | 1fe395805f29e20d2598aa37162e717769a15762 | sauber/sauber | `quellen_a/vantage` |
| zulumonitor | master | 72df0cf49aa4f44fe0d82d9d07112091cf4d5665 | sauber/sauber | `quellen_a/zulumonitor` |

Snapshots wurden mit `git archive HEAD --format=tar --output=...` und `tar -xf`
aus genau diesen Commits erstellt. Private Cookies, lokale Datenbanken,
Trade-/FX-Caches und Einstellungen wurden nicht kopiert. Metadaten stehen in
`{Repository}.manifest.json`. Produktive Arbeitskopien blieben unverändert.
Alle neuen Repros und Daten liegen ausschließlich unter `quellen_a/audit`.

Die vorhandenen Java-Tests wurden ausschließlich in den drei Snapshots mit
`mvn -o test` ausgeführt. Die separaten HeadlessSmoke/HeadlessReport-Programme
mit Plattform-/LLM-Zugriff wurden nicht gestartet; ihre `main`-Methoden sind
keine JUnit-Testläufe. Geprüfte JUnit-Netzpfade verwenden lokale HTTP-Stubs.
Es gab keinen Plattform-, Login-, Broker-, LLM- oder externen FX-Aufruf.

## Laufnachweise

Java: Eclipse Adoptium JDK 25.0.4.101, Maven 3.9.6. Compiler-Release aller drei
Projekte: 25. Pelican-Version 1.5.0, Vantage/Zulu jeweils 1.2.0 laut POM.

| Befehl im jeweiligen Snapshot | Ergebnis | Beleg |
|---|---|---|
| PelicanTrading: `mvn -o test` | 176 Tests, 0 Fehler, 0 Skips | `PelicanTrading.maven.log`, `PelicanTrading/target/surefire-reports` |
| vantage: `mvn -o test` | 49 Tests, 0 Fehler, 0 Skips | `vantage.maven.log`, `vantage/target/surefire-reports` |
| zulumonitor: `mvn -o test` | 107 Tests, 0 Fehler, 0 Skips | `zulumonitor.maven.log`, `zulumonitor/target/surefire-reports` |
| vantage: Store-Python `-m pytest tests/test_download_trades.py -q` | 6 bestanden | `vantage.pythonstore.log` |
| `javac -cp <audit/classpath.txt> -d audit/classes audit/AuditProbe.java` und `java -cp <classpath>;audit/classes AuditProbe audit/run` | alle eingebauten Assertions bestanden | `audit/probe.log`, `audit/run/results.json` |
| Python312 `audit/scanner_contract_probe.py ../scanner/snapshot` | drei CSV-Durchstiche und zwei echte Scanner-Updateauswertungen bestätigt | `audit/scanner_contract_results.json` |

Exakter pytest-Pythonpfad:
`C:/Users/tnickel/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe`.
Der Standardbibliothek-/Scanner-Repro wurde erfolgreich mit
`C:/Users/tnickel/AppData/Local/Programs/Python/Python312/python.exe` ausgeführt.
Zwei zunächst versuchte Runtimes hatten kein pytest; dazu liegen die fehlgeschlagenen
Importlogs `vantage.python.log` und `vantage.python312.log` vor. Keine Installation.

Die Java-Repros ersetzen den HTTP-Transport durch `FakeHttp`: auch fest im
Produktcode enthaltene Plattform-URLs werden ausschließlich im Speicher bedient.
Die REST-Server binden für die Dauer des Repros freie lokale Testports.
FX-Fetcher werfen absichtlich eine IOException, sobald ein externer Abruf nötig wäre.
Die Daten aller Anbieter sind unabhängig konstruierte synthetische Werte.

## REST-Inventar und Endpunktmatrix

Gemeinsamer Präfix `/api/v1`; Datenversion Pelican=`pelican`, Vantage=`vantage`,
Zulu=`zulu`. Gemeinsamer Protokollname `mql5-downloader-v1`. Standardports:
8090, 8092, 8093. Konfiguration `data/rest_api.json`; Instanzkennung frei wählbar.
Die Server binden gemäß `new InetSocketAddress(port)` standardmäßig an alle
lokalen Interfaces. Optionaler Token über `X-API-Token`, `Authorization: Bearer`
oder Query `token`; offener Betrieb ohne Token ist eine bewusste lokale/LAN-Regel.
CORS erlaubt Aufrufern die API-Nutzung; OPTIONS benötigt keinen Token.

| Methode / Pfad | Eingaben | Antwort / Einheiten | Seiteneffekt und geprüfter Zustand |
|---|---|---|---|
| GET `/health` | Token bei Konfiguration | status/service/instance/providers/uptime/serverTime | 200; Anbieterzahl mit Abonnenten; kein Build-Hash im Vertrag |
| GET `/providers` | name, minSubscribers, sort, order, limit, offset | total/count/offset/items; string signalId, version, subscriber count, weeks, currencyCode, links | 200; Default minSubscribers=1; explizit 0 zeigt Rohkatalog; Filter vor Pagination |
| GET `/providers/{id}` | numerische ID | ein item, einschließlich archivierter 0-Abonnenten-Anbieter | 200 bei bekanntem Anbieter; unbekannte ID 404 |
| GET `/providers/{id}/{version}/history` | bekannte ID/Version | count/points mit Datum/Zeit und Abonnentenzahl | 200; ohne lokale Snapshots leere Reihe; kein rückwirkender Plattformnachweis |
| GET `/providers/{id}/{version}/metrics` | bekannte ID/Version | signalId/version/metrics; Prozent, counts, kontoabhängige bzw. explizit normalisierte Geldfelder | 200; unbekannte ID 404; Nullsemantik und Fachgrenzen siehe Teilberichte |
| GET `/providers/{id}/{version}/trades.csv` | bekannte ID/Version, verifizierter Cache | UTF-8/BOM, `Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit`, Netto-PnL USD | 200 für synthetischen Anbieter; fehlende Daten/Kurse 404 mit Grund; keine Teil-FX-Konvertierung |
| GET `/providers/{id}/{version}/trades` | wie CSV | header/count/rows/href plus Normalisierungsmetadaten | gleicher Datenbestand und Fehlerpfad wie CSV |
| GET `/providers/{id}/{version}/reports` | ID/Version | count/items | Pelican listet lokale PDFs/MDs; Vantage/Zulu liefern Platzhalterliste leer |
| GET `/providers/{id}/pelican/reports/{name}` | whitelisted lokaler Berichtname | PDF oder Markdown-Bytes | nur Pelican; synthetischer MD-Download 200, kodierter Traversalversuch 404 |
| POST `/update` | JSON-Objekt: target, tradelisten, katalogMaxAlterH; App entscheidet tatsächlichen Scope | jobId/status/bereitsLaufend | Hintergrundjob; Teststarter 202; busy-Zweig 409 bzw. laufender Job 200 nach Starter; kein anderer POST-Pfad erlaubt |
| GET `/update/status` | Token; kein selektierender Job-ID-Parameter | letzter Job: jobId/state/phase/done/total/message/ergebnis/error | running im HTTP-Repro, done/error/login_required durch Bestandstests/Runner-Repros; Job-ID-Zuordnung im Scanner ist eigener Hauptreviewbefund |
| OPTIONS beliebiger Pfad | CORS-Preflight | 204 | ohne Token |

`limit` wird 1..5000 geklemmt, `offset` mindestens 0. Name ist substring,
order=`asc` oder sonst absteigend. Sortiermöglichkeiten werden durch den
jeweiligen Code bestimmt; Pelican week/monthChange sortiert aktuell nach
Abonnentenzahl und nicht nach dem historischen Änderungswert. Das ist eine
Vertragsgrenze für externe Aufrufer, im regulären Scanneraufruf wird subscribers
verwendet. Boolesche Updateoptionen sind tatsächlich typabhängig; Strings wie
`"false"` sind kein zugesicherter Booleanvertrag.

Die vollständigen Request-/Response-Bodies und Statuscodes stehen in
`audit/run/results.json`: 23 Matrixfälle Pelican, jeweils 21 Vantage/Zulu.
Alle regulären Routen, Versionsfehler, unbekannte Metrics-ID, Pagination,
Tokenheader/Bearer/Query, fehlender Token, OPTIONS und POST-Token wurden geprüft.
Nicht sämtliche Kombinationen jedes Parameters wurden exhaustiv getestet.
Der Extremwert `offset=2147483647` produziert in allen drei Quellen HTTP500
durch `offset+limit`-Integerüberlauf: niedrige Priorität, reguläre Scanner-
Offsets betroffen sind dadurch nicht. Korrektur: lange Arithmetik/saturierendes
Intervall und erwartete leere Seite; Regression MaxInt-Offset.

## Synthetischer Anbieter bis Scanner

Plattform-JSON (FakeHttp bzw. tatsächlicher Parser) → tatsächliches Modell →
tatsächlicher CSV-/Meta-Store → echter lokaler REST-Server → unveränderter
Parser des sauberen Scanner-Snapshots unter
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot`.

| Quelle / Anbieter | Ergebnis Scanner |
|---|---|
| Pelican 970301 | ein EURUSD-Buy, Netto -25 USD, Commission/Swap 0; bekanntes Pflichtdatenmodell korrekt übertragen |
| Vantage 970101, Profit und Richtung fehlen im JSON | ein EURUSD-Sell, Netto 0 USD; erfundene Werte sind bereits vor Scannerimport konkret geworden |
| Zulu 970201, Profit und Richtung fehlen im JSON | ein EURUSD-Sell, Netto 0 USD; gleiches Integritätsproblem |

Pelican mit anschließend entferntem RealisedProfit erhält `null` und verweigert
den CSV-Export mit 404. Der Scanner kann Vantage-/Zulu-Ersetzungen nicht mehr
erkennen: das exportierte CSV ist syntaktisch gültig. Alle drei Quellformate
erreichen den Scanner ohne eigene Adapter. Das ist ein belegter Parserdurchstich,
kein vollständiger Durchlauf durch H1-Rekonstruktion, Ampel, Portfolio oder Sync.

## Zusammenfassung und Prioritäten

1. **P1:** Vantage und Zulu müssen bestehende Historien im Stufe-0-Update erneut
   abgleichen; verifizierte lokale Bytes sind kein Frischenachweis. Der aktuelle
   Pfad aktualisiert bekannte Anbieter unabhängig vom Alter nicht mehr.
2. **P2:** Fehlende Profit-/Richtungswerte nicht erfinden; Pagination muss
   wiederholte IDs/Cursor/Seiten erkennen; Teilfehler maschinenlesbar melden.
3. **P2:** Nicht positive DD-Kapitalbasis verwerfen, DD-/Renditezeitfenster
   abgleichen; unbelegte DD-Kausalbehauptungen in Vantage-/Zulu-Prompts entfernen.
4. **P2 Pelican:** Nichtleere, vollständig falsch strukturierte Katalogarrays
   dürfen keinen erfolgreichen leeren Katalog erzeugen. Nach Katalogskip
   aktualisierte Trades nicht mit alten Stats als zeitkonsistente DD-Basis behandeln.
5. **P3:** Restliche Dokumentations-/Parametergrenzen (Rankingbeschreibung,
   MaxInt-Offset) nachziehen; keine neue Integration der zurückgestellten Projekte.

Die neuen Regressionstests sollen die erwartete Korrektur prüfen, nicht nur den
heutigen Fehlerzustand. Die Auditprobes assertieren absichtlich heutige Istfehler,
um sie reproduzierbar zu belegen. Grüne Bestands- und Auditläufe sind keine
Behauptung, dass das System fehlerfrei oder die Rangfolge statistisch validiert ist.

## Grenzen

Kein frischer Plattformabgleich, keine Login-/Browserinteraktion, keine LLM-
Ausführung, keine Prüfung laufender alter Builds. Plattformfeldbedeutungen ohne
ausreichende lokale Primärbelege bleiben offen; insbesondere Pelican-Winrate,
NumCopiers-Bedeutung, RealisedProfit-Netto-/Bruttosemantik und vollständiger
Discover-Katalog. Echte Gebühren, Flows, Ausführung, Intrabarverluste und
Kopierbarkeit lassen sich aus den vorhandenen Quelltradelisten nicht vollständig
beweisen. Private Persistenzmigrationen wurden nicht gegen Nutzerdaten getestet.

Teilberichte: `review_pelican.md`, `review_vantage.md`, `review_zulu.md`.
