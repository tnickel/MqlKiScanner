# Befundkatalog Gesamtsystem-Review 16.10.2026 (Handover)

Vollständige Einzelaufstellung aller Befunde zur gezielten Nachprüfung.
Klassifikation: **A** = bestätigt mit Beleg · **B** = begründeter Verdacht · **C** = bewusste/dokumentierte Entscheidung · **D** = nicht prüfbar / Information. P0–P3 = Prioritätsempfehlung.
✅ = vom Hauptreviewer zusätzlich selbst am Code/live nachgeprüft.

Geprüfte Stände (alle Arbeitsbäume sauber):
- SignalKiScanner `80d4692548c9` (main) · MqlDownloader `92d8f9cea10b` · PelicanTrading `dde77d705a67` · roboforex `42b268641ad3` · vantage `1fe395805f29` · zulumonitor `72df0cf49aa4`
- Tests: Scanner pytest 1914 grün/1 rot (reihenfolge-abhängig); Java 105/176/147/49/107 grün.
- Laufzeit-Hinweis: die 5 Monitor-Prozesse starten ~10:50, PelicanTrading läuft damit auf ÄLTEREM Code als `dde77d7`.

---

## 1 MqlDownloader (MDL-1…MDL-14) — Port 8089

**MDL-1 (A, P1) ✅ — Update-Job meldet `done` trotz fehlgeschlagener Downloads und schreibt den Frische-Vermerk.**
Ort: `src/gui/MqlDownloaderGui.java:190-215` (Kaskade endet immer in `job.fertig(...)` + `schreibeKatalogVermerk(...)`, Zeilen 211-213); `src/gui/DownloadManager.java:180-198` (Login-/Download-Exception wird im Thread geschluckt, nur Log+Dialog); `src/downloader/SignalDownloader.java:329-353` (`performLogin` wirft); `src/rest/UpdateJob.java:20,102` (State LOGIN_REQUIRED existiert, wird nie gesetzt — toter State).
Auslöser: Selenium-Login schlägt fehl oder Netz weg. Erwartet: `error`/`login_required`, kein Vermerk. Tatsächlich: Kaskade läuft weiter, Job wird `done`, 3-Tage-Vermerk geschrieben → alle weiteren Updates 72 h gesperrt („erfolgreich“-Fassade, 3 Tage Stillstand).
Fix: Fehlertext je Version aus DownloadManager exponieren; bei Fehler `job.fehler`, Vermerk nur bei Erfolg. Test: Fake-DownloadManager mit Login-Fehler → Status `error`, `config/update_state.json` unverändert.

**MDL-2 (A, P2) — `/trades`-JSON verliert Spalten: doppelte CSV-Headernamen kollabieren im Map-Key.**
Ort: `src/rest/CsvParser.java:61-67` (`row.put(header.get(i), value)` überschreibt gleiche Namen); Header mit doppelten `Time/Volume/Price` in `src/rest/ProviderFiles.java:116-118`. Live bestätigt: 11 Header-Spalten, aber nur 8 Keys je Zeile — Open-Time, Open-Price und 2. Volume gehen verloren.
Wirkung: Haltedauer/Einstiegskurs aus dem JSON-Endpunkt nicht rekonstruierbar; „Time“ wird zu Close-Time. (trades.csv roh ist unbeeinflusst; Scanner nutzt die CSV.)
Fix: Duplikat-Keys eindeutig benennen (`Time (2)`) oder Werte-Array mitliefern. Test: echter MT5-Header + 1 Zeile → 11 Werte.

**MDL-3 (A, P2) — `includeUnchanged=true` bei `/events` wirkungslos (invertierte Logik).**
Ort: `src/rest/RestApiServer.java:697` (`onlyChanges = !"false".equalsIgnoreCase(...)`) + `src/database/DatabaseManager.java:482-484` (`change_amount <> 0` bleibt aktiv für jeden Wert außer Literal "false", auch "true"/1/yes).
Wirkung: Baseline-Zeilen (change=0) kommen nie mit `true`; Doku (`doc/REST_API_Dokumentation.md:319,334`) verspricht sie. Kein Test vorhanden.
Fix: `"true".equalsIgnoreCase(...)`/`Boolean.parseBoolean`. Test: 1 Baseline + 1 Event → mit `includeUnchanged=true` 2 Items.

**MDL-4 (A, P2) — Kein `minSubscribers`-Default im REST `/providers`: ≥1-Abonnenten-Regel wird nicht durchgesetzt.**
Ort: `src/rest/RestApiServer.java:890-894` (Filter nur bei explizitem Parameter); DB kann 0-Abonnenten-Zeilen enthalten: `src/downloader/SignalDownloader.java:642-653` (`checkAndUpdateSubscribers` läuft vor der 0-Prüfung) und `:1409-1442` (Extraktionsfehler → still 0 Abonnenten); `subscribersOnly`-Default false (`src/config/ConfigurationManager.java`).
Wirkung: Katalog kann 0-Abonnenten-/Extraktionsfehler-Signale enthalten, wenn der Client den Parameter nicht setzt. Der SignalKiScanner setzt ihn nicht (vertraut Provider-Defaults) — einzige Quelle ohne ≥1-Schutz.
Fix: serverseitiger Default 1 (Verhaltensänderung) oder verbindliche Doku „Client muss setzen“. Test: 0-Abonnent-Fixture.

**MDL-5 (B, P2) — Katalog ist Plattform-Default-Ordnung, kein Ranking.**
Ort: `mql4Limit`/`mql5Limit` Default 1000/max 5000 (`src/config/ConfigurationManager.java:45-46,133-160`); Sortierung nur per Header-Klick-Simulation `ensureSortedBySubscribers` (`src/downloader/SignalDownloader.java:1444-1479`, Verifikation kann bei 0/0 still versagen → aufsteigende Ordnung möglich); erster 0-Abonnent stoppt die ganze Liste (`:649-653`); Pagination `/pageN`, max. Seitenzahl gescrapt (`:148-255`), kein Plattform-Total.
Wirkung: „Top-N nach Abonnenten“ aus dieser Quelle nicht ableitbar; live max. 69 Abonnenten lokal vs. Plattform-Spitze Tausende → Stichprobe. REST-seitig sortiert/filtert die DB korrekt (Default subscribers desc, `RestApiServer.java:897-928`).
Fix: mql5.com-Sortierparameter nutzen; Default-Ordnung dokumentieren.

