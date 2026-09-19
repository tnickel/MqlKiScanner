# Architektur — MqlKiScanner

## Schichten

```
Streamlit UI (app_pages/, streamlit_app.py)
        │
        ▼
Pipeline (pipeline.py) — Crawl → Export → Forensik → Score → optional LLM
        │
        ├─► mql5/     Session, Crawler, Stats, Exporter, Browser-Login
        ├─► forensics/  Martingale, Exposure, Stops, Drawdown, Baskets, News
        ├─► scoring.py  7 Dimensionen + harte DD-Schranke
        ├─► llm/        GLM-Client (Zahlen nur als fertiges JSON)
        └─► db.py       SQLite: Signale, Trades, Forensik, Analysen
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

1. **Listen:** `/en/signals/mt5` + `/en/signals/mt4` (ohne Login).
2. **Vorfilter:** Wochen, Abonnenten → `data/candidates.json` (lokal).
3. **Kennzahlen:** Signalseite HTML → Stats.
4. **Trade-Export (Cookie):**
   - MT5 → `/export/positions`
   - MT4 → `/export/history` (Orderbuch; `/positions` → 404)
   - Fallback: Chrome klickt „History“ auf der Signal-Seite.
5. **Forensik-Batterie** (Spec `doc/03`): Martingale, Peak-Exposure
   (Anzahl- + Volumen-/Schock-Peak), Stops, Drawdown.
6. **Score + Ampel**, Persistenz in `data/mqlkiscanner.db`.
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
