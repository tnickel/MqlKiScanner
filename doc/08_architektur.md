# Architektur — MqlKiScanner

Dokumentationsabgleich mit dem lokalen Code: 16.10.2026.
**MqlRealmonitor ist noch nicht in den Gesamtworkflow eingebunden.**
Die REST-Schnittstellen sind vorbereitet; die Integration bleibt vorerst
zurückgestellt. PelicanWinnerLooser ist ein eigenständiges Einzelprojekt und
ebenfalls noch nicht in den Gesamtworkflow eingebunden; keine Hub-Anbindung.

## Schichten

```
Streamlit UI (app_pages/, streamlit_app.py)
        │
        ▼
Stufe 0 (client_updates.py) — aktive Quellen parallel aktualisieren (optional)
        │
Pipeline (pipeline.py) — Katalog/Crawl → Trades → Forensik → Score/Ampel → optional LLM
        │                   └─► ampel_verlauf.py  Farb-Chronik + Wechsel-
        │                                       protokoll (append-only)
        ├─► mql5/     Session, Crawler, Stats, Exporter, Browser-Login
        ├─► forensics/  Martingale, Exposure, Stops, Drawdown, Baskets, News
        ├─► scoring.py  7 Dimensionen + harte DD-Schranke
        ├─► ampel_matrix.py / regelwerk.py  9-Kriterien-Matrix, Ausschlüsse
        ├─► llm/        GLM-Client (Zahlen nur als fertiges JSON)
        ├─► quellen.py / ingest.py / downloader_client.py  Quellen-REST + SHA-Cache
        ├─► tradeserver_client.py Einmal-Sync zum MqlTradeMonitor (v1)
        └─► db.py       SQLite: Signale, Trades, Forensik, Analysen,
                        Abonnenten-Verlauf, Downloader-PDFs,
                        Ampel-Verlauf (ampel_verlauf/ampel_wechsel)
Nebenläufig: rest_api.py — schreibgeschützter HTTP-Server (127.0.0.1:8611)
als Vorbereitung für MqlRealmonitor; Integration zurückgestellt.
Liest gespeicherte Forensik und leitet Ampel/Urteil mit aktuellen Einstellungen
neu ab; kein neuer Trade-/Kursabruf und keine neue Forensik. Fehlende Bericht-PDFs
können beim Laden materialisiert werden.
Nebenläufig (Phasen A–E): agenten/ — autonomer LLM-Daemon als
eigener Prozess (python -m mqlkiscanner.agenten): Dirigent-Tageslauf,
Scheduler mit Herzschlag/Stopp, Journal (agenten_laeufe/schritte/
meldungen/steuerung, append-only; LLM-Schritte mit vollem Prompt und
voller Antwort), Lauf-Lock gegen die GUI, Rollen-Registry (GLM-5.3
Standard je Rolle), Start/Stopp über Admin → Agenten. Bewertet nie —
beobachtet und meldet; kann reguläre Scan-Läufe starten. Bauplan: doc/19.
```

**Regel:** Die verbindlichen Kennzahlen, Ampel und Score berechnet der Code.
LLM-Berichte interpretieren Befunde; die manuelle Tiefenanalyse darf zusätzlich
auf Trade-Basis mit offengelegten Annahmen rechnen. Credentials gehören nie
in Prompts.
**Bindung:** Die Engine-Ampel (`ampel` + `urteil`, Teil jedes
Kandidaten-JSONs) ist für alle LLM-Berichte verbindlich: ⛔ (Ausschlussliste)
und 🔴 (Martingale/Schranke) bedeuten automatische Ablehnung; ein
Gesamtbericht darf das nicht aufwerten, der Portfolio-Vorschlag darf solche
Signale nie aufnehmen. Das Schockszenario ist ein Stressszenario, kein
gemessener Verlust, und allein kein Ablehnungsgrund. (Hintergrund: Der
Portfolio-Bericht vom 19.09.2026 empfahl das ausgeschlossene Kenni
Breakout und sortierte Gold Spike über das Schockszenario aus, weil der
LLM-Payload Ampel/Ausschluss-Grund nicht enthielt — behoben durch
`urteil` im Payload plus bindende Regeln in Prompt 3/4.)

