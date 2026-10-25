# Quellenprüfung zu DeepSeek F1/F2

18.10.2026. Auftrag: bestehende Quellenverträge und Betriebsbehauptungen
kritisch nachprüfen. Keine Quelländerungen, Testneuläufe, produktiven
Updates, Plattformdownloads, Terminal-/Prozessaktionen oder Commits.
Alle neu angelegten Dateien tragen das Präfix `quellen_`; frühere Belege und
Manifeste bleiben unverändert.

## F2: Vollständiger Anzeigekatalog und reguläre Kandidaten sind verschiedene Scopes

**Die Lücke ist für den vollständigen Scanner-Anzeigekatalog bestätigt.**
Alle fünf Quellen liefern `/providers` standardmäßig ab einem Abonnenten/
Kopierer/Follower. Alle fünf unterstützen ausdrücklich `minSubscribers=0`
für sämtliche lokal gespeicherten Provider, unabhängig von dieser Schwelle.
Der untersuchte Scanner-Aufruf übergab vor der Scopekorrektur nur
`limit`/`offset` und gegebenenfalls `version`:
`SignalKiScanner/src/mqlkiscanner/downloader_client.py:156` und
`SignalKiScanner/src/mqlkiscanner/ingest.py:84`.

Dabei sind die Projektanweisungen gemeinsam zu lesen:

- `SignalKiScanner/src/mqlkiscanner/katalog.py:2` beschreibt die eigene
  Vollkatalogtabelle für „Alle Signale“, unabhängig von Workflowfiltern.
- `SignalKiScanner/AGENTS.md:1519–1548` und
  `SignalKiScanner/doc/23_stufe0-client-updates.md:367–397` bewahren den
  vollständigen **lokalen Katalog**, trennen davon aber die teuren
  Tradelisten. Dort ist ausdrücklich dokumentiert, dass der Scanner
  regulär `minSubscribers=1` verwendet.
- `PelicanTrading/src/main/java/de/pelicanmonitor/update/UpdateJobRunner.java:205`
  lädt den Katalog; die gesonderte Tradephase filtert ab Zeile 237 auf
  Abonnenten und kürzt ab Zeile 253 auf die konfigurierten Top-N.

Daraus folgt eine eng begrenzte Korrektur: **Der Anzeigekatalog-Sync fragt
explizit `minSubscribers=0` ab; die reguläre Kandidatenbeschaffung behält
`minSubscribers=1`.** Den gemeinsamen Default auf Null zu drehen würde
zusätzliche 0-Abonnenten-Kandidaten ermöglichen und den dokumentierten
Trade-Scope verändern. Ein Metadaten-Vollkatalog löst für sich keine
zusätzlichen Trade-Batches aus.

„Vollkatalog“ bezeichnet hier den lokal vorhandenen Quellenbestand. Dadurch
werden weder Plattform-Toplistenlimits noch andere vorgelagerte Quellenfilter
aufgehoben. Die beobachteten Mengen sind keine Aussage über alle weltweit
auf den Plattformen verfügbaren Anbieter.

## Lokale HTTP-Probe am 18.10.2026 um 17:05:53 Europe/Berlin

`quellen_http_probe.py` führte genau **20 begrenzte GETs** aus: pro Quelle
`/health` sowie drei `/providers`-Abfragen mit jeweils `limit=1&offset=0`.
Keine Authentisierungsdatei wurde gelesen. Redirects sind gesperrt;
Trade-/Metrics-Endpunkte wurden nicht abgerufen. Gespeichert werden nur
Status, Zeit, Gesamtzahl und wenige öffentliche Identitäts-/Schemafelder.
Jede Einzelabfrage besitzt einen eigenen UTC-Zeitpunkt in `quellen_http.json`.

| Quelle / Port | Default | `minSubscribers=0` | zusätzliche lokale Rohzeilen |
| --- | ---: | ---: | ---: |
| MqlDownloader / 8089 | 216 | 236 | 20 |
| PelicanTrading / 8090 | 640 | 2188 | 1548 |
| RoboForex / 8091 | 200 | 200 | 0 |
| Vantage / 8092 | 199 | 200 | 1 |
| ZuluMonitor / 8093 | 200 | 200 | 0 |

Die zusätzliche Vantage-Zeile fehlt in der Mengenbilanz des Fremdreviews.
Dies sind die **API-Felder `total`**, keine vollständige neue Pagination,
ID-Normalisierung oder Scanner-Tabellenbilanz. Insbesondere wurde der
bekannte Unterschied zwischen numerischen Scanner-IDs und nichtnumerischen
API-Testzeilen hier nicht neu über den vollständigen Bestand geprüft.

Alle Abfragen antworteten HTTP 200. Ein zusätzlicher unbekannter Parameter
`quellenProbeUnknown=1` neben `minSubscribers=0` wurde von allen fünf
laufenden Diensten akzeptiert; `total` und erste Identität blieben gleich.
Auch der aktuelle Code verwirft unbekannte Queryfelder nicht: Die
Providerhandler lesen nur ihre bekannten Schlüssel aus der Query-Map.

