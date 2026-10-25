# PelicanTrading: neuer normaler Quellenlauf am 19.10.2026

Der reguläre PelicanMonitor wurde nach bestätigtem freien Port 8090 und ohne
laufenden Pelican-Writer aus einer separaten Kopie des vorhandenen geprüften
JARs gestartet. SHA-256 stimmt mit dem Beleg des 181-Test-Builds vom 18.10.
überein; 108 Klassen und die damals geänderten Quelldateien sind hashgleich.
Es wurde kein Paket neu gebaut oder ein aktives Paket überschrieben.
PelicanWinnerLooser wurde nicht gestartet.

Der genau einmal gestartete normale Job
`u-4445cd80-d661-4698-9450-7d24ae92c118` lief von 09:22:23 bis 09:27:44 MESZ:
**200 von 200, 199 aktualisiert, eine verifizierte Leerliste frisch,
null Downloadfehler, kein Abbruch**. Die bestehende 72-Stunden-Katalogfrist
blieb unverändert. Der lokale Katalog enthält 2.190 Provider; 641 haben
Kopierer. Der bestehende normale Top-200-Deckel stellt 441 davon zurück;
1.549 Provider ohne Kopierer bleiben außerhalb des Trade-Downloadumfangs.

Nach Jobende sind alle 200 nativen CSV-/Metadatenpaare einzeln auf SHA,
Zeilenzahl und eindeutige Trade-IDs geprüft. 199 Paare wurden während dieses
exakten Jobs neu publiziert; die Leerliste blieb bytegleich erhalten.
199 REST-Exporte sind verfügbar und haben exakt die native Zeilenzahl.

Eine belegte verbleibende Quellengrenze betrifft Provider **2096343**:
zwei PEPEUSD-Positionen in seiner 687-Zeilen-Historie enthalten Öffnungs-
und Schlusspreis null. Sie standen bereits identisch im Originalbackup vom
18.10. Ein enger neuer authentifizierter Original-GET für die drei betroffenen
Tage bestätigt auch heute beide Nullpreise. Die Hypothese eines erst beim
Speichern entstandenen Rundungsfehlers ist für diese beiden Datensätze damit
widerlegt. Der Export bleibt korrekt mit HTTP 404 gesperrt. Zeilen, PnL und
Originalpreise werden weder entfernt noch erfunden.

Der Quellenjob ist innerhalb seines normalen Umfangs abgeschlossen. Die
Vollständigkeit der Lebenszeithistorien, historische Broker-Kontrakte und eine
belastbare eigene H1-Equitymessung sind dadurch nicht belegt. Unbekannte
aktuelle Renditebasis und Closing-DD werden nicht durch null Prozent ersetzt.
Es wurden keine Scanner-Datenbanken, Scanner-Settings oder Scannerläufe,
Berichte oder Tradeserver-Synchronisationen verändert beziehungsweise gestartet.

Belege:

- `sources_pelican_normal_service_start_20261019.json`
- `sources_pelican_normal_update_start_20261019.json`
- `sources_pelican_normal_update_result_20261019.json`
- `sources_pelican_normal_completion_acceptance_20261019.json`
- `sources_pelican_invalid_positions_20261019.json`

Private Laufprotokolle und Originalbelege liegen unter
`data/runs/liveabschluss_20261019/pelican/`.

## Separater Einzelumfang 2086522

Der außerhalb des normalen Top-200-Umfangs liegende Provider 2086522
(`Range Rocket Long`, USD, zwei Kopierer) war weiterhin im lokalen Katalog
vorhanden. Seine Historie stammte noch vom 27.09. Der bestehende native
Einzelabruf `PelicanMonitorApp.ladeTradeliste` wurde im selben laufenden JVM
verwendet; damit gelten dieselben gemeinsamen Store-Locks wie für REST-Leser.

Der erste Versuch scheiterte an einer abgelaufenen Session. Der bereits im
normalen Job erneuerte Cookie-Dateistand war gültig, der globale CookieManager
aber noch alt. Der Einzelabruf überschrieb vor seinem ersten GET den gültigen
Clientcookie mit diesem alten Manager. Nach Synchronisierung über die
vorhandene native Ladefunktion gelang derselbe Einzelabruf ohne neuen Login:
**359 → 531 eindeutige Trades**, alle ursprünglichen IDs erhalten. CSV und
Metadaten wurden während des gebundenen Einzelabrufs neu publiziert;
der REST-Export umfasst genau 531 Zeilen. Die 4.602 anderen geschlossenen
CSV-/Metadateien sind hashgleich. Der neue Einzelumfang ist getrennt vom
unveränderten ursprünglichen 200er-Job dokumentiert:
`sources_pelican_extra2086522_acceptance_20261019.json`.

## Enger Produktfix für die Sessionübernahme

`ChromeLoginFallback` veröffentlicht nach erfolgreicher vorhandener Prüfung
der geschützten API nun auch den verifizierten CookieManager als globalen
Manager. Dadurch übernimmt der nächste native Einzelabruf dieselbe gültige
Session. Eine nicht verifizierte Kandidatensession verändert weder Manager
noch Persistenz.

Isolierter vollständiger Bau: **183 Tests, 28 Testklassen, keine Fehler oder
Skips**. Der neue Build ist separat gesichert; aktive alte JAR und produktives
`target` wurden beim Bau nicht verändert. Die alten Quellenabschlüsse bleiben
an ihren ursprünglichen Build gebunden.

Der neue Build wurde anschließend im ausdrücklich bestätigten Fenster ohne
Pelican-GETs des Scanners regulär aktiviert: alter Prozess nach belegter
Worker-Abwesenheit über JavaFX beendet, Portende bestätigt, vollständiges
privates Offlinebackup und Integrität aller drei nativen SQLite-Datenbanken
geprüft. Neuer Prozess **13632**, Health auf 8090 erfolgreich, gleiche
Service-/Instanzidentität. Sämtliche **4.604** geschlossenen CSV-/Metadateien
sind bytegleich erhalten; der separate Export von 2086522 hat denselben SHA.
Es wurde kein neuer Quellenjob ausgelöst. Der RAM-Jobstatus ist nach dem
Neustart erwartungsgemäß `idle`; der vorherige Abschlussstatus bleibt im
gesicherten Originalbeleg erhalten. Ein neuer realer Chrome-Login wurde
für diesen Paketwechsel nicht absichtlich provoziert.

Buildbelege: `sources_pelican_session_fix_build_20261019.json`, gleichnamiges
Buildlog und `sources_pelican_session_fix_regression_20261019.xml`.
Die genaue binäre Begrenzung auf eine von 108 Hauptklassen steht in
`sources_pelican_session_fix_binary_comparison_20261019.json`; Aktivierungs-
und Erhaltungsnachweise in `sources_pelican_session_fix_activation_20261019.json`.
