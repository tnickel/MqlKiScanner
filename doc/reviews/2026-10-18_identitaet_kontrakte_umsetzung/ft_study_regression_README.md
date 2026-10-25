# Portierung der drei Studientestdateien auf Quellenidentität

Exklusiver Scope:

- `tests/test_studien_spec_nachmessung.py`
- `tests/test_stale_independent_study_display.py`
- `tests/test_virtuelle_messanzeige.py`

Die alten int-key-Caches waren nicht quellenqualifiziert. Die Fixtures verwenden
jetzt `(quelle, signal_id)`; die aus USD-Beträgen gebauten Studienresultate nennen
ihre vorhandene MQL5-/USD-Basis ausdrücklich. Die beiden DB-Lesemocks akzeptieren
die neue Schlüsselwortangabe `quelle` und prüfen, dass sie exakt `mql5` ist.
Keine Produktivdatei wurde für diese Portierung geändert.

Alle bisherigen fachlichen Assertions blieben erhalten: RAW statt gerundetem
DD, 30,004 Prozent über der 30-Prozent-Schranke, virtuelle Erträge inklusive
echter Null, keine Workflowfreigabe aus virtuellen Studien, Anzeige einer
unabhängigen Studie bei veralteter Engine, kurze Historie ohne Renditeverhältnis,
Teil-/Fehlmessungsgründe, Originalbroker statt Referenzfeed und Erhaltung einer
gültigen Teilmessung nach einem schlechteren Nachversuch.

Aktueller gezielter Lauf: **29 bestanden**, **Exit 0**, **1,93 Sekunden**.
`ft_study_regression_command.json`, `ft_study_regression.log`,
`ft_study_regression.xml`, `ft_study_regression_exit.txt` dokumentieren den
Befehl und das Ergebnis. Die Fehler des ursprünglichen Gesamtlaufs stehen
unverändert in `root_regression_initial.xml/log`.

Keine Schutzregel wurde abgeschwächt, kein fachlicher Sollwert geändert und kein
Test ausgeschlossen. Der gezielte Lauf zeigte nach der Fixture-Portierung
keinen zusätzlichen Produktivcodefehler; er ersetzt nicht die gemeinsame
abschließende Gesamtregression. Kein Live-Cutover, keine produktiven Studien,
keine API- oder Terminalzugriffe.