| Quellrepository | aktueller Filtercode | vorhandener REST-Vertragstest |
| --- | --- | --- |
| MqlDownloader | `src/rest/RestApiServer.java:887` (`parseLong`, Default 1) | `tests/rest/SubscriberDefaultTest.java:36` |
| PelicanTrading | `src/main/java/de/pelicanmonitor/rest/RestApiServer.java:359` | `src/test/java/de/pelicanmonitor/RestApiServerTest.java:226` |
| roboforex | `src/main/java/de/robomonitor/rest/RestApiServer.java:314` | `src/test/java/de/robomonitor/RestApiServerTest.java:181` |
| vantage | `src/main/java/de/vantagemonitor/rest/RestApiServer.java:308` | `src/test/java/de/vantagemonitor/RestApiServerTest.java:124` |
| zulumonitor | `src/main/java/de/zulumonitor/rest/RestApiServer.java:309` | `src/test/java/de/zulumonitor/RestApiServerTest.java:131` |

Bei den vier Monitoren gilt der Filter nur für positive Minima; bei Null
bleibt die lokale Liste ungefiltert. MQL entfernt bei Null lediglich
negative Abonnentenzahlen; der beobachtete Healthbestand 236 stimmt mit
seinem `minSubscribers=0`-Total 236 überein.

## F1: konkrete Builddrift statt pauschalem Neustart aller fünf Quellen

`quellen_process_probe.ps1` liest ausschließlich Listenerzuordnung und
Prozessmetadaten. Vollständige Kommandozeilen bleiben im RAM; ausgegeben
werden nur bekannte Main-Klassen, PID/Startzeit und aktuelle Dateimetadaten.
`quellen_process.json` enthält Quell-/Classdateihashes auf der Festplatte.
Diese Hashes sind ausdrücklich **kein Hash bereits geladener JVM-Bytecodes**.

Alle fünf Listener gehören weiterhin den um **12:01:21–12:01:25 Berlin**
gestarteten JVMs. Der MqlDownloader läuft über Maven Exec, die vier
Monitore referenzieren ihre jeweiligen `target/classes`-Ordner.

- **MQL:** `MqlDownloaderGui.java`/`ClientUpdateRunner.java` und die um
  13:05 ergänzte REST-Wochenausgabe entstanden nach diesem Start. Die
  aktuell abgefragte erste Providerantwort enthält noch kein `weeks`-Feld.
  Die neue Ausgabe aus `RestApiServer.writeStat` ist damit dort nicht
  aktiv. Die auf Platte gebauten neuen Klassen belegen keine automatische
  Übernahme in den laufenden Prozess.
- **Vantage:** `TradeStore.java`, `VantageMonitorApp.java` und der neue
  `HistoryFiles`-Publisher sowie deren geprüfte Classdateien entstanden
  ebenfalls nach diesem JVM-Start. Die Erneuerungskorrektur ist auf Platte
  vorhanden; eine produktive Abnahme nach Übernahme dieses Codes fehlt.
- **Pelican/Robo/Zulu:** Arbeitsbäume sind sauber, aktuelle Commits vom
  16.10.2026. Ihre geprüften REST-Quell-/Classdateien liegen zeitlich
  **vor** dem heutigen Prozessstart. Für diese drei Quellen ist aus diesem
  Befund kein neuer Ausrollbedarf nachgewiesen.

`quellen_repositories.json` hält die gelesenen Git-Revisionen und Statuspfade
fest. Es gibt keine Grundlage, allein aus dem gemeinsamen Startzeitpunkt
die Forderung „alle fünf neu bauen und neu starten“ abzuleiten.
Der Zulu-Hinweis wird zudem in **Scanner-Python** zusammengeführt:
`SignalKiScanner/src/mqlkiscanner/ingest.py:451` liest sowohl
`TradesCompletenessNote` als auch `CompletenessNote`. Dieser Scannerfix
benötigt keinen Neubau des Java-Zulu-Monitors.

## Vantage-404: gültiger Altbestandsschutz bleibt auch nach dem Fix bestehen

Die Aussage „404 nur der alte Build“ ist falsch. Auch der **aktuelle**
`vantage/src/main/java/de/vantagemonitor/rest/RestApiServer.java:482` weist
Historien ohne `TradeStore.hasTrades`-Verifikationsbeleg zurück. Der
aktuelle Test
`vantage/src/test/java/de/vantagemonitor/RestApiServerTest.java:245`
erwartet nach Setzen von `version=1` ausdrücklich 404 für beide
Trade-Endpunkte und erst nach einer gültigen frischen Speicherung 200.
Ein Neustart alleine zertifiziert den Altbestand nicht als UTC und
erneuert keine Historie.

Das Fremdreview nennt drei direkt abgefragte Vantage-IDs. Das belegt diese
HTTP-Stichprobe. Die vorhandene **frühere** lokale Inventur
`nachweise/downloads_vantage_metadata.json` fand 611 v1-Metadateien und
darunter 199/199 damals gelistete Kataloghistorien mit Legacy-Zeitbasis.
Das ist eine starke zusätzliche Bestandsgrundlage für den Schutzgrund,
aber keine aktuelle Vollabfrage aller Trade-Endpunkte. Die Reichweiten
„drei HTTP-Proben“, „199 zugeordnete lokale Kataloghistorien“ und
„611 Metadateien im Cache“ dürfen nicht gleichgesetzt werden.

## Reproduktion

Im Scanner-Repository:

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/deepseek_nachpruefung/quellen_http_probe.py
& ./doc/reviews/2026-10-18_download_datenfluss_pruefung/deepseek_nachpruefung/quellen_process_probe.ps1
```

Die beiden Programme schreiben ausschließlich ihre eigenen neuen
`quellen_*.json`-Belege in dieses Reviewverzeichnis. Die Abfragen sind eine
zeitlich begrenzte Momentaufnahme; keine produktive Reparatur oder
vollständige Laufzeitabnahme wurde durchgeführt.
