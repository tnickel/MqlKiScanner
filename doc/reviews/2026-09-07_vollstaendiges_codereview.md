# Vollständiges Code-Review: MqlKiScanner

**Datum:** 07.09.2026  
**Projekt:** MqlKiScanner  
**Workspace:** `d:\git\MQL\MqlKiScanner`  
**Git-Commit:** `5ffa6636ca04be6aa92adc4bd5b8f807cf29a815` (Branch `main`, working tree clean)  
**Zielgruppe:** Weiterarbeitende KI-Agenten und Prüf-Instanzen zur deterministischen Verifikation und Behebung  
**Teststand:** 231 passed (pytest 9.1.1), 85/85 PASS (`scripts/verify_engine.py`), 5 Linter-Findings (Ruff)

---

## 1. Prüfkontext & Leitfaden für die nachfolgende KI

Behandle jeden Befund in diesem Bericht als **prüfbare Hypothese mit Beweisgrundlage**, nicht als ungeprüfte Wahrheit. Deine Aufgabe als weiterarbeitende KI:

1. **Unabhängige Prüfung:** Lies vor Code-Änderungen `AGENTS.md`, `doc/02_technik-mql5.md` und `doc/03_forensik-tests.md`.
2. **Deterministische Verifikation:** Führe die angegebenen Reproduktions-Snippets aus. Ein grüner Stand der bestehenden Tests (`pytest`) ist kein Gegenbeweis für einen unentdeckten Edge-Case, wenn der Fall von den Tests bisher nicht abgedeckt wurde.
3. **Klassifikation:** Entscheide je Befund unabhängig zwischen:
   - **BESTÄTIGT:** Problem existiert im aktuellen Code, Auswirkung ist real.
   - **BEWUSSTE ARCHITEKTURGRENZE:** Verhalten ist technisch belegt und entspricht einer fachlichen Designentscheidung des Nutzers (z. B. "im Zweifel ablehnen").
   - **WIDERLEGT:** Annahme trifft im aktuellen Code nicht zu.
4. **Präzise Korrektur:** Ändere nur bestätigte Mängel. Verändere keine Erwartungswerte in `scripts/verify_engine.py`, ohne die fachliche Begründung zu belegen.

---

## 2. Zusammenfassung des Codezustands

### Stärken der aktuellen Codebasis
- **Robuste mathematische Engine:** Die 4 Pflicht-Forensiktests (Martingale, Exposure, Stops, Drawdown) in `src/mqlkiscanner/forensics/` sind arithmetisch strikt vom LLM getrennt. Die Engine berechnet deterministisch; das LLM interpretiert fertige JSON-Befunde (AGENTS.md Design-Regel 1).
- **Hohe Regressionsabsicherung:** 231 Pytest-Fälle und 85 Referenzprüfungen auf echten Signalen (Gold Spike, KiraCat, Gold Reaper, MSC Gold, Pure Gold, etc.) sichern die Kern-Arithmetik ab.
- **Datenintegrität beim Export:** `_snapshot_trade_file()` und `publish_validated_export()` nutzen atomare Temp-File-Erstellung und SHA-256-Adressierung. Korrupte CSV-Downloads werden verworfen und blockieren den Cache nicht mehr.
- **Kooperativer Workflow-Stop:** Threading im Streamlit-Frontend entkoppelt die UI von langen Scraping- und LLM-Läufen; Abbrüche zwischen Schritten werden kooperativ signalisiert.

