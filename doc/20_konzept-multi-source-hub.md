# 20 — Konzept: Multi-Source-Hub (Signale über Datenquellen-REST)

Stand: 27.09.2026. Status: **in Umsetzung, Stufe 1** (MqlDownloader als erste
Datenquelle). Nutzer-Entscheidungen von 27.09.2026 sind als solche markiert.

## 1. Zielbild

Der SignalKiScanner wird vom MQL5-Direkt-Crawler zum **Hub für beliebig viele
Datenquellen**: Jede Quelle (heute der MqlDownloader, später weitere Downloader
für andere Signal-Börsen) stellt einen kleinen REST-Vertrag bereit — Katalog,
Tradelisten, Kennzahlen, Abonnenten-Verlauf, Testreport-PDFs. Der Scanner
konfiguriert beliebig viele Quellen, ruft sie nacheinander ab und stellt alle
Signale in **einer gemeinsamen Liste** mit sichtbarer Herkunft dar.

Das eigenständige Holen von mql5.com (Crawler, Exporter, Browser-Fallback)
fällt auf Dauer weg (Nutzer-Entscheidung 27.09.2026: „den Teil, dass du
selbständig von MQL5 was holst, rauswerfen und nur noch vom Downloader per
REST holen"). Übergangsweise bleibt der Direktweg als Modus erhalten
(`listen_modus`, siehe Abschnitt 6) — kein Big-Bang, kein Bruch im Betrieb.

## 2. Nutzer-Entscheidungen (fest)

1. **Stop-Loss ohne Nachweis:** Kommt aus einer Quelle kein SL (z. B. weil der
   Export keine S/L-Spalte hat), kann und wird keiner „angefordert". Die
   **spätere Analyse** (Tiefenanalyse/LLM) muss aus dem Tradingverhalten der
   Trades schließen, ob wohl ein SL drin ist. „Kein Nachweis" ist NEUTRAL
   (kein Nachteil — die meisten Broker übertragen keinen SL; Nutzer-Regel
   28.09.2026: kein Score-Malus, keine Ampel-Sperre, keine Matrix-
   Abwertung; nur die KI darf begründet abwerten).
2. **Initial Deposit:** Der Downloader stellt künftig den Initial Deposit der
   Signalseite über `/metrics` bereit (Erweiterung im MqlDownloader). Bis dahin
   laufen Quellen-Signale ohne Kapitalbasis-Regel (Vorprüfung) — die harte rote
   Regel greift erst mit Belieferung.
3. **Quellen-Kürzel:** Jede Datenquelle hat ein kurzes, eindeutiges Kürzel
   (z. B. `mql5`, `pelik`). Die Ergebnisliste zeigt immer, woher ein Signal
   kommt (Nutzer-Wunsch: „ich will ja auch sehen in der Liste, woher die
   Signale kommen").
4. **Tagesfrische genügt:** Die Daten sind so frisch wie der Lauf der Quelle
   (1×/Tag je Quelle ist ausdrücklich ausreichend).
5. **MPDD-Filter im Downloader ist gewollt:** Der Downloader sortiert ganz
   schlechte Strategien (3MPDD < 0,5) selbst aus. Der Scanner sieht bewusst
   nur das, was die Quellen liefern — die Ampelverteilung verschiebt sich
   dadurch Richtung 🟢/🟡; echte 🔴-Analysen über Ausgesonderte entfallen.
6. **Konfiguration komfortabel:** REST-Punkte werden in der GUI (Admin →
   Datenquellen) gepflegt — hinzufügen, bearbeiten, (de)aktivieren, löschen —
   inkl. **Connection-Test mit Ampel** (🟢 erreichbar / 🟡 eingeschränkt /
   🔴 nicht erreichbar). Gespeichert wird in der Datenbank, Tokens getrennt
   im Secrets-Speicher (nie im Repo).

## 3. Datenmodell

### 3.1 Tabelle `datenquellen`

| Feld | Bedeutung |
|---|---|
| `id` | interner Schlüssel (AUTOINCREMENT) |
| `kuerzel` | eindeutiges Kürzel (z. B. `mql5`) — erscheint in der Liste |
| `name` | Anzeigename (z. B. „MqlDownloader lokal") |
| `base_url` | REST-Basis (Host:Port genügt; `/api/v1` wird ergänzt) |
| `typ` | Protokoll-Version der Quelle — bisher `mql5-downloader-v1` |
| `aktiv` | 0/1 — nur aktive Quellen werden abgerufen |
| `angelegt_am` | Zeitpunkt der Anlage |
| `letzte_pruefung` | JSON des letzten Connection-Tests (Status, Details, Zeit) |

Token je Quelle im Secrets-Speicher unter `datenquelle_{id}_token`.

Migration beim Start: Stand die bisherige Einzelkonfiguration
(`downloader_base_url` in app_settings.json), wird automatisch genau eine
Quelle mit Kürzel `mql5` angelegt (Token wird übernommen). Alle Bestands-
Signale erhalten `signals.quelle='mql5'` — sie stammen aus der MQL5-Welt.

### 3.2 `signals.quelle`

Stufe 1 bewusst einfach: `signals` bekommt eine Spalte `quelle` (Kürzel der
Börsen-Welt, Default `mql5`). `signal_id` bleibt Primärschlüssel — MQL5-IDs
sind global eindeutig, und dasselbe MQL5-Signal über zwei Downloader-Spiegel
ist semantisch dasselbe Signal (erste/primäre Quelle gewinnt, Daten via
INSERT-OR-UPDATE idempotent). Erst wenn eine **zweite Börsen-Welt** mit
eigenem ID-Raum dazukommt, wird der Schlüssel auf `(quelle, signal_id)`
verbreitert (Stufe 2, siehe Abschnitt 7) — inkl. aller abhängigen Tabellen
(trade_files, forensik, analyses, subscriber_history, downloader_reports,
ampel_verlauf, ampel_wechsel, Dossiers) und der Ausschlussliste
`known_signals.json`.

### 3.3 Tabelle `quellen_artefakte`

Ingest-Cache je Quelle und Signal: `(quelle_id, signal_id, version, art)`
→ `sha256`, `path`, `fetched_at` mit `art ∈ {trades, metrics}`. Unveränderte
Artefakte (gleicher SHA) werden nicht erneut verarbeitet — dasselbe
Delta-Prinzip wie beim Betreuer-Agenten.

## 4. REST-Vertrag (Typ `mql5-downloader-v1`)

Genutzt werden die bestehenden Endpunkte des MqlDownloader (Doku:
`MqlDownloader/doc/REST_API_Dokumentation.md`):

| Zweck | Endpunkt |
|---|---|
| Verbindung/Version/**Instanz-Kennung** | `GET /health` (Feld `instance` — Standard: Rechnername des Downloaders, im Setup-Dialog frei wählbar; der Scanner zeigt sie je Quelle und warnt bei Doppelung unter zwei Quellen = Verwechslungsschutz) |
| Katalog (Kandidaten) | `GET /providers` (paginiert; `total`, `items[].links`) |
| Trades roh | `GET /providers/{id}/{version}/trades.csv` (Original-mql5-CSV) |
| Kennzahlen | `GET /providers/{id}/{version}/metrics` (Balance, EquityDrawdown, MaxDDGraphic, 3MPDD, monthProfits …) |
| Abonnenten-Verlauf | `GET /providers/{id}/{version}/history` |
| Testreport-PDFs | `GET /providers/{id}/{version}/reports` |

### 4a. PelicanTrading — zweite Börse (implementiert 27.09.2026)

PelicanTrading (`SIGNALDOWNLOADER/PelicanTrading`, „PelicanMonitor”) spricht
**dasselbe Protokoll** mit Versions-Kürzel **`pelican`** (Port 8090, Autostart,
`data/rest_api.json`, Instanz-Kennung wie beim MqlDownloader). Der Scanner
brauchte dafür nur: `platform_version("pelican")` → `pelican` und die
Plattform-Durchreichung im Ingest — kein eigener Quell-Typ nötig.

Abweichungen gegenüber MQL5-Quellen (bewusst, Server-Doku „REST-API für den
SignalKiScanner"):

| Thema | Pelican-Lage | Folge im Scanner |
|---|---|---|
| Trades | positionell (Open+Close je Zeile), serverseitig ins mql5-CSV konvertiert (Zeitstempel mit Punkten) | Forensik läuft unverändert |
| Kontowährung | **gemischt** (USD, USC, EUR, JPY …), seit 28.09.2026 **serverseitig nach USD umgerechnet** (siehe 4a.1) | `trades.csv` für alle Konten; Forensik rechnet USD wie gehabt |
| Initial Deposit | nicht verfügbar; seit 28.09.2026 zusätzlich `InitialDepositVirtual` (siehe 4a.1) | Kapitalbasis-Regel ruht weiter — **Virtual NICHT in den Abgleich speisen** |
| Stop-Nachweis | StopPrice nur bei offenen Positionen | Historie ohne SL → „kein Nachweis" + Verhaltensanalyse (§2.1) |
| Signalalter | `weeks` im Katalog | Wochen-Vorfilter greift erstmals für Quellen-Signale |
| Abonnenten | Copiers + Historie (copier_historie) | 7/30-Tage-Bilanz wie bei MQL5 |

#### 4a.1 Pelican-Resterweiterung 28.09.2026 (Währungsumrechnung, virtuelle Einlage)

Der PelicanMonitor liefert seit dem 28.09.2026 zusätzliche, **additive**
Felder (Protokoll `mql5-downloader-v1` unverändert — kein bestehendes Feld
geändert oder entfernt; der Ingest läuft ohne Anpassung weiter):

**Währungsumrechnung** — `trades.csv` und `metrics` sind jetzt für ALLE
Kontowährungen verfügbar, Geldbeträge serverseitig in USD:

- USD unverändert; **USC (US-Cent) fix ÷ 100**; alle anderen Währungen per
  **EZB-Referenzkurs** (frankfurter.dev, je Währung gecacht in
  `data/fx_rates.json` der Downloader-Seite).
- Skaliert werden nur Geldbeträge (Profit in `trades.csv`; Balance, Equity,
  CopiersAum, CopiersProfit\* in `metrics`), centgerundet; Preise und Mengen
  bleiben original. Ein einheitlicher Kurs je Provider verzerrt keine
  Verhältnisse — Profit-Faktor, Drawdown-%, Exposure-vs-Balance der Forensik
  sind invariant.
- Kennzeichnung (additiv, der Scanner ignoriert sie heute):
  - `metrics.CurrencyNote` — Klartext, z. B. „US-Cent-Konto: 1 USC = 0,01 USD
    (fixer Umrechnungskurs)" oder „… EZB-Referenzkurs (frankfurter.dev) vom
    2026-09-25, einheitlich auf alle Werte angewandt"
  - `metrics.CurrencyRateToUsd`, `metrics.CurrencyRateDate`,
    `metrics.CurrencyConvertedToUsd` (maschinenlesbar)
  - Katalog `items[].currencyNote` (ohne Kursabruf, nur Kennzeichnung;
    US-Cent-Konten ausdrücklich markiert)
- Offline ohne jemals gecachten Kurs: `trades.csv` 404 + Grund (Scanner
  überspringt wie bisher), `metrics` liefert Geldfelder `null` statt
  Fremdwährungsbeträge fälschlich als USD.

**Virtuelle Einlage** — `metrics.InitialDepositVirtual: 10000.0` plus
`InitialDepositVirtualNote` („Annahme, kein Plattformwert"). Das echte
`InitialDeposit` bleibt **bewusst weg**: `_kapitalbasis_abgleich` gleicht
eine injizierte Kapitalbasis Cent-genau gegen die Web-Balance ab — ein
virtueller Wert würde JEDEM Pelican-Signal „Kapitalbasis unbestätigt"
geben. `InitialDepositVirtual` ist nur für eine bewusste spätere Nutzung
gedacht (z. B. Anzeige/Filter), niemals als `initial_deposit_usd` in den
Abgleich.

**Erweiterter `metrics`-Satz** (28.09.2026, ebenfalls additiv): `Equity`,
`Leverage`, `MinTradesPerMonth`, `MaxTradesPerMonth`, `MarketsCount`,
`TopMarkets`, `CopiersAum`, `CopiersProfitYear`, `CopiersProfitMonth` —
Quelle sind die Strategy-Stats (`/api/strategies/{id}/stats`), die im
PelicanMonitor seit 28.09.2026 zuverlässig geladen werden (vorher wurden sie
technisch verworfen, `metrics` war faktisch leer — bei Cache-Zweifeln also
Artefakt-SHAs der Quellen erneuert abfragen).

**Eigene KI-Risikoberichte im PelicanMonitor** (28.09.2026, nur Monitor-
Feature): der Monitor erzeugt selbst GLM-Berichte je Provider (MD+PDF unter
`data/reports/`, Risiko-Score 1–10, Index `data/llm_reports.json`; Altberichte
mit dem neuen validierten Score-Schema zurückgesetzt). Das ist eine EIGENE
KI-Schicht des Monitors — unabhängig vom LLM-Layer des Scanners und von
dessen Ampel/Score; `/reports` liefert weiterhin eine leere Liste, der
Dokumente-Spiegel des Scanners zeigt also noch nichts. Sobald der Monitor
`/reports` füllt, spiegelt der Scanner die PDFs automatisch (bestehender
Sync, kein Adapter nötig).

### 4b. RoboMonitor (RoboForex) — dritte Quelle (implementiert 27.09.2026)

Der RoboMonitor (`SIGNALDOWNLOADER/roboforex`, RoboForex-CopyFX) spricht
dasselbe Protokoll mit **Version je Plattform**: `mql4` für MT4-,
`mql5` für MT5-Signale (Port 8091, Autostart, `data/rest_api.json`,
Instanz-Kennung). Dadurch benötigt der Scanner **keinen eigenen Adapter** —
Kandidaten, Plattformanzeige (mt4/mt5) und Detail-Sync laufen unverändert;
Ende-zu-Ende per Regressionstest nachgewiesen (`test_roboforex_ende_zu_ende_…`).

Besonderheiten gegenüber den anderen Quellen:

| Thema | RoboForex-Lage | Folge im Scanner |
|---|---|---|
| Trades | MT4 positionell direkt; **MT5-Rohdeals serverseitig über IN/OUT-Paarung zu Positionen** (Commission/Swaps echt) | Forensik läuft unverändert |
| Währung | CopyFX rechnet durchgängig USD | kein Währungsfilter nötig |
| Drawdown | Zeitraum-DD und Gesamt-DD (`MaxDrawdownGesamtProzent`) | `EquityDrawdown` = Gesamt-DD (Fallback Zeitraum) |
| Ertrag | nur Yield % seit Start | `Average3MonthProfit` = Ø-Monatsrendite, serverseitig **hergeleitet** (Yield/Laufzeit) |
| Initial Deposit | nicht verfügbar (MinEinlage ≠ Startkapital) | Kapitalbasis-Regel ruht |
| Stop-Nachweis | keine SL-Daten | „kein Nachweis" + Verhaltensanalyse (§2.1) |
| Signalalter | `weeks` aus Startdatum | Wochen-Vorfilter greift |

### 4c. VantageMonitor — vierte Quelle (implementiert 27.09.2026)

Der VantageMonitor (`SIGNALDOWNLOADER/vantage`, Vantage-Copy-Trading) spricht
dasselbe Protokoll mit Versions-Kürzel **`vantage`** (Port 8092, Autostart,
`data/rest_api.json`, Instanz-Kennung). Scanner-seitig nur die
Plattform-Durchreichung (`pelican`-Muster); Akzeptanz per Regressionstest
(`test_vantage_ende_zu_ende_…`).

| Thema | Vantage-Lage | Folge im Scanner |
|---|---|---|
| Trades | deal-genau, bereits positionell (Open+Close) | direkte Konvertierung |
| Währung | USD direkt; **USC (US-Cent) serverseitig ÷100 nach USD normalisiert**; Drittwährung (EUR, GBP …) bleibt Kontowährung | trades.csv nur für USD/USC-Konten — sonst 404 + klarer Grund (Zulu-Muster, korrigiert 28.09.2026); `currencyCode` im Katalog zeigt die Währung |
| Symbole | Broker-Postfixe („XAUUSD.sc") | Server liefert Basis-Symbol (kontract_specs matchen) |
| Ertrag | **gemessene 30-Tage-Rendite** | `Average3MonthProfit` ohne Herleitung |
| Drawdown | nur Gesamt-DD | `EquityDrawdown` = |Gesamt-DD| |
| Abonnenten-Verlauf | kopierer.db: Tages-Snapshot je „Signale laden" (weekChange/monthChange im Katalog) | `/history` liefert Punkte; 7/30-Tage-Bilanz baut sich mit der Zeit auf |
| Initial Deposit / Balance | nicht verfügbar (AumUsd = Kopierer-Kapital) | beide Regeln ruhen |
| Stop-Nachweis | keine SL-Daten | „kein Nachweis" + Verhaltensanalyse (§2.1) |
| Signalalter | `weeks` aus Monaten | Wochen-Vorfilter greift |

### 4d. ZuluMonitor — fünfte Quelle (implementiert 27.09.2026)

Der ZuluMonitor (`SIGNALDOWNLOADER/zulumonitor`, ZuluTrade) spricht dasselbe
Protokoll mit Versions-Kürzel **`zulu`** (Port 8093, Autostart,
`data/rest_api.json`, Instanz-Kennung). Scanner-seitig nur die
Plattform-Durchreichung; Akzeptanz per Regressionstest
(`test_zulumonitor_ende_zu_ende_…`).

| Thema | ZuluTrade-Lage | Folge im Scanner |
|---|---|---|
| Trades | positionell (Open+Close), nur verifizierte Downloads (.meta) | direkte Konvertierung |
| Symbole | Paare mit Schrägstrich („EUR/USD") | Server liefert „EURUSD" |
| Währung | Trader-Kontowährung gemischt (149/200 USD) | trades.csv nur USD-Konten (404 + Grund), currencyCode im Katalog |
| Abonnenten-Historie | nicht verfügbar | history leer (7/30-Tage-Bilanz bleibt leer, kein Fehler) |
| Drawdown | Gesamt-DD und Max-DD getrennt | EquityDrawdown = Gesamt-DD, MaxDDGraphic = Max-DD |
| Ertrag | nur Gesamt-ROI | Average3MonthProfit hergeleitet (ROI/Laufzeit) |
| Demo-Trader | gekennzeichnet | `demo:true` im Katalog, keine Vorauswahl |
| Initial Deposit / Balance | nicht verfügbar | beide Regeln ruhen |
| Stop-Nachweis | keine SL-Daten | „kein Nachweis" + Verhaltensanalyse (§2.1) |

**Bewertet wird, was der Scanner selbst aus der Trades-CSV rechnet**
(Design-Regel 1: Code rechnet, LLM interpretiert) — die Downloader-Metriken
dienen nur als Ersatz für die wegfallende MQL5-Kennzahlenseite:

| Scanner-Feld | Quellen-Mapping (Stufe 1) |
|---|---|
| `eq_dd_pct` | `metrics.EquityDrawdown`, Fallback `MaxDDGraphic` |
| `ertrag_monat_pct` | `metrics.Average3MonthProfit` |
| `abonnenten` | Katalog `subscribers` |
| `kapitalbasis_usd` | **bisher nicht verfügbar** — bis Downloader-Erweiterung |

### Offene Verifikationspunkte (vor dem Abschalten des Direktwegs)

- **MT4-Orderbuch/S/L: BESTÄTIGT (27.09.2026, Live-Test).** Der MqlDownloader
  liefert bei MT4-Signalen die Orderbuch-CSV **mit S/L- und T/P-Spalte** samt
  Balance-Zeilen (belegt am Signal 2336904, 2222 Zeilen) — der Stop-Beweis
  („direct") bleibt für MT4-Quellen-Signale vollständig erhalten; der Parser
  kennt das Format (Orderbuch-Variante, Profit = Spalte 11).
- **Initial Deposit in `/metrics`** (Entscheidung 2): ohne ihn keine
  Kapitalbasis-Regel und kein Cent-genauer Abgleich für Quellen-Signale —
  **weiterhin offen** (MqlDownloader-Erweiterung). Pelican liefert seit
  28.09.2026 zusätzlich `InitialDepositVirtual` (Annahme 10.000 USD,
  siehe §4a.1) — das ist **kein** Ersatz und darf nie als
  `initial_deposit_usd` in den Abgleich.
- Vollständigkeit: nur Signale mit Downloader-Bestand (404 = überspringen).

## 5. Ingest (Stufe 1, implementiert)

`src/mqlkiscanner/ingest.py` — je aktiver Quelle, sequenziell:

1. **Katalog** paginieren (`limit/offset`) → Kandidaten im Pipeline-Format
   `{id, name, platform, url, abonnenten, wochen: None, quelle_kuerzel, …}`.
   `wochen=None` lässt den Wochen-Vorfilter bewusst durch (der Katalog kennt
   das Signalalter nicht).
2. **Trades** je Kandidat: `trades.csv` laden → SHA gegen `quellen_artefakte`
   → unverändert = keine weitere Verarbeitung; geändert = neue Cache-Datei
   unter `data/quellen/{kürzel}/…` und neuer Artefakt-Satz.
3. **Metrics** je Kandidat analog cachen (JSON).

Der Scan nutzt das über `listen_modus` (Abschnitt 6); die Analyse eines
Quellen-Kandidaten liest die Trade-CSV aus dem Quellen-Cache statt über den
MQL5-Exporter — Forensik-Batterie, Scoring, Ampel und Berichte laufen
unverändert darüber.

## 6. Übergang: `listen_modus` (hybrid)

Neue Einstellung auf der Scan-Seite: **Signale holen aus**

- `mql5` (Default, bisheriges Verhalten): MQL5-Listen per Crawler,
  Kennzahlen/Exporte direkt von mql5.com,
- `quellen`: Kandidaten + Trades + Metrics ausschließlich aus den
  konfigurierten Datenquellen (kein MQL5-Kontakt),
- `beides`: Vereinigung — bei Doppelung gewinnt der MQL5-Direkteintrag
  (vollständigere Kennzahlen), die Quelle ergänzt.

Sobald Initial Deposit geliefert wird und die MT4-S/L-Frage geklärt ist,
wird `quellen` zum Standard und der Crawler-Teil anschließend entfernt
(Stufe 2+). Bis dahin bleibt alles Verhalten wie bisher, wenn der Modus
nicht umgestellt wird.

## 7. Ausbaustufen

1. ✅ **Stufe 1 (27.09.2026):** Quellen-Registry + Admin-UI mit
   Connection-Test-Ampel, Ingest (Katalog/Trades/Metrics), `listen_modus`,
   Quellen-Kürzel in der Ergebnisliste und REST-API, Sync (Verlauf + PDFs)
   über alle aktiven Quellen.
2. **Stufe 2:** Composite-Identität `(quelle, signal_id)` inkl. Migration
   aller Fachtabellen; Betreuer-Agent bezieht sein Tages-Delta aus den
   Quellen statt aus dem MQL5-Export (Takt nach dem Downloader-Lauf).
3. **Stufe 3:** Crawler/Exporter/Browser-Fallback entfernen; MQL5-Credentials
   nur noch im Downloader (Sicherheitsgewinn; mql5.com sieht nur noch die
   Downloader als Abrufer).
4. **Stufe 4:** Quell-Typen für weitere Börsen (`typ`-Feld) mit Adaptern,
   die auf das interne Kandidaten-/CSV-Format normalisieren; Kontrakt-Specs
   (`data/contract_specs.json`) um deren Symbole erweitern.

## 8. Was sich bewusst NICHT ändert

- Ampel/Score/Urteil kommen weiter ausschließlich aus der Engine — Quellen
  liefern Daten, nie Bewertungen.
- Downloader-Abgleich (Verlauf, PDFs) bewertet nie neu.
- REST-API (:8611) für den MqlRealMonitor bleibt schreibgeschützt; das
  `quelle`-Feld kommt abwärtskompatibel hinzu.
- Tradeserver-Sync, PDF-Berichte, Ampel-Verlauf, Agenten-Postfach unverändert.
