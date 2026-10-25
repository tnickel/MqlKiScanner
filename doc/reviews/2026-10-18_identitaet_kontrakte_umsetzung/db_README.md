# Persistenz, Identitätsregister und Copy-Migration

Stand 18.10.2026. Diese Teilabnahme aktiviert keine produktive Datenbank.

## Vertrag und Datenmodell

- `signal_identitaeten.signal_ref` ist die interne Referenz. Externe numerische
  Signal-IDs bleiben unverändert in `externe_id`; `UNIQUE(quellen_uid, externe_id)`
  trennt identische Nummern verschiedener Anbieter.
- `quellen_identitaeten.quellen_uid` ist dauerhaft. `quellen_alias` behält frühere
  Kürzel; eine Umbenennung ändert weder UID noch Signalreferenzen. URL/Port sind
  Verbindungsdaten. Archivierte Transportverbindungen löschen keine Identitäten.
  Die ausdrückliche Wiederverbindung eines reservierten Namens benötigt die UID.
- Der Katalog und Quellenartefakte registrieren Identitäten ohne Workflowkopf in
  `signals`. Kinder verwenden `signal_ref`: Trade-Snapshots, Forensik, Analysen,
  Studien, Abonnentenverlauf, Reportspiegel, Ampelchronik/-wechsel, Kommentare,
  Markierungen, Fixierungen, Dossiers und signalbezogene Journalläufe.
- Für einzelne DB-Lesezugriffe: `quelle=...` oder `signal_ref=...` verwenden.
  ID-only-Lesen ist nur bei einer eindeutigen Registerauflösung erlaubt, sonst
  `AmbiguousSignalIdentity`. Unqualifizierte Sammellisten lassen mehrdeutige IDs
  aus; `identitaeten=True` liefert `(quelle, externe_id)`-Schlüssel.
- Bestehende Identitäten erfordern beim Schreiben eine explizite Quelle oder
  Referenz. Nur eine erstmalige Legacy-Neuanlage ohne Quelle kann MQL5 erhalten.
  Leere/boolesche/numerische explizite Quellen werden abgewiesen. Nichtleere
  historische Labels werden nicht durch Trimmen umgedeutet.
- `signal_identity.identity_key` / `key_for` sind Präsentationsschlüssel;
  `stable_identity_key` bevorzugt Referenz und UID. Bei Chronik-/Journalzeilen hat
  `signal_quelle`/`datenquelle` Vorrang vor `quelle` als Laufart/Auslöser.
- Chronik-Schreibaufrufe erhalten `signal_quelle=...`; ihr bisheriges positionales
  `quelle` bleibt `full`/Teilscan. Journal-`quelle` bleibt GUI/Daemon/CLI.
- Derselbe Besitzer und dieselbe externe ID dürfen keinen MT4/MT5-Widerspruch
  besitzen. `upsert_signal` und komplette Katalogtransaktionen weisen solche
  Konflikte zurück. Verschiedene Besitzer dürfen gleiche IDs, Plattformen und
  CSV-SHAs gleichzeitig speichern.
- Scan-Transaktionen behalten die geprüfte unveränderliche CSV/SHA-Bindung.
  Dossierbeobachtungen prüfen auch die Eigentümer ihrer Delta-/Journalverweise.

## Explizite Migration

`identity_migration.migrate_copy(source_path, destination_path,
verify_files=True, settings={...})` liest die Quelle per SQLite-URI `mode=ro`.
SQLite-`backup` erzeugt einschließlich committed WAL-Seiten ein konsistentes,
privates `*.legacy-backup.sqlite`. Ein neues Staging-Schema wird aufgebaut und
nach Validierung ausschließlich als neue Kandidatendatei veröffentlicht.
Vorhandene Ziele werden nie überschrieben; der produktive Pfad wird nie ersetzt.

`init_db` migriert keinen Altbestand. Auch einzelne alte Kindtabellen und als v2
markierte unvollständige Schemata werden zurückgewiesen. Die Schemaabnahme prüft
Spalten, Primärschlüssel-/NOT-NULL-Verträge, Fremdschlüssel und vollständige
UNIQUE-Indizes; ein partieller Index ersetzt keine zentrale Identitätsgarantie.
Alte ID-only-SQL-Schreibstellen treffen im neuen Schema auf fehlende Spalten.

Belegte Quelle an Workflow/Katalog/Verbindungsartefakt wird übernommen.
Workflow-FK-Kinder werden über ihren alten Elternkopf zugeordnet. Andere alte
ID-only-Kinder erhalten **keine** Quelle allein aus einem heutigen Katalogtreffer,
gleicher Plattform, Name oder SHA. Ohne historischen Quellenbeleg bleiben sie
vollständig in `migration_quarantaene`, einschließlich Grund und ursprünglicher
Zeile; BLOBs sind reversibel base64-kodiert. Dortige Rohdaten bleiben in der
privaten DB, außerhalb des Repositorys. Unbekannte signalbezogene Erweiterungen
benötigen einen eigenen Adapter. Alte Views/Trigger werden nicht neu ausgeführt;
der unveränderte Originalbackup erhält das vollständige alte Schema.

Original-Audit-IDs bleiben erhalten. AUTOINCREMENT-Highwatermarks verwenden auch
das größte Original-ID, wenn quarantänisierte Zeilen sonst zukünftige ID-Werte
freigeben würden; dies gilt auch ohne altes AUTOINCREMENT.

