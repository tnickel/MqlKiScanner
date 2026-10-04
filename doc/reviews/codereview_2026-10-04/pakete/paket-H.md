# Paket H — Projektübergreifendes Review: Startskripte, REST-Verträge, Logs, Archiv

Datum: 04.10.2026 · Prüfer: Subagent PAKET H (Codereview Gesamtnworkspace)
Gegenstand: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER` — 7 Projekte
(SignalKiScanner [Hub], MqlDownloader :8089, PelicanTrading :8090, roboforex :8091,
vantage :8092, zulumonitor :8093, PelicanWinnerLooser [kein REST]).
Methode: rein statisch/lesend; Log-Analyse per Python-Skript (read-only);
kein Start von Apps/Tests/Servern, kein Netzwerk, keine Produktiv-DB schreibend
geöffnet. Secrets in Belegen redigiert.

---

## 0) Manifest und Abdeckung

Geprüfte Artefakte (Auswahl):

| Bereich | Dateien |
|---|---|
| Startskripte | `startall.bat` (Root, 78 Z.), `SignalKiScanner/start.bat` (94 Z.), `PelicanTrading/run.bat`, `roboforex/run.bat`, `vantage/run.bat`, `zulumonitor/run.bat` (je 3–4 Z.), `MqlDownloader/start.bat`, `deploy.bat`/`deploy.ps1`, `PelicanWinnerLooser/run.bat` |
| REST-Server | `PelicanTrading/…/rest/RestApiServer.java` (826 Z.) + `RestApiConfig.java`, Analoges roboforex (610), vantage (600), zulumonitor (602), `MqlDownloader/src/rest/RestApiServer.java` (1079) + `ProviderFiles.java`, `MetricsParser.java`, `ConfigurationManager.java` |
| Hub-Consumer | `SignalKiScanner/src/mqlkiscanner/{quellen.py (170), ingest.py (326), downloader_client.py (200), rest_api.py}` |
| Logs | 9 relevante Logdateien (s. Tabelle 0b), inkl. `C:/Forex/MqlAnalyzer/logs/` (9,8 MB, 15 Dateien) |
| Archiv | `waste/` mit 7 Review-Archiven |
| Tests | SignalKiScanner `tests/` (100 Dateien, 1019 Testfunktionen), je Monitor `src/test/java` (7–21 Klassen), MqlDownloader `tests/` |

**Tabelle 0b — Log-Manifest (Größe, Zeitraum, Muster-Zähler):**

| Log | Größe | Zeitraum | ERROR/WARN | Bemerkung |
|---|---|---|---|---|
| `SignalKiScanner/data/scan_workflow.log` | 479 KB, 4991 Z. | 29.09.–04.10. | 55 Tracebacks, 54 Retries, 4× ValueError ‚9,10‘ | keine Datumszeilen je Lauf |
| `SignalKiScanner/data/agenten_daemon.log` | 0,4 KB | 22.09. | leer | Daemon loggt in DB, nicht Datei |
| `SignalKiScanner/data/streamlit_restart.log` | 0,2 KB | 23.09. | leer | |
| `PelicanTrading/data/pelicanmonitor.log` | 42 KB, 452 Z. | 27.09.–04.10. | 2× Live-Sync-401 | |
| `roboforex/data/robomonitor.log` | 228 KB, 3233 Z. | 26.09.–02.10. | 3× Plattform „rst“ | „500/502“-Treffer sind „Tage“, keine HTTP |
| `vantage/data/vantagemonitor.log` | 50 KB, 489 Z. | 27.09.–04.10. | 24× 10402, 3× echtes 5xx-Muster geprüft=0 | |
| `zulumonitor/data/zulumonitor.log` | 154 KB, 1744 Z. | 25.09.–28.09. | HTTP 500 ZuluTrade-API, 1× LLM length | Monitor seit 28.09. nicht gelaufen |
| `PelicanWinnerLooser/data/pelican-winner-looser.log` | 706 KB, 9715 Z. | 02.10.–04.10. | 31× Session-401, 3× Exception (1× SQLITE_CONSTRAINT_FOREIGNKEY) | |
| `C:/Forex/MqlAnalyzer/logs/application.log` (+14 rotierte) | 675 KB / 9,8 MB | 12/2025–04.10. | 402× ChartDataExtractor-WARN am 04.10. | error.log leer |

Abdeckung der Prüfaufträge: H1 ✅, H2 ✅ (Matrix unten), H3 ✅ (Cluster unten),
H4 ✅ (Index unten), H5 ✅ (Abdeckungstabelle unten), H6 ✅. Grenzen: keine
dynamischen Prüfungen (Ports/Prozesse nicht live abgefragt, Auftragslage
statisch); Zulu-/Robo-Logs enden am 28.09./02.10. — Aussagen zu „aktuell“
beziehen sich auf den letzten Logstand.

---

## 1) Befunde

### H1 — Startskripte

**H1a [P1, BESTÄTIGT] — Portbereinigung ohne Identitätsprüfung tötet fremde Prozesse.**
`startall.bat:15`: PowerShell über `Get-NetTCPConnection -LocalPort` auf
8504/8089–8093 → `Stop-Process -Force` auf den OwningProcess — ohne Prüfung,
WEM der Prozess gehört. Zeile 17 zusätzlich `taskkill /F /IM streamlit.exe`
(global, alle Streamlit-Apps des Nutzers). `SignalKiScanner/start.bat:25`
dasselbe für 8504, `:28` streamlit.exe global, `:33` jedes „python … streamlit
run“ anderer Projekte. Auswirkung: Ein fremdes Tool auf 8089–8093/8504 (oder
ein zweites Streamlit-Projekt) wird kommentarlos abgeschossen — Datenverlust
möglich (z. B. laufender Export eines anderen Tools). Fix (minimal-invasiv):
vor `Stop-Process` die CommandLine des Prozesses prüfen (wie `startall.bat:16`
es für die JavaFX-Monitore bereits korrekt macht: Match auf
pelicanmonitor/vantagemonitor/robomonitor/zulumonitor) und Nicht-Zugehörige
nur melden, nicht töten; `taskkill /IM streamlit.exe` auf Pfad-Basis
(`Get-CimInstance … CommandLine -match 'SignalKiScanner'`) einschränken.

**H1b [P1, BESTÄTIGT] — MqlDownloader (:8089) fehlt in der Startkette.**
`startall.bat:25–39` starten nur Scanner + 4 JavaFX-Monitore; der MqlDownloader
(Swing-GUI, eigenes `start.bat` mit `mvn compile exec:java`) wird NICHT
gestartet, obwohl `:66` ihn als Endpunkt anpreist. Live-Beleg:
`scan_workflow.log` 04.10. 12:46:39 „Abbruch: MqlDownloader unter
http://localhost:8089/api/v1 nicht erreichbar (ConnectionError)“ — genau der
Zustand nach startall. Auswirkung: Downloader-Abgleich/Spiegel bricht ab
bzw. Quelle mql5 rot, solange der Nutzer das GUI-Tool nicht von Hand startet.
Fix: Startzeile ergänzen (`start "" /min cmd /c "cd /d …MqlDownloader &&
start.bat"` — pause dort entfernt) ODER Statuszeile „nicht gestartet — bitte
manuell“ statt stiller Lücke. Nutzer-Entscheidung nötig (GUI-Tool, evtl.
bewusst manuell).

