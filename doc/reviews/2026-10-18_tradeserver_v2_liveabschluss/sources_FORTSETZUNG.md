# Quellencheckpoint nach ausdruecklicher Nutzerpause

**Keine automatische Fortsetzung. Kein 09-Uhr-Termin. Erst nach einer neuen
ausdruecklichen Nutzeranweisung weiterarbeiten.** Keine weiteren Quellen-POSTs,
GUI-Neustarts, Folgeprovider, Scanner-/Studien-/KI-Laeufe oder Builds starten.
Die bereits laufenden nativen Downloads duerfen regulaer fertigwerden.

Maschinenlesbarer Stand: `sources_pause_checkpoint.json`. Die enge Beendigung
nur des eigenen Python-Koordinators ist gesondert und wahrheitsgetreu in
`sources_robo_user_pause_receipt.json` dokumentiert. Keine Finanzdaten wurden
dadurch abgebrochen oder veraendert.

## Robo

- Der alte 200er-Job `u-e55d8f83-aa56-415a-8aea-e06342aaef32` endete 20:34:17
  MESZ teilweise: 180 frische Historien, 17 defekte Altduplikat-Caches, 3 RStocks.
  Originale/Abschluss bleiben erhalten. Chronik:Startzeile 51 und Teilabschluss 66.
- Alter Java-PID 1351408 ist regulaer beendet. Offlinebackup mit 1.471 Dateien,
 1.197 Cache-Hashes vor/nach Exit und im Backup gleich, SQLite integrity=ok;
  `sources_robo_initial_exit_backup.json`.
- Getesteter neuer Code: 195 Tests, isolierte **nun aktive, unveraenderliche**
  Stage `.tmp/source_staged_builds/robo_native_units_20261018T1835/`.
  JAR-SHA256 `47fa66fc692b3d92f49ffeb1c194ffd31f1607e52ac9589ab075c7b44ad6a0e1`.
  Laufende CLIs verwenden die dortigen Klassen plus bisherige Dependency-JARs;
  nicht auf diesen Pfad bauen/kompilieren. Klassenmanifest privat unter
  `.tmp/source_maintenance/robo_native_units_stage.json`.
- Sechs von 17 gezielten Vollerneuerungen waren beim Pausieren fertig und
  verifiziert. Die genauen IDs/SHAs/Count-/Archivbelege stehen in
  `sources_robo_repair_progress.json` und im Checkpoint.
- Der reine Nichtwriter-Koordinator 1764128 wurde nach exakter PID-,
  CreateTime-, Commandline- und `py-spy`-Pruefung des `subprocess._wait` gezielt
  beendet. CIM rundet die CreateTime auf Mikrosekunden; der native Startwert
  hat zusaetzlich zwei 100-ns-Ticks. Es gab kein Konsolen-/Nachkommen-Signal.
- Die beim tatsaechlichen Stopp laufende Java-CLI ist **1771524**, Provider
  **37232470**. Identitaet blieb erhalten, das Log wuchs nach dem Stopp weiter.
  Die zuvor genannte CLI 1783464 war bereits regulaer fertig geworden.
  Aktueller Writer darf enden; danach entstehen keine weiteren Provider-JVMs
  und keine automatische GUI. REST8091 bleibt offline.
- Endbeleg des aktuellen Writers: `.tmp/sources_robo_repair_37232470.log`
  und `../roboforex/data/deals/deals_37232470.csv/.meta`. Prozessabwesenheit
  allein belegt keinen Erfolg: API-Ende/Abschlusslog, SHA, Count, eindeutige IDs,
  Besitzer/Plattform und quarantinierte Originalbytes morgen kontrollieren.
- Danach sind noch zehn bisher ungestartete IDs uebrig, sofern der aktuelle
  Writer erfolgreich endet. Die exakte Liste steht im Checkpoint.
- **Den alten Koordinator nicht unveraendert erneut starten:** Er ist an
  den alten PID/API-Job gebunden und wuerde bereits reparierte Provider erneut
  bearbeiten. Ausgangsfehler und alte Hashes ausschliesslich aus dem
  eingefrorenen `sources_robo_initial_failures_final.json` verwenden.

Nach Nutzerfreigabe: aktuellen Writer-Endbeleg pruefen, nur verbleibende IDs
erneuern, dann normalen neuen GUI-/REST-Start mit unveraenderten Settings
aus der geprueften Stage und native/REST-Abnahme.
`sources_readonly/verify_robo_current.py` ist vorbereitet, noch nicht auf
eine neue produktive API angewendet. Der Einheitenvertrag bleibt unabhaengig
vom Download korrekt gesperrt: keine belegte native Kontowaehrung/Volumeneinheit,
keine Scanner-CSV/Closing-DD-Freigabe. Details `sources_robo_units_README.md`.
Scanner-Alturteile muessen vom Hauptauftrag gesondert nachgeprueft werden.

## Vantage

Die fuenf FT-Provider 178177, 1231244, 504191, 692325 und 762452 sind vollstaendig
erneuert und exakt per REST geprueft. Der GET-only-Listener **1670220** auf 8092
bleibt bestehen, ohne GUI oder UpdateStarter. POST /update ist 405.
Stopdatei nur bei spaeterem beabsichtigten regulaeren Ende:
`.tmp/sources_vantage_readonly.stop`.

Die Vollreparatur der weiteren 14 Provider laeuft als **Java 1580932** weiter. Keine Signale,
kein Abbruch, kein neuer Build auf target/classes/JARs. Aktuelle Logs:
`.tmp/sources_vantage_other_record_identity.log`. Der bereits gestartete
PowerShell-Rahmen schreibt nach Batchende
`sources_vantage_other_record_identity_exit.json`; es gibt keine automatische
GUI- oder Update-Folgephase. FT-Endbeleg:
`sources_vantage_ft_record_identity_exit.json`.

Erst nach Nutzerfreigabe: beide exakten Endbelege pruefen, dann
`sources_readonly/verify_vantage_full_scope_native.py` fuer alle19 Provider ausfuehren.
Danach GET-only-REST-Abnahme der 19 Provider, regulares Ende des temporaeren Listeners
und bestaetigten freien Port 8092 pruefen, normalen GUI-/REST-Start und
regulaeren Quellenupdatejob starten. **Kein force0-Katalogabruf:** Der echte
Marker 16:53:07 UTC ist frisch. 15 der 19 Workflowprovider waren im alten
Top-200-Katalog nicht enthalten; der lokale Katalog wird deshalb 215 umfassen.
Ein erzwungener neuer Top-200-Katalog wuerde sie wieder unsichtbar machen.
Der normale 72-h-Scope muss als 215 und nicht pauschal als 200 dokumentiert werden.

## Ueberblick und andere Quellen

Der bereits laufende reine GET-/Dateibeobachter **1773324** schreibt
`sources_current_progress.json`. Das ist keine KI, keine neue Aktualisierung
und keine Wiederaufnahme. Er startet keine Folgejobs. Stopdatei:
`.tmp/sources_current_progress.stop`.

MQL/Zulu liegen bei `/root/kontrakte_fx_abschluss`, Pelican beim Hauptauftrag.
Deren genauen Stand aus dem uebergeordneten `FORTSETZUNG.json` und den eigenen
Quellenreceipts lesen. Keine Quelle aufgrund alter Fehler-/Teilerfolgsjobs
als fertig melden. Es gibt keinen automatischen Termin und keine Automation.