## Datenfluss (Live-Scan)

Zwei Start-Modi mit gemeinsamem Ablauf: **Full-Scan** (alle ausgewählten
Signale) und **Teilscan** (Signale mit letzter Bewertung 🟢/🟡 laut DB plus
Fix-IDs; erzwingt alle LLM-Stufen neu).

0. **Clients aktualisieren:** Wenn `stufe0_aktiv`, aktive Quellen parallel
   über `POST /api/v1/update` aktualisieren und `GET /api/v1/update/status`
   abwarten; in GUI und autonomem Scan implementiert (doc/23).
1. **Katalog:** `listen_modus=mql5` (Default) lädt `/en/signals/mt5` und
   `/en/signals/mt4`; `quellen` liest die REST-Kataloge; `beides` vereinigt
   beide Wege, bei gleicher ID/Plattform gewinnt MQL5-Direkt.
2. **Vorfilter:** Wochen, Abonnenten und Export-Auswahl; Fix-IDs umgehen die
   Vorfilter und haben Vorrang bei der Auswahl.
3. **Kennzahlen:** Quellen-`/metrics` oder MQL5-Signalseite → Stats.
4. **Trades:** Quellen-`/trades.csv` mit SHA-Artefakt-Cache oder direkter
   MQL5-Export mit Login-Cookie:
   - MT5 → `/export/positions`
   - MT4 → `/export/history` (Orderbuch; `/positions` → 404)
   - Fallback: Chrome klickt „History“ auf der Signal-Seite.
5. **Forensik-Batterie** (Spec `doc/03`): Martingale, Peak-Exposure
   (Anzahl- + Volumen-/Schock-Peak), Stop-Evidenz, Closing-DD und optionale
   Equity-Rekonstruktion auf H1-Bar-Schlusskursen mit Floating.
6. **Score + Ampel**, Persistenz in `data/mqlkiscanner.db`; danach schreibt
   `ampel_verlauf.py` den Chronik-Eintrag und prüft gegen den Vorgänger
   (Farbwechsel ODER gekipptes Einzelkriterium → `ampel_wechsel` mit
   Begründungen). Fehlgeschlagene Prüfungen schreiben keinen Eintrag.
7. **LLM (optional):** Trade- + Risiko-Analyse parallel, dann Gesamtbericht.
   Portfolio-Bericht und manuelle Tiefenanalyse ergänzen den Ablauf.

**Aktuelle Grün-Regeln:** Ausschlussliste, Martingale und Drawdown-Schranke
(Default 30 %, Maximum aus fünf Kanälen) haben Vorrang. Zusätzlich muss der
Jahres-Calmar `retdd_jahr` mindestens `min_calmar_jahr` (Default 3,0) erreichen;
unter drei Monaten Trade-Historie bleibt er unbestimmbar. Nenner ist die
belastbare H1-Equity-Messung, niemals Monitor-Closing-DD oder Plattform-DD.
Vorbehaltswerte entsperren Grün nicht. Die absolute Monats-Ertragshürde ist
standardmäßig aus (`min_ertrag_pct_monat=0`); fehlender SL-Nachweis ist neutral.
Der Risiko-Score bleibt sichtbar, ist aber kein eigenständiges Grün-Gate.

## Wichtige Module