**MDL-6 (C) — `target` und `tradelisten` bewusst ohne Wirkung.** Belegt `RestApiServer.java:222-243`, `MqlDownloaderGui.java:114`, Doku `doc/REST_API_Dokumentation.md:448-456`. Kein Handlungsbedarf.

**MDL-7 (C) — 3MPDD<0.5-Qualitätsfilter löscht html/csv/txt → 404.** `src/converter/HtmlConverter.java:167-188` (NaN → Behalten). REST-Doku §5 dokumentiert 404 als Normalfall. Kein Fix.

**MDL-8 (B, P3) — Keine Währungserkennung: Balance ohne Einheit, USC 100-fach überhöht darstellbar.**
Ort: `src/utils/DataExtractor.java:63-68,77-84` (stript alle Nicht-Ziffern; Währung verschwindet); grep USD/USC/currency über `src/` leer.
Einordnung: alle risikorelevanten Metriken sind %-basiert (EquityDrawdown `:169-238`, MaxDDGraphic, MonthProfitProz, 3MPDD `src/calculators/MPDDCalculator.java:190-198`) → währungsfrei; nur `Balance` absolut und nicht vergleichbar, Trades-CSV in Kontowährung.
Fix: Währungsfeld extrahieren + `Currency` ausliefern. Test: „1 234.56 USC“ → Balance + Currency=USC.

**MDL-9 (B, P3) — Balance-Parsing bricht bei „23.456,78“ (Punkt-Gruppierung + Komma-Dezimal).** `DataExtractor.java:64-68` (replace → „23.456.78“ → NumberFormatException). Fix: letztes Vorkommen von ./, als Dezimaltrenner.

**MDL-10 (B, P3) — Kennzahlen-Semantik.** A: `/metrics` liefert exakt `Balance, Subscribers, MaxDDGraphic, EquityDrawdown, Average3MonthProfit, StabilityValue, MonthProfitProz, 3MPDD` + Rohblöcke (`HtmlConverter.java:205-258`, `src/rest/MetricsParser.java`); **keine Wins/Losses/Trades-Felder** (Winrate aus dieser Quelle nicht beziehbar). A: `Average3MonthProfit` = Mittel der 3 Vormonate ohne Laufmonat (`MPDDCalculator.java:108,131-139`), bei Datenknappheit Ø über weniger Monate ohne Kennzeichnung. B: 3MPDD bei DD≤0 nutzt Ersatzwert 1.0 → Dimensionsbruch (`:171-180`).
Fix: `monthsIncluded`-Feld; Doku der Basis.

**MDL-11 (B, P3) — Trade-CSV wird unter ID aus allen Dateinamen-Ziffern gespeichert.**
Ort: `src/downloader/SignalDownloader.java:1156,1193-1226` (`originalId = dateiname.replaceAll("[^0-9]","")`, Parameter `signalProviderId` ungenutzt); `findDownloadedFile` nimmt erste *.csv (`:1303-1307`). Bekannt als Fehlerreview #6; Milderung `FileUtils.correctFileNumbers` + eindeutige REST-Zuordnung.
Fix: übergebene ID ≠ Datei-ID → ablehnen/loggen. Test: „123_extra456.csv“ wird nicht als „123456“ übernommen.

**MDL-12 (B, P3) — Stille Parameter-Fehlinterpretation.** Unbekannter `sort` → still Default (`RestApiServer.java:905-928`); `version=xyz` → **leere Liste** statt 400 (`applyProviderFilters:878-883`); `format≠csv` → still JSON. Fix: 400 bei unparsebaren Werten.

**MDL-13 (D) — Plattformverhalten (mql5.com) nur indirekt belegt:** Seitengröße, `/pageN`-Schema, Exportzeitraum, Brutto/Netto von Profit, offene Positionen im Export. Empfehlung: echte Export-CSV + Listenkopie als Fixture ins Repo.

**MDL-14 — Korrekt bestätigt:** Pfadsicherheit (`ProviderFiles.java:181-204`, Tests vorhanden); Token mit konstantem Zeitvergleich (`RestApiServer.java:1058-1078`); 409/200/202-Zustandsmaschine (`src/rest/UpdateStarter.java:33-43`); Pagination mit Clamp + total; CsvParser RFC-4180/BOM/ISO-8859-1-Fallback; **Delta-Updates Tradelisten: Dateien jünger `downloadDays` (5) werden übersprungen** (`SignalDownloader.java:842-901`) — einzige Quelle mit funktionierender Aktualisierung; mql4/mql5 als Composite-PK `(signal_id, mql_version)` inkl. Migration (`src/database/DatabaseManager.java:46-169`).

---

## 2 RoboMonitor / roboforex (ROB-1…ROB-11) — Port 8091

**ROB-1 (A, P0) — Deal-Listen erfrieren nach Erstladung.** ✅ (live)
Ort: `src/main/java/de/robomonitor/update/UpdateJobRunner.java` `dealsPhase:203` skippt bei `dealsFrischGeladen` → `src/main/java/de/robomonitor/store/DealStore.java:istFrischGeladen:177-181` vergleicht nur lokalen Meta-SHA gegen `geladen.json`-SHA — kein Zeitkriterium, kein Delta-Fenster. Live 16.10.: „Deals: 18 neu, 179 übersprungen“; `lastUpdated` der Top-Signale (SARUJA, PIus) = **2026-09-26**.
Wirkung: alle handelsbasierten Werte (Closing-DD, Monats-PnL im Export) altern unbegrenzt. Fix: `geladenAm`-Zeitstempel je Login ins Ledger + Skip nur ≤ z. B. 72 h. Test: Ledger-Eintrag vom Vortag → Neuladen.

**ROB-2 (B, P2) — Tageslisten: Skip ist reine Existenzprüfung.** `UpdateJobRunner.java:tageslistenPhase:161`, `DataStore.java:hasDaily:226-252`. Nur interne Wirkung (GUI-Simulation/LLM-Payload), REST liest nicht daraus.

