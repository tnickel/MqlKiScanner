# Intensivreview 2026-09-29/30 — Sub-Review „Pelican" (PelicanTrading :8090 + Scanner-Schnittstelle)

Review-Agent: Pelican-Subagent · Read-only · Code-Stand Scanner: git `ccc383b` ·
Code-Stand PelicanTrading: git `9af1792` (HEAD 29.09.).
Ziellauf: Full-Scan 30.09.2026 00:02:20–02:53:53 (Europe/Berlin), Quelle „pelik",
781 Katalog-Einträge → 34 Kandidaten → 30 Forensik.

Geprüfte Artefakte (Kurzliste, Details je Befund): `PelicanTrading/data/pelicanmonitor.log`
(249 Zeilen, komplett), `providers.csv` (2223 Provider, alle Felder), `fx_rates.json`,
`trade_dd.csv`, `llm_reports.json` (61 Einträge), `data/reports/` (174 Dateien),
`signals/closed/` (4446 Dateien; 30 Vollisten + Stichproben), `abonnenten.db`
(Kopie `abonnenten_review.db` im Review-Verzeichnis), Scanner-DB-Kopie
`tmp/review_copy.db` (Tabellen datenquellen/quellen_artefakte/signals/forensik/
analyses/subscriber_history), Scanner-Cache `data/quellen/pelik/` (60 Dateien),
Java-Quellcode (RestApiServer, PelicanClient, Provider, Signal, SignalStore, CopierDb,
FxRates, ReportService, GlmClient, LlmSettings, PelicanMonitorApp-Auszüge),
Scanner-Quellcode (ingest.py, pipeline.py, scoring.py-Auszug, downloader_sync.py-Auszug),
Scanner-Prompts (risiko_analyse/gesamtbericht/portfolio).

Keine Änderungen an Produktivcode/Daten. Keine LLM-Aufrufe. 1 curl-GET auf
localhost:8090 (verbindungslos abgelehnt, s. Befund R6). Kein Token je benötigt
(token_required=false, s. Befund R7). Zugangsdaten nicht kopiert; config.json-Ausgabe
mit redigierten Key-Feldern gelesen.

---

## 0) Laufbelege (Aufgabe 1) — Kernauszüge pelicanmonitor.log

