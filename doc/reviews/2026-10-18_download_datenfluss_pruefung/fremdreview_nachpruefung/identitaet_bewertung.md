# Unabhängige Nachprüfung DEFECT-02 und DEFECT-03

Stand: 18.10.2026. Untersucht wurde der aktuelle Arbeitsstand, einschließlich
der bereits zuvor vorgenommenen Reviewkorrekturen. Fremdreviewbehauptungen
wurden nicht als neue Tatsachen vorausgesetzt. Sämtliche Reproduktionen und
Tests verwenden synthetische Daten in temporären Datenbanken. Keine produktive
DB, App, Plattform, Zugangsdaten oder Kurs-Terminals wurden verwendet.

## DEFECT-02: teilweise veraltete Behauptung, weitere Low-Level-Lücke bestätigt

Der im Fremdreview genannte Aufruf `store_scan_result(existing_id, payload)`
ohne Quelle war zu Beginn dieser Nachprüfung bereits gesperrt. Der zitierte
Audit-Solltest besteht inzwischen. Dies wurde erneut reproduziert:
`identitaet_before.json` enthält dafür `blocked=true`.

Die darunterliegende öffentliche Funktion `db.upsert_signal` ließ dagegen
weiterhin einen direkten Updateaufruf ohne Quelle zu. Die isolierte Probe
änderte den Namen einer vorhandenen synthetischen MQL-Zeile, ohne ihre Quelle
ausdrücklich zu behaupten; das alte Quellenlabel blieb stehen. Damit ist ein
verbliebenes internes Datenintegritätsrisiko bestätigt.

Alle produktiven Aufrufstellen wurden mit `rg -n 'upsert_signal\(' src
app_pages scripts -g '*.py'` geprüft. Der einzige produktive Aufrufer ist
`store_scan_result`; dessen produktiver Aufrufer ist die Pipeline, die die
Quelle bereits ausdrücklich mitgibt. Weitere direkte produktive Aufrufer
wurden nicht gefunden. Eine extern ausnutzbare Sicherheitslücke oder eine
umgehbare Authentisierungsgrenze ist durch den Fremdreview nicht belegt.
Die tatsächliche API-Vertragslücke wird trotzdem geschlossen.

### Umsetzung statt blinder Übernahme des Abschnitt-7-Patches

Der vorgeschlagene Patch würde den fehlenden Quellenparameter bei bekannten
Quellen grundsätzlich abweisen. Er berücksichtigt aber weder eine fehlende
gegenüber einer bereits vorhandenen Zeile mit leerem Altlabel noch die
Serialisierung gleichzeitiger Neuanlagen. Deshalb wurde der Vertrag zentral
und ausdrücklich umgesetzt:

- `upsert_signal` verlangt bei jeder bereits vorhandenen ID eine explizite,
  nichtleere Stringquelle; unbekannte behauptete Quellen werden nicht aus dem
  Bestand abgeleitet.
- Explizit abweichende Quellen werden weiterhin verworfen. Fehlende Quelle
  bleibt nur für eine Legacy-Neuanlage kompatibel und wird dort `mql5`.
- Ungültige Quellenwerte werden auch bei Neuanlage abgewiesen.
- Standalone-Aufrufe reservieren den SQLite-Schreibzugriff vor der ersten
  Identitätsabfrage mit `BEGIN IMMEDIATE`. In einer bestehenden Transaktion
  wird deren Verbindung weiterverwendet.
- Der vollständige Scanvertrag und die frühere SHA-/Snapshotabsicherung
  bleiben erhalten. Es gibt keine Schema- oder Datenmigration.

`identitaet_after.json` bestätigt den zuvor fehlenden Low-Level-Schutz:
`upsert_signal_without_source.blocked=true` und keine Änderung unter altem
Quellenlabel. Das Probeprogramm gibt JSON auf stdout aus und arbeitet nur in
einem eigenen `TemporaryDirectory`.

## DEFECT-03: Architekturgrenze bestätigt, Komplettmigration nicht gerechtfertigt

Die zentrale Workflowidentität ist weiterhin `signal_id`; Katalog,
Artefaktbezüge und Teile der Datenbeschaffung können dagegen Quellen
unterscheiden. Der Beginn der Nachprüfung reproduziert zudem, dass die
Katalogdarstellung zwei Quellen derselben numerischen ID auf eine Zeile
reduziert. Der frühere UI-Test mit gemocktem `katalog_resultate` beweist den
echten Katalogübergang nicht.

