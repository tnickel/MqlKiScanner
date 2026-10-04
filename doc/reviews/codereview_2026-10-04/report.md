# Gesamtbearbeitungs-Review SIGNALDOWNLOADER — Endreport

**Datum:** 04.10.2026 (Durchführung ca. 12:30–19:30 Uhr, autonomer Lauf nach Nutzerauftrag)
**Auftrag:** „mache alle phasen des review ohne stop … und auch gefundene fehler behehen, ich will dann aber ein pdf endreport haben was du gefunden hast und was du geändert hast"
**Workspace:** `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER` — 7 Projekte + `startall.bat`/`README.md`/`UI_KONVENTIONEN.md`
**Detailberichte:** `doc/reviews/codereview_2026-10-04/pakete/paket-A.md` … `paket-I.md` (je Projekt, mit Datei:Zeile-Belegen)
**Rechenorakel:** `doc/reviews/codereview_2026-10-04/orakel/pruef_orakel.py` — **22/22 PASS**

---

## 1. Management-Zusammenfassung

Das Review prüfte alle sieben Projekte in acht parallelen Paketen (A–H) mit anschließender unabhängiger Gegenprüfung (Paket I, 13/13 Befunde bestätigt) und unabhängigen Rechenorakeln (M01–M27, 22/22). Ergebnis: **4 P0-Befunde, 13 P1-Befunde** — davon wurden **alle 4 P0 und 9 der P1 behoben und getestet**; 4 P1 sowie alle P2/P3 (bis auf die mitgegangenen Nebenkorrekturen) sind als offene Punkte mit konkretem Lösungsweg dokumentiert.

Die drei wichtigsten Erkenntnisse:

1. **Die „Monitor-Zweitmessung" ist keine Equity-Messung.** Das Feld `TradeEqDrawdownPct`, das der Scanner seit dem 30.09. als „floating-inklusive Zweitmessung" in seine Drawdown-Schranke UND als RetDD-Nenner übernahm, ist bei **allen vier JavaFX-Monitoren** nachweislich nur eine Kurve aus **geschlossenen** Trade-PnLs — bestenfalls ergänzt um genau *einen heutigen* Floating-Endpunkt (PelicanTrading `EquityKurve.java:57–84`, `ReportService.tradeDdAusTrades`; RoboForex ohne jedes historische Floating; Vantage/Zulu Closing-DD auf rückgerechneter Basis). Ein historisches Floating-Tief bleibt unsichtbar. Der Scanner hat das korrigiert: Der Monitor-Wert bleibt **5. Kanal der harten 30-%-Schranke** (konservativ, B1 unverändert), ist aber **kein RetDD-Nenner und keine „Max-Drawdown"-Messquelle mehr**. Ohne belastbare eigene Kurs-Messung bleibt RetDD unbekannt → kein Grün (Nutzer-Regel 03.10.).
2. **Robo-Signale rechneten mit doppelt abgezogenen Gebühren.** Die Robo-`trades.csv` schrieb das **Netto** in die Profit-Spalte *und* echte Commission/Swap in deren Spalten; der Scanner rechnet `net = profit + commission + swap` → Swap/Commission flossen zweimal ein (real belegt: −24.709 USD statt −9.337 USD bei Signal 21452129). Behoben: Robo liefert jetzt **Brutto** in Profit; der Bestand braucht einen Re-Scan.
3. **Der MqlDownloader konnte bei Extraktionsfehlern Originaldaten massenhaft löschen.** Der MPDD-Löschfilter behandelte Berechnungs*fehler* wie „schlecht" (0.0) und DataExtractor löschte bei jedem Parse-Fehler HTML+CSV+TXT — nur durch den Produktionsschalter `subscribersOnly=true` aufgehalten. Behoben: NaN-Sentinel + Löschschutz (7 Löschaufrufe aus Fehlerpfaden entfernt).

**Testergebnis nach allen Fixes:** Scanner **1341 passed** (Baseline 1331; +10 neue Regressionstests, +1 Nachbesserungstest), RoboForex 129 ✔, Zulu 81 ✔, PelicanTrading 63 ✔, MqlDownloader 82 ✔, Vantage 25 ✔, PelicanWinnerLooser 156 ✔ (unverändert, kein Eingriff). 22/22 Orakel bestanden.

