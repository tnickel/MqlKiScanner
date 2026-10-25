# Verarbeitung und Persistenz – Nachweise vom 18.10.2026

Nur Audit: keine Produktivcodeänderung, kein produktiver Scan/Download, kein
Terminalstart, keine Secrets gelesen. Die Bestandsprobe liest einen konsistenten
SQLite-Snapshot im Modus `mode=ro`; für den Anwendungs-Reload verwendet sie eine
weitere eigene temporäre Kopie. Referenzierte CSV-Dateien werden nur gelesen.
Alle Defektproben verwenden ausschließlich synthetische Daten in temporären
Verzeichnissen. Diese Dateien enthalten keine Original-CSV, DB oder LLM-Texte.

## Ausgeführte Regressionstests

```powershell
python -m pytest -q -p no:cacheprovider tests/test_second_review_pipeline.py tests/test_review10_db.py tests/test_glm53_scanner_filter_finance.py tests/test_handover_source_currency.py tests/test_studien_waehrungsnachweis.py tests/test_scan_retry.py tests/test_pipeline_export_retry.py tests/test_external_review_ingestion.py --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/persistenz_pytest.xml
```

Ergebnis: **173 passed in 17.19s, Exit 0**. Log, JUnit und Exitcode liegen in
`persistenz_pytest.log`, `persistenz_pytest.xml`, `persistenz_pytest_exit.txt`.
Der erste Versuch mit `py -3.12` verwendete einen anderen Interpreter ohne
pytest und endete vor der Testausführung mit Exit 1. Dieser reine Laufzeitfehler
steht getrennt in `persistenz_pytest_py_launcher_failed.log`.

## Reproduzierte Integritätslücke: Dateiwechsel nach Analyse

**Bestätigter Codefehler unter reproduziertem Konkurrenzablauf, kein belegter
produktiver Eintritt.** Die Pipeline analysiert den veränderlichen
Download-/Cachepfad (`src/mqlkiscanner/pipeline.py:1795`) und erstellt erst beim
Speichern dessen unveränderlichen Snapshot (`pipeline.py:2110`,
`db.py:403`/`:410`). `db.store_forensik` trägt anschließend den SHA dieses
erst später gespeicherten Inhalts ein (`db.py:395`). Er belegt somit nicht,
welche Bytes die Analyse tatsächlich gelesen hat.

`persistenz_probes.py` reproduziert den Ablauf zweimal: zuerst durch einen
deterministischen Dateitausch, dann über den echten manuellen Nachladepfad
`katalog.lade_signal_daten` → `ingest.hole_trades`. Letzterer kann trotz
gehaltenem gemeinsamen Scan-Lock laufen. Der UI-Button in
`app_pages/alle_signale.py:662`/`:668` hat keine entsprechende Laufsperre;
`katalog.py:349` erwirbt sie ebenfalls nicht. Der Artefakt-RLock
(`ingest.py:39`/`:48`) schützt jeweils nur den einzelnen Abruf, nicht das
anschließende Analyse- und Speicherfenster.

Beide Proben ergeben: Befund **2 Trades, 50,0 % Winrate**, gespeicherter
CSV-Snapshot **3 Trades, 66,7 % Winrate**. Der Scan meldet Erfolg, der Befund
trägt den SHA der zweiten Datei und der DB-Reload akzeptiert ihn als aktuell.
Damit können Tabellen-/Bewertungswerte dem als Beleg gespeicherten Export
widersprechen. Gemeinsame Scan-/Studienlocks zwischen den regulären großen
Läufen verhindern diesen konkreten manuellen Nachladeweg nicht.

Die Normalprobe bestätigt zugleich, dass unveränderte Eingaben atomar und mit
passendem SHA gespeichert werden; spätere Mutationen des Downloadcaches
verändern bereits gespeicherte Snapshots nicht.