### Kritische Problembereiche & Lücken
1. **Parser-Datenverlust bei MQL5-Web-Statistiken (P1):** `signal_stats._number` parst keine Zahlen mit Tausendertrennzeichen-Kommas (`"1,234"` oder `"1,403.03"`), wodurch Kennzahlen wie `trades`, `weeks` oder `growth_pct` von der Signalseite stillschweigend zu `None` werden.
2. **Instrumenten-Ausschluss durch FX-Quote-Restriktion (P1/Architektur):** Die Exposure-Engine unterstützt nur Währungspaare mit der Quote-Währung `USD`. Sämtliche USD-Basispaare (`USDJPY`, `USDCAD`, `USDCHF`) sowie alle Cross-Pairs (`EURGBP`, `NZDCAD`, etc.) liefern `shock_usd = None`, was die Pflichtprüfung dauerhaft invalidiert (`urteil_gueltig = False`).
3. **Index-Währungs- und Kontraktverzerrung (P2):** Indizes wie `JP225` (Nikkei) und `GER40` werden pauschal mit Faktor 1.0 USD je Punkt gerechnet. Bei Nikkei (50 Indexpunkte = 50 JPY ≈ 0,35 USD) führt das zu einer massiven Risiko-Übertreibung (~150-fach zu hoch).
4. **Versteckte Foreign-Key-Verletzung bei SQLite (P2):** Das Portfolio-Ergebnis wird unter `signal_id = 0` in `analyses` gespeichert. Da SQLite Fremdschlüssel (`PRAGMA foreign_keys = ON;`) nicht standardmäßig erzwingt, fällt der Verstoß gegen die Tabelle `signals` nicht auf, führt bei Aktivierung jedoch zum Absturz.
5. **Fehlendes Process-Locking bei UI-Neustart/F5 (P2):** Der Hintergrund-Thread ist nur an `st.session_state` gebunden. Ein Browser-Refresh startet eine neue Session, während der Worker als verwaister Daemon weiterläuft. Ein erneuter Klick führt zu zwei konkurrierenden Instanzen auf denselben SQLite- und Chrome-Ressourcen.
6. **Martingale-Erkennungsausfall bei intermittierenden Trades (P2):** `_successor_test` prüft nur streng benachbarte Trades `zip(trades, trades[1:])`. Öffnet während eines Verlusttrades eine Zwischenposition, wird der tatsächliche Folgetrade niemals mit dem Verlusttrade verglichen.
7. **Type-Safety bei Stop-Loss-Orderbuchprüfung (P3):** `_orderbook_evidence` prüft `t.entry_price` vor Subtraktionen nicht auf `None`, was bei unvollständigen CSV-Zeilen zu `TypeError` führen kann.

---

## 3. Detaillierter Befund-Katalog

### Befund 1 (P1 – Funktional): `signal_stats._number` scheitert an Zahlen mit Tausendertrennzeichen-Kommas

