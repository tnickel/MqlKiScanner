# Workflow- und Persistenzreview, 02.10.2026

Basis: Commit `a01b7a3`; rein lesende Prüfung des Produktivcodes. Die
Reproduktionen laufen ausschließlich mit temporärem Speicher, HTTP-Sperre,
Fake-Pipeline oder gemockten Modellantworten. Kein Browser, keine externen
Modellaufrufe, keine Änderungen an Produktivdaten oder laufenden Diensten.

Aktueller Kontext laut Hauptreview: GUI-Lauf mit `listen_modus=beides`,
Agenten-Daemon deaktiviert. Deshalb sind Daemon-Kollision und Monatsmerker
bestätigte latente Fehler, keine Behauptung über einen tatsächlich parallel
laufenden Daemon oder einen bereits fälschlich abgeschlossenen Monat.

## Bestätigte Befunde

### W1 — P1: „Nur Station 6“ führt den ganzen Workflow aus

- Stellen: `app_pages/scan.py:600`, `app_pages/scan.py:1096`.
- Trigger: Expertenbutton „Nur Station 6“ setzt `mode=step_downloader`.
- Ursache: `_worker()` behandelt Station 1–5 einzeln, besitzt aber keinen
  Zweig für `step_downloader`; der abschließende `else` startet Crawl,
  Kandidaten, Forensik, optionale KI/Portfolio und erst danach den Abgleich.
- Wirkung: unerwartete externe Abrufe und je Konfiguration Neubewertungen
  und bezahlte Modellaufrufe bei einem als reiner Abgleich bezeichneten Klick.
- Aktuelle Relevanz: der laufende reguläre Scan wurde dadurch nicht ausgelöst;
  Fehler tritt beim genannten Expertenbutton auf.
- Repro: `test_station6_runs_full_crawl_instead_of_only_sync` führt den
  unveränderten Worker-AST aus und beobachtet `crawl`, `build_candidates`.

### W2 — P1: GUI und Daemon teilen ihren Scan-Lock nicht

- Stellen: `app_pages/scan.py:1153`, `src/mqlkiscanner/scan_worker.py:49`,
  `src/mqlkiscanner/agenten/scan_launcher.py:68`.
- Trigger: GUI-Scan startet, während ein autonomer Scan den Dateilock hält,
  oder umgekehrt.
- Ursache: GUI verwendet ausschließlich die prozessinterne Registry in
  `builtins`; der autonome Launcher verwendet `agenten_lauff.lock`. Die GUI
  erwirbt oder prüft den Dateilock nirgends. Die Daemon-Seite sieht die
  GUI-Registry eines anderen Prozesses nicht.
- Wirkung: beide können dieselben Signale, Cache-Dateien, DB und das
  Scanner-MT5-Terminal gleichzeitig bearbeiten. Atomare Einzeltransaktionen
  schützen nicht vor logisch konkurrierenden Läufen und terminalbedingten
  Unterbrechungen.
- Aktuelle Relevanz: latent, solange der Daemon deaktiviert bleibt. Derselbe
  Schutz fehlt auch zwischen zwei unabhängig gestarteten Streamlit-Prozessen.
- Repro: `test_gui_registry_ignores_existing_daemon_file_lock` hält einen
  echten Lock ausschließlich in `tmp_path` und bestätigt, dass der echte
  `scan_worker.start()` trotzdem startet.

### W3 — P2: Unnötiger MQL5-Login kann Quellen-Forensik komplett verhindern

- Stelle: `app_pages/scan.py:789`–`app_pages/scan.py:803`.
- Trigger: Scope enthält ausschließlich REST-Quellen-Kandidaten; MQL5-
  Credentials sind gespeichert, aber `ensure_mql5_cookies` schlägt fehl.
- Ursache: GUI prüft den MQL5-Login unconditionally vor der Forensikschleife,
  sobald Credentials vorhanden sind. Der Launcher besitzt dagegen den
  passenden `braucht_mql5`-Guard (`scan_launcher.py:198`).
- Wirkung: kein Quellen-Kandidat wird analysiert, obwohl seine Metrics und
  Trades keinen MQL5-Login benötigen. Im Modus `beides` betrifft ein Login-
  Ausfall außerdem die Quellenanteile des gemischten Scopes.
- Aktuelle Relevanz: bedingter Fehler bei Login-Ausfall; kein Nachweis, dass
  der Login des aktuellen laufenden Scans fehlgeschlagen ist.
- Repro: `test_source_only_gui_aborts_on_irrelevant_mql5_login` beobachtet
  einen Login-Aufruf, null Analyse-Aufrufe und Station-3-Status `error`.

### W4 — P2: Autonomer Full-Scan ohne einzige erfolgreiche Forensik gilt als Monatserfolg

- Stellen: `src/mqlkiscanner/agenten/scan_launcher.py:85`,
  `src/mqlkiscanner/agenten/scan_launcher.py:96`,
  `src/mqlkiscanner/agenten/scan_launcher.py:288`–`:299`.
- Trigger: nichtleerer Scope; alle `analyze_candidate`-Ergebnisse sind
  unvollständig/fehlgeschlagen oder Fail-Fast stoppt ohne Erfolg.
- Ursache: `_scan_innerhalb` nennt die Fehlschläge im Text, liefert aber
  keinen fehlgeschlagenen Laufstatus. `starte_scan` behandelt alles außer
  explizitem `skipped` als `ok` und setzt den Full-Scan-Monatsmerker.
- Wirkung: der Monat gilt als versorgt und ein weiterer autonomer Full-Scan
  wird für diesen Monat unterdrückt, obwohl null Signale geprüft wurden.