Ein alleiniger Austausch von Primärschlüsseln und `gesehen` reicht nicht.
Unter anderem Studien, Markierungen, Kommentare, Statistiksammlungen und
verschiedene Einzel-/Batchaktionen verwenden noch numerische IDs. Eine
Teilumstellung könnte fremde Daten verknüpfen oder überschreiben. Deshalb
erfolgt keine ungeprüfte Komplettmigration. Die minimale Katalogdarstellung
und deren Aktionsschutz werden im übergeordneten Arbeitspaket umgesetzt.

### Zentrale defensive Absicherung der ID-basierten Equity-Studien

Als dafür benötigte DB-Schnittstelle wurde `signal_quellen(signal_id)`
ergänzt. Sie liest die bekannten Quellen einer exakten ID aus `signals` und
`katalog_signale`; leere Altlabels werden als `mql5` normalisiert. Sie führt
keine Daten- oder Schemaänderung aus und setzt ein initialisiertes Schema
voraus.

Da `equity_studien` weiterhin nur eine numerische ID besitzt:

- `store_equity_studie` reserviert den Writerlock und verweigert bei mehr als
  einer bekannten Quelle die Speicherung. Ein identischer CSV-SHA zweier
  Quellen hebt den Identitätskonflikt nicht auf.
- `get_equity_studie` und `list_equity_studien` geben solche nicht zuordenbaren
  Studien nicht zurück. Der Bulkfilter verwendet eine einzelne SQL-Abfrage
  mit normalisierter Quellen-UNION und Konflikt-CTE, keine N+1-Abfragen.
- Bereits vorhandene Studien bleiben unverändert in der Datenbank. Die
  Sperre löscht keinen historischen Beleg und verändert keine Bewertung.

Diese Absicherung beweist keine vollständige historische Studienbesitzkette:
Ein alter ID-basierter Beleg ohne Quellenangabe kann seinen früheren Besitzer
nicht nennen, wenn eine Quelle später vollständig aus allen aktuellen Claims
verschwindet. Die vollständige Composite-Architektur bleibt deshalb eine
gesonderte Aufgabe; der vorliegende Schutz verhindert die aktuell erkennbaren
Mehrquellenzuordnungen konservativ.

## Reproduktion und Testnachweise

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/fremdreview_nachpruefung/identitaet_probe.py
```

Die gespeicherten Dateien `identitaet_before.json` und `identitaet_after.json`
halten den jeweiligen Zeitpunkt der DB-Nachprüfung fest. Die im Probeergebnis
ebenfalls dokumentierte Katalogdarstellung kann sich durch die parallele,
separat verantwortete Katalogkorrektur danach verändern.

Neue Tests in `tests/test_source_identity_contract.py` prüfen den zentralen
Quellenvertrag, ungültige und fehlende Quellen, explizite korrekte Updates,
Weiterverwendung aktiver Transaktionen, konkurrierende Neuanlagen, den
Quellen-UNION-Helper und konfliktfreie/konfliktbehaftete Studien einschließlich
unverändertem Rohbestand und Bulkabfrage ohne N+1.

```powershell
python -m pytest tests/test_source_identity_contract.py tests/test_download_snapshot_integrity.py tests/test_audit_identitaet_20261018.py tests/test_second_review_storage.py tests/test_forensik_trade_sha.py tests/test_second_review_pipeline.py tests/test_review10_db.py tests/test_studien_batch.py tests/test_studien_waehrungsnachweis.py tests/test_virtuelle_messanzeige.py -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/fremdreview_nachpruefung/identitaet_db_final.xml
```

**142 passed in 23.10s, Exit 0.** Log, JUnit und Exitcode:
`identitaet_db_final.log`, `.xml`, `_exit.txt`. `git diff --check` für DB und
neue Tests war erfolgreich.

Der erste kleine Low-Level-Testlauf vor der zusätzlichen Studienabsicherung
bestand mit 73 Tests (`identitaet_pytest.*`). Ein erweiterter Zwischenlauf
mit `test_katalog.py` hatte 185 bestandene Tests und eine während paralleler
Katalogänderung veraltete Erwartung an die bisherige Kollisionsunterdrückung
(`identitaet_final.*`). Dieser Zwischenlauf ist kein finaler Katalognachweis.
Die abschließende projektweite Regression und die Katalogtests werden mit
dem stabilen zusammengeführten Stand gesondert ausgeführt.
