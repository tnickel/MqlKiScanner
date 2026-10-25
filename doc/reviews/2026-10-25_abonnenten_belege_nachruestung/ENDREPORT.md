# ENDREPORT 25.10.2026 — Abonnenten-Datenfluss: Belegfelder, Frische, Fortschritt, Overlay

**Status:** Umsetzung abgeschlossen, Tests grün (Stand siehe §7). **NICHT
deployed** — Scanner-App und drei Monitore laufen noch auf ALTEN Builds
(§5.1). Arbeitsbaum UNCOMMITTED in allen vier Repos (bewusst, kein
Commit-Auftrag).

**Für die Review-KI:** Dieser Report ist self-contained. Prüfe intensiv alle
in §2 gelisteten Änderungen (§3 nennt gezielt die riskanten Stellen), halte
dich bei §4 an die bewussten Nutzer-Entscheidungen (nicht als Bug melden)
und arbeite die Prüfaufträge in §6 ab. Alles ist über `Datei:Zeile` bzw.
Symbolname auffindbar — Zeilen können sich um ±5 verschieben.

---

## 0. Repos, Umgebung, Testaufrufe

- **Scanner:** `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner`
  (Python/Streamlit, `PYTHONPATH=src pytest tests/ -q`; LLM-Tests per
  Marker `llm` ausgeschlossen, nie ohne Absicht anfassen)
- **PelicanTrading:** `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\PelicanTrading` (Java/Maven)
- **roboforex (RoboMonitor):** `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\roboforex`
- **zulumonitor:** `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\zulumonitor`
- Native Tests: `mvn test` im jeweiligen Repo. Vantage (`vantage/`) und
  MqlDownloader (`MqlDownloader/`) wurden HEUTE NICHT geändert (nur als
  Kontrakt-Vorlage gelesen).
- Betriebsumgebung: Streamlit :8504, Clients :8089 (MqlDownloader), :8090
  (Pelican), :8091 (Robo), :8092 (Vantage), :8093 (Zulu).

## 1. Nutzerbefunde des Tages (jeder einzeln live diagnostiziert)

| # | Meldung | Diagnose (belegt) |
|---|---|---|
| 1 | Gelbe „unbestätigte Auswahl“ für pelik/robo/zulu | Scanner verlangt seit 24.10. Abdeckungsbeleg (`subscriberSelectionProof`/`subscriberCatalog*`); nur MqlDownloader+Vantage liefern ihn. Pelican/Robo/Zulu-Builds können es nicht → Belegfelder nachgerüstet (§2.1) |
| 2 | Pelican-Zahlen „kommen nicht an“ | Seite zeigt jüngsten HISTORIENpunkt; Zählerlauf snapshottete nur Top-200 → ~2.011 Anbieter auf Vortag. Fix: volle Zähler-Veröffentlichung (§2.1) |
| 3 | mql5-Zahlen eine Messung hinten (NoPain 68 vs 65) | Lesephase brach am 30-s-Katalog-Timeout (Java-IOException im Monitor-Log ~03:00); Fix 60 s (§2.2). Beweis: Client-Historie 25.10. 02:53:20 → 65 (−3); Website 65 |
| 4 | Vantage ONE PERCENT 469 vs Broker 467 | Letzter verifizierter Stand 24.10.; heutiger Lauf verweigerte Übernahme („Kurze Vantage-Listenantwort widerspricht der Offsetprüfung für Anbieter 1585170“) — bewusstes Schutzverhalten, KEIN Codefehler |
| 5 | The Holy Grail 1879 vs Website 1880 | Messzeit-Semantik: 1879 korrekt zum Messzeitpunkt 02:52:08; Website = Stunden später. Kein Fehler (§4.4) |
| 6 | „Alle Signale“: Lenore 120 vs Broker 122 | `list_catalog` las NUR Workflow-Scan-Stand (aktualisiert sich nur per Re-Scan). Fix: Katalog-Overlay (§2.4). Außerdem: verwaiste Historien (ID 1445283 = „Ms Flower“, 492→6) sichtbar ohne Namensfallback-Kennzeichnung — offen (§5.3) |