- Log umfasst 2026-09-27 15:21 … **2026-09-29 23:37** (letzte Zeile 249: „Statistik-Batch
  abgeschlossen"). **Keine Einträge am 30.09.**
- 29.09. 23:00–23:37 (Crash-Umfeld Scan #1): Z233 `23:00 KI-Berichte abgeschlossen (3 parallel) · 15 übersprungen`,
  Z234–237 zweifach REST-Stopp/Restart (23:09), Z240–248: App-Neustart 23:30 („Cache geladen: 2223 Provider (offline)"),
  23:36 Session abgelaufen → sofort Re-Login übernommen (Z246–248), 23:37 letzter Statistik-Batch.
  Der Monitor wurde also um den Scanner-Crash herum neu gestartet und war mit frischer Session UP.
- **Bediente der Monitor die Scanner-Requests um 00:02:24 (Katalog) und 00:05 (Trades)?**
  Direkt nicht logbar: `RestApiServer.behandle()` (RestApiServer.java:133-164) enthält
  **kein Request-Logging** — REST-Zugriffe erscheinen nie im Log. Indirekte Belege, dass
  der Monitor um 00:02–00:05 aktiv bediente:
  1. `fx_rates.json`: Kurse EUR/JPY/AUSD **„abgerufen": „2026-09-30T00:05:33"**, Kursdatum
     2026-09-29. `FxRates.cacheSpeichern()` (FxRates.java:126-138) schreibt nur bei einem
     echten Fremdwährungs-Request von metrics()/tradesCsv() — exakt in der Trade-Abrufphase
     des Scanners (quellen_artefakte fetched_at 00:05:03–00:05:12).
  2. Scanner-DB `datenquellen.letzte_pruefung` für „pelik": `{"status":"ok", … "anbieter": 781,
     "kennung": "Ryzen7950X", "latenz_s": 0.0, "token_required": false, "geprueft":
     "2026-09-30 03:02:33"}` — Verbindungstest kurz nach Scan-Ende erfolgreich.
  3. 60 quellen_artefakte (30 Signale × trades+metrics) mit fetched_at 00:05:03–00:05:12,
     SHA-256 der Dateien stimmt mit DB überein (Verifikation s. Befund OK-2).
  Latenzen/Statuscodes der Einzelrequests: **nicht nachweisbar** (kein Access-Log).
- Letzter „Signale laden"-Lauf im Sinne des Buttons (vollständiger Discover `ladeProvider`,
  PelicanMonitorApp.java:1054-1107: Liste + Details + Stats aller + `copierDb.snapshot`):
  **27.09. 23:17** (Log Z27 „2223 Provider geladen und gecacht") — der EINZIGE
  Snapshot-Tag in abonnenten.db. Danach nur noch Cache-Loads, Statistik-Batches und
  Tradelisten-Batches (jeweils `gefilterteListe`).
- Letzter Tradelisten-Batch: **29.09. 11:59** (Log Z172) — schrieb die 30 Tradelisten
  (mtimes 11:54–11:59, s. OK-3), letzte geladene Einzeln: Lexo mehrfach (u. a. Z163).
- Letzter Statistik-Batch: 29.09. 23:37 (Z249) → providers.csv mtime 29.09. 23:37.
- 429-Kette 15:48–15:55 (Z192–217): 26 KI-Berichte an GLM-Drosselung gescheitert,
  „10 parallel" (Z218); abends „3 parallel · 15 übersprungen" (Z233) — Parallelität
  danach auf 3 gedrosselt (git 17f595d).

## 1) Bestätigte Fehler (belegt)

**F1 — Keine.** Im Pelican-Teil der Kette wurde kein hart bestätigter Defekt gefunden,
der Daten falsch in den Scanner liefert. Die vier numerischen Kernketten (Katalogwerte,
Wochen, FX-Konvertierung, Kapitalbasis-Kennzeichnung) sind an echten Daten
nachgerechnet und stimmen (OK-1 … OK-5). Die folgenden Punkte sind semantische
Inkonsistenzen bzw. Betriebslücken mit Fehlwirkung, keine klassischen Bugs:

**F2 — Metrics „Trades"/„Wins"/„Losses" semantisch inkonsistent (Niedrig, belegt).**
- Ort: Lexo metrics-Cache `pelican_2000028_metrics.json`: `"Trades": 6664, "Wins": 2462,
  "Losses": 871`; Quell-Tradeliste `closed_2000028.csv` = 3296 Positionen ab Inception;
  Wins+Losses = 3333.
- Erwartet: Total ≥ Wins+Losses und ≈ Anzahl CSV-Positionen. Beobachtet: Total ≈ 2×(Wins+Losses);
  CSV ≈ Wins+Losses (±37). Plattform zählt offenbar Deal-Seiten/Teilfills mit.
- Auswirkung: keine auf Ampel/Score (Scanner rechnet Winrate selbst aus der CSV,
  `winrate_pct` aus Forensik); nur Anzeige/Stufe-1-Text. Korrekturidee: Feld im Katalog
  als „Trades (Plattform-Zählung)" benennen oder Wins/Losses/Total aus eigener Liste liefern.
  Verifikation: metrics von 5 Signalen gegen je eigene CSV-Vollliste gegenüberstellen.

**F3 — Abonnenten-Verlauf für Pelican-Signale bleibt im Scanner leer (Mittel, belegt).**
- Ort: `subscriber_history` (Scanner-DB): **0 Zeilen** für alle 30 pelik-Signale, obwohl
  `/pelican/history` für jeden Provider 1 Punkt (2026-09-27) liefern würde und
  `db.store_history_points()` (db.py:392+) auch Einzelpunkte schreibt.
- Ursache-Wolke: abonnenten.db enthält **genau einen** Snapshot-Tag (2026-09-27, 2223
  Provider — Monitor-Installationstag; Kopie ausgewertet: Tabelle copier_historie,
  1 distinct datum). Der History-/Sync-Lauf des Scanners hat zudem offenbar für
  pelik-Signale nie stattgefunden oder nichts übernommen — das ist aus der DB allein
  nicht unterscheidbar (**nicht nachweisbar**, welcher Sync-Weg gemeint war; Sync-Runs
  wurden nicht im Detail geprüft).
- Auswirkung: Abonnenten-Verlauf-GUI leer für Pelican; weekChange/monthChange null.
- Korrekturidee: (a) Monitor: „Signale laden" regelmäßig (Snapshot täglich), (b) Scanner:
  Sync für Quellen-Signale laufen lassen; Test: nach Sync ≥1 Zeile je pelik-Signal.

## 2) Begründete Risiken

**R1 — Monitor-Zweitmessung EQ-DD (bis 316 %) wirkt nicht auf Ampel/Score, verdrängt
aber die Scanner-Eigenmessung (Hoch, belegt in Wirkung, Bewertung der Messmethode unsicher).**
- Kette: Pelican `metrics.TradeEqDrawdownPct` (aus `data/trade_dd.csv`, berechnet in
  ReportService.tradeDdAusTrades, ReportService.java:57-70: Equity-Kurve aus realisierten
  Trades, **Basis = Endkumuliert / (returnInceptionPct/100)**, d. h. Nenner aus
  Plattform-Rendite rückgerechnet) → ingest.metrics_zu_stats
  (`monitor_trade_eq_dd_pct`, ingest.py:223, Kommentar: „Fliesst in KI-Analyse und DB,
  NICHT in die Drawdown-Schranke") → pipeline.py:915-924: **liegt der Wert vor, wird die
  Scanner-eigene Kursdaten-Equity-Rekonstruktion ÜBERSPRUNGEN** (`kursanbieter=None`)
  → scoring.evaluate (scoring.py:168+, 185-187) nutzt nur Trading-DD/EQ-DD/Bal-DD
  (+Reko sofern vorhanden — hier nie berechnet).
- Beobachtet (DB forensik+signals, 24 Forensik-Signale): 7 Signale mit Monitor-DD > 25 %:
  Deus ex machina 316,61 %, AccurateCopier 241,32 %, Grid King 70,64 %, Master H4-1
  66,52 %, TradeSystem 48,52 %, Lemonal 46,65 %, Golden Paradise 42,89 %, MidasAlgo 31,60 %.
  Lemonal bleibt **🟢 Ampel** bei gemeldet 8,56 % / Schranken-Max 8,56 %.
- Die Scanner-KI sieht den Wert (config/prompts/risiko_analyse.md:31, gesamtbericht.md:35,
  portfolio.md:28 deuten ihn; Risiko-Analyse Lemonal zitiert ihn wörtlich: „Kernbefund:
  Monitor-Zweitmessung … 46,65 % … Faktor ≈ 5,4 über dem gemeldeten Wert … (Engine-Ampel
  unverändert)") — aber Code-Schranke und Ampel bleiben unberührt.
- Einordnung/Risiko: Die Monitor-Messung hat einen selbst anfälligen Nenner (bei
  riesiger Plattform-Rendite wird die rückgerechnete Basis winzig; DD > 100 % wie bei
  Deus ex machina ist als echter Konto-EQ-DD unmöglich und deutet auf Basis-Artefakt
  oder fehlende Kontoflüsse/Entnahmen hin). Genau deshalb ist „ignorieren" riskant:
  Es gibt KEINE unabhängige zweite Messung mehr (Reko geskippt), und die eine
  vorhandene Zweitmessung, die den Skip begründet, geht in keine harte Schwelle ein.
  Verstärkt durch R2 (virtuelle Basis): die Scanner-eigene Trading-DD rechnet auf
  10.000-USD-Basis, auch das eine Annahme.
- Korrekturidee: monitor_trade_eq_dd_pct mit Sanity-Gate (z. B. nur 0 < Wert ≤ 150 %
  verwerten) als **viertes Maximum in die Drawdown-Schranke** aufnehmen ODER den
  Reko-Skip davon abhängig machen, dass der Monitorwert plausibel ist; alternativ
  Warn-Ampel-Kriterium „Zweitmessung Faktor ≥ 2 über gemeldet" einführen.
  Verifikation: Unit-Test — Signal mit monitor 46,65 % muss mindestens 🟡/Kernbefund-
  Ampelkriterium auslösen; Lexo (6,19 %) unverändert.

**R2 — Virtuelle Kapitalbasis 10.000 USD vs. echte Konten 530–1.001 USD: relative
Risiko-Prozente für Kleinkonten systematisch unterschätzt (Hoch, belegt).**
- Kette: Pelican metrics `InitialDepositVirtual: 10000.0` + Note (RestApiServer.java:387-389,
  bewusst kein `InitialDeposit`) → ingest.py:216 (`kapitalbasis_virtual_usd`) →
  pipeline.py:908-914 strikt geprüft (`_virtuelle_kapitalbasis`, pipeline.py:52-77) →
  forensik.json `kapitalbasis: {usd: 10000, quelle: "virtuelle_annahme", …}` — Kanal
  KAPITALBASIS_QUELLE_VIRTUELL funktioniert exakt wie dokumentiert (Aufgabe 6: ✓).
- Aber: Die Equity-Kurve (und damit Trading-DD-%, Schock-%) startet bei 10.000, während
  die Web-Balance vieler Provider weit darunter liegt (DB web_balance vs. 10.000):
  MicroJump 529,59 (0,05×), Gold VIP 656,28 (0,07×), ImpulseNet 897,66 (0,09×),
  SafeGold 998,22 (0,10×), Master H4-2 1.703 (0,17×), Master H4-1 1.750 (0,17×),
  Big Ben 2.683 (0,27×), GOLD Tokyo 2.847 (0,28×), Sydney Sunrise 2.971 (0,30×),
  Grid King 3.477 (0,35×), Mr_Profit_FX 4.437 (0,44×), ALPHA-SEVEN 4.861 (0,49×) u. a.
  (AIT FX 1.000,95 wäre auch betroffen — dessen Forensik scheiterte aber, s. R4).
- Folge: Bei einem echten Konto von ~530 USD sind trading_dd_pct und Schock-Prozente
  um Faktor ~5–20 zu NIEDRIG → Risikobewertung zu GÜNSTIG (gegen „Risiko vor Ertrag").
  Bei großen Konten (Lexo 32.147, Holy Grail 99.340, GOLD PRECISION 127.915) wirkt die
  Annahme umgekehrt konservativ. Die Richtung der Verzerrung hängt am Zufall der Kontengröße.
- Milderung vorhanden, aber unzureichend: Urteile/KI nennen die virtuelle Basis
  (Lexo gesamtbericht: „Alle USD-Werte haengen an der virtuellen Kapitalbasis 10.000 USD …";
  Risiko-Analyse nennt sie; forensik-JSON `quelle: virtuelle_annahme`; Cent-Abgleich
  bewusst aus (pipeline.py:501); nie als `initial_deposit_usd` erscheinend — Aufgabe 6
  vollständig bestätigt).
- Korrekturidee: implizites Initial rückrechnen `web_balance_usd − Σ(realisierte Profite)`
  (bei Vollliste ab Inception gut belegt; Lexo → 18.740, gemslime → 9.110) und als
  zweite Basis rechnen oder die virtuelle Basis auf `min(10000, max(implizit, …))`
  kappen; zusätzlich Schock-% auf max(Basis, Web-Balance) ausweisen.
  Verifikation: MicroJump trading_dd_pct muss mit impliziter Basis deutlich steigen;
  Testfixierung in pytest mit synthetischer CSV + Balance.

**R3 — weeks=0 bei 735/781 Katalog-Providern = „Stats nie geladen", nicht „jung" —
Scanner-Vorfilter weeks>=26 sperrt 747/781 aus (Mittel, belegt; fachlich teilweise
gerechtfertigt, Datenverfügbarkeitsverzerrung).**
- Berechnungsstelle: `Provider.wochen()` = `WEEKS.between(inception, LocalDate.now())`,
  0 wenn Inception null (Provider.java:242-246). Inception kommt ausschließlich aus
  `/api/strategies/{id}/stats` (PelicanClient.java:212-216) und wird nur für Provider
  geschrieben, deren Stats je geladen wurden: voll bei „Signale laden"
  (ladeProvider, alle — letzter Lauf 27.09. 23:17) oder im Statistik-/Tradelisten-Batch
  **nur für die UI-gefilterte Liste** (`gefilterteListe`, PelicanMonitorApp.java:1167
  bzw. 1287; gefiltert war „≥5 Wochen, ≥50 Copier" → 43–46 Provider).
- Gemessen (providers.csv): 781 Provider mit ≥1 Copier, davon 735 ohne Inception
  (weeks=0), 46 mit; **kein** Provider mit Copiers ≥ 50 hat weeks=0; 12 der 46 sind
  jünger als 26 Wochen → exakt die beobachteten 34 Kandidaten.
- Bewertung: Kein Rechen-Bug — weeks=0 ist „Alter unbekannt". Der Scanner-Filter
  (pipeline.py:752-770, `weeks is not None and weeks < min_wochen` → raus) kann
  „unbekannt" nicht von „echt <26 Wochen" unterscheiden und sperrt beides aus. Unter
  den 735 könnten alte, gute Provider mit 1–49 Copiern stecken — nicht nachweisbar
  ohne Stats-Load. Gegenrede: „Abonnenten >= 1"-Schwelle plus Nutzer-Katalog-Regel
  „nur mit Abonnenten" (git 9af1792) zeigt, dass der Bestand bewusst auf
  Qualitätskandidaten verdichtet wird; der 46er-Kern deckt alle ≥50-Copier-Provider ab.
- Auswirkung: Auswahlverzerrung durch manuellen UI-Filter des Monitor-Betreibers; der
  Scanner-Kandidatenraum für Pelican steht/fällt mit dieser einmaligen UI-Aktion
  (letzter voller Discover 27.09.; Stats-Nachzug nur bei laufenden Batches).
- Korrekturidee: Monitor: Inception (und nur dieses Feld) über den Discover-Feed
  liefern, wenn die Plattform es dort hergibt (Klassenkommentar PelicanClient.java:151-154
  nennt Inception-Rendite im Discover — prüfbar am Feed), oder Katalog-Feld
  `weeksUnknown: true` statt weeks=0 senden; Scanner: weeks=null nicht hart filtern,
  sondern nur bei bekannten Wochen. Verifikation: Katalog mit 781 Einträgen, davon
  weeks>0 deutlich > 46 ohne dass Stats-Updates nötig waren.

**R4 — 6/30 Pelican-Kandidaten ohne Forensik wegen fehlender Broker-Kennung
(USOIL/GER40) (Mittel-Hoch, belegt; Ursache in der Schnittstelle, Wirkung im Scanner).**
- Beobachtet (signals.stats_json.last_fehler): 4× „Keine anwendbare Kontraktspec
  (cross_broker=false, Broker des Signals UNBEKANNT …): USOIL" (u. a. AIT FX 2019435,
  Mtrader2, Mtrader Holy, TradeSystem — letztere AUD/EUR-Konten) und 2× „Keine belegte
  Brokerspezifikation fuer: GER40" (Yu Trading Club, Deus ex machina).
- Ursache: Quellen-Signale liefern `broker_server=null` (Pelican-Katalog hat kein Feld
  dafür; metrics liefern keins) → Öl-Spec ist broker-gebunden (1 vs 100 Barrel/Lot,
  AGENTS-Regel) und bleibt gesperrt. Ehrlicher Abbruch (kein falscher Wert) — aber
  20 % der Kandidaten sind damit strukturell nicht bewertbar.
- Pelican HAT je Trade einen `ServerCode` (SignalStore CLOSED_HEADER Spalte „Server";
  aus PelicanClient parseSignal `ServerCode`) — er geht in der mql5-Konvertierung
  (RestApiServer.mql5Zeile, 11 Spalten) verloren. Korrekturidee: metrics-Feld
  `Broker`/`Server` (häufigster ServerCode der Trades) liefern; Scanner-seitig
  Mapping ServerCode→contract_specs-broker. Verifikation: AIT FX läuft mit USOIL-Spec
  durch, Ergebnis deckt sich mit der Monitor-Nachmessung.
- Auswirkung: keine positive Einstufung dieser 6 (mit Risiko-vor-Ertrag vereinbar),
  aber Lücken im Katalogbild (AIT FX = #1 nach Abonnenten, 1514).

**R5 — Abonnenten-Snapshots eingefroren seit 27.09.; weekChange/monthChange immer null
(Mittel, belegt).**
- abonnenten.db (Kopie): genau 1 Snapshot-Tag (2026-09-27, 2223 Provider). Snapshot
  wird nur in `ladeProvider()` geschrieben (PelicanMonitorApp.java:1100) — letzter
  Lauf 27.09. 23:17. `CopierDb.zuwachs()` verlangt einen aktuellen Stand ≤ 2 Tage alt
  (CopierDb.java:107 `st.tageAlt > 2 → continue`) → am 30.09. (3 Tage) liefert der
  Katalog `weekChange/monthChange = null` für alle. Auch `/history` führt nur den
  Einzelpunkt 27.09. (Copier-Dopplung mit F3).
- Plausibilität Kopiererwachstum: aus der einzigen Messung nicht prüfbar; einziger
  Anhaltspunkt: Lexo 1.402 (27.09., abonnenten.db) → 1.425 (providers.csv 29.09.,
  Detail-Nachzug in Statistik-Batches PelicanMonitorApp.java:1198-1200), AIT FX
  1.487 → 1.514 — Bewegung plausibel, aber keine Zeitreihe.
- Auswirkung: „Tagesfrische" gilt für Trades (29.09. 11:54–11:59 ✓), nicht für
  Abonnentenzahlen-Verlauf. Scanner-seitig ohne Score-Wirkung (Kandidaten nutzen
  `subscribers`, nicht Change).
- Korrekturidee: Snapshot auch in batchStats()/batchTradelisten() schreiben (die
  NumCopiers aktualisieren sich dort ohnehin) oder „Signale laden" per Zeitplan.
  Verifikation: nach einem Stats-Batch existiert ein Snapshot vom aktuellen Tag.

**R6 — PelicanMonitor zur Review-Zeit OFFLINE (Info/Niedrig, belegt).**
- curl GET http://localhost:8090/api/v1/health am 30.09. (Review): Verbindung
  abgelehnt (exit 7). Letztes Lebenszeichen 03:02:33 (Verbindungstest in Scanner-DB ok).
  Für den Ziellauf folgenlos (Scan nutzte Cache/Requests um 00:05 erfolgreich),
  aber der nächste Scan/Teilscan/Betreuer-Lauf würde auf „Quelle pelik nicht
  erreichbar" laufen (pipeline verarbeitet Quellen-Fehler mit Log, ohne Abbruch).
  Autostart des Monitors ist nicht eingerichtet (nur run.bat) — Betriebsrisiko.

**R7 — REST ohne Token im Netz erreichbar (Niedrig, belegt).**
- `token_required=false` (Verbindungstest 03:02:33; RestApiConfig-Token leer;
  autorisiert() lässt alles durch wenn Token leer, RestApiServer.java:584-600).
  Nur GET, schreibgeschützt, CORS `*` — Daten solo (Trades, Balancen, Copier-AUM).
  Im LAN vertretbar; bei Exposition des Ports nach außen sollten Token gesetzt werden.

**R8 — Tradelisten-Tiefe bei weeks=0-Providern nur Tage bis ~3 Monate (Niedrig-Mittel,
belegt, durch Wochenfilter abgefedert).**
- Ohne Stats/Inception lädt der Batch nur 3 Monate Fallback (PelicanMonitorApp.java:1313-1320)
  — Stichprobe 2098792 (t.me/SHIBUYA_FX): nur 6 Trades 25.–28.09. Wäre der Wochenfilter
  abgeschaltet (s. R3-Korrektur!), kämen flache Forensiken in den Scanner. Holy Grail
  (Inception 2022-12-05): 15.340 Trades ab 2022-12-08 ✓ Vollliste; Lexo 3.296 ab
  2023-07-20 (Inception 2023-04-27; erste ~3 Monate ohne Close oder Lücke —
  nicht weiter nachweisbar).

## 3) Verifikationen OHNE Befund (Positiv-Belege)

**OK-1 Katalog→Scanner-Wertekette (Aufgabe 2), Lexo 2000028 und AIT FX 2019435:**
providers.csv → (Katalog-Item deterministisch aus providers.csv via
RestApiServer.item()/ladeProviders(), Katalog wird nicht gecacht) → signals-DB:
- Lexo: Copiers 1425=1425; Wochen 178 (Inception 2023-04-27 → 30.09.2026 = 178,4) ✓;
  AvgMonthPct 15.39928571 = ertrag_monat_pct 15.39928571 ✓; MaxDD −0.78 → eq_dd 0.78
  (effektiverDdMax=min(DDPct,DDBalancePct), Absolutwert) ✓; Balance 32.146,55 ✓; USD ✓;
  Leverage 500 ✓; updated_at 2026-09-30 00:05:08 ✓; platform „pelican", quelle „pelik" ✓.
- AIT FX: 1514/81 (2025-03-10 → 81,3)/0.27526316/2.13/1.000,95 ✓ jeweils identisch.
- metrics-Caches (pelican_2000028_metrics.json etc.): SHA-256 in quellen_artefakte
  stimmt mit Datei überein; Werte identisch zu providers.csv (Subscribers 1425,
  CopiersAum 3.933.585,12 = CopiersBalance×1, Fee 0.3=30 % Anteil, TopMarkets
  „AUDCAD 5888", MarketsCount 1, Weeks 178, Trades/Monat 10–364, Equity 32.121,50
  = Balance+UnrealisedPnl (Provider.equity(), Provider.java:228-232) ✓).
- Währungsfelder: currencyCode/currencyNote im Katalog; Currency, CurrencyRateToUsd
  (JPY 0.00636), CurrencyConvertedToUsd, CurrencyNote mit Kursdatum 2026-09-29 in
  metrics (gemslime-Beleg) ✓ — belegt RestApiServer.java:320-395.

**OK-2 Trades-Konvertierung (Aufgabe 4):**
- 31-Tage-Blöcke inkl. Grenzen: `ende = start.plusDays(30)`; Request `startDate T00:00:00Z
  … endDate T23:59:59Z`; nächster Block ab `ende+1` (PelicanClient.java:294-316) — keine
  Überlappung, keine Sekundenlücke (23:59:59Z→00:00:00Z grenzenlos), TradeId-Dedup via
  `putIfAbsent` ✓. Doppelte TradeIds in den geprüften Vollisten: 0 (Lexo/GOLD Tokyo/
  gemslime/Mtrader Holy). Teilabschlüsse: keine doppelten IDs; ob Plattion vs. Deal
  aggregiert, ist auf CSV-Ebene nicht erkennbar (nicht nachweisbar).
- mql5-Zeile (RestApiServer.mql5Zeile, 446-461): 11 Spalten, BOM ✓, Semikolon ✓,
  Commission=0, Swap leer, Profit=Spalte 10 — Parser-kompatibel (AGENTS-Format 1).
- Nachgerechnet an je 3 echten Trades je Währung (12/12 exakt):
  EUR (GOLD Tokyo 2072334): 19,73→22,40; 0,06→0,07; 0,81→0,92 (×1.1355, Cent-Rundung) ✓
  JPY (gemslime 2059368): 149,0→0,95; −236,0→−1,50; 114,0→0,73 (×0.00636) ✓
  AUD (Mtrader Holy 2005451): 1,6→1,12; 0,31→0,22; 1,06→0,74 (×0.70045) ✓
  USD (Lexo): unverändert 2,27/2,2/11,91 ✓
- Preise/Mengen durch FX NICHT verändert: positionsweiser Abgleich aller 3.296
  Lexo-Zeilen Open-/Close-Preis + Menge: **0 Abweichungen**; Kursrichtung (Kurs
  einheitlich je Provider, nur Geldbeträge) wie dokumentiert (FxRates.java:29-32).
- USC ÷100: Im Katalog KEIN USC-Konto (781 verteilen sich auf USD/EUR/JPY/GBP/AUD;
  735 ohne Währung da ohne Stats) → an echten Daten **nicht nachweisbar**; Code-Pfad
  belegt (FxRates.java:90-91 fix 0,01; usdRundung bei kurs≠1).

**OK-3 Frische & Vollständigkeit der 30 Tradelisten:** mtimes 29.09. 11:54–11:59
(Tradelisten-Batch Z172), letzte Closes bis 29.09. 05:50 (Lexo) — „Tagesfrische
genügt" (Nutzer-Regel) erfüllt. Zeilenzahlen Lexo 3.297 inkl. Header = „3296 Trades"
(UI-Export-Log Z176, 29.09. 12:11) ✓; AIT FX 284 = „283 Trades" (Z180) ✓.

**OK-4 Skalierung Anteil vs. Prozent (Aufgabe 5): KEINE Dopplung.**
- Pelican-Seite: Profitability-Feed liefert ANTEILE (Lexo-Live-Beweis: Feed 25,54 vs.
  Website +2.554 %, PelicanClient.java:218-226); `anteilZuProzentNull` ×100 für
  Renditen; DD `anteilZuProzent` nur wenn −1<v<0; Monatsrenditen = Differenzen von
  Anteilen ×100 (PelicanMonitorApp.berechneMonate, Zeile 1157-1160) → alle Pct-Felder
  sind PROZENT. Average3MonthProfit = avgMonthPct (Prozent) ✓.
- Scanner-Seite: ingest.py:209 gibt `Average3MonthProfit` 1:1 als
  `monthly_growth_pct` durch; pipeline.py:845 → ertrag_monat_pct ohne ×100;
  in signal_stats/ingest/downloader_client kein ×100-Fund. DB-Werte (15.399 / 0.275 /
  531.3 …) = Prozent-Skala, konsistent mit providers.csv ✓.
- Randnotiz (Niedrig): `anteilZuProzentNull` prüft — anders als die DD-Variante —
  nicht, ob der Feedwert schon Prozent ist; liefert die Plattform eines Tages Prozent,
  gäbe es eine 100×-Übertreibung. Heute korrekt (Live-Beweis), aber ohne Absicherung.

**OK-5 InitialDepositVirtual-Kanal (Aufgabe 6):** s. R2-Kette — Transport, strikte
Prüfung, Kennzeichnung `virtuelle_annahme`, kein Cent-Abgleich, nie
`initial_deposit_usd`, Urteile nennen die Annahme. Erscheint nirgends als echte
Einzahlung. Einzige Schwäche ist die Nenner-Größe (R2), nicht die Kennzeichnung.

**OK-6 Lokale KI (Aufgabe 7):** Promptvorlage wirksam in `data/config.json`
(`promptTemplate`, LlmSettings.java:48/81, Fallback DEFAULT_PROMPT mit
Altvorlagen-Erkennung); Modell glm-5.3 (Report), glm-5.3-flash, temperature 0.4,
maxTokens bis 131072, Budget 10 M je Lauf mit Reservierung (GlmClient.java:42-129),
Retries mit Backoff bei 429/1302 + Transportfehlern (MAX_VERSUCHE), Code 1113 klar
benannt; Parallelität `kiParallelitaet` (Default 3 nach Drosselungsnachweis 29.09.,
git 17f595d; max 16; fixed pool PelicanMonitorApp.java:1582-1596). Score-Schema
1–10 (`Risiko-Score: X/10`, Regex ReportService.java:41-44, scoreSchemaVersion=1).
61 Berichte in llm_reports.json, ALLE 30 Scanner-Kandidaten abgedeckt; Stichprobe
Lexo: MD (15.151 B, 104 Zeilen) ↔ PDF (6 Seiten, Meta-Zeile mit Score 8/10, Modell,
Zeitstempel) ↔ Metadaten (risikoScore 8, model glm-5.3, tokens 39.138, datenStand
 2026-09-29) konsistent.
**Erreichbarkeit für den Scanner: /reports liefert hartkodiert `{"count":0,"items":[]}`
(RestApiServer.java:209) und metrics enthalten KEIN Score-Feld → außer dem
Code-gemessenen TradeEqDrawdownPct erreicht KEIN Pelican-KI-Ergebnis den Scanner.**
Der Scanner erzeugt 72 eigene Analysen (24 Signale × risiko_analyse/gesamtbericht/
trade_analyse; glm-5.3-flash bzw. glm-5.3; Stand 30.09. 01:36–01:38) unabhängig —
doppelt gesichert gegen Prompt-Injection aus Pelican-Berichten (Separator-System-
Prompt ReportService.java:98-104).

**OK-7 REST-Konsistenz (Aufgabe 8, dateibasiert; live GETs unmöglich da offline, R6):**
- /providers: total = 781 (Copiers ≥ 1; minSubscribers-Default 1, RestApiServer.java:242-249;
  health meldet count>0 = 781 konsistent). Sortierung/Default „subscribers desc" ✓
  (ingest sortiert selbst absteigend nach Abonnenten — konsistent).
- metrics: für jeden Katalog-Provider lieferbar (Werte aus providers.csv, ggf. null);
  kein „metrics ohne Provider"-Fall.
- trades.csv: 404 mit klarem Grund, wenn keine verifizierte Liste (hasClosed prüft
  csv+meta+SHA+zeilenzahl, SignalStore.java:129-155) — protects gegen halbe Downloads.
- /history: 1 Punkt je Provider (27.09.) — korrekt, aber nutzarm (F3/R5).
- /reports: leer laut Doku ✓ bestätigt (hartkodiert).
- Scanner-Cache quellen_artefakte: 60 Einträge, SHA der Dateien == SHA in DB
  (Lexo/AIT verifiziert), Cache-Hit-Logik prüft Dateiintegrität (ingest.py:150-159) ✓.

## 4) Nicht prüfbar / nicht nachweisbar

1. Individuelle REST-Requests des Ziellaufs (Pfade, Statuscodes, Latenzen um
   00:02:24/00:05) — RestApiServer loggt keine Requests; nur indirekte Belege (s. §0).
2. USC ÷100 an echten Daten — kein USC-Konto im Katalog.
3. Ob Pelican „Total/Wins/Losses" Deals statt Positionen zählt (F2) — Plattform-API
   undokumentiert (PelicanClient.java:28-40).
4. Trade-Blockgrenzfälle der Plattform-API (Filtert sie nach Close- oder Open-Zeit;
   Randhandelstage) — keine Daten mit passendem Grenzfall geprüft.
5. Warum subscriber_history 0 pelik-Zeilen hat, obwohl /history 1 Punkt liefert —
   Sync-Läufe wurden nicht im Detail verfolgt (F3).
6. Live-REST-Verhalten am 30.09. (Monitor jetzt offline, R6) — Katalog-Item-Inhalte
   stattdessen deterministisch aus providers.csv + Code rekonstruiert.
7. Lexo-Trade-Lücke Inception 2023-04-27 → erster Close 2023-07-20 (R8).

## 5) Auswirkungs-Matrix (Kurzfassung)

| Befund | Auswahl | Ampel/Score | Bericht/DB |
|---|---|---|---|
| R1 Monitor-DD ohne Schrankenwirkung | – | Ampel zu günstig möglich (🟢 bei 46,65 % Zweitmessung) | KI nennt es (Kernbefund), Code ignoriert |
| R2 Virtuelle Basis vs. Kleinkonten | – | trading/schock-% zu niedrig (Faktor bis ~20) | Urteil nennt Annahme, Zahlen bleiben verzerrt |
| R3 weeks=0-Datenlage | 747/781 gesperrt (Long-Tail 1–49 Copier) | – | Kandidatenraum = manuelle UI-Auswahl |
| R4 Broker fehlt (USOIL/GER40) | 6/30 ohne Forensik | keine Einstufung (ehrlich) | last_fehler dokumentiert |
| R5 Abonnenten-Historie 1 Tag | – (subscribers aktuell genug) | – | weekChange/monthChange null; Verlauf leer |
| F2 Trades/Wins/Losses | – | – | nur Anzeige |
| F3 subscriber_history leer | – | – | GUI-Verlauf leer |
| R6 Monitor offline (jetzt) | nächster Scan: Quelle pelik fehler-logged | – | – |
| R7 kein Token | – | – | Daten exponiert (nur GET) |
| R8 Tradelisten-Tiefe ohne Inception | abgefedert durch Wochenfilter | bei Filter-Lockerung: flache Forensik | – |
