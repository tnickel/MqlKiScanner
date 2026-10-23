# Tradeserver v2, Quellenupdates und aktuelle Datenprüfung

**Pausenstand 18.10.2026, 20:58 MESZ.**
Fortsetzung ausschließlich auf ausdrückliche Nutzeranweisung;
keine automatische Wiederaufnahme und kein Termin.
Der Gesamtabschluss ist offen. In diesem Teilauftrag werden keine weiteren
Prüfungen, Codeänderungen, SDK- oder Quellenaktionen gestartet. Bereits aktive
Jobs werden vom Hauptauftrag separat dokumentiert. Es wurde keine Automation
für die Wiederaufnahme angelegt.

Der genaue gespeicherte Stand und die Reihenfolge für eine ausdrücklich
beauftragte Fortsetzung stehen in [FORTSETZUNG.json](FORTSETZUNG.json).

Gesicherter Checkpoint: **2.803 Tests grün**, 112 Produktionsdateien und 190
Testdateien hashgleich; Remote-Run **13** mit **199** eindeutigen Quellen-UID/ID-
Paaren, **0** aktuellen PDFs und unveränderten Legacy-Originalen **32/313**.
Für eine spätere ausdrücklich beauftragte Fortsetzung offen: FT-Studien mit
eigener strikter Abruf-Nachrunde, belegte
Pelican-Auswahlumfänge, weitere Quellenabschlüsse, aktuelle Berichte und finale
Veröffentlichung mit Remote-Abnahme. Der enge Katalog-/Transportfix ist
getestet; er ist kein Nachweis eines abgeschlossenen gesamten Datenbestands.

Der Nutzer hat Protokollerweiterung, tatsächliche Dienstupdates und die
verbleibenden Datenprüfungen am 18.10.2026 ausdrücklich beauftragt.
Kein Commit/Push. Vorherige uncommittete Korrekturen bleiben erhalten.

## Aktueller Zwischenstand nach der vollständigen Scanner-Abnahme

- Vollständiger Testlauf des aktuellen eingefrorenen Codes einschließlich
  Transport-Restorefix mit der jetzt produktiven gebündelten Python-Laufzeit
  **3.12.14** und denselben User-Site-Paketen: **2.803 bestanden, ein Skip wegen
  fehlenden Windows-Symlinkprivilegs, vier LLM-Tests abgewählt**, Exit 0,
  1.115,30 Sekunden. Alle **112** erfassten Core-/App-/Spezifikations- und
  Settingsdateien sowie alle **190** Python-Testdateien blieben währenddessen
  hashgleich; keine kamen hinzu oder wurden entfernt. Laufzeit, Paketversionen
  und Modulpfade stimmen mit dem vorherigen und dem während dieses Laufs
  erfassten Beleg überein. [JUnit](scanner_final_transport_bundled_full.xml),
  [Hashvergleich](scanner_final_transport_bundled_hash_comparison.json),
  [Laufzeitvergleich](scanner_final_transport_bundled_runtime_comparison.json).
  Der frühere grüne 2.784er Volltest und die 241 gezielten Transporttests bleiben
  als überlappende Nachweise erhalten; ihre Zahlen werden nicht addiert.
  Tests sind kein Nachweis abgeschlossener produktiver Quellenjobs.
- Die drei bestätigten UI-Korrekturen und die begrenzte Bündelung historischer
  H1-Innenlücken sind umgesetzt und abgenommen. Quellqualifizierte Fix-Labels,
  die tatsächliche orange ≈-Zelle und aktueller Workflow-DD in USD sind im
  Browser bestätigt. Native graue `None`-Platzhalter bleiben erhalten; die
  Finanzspalten bleiben numerisch. [Beleg](server_ui_h1_fixes.json).
- Schema-2-Workflowzeilen verloren beim Reload ihre Transportreferenz, weil
  sie nicht mehr als reine Katalogzeilen geliefert werden. Der enge Fix löst
  einen vorhandenen Besitzer über seine exakte aktive Registry-UID und die
  bekannte Plattform auf. Gleiche Anbieter-IDs anderer Quellen, widersprüchliche
  Alias-/UID-/Referenzbelege und unbekannte Plattformen bleiben gesperrt.
  Explizite Spiegel derselben UID behalten die stabile Transportreihenfolge.
  **241 gezielte Tests bestanden**. Der frühere FT-Studienjob verwendete bereits
  belegte frische CSV-SHAs und USD-Metadaten; `fetched=0` dokumentiert die fehlende
  erneute Transportauflösung und ist kein Nachweis eines frischen Abrufs.
  Nach regulärem Jobende folgt eine neue strikte Erhebung und Studienbindung.
  [Regression](scanner_workflow_transport_restore_broad_tests.xml).
- Pelican Top 200: **199 erneuert, einer frisch, keine Downloadfehler**.
  Der anschließende Scannerlauf für 39 Kandidaten endete um 20:21:09 MESZ:
  **33 vollständig, 39 Versuche gespeichert, sechs Fehler**. Drei betreffen
  unbelegte Axi-Kontraktspezifikationen, drei nicht mehr von der Quelle
  gelieferte Signale. Das ist kein fehlerfreier Abschluss aller 39 Signale.
