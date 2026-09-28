# 21 — Megaprojekt-Architektur: Signal-Kette von der Quelle bis zum Monitor

Stand: 27.09.2026 (Nachtrag 28.09.2026: Vantage-Währungsschutz + Kopierer-
Historie nachgetragen, Testzahlen aktualisiert). Diese Seite ist die
**Gesamtdokumentation des Megaprojekts**
im Workspace `SIGNALDOWNLOADER` — der SignalKiScanner als Hub, fünf Datenquellen
per REST angebunden, zwei Konsumenten nachgelagert. Detail-Doku der Quellen:
doc/20 (Multi-Source-Hub, §4a–d); je Projekt existiert eine eigene README.

## 1. Das Bild

```
Signale-Quellen (je Projekt eigener Monitor + REST-Interface)          Ports
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
              ┌──────────────────────────────┐
              │  SIGNALDOWNLOADER/SignalKiScanner  │  Der Hub — bewertet
              │  • Ingest (SHA-Delta-Cache)        │
              │  • Forensik-Batterie (Code rechnet)│
              │  • Ampel/Score/Urteil (Engine)     │
              │  • LLM-Berichte + Agentenbetrieb   │
              └───────────────┬──────────────────┘
                     │                 │
     PUSH (Einmal-Sync v1)      PULL (schreibgeschützte REST-API)
     /api/kiscanner, X-User-Key GET /api/v1/signals?ampel=gruen,gelb
                     ▼                 ▼
   GitWorkspace/MqlTradeMonitor   D:\git\MQL\MqlRealmonitor
   (Spring Boot :8080, Kachel      (holt sich die Ampel-Liste
    „🔬 MqlKiScanner“ + PDFs)       selbst ab; 127.0.0.1:8611)
```

**Grundregel der Kette:** Quellen liefern nur Daten. Bewertet ausschließlich
die Engine des SignalKiScanners (Ampel/Score/Urteil); Konsumenten zeigen
Ergebnisse, sie bewerten nie. LLMs interpretieren, der Code rechnet.

## 2. Die fünf Datenquellen

Alle Quellen implementieren dasselbe REST-Protokoll (doc/20 §4):
`GET {base}/api/v1/health · /providers · /providers/{id}/{version}/
{history,trades,trades.csv,metrics,reports}` — mit Instanz-Kennung
(`instance`, Standard Rechnername) und optionalem Token
(`X-API-Token`/Bearer/`?token=`). Konfiguration je Quelle:
`data/rest_api.json` (enabled/port/token/instanceName), Autostart +
Toolbar-Button „REST-API an/aus“.

| Projekt (Ordner) | Version(en) | Währung | Besonderheiten / Grenzen |
|---|---|---|---|
| **MqlDownloader** (Git: `tnickel/MqlDownloader`) | `mql4`/`mql5` | USD | Originär; Original-mql5-Exporte; MPDD-Filter gewollt; Initial Deposit folgt |
| **PelicanTrading** (kein Git) | `pelican` | USD-normalisiert | serverseitige FX-Umrechnung seit 28.09.2026 (USC fix ÷100, übrige EZB-Kurs, Kennzeichnung in metrics/Katalog — doc/20 §4a.1); SL nur offene Positionen; weeks im Katalog; InitialDepositVirtual (additiv) |
| **roboforex** (Git: `tnickel/robomonitor`) | `mql4`/`mql5` je Plattform | USD | MT5-Rohdeals serverseitig zu Positionen gepaart; Ø-Monatsrendite hergeleitet (Yield/Laufzeit) |
| **vantage** (kein Git) | `vantage` | USD/USC-normalisiert | gemessene 30-Tage-Rendite; Basis-Symbole (XAUUSD statt XAUUSD.sc); USC (US-Cent) serverseitig ÷100 nach USD; Drittwährung (EUR, GBP …): trades.csv 404 + Grund (Forensik rechnet USD); Kopierer-Historie aus kopierer.db (/history, 7/30-Tage-Zuwachs im Katalog) |
| **zulumonitor** (Git: `tnickel/zulumonitor`) | `zulu` | Trader-Konto | trades.csv nur USD-Konten (149/200); keine Abonnenten-Historie (ehrlich leer); Demo-Flag im Katalog |

Allen gemeinsam (Nutzer-Entscheidungen 27.09.2026, doc/20 §2): kein
SL-Nachweis in Historien → „kein Nachweis" + Verhaltensanalyse; Initial
Deposit ruht bis Belieferung; Tagesfrische genügt; der Code des Scanners
rechnet alle forensischen Zahlen selbst aus den Trades.

## 3. Der Hub: SignalKiScanner

(Git: `tnickel/MqlKiScanner` — öffentlich; lokale Doku: AGENTS.md, doc/01–20)

