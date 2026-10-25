# Tradeserver v2: Umsetzung und produktives Update

**Aktueller Zwischenstand:** Der letzte vollständig übernommene
Remote-Snapshot ist Run 13 vom 18.10.2026, 20:36:58 MESZ mit 199
eindeutigen Quellen-UID/ID-Paaren und null aktuellen PDFs. `v2_active=true`;
32 alte Signalzeilen und 313 alte PDFs bleiben unverändert in den Legacy-
Originaltabellen erhalten. Die folgenden Deploymentabschnitte beschreiben
ihre damaligen Zustände; eine erneute finale Veröffentlichung und Remote-
Abnahme nach Quellen-/Studien-/Berichtsabschluss stehen noch aus.
[Separate Run-13-Prüfung](server_v2_run13_checkpoint.json): kein offener Lauf,
lokaler und entfernter Besitzerhash identisch, unveränderte finale WAR.

Der abschließende Scanner-Volltest einschließlich Transport-Restorefix ist
ebenfalls grün: **2.803 bestanden, ein Windows-Symlinkskip, vier LLM-Tests
abgewählt**, 1.115,30 Sekunden, Exit 0. 112 Produktionsdateien und 190
Testdateien blieben vor/nach dem Lauf hashgleich; gebündelte Python-Laufzeit
3.12.14, Pakete und Modulpfade stimmen überein.
[Aktueller Code-Abnahmebeleg](scanner_final_transport_bundled_summary.json).
Die älteren Testzahlen unten gehören zu ihren jeweiligen damaligen Ständen.

Stand: 18.10.2026, Abschlussprüfung nach Deployment. Der Java-Server unterstützt
jetzt das Quellenpaar `(sourceUid, signalId)`, qualifizierte Dokumentbesitzer,
Run-ID/API-Key-Bindung sowie atomare v2-Snapshots bis `complete`. Ein `abort`,
Serverneustart oder fehlgeschlagener Commit erhält den vorherigen Bestand.
V1 bleibt vor dem ersten v2-Commit kompatibel; danach werden v1-Schreibzugriffe
abgewiesen. Browserdialoge/Dokumentfilter verwechseln gleiche Anbieter-IDs nicht.
Der vollständige Wire-Vertrag steht im Serverrepo unter
`Doku/MqlKiScanner_Integration.md`.

Abnahme: komplette `mvn -q test`-Suite mit JDK21, Java17-Ziel: **70 bestanden,
0 Fehler, 0 übersprungen**. Davon15 bestehende Protokolltests,8 neue v2-Tests,
2 echte H2-Migrationsfälle. Tests umfassen doppelte externe IDs, Rename,
Dokumentbesitzer, manipulierte Hashes, fremde Run/API-Keys, Abbruch, absichtlich
fehlschlagenden DB-Commit mit Rollback und Copy-Rollback in der zweiten Tabelle.

Das produktive Update auf Contabo ist ausgeführt: WildFly aktiv,
`ROOT.war.deployed`, externe HTTP-Prüfung200. Vorher wurden die bisherige WAR
und die geschlossene produktive H2 nach bestätigtem Ende aller Dateizugriffe
konsistent gesichert und beide Kopien per SHA256 verglichen. Sicherungen bleiben
privat auf dem Server; Pfad und Hashes stehen in `server_deployment.json`.

Produktive Copy-Migration zusätzlich nurlesend geprüft: **32 Signale und313
PDFs**, alle ursprünglichen Spaltenwerte einschließlich interner IDs erhalten,
PDF-Bytes per SHA256 verglichen, **0 Abweichungen**. Die alten Tabellen bleiben
unverändert. Die kopierten Besitzer sind ausdrücklich `legacy:v1`, keine heute
geratene Quelle. H2-Identity-Sequenzen sind vor der Copy-Transaktion auf
`max(alt.id)+1` vorbereitet. `migrated=true`, beim Abschluss dieser Prüfung
`v2_active=false`: der erste echte Scanner-v2-Sync steht noch aus.

