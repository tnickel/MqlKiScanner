# Architektur — MqlKiScanner

## Schichten

```
Streamlit UI (app_pages/, streamlit_app.py)
        │
        ▼
Pipeline (pipeline.py) — Crawl → Export → Forensik → Score → optional LLM
        │                   └─► ampel_verlauf.py  Farb-Chronik + Wechsel-
        │                                       protokoll (append-only)
        ├─► mql5/     Session, Crawler, Stats, Exporter, Browser-Login
        ├─► forensics/  Martingale, Exposure, Stops, Drawdown, Baskets, News
        ├─► scoring.py  7 Dimensionen + harte DD-Schranke
        ├─► ampel_matrix.py / regelwerk.py  8-Kriterien-Matrix, Ausschlüsse
        ├─► llm/        GLM-Client (Zahlen nur als fertiges JSON)
        ├─► downloader_client.py  MqlDownloader-REST (lesend): Verlauf + PDFs
        ├─► tradeserver_client.py Einmal-Sync zum MqlTradeMonitor (v1)
        └─► db.py       SQLite: Signale, Trades, Forensik, Analysen,
                        Abonnenten-Verlauf, Downloader-PDFs,
                        Ampel-Verlauf (ampel_verlauf/ampel_wechsel)
Nebenläufig: rest_api.py — schreibgeschützter HTTP-Server (127.0.0.1:8611)
für den MqlRealMonitor, liest nur die DB, bewertet nie neu.
```

**Regel:** Die Engine rechnet alle Zahlen. Das LLM interpretiert nur
Befund-JSONs — keine Roh-Trades, keine Credentials im Prompt.
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
Signale) und **Gelb/Grün-Scan** (nur Signale mit letzter Bewertung 🟢/🟡 laut
DB-Stand; erzwingt alle LLM-Stufen neu — Modus-Vertrag, Laufzeit-Toggles
gelten dort nicht).

1. **Listen:** `/en/signals/mt5` + `/en/signals/mt4` (ohne Login).
2. **Vorfilter:** Wochen, Abonnenten → `data/candidates.json` (lokal).
3. **Kennzahlen:** Signalseite HTML → Stats.
4. **Trade-Export (Cookie):**
   - MT5 → `/export/positions`
   - MT4 → `/export/history` (Orderbuch; `/positions` → 404)
   - Fallback: Chrome klickt „History“ auf der Signal-Seite.
5. **Forensik-Batterie** (Spec `doc/03`): Martingale, Peak-Exposure
   (Anzahl- + Volumen-/Schock-Peak), Stops, Drawdown.
6. **Score + Ampel**, Persistenz in `data/mqlkiscanner.db`; danach schreibt
   `ampel_verlauf.py` den Chronik-Eintrag und prüft gegen den Vorgänger
   (Farbwechsel ODER gekipptes Einzelkriterium → `ampel_wechsel` mit
   Begründungen). Fehlgeschlagene Prüfungen schreiben keinen Eintrag.
7. **LLM (optional):** Trade- + Risiko-Analyse parallel, dann Gesamtbericht.

## Wichtige Module

| Pfad | Rolle |
|---|---|
| `parser.py` | Positions-CSV und MT4-Orderbuch |
| `forensics/exposure.py` | Peak-Positionen + USD-Schock je Symbol |
| `forensics/stops.py` | Orderbuch-Beweis / Distanz-Clustering (symbolgerecht) |
| `forensics/drawdown.py` | USD-Anker + `dd_pct_max_rel` für Risiko |
| `mql5/session.py` | Rate-Limit, Cookie-HTTP, Export-Pfade |
| `mql5/browser_session.py` | Selenium-Login, Cookie-Ernte, CSV-Download |
| `ampel_matrix.py` | 8-Kriterien-Matrix je Signal (Audit-Snapshot je Lauf) |
| `ampel_verlauf.py` | Append-only Farb-Chronik + Wechsel-Protokoll mit Kriterium-Begründungen; bewertet selbst nichts |
| `regelwerk.py` | Kuratierte Ausschlussliste (6 Kategorien) |
| `fx_rates.py` | EZB-Referenzkurse zur USD-Umrechnung fremdwährungsquotierter Trades |
| `downloader_client.py` | REST-Client für den MqlDownloader (Abonnenten-Verlauf, Testreport-PDFs; rein lesend, Fehler klar sortiert: Netz/Auth/404) |
| `tradeserver_client.py` / `tradeserver_sync.py` | Einmal-Sync zum MqlTradeMonitor (Protokoll v1, `/api/kiscanner`, SHA-256-Diff; bewertet nie neu) |
| `rest_api.py` | Schreibgeschützter REST-Server für den MqlRealMonitor (127.0.0.1:8611, `/api/v1`; bewertet nie neu) |
| `pdf_reports.py` | PDF-Materialisierung eigener Berichte + Portfolio |
| `tiefen_batch.py` | Hintergrund-Batch der Tiefenanalyse (Prompt 5, überspringt vorhandene) |
| `pipeline.py` | Orchestrierung, `forensik_ok`, Ampel |

## Konfiguration

- Defaults: `src/mqlkiscanner/config.py`
- Persistenz GUI: `config/app_settings.json` (keine Secrets)
- Secrets: Env → `.env` → `config/secrets.local.json`

## Tests

- `scripts/verify_engine.py` — Anker gegen `data/raw/`
- `tests/` — Unit, Pipeline, Streamlit AppTest
- `pytest.ini` begrenzt die Sammlung auf `tests/`
- **Prompt-Mechanismus (immer, 0 Token):** `tests/test_prompt_fill.py`
  sichert Füllung/Builder (Injection-Schutz, Platzhalter-Guard) und die
  Bericht-Parser (`tests/bericht_parse.py`).
- **Prompt-Regression (opt-in, echte glm-5.3-Aufrufe):**
  `pytest -m llm` — 4 Tests gegen die bindenden Regeln
  (Ausschluss ⇒ ABLEHNUNG; kein Stop ⇒ nie EMPFEHLUNG; Portfolio nimmt
  ⛔/🔴 nie auf und bleibt intern konsistent; Schockszenario allein ist
  kein Ablehnungsgrund). Im Standard-Build deselektiert (`addopts` in
  `pytest.ini`); ausführen, wann immer an Vorlagen, Payloads, Buildern
  oder Ampel-Bindung etwas geändert wird.
