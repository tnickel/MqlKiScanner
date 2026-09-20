# 06 · Tradeserver-Sync (MqlTradeMonitor) — Konzept, Protokoll, Betrieb

Stand: 20.09.2026 · Status: umgesetzt und getestet (Scanner 748 Tests grün,
Tradeserver 56 Tests grün)

## 1. Ziel und Architektur

Der MqlKiScanner bewertet MQL5-Signale forensisch (Ampel, Score, Urteil,
PDF-Berichte). Diese Ergebnis-Tabelle soll auch auf dem **MqlTradeMonitor**
sichtbar sein — einem Spring-Boot-Tradeserver
(`D:\AntiGravitySoftware\GitWorkspace\MqlTradeMonitor`), zu dem sich sonst
MetaTrader-EAs und Apps verbinden und der ein Kachel-Dashboard betreibt.

```
MqlKiScanner (hier, Streamlit)                MqlTradeMonitor (Spring Boot 3.2)
┌─────────────────────────────┐   HTTP/JSON   ┌──────────────────────────────────┐
│ Sync-Button (Ergebnisse)    │──────────────▶│ /api/kiscanner/* (Protokoll v1)  │
│ tradeserver_client.py       │   X-User-Key  │ KiScannerApiController           │
│ tradeserver_sync.py         │◀──────────────│ KiScannerService                 │
└─────────────────────────────┘   Inventory   │ H2: ki_signals / ki_documents /  │
        Einmallauf:                          │     ki_sync_runs                 │
        verbinden → übertragen → trennen     │ Kachel „🔬 MqlKiScanner“ im Dash- │
                                             │ board → Seite /kiscanner         │
                                             │ (Tabelle, Charts, PDF-Ansicht)   │
                                             └──────────────────────────────────┘
```

**Feste Vorgaben (Nutzer, 20.09.2026):**

- Der Verbindungsaufbau geht **vom Scanner aus**: Sync-Klick → verbinden →
  alles übertragen → die Verbindung wird danach **wieder getrennt**
  (Einmallauf, keine Dauerverbindung, kein Heartbeat).
- Der Tradeserver ist extern mit **fester IP**; Adresse und API-Key stehen
  in der Konfiguration des Scanners (Admin-Bereich).
- Der MqlKiScanner ist **kein MetaTrader-EA** und bekommt deshalb eine
  **Sonderbehandlung bei der Anmeldung**: ein eigenes Protokoll mit
  Pflicht-Handshake statt des EA-Wegs über `/api/register` + Trades.
- Der Server speichert alles in **seiner** Datenbank und zeigt den Stand
  in einer eigenen Kachel + Detailseite — auch wenn der Scanner gerade
  nicht verbunden ist (Spiegel-Prinzip wie beim MqlDownloader, nur invertiert).
- Der Sync **bewertet nie neu** und schreibt nichts in die Fachtabellen
  (signals/forensik/analyses) — lokal entsteht nur die Lauf-Historie
  (`tradeserver_sync_runs`).

## 2. Protokoll „KiScanner-Sync v1“

Basis: `{Base-URL}/api/kiscanner`, z. B. `http://192.0.2.10:8080`.
Jeder Aufruf trägt den Server-API-Key im Header **`X-User-Key`** (gleicher
Mechanismus wie bei den EAs: der Key gehört zu einem Benutzer des
Tradeservers, Feld „API-Key“ in dessen Admin-Oberfläche; ein Benutzer ohne
freigegebene Accounts kann sonst nichts — ideal für einen reinen Sync-User).

Die Schritte sind Pflicht und nur in dieser Reihenfolge erfolgreich:

| # | Aufruf | Richtung | Zweck |
|---|--------|----------|-------|
| 0 | `GET /ping` | Scanner → Server | Verbindungstest (erreichbar + Key gültig). Kein Sync-Lauf. |
| 1 | `POST /register` | Scanner → Server | **Handshake/Sonderbehandlung.** Body muss `client:"MqlKiScanner"`, `protocolVersion:1`, `scannerVersion`, `signalCount` enthalten — sonst HTTP 400 mit Begründung. Öffnet einen Lauf (ki_sync_runs, Status `running`) und antwortet mit `runId`, `serverTime` und dem **Serverbestand**: `documents:[{docKey, sha256}]` + `signalIds`. |
| 2 | `POST /signals` | Scanner → Server | Vollständiger Tabellen-Snapshot `{signals:[…]}`. Spiegel-Semantik: Server speichert/aktualisiert alle Zeilen (Key = signalId) und **löscht** Zeilen, die im Snapshot fehlen. Antwort: `{stored, deleted}`. |
| 3 | `POST /documents` | Scanner → Server | **Ein Dokument pro Aufruf** (max ~12 MB dekodiert, nur `application/pdf`, Magic-Byte-Prüfung): `{docKey, signalId, group, kind, label, fileName, contentType, sha256, sizeBytes, lastModified, contentBase64}`. Upsert über `docKey`. |
| 4a | `POST /complete` | Scanner → Server | Abschluss mit Bilanz `{signals, documents, uploaded, skipped, bytes}` → Lauf wird `ok`, Verbindung endet. |
| 4b | `POST /abort` | Scanner → Server | Fehlerpfad: Lauf wird `aborted` (mit Grund). |

