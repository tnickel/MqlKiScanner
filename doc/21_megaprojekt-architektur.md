# 21 — Megaprojekt-Architektur: Signal-Kette von der Quelle bis zum Monitor

Stand: 04.10.2026. Diese Seite ist die **Gesamtdokumentation des Megaprojekts**
im Workspace `SIGNALDOWNLOADER` — der SignalKiScanner als Multi-Source-Hub,
fünf Datenquellen per REST angebunden, das spezialisierte Analyse-Tool
`PelicanWinnerLooser` für Kopierkonten-Verteilungsforensik, sowie zwei nachgelagerte
Konsumenten (`MqlTradeMonitor` und `MqlRealmonitor`).

Detail-Doku der Quellen: doc/20 (Multi-Source-Hub, §4a–d); je Projekt existiert
eine eigene README.

---

## 1. Das Bild

```
5 Signal-Downloader (je eigene GUI + REST)            Ports
─────────────────────────────────────────────────────────────────────────────
 SIGNALDOWNLOADER/MqlDownloader   MQL5-Signale (originär)            :8089
 SIGNALDOWNLOADER/PelicanTrading  Pelican-CopyTrading  (~2.200)      :8090
 SIGNALDOWNLOADER/roboforex       RoboForex-CopyFX     (~200 Deals)  :8091
 SIGNALDOWNLOADER/vantage         Vantage-CopyTrading  (100.000+)    :8092
 SIGNALDOWNLOADER/zulumonitor     ZuluTrade-Trader     (Top 200)     :8093
        │            │            │            │            │
        └────────────┴─────┬─────┴────────────┴────────────┘
                           │  REST, Protokoll „mql5-downloader-v1“
                           │  (Katalog/Trades/Metrics/History/Reports,
                           │   Instanz-Kennung, optionaler Token)
                           ▼
              ┌──────────────────────────────────────┐
              │  SIGNALDOWNLOADER/SignalKiScanner    │  Der Multi-Source-Hub
              │  • Ingest (SHA-Delta-Cache)          │  • RetDD-Effizienz (Calmar)
              │  • Forensik-Batterie (Code rechnet)  │  • Kopier-Simulation (10k $)
              │  • Ampel/Score/Urteil (Engine)       │  • Kapitalfluss-Brücke
              │  • LLM-Berichte + Multi-Agenten      │  • Append-only Audit Trail
              └───────────────┬──────────────────────┘
                     │                 │
     PUSH (Einmal-Sync v1)      PULL (schreibgeschützte REST-API)
     /api/kiscanner, X-User-Key GET /api/v1/signals?ampel=gruen,gelb
                     ▼                 ▼
   GitWorkspace/MqlTradeMonitor   D:\git\MQL\MqlRealmonitor
   (Spring Boot :8080, Kachel      (holt sich die Ampel-Liste
    „🔬 MqlKiScanner“ + PDFs)       selbst ab; 127.0.0.1:8611)

─────────────────────────────────────────────────────────────────────────────
Ergänzendes Spezialwerkzeug im Workspace:
 SIGNALDOWNLOADER/PelicanWinnerLooser — JavaFX Desktop-Anwendung zur
 Erfassung und statistischen Forensik von Pelican-Kopierkonten (Gewinnverteilungen,
 Quantile, Konzentrationsanalysen, Renditekurven-Overlay, EZB-EUR-Normalisierung).
```

**Grundregel der Kette:** Quellen liefern nur Daten. Bewertet ausschließlich
die Engine des SignalKiScanners (Ampel/Score/Urteil); Konsumenten zeigen
Ergebnisse, sie bewerten nie. LLMs interpretieren, der Code rechnet.

---

## 2. Die Datenquellen und Komponenten im Workspace

Alle REST-Quellen implementieren dasselbe Protokoll (doc/20 §4):
`GET {base}/api/v1/health · /providers · /providers/{id}/{version}/
{history,trades,trades.csv,metrics,reports}` — mit Instanz-Kennung
(`instance`) und optionalem Token (`X-API-Token`/Bearer/`?token=`).
Konfiguration je Quelle: `data/rest_api.json` (enabled/port/token/instanceName),
Autostart + Toolbar-Button „REST-API an/aus“.