- **Ingest** (`quellen.py`, `ingest.py`): beliebig viele Quellen in der
  DB-Registry `datenquellen` (Admin → Datenquellen; Kürzel je Quelle erscheint
  als Herkunft in der Ergebnisliste). Katalog → Kandidaten; Trades/Metrics mit
  SHA-Artefakt-Cache (`quellen_artefakte`) — unveränderte Daten werden nicht
  neu verarbeitet. Verbindungstest je Quelle mit Ampel 🟢/🟡/🔴 inkl.
  Instanz-Kennung; Doppelung einer Instanz unter zwei Quellen = Warnung.
- **Scan-Modus** `listen_modus`: `mql5` (bisheriges Verhalten, Crawler) ·
  `quellen` (nur REST, kein MQL5-Kontakt) · `beides` (Vereinigung).
- **Forensik + Ampel + Berichte + Agentenbetrieb**: unverändert über allen
  Quellen — Martingale, Peak-Exposure, SL-Clustering, DD-Rekonstruktion,
  Ampel-Matrix, PDF-Berichte, Agenten Phasen A–E (doc/19).

## 4. Die Konsumenten

| Konsument | Richtung | Protokoll | Inhalt |
|---|---|---|---|
| **MqlTradeMonitor** (`D:\AntiGravitySoftware\GitWorkspace\MqlTradeMonitor`, Spring Boot :8080) | Scanner **pusht** einmalig (Button „Tradeserver-Sync“) | Einmal-Protokoll v1: `/api/kiscanner`, X-User-Key-Handshake (doc/06) | Ergebnistabelle + alle PDFs (SHA-Diff); Kachel „🔬 MqlKiScanner", Seite /kiscanner |
| **MqlRealmonitor** (`D:\git\MQL\MqlRealmonitor`) | **holt selbst ab** | schreibgeschützte REST-API auf `127.0.0.1:8611` (startet mit der App; Token optional): `GET /api/v1/health`, `GET /api/v1/signals?ampel=gruen,gelb` | Signalliste mit Ampel, Score, Urteil, Kurzfassung, **Quelle** (Kürzel) |

Beide Konsumenten werden nie vom Scanner bewertet beeinflusst und schreiben
nichts zurück — die Kette ist am Hub einseitig geschlossen.

## 5. Ports, Konfiguration, Betrieb

| Dienst | Port | Konfiguration |
|---|---|---|
| MqlDownloader-REST | 8089 | `config/MqldownloaderConfig.txt` (instanceName im Setup-Dialog) |
| PelicanTrading-REST | 8090 | `data/rest_api.json` |
| RoboMonitor-REST | 8091 | `data/rest_api.json` |
| VantageMonitor-REST | 8092 | `data/rest_api.json` |
| ZuluMonitor-REST | 8093 | `data/rest_api.json` |
| SignalKiScanner GUI (Streamlit) | 8501 | `data/app_settings.json` (Quellen in DB, Tokens im Secrets-Speicher) |
| SignalKiScanner REST für Realmonitor | 8611 (nur 127.0.0.1) | Admin → REST-API |
| MqlTradeMonitor | 8080 | dortige Projektdoku |

Anbindung einer neuen Quelle im Scanner: Admin → Datenquellen → hinzufügen
(Kürzel + Base-URL + optional Token) → „Alle Quellen testen“ → Scan-Seite
„Signale holen aus: Datenquellen (REST)“ oder „Beides“.

## 6. Testabdeckung (Stand 28.09.2026)

| Projekt | Suite | Davon REST |
|---|---|---|
| SignalKiScanner | **948** grün (28.09.: +14 Fix-IDs) | 21 Quellen-/Akzeptanztests (je Quelle ein Ende-zu-Ende-Regressionstest) |
| MqlDownloader | **81** grün | 3 (Instanz-Kennung) |
| PelicanTrading | **24** grün | 8 |
| roboforex | **114** grün | 9 (inkl. MT5-Paarung) |
| vantage | **10** grün (28.09.: +2 Währungsschutz) | 10 |
| zulumonitor | **63** grün | 9 |

## 7. Offenes / Ausbaustufen (doc/20 §7)

- Initial Deposit: MqlDownloader-/metrics-Erweiterung (Vorlage für alle) →
  danach volle Kapitalbasis-Regel für Quellen-Signale.
- USD-Konten-Filter durch FX-Umrechnung ersetzen — **Pelican erledigt
  (28.09.2026, serverseitig im Downloader, doc/20 §4a.1)**; Zulu und Vantage
  offen (Vantage deckt USD+USC ab und lehnt Drittwährung seit 28.09.2026
  ehrlich mit 404 + Grund ab, Zulu-Muster).
- Stufe 2–4: Composite-Identität (quelle, signal_id), Betreuer-Agent auf
  Quellen umstellen, MQL5-Crawler entfernen (`listen_modus=quellen` als
  Standard), weitere Börsen.
- vantage und PelicanTrading: noch ohne Git-Repository.