**H1c [P2, BESTÄTIGT] — Bereitschaftsmeldung prüft nur GUI-Port 8504.**
`startall.bat:46–56`: Warteschleife pollt ausschließlich Port 8504; danach
erscheint „Fertig“ (Zeile 76) inkl. Endpunkt-Liste — auch wenn 8090–8093
(Maven-Compile der JavaFX-Monitore dauert deutlich länger) noch nicht hören.
Zusätzlich Inkonsistenz Zeile 22: Die Freigabe-Warteschleife listet
@(8504, 8090–8093) — **8089 fehlt** (dort zwar laut H1b nicht gestartet, aber
die Kill-Liste Zeile 15 enthält es). Fix: alle 6 Ports mit Einzelstatus pollen
und je Port „bereit/wartet“ ausgeben; Meldung „Fertig“ an alle-ports-gebunden
koppeln oder ehrlich „Scanner bereit, Monitore starten im Hintergrund“.

**H1d [P3, BESTÄTIGT] — run.bat der Monitore ohne Maven-Check/Fehlerbehandlung.**
`PelicanTrading/run.bat`/`vantage`/`roboforex` (je 3 Zeilen: `mvn javafx:run`)
prüfen weder `mvn`-Vorhandensein (MqlDownloader/start.bat:11–19 macht das
korrekt) noch werten sie errorlevel aus; vantage/robo schließen das Fenster
sofort (kein `pause`, anders als zulu `run.bat:4`). Bei Build-Fehler verschwindet
die Ursache mit dem Fenster. Fix: 3-Zeilen-Muster um `where mvn`-Check + `pause`
ergänzen (Kopie des MqlDownloader-Musters).

**H1e [GRENZE] — Doppelstart-Schutz existiert praktisch nicht (bewusst kill-first).**
Beide Skripte lösen Doppelinstanzen über Vorab-Kill (H1a), nicht über
Port-Erkennung mit Abbruch. Zweiter startall-Lauf im Abstand von Sekunden
tötet frisch gestartete Monitore wieder (Kill-Phase läuft vor jedem Start).
Verhalten konsistent, aber in Kombination mit H1a riskant. Fix: nach Kill
 kurzen Port-Frei-Warten (existent, `startall.bat:21–22`) belassen und im
