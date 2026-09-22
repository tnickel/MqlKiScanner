# Bauplan: Autonomer Agentenbetrieb (LLM-Orchestrator)

**Status: Konzept/Bauplan — beschlossen am 22.09.2026, noch nichts implementiert.**
Entstanden aus drei Konzeptrunden (Recherche: Projekt, Datenbasis, PDF-Berichte,
Backtester-Projekt `D:\AntiGravitySoftware\GitWorkspace\Backtester`).

---

## 1. Ziel

Die manuelle Arbeit am MqlKiScanner — Scans starten, Signale beobachten,
Berichte lesen, auf Änderungen achten — wird durch **autonom arbeitende
LLM-Einheiten** ersetzt. Die Einheiten:

- machen regelmäßig Scans (Daily-Delta, wöchentlich Gelb/Grün, monatlich Full),
- beobachten den Markt (Kursdaten aus dem MetaTrader des Nutzers),
- kennen die Handelsalgos der Signale (Algo-Profile, destilliert aus den
  Tiefenanalysen) und prüfen, ob die Signale noch wie beschrieben handeln,
- führen je Signal eine ständig wachsende Datenbasis (Dossier),
- bewerten, welche Trades seit dem letzten Blick hinzugekommen sind,
- melden Auffälligkeiten — ohne selbst jemals neu zu bewerten.

## 2. Feststehende Entscheidungen (22.09.2026)

