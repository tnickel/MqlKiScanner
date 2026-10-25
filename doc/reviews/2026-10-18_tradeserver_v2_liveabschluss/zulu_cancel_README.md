# Zulu: kooperativer Abbruch, Shutdown und atomare Archivgenerationen

Der neue Build behebt die bestaetigten Lifecycle- und Publikationsfehler.
Waehrend der Implementierung und der isolierten Tests blieb die produktive
Altinstanz unveraendert. Anschliessend wurde der lange Altjob durch den unten
belegten, separat getesteten Schutz kooperativ abgebrochen und die Instanz
normal geschlossen. Der gepruefte neue Build ist seit 18.10.2026 produktiv;
sein vollstaendiger neuer Top-200-Updatejob laeuft noch.

## Abbruchvertrag

`POST /api/v1/update/cancel` verwendet dieselbe konfigurierte API-Tokenpruefung
wie der Update-Start. Der JSON-Body muss die **exakte aktuelle** `jobId`
enthalten. Eine fehlende ID ergibt HTTP 400, eine andere/alte ID HTTP 409,
ein fehlender Job HTTP 404 und ein bereits abgeschlossener Job HTTP 409.
Damit kann ein verzoegerter Client keinen inzwischen neu gestarteten Job
abbrechen. Solange derselbe Abbruch noch aussteht, ist die Anforderung
wiederholbar.

HTTP 202 bestaetigt nur `cancellationRequested=true`. Der Job bleibt bis zur
Bestaetigung durch seinen Worker aktiv. Danach meldet
`GET /api/v1/update/status` **`state=cancelled`**, einen Abschlusszeitpunkt und
`ergebnis.datenstand=null`. Er wird weder als `done` noch als Quelle mit
erfolgreichem Gesamtdatenstand ausgegeben. Einzelne bereits abgeschlossene
Provider-Archive bleiben bestehen. Auch ein Interrupt beim letzten Provider
kann den Job nicht mehr versehentlich erfolgreich abschliessen.

Offene HTTP-Anfragen laufen ueber `sendAsync`. Der Worker prueft den
kooperativen Abbruch alle 100 ms und bricht den Transport ueber dessen
Future ab; Retry- und Drosselungspausen beachten dasselbe Flag. Das ist kein
`Thread.stop` und keine nachtraegliche Thread-Injektion. Eine laufende
Archivpublikation wird nicht durch ein Shutdown-Threadinterrupt zerrissen:
Abbruchpruefungen liegen vor und nach dem Publikationsabschnitt. Ist ein
Provider bereits atomar veroeffentlicht, bleibt dieses Ergebnis erhalten;
der Gesamtjob kann danach trotzdem `cancelled` sein.

Ein zur GUI-Ausfuehrung vorgemerkter Job reserviert bereits seinen Zustand
und seine ID. Ein zweiter REST-Start vor dem ersten GUI-Callback erzeugt
keinen zweiten, spaeter unerreichbaren Job. Fortschritts- und terminale
Zustandsuebergaenge sind gemeinsam synchronisiert; spaete Meldungen oeffnen
einen abgebrochenen oder abgeschlossenen Job nicht wieder.

## Application.stop und Ressourcenbesitz

Stufe 0 benutzt jetzt dieselbe Worker-Verwaltung wie die anderen Aktionen.
Die Worker sind **nicht daemonisiert**. `Application.stop()` fordert den
Jobabbruch an, setzt das globale Client-Abbruchflag, beendet den REST-Server
und wartet bis zu fuenf Sekunden auf die registrierten Worker. GUI-Tasks
werden mit `cancel(false)` markiert; ihre Publikationsphase wird nicht
unterbrochen.

Sollte ein ungewoehnlich langsamer Writer laenger brauchen, bleibt sein
nicht daemonisierter Thread mit den benoetigten Ressourcen am Leben. Die
Abonnenten-DB wird erst im `finally` des letzten Workers geschlossen. Die
JVM kann diesen Writer beim Schliessen des Fensters nicht still verwerfen.
Die Tests pruefen sowohl den normalen Join als auch diese Deadline-Grenze.

## CSV, Integritaetsmarker und History-Endbeleg: ein Commit

Neue geschlossene Trade-Archive werden unveraenderlich unter
`data/trades/.generations/<provider>/<uuid>/` geschrieben:

- `trades.csv`: ungerundete CSV mit Anbieteridentitaet und vorhandenen UTC-Instants.
- `archive.meta`: Anforderung, Anzahl und SHA derselben CSV-Bytes.
- `history.receipt`: optionaler, SHA-gebundener History-End-/Pagingbeleg.

Der produktive Downloadpfad uebergibt alle History-Metadaten gemeinsam an
`mergeTrades(..., HistoryEvidence)`. CSV, Marker und Endbeleg werden vollstaendig
geschrieben und erzwungen, bevor genau **ein atomarer Move** von
`trades_<provider>.current` die Generation aktiviert. Fuer diesen Commit gibt
es keinen nichtatomaren Fallback. Das Datum/Total des Katalogs erzeugt keinen
History-Beleg.