| Pfad | Rolle |
|---|---|
| `parser.py` | Positions-CSV und MT4-Orderbuch |
| `forensics/exposure.py` | Peak-Positionen + USD-Schock je Symbol |
| `forensics/stops.py` | Orderbuch-Beweis / Distanz-Clustering (symbolgerecht) |
| `forensics/drawdown.py` | USD-Anker + `dd_pct_max_rel` für Risiko |
| `mql5/session.py` | Rate-Limit, Cookie-HTTP, Export-Pfade |
| `mql5/browser_session.py` | Selenium-Login, Cookie-Ernte, CSV-Download |
| `ampel_matrix.py` | 9-Kriterien-Matrix je Signal einschließlich Jahres-Calmar (Audit-Snapshot je Lauf) |
| `ampel_verlauf.py` | Append-only Farb-Chronik + Wechsel-Protokoll mit Kriterium-Begründungen; bewertet selbst nichts |
| `regelwerk.py` | Kuratierte Ausschlussliste (6 Kategorien) |
| `fx_rates.py` | EZB-Referenzkurse zur USD-Umrechnung fremdwährungsquotierter Trades |
| `quellen.py` / `ingest.py` | Quellen-Registry, Katalog, Trades und Metrics aller aktiven Quellen |
| `downloader_client.py` / `client_updates.py` | Gemeinsamer Quellen-REST-Client; Daten-GETs und Stufe-0-Update per POST mit Status-Polling |
| `forensics/equity_rekonstruktion.py` / `kursdaten.py` | H1-Equity-Modell einschließlich Floating; mehrere portable MT5-Referenzterminals |
| `portfolio_statistik.py` | Rendite, Jahres-Calmar, Mindesthistorie und Portfolio-Statistik |
| `tradeserver_client.py` / `tradeserver_sync.py` | Einmal-Sync zum MqlTradeMonitor (Protokoll v1, `/api/kiscanner`, SHA-256-Diff; bewertet nie neu) |
| `rest_api.py` | Vorbereiteter, schreibgeschützter REST-Server für MqlRealmonitor (127.0.0.1:8611, `/api/v1`); Integration zurückgestellt |
| `pdf_reports.py` | PDF-Materialisierung eigener Berichte + Portfolio |
| `tiefen_batch.py` | Hintergrund-Batch der Tiefenanalyse (Prompt 5, überspringt vorhandene) |
| `pipeline.py` | Orchestrierung, `forensik_ok`, Ampel |

## Konfiguration

- Defaults: `src/mqlkiscanner/config.py`
- Persistenz GUI: `config/app_settings.json` (keine Secrets)
- Secrets: Env → `.env` → `config/secrets.local.json`

**Offene Architekturarbeit:** Die zentrale Tabelle `signals` verwendet noch
`signal_id` als alleinigen Primärschlüssel. Der Kollisionsschutz verwirft
Schreibversuche einer anderen Quelle; die vollständige Migration auf
`(quelle, signal_id)` steht aus. Der tägliche Betreuer verarbeitet derzeit
nur MQL5-Signale und überspringt andere Quellen dokumentiert.

**UI-Abgleich vom 16.10.2026:** Die Seitenleiste zeigt die konfigurierten
Drawdown-/Jahres-Calmar-Grenzen, die optionale Monats-Ertragshürde und den
neutralen SL-Hinweis. `app_ui.render_downloader_section` prüft die aktiven
Quellen über `downloader_sync.konfiguriert()` und verweist auf
„Datenquellen“; eine leere Legacy-URL blockiert den Quellenbereich nicht mehr.
Die fachlichen Bewertungsregeln bleiben unverändert. 57 gezielte Offline-Tests
für diese UI-Korrekturen, Downloader-Client und Verbindungsmonitor bestanden
am 16.10.2026; kein vollständiger Workspace-Testlauf.

## Tests

- `scripts/verify_engine.py` — Anker gegen `data/raw/`
- `tests/` — Unit, Pipeline, Streamlit AppTest
- `pytest.ini` begrenzt die Sammlung auf `tests/`
- **Prompt-Mechanismus (immer, 0 Token):** `tests/test_prompt_fill.py`
  sichert Füllung/Builder (Injection-Schutz, Platzhalter-Guard) und die
  Bericht-Parser (`tests/bericht_parse.py`).
- **Prompt-Regression (opt-in, echte glm-5.3-Aufrufe):**
  `pytest -m llm` — 4 Tests gegen die bindenden Regeln
  (unter anderem Ausschluss ⇒ ABLEHNUNG und Portfolio-Ampel-Bindung).
  Fehlender Stop-Nachweis ist nach aktueller Regel neutral; ältere
  Testbeschreibungen mit pauschaler Empfehlungssperre sind überholt.
  Im Standard-Build deselektiert (`addopts` in
  `pytest.ini`); ausführen, wann immer an Vorlagen, Payloads, Buildern
  oder Ampel-Bindung etwas geändert wird.