| Thema | Entscheidung |
|---|---|
| Architektur | **Eigener Daemon-Prozess im selben Repo** (`python -m mqlkiscanner.agenten`), nutzt Pipeline/Forensik/DB als Bibliothek wie die Streamlit-App; ein Projekt, eine SQLite, getrennte Prozesse. Kein Extra-Programm über REST (Schreib-API wäre Angriffsfläche; SQLite ist eine Datei). |
| Rollen | **5 Rollen**: Dirigent, Marktbeobachter, Signal-Betreuer, Chefermittler, Melder (Abschnitt 4). |
| Standard-Modell | **GLM-5.3 (glm-5.3) für ALLE Rollen** (Nutzer-Vorgabe). `glm-5.3-flash` bleibt pro Rolle in der UI wählbar als Kostenschraube. Die bestehende Scan-Pipeline (Stufe 1 Flash / Stufe 2 Stark) bleibt davon unberührt. |
| Prompts | **6 Vorlagen** unter `config/prompts/agenten/`, einsehbar und editierbar wie die bestehenden Prompts (Reset auf Default, Platzhalter-Guard, Füllungstest ohne Token). Rohfassungen: Anhang A. |
| Trockenmodus | **Nein — gleich richtig.** Ersatz für den Trockenmodus ist die lückenlose Protokollierung (Abschnitt 11): jeder LLM-Schritt mit vollständigem Prompt und vollständiger Antwort nachlesbar. |
| Meldewege | **Nur Postfach in der App** (Seite „Agenten"). Kein E-Mail/Telegram/Push. |
| Taktung | Bestätigt: täglich Trade-Delta + Marktkontext; wöchentlich Gelb/Grün-Scan + Lagebericht; monatlich Full-Scan + Portfolio; ereignisgesteuerte Alerts. |
| Budget | Bestätigte Startwerte, in der UI stellbar: Agenten-Tagesbudget 500.000 Tokens, Agenten-Monatsbudget 5.000.000 (Abschnitt 10). Reguläre Scan-Läufe zählen auf ihr bestehendes Lauf-Budget. |
| Kursdaten | **Offizielles `MetaTrader5`-Python-Paket** (bereits installiert, v5.0.5735) gegen das MetaTrader-5-Terminal des Nutzers. Kein EA, kein INI-Start, kein KursExporter-Skript (Abschnitt 7). |
| Terminal | Terminal-Pfad **austauschbar in der Config**; ob der Daemon ein nicht laufendes Terminal selbst starten darf, ist ein Konfig-Schalter (Default: **nein** — Live-Terminal, Abschnitt 7.3). |

## 3. Architektur

```
┌────────────────────────────────────────────────────────────────┐
│ MqlKiScanner (ein Repo, zwei Prozesse)                         │
│                                                                │
│  Streamlit-App (wie bisher)          NEU: Agenten-Runner      │
│  ┌───────────────────────────┐         python -m               │
│  │ Scan · Ergebnisse · Admin │◄──SQLite─mqlkiscanner.agenten   │
│  │ NEU: Seite „Agenten“      │         │                       │
│  │  (Protokoll/Postfach/     │         ├─ Dirigent (Scheduler, │
│  │   Dossiers)               │         │   Scan-Steuerung)     │
│  └───────────────────────────┘         ├─ Marktbeobachter      │
│         │ REST 127.0.0.1:8611          │   └─► MetaTrader5-    │
│         ▼                             │      Paket (nur Lesen) │
│  MqlRealMonitor (unverändert)         │      → laufendes MT5-  │
│                                      │      Terminal (Kurse)   │
│  SQLite data/mqlkiscanner.db         ├─ Signal-Betreuer × N    │
│  (+ neue Agenten-/Dossier-Tabellen,  ├─ Chefermittler          │
│   8 bestehende Tabellen bleiben)     └─ Melder → Postfach      │
└────────────────────────────────────────────────────────────────┘
```

- Der Agenten-Runner ist ein **Daemon** (Dienst neben der App, überlebt
  App-Neustarts). Konfiguriert wird alles in der Streamlit-UI; der Daemon liest
  dieselben Settings (`config/app_settings.json`, keine Secrets) und Secrets
  (`secrets_store`).
- **Koordination mit der GUI:** Ein prozessübergreifendes Lauf-Lock (DB-Tabelle
  `agenten_laeufe` als Mutex plus Datei-Lock) verhindert, dass Agenten-Scan und
  manueller GUI-Scan sich gleichzeitig bei MQL5 und in der DB in die Quere
  kommen — Erweiterung des bestehenden `scan_worker`-Musters.
- **SQLite für zwei Prozesse:** WAL-Modus und `busy_timeout` aktivieren; alle
  Agenten-Tabellen sind append-only (gleiche Philosophie wie `ampel_verlauf`).

## 4. Die fünf Rollen

Alle Rollen: Standard-Modell **glm-5.3**, pro Rolle umstellbar (Abschnitt 8.1).
Keine Rolle bewertet jemals neu — neue Ampeln entstehen ausschließlich durch
reguläre Engine-Läufe, die der Dirigent anstößt (Grundregel wie beim
Downloader-Abgleich: Abgleich/Beobachtung ist nie Neubewertung).

### 4.1 Dirigent (Orchestrator)
- **Takt:** täglich (Wochentage) 06:30; wöchentlich So; monatlich 1. Werktag.
- **Aufgabe:** plant und steuert den Betrieb: weckt die Rollen nach Zeitplan,
  stößt Gelb/Grün- und Full-Scans über die bestehende Pipeline an, verwaltet
  Token-Budget und MQL5-Rate-Limit, respektiert das Lauf-Lock, überspringt
  Wochenenden/Feiertage (Forex geschlossen).
- **LLM-Anteil:** klein — der Ablaufplan ist Code (deterministisch). Das LLM
  entscheidet nur Randfragen (z. B. ungewöhnliche Lage einschätzen); seine
  Entscheidungen sind auf eine **Whitelist erlaubter Aktionen** begrenzt und
  werden vor Ausführung vom Code validiert. Pro Rolle abschaltbar
  („Dirigent ohne LLM").
- *Erlöst nebenbei das offene Roadmap-Item „Re-Scan als Kommandozeilenaufruf".*

### 4.2 Marktbeobachter
- **Takt:** täglich vor den Signal-Betreuern; zusätzlich ereignisgesteuert.
- **Aufgabe:** holt Kursdaten über das MetaTrader5-Paket (Abschnitt 7), lässt
  **Code** die Kennzahlen berechnen (Bewegung heute/7d/30d, Volatilität/ATR,
  Range, Trendrichtung, Abstand zu Hoch/Tief) und fasst mit dem LLM die
  Marktlage je Symbol in wenige Sätze (Prompt `markt_kontext`).
- **Output:** Marktkontext-JSON + Klartext (wird Input für Betreuer/Chef).

### 4.3 Signal-Betreuer (einer je 🟢/🟡-Signal)
- **Takt:** täglich je Signal (werktags).
- **Aufgabe:** holt den MQL5-Trade-Export (mit Rate-Limit), vergleicht den SHA
  gegen den letzten Snapshot: unverändert → nur Journal-Eintrag, **kein
  LLM-Aufruf**. Neue Trades → Delta-Forensik (Code) → Prompt `betreuer_delta`
  mit Algo-Profil + Delta-Kennzahlen + Marktkontext → Beobachtung mit
  Einordnung KONFORM / AUFFAELLIG / STILBRUCH / KEINE_NEUEN_TRADES.
  Bei STILBRUCH-Verdacht: erneute Prüfung mit max. Tokens (gleiche Vorlage,
  ausführlichere Antwort) und Alert an den Melder.
- **Sub-Aufgabe Profil-Destillation (einmalig je Signal):** aus Tiefenanalyse +
  Gesamtbericht ein kompaktes, versioniertes **Algo-Profil** erzeugen (Prompt
  `profil_destillation`) — inklusive explizit prüfbarer Konformitäts-Merkmale
  (Sessions, Lot-Verhalten, Haltezeiten, Stop-Disziplin), anhand derer spätere
  Deltas geprüft werden. Rückwirkend für alle bestehenden Signale möglich
  (47 Tiefenanalysen vorhanden).

### 4.4 Chefermittler
- **Takt:** wöchentlich (so) + monatlich.
- **Aufgabe:** Synthese über alle Dossiers + Marktkontext + Wechsel-Protokoll
  → **Lagebericht** (Prompt `lagebericht`): Wer verhält sich konform, wo
  drückt der Schuh, welche Signale sollten beim nächsten Gelb/Grün-Scan
  besonders genau geprüft werden, wann lohnt eine Tiefenanalyse-Erneuerung.
  Formuliert Handlungsvorschläge — entscheidet aber nichts und bewertet nichts
  neu (Engine bindend).

### 4.5 Melder
- **Takt:** sofort bei Ereignis; sonst täglicher Digest.
- **Aufgabe:** verdichtet Journal und Ereignisse zu Klartext-Meldungen ins
  **Postfach der App** (Prompt `meldung`): Alerts bei Ampelwechsel
  (`ampel_wechsel` als Auslöser — Fundament existiert schon), Stilbruch-Flag,
  Schrankenverletzung, Budget-Überschreitung, Terminal-/MQL5-Fehlern;
  Tagesdigest (3 Signale konform, 1 Auffälligkeit, Marktlage in einem Satz).

## 5. Prompt-Vorlagen (6 Dateien)

Pfad: `config/prompts/agenten/` — gleiche Verwaltung wie die bestehenden fünf
Prompts: Datei fehlt → Default wird angelegt; Admin-Editor mit
Speichern/Zurücksetzen; Platzhalter-Schutz und Füllungstest ohne Token
(`tests/test_prompt_fill.py` wird erweitert).

| Datei | Rolle | Platzhalter |
|---|---|---|
| `dirigent_planung.md` | Dirigent | `{lagestatus_json}`, `{zeitplan_json}` |
| `markt_kontext.md` | Marktbeobachter | `{kurse_json}`, `{symbole_json}` |
| `profil_destillation.md` | Betreuer (initial) | `{signal_name}`, `{signal_url}`, `{tiefenanalyse}`, `{gesamtbericht}`, `{forensik_json}` |
| `betreuer_delta.md` | Betreuer (täglich) | `{signal_name}`, `{profil_text}`, `{delta_json}`, `{marktkontext}`, `{letzte_beobachtungen}` |
| `lagebericht.md` | Chefermittler | `{dossiers_json}`, `{marktkontext_woche}`, `{ampel_wechsel_json}`, `{budget_status}` |
| `meldung.md` | Melder | `{typ}`, `{ereignisse_json}` |

Rohfassungen: **Anhang A**. Alle folgen dem Projekt-Stil: Zahlen werden nur
zitiert (Code rechnet), Engine-Ampel ist bindend, keine Emojis, keine
Anlageberatung, deutsch.

## 6. Datenmodell (neue SQLite-Tabellen, alle append-only)

```sql
CREATE TABLE IF NOT EXISTS agenten_laeufe (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle       TEXT NOT NULL,           -- dirigent|markt|betreuer|chef|melder
    start       TEXT NOT NULL,
    ende        TEXT,
    status      TEXT NOT NULL,           -- laeuft|ok|fehler|abgebrochen|skipped
    signal_id   INTEGER,                 -- optional
    zusammenfassung TEXT
);

CREATE TABLE IF NOT EXISTS agenten_schritte (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lauf_id     INTEGER REFERENCES agenten_laeufe(id),
    ts          TEXT NOT NULL,
    rolle       TEXT NOT NULL,
    schritt     TEXT NOT NULL,   -- llm|export|forensik_delta|scan|kursholen|lock
    prompt      TEXT,            -- bei llm: VOLLSTÄNDIG gefüllter Prompt
    antwort     TEXT,            -- bei llm: VOLLSTÄNDIGE Antwort
    modell      TEXT,
    tokens      INTEGER,
    dauer_s     REAL,
    status      TEXT NOT NULL,
    detail_json TEXT             -- maschinelle Details (SHAs, Zahlen, Fehler)
);

CREATE TABLE IF NOT EXISTS agenten_meldungen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    typ         TEXT NOT NULL,           -- alert|digest|lagebericht
    prioritaet  INTEGER NOT NULL DEFAULT 1,  -- 1=info 2=warnung 3=kritisch
    titel       TEXT NOT NULL,
    text        TEXT NOT NULL,
    quellen_json TEXT                    -- Verweise auf agenten_schritte-IDs
);

CREATE TABLE IF NOT EXISTS dossier_profil (
    signal_id   INTEGER NOT NULL,
    version     INTEGER NOT NULL,
    erstellt    TEXT NOT NULL,
    modell      TEXT,
    profil_json TEXT NOT NULL,   -- strukturierte Konformitäts-Merkmale
    profil_text TEXT NOT NULL,
    aenderungs_grund TEXT,
    PRIMARY KEY (signal_id, version)
);

CREATE TABLE IF NOT EXISTS dossier_beobachtungen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    einordnung  TEXT NOT NULL,   -- KONFORM|AUFFAELLIG|STILBRUCH|KEINE_NEUEN_TRADES
    text        TEXT NOT NULL,
    delta_ref   INTEGER,         -- → trade_deltas.id
    schritt_ref INTEGER          -- → agenten_schritte.id (LLM-Nachweis)
);

CREATE TABLE IF NOT EXISTS trade_deltas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    alt_sha256  TEXT,
    neu_sha256  TEXT NOT NULL,
    neue_trades INTEGER NOT NULL,
    delta_json  TEXT             -- maschinell berechnete Delta-Kennzahlen
);
```

Trade-Diffs sind dank der SHA-adressierten `data/trade_snapshots/` billig:
neuer Export laden → SHA vergleichen → nur bei Abweichung Delta berechnen.

## 7. Kursdaten-Anbindung: MetaTrader5-Paket (korrigierter Weg)

### 7.1 Interface
Das offizielle Python-Paket **`MetaTrader5`** von MetaQuotes (bereits auf dem
Rechner installiert, Version 5.0.5735; Windows-only — passt) verbindet sich
direkt mit dem Terminal. Für uns relevante Aufrufe — **ausschließlich
Lese-Funktionen**:

| Aufruf | Zweck |
|---|---|
| `initialize(path=…terminal64.exe)` | Verbindung zum Terminal (attach wenn läuft, sonst starten je Policy) |
| `terminal_info()`, `version()` | Status/Verbindungstest |
| `symbol_select(sym, True)` | Symbol in Market Watch aktivieren |
| `symbol_info_tick(sym)` | aktueller Kurs (Bid/Ask/Last) |
| `copy_rates_from_pos / copy_rates_range` | OHLCV-Bars (M15/H1/D1, Lookback) |
| `copy_ticks_from / copy_ticks_range` | Ticks, falls je benötigt |
| `shutdown()` | Verbindung trennen |

**Explizit NICHT angebunden:** `order_send`, `order_check`, `login` mit
Fremdzugangsdaten und alles Schreibende. Der Marktbeobachter handelt nie
(Projekt-Regel: Analyse, kein Order-Routing). Ein statischer Test
(`tests/test_mt5_readonly.py`) bewacht die Whitelist der erlaubten Aufrufe.

### 7.2 Warum nicht der Backtester-Weg (EA/INI)?
Der Backtester steuert den **Strategy Tester** per `[Tester]`-INI vollautomatisch
— für Backtests das richtige Muster. Für *Skript*-Autostarts gibt es aber keine
CLI-Unterstützung (im Backtester muss der DukaImporter manuell gestartet
werden). Für reine Kursdaten ist das offizielle Python-Paket der einfachere,
offiziell unterstützte Weg — kein EA, kein INI-Headless-Zirkus. Der frühere
Konzept-Baustein „KursExporter.mq5" ist damit **gestrichen**.

### 7.3 Betrieb & Konfiguration (eigner Admin-Bereich, Abschnitt 8.2)
- **Terminal-Pfad** austauschbar (Default
  `C:/Forex/Mt5/TickmillLifeMql5/terminal64.exe`).
- **Start-Politik-Schalter:** „Terminal selbst starten, falls nicht läuft"
  — Default **aus**. Grund: Live-Terminal; ein unüberwachter Start könnte
  dort laufende EAs/Signale aktivieren. Läuft das Terminal nicht, wartet der
  Marktbeobachter bis zum nächsten Intervall und der Melder vermerkt es im
  Digest. (Unter der Woche läuft das Terminal ohnehin meist.)
- **Symbol-Watchlist:** automatisch aus den 🟢/🟡-Signalen abgeleitet
  (deren `forensik.symbole`), manuell erweiterbar.
- Timeframes (M15/H1/D1), Lookback-Tage, Abrufzeit, Timeout.
- Wochenende: Forex/Gold geschlossen → Marktbeobachter überspringt Sa/So.

### 7.4 Verifikation V1 (offen, ~10 Minuten, mit Nutzer zusammen)
Attach-Test gegen das **laufende** Terminal: `initialize()` ohne Start,
`copy_rates_range("XAUUSD", …)` lesen, `shutdown()`. Klären: Admin-Rechte-/Bitness-Parität
(Python und Terminal müssen gleiche Rechteebene haben — bekannte Stolperfalle
des Pakets) und ob bei mehreren MT5-Installationen der richtige Pfad greift.
Ergebnis wird hier nachgetragen.

## 8. Grafische Oberfläche

### 8.1 Admin-Bereich „Agenten & LLMs"
- **Rollenkarten** (5): je Rolle Icon, Klartext-Beschreibung, Ein/Aus,
  Modell-Auswahl — **Default glm-5.3**, wählbar glm-5.3 / glm-5.3-flash /
  Freitfeld (OpenAI-kompatibel) —, Max-Tokens, Tagesbudget, Takt.
- **LLM-Profile** (Anbieter): „GLM (Z.ai)" vorinstalliert mit bestehendem Key
  aus dem Secrets-Store; spätere Profile (z. B. OpenRouter wie im Backtester)
  möglich. Keys nur im Secrets-Store.
- **Prompt-Editor** je Rolle: Textarea, Speichern/Zurücksetzen,
  Platzhalter-Liste, „geändert"-Markierung — exakt wie der bestehende
  Prompt-Bereich der App.
- **Globalschalter:** Agentenbetrieb Start/Stopp; Dirigent „ohne LLM"-Option.
- Budget-Anzeige: Verbrauch heute/Monat gegen die Limits.

### 8.2 Admin-Bereich „Marktdaten (MetaTrader)"
Terminal-Pfad, Start-Politik, Symbol-Watchlist (Auto + manuell), Timeframes,
Lookback, Abrufzeit, Timeout, **Verbindungstest-Button** (attach auf laufendes
Terminal, eine Bar-Reihe lesen, Ergebnis anzeigen — analog zum
Downloader-Verbindungstest).

### 8.3 Seite „Agenten" (Beobachtung — das Fenster zu den LLMs)

```
┌ Agenten ────────────────────────────────────────────────────────┐
│ [Live]   [Protokoll]   [Postfach (3)]   [Dossiers]              │
│ ── Live ────────────────────────────────────────────────────────│
│ 🟢 Dirigent        06:30  Tagesplan erstellt (7 Aktionen)       │
│ 🟢 Markt           06:35  6/6 Symbole, XAUUSD +0,4 % / ATR 18,2 │
│ 🟢 Betreuer        06:45  Gold Spike: 2 neue Trades → KONFORM   │
│ 🟡 Betreuer        06:52  KiraCat: keine neuen Trades           │
│ …                                                                │
│ ── Protokoll (Filter: Rolle/Signal/Tag) ─────────────────────── │
│ ▸ 06:47 Betreuer · Gold Spike · glm-5.3 · 3.812 Tok · 41 s      │
│    [gefüllter Prompt vollständig]  [Antwort vollständig]        │
│ ▸ 06:35 Markt · glm-5.3 · 1.204 Tok · 9 s   …                   │
└──────────────────────────────────────────────────────────────────┘
```

- **Live:** welche Rolle arbeitet woran (gleiche Philosophie wie das
  Aktivitätsbanner — sichtbar, WAS läuft).
- **Protokoll:** chronologische Liste **jedes** LLM-Aufrufs, aufklappbar mit
  vollständigem gefülltem Prompt und vollständiger Antwort, Modell, Tokens,
  Dauer, Status. Auch Code-Schritte (Export, Delta, Lock) erscheinen als
  Einträge. Nichts wird gekürzt — alles, was ein LLM sagt, steht im Protokoll.
- **Postfach:** Alerts + Digests + Lageberichte mit Quellenverweisen
  (Sprung zum auslösenden Schritt).
- **Dossiers:** je Signal Algo-Profil (Version + Historie), Trade-Chronik,
  Beobachtungen, Ampel-Verlauf.

## 9. Betriebsrhythmus

| Wann | Wer | Was |
|---|---|---|
| Werktag 06:30 | Dirigent | Tagesplan: Budget/Locks/Feiertag prüfen, Rollen wecken |
| 06:35 | Marktbeobachter | Kursdaten holen (Policy beachten), Marktkontext erzeugen |
| 06:45 | Betreuer ×N | je 🟢/🟡-Signal: Export → SHA-Diff → ggf. Delta-Forensik + Bewertung |
| 07:10 | Melder | Tagesdigest ins Postfach |
| Sonntag | Chefermittler | Wochen-Lagebericht aus Dossiers + Wechsel-Protokoll |
| Sonntag | Dirigent | Gelb/Grün-Scan anstoßen (bestehender Ablauf, alle LLM-Stufen — Nutzer-Vorgabe bleibt) |
| 1. Werktag/Monat | Dirigent | Full-Scan + Portfolio anstoßen |
| jederzeit | Melder | Alert bei Ampelwechsel, STILBRUCH, Schrankenverletzung, Budget-/Terminalproblemen |

Regeln: Wochenenden/Forex-Schließung → Markt/Delta überspringen; Lauf-Lock
ggg. GUI-Scans respektieren; MQL5-Rate-Limiter gilt für jeden Agenten-Export
(ToS-Risiko bleibt bestehen — Pausen zwischen Signalen einhalten).

## 10. Budget und Kostensteuerung

- **Agenten-Tagesbudget:** 500.000 Tokens (alle Rollen zusammen).
- **Agenten-Monatsbudget:** 5.000.000 Tokens.
- Reguläre Scan-Läufe (Gelb/Grün, Full) nutzen weiterhin ihr bestehendes
  `llm_max_total_tokens` je Lauf und zählen **nicht** ins Agenten-Budget.
- Der Dirigent prüft vor jedem LLM-Aufruf das Budget; bei Erschöpfung werden
  LLM-Schritte übersprungen und **gemeldet** (kein Absturz) — Code-Schritte
  (Export, Delta, Forensik) laufen budgetfrei weiter.
- Größte Sparregel bleibt: **keine neuen Trades → kein LLM-Aufruf.**

## 11. Protokoll und Nachvollziehbarkeit (Audit statt Trockenmodus)

Der Nutzer hat bewusst auf einen Trockenmodus verzichtet — Voraussetzung ist
lückenlose Transparenz:

1. **Jeder LLM-Aufruf** wird als `agenten_schritte`-Eintrag mit vollständigem
   gefülltem Prompt, vollständiger Antwort, Modell, Tokens und Dauer
   gespeichert (append-only).
2. **Jeder Code-Schritt** (Export, SHA-Diff, Delta-Forensik, Scan, Lock)
   erscheint als Schritt mit `detail_json` (SHAs, Zahlen, Fehler).
3. **Jede Meldung** verweist auf ihre Quellschritte (klickbarer Nachweis).
4. Die UI filtert nach Rolle/Signal/Tag; alte Einträge werden nie geändert.
5. Ampel-relevante Ereignisse laufen ohnehin über die bestehenden
   append-only-Tabellen (`ampel_verlauf`/`ampel_wechsel`).

## 12. Sicherheit und Robustheit

- Secrets ausschließlich über `secrets_store` (Env → `.env` →
  `secrets.local.json`); MQL5-Credentials bleiben außerhalb jedes LLM-Kontexts.
- MetaTrader5-Paket nur mit Lese-Whitelist (Abschnitt 7.1, bewacht durch Test).
- MQL5-Zugriffe nur über die bestehende Session mit Rate-Limit.
- Daemon: sauberes Shutdown (SIGTERM/KeyboardInterrupt), hängt gebliebene
  Läufe werden als `fehler` geschlossen; Neustart übernimmt den Zustand aus DB.
- SQLite: WAL + busy_timeout + kurze Transaktionen (bestehendes Muster).

## 13. Phasenplan

### Phase A — Fundament — ✅ abgeschlossen (22.09.2026)
Daemon + Scheduler + Lauf-Lock, Journal-Tabellen, Admin-Bereich „Agenten &
LLMs" (GLM-5.3 vorkonfiguriert), Seite „Agenten" mit Live/Protokoll.
CLI-Re-Scan als Nebenprodukt.
**Abnahme: Ein Dirigent-Tageslauf ist im Protokoll vollständig nachlesbar;
Start/Stopp und Rollen-Konfiguration funktionieren über die UI.**
Umgesetzt: `src/mqlkiscanner/agenten/` (journal, lock, rollen,
rollen_prompts, dirigent, scheduler, daemon, admin_tab, `__main__`),
`app_pages/agenten.py`, Admin-Tab „Agenten", 6 Rollen-Prompts unter
`config/prompts/agenten/`, 46 neue Tests (Gesamt: 812 grün).
Ende-zu-Ende verifiziert: Daemon-Start (PID/Trennung/Logfile), Herzschlag,
Dirigent-Tageslauf mit LLM-Whitelist-Entscheidung im Protokoll, kooperativer
Stopp. Dirigent-Default max_tokens 8192 (glm-5.3 braucht Reasoning-Spielraum
auch für kleine JSON-Antworten — 2048 brach mit finish_reason=length ab).
CLI: `PYTHONPATH=src python -m mqlkiscanner.agenten [--once|--tick]`.

### Phase B — Dossiers & Trade-Delta — ✅ abgeschlossen (22.09.2026)
Dossier-Tabellen, Profil-Destillation (rückwirkend für alle 🟢/🟡 + Watchlist),
täglicher Betreuer-Lauf mit SHA-Diff, `betreuer_delta`, STILBRUCH-Flag.
**Abnahme: Jedes 🟢/🟡-Signal hat ein Dossier; ein Tag mit neuen Trades
erzeugt je Signal eine Beobachtung im Protokoll.**
Umgesetzt: `agenten/dossier.py`, `agenten/delta.py` (Zeilen-Diff über
Feld-Schlüssel + maschinelle Delta-Kennzahlen), `agenten/destillation.py`
(ohne Tiefenanalyse/Gesamtbericht wird KEIN Profil erfunden — protokollierter
Skip), `agenten/betreuer.py` (Export über Rate-Limiter mit 20-h-Cache; SHA
unverändert ⇒ kein Modellaufruf), Dossiers-Tab auf der Agenten-Seite,
Scheduler-Takt Betreuer = Startzeit + 15 min, CLI `--betreuer`, 13 neue
Tests (Gesamt: 825 grün). Ende-zu-Ende verifiziert: echte Destillation
Gold Spike (Version 1, 6.067 Zeichen, alle 8 Abschnitte inkl.
Konformitäts-/Warn-Merkmalen); Delta-Prüfung mit 2 simulierten neuen
Trades auf Temp-DB-Kopie → EINORDNUNG KONFORM, Begründung zitiert
Profil-Merkmal-Nummern, Beobachtung verlinkt auf den LLM-Schritt.

### Phase C — Marktbeobachter — ✅ abgeschlossen (22.09.2026, ein Punkt offen)
Admin-Bereich „Marktdaten", MetaTrader5-Anbindung (nur Lesen), Marktkontext,
Einbindung in Betreuer- und Chef-Prompts.
**Abnahme: Marktlage steht täglich im Protokoll; Betreuer-Beobachtungen
zitieren den Marktkontext.**
Umgesetzt: `agenten/marktdata.py` (Whitelist statisch getestet — nur
initialize/terminal_info/version/last_error/symbol_select/copy_rates_*/
shutdown; Start-Politik Standard NEIN mit sauberem Skip), `agenten/markt.py`
(Rolle + Tabelle `markt_kontext`; Symbol-Beobachtungsliste aus 🟢/🟡-
Forensik + manuell; LLM-Lage mit maschineller Fallback-Fassung), Betreuer-
Prompt erhält `{marktkontext}` aus `kontext_heute()` und echte
`{letzte_beobachtungen}` aus dem Dossier, Admin-Bereich mit Verbindungstest,
Scheduler-Takt Startzeit + 5 min, CLI `--markt`, 14 neue Tests (Gesamt:
839 grün). E2E: synthetische Kurse + echtes LLM auf Temp-DB-Kopie —
LLM-Lage zitiert alle Kennzahlen, Betreuer-Antwort prüft im Kontext;
Produktions-CLI ohne Terminal = protokollierter Skip (Start-Politik).
**OFFEN: V1-Attach-Prüfung (Abschnitt 7.4) mit dem Nutzer** — Terminal
starten, Admin → Marktdaten → „Verbindung testen", Ergebnis hier nachtragen.

### Phase D — Melder & Alerts — ✅ abgeschlossen (22.09.2026)
Postfach, `agenten_meldungen`, Auslöser: `ampel_wechsel`, STILBRUCH,
Budget-/Terminal-/MQL5-Fehler; Tagesdigest.
**Abnahme: Ein künstlich ausgelöster Ampelwechsel (Test-DB) erzeugt einen
Alert mit Quellverweis.**
Umgesetzt: `agenten/melder.py` (alert/stilbruch_alert mit Journaleintrag
als Nachweis; Ampelwechsel-Watcher in jedem Scheduler-Tick, idempotent
über `melder_ampel_wechsel_id` in der Steuerung — GUI-Scan-Wechsel werden
beim nächsten Tick bemerkt; Tagesdigest mit LLM-Fassung und maschineller
Fallback-Meldung, verschiebt sich automatisch, solange ein Betreuer-Lauf
aktiv ist), Betreuer löst bei STILBRUCH den Sofort-Alert direkt aus,
Postfach-Tab auf der Agenten-Seite (Priorität 1/2/3, Quellen-Verweise),
Takt Startzeit + 40 min, CLI `--digest`, 10 neue Tests (Gesamt: 849 grün).
Abnahme verifiziert (E2E auf Temp-DB): Ampelwechsel 🟡→🔴 → Alert P3 mit
`ampel_wechsel#N`/`signal#N`-Quellen; echter LLM-Digest fasst Läufe,
Beobachtungen und Token-Budget des Tages zusammen.

### Phase E — Chefermittler & autonome Scan-Steuerung — ✅ abgeschlossen (22.09.2026)
Wochen-Lagebericht, Dirigent stößt Gelb/Grün- und Full-Scans selbst an.
**Abnahme: Ein kompletter Monat ohne einen manuellen Scan-Klick; alle
Schritte im Protokoll nachvollziehbar.**
Umgesetzt: `agenten/chef.py` (Lagebericht aus Dossier-Spitzen,
Wochen-Marktkontexten und Wechsel-Protokoll — Meldung `lagebericht` ins
Postfach; LLM mit maschineller Fallback-Fassung; wartet auf laufende
Scans) und `agenten/scan_launcher.py` (headless-Pipeline identisch zur
Scan-Seite inklusive Modus-Vertrag und Fail-Fast; Tages-/Monats-Merker;
Scan-Threads neben dem Scheduler-Herzschlag; Abschluss-Meldung ins
Postfach). Takte: Sonntag 12:00 Gelb/Grün; 1. Werktag des Monats
Full-Scan; Chef sonntags ab 18 Uhr + am Full-Scan-Tag. CLI `--chef`,
`--scan`. 12 neue Tests (Gesamt: 861 grün). Orchestrierung mit
Fake-Pipeline verifizert; E2E-Lagebericht mit echtem LLM auf Temp-DB
(15 Dossiers korrekt verdichtet, Budget-Zitate stimmen). Die
Monats-Abnahme bestätigt sich mit dem ersten vollständigen autonom
durchlaufenen Monat (Start: nächster Sonntag bzw. 1. Werktag).

Je Phase: pytest (Unit + AppTest für die neuen UI-Teile), Doku-Nachzug
(README-Index, Benutzerhandbuch, Architektur), Commit + Push auf main.

## 14. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Token-Kosten (glm-5.3 überall) | Tages-/Monatsbudget, „keine neuen Trades → kein LLM-Aufruf", Flash pro Rolle wählbar |
| MQL5-ToS / Accountsperre | bestehender Rate-Limiter, Pausen zwischen Signalen, Export-Fenster streuen |
| SQLite-Schreibkonflikte (2 Prozesse) | WAL, busy_timeout, Lauf-Lock |
| MetaTrader5-Paket-Attach schlägt fehl (Rechte/Bitness/mehrere Terminals) | Verifikation V1 vor Phase C; Verbindungstest-Button; Melder-Information statt Stillstand |
| Unbeabsichtigter Terminal-Start | Start-Politik Default „nein"; Live-Terminal wird vom Daemon nie ohne Freigabe gestartet |
| LLM-Fehlleistung | Zahlen nur aus JSON zitieren; Dirigent-Entscheidungen whitelist-validiert; Engine-Ampel bindend; alles protokolliert |

## 15. Abgrenzung (Agenten tun das NIE)

- Keine Neubewertung von Ampeln/Urteilen/Scores (nur die Engine im regulären
  Scan bewertet — Nutzer-Grundregel).
- Kein Order-Routing, kein Eigenhandel, keine Order-Funktionen im
  MetaTrader5-Paket.
- Kein Überschreiben der append-only-Chroniken; keine Credentials im Prompt.
- Portfolio-Vorschläge/Urteile folgen weiterhin der Engine-Bindung
  (⛔/🔴 ⇒ Ablehnung).

---

## Anhang A — Prompt-Rohfassungen

*Startpunkte; finaler Wortlaut entsteht bei Implementierung in
`config/prompts/agenten/` und ist dort editierbar. Alle Platzhalter werden vom
Code gefüllt (Injection-Schutz wie bestehend).*

### A.1 `dirigent_planung.md`
```
# Dirigent — Tagesplanung (Agentenbetrieb)

Du steuerst den Betrieb des MqlKiScanner-Agentenbetriebs. Der Ablaufplan
selbst ist Code — du entscheidest nur Randfragen. Deine Antwort ist NUR
gültig als JSON-Objekt mit dem Schlüssel "aktionen" (Liste von Strings aus
der erlaubten Menge: "delta_laufen_lassen", "delta_ueberspringen",
"markt_holen", "markt_ueberspringen", "scan_gelb_gruen", "scan_full",
"meldung_schicken") plus "begruendung" (max. 30 Wörter). Erlaube niemals
Aktionen außerhalb der Menge. Zahlen stammen ausschließlich aus den Daten.

## Lagestatus (maschinell)
{lagestatus_json}

## Zeitplan (maschinell)
{zeitplan_json}
```

### A.2 `markt_kontext.md`
```
# Marktbeobachter — Marktlage je Symbol (glm-5.3)

Du bist Marktbeobachter eines MQL5-Signal-Scanners. Dir liegen ausschließlich
maschinell berechnete Kurskennzahlen vor — zitieren erlaubt, nichts
dazuerfinden, nichts selbst rechnen.

## Kurs-Kennzahlen (Code-berechnet)
{kurse_json}

## Beobachtete Symbole (Universum der 🟢/🟡-Signale)
{symbole_json}

## Aufgabe
Schreibe je Symbol 2–3 Sätze Marktlage (Bewegung, Volatilität, Trendlage,
besondere Ereignisse im Zeitfenster) und danach EINEN Gesamtabsatz
("Marktlage insgesamt"). Deutsch, sachlich, keine Emojis, keine
Anlageberatung. Max. 250 Wörter gesamt.
```

### A.3 `profil_destillation.md`
```
# Profil-Destillation — Algo-Profil für {signal_name}

Du destillierst aus vorliegenden Analysen ein kompaktes, PRÜFBARES
Handelsprofil des Signals {signal_name} ({signal_url}). Das Profil wird
später täglich gegen neue Trades geprüft — formuliere Merkmale so, dass man
Abweichung erkennen kann.

## Tiefenanalyse (KI, ausführlich)
{tiefenanalyse}

## Gesamtbericht (KI)
{gesamtbericht}

## Forensik der Engine (maschinell, maßgeblich)
{forensik_json}

## Ausgabe (Markdown, feste Abschnitte)
1. **Strategietyp** — 1–2 Sätze
2. **Einstieg/Exit** — erkennbare Muster, Auslöser
3. **Zeiten/Sessions** — wann handelt das System (Wochentage, Stunden)
4. **Sizing** — Lot-Verhalten, Eskalation ja/nein
5. **Stop-Disziplin** — bewiesen/behauptet, typische Distanzen
6. **Erwartetes Verhalten** — DD-Band, Verlustserien-Länge, Gewinnmuster
7. **Konformitäts-Merkmale** — nummerierte Liste: woran man später erkennt,
   dass das Signal NORMAl handelt (für die Tagesprüfung)
8. **Warn-Merkmale** — nummeriert: was eine Abweichung wäre (Stilbruch-
   Indikatoren)

Nur belegte Aussagen; Widersprüche zugunsten der Engine-Forensik. Deutsch,
keine Emojis, keine Anlageberatung.
```

### A.4 `betreuer_delta.md`
```
# Signal-Betreuer — Tagesprüfung {signal_name}

Du betreust das Signal {signal_name} und prüfst die NEUEN Trades seit dem
letzten Blick gegen das dokumentierte Algo-Profil. Alle Zahlen sind
maschinell berechnet — zitieren erlaubt, nichts dazuerfinden.

## Algo-Profil (dokumentiert)
{profil_text}

## Neue Trades / Delta-Kennzahlen (Code-berechnet)
{delta_json}

## Marktkontext (heute)
{marktkontext}

## Letzte Beobachtungen (Verlauf)
{letzte_beobachtungen}

## Aufgabe
Bewerte: Handelt das Signal im Rahmen des Profils?
Beginne mit EXAKT einer Zeile:
EINORDNUNG: KONFORM | AUFFAELLIG | STILBRUCH | KEINE_NEUEN_TRADES
Danach max. 200 Wörter Begründung mit Zahlen; bei AUFFAELLIG/STILBRUCH nenne
die verletzten Profil-Merkmale (Nummern) und den Schweregrad.
Du bewertest NIEMALS neu — Ampel/Urteil/Score sind Engine-Sache; deine
Einordnung ist Beobachtung, keine Neubewertung. Deutsch, keine Emojis,
keine Anlageberatung.
```

### A.5 `lagebericht.md`
```
# Chefermittler — Wochen-Lagebericht

Du bist der leitende Prüfer des MqlKiScanner-Agentenbetriebs und schreibst
den Wochen-Lagebericht über alle betreuten Signale. Alle Zahlen sind
maschinell berechnet — zitieren erlaubt, nichts dazuerfinden.

## Dossiers (kompakt, maschinell aufbereitet)
{dossiers_json}

## Marktkontext der Woche
{marktkontext_woche}

## Ampel-Wechsel der Woche (Engine-Protokoll)
{ampel_wechsel_json}

## Budget-Status
{budget_status}

## Aufgabe (Markdown, 400–700 Wörter)
1. **Kurzfassung** — max. 3 Sätze
2. **Signale im Detail** — je 🟢/🟡-Signal: konform/auffällig, wichtigste
   Entwicklung, Dringlichkeit der nächsten Prüfung
3. **Markt und Zusammenhänge** — welche Marktlage erklärt welches Verhalten
4. **Empfehlungen** — welcher Signal beim nächsten Gelb/Grün-Scan besonders
   genau zu prüfen ist; ob eine Tiefenanalyse-Erneuerung lohnt; welche
   Watchlist-Signale reif für den nächsten Full-Scan sind
Bindend: Du entscheidest nichts und bewertest nichts neu — Engine-Ampel und
Urteil sind maßgeblich; deine Empfehlungen sind Vorschläge an den Nutzer.
Deutsch, sachlich, keine Emojis, keine Anlageberatung.
```

### A.6 `meldung.md`
```
# Melder — Nachricht für das Postfach

Du verdichtest Agenten-Journal-Einträge zu einer kurzen Klartext-Nachricht an
den Nutzer. Alle Zahlen stammen aus den Einträgen — nichts dazuerfinden.

## Typ
{typ}

## Ereignisse (maschinell)
{ereignisse_json}

## Aufgabe
Eine Nachricht, max. 120 Wörter: was ist passiert, welche Signale betroffen,
was empfiehlt sich anzusehen (Verweis auf Protokoll/Postfach genügt).
Bei Alerts (Priorität 2/3) das Wichtigste in den ersten Satz. Deutsch,
keine Emojis, keine Anlageberatung.
```

---

*Dokument erstellt am 22.09.2026 im Rahmen der Konzeptphase „Autonomer
Agentenbetrieb". Umsetzung siehe Phasenplan; nach jeder Phase wird hier der
Status nachgetragen.*