Fehler oder Abbruch vor dem Pointerwechsel lassen den vorherigen Pointer
und das bisherige verifizierte Archiv unveraendert. Ein Fehler nach dem
sichtbaren Wechsel wird ausdruecklich als `PublicationCommittedException`
mit `activated=true` und CSV-SHA gemeldet; er darf nicht als Rollback behandelt
werden. Auch der Fall, dass der Dateisystemaufruf den Wechsel bereits ausgefuehrt
hat und danach einen Fehler meldet, wird am exakten neuen Commitrecord erkannt.

Flache Altarchive bleiben unveraendert lesbar, solange fuer diesen Provider
kein Pointer existiert. Ein vorhandener beschaedigter Pointer fuehrt zur
Ablehnung; er wird nicht durch einen stillen Rueckfall auf alte flache Dateien
verdeckt. DataStore-Leser teilen pro Provider einen stabilen Lock und koennen
Zeilen, Integritaets-SHA und Receipt als **einen Snapshot** erhalten. REST nutzt
diesen Snapshot fuer CSV, JSON und Metrics. Die `lastUpdated`-Angabe zeigt auf
die ausgewaehlte Generation.

Es wurde keine automatische Loeschung alter Generationen eingefuehrt. Auch
fehlgeschlagene, nicht ausgewaehlte Staging-Generationen bleiben als
Wiederherstellungsbelege erhalten. Das erhoeht den Speicherbedarf bei weiteren
Updates; eine spaetere Aufbewahrungsregel muss aktuelle und benoetigte
Vorversionen gezielt schuetzen. Kein Teilverzeichnis wird allein wegen seiner
Existenz als aktives oder verifiziertes Archiv ausgegeben.

`TradesHistoryComplete` bleibt eine **zusaetzliche End-/Pagingdiagnose**.
Es ersetzt weder den davon verschiedenen `TradeHistoryComplete`-Input-/UTC-Beleg
noch eine forensische Bewertungsregel. Unbekannt bleibt `null`. Katalogzaehler,
Seitenende, Historienumfang und Eingabeintegritaet bleiben getrennt.

## Abnahme

Die vollstaendige neue Zulu-Maven-Suite hat **149 bestandene Tests**, keine
Fehler und keine ausgelassenen Tests (`mvn test -q`, Exit 0). Der erste
129er-Lauf in `zulu_tests_*` bleibt ein historischer Nachweis des vorherigen
Fortschritts-/History-Fixes. Fuer den finalen Code gelten
`zulu_cancel_tests_summary.json`, `zulu_cancel_tests.log`,
`zulu_cancel_tests_exit.txt` und `zulu_cancel_TEST-*.xml`.

Die gezielten neuen Faelle pruefen blockierenden HTTP-Transport, Abbruch vor
Publikation, Abbruch waehrend eines beendeten Provider-Commits, den letzten
unterbrochenen Provider, Authentifizierung und exakte Job-ID, wartende
GUI-Jobreservierung, normalen Shutdown-Join und sicheren Weiterlauf nach der
Shutdown-Deadline. Elf Publikationsfaelle decken CSV-/Meta-/Receipt-Fehler,
nicht unterstuetzten atomaren Move, Interrupt vor Commit, Fehler nach Commit,
unklares Move-Ergebnis, defekten Pointer, Legacy-Erhalt und konkurrierende
Snapshot-Leser ab. Die Publikationsimplementierung und die Cancel-Verdrahtung
wurden zusaetzlich unabhaengig gegengeprueft.

## Sicherer Wechsel der alten Instanz

Der Altjob `u-20261018-184200-b328fbb6` hatte zehn Provider abgeschlossen.
Provider 429450 war mit **48.396 Zeilen** veroeffentlicht; eine Endlosschleife
bis zur Katalogzahl 6.794.903 war damit widerlegt. Die verbleibenden alten
Caches entsprachen jedoch rund **7.427 weiteren 100er-Seiten**. Szenarien von
einer bis fuenf Sekunden je Seite bedeuten zwei bis zehn Stunden; das war
ausdruecklich keine zuverlaessige ETA. Ein direkter Interrupt war unsicher:
Der alte Runner schluckte ihn als Providerfehler und konnte danach noch
publizieren oder trotz Serienfehlern `fertig()` melden.

Der einmalige Attach-Controller unter `zulu_alt_cancel/` wurde zunaechst in
vier isolierten JVMs mit dem separat gebauten **alten HEAD-Code** geprueft:

- blockierender HTTP-Aufruf mit fuenf kooperativen Unterbrechungen;
- HTTP-Return absichtlich nach Erwerb der Locks und vor Retransform: ein alter
  aktiver `mergeTrades`-Frame erreicht spaeter den geschuetzten inneren Writer;
- bereits laufender anderer Publisher beendet seine komplette Publikation,
  bevor der Controller dessen Lock uebernimmt;
- absichtlich abweichender Altcode: keine Guard-Aktivierung, kein Interrupt.

