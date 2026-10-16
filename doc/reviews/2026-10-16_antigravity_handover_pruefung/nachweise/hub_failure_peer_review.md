# Peerprüfung neuer Hub-Fehlerpfade

Geprüft am 16.10.2026: `llm/client.py`, `db.py`, `tradeserver_sync.py`,
`config.py`, `tiefen_batch.py` im aktuellen Scanner-Diff. Keine Produktänderung
durch diesen Peer; kein Live-HTTP, keine echte DB/Settings verwendet. Allgemeine
Budgetpolitik und Root-Gesamttest lagen ausdrücklich außerhalb des Auftrags.

## Bestätigter neuer Fehler, inzwischen korrigiert

Der neue Auditwriter stand nach Empfang einer HTTP200-Antwort vor deren
Kostenbuchung. Ein SQLite-Auditfehler ließ bekannte bezahlte Nutzung aus
`client.usage` und `meta_out` verschwinden, während finally die Reservierung
korrekt freigab. Unabhängiger AST-Repro mit gültiger Nutzung 100 Tokens:
Kontrolle usage100/meta100/requests1; Auditfehler usage0/meta fehlend/requests0,
inflight jeweils0. Beleg: `hub_audit_write_peer_probe.json`.

Der zuständige Hub-Agent korrigierte diesen Fehler minimal. Er erhält bekannte
Nutzung und Komponenten vor dem lokalen LlmError und bewahrt die rohe Antwort
im Fehler-Meta. Keine neue bezahlte Wiederholung bei lokaler Auditstörung.
Unabhängige Nachprobe mit `finish_reason=stop` und `length`: jeweils genau ein
HTTP-Stub, usage100, prompt60, completion40, meta100, inflight0 und klarer
lokaler Auditfehler. Beleg: `hub_audit_write_peer_after.json`; geprüfter
Client-SHA256 `43a50312874d966b0be536e8d2917b76ac1819adcb1d93411e50f1ddfe15dc88`.
Die normale Retry-Abrechnung addiert rohe Responseusage genau einmal zur
Clientusage und summiert die Meta-Komponenten über die Versuche; kein
Doublecharge-Befund.

## Weitere unabhängige Fehlerpfadproben

`hub_sync_failure_peer_probe.json` enthält sechs AST-Proben der aktuellen
Syncfunktionen mit synthetischem Client/DB/Lock: Erfolg, Snapshotvorbereitung
defekt, Register-, Signals-, Complete-Fehler sowie abschließender DB-Schreibfehler.
Alle geben Mutex und Workflow-Lock frei. Vorbereitungs-/Transportfehler landen
als abgebrochen; nach erfolgreichem Register folgt bestmöglich abort. Ein
abschließender DB-Schreibfehler wird weitergereicht und hält kein Lock fest.
Ein unbeschreibbarer DB-Abschluss kann naturgemäß keinen geschlossenen Status
persistieren; der Fehler wird nicht als Erfolg ausgegeben. Keine weitere
konkrete Regression festgestellt.

`hub_deep_batch_failure_peer_probe.json` enthält vier AST-Proben: Erfolg,
Threadstartfehler, Logcallbackfehler und Worker-DB-Fehler. Alle geben das
Workflow-Lock genau einmal frei. Startfehler entfernen das Register, Worker-
Fehler setzen fertig/abgebrochen und Fehlerzähler. Die Proben steuern den
Worker synchron über einen Stub und beweisen Kontrollfluss, keine realen
Thread-Scheduling-Eigenschaften.

Config schreibt erst vollständig in eigene Tempdatei, fsync, danach Replace;
finally entfernt die Tempdatei. Serialisierungsfehler liegen vor Dateimutationen;
defektes Settings-JSON aktiviert nicht still Defaults. Neue DB-Methoden verwenden
parameterisierte SQL-Statements und getrennte Transaktionen. Neuester Quellen-
Updateeintrag wird je Kürzel über MAX(id) ermittelt statt über ein globales
500-Zeilen-Limit. Keine weitere konkrete Fehlerstelle in diesem engen Scope.

Die zehn zusätzlichen Lock-/Statusproben und zwei Audit-Nachproben sind reine
isolierte Funktionsproben, keine zusätzlichen vollständigen Pytest-Läufe.
Breitenprüfung und endgültige Testzahlen übernimmt Root.
