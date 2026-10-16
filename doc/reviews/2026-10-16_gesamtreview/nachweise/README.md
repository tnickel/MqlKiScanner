# Review-Nachweise

Diese Dateien enthalten ausschließlich Reviewcode, synthetische Ergebnisse und Testlogs.
Keine Cookies, echten Trade-Caches, Datenbanken oder geheimen Einstellungen wurden kopiert.

Die vollständige lokale Laufumgebung liegt unter
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16`.
Die Reproskripte sind gegen dort eingefrorene Git-Archive geschrieben; sie erwarten
die im jeweiligen Skript genannten Snapshotpfade. Bei Wiederholung entweder diese
Archivstruktur aus den sechs Commits in revisions.json herstellen oder die
Snapshotkonstanten auf entsprechende saubere Checkouts setzen. Niemals produktive
Datenverzeichnisse als synthetisches Ausgabeziel verwenden.

Die Probes bestätigen absichtlich die damaligen Fehlerzustände. Erfolgreiche Assertions
bedeuten, dass ein Gegenbeispiel reproduziert wurde. Sie sind keine bestandenen
Regressionstests einer Reparatur. Die vorhandenen Suiten wurden getrennt ausgeführt.

- Python: Scanner `pytest -q` in `scanner/snapshot`; LLM-Marker ist standardmäßig aus.
- Java: je Snapshot `mvn -o test`; JDK25 und Maven3.9.6 benutzt.
- Finanzkern: `finanzen/repro_finance.py`, 18 Fallgruppen / 12 Orakelkontrollen.
- Scannerintegration: `scanner/test_review_hub_repros.py`, 9 Istzustandsnachweise.
- Quellen A: AuditProbe.java mit den drei Surefire-Classpaths; FakeHttp / lokale REST-Ports.
- Quellen B: run_probes.ps1 und die drei Java-Probes; anschließend check_scanner_csv.py.

Wenn der Windows-Store-Pythonlauncher hängt, einen vorhandenen Python3.12-Interpreter
mit dem passenden lokalen site-packages verwenden; im Review wurde dafür nichts installiert.
Die genauen Interpreterpfade und Befehle stehen in den Teilberichten.

Die vier übersprungenen Scanner-Originalexporttests brauchen private optionale Snapshots.
Ihre Gründe stehen in test_results.json. Diese privaten Daten wurden nicht veröffentlicht.
