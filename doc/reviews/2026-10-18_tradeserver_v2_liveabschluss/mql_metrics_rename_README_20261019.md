# MQL-Quellenabschluss und Dateifamilienbindung, 19.10.2026

Der exakte Quellenjob `u-35579920-eb3d-4db4-83ef-ae6a24b934c9` endete
am 18.10. um 21:37:56 MESZ regulär: MT4 92 Exporte auf zwei Seiten,
MT5 176 auf vier Seiten, keine gemeldeten Downloadfehler. Bei der
Fortsetzung war die alte JVM bereits beendet und Port 8089 offline.
Der gespeicherte reine API-Beobachter, beide nativen Abschlussjournale
und alle 268 erfolgreichen CSV-/HTML-/Metrics-Dateifamilien wurden
deshalb vor dem Start einer neuen Instanz geprüft. 3.084 Quell-Dateien
einschließlich Konfiguration und Datenbanken liegen zusätzlich in einer
vollständig hashgeprüften privaten Offline-Sicherung.

Die zunächst aktivierte 163-Test-Fassung schloss die vier erhaltenen
historischen Navigations-/Testkennungen an der öffentlichen API aus.
Die anschließende vollständige GET-Abnahme fand einen weiteren Fehler:
Bei Signalumbenennungen wählte `ProviderFiles.resolveRootTxt` die
Kennzahlen unabhängig von der gewählten Trade-CSV nach Änderungszeit.
Die Sammelkonvertierung hatte auch alte HTML-Profile erneut verarbeitet;
deren später geschriebene TXT-Dateien konnten dadurch gewinnen.

Betroffen waren genau zwei der 268 erfolgreichen Generationen:

- MT5 2360068: aktuelle Familie `Harmonizer_Extreme`, ausgelieferte alte
  Kennzahlenfamilie `Recovery2360068`.
- MT5 1059619: aktuelle Familie `Tharos_II`, ausgelieferte alte
  Kennzahlenfamilie `Tharos_II_LiquidityMinerEA`.

Der Resolver bindet Kennzahlen nun an das exakte `*_root.txt`-Gegenstück
der tatsächlich gewählten regulären oder belegten Archiv-CSV. Ein
fehlendes Gegenstück liefert 404; ältere umbenannte Familien ersetzen es
nicht. Reiner Metadatenzugriff ohne vorhandene Trade-CSV bleibt möglich.
Die Originaldateien wurden weder geändert noch gelöscht. Drei neue
Unit-/HTTP-Regressionen scheitern gegen die Vorversion und bestehen mit
der Korrektur. Der isolierte Clean-Paketbau bestand mit **166 Tests,
null Fehlern und null Skips**. Build, Quellhashes und Testprotokolle sind
in `mql_metrics_rename_build_20261019.json` und `mql_metrics_rename_TEST-*.xml`
gebunden.

Die zweite Aktivierung erfolgte ausschließlich bei API-Status `idle`,
ohne Download-/Konvertierungsstacks, über normalen Fensterabschluss,
bestätigtes Prozess-/Portende und erneute Offline-Sicherung der aktuellen
Datenbank-/Konfigurationsdateien. Das neue Paket läuft als PID 54788 mit
SHA-256 `52c22f3ea025da5d3726726d2f0358277b8180ecaea7ac29aee36dc9c4d793d2`.
Kein aktives JAR oder `target/classes` wurde während eines Laufs gebaut
oder überschrieben. Es gab keinen neuen Update-POST.

Die abschließende API-Abnahme prüfte alle 268 erfolgreichen CSVs gegen
ihre vor Aktivierung gesicherten Bytes sowie alle 268 frischen Metrics
gegen die passende CSV-Dateifamilie. Provider-JSON/-CSV, Health,
Zusammenfassung, Events und Dateikatalog sind auf zulässige Identitäten
geprüft; direkte Zugriffe auf die vier Altkennungen ergeben 404. Der
vollständige lokal angebotene Katalog umfasst 372 eindeutige
Plattform-/ID-Paare. Davon liegen 104 außerhalb des nachgewiesenen
268er-Updates. Es wird keine Vollständigkeit der ursprünglichen
Handelsplattform und keine Frische dieser 104 Altzeilen behauptet.

Der ursprüngliche Scannerparser wies eine der 268 Dateien wegen 38
`Deal Interestrate`-Zeilen ab. Dieser damalige Befund bleibt erhalten;
die spätere Parserkorrektur und vollständige Nachprüfung des Hauptagenten
sind separat über `mql_source_acceptance_20261019.json` gebunden. Die
Quellbeträge bleiben nativ: 208 der 268 Konten sind als USD ausgewiesen,
60 tragen andere Einheiten. Die bestehenden Währungsprüfungen bleiben
verbindlich. Quellenabschluss, Scannerneuberechnung, Studien, Berichte
und Tradeserver-Sync sind getrennte Arbeitsschritte.

Hauptbelege: `mql_source_offline_preservation_20261019.json`,
`mql_api_guard_activation_20261019.json`,
`mql_metrics_rename_activation_20261019.json`,
`mql_corrected_final_verification.json`,
`mql_source_acceptance_20261019.json`.
Private Rohbelege, Backup, expliziter 268er-Umfang und vorbereiteter,
noch nicht geschriebener Chronikpayload liegen unter
`data/runs/liveabschluss_20261019/mql/`.
