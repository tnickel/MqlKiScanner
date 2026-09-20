# Roadmap: Build-Plan für MqlKiScanner

**Status (Stand 20.09.2026): Phasen 0–4 abgeschlossen, Engine verifiziert,
634 Tests grün (`pytest` ohne LLM-Marker).** Offen sind nur noch Teile von
Phase 5 (Betrieb). Dieser Plan dokumentiert den Build-Weg; die Haken
verweisen auf die tatsächlich gebauten Module, wo sie vom Originalplan
abweichen.

Ursprungskontext: `AGENTS.md` (Pflichtlektüre) + `doc/02_technik-mql5.md`
(Endpunkte/Formate) + `doc/03_forensik-tests.md` (Test-Specs) +
`scripts/reference/` (bewährte Implementierungen — konsolidiert, nicht
neu erfunden).

## Phase 0: Grundlagen — ✅ abgeschlossen

- [x] Python-Umgebung (venv), `requirements.txt` — requests, beautifulsoup4,
      pandas, reportlab (PDF), streamlit[pdf] (GUI + eingebetteter
      PDF-Viewer), selenium (MQL5-Login/Export-Fallback)
- [x] `config.py` — Credentials ausschließlich via `secrets_store`
      (Umgebung > `secrets.local.json` > Admin-UI), nie im Code
- [x] Session-Modul: Login-Flow (auth_login → Cookie), Session-Check
      (Antwort beginnt mit `Time;` = ok), Rate-Limiter —
      `mql5/session.py`, `mql5/browser_session.py`, `mql5/ratelimit.py`,
      `mql5/errors.py` (Fail-Fast)

## Phase 1: Kern-Engine — ✅ abgeschlossen (läuft ohne LLM)

- [x] Crawler: Listenseiten MT4+MT5 → Signale mit ID, Name, Abonnenten,
      Growth, Reliability — `mql5/crawler.py`
- [x] Signalseiten-Kennzahlen (Label/Wert-Zeilen aus der MQL5-Statistik) —
      `mql5/signal_stats.py`
- [x] Trade-Export je Signal (MT5 `/export/positions`, MT4
      `/export/history`; HTML-Antwort → Session erneuern) —
      `mql5/exporter.py`
- [x] Forensik-Batterie nach `doc/03_forensik-tests.md` — `forensics/`:
      `martingale.py` (Lot nach Verlust), `exposure.py` (Peak-Positionen +
      USD-Risiko; Kontraktgrößen je Instrument über
      `data/contract_specs.json`, FX-Kreuze über EZB-Kurse `fx_rates.py`),
      `stops.py` (SL-Clustering/Orderbuch), `drawdown.py` (Rekonstruktion +
      Plattform-Abgleich; Schranke = max(By-Equity, By-Balance,
      Trading-DD)), plus `news.py` (News-Korrelation) und `baskets.py`
- [x] `scoring.py`: 7-Dimensionen-Score (1–10, hoch = riskant), nur nach
      bestandener Forensik-Batterie; Kalibrierung aus der Analyse-Reihe
      (Gold Spike 4,0 … World PEACE 8,0); Skript `scripts/calibrate_scoring.py`
- [x] **Verifikation:** `scripts/verify_engine.py` (Anker-Checks gegen
      `data/raw/` und die Werte aus `doc/01_analysen-verlauf.md`) + 634
      pytest-Tests grün. Erst wenn die Rekonstruktion auf den Cent stimmt,
      ist die Engine fertig — Kriterium erfüllt.

## Phase 2: Scoring-Lauf + Ausgabe — ✅ abgeschlossen

- [x] Batch-Lauf über Katalog — `pipeline.py` (+ `scan_worker.py` für
      prozessweite Koordination unabhängig von Streamlit-Sitzungen)
- [x] Ampel-Ausgabe — `ampel_matrix.py` (je Kriterium eine Ampel mit
      exaktem Berechnungstext, DB-Audit-Snapshot), `regelwerk.py` (explizite
      Kategorien der Ausschlussliste, Anzeige-Markdown bei ⛔)
- [x] Berichte — `pdf_reports.py` (deterministische PDFs, dauerhaft in
      SQLite) + LLM-Berichte (`db.py`: Tabellen signals, trade_files,
      forensik, analyses)

## Phase 3: LLM-Layer — ✅ abgeschlossen