| Projekt (Ordner) | Version / Port | Währung | Besonderheiten / Highlights |
|---|---|---|---|
| **MqlDownloader** (Git: `tnickel/MqlDownloader`) | v0.0.34 / :8089 | USD | Originär; Selenium-Scraper für mql5.com; MPDD-Filter; sortierter REST-Katalog; liefert S/L-Orderbuchdaten. |
| **PelicanTrading** (Git: `tnickel/PelicanTrading`) | v1.4.3 / :8090 | USD-normalisiert | Deal-genaue Trades; Zwei-Phasen-Sync (Phase 1 UUID-Discovery aller Provider, Phase 2 Closed-Historie nur kopierter); Live-Trading je Strategie aus `strategien.db`; 24h-Erinnerung; serverseitige FX-Umrechnung. |
| **PelicanWinnerLooser** (Desktop JavaFX) | Stand 04.10. | EUR-normalisiert + Original | Erfasst Kopierkonten und deren Performance; Dashboard mit Gewinnverteilung, Quantilen, Konzentrationsanalysen (Top 10 %); Renditekurven-Overlay; DPAPI-Sessionverwaltung; unbegrenzter fortsetzbarer Arbeitsplan. |
| **roboforex** (Git: `tnickel/robomonitor`) | v1.1.1 / :8091 | USD | MT5-Rohdeals serverseitig zu Positionen gepaart; Tradelisten-Persistenz mit atomarem `geladen.json`-Ledger; `SubscriberDb` mit 7/30-Tage-Zuwachs; 24h-Erinnerung; Trade-EQ-DD Metriken. |
| **vantage** (Git: `tnickel/vantagemonitor`) | v1.1.3 / :8092 | USD/USC-normalisiert | Deal-genaue Trades ohne Login (bis 20.000 Trades); Signal-Alter aus lokaler Historie verifiziert; Spalte „Risiko (Broker)“ fett neben „Risiko (KI)“; `TradeListStore` mit `geladen.json`; `CopierDb`. |
| **zulumonitor** (Git: `tnickel/zulumonitor`) | v1.1.1 / :8093 | Trader-Konto | Gateway-JSON-API mit automatischem Dual-Host-Fallback; `TradeListenStore` mit `geladen.json`; `SubscriberDb` (`abonnenten.db`) mit 7/30-Tage-Zuwachs und REST `/history`; 24h-Erinnerung. |

---

## 3. Der Hub: SignalKiScanner

(Git: `tnickel/MqlKiScanner` — öffentlich; lokale Doku: AGENTS.md, doc/01–22)

- **Ingest & Delta-Engine** (`quellen.py`, `ingest.py`): Beliebig viele Quellen in der
  DB-Registry `datenquellen`. Trades/Metrics mit SHA-Artefakt-Cache (`quellen_artefakte`)
  – unveränderte Daten werden ohne CPU- oder Token-Verschwendung übersprungen.
- **RetDD (Rendite-Risiko-Effizienz)**: Durchgängige Bewertung nach geometrischem
  Monatsmittel (`ertrag_monat_geom_pct`) und echtem Calmar-Faktor (`cagr_jahr_pct ÷ MaxDD`).
  Feste 9. Zelle in der Ampel-Matrix (grün ≥ 0,5 · gelb 0,167–0,5 · orange < 0,167).
- **Kopier-Simulation in der KI-Studie**: Berechnet auf Basis eines fixen
  10.000-USD-Modellkontos den realen Verlauf und beantwortet dem Anleger:
  „Was wäre mit deinem Konto passiert?“.
- **Kapitalfluss-Brücke**: Erkennt historische Einlagen und Entnahmen auf MQL5,
  um künstlich verzerrte Broker-Drawdown-Angaben zu entlarven.
- **Forensik-Batterie**: Martingale-Erkennung, Peak-Exposure (Anzahl- und Schock-Peak),
  SL-Evidenz (Orderbuch vs. Verhaltensmuster), M1/M5-Equity-Rekonstruktion mit Auto-GMT,
  harte 30-%-Drawdown-Schranke, GLM-5.3 Multi-Agenten-Audits.
- **Append-only Audit Trail**: Wechsel-Protokoll dokumentiert jeden Ampelwechsel mit
  Alt- und Neuwerten aller Einzelkriterien.

---

## 4. Die Konsumenten

