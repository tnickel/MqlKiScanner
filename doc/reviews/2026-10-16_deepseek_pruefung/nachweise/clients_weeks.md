# Nachtrag: nicht endliche Quellen-Wochen umgehen den Altersfilter

Datum: 16.10.2026. Basis `cef1e5a`; enger Folgeauftrag zu `ingest.kandidaten`
und `ScanPipeline.build_candidates`. Unabhängig synthetisch reproduziert.
Der laufende eingefrorene Snapshot `Scanner_final2` wurde nicht verändert.

## Bestätigter Befund

Vorher konvertierte Ingest `weeks="NaN"` beziehungsweise `"Infinity"` zu
`float('nan')`/positiver Unendlichkeit. Der lokale Filter verwarf nur `None`
oder `weeks < min_wochen`. Bei `min_wochen=26` ist `nan < 26` falsch; positive
Unendlichkeit ist ebenfalls nicht kleiner. Beide ungültigen Altersangaben
wurden deshalb ausgewählt. Der Fehler ist im tatsächlichen synthetischen
Pfad JSON → `ingest.kandidaten` → `build_candidates` nachgewiesen, nicht nur
an einem isolierten Vergleich.

Auch direkt übergebene Kandidaten mit numerischem NaN/+inf passierten;
direkte numerische Strings wie `"26"` verursachten dagegen einen `TypeError`
beim Vergleich mit der numerischen Mindestschwelle. Negative und boolesche
Werte wurden außerdem nicht konsistent als unbelegt normalisiert; bei einem
Minimum von 0 konnten Booleans wie echte Alterswerte durchgehen.

`"NaN"` und `"Infinity"` als Strings sind gültige JSON-Werte. Zusätzlich
testen die Regressionen direkte Floatwerte und Python-JSONs tolerante
NaN-Dekodierung; eine Behauptung, NaN sei ein standardkonformer JSON-Zahlentyp,
wird daraus ausdrücklich nicht abgeleitet.

## Minimale Korrektur

- `ingest.py::normalisiere_wochen`: akzeptiert endliche, nicht negative
  Zahlen/numerische Strings. None, Booleans, ungültige/nicht endliche/negative
  Angaben werden None. Konvertierungsfehler einschließlich Overflow werden
  abgefangen.
- `ingest.kandidaten` verwendet diese Normalisierung beim Quellenimport.
- `pipeline.build_candidates` verwendet dieselbe Normalisierung nochmals
  für direkte Kandidaten. Eine Kopie verhindert eine Mutation des eingehenden
  Quellkatalogs.
- Ungültiges Alter bleibt auch im Kandidaten-/Begründungs-Payload unbekannt.
  Die explizite Fix-ID-Ausnahme bleibt erhalten: solche IDs werden weiterhin
  gewählt, der ungültige Alterswert wird jedoch nicht als bewiesen ausgegeben.
- Gültiges 0 ist bei Minimum 0 zulässig; die inklusive 26-Wochen-Grenze und
  normale Zahlen/Numericstrings bleiben unverändert.

Keine Forensikformel, keine Schwelle, keine Settings, keine Quelldaten oder
Produktiv-DB geändert. Kein Login/LLM/Terminalstart. Kein Commit/Stage/Push.

## Regressionen und isolierte Nachweise

Neue Datei: `tests/test_deepseek_weeks_validation.py` mit 110 parametrisierten
Fällen für beide Wege (echter Ingestpfad und direkte Kandidaten), Minima
0/26, inklusive Grenze, gültige Numericstrings und Fix-ID-Ausnahme.

Eigenständiger Snapshot `clients_weeks_snapshot/`: `git archive cef1e5a`
plus ausschließlich die neue Testdatei; nach dem Vorherlauf Overlay der zwei
Produktdateien. Alle Test-DBs und `candidates.json` liegen in pytest-Tempdirs.

- **Vorher: 77 fehlgeschlagen, 33 bestanden**, 1,43 s;
  `clients_weeks_before.log` / `clients_weeks_before.xml`. Dies sind
  Regressionstestfälle mit verschiedenen Auslösern/Verträgen, nicht 77
  voneinander unabhängige Produktfehler.
- **Nachher: 205 bestanden, kein Skip, 155,67 s**;
  `clients_weeks_after.log` / `clients_weeks_after.xml`. Enthält alle 110 neuen
  Fälle plus bestehende Fix-ID-, Quellen-/Stringzahlen- und GLM-Regressionen,
  einschließlich Streamlit-AppTests in der Fix-ID-Zielgruppe.
- Produktdiff ausschließlich `ingest.py`, `pipeline.py`; dazu neue
  Regressionstestdatei. `git diff --check` erfolgreich.
- Endgültiger Codefreeze an Root gemeldet. Für den zusätzlichen Produktfix ist
  ein neuer Abschlusssnapshot nötig; der zuvor laufende `Scanner_final2` ist
  kein Nachweis dieser erst später ergänzten Wochenvalidierung.

Der frühere Parserauftrag und sein offengelegter Baseline-Zwischenlauf sind
separat in `clients.md` dokumentiert. Dieser Wochen-Nachtrag wurde vom ersten
pytest-Aufruf an ausschließlich im eigenen isolierten Snapshot geprüft.
