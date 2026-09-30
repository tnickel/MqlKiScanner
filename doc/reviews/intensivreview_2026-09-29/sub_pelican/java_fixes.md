# Java-Fixes PelicanTrading — Umsetzung Review B5 + B6 (30.09.2026)

Repo: `SIGNALDOWNLOADER/PelicanTrading` (Java 25, Maven). Kein Commit — das
übernimmt der Hauptagent. Baseline Review: `notes.md` (B5 = R3-Variante
weeks=0, B6 = R4 Broker-Kennung). PelicanMonitor wurde für die Umsetzung
NICHT gestartet (Betriebsregel).

## Fix 1 — weeks ehrlich: null statt 0, wenn Inception unbekannt (B5)

Semantik ab jetzt: `weeks` (Katalog) bzw. `Weeks` (metrics) = belegte
Handelsgeschichte (Inception-basiert) ODER null. 0 heißt nur noch
„echt jünger als eine Woche“, nie „Stats nie geladen“.

- `src/main/java/de/pelicanmonitor/model/Provider.java`
  - neu `wochenOderNull()` (Z. 254-258): `Long`, null wenn Inception null,
    sonst `WEEKS.between(inception, today)`.
  - `wochen()` (Z. 242-247) delegiert darauf (0-Fallback) — interne Logik
    (Ampel `startBekannt`, ProviderFilter, UI-Spalte „Alter (W)“ mit
    „–“-Darstellung) bleibt unverändert und wird nicht NPE-anfällig
    (kein Unboxing an neuen Stellen).
- `src/main/java/de/pelicanmonitor/rest/RestApiServer.java`
  - Katalog-Item Z. 303: `item.put("weeks", p.wochenOderNull())`.
  - metrics Z. 385: `metrics.put("Weeks", p.wochenOderNull())` — gleiche
    Semantik, konsistent (Scanner-Seite behandelt null wie 0 im Filter,
    wird dort parallel umgesetzt).
  - providers.csv (DataStore) speichert Inception roh, nicht Wochen —
    kein Round-Trip-Anpassungsbedarf. Andere weeks-Schreiber existieren
    nicht (grep über src: nur die zwei REST-Stellen).
- `PelicanMonitorApp.java` Z. 1353: Kommentar angepasst („Scanner liest
  weiter weeks=null (unbekannt)“ statt weeks=0) — Verhaltensbeschreibung.

Kein NPE-Risiko im eigenen Code: `wochenOderNull()` fließt nur in
LinkedHashMap-Werte der REST-Serialisierung (Jackson schreibt `"weeks":null`,
wie bisher schon bei `weekChange`/`latestChange`).

## Fix 2 — metrics.Broker = häufigster ServerCode (B6)

Belegweg (nachgesehen, nicht erfunden): `Signal` trägt je Trade einen
`serverCode` (PelicanClient parseSignal, JSON-Feld `ServerCode`), persistent
in Spalte „Server“ (12.) der closed-CSV (`SignalStore.CLOSED_HEADER`);
`SignalStore.loadClosed()` liest sie zurück in `Signal.getServerCode()`.
Der Wert ging bisher nur in der mql5-Konvertierung verloren — jetzt
ausgewertet:

- `RestApiServer.haeufigsterServer(id)` (Z. 559-586): häufigster
  nicht-leerer ServerCode über die geschlossenen Trades; Gate
  `store.hasClosed(id)` (verifizierte Liste, gleiche Schutzregel wie
  trades.csv — halbe Downloads werden ignoriert); Leer-/Fehlwerte
  übersprungen; Gleichstand → erster Code der Tradeliste (deterministisch,
  LinkedHashMap-Einfügereihenfolge); Lesefehler → null, nie 500er.
- metrics Z. 388-392: neues Feld `metrics.put("Broker", haeufigsterServer(id))`
  — Roh-String des ServerCodes (z. B. „ICM“, „Tickmill-Live01“); das Mapping
  auf Broker-Namen/contract_specs macht der Scanner. Ohne Trades → null.
- Katalog führt das Feld bewusst NICHT (Test sichert das ab).
- Klassen-Doku (RestApiServer.java Z. 58-76) dokumentiert beide neuen
  Semantiken.

## Tests

`RestApiServerTest` (echter HttpServer auf TempDir, bestehendes Muster):

- neu `weeksNullWennInceptionUnbekannt` (Test Z. 301-318): Katalog enthält
  `"weeks":52` (Provider mit Inception) UND `"weeks":null` (Provider ohne
  Stats), KEIN `"weeks":0`; metrics `"Weeks":null` bzw. `"Weeks":52`.
- neu `metricsLiefernBrokerAlsHaeufigstenServerCode` (Z. 320-336):
  Provider mit 2× „ICM“ + 1× „Tickmill-Live01“ → `"Broker":"ICM"`;
  Provider ohne Tradeliste → `"Broker":null`; Katalog ohne `"Broker"`.
  Fixture: dritter Trade (USOIL, anderer ServerCode) für Provider 100.

Ergebnis: `mvn -DskipTests=false test` → **53 Tests, 0 Fehler, 0 Errors**
(CoreRegression 13, EquityKurve 7, FixtureParse 5, GlmParallel 8,
PelicanMonitorUi 5 — JavaFX-Toolkit startete hier problemlos —,
RestApiServer 15). Kompilierung `mvn -q compile` grün.

## Offene Punkte

- Scanner-Seite (Hauptagent, parallel): null-Behandlung im Wochen-Vorfilter
  (null wie 0: Filter schließt beides aus — bewusste Nutzer-Entscheidung)
  und Mapping `metrics.Broker` → `broker_server`/contract_specs
  (löst die 6 USOIL/GER40-Forensik-Abbrüche aus R4, sofern der ServerCode
  auf einen bekannten Broker mappt).
- Fix 1 macht die 735 weeks=0-Einträge im Katalog zu null — die
  Auswahlverzerrung aus R3 (Stats nur für UI-gefilterte 46 geladen) bleibt
  als Datenlage bestehen; null ist nur die ehrliche Kennzeichnung davon.
- Kein Commit, kein Restart des Monitors; Produktion zieht die Änderungen
  mit dem nächsten Start/Commit des Hauptagenten.