## 2. Änderungen im Detail

### 2.1 Native Clients: Belegfelder + volle Zähler-Veröffentlichung
(alle drei Repos, Vorlage = Vantage `UpdateJobRunner`/`SubscriberCatalogResult`)

**Gemeinsames Muster:** Neue Beleg-Records (Auswahl + `alleGelesene` +
`scannedProviders` + `reachedEnd` + `months` + `sort`), neuer abstrakter
`Dienste`-Methoden `ladeAbonnentenKatalog(...)` und
`veroeffentlicheAbonnentenZaehler(alle)`, Runner-Phase `nurAbonnenten`
emittiert die sechs Scanner-Felder `subscriberCatalogComplete/ReachedEnd/
Scanned/SkippedPositions/Months/Sort`, Wächter wie Vantage (keine belegte
Endseite → kein Übernehmen; Auswahl > gelesene Anbieter → Fehler). Alte
Methoden bleiben als Delegates (bestehende Tests unverändert lauffähig).

- **PelicanTrading:**
  - `update/AbonnentenKatalog.java:21` — `record Beleg`; `:30` `katalog()`
    (Discover-Liste = EINE vollständige Antwort → complete/reachedEnd=true;
    Strict-Parsing wirft statt zu skippen → skippedPositions=[]).
  - `update/UpdateJobRunner.java:71` (Interface, jetzt ABSTRAKT — siehe
    §3.1), `:245-270` (Phase + Felder, `months=1`, `sort="discover"`).
  - `PelicanMonitorApp.java` (~:517) — Implementierungen;
    `store/DataStore.java:134` — `veroeffentlicheZaehler` (Counter-Merge in
    Vollkatalog; Auswahl-Datei `providers_abonnenten.csv` unberührt) +
    `copierDb.snapshot(alle)` → Tages-Snapshots für ALLE (~2.211) statt
    Top-200.
