# Ergänzung: optionale Signalverweise des Agentenjournals

`agenten/journal.py` speichert einen optionalen Signalbesitzer über
`signal_ref REFERENCES signal_identitaeten(signal_ref)`. Ein globaler Lauf ohne
Signal bleibt zulässig. Die vorhandene Spalte `quelle` bedeutet weiterhin
Auslöser (daemon/gui/cli), niemals Datenquelle.

`lauf_starten` verlangt bei Signalbezug die ausdrückliche `signal_quelle` oder
`signal_ref` und prüft widersprüchliche ID-/Quellenangaben. Identitätsanlage und
Laufeintrag erfolgen auf derselben Verbindung und in derselben Transaktion.
`list_laeufe`, `letzter_lauf` und `aktive_laeufe` liefern externe `signal_id`,
aktuelle `signal_quelle`, stabile `signal_ref` und `quellen_uid`. Auch reine
Katalogidentitäten ohne zentralen Signalkopf sind erlaubt.

Legacy-Journale werden nicht still am Produktivbestand umgeschrieben;
`init_journal` verlangt hierfür die zentral koordinierte Copy-Migration.
Die Umsetzung der Legacy-Zuordnung und Quarantäne liegt im separaten
Identitätsmigrationsmodul. Journal-Originaltexte werden durch diesen API-Umbau
nicht geändert. Produktive Läufe oder Migrationen wurden hier nicht gestartet.

Gezielter Nachweis: **65 bestanden**, Exit 0, 9,84 Sekunden, aus
`test_journal_signal_identity.py`, `test_agenten_journal.py`,
`test_agenten_lock_und_scheduler.py`, `test_stufe0_abschluss.py`.
Elf neue Fälle prüfen ID-Kollisionen, fehlende/widersprüchliche Qualifikation,
Null-Bezug, Katalogreferenz, Quellenumbenennung, Transaktionsrollback und
Legacy-Sperre. `ft_journal_command.json`, `ft_journal_tests.log`,
`ft_journal_tests.xml`, `ft_journal_exit.txt` dokumentieren den Lauf.

Die produktive einzelne signalbezogene Aufrufstelle in `agenten/betreuer.py`
wurde parallel im Root-Scope auf ausdrückliche Signalquelle umgestellt. Der
genannte gezielte Lauf umfasst den vollständigen Betreuer-/UI-Pfad nicht;
die gemeinsame Consumerregression erfolgt separat.