Zweitlauf abfragen.

### H2 — REST-Vertragsmatrix

**Tabelle H2-1 — Endpunkte je Quelle (implementiert ✓ / Hub konsumiert ←):**

| Endpunkt | MqlDownloader :8089 (v mql4/mql5) | Pelican :8090 (pelican) | robo :8091 (mql4/mql5 je Signal) | vantage :8092 (vantage) | zulu :8093 (zulu) |
|---|---|---|---|---|---|
| `/api/v1/health` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `/providers` (Katalog, paginiert) | ✓ (+CSV-Format) | ✓ (Filter/Sort) | ✓ | ✓ | ✓ |
| `/providers/{id}` | ✓ (alle Versionen) | ✓ | ✓ | ✓ | ✓ |
| `/{v}/history` | ✓ (DB-Abonnenten) | ✓ (kopierer.db) | ✓ | ✓ (Tages-Snapshots) | ✓ (ehrflich leer) |
| `/{v}/trades` (JSON) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `/{v}/trades.csv` (mql5-Format) | ✓ (Original) | ✓ (konvertiert) | ✓ (Deal→Position) | ✓ | ✓ (nur USD-Konten) |
| `/{v}/metrics` | ✓ (aus *_root.txt) | ✓ | ✓ | ✓ | ✓ |
| `/{v}/reports` + `/{datei}` | ✓ + Download | ✓ + Download (B18) | Stub (leer, kein Download) | Stub (leer) | Stub (leer) |
| Extras | `/trades`-Katalog, `/trades/file/{v}/{name}`, `/events`, `/summary`, `/openapi.json` | — | — | — | — |
| Hub konsumiert (`downloader_client.py`) | health, providers, provider, metrics, trades_csv, history, reports, download_report (Z. 138–191) — identisch für ALLE Quellen | ← | ← | ← | ← |

**H2a [P1, BESTÄTIGT] — Alle 5 REST-Server binden Wildcard (0.0.0.0), Token-Default leer.**
`new InetSocketAddress(config.getPort())` ohne Host = alle Interfaces:
PelicanTrading `RestApiServer.java:117`, roboforex `:96`, vantage `:98`,
zulumonitor `:101`, MqlDownloader `:74` (dort Doku Z. 42 ausdrücklich „im LAN“;
`getLocalUrls()` Z. 110–127 druckt die LAN-IP). `RestApiConfig.java:31`
(`token = ""`) bzw. MqlDownloader `configManager.getApiToken()` — ohne
Konfiguration läuft jeder Server **ohne Auth im LAN**. Kontrast: Der Hub
selbst bindet bewusst `127.0.0.1` (`rest_api.py:44 DEFAULT_BIND`). Gefahr:
Trade-Historien, Berichte, Provider-Stammdaten für jeden LAN-Teilnehmer
lesbar; mit CORS `*` (alle Server, z. B. Pelican `RestApiServer.java:759–762`)
kann sogar eine beliebige Webseite im Browser des Nutzers die Daten
cross-origin abrufen, wenn kein Token gesetzt ist. Fix (minimal): Default-Bind
auf `127.0.0.1` legen und `bindAddress` in `rest_api.json`/Konfiguration
optionale machen (Nutzer, der LAN will — Log zeigt Nutzung von
192.168.178.164 — trägt sie explizit ein); alternativ Token-Pflicht erzwingen,
sobald bind ≠ loopback.

**H2b [P2, BESTÄTIGT] — Token im URL-Query akzeptiert (Token-in-URL-Log-Risiko).**
Alle 5 Server nehmen `?token=` an: Pelican `RestApiServer.java:723–725`, robo
`:530`, vantage analog, zulu analog, MqlDownloader `:970–971` (der eigene Test
`tests/rest/RestApiServerTest.java:228` demonstriert die Query-Nutzung).
Tokens in URLs landen in Proxy-/Browser-/Server-Logs. Der Hub-Client nutzt
korrekt nur den Header (`downloader_client.py:93–94`). Fix: Query-Variante
deprecaten (Log-Warnung) bzw. entfernen; Header/Bearer reichen.

