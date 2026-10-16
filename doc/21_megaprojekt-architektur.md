# 21 — Megaprojekt-Architektur: Signal-Kette von der Quelle bis zum Monitor

Dokumentationsabgleich: 16.10.2026. Diese Seite ist die **Gesamtdokumentation des Megaprojekts**
im Workspace `SIGNALDOWNLOADER` — der SignalKiScanner als Multi-Source-Hub,
fünf Datenquellen per REST angebunden und der nachgelagerte Konsument
`MqlTradeMonitor`. Daneben liegt das eigenständige Einzelprojekt
`PelicanWinnerLooser` für Kopierkonten-Verteilungsforensik; es ist noch nicht
in den Gesamtworkflow eingebunden.

**MqlRealmonitor ist noch nicht in den Gesamtworkflow eingebunden.**
REST-Server im Scanner und Client-Code im Monitor sind vorbereitet;
die Integration bleibt vorerst zurückgestellt (Nutzerentscheidung 16.10.2026).
Das Mitstarten über `startall.bat` bedeutet keine abgeschlossene Integration.
**PelicanWinnerLooser ist ein eigenständiges Einzelprojekt und ebenfalls
noch nicht eingebunden.** Eine Hub-Anbindung ist nicht implementiert.

Detail-Doku der Quellen: doc/20 (Multi-Source-Hub, §4a–d); je Projekt existiert
eine eigene README.

---

## 1. Das Bild

```
5 Signal-Downloader (je eigene GUI + REST)            Ports
─────────────────────────────────────────────────────────────────────────────
 SIGNALDOWNLOADER/MqlDownloader   MQL5-Signale (originär)            :8089
 SIGNALDOWNLOADER/PelicanTrading  Pelican-CopyTrading               :8090
 SIGNALDOWNLOADER/roboforex       RoboForex-CopyFX                  :8091
 SIGNALDOWNLOADER/vantage         Vantage-CopyTrading               :8092
 SIGNALDOWNLOADER/zulumonitor     ZuluTrade-Trader                  :8093
        │            │            │            │            │
        └────────────┴─────┬─────┴────────────┴────────────┘
                           │  REST, Protokoll „mql5-downloader-v1“
                           │  (Katalog/Trades/Metrics/History/Reports,
                           │   Instanz-Kennung, optionaler Token;
                           │   Stufe 0: POST /update + GET /update/status)
                           ▼
              ┌──────────────────────────────────────┐
              │  SIGNALDOWNLOADER/SignalKiScanner    │  Der Multi-Source-Hub
              │  • Ingest (SHA-Delta-Cache)          │  • RetDD-Effizienz (Calmar)
              │  • Forensik-Batterie (Code rechnet)  │  • Kopier-Simulation (10k $)
              │  • Ampel/Score/Urteil (Engine)       │  • Kapitalfluss-Brücke
              │  • LLM-Berichte + Multi-Agenten      │  • Append-only Audit Trail
              └───────────────┬──────────────────────┘
                     │
     PUSH (Einmal-Sync v1)
     /api/kiscanner, X-User-Key
                     ▼
   GitWorkspace/MqlTradeMonitor
   (Spring Boot :8080, Kachel „🔬 MqlKiScanner“ + PDFs)

   Vorbereitet, noch nicht in den Gesamtworkflow eingebunden:
   Scanner-REST 127.0.0.1:8611/api/v1/signals?ampel=gruen,gelb
   MqlRealmonitor-Client vorhanden; Integration vorerst zurückgestellt.

─────────────────────────────────────────────────────────────────────────────
Eigenständiges Einzelprojekt, noch nicht eingebunden:
 SIGNALDOWNLOADER/PelicanWinnerLooser — JavaFX Desktop-Anwendung zur
 Erfassung und statistischen Forensik von Pelican-Kopierkonten (Gewinnverteilungen,
 Quantile, Konzentrationsanalysen, Renditekurven-Overlay, EZB-EUR-Normalisierung).
 Keine implementierte Hub-Anbindung.
```

**Grundregel der Kette:** Die zentrale Hub-Ampel samt Score und Urteil
berechnet ausschließlich die Scanner-Engine. Quellen liefern Daten und können
unabhängige eigene KI-Berichte erzeugen. Die verbindlichen Kennzahlen rechnet
der Code; LLMs interpretieren. Die manuelle Tiefenanalyse darf ergänzende
Rechnungen mit offengelegten Annahmen liefern, ohne Ampel/Score zu ändern.

---

## 2. Die fünf Datenquellen

Alle REST-Quellen implementieren dasselbe Protokoll (doc/20 §4):
`GET {base}/api/v1/health · /providers · /providers/{id}/{version}/
{history,trades,trades.csv,metrics,reports}` — mit Instanz-Kennung
(`instance`) und optionalem Token (`X-API-Token`/Bearer/`?token=`).
Die fünf Quellen unterstützen außerdem `POST /api/v1/update` und
`GET /api/v1/update/status` für Stufe 0 (doc/23). Datenabfragen bleiben GETs;
die Quellen-API ist insgesamt nicht mehr ausschließlich lesend.
Konfiguration der JavaFX-Quellen: `data/rest_api.json`
(enabled/port/token/instanceName); MqlDownloader verwendet
`config/MqldownloaderConfig.txt`.