`agenten_budget_altkosten` bewahrt die Kostenbelege quarantänisierter Schritte,
ohne einen Signaleigentümer oder Rohprompt zu erfinden. Tages-/Monatsanzeige und
Reservierung beziehen diese Belege über `budget._legacy` ein. `budget_ledger=1`
bleibt ein Spiegel und zählt nicht noch einmal neben dem HTTP-Ledger. Jede
Copy-Migration vergleicht alle bekannten Tages-/Monatskosten einschließlich
offener Reservierungen vor und nach der Umstellung; Abweichung bricht ab.

Legacy-Fixnummern aus Settings werden nur bei genau einem heutigen registrierten
Besitzer als aktuelle Fixierung übernommen; unbekannte/mehrdeutige Werte bleiben
mit Grund in Quarantäne. Settings werden durch diese API nicht verändert.

## Nachweise und Wirkung auf den echten Altbestand

`db_final_dryrun_report.json` wurde mit dem finalen Migrator auf einem bereits
konsistent privat gesicherten produktiven Altbestand erzeugt. Es ist ausdrücklich
kein unmittelbar vor einem Cutover erstellter Livekandidat.

- 26 ursprüngliche Fachtabellen, 12.764 Originalzeilen: 8.306 aktiv übernommen,
  4.458 vollständig quarantänisiert. Alle ursprünglichen Fachwerte und Texte
  bleiben erhalten (`db_final_payload_verification.json`). Nur leere Quellenlabels
  und globale Portfolio-ID0 erhalten die dokumentierte neue Repräsentation.
- 194 Workflowköpfe, 193 Trade-Dateien, 163 Forensikbefunde, 1.454 Katalogeinträge,
  3.094 Quellenartefakte aktiv. 2.279 Analysen aktiv, drei alte Orphans in Quarantäne.
- Ohne historischen Besitzerbeleg bleiben unter anderem alle 1.572 alten
  Studien, 1.305 Historypunkte, 68 Reportspiegel, 834 Chronikzeilen, 240 Wechsel,
  19 Profile, 71 Beobachtungen, 45 Deltas, vier Kommentare sowie 84 Journalläufe
  und deren 213 Schritte in Quarantäne. Daraus folgen bewusst sichtbare Lücken
  bis zu einer belegten Zuordnung oder einer neuen Prüfung.
- Die 213 reinen Kostenbelege erhalten sämtliche Tages-/Monatssummen: September
  483.897 und Oktober 102.018 Tokens jeweils vor/nach gleich. Auch Reservierung
  und bezahlter Verbrauch stimmen je bekannter Periode überein.
- Fünf Besitzer, 1.732 registrierte Identitäten einschließlich Artefakt-only-IDs;
  15 eindeutige Legacy-Fixierungen. SQLite-Integrität `ok`, keine FK-Verletzung.
  3.287 referenzierte Dateien SHA-korrekt, keine fehlend oder verändert.

`db_dryrun_report.json` und `db_payload_verification.json` konservieren den ersten
Zwischenstand vor der Kostenbelegergänzung. `db_source_state_verification.json`
zeigte danach einen echten weiteren Live-Herzschlag ausschließlich in
`agenten_steuerung.letzter_tick`; dieser Befund wurde dem Hauptagenten gemeldet.
Der erste physische Live-SHA vor dem allerersten Backup wurde nicht separat
aufgenommen. Der finale Backuphelper erfasst diese Vorher-/Nachher-SHAs.

## Regression und Cutover-Grenze

Reproduktion: `python doc/reviews/2026-10-18_identitaet_kontrakte_umsetzung/db_run_regression.py`.
Komplette Argumentliste, Exitcode und vor/nach verglichene Quell-/Testhashes stehen
in `db_regression_command.json`, Ergebnisse in `db_regression.xml` und
`db_regression.log`: **196 bestanden, Exit 0**. Die sechs erfassten produktiven
Quelldateien waren während dieses Laufs unverändert. Zwei parallel bearbeitete
Testdateien änderten sich; ausschließlich diese wurden anschließend vollständig
erneut geprüft: **31 bestanden, Exit 0**, Datei-Hashes vor/nach identisch
(`db_regression_followup*`). Diese 31 sind Wiederholungen und keine zu addierende
Anzahl unabhängiger Fälle. `db_verification.json` ordnet die Quellhashes und
Modulfallzahlen zu. `db_regression_intermediate_188*` hält den davor bestandenen
188er-Lauf fest. Die Sourcecontract-/Auditfixtures wurden auf die neue fachliche
Abnahme umgestellt; keine roten Fälle werden durch Marker ausgeschlossen.
Nach dem Lauf entfernte der Hauptagent genau eine leere CRLF-Zeile am Ende von
`db.py`. Die Identität des getesteten Inhalts einschließlich dieser einen Zeile
ist durch den SHA-Vergleich in `db_verification.json` nachgewiesen; der endgültige
normalisierte Stand wird zusätzlich durch die anschließende Hauptregression
abgedeckt.

Die Hauptabnahme koordiniert einen frischen Backup-/Copy-Lauf nach überprüftem
Prozessstillstand und die exklusive Aktivierung. Beide privaten Probekandidaten
dieser Teilabnahme werden nicht aktiviert. Nach neuen quellenüberlappenden
Schreibvorgängen ist ein verlustfreier Rückwechsel in das alte ID-only-Schema
nicht möglich; ein Rückfall muss den vollständigen V2-Stand bewahren.
