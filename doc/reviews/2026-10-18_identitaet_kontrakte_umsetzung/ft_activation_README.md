# Explizite Aktivierungshilfe, ausschließlich an TempDBs getestet

API in `src/mqlkiscanner/identity_activation.py`:

```python
activate_candidate(
    live_path, candidate_path,
    expected_live_sha256=approved_live_sha256,
    expected_candidate_sha256=approved_candidate_sha256,
    lock_basis=actual_shared_data_dir,
)
```

Kein Appstart-Hook, kein automatischer Cutover, keine Prozesssteuerung.
Alle Quellen-/Writerprozesse müssen vor dem ausdrücklichen Aufruf stillstehen.
Die freigegebene Kandidaten-/Quarantänebilanz und der erhaltene Rollbacksnapshot
bleiben Voraussetzung des Aufrufers. Ein neuer Live-SHA nach einer Änderung macht
einen älteren Kandidaten nicht automatisch aktuell; das freigegebene Paar muss
aus demselben überprüften Migrationsstand stammen. `lock_basis` muss das wirklich
von Scanner und Agenten gemeinsam verwendete DATA_DIR sein.

Der Helfer prüft absolute lokale Pfade ohne Symlink/Junction/Reparse-Punkt,
unterschiedliche Dateiidentitäten, gültige erwartete SHA-Werte und das Fehlen
aller vorhandenen WAL-/SHM-/Journal-Dateien, auch leerer. Er hält das gemeinsame
Lauflock und alle fünf Rollenlocks. Die Kandidatdatei bleibt unter einem nativen
Windows-Handle `GENERIC_READ / FILE_SHARE_DELETE` gegen andere Lese-/Schreibhandles
gesperrt. Genau deren Bytes werden gehasht, in RAM eingefroren und privat auf
`user_version=2`, aktuellen `db._check_schema`, Integrität und Fremdschlüssel
geprüft. Der Kandidat muss als geschlossenes DELETE-Datenbankabbild vorliegen.

Das Liveziel verwendet einen durchgehenden SQLite-Exklusivlock: EXCLUSIVE vor dem
ersten Datenbankzugriff, dann BEGIN EXCLUSIVE/COMMIT. Dieser Modus behält Locks
bis zum Schließen der Verbindung; damit besteht zwischen Live-SHA-Prüfung und
Backup kein Freigabefenster für SQLite-Leser/Schreiber. Das entspricht der
[offiziellen PRAGMA-Dokumentation](https://www.sqlite.org/pragma.html#pragma_locking_mode).
Die eigentliche Kopie vom privaten RAM-Kandidaten erfolgt als eine SQLite-
Backuptransaktion. Die API hält das Ziel währenddessen exklusiv; ein Abbruch vor
SQLITE_DONE rollt die Zieltransaktion zurück, gemäß
[SQLite Backup API](https://www.sqlite.org/c3ref/backup_finish.html).

Ein Live-WAL-Header ohne vorhandene Seitendateien wird unterstützt. EXCLUSIVE
wird vor dem ersten WAL-Zugriff gesetzt, damit keine gemeinsam benutzte SHM
entsteht. Ein eigener anfänglich leerer WAL wird nach erfolgreichem Backup unter
derselben Sperre durch SQLite checkpointed; SQLite entfernt eigene Seitendateien
beim normalen Schließen. Fremde oder neu befüllte WAL-Seiten vor dem Backup
blockieren. Es gibt kein manuelles Löschen von WAL/SHM/Journaldateien.
Die Grundlagen sind in der
[SQLite-WAL-Dokumentation](https://www.sqlite.org/wal.html#use_of_wal_without_shared_memory)
beschrieben. Bei WAL müssen Quell- und Zielseitengröße übereinstimmen.

Die Rückgabe meldet `activated=True`, `method="sqlite_backup_exclusive"`,
`previous_live_sha256`, `candidate_sha256`, `activated_sha256`, `journal_mode`,
Schema 2 und UTC. Der physische Live-SHA darf wegen SQLite-Headerzählern und
beibehaltenem Journalmodus vom Kandidaten-SHA abweichen; die Zielinhalte und das
Schema werden geprüft. Kandidat und Rollbacksnapshot bleiben unverändert.
Fehler nach bestätigtem SQLITE_DONE werden als
`IdentityActivationCommittedError` mit `activated=True` kenntlich gemacht;
BaseExceptions nach DONE tragen `activation_committed=True` und werden
weitergeworfen. Niemals wird eine alte DB blind zurückkopiert.

Native Umbenennung ist ausdrücklich kein Fallback: Die vorherige Tempdatei-
Matrix auf C: und D: zeigte WinError 5 bei `os.replace` und bei
`SetFileInformationByHandle(FileRenameInfo)` mit gehaltenem Livehandle.
Ohne Livehandle funktionierten die Kontrollfälle. Die ursprünglichen
synthetischen Nachweise stehen in `ft_activation_handle_probe.json` und
`ft_activation_native_probe.json`; keine produktive Datei wurde dafür geöffnet.
Die Share-Semantik ist in
[Microsoft CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
und der native Namensvertrag in
[FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info)
dokumentiert. Der schließlich implementierte Aktivierungspfad verwendet keine
dieser Umbenennungen.

Aktueller Testnachweis: **47 bestanden, 1 übersprungen**, Exit **0**, 12,19 s.
Der übersprungene Fall benötigt Windows-Symlinkrechte (WinError 1314), die in
dieser Umgebung fehlen. Nachgewiesen sind erfolgreiche DELETE-/WAL-Aktivierung,
unveränderte Kandidaten-/Rollbackbytes, Version/FKs/Integrität, Sperren vor,
während und nach Backup gegen nebenläufige SQL-Leser/Schreiber, SHA-Abweichung
ohne Backupaufruf, tatsächlicher bytegenauer Rollback bei erzwungenem Fehler
vor DONE in beiden Journalmodi und die eindeutige Meldung eines Fehlers nach
Commit ohne Legacy-Restore. Weitere Fälle prüfen seitliche Dateien, Schema-
Fehler, aktive Transaktionen, Locks, harte Dateialiases und Pfadgrenzen.

`ft_activation_command.json`, `ft_activation_tests.log`,
`ft_activation_tests.xml`, `ft_activation_exit.txt` dokumentieren den Lauf.
Danach wurde ausschließlich ein veralteter Kommentar zum nicht mehr verwendeten
Renamepfad korrigiert; das Laufverhalten blieb unverändert. Die gemeinsame
Vollregression und jede echte Aktivierung liegen bei Root. In diesem Auftrag
wurde **keine echte Aktivierung** vorgenommen.