- [x] GLM über die OpenAI-kompatible Z.ai-API, zweistufig: Stufe 1
      `glm-5.3-flash` (Massen-Profile im Scan), Stufe 2 `glm-5.3`
      (Finalisten-Verdict) — `llm/client.py`, `llm/prompts.py`,
      `llm/prompt_fill.py`; editierbare Vorlagen in `config/prompts/`
- [x] Regel durchgesetzt: LLM bekommt nur Forensik-/Kennzahlen-JSON plus
      kuratierte Beispiel-Trades, nie Roh-Trades; der Engine-Verdict ist
      bindend (LLM zitiert, widerspricht nicht). Regressionstests mit
      echten Modellaufrufen: `pytest -m llm` (opt-in, Token-Kosten)
- [x] Kosten-Budget: `max_total_tokens` je Lauf, geprüft vor jedem Aufruf;
      Coding-Plan-Endpunkt als Default (1113-Falle „Insufficient balance",
      dokumentiert in `config.py`)

## Phase 4: GUI — ✅ abgeschlossen

- [x] Streamlit: `streamlit_app.py` + `app_pages/` (Scan, Ergebnisse,
      Admin) — Tabelle mit Filtern, Detailansicht je Signal (Forensik +
      LLM-Profil), Ampel-Matrix, NEU-Markierung, PDF-Viewer mit
      Speichern-Button, Admin-UI für Secrets und GLM-Einstellungen
- [x] JavaFX-Alternative verworfen (Streamlit reicht)

## Phase 5: Betrieb — 🟡 teils offen

- [x] Datenhaltung: `data/runs/{zeitstempel}/results.json` je Lauf plus
      SQLite (`data/mqlkiscanner.db`) als zentrale Persistenz; fertige
      Läufe werden beim Neustart aus der DB übernommen
- [ ] Wiederholungsmodus als Kommandozeilen-Aufruf mit Diff gegen den
      letzten Lauf (Läufe gibt es bisher nur über die Scan-Seite der GUI)
- [ ] Alerting-Kriterien: Schranke-Verletzung ist in der Ampel-Matrix
      sichtbar, MT4/MT5-Zwillingsvergleich existiert (`compare.py`);
      fehlen: automatisierte Alerts bei Anbieter-Stilbruch oder
      Copy-Abweichung > x %

## Phase 6: MqlDownloader-Anbindung — ✅ abgeschlossen (20.09.2026)

Anbindung an die REST-API des lokalen MqlDownloader-Dienstes (Doku:
`MqlDownloader/doc/REST_API_Dokumentation.md`), rein lesend:

- [x] REST-Client `downloader_client.py` — Base-URL (Default-Port 8089,
      `/api/v1` wird ergänzt), optionaler Token (`X-API-Token`), Fehler
      klar sortiert: Netz vs. Auth (401) vs. „nicht vorhanden" (404)
- [x] Admin-Tab „MqlDownloader" — Base-URL + Token konfigurieren,
      Verbindungstest per `GET /health` (Provider-Anzahl, API-Version,
      `tokenRequired`-Warnung)
- [x] Abonnenten-Verlauf je Signal (`/providers/{id}/{version}/history`)
      → SQLite `subscriber_history`, Anzeige als Chart/Kennzahl/Tabelle
      über „Nutzer-Verlauf aktualisieren" in der Signal-Detailansicht
- [x] Testreport-PDFs je Signal (`/reports` + Download) → lokale Spiegelung
      `data/downloader/{Signal-ID}/reports/{version}/` + SQLite
      `downloader_reports`; unveränderte Dateien (gleiche Größe) werden
      nicht erneut geladen; Einsicht per Button in der Detailansicht
- [ ] Tradelisten aus dem Downloader (`/trades`) — bewusst offen: Die
      Engine arbeitet mit den eigenen, verifizierten MQL5-Exporten;
      Bedarf laut Nutzer noch unklar

## Bewusst außerhalb des Scopes

- Kein Eigenhandel/Order-Routing — das Tool analysiert und bewertet nur
- Keine Garantie-Logik: "bewiesener Stop" heißt nicht risikolos
  (Historie ≠ Zukunft; 30-%-Schranke schützt nur bei kontinuierlichen
  Verlusten, nicht bei Gap-Risiken)
