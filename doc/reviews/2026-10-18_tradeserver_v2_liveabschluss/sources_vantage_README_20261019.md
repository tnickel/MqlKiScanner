# Vantage: Fortsetzung am 19.10.2026

Die Fortsetzung wurde ausdrücklich beauftragt. Es wurden keine Scannerläufe,
Scanner-Datenbankänderungen, Commits oder Tradeserver-Synchronisationen ausgelöst.

Die zwei gezielten Vollabrufe vom 18.10. sind beendet: fünf FT-Provider und
14 weitere Provider, jeweils Exit 0. Alle 19 nativen Endgenerationen sind am
19.10. erneut geprüft: CSV-/Meta-SHA, Anzahl, eindeutige positive
`historyRecordId`, UTC und exakter positiver Anbieter-Gesamtcount. Die beiden
nativen Stores stimmen feldweise überein. Frühere Originalgenerationen sind
unverändert in der Quarantäne erhalten.

Der alte temporäre GET-Dienst und sein Listener auf 8092 waren bei der
Fortsetzung bereits beendet. Ein nachträglicher regulärer Exit dieses alten
Prozesses ist nicht belegt. Das eigene Stopfile wurde gesetzt; unmittelbar vor
dem normalen Dienststart war der Port frei.

Der normale `VantageMonitorApp` läuft aus einer separaten unveränderlichen
Kopie des vorhandenen geprüften JARs. Dessen 101 Klassen stimmen byteweise
mit `target/classes` überein; die vorhandenen 94 Testberichte sind fehlerfrei.
Es wurde kein neues Paket gebaut und kein laufendes Paket überschrieben.

Die normale REST-API hat danach sämtliche 19 reparierten Exporte bestanden:
alle Zeiten, Richtungen, Symbole, Mengen, Preise und Nettoergebnisse sind mit
den nativen Zeilen verglichen. HKD und EUR sind zusätzlich unabhängig gegen
die historischen EZB-Tagesfaktoren geprüft. USC wurde bereits beim Import in
USD normalisiert; die Lots bleiben unverändert. Diese Exportprüfung belegt
keine historischen Fremdbroker-Kontrakte oder fehlende echte Kapitalbasis.

Ein neuer normaler Updatejob wurde genau einmal gestartet:
`u-20261019-092038-e16ea0fc`, Ziel 200, Trades angefordert, bestehende
72-Stunden-Katalogfrist. Der tatsächlich verwendete lokale Katalog enthält
215 Provider. Der frische Cache wird wiederverwendet und die zusätzlichen
15 direkt aufgelösten Profile bleiben erhalten. Die Health-Zahl 167 zählt nur
Provider mit Kopierern und ist kein abweichender Gesamtkatalog.

Der normale Updatejob ist noch kein Abschlussnachweis. Er verwendet weiterhin
die normale 2.000er-Abrufkappe und die vorhandene adaptive Drosselung. Ein
späteres `done` wird getrennt auf Fehler, Abbruch, Generationen und tatsächliche
Abdeckung geprüft. Laufende Meldungen stehen in
`sources_vantage_normal_update_progress_20261019.json`.

Belege:

- `sources_vantage_full_scope_native_checkpoint_20261019.json`
- `sources_vantage_normal_service_start_20261019.json`
- `sources_vantage_all19_rest_acceptance_20261019.json`
- `sources_vantage_normal_update_start_20261019.json`

Private Laufdateien und unveränderte Sicherungen der 19 reparierten Generationen:
`data/runs/liveabschluss_20261019/vantage/`.

## Erneute Abnahme der 19 aktuellen Generationen um 10:08 MESZ

Während der normale Gesamtjob erst bei **14 von 215** stand, wurden alle
19 relevanten aktuellen Generationen erneut vollständig gegen REST geprüft.
Es gab keine zusätzlichen Update-POSTs. Native CSV-/Meta-SHA, positive exakte
Anbieter-Gesamtzahlen, eindeutige IDs und UTC stimmen; beide nativen Stores
sind feldgleich. Die REST-Exporte stimmen in sämtlichen Feldern einschließlich
der historischen HKD-/EUR-Umrechnung. Alle ursprünglichen Reparatur-IDs bleiben
in den aktuellen Archiven erhalten.

Zwei Anbieter waren im normalen Job inzwischen neu publiziert: **1010186**
hat weiterhin 4.591 Zeilen, aber einen anderen CSV-/Export-SHA; **1286742**
wuchs von 1.372 auf 1.373 Zeilen. Die übrigen 17 Anbieter einschließlich der
fünf FT-Provider haben dieselben CSV-/Export-SHAs wie bei der ersten Abnahme.
Die gegenwärtigen Daten sind während dieser Nachprüfung stabil geblieben.
Neue nachgelagerte Läufe müssen die aktuellen SHAs binden. Der allgemeine
215er-Lauf bleibt bis zu seinem tatsächlichen Ende getrennt offen.

