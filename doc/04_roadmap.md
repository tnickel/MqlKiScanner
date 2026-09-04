# Roadmap: Build-Plan für MqlKiScanner

Zuständig für die Umsetzung: der Agent, der in diesem Projektverzeichnis
startet. Kontext: `AGENTS.md` (Pflichtlektüre) + `doc/02_technik-mql5.md`
(Endpunkte/Formate) + `doc/03_forensik-tests.md` (Test-Specs) +
`scripts/reference/` (bewährte Implementierungen — konsolidieren, nicht
neu erfinden).

## Phase 0: Grundlagen (halber Tag)

- [ ] Python-Umgebung (venv), `requirements.txt` installieren
  (requests, beautifulsoup4 oder lxml, pandas, matplotlib, streamlit)
- [ ] `config.py` mit MQL5-Credentials aus Umgebungsvariablen
      (`MQL5_USER`, `MQL5_PASS`) — nie im Code
- [ ] Session-Modul: Login-Flow (auth_login → Cookie), Session-Check
      (Antwort beginnt mit `Time;` = ok), Rate-Limiter (1 req/1-2 s)

## Phase 1: Kern-Engine (1 Tag) — läuft ohne LLM

- [ ] `crawler.py`: Listenseiten MT4+MT5 (Seiten 1-N) → Signale mit
      ID, Name, Abonnenten, Growth, Reliability (`data/candidates.json`)
- [ ] `stats.py`: je Signalseite alle Kennzahlen (Labels aus
      `doc/02_technik-mql5.md` Abschnitt 4) → `data/stats/{ID}.json`
- [ ] `exporter.py`: Trade-Export je Signal → `data/trades/{ID}.csv`
      (Erfolgs-Check: beginnt mit `Time;`; HTML → Session erneuern)
- [ ] `forensics/`: Test-Batterie nach `doc/03_forensik-tests.md`
      — Referenzlogik steht in `scripts/reference/`:
      - `martingale.py` (Test 1: Lot nach Verlust; aus
        `martingale_exposure_test.py` konsolidieren)
      - `exposure.py` (Test 2: Peak-Positionen + USD-Risiko,
        XAUUSD = 100 USD/Lot/USD)
      - `stops.py` (Test 3: SL-Clustering; Orderbuch-Variante für
        History-CSVs aus `analyze_goldspike_orderbook.py`)
      - `drawdown.py` (Test 4: Rekonstruktion + Plattform-Abgleich)
- [ ] `scoring.py`: 7-Dimensionen-Score, Kalibrierung aus
      `doc/01_analysen-verlauf.md` (Gold Spike 4,0 … World PEACE 8,0)
- [ ] **Verifikation:** Pipeline gegen die 8 CSVs in `data/raw/` laufen
      lassen — Ergebnisse müssen die Werte aus `doc/01_analysen-verlauf.md`
      reproduzieren (Winrates, DDs, Serien). Erst wenn die Rekonstruktion
      auf den Cent stimmt, ist die Engine fertig.

## Phase 2: Scoring-Lauf + Ausgabe (halber Tag)

- [ ] Batch-Lauf über Katalog (gesamte Listen, nach Abonnenten sortiert)
- [ ] Ampel-Ausgabe: Kandidaten (Score < 5, Schranke erfüllt),
      Ausschlüsse (`data/known_signals.json`), Watchlist mit Befund
- [ ] Report: Markdown/HTML je Kandidat (Profil, Testergebnisse, Urteil)

## Phase 3: LLM-Layer (halber Tag — Key nötig)

- [ ] Stufe 1 (Flash-Klasse): JSON je Kandidat → deutsches Profil
      (~300 Tokens out), Review-Zusammenfassung
- [ ] Stufe 2 (starkes Modell): Finalisten → Verdict mit Argumentation,
      Widerspruchscheck gegen Kriterien
- [ ] Regel durchsetzen: LLM bekommt nur Forensik-JSON, nie Roh-Trades;
      Zahlen kommen ausschließlich aus der Engine
- [ ] Kosten-Budget im Tool begrenzen (z. B. Max-Token-Limit pro Lauf)

## Phase 4: GUI (1 Tag)

- [ ] Streamlit (Empfehlung): Tabelle mit Filtern (DD, Wochen, Ertrag,
      Score), Detailseite je Kandidat (Forensik-Karten + LLM-Profil),
      Re-Scan-Button
- [ ] Alternative (falls Java gewünscht): JavaFX-Tabelle, Engine 1:1
      portieren — Logik bleibt identisch

## Phase 5: Betrieb

- [ ] Wiederholungsmodus: Re-Scan (wie die Okt.-Automation) als
      Kommandozeilen-Aufruf, Diff gegen letzten Lauf
- [ ] Datenhaltung: `data/runs/{DATUM}/` je Lauf, Vergleich über Läufe
- [ ] Alerting-Kriterien: Kandidat verletzt Schranke, Anbieter-Stilbruch,
      Copy-Abweichung > x %

## Bewusst außerhalb des Scopes

- Kein Eigenhandel/Order-Routing — das Tool analysiert und bewertet nur
- Keine Garantie-Logik: "bewiesener Stop" heißt nicht risikolos
  (Historie ≠ Zukunft; 30-%-Schranke schützt nur bei kontinuierlichen
  Verlusten, nicht bei Gap-Risiken)
