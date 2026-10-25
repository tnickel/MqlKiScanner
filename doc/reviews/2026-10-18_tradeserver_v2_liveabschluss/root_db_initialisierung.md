# Atomare Erstanlage der Scanner-Datenbank

Der umfassende Pythonlauf `scanner_final_regression.xml` zeigte 2.750 bestandene
Fälle und einen Fehler in `test_stufe0_dialog_oeffnet_grosses_fenster`.
Es war ein tatsächliches Parallelitätsproblem, kein zu lockernder Schemavertrag:
SQLite `executescript` veröffentlichte CREATE-Anweisungen einzeln. Ein zweiter
Startzugriff konnte bereits `signal_identitaeten`, aber noch nicht das gesamte
Schema und den Versionsmarker sehen. Die korrekte Schema-Prüfung wies diesen
Zwischenzustand als unvollständig ab.

`db.init_db` veröffentlicht nun alle DDL-Anweisungen und `user_version` in
einer gemeinsamen Transaktion. Die vorausgehende lesende Schema-Prüfung
verwendet einen konsistenten SQLite-Snapshot. Bestehende unvollständige oder
alte Datenbanken werden weiterhin abgewiesen; keine automatische Migration.

Zwei neue deterministische Tests halten die Erstanlage mitten in den
CREATE-Anweisungen an und prüfen sie aus einer unabhängigen Verbindung
beziehungsweise erzwingen einen SQL-Fehler. Leser sehen vor dem Commit
keine halben Tabellen; zwei Initialisierer können abschließen; ein Fehler
hinterlässt weder Teilschema noch gesetzten Versionsmarker.

Gezielte Nachprüfung einschließlich UI, Identitätskern, Migration und
Aktivierung: **89 bestanden, ein Windows-Symlinkfall übersprungen**,
`scanner_atomic_init_tests.xml`. Der erneute Gesamtlauf ist davon getrennt.
