# Paket E — PelicanWinnerLooser (Arbeitsbaum-Review, 04.10.2026)

Reviewer: Subagent PAKET E (statisch, nur lesend). Prüfaufträge E1–E10.

## 0) Manifest und Abdeckung

- Projekt: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\PelicanWinnerLooser`
- HEAD: `dd4a94f` ("Überarbeite Kontoanalyse und ergänze Pelican-Direktlinks").
- Arbeitsbaum: **35 uncommittete Dateien** (24 modified, 11 untracked). Wichtigste:
  neu `analytics/KurvenStatistik.java`, `auth/SessionWiederaufnahme.java`,
  `gui/GewinnkurvenFenster.java`, `Launcher.java`, Tests `KurvenStatistikTest`,
  `LoginManagerTest`, `PelicanHttpSessionTest`, `SessionWiederaufnahmeTest`,
  `SettingsTest`, `auth/LoginDialogTest`, `gui/*Test`, `.launch`-Starter;
  geändert u. a. `CrawlService`, `PelicanApi`, `PelicanHttp`, `SessionStore`,
  `LoginManager`, `Statistik`, `WaehrungsUmrechnung`, `PelicanWinnerLooserApp`,
  `pom.xml`, README/Konzept/API-Verifikation. Review gilt exakt für diesen Stand.
- Vollständig gelesen: CrawlService, CrawlRepository, Database, V1–V3-SQL,
  SessionStore, LoginManager, SessionService, SessionWiederaufnahme, PelicanHttp,
  PelicanApi, RateLimiter, ApiExceptions, Settings, Statistik, Ranking,
  KurvenStatistik, WaehrungsUmrechnung, AccountRepository, AnalyticsRepository,
  PelicanWinnerLooserApp, StatistikFenster, RankingTabelle, GewinnkurvenFenster,
  CsvExport, EinstellungenDialog, Log, Parsers, Dtos.
- Stichprobenartig (grep-/Blocklektüre): SignalTabelle, KontoDetailDialog,
  FortschrittTab, LoginDialog, AppLock.
- Tests: alle 22 Testklassen per Methodenliste gesichtet, 4 Testklassen im Detail.
- Log `data/pelican-winner-looser.log` (9.715 Zeilen) aggregiert ausgewertet
  (Zählungen/Zeiträume, kein Sessionmaterial ausgegeben). DB (75 MB) nicht
  geöffnet. Keine Tests/Apps/Netzwerk ausgeführt, nichts geändert, nichts committet.

### E1) Architektur-/Datenflusskarte (Befund E1a, INFO)

```
JavaFX-App (PelicanWinnerLooserApp)
 ├─ Login: LoginDialog (WebView) → LoginManager (CookieManager + AblaufCookieStore)
 │    → SessionStore (data/session.dat, DPAPI+ACL) ; SessionService (Prüfung über
 │    authentifizierungspflichtigen Katalog-Abruf) ; SessionWiederaufnahme (Auto-Fortsetzen)
 ├─ HTTP: PelicanHttp (HttpClient, CookieManager geteilt, Body-Limit, Redirect.NEVER)
 │    → PelicanApi (GET /api/discover/Strategies, /strategies/{id}[/copiers|/stats],
 │      /copiers/{id}[/strategies|/stats], /profiles/{id}) → Parsers (feldvertragstreue DTOs)
 │    → RateLimiter (3 s + 1–2 s Jitter, globaler 429-Cooldown, Stop/Pause)
 ├─ Sammler: CrawlService (1 Worker-Thread)
 │    Arbeitsplan: crawl_runs → crawl_budget_sections → crawl_jobs
 │    (pending/running/done/skipped_reused/failed_exhausted/failed_terminal/cancelled)
 │    → request_attempts (VOR Versand gebucht) → raw_responses (Audit, SHA/Body)
 │    Verarbeitung je Job-Typ in EINER SQLite-Transaktion:
 │      strategy_copiers → membership_scans/observations + profiles-Stamm +
 │        copier_accounts-Stamm + Nachfolge-Jobs (detail/stats/strategies/profile)
 │      account_stats   → account_snapshots (Upsert 1/Konto) + return_series/points
 │        (ersetzt) + balance_observations (append-only Ledger) + fetch_state
 │      account_detail / account_strategies / profile → Stamm-/Beobachtungs-Updates
 ├─ Store: Strategy/Profile/Account/Membership/Crawl/Analytics/RawRepository auf Database
 │    (SQLite, WAL, busy_timeout, Migrationen V1–V3)
 └─ GUI: SignalTabelle (Auswahl) · StatistikFenster (Analyse) · RankingTabelle
      (Gewinner/Verlierer) · GewinnkurvenFenster (Kurven) · KontoDetailDialog ·
      FortschrittTab (Abdeckung) · CsvExport ; AnalyticsRepository.zeilen() als
      Offline-Auswertungsschicht; WaehrungsUmrechnung (ECB-Snapshot, offline)
```

Datenfluss ist sauber geschichtet (Transport → Parser → Repositories → Analytics →
GUI); Auswertung komplett offline aus SQLite. Kein Befund.

## 1) Befunde

### E2a [P1, BESTÄTIGT] Fehler mitten im Job lässt Job „running“ — Fortsetzen derselben Sitzung dreht endlos Leer

`CrawlService.fuehreJobAus` setzt den Job VOR der Ausführung auf RUNNING
(`CrawlService.java:589`):
```java
crawl.jobZustand(job.jobId(), JobState.RUNNING, job.attempts() + 1, null, null, null);
```
Die Catch-Blöcke behandeln Session/429/403/404/Schema/IOException/Interrupted —
**aber weder SQLException noch beliebige RuntimeException**. Beide landen im
äußeren Handler der Schleife (`CrawlService.java:442-455`), der nur den Lauf auf
ERROR persistiert. Der aktuelle Job bleibt `state='running'`.

Beim „Fortsetzen“ **in derselben App-Sitzung** (ERROR ist fortsetzbar,
`CrawlRepository.java:84-98`) gilt: `naechsterJob()` liefert nur `'pending'`
(`CrawlRepository.java:215-226`), `offeneJobs()` zählt running mit
(`:101-105`), `fruehesterVersuch()` fragt nur pending ab und liefert NULL
(`:108-111`) → Schleifenzweig `CrawlService.java:385-395`:
```java
if (fruehester == null) { Thread.sleep(500); continue; }
```
→ Endlosschleife mit 500-ms-Takt: Status RUNNING, null Fortschritt, Lauf wird nie
fertig. `verwaisteJobsZuruecksetzen()` läuft nur beim App-Start
(`sturzWiederherstellen`, `CrawlService.java:117-128`). Wirkung: hängender Lauf
bis zum Neustart (kein Datenverlust — Commits bleiben). Auslöser real: ein
einzelner DB-Fehler (Disk full/Lock) oder Parser-Bug (nicht-`SchemaException`-
RuntimeException) mitten im Job.
**Fix:** in den äußeren Catch-Blöcken den aktuellen Job auf PENDING zurücksetzen
(Job-Referenz im Scope halten) — oder in `fortsetzen()` vor dem Start
`UPDATE crawl_jobs SET state='pending' WHERE run_id=? AND state='running'`
ausführen (analog `sturzWiederherstellen`, aber pro Lauf).

### E2b [P2, GRENZE] „Fortsetzen“ kann einen veralteten Plan wiederbeleben; ältere Läufe verschwinden stumm

`offenerLauf()` nimmt den neuesten fortsetzbaren Lauf aus den letzten 5
(`CrawlRepository.java:84-98`). Zwei Folgen: (a) Liegen 5 neuere Läufe darüber,
ist ein alter STOPPED-Lauf stumm nicht mehr fortsetzbar. (b) Wird ein neuer Lauf
mit anderer Auswahl gestartet (`starteLauf` prüft nur `laeuft()`,
`CrawlService.java:188-229`) und später beendet, taucht der alte Lauf wieder als
„offen“ auf — „Fortsetzen“ arbeitet dann den **veralteten** Plan ab, ohne dass die
UI ihn als überholt kennzeichnet. Kein Datenverlust, aber verwirrende Semantik.
**Fix:** beim `starteLauf` ältere fortsetzbare Läufe explizit „superseded“
markieren oder in der Fortsetzen-Anzeige Lauf-ID/Erstellungszeit/Strategien nennen.

### E2c [P3, BESTÄTIGT] Neue Plattform-Konten werden im fortgesetzten Lauf nicht entdeckt

`STRATEGY_COPIERS`-Jobs sind nach Erledigung DONE; ein Resume führt nur offene
Jobs fort. Konten, die erst NACH dem Kopiererlisten-Abruf bei einem Signal
dazukommen, findet derselbe Lauf nicht mehr — erst ein neuer Lauf. Für
Resume-Semantik korrekt („Erledigtes geht nicht verloren“), aber in UI/README
nicht erwähnt. **Fix:** Hinweistext am Fortsetzen-Knopf.

### E2d [BESTÄTIGT/entlastend] Crash zwischen DB-Commit und Job-Commit: kein Double-Counting, kein Verlust

Fachverarbeitung läuft in EINER Transaktion (`db.schreibe`,
`CrawlService.java:800/887/916/951/990`: raw_response + Snapshot/Serie/Ledger +
fetch_state gemeinsam). Crash danach, vor `jobZustand(DONE)`: Job wird beim Start
auf PENDING zurückgesetzt, `request_attempts` ‚open‘ → ‚aborted‘
(`CrawlService.java:117-128`) — der Versuch bleibt im Budget gezählt (ehrliches
Audit). Wiederholung ist idempotent: Snapshot/Serie = Upsert/Replace
(`AccountRepository.java:189-218, 339-377`), Jobs `INSERT OR IGNORE` über
UNIQUE-Schlüssel (`CrawlRepository.java:206-212`), Membership-Observations
UNIQUE je Scan. Einziger „Mehrbestand“: `balance_observations` erhält je echter
Wiederholungsabfrage eine weitere Zeile — das ist Vertrag („bei JEDEM erfolgreichen
Abruf“, V3__init.sql:1-5) und dadurch wahrheitsgemäß. Test dazu existiert
(`absturzWiederherstellungBuchtVersucheVorab`, CrawlServiceTest:690).

### E3a [BESTÄTIGT/entlastend] Session-Ablage ist tatsächlich DPAPI-verschlüsselt und vernünftig geschützt

`data/session.dat` beginnt mit Kennung `PWLSESSION1 DPAPI` (Zeile 1 verifiziert,
Inhalt nicht ausgelesen). `SessionStore.java:141-160` (Crypt32Util),
`:164-182` ACL nur aktueller Nutzer, PLAIN-Fallback nur mit Warnung
(`PelicanWinnerLooserApp.java:144-147`), abgelaufene Cookies werden beim Laden
gefiltert (`SessionStore.java:105-109`). Passwort sieht die App nie (WebView-
Login). Logs enthalten keine Sessionwerte (`ApiExceptions.java:11`,
`Log.java:43-55`); `Location`-Header wird bewusst nicht in Meldungen ausgegeben,
weil OIDC-URLs Token enthalten können (`PelicanApi.java:147-151`). `.gitignore`
deckt `data/`, `session.dat`, `*.db` ab (verifiziert via `git check-ignore`).
Kein Secret-Leak gefunden.

### E3b [P3, GRENZE] Beschädigter Ciphertext und fehlende manuelle Session-Option

Beschädigte Datei: `dpapiOeffnen` wirft IOException — ok; aber kaputtes Base64
wirft ungeprüfte `IllegalArgumentException` aus `laden()` (nur IOException
deklariert, `SessionStore.java:94`). Aufgefangen wird sie nur, weil
`LoginManager.initialisiereCookieStore` breit fängt (`LoginManager.java:49-51`).
Es gibt **keine** Möglichkeit, eine Session manuell (Cookie-Import) zu setzen —
Weg nur WebView-Login oder gespeicherte Datei. Bei defekter WebView-Auth kein
Fallback. **Fix:** Base64-Fehler in IOException verpacken; optional
Import-Feld für Notfälle.

### E4a [BESTÄTIGT/entlastend] Rate-Limit/Retry-After/Abbruch robust

Retry-After als Sekunden ODER HTTP-Datum, Fallback 60 s (`PelicanApi.java:243-257`);
429-Cooldown wird schon im API-Layer gesetzt (`:157-165`) UND im Sammler
persistiert (`CrawlService.java:617-628`, `crawl_runs.cooldown_until`,
COALESCE verhindert Verkürzen, `CrawlRepository.java:68-76`) und beim Fortsetzen
übernommen (`CrawlService.java:253-257`). Log: **0** HTTP-429-Ereignisse in
9.715 Zeilen. Abbruch: max. 3 Versuche je Job, 3 konsekutive Fehlschläge →
Lauf-Stopp + Popup (`CrawlService.java:418-431`); Stop/Pause unterbrechen
Anfragen ohne Fehlversuch-Verbrauch (`PelicanApi.java:109-127`); Budget wird vor
Versand gebucht (`CrawlRepository.versuchBuchen:263-283`). Wiederaufnahme zählt
keinen Fehler endlos: `attempts` persistiert je Job, `fortlaufendeFehler`
in-memory und wird bei jedem Erfolg resettet (`CrawlService.java:602`).

### E4b [P3, VERDACHT] `backoffMs1=0` (Hand-Edit) → `SecureRandom.nextInt(0)` → Lauf-Abbruch + E2a

`CrawlService.java:708-709`:
```java
long backoffMs = versuche == 1 ? settings.backoffMs1 : settings.backoffMs2;
backoffMs += settings.backoffMs1 > 0 ? jitter.nextInt(Math.min(5_000, (int) settings.backoffMs1)) : 0;
```
Der ternäre Ausdruck schützt zwar `nextInt`, ABER der Additions-Ausdruck wertet
`Math.min(5000, 0)=0` nur im then-Zweig aus — der else-Zweig (0) greift korrekt.
Nach nochmaliger Prüfung: **widerlegt** (Schutz existsiert). Stattdessen gilt:
`Settings.laden` klemmt `backoffMs1/2` nicht auf ≥ 0 (`Settings.java:144-145`),
negative Werte aus Hand-Edit würden aber nur kürzere Backoffs erzeugen — harmlos.
→ Kein eigener Befund; nur Hinweis auf fehlende Validierung beim Laden.

### E5a [P2, BESTÄTIGT] Survivorship-Bias wird im Konzept benannt, in der Auswertungs-GUI aber nicht

Kopiererlisten sind CURRENT-only: ausgestiegene, gekündigte oder gelöschte
Kopierkonten sind nicht beobachtbar. Das Konzept formuliert das korrekt
(`doc/KONZEPT_PELICAN_WINNER_LOOSER.md:384`: „… fehlende Konten und aktuelle
Überlebendenauswahl“). Die Methodik-Box der Statistik
(`StatistikFenster.java:446`) sagt aber nur: „Erfasste Stichprobe, keine Aussage
über alle Pelican-Nutzer“ — ohne den entscheidenden Zusatz, dass **nur aktuell
sichtbare Kopierkonten** erfasst sind und die Gewinnerquote dadurch systematisch
nach oben verzerrt sein kann. Gleiches gilt für `FortschrittTab` (Hinweis ohne
Survivorship, `FortschrittTab.java:165-167`). **Fix:** je ein Satz in
`methodik()` und den Fortschritt-Hinweis („Ausgestiegene oder gelöschte Konten
fehlen; Verlierer sind vermutlich unterrepräsentiert“).

### E5b [BESTÄTIGT/entlastend] Kette Grundgesamtheit → erreichbar → ausgewertet ist sichtbar

`membership_scans` speichert `reported_count` vs. `unique_entries` +
`visibility_complete` (`CrawlService.java:849-857`); `AnalyticsRepository.abdeckung`
(`:188-210`) je Signal gemeldet/entdeckt/mitStatistik/positiv/negativ; Qualität
„eingeschränkt“ für 403/404-Komponenten sichtbar und filterbar
(`AnalyticsRepository.java:156-171`, RankingTabelle). Ehrlich: NULL ≠ 0 beim
gemeldeten Zähler (V1-SQL Kommentar). Grenze: das StatistikFenster nennt die Zahl
der Ausgeschlossenen nicht numerisch („bleiben ausgeblendet“) — vertretbar, da
der Fortschritt-Tab die Zahlen führt.

### E6a [BESTÄTIGT/entlastend] Statistik-Kern nachgerechnet — korrekt

Unabhängige Nachrechnung: Quantil Typ 7 (`Statistik.quantil`, `:27-43`) —
Position p·(n−1), linear interpoliert; Beispiel [−10,−4,−1,2,8,20]: Q1=−3,25,
Median=0,5 — korrekt. Median=Quantil 0,5 identisch. Top-10-% =
`ceil(n/10)` größte Beträge ÷ Gruppensumme (`:112-122`), Tooltip nennt Nenner und
Aufrundung übereinstimmend (`StatistikFenster.java:311-314`). Netto =
Gewinnsumme+Verlustsumme (Verluste negativ), negatives Netto rot + klarem Text
(`nettoZeile`, `:237-244`). n=0 → „Keine auswertbaren Ergebnisse“ (`:167`), n=1 →
Singleton-Gruppe korrekt (Tests `einzelnerWert…`, `negativeSingletons…`).
Kontogewichtet (Median/Ø) und Geldsummen strikt getrennt; „Prozentwerte werden
nie addiert“ ist codlich erzwungen (`:78-83`). Gewinnquote ohne Ausgeglichene mit
0/0-Schutz (`anteil`, `:486`). Geld über Währungen strikt getrennt; unbekannte
Währung zählt, summiert aber nicht (`:79-83`, Test `unbekannteWaehrung…`).

### E6b [P3, GRENZE] Kein Startkapital, keine Cashflows — und nichts erfunden

Die API liefert keine Ein-/Auszahlungen; die App behauptet nirgends
Kapitalfluss-Renditen. Realisierter P/L ist Plattform- lifetime-Wert
(`StatsDto.realisedPnl`), Renditen sind Plattform-Prozentkurven
(`realisedReturnRaw`, Anteil ×100 fester Vertrag, `AnalyticsRepository.prozent`).
„Keine einheitliche Anlagedauer“ wird benannt (`StatistikFenster.java:448`).
Kontostand-Ledger (V3) ist reine Beobachtungshistorie ohne Cashflow-Interpretation
— korrekt. Grenze: Nutzer könnten „Realisierte Rendite %“ als vergleichbare
Jahresrendite misslesen; Hinweis existiert nur in RankingTabelle (`:437`), nicht
im StatistikFenster-Kopf.

### E6c [P3, BESTÄTIGT] Toter Code: `PeriodenRendite`

`analytics/PeriodenRendite.java` wird in der Produktion nirgends referenziert
(grep über `src/main`: nur Eigendatei + Test). Kein Risiko, aber Wartungslast und
Versuchung, ungeprüfte Periodenrenditen einzubauen. **Fix:** entfernen oder
bewusst integrieren (mit Startpunkt-/Cashflow-Diskussion).

### E7a [P3, BESTÄTIGT] Kurven: Wert-Lücken werden als durchgezogene Linie gezeichnet

Punkte ohne `normalizedPercent` (quality `wert_fehlt`,
`CrawlService.java:919-926`) werden in Anzeige und Verdichtung übersprungen
(`GewinnkurvenFenster.punkt/verdichten`, `:336-357`; KontoDetailDialog:176-190).
Der LineChart verbindet die verbleibenden Punkte geradlinig — ein fehlender
Abschnitt erscheint als gemessene Gerade, nicht als Lücke. Kennzahlen
(`KurvenStatistik.berechne`) rechnen korrekt nur über vorhandene Punkte, und die
UI sagt „Verdichtete Anzeige aus maximal 400 Punkten“ — aber Längen/fehlende
Werte werden optisch nicht markiert. **Fix:** bei null-Wert einen Series-Break
(neue XYChart.Series) oder NaN-Punkt setzen und im Hinweis nennen.

### E7b [BESTÄTIGT/entlastend] Kurven-/Ranglisten-Basis ehrlich

Kein Overlay verschiedener Konten über verschiedene Startzeiten — je Zeile eine
eigene %-Kumulationskurve mit Datumachse; Hinweis „Zeitraum ist die erfasste
Historie, kein belegter Abonnementzeitraum“ (`GewinnkurvenFenster.java:539-540`);
„letzter Kurvenpunkt ist Echtzeitwert“; „Plattformkurve hat keine Geldachse“.
Drawdown ist als **Prozentpunkte** (Spitze−Tal) beschriftet, nicht als %
(`KurvenStatistik.java:27`, GewinnkurvenFenster:537-538). Ranglisten: NULL-Werte
in BEIDE Richtungen ans Ende (`Ranking.sortiere`, `:35-45`), Spalten-Comparatoren
NULL-last (`RankingTabelle.numSpalte:576-587`), Geldrangliste nur je Währung
(`neuSortieren:390-393`), Gleichstand deterministisch nach copierId.

### E8a [BESTÄTIGT/entlastend] EUR-Umrechnung konsistent und gekennzeichnet

Originalbeträge bleiben in DB/Tabellen (EUR nur als separate Anzeigezeile,
`WaehrungsUmrechnung.nachEuro(AccountRow)`, `:144-160`); Kursdatum 2026-10-02
steht aus dem ECB-Snapshot und wird sichtbar genannt (`StatistikFenster:156`,
`:447`), Quelle im Javadoc + KURSQUELLE. Offline (gebündelte Ressource, kein
Netzwerk). Der entscheidende Hinweis existiert wörtlich: „Die gesamte Historie
wird zum selben Kurs umgerechnet; keine historische Wechselkursabrechnung“
(`:447`) — HEUTE-Kurs ≠ historische EUR-Rendite ist damit korrekt deklariert.
USC ÷100 nur mit Belegen, keine Cent-Raterei (`:185-190`); nicht umrechenbare
Währungen fliegen raus und werden benannt; alle Geldfelder mit demselben Kurs
(stückweise konsistent); Prozentwerte/Drawdowns unverändert (`:153-158`).

### E8b [P3, GRENZE] ECB-Snapshot altert ohne Update-Mechanismus

`wechselkurse.xml` trägt `time="2026-10-02"` (heute 04.10.) — ist im Artefakt
gebündelt und veraltet sichtbar weiter. Gekennzeichnet (Kursdatum wird angezeigt),
kein falscher Wert — aber kein Hinweis „Snapshot kann veraltet sein“ und kein
Aktualisierungsweg außer Rebuild. **Fix:** Alter im UI warnend ab x Tagen.

### E9 [BESTÄTIGT, INFO] Session-Pausen-Cluster im Log sind erwartbare Session-Lebensdauer

`data/pelican-winner-looser.log` (02.10 17:25 → 04.10 11:37): 14× „Session
abgelaufen – Lauf pausiert“, 14× Fortsetzen, 16 App-Starts, 0× HTTP 429,
0× Budget-/Drosselfehler. Am 03.10 abends exakte ~65-min-Kadenz
(19:37 → 20:43 → 21:50 → 22:56 → 00:01 → 01:06) mit je ~1 h Arbeitsphase:
Pelican-Session-Lebensdauer ≈ 60 min; Pausen sind korrekt behandelt
(WAITING_SESSION, Arbeitsstand gespeichert, Auto-Fortsetzen nach bestätigter
Anmeldung via `SessionWiederaufnahme`). Erwartbar, kein Fehlerbild. Auffällig
(leicht): 04.10 10:16→10:20, 10:50→10:53, 11:03→11:37 je „Anwendung gestartet …
Stop angefordert“ ohne einzige Job-Zeile — vermutlich Anmeldeversuche; ohne
Fehlerlog nicht diagnostizierbar (siehe offene Fragen).

### E10) Pflichttest-Mapping (gelesen, nicht ausgeführt)

| Szenario | Deckung |
|---|---|
| 401 mitten im Paging | TEILWEISE — Paging existiert nicht (ein Array je Liste; `membership_scans.cursor` ungenutzt). 401 mitten im Lauf: `sessionMittenImKonto…`, `sessionAbgelaufenPausiertUndSetztNachAnmeldungFort` (CrawlServiceTest:201, 452) ✔ |
| Profile-404 | `systematischerProfilFehlerBrichtProfiljobsAb` (:640) ✔ + Livedaten-Trace im Log |
| Crash nach DB-Commit vor Workitem-Commit | `absturzWiederherstellungBuchtVersucheVorab` (:690) — prüft Budget-Buchung und running→pending, **nicht** die Wiederholungs-Idempotenz nach Crash-between-commits (E2d statisch als sicher bewertet) |
| Resume nach Settingsänderung | `normalbetriebIgnoriertAlteBudgetsUndPilotlimit` (:173) + SettingsTest (Migration/Roundtrip) ✔ |
| Leerer Bestand | `leerePopulationHatKeineErfundenenMedianwerte`, `histogrammeErlaubenLeer…`, StoreTest ✔ |
| Ein Konto | `einzelnerWertUndUnveraenderlicheErgebnisse`, `negativeSingletons…` ✔ |
| Mehrere Währungen | `waehrungenWerdenStriktGetrennt…`, WaehrungsUmrechnungTest (USC, Filter) ✔ |
| Cashflows | ENTFÄLLT — App modelliert keine Ein-/Auszahlungen (E6b); kein Test nötig, kein falscher Claim |
| Kurvenlücken | `nullProzentwerteWerdenUebersprungen`, `punkteOhneProzentOderDatumWerdenUebersprungen` ✔ (aber kein Test zur optischen Lücken-Darstellung, s. E7a) |
| Unabhängige Quantil-Nachrechnung | `summenAnzahlenUndQuantile…`, `quantileInterpolierenOhneVerlust…` mit Handwerten ✔ (eigene Nachrechnung E6a stimmt überein) |
| **Fehlt** | Test auf E2a (SQLException/RuntimeException im Job → Fortsetzen ohne Endlosschleife); Test „alter Lauf nach FINISH wieder offen“ (E2b) |

## 2) Widerlegte Verdachte (explizit)

- **V1 „Double-Counting nach Crash zwischen Commits“:** widerlegt durch
  Transaktionsgrenzen + idempotente Wiederholung (E2d).
- **V2 „429-Sturm / ignoriertes Retry-After“:** widerlegt — Auswertung korrekt,
  doppelte Cooldown-Setzung (API-Layer + Sammler-Catch) harmlos (max-Semantik),
  0 Ereignisse im Log (E4a).
- **V3 „`nextInt(0)`-Crash bei backoffMs1=0“:** widerlegt — ternärer Schutz in
  `CrawlService.java:709` vorhanden (E4b).
- **V4 „Sessionmaterial geloggt“:** widerlegt — Log-Meldungen enthalten nur
  Pfad/Status, Location wird ausdrücklich verschwiegen (E3a).
- **V5 „Ranglisten mischen Währungen“:** widerlegt — Geldmetriken erzwingen eine
  bekannte Währung; unbekannte fliegen raus (E7b).
- **V6 „Geldgewichtet als Kontomittel deklariert“:** widerlegt — kontogewichtete
  Kennzahlen und Geldsummen sind getrennt ausgewiesen (E6a).

## 3) Offene Fragen (an Nutzer/Autor)

1. E2a: Soll `fortsetzen()` grundsätzlich verwaiste `running`-Jobs des Laufs
   zurücksetzen (empfohlen), oder genügt eine Absicherung in den äußeren
   Catch-Blöcken?
2. E5a: Ist der gewünschte Survivorship-Hinweis nur Textarbeit im Statistik- und
   Fortschritt-Tab, oder soll die Abdeckung künftig auch „ehemals beobachtet,
   jetzt verschwunden“-Konten zählen (membership_observations liefert die Rohbasis)?
3. E9: Was geschah am 04.10 zwischen 10:16 und 11:37 (drei Kurzstarts ohne
   Job-Log)? Falls Anmeldeversuche: sollte die Sitzungsprüfung ihr Ergebnis
   (FEHLER/EINGESCHRAENKT) protokollieren, um solche Fenster diagnostizierbar zu
   machen?
4. E2b: Gewünschtes Verhalten, wenn ein neuer Lauf einen alten offenen Lauf
   überholt — veralteteten Plan automatisch schließen oder sichtbar_choicebar
   lassen?

— Ende Paket E. Schwerste Befunde: E2a (P1), E2b/E5a (P2). Kein P0 (keine falsche
Statistik-Aussage, kein Datenverlust, kein Secret-Leak gefunden).
