# Download- und Quellenprüfung am 18.10.2026

Eigener Prüfbereich: MqlDownloader, PelicanTrading, roboforex, vantage, zulumonitor sowie Scanner-Stufe 0, REST-Ingest und Exportparser. Keine AGENTS.md in diesen fünf Quellprojekten gefunden; Scanner-AGENTS.md und übergebene Nutzerregeln berücksichtigt. MqlRealmonitor und PelicanWinnerLooser ausgelassen.

Produktiver Zugriff ausschließlich lesend: lokale HTTP-GETs, SQLite-Snapshot des Hauptprüfers, vorhandene Artefakte und Metadaten. Keine Update-POSTs, App-/Terminalstarts, Scans, Produktivcodeänderungen oder Zugangsdaten ausgegeben. Reproduktionsprogramme schreiben ausschließlich synthetische Fixtures unter diesem Nachweisverzeichnis. Die Java-Reproduktion für MQL konstruiert keine GUI und ruft keinen Downloader auf.

## Bestätigte Befunde

### D1: MqlDownloader überspringt bei frischem Katalog auch die Trade-Aktualisierung

Priorität: P1; deterministisch im kompilierten Code reproduziert, heute kein produktiver Frische-Skip ausgelöst.

- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java:151–160`: Ist der Katalogvermerk jünger als das Zeitfenster, setzt die Methode `katalogUebersprungen=true`, `job.fertig(letzterLoad)` und kehrt vor der gesamten Downloadkaskade zurück.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/client_updates.py:218–220`: Scanner fordert zugleich `tradelisten=True` an. Der Vertrag in `doc/23_stufe0-client-updates.md:166` fordert Trade-Delta unabhängig vom Katalog-Skip.
- Isolierter Aufruf der tatsächlichen `target/classes/gui/MqlDownloaderGui.class` mit synthetischem 1-Stunden-Vermerk und 72-Stunden-Fenster: `state=done`, null neue/aktualisierte Tradelisten, kein Zugriff auf die bewusst uninitialisierten Download-/Konvertierungsmanager. GUI-Konstruktor wurde nicht ausgeführt.
- Nachweise: `downloads_MqlFreshnessProof.java`, `downloads_mql_freshness_runtime.txt` (Exitcode 0). Die aktuelle produktive Vermerkdatei stammt vom 11.10.2026; der Test belegt den Fehlerpfad, keine neue Aktualisierung dieses Tages.
- Wirkung: Nach erfolgreichem Gesamtdownload können nachfolgende tägliche Stufe-0-Läufe innerhalb 72 Stunden neue MQL-Trades überspringen und dennoch sauber fertig melden.
- Korrekturrichtung: Katalogfrische und Trade-Aktualisierung trennen oder den Gesamt-Skip bei angeforderten Tradelisten unterbinden.

### D2: Vantage-Altbestand ist gesperrt; der normale Updatepfad kann ihn nicht erneuern

Priorität: P1; aktueller Bestandsblocker plus isolierte Reproduktion. Die Ablehnung unbelegter UTC-Zeitstempel ist fachlich richtig.

- Live: vier konkrete GETs `/providers/{id}/vantage/trades.csv` für 1419494, 1286742, 1010186 und 1096166 liefern HTTP 404. Die API ist erreichbar; passende lokale CSVs und Metavermerke existieren.
- Bestandsinventar: sämtliche 199 aktuellen Katalog-IDs haben CSV und `version=1`-Vermerk ohne `timeBasis=UTC`. Gesamter lokaler TradeStore: 611 solche Metavermerke; kein version-2-/UTC-Vermerk.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:129`: `mergeHistory` verweigert jeden bereits vorhandenen, unbestätigten Bestand. `saveTrades` ruft dieselbe Sperre auf Zeile 85 erneut auf. `verifiziert` verlangt version 2 und UTC (Zeilen 345–349).
- Normaler Stufe-0-Pfad: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:390–391` bindet `vereinigeArchiv` direkt an `tradeStore.mergeHistory`; `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/update/UpdateJobRunner.java:205` ruft dies nach dem frischen Download und vor Speicherung auf. Auch ein neuer gültiger Download löst daher den bestehenden Block nicht.
- Synthetische version-1-Historie gegen die tatsächlich kompilierte TradeStore-Klasse: sowohl `mergeHistory` als auch `saveTrades` mit gültigen neuen Datensätzen werfen `Vorhandene Historie nicht verifiziert; kein stilles Ueberschreiben`. Originaldatei bleibt unverändert.
- Nachweise: `downloads_vantage_metadata.json`, `downloads_e2e_live.json`, `downloads_VantageRefreshProof.java`, `downloads_vantage_freshness_runtime.txt` (Exitcode 0).
- Korrekturrichtung: Kontrollierte Archivierung/Quarantäne und separate neue UTC-Historie oder belegte Migration ermöglichen; UTC-Schutz und Bewahrung der alten Daten erhalten. Keine automatische Änderung am Produktivbestand vorgenommen.

### D3: Zulu-Hinweis zur historischen Vollständigkeit geht beim Mapping verloren

Priorität: P2; tatsächliche Liveantwort und produktives Mapping verglichen.

- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor/src/main/java/de/zulumonitor/rest/RestApiServer.java:418` liefert den erklärenden Text unter `TradesCompletenessNote`.
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py:408` liest ausschließlich `CompletenessNote` nach `quelle_trades_completeness_note`. `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/alle_signale_ui.py:159–161` kann folglich keinen Quellenhinweis anzeigen.
- Konkreter Livefall 430306: 1164 gespeicherte Trades, Plattformgesamtwert 8992, `TradesTruncated=true`; der Zulu-Text erklärt, dass der kleinere Cache gekappt ODER älter sein kann und auch Zahlengleichheit keine vollständige Historie beweist. `metrics_zu_stats` liefert dafür einen leeren Hinweistext. Die Kappungsflagge selbst wird durchgereicht.
- Nachweis: `downloads_e2e_live.json`, Quelle `zulu`, Signal 430306: `completeness.TradesCompletenessNote` vorhanden, `mapped_completeness_note` leer.
- Korrekturrichtung: Feldvertrag vereinheitlichen oder beide belegten Namen beim Ingest unterstützen.

## Erfolgreich überprüft

- Alle fünf lokalen APIs erreichbar. Zum Prüfzeitpunkt melden alle `/update/status` nur `idle`; ein gerade erfolgreich ausgeführter Download ist damit nicht belegt.
- Pagination mit Limit 73 über alle vorhandenen Seiten: MQL 216, Pelican 640, Robo 200, Vantage 199, Zulu 200, jeweils exakt `total` und ohne doppelte (ID,Version)-Identitäten.
- MQL `health.providers=236` ist korrekt durch 20 Anbieter ohne Abonnenten erklärbar: `/providers?minSubscribers=0` liefert 236, Standardfilter >=1 liefert 216 (`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/rest/RestApiServer.java:885–887`).
- MQL 216 Livezeilen versus 215 Scanner-Katalogzeilen: Der einzige zusätzliche Liveeintrag ist `signalId=test_1,version=mql4`. Scanner verwirft diese nichtnumerische ID korrekt. Keine hier beobachtete MT4-/MT5-Kollision. Nachweis: `downloads_catalogue_identity.json`.
- 17 konkrete Trade-GETs, davon 13 HTTP-200-CSV-Lieferungen und vier Vantage-404. Alle 13 gelieferten CSVs wurden ausschließlich im RAM mit dem produktiven `parser.load_export` erfolgreich geprüft. Ergebnisse enthalten Format, Anzahl, Zeitraum, Netto und Hash; keine Rohtrades persistiert. MQL-Signal 2379208 hat JPY-Kontowährung: sein Netto ist JPY und kein USD-Betrag.
- Mehrere Scanner-Caches sind gegenüber der lokalen Quellen-API älter, bleiben aber SHA-intern korrekt. Beispiele: Pelican 2014074 live 15599 gegenüber Cache 15340 Trades, Robo 21596244 live 38 gegenüber Cache 20, Zulu 402995 live 5725 gegenüber Cache 5717. Das allein beweist keinen Cache-Codefehler: Es wurde kein neuer produktiver Scan durchgeführt.
- Deployte UpdateJob-Klassen aller fünf Projekte enthalten die Teilfehler-/Abbruchfelder; Hash und Zeitstempel in `downloads_deployed_classes.json`. Laufende Java-Prozesse gehören zu den fünf Projektpfaden. Ein idle-Status belegt nicht, wie ein neuer Job diese Felder befüllt; deshalb keine vollständige Live-Abnahme des Updatevertrags behauptet.

## Bestehende Tests

Ausgeführt am 18.10.2026:

```powershell
python -m pytest tests/test_client_updates.py tests/test_downloader_client.py tests/test_quellen.py tests/test_quellen_stringzahlen.py tests/test_stufe0_ui.py tests/test_gesamt_review_hub_fixes.py -q -p no:cacheprovider
```

Ergebnis: **136 passed in 82.49s**, Exitcode **0**. Aktuelle Ausgabe und exakter Befehl: `downloads_tests.txt`. Diese Tests isolieren Speicher und Netzwerk über `tests/conftest.py`; sie belegen keinen neuen produktiven Download.

## Reproduktion der lesenden GET-Prüfungen

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/downloads_probe.py
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/downloads_e2e_probe.py PFAD_ZUM_SCANNER_SNAPSHOT
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/downloads_catalogue_identity.py PFAD_ZUM_SCANNER_SNAPSHOT
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/downloads_vantage_inventory.py
```

Java-Reproduktionen mit den vorhandenen kompilierten Klassen:

```powershell
$auditEvidence = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise'
$auditMqlCp = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/classes;D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
New-Item -ItemType Directory -Force -Path "$auditEvidence/downloads_mql_sandbox" | Out-Null
javac -cp $auditMqlCp -d "$auditEvidence/downloads_mql_sandbox" "$auditEvidence/downloads_MqlFreshnessProof.java"
Push-Location "$auditEvidence/downloads_mql_sandbox"
java '-Djava.awt.headless=true' -cp ".;$auditMqlCp" downloads_MqlFreshnessProof
Pop-Location

$auditVantageCp = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/target/classes'
javac -cp $auditVantageCp -d $auditEvidence "$auditEvidence/downloads_VantageRefreshProof.java"
Push-Location $auditEvidence
java -cp ".;$auditVantageCp" downloads_VantageRefreshProof
Pop-Location
```

Beide Dateien erzeugen ausschließlich synthetische Fixtures unter dem Nachweisverzeichnis. Keine Hauptklasse einer App und keine Netzwerkfunktion wird aufgerufen. Kompilierte Testklassen und erzeugte Fixtures wurden nach erfolgreichem Nachweis wieder entfernt; Quellen und Textausgaben bleiben erhalten.

Grenzen: Kein neuer Voll-/Teilscan, keine MQL5-Webabfrage, kein externer Provider-Download und kein Stufe-0-POST ausgeführt. Die Quellen-Metadaten belegen vorhandene lokale Bestände; eine vollständige aktuelle Lebenszeithistorie wird daraus nicht abgeleitet.
