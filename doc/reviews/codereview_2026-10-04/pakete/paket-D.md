# Paket D — PelicanTrading (Provider-Monitor, REST :8090) · Codereview 04.10.2026

## 0) Manifest und Abdeckung

- Projekt: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\PelicanTrading` (JavaFX/Maven, Java 17+, Jackson, SQLite, com.sun.net.HttpServer).
- Git: HEAD `9ea8b39` („fix: Nach ‚Signale laden' steht nur noch die gefilterte Statuszeile …", v1.4.3). Working tree: nur `README.md` modifiziert (kein Code dirty).
- Relevante Commits (bereits behoben, nicht neu gemeldet): `31442f8` (B18 /reports echt), `cd9612f` (B5/B6 weeks-null, metrics.Broker), `c4b3038` (12 Fremd-Review-Fixes), `1dc8490`/`ce8a0eb`/`760d444`/`a7252ea` (Zwei-Phasen-Live-Sync), `9af1792` (Katalog nur mit Abonnenten), `7d586c2`/`27eeed2` (Trade-EQ-DD).
- Geprüfte Dateien (alle vollständig gelesen): `report/ReportService.java`, `model/EquityKurve.java`, `model/EquityDrawdown.java`, `model/Signal.java`, `model/Provider.java`, `rest/RestApiServer.java`, `rest/FxRates.java`, `rest/RestApiConfig.java`, `store/{DataStore,SignalStore,LiveDataStore,StrategieDb,CopierDb,LlmReportStore,UiPrefs}.java`, `api/PelicanClient.java`, `gui/LiveTradingSyncDialog.java`, `gui/LiveTradingWindow.java` (Kernbereiche), `PelicanMonitorApp.java` (Kernbereiche: Laden, Tradelisten, KI, Persistenz, starteTask), `llm/GlmClient.java`, `config/{LlmSettings,Ampel}.java`, alle 8 Testdateien.
- Daten (read-only): `data/trade_dd.csv` (39 Werte, mtime 30.09. 22:57), `data/providers.csv` (2244 Provider, mtime 01.10. 15:01), `data/signals/closed+open/` (4446 Dateien, mtimes 27.–29.09.), `data/fx_rates.json` (EUR/JPY/AUD vom 29.09., abgerufen 30.09. 00:05), `data/reports/` (174 Dateien), `data/llm_reports.json` (61 Einträge), `data/pelicanmonitor.log` (452 Zeilen, Zeitraum 27.09. 15:21 – 04.10. 12:50).
- Eigene Nachrechnungen (nur lesend, Python über die CSVs): DD-Algorithmus für #2007510, #2000028, #2000892 exakt nachvollzogen; Trade-Summen gegen providers.csv-RealisedPnl gegenübergestellt.
- Abdeckung: D1–D8 vollständig bearbeitet; dynamische Ausführung, Tests, Netz und LLM bewusst nicht (Auftragslage).

## 1) Befunde

### D1 — Drawdown-Semantik von TradeEqDrawdownPct (Kernbefunde)

**D1a [P0 · BESTÄTIGT] — TradeEqDrawdownPct ist KEIN floating-inklusiver Equity-DD über die Historie, sondern Close-Kurve plus EIN aktueller Floating-Endpunkt.**

Exakter Algorithmus (verfolgt über alle Schichten):

1. `ReportService.tradeDdAusTrades` (ReportService.java:57-70):
   ```java
   List<EquityKurve.Punkt> eqPunkte = EquityKurve.punkte(trades, offene);
   double basis = eqPunkte.get(eqPunkte.size() - 1).kumuliert() / (p.getReturnInceptionPct() / 100.0);
   for (var pkt : eqPunkte) werte.add(basis + pkt.kumuliert());
   return EquityDrawdown.maxDrawdown(werte).ddPct();
   ```
2. `EquityKurve.punkte` (EquityKurve.java:57-63): Kurve = Startpunkt 0, dann **je geschlossenem Trade** (aufsteigend Close-Zeit) die kumulierte Summe `realisedProfit`. **(a) Kurve nur aus geschlossenen PnLs: JA.**
3. **(b) Aktueller Floating-Endpunkt: JA, aber genau EINER** (EquityKurve.java:73-83): nur wenn offene Positionen existieren, wird EIN Endpunkt angehängt = Summe der unrealisierten PnL ALLER offenen zum spätesten `lastUpdated`. **(c) HISTORISCHER Floating-Verlauf zwischen Trade-Closings: NEIN, nirgends abgebildet** — zwischen zwei Close-Zeitpunkten existiert kein Kurvenpunkt.
4. `EquityDrawdown.maxDrawdown` (EquityDrawdown.java:39-55): klassischer Peak→Tief-Rückfall, `ddPct = (peak − wert)/peak · 100`, peak ≤ 0 → 0 %.
5. Persistenz: `PelicanMonitorApp.berechneTradeDd/speichereTradeDd` (PelicanMonitorApp.java:2289-2336) → `data/trade_dd.csv` (Kopf `Id;MaxEqDdPct`, atomar geschrieben) → REST `metrics.TradeEqDrawdownPct` (RestApiServer.java:377, gelesen je Request in `tradeDd()` 544-559).

Zahlenbeispiel (eigene Nachrechnung aus data/, #2007510 „Yu Trading Club", EUR): 2 716 gelieferte Closings, Summe +4 874,89 EUR, Plattform-Rendite 207,39 % → basis 2 350,59 (ohne Floating) bzw. 1 347,65 (mit Floating-Endpunkt −2 079,99 EUR). Close-only-DD = **17,09 %**, mit dem EINEN heutigen Floating-Endpunkt = **33,43 %** (trade_dd.csv: 33,367; Differenz 0,06 pp = zwischenzeitlich neuere Rendite-Basis). Der Wert lebt also massiv vom **heutigen** Floating.

Auswirkung: Der Scanner-Hub nimmt `TradeEqDrawdownPct` als `monitor_trade_eq_dd_pct` — laut Scanner-Regelwerk (B1, 30.09.) als „floating-inclusive Zweitmessung" — als fünftes Maximum in die 30-%-Drawdown-Schranke. Tatsächlich misst der Wert floating nur am **Gegenwartsendpunkt**. Ein Signal, dessen Floating-Tief in der VERGANGENHEIT lag (Position tief unten, später erholt oder mit kleinem Verlust geschlossen), wird NUR über seine Closings gemessen → der DD wird unterschätzt → die harte Risikoschranke ist zu milde → für Investoren gefälscht-entschärfendes Signal. Beleg der Größenordnung: Lexo #2000028 meldet Plattform-MaxDD −0,78 %, TradeEqDrawdownPct 6,19 % — keiner von beiden enthält irgendein historisches Floating.

Fix-Vorschlag: (1) Feld umbenennen bzw. Zusatzfeld `TradeEqDrawdownFloatingScope: "endpoint_only"` in metrics; der Scanner entscheidet dann, ob der Wert als Zweitmessung in die Schranke darf. (2) Mittelfristig Tages-Approximation des Floating aus `stats.Profitability.Inception.History` (Realised vs. Unrealised-Kurve je Tag) — Pelican liefert Realised+Unrealised-Rendite je Tag; daraus wäre ein historisch floating-inklusiver DD auf Tagesraster ohne Kurse rekonstruierbar.

**D1b [P0 · BESTÄTIGT] — Kapitalbasis ist aus der Plattform-Inception-Rendite rückgerechnet; die Identität „gelieferte Trade-Summe = Plattform-Rendite" ist in den Realdaten widerlegt.**

(d) Kapitalbasis: `basis = endKum / (returnInceptionPct/100)` (ReportService.java:65-68) — d. h. es wird angenommen, die Equity am Kurvenende sei exakt `basis · (1 + r)` mit r = Plattform-RealisedReturn. Zwei Verzerrungen, live belegt:

1. **Zähler/Nenner-Mix:** Der LETZTE Kurvenpunkt enthält den aktuellen Floating-PnL (`punkte()` hängt den inklOffen-Punkt an, `eqPunkte.get(size()-1)` nimmt genau den), der Nenner `returnInceptionPct` ist laut PelicanClient.java:220-221 aber `Profitability.Inception.RealisedReturn` (NUR realisiert)._basis systematisch zu klein, wenn Floating negativ._
2. **Trade-Summe ≠ Plattform-RealisedPnl**, beide Richtungen (providers.csv Spalte RealisedPnl vs. eigene Summation der closed-CSV):
   - #2007510: Trades-Summe +4 874,89 EUR vs. Plattform 3 641,86 EUR → Δ **+25 %**
   - #2000892: 5 773,40 vs. 8 228,29 USD → Δ **−30 %**
   - #2000028: 13 439,64 vs. 11 840,04 USD → Δ **+13,5 %**
   Die Basis steht damit nachweislich ±13–30 % daneben; DD% verzerrt entsprechend (Basis zu groß → DD zu klein und umgekehrt). Zusätzlich geliefert: nur ~50 % von TradesTotal (2 716/5 441; 3 304/6 677; 1 927/3 893 — plausibel Entry/Exit-Zählung der Plattform, unerklärt).
3. **(e) Sonderfälle:** `returnInceptionPct == null || <= 0` → null (ehrlich, ReportService.java:58-60); unvollständige Historie (Fehler beim Blockladen wirft, alte CSV bleibt — PelicanClient.java:294-316 ohne Teil-Toleranz; Batch überspringt Provider, PelicanMonitorApp.java:1396-1412) → Wert bleibt einfach alt (siehe D1c); Einzahlungen des Providers sind in keiner Schicht sichtbar (auch der KI-Prompt bekennt das, LlmSettings.java:244-245) → Prozent-DD eines durch Einzahlungen geglätteten Kontos ist zu klein (GRENZE der Datenlage, aber Semantik muss dem Scanner bekannt sein).

Fix: Basis über `Balance` und `RealisedPnl` der Plattform konsistent herleiten (`basis ≈ (Balance − RealisedPnl)` statt Rendite-Rückrechnung) oder wenigstens Trade-Summe vs. RealisedPnl als Konsistenzprüfung ausweisen (`basisKonsistenzPct`-Feld in metrics) und bei Abweichung >5 % den DD auf null/„unbelastbar" setzen.

**D1c [P1 · BESTÄTIGT] — trade_dd.csv ist ein Stale-Cache ohne Zeitstempel, der alte Werte lautlos überdauert.**

`berechneTradeDd` kehrt bei `dd == null` einfach zurück („if (dd == null) return", PelicanMonitorApp.java:2290-2291): Wird eine Tradeliste neu geladen und ist danach kein DD berechenbar (Rendite-Basis null/≤0, Trades leer), bleibt der ALTE Wert im `tradeDdCache` und in `trade_dd.csv` stehen — obwohl er zu einer VORHERIGEN Kurve gehörte. Die Datei hat nur `Id;MaxEqDdPct`, kein Berechnungsdatum (2320-2323); `REST tradeDd()` liefert ihn je Request frisch aus (RestApiServer.java:544-559). Real belegt: trade_dd.csv = 30.09. 22:57, providers.csv (Rendite-Basis!) = 01.10. 15:01 — „Signale laden" aktualisiert Rendite, ohne DD neu zu berechnen. Der Scanner erhält einen DD, der zu einer älteren Rendite-Basis und älteren Trades gehört, ohne es erkennen zu können. Fix: Spalte `BerechnetAm` + Löschen des Cache-Eintrags, wenn ein Neuladen null ergibt; alternativ Trade-DD beim „Signale laden" aus den gecachten Listen nachberechnen.

### D2 — Zwei-Phasen-Sync (Live-Trading)

**D2a [P2 · BESTÄTIGT] — Phase 2 lädt nur 92 Tage Closed-Historie; ältere eigene Trades fehlen dauerhaft, abbestellte Copy-Signale verwaisen still.**

Phase 1 = EIN Request `/api/copiers/{id}/signals/open`; Phase 2 = `/signals/closed` in 30-Tage-Blöcken, hart 92 Tage zurück (`CLOSED_RUECKBLICK_TAGE = 92`, LiveTradingSyncDialog.java:44-46, 102-112). UUID-Discovery ausschließlich aus offenen + ≤92 Tage alten geschlossenen Kopien (118-131). Konsequenzen: (1) `LiveDataStore.kennzahlen()`/`geschlosseneTrades()` (LiveDataStore.java:175-203, 258-288) zählen nur was im 92-Tage-Fenster lag — „realisiert gesamt" je Copy-Signal ist eine Untergrenze, nicht die Wahrheit; (2) ein abgeaveragestes Signal taucht in keiner Phase mehr auf → alter DB-Stand bleibt ohne jede Markierung stehen (Kurve friert ein, ohne als „nicht mehr aktiv" erkennbar zu sein). Kein klassisches Paging-Fehler-Resume nötig, weil Blöcke werfen statt still leeren (PelicanClient.java:342-360) — Teilfehler in Phase 2 bricht den GANZEN Sync ab, bevor irgendetwas geschrieben wird (try/catch um beide Phasen, Speichern erst danach, LiveTradingSyncDialog.java:90-178) → **kein Teilzustand, korrekt**. Log-Belege: 01.10. 18:17–19:23 vier Abbrüche (401-Session bzw. „client is null" vor Fix ce8a0eb); 02.10. 12:19 erfolgreich „Phase 1: 64 offene … Phase 2: 22 geschlossene … fertig: 86 Copy-Signale, 86 Trades".

Frischemarke: `uiPrefs.vermerkeLadung()` läuft NUR im Erfolgs-Callback von „Signale laden" (PelicanMonitorApp.java:1184; `starteTask` setzt beiErfolg nur in `setOnSucceeded`, 2217-2222) — ein Live-Sync oder Teilfehler setzt die 24-h-Marke NICHT. **Teilsync stellt sich also nicht fälschlich „vollständig frisch" — Verdacht widerlegt.** Grenze: `letzteLadung()`-Fallback auf providers.csv-mtime (UiPrefs.java:54-66) — die mtime wandert auch durch batchStats/Tradelisten-`speichereCache`, die Erinnerung könnte dadurch zu früh verstummen (nur relevant ohne Pref-Stempel).

**D2b [P3 · GRENZE] — copy_trades hat PRIMARY KEY nur (trade_id)** (LiveDataStore.java:64, 117-119): TradeIds zweier Copy-Signale müssten Plattform-global eindeutig sein (plausibel); ein Konflikt würde den Trade still dem Erst-Signal zuordnen (uuid wird im Update-Zweig nicht überschrieben). Keine Auswirkung auf REST/Scanner (live_trading.db geht nicht an den Hub), nur auf die eigene Live-Anzeige.

### D3 — Tradeabbildung

**D3a [P2 · BESTÄTIGT] — Zeitstempel: UTC-„Z" wird abgestreift und als lokale Wanduhrzeit weiterverwendet, während die Blockabfragen in UTC-Grenzen laufen.**

`parseTs` entfernt ein trailing „Z" ohne Zeitzonenkonvertierung (PelicanClient.java:408-417); die Chunk-Requests fragen `startDate=…T00:00:00Z&endDate=…T23:59:59Z` (303-304, 349-350). Persistenz (SignalStore.java:65-66) und mql5-Export (RestApiServer.java:496-498, MQL5_TIME) geben naive Wanduhrzeiten ohne Zonenkennung aus. Auswirkung: trades.csv-Zeiten sind „UTC-Uhrzeit als lokale Zeit gelesen" (feste Verschiebung, DST-saubere Plattform vorausgesetzt linear). Der Scanner gleicht per Preisabgleich selbst GMT aus (Auto-GMT), eine systematische Doppelkorrektur entsteht im Monitor-Code nicht — ABER die Zeitzonen-Semantik ist an der Schnittstelle nirgends deklariert; ein Scanner, das die Zeiten als Broker-Serverzeit interpretiert, trifft zufällig richtig. Fix: eine Zeile im trades.csv-Header-Kommentar bzw. metrics-Feld `TimestampTimezone: "UTC (naive)"`.

**D3b [P3 · BESTÄTIGT] — SignalStore.loadClosed überspringt unlesbare Zeilen still** (SignalStore.java:124 `catch (RuntimeException skipped) { }`; außerdem wird Profit still null, wenn `c.length <= 9`, Zeile 122). Kaputte Trade-Zeilen verschwinden aus trades.csv ohne Zähler/Log — für ein forensisches Exportformat sollten sie gezählt und im Log/ggf. metrics gemeldet werden (Scanner-seitig gilt dank beweisbasiertem Dedup-Paradigma: stiller Verlust ist schlimmer als sichtbarer).

Entlastend dokumentiert (kein Befund): je Zeile EINE geschlossene Position (Open+Close, Preise, Menge) → mql5-Positions-Format (RestApiServer.java:470-487); Commission=0/Swap leer ehrlich; offene Positionen NICHT in trades.csv (nur closed — Scanner kennt die Konvention); RealisedProfit brutto, fee separat im Katalog (Prompt erklärt es).

### D4 — Währungen

**D4a [BESTÄTIGT · GRENZE] — Snapshot-Umrechnung ist realisiert und offengelegt, aber der Kurs wird NIE erneuert.** `FxRates.rateFuer` liefert den Cache sofort zurück (FxRates.java:92-93) — data/fx_rates.json enthält EUR 1,1355 / JPY / AUD vom 29.09., abgerufen 30.09. 00:05, und bleibt bis zur manuellen Löschung für ALLE historischen Geldwerte stehen (heute 5+ Tage alt). Bewusst so dokumentiert (Klassen-Doku FxRates.java:29-33: einheitlicher Kurs erhält alle Verhältnisse) und je Provider in `CurrencyNote` mit Kursdatum offengelegt (RestApiServer.java:350-358, 403-409). Preis/Lot/Prozent werden NICHT mitgeskaliert — nur Geldbeträge: `mql5Zeile` skaliert ausschließlich Profit (472-486, `usdRundung` 491-494 cent-gerundet), Preise/Menge unverändert; metrics Balance/Equity/Copiers* via `usd()` (368-390). DD-Prozente invariant: TradeEqDrawdownPct wird in Kontowährung aus Kontowährungs-Kurve gerechnet (Basis und PnL gleiche Währung) — Skalierung hebt sich raus. USC fix ÷100 (FxRates.java:90-91). Offline ohne je gecachten Kurs → trades.csv 404 mit Grund (RestApiServer.java:449-456) — **Auftrag D4 im Ergebnis bestätigt**. P3-Anmerkung: eine TTL (z. B. Kurs älter als 7 Tage → neu holen, sonst Cache) wäre eine Zeile; heute veraltet der Kurs lautlos (Datum ja im Note-Feld).

### D5 — Strategiemodul (strategien.db)

**D5a [BESTÄTIGT — entlastend] — Keine einzige Handels-/Kopier-Aktion im Code.** Vollständiger Call-Graph des Moduls: `StrategieDb` (strategien.db, readonly): `strategien()` SELECT (54-66), `kurve(id)` SELECT auf View `strategie_kurve` (69-81), `summenKurve()` = reine Java-Aggregation über `kurve()`-Ergebnisse (88-120), `existiert()` (49-51). Aufrufer nur `LiveTradingWindow.bauteStrategieAnsicht`-Umgebung (LiveTradingWindow.java:224-272) für Karten/Charts. `PelicanClient` besitzt als EINZIGE HTTP-Methode `get()` (96-134) — keine POST/PUT/DELETE-Spur im ganzen Projekt. Damit entfallen Autorisierungs-/Demo-Live-/Doppelklick-Fragen für Handelsaktionen gegenstandslos. Randnotizen: SQL-Konkatenation `"... WHERE strategy_id = " + strategyId` (StrategieDb.java:72) ist typsicher (long) — keine Injektion; COPIER_ID 1378061 hartkodiert (LiveTradingSyncDialog.java:43) nur lesend genutzt; `LiveTradingWindow`-Kennzahlen je Strategie aus `LiveDataStore.kennzahlenJeProvider()` (LiveDataStore.java:321-344, reine SELECT-Summen) — Join über provider_id; abbestellte Strategien tauchen weiter in der Summenkurve auf (D2a-Spiegelung, P2 siehe dort).

### D6 — Store-Snapshot-Kohärenz

**D6a [P1 · BESTÄTIGT] — Die Artefakte eines „Snapshots" sind zeitlich auseinandergerissen; „Signale laden" erzeugt den Anschein von Frische, ohne Tradelisten/DD anzufassen.**

`ladeProvider` (PelicanMonitorApp.java:1136-1192) lädt Discover+Details+Stats neu → `speichereCache` (providers.csv) + `copierDb.snapshot` + `uiPrefs.vermerkeLadung` (24-h-Marke). Tradelisten (`signals/closed+open`), `trade_dd.csv`, Abonnenten-DB-SNAPSHOT je Tag und Reste bleiben ALT. Real: providers.csv 01.10. 15:01, closed-CSVs 27.–29.09., trade_dd.csv 30.09. — der Scanner bekäme heute Katalog-Stats vom 01.10. mit trades.csv vom 29.09. (7 Tage alt; `lastUpdated` im Katalog = closed-mtime, RestApiServer.java:670-681, immerhin ehrlich). Der Monitor meldet nach „Signale laden" Erfolg + grünt die 24-h-Erinnerung, obwohl die forensisch relevanten Artefakte unverändert alt sind — ein Nutzer schließt daraus „alles frisch". Cache-First ohne Remote-Hash-Prüfung: `SignalStore.hasClosed` verifiziert nur LOKALEN SHA/Count (SignalStore.java:130-155) — „unverändert" heißt dort unverändert GEGENÜBER DER LETZTEN SPEICHERUNG, nicht gegenüber der Plattform (echte Remote-Freshness wird nie geprüft; das ist Design der manuellen Last, aber die UI-Sprache „Tradeliste geladen" + 24-h-Marke vermischt die Ebenen). Fix: `lastUpdated` je Provider zusätzlich ins Katalog-Item für trades (schon da) UND die Signale-laden-Erfolgsmeldung um „Tradelisten unverändert (Stand …)" ergänzen; trade_dd.csv um Berechnet-Datum (siehe D1c).

### D7 — KI-Berichte

**D7a [BESTÄTIGT — entlastend] — /reports ist NICHT mehr leer; die Angabe in SignalKiScanner-AGENTS.md („/reports liefert (noch) eine leere Liste") ist ÜBERHOLT.** `reportsJson` listet echte Dateien im MqlDownloader-Format (RestApiServer.java:619-645), `reportDownload` liefert Bytes (650-660); Namenskonvention `bericht_{id}_{uuid}.pdf|.md` mit Prefix-Schutz gegen Mehrdeutigkeit (596-614) und Pfad-Traversal-Schutz (nur exakte Namen aus gefilterter Liste). data/reports enthält 174 Dateien; llm_reports.json 61 Einträge; Tests `reportsLiefernBerichtdateienJeProvider` + `reportDownloadLiefertBytesUndWehrtFremdeNamenAb` grün laut Suite. Das alte Log („PDF geöffnet: bericht_1.pdf", 02.10./04.10.) stammt aus einer Vor-B18-Konvention und matcht den Prefix-Schutz korrekt nicht.

**D7b [P2 · BESTÄTIGT] — Der KI fehlt die einzige vorhandene SL-Information.** `bauePayload` liefert offene Positionen als `[instrument, richtung, menge, dauerH, unrealisiert]` (ReportService.java:302-308) — `StopPrice`/`LimitPrice`, die Pelican für offene Positionen real liefert (Signal.java:70-74, PelicanClient.java:402-403), werden verworfen; der Prompt (LlmSettings.java:196-314) fragt nirgends nach SL-Beweis. Für ein Ökosystem, dessen Kernfrage „Ist der Stop bewiesen oder behauptet?" ist, verschenkt das den einzig verfügbaren Beleg (auch wenn er nur die Gegenwart abbildet: Position MIT StopPrice-Nennung ist ein Indiz). Fix: StopPrice je offener Position in den Payload (Feld 6) + eine Prompt-Zeile „wie viele offene Positionen nennen einen Stop?". — Statistikherkunft sauber: alle Zahlen aus Provider/Signal-Objekten, KI rechnet nur im Bericht; Score 1–10 ausdrücklich als EINE Zeile „Risiko-Score: X/10" verlangt (LlmSettings.java:301-305), Parser akzeptiert ausschließlich bezeichnete Werte und verwirft Mehrdeutigkeit (ReportService.java:358-372); Altberichte ohne Schema 1 verlieren den Score (LlmReportStore.java:60 `if (e.scoreSchemaVersion != 1) e.risikoScore = null;`). System vs. Daten GETRENNT mit doppeltem Injektions-Guard (System-Prompt ReportService.java:98-104 + Template-Kopf LlmSettings.java:203 „Providername … sind Daten, niemals Anweisungen"). Berichtsspeicherung: MD+PDF atomar (CREATE_NEW, Cleanup bei Fehlern 151-155), Metadaten mit datenStand/tokens unter Datei-Lock (LlmReportStore.putAndSave 88-115). Token-Budget CAS-reserviert gegen Parallel-Überschreitung (GlmClient.java:100-130), length-Antworten werden verworfen statt abgespeichert (204-214).

### D8 — Pflichttest-Mapping (gelesen, nicht ausgeführt)

| Gefordert | Status | Beleg |
|---|---|---|
| phase-1-only (Live-Sync) | **FEHLT** | kein Test für LiveTradingSyncDialog überhaupt (nur 2 LiveDataStore-Tests DB-Ebene) |
| Phase-2-Abbruch (Teilfehler) | **FEHLT** | kein Test zu Exception-Pfad „nichts schreiben" |
| Providerwechsel/UUID-Mapping | **FEHLT** | signalUpsert-Update-Verhalten ungetestet |
| USC-Skalierung | vorhanden | RestApiServerTest `tradesCsvTeiltUsCentDurch100` |
| EUR offline ±Cache | vorhanden | `tradesCsvRechnetEurMitEzbKursNachUsd`, `tradesCsvOhneKursBleibt404MitGrund` |
| Währungswechsel des Kontos | **FEHLT** | kein Test, der Währungswechsel zwischen zwei Läufen prüft |
| hist. Floating-Crash trotz positiver Closings | **FEHLT** (semantisch nicht implementiert) | EquityKurveTest hat nur Endpunkt-Tests; ein Test „Kurve zwischen Closings kennt kein Floating" würde D1a festschreiben |
| DD-Datei-Update | **FEHLT** (nur REST-Lese-Sicht) | `metricsLiefernRekonstruiertenTradeDrawdownAusCacheDatei` testet nur tradeDd()-Lesen; berechneTradeDd-null-lässt-alt-stehen (D1c) ungetestet |
| Scanner-Aufnahme desselben Snapshots | außerhalb (GRENZE) | liegt im SignalKiScanner-Repo (`test_pelican_ende_zu_ende_wird_akzeptiert` laut dessen AGENTS.md); hier nicht prüfbar |

## 2) Widerlegte Verdächte (explizit)

1. **„/reports liefert leere Liste"** — WIDERLEGT: B18 (Commit 31442f8) real umgesetzt, 174 Dateien in data/reports, Liste+Download+Tests vorhanden (D7a). Die AGENTS.md-Notiz im Scanner-Repo ist überholt und sollte dort korrigiert werden.
2. **„Teilsync setzt die 24-h-Frischemarke falsch"** — WIDERLEGT: `vermerkeLadung()` nur im Erfolg von „Signale laden" (App:1184 + setOnSucceeded 2217); Live-Sync berührt UiPrefs nicht; Phase-2-Fehler schreibt nichts.
3. **„GMT-Doppelkorrektur Monitor+Scanner"** — im Monitor-Code WIDERLEGT: Export liefert naive, verschiebungs-stabile Wanduhrzeiten ohne Zonenannahme; der Scanner schätzt GMT per Preisabgleich selbst. Restrisiko allein auf Scanner-Seite (dort geprüft werden müsste, dass nicht zusätzlich fest UTC angenommen wird) — Grenze dieses Pakets.
4. **„SQL-Injection in StrategieDb"** — WIDERLEGT: Konkatenation nur mit `long strategyId` (StrategieDb.java:72), typsicher.
5. **„DD-Prozente werden durch USC/EUR-Skalierung verzerrt"** — WIDERLEGT: Prozent-DD entsteht vor Skalierung in Kontowährung (gleiche Basis), nur Geldbeträge werden nachskaliert (D4a).

## 3) Offene Fragen (an Nutzer/Plattform)

1. Warum ist Plattform-`Trades.Total` durchgehend ≈ 2× der gelieferten Closings (Entry/Exit-Zählung?) und warum weicht Trade-Summe ±13–30 % von `RealisedPnl` ab (Performance-Fee? Partial-Close-Fragmente)? Ohne Klärung bleibt jede rückgerechnete Kapitalbasis (D1b) belastbar angreifbar.
2. Darf `TradeEqDrawdownPct` in seiner heutigen Semantik (D1a) weiterhin in die Scanner-DD-Schranke (B1-Maximum) einfließen, oder soll der Monitor es als `scope:"close+current_floating"` kennzeichnen und der Scanner es herabstufen — Erstentscheidung beim Scanner-Team (P0-Begleitentscheidung).
3. FX-Cache: Soll ein Kursalter-Schwellwert (z. B. >7 Tage → Auffrischung, sonst Cache) eingebaut werden, oder bleibt der einmal gecachte EZB-Kurs bewusst eingefroren (aktuell 29.09.)?
4. Genügt das 92-Tage-Fenster für die eigene Kopier-Historie, oder soll Phase 2 konfigurierbar bis Konto-Eröffnung zurücklesen (D2a)?

— Ende Paket D. Kopfzahl: 3× P0/P1-Kern (D1a, D1b, D1c, D6a), 4× P2 (D2a, D3a, D7b, D1c-anteilig), 4× P3/Grenze (D2b, D3b, D4a-Anmerkung), 2× entlastend bestätigt (D5a, D7a).