**Diff-Prinzip:** Der Scanner überträgt ein PDF nur, wenn `sha256` vom
Serverbestand abweicht (Antwort von Schritt 1); unveränderte Dateien zählen
als „übersprungen“. `docKey`-Schema:

- eigene Berichte: `signal/{Signal-ID}/{01-trade-analyse|02-risiko-analyse|03-gesamtbericht|04-tiefenanalyse}.pdf`
- Portfolio: `portfolio/portfolio-gesamtbericht.pdf`
- Downloader-Spiegel: `signal/{Signal-ID}/downloader/{mql4|mql5}/{Name}.pdf`

**Fehler-Sortierung (Client):** Netzwerk/Timeout → Abbruch mit Nachricht;
401 (Key falsch) → Abbruch; 400 (Protokollverstoß) → Abbruch mit
Server-Begründung; Einzeldokument-Fehler lokal (z. B. Datei fehlt, > 8 MB)
→ Hinweis im Bericht, Lauf läuft weiter.

**Signal-Zeile (JSON, CamelCase)** enthält alle Tabellenfelder der
Ergebnisansicht: `signalId, name, platform, url, ampel, score, urteil,
kurzfassung, stop, stopEvidence, tradingDdPct, ddEquityPct, ddBalancePct,
ertragMonatPct, growthPct, pf, winratePct, aboPreisUsd, abonnenten, wochen,
aboDelta7, aboDelta30, aboStand, martingale, peakPositionen, peakNettoLots,
shockUsd, kapitalbasisUsd, brokerServer, symbole, berichtVom, docsBerichte,
docsTiefenanalyse, docsDownloader, tradesSha256, stand` („NEU“-Markierung).
Zahlen werden vor der Übertragung gerundet (der Server rechnet nicht).

## 3. Konfiguration

| Ort | Schlüssel | Beispiel |
|-----|-----------|----------|
| Admin → Tradeserver (landet in `config/app_settings.json`) | `tradeserver_base_url` | `http://192.0.2.10:8080` |
| Admin → Tradeserver / `.env` / Env (`MQLTRADEMONITOR_KEY`, `MQLKISCANNER_TRADESERVER_KEY`) | `tradeserver_api_key` | 43-Zeichen-Key des Tradeserver-Benutzers |

Default-Platzhalter: `config.TRADESERVER_DEFAULT_BASE = http://192.0.2.10:8080`.
Der Client ergänzt `/api/kiscanner` selbst; ein Kontextpfad in der Base-URL
bleibt erhalten. Secrets liegen wie immer nur im secrets_store (nie im Repo).

## 4. Bedienung

1. **Einrichten (einmalig):** Admin → Tradeserver → Base-URL + API-Key
   speichern → „Gespeicherte Tradeserver-Verbindung testen“ (ruft `/ping`).
   Danach zeigt die Sidebar den Badge „Tradeserver verbunden“ (5-Min-Cache).
2. **Sync starten:** Ergebnisse-Seite → Button **„Tradeserver-Sync“** (neben
   dem MqlDownloader-Abgleich). Übertragen wird die **aktuell gewählte
   Quelle** (Datenbank/Sitzung/Archiv) mit allen zugehörigen PDFs — eigene
   Berichte (nötigenfalls werden sie dafür erzeugt), Portfolio-Gesamtbericht
   und gespiegelte Downloader-Testreports. Statusfenster zeigt Fortschritt
   je Dokument; am Ende steht die Bilanz (Signale gespeichert/gelöscht,
   PDFs übertragen/unverändert, MB, Dauer).
3. **Am Tradeserver ansehen:** Dashboard-Kachel „🔬 MqlKiScanner“ zeigt
   Verbunden/Zähler/letzte Synchronisierung (aktualisiert sich alle 30 s);
   Klick öffnet `/kiscanner` mit Tabelle (Ampel, Stop, DD, Ertrag, Score-
   Balken, Urteil, Abonnenten-Deltas, 📄/🟡), Ampel-Donut, Risiko-Ertrag-
   Scatter (Schranken 30 % DD / 5 % Ertrag) und der PDF-Ansicht je Signal
   (Browser-Viewer, Login-geschützt).

## 5. Umsetzung im Scanner (dieses Repo)