| Projekt (Ordner) | Port / Typ | Währung | Besonderheiten / Highlights |
|---|---|---|---|
| **MqlDownloader** (Git: `tnickel/MqlDownloader`) | :8089 | USD-Export; Metadaten beachten | Selenium-Scraper für mql5.com; MPDD-Filter; REST-Katalog und MT4-S/L-Orderbuchdaten. |
| **PelicanTrading** (Git: `tnickel/PelicanTrading`) | :8090 | USD-normalisiert | Provider-Katalog, Trades, Kopiererstatistik, lokale Berichte und serverseitige FX-Umrechnung; Stufe-0-Tradelisten-Auswahl konfigurierbar. |
| **roboforex** (Git: `tnickel/robomonitor`) | :8091 | Export behandelt Beträge als USD; keine FX-Normalisierung | MT5-Deals zu Positionen gepaart; Tradelisten-Ledger; Abonnentenhistorie; Closing-DD. |
| **vantage** (Git: `tnickel/vantagemonitor`) | :8092 | USD-normalisierter Export; FX-Metadaten beachten | Deal-genaue Trades mit Kappungsgrenze (20.000); Broker-/KI-Risiko getrennt; Tradelisten-Ledger; Kopiererhistorie. |
| **zulumonitor** (Git: `tnickel/zulumonitor`) | :8093 | USD-normalisierter Export; FX-Metadaten beachten | Dual-Host-Fallback; Tradelisten-Ledger; Abonnenten-Snapshots und REST `/history`; Closing-DD. |

**Separates Einzelprojekt:** PelicanWinnerLooser (JavaFX, eigene SQLite-Datenbank)
analysiert Kopierkonten, Gewinnverteilungen, Quantile und Renditekurven.
Es ist noch nicht eingebunden und gehört nicht zu den fünf Hub-Datenquellen.

---

## 3. Der Hub: SignalKiScanner

(Git: `tnickel/MqlKiScanner`; lokale Doku: AGENTS.md, doc/01–23).
Jedes Anwendungsprojekt hat ein eigenes Git-Repository und einen eigenen
Startweg. Das zusätzliche Repository `tnickel/SIGNALDOWNLOADER` sichert nur
die übergeordnete README, `startall.bat` und `UI_KONVENTIONEN.md`; die
Anwendungs-Repositories sind darin weder kopiert noch als Submodule eingebunden.

- **Ingest & Delta-Engine** (`quellen.py`, `ingest.py`): Beliebig viele Quellen in der
  DB-Registry `datenquellen`. Trades/Metrics mit SHA-Artefakt-Cache (`quellen_artefakte`)
  – SHA-Vergleiche erkennen unveränderte Artefakte. Der Teilscan erzwingt
  dennoch neue KI-Berichte; Cache-Treffer bedeuten nicht generell null Modellaufrufe.