**ROB-3 (B, P1) — Closing-DD-Basis enthält Ein-/Auszahlungen → Risiko unterschätzt.**
Ort: `src/main/java/de/robomonitor/report/SignalPayloadBuilder.java:tradeDdAusDeals:50-61` filtert nur Fenster, nicht `Deal.istBalanceOperation()` (`model/Deal.java:39-41`); `model/EquityKurve.java:punkteAusDeals:55-73` nimmt jedes Deal inkl. side=BALANCE; `closingDd:78-84` (Basis = Fenster-Kumuliert/(Yield/100)). Realbeispiel LadyTrader1 (+87k/−51k Flüsse) im Code kommentiert (`RestApiServer.java:455-461`). Kein Test mit Balance-Fall.
Fix: `fenster.removeIf(Deal::istBalanceOperation)`. Test: +1000-Balance-Op ändert DD nicht.

**ROB-4 (B, P2) — 20.000-Deal-Kappung im Export unkennzeichnet.** `api/RoboForexClient.java:MAX_DEALS_PER_SIGNAL=504` (Konstante = Limit 20 000), Kappung geloggt (`:584-587`); metrics ohne `TradesStored/TradesTruncated` (Zulu hat sie). Fix: Felder ergänzen wie Zulu (`RestApiServer.java` dort :413-417).

**ROB-5 (B, P2) — Stiller Katalog-Filter `profit_percent_max=300`.** `RoboForexClient.java:99` im getRating-Body; im REST nirgends ausgewiesen (Website-Parität). Fix: Hinweisfeld im /providers-Response.

**ROB-6 (B, P2) — ≥1-Regel nur im REST, nicht im Update-Scope.** REST `minSubscribers` Default 1 (`RestApiServer.java:298-302`); `UpdateJobRunner`-Schleifen (159/201) laden für alle Top-200 inkl. 0-Abonnenten. Wirkung: API-Last/login_required-Risiko ohne Scanner-Nutzen. Fix: `subscriberCount < 1 → continue`.

**ROB-7 (C) — 3-Tage-Vermerk UTC+Z korrekt** (`UpdateJobRunner.java:244-245,272-278`, Altbestand-tolerant).

**ROB-8 (C) — MT4/MT5-Deal-Semantik korrekt:** MT4 Orders (`parseMt4Deals:598-618`, Mikro-Lots/1e6), MT5 Deals IN/OUT je `position_id` mit Teilschluss-/Pyramiden-Aggregation (`parseMt5Deals:621-642`, `deals/TradeAggregator.java:63-120`), offene Position = IN ohne OUT, OUT-ohne-IN-Rettung mit Begründung.

**ROB-9 (C) — Tageslisten-Bereinigung dokumentiert und behandelt:** `cleanBalanceEquity:339-384` (0/0-Löcher, transiente Ausreißer), `carryForward:392-409`, JSON-null ⇒ kein fantasierter Totalverlust (`dateValueMap:316-328`).

**ROB-10 (C, P3) — URL-Feld live degradiert auf Rating-Übersicht**, weil `source_id` in getRating-Einträgen fehlt (dokumentierter Fallback `RestApiServer.java:350-354`). Fix-Idee: sourceIds aus Stats anreichern.

**ROB-11 (C, P3) — Winrate-Nenner `gewinner+verlierer`** (`deals/DealStatistik.java:79,93`) — Zulu zählt Neutrale dazu (s. ZUL-8): monitors-inkonsistent, im LLM-Payload erklären.

---

## 3 ZuluMonitor / zulumonitor (ZUL-1…ZUL-9) — Port 8093

**ZUL-1 (A, P0) — Tradelisten erfrieren (Pelican-Muster, live bestätigt).** ✅ (live)
Ort: `src/main/java/de/zulumonitor/update/UpdateJobRunner.java:tradelistenPhase:151-155` skippt bei `tradelisteFrischGeladen` → `ZuluMonitorApp.java:391-396` (= lokaler Integritäts-SHA `store/TradeListenStore.java:istFrisch:61-65` + hasTrades); der Ledger trägt bereits `geladenAm` (`TradeListenStore.java:Eintrag:40,87`) — **wird nie ausgewertet**. Live: „0 neu, 199 übersprungen“; lastUpdated **2026-10-07/09**.
Fix: `istFrisch` um Ledger-Alter (≤72 h) ergänzen. Test: `geladenAm` 4 Tage alt + passender SHA → Neuladen.

**ZUL-2 (B, P1) — DD-Basis = ROI-Rückrechnung ohne Kappungs-/Flussschutz.**
Ort: `src/main/java/de/zulumonitor/report/TradePayloadBuilder.java:tradeDdAusTrades:39-47` (Basis = End-Kumuliert/(roiProfit/100)). Update-Job lädt vollständig (`UPDATE_TRADES_PRO_TRADER = Integer.MAX_VALUE`, `ZuluMonitorApp.java:298`), aber der **GUI-Batch mit wählbarer Tiefe** ruft denselben `berechneTradeDd` (`:1355`) und **persistiert** den DD aus gekappter Liste in `data/trade_dd.csv` (`:1907-1920`) → Scanner liest verzerrten Wert (Kappung ⇒ Basis zu klein ⇒ DD % zu groß).
Fix: `berechneTradeDd` nur bei vollständiger Historie oder null. Test: 500-Trade-Teilliste + roiProfit ⇒ keine Persistierung.

**ZUL-3 (B, P1) — Trade-DD meldet 0.0 statt null bei PnL-losen Historien.**
Ort: `tradeDdAusTrades:40-43` prüft nur `roiProfit <= 0`, nicht `ende == 0`; bei Nicht-USD-Konten ohne PnL-Daten (GUI-Kommentar „nur USD-Konten haben PnL“ `ZuluMonitorApp.java:1650-1651`) → Kurve konstant 0 → `EquityDrawdown.java:44` → **0 % DD** statt „nicht berechenbar“. GUI-Gegenstelle prüft `Math.abs(ende)>0` (`:1604`).
Fix: `ende == 0 → null`. Test: netPnl=0-Trades, roi=50 ⇒ null.