- `src/mqlkiscanner/tradeserver_client.py` — REST-Client (Fehlerhierarchie,
  `normalize_base_url`, Protokollschritte als Methoden).
- `src/mqlkiscanner/tradeserver_sync.py` — `signal_zeilen` (Payload),
  `dokumente_sammeln` (PDF-Sammlung inkl. Erzeugung), `sync_alle`
  (Protokoll-Ablauf mit Diff, Abort, Lauf-Historie), `verbindungs_status`
  (TTL-Cache 5 Min), `konfiguriert`.
- `db.py` — Tabelle `tradeserver_sync_runs` + `store_/list_tradeserver_sync_runs`
  (append-only, nur Protokoll — Fachtabellen bleiben unberührt; Test sichert
  die Invariante).
- UI: Admin-Tab „Tradeserver“ (Verbindung + Test + Sync-Historie), Sidebar-
  Badge, Sync-Button auf der Ergebnisseite (aktivitaets_banner + st.status),
  Help-Texte (`tradeserver_sync`, `settings_tradeserver*`).
- Tests: `tests/test_tradeserver_client.py` (URL/Header/Fehler/Protokoll-
  Pflichtfelder), `tests/test_tradeserver_sync.py` (Mapping, Dokumente,
  Happy Path mit SHA-Diff, Abbruch mit Abort, Invariante, TTL-Cache).

## 6. Umsetzung im Tradeserver (Projekt MqlTradeMonitor)

- `KiScannerApiController` (`/api/kiscanner/*`) — Maschinen-Endpunkte
  (permitAll + CSRF-frei, eigene X-User-Key-Prüfung, AUTH_FAILED-Logging)
  und Browser-Endpunkte (`/status`, `/documents/{id}/view` — session-
  authentifiziert).
- `KiScannerService` — Lauf-Verwaltung, Spiegel-Semantik, Dokument-Validierung
  (nur PDF, Magic-Bytes, 12-MB-Limit), Status-Aggregat für Kachel.
- Entities: `KiSignalEntity` (ki_signals), `KiDocumentEntity` (ki_documents,
  PDF als BLOB wie account_documents), `KiSyncRunEntity` (ki_sync_runs).
- `SecurityConfig` — die fünf POST-Pfade + `/ping` freigegeben (exakte Pfade,
  ohne Wildcard, damit `/documents/{id}/view` geschützt bleibt).
- Kachel in `dashboard.html` (Muster News-Kachel, 30-s-Refresh) und Seite
  `kiscanner.html` mit Chart.js; Doku dort: `Doku/MqlKiScanner_Integration.md`.
- Tests: `KiScannerApiControllerTest` (11 Tests: Key-Pflicht, Handshake-
  Validierung, Komplettlauf, Spiegel-Löschung, PDF-Validierung, Session-
  Schutz der Browser-Endpunkte).

## 7. Sicherheit

- Key nur im Header, nur im secrets_store; Server protokolliert fehlgeschlagene
  Anmeldungen (ClientErrorLog) wie bei EAs.
- Der Sync-User braucht **keine** Account-Freigaben im Tradeserver — die
  KiScanner-Endpunkte prüfen nur den Key.
- PDFs werden serverseitig auf Magic-Bytes geprüft und ausschließlich inline
  mit `X-Content-Type-Options: nosniff` ausgeliefert; die Ansicht erfordert
  eine eingeloggte Browsersitzung.
- Grenzen: Server validiert max. 12 MB je Dokument; nginx (monitor.tnickel-ki.de,
  `client_max_body_size 200m`) ist großzügiger — der Scanner-Cap von 8 MB
  bleibt als Reserve für den Base64-Overhead (~33 %) bestehen.
- Produktiv-URL des Monitors: **https://monitor.tnickel-ki.de** (proxyt alles
  auf 8080). Andere Domains auf dem Server (z. B. die Homepage) geben nur
  eine Pfad-Allowlist frei — dort antwortet `/api/kiscanner` mit nginx-404,
  das ist kein Fehler der Integration.

## 8. Betrieb & Known Issues

- Server lokal starten: Eclipse/`java -jar` (Port 8080); Deploy wie gehabt
  (`.agents/workflows/deploy.md`, WildFly/ROOT.war). **Tests auf dieser
  Maschine mit JDK 21 laufen lassen** (`JAVA_HOME=C:\Program Files\Java\jdk-21`) —
  das JDK 25 lässt Mockitos Byte Buddy scheitern (Umgebungsproblem, unabhängig
  von dieser Erweiterung).
- Erster Sync nach Deploy: H2 legt die drei ki_-Tabellen automatisch an
  (ddl-auto=update).
- Ein abgebrochener Lauf lässt den letzten vollständigen Stand am Server
  stehen; „verbunden“ zeigt die Kachel erst nach einem vollständigen Lauf.