| Konsument | Richtung | Protokoll | Inhalt |
|---|---|---|---|
| **MqlTradeMonitor** (`GitWorkspace/MqlTradeMonitor`, Spring Boot :8080) | Scanner **pusht** transaktional | Einmal-Protokoll v1: `/api/kiscanner`, X-User-Key (doc/06) | Ergebnistabelle + alle PDF-BLOBs (SHA-Diff); Web-Cockpit mit Ampel-Kacheln, Scatter-Plots, Live-EA-Überwachung und Homey-Alarmierung. |
| **MqlRealmonitor** (`D:\git\MQL\MqlRealmonitor`) | **holt selbst ab** | schreibgeschützte REST-API auf `127.0.0.1:8611` | Signalliste mit Ampel, Score, Urteil, Kurzfassung und Quellenkürzel. |

---

## 5. Ports und Dienste

| Dienst | Port | Konfiguration / Protokoll |
|---|---|---|
| MqlDownloader-REST | 8089 | `config/MqldownloaderConfig.txt` (mql5-downloader-v1) |
| PelicanTrading-REST | 8090 | `data/rest_api.json` (mql5-downloader-v1, Version `pelican`) |
| RoboMonitor-REST | 8091 | `data/rest_api.json` (mql5-downloader-v1, Version `mql4`/`mql5`) |
| VantageMonitor-REST | 8092 | `data/rest_api.json` (mql5-downloader-v1, Version `vantage`) |
| ZuluMonitor-REST | 8093 | `data/rest_api.json` (mql5-downloader-v1, Version `zulu`) |
| SignalKiScanner GUI | 8504 | Streamlit Web-UI (`start.bat`) |
| SignalKiScanner REST | 8611 (127.0.0.1) | schreibgeschützte REST-API für Realmonitor |
| MqlTradeMonitor | 8080 | Spring Boot 3 Web-Server |

---

## 6. Testabdeckung (Stand: 04.10.2026)

| Projekt | Automatisierte Tests | Suite-Umfang & Details |
|---|---|---|
| **SignalKiScanner** | **1.331** gesammelt | 100 Pytest-Dateien (18.822 LOC Testcode; Forensik, RetDD, Hub-Ingest, Agenten, TradeServer-Sync) |
| **PelicanWinnerLooser** | **156** grün | 21 Testdateien (3.600 LOC Testcode; Resume, Fake-HTTP, Kurvenstatistik, Quantile, DPAPI) |
| **roboforex** (RoboMonitor) | **129** grün | 15 Testdateien (2.640 LOC Testcode; DealStore, SubscriberDb, MT5-Paarung, UiPrefs) |
| **zulumonitor** (ZuluMonitor) | **81** grün | 13 Testdateien (1.816 LOC Testcode; TradeListenStore, SubscriberDb, REST-Server) |
| **MqlDownloader** | **76** grün | 15 Testdateien (2.306 LOC Testcode; Parser, MPDD, REST-Katalog, Setup) |
| **PelicanTrading** (PelicanMonitor) | **63** grün | 8 Testdateien (1.739 LOC Testcode; 2-Phasen-Sync, UiPrefs, REST-Konvertierung) |
| **vantage** (VantageMonitor) | **25** grün | 7 Testdateien (793 LOC Testcode; TradeListStore, CopierDb, Historienalter, Broker-Risiko) |
| **GESAMT (WORKSPACE)** | **1.861 Tests** | **31.716 LOC reiner Testcode** zur Absicherung der Plattform |

---

## 7. Ausbaustufen & Roadmap

- ✅ **Vantage Git-Repository:** `tnickel/vantagemonitor` eingerichtet und angebunden.
- ✅ **Pelican Git-Repository:** `tnickel/PelicanTrading` eingerichtet und synchronisiert.
- ✅ **Trade-EQ-DD Direktanbindung:** Monitore liefern den echten Trade-Drawdown direkt an den Scanner-Ingest.
- ✅ **Abonnenten-Historie:** Standardisiert auf `abonnenten.db` in allen Plattform-Monitoren.
- ✅ **24h-Ladeerinnerung & UI-Prefs:** In allen Monitoren integriert.
- ✅ **RetDD-Effizienz & Kopier-Simulation:** Im Hub produktiv im Einsatz.
- 🔄 **Nächste Stufen:** Composite-Signalidentität `(quelle, signal_id)` im Multi-Source-Betrieb, Erweiterung um Krypto-/Futures-Signale.