**ZUL-4 (C) — Währungskette korrekt:** EZB-Historie je Trade-Schlussdatum, UTC-Datumsbasis, max. 10 Tage Rücklauf, kein Zukunftskurs, 1 Netzversuch/Tag (`rest/FxRates.java:61-94`); ehrliches 404 ohne Kurs (`RestApiServer.tradesCsv:463-471`); USC fix ÷100 (`:64-65`).

**ZUL-5 (C) — Katalog/Abonnenten korrekt:** 20/Page bis count mit LinkedHashMap-Dedup (`TRADERS_PER_PAGE:45`, `:196-216`); Abonnenten = `overallStats.followers`, `liveFollowersNew` bevorzugt (`parseTrader:258-261`); REST `minSubscribers` Default 1 (`:309-312`); Zuwachs ehrlich null statt 0 (`store/SubscriberDb.java:100-107`).

**ZUL-6 (C) — Betriebsfallstricke behandelt:** Host-Fallback mit Schema-Prüfung (`ZuluTradeClient.getTradingJson:431-465`), Pseudo-Positionen gefiltert (`gueltigerTradeDatensatz:350-364`), leere Seite = Fehler (`:302-326`).

**ZUL-7 (C) — Update/Login korrekt:** kein Login nötig; optionaler JWT + OAuth-Refresh nach 401 (`ZuluTradeClient.java:79-135,497-514`); offene Positionen Best-effort mit Cache-Verwurf (`ZuluMonitorApp.java:410-429`).

**ZUL-8 (C, P3) — REST korrekt; Winrate zählt Neutrale in den Nenner** (`TradePayloadBuilder:133`) — Gegenstück ROB-11.

**ZUL-9 (D) — Vollhistorie MAX_VALUE je Trader:** langsam, aber durch ZUL-1 genau einmal teuer.

---

## 4 VantageMonitor / vantage (VAN-1…VAN-11) — Port 8092

**VAN-1 (B, P2) — Katalog-Vereinigung degeneriert für target ≤ 250.**
Ort: `src/main/java/de/vantagemonitor/api/VantageClient.java:142-143` — Phase „2“ (Kopierer-Sortierung) läuft bis `kopiererZiel = min(count, KOPIERER_TIEFE=250)`; bei Default `target=200` (`VantageMonitorApp.java:295`) ist das Ziel in Phase 1 erreicht → die Return-Sortierung (Phase „1“) trägt nichts bei. Live: 199 Provider, reine Kopierer-Auswahl.
Wirkung: junge Hochrendite-Signale mit wenigen Kopierern fehlen im Katalog (Kommentar verspricht „Vereinigung aus beste Rendite und meiste Kopierer“ `:132-141`).
Fix: Aufteilung (z. B. 60/40) sobald count ≤ Tiefe. Test: Stub beider Sortierungen → beide Phasen tragen bei.

**VAN-2 (A) — MQL5-Trades-CSV mit doppelten Time/Volume/Price-Headern ist Absicht** (Open-Leg + Close-Leg des MT5-Positionsformats). `RestApiServer.java:75-76` (MQL5_HEADER), `mql5Zeile:486-500`; live inkl. BOM verifiziert. Consumer mappt spaltenpositionell — kein Handlungsbedarf.

**VAN-3 (B, P3) — 2000-Deckel erkannt und ausgewiesen; zwei Randfälle.**
Ort: Deckel Batch/Update `VantageMonitorApp.java:388,2002`, Einzel 20 000 (`VantageClient.java:50`); Ausweis `TradesStored/TradesTotalAvailable/TradesTruncated` (`RestApiServer.java:416-418`, live `2000/2676/true`) via `TradeStore.totalVerfuegbar:107-119`. Randfälle: (a) `totalCount` fehlt/0 (`VantageClient.java:355`) → `TradesTotalAvailable:null` + `TradesTruncated:false` — „vollständig“ und „unbekannt“ ununterscheidbar; (b) Historie exakt 2000 sieht wie Kappung aus. Fix (a): bei fehlendem total `TradesTruncated:null`.

**VAN-4 (C, P1) — Tradelisten-Freeze: einmal geladen = nie aktualisiert.** ✅ (live: lastUpdated aller Top-Signale = 2026-10-08)
Ort: `src/main/java/de/vantagemonitor/update/UpdateJobRunner.java:193-198` (Skip-Register `geladen.json`, persistent, kein TTL — `TradeListStore.istGeladen:163-165`); `job.ergebnis("tradelistenAktualisiert", 0)` fest verdrahtet (`:247`). Fix: `geladenAm`-Schwelle (Feld existiert) → wieder laden + als aktualisiert zählen. Test: alter Registereintrag → Neuladen, neuer SHA.

**VAN-5 (B, P2) — Kein Delta: jede Ladung ist Voll-Ladung ab neuestem Trade rückwärts.** `VantageClient.downloadTrades:344-368` (Cursor `lastId` ab Seite 1; API ohne Datumskursor). ~82 Requests für 1639 Trades je Refresh — erst nach VAN-4-Fix richtig schmerzhaft. Fix: Abbruch beim ersten bekannten `tradeOrderId`.

**VAN-6 (C→B, P1) — `TradeEqDrawdownPct`-Basis inkonsistent bei gekappter Historie.**
Ort: `report/SignalPayloadBuilder.java:tradeDdAusTrades:43-51` — Basis = kumuliertes PnL der geladenen (≤2000) Trades ÷ Gesamtrendite (ReturnAll). Zähler Fenster, Nenner Gesamt ⇒ bei Kappung verzerrt; `null` bei returnAll ≤ 0; DD nur im geladenen Fenster. Live AlphaPilot: `TradeEqDrawdownPct 59,3 %` vs. Plattform `EquityDrawdown 0,39 %` bei 2000/2676. Nebenfund (nur GUI): „Plattform-DD (gemessen)“ relativ zum PnL-Peak statt Equity (`VantageMonitorApp.java:2376-2386`).
Fix: bei `totalVerfuegbar > trades.size()` null schreiben oder Basis anders ableiten. Test: metrics-Test mit gekapptem Bestand.