- **RetDD (Rendite-Risiko-Effizienz)**: Durchgängige Bewertung nach geometrischem
  Monatsmittel (`ertrag_monat_geom_pct`) und echtem Calmar-Faktor (`cagr_jahr_pct ÷ MaxDD`).
  Seit 05.10. prüft die Matrix-Zelle den Jahres-Calmar: grün ab
  `min_calmar_jahr` (Default 3,0), gelb ab der Hälfte, orange darunter,
  ⚪ ohne Messung. Die frühere Monats-RetDD-Schwelle 1,0 ist abgelöst.
  Mindestens drei Monate Trade-Historie sind erforderlich. Die absolute
  Monats-Ertragshürde ist standardmäßig ausgeschaltet (`min_ertrag_pct_monat=0`);
  Nenner ist ausschließlich die valide EIGENE Kurs-Messung (H1-Rekonstruktion) —
  NIEMALS Closing-/Balance-/Trading-DD oder Plattform-Selbstauskunft. Der Monitor-Wert
  (`TradeEqDrawdownPct`) ist eine Closing-Kurve und bleibt nur Untergrenzen-Kanal der
  harten 5-Kanal-Schranke (Review 04.10., Nutzer-Entscheidung „zentral + ehrlich").
- **Kopier-Simulation in der Equity-Studie**: Modellrechnung für ein
  10.000-USD-Konto unter den angezeigten Skalierungs- und Kostenannahmen;
  kein Nachweis eines tatsächlich kopierten Kontoverlaufs.
- **Kapitalfluss-Brücke**: Berücksichtigt überlieferte Einlagen und Entnahmen
  und legt die Kapital- und Zeitbasis der jeweiligen Kennzahl offen.
- **Forensik-Batterie**: Martingale-Erkennung, Peak-Exposure (Anzahl- und Schock-Peak),
  SL-Evidenz (Orderbuch vs. Verhaltensmuster), H1-Equity-Rekonstruktion mit Auto-GMT
  (produktiver Pfad; M1 nur als Spitzentage-Referenz in der DD-Kalibrierung doc/22),
  harte Drawdown-Schranke (Default 30 %), optionale KI-Berichte und Agentenbetrieb.
  Fehlender SL-Nachweis ist neutral; der Risiko-Score ist kein eigenständiges
  Grün-Gate. Unzuverlässige Kursmessungen liefern höchstens orange Vorbehaltswerte.
- **Append-only Audit Trail**: Wechsel-Protokoll dokumentiert jeden Ampelwechsel mit
  Alt- und Neuwerten aller Einzelkriterien.

---

## 4. Die Konsumenten

| Konsument | Richtung | Protokoll | Inhalt |
|---|---|---|---|
| **MqlTradeMonitor** (`GitWorkspace/MqlTradeMonitor`, Spring Boot :8080) | Scanner **pusht** transaktional | Einmal-Protokoll v1: `/api/kiscanner`, X-User-Key (doc/06) | Ergebnistabelle + alle PDF-BLOBs (SHA-Diff); Web-Cockpit mit Ampel-Kacheln, Scatter-Plots, Live-EA-Überwachung und Homey-Alarmierung. |
| **MqlRealmonitor** (`SIGNALDOWNLOADER/MqlRealmonitor`) | **vorbereitet, noch nicht eingebunden** | REST-Server und Client-Code für `127.0.0.1:8611/api/v1` vorhanden | Vorgesehen: Signalliste mit Ampel, Score, Urteil, Kurzfassung und Quellenkürzel. Integration vorerst zurückgestellt. |

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
| SignalKiScanner REST | 8611 (127.0.0.1) | vorbereitete schreibgeschützte API; MqlRealmonitor-Integration zurückgestellt |
| MqlTradeMonitor | 8080 | Spring Boot 3 Web-Server |

---

## 6. Historisch dokumentierte Testabdeckung (04.10.2026)

Die folgenden Zahlen stammen aus der damaligen Dokumentation und wurden beim
Abgleich am 16.10.2026 nicht erneut erhoben. Sie sind kein Nachweis für den
aktuellen Arbeitsstand oder eine abgeschlossene MqlRealmonitor-Integration.

| Projekt | Automatisierte Tests | Suite-Umfang & Details |
|---|---|---|
| **SignalKiScanner** | **1.341** gesammelt | 100 Pytest-Dateien (18.822 LOC Testcode; Forensik, RetDD, Hub-Ingest, Agenten, TradeServer-Sync) |
| **PelicanWinnerLooser** | **156** grün | 21 Testdateien (3.600 LOC Testcode; Resume, Fake-HTTP, Kurvenstatistik, Quantile, DPAPI) |
| **roboforex** (RoboMonitor) | **129** grün | 15 Testdateien (2.640 LOC Testcode; DealStore, SubscriberDb, MT5-Paarung, UiPrefs) |
| **zulumonitor** (ZuluMonitor) | **81** grün | 13 Testdateien (1.816 LOC Testcode; TradeListenStore, SubscriberDb, REST-Server) |
| **MqlDownloader** | **76** grün | 15 Testdateien (2.306 LOC Testcode; Parser, MPDD, REST-Katalog, Setup) |
| **PelicanTrading** (PelicanMonitor) | **63** grün | 8 Testdateien (1.739 LOC Testcode; 2-Phasen-Sync, UiPrefs, REST-Konvertierung) |
| **vantage** (VantageMonitor) | **25** grün | 7 Testdateien (793 LOC Testcode; TradeListStore, CopierDb, Historienalter, Broker-Risiko) |

---

## 7. Ausbaustufen & Roadmap

- ✅ **Vantage Git-Repository:** `tnickel/vantagemonitor` eingerichtet und angebunden.
- ✅ **Pelican Git-Repository:** `tnickel/PelicanTrading` eingerichtet und synchronisiert.
- ✅ **Closing-DD-Anbindung:** Monitore liefern `TradeEqDrawdownPct` als Legacy-Feld. Es bleibt ein Kanal der harten Schranke, ersetzt aber keine historische Equity-Messung einschließlich Floating.
- ✅ **Abonnenten-Historie:** Standardisiert auf `abonnenten.db` in allen Plattform-Monitoren.
- ✅ **24h-Ladeerinnerung & UI-Prefs:** In allen Monitoren integriert.
- ✅ **RetDD-Effizienz & Kopier-Simulation:** Im Hub produktiv im Einsatz.
- ✅ **Stufe 0:** Quellen-Updates vor GUI- und autonomen Scans implementiert (doc/23).
- 🔄 **Offen:** Vollständige Composite-Signalidentität `(quelle, signal_id)`;
  die zentrale Signaltabelle verwendet noch allein `signal_id` und wehrt
  Quellenkollisionen ab. Betreuer-Agent auf Quellen-Cache umstellen (derzeit
  nur MQL5); weitere Quelltypen. Krypto-/Futures-Kontrakte sind bereits
  teilweise vorhanden und nicht mit einer zusätzlichen Datenquelle gleichzusetzen.
- ⏸ **MqlRealmonitor:** Noch nicht in den Gesamtworkflow eingebunden;
  Integration ausdrücklich zurückgestellt. Keine Änderung an der technischen
  Vorbereitung oder den Startskripten im Rahmen dieses Dokumentationsabgleichs.