**H2c [BESTÄTIGT, positiv] — Pfad-Traversal überall verhindert.**
(a) Pelican reportDownload (`RestApiServer.java:647–660`): liefert nur exakte
Namen aus der gefilterten Liste, nie zusammengesetzte Pfade. (b) MqlDownloader
`ProviderFiles.findByName` (`:114–120`) lehnt `/`, `\`, `..` ab; Regressionstest
`RestApiServerTest.java:191–192` (Traversal-URL → 404). (c) Hub-Seite
sanitisiert Kürzel UND Version für Cache-Pfade (`ingest.py:30–42
_version_sicher`, Review 29.09. D). (d) robo/vantage/zulu `/reports` sind
leere Stubs (Z. 196 je) — kein Downloadpfad, kein Risiko. Kein Traversal
gefunden.

**H2d [P2, BESTÄTIGT] — Feldnamen-Gleichheit suggeriert gleiche Semantik (DD-Felder).**
`Tabelle H2-2 — DD-/Kapitalfelder je Quelle (Produzenten-Semantik → Hub-Verarbeitung)`:  

| Feld | MqlDownloader | Pelican | robo | vantage | zulu | Hub (`ingest.metrics_zu_stats`, Z. 291–326) |
|---|---|---|---|---|---|---|
| `EquityDrawdown` | aus Root-Seite (Plattform-Selbstauskunft) | `effektiverDdMax()` (Web-DD, abs) | Gesamt-DD bevorzugt, sonst Zeitraum | `MaxDrawDownPctAll` (abs) | `OverallDrawdownPercent` (abs) | → `dd_equity_pct` (Fallback `MaxDDGraphic`) — **nur Name, keine Semantikprüfung** |
| `MaxDDGraphic` | Root-Seite | `maxDrawdownPct` | Zeitraum-DD | = EquityDrawdown | `MaxDrawdownPercent` | Fallback-Nenner |
| `TradeEqDrawdownPct` | **nicht vorhanden** | eigene Reko aus trade_dd.csv (`:544–559`) | eigene Reko | eigene Reko | eigene Reko | → `monitor_trade_eq_dd_pct` = 5. Maximum in DD-Schranke (B1) |
| `InitialDeposit` | nicht geliefert (ruht) | **bewusst nicht gesetzt** (Klassen-Doku `:59–64`) | nicht vorhanden | nicht vorhanden (AumUsd ist Kopierer-Kapital) | nicht vorhanden | → `initial_deposit_usd` (None → Kapitalbasis-Regel ruht) |
| `InitialDepositVirtual` | — | 10000.0 + Note (`:413–415`) | — | — | — | → `kapitalbasis_virtual_usd` (Engine-Fallback, nie Cent-Abgleich) |
| `Average3MonthProfit` | Root-Seite | `avgMonthPct` | **hergeleitet**: Yield% ÷ Laufzeit (`:412–418`) | **gemessen** 30-Tage (`:321`) | **hergeleitet**: ROI ÷ Laufzeit | → `monthly_growth_pct` (Zusatzinfo; maßgeblich ist eigene geom. Rendite) |
| `Weeks` | — (Katalog hat Alter nicht) | null statt 0 bei unbekanntem Inception (B5, `:65–68`) | null-fähig | `(int) s.wochen()` — **nie null** | `t.getWeeks()` | Katalog `weeks` → Wochen-Vorfilter (None = durchlassen) |
| Subscriber-Historie | DB-Events (`/history`, `/events`) | kopierer.db, weekChange/monthChange | Members-API | kopierer.db Tages-Snapshots | **keine** (history ehrlich leer) | `history()` → Abonnenten-Verlauf/Monitor |

Konstellations-Risiko: Liefert künftig eine Quelle einen Closing-/Balance-DD
unter dem Namen `EquityDrawdown` (Szenario E04), übernimmt ihn der Hub
unkritisch als EQ-DD. Heute korrekt je Produzent dokumentiert — aber nichts
prüft die Semantik zur Laufzeit. Fix-Vorschlag: je Version ein
`ddSemantics`-Feld („equity_peak“/„balance“) im metrics-Contract ergänzen und
im Hub validieren; bis dahin Kontrasttest gegen `TradeEqDrawdownPct` loggen.

**H2e [P3, GRENZE] — Versionen sind korrekt getrennt.**
Jeder JavaFX-Monitor akzeptiert NUR sein Kürzel (Pelican `:208–212` 404
„Unbekannte Version“); MqlDownloader normalisiert mql4/mt4/mt5→mql5
(`ProviderFiles.normalizeVersionFolder`, `RestApiServer.java:773–776`).
Hub `platform_version()` (`downloader_client.py:69–86`) mappt die Richtung.
Keine Gleichsetzung gefunden — Vorgabe eingehalten.

**H2f [P3, GRENZE] — health-Ausnahmen.**
Health liefert überall status/instance/tokenRequired; bei Pelican zählt
`providers` nur Copier>0 (`:244–245`). Kein Server wirft in health (Fehler →
500-JSON-Körper, z. B. Pelican `:169–171`); MqlDownloader loggt zusätzlich
(`:162`). Anmerkung: `providers` ist bei MqlDownloader die DB-Statistik-Zahl
(mql4+mql5-Summe), bei den Monitoren aktive Provider — Zahl ist nicht
gleichbedeutend. Nur informativ.

### H3 — Log-Cluster

**Tabelle H3-1 — Cluster mit Status:**

| # | Projekt | Cluster (Muster) | Anzahl | Erster/Letzter | Status | Code-/Fix-Verweis |
|---|---|---|---|---|---|---|
| K1 | Scanner | `ValueError: '9,10'` (GS MT5 #2375480) | 4 | 04.10 10:30 (L4587–4610) | **historisch-behoben** — Fix 85dc290 (04.10 10:57), kein Treffer danach (Log bis 12:46); Regressionstest `test_quellen_stringzahlen.py::test_metrics_zu_stats_parsst_komma_strings` | `ingest._zahl` |
| K2 | Scanner | MT5-Export `Pflichtfeld fehlt (Buy)` Zeile 9220, Signal 840474 (+2268766) | 8 FEHLER + 54 Retry-Meldungen | 29.09 00:04 – 02.10 01:42 | **GRENZE (bewusst lauter Fehler)** — Signal 840474 fällt dadurch dauerhaft aus der Forensik; Zeile 9220 des Exports nie inspiziert | `parser.py`-Artefaktregeln; AGENTS „Inhalt ohne Typ bleibt lauter Fehler“ |
| K3 | Scanner | Downloader-Abgleich: URL-Divergenz + ConnectionError-Abbruch | je 1 | 04.10 12:46 | **aktuell (Betriebsproblem)** — Folge von H1b + Divergenz Setting 192.168.178.164 vs. Quelle localhost:8089 | `downloader_sync` (B9-Warnung arbeitet korrekt) |
| K4 | vantage | `10402 err_invalid_param` topLists type=2/3/4 | 24 | 27.09 15:29 – 04.10 10:23 | **aktuell-reproduzierbar, ungeklärt** (API lehnt 3 der Kategorien ab; Katalog läuft über andere Pfade weiter) | `vantagemonitor` topLists-Download |
| K5 | roboforex | Plattform „rst“ (R StocksTrader) keine Deal-Historie | 3 | 26.09 22:28–22:48 | **erwartbare Grenze** (Members-API nur MT4/MT5; FEHLER je Signal, sauber begründet) | RoboMonitor Members-API |
| K6 | zulu | HTTP 500 ZuluTrade trades/history (CentaFX1 u. a.) + „kein gültiger Trade in Seite 0“ | 61/15 FEHLER | 25.09 12:04 – 26.09 11:53 | **erwartbare Grenze (Anbieter-Seite)**; Monitor seit 28.09. nicht mehr gelaufen (Log-Ende) | ZuluTradeClient |
| K7 | zulu | LLM `finish_reason=length` Bericht verworfen | 1 | 25.09 22:47 | **GRENZE** — bewusst nicht gespeichert, Hinweis „Ausgabelimit erhöhen“ | `GlmClient$LlmException` |
| K8 | PWL | Session abgelaufen (HTTP 401) → Lauf pausiert | 30/31 WARN | 02.10 18:59 – 04.10 | **erwartbare Grenze** — Pausen-Konzept arbeitet (E25-Tests grün) | `ApiExceptions$SessionException` |
| K9 | PWL | `SQLITE_CONSTRAINT_FOREIGNKEY` — Lauf 1 abgebrochen | 1 | 02.10 21:38 | **ungeklärt** (einmalig; spätere Läufe liefen weiter) — Ursache nicht im Log | kopierer.db-Schreibpfad |
| K10 | MqlDownloader | `ChartDataExtractor: Keinen Datumsbereich aus MonthProfitProz, Fallback` | 402 | 04.10 10:26–10:27 (Konvertierungslauf) | **GRENZE** — bekannt, Fallback greift; mindert monthProfits-Metadaten-Qualität | `utils.ChartDataExtractor` |
| K11 | PelicanTrading | Live-Trading-Sync Session 401 | 2 | 01.10 19:23 | **erwartbare Grenze** — klare Nutzer-Anleitung im Log | ANLEITUNG_LOGIN.md |
| K12 | Robo/Vantage/Scanner | Schein-Cluster „500/502“ | 168/3/4 | — | **Widerlegt** (s. Abschnitt 2) — „500 Tage“, „503 Zeilen“, „13.500 Zeichen“ | — |

### H4 — Archiv waste/ (Index, keine Neu-Prüfung)

| Archiv | Thema (1 Zeile) |
|---|---|
| `codereview_2026-10-01/` | Fremd-Review Signalauswahl/KI-Bewertung: 4 schwere DD-Schranken-/Codefehler (F1–F9, K1–K3) mit Lauf-Audit-Skripten |
| `drawdown_2026-10-03/` | KiraCat-DD-Prüfung: 8,14 % nur Closed-Trade-DD auf virtueller Basis; H1-Reko ~20,4 % statt 44,34 % |
| `drawdown_3signale_2026-10-03/` | Drei reale DD-Nachrechnungen (GS MT4/Meridian/Night Scalper), GMT-Kalibrierung, Forensik v10; bericht.md + abschlusspruefung.md |
| `intensivreview_2026-09-29/` | Intensiv-Review des Full-Scans 29./30.09.: Befunde B1–B26 (u. a. Monitor-EQ-DD, Ertragsbasis, Dedup) |
| `laufreview_2026-10-02/` | Lauf-Review 02.10.: 13 bestätigte Befunde, Rechnungen korrekt/Workflow nicht (B24 RetDD toter Code, B25 Duplikate) |
| `retdd_equity_2026-10-03/` | RetDD-/EQ-DD-Kriterien-Review: Gewinn%/Monat + RetDD an gemessenen Equity-DD gebunden |
| `stop_erkennung_2026-10-02/` | Schutzsignaturen aus synchronisierten Closings (SL-Erkennung), Implementierung + Handoff |

### H5 — E-Szenario-Abdeckung (28 Szenarien → Tests)

**Tabelle H5-1 — Zuordnung (Testdatei::Testfunktion, jeweils repräsentativ):**

| Szenario | Abdeckung | Beleg |
|---|---|---|
| E01 MQL4-Orderbuch→Bericht | ✔ | `test_mql5_fail_fast.py::test_export_kinds_mt4_prefers_history`, `test_parser_export_artefakte.py`, `bericht_parse.py` |
| E02 MT5 ohne SL | ✔ | `test_review10_stop_gate.py`, `test_sl_prompt_evidenz.py`, `test_stop_befund_pipeline.py` |
| E03 je Quelle Export | ✔ | `test_quellen.py::test_{pelican,roboforex,vantage,zulumonitor}_ende_zu_ende_wird_akzeptiert` |
| E04 Closing-DD unter EQ-Feldname | ✘ | kein Test prüft Semantik von `EquityDrawdown`-Werten (nur Komma-Parsing `test_quellen_stringzahlen.py`) |
| E05 SHA/geänderte Metrics | ✔ | `test_quellen.py` (Cache/SHA), `test_doc10_ingestion.py`, `test_review17_ingestion.py` |
| E06 Quelle offline + Cache-SHA | ✔ | `test_laufreview2_fixes.py::test_b5_offline_cache_mit_falschem_sha_wird_abgelehnt` |
| E07 Cache-Poisoning | ✔ | `test_quellen.py::test_korrumpierte_{trades,metrics}_cachedatei_wird_neu_geschrieben` |
| E08 Snapshotbruch | ✔ | `test_quellen.py::test_cache_datei_wird_atomar_geschrieben` |
| E09 ID-Kollision | ✔ | `test_intensivreview_fixes.py` (R1), `test_external_review_db.py` (R3 Raise) |
| E10 Pfadtraversal | ✔ | MqlDownloader `tests/rest/RestApiServerTest.java:191` + `ingest._version_sicher` |
| E11 Login-HTML | ✔ | `test_mql5_fail_fast.py::test_is_hard_mql5_failure_detects_throttle_and_login_html` |
| E12 429/5xx-Serie | ✔ | `test_scan_retry.py`, `test_review_pipeline_fixes.py::test_exhausted_network_retry_marks_signal_and_continues` |
| E13 Crash zwischen Updates | ✔ | `test_review17_pipeline.py::test_retry_keeps_actual_first_write_when_second_write_fails` |
| E14 gleichzeitiger Download+REST | ✘ | keine Konkurrenz-Tests auf Java-Seite (kein Thread/Concurrent-Test in allen 5 RestApiServerTest) |
| E15 Fix-ID außerhalb Katalog | ✔ | `test_fix_signale.py::test_crawl_laedt_fehlende_fix_id_von_der_detailseite` |
| E16 Teilscan+offline | ✔ | `test_laufreview2_fixes.py` (B5/B12), `test_fix_signale.py::test_teilscan_ziel_ids_*` |
| E17 Version ändern | ✔ | `test_downloader_client.py::test_platform_version/test_versions_hilfe`, `test_agenten_phase_b.py::test_profil_versioniert_nie_ueberschrieben` |
| E18 Studie↔Produktscan | ✔ | `test_equity_studie.py` (7 Tests), `test_equity_zeitbasis_pipeline.py::test_studien_cache_verwendet_neue_methodikversion` |
| E19 GUI-Reload | ✔ | `test_agenten_tageskette.py::test_starte_komplettlauf_im_hintergrund`, `test_app.py` |
| E20 PID-Recycling | ◐ | `test_agenten_lock_und_scheduler.py::test_lock_mit_lebender_pid_blockiert_auch_ueber_stale` + PWL `AppLockTest`; Recycling (PID-Wiederverwendung durch Fremdprozess) ungetestet |
| E21 Monatsjob DST/Restart | ◐ | `test_agenten_phase_e.py::test_monatserster_werktag_full_scan_faellig`, `test_agenten_regression.py::test_fehlgeschlagener_scan_verbraucht_monat_nicht`; DST-Grenzfälle im Scheduler ungetestet |
| E22 LLM-Ausfall | ✔ | `test_agenten_phase_c.py::test_markt_fallback_ohne_llm`, `test_tiefen_batch.py`, `test_portfolio_step.py` |
| E23 Tradeserver Teilfehler | ✔ | `test_tradeserver_sync.py` (14 Tests inkl. Abbruch) |
| E24 REST stale | ✔ | `test_review_findings.py::test_a_same_second_error_marks_forensik_stale`, `test_rest_api.py` (forensikUpdatedAt) |
| E25 PWL-Resume | ✔ | PWL `CrawlServiceTest` (manuellesFortsetzen/stopNachSessionPause/budgetEndetMittenImSignal), `SessionWiederaufnahmeTest` |
| E26 Offline-Restart Suite | ✘ | kein Test: alle Quellen nach Neustart weg → Nur-Cache-Verhalten über die GESAMTE Kette |
| E27 fremder Portbesetzer | ✘ | kein Test/keine Skript-Logik (vgl. H1a) |
| E28 Drittwährung/USC/Demo | ✔ | `test_fx_rates.py`, `test_quellen.py` (BOM/FX/virtuelle Basis), zulu demo im Katalog; Java-Seite `WaehrungsUmrechnungTest` (PWL) |

**H5r [P2, BESTÄTIGT] — 5 wichtigste UNBEDECKTE Szenarien:**
1. **E04** Closing-/Balance-DD unter EQ-Feldname (Vertrags-Semantik, s. H2d) —
   ein falsch etikettierter DD bliebe unbemerkt in der Schranke.
2. **E14** gleichzeitiger Download + REST auf demselben Monitor (Java):
  HttpServer-Thread liest CSV/DB, während GUI-Download schreibt — keine
   Tests, keine Sichtbarkeit.
3. **E27** fremder Portbesetzer: taskkill tötet Unbeteiligte (H1a) — Verhalten
   weder getestet noch abgesichert.
4. **E26** Offline-Restart der Suite: alle 5 Quellen gleichzeitig weg
   (Startreihenfolge startall) → Hub-Verhalten über alle Quellen hinweg
   (B9 „Abbruch nur wenn KEINE Quelle antwortet“) nur implizit getestet.
5. **E21 (DST-Teil)** Monatsjob über DST-Wechsel/Neustart-Nachholung —
   Scheduler-Takte sind getestet, die DST-Grenze (02:00/03:00-Fenster) nicht.

### H6 — Sicherheits-Querschnitt

**H6a [BESTÄTIGT, positiv] — Keine Secrets in Git.**
`git ls-files` je Projekt: keine Cookies, Keys, .env, DBs getrackt.
SignalKiScanner: `.env` (GLM_API_KEY, MQL5_USER, MQL5_PASS — Namen geprüft,
Werte redigiert) via `.gitignore:2–4` ignoriert; `config/secrets.local.json`
(Z. 5–6) ebenso; `config/app_settings.json` ignoriert (Z. 45). Java-Monitore:
`data/` vollständig ignoriert (robo/vantage/zulu/PWL), Pelican ignoriert
Einzelpfade inkl. `data/config.json` (glmApiKey enthalten; per
`git check-ignore` verifiziert). MqlDownloader-Daten liegen außerhalb
(C:/Forex/MqlAnalyzer). Scanner `data/raw/*`-CSVs sind bewusste Testdaten
(AGENTS) — GRENZE, dokumentiert.

**H6b [P3, BESTÄTIGT] — PelicanTrading committet Provider-Daten unter data/.**
6 Dateien `data/the-holy-grail-2014074/*` (Trades/JSON) sind getrackt,
obwohl die eigene `.gitignore`-Kopfzeile „lokale Daten … NIEMALS committen“
sagt (die Datei listet nur andere Pfade). Keine Secrets, aber
provider-bezogene Handelsdaten im Repo-Historie. Fix: aus Git entfernen
(`git rm --cached`) und Verzeichnis ins .gitignore.

**H6c [P2, s. H2a/H2b] — Bind 0.0.0.0 + leeres Token-Default + Token-im-Query.**
Zusammenfassung siehe H2a/H2b; das ist der Sicherheits-Kernbefund des
Querschnitts. Kein weiteres Token-im-URL-Vorkommen im Hub-Code gefunden
(`downloader_client._headers` nur Header).

**H6d [P3, BESTÄTIGT] — Logs enthalten interne LAN-IP und Nutzernamen-Pfade.**
`scan_workflow.log` 04.10 12:46 nennt `http://192.168.178.164:8089` und
D:\…\Pfade — unkritisch, aber bei Weitergabe der Logs zu redigieren.
Kein Token/Passwort in irgendeinem Log gefunden (Stichproben + Muster).

**H6e [P3, GRENZE] — CORS `*` auf allen Quell-Servern.**
Pelican `RestApiServer.java:759–762`, MqlDownloader `:984` — mit leerem
Token (H2a) darf jede Webseite die REST-Daten lesen. Mit Token erlauben die
Header nur X-API-Token (Preflight schützt). Fix: Access-Control-Allow-Origin
auf explizite Origin oder Weglassen (Hub ist kein Browser-Client).

---

## 2) Widerlegte Verdachte

- **W1 — „startall.bat-Warteschleife hat Delayed-Expansion-Bug (%VERSUCH% statt
  !VERSUCH!)“**: widerlegt. `:warte` ist ein goto-Loop, keine Klammerblock —
  jede Zeile wird einzeln geparst, `%VERSUCH%` (L55) zählt korrekt hoch;
  `!errorlevel!` (L51) ist korrekt delayed. Kein Bug.
- **W2 — „Robo-Log zeigt 168 HTTP-5xx“**: widerlegt — Regex-Fehltreffer auf
  „OK … 500 Tage/502 Tage“-Erfolgszeilen; echte HTTP-5xx-Muster: 0 Treffer.
- **W3 — „Scanner-Log 4× HTTP 5xx“**: widerlegt — Treffer sind „13,500
  Zeichen“, „503 Zeilen (Cache)“.
- **W4 — „Vantage 92 Retry-Fehler“**: widerlegt — Treffer sind
  WebDriver-Initialisierungs-Versuche („Versuch 1 von 3“), keine
  Fehler-Loops.
- **W5 — „Pfadtraversal über reports/{datei} oder trades/file möglich“**:
  widerlegt (H2c): Listen-Filter + findByName-Prüfung + Test vorhanden.
- **W6 — „Hub gleicht mql4/mql5/pelican/vantage/zulu-Versionen falsch aus“**:
  widerlegt (H2e): Server weisen fremde Versionen mit 404 ab; Hub mappt
  korrekt.
- **W7 — „ValueError ‚9,10‘ noch aktuell“**: widerlegt — letzter Treffer
  04.10 10:30, Fix 85dc290 04.10 10:57, Log läuft ohne Wiederholung weiter
  (K1).

---

## 3) Offene Fragen (an Nutzer/Koordination)

1. **MqlDownloader über startall starten?** (H1b) — Swing-GUI; bewusst manuell
   oder per Startzeile? Daneben: Divergenz Setting `192.168.178.164:8089`
   vs. Datenquelle `localhost:8089` (K3) — welche Adresse ist gewollt?
2. **LAN-Freigabe der Monitore beabsichtigt?** (H2a) — Wenn ja: Token-Pflicht
   erzwingen; wenn nein: Default-Bind auf 127.0.0.1. Entscheidung nötig, bevor
   ein Fix-PR entsteht (betrifft 5 Projekte gleich).
3. **PWL FOREIGN-KEY-Abbruch 02.10 21:38** (K9) — einmalig; Ursache im
   kopierer.db-Schreibpfad klären (Paket mit PWL-Fokus)?
4. **Vantage topLists 10402** (K4) — Parameter type=2/3/4 von der
   Vantage-API überhaupt unterstützt? (API-Doku prüfen oder Kategorien aus
   der Konfiguration entfernen.)
5. **Signal 840474 Export-Zeile 9220** (K2) — einmalige CSV-Inspektion
   empfohlen (nur-lesend) zur Entscheidung, ob ein weiteres Artefakt-Muster
   in den Parser gehört.

---

## Anhang — Executive-Zusammenfassung

- P0: keiner.
- P1: H1a (taskkill ohne Identität), H1b (MqlDownloader fehlt in startall,
  live belegt), H2a (5× Bind 0.0.0.0 + Token-Default leer + CORS `*`).
- P2: H1c („Fertig“ prüft nur 8504; 8089 fehlt in Freigabe-Liste), H2b
  (?token=), H2d/H5r-E04 (DD-Feldsemantik ungeprüft), H5r (E14/E26/E27
  ungedeckt), K3 (Downloader-Abbruch im Betrieb).
- Positiv: Traversal überall geschützt (inkl. Test), Git-Ignores wirksam,
  9,10-Fix im Log bestätigt, Cache-Poisoning-/Offline-Pfade getestet.

Bericht: 366 Zeilen. Ende Paket H.
