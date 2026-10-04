# Paket C — MqlDownloader (statisches Codereview, 04.10.2026)

Prüfer: Subagent PAKET C · Nur-lesende Analyse (Read/Grep/git log), keine Ausführung.

## 0) Manifest und Abdeckung

- Projekt: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\MqlDownloader`
- Git: HEAD `c44d2f6` ("REST-Katalog default absteigend + limit/offset geklammert"), dirty: nur
  `README.md` (uncommittete Doku-Änderung, kein Code).
- Bereits behoben (nicht erneut gemeldet): Katalog-Sortierung/Pagination (c44d2f6, Test vorhanden),
  Bugfixpakete 288c6b7/26fdddf (Reviews v0.0.30/31), EquityDrawdown-7-Pattern (ae81b3c),
  Abonnenten-Statistik-Fixes (d4a9967/1ed10b1), Encoding (b629652).
- Abdeckung: C1 Export-Abruf (SignalDownloader 1497 Z., WebDriverManager 299 Z. vollständig),
  C2 Kennzahlen/Filter (HtmlConverter, MPDDCalculator, MonthDetailsExtractor, HtmlDatabase,
  DataExtractor, MetricsParser + realer Bestand C:/Forex/MqlAnalyzer), C3 H2 (DatabaseManager 591 Z.
  vollständig), C4 REST (RestApiServer 1079 Z., CsvParser, ProviderFiles, JsonWriter vollständig),
  C5 Swing/Jobs (DownloadManager, ConversionManager, MqlDownloaderGui, AutoSchedulerManager),
  C6 Build/Start (pom, start.bat, deploy.bat/ps1, LoggerManager, log4j2-Suche, Logs-Stichprobe
  29.12.2025–04.10.2026), C7 Pflichttest-Mapping (tests/ 15 Dateien, nur gelesen).
- Produktiv-Belege (read-only): `C:/Forex/MqlAnalyzer/logs/application.log` (04.10.),
  `application-2026-09-27-1.log`, `download/mql{4,5}download.txt`, 201 `_root.txt`,
  `config/MqldownloaderConfig.txt` (nur nicht-geheime Keys gelesen: subscribersOnly=true,
  downloadDays=0, Limits 4500/4500, Wait 4000–8000 ms).

## 1) Befunde nach Schwere

### P0

**C2a [P0, BESTÄTIGT] Monats-Extraktion ist real kaputt — Ertrag 0 für über die Hälfte des Bestands.**
`src/utils/MonthDetailsExtractor.java:79-80` (identisch :30-31):
```java
Pattern yearRowPattern = Pattern.compile(
    "<tr>\\s*<td[^>]*>(\\d{4})</td>\\s*((?:<td[^>]*>([^<]*)</td>\\s*){12})");