Bis zu diesem Deploymentstand war noch kein produktiver Scanner-Register-/PDF-Upload
vorgenommen worden. Der anschließend ausdrücklich autorisierte echte Sync ist
im aktuellen Abschlussblock unten separat belegt. Keine Commits/Pushs. Rohlogs mit privaten Laufzeit- oder Zugangsdaten sind
kein Bestandteil dieser Belege. Quellhashes und Testklassen stehen in
`server_tests_manifest.json`.


## Zweite Abnahme: Jahres-Calmar und Anzeige

Die anschließende unabhängige Wire-Prüfung fand einen bestehenden Anzeigefehler:
Python sendete `minCalmarJahr`, Java ignorierte das Feld und die Hauptspalte
färbte Monats-RetDD gegen eine alte Monatsschwelle. Mit Root-Freigabe korrigiert:
`minCalmarJahr`, `retddJahrVorbehalt`, `retddVorbehaltGrund` und
`equityMeasurementStatus` werden übertragen/persistiert. Hauptspalte und
Rohwertvergleich verwenden Jahres-Calmar; Vorbehaltswerte bleiben orange mit
`≈`. Fehlende historische Schwellen bleiben unbekannt/neutral. Eine übertragene
DD-Grenze50 wird ohne feste30-Begrenzung angezeigt. Die Scanner-Ampel und
Berechnung bleiben unverändert.

Vollständige zweite Serversuite: **73 bestanden,0 Fehler,0 übersprungen**.
Zusätzliche Tests belegen Jahres-Rohpräzision, Monatswert als Zusatz,
Vorbehaltsstatus, unbekannte Alt-Schwellen und50-Prozent-DD-Anzeige. Finale
WAR: `89d081fc1190d41589e6a3c6a5548e051715fe4417c1de9e989882ed1e3e2615`.

Zweites produktives Update mit erneut konsistenter Sicherung abgeschlossen;
Beleg `server_deployment_calmar.json`. Erste Deployment-Evidenz bleibt unter
`server_deployment_identity.json`, erste Testhashes unter
`server_tests_manifest_identity.json` erhalten. Nach zweitem Update wieder
32 Signale/313 PDFs ohne ursprüngliche Wertabweichung; neue Calmarspalten
vorhanden, keine historische Schwelle oder Vorbehaltszahl erfunden.
WildFlyaktiv, Deploymentmarker vorhanden, externeHTTP200. Die aktuellen
Quellhashes und73Tests stehen in `server_tests_manifest.json`.

Bei dieser Abschlussprüfung stand weiterhin `v2_active=false`; Root übernimmt
den folgenden echten Scanner-v2-Sync und dessen separaten Ping-/Sync-Beleg
(siehe aktueller Abschlussblock). Bis zu jenem Deploymentstand war kein
Server-Agenten-Register/Upload erfolgt.


## Aktueller echter v2-Sync:18.10.2026,19:33MESZ

Der ausdrückliche Folgeauftrag hat den ersten echten Scanner-v2-Sync ausgeführt.
Lauf11 übertrug194Zeilen und47PDFs. Die kritische echte Abnahme fand dabei
47alte Tiefenanalysen ohne aktuelle Berichtsgrundlage: lokale historische Texte
blieben bei fehlender vollständiger Forensik absichtlich sichtbar, wurden aber
von der Exportgrenze unzulässig als aktuelle eigene PDFs übernommen.

Mit Root-Freigabe gezielt korrigiert: eigene Berichte einschließlich Tiefenanalyse,
Dokumentzähler, Berichtsdatum und positive Kurzfassung werden nur bei aktueller
`berichte_basis`, vollständiger fehlerfreier und nicht veralteter Forensik
exportiert. Die lokale historische Anzeige bleibt erhalten; separat nach Quelle
zugeordnete Downloader-Originale bleiben spiegelbar. Bestehende UID-Goldentests
haben explizite aktuelle Beleg-Fixtures;7neue Regressionfälle prüfen die Grenze.
Abnahme Client/Sync/v2 plus neue Fälle: **50bestanden**, keine Fehler.