**VAN-7 (B, P3) — DD-Semantik der Plattformzahl ungeklärt.** `/metrics EquityDrawdown/MaxDDGraphic` = |overview(All) maxDrawDown| (`VantageClient.java:285`, `RestApiServer.java:388-390`), Einheit Prozent; ob fee-basiert (Kopierer-HWM) ist im Code nicht belegbar und wird unbewertet durchgereicht. Fix: `ddSource`-Feld je DD.

**VAN-8 (B, P2) — Kennzahlen-Deckel 150: Schwanz-Signale mit Null-/30-Tage-Fenster-Metriken.**
Ort: `UpdateJobRunner.java:156-170` + `VantageMonitorApp.java:1843-1860` — overview(All) nur für die ersten 150 von target; live 199 ⇒ 49 ohne. Für sie: `ReturnAllPct=0` (wirkt „renditelos“), `EquityDrawdown` = 30-Tage-Fenster-DD (`parseFilterSignal:227-228` überschreibt), `TradeEqDrawdownPct=null`.
Fix: `metricsWindow: all|30d`-Kennung oder Tail nachziehen. Test: metrics ohne overview → Kennung.

**VAN-9 (B, P2) — Namens-Semantik:** `Average3MonthProfit` ist die **30-Tage**-Fensterrendite (`months=1`, `VantageClient.java:192`), bewusst auf den Scanner-Namen gemappt (`RestApiServer.java:63-64,393-396`); `WinRate` ebenfalls 30-Tage. Fix: `profitWindowDays:30`-Feld. (Pelican mappt denselben Namen auf „Ø aller Monate“, MQL5 auf „Ø 3 Vormonate“ — gleiches Feld, drei Fenster!)

**VAN-10 (A) — REST-Vertrag weitgehend korrekt** (live bestätigt): Endpunkte+Codes 202/400/401/404/405/409/500, einziger Schreib-Endpunkt POST /update, Token-Mechanik, URL=discoverDetail, USC ÷100 beim Import (`normCent:458-460`), historische EZB-Kurse mit 404-ohne-Kurs (`FxRates.java:61-106`).

**VAN-11 (B, P3) — Stille Datenverluste, Restposten:** (a) Fehler 1223 auf früher filter-signal-Seite wird als Listenende gewertet → transienter Serverfehler kürzt Katalog unbemerkt (`VantageClient.java:151-158`); (b) Schema-Drift: `path()`-Defaults liefern 0/leer statt Fehler (z. B. `closeNetPnl` verschwunden → stille 0-PnL-Trades, `parseTrade:401-413`); (c) CSV-Leser übergehen unparseierbare Zeilen still (`TradeStore.loadTrades:155`); (d) Positions-Pagination Safety-Deckel 100 Seiten ohne Feld (`VantageClient.java:385-395`); (e) `parseEpochMs` lokale Zone (`:448-451`) — FX-Schlussdatum kann um einen Tag rutschen.

---

## 5 PelicanTrading — Status der Vormittags-Befunde am geprüften Stand `dde77d7`

(Fixes durch Parallelintegration 16:39; Quelle: eigenes Review + `doc/reviews/2026-10-16_fremdreview_pruefung.md`)

| Befund | Status am Stand |
|---|---|
| F-1 Parallel-Schreib races / feste tmp-Namen | **Gefixt:** per-Ziel-WRITE_LOCKS + createTempFile (`DataStore.java:180+`), mergeClosed per-Provider synchronized, GUI-Batch-Doppelstartschutz |
| F-2 mergeClosed IO-Fehler = leerer Bestand | **Gefixt:** nur fehlendes CSV **und** fehlende Meta = Neustart; Lese-/Hash-/Parsefehler brechen ab (`SignalStore.java:77+,151-154`) |
| F-3 winrate falscher Nenner (`Provider.winrate()` = wins/tradesTotal; Plattform-`Total` ≈ 2× Positionszeilen bei Tokyo 946/464 und HG 30611/15340; website „95 % Trefferquote“ vs. 48,1 %) | **OFFEN/diskutiert:** Parallel-Agent hält Semantik für nicht belastbar belegt (Swagger ohne Deals-/Positionsangabe); Code unverändert, GUI (:822) + Bericht (:1854) zeigen ~halbte Winrate. Schiedsrichter: Website-Abgleich Wins/Losses/Total einer Strategy |
| F-4 Faktor-100 in KI-Kopier-Simulation | **Gefixt:** echte Periodenrendite `(1+R_neu)/(1+R_alt)-1`, korrekte Skalierung (`ReportService.java:238-273`) |
| F-5 Einzelabruf ohne ≥1-Gate | **Entschieden:** Einzelzugriff bleibt (Nachlieferung); aktive GUI-Auswahl erfordert jetzt ≥1 unabhängig vom Anzeigefilter |
| F-6 Enabled=false im Katalog | **Abgelehnt:** keine ungeforderte Ausschlussregel; Restabonnenten legitim |
| F-7 FX-Snapshot-Cache ohne Ablauf + `abgerufen` umetikettiert | **Gefixt:** 24-h-TTL, ehrliche Abrufzeit je Eintrag, sichtbarer Offline-Fallback (`FxRates.java` CACHE_TTL) |
| F-8 DD −1.0-Randfall / Geld-0 vs missing | **Gefixt:** Anteil eindeutig skaliert inkl. −1→−100 %; 0 vs null getrennt |
| F-9 target-Ignore / Bool-Typen / Teilfehler | **Teilfix:** JSON-Typen validiert, Teilfehler strukturiert; 409 bleibt absichtlich 200+bereitsLaufend (kompatibel) |
| F-10 verklebte Zeile / leere TradeIds / stiller Teilkatalog | **Gefixt:** Zeile formatiert, leere IDs einzeln erhalten, Katalogparse bricht bei korruptem Kopf ab |

Neu offen aus dem Nachmittag: **laufende Instanz ist älter als der Code** (Start 10:50, Fixes 15:19/16:39) → Delta-Nachzug + URL-Fix + alle obigen Fixes wirken erst nach Neustart.

---

## 6 SignalKiScanner — Finanzmathematik (FIN-1…FIN-11)