Belege: `sources_vantage_rest19_snapshot_20261019T080849Z.json` und
`sources_vantage_native19_snapshot_20261019T080849Z.json`.

Die Positionsangaben `scope_position_one_based` in den historischen FT5-/19er-
Belegen beziehen sich auf die REST-Katalogsortierung. Sie sind keine
Abarbeitungspositionen des nativen Jobs. Dieser lädt `data/signals.csv` in
Dateireihenfolge; die FT5 stehen dort an Position 201 bis 205. Die beiderseits
identische 215er-ID-Menge und die unveränderte native Dateigeneration sind in
`sources_vantage_job_order_correction_20261019.json` belegt. Die SHA-, Zeilen-
und Feldprüfungen sowie der damalige FT5-Nicht-Neuveröffentlichungsbefund
bleiben davon unberührt. Die ursprünglichen Belege bleiben erhalten.

## Getrennter finaler Exportumfang

Der normale Job kann auch Teilhistorien liefern. `TradesTruncated=true` ist
im Vantage-Exporter kein Exportverbot; ein erfolgreicher CSV-Abruf belegt
deshalb keine vollständige Historie. Bei Gesamtzahl null bleiben
`TradesTotalAvailable` und `TradesTruncated` unbekannt. Die Felder
`TradesHistoryComplete` und `TradeHistoryComplete` liefert Vantage derzeit
nicht. Native Schema-Version 2, REST-Version `vantage` und API `v1` sind
getrennte Versionsangaben.

Nach erfolgreicher bestehender nativer Abschlussprüfung wartet ein einmaliger
rein lesender Folger auf die aktuellen Generationen und prüft HTTP 200/404,
den exakten CSV-SHA, Zeilenzahlen und den echten Produktparser. Elf
hermetische Regressionstests bestanden. Er erzeugt erst am Ende
`data/runs/liveabschluss_20261019/vantage/normal-final/eligible_scope.json`.
Diese Datei darf ausschließlich mit erfolgreichem `follower_exit.json`,
passendem Feld `eligible_scope_sha256` und ohne `follower_failure.json`
verwendet werden. Der zulässige Exportumfang gibt keine Workflowbewertung,
Studie oder Tradeserver-Veröffentlichung frei.

Vertrag und festes Schema sind in
`sources_vantage_export_contract_and_follower_20261019.json` dokumentiert.
Die bisherigen echten Laufzeiten stehen in
`sources_vantage_runtime_observation_20261019.json`; die dortigen
Tempo-Fortschreibungen sind keine feste Endzeit. Der normale 215er-Job
bleibt weiterhin offen.

## Belegter Einzelfehler und getrennte Teilabnahme

Am 19.10. um 11:31:56 MESZ wies der laufende Normaljob Provider 376760
(`Jessi`) wegen ungültigem `openPrice` ab. Seine alte native CSV samt
Version-1-Metadaten blieb bytegleich erhalten; der Export ist HTTP 404.
Der Originalpreis wurde dabei nicht separat untersucht, daher ist weder
ein Quell-Nullpreis noch ein Rundungsfehler belegt. Es gibt keine
Preisersetzung, keinen erneuten Quellenjob und keine Freigabe alter Bytes
als frische Lieferung. Beleg: `sources_vantage_jessi_rejection_20261019.json`.

Der alte strikte Folger wird dadurch keine globale 215er-Freigabe erzeugen.
Ein zusätzlicher, unabhängiger Teilfolger wartet auf dessen Ende und den
tatsächlich terminalen Originaljob. Er verwendet ein eigenes Schema 2 und
einen eigenen Ordner `normal-final-partial/`, ohne die eingefrorenen Reader
zu verändern. Fehler-IDs und nicht erneuerte IDs müssen exakt dem echten
Jobfehlerzähler entsprechen; alle übrigen Generationen müssen frisch,
beidseitig verifiziert, exportierbar und parsergeprüft sein. Erst dann
können sie in seinen begrenzten `eligible_scope` eingehen.
`source_job_fully_accepted` bleibt bei Fehlern ausdrücklich `false`.

Der Teilfolger hat 15 hermetische Tests bestanden und prüft
`STOP_AFTER_PHASE` im Root-Runordner vor und während des Wartens sowie
unmittelbar vor der Lesephase. Eine Pause erzeugt ausschließlich einen
Stoppreceipt und keinen zulässigen Exportumfang. Der neue Zeitvergleich
berücksichtigt die belegte Sekundengenauigkeit des nativen `finishedAt`;
ein früherer eingefrorener Vergleich mit nur 1 ms Toleranz war zu eng.
Vertrag, Hashes und Testbelege:
`sources_vantage_partial_reader_preparation_20261019.json`.
