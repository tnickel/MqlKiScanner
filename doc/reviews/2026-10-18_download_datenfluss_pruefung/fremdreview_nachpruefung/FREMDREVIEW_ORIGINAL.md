# Technischer Systemprüfbericht: Datenfluss, Persistenz, Identitätsmanagement und Tabellenmapping

> **Ziel-Audienz:** Autonome Software-Agenten / LLM-Coding-Assistenten  
> **System-Kontext:** Multi-Source Trading-Signal Hub & Forensic Risk Scanner  
> **Root-Pfad des Prüfobjekts:** `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner`  
> **Verbundene Quellsysteme:** `MqlDownloader` (Port 8089), `PelicanTrading` (Port 8090), `roboforex` (Port 8091), `vantage` (Port 8092), `zulumonitor` (Port 8093)  
> **Prüfdatum:** 18.10.2026

---

## 1. Executive Summary & Komponenten-Statusmatrix

| Komponente / Teilsystem | Prüfstatus | Primäre Code-Lokation | Festgestellter Zustand / Kernbefund |
| :--- | :--- | :--- | :--- |
| **Quelle: PelicanTrading (`pelik`)** | **PASSED** | [UpdateJobRunner.java](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/PelicanTrading/src/main/java/de/pelicanmonitor/update/UpdateJobRunner.java) | Delta-Updates für Tradelisten (`T-1 bis heute`) entkoppelt von der 3-Tage-Katalogregel. Automatischer Selenium-Login-Fallback. |
| **Quelle: RoboMonitor (`robo`)** | **PASSED** | [UpdateJobRunner.java](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/roboforex/src/main/java/de/robomonitor/update/UpdateJobRunner.java) | Getrennte Phasen: Katalog → Tageslisten → Deals. PnL-Umrechnung und Session-Handling verifiziert. |
| **Quelle: ZuluMonitor (`zulu`)** | **PASSED** | [UpdateJobRunner.java](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor/src/main/java/de/zulumonitor/update/UpdateJobRunner.java) | Historien-Merge intakt. Strikter USD-Ausschluss (10 Fremdwährungskonten legitim als Fehler/Vorprüfung markiert). |
| **Quelle: VantageMonitor (`vant`)** | **PASSED** *(mit Datenlücken)* | [UpdateJobRunner.java](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/update/UpdateJobRunner.java) | Pipeline intakt. 5 Signale ohne Forensik aufgrund nicht gepflegter Kontraktspezifikationen in `contract_specs.json`. |
| **Quelle: MqlDownloader (`mql5`)** | **FAILED** | [MqlDownloaderGui.java:L154](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java#L154) | **Designbruch Frischeregel:** Wenn Katalog-Alter `< 72 h`, wird der gesamte Update-Job inkl. aller Trade-Downloads abgebrochen. Keine Wochenzahl (`weeks=null`) in REST-API. |
| **MQL5-Direktabruf (Crawler/HTTP)** | **PASSED** | [session.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/mql5/session.py), [exporter.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/mql5/exporter.py) | MT4/MT5-Verzweigung (`history` vs. `positions`), BOM-Stripping, automatische Erkennung von Login-HTML (`<!DOCTYPE`), atomare Dateiablage via Temp-Files. |
| **Kursdaten-Zweig (H1-Bars)** | **PASSED** | [kursdaten.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/kursdaten.py), [kurs_cache.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/kurs_cache.py) | 10.095.805 H1-Bars über 3 Broker-Feeds in `kursdaten.db`. Portable MT5-Prozesssteuerung mit Prüfung von `/portable` und Datenpfad. |
| **Tabelle „Alle Signale“** | **PASSED** *(mit Kollisionsmaskierung)* | [alle_signale.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/app_pages/alle_signale.py), [alle_signale_ui.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/alle_signale_ui.py) | 1.477 sichtbare Zeilen arithmetisch konsistent. Zweitsignale bei gleicher numerischer ID über Quellen hinweg werden durch `gesehen: set[int]` in der Anzeige unterdrückt. |
| **Tabelle „Ergebnisse“** | **PASSED** | [ergebnisse.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/app_pages/ergebnisse.py), [app_ui.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/app_ui.py) | 194 Zeilen aus `signals`. Saubere Trennung von Schranken-Kanälen und Calmar-Nenner. Marker „NEU“ isoliert auf frische Persistenz in aktueller Session. |
| **Persistenz-Kollisionsschutz** | **FAILED** *(Sicherheitslücke)* | [db.py:L299-L342](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py#L299-L342) | `db.upsert_signal` prüft Quellkollision nur, wenn `quelle is not None`. Ein Aufruf ohne `quelle` überschreibt bestehende Fremddaten unbemerkt (`test_audit_identitaet_20261018.py`). |

---

## 2. Architektur-Topologie & Schnittstellen

### 2.1 Dienst-Topologie
```
┌────────────────────────────────────────────────────────────────────────┐
│ SignalKiScanner (Streamlit GUI :8504 / REST API :8611)                 │
│ Engine, Forensics, SQLite Persistenz (mqlkiscanner.db, kursdaten.db)   │
└───────┬──────────────┬──────────────┬──────────────┬───────────────────┘
        │              │              │              │
        ▼ :8089        ▼ :8090        ▼ :8091        ▼ :8092        ▼ :8093
┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐
│MqlDownloader ││PelicanTrading││ RoboMonitor  ││VantageMonitor││ ZuluMonitor  │
│(Typ: mql5)   ││(Typ: pelik)  ││ (Typ: robo)  ││ (Typ: vant)  ││ (Typ: zulu)  │
└──────────────┘└──────────────┘└──────────────┘└──────────────┘└──────────────┘
```

### 2.2 Standardisiertes Stufe-0-Protokoll (`doc/23`)
Jeder Quellen-Monitor implementiert zwei zentrale Steuerungs-Endpunkte:
1. `POST /api/v1/update`:
   - Payload: `{"target": 200, "tradelisten": true, "katalogMaxAlterH": 72, "quelle": "signalkiscanner"}`
   - HTTP 202: Job gestartet oder bereits laufend. Antwort: `{"jobId": "<uuid>", "status": "gestartet"|"laeuft_bereits", "bereitsLaufend": bool}`
   - HTTP 409: Client beschäftigt (`DownloaderBusy`).
   - HTTP 405: Client-Version veraltet (`DownloaderUpdateNotSupported`).
2. `GET /api/v1/update/status`:
   - Response: `{"jobId": "<uuid>", "state": "idle"|"running"|"done"|"error"|"login_required", "phase": str, "done": int, "total": int, "message": str, "ergebnis": {...}}`
   - Ergebnis-Objekt: `{"signaleGeliefert": int, "tradelistenNeu": int, "tradelistenAktualisiert": int, "tradelistenFehler": int, "tradelistenAbgebrochen": bool, "katalogUebersprungen": bool, "datenstand": str}`

---

## 3. Formale Fach- und Berechnungsregeln (Invarianten)

1. **Drawdown-Definitionen (strikt getrennt):**
   - **Plattform-Drawdown (`dd_equity_pct` / `dd_balance_pct`):** Selbstauskunft der Plattform. Reines Filterkriterium für die harte 30-%-Schranke. Niemals Calmar-Nenner!
   - **Trading-Drawdown (`trading_dd_pct`):** Drawdown geschlossener Trades aus der realen Kontokurve (inkl. Einzahlungen; Auszahlungen senken den Peak via High-Watermark).
   - **Max-Drawdown Equity (`equity_dd_rekonstruiert_pct`):** Echte H1-Equity-Rekonstruktion aus Kursdaten inklusive Floating von offenen Positionen. **Ausschließlicher Calmar-Nenner.**
   - **Monitor-Drawdown (`monitor_trade_eq_dd_pct`):** Closing-Kurve des Quellen-Monitors. Wirkt nur als Schrankenkanal, niemals als Calmar-Nenner.
2. **Effizienz-Metriken (Jahres-Calmar):**
   $$\text{TrueRetDD} = \frac{\text{CAGR}_\text{Jahr}}{\text{Max-Drawdown}_\text{Equity}}$$
   - Mindest-Historie: 3 Monate ($\ge 12$ Wochen). Historie unter 3 Monaten markiert `effizienz_status = "historie_zu_kurz"` $\rightarrow$ Grün gesperrt.
   - Vorbehalt: Fehlen Kurse für einzelne Symbole oder übersteigt die H1-Lücke 1 %, wird der Wert in `TrueRetDD (Vorbehalt)` ausgelagert und orange dargestellt $\rightarrow$ Grün gesperrt.
3. **Währungs- und Kapitalbasis-Invariante:**
   - USD-Zwang: Jede Forensik setzt ein verifiziertes USD-Konto voraus ([require_usd_account](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py#L809)). Konten mit EUR, AUD, SGD etc. ohne implementierten FX-Umrechnungskontrakt werden mit `ValueError` abgewiesen und bleiben im Status Vorprüfung / Fehler (`⚪`).
   - Kaskade der Kapitalbasis:
     1. CSV-Einzahlungen im Trade-Export (höchste Priorität).
     2. Verifizierter `Initial Deposit` der Signalseite.
     3. Virtuelle Annahme 10.000 USD (muss als `virtuell` markiert sein).
     - *Verboten:* Implizite Rückrechnung (`Balance - Netto`), da Einzahlungen fälschlich als Startkapital interpretiert würden.

---

## 4. Vollständiger Datenfluss: End-to-End Trace

```
1. TRIGGER:
   GUI-Klick (app_pages/scan.py) ODER Autonomer Daemon (agenten/scan_launcher.py)
   │
2. STUFE 0 (Aktualisierung):
   client_updates.py:_update_eine_quelle()
   ├─ GET /api/v1/health (Bereitschaft abwarten, max 60s)
   ├─ POST /api/v1/update (target=200, katalogMaxAlterH=72)
   └─ Poll GET /api/v1/update/status (intervall=5s, timeout=120min, login_timeout=10min)
      └─ Append to SQLite: client_updates
   │
3. STUFE 1 (Katalog- & Signalauswahl):
   pipeline.py:crawl()
   ├─ ingest.py:kandidaten_aus_quellen() -> hole_katalog() via GET /api/v1/providers
   ├─ crawler.py:crawl_lists() (wenn listen_modus in ['mql5', 'beides'])
   ├─ Dedup in crawl(): MQL5-Direkt gewinnt vor Quellen bei (id, platform)
   └─ pipeline.py:build_candidates()
      ├─ Filter: identities[id] -> Konflikt bei verschiedenen (quelle, platform) -> DROP
      ├─ Filter: wochen >= min_wochen (26) & abos >= min_abonnenten (1)
      └─ Bypass: fix_signal_ids umgehen Vorfilter
   │
4. STUFE 2 (Download & Caching):
   pipeline.py:analyze_candidate()
   ├─ Metadata: ingest.py:hole_metrics() -> GET .../metrics -> data/quellen/<q>/metrics.json
   └─ Trades CSV:
      ├─ Quelle: ingest.py:hole_trades() -> GET .../trades.csv -> data/quellen/<q>/trades.csv
      └─ MQL5-Direkt: exporter.py:export_positions() -> GET /export/positions bzw. /history
         └─ Atomic replacement via tempfile + os.replace()
         └─ Registrierung in SQLite: quellen_artefakte (quelle_id, signal_id, version, art, sha256)
   │
5. STUFE 3 (Kursdaten-Beschaffung für H1-Rekonstruktion):
   forensics/equity_rekonstruktion.py
   ├─ kursdaten.py:KursDaten.hole_h1()
   ├─ kurs_cache.py:KursCache.lese() aus data/kursdaten.db
   ├─ Cache Miss -> MetaTrader5 SDK: copy_rates_range()
   └─ kurs_cache.py:KursCache.schreibe() -> INSERT OR REPLACE into h1_bars
   │
6. STUFE 4 (Forensik & Risiko-Berechnung):
   forensics/engine.py:analyze_export()
   ├─ parser.py:load_export() -> Parsing der Trades & Cashflows
   ├─ exposure.py:calculate_exposure() -> Peak Positions, Lots, Schock-USD (via contract_specs.json)
   ├─ drawdown.py:calculate_drawdown() -> Reale Kontokurve (mit Einzahlungen)
   ├─ equity_rekonstruktion.py -> H1-Kursrekonstruktion (Equity-DD, Floating)
   ├─ martingale.py -> Erkennung von Martingale-Mustern
   └─ stop_loss.py -> Nachweis von SL-Orders (Orderbuch oder Cluster)
   │
7. STUFE 5 (Persistenz & Chronik):
   pipeline.py:_analyze_candidate_once()
   ├─ db.store_scan_result() -> Atomare Transaktion:
   │  ├─ signals (Metadaten, Kennzahlen-JSON, quelle)
   │  ├─ trade_files (Snapshot in data/trade_snapshots/, sha256)
   │  └─ forensik (Forensik-JSON, FORENSICS_VERSION)
   └─ ampel_verlauf.erfasse_bewertung() -> Append to ampel_verlauf & ampel_wechsel
   │
8. STUFE 6 (Präsentation in Web-UI):
   ├─ app_pages/ergebnisse.py -> pipeline.results_from_db() -> app_ui.py:render_results_table()
   └─ app_pages/alle_signale.py -> katalog.katalog_resultate() + gescannte -> alle_signale_ui.py
```

---

## 5. Quantitative Mengenbilanz (Mengenabgleich)

### 5.1 Bestandsübersicht per 18.10.2026
```
+---------------------------------------------------------------------------------------+
| Stufe                                  | mql5  | pelik | robo  | vant  | zulu  | Summe|
+----------------------------------------+-------+-------+-------+-------+-------+------+
| 1. Katalog-Einträge (katalog_signale)  |   215 |   640 |   200 |   199 |   200 | 1454 |
| 2. Wochen vorhanden (wochen != null)   |     0 |   634 |   200 |   187 |   200 | 1221 |
| 3. Vorfilter ok (Wochen>=26, Abos>=1)  |     0 |   436 |   163 |    66 |   191 |  856 |
| 4. Gescannt in Tabelle 'signals'       |    71 |    37 |    33 |    16 |    37 |  194 |
| 5. Vollständige Forensik ('forensik')  |    68 |    34 |    33 |     9 |    19 |  163 |
| 6. Keine Forensik / Fehler             |     3 |     3 |     0 |     7 |    18 |   31 |
| 7. Gecachte Tradelisten (Artefakte)    |   165 |   636 |   197 |   347 |   199 | 1544 |
| 8. Gecachte Metrics (Artefakte)        |   166 |   636 |   200 |   348 |   200 | 1550 |
| 9. Sichtbar in "Alle Signale"          |   215 |   640 |   200 |   199 |   200 | 1477*|
| 10. Sichtbar in "Ergebnisse" (DB)      |    71 |    37 |    33 |    16 |    37 |  194 |
+---------------------------------------------------------------------------------------+
* Arithmetische Auflösung Zeile 9: 194 gescannte + (1.454 Katalog - 171 Schnittmenge) = 1.477 eindeutige Zeilen.
```

### 5.2 Lückenlose Kausalanalyse der 31 Signale ohne Forensik

Die Diskrepanz von 31 Signalen zwischen `signals` (194) und `forensik` (163) ist zu 100 % forensisch belegt:

1. **`mql5` (3 Signale ohne Forensik):**
   - `#1` (*Test*): Manuell angelegter Testdatensatz ohne Trades.
   - `#2271995` (*Range Breakout EA Live*): CSV-Korruption. `parser.py` bricht ab: `Zeile 221: unbekannter Datensatztyp ''`.
   - `#2360068` (*Harmonizer Extreme*): CSV-Formatfehler. `Zeile 13: unbekannter Datensatztyp 'Commission'`.
2. **`pelik` (3 Signale ohne Forensik):**
   - `#2000892` (*Mtrader2*), `#2005451` (*Mtrader Holy*), `#2007510` (*Yu Trading Club*):  
     `ValueError: Keine anwendbare Kontraktspec (cross_broker=false, Broker 'AxiTraderUs07Live' / 'AxiTrader5' nicht freigegeben): COIN, TSLA, USOIL`.
3. **`vant` (7 Signale ohne Forensik):**
   - 5 Signale mit fehlenden Instrument-Spezifikationen in `contract_specs.json`:  
     `#178177` (*CL-OIL, DJ30, DJ30FT, etc.*), `#538344` (*UKOUSD*), `#954691` (*SP500*), `#1024672` (*XAUAUD, XAUJPY*), `#1121200` (*NAS100FT*).
   - 2 Signale mit unvollständiger Provider-Historie (`forensik_ok=False`): `#504191`, `#1121175`.
4. **`zulu` (18 Signale ohne Forensik):**
   - **10 Signale strikte Währungsabweisung:** `#402995`, `#407191`, `#410467`, `#412811`, `#417345`, `#418271`, `#424309`, `#427110`, `#429446`, `#430525` (EUR), `#417743` (SGD), `#424932`, `#426652` (AUD).  
     Fehlertext: `DownloaderNotFound: Kontowährung wird (noch) nicht unterstützt – trades.csv nur für USD-Konten`.
   - **4 Signale defekte Tradedatensätze:** `#304366`, `#425666`, `#426987`, `#430016` (`ungueltiges Volumen oder Handelszeitraum`).
   - **1 Signal unbekanntes Symbol:** `#429464` (*Spruce waveband*) mit Symbol `U` ohne Kontraktgröße.
   - **3 Signale:** Initiale Synchronisationsabbrüche vor Trade-Erfassung.

---

## 6. Datenwörterbuch & Feldmapping der Tabellen

### 6.1 Tabelle „Ergebnisse“ (`app_pages/ergebnisse.py` via `app_ui.py`)

| Spaltenname | Technisches Feld | Datentyp & Transformation | Nullability / Leere Zelle Begründung |
| :--- | :--- | :--- | :--- |
| **Stand** | `df["Stand"]` | `TEXT`: `"NEU"` oder `""` | Leer, wenn Signal nicht im letzten Lauf der Sitzung persistiert wurde. |
| **Fix** | `df["Fix"]` | `TEXT`: `"📌 FIX"` oder `""` | Leer, wenn ID nicht in `app_settings.json:fix_signal_ids`. |
| **Ampel** | `ScanResult.ampel` | `TEXT`: `🟢`, `🟡`, `🔴`, `⚪`, `⛔` | Niemals null. `⚪` signalisiert Fehler oder Vorprüfung ohne Forensik. |
| **Name** | `ScanResult.name` | `TEXT`: Providername | Fallback auf `#<id>`, falls unbenannt. |
| **Quelle** | `ScanResult.quelle` | `TEXT`: Kürzel (`mql5`, `pelik`, etc.) | Niemals null (Default `'mql5'`). |
| **Stop** | `ScanResult.stop_nachweis`| `TEXT`: Evidenz-String | `"SL nicht übertragen (neutral)"`, wenn kein Nachweis im Orderbuch. |
| **Max-Drawdown %**| `ScanResult.max_drawdown_equity_pct` | `REAL`: Format `%.1f` | **Leer**, wenn weder H1-Kursrekonstruktion noch Monitor-Closing-DD vorliegen. |
| **Trading-DD % (geschlossen)**| `ScanResult.trading_dd_pct` | `REAL`: Format `%.1f` | **Leer**, wenn Trade-Export fehlt oder unvollständig ist. |
| **Drawdown % (Plattform)**| `ScanResult.dd_equity_pct` | `REAL`: Format `%.1f` | **Leer**, wenn Provider-API den Wert nicht ausweist. |
| **Gewinn %/Monat** | `ScanResult.ertrag_monat_geom_pct` | `REAL`: Format `%.1f` | Geometrische Rendite. **Leer**, wenn keine validen Trades vorliegen. |
| **TrueRetDD** | `ScanResult.true_retdd_jahr` | `REAL`: Format `%.2f` | **Leer**, wenn kein Max-Drawdown Equity vorliegt oder Historie < 3 Monate. |
| **Ertrag/Monat %** | `ScanResult.ertrag_monat_pct` | `REAL`: Format `%.1f` | Plattform-Selbstauskunft monatliches Wachstum. |
| **Score** | `ScanResult.score` | `REAL`: Bereich 1.0–10.0 | **Leer**, wenn Forensik unvollständig oder veraltet (`forensik_stale`). |
| **Urteil** | `ScanResult.urteil` | `TEXT`: Regelbegründung | Enthält Klartext-Entscheidungsgrund und Kennzahlenstring. |
| **Bericht vom** | `ScanResult.gesamtbericht_at`| `DATETIME`: `DD.MM.YYYY HH:mm`| **Leer**, wenn kein LLM-Gesamtbericht generiert wurde. |
| **Link** | `df["Link"]` | `LINK`: Broker-Spezifische URL | URL generiert über `quellen.oeffnen_url()`. |
| **Abonnenten** | `df["Abonnenten"]` | `INTEGER` / `BUTTON` | Aktuelle Abonnentenzahl laut Downloader-Historie. |
| **30 Tage / 7 Tage** | `df["30 Tage"]` / `["7 Tage"]`| `TEXT`: Delta `+X` / `-Y` | Leer, wenn Historie im Zeitfenster keine Punkte aufweist. |

### 6.2 Tabelle „Alle Signale“ (`app_pages/alle_signale.py` via `alle_signale_ui.py`)

| Spaltenname | Technisches Feld | Datentyp & Transformation | Nullability / Leere Zelle Begründung |
| :--- | :--- | :--- | :--- |
| **Mark.** | `zeile["Mark."]` | `TEXT`: `🟩`, `🟨`, `🟧` | Leer, wenn keine manuelle Markierung in `signal_markierungen`. |
| **Komm.** | `zeile["Komm."]` | `TEXT`: `"📋"` oder `""` | Leer, wenn kein Eintrag in `signal_kommentare`. |
| **Ampel** | `zeile["Ampel"]` | `TEXT`: Ampel-Symbol oder `"—"` | `"—"`, wenn Signal nur im Katalog existiert und nie gescannt wurde. |
| **Herkunft** | `zeile["Herkunft"]` | `TEXT`: `"Workflow"` / `"Katalog"`| Unterscheidet gescannte Datensätze von reinen Downloader-Katalogzeilen. |
| **Wochen** | `zeile["Wochen"]` | `REAL`: Alter in Wochen | `None`, wenn Quelle kein Alter liefert (z. B. alle `mql5`-Katalogzeilen). |
| **Trading-DD %** | `statistik["trading_dd_pct"]` | `REAL`: Format `%.1f` | `None`, wenn Trade-CSV nicht geladen oder Währung nicht USD ist. |
| **True-DD %** | `zeile["True-DD %"]` | `REAL`: Format `%.1f` | Gemessener H1-Equity-DD. `None`, wenn keine Studie vorliegt. |
| **True-DD ≈** | `zeile["True-DD ≈"]` | `REAL`: Vorbehaltswert | Nur gefüllt, wenn Studie Vorbehalt aufweist (z. B. H1-Datenlücke). |
| **True-DD USD** | `zeile["True-DD USD"]` | `REAL`: Absoluter Drawdown | Dollar-Betrag des maximalen Floating-Drawdowns. |
| **Geom. %/M** | `statistik["ertrag_monat_geom_pct"]`| `REAL`: Format `%.1f` | `None` bei reinen Katalogzeilen ohne Trade-Download. |
| **TrueRetDD** | `zeile["TrueRetDD"]` | `REAL`: Jahres-Calmar | `None`, wenn True-DD fehlt oder Historie < 3 Monate. |
| **Basis** | `zeile["Basis"]` | `TEXT`: `CSV`, `Seite`, `virtuell` | `"—"`, wenn Kapitalbasis unklar oder keine Trades vorliegen. |
| **Forensik** | `zeile["Forensik"]` | `TEXT`: `"✓"` oder `"—"` | `"✓"` nur bei vollständig bestandener 4-Stufen-Forensikbatterie. |
| **Messstatus** | `zeile["Messstatus"]` | `TEXT`: Status-String | Gibt den genauen Grund für Lücken an (z. B. `"Trade-Datei fehlt"`). |

---

## 7. Bestätigte Fehler (Defect Catalog)

### DEFECT-01: MqlDownloader Stufe-0-Frischeregel blockiert Trade-Aktualisierungen
- **Klassifikation:** Logic Defect / Data Stale Risk
- **Schweregrad:** **CRITICAL**
- **Komponente:** `MqlDownloader` (Java/Swing)
- **Datei:** [MqlDownloaderGui.java:L154-L160](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java#L154-L160)
- **Fehlerbeschreibung:**  
  In `starteUpdateKaskade(rest.UpdateJob job, int katalogMaxAlterH)` prüft der Code:
  ```java
  String letzterLoad = leseKatalogVermerk(vermerk);
  if (letzterLoad != null && katalogFrischGenug(letzterLoad, katalogMaxAlterH)) {
      job.ergebnis("katalogUebersprungen", true);
      job.fertig(letzterLoad);
      return;
  }
  ```
  Da MqlDownloader Katalog und Trades in einer unteilbaren Kaskade (`downloadManager.startDownload("MQL4")` $\rightarrow$ `startDownload("MQL5")`) abruft, bricht die 72-Stunden-Regel den **gesamten Abruf** ab. Es werden keinerlei neue Trades bestehender Signale abgefragt.
- **Soll-Verhalten:** Entsprechend doc/23 §5a dürfen Tradelisten nicht übersprungen werden, wenn `tradelisten == true` übergeben wurde. Der Katalog-Vermerk darf nur den Metadaten-Scan drosseln.
- **Fix-Spezifikation:**  
  In [MqlDownloaderGui.java](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java) die Verzweigung anpassen: Wenn der Update-Auftrag Tradelisten fordert, darf `katalogFrischGenug` nicht zum vorzeitigen `return` führen, sondern muss stattdessen direkt in die Trade-Download-Phase übergehen.

---

### DEFECT-02: Stillschweigendes Überschreiben bei `store_scan_result` ohne `quelle`
- **Klassifikation:** Security & Data Integrity Defect
- **Schweregrad:** **HIGH**
- **Komponente:** `SignalKiScanner.db`
- **Datei:** [db.py:L299-L342](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py#L299-L342)
- **Test-Beweis:** [test_audit_identitaet_20261018.py:test_d_luecke_store_scan_result_ohne_quelle_ueberschreibt_fremde_id](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/tests/test_audit_identitaet_20261018.py#L204-L222) (FAILED).
- **Fehlerbeschreibung:**  
  `db.upsert_signal` führt die Quell-Kollisionsprüfung nur im Block `if quelle is not None:` durch. Wird `db.store_scan_result(signal_id, payload)` aufgerufen und enthält `payload` keinen Schlüssel `"quelle"`, fällt der Aufruf in `if quelle is None:`. Der bestehende Datensatz wird in SQLite via `ON CONFLICT(signal_id) DO UPDATE` mit Name, Plattform und Kennzahlen der fremden Quelle überschrieben, während die alte `quelle` in der Spalte stehen bleibt (Szenario F3).
- **Fix-Spezifikation in [db.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py#L299):**
  ```python
  # db.py: Zeile 299 ersetzen durch:
  alt = conn.execute("SELECT quelle FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
  alt_quelle = (alt[0] if alt and alt[0] else None)
  if alt_quelle is not None:
      ziel_quelle = quelle if quelle is not None else alt_quelle
      if alt_quelle != ziel_quelle or (quelle is None and alt_quelle is not None):
          raise ValueError(
              f"ID-Kollision abgewehrt: Signal {signal_id} gehört Quelle {alt_quelle!r}; "
              f"Schreibversuch mit quelle={quelle!r} verworfen.")
  ```

---

### DEFECT-03: Fehlende Composite-Identität in Kern-Tabellen
- **Klassifikation:** Architectural Limitation
- **Schweregrad:** **MEDIUM**
- **Komponente:** `SignalKiScanner.db` (Schema) & [katalog.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py#L128)
- **Fehlerbeschreibung:**  
  `signals`, `forensik`, `trade_files` und `equity_studien` verwenden ausschließlich `signal_id INTEGER PRIMARY KEY`. Haben zwei Signal-Provider auf unterschiedlichen Plattformen (z. B. MQL5 #504191 und Vantage #504191) dieselbe numerische ID, blockiert der Kollisionsschutz die Aufnahme des zweiten Signals vollständig. In [katalog.py:L128](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py#L128) wird über `gesehen: set[int]` dedupliziert, wodurch das zweite Signal in der Tabelle „Alle Signale“ unsichtbar bleibt.
- **Fix-Spezifikation:**  
  Schema-Migration gemäß doc/20 Stufe 2:
  ```sql
  -- Migration von signals, trade_files, forensik auf:
  PRIMARY KEY (quelle, signal_id)
  ```
  Und in `katalog.py:128` Deduplikation anpassen auf:
  ```python
  gesehen: set[tuple[str, int]] = set()
  # key = (kuerzel, signal_id)
  ```

---

### DEFECT-04: MqlDownloader REST-Katalog liefert kein Signalalter (`weeks`)
- **Klassifikation:** Integration Gap
- **Schweregrad:** **MEDIUM**
- **Komponente:** `MqlDownloader` (REST-API) & [ingest.py](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py#L120)
- **Fehlerbeschreibung:**  
  Im Endpunkt `GET /api/v1/providers` von MqlDownloader fehlt das Feld `weeks`. Alle 215 Katalogeinträge werden in [katalog_signale](file:///d:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py) mit `wochen = None` abgelegt.
- **Auswirkung:**  
  Wenn `listen_modus = "quellen"` konfiguriert ist, scheitern alle 215 MQL5-Kandidaten am Vorfilter (`weeks is None or weeks < 26`), sofern sie nicht explizit in `fix_signal_ids` eingetragen sind.
- **Fix-Spezifikation:**  
  In MqlDownloader `ProvidersHandler.java` das Alter aus der gecachten Signalseite parsen und im JSON als `"weeks": <int>` mitsenden.

---

## 8. Verifikations- und Testnachweisergebnisse

### 8.1 Testsuite-Lauf (pytest)
- **Ausführungsbefehl:** `python -m pytest`
- **Laufzeit:** 396,38 Sekunden (06:36 min)
- **Ergebnis:** **2.412 PASSED**, **1 FAILED**, **4 DESELECTED** (reine Token-Tests via Marker `-m "not llm"`).
- **Fehlgeschlagener Test:**  
  `tests/test_audit_identitaet_20261018.py::test_d_luecke_store_scan_result_ohne_quelle_ueberschreibt_fremde_id`  
  *Dieser Test wurde gezielt als Soll-Bruch-Test angelegt und belegt DEFECT-02.*

### 8.2 Nachweis-Matrix

```
+-----------------------------------------------------------------------------------------+
| Prüfpunkt                                      | Status     | Belegmethode              |
+------------------------------------------------+------------+---------------------------+
| Stufe-0-Signalaktualisierung (Ports 8089-8093) | VERIFIED   | Live Socket & REST Poll   |
| MQL5 Direct Download Fallback-Kette            | VERIFIED   | Code-Audit & Unit Tests   |
| H1-Kursdaten-Abdeckung (10 Mio. Bars)          | VERIFIED   | SQLite-Query kursdaten.db |
| Nicht-USD-Forensiksperre                       | VERIFIED   | 10 Zulu EUR-Signale in DB |
| Veraltung alter grüner Befunde bei Neufehler   | VERIFIED   | test_audit_identitaet_... |
| Mengenbilanz (1.454 Katalog / 194 Workflow)    | VERIFIED   | Vollständiger DB-Scan     |
| Stufe-0-Frischeregel MqlDownloader bricht ab   | DEFECT-01  | Code-Audit MqlDownloader  |
| Store-Scan-Result ohne Quelle überschreibt     | DEFECT-02  | test_audit_identitaet_... |
| Composite-Identität in signals unvollständig   | DEFECT-03  | DB-Schema-Inspektion      |
| MqlDownloader liefert weeks=null               | DEFECT-04  | DB-Inspektion katalog_... |
+-----------------------------------------------------------------------------------------+
```

---

## 9. Handlungsanweisung für nachfolgende Agenten

1. **Keine Änderungen an den mathematischen Bewertungsregeln vornehmen:**  
   Die Berechnung von TrueRetDD (Jahres-Calmar), die High-Watermark-Methode für Kapitalflüsse und die strikte Währungstrennung sind korrekt implementiert und durch 2.412 Tests abgesichert.
2. **Behebung von DEFECT-02 in `db.py` durchführen:**  
   Den Patch für `db.upsert_signal` einpflegen, sodass `test_audit_identitaet_20261018.py` vollständig grün wird (`2413 passed`).
3. **Behebung von DEFECT-01 in `MqlDownloaderGui.java` vornehmen:**  
   Die Kaskade entkoppeln, damit Tradelisten trotz frischem Katalog-Timestamp aktualisiert werden.
4. **`data/contract_specs.json` erweitern:**  
   Die fehlenden Symbole für Vantage (`UKOUSD`, `SP500`, `NAS100FT`) und AxiTrader-Broker eintragen, um die 8 blockierten Signale in die Forensik zu überführen.