**FIN-1 (A, korrekt) — Winrate:** `stats.py:33-35,96` — Nenner = alle Trades, Break-even neutral (konservativ, als F4 dokumentiert, in Streak/Martingale identisch gespiegelt `martingale.py:46-49`).
**FIN-2 (A, korrekt) — Profitfaktor:** `stats.py:36-37,103` — nur Verluste → 0.0, nur Gewinne → None (kein ∞, kein DivByZero).
**FIN-3 (A, korrekt) — geom. Rendite/CAGR:** `portfolio_statistik.py:280-286` (expm1(ln), exakte Sekundenspanne, 365,2425-Tage-Jahr), TWR-Verkettung bei Flüssen `:260-279`; <3 Monate sperrt RetDD **und** Vorbehalt (`:31-35,301-304`) — annualisierte Kurzhistorien können kein Grün erzeugen.
**FIN-4 (A, korrekt) — TrueRetDD/Calmar:** Zähler/Nenner auf derselben Kapitalbasis (`engine.py:50-53`); Nenner ausschließlich Kursmessung (`pipeline.py:289-299`); DD=0 ⇒ kein ∞ (`pipeline.py:355-361`).
**FIN-5 (B, P3) — Trading-DD sieht Floating nicht:** `forensics/drawdown.py:152-171`. Systemfalle geschlossen (Calmar nur aus Kursmessung; fehlt sie → gelb). Optionaler Hinweistext bei Trading-DD >50 % der Schranke ohne Kursmessung.
**FIN-6 (B, P2) — H1-Schluss-DD ist systematische Untergrenze:** `forensics/equity_rekonstruktion.py:583-1056` — (i) Intrabar-Tiefs fehlen (Schlusskurse), (ii) offene Positionen am Exportende fehlen (`:1016`), (iii) MT5-Bid-Kurse (Sell-Floating optimistisch). GMT-Kalibrierung robust (Plateau-Skip `:574-577`, Wochen-Modell, Nichtmonotonie-Abbruch `:711-714`), Marktpausen aus Abdeckungsnenner (`:408-438`). Wirkung: Calmar-Nenner zu klein ⇒ Calmar zu hoch. Fix: „Untergrenze“-Kennzeichnung im effizienz_befund.
**FIN-7 (C, P2) — Scanner erkennt keine Kontowährung (USC):** `forensics/exposure.py:513-514`, `mql5/signal_stats.py:135-157` (Feld „Currency:“ wird nicht geparsed). %-Kennzahlen skaleninvariant (korrekt), USD-beschriftete Felder 100× überhöht bei Cent-Konten. Fix: Currency parsen + USC-Kennzeichnung.
**FIN-8 (C, P3) — Winrate/PF brutto vs. DD/Martingale netto:** `stats.py:33-37`. Trade +1 Profit/−5 Kommission zählt als „Gewinn“. Entspricht MQL5-Konvention; Doku/Zusatzfeld.
**FIN-9 (C, korrekt) — FX-Kette konservativ:** `fx_rates.py:189-220` (EZB, 10-Tage-Walkback, fehlender Kurs ⇒ None ⇒ Messung gesperrt).
**FIN-10 (C, P3) — virtuelle 10k-Basis in Schranken/Calmar:** durchgängig markiert (`pipeline.py:1225-1240`); bei realem Mikro-Kapital zu günstige DD %.
**FIN-11 (D, korrekt) — Randdetails:** Auszahlungs-Peak-Regel, ULP-Budget, Placeholder-DD 100 % bei Basis ≤ 0 kann nicht still rot färben (`pipeline.py:817-829`).

Nachrechnungen (Sandbox-Import der Produktionsfunktionen): 8 Fälle inkl. TWR-Fluss, DD=0, USC, Auszahlung — alle exakt.

---

## 7 SignalKiScanner — Filter/Ampel (FLT-1…FLT-12)

Soll-Stand aus §8 vollständig am Code verifiziert (26 Wochen `config.py:76`/`pipeline.py:1465`; 0 Abonnenten `:75/:1474`; Top-30 je Quelle `fix_signale.py:124-170`; Fix-ID-Umgehung `pipeline.py:1450-1457` + slot-frei; DD-Schranke nur >30 `pipeline.py:800-802`, `ampel_matrix.py:181`; 5 DD-Kanäle `ampel_matrix.py:162-166`; Calmar ≥3 exakt-grün `pipeline.py:882`; Ertrag ≥0; 3-Monate-Sperre (91,31 Tage) `portfolio_statistik.py:35,301`; Score/SL keine Gates `pipeline.py:835-853`; Forensik v16 `analysis_version.py:30`). Priorität ⛔→Martingale→Kapitalbasis→DD→Fehler→Ertrag→Historie→Calmar; ⛔ kann nie grün werden.