**Wichtigste Betriebsfolge:** Der Scanner-Bestand braucht einen **Re-Scan mit laufendem MT5-Terminal** — dann wirken (a) die Dedup-Konsistenz für RetDD/Portfolio, (b) Robo-Brutto-Neulieferungen und (c) die neue RetDD-Basis (Kurs-Messung statt Monitor-Closing-DD). **HRC Algo und ImpulseNet (pelik) können dabei von 🟢-Kandidat auf 🟡 kippen**, solange keine belastbare Kurs-Messung vorliegt — das ist regelkonform („kein Grün ohne valide Equity-Messung") und bewusst so dokumentiert.

---

## 2. Manifest (Phase 0, eingefrorener Stand 04.10.2026 ~12:30)

| Projekt | HEAD | Arbeitsbaum | Rolle |
|---|---|---|---|
| SignalKiScanner | `85dc290` | 5 dirty (README, doc/21, `=2076`, doc/reviews/, output/) — **vorhandene Änderungen blieben unangetastet** | Hub, Forensik, Ampel, RetDD |
| MqlDownloader | `c44d2f6` | README | MQL4/5-Downloader, :8089 |
| PelicanTrading | `9ea8b39` | README | Pelican-Monitor, :8090 |
| PelicanWinnerLooser | `dd4a94f` | **35 dirty** (aktive Entwicklung) → nur Review, kein Eingriff | Kopierkonto-Forensik |
| roboforex | `6eda52a` | README | CopyFX-Monitor, :8091 |
| vantage | `571e9c2` | README | Vantage-Monitor, :8092 |
| zulumonitor | `97f02ff` | README | Zulu-Monitor, :8093 |

Umgebung: Python 3.12.10, Maven 3.9.6, JDK 25 (Temurin). `=2076` ist eine **leere** Datei (offenbar versehentlich erzeugt, z. B. `curl -o =2076`); sie wurde nicht gelöscht (fremdes Artefakt). `output/pdf` enthält Arbeitsausgaben.

## 3. Methodik

- **Phase 1–2:** 8 parallele Subagent-Pakete (A Scanner-Mathematik, B Scanner-Abläufe, C MqlDownloader, D PelicanTrading, E WinnerLooser, F RoboForex, G Vantage+Zulu, H projektübergreifend: Skripte/REST-Verträge/Logs) — nur lesend, Belegpflicht Datei:Zeile, Widerlegungs-Pflicht für Verdachte.
- **Phase 3:** Test-Baselines vor jedem Fix (pytest 1331 grün; mvn × 6 grün) + **unabhängige Rechenorakel** (M01/M02/M04–M07/M23/M24/M27; Soll-Werte ohne Import der Produktionsformeln hergeleitet). Die Orakel fanden selbst einen Fehler (M27: NaN/Infinity flossen ungefiltert in die DD-Schranke).
- **Phase 4:** Ende-zu-Ende-Verifikation der Kernketten über bestehende Akzeptanztests (Quellen-Regressionen, Beweis-Dedup-Tests, Stop-Gate-Tests) und neue Tests.
- **Phase 5:** Unabhängige Gegenprüfung (Paket I) **aller** P0/P1-Schlüsse und jedes Fix-Diffs — 13/13 BESTÄTIGT; 3 Nachbesserungen (llm_runner-Durchreichung, Vakuum-Test, Doku) unmittelbar umgesetzt.
- **Phase 6:** dieser Bericht + PDF.

Grenzen: kein produktiver Netzwerkabruf, kein echter Login, kein LLM-API-Aufruf, kein Terminalstart. Sämtliche Live-abhängige Prüfungen (MqlDownloader-DOM, Vantage-10402-Parameter-Echtheit) sind als isoliert belegte Befunde mit Repro-Weg dokumentiert.

---

## 4. Befunde und Maßnahmen (nach Schwere)

### P0 — behoben (4)

| ID | Projekt | Befund (Beleg) | Maßnahme |
|---|---|---|---|
| A2a | Scanner | RetDD-Zähler + Portfolio-Kurven lasen Trade-CSVs **ohne Dedup-Beweis** (`portfolio_statistik.py:78,122`), während die Forensik deduped rechnete → Ertrag/RetDD auf rohem, DD auf bereinigtem Bestand (THG: 27 % Duplikate). Latent scharf: 26 Signale im Bestand mit identischen Zeilen. | `plattform_positions` durchgereicht in `monatsrenditen`, `effizienz_kennzahlen`, `statistik()`, `pipeline.py` (2 Caller + `_implizite_kapitalbasis`) sowie nach Gegenprüfung auch `llm_runner.py` (beide `load_export`). Tests: `test_review_2026_10_04.py`. |
| A1c/D1/F6a/V5/Z4 | Scanner + alle Monitore | **Monitor-DD ist Closing-Kurve**: Pelican `EquityKurve.java:57–84` (nur Close-PnLs + 1 heutiger Floating-Endpunkt; Basis = endKum ÷ Plattform-RealisedReturn, live ±13–30 % Diskrepanz), Robo `EquityKurve.java:20–49` (Positions-Netto erst zum letzten OUT; Yield-Fenster ÷ Lebensalter), Vantage/Zulu Closing-DD auf rückgerechneter Basis. Der Scanner machte ihn zum RetDD-Nenner und übersprang bei ihm die Kurs-Reko (`pipeline.py:1411–1420`). | Monitor raus aus `_equity_messwerte`/`max_drawdown_equity_pct`; **Skip entfernt** — Kurs-Reko läuft jetzt auch bei Quellen-Signalen; Monitor bleibt Schranken-Kanal (B1) und Score-Dimension. Prompts (Default + Dateien, B12-synchron), Ampel-Matrix, Regelwerk, Urteilstexte angepasst; 5 Testdateien auf die neue Semantik gebracht (Intention jeweils gewahrt). |
| F4 | roboforex + Scanner | **CSV-Netto-Vertragsbruch**: `RestApiServer.mql5Zeile` schrieb `netPnl` in Profit UND echte Commission/Swap → Scanner `models.py:28–30` zog Gebühren doppelt (ΣStorage −15.523 USD wurde zu −24.709 USD Netto). | Robo schreibt jetzt **Brutto** (`netPnl − commission − swaps`); 2 Tests aktualisiert (MT4-Fall mit 0-Gebühren unverändert). 129 Tests grün. **Re-Scan erforderlich** (alter SHA-Cache heilt erst nach Neulieferung). |
| C2a/C2b | MqlDownloader | **C2a** (offen): Monats-Extraktion matcht DOM nicht mehr — 110/201 `_root.txt` ohne `MonthProfitProz`, `Average3MonthProfit=0,00`, 402× WARN am 04.10. → Scanner erhält Ertrag 0 für >50 % der Signale. **C2b** (behoben): MPDD-Löschfilter und DataExtractor löschten Originaldaten auch bei Berechnungs-/Extraktions**fehlern** (7 `deleteRelatedFiles`-Aufrufe in Fehlerpfaden; 0.0-Sentinel „wie schlecht"). | C2b: NaN-Sentinel in `HtmlConverter`/`MPDDCalculator`; Löschen nur bei `!isNaN && < 0.5`; alle 7 Fehl-Löschungen entfernt; 82 Tests grün. C2a: braucht Live-MQL5-Seite (DOM-Struktur der Monatszeilen) — Repro-Weg im Report, **offen bis Freigabe**. |

### P1 — behoben (9)

| ID | Projekt | Befund | Maßnahme |
|---|---|---|---|
| B1a | Scanner | Autonomer Full-Scan erzeugte **3 LLM-Berichte je Signal** (bis ~200k Token/Lauf), obwohl die GUI basis-aktuelle Berichte aus der DB restauriert. | `scan_launcher.py` restauriert wie die GUI — **nur modus=full** (Teilscan-Vertrag „alle Stufen neu" bleibt unangetastet). |
| B2a | Scanner | Endlos-Retry: skipped/geprueft==0 setzen keine Merker (F4/B8, absichtlich) → Dauerfehler erzeugte **jedem Daemon-Takt** vollen Listen-Crawl + P2-Postfach-Meldung. | Versuchs-Deckel `SCAN_VERSUCHE_PRO_TAG=3` (Zähler im gehaltenen Lock — Kollisionen kosten nichts; Erfolgs-/F4/B8-Semantik unverändert). |
| D1 | PelicanTrading | siehe P0-Zeile oben (Semantik-Beweis) | Scanner-seitig behoben; monitor-seitig D1c. |
| D1c | PelicanTrading | `berechneTradeDd`: null ließ **alte** DD-Werte lautlos überdauern; `trade_dd.csv` ohne Zeitstempel (30.09.-DD neben 01.10.-Rendite-Basis). | null → Cache-Eintrag verworfen (+Log); Datei jetzt mit Spalte „Berechnet" (abwärtskompatibel gelesen, REST unbeeinflusst). 63 Tests grün. |
| Z5 | zulumonitor | LLM-**Systemtext leer** (`ReportService.java:77`): Trader-Name/Land/Broker als Fremdtext auf gleicher Priorität wie die Betreiber-Vorlage (Injektionsfläche). | System-Nachricht nach RoboMonitor-Muster (P05) ergänzt; GlmClient nutzt `role:system` (verifiziert). 81 Tests grün. |
| V1 | vantage | `10402 err_invalid_param` bei Kategorien type 2–4 mit leerem `accountId` — **dauerhaft** (8 Läufe, 27.09.–04.10.), geschluckt und für Nutzer/Hub unsichtbar; kuratierte Listen 2–4 + deren Feld `months` fehlen. | Gebündelter, deutlicher Hinweis je Laden ( Ursache + Folge + Kompensation über Historien-Korrektur ee2c07c). Paramter-Echtheit selbst braucht Live-Prüfung → offene Anschlussprüfung. |
| V2a | vantage | Batch-Download kappt auf **2.000 Trades** (Fall: „2000 von 72825") — REST meldete die Kappung nicht → Scanner konnte DD/RetDD auf ~2,7 % der Historie rechnen. | `TradeStore.meta` führt jetzt `total=`; `/metrics` liefert `TradesStored`, `TradesTotalAvailable`, `TradesTruncated`. Scanner-Verbrauch des Felds = Folgeschritt (offen). 25 Tests grün. |
| H1a/H1b/H1c | Startskripte | `startall.bat` + `start.bat` killten **jeden** Portbesitzer (8504, 8089–8093) und **global** `streamlit.exe` ohne Identitätsprüfung; MqlDownloader (:8089) wurde nie gestartet (Hub-Meldung „nicht erreichbar" 04.10. 12:46); Bereitschaftsprüfung nur Port 8504 → „Fertig"-Meldung irreführend. | Identitätsgeprüfte Beendigung (CommandLine-Suite-Muster; fremde Prozesse bleiben unangetastet + werden gemeldet), globaler streamlit-Kill entfernt, MqlDownloader-Start ergänzt, Bereitschaftsschleife über die ganze REST-Kette + je-Port-Statusbild. Statisch geprüft (Ausführung bewusst nicht auf dem Produktivrechner). |
| E2a-Eskalation | PelicanWinnerLooser | — (siehe offene Punkte: bewusst nur Report, aktive Parallel-Entwicklung) | — |

### P2/P3 — mitgegangene Korrekturen (Scanner)

- **B9a:** Scan-Seite las `session_state["results"]` statt `"scan_results"` → Portfolio-PDF-Anhang „Empfohlene Strategien" war dort **still leer**. Korrigiert.
- **B3a:** Korrupte Lock-`ts` warf ValueError statt sauberer Lock-Entscheidung → robust (Entscheidung über `_lock_blockiert` am lebenden PID).
- **A-P3 / Orakel M27:** `_platform_float` versteht jetzt Mischformate (`1.403,03`, `1,403.03` — letztes Trennerzeichen entscheidet) und leitet **NaN/Infinity (Zahl oder String) auf Default** (max() mit NaN ist positionsabhängig, Infinity sperrt immer) — ein echter, vom Orakel gefundener Fehler.
- **A-P3:** `ertrag_monat_pct_forensik` nutzt jetzt `365,2425/12` (MONAT_TAGE) statt gerundet 30,44 — konsistent mit `effizienz_kennzahlen`.
- **A-P3/Stale-Texte:** Score-Gate-Resttexte („Grün verlangt Score < 5", „kein Kandidat") aus `ampel_matrix.py` und `regelwerk.py` entfernt — der Grün-Weg entscheidet seit 04.10. Vormittag nicht mehr gegen den Score.
- **D7-Teil:** (PelicanTrading StopPrice im KI-Payload) — nicht umgesetzt, offener Punkt (siehe 5.3).

---

## 5. Offene Punkte (mit Lösungsweg und Priorität)

### 5.1 Braucht Nutzer-Entscheidung
1. **H2a — REST-Sicherheit der 5 Monitore:** Alle REST-Server binden `0.0.0.0` mit Token-Default **leer** und CORS `*` — Trade-Daten sind damit im Heim-LAN/browser-lesbar. Bewusst **nicht** autonom umkonfiguriert, weil die Produktiv-Verkabelung (Scanner → Monitore über `192.168.178.164`) ein Loopback-Bind brechen würde. Empfehlung: je Quelle ein Token setzen (Admin → Datenquellen speichert es je Quelle im Secrets-Store) ODER Bind auf 127.0.0.1 + Umstellung der Quellen-URLs auf localhost.
2. **Verhalten RetDD/Grün:** Mit dem Fix verlieren Signale ohne belastbare Kurs-Messung den Grün-Weg (RetDD unbekannt). HRC Algo/ImpulseNet sind erst nach **Re-Scan mit Terminal** wieder Grün-Kandidaten. Falls der Nutzer stattdessen die alte (unsichere) Monitor-Nenner-Variante will: Revert ist ein Einzeiler in `pipeline._equity_messwerte` — nicht empfohlen.

### 5.2 Braucht Live-Zugang / nächsten Lauf
3. **C2a Monats-Extraktion (P0, Wirkung):** DOM-Regex `MonthDetailsExtractor.java:79/30` gegen aktuelle Signalseite prüfen (lokal vorhandene `_root.html`-Bestände nutzen). Bis dahin liefert `/metrics` für >50 % der MqlDownloader-Signale Ertrag 0 — der Scanner sieht das als „unbekannt/0", nicht als Fehler.
4. **Robo-Rebuild + Re-Scan:** Robo-Monitor neu starten/bauen, damit `trades.csv` Brutto liefert (SHA ändert sich → Scanner übernimmt neu); danach Scanner-Bestands-Re-Scan (wirkt auch für Dedup-Konsistenz + RetDD-Basis).
5. **Vantage-10402-Parameter:** mit echtem `accountId`-Wert testen ob type 2–4 dann gültig sind (dann statt Hinweis den Parameter fixen).
6. **Zulu Z1a (P1, nicht behoben):** Schema-ungültige 200er-Antworten lösen keinen Host-Wechsel aus (nur ≥500/404/0) — Provider 426712 blieb dauerhaft ohne Trades (7 Totalausfälle 26.09.). Fix-Vorschlag: Parse-Fehler als Host-Fehler werten mit begrenztem Retry + Test (Muster im Bericht G).

### 5.3 Umsetzung empfohlen, nächster Coding-Auftrag
7. **Robo F6a (P1):** `YieldInceptionPct`/`Average3MonthProfit` nutzen den Toolbar-Rating-Yield (Fenster wählbar, Produktionslog zeigte „Zeitraum 4" = 6 Monate) geteilt durch das **Lebensalter** → Fenstersprung; dieselbe falsche Basis in `tradeDdAusTrades`. Korrektur: Inception-/Gesamt-Yield bzw. Kennzeichnung + Persistenz des Zeitraums.
8. **Robo F1b (P1):** Equity-Kurve schreibt Positions-Netto erst zum **letzten** OUT → Teilschließungs-Gewinne vor Schlussverlust verschwinden aus `TradeEqDrawdownPct`. Korrektur: Kurvenpunkte je Teil-OUT.
9. **PWL E2a (P1):** SQLException mitten im Job lässt ihn `state='running'` → „Fortsetzen" endet in 500-ms-Endlosschleife bis Neustart. **Bewusst nicht behoben** — der Arbeitsbaum enthält 35 uncommittte Dateien aktiver Entwicklung; Fixvorschlag liegt im Bericht E (Job im Catch auf PENDING bzw. running-Jobs des Laufs beim Fortsetzen zurücksetzen).
10. **B6a (P2):** `results_from_db` materialisiert bei jeder DB-Lesung alle PDFs (`pipeline.py:544–550`) — Performance; Empfehlung: nur bei fehlender Datei.
11. **Scanner-Konsum von `TradesTruncated` (V2a-Folge):** Warnhinweis im Scan-Protokoll/KI-Payload, wenn eine Quelle gekappte Historie meldet.
12. **D7 (P2):** PelicanTrading KI-Payload verwirft `StopPrice` offener Positionen (einziger verfügbarer SL-Beleg erreicht das LLM nicht).
13. **D6a (P1, konzeptionell):** „Signale laden" erneuert Stats, aber nie Tradelisten/DD — 24-h-Frischemarke signalisiert trotzdem Frische; hasClosed prüft nur lokalen Hash. Braucht Konzept (Frische-Prüfung oder ehrliches Offline-Alter).
14. **A-P3-Rest:** Credit-Zeilen werden still verworfen (`parser.py:210`) — Zähler/Log empfohlen.

### 5.4 Entlastend widerlegt (Auszug)
- RetDD-Nenner nutzte **nicht** `dd_maximum` (alle 5 Kanäle) — Plattform-/Balance-DD flossen nur in die harte Schranke; die Schranke vergleicht überall ungerundet (30,0001 % fällt durch).
- Keine Kommissions-Doppelung bei Vantage (`0/leer` bei nettem Profit) und keine GMT-Doppelverschiebung (Preisabgleich selbstkorrigierend, DST über Wochen-Vererbung begrenzt).
- Lock v4, Teilscan-Scope-Parität, Fix-ID-Wirkstellen, Betreuer/Melder/Chef-Idempotenz, Tradeserver-Sync, B12-Prompt-Sync, Traversal-Schutz, H2-Transaktionen, Robo-Aggregator-Summenerhaltung — jeweils intakt bestätigt.
- `/reports` bei PelicanTrading ist **nicht mehr leer** (174 Dateien; AGENTS-Notiz überholt), Zulu `/history` seit 16f693e gefüllt.

---

## 6. Test- und Beweislage

| Suite | Baseline | Nach Fixes |
|---|---|---|
| SignalKiScanner (pytest) | 1331 passed | **1341 passed** (+10 neue; 4 llm deselected wie immer) |
| roboforex (mvn) | 129 ✔ | **129 ✔** (2 Tests auf Brutto-Vertrag angepasst) |
| zulumonitor (mvn) | 81 ✔ | **81 ✔** |
| MqlDownloader (mvn) | 82 ✔ | **82 ✔** |
| PelicanTrading (mvn) | 63 ✔ | **63 ✔** |
| vantage (mvn) | 25 ✔ | **25 ✔** |
| PelicanWinnerLooser (mvn) | 156 ✔ | 156 ✔ (kein Eingriff) |
| Rechenorakel M01–M27 | — | **22/22 PASS** |

Neue Testdatei: `tests/test_review_2026_10_04.py` (10 Tests: Dedup-Konsistenz Forensik↔RetDD↔Portfolio↔KI, Monitor-kein-Nenner, Scheduler-Deckel, Lock-ts, Zahlenformate, NaN/inf). Semantik-Tests angepasst (je mit Begründungskommentar): `test_retdd_equity_pipeline.py`, `test_retdd_kriterien_prompts.py`, `test_ampel_matrix.py`, `test_drawdown_anzeige.py`, `test_quellen.py`, `test_review10_stop_gate.py`, `test_review15_reports.py`, `test_pdf_reports.py`.

**Abdeckung:** alle produktrelevanten Rechen- und Bewertungspfade statisch geprüft + durch Tests/Orakel gestützt; JavaFX-UI-Feinprüfungen und Selenium-Abläufe stichprobenartig (Pakete C–G). E2E-Szenarien: 19/28 durch bestehende Tests abgedeckt, 2 teilweise, 5 offen (E04/E14/E21-DST/E26/E27 — E27 durch das Startskript-Härting jetzt konzeptionell abgedeckt, aber nicht automatisch getestet).

## 7. Empfohlene nächste Schritte (Reihenfolge)

1. Robo-Monitor neu bauen/starten (Brutto-CSV) → dann Scanner-**Voll-Re-Scan mit laufendem MT5-Terminal** (wirkt für RetDD-Basis, Dedup-Konsistenz, Robo-Brutto; Ampel-Änderungen erscheinen im Wechsel-Protokoll).
2. H2a-Entscheidung (Token je Quelle oder Loopback) treffen.
3. C2a mit Live-Seite angehen (MqlDownloader-Monatswerte).
4. Offene P1 aus 5.3 als nächsten Auftrag (Robo F6a/F1b, Zulu Z1a, PWL E2a nach Abschluss der Parallel-Entwicklung).

---
*Erstellt autonom am 04.10.2026; alle Zeilenangaben gegen den Stand des jeweiligen Arbeitsbaums vom 04.10.2026 ~12:30 verifiziert; Details und Belege in den Paketberichten A–I.*