Erst danach wurden im Produktivprozess alle **200 bereits vorhandenen**
Provider-Lock-Keys im selben absoluten normalisierten Namensraum geprueft.
Unter diesen Locks und in belegter History-HTTP-Wartephase wurden die noch
nicht aktiven Einstiege von `writeVerifiedTrades` und beiden `writeAtomic`-
Methoden um einen synchronen Schreibschutz fuer exakt den alten Worker ergaenzt.
Der gesamte normalisierte Instruktions-/Feldstand beider geladenen Klassen
musste zum getesteten Altcode passen. Erfolgreicher Retransform, erzeugte
Guards fuer beide Klassen und fehlender Transformfehler waren zwingend.
Erst danach wurden die Locks freigegeben und HTTP-/Page-Wartephasen streng
bewacht unterbrochen. Ein HTTP-Return-Rennen kann dadurch keine CSV-/Meta-
Publikation mehr erreichen. Es gab weder `Thread.stop` noch Kill/Exit waehrend
eines Writers.

Am **18.10.2026 um 17:46:54 UTC** endete der alte Worker nach fuenf solchen
HTTP-Unterbrechungen. Alle **400 CSV-/Meta-Dateizustaende** waren vor und nach
dem Schutz bytegleich. `fertig()` wurde fuer exakt diesen Job synchron
abgewiesen; der vorhandene aeussere Catch meldete korrekt **`state=error`**,
`tradelistenAbgebrochen=true`, `datenstand=null`. Die zehn abgeschlossenen
Archive blieben erhalten. Die fuenf Fehler wurden **durch den manuellen Abbruch**
ausgeloest; der alte generische Hinweis auf eine moegliche API-Stoerung ist
hier keine Ursachenfeststellung. Der Altjob wird nicht als Gesamterfolg gewertet.

Nach zusaetzlichem Nachweis, dass kein `update-job`-Thread und kein DataStore-
Writer mehr aktiv war, wurde das Fenster normal geschlossen. Prozess 52084
endete um **17:47:47 UTC**. Das anschliessende private Backup umfasst **756
Dateien / 152.747.766 Bytes**, alle Kopie-Hashes verifiziert. Zugangsdaten,
Rohtrades und Datenbankdateien verbleiben im privaten, ignorierten Backup.

Nachweise: `zulu_alt_cancel_fixture_summary.json`, `zulu_alt_cancel_*.jsonl`,
`zulu_alt_cancel_live.jsonl.before.sha256`,
`zulu_alt_cancel_live.jsonl.after.sha256`, `zulu_live_transition_status.json`.

## Produktiver neuer Build und laufender Gesamtabgleich

Prozess **1595272** verwendet den eingefrorenen Jar mit SHA-256
`a176d947f14c5564c4995ac58648d1599e528f1a7581a36c8e3b464725270828`,
gleiche Arbeitsablage und unveraenderte Settings. Gestartet wurde mit
`Start-Process -WindowStyle Hidden`. Die lokale PowerShell-Skriptrichtlinie
wurde nicht geaendert; der Prozessstart erfolgte als direkter Befehl.

Der neue Job **`u-20261018-195000-c347a8c1`** wurde um **17:50:00 UTC** real
gestartet: `target=200`, `tradelisten=true`, `katalogMaxAlterH=0`. Kein kleinerer
Scope wird als Top-200-Erfolg ausgegeben. Die aktuelle Implementierung ruft
je Anbieter die gesamte angebotene API-History ab (`timeframe=10000`, Seiten
ab null, 100 Zeilen) und vereinigt sie danach mit dem verifizierten Archiv.
Vorhandene Caches dienen der Erhaltung und dem Merge, **nicht** als Beleg eines
frischen Remote-Abgleichs. Es gibt keinen belegten Delta-Endpunkt und keinen
Resume mitten in einer abgebrochenen Provider-History. Ein neuer Job kann auf
den erhaltenen kompletten Provider-Archiven aufbauen, fragt sie fuer einen
neuen Frischenachweis jedoch erneut ab.

Live belegt um 17:50:36 UTC: Provider 402995 auf Seite 43, **4.200 / 5.725**
Zeilen. Um 17:51:51 UTC waren die ersten **zwei von 200** Anbietern fertig:
402995 mit 5.725 Zeilen / 58 Seiten, 404656 mit 5.006 / 51. Fuer beide sind
neue atomare Generation, CSV-/Meta-/Receipt-SHA, API-Seitenende sowie die
Zeilenanzahl des REST-Exports gegengeprueft. Ihre flachen Altarchive stimmen
weiter mit dem Shutdownbackup ueberein.

`zulu_live_generation_beleg.json` enthaelt die exakten Generationen und
Exporthashes; `zulu_live_transition_status.json` trennt den manuellen Altjob-
Abbruch vom neuen Lauf. **Der Top-200-Gesamtabgleich ist noch nicht abgenommen.**
Der Status-/Cancelpfad des neuen Builds bleibt waehrenddessen erreichbar.