**FLT-1 (B, P2) ✅ = LLM-2** — Altregel „Risiko-Score unter 5“ im Prompt-Baustein REGELN_RETDD (`llm/bausteine.py:83-87`), Engine hat das Score-Gate am 04.10. entfernt (`pipeline.py:844-853`). Bericht konterkariert Ampel.
**FLT-2 (B, P2) ✅ = SYN-1** — `report_basis` ohne `min_calmar_jahr` (`pipeline.py:1206-1209`): nach Schwellenänderung bleiben alte EMPFEHLUNGS-Berichte „aktuell“ (`restore_current_reports:1266-1305`).
**FLT-3 (B, P2) — Teilscan-⚪-Falle:** `fix_signale.py:229-232` — Scope nur 🟢/🟡/Fix; ein transienter Scanfehler (⚪) wirft das Signal dauerhaft aus der automatischen Beobachtung. Fix: ⚪ mit `forensik_stale`/`last_fehler` in den Scope aufnehmen oder Warnung in der Stationsbilanz.
**FLT-4 (B, P2) — Top-N sortiert nach Abonnenten:** `fix_signale.py:161-163` — renditeeffiziente Signale mit wenigen Copierern werden vor jeder Bewertung aussortiert (transparent in `auswahl_begruendung.json`, aber strukturell). Fix-Option: dokumentierter Zweit-Schlüssel.
**FLT-5 (C, P3) — Gleichstand nicht laufstabil:** `fix_signale.py:162` (nur `-abonnenten`; Tie = mql5-Listenposition). Fix: `key=(-abo, id)`.
**FLT-6 (B/C, P2) — Ertrags-Fallback 5.0 statt 0.0:** `ampel_matrix.py:246,465`, `regelwerk.py:102`, `tradeserver_sync.py:101`, `app_ui.py:1017,1020`; Default 0.0 `config.py:82`. Wirkt nur bei partiellen Settings (Tests) — Matrix dann strenger als das Gate. Fix: Fallbacks vereinheitlichen.
**FLT-7 (C, P3) — Grenzwerte DD exakt 30.0 / Wochen exakt 26 untestet** (`test_ampel_matrix.py:45-54` testet nur 30.1/28.0). Fix: Parametrisierung.
**FLT-8 (C) — Fehlende DD-Kanäle werden ignoriert, nicht als 0 gezählt** (`scoring.py:96-102`) — kein unterschätztes Risiko durch None; Beweislast-Lücke aber über `equity_messung_status` ausgewiesen.
**FLT-9 (C, P3) — `abonnenten=None` wird als 0 behandelt und so begründet** (`pipeline.py:1474,1478`), Wochen dagegen als „unbekannt“ — asymmetrisch, ohne Bewertungswirkung.
**FLT-10 (D) — Exporte/REST/„Alle Signale“ verwenden dieselbe Ampel-Ableitung** (`rest_api.py:246-248` → `results_from_db` → `ampel_for`); `minRetddMonthly:1.0` im Sync als bewusst veraltet markiert.
**FLT-11 (D) — Fix-IDs: Risikoprüfung unverändert**; ⛔+Fix gleichzeitig möglich und dokumentiert (`fix_signale.py:108-121`).
**FLT-12 (C, P3) — Wochen float im Filter, int in der UI** (`pipeline.py:1439` vs `app_pages/scan.py:638`).

---

## 8 SignalKiScanner — LLM/Agenten (LLM-1…LLM-13)

**LLM-1 (B, P1) ✅ — Altregel „retdd_monat < 1,0 nicht empfehlen“ im Portfolio-Statistik-Hinweis.** `portfolio_statistik.py:416-420` (Feld `hinweis` Punkt (4)), Einspeisung `pipeline.py:2134-2142`. Widerspricht der Jahres-Calmar-Regel (Nutzer 05.10., `pipeline.py:863-888`) — Modell erhält konträre bindende Anweisungen; `verdict_check` korrigiert nur Aufwertungen.
**LLM-2 (B, P1) ✅ = FLT-1** — „Risiko-Score unter 5“ in `llm/bausteine.py:83-87`; läuft in risiko_analyse, gesamtbericht, portfolio. Realer Konfliktfall HRC Algo (Score 5,8, Engine 🟢).
**LLM-3 (B, P1) ✅ — Monatsbudget wird nirgends durchgesetzt.** Einzige Prüfung `agenten/dirigent.py:70-71` erzeugt `budget_pause` **ohne Consumer**; alle 6 Call-Sites rechnen nur Tagesrest (`betreuer.py:124-141`, `destillation.py:71-93`, `markt.py:201-217`, `melder.py:201-213`, `chef.py:139-152`, `dirigent.py:82-99`); Scheduler ohne Budgetprüfung (`scheduler.py:98-137`); Dirigent meldet bei leerem Monatsbudget fälschlich „Regelbetrieb freigegeben“ (`dirigent.py:205-210`); Hilfe-Text verspricht Begrenzung (`help_settings.py:310-312`). Wirkung: Monatsbudget × Tage Mehrverbrauch möglich. Fix: `budget_rest()`-Helper.
**LLM-4 (C, P2) — Scan-/Portfolio-/Tiefen-Token außerhalb der Agenten-Budgetbuchung:** `pipeline.py:1329-1334`, `agenten/scan_launcher.py:359-381` schreiben keine Journal-Tokenzeilen (`journal.py:390-408`); tiefen_batch ohne Lauf-Lock (`tiefen_batch.py:43-108`) ⇒ zwei 10-Mio-Budgettöpfe parallel möglich; prozessübergreifender Tagesbudget-Race (`llm/client.py:70-76` nur In-Process gefixt).
**LLM-5 (C, P2) ✅ — Dauerbetreuung nur MQL5:** `agenten/betreuer.py:65-77` (`mql5_kandidaten`), Skip nur im Daemon-Log (`tageslauf:351-358`); Quellen-Signale erhalten keine Delta-/STILBRUCH-Betreuung (dokumentierte Lücke B4), reguläre Scans/Watcher decken sie weiter ab.
**LLM-6 (D, P3) — length-Retry: alle Versuche werden bezahlt/gezählt** (`llm/client.py:209-245`), aber verworfene Antworttexte und `verworfene_retry_tokens` werden nicht persistiert.
**LLM-7 (C, P2) — REST-Ampel-Semantik** (gespeicherte Forensik + aktuelle Einstellungen, im Docstring dokumentiert `rest_api.py:14-19`): v15 wird korrekt als stale markiert (`pipeline.py:516-527`); Payload trägt die Semantik aber nicht nach außen; `kurzfassung` (alter LLM-Text) kann zur neu gerechneten Ampel passen. Fix: `ampelBasis`-Feld.
**LLM-8 (B, P2) = SYN-1.**
**LLM-9 (C, P2) — Agenten-Prompts ohne Fremdtext-Schutzblock:** `{regeln_fremdtext}` nur in den 5 Workflow-Vorlagen (`bausteine.py:12-17`), keine der 6 Agenten-Vorlagen; Anbieter-kontrollierte Namen/Texte erreichen das Modell ungefiltert. Wirksamer Gegenschutz: Betreuer-/Dirigent-Antworten whitelist-/regex-gefiltert, Ampel nie vom Modell — Injection kann nur Textqualität fälschen.
**LLM-10 (D, P3) — Deterministische/Modell-Trennung intakt** (`verdict_check.py:47-97` sanitiziert ⛔/🔴/🟡); Nische: `extract_llm_urteil`-Fallback nimmt letztes Auftreten (`:21-44`).
**LLM-11 (D, Positiv) — Fehlerbehandlung robust** (leere Antwort, length-Retry mit Budgetprüfung, 429/5xx-Backoff, 1113-Guthaben); Restmuster `llm_runner.py:156,206` (Laufsummen-Fallback in Audit-Spalte) durch `or 0` ersetzen.
**LLM-12 (D) — Dirigent sieht Monatsbudget im Lagebericht, kann aber keine Budgetaktion äußern** (Whitelist) — mit LLM-3 mitfixen.
**LLM-13 (D, P3) — Altregel-Kommentare/Tests** (`pipeline.py:964-965`, `portfolio_statistik.py:198-199`, `tests/test_retdd_produzent_und_dedup.py:9-10`) — Quelle für künftiges Wiedereinkopieren.

