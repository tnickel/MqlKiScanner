# Behebung F2 und des zusätzlichen Scan-API-Identitätsvertrags

Stand: 18.10.2026. Keine produktiven Daten, Downloads, Terminals, Apps oder
Zugangsdaten wurden für diese Umsetzung verwendet. Änderungen betreffen
`src/mqlkiscanner/pipeline.py`, `src/mqlkiscanner/db.py` und gezielte Tests.
Die ursprünglichen Fehlernachweise und ihre Ergebnisdateien bleiben erhalten.

## Umsetzung

- `db.snapshot_trade_file()` sichert die tatsächlich gelesenen Eingabebytes
  unmittelbar nach dem Download in einen atomar veröffentlichten Snapshot und
  gibt dessen SHA zurück. Die Pipeline verwendet danach diesen Snapshot für
  Parser/Engine und ergänzende Effizienzberechnungen.
- `db.store_scan_result(..., expected_trades_sha256=...)` übernimmt den vor der
  Analyse bestimmten SHA. Der Befund muss ihn bereits ausdrücklich enthalten.
  Kopierte Snapshotbytes und erwarteter SHA müssen vor der Speicherung passen;
  andernfalls werden die SQL-Änderungen vollständig zurückgerollt. Der neue
  Pipelinepfad kann keinen älteren Befund nachträglich an einen neu gelesenen
  Export binden. Bestehende Importaufrufe ohne diesen neuen Parameter behalten
  ihre Schnittstelle.
- Der DB-Reload prüft bei ansonsten aktuellen, SHA-gebundenen Befunden auch die
  referenzierte Datei. Fehlende, unlesbare oder veränderte Belege werden als
  veraltet/fehlerhaft behandelt. Die neue Prüfung macht aus einem alten
  Workflowbefund keine neue Forensik und verändert keine Finanzberechnungen.
- Produktive Aufrufer von `store_scan_result` wurden geprüft: ausschließlich
  die Pipeline, die ihre Quelle bereits ausdrücklich mitgibt. Bei vorhandener
  Signal-ID verlangt diese API jetzt eine explizite nichtleere Quelle. Die
  behauptete Eingangsquelle wird niemals aus dem vorhandenen Datensatz
  abgeleitet. Legacy-Neuanlagen ohne Quelle erhalten `mql5`.
- `BEGIN IMMEDIATE` reserviert den SQLite-Schreibzugriff vor der
  Identitätsprüfung. Gleichzeitige Neuanlagen aus verschiedenen Quellen können
  dadurch nicht beide eine fehlende ID beobachten und später den anderen
  Datensatz überschreiben. Abgelehnte Updates lassen den Bestand unverändert.

Die fachliche DD-Schranke, Calmar-/Ertragsregeln, Forensikversion und
Produktiveinstellungen wurden in diesem Arbeitspaket nicht verändert.

## Regressionen

`tests/test_download_snapshot_integrity.py` enthält 13 ausgeführte Fälle:

- Eine echte Quellen-Ingest-/Nachladekette wird mit zwei Threads und Events
  deterministisch während der Analyse verschachtelt. Der manuelle Abruf
  ersetzt den Cache durch B (3 Trades/66,7 % Winrate), während der Scanner das
  gemeinsame Scan-Lock hält. Engine, Effizienz und gespeicherter Snapshot
  bleiben bei A (2 Trades/50,0 %). Befund-SHA und DB-Reload passen dazu.
- Geänderte Eingabebytes vor Commit sowie ein fehlender/falscher ausdrücklicher
  Befund-SHA werden abgewiesen; Stammdaten, Tradeverweis und Befund rollen
  gemeinsam zurück.
- Ein nach dem Scan gelöschter oder manipulierter Snapshot kann beim Reload
  nicht als aktuelle vollständige Forensik gelten.
- Fehlende/leere/ungültige Quellen bei bestehenden IDs werden abgewiesen,
  Legacy-Neuanlage und ausdrücklich zugeordnete Updates bleiben möglich.
  Konkurrierende Neuanlagen können keinen fremden Quelleninhalt übernehmen.

Zwei bestehende Testfixtures wurden dem präzisierten Updatevertrag angepasst:
`test_forensik_trade_sha._signal()` nennt seine Quelle `mql5`; der zweite
Schreibvorgang in `test_second_review_storage` ebenfalls. Fremde unversionierte
Audit-Testdateien wurden nicht verändert. Der zuvor absichtlich rote Fall
`test_d_luecke_store_scan_result_ohne_quelle_ueberschreibt_fremde_id` besteht nun.

## Letzter gezielter Testlauf

```powershell
python -m pytest tests/test_download_snapshot_integrity.py tests/test_second_review_storage.py tests/test_forensik_trade_sha.py tests/test_second_review_pipeline.py tests/test_review10_db.py tests/test_pipeline_export_retry.py tests/test_scan_retry.py tests/test_audit_identitaet_20261018.py -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/fix_persistenz_final.xml
```

**72 passed in 18.17s, Exit 0.** Keine Ausklammerung. Nachweise:
`fix_persistenz_final.log`, `.xml`, `_exit.txt`.

Vor dem zusätzlichen Identitätsguard bestand die erste F2-/Storagegruppe mit
58 Tests (`fix_persistenz_pytest.*`). Eine weitere Konsumentengruppe für
Währung, Studien, DB-Reload, Rendite, Tabellen und neue Auditproben bestand mit
174 Tests bei einem damals bewusst ausgelassenen roten Identitätsfall. Dieser
Fall ist im abschließenden 72-Test-Lauf enthalten und grün:

```powershell
python -m pytest tests/test_glm53_scanner_filter_finance.py tests/test_handover_source_currency.py tests/test_studien_waehrungsnachweis.py tests/test_retdd_equity_pipeline.py tests/test_drawdown_anzeige.py tests/test_review17_pipeline.py tests/test_alle_signale_performance.py tests/test_audit_tabellen_20261018.py tests/test_audit_identitaet_20261018.py -k 'not test_d_luecke_store_scan_result_ohne_quelle_ueberschreibt_fremde_id' -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/fix_persistenz_consumers.xml
```

**174 passed, 1 deselected in 30.76s, Exit 0.** Nachweise:
`fix_persistenz_consumers.log`, `.xml`, `_exit.txt`. Die Gruppen überlappen und
dürfen nicht zu einer Zahl unterschiedlicher Tests addiert werden.

`git diff --check` für die geänderten Dateien war erfolgreich. Die hier
aufgeführten gezielten Tests ersetzen keine projektweite abschließende
Regression und keine produktive Betriebsabnahme. Die ursprüngliche
`persistenz_probes.py` behauptet absichtlich den alten Fehler und ist nach der
Korrektur kein Sollverhaltenstest.
