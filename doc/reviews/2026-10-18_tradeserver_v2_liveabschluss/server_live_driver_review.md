# Gegenprüfung des einmaligen Live-Abschluss-Treibers

Stand18.10.2026. Dies ist ein geprüftes Design, keine implementierte Automation
und kein gestarteter Produktivlauf. Root bearbeitet den Wartungscode.

## Abnahme des vorhandenen Wartungsskripts

`pytest -q tests/test_live_abschluss.py tests/test_live_abschluss_source_scan.py`
→25bestanden (2Studienrefresh-Fälle,23Source-Scan-Fälle). JUnit:
`server_maintenance_tests.xml`. Reale ingest-Normalisierung, Pipeline-Vorfilter
und Top-N/Fix-Auswahl werden getestet; Netz/Forensik/Terminals sind isoliert.

Ursprünglich reproduzierte Fehler: unbekannte alte Plattform erlaubte den
späteren MQL5-Fallback; ein aktueller MT4/MT5-Quellenkonflikt konnte durch
Wiederanfügen eines alten Workflowkopfs umgangen werden. Root hat beide
Sperren ergänzt, einschließlich expliziter `blocked`-Gründe. Die25Tests sind
danach grün. Der separate ältere Studien-SHA-Befund wurde von Root durch
explizite Neuberechnung (`nur_luecken=False`) korrigiert.

## Vorgeschlagener einmaliger CLI-Treiber

Ein langlebiger CLI-Prozess beobachtet nur bereits akzeptierte Quelljobs und
startet pro fertiger Quelle drei kurzlebige Python-Unterprozesse, seriell:
`catalog --source Q` →`source-scan --source Q` →`studies --source Q`.
Er ruft niemals `scan`, `starte_scan`, `starte_alle_updates` oder POST/update auf.
Andere Quelljobs dürfen währenddessen fertig werden. Es läuft immer höchstens
eine Scanner-/Studienphase mit dem vorhandenen gemeinsamen Lauf-Lock.

Der Treiber erhält `--live --expected-version21 --manifest <privaterPfad>`.
Das private Manifest bindet:

- eindeutige Abschlusslauf-ID und UTC-Erstellungszeit;
- SHA256 der sortierten produktiven Pythonquellen, CLI-Dateien, Kontraktspecs
  und relevanten Einstellungen; zusätzlich FORENSICS_VERSION und Python-/Paket-
  Versionen; GitHEAD allein reicht wegen uncommitteter Änderungen nicht;
- pro Quelle stabile Quellen-UID, Transport-ID, damaliges Kürzel, normalisierte
  BaseURL, belegte Backend-Instanz sowie akzeptierte Update-Job-ID und Startbeleg;
- bei schon laufenden übernommenen Jobs ausdrücklich `adopted`, keine erfundene
  eigene Startzeit. Fertige Altmeldungen ohne passenden aktuellen Start-/Übernahme-
  Beleg werden nicht als neuer Updateerfolg akzeptiert.

Vor jeder Phase und danach: CodeSHA/Version/Settings unverändert, Quelle aktiv,
UID/Transport/URL/Instanz passend; aktueller Backendstatus hat exakt dieselbe
nichtleere Job-ID, `state=done`, kein Fehler, kein Tradelistenabbruch und keine
Tradelistenfehler. Dafür rohe Statusantworten prüfen: fehlende oder typfalsche
Ergebnisfelder sind unbekannt, nicht automatisch0/False wie in einem
abwärtskompatiblen Normalisierer. `done` allein genügt nicht. Der zulässige Katalogcache-Hinweis
(72h-Regel) bleibt im Beleg sichtbar und wird nicht als neuer Vollkatalogdownload
beschrieben. Zulu bleibt bis zur getrennten Qualitätsabnahme gesperrt.

Der Treiber pollt andere offene Quellen z.B. alle15Sekunden und kann Fortschritt
fortlaufend privat schreiben. Keine pauschale Zwei-Stunden-Erfolgsannahme und
kein automatischer neuer POST bei langem Job. Quelle mit `error`, Abbruch,
Timeout, `idle`, anderer/fehlender Job-ID oder Instanzwechsel wird blockiert.
Andere erfolgreich gebundene Quellen können weiterlaufen. Eine teilweise
aktualisierte Quelle darf separat als teilweise geprüft werden, aber niemals
als frischer Gesamterfolg in dieselbe Erfolgswarteschlange gelangen.

Jede Phase läuft in einem neuen Interpreter mit Argumentliste (`shell=False`)
und eigenem Beleg-Unterordner. Vor dem Start wird ein atomarer started-Beleg
mit manifestSHA, Quelljob, CodeSHA und Version geschrieben; danach werden
Exitcode, CLI-Ergebnisbeleg und dessen SHA gebunden. Nur Existenz einer JSON-
Datei oder Exitcode0 gilt nicht als Erfolg: Katalogfehler, `blocked`, nicht
persistierte Forensik, Studienfehler/-abbruch/-skips und unvollständige Messungen
bleiben im Ergebnis sichtbar. Bei Studien müssen Worker-Ende und `fertig=true`
plus Phase/Fehlerliste geprüft werden. Fehler einer Quelle werden nicht durch
die erfolgreiche nächste Quelle überschrieben.

Wiederaufnahme akzeptiert nur identische Manifest-/Code-/Jobbindung und vollständig
abgeschlossene Belege. Ein started-Beleg ohne Ende ist unbekannt, kein Erfolg;
keine doppelte Phase starten, solange ihr Prozess oder Lauf-Lock noch lebt.
Ein neuer Code-/Modellstand verlangt eine neue manifestierte Generation und
gezielte Neuberechnung. Bei Stop keine weitere Phase starten; laufende Studien
kooperativ abbrechen/auf Cleanup warten, keine Terminal-Prozesse blind beenden.