- Die fünf FT-Historien sind mit korrigierter Datensatzidentität vollständig
  neu geladen und über den temporären GET-Dienst auf 8092 geprüft. Alle fünf
  aktuellen Scannerbewertungen sind **rot**: vier haben einen belegten
  Martingale-Befund; drei überschreiten die konfigurierte DD-Grenze 50 %
  (mit Überschneidungen). Der einzige ohne Martingale ist wegen DD rot.
  Zusätzlich fehlt allen fünf die belegte Kapitalbasis. Das verhindert eine
  vollständige eigene Equity-Messung, hebt bekannte harte Ausschlussgründe
  aber nicht auf. Separate virtuelle Studien ersetzen diese Kapitalbasis
  nicht. [Nurlesende Klassifikation](scanner_ft_status_readonly_explanation.json).
  Die älteren FT-Nachrechnungen unten bleiben getrennte historische Nachweise.
- MQL bleibt offen: 48 erfolgreiche Exporte je Plattform belegten nur die
  erste Auswahlseite. Die Live-Gegenprüfung widerlegt den zwischenzeitlichen
  Weg ohne `/list`: der originale Paginator `/list/page2` liefert weitere
  44 Provider mit Abonnenten. Der Folgefix wird separat geprüft und aktiviert.
  Der Logger-Kontextfix ist mit **154 Tests isoliert gebaut**, noch nicht im
  belegten Leerlauf produktiv bereitgestellt.
- Zulu verwendet den neuen **149-Tests-Build**, sein Top-200-Job läuft noch.
  Der Robo-Altlauf ist mit 20 Fehlern beendet. Der neue mit **195 Tests**
  isoliert geprüfte Einheitenvertrag sperrt unbelegte Geld-/Volumeneinheiten
  für Scanner-CSV und Closing-DD; Aktivierung und erneute Abnahme stehen aus.
  [Robo-Einheitenbefund](sources_robo_units_README.md). Bei
  Vantage laufen weitere Vollhistorien außerhalb der fünf fertigen FT-Provider.
  Laufende Zähler sind Momentaufnahmen, keine Abschluss-/Frischenachweise.
- Neuer abgeschlossener Tradeserver-Zwischensnapshot: **Run 13 von
  20:36:58 MESZ mit 199 eindeutigen Quellen-UID/ID-Paaren und null aktuellen
  PDFs**. Der lokale Besitzerhash stimmt mit dem Server überein; kein Lauf
  ist offen. Die 32/313 Legacy-Originale sind unverändert gegen das
  konsistente Backup geprüft. Eine finale Veröffentlichung nach allen
  Quellen-/Studien-/Berichtsabschlüssen steht noch aus.
  [Run-13-Abnahme](server_v2_run13_checkpoint.json); Run 12 bleibt als
  historischer Beleg erhalten.

## Bereits umgesetzt und aktiviert

- MqlTradeMonitor produktiv mit Protokoll v2, Quellenidentität
  `(sourceUid, signalId)`, quellengebundenen PDFs, Run-ID/API-Key-Bindung,
  atomarer Übernahme erst bei Complete und bestandserhaltendem Abort.
- Jahres-Calmar, konfigurierte Schwelle, H1-Messstatus und orange
  Vorbehaltswerte werden vollständig gespiegelt. Legacy-Schwellen bleiben
  unbekannt. Kein v1-Schreibzugriff nach erster erfolgreicher v2-Übernahme.
- Zwei konsistent gesicherte Deployments; finale WAR
  `89d081fc1190d41589e6a3c6a5548e051715fe4417c1de9e989882ed1e3e2615`.
  Alle 32 alten Signale und 313 PDFs sind mit ihren Originalwerten, IDs und
  BLOB-Hashes erhalten. Sie werden keinem heutigen Quellenbesitzer geraten.
  [Serverabnahme](server_README.md), [finaler Scanner-Ping](root_server_final_ping.json).
- Scanneroberfläche nach dem Ende der alten WindowsStore-Python-Prozesse mit
  gebündeltem Python 3.12.14 und denselben User-Site-Paketen wiederhergestellt:
  PID 1639856, Port 8504, Health 200. Die Ursache jener Prozessenden ist nicht
  abschließend belegt. [Aktueller Neustartbeleg](root_scanner_bundled_restart.json).
- Exakte Nikkei-/Sojabohnen-Kontrakte und abgesicherte CNH-/ETH-Umrechnung;
  Forensikversion **21**. EZB bis 16.10.2026 aktualisiert.
  Vier der fünf **alten** FT-Snapshots sind vollständig umgerechnet. Im fünften
  bleiben drei BTCETH-Trades wegen nicht passender eigener Preisereignisse
  gesperrt. Keine Toleranzlockerung und keine erfundene Kapitalbasis.
  [Kontrakte/FX und Grenzen](contracts_README.md).

## Zusätzliche gefundene Fehler

