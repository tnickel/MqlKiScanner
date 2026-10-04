# Paket I — Adversariale Gegenprüfung der umgesetzten Fixes (04.10.2026)

Auftrag: unabhängige Gegenprüfung der Schlüsselentscheidungen/Fixes aus den
Paketberichten A–H. Nur lesend (Read/Grep/git diff, gezielte pytest-Einzeltests,
Orakel-Lauf); keine Änderungen außer diesem Bericht.

Methode/Basis:
- Working-tree-Diffs je Projekt (SignalKiScanner 24 Dateien; MqlDownloader 3;
  PelicanTrading 1; roboforex 2; vantage 4; zulumonitor 1; startall.bat/start.bat).
- Java-Codebefunde durch vollständiges Lesen der benannten Klassen
  (EquityKurve.java beider Monitore, ReportService, SignalPayloadBuilder,
  RestApiServer, GlmClient, TradeStore, HtmlConverter, MPDDCalculator,
  DataExtractor, MetricsParser).
- Pytest: test_review_2026_10_04 / test_beweis_dedup / test_retdd_equity_pipeline /
  test_quellen (75 bestanden, 135 s) + test_ampel_matrix /
  test_retdd_kriterien_prompts / test_drawdown_anzeige (54) +
  test_review10_stop_gate / test_review15_reports / test_pdf_reports (43).
- Orakel pruef_orakel.py ausgeführt: 22/22 PASS.

---

## I1) [P0 A2a] Dedup-Beweis-Durchreichung — **BESTÄTIGT (mit einer Lücke)**

Belege:
- `src/mqlkiscanner/portfolio_statistik.py:84,129,211-213` — monatsrenditen,
  effizienz_kennzahlen, statistik reichen `plattform_positions` durch; Signatur
  + Default None (kein Beweis = roh, ehrlich).
- `src/mqlkiscanner/pipeline.py:77-79` (_implizite_kapitalbasis), `:1567-1569`
  (analyze_candidate, `res.plattform_trades`), `:1985-1987` (Refresh-Pfad,
  `st.get("trades")`).
- Roundtrip intakt: Persistenz `pipeline.py:1676` (`"plattform_trades"` in
  stats_payload) bzw. `:806` (Forensik-JSON) → Rücklesen `pipeline.py:469`
  (`results_from_db`), Studie `equity_studie_ui.py:58-59`.
