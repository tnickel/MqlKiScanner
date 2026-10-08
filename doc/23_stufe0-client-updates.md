# Konzept 23 — Stufe 0 „Clients aktualisieren" vor jedem Scan

Stand: 07.10.2026 · Status: **UMGESETZT** (gleicher Abend; Changelog §11)

## 1. Problem und Ziel

Der SignalKiScanner startet seinen Workflow (Full-Scan/Teilscan) mit dem
Datenstand, den die 5 Client-Monitore **gerade zufällig** haben. Ob der
MqlDownloader, Pelican, RoboForex, Vantage oder Zulu ihre Signallisten und
Tradelisten heute schon geladen haben, hängt davon ab, ob jemand vorher in
jedem Fenster den richtigen Button gedrückt hat.

**Ziel (Nutzer-Anforderung 07.10.2026):**

1. Ein EINZIGER Knopf im Scanner („Full-Scan" oder „Teilscan") löst die
   komplette Kette aus — danach ist kein Zutun mehr nötig:
   **Stufe 0** stößt bei allen 5 Clients den Daten-Download an, alle Clients
   melden „fertig", erst dann beginnt Station 1 (Signale holen).
2. Stufe 0 protokolliert je Client, was gemacht wurde, ob der Client fertig
   ist und wie aktuell seine Daten sind.
3. Klick auf den Stufe-0-Kreis öffnet ein großes Fenster mit Live-Status
   je Client (wie die Stations-Dialoge 1–6).
