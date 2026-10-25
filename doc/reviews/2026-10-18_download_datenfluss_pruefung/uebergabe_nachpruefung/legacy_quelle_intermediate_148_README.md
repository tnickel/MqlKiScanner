# Nachprüfung und Behebung leerer Legacy-Quellen

Stand: 18.10.2026. Der zusätzliche Randfall wurde vor der Produktcodeänderung
mit synthetischen Daten in temporären SQLite-Datenbanken reproduziert.
Produktive Datenbanken, Einstellungen, Apps, Downloads und Zugangsdaten wurden
nicht verwendet. Frühere Berichte und Manifeste bleiben unverändert.

## Bestätigter Fehler vor der Änderung

Die gemeinsame Prüfung in `db.upsert_signal` verglich das vorhandene
Quellenlabel nur, wenn es einen wahren Wahrheitswert hatte. Dadurch konnten
`NULL` und `''` über beide APIs (`upsert_signal` und `store_scan_result`) von
einer ausdrücklich fremden Quelle übernommen werden. Ein vorhandenes `' '`
wies zwar die fremde Quelle ab, blockierte jedoch auch ein korrektes,
ausdrücklich als `mql5` bezeichnetes Update.

Die sechs neuen parametrisierten Fälle in
`tests/test_source_identity_contract.py::test_legacy_empty_source_only_allows_explicit_mql5_update`
decken beide APIs und die drei Altlabels `None`, `''`, `' '` ab. Jeder Fall
verlangt die Ablehnung eines `vant`-Updates, unveränderte Signal- und
Forensikzeilen nach der Ablehnung sowie ein anschließend erfolgreiches
explizites MQL5-Update. Es wurden keine vorhandenen Assertions gelockert.

Der Test lief vor dem Fix:

```powershell
python -m pytest tests/test_source_identity_contract.py -k legacy_empty_source_only_allows_explicit_mql5_update -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/uebergabe_nachpruefung/legacy_quelle_before.xml
```

**6 fehlgeschlagen, 20 abgewählt, Exit 1**, 5,21 Sekunden. Bei vier Fällen
fehlte die geforderte Ablehnung; zwei scheiterten am erlaubten MQL5-Update.
Das ist der isolierte Fehlernachweis, kein abschließender Testlauf.
Belege: `legacy_quelle_before.log`, `.xml`, `_command.json`, `_exit.txt`.

## Minimale Änderung

`src/mqlkiscanner/db.py:311` normalisiert das vorhandene Label vor dem
Quellenvergleich genau wie `signal_quellen`: `str(label or '').strip() or 'mql5'`.
Eine vorhandene Zeile wird dadurch auch bei leerem Altlabel ausschließlich
der Legacy-Quelle MQL5 zugeordnet. Die Eingangsquelle muss weiterhin explizit
vorliegen; sie wird nicht aus dem Bestand ergänzt. Die bestehende
Schreibtransaktion und deren Rollback bleiben erhalten.

Beide Schreibschnittstellen verwenden diese zentrale Prüfung. Es gibt keine
Schemaänderung, keine Datenmigration und keine Änderung fachlicher Bewertung.
Legacy-Neuanlagen ohne Quelle behalten ihren bisherigen Default.

## Abschließende gezielte Regression

```powershell
python -m pytest tests/test_source_identity_contract.py tests/test_download_snapshot_integrity.py tests/test_audit_identitaet_20261018.py tests/test_second_review_storage.py tests/test_forensik_trade_sha.py tests/test_second_review_pipeline.py tests/test_review10_db.py tests/test_studien_batch.py tests/test_studien_waehrungsnachweis.py tests/test_virtuelle_messanzeige.py -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/uebergabe_nachpruefung/legacy_quelle_final.xml
```

**148 bestanden, Exit 0**, 21,74 Sekunden: die vorherige 142-Fälle-Gruppe plus
genau sechs neue Fälle. Keine Testauswahl per `-k`, keine Ausschlüsse.
Die Standardkonfiguration `not llm` bleibt erhalten; diese Gruppe enthielt
keine dadurch abgewählten Fälle. Die Quellenvertragsdatei umfasst jetzt
26 ausgewählte Fälle.

Belege: `legacy_quelle_final.log`, `.xml`, `_command.json`, `_exit.txt`.
Die Command-Dateien enthalten exakte Argumente, Zeitpunkte, Exitcodes und
SHA-256 der beiden betroffenen Quell-/Testdateien. Nur der Kindprozess erhielt
`PYTHONIOENCODING=utf-8`. `git diff --check` für beide Dateien war erfolgreich.

Der frühere vollständige Lauf mit 2.499 bestandenen Fällen liegt vor dieser
zusätzlichen Korrektur. Er wurde dafür nicht wiederholt; der neue Nachweis ist
die oben abgegrenzte gezielte Regression. Eine produktive Betriebsabnahme und
die vollständige Composite-Migration werden damit nicht behauptet.