Nach dem seriellen Quellenabschluss: `verify` separat. Reports, Portfolio und
Tradeserver-Publish bilden explizite spätere Phasen; kein alter Portfoliobericht
wird automatisch als neue Bewertung publiziert. Ein v2-Ping ist Voraussetzung
für Publish; finale Source-/Studien-/Report-SHA-Bindungen werden davor geprüft.
Die Automatik-/Daemon-Einstellung wird dabei nicht verändert.

## Frische-Grenze und inzwischen implementierte Wartungssperre

`ingest.hole_trades` kann nach einem ConnectionError intakte alte Bytes liefern;
`hole_metrics` erlaubt ebenfalls standardmäßig Offlinecache. Deshalb bewies
`lade_signal_daten`-Erfolg/`fetched+=1` vor der folgenden Root-Korrektur nicht,
dass ein frischer GET gelang.
Auch `geaendert=False` unterscheidet online-identische Bytes nicht von Offline-
Fallback; `fetched_at` bleibt bei unverändertem Onlinecache alt. Ein fertiger
Quelljob plus gültiger SHA ist nur Jobabschluss plus Inhaltsintegrität.

Root hat für diesen ausdrücklichen Liveabschluss jetzt
`allow_offline_cache=False` durch Wartungs-Studien und Wartungs-Scan bis zu
Metrics/Trades-GET ergänzt; Pipeline-Option `allow_offline_source_cache=False`.
Normale Offline-Teilscans behalten ihr bisheriges DefaultTrue. Die neuen
SourceScan-Tests prüfen die explizite Strict-Option; Root testet zusätzlich den
echten Offlinecache-Fehlerpfad. Alternativ braucht jeder akzeptierte Artefaktabruf einen separaten
Onlinebestätigungsbeleg mit Zeitpunkt, UID/ID/Version und SHA; ohne einen dieser
Wege darf der Treiber keine behauptete neue Artefaktprüfung aus Cache ableiten.

Die GET-Antworten sind nicht an einen Backend-Snapshot-Epoch gebunden. Status-
prüfung vor/nach den Phasen erkennt Jobwechsel, ersetzt aber keinen solchen
Serververtrag. Verlässlich belegt werden können deshalb konkrete eingefrorene
Artefaktbytes und ihre Hashes; kein unbelegter atomarer Weltbestand der Quelle.


## Ergänzte UID-Cachetrennung

Auf ausdrücklichen Zusatzauftrag wurde ausschließlich
`ingest._kuerzel_verzeichnis` eng gepatcht. Neue Schreibpfade verwenden
`owner-` plus vollen SHA256 der exakten Quellen-UID. Anzeigename, Regex-
Bereinigung, Groß-/Kleinschreibung oder Unicode-Normalisierung können dadurch
keinen Besitzer zusammenlegen. Aliasrename/ausdrücklicher Transportersatz mit
selber UID behalten den Besitzerpfad. UIDlose synthetische Dicts erhalten einen
klaren `unverified-`-Hash aus ID/Kürzel/URL; keine Registry wird angelegt und
keine Besitzer-UID erfunden. Gespeicherte ältere DB-Dateipfade bleiben lesbar.

`tests/test_ingest_owner_cache.py` enthält10Fälle: reale registrierte Quellen
mit kollidierenden Aliasen, gleiche externe ID/verschiedene Bytes, Rename,
Mirror mit gleicher UID, Case-/Unicode-/Traversaltrennung, UIDloser Fallback
und intakte ältere Trade-/Metrics-Cachepfade. Zusammen mit den23SourceScan-
Fällen **33bestanden**, JUnit `server_cache_maintenance_tests.xml`. Kein
Produktivscan/Upload im Zusatzauftrag ausgeführt.


Praktischer Aufrufvorschlag (Datei erst von Root zu implementieren):
`python scripts/reference/live_abschluss_driver.py --live --expected-version21
--manifest data/runs/<lauf>/abschluss_plan.json --manifest-sha256 <SHA>`.
Manifest und veränderlicher Fortschritt sind getrennte Dateien. Bereits laufende
Backend-Jobs werden nur aus den ausdrücklich übernommenen akzeptierten IDs
beobachtet, auch länger als zwei Stunden. Es wird kein neuer Job gestartet,
um eine Wartefrist zu umgehen. Vorhandener Beobachter-Timeout ist kein Beleg
für Backend-Abbruch oder Backend-Erfolg; ausschließlich der identische rohe
Jobabschluss liefert diese Aussage. Nutzerabbruch darf nicht stillschweigend
als Wiederaufnahmefreigabe behandelt werden.

Nach aktualisierter Root-Strict-Durchreichung plus Cachepatch abschließende
gezielte Prüfung: **35bestanden** (10Cache,23SourceScan,2Studienrefresh),
`server_maintenance_final.xml`. Produktivcode ist für diesen Teilauftrag ab
jetzt eingefroren; der breitere Lauf einschließlich der40bestehenden Quellenfälle ist ebenfalls
abgeschlossen: **74bestanden in199,48s**. Dieser Lauf hatte9Cachefälle vor
Ergänzung des zehnten gesammelt; der zusätzliche reale Zwei-Quellen-Bytefall
ist im abschließenden35er-Lauf grün. Diese überlappenden Testzahlen werden
nicht addiert.