4. Je Client sollen **mindestens 200 Signale mit Abonnenten** geladen werden
   (Wunsch-Ziel, kein hartes Kriterium — MqlDownloader meldet nur ~50;
   „es soll versucht werden, was kommt").
5. Pelican-Login voll automatisieren: Zugangsdaten werden EINMALIG lokal
   hinterlegt, das Login-Fenster füllt sich selbst aus und meldet die
   Session an den Update-Job zurück (Nutzer-Anforderung 07.10. — löst die
   alte Einschränkung „Login nicht automatisierbar" für den Batch-Betrieb).
6. RoboForex-Cookie ist langlebig (Nutzer: „funktioniert schon die ganze
   Zeit") — wird nur geprüft und gemeldet, kein Auto-Login nötig.

## 2. Ist-Zustand (recherchiert 07.10.2026)

### 2.1 Client-Seite: keine Fern-Steuerung möglich

Alle 5 REST-Server sind **bewusst rein lesend** — Nicht-GET wird mit
`405 „Nur GET und OPTIONS"` abgewiesen (MqlDownloader `RestApiServer.java:141`,
Pelican `:145`, Robo `:125`, Vantage `:126`, Zulu `:129`). Es gibt:

- **keinen Trigger-Endpoint** (alle Lade-Aktionen hängen an GUI-Buttons
  bzw. beim MqlDownloader am Freitag-18:00-Scheduler),
- **keinen Job-Status-Endpoint** (Busy-/Progress-Zustände wie Robos
  `beginJob()/busy` sind rein GUI-intern),
- als Zustand nur `GET /api/v1/health` (status, service, instance,
  uptimeSeconds, providers, tokenRequired) und je Katalog-Item
  `lastUpdated` (Datei-mtime bzw. beim MqlDownloader `/summary.newestMeasurement`).

### 2.2 Die Lade-Kaskaden hinter den Buttons (bereits vorhanden, wiederverwendbar)

| Client | Port | Katalog laden | Tradelisten laden | Login | Job-Schutz |
|---|---|---|---|---|---|
| MqlDownloader | 8089 | „Alles ausführen": MQL4-Download → MQL5 → Konvertieren (`MqlDownloaderGui.handleDoAllButton`, eigener Thread, `overallProcessRunning`) | im Download je Provider (`downloadTradeHistory`) | **automatisch** (Selenium + `config/Credentials.java`) | `DownloadManager.isDownloadRunning()` |
| Pelican | 8090 | „Signale laden" (`ladeProvider`, throttled, alle ~2250 Provider, ~648 mit Copiers ≥ 1) | „Tradelisten für ALLE" (`batchTradelisten`, Modus „Nur neue" = Merge via `SignalStore.mergeClosed`) | **WebView-Dialog** (`zeigeLoginDialog`), Cookies → `data/session_cookie.txt` | `starteTask()`-ProgressBar, KEIN Busy-Flag |
| Robo | 8091 | „Signale laden" (`startSignalDownload`, `downloadTopSignals(count,…)`) | „Deals für ALLE" (`starteDealsBatch`, skip-Ledger `data/deals/geladen.json`) | **Cookie-Datei** (manuell eingespielt, langlebig) | ausgereift: `busy`/`beginJob`/`pauseWennBusy` |
| Vantage | 8092 | „Signale laden" (`downloadProviders`, Top-N + Stats der ersten 150) | „Tradelisten für ALLE" (skip-Ledger, Batch-Kappung 2.000) | **keiner** | wie Robo |
| Zulu | 8093 | „Signale laden" (`downloadTopTraders`) | „Tradelisten für ALLE" (skip-Ledger `frischerSha`/`merkeGeladen`) | **keiner** | wie Robo |

Fazit: Die Arbeit existiert — es fehlt nur (a) ein REST-Auslöser, (b) ein
Job-Status, (c) die Kopplung an den Scanner-Workflow, (d) der automatische
Pelican-Login im Batch-Betrieb.

### 2.3 Scanner-Seite: woran Stufe 0 andockt

- `app_pages/scan.py`: Stations-Tupel `STEPS` (6 Stationen), Workflow-Dict
  (`_new_workflow`), Worker-Thread (`scan_worker.start`, Lauf-Lock),
  Live-Fragment `_live_status` (Tick 1 s), Stations-Stepper mit Klick →
  `_scan_station_dialog` → `@st.dialog(width="large")` je Station
  (`_station_dialoge`-Registry, scan.py:1782 ff.).
- Autonomer Pfad: `agenten/scan_launcher.py` repliziert die Stationen
  (Sonntags-Teilscan, Monats-Full-Scan) — Stufe 0 muss auch dort vor
  „listen" laufen.
- Quellen-Zugriff: `quellen.py` (Registry `datenquellen`), `ingest.py`
  (Katalog/Trades/Metrics-Pull mit SHA-Cache), `downloader_client.py`
  (GET-Wrapper — wird um POST/Status erweitert).
- startall.bat startet bereits alle 7 Programme inkl. REST-Bereitschafts-
  schleife; der Scanner selbst muss trotzdem auf spät hochfahrende Clients
  robust warten.

## 3. Architektur-Entscheidungen

1. **Trigger über das bestehende REST-Interface** (Nutzer-Vorschlag):
   Jeder Client erhält ein Mini-Job-Protokoll aus zwei Endpoints
   (§4). Kein zweites Protokoll, kein Message-Bus — das
   „mql5-downloader-v1"-Muster wird um einen Schreib-Endpoint erweitert.
   Das bricht bewusst die „rein lesend"-Regel der Server; die Erweiterung
   ist reiner DATEN-IMPORT (keine Bewertung, keine Löschung), im LAN, mit
   dem bisherigen optionalen Token-Verfahren geschützt.
2. **Clients machen die Arbeit, der Scanner wartet**: Stufe 0 ist kein
   Daten-Pull, sondern Anstoß + Polling. Die Clients kennen ihre
   Plattform-Limits, Rate-Limiter, Ledgers und Fortschritts-Callbacks
   selbst — wir rufen dieselben Codepfade auf, die auch hinter den
   GUI-Buttons liegen (keine zweite Implementierung = keine Drift).
3. **Alle 5 parallel**: Die Clients sind unabhängig; die Gesamtzeit von
   Stufe 0 ist die des langsamsten Clients statt der Summe.
4. **Stufe 0 ist eine echte Workflow-Station** mit eigenem Schritt im
   Workflow-Dict (`clients`), eigenem Log-Kanal, eigenem Dialog und
   eigenem DB-Protokoll — nachvollziehbar wie jede andere Station
   (Explainability-Regel).
5. **Ein-Knopf-Prinzip**: Die bestehenden Buttons „Full-Scan" und
   „Teilscan" führen Stufe 0 automatisch aus (Setting `stufe0_aktiv`,
   Default an). Die Einzelstation-Buttons der Expertenansicht starten
   bewusst OHNE Stufe 0. Der autonome Scan-Launcher ruft dieselbe Funktion.

## 4. Neue Schnittstelle: Update-Job-Protokoll v1 (je Client identisch)

### 4.1 `POST /api/v1/update` — Update anstoßen

Request-Body (JSON, alle Felder optional):
```json
{"target": 200, "tradelisten": true, "katalogMaxAlterH": 72,
 "quelle": "signalkiscanner"}
```
- `target` (int, Default 200): Wunsch-Anzahl Signale mit Abonnenten für den
  Katalog-Load (Nutzer-Regel „mindestens 200 versuchen"). Der Client lädt
  so viele, wie die Plattform hergibt — die Antwort/der Status nennt die
  Ist-Zahl (MqlDownloader wird z. B. „50 geliefert" melden — gewollt).
  **Bedeutung je Client (Nutzer-Entscheid 07.10. abends):** Bei Plattformen
  mit serverseitig sortierter Top-Liste (Robo/Vantage/Zulu laden Top-N der
  Plattform) ist `target` die Listenlänge. Bei Pelican gilt die
  „Beste-200-Regel" (§5a): Deckeln ist nur erlaubt, wenn eine beweisbar
  nach Abonnenten sortierte, NEUE Signale einschließende Top-Liste
  existiert — das ist dort nicht der Fall, also lädt Pelican ALLE Signale
  mit Abonnenten (~648; neue Top-Kandidaten dürfen nicht verpasst werden).
- `tradelisten` (bool, Default true): Tradelisten-Update mitlaufen lassen
  (inkrementell: bereits geladene aktualisieren/mergen, neue Top-Signale
  nachziehen). `false` = nur Katalog + Abonnenten-Snapshot (schneller Modus).
- `katalogMaxAlterH` (int, Default 72): **3-Tage-Regel (Nutzer-Entscheid
  07.10. abends, ersetzt „immer frisch")** — EINE globale Schranke für ALLE
  Clients gleichermaßen (der Scanner übergibt denselben Wert an jeden
  Client; bewusst KEINE je-Client-Konfiguration — Nutzer-Entscheid
  07.10.): Ist der letzte erfolgreiche Katalog-Load des Clients jünger
  als dieses Fenster, überspringt der Client die Katalog-Phase und meldet
  „Katalog aktuell genug (Stand …)".
  Die Tradelisten-Phase läuft davon UNBERÜHRT weiter (inkrementelles
  Delta — sonst arbeitete der Scan auf alten Trades). Login-Phase nur
  bei Bedarf. Der Client hält den Zeitstempel des letzten Katalog-Loads
  selbst (z. B. `data/update_state.json`); ein erzwungener Voll-Load geht
  weiterhin über den GUI-Button des Clients.
- `quelle`: Absender-Kennung fürs Client-Log.

Antwort (sofort, ohne auf das Laden zu warten):
```json
{"jobId": "u-20261007-1530-a1b2", "status": "gestartet", "bereitsLaufend": false}
```
- Läuft schon ein Update-Job (REST oder GUI-Button — derselbe Job-Schutz
  wie `beginJob`): `200` mit der vorhandenen `jobId` und
  `"bereitsLaufend": true` statt eines Zweitlaufs.
- Client beschäftigt (Nutzer klickt gerade etwas anderes): `409` mit
  `{"error": "beschaeftigt", "detail": "…"}` — der Scanner meldet 🟡 und
  wiederholt den Versuch (Backoff 30 s, max. 3×).

### 4.2 `GET /api/v1/update/status` — Job-Status (Polling)

```json
{
  "jobId": "u-20261007-1530-a1b2",
  "state": "idle | running | done | error | login_required",
  "phase": "login | katalog | tradelisten | konvertieren",
  "done": 47, "total": 200,
  "message": "Tradelisten: 47/200 (nur neue)",
  "startedAt": "2026-10-07T15:30:02", "finishedAt": null,
  "ergebnis": {
    "signaleGeliefert": 200, "tradelistenNeu": 12,
    "tradelistenAktualisiert": 188, "tradelistenUebersprungen": 0,
    "datenstand": "2026-10-07T15:41:10",
    "hinweise": ["Vantage: Batch auf 2000 Trades gekappt (3 Signale)"]
  },
  "error": null
}
```
- `login_required` (nur Pelican realistisch): Session fehlt/abgelaufen und
  der Auto-Login (§5) ist gescheitert. Der Client öffnet in dem Fall das
  Login-Fenster sichtbar; der Scanner zeigt „wartet auf Login-Eingabe"
  mit konfigurierbarem Timeout (Default 10 min), danach 🟡 Weiterlauf mit
  Datenstand-Datum (kein Endlos-Block des Gesamtlaufs).
- `idle` = noch nie/kein Job gelaufen (nach Server-Neustart).
- Phasen-`done/total` speist direkt den Fortschrittsbalken im Stufe-0-Fenster.

### 4.3 Mapping auf die vorhandenen Codepfade (Implementations-Kern)

| Client | POST /update führt aus | Phasen |
|---|---|---|
| MqlDownloader | `handleDoAllButton()`-Kaskade: Selenium-Login (Credentials.java, automatisch) → MQL4-Download → MQL5-Download → Konvertierung. `target` setzt die Download-Limits je Version auf max(target, konfiguriert). | `login → mql4 → mql5 → konvertieren` |
| Pelican | Session prüfen → ggf. **Auto-Login** (§5) → `ladeProvider()` mit minCopiers ≥ 1 — **ALLE Signale mit Abonnenten (~648), kein Deckel** („Beste-200-Regel" §5a: neue Top-Kandidaten dürfen nicht verpasst werden) → `batchTradelisten("Nur neue")` (Merge) → `copierDb.snapshot`. | `login → katalog → tradelisten` |
| Robo | Cookie-Check (fehlt → `login_required` mit ANLEITUNG_DEALS-Hinweis; ist langlebig, selten) → `startSignalDownload(count=target)` → Tagesliste ALLE → `starteDealsBatch(skipExisting=true)`. | `katalog → tagesliste → tradelisten` |
| Vantage | `startSignalDownload(target)` → `startTradesDownload(all=true, skip=true)`. | `katalog → tradelisten` |
| Zulu | `startTraderDownload(target)` → `startTradeDownload(all=true, skip=true)`. | `katalog → tradelisten` |

Technisch je Client: ein `UpdateJob`-Handler am bestehenden HttpServer
(das Routing kennt bereits GET/OPTIONS — POST kommt als dritter Zweig,
gleiche Token-Prüfung), der genau DIESEN Codepfad in den bestehenden
Job-Thread-Mechanismus (`beginJob`/`launchJob`/`starteTask`) legt und die
bereits vorhandenen Progress-Callbacks in den Status-Endpoint spiegelt.
Robo/Vantage/Zulu teilen sich fast identische Struktur — Vorlage je eine
`UpdateJobRunner`-Klasse im rest-Paket, MqlDownloader/Pelican einzeln.

### 4.4 Frische-Nachweis nach Job-Ende („sind die Daten aktuell?")

Nach `state=done` prüft der Scanner selbst nach (misstraut dem Job):
- MqlDownloader: `GET /summary` → `newestMeasurement` ≥ Heute,
- Monitore: `GET /providers` → max(`lastUpdated`) der Items ≥ Heute,
- Ergebnis je Quelle im Stufe-0-Protokoll: „Datenstand: 07.10. 15:41 ✅".
Damit deckt Stufe 0 auch den Fall ab, dass ein Client „fertig" meldet,
aber auswendig nichts Neues geschrieben hat (z. B. leerer API-Dialog).

## 5. Pelican-Login voll automatisieren (Forschung 07.10.2026 abends)

**Bisher:** Login-Dialog ist ein JavaFX-Dialog mit WebView auf
`https://pelican.copy-trade.io/` — der Nutzer tippt E-Mail/Passwort; das
Tool liest danach die Session-Cookies aus dem CookieManager und persistiert
sie in `data/session_cookie.txt` (Format `name=value` je Zeile).

### 5.1 Forschungsergebnis: Wie der Login technisch aufgebaut ist

Untersucht mit echtem Seitenabruf (GET, 07.10.2026):

- **Zwei-Stufen-OAuth:** `pelican.copy-trade.io` leitet auf den
  IdentityProvider `identity.copy-trade.io` weiter (Duende IdentityServer
  auf .NET 9): Authorization-Code-Flow **mit PKCE** (S256) und BFF-
  Callback (`/bff/login-callback`, form_post). Die Passwortseite gehört
  dem IdentityServer, nicht der App.
- **Die Passwortseite ist servergerendertes ASP.NET-Core-Identity-HTML
  mit STABILEN Feld-IDs** (keine SPA — DOM-Bruch-Risiko klein):
  E-Mail `input#Email` (`type=email`), Passwort `input#Password`
  (`type=password`), Hidden-Felder `ReturnUrl`, `Tenant=Pelican`,
  `HasRegistration`, `__RequestVerificationToken` (CSRF) sowie
  **`AfDeviceId`/`AdId`/`OsVersion`/`OsPlatform` — ohne JavaScript LEER**
  (AppsFlyer-Device-Tracking, füllt sich erst im echten Browser per JS).
  Formular: `method=post` auf die Seite selbst.
- **Kein Captcha** (kein reCAPTCHA/hCaptcha/Turnstile im HTML).
- **Warum der reine HTTP-Login 500 bleibt** (LoginManager-Kommentar,
  verifiziert: „auch mit vollständigen Browser-Headern"): Ohne echte
  JS-Ausführung bleiben die Device-Felder leer bzw. Fingerprint/JS-Signale
  fehlen — serverseitige Bot-Erkennung. Scripted POST ist DAUERHAFT
  ausgeschlossen; ein **echter Browser** (JS läuft, Felder füllen sich
  von selbst) verhält sich aus Serversicht wie manuelles Tippen.

### 5.2 Lösung: Plan-Kaskade — Plan A Selenium (Nutzer-Verdacht bestätigt)

**Plan A — Selenium-Firefox im PelicanMonitor (Muster vom MqlDownloader):**
Der MqlDownloader loggt sich seit jeher per Selenium in mql5.com ein
(`SignalDownloader.performLogin`: Felder per `By.id`, Button-Klick per
JS-Executor, Erfolg per URL-Check; `selenium-java` 4.26.0 +
`webdrivermanager` 5.6.3). Dasselbe Rezept auf die Identity-Seite, mit den
bewiesenen Selektoren:

1. `driver.get("https://pelican.copy-trade.io/")` — der Firefox folgt dem
   Redirect zum IdentityServer automatisch; PKCE/state/nonce übernimmt der
   Browser, wir rechnen den OAuth-Flow NICHT selbst.
2. Warten auf `#Email` → `sendKeys` Zugangsdaten; `#Password` →
   `sendKeys`; Submit (Selektor-Kaskade wie `findLoginButton`).
3. **Erfolg messen, nicht glauben:** warten, bis die URL zurück auf
   `pelican.copy-trade.io` zeigt (BFF-Callback durch, kein `/connect/`
   mehr). Timeout 30 s → `login_required`.
4. **Cookies übernehmen:** `driver.manage().getCookies()` der Domain
   `pelican.copy-trade.io` → als `name=value`-Zeilen in
   `data/session_cookie.txt` (exakt das LoginManager-Format) + direkt in
   den laufenden CookieManager injizieren und per
   `aktualisiereClientCookie()` an den PelicanClient geben; Selenium
   beenden.
5. **Persistentes Firefox-Profil** `data/selenium_profile`: die Device-
   Erkennung (AppsFlyer) sieht denselben „Browser" wie beim letzten Login
   — weniger Bot-Verdacht, stabilere Sessions.

Warum Selenium statt WebView zuerst: Der Update-Job soll VOLLautomatisch
laufen — auch beim autonomen Sonntags-/Monatsscan. Selenium läuft
**headless** (Firefox `-headless`) ganz ohne Fenster und unabhängig vom
JavaFX-Thread; der WebView-Weg wäre an FX-Application-Thread und ein
(minimiertes) Fenster gebunden. Firefox + automatischen Treiber-Download
bringt der Rechner schon mit (MqlDownloader nutzt beides täglich).

**Plan B — WebView-Auto-Fill (falls Selenium/Treiber streikt):** Der
bestehende Login-Dialog füllt nach Page-Load per `engine.executeScript`
`#Email`/`#Password` mit echten input/change-Events und submittiert. Der
WebView IST ein echter Browser mit JS (Device-Felder füllen sich) — aus
Serversicht identisch zum manuellen Tippen. Nachteil: FX-Thread + Fenster.

**Plan C — manuell (Notausgang, wie heute):** Auto-Login scheitert →
Login-Fenster sichtbar in den Vordergrund, Client meldet `login_required`,
Stufe 0 zeigt „wartet auf Login-Eingabe" (Timeout 10 min). Kein stiller
Ausfall — der heutige Weg bleibt immer erreichbar.

**Risiko, ehrlich benannt:** Ändert Pelican die Login-Seite (andere Feld-
IDs, Captcha nachrüsten), bricht Plan A/B — Konsequenz ist nur der
Fallback auf manuelle Eingabe (Plan C), nie ein stiller Ausfall; der
Status-Endpoint meldet `login_required` mit Grund. ASP.NET-Identity-IDs
sind historisch stabil; die Selektoren liegen als Konstante im Code
(Patch = kleine Änderung, DOM-Änderungen sind selten).

### 5.3 Zugangsdaten: nur lokal, nie im Git (Regel bleibt)

- Ablageort: `PelicanTrading/data/credentials.properties`
  (`user=…`, `password=…`) — im `data/`-Verzeichnis des Monitors, per
  .gitignore gesichert, zusätzlich explizit ignoriert.
- **Niemals** im Git (auch nicht in Doku/Commits — dieses Konzept nennt
  bewusst KEINE Werte), niemals im Log, niemals im LLM-Kontext, nie im
  Scanner-Repo. Heim-LAN-Sicherheitslinie H2a (04.10.): Klartext lokal ok.
- Befüllung: Der Nutzer hat die Zugangsdaten der umsetzenden Session
  übergeben (07.10.); sie werden ausschließlich in diese Datei geschrieben.
  Alternativ eigene Eingabe in die Datei oder ein kleiner
  „Zugangsdaten hinterlegen"-Dialog im Monitor (maskierte Passwort-Eingabe,
  speichert in dieselbe Datei).
- Keine Credentials-Datei → Plan A/B melden ehrlich `login_required` mit
  Hinweis „Zugangsdaten hinterlegen" (kein Blind-Versuch mit leeren
  Feldern — kein Kontosperr-Risiko durch Fehlversuche).

**RoboForex (bewusst ohne Auto-Login):** Cookie ist langlebig
(Nutzer-Erfahrung). Stufe 0 prüft vor dem Deal-Download `client.hatCookies()`
bzw. behandelt `SessionAbgelaufenException` → Client-Status
`login_required` mit dem bewährten Hinweistext (ANLEITUNG_DEALS.md, Cookie
aus Browser in `data/session_cookie.txt`). Kein zweiter Auto-Mechanismus.

### 5a. Beste-200-Regel für Katalog-Loads (Nutzer-Entscheid 07.10. abends)

„Nur die 200 besten Signale laden" ist eine **Optimierung mit
Verlust-Risiko**: Eine Top-200-Liste nach Abonnenten sortiert NEUE Signale
nach unten oder raus — genau die können aber die interessanten
Top-Kandidaten sein (neu, erste Abonnenten, noch unbekannt). Deshalb:

- **Deckeln (Top `target`) ist nur erlaubt, wenn die Plattform eine
  serverseitig sortierte Liste liefert, die nachweislich vollständig ist
  und neue Signale einschließt.** Bei Robo/Vantage/Zulu ist das gegeben:
  `downloadTopSignals/downloadProviders/downloadTopTraders(count, sortBy=…)`
  holen die sortierte Plattform-Top-Liste — dort ist `target=200` die
  Listenlänge und die „besten 200" sind genau das, was die Plattform selbst
  als Top führt.
- **Pelican: KEIN Deckel.** Die API bietet keine beweisbar sortierte,
  neue-Signale-einschließende Top-Liste (der Monitor lädt heute den
  Gesamtbestand ~2250, gefiltert ~648 mit Abonnenten). Der Update-Job lädt
  daher ALLE Signale mit Abonnenten (~648). Genau die Nutzer-Begründung:
  „wenn nicht sichergestellt ist, dass man nur die 200 besten bekommt,
  dann muss man halt 600 laden — es könnten ja neue Top-Kandidaten dabei
  sein." Die 3-Tage-Regel (§4.1 `katalogMaxAlterH`) begrenzt die Kosten
  dieses Voll-Loads auf einen Lauf je 3 Tage.
  **Präzisierung 08.10. (Nutzer-Wunsch „wir brauchen nur max 200"):** Die
  §5a-Regel schützt den KATALOG — nicht die Tradelisten. Der Katalog bleibt
  vollständige 2250/648 ohne Deckel (neue Top-Kandidaten werden entdeckt
  und im GUI gezeigt), aber die TEURE Tradelisten-Phase (Stats + volle
  Historie + offene Positionen je Provider) läuft nur noch für Provider
  MIT Abonnenten. Begründung: Der Scanner meldet 0-Copier-Provider nie
  (providers-Filter minSubscribers=1) — deren Historien liest niemand.
  Die §5a-Garantie bleibt vollständig: Ein Signal, das ERST später
  Abonnenten gewinnt, hat dann noch keine Tradelisten-Datei und bekommt
  sie im nächsten Update-Lauf nachgeladen (hatTradeliste == false).
  Konfiguration: `data/rest_api.json`
  `"updateTradelistenNurAbonnenten": true` (Default an), pro Auftrag
  überschreibbar per `/update`-Body `"tradelistenNurAbonnenten": false`;
  Fortschritt zeigt die gekürzten Totals, Ergebnisfeld
  `tradelistenOhneAbonnentenUebersprungen` zählt die Übersprungenen.
  **Top-N-Deckel 08.10. (Nutzer-Entscheid „die 2263 werden erst sortiert,
  über 200 abschneiden"):** Zusätzlich werden die Tradelisten auf die TOP-N
  Provider nach Abonnentenzahl gekürzt — lokal sortiert, was hier erstmals
  „beweisbar" ist, weil der Katalog ja vollständig ist (wir haben ALLE
  Abonnentenzahlen selbst). Default N=200, `0` = aus; konfigurierbar in
  `data/rest_api.json` (`"updateTradelistenMaxNachAbonnenten": 200`) und
  pro Auftrag per `/update`-Body. Bewusst akzeptiertes Restrisiko
  (Nutzer-Entscheid): Rang N+1 nach Abonnenten könnte nach Rendite/DD der
  bessere Kandidat sein — aber bereits vorhandene Tradelisten werden NIE
  gelöscht, und steigt ein zurückgestelltes Signal in den Top-N (oder
  gewinnt überhaupt erst Abonnenten), lädt der nächste Lauf seine
  Historie nach. Ergebnisfeld `tradelistenDeckelUebersprungen` zählt die
  zurückgestellten.
- **MqlDownloader:** lädt die Plattform-Liste ohnehin vollständig; gemeldet
  werden die ~50 Signale MIT Abonnenten — Wunsch 200, Ist ehrlich genannt.
- Falls eine zukünftige Pelican-API-Version eine sortierte Top-Liste mit
  Vollständigkeits-Garantie bekommt: Deckel wieder aktivieren — die Regel
  steht hier, nicht im Code vergraben.

## 6. Scanner-Seite: Stufe 0 im Workflow

### 6.1 Neues Modul `src/mqlkiscanner/client_updates.py`

Reine Logik (kein st.*), vom GUI-Worker UND vom autonomen Launcher gleich
genutzt — Muster wie `scan_fortschritt`:

```python
starte_alle_updates(settings, log, on_fortschritt) -> dict[str, ClientUpdateErgebnis]
```

- Läuft die aktiven Quellen durch (Tabelle `datenquellen`, Typ
  `mql5-downloader-v1`), **parallel** je Quelle (ThreadPool, 5 Worker):
  1. Bereitschaft: `/health`-Poll bis 60 s (Client evtl. gerade von
     startall hochgefahren; danach 🟡 „nicht erreichbar").
  2. `POST /update` mit `target=settings["update_ziel_signale"]`
     (Default 200, Admin editierbar) und
     `katalogMaxAlterH=settings["update_katalog_max_alter_h"]`
     (Default 72 = 3-Tage-Regel, Admin editierbar, EINE globale
     Einstellung für alle Clients); 409-Behandlung mit
     Backoff. Der Client meldet im Status, ob er die Katalog-Phase
     übersprungen hat („Katalog aktuell genug, Stand …") — Stufe 0 zeigt
     das als normalen Erfolg, nicht als Warnung.
  3. Poll `GET /update/status` alle 5 s; jede Änderung → `on_fortschritt`
     (schreibt in `workflow["steps"]["clients"]` und das Stufe-0-Protokoll).
  4. `login_required` → wartet `update_login_timeout_min` (Default 10),
     danach 🟡 mit Datenstand; `error` → 🔴 mit Fehlermeldung; `done` →
     Frische-Nachweis (§4.4).
- Stopp-Knopf respektiert: bricht Polling ab, meldet je Client „abgebrochen".
- Gesamt-Timeout `update_timeout_min` (Default 120) → 🟡 Weiterlauf mit
  dem, was fertig ist (nie Endlos-Blockade des Ein-Knopf-Versprechens);
  jeder nicht fertige Client wird mit Datenstand-Datum in der Station-1-
  Begründung geführt.
- Rückgabe/Protokoll je Quelle: status (done/error/login/timeout/offline),
  dauer_s, signaleGeliefert, tradelistenNeu/Aktualisiert, datenstand,
  hinweise, fehler.

### 6.2 Workflow-Verdrahtung (scan.py)

- `STEPS` bekommt vorne `("clients", "Clients aktualisieren", "cloud_sync",
  "Quellen", "Daten der angeschlossenen Clients (MqlDownloader, Pelican,
  RoboForex, Vantage, Zulu) per REST auf den neuesten Stand bringen")`.
  Der Stepper zeigt für diesen Schritt die Nummer **0** statt 1 (Nutzer-
  Sprache „Stufe 0"; Stationen 1–6 behalten ihre Nummern).
- Beim Start von „Full-Scan"/„Teilscan" läuft im Worker zuerst
  `w_run_clients()` (analog `w_run_listen`): Stufe 0 → Status complete,
  wenn ≥1 Quelle „done" ODER alle 🟡; **error**, wenn ALLE Quellen 🔴 sind
  (dann wäre der Scan eine reine Alt-Daten-Verarbeitung — besser abbrechen
  mit klarer Meldung). Einzelfehler sind 🟡 („mit Hinweisen"), der Lauf
  geht weiter — der Teilscan hat ohnehin den Offline-Fallback aus dem
  Quellen-Cache (ingest B5).
- Modus `local` (Testdaten) und die Einzelstation-Buttons starten OHNE
  Stufe 0 (Expertenpfad bleibt schnell).
- `control["client_updates"]` nimmt das Ergebnis-Dict für den Dialog und
  die Ergebnis-Seite; die Lauf-Zusammenfassung (save_run) erwähnt die
  Stufe-0-Bilanz („5/5 Clients aktualisiert, Datenstand 07.10. 15:41").

### 6.3 Stufe-0-Kreis → großes Live-Fenster

Wie Station 1–6 (gleiche `_station_dialoge`-Mechanik, `@st.dialog(...,
width="large")`), Inhalt live über das 1-s-Fragment:

```
🔄 Stufe 0 · Clients aktualisieren
┌───────────────────────────────────────────────────────────────┐
│ MqlDownloader :8089   🟢 fertig  15:42  ·  4:10 min           │
│   50 Signale geliefert (200 angefordert — mehr hat MQL5 mit   │
│   Abonnenten nicht) · Tradelisten 12 neu / 38 aktualisiert    │
│   Datenstand 07.10. 15:41 ✅                                  │
├───────────────────────────────────────────────────────────────┤
│ Pelican :8090         🔵 läuft — Tradelisten 47/200 (nur neue)│
│   Katalog 06.10. ✅ (3-Tage-Regel: jünger als 72 h, übersprungen)│
│   Phase: tradelisten · 21:03 min · Login automatisch ✅ 15:30  │
├───────────────────────────────────────────────────────────────┤
│ RoboForex :8091        🟢 fertig · Cookie ✅ · 200/200         │
│ Vantage   :8092        🟡 Hinweis: 3 Signale auf 2000 Trades   │
│                          gekappt (Plattform-Limit)            │
│ Zulu      :8093        🟢 fertig · 200 geliefert               │
└───────────────────────────────────────────────────────────────┤
│ Gesamtbilanz: 4 fertig · 1 läuft · Ziel ≥200: 4× erreicht,    │
│ 1× nur 50 lieferbar (MqlDownloader)                           │
└───────────────────────────────────────────────────────────────┘
```

Je Client-Zeile: Ampel, Phase, done/total-Balken, letzte Meldung, Dauer,
Ergebnis-Zahlen, Datenstand, Handlungs-Hinweis bei 🔴/🟡 (z. B. Robo-Cookie
erneuern). Bei `login_required` steht da groß: „Pelican wartet auf
Login-Eingabe — Fenster ist geöffnet, Auto-Ausfüllen gescheitert".

### 6.4 Protokollierung (Nutzer-Forderung „Stufe 0 protokolliert alles")

1. **Live-Log**: jeder Poll-Fortschritt in `scan_logs["clients"]` +
   `data/scan_workflow.log` (bestehendes `w_log_for`-Muster) — dezenter
   Takt (nur Phasenwechsel/Jede-30-s-Kurzzeile), kein Spam.
2. **DB dauerhaft**: neue Tabelle `client_updates`
   (lauf_ts, quelle_kuerzel, quelle_url, job_id, status, phase_ende,
   dauer_s, signale_geliefert, tradelisten_neu, tradelisten_aktualisiert,
   datenstand, fehler, hinweise) — append-only, wie `ampel_verlauf`.
   Sichtbar: im Stufe-0-Dialog unten „Letzte Läufe je Client" und als
   Admin-Datenquellen-Ergänzung (letzte Spalte „letztes Update").
3. **Lauf-Datei**: Stufe-0-Bilanz in der last_run-JSON.

### 6.5 Autonomer Pfad (Agenten)

`agenten/scan_launcher.py::_scan_innerhalb` ruft vor Station „listen"
dieselbe `starte_alle_updates` auf; Fortschritt über
`scan_fortschritt.aktualisieren("clients", …)` (Station 0 im Journal).
Sonntags-Teilscan und Monats-Full-Scan werden damit ohne Zutun aktuell —
das schließt die Lücke „autonomer Monat mit Daten von vorgestern".
Der Melder erwähnt im Scan-Abschluss-Postfach die Stufe-0-Bilanz.

### 6.6 REST-API/Tradeserver

Unverändert (Stufe 0 betrifft Datenbeschaffung, keine Bewertung). Die
Scanner-REST kann später `clientUpdates` je Quelle ausliefern — nicht
Teil dieses Konzepts.

## 7. Ablauf im Zielbild

```
startall.bat
  └─ 7 Programme (Scanner-App, MqlDownloader :8089, Pelican :8090,
     Robo :8091, Vantage :8092, Zulu :8093, PelicanWinnerLooser)
Nutzer klickt EINMAL „Full-Scan" (oder Teilscan, oder Sonntag kommt)
  └─ Stufe 0: 5× POST /update (parallel)
       ├─ MqlDownloader: Selenium-Login automatisch → Listen → Trades → Konvertieren
       ├─ Pelican: Auto-Login (WebView-Auto-Fill) → Katalog: ALLE mit
       │    Abonnenten (~648; 3-Tage-Regel überspringt frische Loads) → Tradelisten-Merge
       ├─ Robo: Cookie-Check → 200 Signale → Tagesliste → Deals (nur neue)
       ├─ Vantage: 200 Signale → Tradelisten (nur neue)
       └─ Zulu: 200 Trader → Tradelisten (nur neue)
     Poll /update/status je 5 s → Live-Fenster per Stufe-0-Kreis
  └─ alle done (oder Timeout 🟡) → Station 1 „Signale holen"
     (ingest zieht jetzt FRISCHE Kataloge/Trades — SHA-Delta wie gehabt)
  └─ Stationen 2–7 unverändert (Auswahl → Forensik → KI → Portfolio → Abgleich)
```

## 8. Ehrliche Grenzen und Risiko-Abwägungen

- **Laufzeiten**: MqlDownloader-Kaskade ~10–30 min; Pelican-Katalog
  (~648 Provider, throttled) + Tradelisten kann 30–90 min dauern.
  Stufe 0 läuft parallel — Gesamtzeit = langsamster Client. Der schnelle
  Modus (`tradelisten=false`) und das Ziel-Setting dämpfen das. Die
  Dauer steht live im Fenster (kein „geht das noch?"-Rätsel).
- **„≥200" ist eine Bitte, kein Muss**: Die Antwort nennt die Ist-Zahl;
  MqlDownloader meldet ~50. Das Fenster zeigt „200 angefordert, X
  geliefert" — genau die Nutzer-Erwartung („versuchen was kommt").
- **Auto-Fill-Bruch** (Pelican-DOM ändert sich): Fallback manuelle
  Eingabe, Status `login_required` — kein stiller Ausfall.
- **Keine Zombies**: Job-Singleton je Client (GUI-Button und REST teilen
  dasselbe `busy`/`beginJob`), Scanner-Timeouts auf drei Ebenen
  (Bereitschaft 60 s, Login 10 min, Gesamt 120 min).
- **Ausbleibende Aktualität trotz „done"**: Frische-Nachweis aus
  lastUpdated/newestMeasurement (§4.4) statt blindem Vertrauen.
- **Sicherheit**: Post-Endpoints im LAN wie bisher optional token-geschützt
  (H2a: bewusst ohne Zwangs-Security, 04.10.). Credentials nur in
  PelicanTrading/data/ (gitignored) — nie Repo, nie Log, nie LLM.
- **Backwards-Kompatibilität**: Kennt ein Client das neue Protokoll noch
  nicht (älterer Build läuft), antwortet er 405 auf POST — Stufe 0 zeigt
  🟡 „Client-Version ohne Update-Endpoint — bitte Client aktualisieren"
  und der Scan läuft weiter (alles Optional, kein Big-Bang-Deploy über
  alle 6 Repos an einem Tag nötig).

## 9. Umsetzungsschritte (Vorschlag Reihenfolge)

1. **Scanner-Kern**: `client_updates.py` (Trigger/Poll/Frische-Logik,
   reine Dicts) + `downloader_client.py`-Erweiterung (`update_starten`,
   `update_status`, POST-Pfad) + Tests mit lokalem Fake-REST-Server
   (Thread-Server: running→done, login_required, 409, 405, offline,
   Timeout-Pfade).
2. **Clients** (je ~1 Endpoint-Paar + Job-Runner, Vorlage Robo wegen
   ausgereiftem beginJob): Robo → Vantage → Zulu → MqlDownloader →
   Pelican (Reihenfolge: erst die ohne Login). Je Projekt 1–2 Java-Tests
   (Update-Job gegen Fake-Client/Temp-Verzeichnis; 405 bleibt für
   unbekannte POST-Pfade; Token gilt auch für POST).
3. **Pelican Auto-Login**: `data/credentials.properties` (gitignored) +
   Selenium-Firefox-Login nach MqlDownloader-Muster (Selektoren `#Email`/
   `#Password`, URL-Erfolgscheck, Cookie-Übernahme in
   `data/session_cookie.txt`, persistentes Profil `data/selenium_profile`);
   Plan B WebView-Auto-Fill; Plan C manueller Dialog. Abnahme: ein
   echter Update-Lauf mit Auto-Login (headless), ein Lauf mit falschen
   Zugangsdaten (muss sauber `login_required` melden), ein Lauf ohne
   Credentials-Datei (muss „Zugangsdaten hinterlegen" melden, kein
   Blind-Versuch).
4. **GUI**: Stufe 0 in scan.py (STEPS-Eintrag mit Nummer 0, `w_run_clients`,
   Dialog, Fragment-Anbindung, Expertenpfade ohne Stufe 0), Admin-Settings
   (update_ziel_signale=200, update_katalog_max_alter_h=72,
   update_timeout_min=120, update_login_timeout_min=10, stufe0_aktiv=true),
   Hilfe-Thema „stufe0_client_updates", DB-Tabelle client_updates,
   scan_launcher + scan_fortschritt + Melder-Zeile.
5. **Abnahme E2E**: startall → ein Klick Full-Scan → Stufe-0-Fenster
   verfolgt alle 5 live → DB-Protokoll prüfen → zweiter Klick direkt danach
   zeigt „bereitsLaufend/aktuell genug" (Doppel-Trigger-Schutz).
6. **Doku**: doc/23 (dieses Konzept) auf Umsetzungsstand nachziehen,
   REST-Doku je Client (MqlDownloader REST_API_Dokumentation.md,
   UI_KONVENTIONEN), README-SIGNALDOWNLOADER-Kette ergänzen.

## 10. Entscheidungen des Nutzers (07.10.2026 abends — offene Punkte geklärt)

1. **Pelican-Deckel: NEIN — alle Signale mit Abonnenten laden (~648).**
   „Nur die 200 besten" ist nur zulässig, wenn die Plattform eine
   beweisbar sortierte Top-Liste liefert, die neue Signale einschließt.
   Bei Pelican gibt es das nicht → Voll-Load aller ~648 (Beste-200-Regel
   §5a). Begründung des Nutzers: „Es könnten ja neue Signale mit
   Abonnenten dabei sein — da könnten Top-Kandidaten bei sein."
   Kosten-Bremse dafür ist die 3-Tage-Regel (Punkt 2).
2. **Katalog-Loads: 3-Tage-Regel statt „immer frisch" (72 h), GLOBAL.** Ein
   Katalog-Load, der jünger als 72 h ist, wird bei Stufe 0 übersprungen
   („einmal alle 3 Tage laden reicht"; erweitert die 24-h-Regel der
   Pelican-UI). **EINE Schranke für alle Clients gleich** — eine
   Scanner-Einstellung (`update_katalog_max_alter_h`, Default 72), KEINE
   je-Client-Konfiguration (Nutzer-Entscheid 07.10.). Tradelisten-Delta
   läuft weiterhin bei jedem Lauf (SHA/„nur neue"). Erzwungener Voll-Load
   über den GUI-Button des Clients bleibt möglich.
3. MqlDownloader `target` (informativ): wirkt nur auf die Listen-Limits —
   der Downloader lädt die Plattform-Top-Liste sowieso vollständig; die
   Ergebnis-Meldung nennt die Zahl derer MIT Abonnenten (~50) — entspricht
   der Nutzer-Erwartung („versuchen was kommt").

## 11. Umsetzungs-Changelog (07.10.2026 — komplett umgesetzt)

Alle Commits desselben Tages; jede Suite vollständig grün.

| Projekt | Commit | Inhalt |
|---|---|---|
| SignalKiScanner | c2c809b | `client_updates.py` (Kern: Bereitschaft 60 s → POST → Poll 5 s → Login-Warten 10 min → Gesamt-Timeout 120 min, 409-Backoff, 405/offline/stop), `downloader_client` POST/Status + Fehlerklassen, DB-Tabelle `client_updates`, Settings (stufe0_aktiv, update_ziel_signale 200, update_katalog_max_alter_h 72 global, Timeouts), scan.py Stufe 0 (Kreis „0", w_run_clients, großer Live-Dialog + Chronik), Admin-Abschnitt + Hilfe, scan_launcher + scan_fortschritt; +24 Tests |
| RoboMonitor | 7aa735e | Vorlagen-Implementierung: UpdateJob/UpdateJobRunner (Katalog Top-N nach Abonnenten → Tageslisten inkrementell → Deals inkrementell mit geladen.json-Skip + Closing-DD; Cookie fehlt/abgelaufen → login_required), UpdateStarter, RestApiServer POST/status, App mit busy-Kopplung; +11 Tests, 146/146 |
| VantageMonitor | c79bd39 | Struktur 1:1 von Robo; Katalog = downloadProviders + Stats-Nachzug der ersten 150 + copierDb-Snapshot; Tradelisten inkrementell mit SHA-Vergleich, TradeStore + Closing-DD; kein Login; +10 Tests, 35/35 |
| ZuluMonitor | bad95e3 | Struktur 1:1 von Robo; Katalog = detectFlavor + downloadTopTraders nach Followern + Snapshot; Tradelisten inkrementell (Ledger) mit KOMPLETTER Historie statt GUI-Default 5000; kein Login; +10 Tests, 94/94 |
| MqlDownloader | 1c12e77 | Java-8-kompatibel (kein record/switch-Ausdruck); Kaskade = „Alles ausführen" (MQL4 → MQL5 → Konvertierung, Selenium-Login automatisch) mit Status-Poller; Ergebnis = Signale MIT Abonnenten; 3-Tage-Vermerk config/update_state.json; +5 Tests, 87/87 |
| PelicanTrading | 0da1b3c | LoginAutomat (Plan A §5.2): Selenium-Firefox headless, #Email/#Password, URL-Erfolgscheck, Cookies → session_cookie.txt, persistentes Profil; Credentials nur in gitignored data/credentials.properties (angelegt; ohne Datei kein Blind-Versuch); Kaskade login → katalog (ALLE, kein Deckel; signaleGeliefert = mit Abonnenten) → tradelisten (Merge); Session-Abfall im Batch → 1× Auto-Login, dann Notausgang-Fenster; +10 Tests, 77/77 |

**Bewusste Abweichungen vom Konzept:**
- Zulu lädt Tradelisten mit KOMPLETTER Historie statt GUI-Default 5000 —
  headless muss fest wählen; tiefste Historie = beste Forensik-Basis, der
  Ledger-Skip verhindert Wiederholungslast.
- Pelican behandelt Session-Abfall MITTEN im Tradelisten-Batch mit EINEM
  erneuten Auto-Login (Konzept sah nur den Vorcheck vor) — danach
  Notausgang; verhindert Batch-Verlust bei kurzlebigen Sessions.
- MqlDownloader: `tradelisten=false` ist dort sinnlos (Katalog+Trades sind
  EIN Download) — Parameter wird ignoriert, im Code dokumentiert.

**Wirksam ab Client-NEUSTART** (startall startet die neuen Builds); die
Scanner-Seite wirkt sofort. Pelicans Auto-Login nutzt denselben Firefox wie
der MqlDownloader (WebDriverManager lädt den Treiber automatisch).

**E2E-Abnahme (manuell, Nutzer):**
1. startall.bat → im Scanner „Full-Scan" → Stufe-0-Kreis anklicken: alle
   5 Clients laufen live; Pelican meldet „Login automatisch ok".
2. Direkt danach erneut starten → 3-Tage-Regel: Katalog-Phasen übersprungen
   („Katalog aktuell genug"), nur Tradelisten-Delta — deutlich schneller.
3. Sonderfälle über Status-Texte erkennbar: Robo ohne Cookie → login_required
   mit ANLEITUNG_DEALS-Hinweis; Pelican bei gescheitertem Auto-Login →
   Login-Fenster öffnet sich, Stufe 0 wartet die eingestellte Zeit.

## 12. Intensiv-Review (Nutzer-Auftrag 07.10. spät) — Befunde und Fixes

Jeder Schritt nochmals kritisch geprüft (Kern Zeile für Zeile, Java-Rand-
stellen, Testabdeckung). **6 Befunde, alle behoben; 15 neue Tests.**

| # | Befund | Schwere | Fix |
|---|---|---|---|
| 1 | Ein EINZELNER Netz-Schluckser beim Status-Poll machte einen laufenden Client sofort 🔴 (Job lief beim Client weiter) | hoch | Toleranz: erst 3 Fehlversuche in Folge → FEHLER (Zähler resetet bei Erfolg) |
| 2 | Log-Flut: Jeder 5-s-Poll schrieb eine Zeile in scan_workflow.log (>1000 Zeilen je langem Pelican-Lauf) | mittel | Log-Takt: identische Nachrichten höchstens alle 30 s; echte Änderungen sofort; Dialog bleibt live (on_fortschritt ungefiltert) |
| 3 | starte_alle_updates reichte timeout_s/login_timeout_s nicht durch → Gesamt-Timeout war untestbar | niedrig | Parameter durchgereicht; +Test |
| 4 | w_run_clients (scan.py) bewertete die Bilanz aus dem CALLBACK-Stand (live) statt der Rückgabe — verlorene Callbacks hätten falsch grün/gelb gemacht | hoch | Bewertung aus ergebnisse (Rückgabe); live nur noch Dialog-Fallback |
| 5 | DERSSELBE Fehler im scan_launcher (live_clients) — ein Total-Ausfall ohne on_fortschritt wäre STILL durchgelaufen (Test bewies es: Status „ok" statt „fehler") | hoch | Bewertung aus der Rückgabe; Launcher-Tests mit/ohne Total-Ausfall |
| 6 | UpdateJob.melde() konnte nach login_required den Zustand zu „running" zurückholen (nachlaufender Callback) — Scanner hätte endlos gewartet | mittel | melde-Guard um LOGIN_REQUIRED in ALLEN 5 Clients + Pelican-Test |

Weitere Prüfungen OHNE Befund: POST-Token-Check überall (auch MqlDownloader),
405 für fremde POST-Pfade, OPTIONS unverändert, Path-Traversal (keine Pfade
im Body), Credentials nicht im Git (verifiziert), Java-8-Kompatibilität
MqlDownloader, FX-Thread-Verdrahtung Robo/Vantage/Zulu (runLater +
beginJob/endJob), 3-Tage-Vermerk aller 5 Clients, Idle-Status vor erstem
Job, Idle-Behandlung im Scanner-Poll (läuft wie running).

Testlücken geschlossen (+15): Scanner — Gesamt-Timeout, Poll-Schluckser
(2× toleriert / 3× Fehler), Log-Takt-Drossel, Ein-Knopf-Workflow
(Stufe 0 VOR Station 1; Total-Ausfall bricht ab; mql5-Modus ohne Stufe 0),
Launcher (Stoß + Total-Ausbruch, Merker-Reset). Pelican — LoginAutomat-
Helfer testbar gemacht (Pfade parametrisierbar): credentials erkannt/
unvollständig/fehlend, Cookie-Header-Format, melde-Guard. MqlDownloader —
Vermerk-Helfer package-private + Roundtrip/Grenzen/defekt (0-h-Fenster
gültig). Suiten danach: Scanner 1461 · Robo 146 · Vantage 35 · Zulu 94 ·
MqlDownloader 90 · Pelican 79 — alles grün.

Bewusst NICHT geändert (geprüft, vertretbar): datenstand=jetzt auch bei
Katalog-Skip (Tradelisten wurden ja aktualisiert; katalogUebersprungen wird
separat gemeldet); Pelican erlaubt parallele GUI-Tasks neben dem Update-Job
(projektübliches Task-Modell, Store-Zugriffe synchronized); Selenium-Login
bleibt manuelle Abnahme (Netz/GUI, doc/23 §9.3).

### Nachtrag Live-Betrieb (07.10. 11:17, erster echter Lauf)

Pelican-Update-Job starb mit NPE (`client == null`): Der PelicanClient wird
in der App LAZY erzeugt — die GUI-Buttons rufen vorher `clientInitialisiert()`
auf, der Update-Job nicht. Fix: Vorab-Check in `starteUpdateJob` + defensiv
in `hatSession()` (Robo/Vantage/Zulu/MqlDownloader erstellen ihre Clients
beim App-Start — geprüft, kein gleichartiger Fall). Der Scanner hatte den
Ausfall dabei KORREKT als 🟡-Hinweis geführt und der Scan lief weiter.

### Nachtrag Auto-Login 2.0 (07.10. nachmittags — Session abgelaufen 11:22
### aufgeklärt, LoginAutomat neu gebaut)

**Fall „Session abgelaufen (HTTP 401)" im Stufe-0-Fenster (11:22):** Wurzel
war eine LÜCKE in der Job-Logik, nicht der Auto-Login selbst —
`hatSession()` prüft nur die EXISTENZ der Cookie-Datei; ob die Session noch
lebt, zeigt erst der erste API-Call. Die letzte manuelle Session stammte vom
04.10. 19:45 und war tot. Ablauf damals: Job glaubte „Session da" →
übersprang den Auto-Login komplett → Katalog-Call 401 → Fehler mit dem alten
Hand-Anweisungs-Text. **Fix (UpdateJobRunner):** SessionException in der
Katalog-Phase fängt der Runner jetzt ab → 1× automatischer Nachlogin → Phase
wird wiederholt; erst ein scheiternder Auto-Login führt zu login_required +
manuellem Fenster (derselbe Retry existierte für die Tradelisten-Phase
bereits). +2 Tests (Nachlogin-Retry / Login_required ohne Retry).

**LoginAutomat: Selenium → JavaFX-WebView (Plan B §5.2).** Beweiskette aus
~10 Live-Versuchen mit echtem Login: Firefox ist auf dem Zielrechner NICHT
installiert (erster Blocker); Chrome-headless UND Chrome-sichtbar kommen
durch den Identity-Login (der Server akzeptiert den Benutzernamen OHNE @ —
`form.submit()` umgeht die clientseitige @-Validierung, die den Button
still blockt), aber `/bff/login-callback` antwortet DURCHGÄNGLIG HTTP 500:
Im WebDriver-Browser initialisiert das AppsFlyer-SDK nicht
(`navigator.webdriver=true`; AfDeviceId/AdId/OsVersion/OsPlatform bleiben
leer — auch nach 30 s und im sichtbaren Fenster) und der Identity-Server
setzt keine Session-Cookie. Der JavaFX-WebView ist der bewiesen
funktionierende Kontext (manueller Login des Nutzers). Neuer Ablauf:
WebView-Stage (schließt sich selbst) → JS füllt #Email/#Password + stabile
Geräte-ID (`data/auto_login_device.txt`, nur leere Device-Felder) →
`form.noValidate=true` + echter Button-Klick → Watchdog auf der OAuth-
Auto-Submit-Seite (eigenes sofortiges Submit würde die laufende Navigation
ABBRECHEN — CANCELLED-Race live bewiesen; Watchdog feuert erst nach 8 s
Stillstand) → Erfolg wird an den SESSION-COOKIES gemessen, nie an der URL
(false positive bewiesen: der fehlgeschlagene Flow landet ebenfalls auf der
App-Domain). Selenium-/WebDriverManager-Dependencies aus pom entfernt.

**OFFEN (serverseitig, 07.10. Stand):** Der BFF-Callback
(`/bff/login-callback`) antwortet am 07.10. AUCH im WebView mit Fehler
(Navigation CANCELLED) — beim letzten manuellen Login (04.10. 19:45)
funktionierte derselbe Flow. Die Login-UI validiert inzwischen clientseitig
eine E-Mail-Adresse („@-Zeichen") — beides deutet auf einen Plattform-Deploy
nach dem 04.10. hin. Der Auto-Login ist technisch fertig und greift
automatisch, sobald der Login wieder durchgeht — vermutlich mit der
Login-E-MAIL-Adresse statt des Benutzernamens: Dann in
`PelicanTrading/data/credentials.properties` `user=…@…` eintragen (Datei ist
gitignored; Passwort unverändert). Bis dahin: manuellen Login im
PelicanMonitor testen (Login-Button → tippen → „Anmeldung"); das Update-Job-
Ergebnis (login_required statt Endlosfehler) ist der saubere Notausgang.