---

## 9 SignalKiScanner — REST/Persistenz (SYN-1…SYN-12)

**SYN-1 (B, P2) ✅ — Berichtsbasis kennt das Calmar-Gate nicht:** `pipeline.py:1207-1208` (criteria nur `schranke_eq_dd_pct`, `min_ertrag_pct_monat`) vs. Gate `pipeline.py:871` — nach `min_calmar_jahr`-Änderung bleiben alte KI-Berichte ohne „veraltet“-Hinweis, laufen in PDFs/Sync weiter. Fix: Key ins Dict.
**SYN-2 (B, P2) — `equity_studien` ohne Forensik-Version:** `db.py:882-912` (keine Versionsspalte), `studien_batch.py:433-447`, `pipeline.py:702-788` — Studien überleben FORENSICS_VERSION-Bumps bei gleichem Trade-SHA; analysis_version-Mechanismus wirkt hier nicht.
**SYN-3 (B, P2) ✅ — mql4+mql5 desselben Signals: Last-wins:** Schema `db.py:38-60` (PK signal_id), Kandidaten-Dedupe hält beide Versionen (`ingest.py:119-132`, Key `(id, platform)`), `trade_files`/`forensik` mit `ON CONFLICT(signal_id) DO UPDATE` (`db.py:370-374,386-390`) — zweite Version überschreibt erste (Kopfdaten, Snapshot, Forensik; katalog_signale verliert eine Version). Fix: je id auf eine Version dedupieren oder auf (signal_id, version) migrieren.
**SYN-4 (B, P2) ✅ — „Schreibgeschütztes“ REST schreibt PDFs:** `rest_api.py:246-248` → `pipeline.results_from_db()` mit Default `materialize_pdfs=True` (`pipeline.py:479-481,658-664`) — jeder /signals-Abruf kann PDFs+Cache rendern. Fix: `materialize_pdfs=False`.
**SYN-5 (C, P3) — Job-Adoption:** `/update/status` wird ohne jobId-Abgleich gepollt (`client_updates.py:222,245-304`; `downloader_client.py:255-259`) — ein parallel gestarteter fremder Job kann als Ergebnis dieses Laufs verbucht werden (Server ist Single-Job; Adoption dokumentiert). Fix: jobId-Abgleich falls Server ihn liefert.
**SYN-6 (C, P3) — Sync-Historie: `started_at == finished_at`, Crash verliert Lauf:** `db.py:573-587` + `tradeserver_sync.py:326-331` (Insert erst im finally). Fix: Startzeile + Update.
**SYN-7 (C, P3) — `save_settings` nicht atomar + stiller Default-Fallback:** `config.py:191-193` (write_text ohne tmp), `:181-188` (Fehler ⇒ still Defaults — inkl. Regelwerten). Fix: tmp+os.replace.
**SYN-8 (C, P3) — 404 vor Token-Prüfung:** `rest_api.py:181-190` (Pfad-Enumeration ohne Auth; nur 2 Pfade, 127.0.0.1). Fix: Token zuerst.
**SYN-9 (C, P3) — Tradeserver-Sync ohne Lock:** `app_pages/ergebnisse.py:149-166`, `tradeserver_sync.py:250` — zwei Sessions können parallel synchen. Fix: lauf_lock nehmen.
**SYN-10 (C, P3) — Admin-Anzeige auf 500 Zeilen begrenzt:** `db.py:1034-1040` — stillen Quellen fällt der neueste Stand aus dem Fenster. Fix: GROUP-BY-SQL.
**SYN-11 (D, P3) — REST default aktiv, Token optional:** `rest_api.py:44,254` — ohne Token jeder lokale Prozess lesend. Bewusste Entscheidung (127.0.0.1).
**SYN-12 (D, P3) — „NEU“-Fallback markiert Altsitzungen komplett als frisch:** `app_pages/ergebnisse.py:48-54`.

Korrekt bestätigt: Token byteweise (`hmac.compare_digest`, `rest_api.py:213-220`), Bind 127.0.0.1, SHA-Konsistenz (Rohbytes inkl. BOM, `ingest.py:144-194`), content-addressed Snapshots mit fsync+replace (`db.py:334-364`), WAL+busy_timeout, prozessübergreifendes Lauf-Lock mit Liveness (`agenten/lock.py`), Secrets-Hygiene (nie in DB/Logs/Berichten), Fixtures committet — frischer Checkout lauffähig.

---

## 10 Querschnitt systemisch

**S1 Freeze (P0):** VAN-4 + ZUL-1 + ROB-1 (+ Pelican bis Neustart) + MDL-1 als „Erfolgsfassade“. Live-Alter der Tradelisten: Robo 26.09., Zulu 07.10., Vantage 08.10., Pelican-Bestand 29.09. — nur MqlDownloader frisch.
**S2 Monitor-DD-Basen (P1):** ROB-3, ZUL-2, ZUL-3, VAN-6, VAN-3a.
**S3 LLM/Cache (P1/P2):** LLM-1/2, LLM-3, LLM-4, SYN-1/2, LLM-7.
**S4 Auswahl vor Bewertung (P2):** FLT-4, VAN-1, MDL-5, MDL-4, ROB-6, FLT-3, ROB-5.
**S5 Identität (P2/P3):** SYN-3, MDL-11, Pelican F-3.
**S6 DD-Untergrenze (P2):** FIN-6.
**S7 Testverschmutzung (P2):** 2 Läufe, 3 verschiedene je einzeln grüne Fehler (`test_review_t12_llm_forensik` 2×, `test_parser_export_artefakte` 1× — `parser.py:110` WindowsPath.lower).
