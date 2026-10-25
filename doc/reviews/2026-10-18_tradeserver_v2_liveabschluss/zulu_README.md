# Zulu: Katalogzahl, History-Pagination und sichtbarer Fortschritt

**Historischer Stand vor dem späteren Lifecycle-Update:** Die Angaben zur
laufenden Altinstanz und die 129er-Testsuite unten beschreiben die damalige
Prüfung. Inzwischen wurde diese Instanz nach separat belegtem kooperativem
Abbruch geschlossen und der mit 149 Tests geprüfte neue Build aktiviert.
Sein Top-200-Gesamtabgleich läuft noch. Maßgeblich für den aktuellen
Lifecycle-/Generationsstand ist [zulu_cancel_README.md](zulu_cancel_README.md).

Die Katalogzahl **6.794.903** fuer `AF Gold Hunter Pro`, Provider 429450,
ist **kein belastbarer Zaehler der eigenen herunterladbaren History-Zeilen**.
Was die Katalogstatistik fachlich genau aggregiert, ist anhand der vorliegenden
Schnittstelle nicht abschliessend belegt; eine Follower-Aggregation ist eine
Hypothese, keine bestaetigte Erklaerung.

Am 18.10.2026 antworteten beide History-Hosts auf Seite 0 und 1 konsistent
mit **48.396 Zeilen / 484 Seiten**, Seitengroesse 100. Die Authentifizierung
mit dem vorhandenen lokalen Session-Token aenderte dieses Ergebnis nicht.
Keine Tokens oder Rohtrades sind in diesen Nachweisen enthalten.

- Der Cursor ist auf den Stichproben korrekt von 0 auf 1 fortgeschritten.
  Beide Seiten hatten jeweils 100 unterschiedliche Trade-IDs und keine
  Ueberschneidung. Die Hosts lieferten identische ID-Hashes je Seite.
- Die oeffentlichen History-Zeilen enthalten `providerId=0` und
  `providerName=Manual`. Das ist kein positiver Besitzerbeleg innerhalb der
  Zeile. Die eindeutige Providerroute ist der Transportkontext. Eine
  Kontrollabfrage von Provider 402995 liefert andere IDs und ein anderes
  History-Total von 5.725: kein identischer globaler History-Dump.
- Die Randprobe auf Seite 483 lieferte einen der bekannten transienten
  HTTP-404-Fehler; Seite 484 lieferte eine leere Seite mit `last=true` und
  `number=484`. Das dortige Total war 48.296. API-Zahlen koennen zwischen
  Anfragen variieren; die Stichproben zertifizieren keinen eingefrorenen
  kompletten Snapshot und keine globale Duplikatfreiheit ueber alle Seiten.

Nachweise: `zulu_pagination_probe.json`, `zulu_authenticated_probe.json`,
`zulu_ownership_probe.json`, `zulu_boundary_probe.json`.

## Laufende Altinstanz

Der bestehende Job `u-20261018-184200-b328fbb6` (Prozess 52084, Port 8093)
meldete bei dieser Pruefung weiterhin vier abgeschlossene Provider von 200.
Die vier frisch geschriebenen Archivdateien und die Katalogreihenfolge
passen zu Provider 429450 als aktuellem fuenften Anbieter. Ein vorliegender
Thread-Dump zeigt aktive Arbeit in `HttpClient.send`, keinen nachgewiesenen
Deadlock. Der historische Provider-CSV-Cache ist waehrend des noch laufenden
Downloads unveraendert; der Client sammelt Seiten erst im RAM.

**Eine exakte aktuell geladene Provider-Zahl und eine serioese ETA sind aus
dieser Altinstanz nicht ablesbar.** Ihr GUI-Adapter verwirft jeden internen
Seitenfortschritt. Das prozessweite Klassenhistogramm zaehlte 68.800
Trade-Objekte einschliesslich anderer Anbieter, Altobjekten und noch nicht
bereinigten Objekten; daraus wird keine aktuelle Provider-Zahl erfunden.
484 Seiten mit 350 ms Mindestabstand bedeuten allein circa 169 Sekunden
Abstandszeit. Netzwerkdauer, 404-/Host-Fallback und Wiederholungen kommen
hinzu; diese theoretische Untergrenze ist keine Restzeitprognose.
`zulu_active_status.json` und `zulu_progress_limit.json` halten diese Grenze fest.

Es wurde kein weiterer Updatejob gestartet, keine aktive Cachedatei
geschrieben, kein Prozess beendet und keine Instrumentierung in den laufenden
Client eingeschleust. Die nachfolgenden Fixes gelten fuer einen neuen Build;
die aktive Altinstanz wurde waehrend dieses Jobs nicht ersetzt.

Nachpruefung des Neustartpfads (19:10/19:11 MESZ): Prozess 52084 gehoert exakt
zum Zulu-Workspace, nicht zu einem anderen Monitor. Der aktive `update-job`
ist ein separat gestarteter Daemon-Thread. `Application.stop()` unterbricht
nur `activeTask` und die zentral registrierten `workers`; dieser Stufe-0-Thread
ist dort nicht registriert. Ein vorhandener REST-Cancelpfad existiert nicht.
Damit ist Window-Close kein belegter kooperativer Abbruch dieses Writers:
das anschliessende JVM-Ende koennte den unbetreuten Daemon abschneiden.
CSV und Integritaetsmarker werden ausserdem in zwei getrennten atomaren
Moves publiziert, nicht als gemeinsames Transaktionspaar. Deshalb wurde
der aktive Job auch bei der ausdruecklichen Neustartpruefung nicht beendet.
Die vier neu veroeffentlichten Archiv-/Markerpaare und das unveraenderte
Altarchiv 429450 wurden SHA-geprueft; alle fuenf Paare waren konsistent und
waehrend der lesenden Pruefung stabil. Exakter Laufzeitkontext, aktuelle
HTTP-Wartephase und Hashbelege stehen in `zulu_shutdown_assessment_runtime.json`,
`zulu_shutdown_update_thread.txt` und `zulu_shutdown_published_hashes.json`.

