# MQL-Paginierung: Live-Gegenprüfung und Folgekorrektur

Stand: 18.10.2026, neuer korrigierter Build seit 20:33:01 MESZ aktiv,
neuer Job noch in produktiver Prüfung. Der Altjob
`u-559dfc47-4a38-4426-b51d-59adf5ffb5db` ist **nur ein Teilstand**;
sein API-Ergebnis `done`, 96 aktualisiert und null Downloadfehler ist kein
Nachweis einer vollständigen Discovery.

## Historischer erster Korrekturversuch

Der erste Build mit 153 Tests war für den Job ab 20:04:14 MESZ unter PID
1629024 produktiv aktiviert. Er erhielt `orderby=subscribers` auf Folgeseiten,
bildete aber den falschen Pfad `/mt4/page2` beziehungsweise `/mt5/page2`.
Die damalige Fixture bestätigte einen angenommenen URL-Vertrag, nicht den
tatsächlichen Paginator der Website. `root_mql_pagination_build.json`
dokumentiert diesen historischen Stand.

Die aktive Instanz besuchte die falsche Folge-URL. Sie exportierte jeweils
48 Provider unter MT4 und MT5 und beendete beide Plattformen mit der
irreführenden Meldung `BENUTZER-STOPP`, ohne entsprechenden Benutzerabbruch.
Der Job endete um 20:29:52 MESZ. Der API-Rohabschluss bleibt in
`mql_pagination_unaccepted_terminal.json` erhalten; die Scanner-Chronik
enthält dafür einmalig `teilweise`, Zeile 64, statt eines Erfolgsabschlusses
(`mql_pagination_stufe0_receipt.json`).

## Tatsächlicher Website-Vertrag

Zwei behutsame, autorisierte Abrufe mit bestehender Sitzung und 20 Sekunden
Abstand belegen den ursprünglichen Paginator. Die erste MT4-Tabellenseite
verlinkt auf `/en/signals/mt4/list/page2?orderby=subscribers`. Genau diese
Folge-URL lieferte HTTP 200, 48 numerische Provider-IDs, davon **44 mit
positiver Abonnentenzahl und vier mit expliziter Null**. Keine Zahl war
unbekannt. Der Altjob ließ damit mindestens 44 weitere abonnierte
MT4-Provider aus.

Belege: `mql_pagination_dom_first.json` und
`mql_pagination_dom_original_page2.json`. Vollständige HTML-Seiten liegen
wegen enthaltenen Sitzungs-/Kontomarkups ausschließlich privat unter
`data/runs/liveabschluss_20261018/mql_dom_probe/`; Cookies wurden nicht
protokolliert oder veröffentlicht.

Die falsche MT5-Folgeseite war keine nachgewiesene HTTP-404-Seite. Eine
passive DOM-Abfrage der bereits geöffneten Browserseite belegt eine
Kachelansicht mit 48 numerischen Providerlinks, aber ohne die vom alten
Tabellenparser erwarteten `.signal`-Zeilen. Ein HTTP-Status wurde dabei
nicht gemessen. Der breite Link-Fallback konnte Navigation als Provider
ansehen und fehlende Abonnentendaten als Null interpretieren
(`mql_pagination_wrong_mt5_page2_dom.json`).

## Korrigierter Quellstand und Regressionen

`MqlDownloader/src/downloader/SignalDownloader.java` verwendet jetzt auf
allen Seiten den belegten Tabellenpfad `/list/pageN` und erhält Sortierung
sowie kodierte Filter. Nur positive numerische Signal-IDs auf dem exakten
MQL5-Host gelten als Provider; Navigation und doppelte Links werden verworfen.
Unbekannte Abonnentenzahlen bleiben unbekannt. Der Client wartet auf den
Wert und meldet bei fehlendem Nachweis einen Fehler, statt daraus eine Null
oder einen Benutzerabbruch abzuleiten. Vor Verwendung der Null-Grenze prüft
er die absteigende Abonnentensortierung. Eine ausdrücklich erreichte
Abonnentengrenze bekommt einen eigenen Abschlussgrund. Die Seitenstatistik
verwendet die tatsächlich erkannten Provider statt einer festen Null.

Die Auswahlgrenze und Bewertungsregeln wurden nicht gelockert.
`mvn -q test` bestand mit **159 Tests, null Fehlern und null Skips**.
Die sieben Paginationstests prüfen unter anderem den realen Tabellenpfad,
mehrere Seiten, Navigationslinks, verzögerte/unbekannte Zahlen, Zahlenformate
und eine ungültige Null vor einem späteren positiven Wert. Dieser Prüfschritt
führte ausdrücklich kein Packaging und keinen Dienstneustart aus.

