# MqlKiScanner

Scanner für MQL5-Handelssignale mit forensischer Risiko-Analyse und
zweistufigem GLM-LLM-Layer. Fortsetzung einer forensischen Analyse-Reihe
(6 Tiefenanalysen, 37 gescannte Signale, Sep. 2026).

**Grundsatz: Risiko vor Ertrag.** Harte 30-%-Drawdown-Schranke, mindestens
5 % Ertrag/Monat, und: kein positives Urteil ohne bewiesenen Stop-Loss.

## Schnellstart

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

- **Scan-Seite:** 4 sichtbare Schritte — (1) MQL5-Signal-Listen lesen,
  (2) Kandidaten-Liste erzeugen, (3) Daten extrahieren + Forensik,
  (4) LLM-Auswertung — plus Ergebnistabelle mit Ampel und Detailansicht.
  Ohne MQL5-Login gibt es einen Verifikations-Modus: die 9 realen
  Datensätze aus `data/raw/` laufen durch die Engine (83/83 Checks
  reproduzieren die Werte aus `doc/01_analysen-verlauf.md`, Aufruf:
  `python scripts/verify_engine.py`).
- **Ergebnisse-Seite:** Gesamttabelle (Filter, Zeilenauswahl), Urteile,
  Detailkarten je Signal.
- **Admin-Seite:** GLM-API-Key und MQL5-Login setzen (siehe unten),
  Verbindungstests, Rate-Limits, Prompt-Vorlagen anzeigen/bearbeiten.

## Sicherheit: Keys und Logins

Geheimnisse landen **nie** im Repository. Reihenfolge beim Laden:
Umgebungsvariable → `.env` → `config/secrets.local.json`
(beide Dateien stehen in `.gitignore`).

| Geheimnis | Env-Variable | Zweck |
|---|---|---|
| GLM-API-Key | `GLM_API_KEY` (oder `MQLKISCANNER_GLM_KEY`) | LLM-Auswertung |
| MQL5-Login | `MQL5_USER` | Trade-Exporte |
| MQL5-Passwort | `MQL5_PASS` | Trade-Exporte |

Vorlage: `.env.example` kopieren nach `.env` und füllen — oder direkt in
der App im Admin-Bereich setzen (wird nach `config/secrets.local.json`
geschrieben, ebenfalls gitignored).

## LLM-Layer (GLM, zweistufig — AGENTS.md Design-Regel 5)

- **Stufe 1** `glm-5.3-flash`: Massen-Profile für alle Forensik-Kandidaten.
- **Stufe 2** `glm-5.3`: Verdicts (EMPFEHLUNG/WATCHLIST/ABLEHNUNG) nur für
  Finalisten (Score < 5), mit Widerspruchscheck gegen die Engine-Zahlen.
- Die Engine rechnet **alle** Zahlen; das LLM bekommt nur fertige
  Befund-JSONs und formuliert. Token-Budget je Lauf einstellbar.
- Prompts liegen als editierbare Vorlagen unter `config/prompts/` und sind
  per Button in der GUI anzeigbar und änderbar.
- Die Engine läuft komplett ohne LLM-Key (Schritt 4 ist optional).

## Rate-Limiting (Account-Schutz)

Alle MQL5-Requests laufen über `RateLimiter` (mql5/ratelimit.py):
Mindestabstand je Request (Standard 2 s + Jitter), Zusatzpause zwischen
Signalen (5 s), Backoff bei HTTP 429/503. Trade-Exporte werden 24 h
gecached (`data/trades/`). Limits im Admin-Bereich änderbar — aggressiv
senken kann zur Account-Sperre führen (MQL5-ToS).

## Projektstruktur

```
streamlit_app.py     App-Einstieg (Navigation, Status)
app_pages/           scan.py, ergebnisse.py, admin.py
src/mqlkiscanner/    Engine + Pipeline
  parser.py stats.py engine.py scoring.py pipeline.py
  forensics/         martingale, exposure, stops, drawdown, baskets, news
  mql5/              session (Login+Rate-Limit), crawler, signal_stats, exporter
  llm/               client (GLM 2-stufig), prompts (editierbar)
scripts/
  verify_engine.py   Verifikation gegen doc/01-Werte (83 Checks)
  calibrate_scoring.py  Score-Kalibrierung gegen die 6 Tiefanalysen
  reference/         bewährte Analyse-Skripte aus der Reihe
data/raw/            reale Trade-CSVs (Testdaten, Verifikations-Modus)
data/known_signals.json   Ausschlüsse / Watchlist / Empfehlung
config/prompts/      LLM-Prompt-Vorlagen (editierbar)
doc/                 Analyse-Verlauf, MQL5-Technik, Test-Specs, Roadmap
tests/test_app.py    Headless-UI-Tests (st.testing.v1.AppTest)
```

## Tests

```bash
python scripts/verify_engine.py   # 83 Checks gegen die Analyse-Reihe
python tests/test_app.py          # 5 UI-Tests (headless)
python scripts/calibrate_scoring.py
```

## Zweck-Hinweis

Das Tool analysiert und bewertet ausschließlich. Kein Order-Routing,
keine Anlageberatung. „Bewiesener Stop“ heißt nicht risikolos —
Historie ≠ Zukunft.