Der sofortige Resync Lauf12 wurde um19:33:18MESZ erfolgreich abgeschlossen:
**194eindeutige Quellen-UID/Anbieter-ID-Paare,0aktuelle PDFs**, keine offenen
Serverläufe, `v2_active=true`. Damit sind die47ungebundenen PDFs aus dem aktiven
Snapshot atomar entfernt. Originaltabellen:32Signale und313PDFs mit identischen
Wert-/BLOB-Tabellenhashes gegenüber der konsistenten Offline-Sicherung. Der
Besitzerpaarhash entspricht exakt dem lokalen Scannerbestand.

Dieser Zwischenstand enthält1grüne,77rote,98weiße und18ausgeschlossene Zeilen.
Kein Grün ohne gemessenen Jahres-Calmar; konfigurierte Jahres-Schwelle3 und
DD-Grenze50 korrekt übernommen.0aktuelle PDFs ist ausdrücklich kein Nachweis
neu erstellter Berichte; der Snapshot hat derzeit keine passenden eigenen
Neuberichte. Nichtleere PDF-Zuordnung wird in Integrationstests belegt, nicht
als im leeren aktuellen PDF-Bestand produktiv gemessen behauptet.

Belege: `server_v2_live_sync.json`, `server_v2_first_sync.json`,
`server_current_report_guard_tests.xml`. Backend-WAR weiterhin
`89d081fc1190d41589e6a3c6a5548e051715fe4417c1de9e989882ed1e3e2615`.
Root hat Streamlit um19:34 mit dem neuen Exportguard neu gestartet. Quellenupdates
und weitere neue Berechnungen laufen gesondert weiter; deren Ergebnisse brauchen
anschließend einen erneuten Sync. Dieser technische Sync ist kein behaupteter
Gesamtdatenabschluss. Keine Commits/Pushs.

## Scanner-UI, H1-Optimierung und vollständiger Laufzeitnachweis

Quellqualifizierte Fix-Labels, der aktuelle belastbare Workflow-DD in USD
und die orange Darstellung der tatsächlich befüllten ≈-Zelle sind korrigiert.
Nach dem gebündelten Scanner-Neustart wurden die Anzeigen mit CUA rein lesend
geprüft; DD-Prozent und Jahres-Calmar blieben unverändert. Streamlits native
graue `None`-Darstellung numerischer Lücken bleibt bestehen. Ein unwirksamer
neuer Styler-Platzhalterversuch wurde zurückgenommen; keine Finanzspalte
wurde in Text umgewandelt. Beleg: `server_ui_h1_fixes.json`.

Historische H1-Innenlücken werden nur zwischen vorhandenen finalen H1-Bars
desselben Feeds/Symbols in höchstens 31 Tage breite SDK-Fenster gebündelt.
Gespeichert werden ausschließlich die ursprünglich fehlenden Teilbereiche;
Brückenbars werden nicht überschrieben. Ränder und provisorische Bars bleiben
einzeln, TTLs und fehlende Abdeckungsbelege unverändert. Die tatsächliche
Laufzeitverbesserung des produktiven Gesamtscans wird separat beurteilt.

Nach 352 gezielten bestandenen Tests lief die vollständige Suite mit dem nun
produktiven gebündelten Python 3.12.14 und identischen User-Site-Paketen:
**2.784 bestanden, ein Windows-Symlink-Skip, vier LLM-Tests abgewählt**,
Exit 0, 856,81 Sekunden. **112 erfasste Produktivdateien blieben identisch**,
ebenso Laufzeit, Paketversionen und geladene Modulpfade. Die alten 2.760er-
und 352er-Nachweise bleiben separat erhalten und werden nicht addiert.
Belege: `scanner_final_bundled_full.xml`,
`scanner_final_bundled_hash_comparison.json`,
`scanner_final_bundled_runtime_comparison.json`.

Diese Softwareabnahme ist keine Freigabe aller aktuellen Quellenhistorien,
Studien oder KI-Berichte und löst keinen weiteren Tradeserver-Sync aus.