- Aktuelle Relevanz: latent bei deaktiviertem Daemon.
- Repro: `test_failed_autonomous_month_is_marked_as_success` erhält
  `geprueft=0`, `status=ok`, Text „endgültig fehlgeschlagen“ und gesetzten
  Monatsmerker in einer ausschließlich temporären DB.

### W5 — P2: Teilscan-Details behaupten Prüfung für tatsächlich ausgelassene Slot-Kandidaten

- Stellen: `src/mqlkiscanner/fix_signale.py:136`, `:155`, `:160`.
- Trigger: mindestens zwei Teilscan-Kandidaten derselben Quelle,
  `top_n_export=1` (allgemein mehr Kandidaten als Slots).
- Ursache: `_slot_grund` ignoriert im Teilscan `genommen_` und markiert jede
  Zeile `AUSGEWAEHLT` mit „wird geprüft“, obwohl die reale Auswahl weiterhin
  `gruppe[:limit]` verwendet.
- Wirkung: Station 2 zeigt falsche Auswahlgründe; Station 3 kann „nicht
  geprüft“ und gleichzeitig „wird geprüft … alle Quellen-Slots reichten“
  zeigen. Die reale Forensikgrenze bleibt wirksam.
- Aktuelle Relevanz: nur bei einer Quelle mit mehr Scope-Kandidaten als Slots;
  keine Behauptung, dass diese Bedingung im heutigen Lauf bereits erfüllt ist.
- Repro: `test_unselected_partial_scan_row_is_claimed_selected` bestätigt
  Auswahl `[1]`, aber Status `AUSGEWAEHLT` auch für ausgelassene ID `2`.

### W6 — P2: Station 1 kann während desselben Workflows alte Daten zeigen

- Stellen: `app_pages/scan.py:700`, `app_pages/scan.py:1350`,
  `src/mqlkiscanner/scan_state.py:14`.
- Trigger: langsamer Crawl; Session wird bei Workerstart an den noch leeren
  `control['signals']` angehängt. Crawl beendet sich und der Nutzer öffnet
  Station 1, bevor ein voller Seiten-Rerun/erneutes Attach stattfindet.
- Ursache: Worker ersetzt `control['signals']` durch eine neue Liste.
  `session_state.scan_signals` referenziert weiterhin die vorherige leere
  Liste. Der sekündliche Status-Fragment-Tick synchronisiert sie nicht.
  Station 1 liest die Sessionliste, dann die vorige Auswahl-Datei.
- Wirkung: „Signale holen“ kann bereits fertig sein, aber Stationsdetails
  zeigen noch den vorherigen gespeicherten Lauf. Reload/normaler voller
  Seiten-Rerun und Abschlussübernahme korrigieren den Zustand.
- Aktuelle Relevanz: direkt möglich während des aktiven Workflows; die
  Anzeige enthält dann den Zeitstempel der alten Datei, bleibt also erkennbar.
- Repro: `test_station1_session_data_does_not_follow_current_worker_control`
  nutzt echtes `scan_state.attach_worker` und unveränderten Worker-AST:
  `control['signals']` enthält die neue ID, Sessionliste ist noch leer.

RetDD/Geometrie-None wurde zusätzlich im echten Offline-Forensikpfad
reproduziert; dieser Befund wird im getrennten Berechnungsreview geführt.

## Korrekte Teile des geprüften Pfads

- Prozessinterne Doppelstarts werden atomar durch die Workerregistry
  abgewehrt; Registry in `builtins` überlebt lokale Modul-Neuladungen
  (`scan_worker.py:24`–`:64`). Dies ersetzt den fehlenden Prozesslock nicht.
- Reattach übernimmt dieselben Worker-Dicts/Ergebnisliste; abschließende
  Metadaten werden je Session einmal kopiert (`scan_state.py:20`–`:49`).
- Teilscan erzwingt `nur_neue=False`, `berichte_neu=True` und beide LLM-
  Stufen (`scan.py:635`); Fix-IDs umgehen Vorfilter und Quellen-Slots,
  Teilscan-Scope nutzt die neu berechnete DB-Ampel plus Fix-IDs.
- Stop wird kooperativ vor Stationen, zwischen Signalprüfungen und vor dem
  Gesamtbericht/Portfolio geprüft. Schon bezahlte Modellantworten werden
  gespeichert; ein erfolgreicher Stop wird als Laufhinweis ausgewiesen.
- Fehlgeschlagene Einzelprüfung wird einmal wiederholt; systemischer
  MQL5-Fail-Fast behält das letzte Ergebnis und beendet weitere Abrufe.
  Kursdaten werden im `finally` der Forensikschleife beendet.
- `db.store_scan_result` bestätigt Signal, Trade-Verweis und Forensik in
  einer DB-Transaktion (`db.py:314`). Trade-Dateien werden als unveränderliche
  SHA-256-Snapshots statt als veränderliche Exportcache-Pfade gehalten.
- Workflow-Berichte werden nur mit passender Basis geladen: CSV-Hash,
  Forensikversion/Befunde und Bewertungskriterien; alte Texte bleiben in der
  Historie (`pipeline.py:667`, `:771`).
- Ergebnisarchiv hat eindeutigen Namen und wird vollständig geschrieben,
  geflusht/gefsynct und erst per `os.replace` sichtbar (`pipeline.py:1636`,
  `:1683`).

## Reproduktionslauf

```
$env:PYTHONPATH='src;tests'
python -m pytest -q doc/reviews/laufreview_2026-10-02/workflow/test_workflow_review.py
```

Ergebnis: **7 passed in 0.48s**. Die Tests dokumentieren das gegenwärtige
Fehlverhalten durch Assertions; sie sind Reproduktionen für das Review,
keine Abnahmetests einer bereits implementierten Reparatur.