- **roboforex:**
  - `api/RoboForexClient.java:155` — `record SubscriberCatalogResult`;
    `:164` `downloadSubscriberCatalog` — reachedEnd durch einen von DREI
    belegten Endzuständen (more=false · Nullgrenze des absteigenden
    Rankings · mathematischer Frühabbruch „nichts dahinter kann Top-200
    erreichen"); `months=3` (Ratings-Fenster des Zählerlaufs),
    `sort="subscriber_count"`. Alte `downloadSubscriberSignals` delegiert.
  - `update/UpdateJobRunner.java` (Interface + Phase, Felder-Emission),
    `RoboMonitorApp.java` (Impl; Achtung: `preserveSubscriberDetails`
    wird in `ladeAbonnentenKatalog` auf die Auswahl angewandt und in
    `saveSubscriberSignals` ERNEUT — idempotent, aber prüfenswert, §3.4),
    `store/DataStore.java:180` — `veroeffentlicheZaehler` (Merge in
    signals.csv, `subscriberFile` unberührt) + `subscriberDb.snapshot(alle)`.
- **zulumonitor:**
  - `api/ZuluTradeClient.java:246` — `record SubscriberCatalogResult`;
    `:255` `downloadSubscriberCatalog` — Ende = leere Endseite,
    `months=1` (timeFrame=10000 → fensterlos, siehe §4.1),
    `sort="followers"`. Alte `downloadSubscriberTraders` delegiert.
  - `update/UpdateJobRunner.java` (Interface + Phase),
    `ZuluMonitorApp.java` (Impl; `withSubscriberCounts`-Merge),
    `store/DataStore.java:125` — `veroeffentlicheZaehler` (Counter-Only-
    Merge in tradersFile; `subscriberTradersFile` unberührt) +
    `subscriberDb.snapshot(alle)`.

**Scanner-Seite unverändert:** `client_updates._abonnenten_katalog`
validiert die Felder (complete + keine Skips → Status FERTIG/grün statt
gelb „unbestätigt“). MqlDownloader (`subscriberSelectionProof`) und
Vantage unverändert.

### 2.2 Scanner: Login-Hinweis + Katalog-Timeout

- `src/mqlkiscanner/client_updates.py:507` — Login-Meldung nennt
  ausdrücklich „bitte jetzt im Fenster von <kuerzel> einloggen“ (Klartext
  im Chronik-Protokoll, KEIN Markdown in DB-Hinweise).
- `app_pages/abonnenten_statistik.py:142` — UI rendert die Statuszeile bei
  `status == LOGIN` FETT; Dialog-Caption warnt vorab (Login passiert im
  Client-FENSTER, nicht im Scanner).
- `src/mqlkiscanner/abonnenten_statistik.py:84` — `_KATALOG_TIMEOUT_S`
  30 → 60 s (Befund: mql5-Vollkatalog brach bei Last ab; entlastet 2,5 s).

### 2.3 Scanner: Frische-Gate 24 h + Progress + Button-Zahlen (Daten-Button)

- `abonnenten_statistik.py:94` — NEU `juengste_messung(kuerzels)`: jüngste
  echte MESSUNG je Quelle (max(ts) aus `subscriber_history` über
  Identitäts-Join; Spiegelzeit zählt bewusst NICHT; None = nie gemessen).
- `abonnenten_analyse.py:284-334` — `daten_starten(...,
  akzeptiere_veraltete_abos=False)`: lehnt ab, wenn eine gewählte Quelle
  >24 h oder nie gemessen; Fehler nennt Quelle+Alter und den Weg über
  „Abonnentenzahlen aktualisieren → Frisch messen“. Bei Start wird
  `abonnenten_frische` im Lauf vermerkt (geprueft_am, Messzeitpunkte,
  akzeptiert_veraltete).
- `abonnenten_analyse_ui.py` Dialog (~:1330): Vorab-Prüfung je gewählter
  Quelle, Warnung mit Altersangaben, Override-Checkbox
  (`abonnenten_daten_veraltete_akzeptieren`, :1371), Start-Button disabled
  bei Verstoß ohne Override.
- Progress: `_render_daten_results` :1469 — `st.progress`
  (data_done/gesamt, 2-s-Polling; NUR im Datenmodus — der Modellauftrag
  behält seinen eigenen „Modellbearbeitung“-Balken).
- Button-Zahlen (:1490-1500): „Datensammlung fortsetzen — X/y geladen, z
  offen“ und „Datensammlung stoppen — X/y geladen“; Caption nennt den
  gespeicherten Modus (:1477-1479, „Nur fehlende laden“ vs „Alle neu
  laden“ — bestimmt, was ein Resume wirklich lädt).

### 2.4 Scanner: Abonnentenstatistik-Lesephase mit Progress

- `abonnenten_statistik.py:137` — `sync_quelle(..., on_fortschritt=)`:
  meldet `{"phase":"historie","kuerzel","gesamt","fertig"}` in
  25er-Schritten; `:223` `sync(..., on_fortschritt=)` meldet
  `{"phase":"quelle","kuerzel","nr","von"}` je Quellenwechsel;
  `:542` `_lesen_fortschritt` legt es unter `_REFRESH["lesen"]` ab.
- `app_pages/abonnenten_statistik.py` Fragment: `st.progress` „Neu
  einlesen: Quelle 2/5 — pelik: Historie 150/2211 Anbieter“ (ohne Meldung
  unbestimmt laufend).

### 2.5 Scanner: „Alle Signale“ — Overlay, Frische-Zeile, Frischmess-Button

- `src/mqlkiscanner/db.py:807` + FROM-Klausel — `list_catalog` joint jetzt
  `katalog_signale` und nimmt `COALESCE(k.abonnenten, s.abonnenten) AS
  abonnenten`: Spiegelstand des letzten Client-Laufs gewinnt, Scan-Stand
  ist Fallback ohne Katalogzeile. **Wirkt programmweit** (Alle Signale,
  Workflow-Anzeige, REST) — siehe §3.2.
- `app_pages/alle_signale.py:~90-120` — Frische-Zeile „Abonnenten-Messung
  je Quelle: vant vor 30 h ⚠ · …“ (juengste_messung, ⚠ >24 h) + Button
  „Abonnentenzahlen frisch messen“ (:107, `starte_refresh(messen=True)`,
  gesperrt bei laufendem Workflow-Scan; Fortschritt/Ergebnis auf
  Abonnentenstatistik; laufender Refresh wird als blaue Caption gezeigt).

### 2.6 Neue/erweiterte Tests

- Scanner NEU: `tests/test_katalog_overlay_abonnenten.py` (Katalog 122
  schlägt Scan 120; Fallback ohne Katalogzeile).
- Scanner ERWEITERT: `test_abonnenten_statistik.py`
  (`test_sync_meldet_fortschritt_fuer_ui_balken`, Schritte 0/25/50/60),
  `test_abonnenten_datenmodus.py` (Gate: nie → „nicht frisch“, 48 h →
  „48 h alt“, Override → vermerkt, frisch → sauber),
  `test_abonnenten_daten_ui.py` (Frische-Seed, Button-Label „2/3 geladen,
  1 offen“, Overlay-kwargs `akzeptiere_veraltete_abos: False`).
- PelicanTrading `UpdateJobStufe0Test`: Belegfelder im Job-Ergebnis +
  `veroeffentlichteZaehler` (250 gelesene); roboforex
  `subscriberOnlyAlwaysRefreshes...` erweitert; zulumonitor
  `subscriberOnlyAlwaysRefreshesAndInvalidatesFullFreshness` erweitert.

## 3. Riskante Stellen — HIER INTENSIV PRÜFEN

1. **Abstrakte Interface-Methoden (alle 3 Java-Repos):**
   `ladeAbonnentenKatalogBelegt`/`ladeAbonnentenKatalog` und
   `veroeffentlicheAbonnentenZaehler` sind JETZT ABSTRAKT in
   `UpdateJobRunner.Dienste`. In-repo-Implementierer (App + Test-Fakes)
   sind angepasst und kompilieren; prüfe, ob es IRGENDWO sonst
   Implementierungen gibt (anonyme Klassen, andere Module, Skripte), die
   jetzt brechen würden.
2. **`list_catalog`-Overlay (db.py:807):** Größter Blast-Radius des Tages.
   LEFT JOIN kann Zeilen nicht vervielfachen (katalog_signale ist über
   signal_ref eindeutig — VERIFIZIERE das Schema-Unique!), aber:
   Null-Semantik von `COALESCE` (katalog 0 ist ein legaler Wert und MUSS
   den Scan-Stand überschreiben — 0 ≠ NULL!), Auswirkung auf
   min_abo-Filter, Sortierung, CSV-Export, REST-Payload. Prüfe, ob irgendwo
   `abonnenten`-Werte aus list_catalog in Bewertungspfade fließen, die
   inzwischen einen anderen Stand erwarten (Ampel/Schranken nutzen
   laut Design NICHT die Abonnentenzahl — verifizieren!).
3. **Progress-Callback im Refresh-Thread:** `_lesen_fortschritt` schreibt
   unter `_REFRESH_LOCK` in den geteilten Zustand; `sync_quelle` ruft den
   Callback im Arbeitsthread. Prüfe Lock-Reihenfolge/Totes-Sperren-Risiko
   und dass eine Callback-Exception den Sync nicht abreißen lässt (der
   Callback ist einfach gehalten — prüfe trotzdem).
4. **Robo: doppelte `preserveSubscriberDetails`** (App-Impl in
   `ladeAbonnentenKatalog` UND erneut in `store.saveSubscriberSignals`)
   — idempotent nach Analyse, aber prüfe Seiteneffekte (z. B. Platform-
   Normalisierung doppelt angewandt).
5. **Frische-Gate (abonnenten_analyse.py:296-330):** Zeitvergleich naiv
   (naive lokale Zeitstempel gegen `datetime.now()`) — Client-Zeitstempel
   sind naive lokale Marken (Tages-Snapshots 00:00). Randfälle: MESZ-/UTC-
   Mischung der Client-Stempel (Zulu/Vantage liefern teils UTC-Suffixe —
   prüfe, ob `_parse_ts`/max(ts) hier gemischte Zeitzonen vergleicht).
6. **Pelican-Zählerlauf-Frische:** `veroeffentlicheZaehler` schreibt den
   VOLLKATALOG neu (saveRetainingTimestamp) — bei 2.211 Anbietern je Lauf
   Dateigröße/IO prüfen; Full-Basis-Receipt (`providers_catalogue
   .sha256`) muss danach weiterhin konsistent sein.
7. **`juengste_messung`-Grundlage:** max(ts) über ALLE Punkte einer Quelle
   — ein einzelner frischer Punkt (auch 0-Abonnenten-Zeile) macht die
   Quelle „frisch“, auch wenn 99 % der Zeilen alt sind. Ist das die
   richtige Semantik für das Gate? (Bewusste Vereinfachung, dokumentiert.)

## 4. Bewusste Nutzer-Entscheidungen — NICHT als Bug melden

1. **`months=1` bei Pelican/Zulu** = Provenienz-Metadatum für fensterlose
   Gesamtlisten (Dokumentation je Codestelle); Scanner validiert nur
   Zulässigkeit (1/3/6/12), zeigt es nicht als Plattformfenster an.
2. **Override-Checkbox** bei veralteten Abonnentenzahlen: bewusst
   möglich, damit ein offline-Client den Datenauftrag nicht blockiert;
   Übersteuerung wird IM LAUF vermerkt.
3. **Vantage-Übernahmeverweigerung** (kurze Listenantwort widerspricht
   Offsetprüfung → ganze Auswahl verwerfen) ist das gebaute Schutz-
   verhalten vom 23./24.10. (Grok-Korrektur) — genau richtig so.
4. **Messzeit-Semantik:** „Abonnentenzahlen aktualisieren“ misst zum
   Laufzeitpunkt; Differenz zur Live-Website Stunden später ist normal.
   Die „Messung“-Spalte zeigt die Tagesmarke (00:00) der Monitore, nicht
   die Abrufsekunde — bekannte Anzeige-Eigenheit, NICHT geändert.
5. **Standard „Nur fehlende laden“** im Daten-Dialog bleibt
   Fortsetzen-Semantik (Nutzer-Entscheidung 24.10.); „Alle neu laden“
   ist die Frischmess-Option.
6. **Verwaiste Historienreihen** (z. B. 1445283 „Ms Flower“ 492→6) bleiben
   absichtlich erhalten („Messpunkte gehen nie still verloren“) und
   erscheinen als Minimalzeile mit ID-Fallback. UX-Kennzeichnung wurde
   ANGEBOTEN, aber nicht freigegeben → offen (§5.3), nicht selbstständig
   umgesetzt.

## 5. Bekannte Grenzen / Offene Punkte

1. **DEPLOY PENDING (wichtigster Punkt):** Streamlit-App :8504 und die
   Monitore Pelican/Robo/Zulu laufen auf ALTEN Builds. Alle
   Belegfelder/Voll-Veröffentlichungen greifen erst nach Neubau + sanftem
   Neustart (`startall.bat` kompiliert selbst); Scanner-UI (Progress,
   Frische-Zeile, Buttons, Gate, Overlay) erst nach App-Neustart.
   Bewusst NICHT automatisch neugestartet (Nutzer arbeitete aktiv).
   Danach: grüne Zählerläufe als Abnahme SEPARAT nachweisen.
2. **Vantage-Anbieter 1585170** (Offset-Widerspruch) nicht untersucht —
   mögliche Folge-Läufe können erneut scheitern, falls die Verifikation
   in einem Grenzfall zu streng ist. Untersuchung angeboten, nicht
   beauftragt.
3. **Verwaiste Historien** (15 vant-Reihen ohne Katalogeintrag) ohne
   Kennzeichnung in den Tabellen (siehe §4.6).
4. **mql5-Verwaiste im Gate:** mql5 hatte heute keinen Sync (Timeout-
   Vorfall vorm Fix); die Frische-Zeile zeigt das ehrlich als ⚠.
5. **Commits:** Alle Änderungen liegen uncommitted in den Arbeitsbäumen
   (Scanner + 3 Repos). Kein Commit ohne Auftrag.

## 6. Prüfaufträge für die Review-KI (abzuarbeiten)

1. Kompilierbarkeit aller vier Repos frisch verifizieren
   (`mvn -q compile` je Java-Repo; Scanner-Import-Check).
2. TestSuiten laufen lassen und Ergebnisse bestätigen (§7).
3. §3.1: Volltextsuche nach weiteren `UpdateJobRunner.Dienste`-
   Implementierungen in ALLEN Workspace-Projekten.
4. §3.2: Schema-Prüfung `katalog_signale.signal_ref` (UNIQUE?) und
   Durchsuchen aller `list_catalog`-Verbraucher auf Abonnenten-Verwendung
   (grep `abonnenten` in src/, app_pages/; gesondert scoring/pipeline:
   fließt die Zahl in Bewertung/Schranken?).
5. §3.5: Zeitzonen-Mischung in `subscriber_history.ts` stichprobenartig
   prüfen (echte DB: `data/mqlkiscanner.db`, Tabelle ansehen) und das
   Gate gegen einen UTC-stempelführenden Client testen.
6. Kontrakt-Symmetrie: Felder/Namen/Wächter der drei Java-Runners
   gegen `client_updates._abonnenten_katalog` (Scanner) Feld für Feld
   abgleichen (Namen, Typen: boolean vs. int vs. Liste; `reachedEnd`
   MUSS true sein, `complete == (skipped leer)`).
7. Thread-Sicherheit des Refresh-Zustands (§3.3) im Code nachvollziehen.
8. UI-Texte auf Eindeutigkeit: „geladen/offen“-Zählung = data_done —
   semantisch im Kontext „Alle neu laden“ korrekt beschriftet?
9. Seitenblöcke, die `scan_worker.active_run()` aufrufen: Das Projekt
   hat aufrufzählergenaue AppTest-Fakes (ein Extra-Aufruf verschiebt die
   Choreographie — heute selbst passiert, siehe §7). Prüfe, ob meine
   Blöcke (Frische-Zeile nutzt jetzt `_batch_run`) und alle anderen
   neuen Codepfade keine zusätzlichen active_run-Aufrufe einführen.

## 7. Teststand zum Zeitpunkt des Reports

- PelicanTrading: `mvn test` → **222 Tests grün**
- roboforex: `mvn test` → **222 Tests grün**
- zulumonitor: `mvn test` → **180 Tests grün**
- Scanner gezielte Suiten: 207 (client_updates/statistik/freshness +
  daten_ui/alle_signale/glm_catalog_scope) + 110 (datenmodus/daten_ui/
  statistik/freshness) + 37 (ergebnis/workflow) + 2 (Overlay, neu)
  **grün**.
- Scanner VOLLsuite (`pytest tests/ -q`, LLM-Tests deselected):
  **3.993 passed · 17 failed · 1 skipped (8:36 min)**. Isolations-Nachweis:
  Die SELBEN 17 Tests scheitern IDENTISCH mit gestashten Änderungen
  dieses Tages (Baseline ohne meine Arbeit) — es sind Altlasten des
  Arbeitsbaums von VOR diesem Tag (Dateien: test_katalog, test_partial_
  forensik, test_remaining_contracts_h1_exposure, test_review15_engine,
  test_review_findings, test_review_table_fixes, test_stale_independent_
  study_display, test_virtuelle_messanzeige; exakte Liste im Lauf-Log).
  **Null Regressionen aus den Änderungen dieses Tages.** Der erste
  Vollsuit-Lauf (mit `-x`) hatte zusätzlich einen ECHTEN Regressionstreffer
  meiner Frische-Zeile aufgedeckt: der Block rief `scan_worker.active_run()`
  ein EXTRA-Mal auf und verschob einen aufrufzählergenauen AppTest
  (`test_alle_signale_batch_refresh`). Behoben: der Block steht jetzt NACH
  der `_batch_run`-Zuweisung und nutzt deren Ergebnis statt eines eigenen
  Aufrufs (app_pages/alle_signale.py, Kommentar im Block). Diese Falle
  (aufrufzählergenaue active_run-Fakes) ist ein bekanntes Testmuster des
  Projekts und als Prüfpunkt in §6 Ziff. 9 für die Review-KI vermerkt.

## 8. Maschinenparsebarer Block

```json
{
  "report": "ENDREPORT 2026-10-25",
  "repos_changed": ["SignalKiScanner", "PelicanTrading", "roboforex", "zulumonitor"],
  "features": [
    "subscriber_catalog_receipts_pelican_robo_zulu",
    "full_counter_publication_pelican_robo_zulu",
    "login_window_hint_scanner",
    "catalog_timeout_60s",
    "freshness_gate_24h_daten_starten",
    "progress_bars_refresh_and_data_job",
    "resume_stop_button_counts",
    "list_catalog_abonnenten_overlay",
    "alle_signale_freshness_line_and_fresh_measure_button"
  ],
  "key_files_scanner": [
    "src/mqlkiscanner/abonnenten_statistik.py",
    "src/mqlkiscanner/client_updates.py",
    "src/mqlkiscanner/abonnenten_analyse.py",
    "src/mqlkiscanner/abonnenten_analyse_ui.py",
    "src/mqlkiscanner/db.py",
    "app_pages/abonnenten_statistik.py",
    "app_pages/alle_signale.py",
    "tests/test_katalog_overlay_abonnenten.py"
  ],
  "key_files_java": [
    "PelicanTrading/src/main/java/de/pelicanmonitor/update/AbonnentenKatalog.java",
    "PelicanTrading/src/main/java/de/pelicanmonitor/update/UpdateJobRunner.java",
    "PelicanTrading/src/main/java/de/pelicanmonitor/PelicanMonitorApp.java",
    "PelicanTrading/src/main/java/de/pelicanmonitor/store/DataStore.java",
    "roboforex/src/main/java/de/robomonitor/api/RoboForexClient.java",
    "roboforex/src/main/java/de/robomonitor/update/UpdateJobRunner.java",
    "roboforex/src/main/java/de/robomonitor/RoboMonitorApp.java",
    "roboforex/src/main/java/de/robomonitor/store/DataStore.java",
    "zulumonitor/src/main/java/de/zulumonitor/api/ZuluTradeClient.java",
    "zulumonitor/src/main/java/de/zulumonitor/update/UpdateJobRunner.java",
    "zulumonitor/src/main/java/de/zulumonitor/ZuluMonitorApp.java",
    "zulumonitor/src/main/java/de/zulumonitor/store/DataStore.java"
  ],
  "tests_green": {"pelican": 222, "robo": 222, "zulu": 180, "scanner_gezielt": 356,
                   "scanner_vollsuit_passed": 3993},
  "scanner_vollsuit_preexisting_failures": 17,
  "regressions_from_this_day": 0,
  "not_deployed": true,
  "commits_pending": true,
  "open_items": [
    "restart_app_and_three_monitors",
    "vantage_1585170_verification_case",
    "orphan_history_rows_ux_label",
    "preexisting_vollsuit_failures_17_not_from_this_day"
  ],
  "do_not_flag_as_bugs": [
    "months1_provenance_fensterlose_listen",
    "override_checkbox_veraltete_abos",
    "vantage_refusal_protection",
    "measurement_time_semantics",
    "default_nur_fehlende_laden",
    "orphan_history_rows_kept_by_design"
  ]
}
```