Ausführen:

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/persistenz_probes.py
```

Ergebnis und Assertions: `persistenz_probes.json`, Exit 0. Als zusätzliche
Robustheitsbeobachtung zeigt dieselbe Probe: Ein nach dem Scan gelöschter
Snapshot wird beim normalen `results_from_db` nicht durch Dateiprüfung erkannt.
Produktiv fehlen laut Bestandsinventur keine referenzierten Trade-Dateien;
daraus wird kein zusätzlicher aktueller Fehlzustand behauptet.

## Produktiver Bestand am konsistenten Snapshot

`persistenz_bestand.py`/`.json` enthalten ausschließlich aggregierte Befunde
und öffentliche Signal-IDs zur Zuordnung.

- 194 Signale, 163 Forensikdatensätze, 193 referenzierte Trade-Dateien.
- Forensikversionen: 7 (27), 11 (3), 14 (10), 15 (104), 16 (15), ohne Version (4).
  **Kein gespeicherter Workflow-Befund hat aktuelle Version 19.**
- 148 der 163 Befunde ohne gespeicherte SHA-Bindung, 15 mit passender Bindung;
  keine abweichende gespeicherte SHA-Bindung.
- Alle 194 Signal-Stammdatensätze ohne `account_currency` und ohne
  `account_currency_evidence_version`. Das ist ein veralteter Datenstand, kein
  Nachweis eines aktuellen USD-Guard-Defekts.
- Aktueller Anwendungs-Reload auf eigener Temp-Kopie: 194 Zeilen, 0 aktuelle
  Workflow-Forensiken, 161 als veraltet markiert, 63 Fehler. Ampeln: 106 rot,
  70 weiß, 18 ausgeschlossen; keine grüne oder gelbe Freigabe.
- Das betrifft die Workflow-Forensik. Die separat gespeicherten Equity-Studien
  sind ein anderer Datenkanal und dürfen daraus nicht pauschal als veraltet
  eingeordnet werden.
- 163/163 referenzierte CSVs mit Forensik erfolgreich neu geparst. 150 stimmen
  in allen vorhandenen Vergleichsfeldern überein (Tradeanzahl, Winrate,
  maximale Verlustserienlänge/-summe). 13 alte Befunde unterscheiden sich von
  heutigen Parser-/Statistikwerten. Betroffene Versionen sind sämtlich alt
  oder unbekannt; die Differenzen belegen daher keinen aktuellen v19-Bug.

Die 3 Fremdschlüsselverletzungen betreffen ausschließlich `analyses.id`
36/37/38 zur nicht mehr vorhandenen `signal_id=424242`, erstellt am
05.09.2026 11:57:38, für `trade_analyse`, `risiko_analyse`, `gesamtbericht`.
Die signalgetriebene Katalogabfrage zeigt diese verwaisten Zeilen nicht.
Sie belegen historische Dateninkonsistenz; die aktuellen Tests bestätigen
Fremdschlüsselschutz für neue Schreibvorgänge. Keine automatische Bereinigung.

`persistenz_metrics_identitaet.py`/`.json` prüfen alle gecachten
Metrics-Artefakte: **1550/1550** JSON-Dateien lesbar, jeweils Root und `metrics`
als Objekt, **1550/1550** `signalId` und `version` passend zur Artefakt-DB.
Keine fehlende Identität und kein Konflikt. Aufteilung: mql5 166, pelik 636,
vant 348, robo 200, zulu 200. Dabei wurden nur Cachedateien gelesen und
Zähler/öffentliche Signal-IDs als Evidenz ausgegeben.

Für einen Bestandsnachlauf benötigt das Skript den Pfad zu einem konsistenten
Scanner-DB-Snapshot:

```powershell
python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/persistenz_bestand.py <snapshot.db>
```

Die Originaltabellen wurden nicht neu synchronisiert. Dieser Audit bestätigt
somit den gespeicherten Bestand und die isolierten Codeabläufe; er bestätigt
keine frische vollständige Lieferung aller Anbieter vom 18.10.2026.