Testnachweise und Quellhashes: `mql_pagination_final_tests_summary.json`,
`mql_pagination_final_tests.log` und `mql_pagination_final_TEST-*.xml`.
Der kombinierte isolierte Paketbau und seine produktive Aktivierung werden
gesondert durch den Hauptlauf dokumentiert. `root_mql_corrected_live_start.json`
belegt die normale Aktivierung im Leerlauf: PID 1663784, Paket-SHA-256
`f343519189c345cac7ed08e1b01b02485f2477bf80f80eabd0ba47359fc09315`,
159 Tests und funktionierende INFO-Ausgaben. Ein vollständiges Offlinebackup
von Konfiguration, Datenbank und Downloads wurde davor gesichert.
Der neue Job `u-35579920-eb3d-4db4-83ef-ae6a24b934c9` wurde um
20:33:43 MESZ ausgelöst; die API führt `startedAt=20:33:42`.
Er erzwingt Discovery. Seine eigene Beobachtung liegt unter
`mql_corrected_watch_status.json` und `mql_corrected_observations.jsonl`;
die Altbelege bleiben getrennt. Der beobachtete Start ist noch keine Abnahme
der Folgeseiten oder des vollständigen Laufs.

Der neue reale MT4-Lauf erreichte um 20:45:17 MESZ die korrekte
`/list/page2?orderby=subscribers`. Provider 49, ID 1750918, wurde um
20:45:37 erfolgreich exportiert. Seine frische CSV stimmt bytegenau mit
dem REST-Export überein, 2.706 gelieferte CSV-Zeilen. Damit ist die alte
48er-Grenze tatsächlich überschritten; der Gesamtlauf, MT5 und die folgende
Konvertierung sind dadurch noch nicht abgenommen.
Beleg: `mql_corrected_mt4_page2_first_export.json`.

## Davon getrennte Logger- und Paketprobleme

Der Logger-Kontextfix ist in `root_mql_logger_README.md` beschrieben. Er
behebt die fehlende INFO-Konfiguration im Fat-JAR; der zukünftige
Startparameter verwendet zusätzlich eine korrekte `file:///`-URI.

Bei einem früheren Packaging um 20:16 MESZ wurde versehentlich das noch
laufende Fat-JAR überschrieben. Danach dokumentiert das erhaltene
Laufzeit-stderr `NoClassDefFoundError` für `HtmlParser` und
`ProviderAge$Snapshot`; Konvertierung und REST-Zugriff sind damit zusätzlich
betroffen. Das erklärt fehlgeschlagene Abschlussabfragen, widerlegt aber
nicht den unabhängig belegten Paginierungsfehler. Die 96 gemeldeten Updates
werden auch deshalb nicht pauschal als frisch und vollständig übernommen.

Der Ersatzbau erfolgt vollständig isoliert. Aktivierung erst nach belegtem
API-Leerlauf, beendetem Downloadworker und normalem Fensterende; keine
Unterbrechung eines aktiven Writers. Originale Downloadprotokolle und
Fehlerausgaben bleiben erhalten.

## Zusätzlich belegte historische Katalogverschmutzung

Der erneuerte REST-Server liefert die Katalogseiten wieder zuverlässig.
Die vollständige lokale Gegenprüfung fand unter 239 angebotenen Zeilen vier
ungültige Providerkennungen: `test_1`/MT4 und `test_2`/MT5 vom 21.06.2026
sowie `page2` unter MT4 und MT5 aus den fehlerhaften Abschlüssen um 20:17
und 20:29 MESZ. Ihre URLs entsprechen Test-/Navigationsseiten statt
numerischen Signalprofilen. Der aktuelle Downloader verhindert neue solche
Einträge; vorhandene Altzeilen wurden durch ihn nicht gelöscht.
`mql_corrected_catalog_legacy_invalid.json` belegt diese rein lesende
Gegenprüfung. Vor einer fehlerfreien Katalogabnahme müssen diese Altzeilen
in der Ausgabe zuverlässig ausgeschlossen oder ausdrücklich gesichert
bereinigt werden. Es wurde dafür keine Produktionsdatenbank verändert.
Die daraufhin implementierte API-Ausgabesperre erhält sämtliche Rohzeilen
und hat 163 isolierte Tests bestanden; produktive Aktivierung folgt nach
diesem Downloadjob. Details: `mql_api_guard_README.md`.

## Noch erforderliche produktive Abnahme

Ein neuer Wartungslauf muss Discovery ausdrücklich mit
`katalogMaxAlterH=0` erzwingen; dafür werden keine produktiven Einstellungen
geändert. Abnahme benötigt die exakt zugeordnete neue PID und Job-ID,
`/list/page2?orderby=subscribers` im echten Browserlauf sowie erfolgreiche
Providerexporte über die erste Seite hinaus. Katalog, Metrics und CSV werden
anschließend anhand konkreter frischer Generationen und Hashes gegengeprüft.
Erst danach folgen ein Erfolgsabschluss in der Chronik und der mit dem
Hauptlauf abgestimmte Scannerlauf unter dem gemeinsamen Lauf-Lock.