- Unterschiedliche Quellen-UIDs durften über gleichlautende bereinigte Slugs
  nicht dieselben PDF-/Artefaktpfade erhalten. Neue Pfade verwenden Hashes der
  exakten UID; gespeicherte alte Pfade bleiben lesbar. Aliasumbenennungen
  verändern den Besitzer nicht.
- Nach einem frischen Trade-SHA konnten vorher angehängte alte Messfelder
  die Wartungsstudie überspringen. Der neue Wartungsweg rechnet seine
  aktualisierten Eingaben ausdrücklich neu.
- Live-Abnahme darf nicht über intakten Offlinecache vorgetäuscht werden.
  Wartungsabrufe verwenden ausdrücklich `allow_offline_cache=False`;
  der normale bekannte Offline-Teilscan behält seinen bisherigen Vertrag.
- Ein Plattformkonflikt im aktuellen Katalog darf nicht durch das Anhängen
  eines alten Workflow-Kopfs umgangen werden. Unbekannte Plattformen erhalten
  keine MQL5-Vorbelegung. Explizit beauftragte, quelleneindeutige Wartungs-IDs
  dürfen Auswahlvorfilter umgehen, die numerischen Bewertungsgates bleiben
  unverändert.
- Tatsächlicher MQL-Downloadfehler: echte Dateien heißen unter anderem
  `2349227.history.csv`; die zu enge Namensprüfung erkannte sie nicht.
  Korrektur, neue Realformat-Fixtures und aktueller erneuter Job sind belegt.
- Robo-Altcaches mit doppelten Tickets blockierten die Neuerhebung.
  Korrigierte sichere Erneuerung ist getestet; produktive Aktivierung und
  gezielte Nachprüfung erfolgen nach sicherem Writer-Ende.
- Zulu verwechselte Katalog-Trades mit dem Umfang des History-Endpunkts und
  verlor den Seitenfortschritt. Die API meldet im geprüften Fall 48.396
  Trades, nicht 6,79 Millionen. Neue Endbelege sind SHA-gebunden. Zusätzlich
  war der bisher unverwaltete Stufe-0-Thread beim Shutdown unsicher. Der neue
  Lifecycle-/Publikationscode ist produktiv; der belegte kooperative Wechsel
  und der noch laufende neue Job stehen in [zulu_cancel_README.md](zulu_cancel_README.md).

## Laufende operative Arbeit

[Quellenbelege und genaue Umfänge](sources_README.md),
[Zulu-Befunde](zulu_README.md). `sources_live_progress.json` ist ein
veränderlicher Zwischenstand und ausdrücklich kein finaler Hash-/Frischenachweis.
Ein Timeout der Scannerüberwachung beendet keinen Backendjob. `done` mit
Abbruch-/Tradefehlerflag gilt nicht als fehlerfreier Abschluss.

Kataloge wurden bereits ohne Quellenkonflikte eingelesen: 3.022 lokal angebotene
Zeilen zum Zeitpunkt der ersten Synchronisation. Das beweist weder neue Trades
für jeden Provider noch die Vollständigkeit der ursprünglichen Plattformen.
Die Gold-Spike-Neubewertung ist inzwischen gespeichert und in der Oberfläche
mit H1-DD 9,70385 % und Jahres-Calmar 34,04 bestätigt. Das hebt weder offene
Quellenarbeiten noch fehlende aktuelle KI-Berichte auf. Weitere Quellen/IDs
folgen nach überprüfter tatsächlicher Neuerhebung.

Der einmalige Wartungsweg liegt in `scripts/reference/live_abschluss.py`:
SQLite-Onlinebackup, Katalog, Source-Scan, Studien, Berichte, Spiegel, v2-Export
und readonly Abnahme sind getrennte Phasen. Quellen- und ID-Auswahl sind explizit;
der Source-Scan löst keinen zweiten Stufe-0-POST aus. Private Logs, Originaldaten,
Sicherungen und detaillierte Ergebnislisten bleiben unter `data/runs/`.
Das geprüfte Treiberdesign steht in [server_live_driver_review.md](server_live_driver_review.md).

## Abnahme und bewusst erhaltene Grenzen

Offline-Tests, Deployment, tatsächliche Downloads, neue Messungen und echter
v2-Sync werden getrennt belegt. Der erste vollständige Pythonlauf zeigte drei
alte Fixture-Verträge (Mock-Complete ohne JSON-Dict und zwei unregistrierte
Quellen); diese wurden korrigiert und vollständig nachgeprüft. Die zugehörigen
JUnit-Dateien erhalten auch den diagnostischen roten Lauf. Testzahlen sind
nicht über überlappende Gruppen zu addieren.

Produktive DD-Schranke **50 %**, Mindest-Jahres-Calmar **3,0**, keine absolute
Monatshürde, fehlender SL neutral. Alte 1.572 Studien bleiben gesichert in
Quarantäne und werden nicht nach heutiger Eindeutigkeit neu zugeordnet.
Unbelegte Historien-/Kurs-/Kapitalwerte bleiben unbekannt beziehungsweise
vorbehaltlich. Die ausgeschaltete Automatik, MqlRealmonitor und
PelicanWinnerLooser werden durch diesen Wartungslauf nicht freigegeben.
