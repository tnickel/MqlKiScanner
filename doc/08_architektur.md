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