## Bestaetigte Fehler und umgesetzte Korrekturen

1. Der `UpdateJobRunner` gibt den History-Seitenfortschritt jetzt durch den
   GUI-Diensteadapter weiter. REST behaelt den Gesamtzaehler der Provider
   und ergaenzt `ergebnis.tradeDownload` mit Provider-ID, geladenen eindeutigen
   Positionen, History-API-Gesamtzahl und Aktualisierungszeit. Unbekanntes
   History-Total ist 0/indeterminiert, niemals `Integer.MAX_VALUE` als scheinbare
   reale Arbeitsmenge. Periodische History-Logzeilen nennen Provider und Seite.
2. Optionale API-Cursor und Seitenzahlen werden geprueft. Wiederholte Seiten
   ohne neue Trade-Identitaeten bleiben Fehler. Widerspruechliche Endmarker
   oder ein anderer expliziter positiver Provider in einer Zeile werden nicht
   unter die angefragte ID umgeschrieben. Die real beobachtete redigierte 0
   bleibt zulaessig; fehlende IDs werden nicht als positiver Zeilenbeleg behauptet.
3. Nach einem erfolgreichen Download wird ein separater History-Beleg mit
   Provider, API-Total, heruntergeladenen gueltigen Positionen, Seitenzahl,
   Endmarkierung und UTC-Zeit an den SHA des verifizierten Archivs gebunden.
   Ein Anforderungslimit ist kein Endbeleg. Fehler erzeugen keinen neuen
   Beleg; CSV-Aenderung, Fremdbesitzer oder falscher SHA machen ihn unlesbar.
4. REST trennt nun `CatalogTrades` von `TradesTotalAvailable`. Letzteres stammt
   ausschliesslich vom SHA-gebundenen History-Beleg. `TradesHistoryComplete`
   und `TradesTruncated` sind ohne Beleg unbekannt (`null`), mit Beleg werden
   Endmarkierung und bewusste Begrenzung offengelegt. Die alte Rechnung
   `Katalogzahl > Archivzeilen` ist entfernt. Ein Archiv kann frueher gesicherte
   Zusatzpositionen enthalten; Zeilengleichheit wird nicht als Snapshot-Beweis
   ausgegeben.

Die alten Archive und Katalogstatistiken werden nicht umgeschrieben. Es gibt
keine gelockerte Seitenkappe, keine automatische Vollstaendigkeitsfreigabe
und keine Aenderung fachlicher Signalbewertungen.

## Sicheres Cancel/Resume fuer kuenftige sehr grosse Historien

Eine Millionen-History ist fuer diesen Provider nicht nachgewiesen. Ein
dauerhafter Cancel/Resume-Pfad ist trotzdem sinnvoll, wurde in dieser
laufenden Altinstanz aber nicht nachtraeglich vorgetaeuscht. Konkreter Pfad:

- Kooperatives Job-Abbruchflag, geprueft vor der naechsten HTTP-Seite und in
  Retry-/Throttle-Pausen; `cancelled` ist ein eigener Endzustand. Das bisherige
  positive Archiv bleibt dabei unveraendert und wird nicht als frisch markiert.
- Providerbezogene, getrennte Staging-Seiten mit Schema-/Owner-/Cursorbeleg,
  ID-Hashes und separatem Checkpoint. Resume darf diese Daten nur nach
  erneuter Identitaets- und Integritaetspruefung verwenden.
- Da Zulu nach neuestem Abschluss sortiert und keinen Snapshot-Cursor
  garantiert, ist ein gespeicherter Seitennummer-Offset kein sicherer Resume.
  Erneut vorne beginnen und per stabiler Trade-ID vereinigen; eine spaetere
  Seitenfortsetzung braucht einen vom Server belegten Snapshot-/Cursorvertrag.
- Erst eine erneut belegte Endmarkierung erlaubt die atomare Archivfreigabe.
  Teilseiten bleiben als Wiederaufnahmehilfe getrennt, nie als vollstaendige
  Scanner-Historie. Fortschritt soll geladene Positionen, aktuelle Seite,
  letzte Aktivitaet und eine ausdruecklich geschaetzte Restzeit zeigen.

## Validierung

Im Zulu-Repository lief die **vollstaendige Maven-Testsuite: 129 bestanden,
0 Fehler, 0 ausgelassen**, `mvn test -q`, Exit 0. Neue Faelle decken echte
History-Totals, Cursor/Endmarker, positive fremde und redigierte Besitzer,
Limit ohne Endbeleg, SHA-/Owner-Bindung, Katalog-/History-Trennung und den
REST-sichtbaren inneren Fortschritt ab. JUnit-Dateien, Summary und Log liegen
als `zulu_TEST-*.xml`, `zulu_tests_summary.json`, `zulu_tests.log` und
`zulu_tests_exit.txt` vor. Keine Netzwerkfixtures oder produktiven Dateien
wurden durch die Tests beschrieben. `git diff --check` war erfolgreich.