- Semantik identisch zur Forensik: derselbe Parameter landet in demselben
  `parser.load_export` (parser.py:225-246, Beweisregel „Anzahl == Zeilen ohne
  Mehrfachvorkommen").
- `analyze_local_files` (pipeline.py:1985): dort ist `st = report["stats"]` die
  EIGENE Zeilenzahl ohne Beweis → roh == anzahl → kein Dedup. Konsistent zum
  engine-Lauf ohne Beweis (Demo-Modus), kein Widerspruch.

Lücke (mittel): NICHT erfasst sind `llm_runner.py:93,243` —
`build_trade_payload(load_export(result.trades_path))` OHNE Beweiswert.
Für bewiesen duplizierte Signale (THG, 27,4 %) sieht die KI-Trade-Analyse die
Doppellieferung: eigene Verlustserie/Trade-Zählungen im Payload (trade_data.py:
107-123) bleiben verdoppelt, während Forensik/Ampel deduped rechnen — exakt das
B25-Phänomen („Verlustserie 120 statt 50"), nur noch im LLM-Bericht. Ampel/Score
unberührt (Engine-Bindung), aber Berichtstext kann falsche Trade-Muster behaupten.
`engine.py:67` (MT4/MT5-Vergleich) und `agenten/delta.py` bleiben bewusst roh
(beidseitig konsistent — vertretbar).
Nachbesserung: `plattform_positions=getattr(result, "plattform_trades", None)` in
llm_runner an beiden Stellen.

Testabdeckung: effizienz/monatsrenditen dedup-wie-Forensik getestet; ABER
`test_statistik_nimmt_plattform_trades_je_ergebnis` ist LEERLAUFEND —
`stat["kurven_pro_signal"]` existiert nicht (Rückgabe-Keys: signale,
verlustmonate_cluster, gemeinsames_fenster, instrument_overlap;
portfolio_statistik.py:288-294) → `kurve is None or …` passiert vacuous.
Siehe I13.

## I2) [P0 A1c/D1/F6a/V5/Z] RetDD-Nenner nur Kurs-Rekonstruktion — **BESTÄTIGT**

(a) Java-Codebefund „Closing-Kurve" stimmt exakt:
- PelicanTrading `model/EquityKurve.java:57-84`: Kurve = Startpunkt 0 + je
  GESCHLOSSENEM Trade kumuliertes PnL; offene Positionen erzeugen GENAU EINEN
  Endpunkt mit unrealisiertem PnL obendrauf. Kein historischer
  Floating-Verlauf zwischen Closings. `ReportService.tradeDdAusTrades`
  (ReportService.java:57-70) rechnet DD über genau diese Punkte; REST liest
  trade_dd.csv (RestApiServer.java:544-553).
- RoboForex `model/EquityKurve.java:20-49`: noch strenger — NUR geschlossene
  Trades (kumuliertes netPnl je Close-Time), GAR KEIN Floating-Endpunkt;
  Basis aus Yield rückgerechnet (SignalPayloadBuilder.java:44-52), REST
  trade_dd.csv (RestApiServer.java:457-472). Beide Male ist „historisch
  floating-inklusiv" schlicht nicht enthalten — der Paket-D-Befund D1a
  (einschl. Zahlenbeispiel Yu Trading Club) wird vom Code getragen.
- Umsetzung im Scanner: `pipeline.py:279-303` (_equity_messwerte nur noch
  Kurse; Monitor aus dem Nenner-Set entfernt), Skip der Kurs-Reko bei
  Monitor-Wert aufgehoben (`pipeline.py:1424-1437`, Kursanbieter startet,
  Log nennt Closing-Kurve/Schranken-Kanal). Prompts synchron:
  llm/prompts.py (3 Stellen) + config/prompts/{risiko_analyse,gesamtbericht,
  portfolio}.md, B12-Sync-Test grün; ampel_matrix.py:124-133 + regelwerk.py
  Texte angepasst.

(b) Regelkonflikt-Auflösung vertretbar: Die Design-Regel 03.10. hat zwei
Sätze — „NIEMALS geschlossene Trades/Balance-DD/Plattform-Selbstauskunft als
Ersatznenner" (absolut) und die Klammer „(valide H1-/Monitor-Messung, höchste
davon)" (kontingent auf die Annahme, der Monitor messe Equity floating-inklusiv).
Diese Annahme ist jetzt code-seitig widerlegt; der Monitor-Wert fällt unter die
absolute Verbotskategorie (Closing-Kurve ≙ Trading-DD-artig). Die Auflösung
zugunsten der eigenen Messung ist damit regelkonform UND konservativ im
Sinne von „Risiko vor Ertrag", weil der Monitor als 5. Kanal der harten
30-%-Schranke erhalten bleibt (pipeline.py:553,596,621,1037; pdf_reports.py:266;
Test belegt 🔴 bei Monitor 35 %). Der alte Nutzer-Wunsch „keine Doppelarbeit"
(29.09.) beruhte auf derselben widerlegten Annahme — Aufhebung dokumentiert im
Code-Kommentar und im Test-Kommentar (test_quellen.py:283-293).
ABER: AGENTS.md (Design-Regel Ertrag/RetDD) sagt weiterhin „valide H1-/Monitor-
Messung, höchste davon" — Datei im Working Tree NICHT angefasst. Dok-Drift;
Nachbesserung: AGENTS.md-Regelsatz + kurzer Fix-Report (Verhaltensänderung:
Monitor-nur-Signale verlieren RetDD/Grün bis Kurs-Reko vorliegt).

(c) Hartes Risiko „Grün durch kleineren Nenner": Ja, beide Richtungen sind real
und Tests fixieren sie bewusst:
- Reko vorhanden: Nenner kleiner als max(Reko,Monitor) → RetDD größer →
  🟡→🟢 möglich (test_ampel_matrix: 15/10=1,5 → GRÜN). Regelkonform: Nur eine
  VALIDE Messung darf Nenner sein; die harte Schranke (5-Kanal-max inkl.
  Monitor) begrenzt das Risiko weiterhin, und Monitor-DD >30 % sperrt.
- Reko fehlt (kein Terminal/Abdeckung <95 %): RetDD unbekannt → kein Grün mehr
  aus Monitor (test_review10_stop_gate: alle vormaligen 🟢-Fälle jetzt 🟡;
  test_retdd_equity_pipeline: Monitor-allein → RetDD None → 🟡).
Nebenwirkung für den Bestand: Quellen-🟢 von gestern (HRC Algo, ImpulseNet —
Grün u. a. über monitor-basierten RetDD nach Score-Gate-Entfernung) können beim
nächsten Scan auf 🟡 fallen, wenn die Kurs-Reko nicht zustande kommt (Terminal-
Politik markt_start_erlauben, Symbol-Abdeckung). Konservative Richtung, aber
Nutzer-sichtbar → im Fix-Report/AGENTS.md kommunizieren.

## I3) [P0 F4] RoboForex Profit-Spalte BRUTTO — **BESTÄTIGT (Kommunikationslücke)**

- Algebra exakt: `RestApiServer.mql5Zeile` schreibt nun
  `netPnl − commission − swaps`; Scanner-Netto = `profit + commission + swap`
  (models.py:28-30) → (n−c−s)+c+s = n, vorzeichenunabhängig (auch positive
  Commission). `num()` (RestApiServer.java:409-414) nutzt Double.toString —
  keine Rundung, nur binäre Epsilon (vernachlässigbar).
- Tests schlüssig angepasst (10.0 statt 9.3; −0.22 mit Rückführ-Kommentar —
  Scanner-Netto wieder −0.3815).
- Lücke: Cache-Kommunikation. Der Scanner-Artefakt-Cache (ingest.py hole_trades)
  heilt per SHA erst dann, wenn der NEU gebaute RoboMonitor andere CSV-Inhalte
  liefert. Läuft der alte Prozess weiter, bleibt die Doppelt-Abzugs-Semantik
  unbemerkt aktiv — kein Protokoll-Versionssprung, kein Semantik-Marker (z. B.
  metrics-Feld), kein Scanner-Log-Hinweis, kein Re-Scan-Aufruf im Report.
  Nachbesserung (klein): RoboMonitor neu bauen+starten und Full-Scan erzwingen;
  sauber wäre ein metrics-Marker „profitSemantics: brutto" oder Version-Bump,
  an dem der Scanner den Umbruch erkennt.

## I4) [P1 C2b] MqlDownloader NaN statt 0.0-Sentinel — **BESTÄTIGT**

- HtmlConverter.java:167-180: NaN-Zweig VOR dem Löschvergleich — gelöscht wird
  nur bei !isNaN && !skipFilter && <0.5; exakt wie gefordert. calculate3MPDD
  (HtmlConverter.java:283-286) und calculateMPDD (MPDDCalculator.java:49,69)
  liefern NaN statt 0.0.
- Keine übrig gebliebenen Referenzen: deleteRelatedFiles nur noch Definition
  (DataExtractor.java:99, privat, ungenutzt — kompiliert) + HtmlConverter;
  grep über src/ findet KEINEN weiteren Aufrufer von calculateMPDD/calculate3MPDD
  (0.0-Sentinel-Konsument existiert nicht).
- NaN-Weitergabe: `String.format("%.4f", NaN)` → „NaN" in der txt
  (HtmlConverter.java:226); MetricsParser liest Werte als Strings; der Scanner
  parst über _zahl/_platform_float — NaN (Zahl oder String) fällt jetzt zum
  Default (scoring._platform_float, Orakel M27 grün). Rest: MetricsParser
  speichert nur Strings, JsonWriter gibt Strings aus — kein Java-seitiger
  numerischer Konsum von 3MPDD gefunden. Unschädlich.
- Anmerkung:DataExtractor wirfen RuntimeException statt Datei zu löschen —
  Aufrufer (HtmlConverter-Konvertierung) muss das fangen; vor dem Fix war das
  Verhalten „löschen + weiter", jetzt „Abbruch des Einzelvorgangs". Kein
  anderer Aufrufer gefunden, der auf stilles Weiterlaufen setzt. Vertretbar.

## I5) [P1 B1a] scan_launcher restore_current_reports nur bei full — **BESTÄTIGT**

- scan_launcher.py:299-315: Restore-Schleife nach GUI-Muster
  (`if pipeline.restore_current_reports(r, settings): jobs.remove(r)`);
  Iteration über list(jobs)-Kopie korrekt; Exception → Signal bleibt in jobs
  (Neuerstellung statt Datenverlust).
- Settings-Typ identisch: GUI scan.py:901 nutzt cfg (Settings-dict aus
  config.load_settings-Kette), Launcher `settings = config.load_settings()`
  (scan_launcher.py:83) — beides dict, restore_current_reports(
  result, settings: dict) (pipeline.py:1044) braucht keine Laufzeit-Toggles.
- Teilscan bleibt „alle Stufen neu" (Modus-Vertrag) — korrekt nur `modus ==
  "full"`. Keine Testabdeckung für den Launcher-Restore (siehe I13).

## I6) [P1 B2a] Scheduler-Versuchsdeckel — **BESTÄTIGT**

- scheduler.py:241 SCAN_VERSUCHE_PRO_TAG=3; faellige_scans prüft
  versuche < 3 für beide Modi (scheduler.py:174-183).
- Zählung NUR im gehaltenen Lock (scan_launcher.py:96 innerhalb `with
  lock.lauf_lock(...)`): Lock-Kollision wirft VOR dem Zählen → GUI-/Daemon-Lauf
  verbraucht keinen autonomen Versuch — richtig.
- Format „YYYY-MM-DD|n" robust: partition + Datumvergleich + int-try
  (scan_launcher.py:46-70); falsches Datum → 0.
- F4/B8 erhalten: skipped/Login-Abbruch setzt KEINE Erfolgs-Merker
  (scan_launcher.py:100-110 unverändert), Erfolg setzt Merker weiter →
  Wiederholung nach Login-Fix am selben Tag bis 3× möglich. Test deckt
  Zählen+Deckel+Tagesreset (test_review_2026_10_04.py:113-122).

## I7) [P1 Z5] zulumonitor System-Prompt — **BESTÄTIGT**

ReportService.java:77-89 übergibt jetzt nicht-leeren system-Text;
GlmClient.chat (GlmClient.java:82-86) fügt ihn als role:system-Nachricht VOR
dem User-Prompt ein — wird wirklich genutzt, nicht ignoriert. Muster identisch
zu PelicanTrading/RoboMonitor (Injection-Guard, „Antworte auf Deutsch").

## I8) [P1 V1/V2a] vantage Truncation-Offenlegung — **BESTÄTIGT**

- VantageClient.java:93-127: gebündelter 10402-Hinweis am Ende (Liste der
  abgelehnten Kategorien + Konsequenz + Gegenmaßnahme) statt einzelner
  Routine-WARNs.
- TradeStore.java:100-121: meta „total=" + `Math.max(totalCount, trades.size())`
  (niemals total < count); totalVerfuegbar() liest zeilenweise startsWith —
  alte meta-Dateien ohne total → 0/unbekannt, verifiziert()/ladePfad-Parser
  (TradeStore.java:277-298) liest nur version/count/sha256 → abwärtskompatibel.
- RestApiServer.java:330-344: TradesStored/TradesTotalAvailable (null bei
  unbekannt)/TradesTruncated; Scanner-ingest mappt nur bekannte Keys
  (metrics_zu_stats), unbekannte werden ignoriert — unkritisch.
- App übergibt `Math.max(bundle.totalCount(), anzeigeTrades.size())`
  (VantageMonitorApp.java:1871); TradeBundle.totalCount existiert
  (VantageClient.java:305-306) — kompiliert logisch.

## I9) [P1 D1c] PelicanTrading null → Cache-Entfernung + Berechnet-Spalte — **BESTÄTIGT**

- PelicanMonitorApp.java:2293-2306: berechneTradeDd entfernt bei null den
  Alt-Eintrag aus tradeDdCache (mit HINWEIS-Log) statt ihn lautlos weiter-
  leben zu lassen; Zeitstempel-Map Pflegt mit.
- speichereTradeDd (2337-2348): Kopf „Id;MaxEqDdPct;Berechnet" — REST liest
  weiterhin Spalte 1/2 per split(";", -1) (RestApiServer.java:544-553) →
  unbeeinflusst; Kommentar bei 541-543 nennt noch alten 2-Spalten-Kopf
  (kosmetisch).
- ladeTradeDdCache (2319-2326): t.length>=2 Pflicht, Spalte 3 optional →
  tolerant für Altdaten. Nil returns keinen Wert → kein vergifteter
  trade_dd.csv-Eintrag.

## I10) [P1 H1] startall.bat + start.bat — **BESTÄTIGT (statisch)**

- startall.bat: `setlocal EnableDelayedExpansion` (Zeile 2) vorhanden →
  `if !errorlevel! equ 0` (66) korrekt; goto-Schleife (kein Klammer-Block),
  %VERSUCH%-Zähler passt; PowerShell-Strings enthalten kein `!` → keine
  versehentliche Delayed-Expansion; Ports konstant 8504+8089-8093 überall
  konsistent (19/28/65/74); `start "" cmd /c "cd /d "%BASE%…" && …"` —
  cmd-/c-Quote-Stripping (mehr als 2 Quotes → erste/letzte weg) etabliertes,
  funktionierendes Muster.
- Identitätsprüfung: Suite-Regex gegen CommandLine vor Stop-Process; fremde
  Portbesitzer werden nur gemeldet — sowohl in startall.bat (15-23) als auch
  start.bat (23-36; globaler streamlit.exe-Kill entfernt, (c) zusätzlich auf
  SignalKiScanner/streamlit_app.py eingeschränkt). Kleinere Anmerkung: Muster
  `streamlit_app\.py` in start.bat trifft theoretisch fremde Projekte mit
  gleichem Dateinamen — praktisch vertretbar.
- MqlDownloader/start.bat existiert, kompiliert+startet MqlDownloaderApp
  (mvn compile exec:java); GUI-Konstruktor ruft startApiServer() → apiEnabled
  default „true" (ConfigurationManager.java:230-233), Port-Default 8089
  (DEFAULT_API_PORT) → :8089 hört wirklich. Hinweis: mvn-Kaltstart kann die
  120-s-Bereitschaftsschleife (24×5 s) überdauern → FEHLT-Anzeige möglich,
  nur kosmetisch. Kein Ausführungs-Test durchgeführt (Auftragsregel).

## I11) [P2/P3-Bundle] Scanner-Kleinfixes — **BESTÄTIGT**

- scan.py:1816: Portfolio-PDF-Viewer liest jetzt `scan_results` — Korrekt,
  da ausschließlich dieser Key befüllt wird (streamlit_app.py:43,
  scan.py:81,145,151…); alter „results"-Key war immer leer (Bug real).
- lock.py:158-171: korrupte ts → alter=0, _lock_blockiert entscheidet an
  PID-Lebendigkeit/recycelter Startzeit (lock.py:78-103) — Daemon wirft nicht
  mehr; Test vorhanden.
- scoring._platform_float: Mischformat-Logik korrekt (letzter Trenner gewinnt:
  1.403,03 und 1,403.03 → 1403.03); NaN/inf (Zahl wie String) → Default;
  math-Import da; Orakel M27 + 2 Tests grün. Synergie mit I4 (Downloader-NaN).
- ertrag_monat_pct_forensik: MONAT_TAGE = 365,2425/12 (portfolio_statistik.py:
  30) statt 30,44 — jetzt identische Monatsdefinition wie effizienz_
  kennzahlen (pipeline.py:1552-1558). Kein eigener Test (siehe I13).
- Score-Gate-Texte: ampel_matrix.py (Score-Zelle informativ, 04.10.-
  Kennzeichnung) + regelwerk.py (Regeltitel/Kriterienzeile ohne Score-Gate)
  konsistent zum Code (Gate war bereits 85dc290/0799167 entfernt).

## I12) Orakel — **BESTÄTIGT (22/22 PASS; zwei Schönheitsfehler)**

Ausführung: `python doc/reviews/codereview_2026-10-04/orakel/pruef_orakel.py`
→ 22/22 PASS (Exit 0). Unabhängigkeit: SOLL-Werte aus Literalen/eigener
math-Herleitung (1.21^(MONAT/59) etc.), KEIN Projektformel-Import für SOLL;
Produktionsfunktionen werden nur für IST aufgerufen — nicht zirkulär. M05 ist
valide, weil ampel_for intern refresh_efficiency() aufruft (pipeline.py:592)
— die 0,9995-Grenze wird tatsächlich über den recomputeten RetDD geprüft.
Schönheitsfehler: (1) M02/M23/M24 sind reine Arithmetik-Selbstabgleiche ohne
Produktionskontakt (decken keine Produktionsfunktion); (2) M01-Kommentarzeilen
(43-47, 57) sind verworrene Redaktionsreste — harmlos, aber irreführend beim
Nachvollzug der konstruierten Dauer.

## I13) pytest + Abdeckungslücken — **BESTÄTIGT (172 Tests grün), Lücken siehe unten**

Gelaufen: test_review_2026_10_04 + test_beweis_dedup + test_retdd_equity_pipeline +
test_quellen = 75 PASS; test_ampel_matrix + test_retdd_kriterien_prompts +
test_drawdown_anzeige = 54 PASS; test_review10_stop_gate + test_review15_reports +
test_pdf_reports = 43 PASS. Kein Fail, keine Netzwerk-/LLM-/DB-Seiteneffekte
(conftest-isoliert).

Abdeckungslücken der NEUEN Fixes:
1. `test_statistik_nimmt_plattform_trades_je_ergebnis` ist VACUOUS (falscher
   Rückgabe-Key „kurven_pro_signal") — der statistik()-Durchgriff hat effektiv
   KEINEN wirksamen Test.
2. I5 (Launcher-Restore bei full) — kein Test (nur GUI-Pfad ist über
   test_review17_ui abgedeckt).
3. I2-Verhalten „Quellen-Signal mit Monitor-Wert startet jetzt Kurs-Reko" ist
   über test_quellen.py:283-293 abgesichert (kursanbieter_angefragt == [1]) —
   gut; offen ist nur die Endprodukt-Seite (s. I2b AGENTS.md).
4. scan.py-Session-Key (I11) und MONAT_TAGE-Konsistenz (I11) — ohne Test.
5. I6: „Lock-Kollision verbraucht keinen Versuch" nur strukturell (Zähler im
   with-Block), kein expliziter Test.
6. Java-Seite (I3/I4/I7/I8/I9): RoboForex hat 2 angepasste Tests (nicht
   gelaufen — mvn verboten); MqlDownloader/zulu/vantage/Pelican-Änderungen
   ohne neue automatische Tests; Batch-Dateien (I10) statisch-only.

---

## Gesamturteil

Alle 13 Prüfpunkte im Kern BESTÄTIGT — keine widerlegte Schlüsselentscheidung.
Die RetDD-Nenner-Entscheidung (I2) ist code-seitig dreifach belegt (beide
Java-Monitore messen nachweislich Closing-Kurven), regelkonform in der
Priorisierung „NIEMALS geschlossene Trades" über die kontingente Monitor-Klammer,
und die harte 5-Kanal-Schranke inkl. Monitor bleibt intakt (Test-belegt).

Nachbesserungen (Priorität):
1. [mittel] llm_runner.py:93,243 — plattform_trades an load_export durchreichen
   (KI-Trade-Payload rechnet sonst bei bewiesener Doppellieferung roh →
   verdoppelte Verlustserien im Bericht).
2. [mittel] AGENTS.md Design-Regel RetDD aktualisieren („nur H1-Rekonstruktion;
   Monitor = Schranken-Kanal, Closing-Kurve") + kurzer Fix-Report mit den zwei
   Verhaltensänderungen (Monitor-nur-Signale verlieren Grün bis Reko vorliegt;
   Quellen-Kurs-Reko läuft jetzt zusätzlich — RetDD-Bestand braucht Re-Scan
   mit Terminal) — Nutzer-sichtbare Ampelkippel.
3. [klein] Vacuous Test ersetzen (statistik()-Key korrigieren), RoboForex-
   Umbruch kommunizieren (Rebuild+Re-Scan; idealerweise Semantik-Marker im
   Protokoll), Restlaufzeit-Hinweis mvn-Kaltstart vs. 120-s-Warteschleife.