- **Kategorie:** Datenakquise / MQL5 Scraper
- **Fundstelle:** [src/mqlkiscanner/mql5/signal_stats.py:37-50](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/mql5/signal_stats.py#L37-L50)
- **Status:** **BESTÄTIGT (Reproduzierbar)**

#### Sachverhalt & Code
```python
def _number(text: str) -> float | None:
    cleaned = text.replace("\xa0", "").replace(" ", "")
    m = re.search(r"-?\d[\d.,]*", cleaned)
    if not m:
        return None
    raw = m.group(0)
    # "1 403.03" -> "1403.03" (Leerzeichen schon weg); Punkte nach der 3. Stelle = Tausender
    if raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        return float(raw.rstrip("."))
    except ValueError:
        return None
```

#### Fehlermechanismus
MQL5 formatiert Zahlen auf englischen Detailseiten häufig mit Kommas als Tausendertrennzeichen (z. B. `Trades: 1,085`, `Subscribers: 1,500`, `Initial Deposit: 10,000`, `Growth: 1,403.03 %`).
- `cleaned` behält das Komma bei (`"1,085"`).
- `raw.count(".")` ist 0 oder 1.
- `float("1,085")` schlägt in Python mit `ValueError: could not convert string to float: '1,085'` fehl.
- Der `except ValueError:` fängt den Fehler ab und gibt lautlos `None` zurück.
- Im Gegensatz dazu bereinigt `crawler.py:28` Kommas korrekt via `re.sub(r",(?=\d{3}(\D|$))", "", cleaned)`.

#### Deterministische Reproduktion
```bash
python -c "import sys; sys.path.insert(0, 'src'); from mqlkiscanner.mql5.signal_stats import _number; print('Trades:', _number('1,085')); print('Growth:', _number('1,403.03 %'))"
# Output:
# Trades: None
# Growth: None
```

#### Auswirkung
Kennzahlen auf der MQL5-Signal-Detailseite gehen verloren. Wenn `res.wochen` zu `None` wird, greift der Track-Record-Score (`scoring.py:118`) auf 0 Wochen zurück und vergibt den schlechtesten Risiko-Score von 9.0 (WEEKS_MAP).

#### Empfohlene Korrektur
Angleichung an die Regex-Bereinigung aus `crawler.py` vor dem Float-Cast:
```python
cleaned = re.sub(r",(?=\d{3}(\D|$))", "", cleaned)
```

---

### Befund 2 (P1 – Architektur/Domain): Vollständiger Ausschluss aller FX-Paare mit Quote != USD

- **Kategorie:** Forensik / Exposure-Engine
- **Fundstelle:** [src/mqlkiscanner/forensics/exposure.py:50-70](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/forensics/exposure.py#L50-L70), [src/mqlkiscanner/forensics/exposure.py:116-123](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/forensics/exposure.py#L116-L123), [src/mqlkiscanner/scoring.py:174-184](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/scoring.py#L174-L184)
- **Status:** **BESTÄTIGT (Strukturelle Grenze)**

#### Sachverhalt & Code
```python
def _quote_currency(symbol: str) -> str:
    return normalize_symbol(symbol)[-3:] if symbol_class(symbol) == "FX" else "USD"

def shock_usd(net_lots: float, move: float, symbol: str) -> float | None:
    sclass = symbol_class(symbol)
    if sclass == "UNKNOWN":
        raise ValueError(f"Unbekanntes Instrument {symbol!r}: Kontraktgroesse nicht belegt")
    if _quote_currency(symbol) != "USD":
        return None
    return abs(net_lots) * move * CONTRACT_FACTOR_PER_UNIT[sclass]
```

#### Fehlermechanismus
1. Bei jedem Währungspaar, dessen Quote-Währung nicht `USD` ist, liefert `shock_usd()` `None`.
2. Dies betrifft:
   - Alle Währungskreuze: `EURGBP`, `EURJPY`, `GBPJPY`, `NZDCAD`, `AUDNZD`, `EURCHF`, etc.
   - **Alle USD-Basispaare:** `USDJPY` (Quote: JPY), `USDCAD` (Quote: CAD), `USDCHF` (Quote: CHF).
3. Wenn ein Signal ein solches Paar handelt:
   - `conversion_complete = False`
   - `temporal_risk_available = False`
   - `shock = None`, `shock_pct_max = None`
   - In `scoring.py`: `_forensics_complete()` liefert `False`.
   - `urteil_gueltig = False`, `res.forensik_vorhanden = False`.
   - Die Ampel verbleibt zwingend auf ⚪ ("Vorprüfung mit Fehler: Forensik unvollständig: USD-Umrechnung fehlt...").

#### Bewertung & Abwägung
- **Hintergrund:** In `doc/07_codereview_korrekturen_2026-09-07.md` wurde festgelegt: *"Ohne belegte Umrechnung nicht USD-quotierter Paare bleiben Dollarwerte unbekannt und die Pflichtprüfung unvollständig."* Dies verhindert Phantasie-Berechnungen ohne historische Wechselkurse.
- **Problem:** Die aktuelle Implementierung unterscheidet nicht zwischen Cross-Pairs und USD-Basispaaren (`USDJPY`). Bei `USDJPY` wäre der Pip-Wert `1000 JPY / Kurs(USDJPY)` bekannt. Aktuell können **ausschließlich** Signale, die Gold (`XAUUSD`), US-Indizes oder `EURUSD`/`GBPUSD`/`AUDUSD`/`NZDUSD` handeln, eine grüne Ampel erhalten. Jedes andere Signal wird zwingend disqualifiziert.

#### Verifikationskriterium für die prüfende KI
Prüfe ein reines `USDJPY`-Signal mit 100 Trades: Es wird stets mit `conversion_complete=False` als "unvollständig" abgelehnt.

---

### Befund 3 (P2 – Domain/Arithmetik): Falsche Kontraktbewertung bei Non-USD-Indizes (JP225, GER40)

- **Kategorie:** Forensik / Kontraktgrößen
- **Fundstelle:** [src/mqlkiscanner/forensics/exposure.py:33-51](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/forensics/exposure.py#L33-L51), [src/mqlkiscanner/symbols.py:12-16](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/symbols.py#L12-L16)
- **Status:** **BESTÄTIGT (Logikfehler)**

#### Sachverhalt & Code
```python
CONTRACT_FACTOR_PER_UNIT: dict[str, float] = {
    "METAL": 100.0,
    "INDEX": 1.0,     # US30, NAS100, SPX500, GER40, JP225 ...
    "FX": 100_000.0,
}
STRESS_MOVE_BY_CLASS: dict[str, float] = {
    "METAL": 50.0,
    "INDEX": 50.0,
    "FX": 0.05,
}
def _quote_currency(symbol: str) -> str:
    return normalize_symbol(symbol)[-3:] if symbol_class(symbol) == "FX" else "USD"
```

#### Fehlermechanismus
1. In `symbols.py` sind `JP225` (Nikkei 225, Währung JPY), `GER40` (DAX, Währung EUR) und `UK100` (FTSE, Währung GBP) als `INDEX` klassifiziert.
2. `_quote_currency` stuft alle Symbole, die nicht `FX` sind, pauschal als `USD` ein.
3. Beim Nikkei 225 (`JP225`) bedeutet ein Move von 50 Punkten einen Verlust von 50 JPY pro Kontrakt. Bei aktuellem Wechselkurs (1 USD ≈ 150 JPY) entspricht dies ca. **0,33 USD**.
4. Die Engine rechnet jedoch: `1 Lot * 50 Punkte * 1.0 = 50.00 USD`.
5. Das Risiko für `JP225` wird dadurch um den Faktor **~150 künstlich überhöht**.
6. Umgekehrt wird `GER40` (50 EUR = ca. 55 USD) leicht unterbewertet.

#### Empfohlene Korrektur
Indizes müssen ihre Quotierungswährung (`EUR`, `GBP`, `JPY`, `USD`) kennen. Non-USD-Indizes müssen entweder analog zu Non-USD-FX-Paaren als `missing_conversion` deklariert werden oder einen passenden Währungsfaktor erhalten.

---

### Befund 4 (P2 – Datenintegrität): Scheitelpunkt-Verletzung des Fremdschlüssels bei Portfolio-Analysen (`signal_id = 0`)

- **Kategorie:** Datenbank / SQLite Schema
- **Fundstelle:** [src/mqlkiscanner/pipeline.py:762](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/pipeline.py#L762), [src/mqlkiscanner/db.py:55-63](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/db.py#L55-L63)
- **Status:** **BESTÄTIGT (Latenter Defekt)**

#### Sachverhalt & Code
In `src/mqlkiscanner/db.py`:
```sql
CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER REFERENCES signals(signal_id),
    kind        TEXT,
    model       TEXT,
    tokens      INTEGER,
    text        TEXT,
    created_at  TEXT
);
```
In `src/mqlkiscanner/pipeline.py`:
```python
PORTFOLIO_ANALYSIS_ID = 0  # analyses-Zeile ohne Signalbezug (globaler Bericht)
...
db.store_analysis(self.PORTFOLIO_ANALYSIS_ID, "portfolio", model_strong,
                  self.llm.usage.total_tokens, text)
```

#### Fehlermechanismus
In der Tabelle `signals` existiert kein Datensatz mit `signal_id = 0`.
SQLite prüft Fremdschlüssel-Constraints nur, wenn pro Verbindung `PRAGMA foreign_keys = ON;` gesetzt wird. Da dies in `db._connect()` nicht geschieht, funktioniert der Insert aktuell ohne Fehler.
Sobald jedoch:
- ein SQLite-Viewer, ein Migrationstool oder eine spätere Code-Verbesserung Fremdschlüssel aktiviert,
- bricht `db.store_analysis(0, ...)` mit `sqlite3.IntegrityError: FOREIGN KEY constraint failed` ab.

#### Empfohlene Korrektur
Das Schema von `analyses` sollte für globale Berichte `signal_id` als `NULLABLE` ohne Pseudo-ID definieren: `signal_id = NULL` für Portfolio-Einträge, oder einen definierten Dummy-Datensatz für Signal 0 anlegen.

---

### Befund 5 (P2 – Nebenläufigkeit/UI): Verwaiste Worker-Threads bei Browser-Refresh / Mehrfach-Starts

- **Kategorie:** Streamlit / Concurrency
- **Fundstelle:** [app_pages/scan.py:830-833](file:///d:/git/MQL/MqlKiScanner/app_pages/scan.py#L830-L833), [app_pages/scan.py:87-104](file:///d:/git/MQL/MqlKiScanner/app_pages/scan.py#L87-L104)
- **Status:** **BESTÄTIGT (Grenzfall bei Benutzerinteraktion)**

#### Sachverhalt & Code
```python
_lauf_thread = threading.Thread(target=_worker, name="mqlkiscanner-workflow", daemon=True)
st.session_state.scan_thread = _lauf_thread
st.session_state.scan_running = mode if mode != "scan" else "listen"
_lauf_thread.start()
```

#### Fehlermechanismus
1. Streamlit isoliert `session_state` pro Browser-Tab.
2. Drückt der Nutzer während eines laufenden Workflows `F5` (Seiten-Reload) oder schließt und öffnet den Tab:
   - Ein neuer `st.session_state` wird erzeugt.
   - `st.session_state.scan_thread` ist `None`.
   - Die UI zeigt wieder den Zustand "Bereit. Drücken Sie 'Starte Workflow'".
   - Der alte Hintergrund-Thread (`daemon=True`) läuft im Python-Prozess unbemerkt weiter.
3. Klickt der Nutzer erneut auf "Starte Workflow":
   - Ein zweiter Worker-Thread wird gestartet.
   - Beide Threads greifen parallel auf `data/chrome_profile` zu. Selenium Chrome stürzt ab (`user data directory is already in use`).
   - Beide Threads schreiben gleichzeitig in dieselbe SQLite-Datenbank `mqlkiscanner.db` (Locking-Fehler).

#### Empfohlene Korrektur
Einführung eines prozessweiten Locks (z. B. via `threading.Lock` auf Modulebene in `pipeline.py` oder File-Lock unter `data/.scan.lock`), das einen zweiten Scan-Start verhindert, solange ein aktiver Worker läuft.

---

### Befund 6 (P2 – Forensik-Logik): Martingale-Folgetrade-Erkennung wird durch parallele Trades blind

- **Kategorie:** Forensik / Martingale-Detektion
- **Fundstelle:** [src/mqlkiscanner/forensics/martingale.py:33-36](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/forensics/martingale.py#L33-L36)
- **Status:** **BESTÄTIGT (Algorithmische Einschränkung)**

#### Sachverhalt & Code
```python
for symbol, trades in by_symbol.items():
    losses, wins = [], []
    for a, b in zip(trades, trades[1:]):
        if b.open_time > a.close_time:  # nicht parallel offen
            ratio = b.volume / max(a.volume, 1e-9)
            (losses if a.profit <= 0 else wins).append(ratio)
```

#### Fehlermechanismus
`trades` ist nach `open_time` sortiert.
Angenommen, folgende Trade-Sequenz tritt auf:
1. Trade 1: Open 10:00, Close 10:30, Profit: -50 USD, Lot: 0.10
2. Trade 2 (intermittierender Scalp): Open 10:15, Close 10:20, Profit: +5 USD, Lot: 0.01
3. Trade 3 (gezielter Martingale-Recovery-Trade): Open 10:45, Close 11:15, Profit: +120 USD, Lot: 0.20 (2x Eskalation nach Trade 1)

Durch `zip(trades, trades[1:])`:
- Paar 1: `(Trade 1, Trade 2)`. Bedingung `b.open_time > a.close_time` ist `10:15 > 10:30` -> **False**. Trade 1 wird verworfen!
- Paar 2: `(Trade 2, Trade 3)`. Bedingung `10:45 > 10:20` -> **True**. Aber verglichen wird Trade 3 (0.20 Lot) mit Trade 2 (0.01 Lot, Gewinn!).
- **Ergebnis:** Trade 1 (der Verlusttrade) wird mit KEINEM Trade verglichen. Die Lot-Eskalation nach dem Verlust von Trade 1 wird vollständig übersehen.
- Da Trade 1 und Trade 3 nicht zur selben Sekunde schließen, greift auch der Basket-Ladder-Test nicht.

#### Bewertung
Bei Systemen mit Einzel-Positionen (klassisches Reinkarnations-Martingale) funktioniert der Test perfekt. Bei Systemen, die während eines offenen Verlustes parallele Positionen eröffnen (Grid/Hedging), versagt der Nachfolger-Test für alle überlappten Verlusttrades.

---

### Befund 7 (P3 – Robustheit/Edge-Case): Case-Sensitivity und `NoneType`-Risiko bei Stop-Loss-Orderbuch-Prüfung

- **Kategorie:** Forensik / Stopps
- **Fundstelle:** [src/mqlkiscanner/forensics/stops.py:43-58](file:///d:/git/MQL/MqlKiScanner/src/mqlkiscanner/forensics/stops.py#L43-L58)
- **Status:** **BESTÄTIGT (Defensive Programming)**

#### Sachverhalt & Code
```python
sl_exits = [t for t in trades if t.comment == "[sl]"]
...
for t in with_sl_tp:
    sld = (t.entry_price - t.sl) * t.sign
    tpd = (t.tp - t.entry_price) * t.sign
```

#### Fehlermechanismus
1. **Case-Sensitivity:** Manche MT4-Broker schreiben Kommentare wie `[SL]` (Großbuchstaben) oder `[sl] 1.2345` (mit Ticket/Level). Der strikte String-Vergleich `t.comment == "[sl]"` bewertet solche Ausführungen als manuelle Exits.
2. **`NoneType` Subtraktion:** `with_sl_tp` filtert nur `t.sl and t.tp`. Wenn in einem unvollständigen Datensatz `entry_price` den Wert `None` hat, stürzt `(t.entry_price - t.sl)` mit einem `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'` ab.

#### Empfohlene Korrektur
```python
with_sl_tp = [t for t in trades if t.sl and t.tp and t.entry_price is not None]
sl_exits = [t for t in trades if t.comment and "[sl]" in t.comment.lower()]
```

---

### Befund 8 (P3 – Code-Qualität / Linter): 5 unbereinigte Linter-Verstöße

- **Kategorie:** Code Cleanliness / Wartbarkeit
- **Status:** **BESTÄTIGT**

Bei der Ausführung von `ruff check` werden 5 Verstöße gemeldet:
1. `src/mqlkiscanner/app_ui.py:7:52`: `info_button` importiert, aber unbenutzt (F401).
2. `src/mqlkiscanner/forensics/exposure.py:29:36`: `Trade` importiert, aber unbenutzt (F401).
3. `src/mqlkiscanner/mql5/signal_stats.py:32:60`: Variable `l` in Generator-Expression verletzt PEP8/E741 (Mehrdeutiger Variablenname).
4. `src/mqlkiscanner/scoring.py:141:5`: Lokale Variable `hard_block` zugewiesen, aber nie verwendet (Toter Code, F841).
5. `src/mqlkiscanner/secrets_store.py:12:21`: `Path` importiert, aber unbenutzt (F401).

---

## 4. Übersichtstabelle aller Befunde

| ID | Priorität | Komponente | Symptom / Ursache | Reproduzierbar? |
|---|---|---|---|---|
| **1** | **P1** | `mql5/signal_stats.py` | Zahlen mit Tausender-Komma (`1,085`) liefern `None`; Kennzahlen gehen verloren | **Ja** (Python-Einzeiler) |
| **2** | **P1** | `forensics/exposure.py` | FX-Paare mit Quote != USD (auch `USDJPY`, `USDCAD`) scheitern an Pflichtprüfung | **Ja** (Architekturregel) |
| **3** | **P2** | `forensics/exposure.py` | Non-USD-Indizes (`JP225`, `GER40`) werden mit 1:1 USD-Faktor gerechnet (Nikkei ~150x überbewertet) | **Ja** (Code-Inspektion) |
| **4** | **P2** | `db.py` / `pipeline.py` | Globales Portfolio nutzt `signal_id = 0`; bricht bei aktivem FK-Check ab | **Ja** (SQLite Schema) |
| **5** | **P2** | `app_pages/scan.py` | F5 im Browser verwaist Hintergrund-Thread; Mehrfachstarts führen zu Konflikten | **Ja** (Thread-Lifecycle) |
| **6** | **P2** | `forensics/martingale.py`| Intermittierende Trades lassen Verlusttrades aus dem Nachfolger-Test fallen | **Ja** (Logik-Trace) |
| **7** | **P3** | `forensics/stops.py` | Case-Sensitive `[sl]`-Prüfung und fehlender `None`-Check bei `entry_price` | **Ja** (Corner-Case) |
| **8** | **P3** | Diverse Module | 5 Linter-Fehler (Dead Code `hard_block`, ungenutzte Imports, E741) | **Ja** (`ruff check`) |

---

## 5. Verifikations-Anleitung für die nachfolgende KI

Um diesen Bericht zu überprüfen und Korrekturen abzusichern:

1. **Befund 1 prüfen:**
   ```bash
   python -c "import sys; sys.path.insert(0, 'src'); from mqlkiscanner.mql5.signal_stats import _number; assert _number('1,085') is None; assert _number('1,403.03') is None"
   ```
2. **Regressionstests ausführen:**
   ```bash
   pytest
   python scripts/verify_engine.py
   ```
   *Bedingung:* Alle 231 Tests und 85 Engine-Checks müssen grün bleiben.
3. **Linter prüfen:**
   ```bash
   ruff check src app_pages streamlit_app.py
   ```
   *Bedingung:* Nach Behebung von Befund 8 müssen 0 Fehler gemeldet werden.