```
Dieses Muster (Jahreszeile + exakt 12 td-Zellen) matcht das aktuelle MQL5-DOM nicht mehr.
Beleg am Bestand (04.10.): **110 von 201** `_root.txt` haben `MonthProfitProz=` leer und
`Average3MonthProfit=0,00` (mql5: 54/104, mql4: 56/97); die zuletzt konvertierten Dateien
(ZPowerLX_2361018, Xauusd_H1_2376983) sind leer, ältere (XAUUSD_and_EURUSD_2368349) tragen noch
Werte — also ein Bruch vor Kurzem. Log-Symptom: 402× am 04.10. und 374× am 27.09.
`ChartDataExtractor.java:137` „Konnte keinen Datumsbereich aus MonthProfitProz extrahieren" —
100 % aller WARN beider Stichproben-Tage. Auswirkung: `/api/v1/providers/{id}/{v}/metrics` liefert
für >50 % der Signale Average3MonthProfit=0 und leeres monthProfits an den Scanner (falsche Werte
im Sinne von P0); MPDD-Bewertung läuft auf 0-Basis. Fix: Muster gegen ein aktuelles Beispiel-HTML
aktualisieren, die 12-Zellen-Annahme lockern (leere Zellen), Regressionstest mit archiviertem
HTML-Schnipsel, und bei „0 Monate erkannt" Warnung + Zähler statt stiller 0.

**C2b [P0, BESTÄTIGT — aktuell nur durch Konfiguration aufgehalten] MPDD-Löschfilter löscht Dateien auch bei Berechnungsversagen.**
`src/converter/HtmlConverter.java:171-173`:
```java
if (!skipFilter && mpdd3 < 0.5) {
    deleteRelatedFiles(htmlFileName);
```
`calculate3MPDD` (HtmlConverter.java:278-281) und `MPDDCalculator.calculateMPDD` (:67-70, :82-84)
liefern bei **jeder** Exception und bei „keine Monatsdaten" den Wert 0.0 — identisch behandelt wie
„echt schlecht". Folge: Ein DOM-Bruch (siehe C2a) oder Parse-Fehler führt bei JEDEM Konvertierungs-
lauf zur Löschung von HTML+CSV+TXT. Dass es heute nicht passiert, liegt allein an
`skipFilter = configManager.isSubscribersOnly()` (HtmlConverter.java:169) und dem Produktiv-Wert
`subscribersOnly=true` — ein einziger Schalter um (Checkbox „Abonnenten only" aus) und der nächste
Lauf löscht ~110 Signale inkl. Original-CSV. DataExtractor verschärft das:
`src/utils/DataExtractor.java:84/91, 254/260, 288` ruft bei Balance-/Drawdown-/Profit-Misserfolg
ebenfalls `deleteRelatedFiles` (z. B. Login-HTML statt Signalseite ⇒ kein „Kontostand:" ⇒ Löschung
des kompletten Signalsatzes). Fix: „Berechnung fehlgeschlagen" von „echt < 0.5" trennen
(Optional/NaN + überspringen statt löschen), Löschung nur bei gültiger Berechnung, Löschen in
einen Quarantäne-Ordner verschieben statt delete, und Löschrate pro Lauf deckeln (z. B. >10 % ⇒
Abbruch).

### P1

**C1a [P1, BESTÄTIGT] Keine CSV-Inhaltsvalidierung (Time;-Header/Größe) und keine Login-HTML-Erkennung.**
`src/downloader/SignalDownloader.java:1217-1227`: die erste gefundene `.csv` im Download-Ordner
wird ohne jede Prüfung umbenannt und persistiert (`Files.move`, Zeile 1227-1228). Die bekannte
Regel „Erfolg = Antwort beginnt mit `Time;`, Session abgelaufen = Login-HTML" ist nicht umgesetzt;
0-Byte- oder abgeschnittene Dateien werden gespeichert. `isFileRecentlyDownloaded`
(:842-901) überspringt den Provider danach N Tage (Produktiv: downloadDays=0 ⇒ dort neutral).
Fix: nach dem Move Header prüfen (`Time;` bzw. MT4-Orderbuch-Header), Mindestgröße, sonst löschen
und als FEHLER werten.

**C1b [P1, BESTÄTIGT] Login-Verifikation bedeutungslos; kein Session-Neulogin während des Laufs.**
`src/downloader/SignalDownloader.java:379`:
```java
wait.until(ExpectedConditions.urlContains("/en"));
```
Die Login-Seite selbst enthält `/en` — ein fehlgeschlagener Login besteht die Verifikation.
Ein Sessionablauf mitten im Lauf wird nie erkannt (Neulogin nur nach WebDriver-Crash,
`attemptRecovery`:812-814). Produktiv-Beleg 04.10. 10:26 (mql5download.txt): nach 48 erfolgreichen
Providern plötzlich „PAGE 1: 0 Provider gefunden | Gesamt verarbeitet: 48", „PAGE 2: 0 Provider",
dann BENUTZER-STOPP — klassisches Bild einer abgelaufenen Session/leeren Antwort ohne Recovery.
Fix: Login-Erfolg prüfen (Cookie/Profil-Element bzw. Fehlertext), und bei „0 Provider auf Seite 1"
oder „Keine CSV" einmalig performLogin + Retry, bevor aufgegeben wird.

**C1c [P1, BESTÄTIGT, wirkconfig-abhängig] Download-Ordner wird vor jedem CSV-Download komplett von CSVs geräumt.**
`src/downloader/SignalDownloader.java:1118` + `:1382-1396` (`cleanupDownloadDirectory` löscht
ALLE `.csv` in `configManager.getDownloadPath()`). Der Pfad ist frei konfigurierbar (SetupDialog);
zeigt er auf einen allgemeinen Ordner (z. B. Downloads), löscht der Downloader dort regelmäßig
sämtliche CSVs des Nutzers. Default (eigener `download`-Ordner) harmlos — deshalb P1 statt P0.
Fix: nur Dateien löschen, die der Downloader selbst in dieser Session angelegt hat, oder
pro-Lauf-Temp-Unterordner nutzen.

**C5a [P1, BESTÄTIGT] Fenster schließen hinterlässt Chrome, Scheduler und Threads.**
`src/gui/MqlDownloaderGui.java:108`:
```java
setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
```
Kein WindowListener: `driver.quit()` (nur in `DownloadManager.cleanupDownload`:269),
AutoScheduler-Stopp und REST-Stopp laufen beim Schließen nicht. Chromedriver+Chrome überleben die
JVM als Waisenprozesse; beim wöchentlichen Automatiklauf summiert sich das. Fix:
WindowClosing-Handler: Download stoppen + waitForDownloadCompletion (mit Timeout), Scheduler/REST
stoppen, dann EXIT.

### P2

**C5b [P2, BESTÄTIGT] Limit-Race: GUI quitet den WebDriver, ohne den Downloader zu stoppen.**
`src/gui/DownloadManager.java:149-160`: im progressCallback wird `stopRequested = true` (GUI-Feld)
gesetzt und `cleanupDownload()` in einem Parallel-Thread gestartet — aber `activeDownloader.
setStopFlag(true)` fehlt (nur `stopDownload()`:215-218 macht das). Der SignalDownloader hat sein
eigenes Flag und navigiert auf dem bereits gequiteten Driver weiter ⇒ Folgefehler im
Protokoll/Statistik. Fix: im Limit-Zweig activeDownloader stoppen und auf Thread-Ende warten.

**C5c [P2, BESTÄTIGT] Status „ERFOLGREICH HERUNTERGELADEN" auch ohne CSV.**
`src/downloader/SignalDownloader.java:969-979`: scheitert die Trading-History (nur Warn), läuft
trotzdem `updateProgress(providerName, "ERFOLGREICH HERUNTERGELADEN", true)` — Erfolg zählt auch
bei fehlender CSV; der Scanner sieht das Signal später nur als 404. Fix: Erfolg nur werten, wenn
HTML+CSV vorhanden; sonst eigener Status „TEILFEHLER (CSV fehlt)".

**C1d [P2, VERDACHT] ID-Extraktion aus dem Export-Dateinamen per Ziffern-Konkatenation.**
`src/downloader/SignalDownloader.java:1219`:
```java
String originalId = downloadedFile.getName().replaceAll("[^0-9]", "");
```
Enthält der MQL5-Export-Dateiname weitere Ziffern (Signalnamen wie „Pure Gold 2000" sind üblich),
entsteht eine falsche „ID" im Zielnamen `{Name}_{falscheID}.csv`; `ProviderFiles.extractSignalId`
(:86-100) erwartet reine Ziffern nach dem letzten Unterstrich — Zuordnung bricht. Heutige
Produktivdateien (MSC_SuperGold_IC_Pro_2381088.csv, Gold_and_GBPUSD_2383311.csv) sind korrekt
gepaart, daher VERDACHT (tritt nur bei ziffernhaltigen Exportnamen auf). Fix: ID aus der URL
(`providerId`) nehmen statt aus dem Dateinamen.

**C2c [P2, VERDACHT] „Last 3 Months" ohne Sortierung; Average3MonthProfit-Fenster verschiebbar.**
`src/utils/MonthDetailsExtractor.java:60-66` (getLastThreeMonthsDetails) nimmt die **letzten
Listeneinträge in HTML-Reihenfolge**, während getAllMonthsDetails (:109) explizit sortiert —
rendert MQL5 das neueste Jahr zuerst, mittelt `Average3MonthProfit` über die ältesten Monate.
Zudem gilt der neueste EINTRAG pauschal als „aktueller Monat" und wird übersprungen — bei
inaktiven Signalen (Tabelle endet Vormonat) verschiebt sich das 3-Monats-Fenster um einen Monat
(MPDDCalculator.java:108/132). Vollständige Kalendermonate sind gegeben (lfd. Monat wird
übersprungen), aber das Fenster ist nicht das nominelle. Fix: getLastThree auf die sortierte
Variante stützen; „aktueller Monat" am Kalender vergleichen, nicht am neuesten Eintrag.

**C6a [P2, BESTÄTIGT] Gemischte Logging-Frameworks: die entscheidenden Warnungen fehlen im Log.**
`MPDDCalculator.java:17` / `HtmlDatabase.java:12` nutzen `java.util.logging`, der Rest log4j2 —
JUL ist nicht konfiguriert; „Keine monatlichen Profite … gefunden" erscheint NICHT in
application.log (grep 04.10./27.09.: 0 Treffer). Die Ursache von C2a war im Produktiv-Log damit
unsichtbar, nur das ChartDataExtractor-Symptom war sichtbar. Fix: auf log4j2 umstellen.

**C4a [P2, BESTÄTIGT] Instabile JSON-Typen durch deutsches Dezimalkomma.**
`HtmlConverter.java:199-220` formatiert mit `String.format` ohne `Locale.ROOT` ⇒ „Balance=860,41";
`JsonWriter.numberOrString` (JsonWriter.java:89-104) parst nur Punkt-Zahlen als Number —
Komma-Werte gehen als String raus, Punkt-Werte als Zahl. Typ eines Feldes schwankt je Signal.
Fix: Locale.ROOT beim Schreiben oder Parser mit Komma-Normalisierung in JsonWriter.

**C5d [P2, BESTÄTIGT] Verpasster Automatik-Lauf wird nicht nachgeholt.**
`MqlDownloaderGui.handleDoAllButton:282-285`: läuft um Fr 18:00 bereits etwas, wird der
Gesamtprozess nur verworfen; `AutoSchedulerManager.scheduleNextRun` plant sofort den nächsten
Freitag — die Woche ist still verloren. Fix: kurze Retry-Schleife (z. B. stündlich bis Mitternacht).

**C2d [P2, BESTÄTIGT] Ausschlussgründe für den Scanner nicht abfragbar.**
Verworfen werden Signale durch (a) 3MPDD<0.5-Löschung (Grund nur in `download/conversionLog.txt`,
HtmlConverter.java:176 — nicht in H2/REST), (b) Abonnenten-Sortierung + Abbruch beim ersten
0-Abonnenten-Signal (SignalDownloader.java:649-652 — alles dahinter wird nie geladen, Grund nur
implizit), (c) Löschung bei Extraktionsfehler (nur Log). Fix: Ausschluss-Tabellen in H2 +
REST-Endpunkt (z. B. /excluded), damit der Hub „Signal existiert, wurde gefiltert, weil X" sagen
kann.

### P3

- **C1e [GRENZE]** Rate-Limit = rein zufällige Wartezeit (4000–8000 ms Prod.) zwischen Navigationen
  (SignalDownloader.java:1309-1313); Recovery-Refresh, Sortier-Klicks und Retry-Serien zählen in
  kein globales Budget; ein Zähler/Minute existiert nicht. Sequenzieller Ablauf + 4 s Minimum
  wirken praktisch, sind aber kein echtes Limit. Parallele Netzwerk-Aktionen sind ausgeschlossen
  (Download-Buttons deaktiviert, Jobs serialisiert), Convert läuft lokal.
- **C1f [P3]** Export-Klick nur EIN XPath ohne Fallback (SignalDownloader.java:1132-1136,
  `text()='Trading history'|'Handelshistorie'` bzw. :1136 'History'|'Historie') — Label-Änderung ⇒
  stiller CSV-Verlust (nur Warnung). MT4/MT5-Exportpfade werden korrekt der Plattform überlassen
  (UI-Klick statt direkter /export-URLs, keine 404-Problematik).
- **C6b [P3/GRENZE]** pom.xml:24-25 `source/target 1.8` ohne `--release` bei installiertem JDK 25 —
  baut (mit Warnung), API-Kompatibilität ungeprüft. deploy.ps1 paketiert mit `-DskipTests`
  (Deployment ohne Tests). start.bat ok (keine problematischen absoluten Pfade; Leerzeichen-safe
  durch cwd-Nutzung).
- **C6c [P3]** Hardcodiertes Wurzelverzeichnis `C:\Forex\MqlAnalyzer` (MqlDownloaderApp.java:17,
  MqlDownloaderGui.java:56) — keine Umschaltung/Parameter. Keine log4j2.xml im Repo (liegt im
  Produktiv-Root; LoggerManager-Default schreibt relativ `logs/application.txt`).
- **C4b [P3]** `/health` und `/providers` rufen pro Request `getAllSubscriberStatistics()` ab
  (korrelierte Subqueries über alle Signale, RestApiServer.java:266/273) — LAN-vertretbar, ohne
  Cache aber O(Signale) je Health-Poll.
- **C4c [P3]** CORS `*` mit optionalem Token (RestApiServer.java:980-986); H2 mit `sa`/leerem
  Passwort + AUTO_SERVER (DatabaseManager.java:30) — nur für vertrauenswürdiges LAN vertretbar.
- **C6d [P3]** Chrome-Optionen `--disable-web-security`, `--allow-running-insecure-content`
  (WebDriverManager.java:141-142) und UA eines Chrome 91 (:118) — Bot-Erkennungs-/Sicherheitsrisiko.
- **C6e [Fundort, kein Inhalt]** MQL5-Zugangsdaten stehen KLARTEXT in
  `C:/Forex/MqlAnalyzer/config/MqldownloaderConfig.txt` (keys username/password,
  ConfigurationManager.java:85-99 speichert direkt). Nicht im Git-Repo; Empfehlung: Windows-Credential-
  Store/env statt Properties-Datei.
- **C3a [GRENZE]** Kein Backup-/Migrationswerkzeug für die H2-Datei (`config/subscribers*`);
  Schema-Evolution läuft über idempotente DDL + Migrationen — sauber, aber ohne Datensicherung.

## 2) Widerlegte Verdachte (explizit)

- **H2-Connection-Leak: WIDERLEGT.** Jede Operation öffnet/schließt Connections über
  try-with-resources (DatabaseManager.java:72, 220, 316, 360, 397, 447, 487, 521, 560); Methoden
  sind synchronized; kein Feld hält eine Connection offen.
- **Unvollständiger Historien-Schreib über intakte alte Zeile: WIDERLEGT.**
  `checkAndUpdateSubscribers` schreibt Snapshot+Historie in EINER Transaktion mit Rollback
  (DatabaseManager.java:221-277); Migrationen sind idempotent und bei Unterbrechung fortsetzbar
  (:119-171, DDL-Kommentar).
- **REST: Pfad-Traversal über Report-/CSV-Namen: WIDERLEGT.** `ProviderFiles.findByName`
  (:114-126) lehnt `/`, `\`, `..` ab und löst NUR exakt gegen die gelisteten Dateien auf;
  hrefs werden pro Segment encodiert (RestApiServer.java:923-927).
- **REST-Sortierung/Pagination (Review 28.09.): BEHOBEN (c44d2f6).** Default absteigend
  (RestApiServer.java:797-827), pageWindow/parseLong geklammert bzw. 400 (:841-847, :859-868);
  Test `katalogDefaultAbsteigendUndLimitGeclammt` (RestApiServerTest.java:236) vorhanden.
- **Detailabruf löst Plattform-Requests aus: WIDERLEGT.** Der komplette REST-Pfad liest nur
  Dateisystem + H2; Selenium/Crawler werden nie berührt.
- **MT4-S/L-Verlust: WIDERLEGT.** MT4-Orderbuch-CSV (reales Beispiel ATong_2327790.csv, Header
  `Time;Type;Volume;Symbol;Price;S/L;T/P;…`) wird 1:1 durchgereicht; MT5-CSV reale 11 Spalten
  ohne S/L — erwartbar.
- **Scanner-Kommunikation Initial Deposit: STAND BESTÄTIGT offen.** HtmlConverter schreibt
  Balance/Subscribers/MaxDDGraphic/EquityDrawdown/Average3MonthProfit/StabilityValue/
  MonthProfitProz/3MPDD (:199-220) — kein Initial-Deposit-Feld; MetricsParser kennt keins.
  Hub-Doku „liefert künftig der Downloader" bleibt aktuell.

## 3) Logs-Stichprobe (Klassifikation, C6)

- Umfang/Zeitraum: 15 rotierte Logs 29.12.2025–27.09.2026 + application.log (04.10.).
  Stichprobe: application.log 04.10. 10:03–10:28 (4.853 Zeilen, 402 WARN, 0 ERROR) und
  application-2026-09-27-1.log (637 KB, 374 identische WARN).
- „Datumsbereich fehlt"-Warnung (ChartDataExtractor): **WEITERHIN FEHLERHAFT** — kein kosmetisches
  Restrisiko, sondern das Hauptsymptom von C2a (leeres MonthProfitProz); trat an beiden Tagen bei
  100 % der Warnungen auf.
- Monatsrendite-Warnungen („Keine monatlichen Profite", „Zu wenige Monate"): im log4j-Log
  **unsichtbar** (JUL, siehe C6a) — 0 Treffer; Klassifikation: vorhanden, aber ins falsche
  Logging-Framework — Verhalten selbst „erwartbar falsch" (0 statt Fehler).
- heutiger MQL5-Lauf (mql5download.txt): 48/48 SUCCESS (100 %), danach „PAGE 1/2: 0 Provider
  gefunden" → BENUTZER-STOPP — Beleg für C1b (kein Auto-Recovery nach Sessionverlust).
- Randbeobachtung: `download/` enthält Alt-Ordner `mql45`, `mql45_diamond trade`, `mql4mql5_`
  (Spuren historischer Pfad-Bugs, aktueller Code legt sie nicht mehr an — nicht als Befund gewertet).

## 4) Pflichttest-Mapping (C7, nur gelesen)

| Pflichttest | Status | Ort |
|---|---|---|
| MT4+MT5 zum selben Signal (Composite-Identität) | VORHANDEN | DatabaseManagerTest (6 Tests) |
| Login-HTML statt CSV | FEHLT | kein SignalDownloader-Test überhaupt |
| Datumsbereich fehlt / Monats-Tabelle | FEHLT | kein MonthDetailsExtractor-/ChartDataExtractor-Test |
| Dezimalkomma | TEILWEISE | CsvParserTest (RFC 4180, 7 Tests); Komma-Zahlen in Metrics/JsonWriter ungetestet |
| Paginierter REST-Katalog | VORHANDEN | RestApiServerTest.katalogDefaultAbsteigendUndLimitGeclammt |
| MPDD-Grenze (0,5) | FEHLT | kein MPDDCalculator-/HtmlConverter-Test (Löschverhalten!) |
| Sessionretry/Neulogin | FEHLT | — |
| Downloadabbruch (Cancel) | FEHLT | kein DownloadManager-Test |
| Beschädigte/abgeschnittene letzte Datei | FEHLT | keine Validierung im Code (C1a) |
| Scanner-Akzeptanz aus realem Export | FEHLT (hier) | liegt scanner-seitig; Downloader liefert Rohdaten 1:1 |

Gesamtbestand: 15 Testdateien, Schwerpunkt REST/DB/GUI — Download-, Konvertier- und
Kennzahlen-Kern sind ungetestet.

## 5) Offene Fragen

1. Ist `subscribersOnly=true` bewusste Dauerlösung? Es deaktiviert currently als Seiteneffekt den
   MPDD-Löschfilter und ist der einzige Schutz vor C2b — nach Fix von C2b sollte der Filter
   bewusst (mit Quarantäne) wieder aktivierbar sein.
2. Seit wann genau ist die Monats-Tabelle der Signalseite geändert (ältere TXT mit Werten bis
   ~2026/04 vs. leere aktuelle)? Im Repo nicht ermittelbar — für den Fix ist ein aktuelles
   Beispiel-HTML zu archivieren.
3. Verbraucht der SignalKiScanner `Average3MonthProfit` aus /metrics als Filtergröße? Wegen C2a
   ständen dann >50 % der Signale mit Ertrag 0 im Hub (scanner-seitig zu verifizieren, Pak C
   greift nicht in den Hub-Code ein).
