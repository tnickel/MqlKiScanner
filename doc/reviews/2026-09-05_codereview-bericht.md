# Code-Review-Bericht MqlKiScanner — Prüfbericht für eine nachfolgende KI

```yaml
datum: "2026-09-05"
commit: "b3a3900 (main, == origin/main)"
reviewer: "ZCode (GLM-5.3), vollständiges manuelles Review"
gegenstand: "Static + datenvalidiertes Review des gesamten Produktivcodes"
umfang_zeilen: 6310 Python (src/, app_pages/, tests/, scripts/, streamlit_app.py)
auftrag_an_pruefende_ki: >
  Verifiziere jeden unten stehenden Befund (F1-F19) unabhängig nach.
  Jeder Befund enthaelt Ort (Datei:Zeile), Behauptung, Beweis und eine
  kopierfaehige Reproduktion. Melde je Befund: BESTAETIGT / WIDERLEGT /
  BESTAETIGT-MIT-EINSCHRAENKUNG, mit eigenem Beweis. Fixe nichts ohne
  Rueckmeldung an den Nutzer — dieser Bericht ist Pruefauftrag, kein Fixauftrag.
wichtig_fuer_pruefende_ki: >
  Die Engine hat 83/83 Anker-Checks gegen die Analyse-Reihe bestanden und
  38/38 Unit-/UI-Tests sind gruen. Die Befunde F1/F2 liegen ausserhalb der
  Kalibrierungs-Szenarien (dort fallen Peak-Count und Peak-Volumen zusammen);
  sie sind deshalb von den Anker-Checks NICHT abgedeckt — das ist kein
  Widerspruch, sondern der Kern des Befunds.
```

---

## 1. Gesamteinschätzung

Solide, diszipliniert aufgebaute Codebasis mit klarer Schichtung (Engine
rechnet / LLM formuliert / UI duenn), durchdachtem Secret-Konzept und einer
aussergewoehnlich guten Absicherung durch Anker-Checks (`scripts/verify_engine.py`,
83 Checks gegen die Analyse-Reihe) und Tests (38, inkl. Streamlit-AppTest).

**Zwei substanzielle Schwächen betreffen genau den Kern des Tools — die
Risikomessung:** Die Peak-Exposure-Ermittlung (F1, F2) wählt ihren
Messzeitpunkt nach Positionen-**Anzahl** statt nach **Volumen** und rechnet
Multi-Symbol-Portfolios mit einem einzigen Kontrakt-Faktor um. Beides kann
das Dollar-Schockrisiko um Faktoren verfälschen (in beide Richtungen). Bei
den 9 Kalibrier-Datensätzen fällt das nicht auf, weil dort (z. B. PureGold:
nur XAUUSD, Peak-Count == Peak-Volumen) die verausgabten Pfade zusammenfallen.

Dazu 4 mittelgradige Befunde (F3-F7: DD-Doppelzaehlung im Diagnostikwert,
lückenhafte 30-%-Schranke, crash-anfaelliges LLM-Error-Handling,
unvalidierter Browser-Download in den CSV-Cache) und 12 kleinere/Hinweise.

---

## 2. Verifizierter Soll-Zustand (vom Reviewer gemessen, bitte stichprobenartig nachmessen)

| Prüfung | Befehl | Ergebnis |
|---|---|---|
| Engine-Anker vs. Analyse-Reihe | `python scripts/verify_engine.py` | **83 PASS, 0 FAIL** |
| Test-Suite | `python -m pytest tests/ -q` | **38 passed** |
| Score-Kalibrierung | `python scripts/calibrate_scoring.py` | Max-Abweichung MSC +1,3; Rest ±0,4 |
| Secrets im Repo | `git log --all -p` grep + `git ls-files` | keine (`.env`, `secrets.local.json`, `mql5_cookies.json`, `chrome_profile/` sauber ignoriert) |
| Parser-Spalten vs. echte Header | `head -2 data/raw/*.csv` | Positions: 11 Spalten, Profit=Idx 10 ✓; Orderbuch: 13 Spalten, Profit=Idx 11, Comment=Idx 12 ✓ |

Struktur-Regeln aus AGENTS.md, deren Einhaltung code-seitig bestätigt wurde:

- R1 „LLM rechnet nie": `llm/prompts.py` + `pipeline.py:429-455` liefern nur
  fertige JSONs; keine Roh-Trades, keine Zugangsdaten im LLM-Kontext. ✓
- R5 „Credentials nur im Crawler-Modul": `secrets_store.py` ist die einzige
  Quelle; Admin-UI zeigt nur Booleans. ✓
- R2 „keine positive Einstufung vor Forensik": `pipeline.py:159-177`
  (ampel_for) verlangt `forensik_vorhanden` für 🟢/🟡. ✓ (Aber siehe F4:
  die *harte* DD-Schranke hat eine Lücke.)
- Rate-Limit/Fail-Fast mit Tests abgedeckt (`tests/test_mql5_fail_fast.py`). ✓

---

## 3. Befunde (nach Schwere sortiert)

Schwere: **E** = erheblich (Kernfunktion Risiko fehlerhaft anfaellig) ·
**M** = mittel · **N** = niedrig · **I** = Information/Design-Hinweis.

### F1 — Exposure: Peak wird nach Positionen-Anzahl, nicht nach maximalem Nettovolumen gewählt 【E】

- **Ort:** `src/mqlkiscanner/forensics/exposure.py:70-86`
- **Behauptung:** Die Ereignisschleife aktualisiert `peak_long/peak_short/peak_time`
  nur, wenn `open_count > peak_count` (Zeile 76). Das maximale aggregierte
  (Netto-)Volumen kann zu einem *anderen* Zeitpunkt auftreten als die maximale
  Anzahl offener Positionen. `shock_usd` wird dann auf den Volumensstand des
  Count-Peaks berechnet — das echte Maximum wird verpasst.
- **Beweis (vom Reviewer ausgeführt):**

  ```python
  # 1 grosse Position (5.0 Lots, 10 h) vs. spaeter 3 Mini-Positionen (0.3 Lots)
  # exposure.run(...) liefert:
  #   peak_open_positions = 3 | peak_net_lots = -0.3 | shock_usd = 1500.0
  # Korrekt: Schock auf max |netto| = 5.0 Lots -> 5 x 50 x 100 = 25 000 USD
  ```
- **Auswirkung:** `shock_usd`, `scoring.py` Dimension `margin`
  (`scoring.py:81-86`), `ScanResult.shock_usd`, UI-Metrik „50-USD-Schock"
  und LLM-Prompt-Daten können das Schockrisiko um beliebig grosse Faktoren
  *unterschätzen* (Signale mit wenigen grossen Positionen). Ueberschätzung
  ist ebenfalls moeglich. Genau die Nutzer-Kernfrage („wie hoch ist das
  reale Exposure?") ist betroffen.
- **Fix-Richtung:** Beim Sweep zusaetzlich den Zeitpunkt des maximalen
  `|peak_long - peak_short|` (je Symbol, s. F2) tracken und beide Peak-Masse
  (nach Count und nach Volumen)reporten; Schock auf dem Volumen-Peak berechnen.
- **Nachpruefung:** Obiges Mini-Beispiel gegen `exposure.run` fahren;
  danach pruefen, ob `verify_engine.py`-Anker (PureGold 32 Pos / 2,66 Lots /
  13 300 USD) nach dem Fix weiterhin PASSen (dort fallen beide Peaks zusammen,
  muss stabil bleiben).

### F2 — Exposure: Multi-Symbol-Portfolio wird mit einem einzigen Kontrakt-Faktor umgerechnet 【E】

- **Ort:** `src/mqlkiscanner/forensics/exposure.py:81-102` (`net = peak_long - peak_short`
  ueber ALLE Symbole; `sym = peak_symbol` ist das Symbol des *letzten Events*
  beim Count-Peak, Zeile 79)
- **Behauptung:** Long/Short-Volumina werden ueber alle Symbole aggregiert,
  der USD-Schock aber mit `CONTRACT_FACTOR_PER_UNIT[symbol_class(peak_symbol)]`
  eines einzigen Symbols berechnet. Der Faktor unterscheidet sich je Klasse um
  bis zum Faktor 100 000 (INDEX 1 vs. FX 100 000).
- **Beweis (real, KiraCat #2342895, US30 + NZDCAD gemischt):**

  ```text
  peak_long_lots = 1.95   symbol_class = FX   shock_usd = 9750.0
  Formel: 1.95 Lots x 0.05 x 100000 = 9 750 USD
  ```
  Die 1,95 Lots sind ein Gemisch aus US30- (Faktor 1) und NZDCAD-Positionen
  (Faktor 100 000). Waeren es ueberwiegend US30-Scalps, laege der echte Schock
  nahe 97,50 USD; waeren es NZDCAD, bei 9 750 USD. Der ausgewiesene Wert ist
  damit um bis zum Faktor ~100 unbestimmt — in beide Richtungen.
- **Auswirkung:** Wie F1: Kernkennzahl `shock_usd` fuer alle Multi-Symbol-
  Signale (KiraCat, FXtrading, kuenftige Scan-Kandidaten) unzuverlaessig.
  Einschraenkung: Es handelt sich um eine *konservative* Ueberschätzung, wenn
  zufaellig der FX-Faktor gewinnt — aber das ist Zufall (`peak_symbol` haengt
  an der Reihenfolge der Events), keine Methode.
- **Fix-Richtung:** Long/Short-Volumen **je Symbol** zum Peak-Zeitpunkt
  fuehren, Schock je Symbol mit dessen Klassenfaktor berechnen und summieren;
  `shock_formula` entsprechend je Symbol ausgeben.
- **Nachpruefung:** KiraCat-Report wie oben ausgeben; Plausibilisieren, dass
  `peak_symbol` von der Event-Reihenfolge abhaengt (Zeile 79 setzt es bei
  jedem neuen Count-Peak neu).

### F3 — Drawdown: `end_balance_estimated` zählt Startkapital doppelt 【M】

- **Ort:** `src/mqlkiscanner/forensics/drawdown.py:72`
- **Behauptung:** `end_balance_estimated = deposits_start + flows_total + net_total`,
  wobei `flows_total = deposits_total + withdrawals_total` (Zeile 63) die
  Einzahlungen vor dem ersten Trade (`deposits_start`, Zeile 52) bereits
  enthaelt. Einzahlungen vor dem ersten Trade werden doppelt gezaehlt.
- **Beweis (real):**

  ```text
  kiracat: Engine 10 535,48  korrekt (flows+net) 1 000,00  Differenz = 9 535,48 = deposits_start
  reaper : Engine  7 661,69  korrekt              6 046,64  Differenz = 1 615,05 = deposits_start
  ```
- **Auswirkung:** Nur Diagnostik-Feld im Engine-Report-JSON (`analyze_to_json`);
  nicht in Scoring, Ampel oder LLM-Prompts (`_forensik()` in pipeline.py
  uebergibt es nicht). Keine Fehlentscheidung, aber eine falsche Zahl in
  Befund-JSONs, die Dritten (und dem LLM via Trade-Payload? — nein, auch dort
  nicht enthalten) begegnen kann. Mittel wegen des Anspruchs „Befunde stimmen
  auf den Cent".
- **Fix-Richtung:** `end_balance_estimated = deposits_total + withdrawals_total + net_total`.
- **Nachpruefung:** `engine.analyze('data/raw/kiracat_2342895_positions.csv')['forensics']['drawdown']`
  gegen `deposits_total + withdrawals_total + net_total` abgleichen.

### F4 — Harte 30-%-Drawdown-Schranke prüft nur den Plattform-EQ-DD, nie den rekonstruierten Trading-DD 【M】

- **Ort:** `src/mqlkiscanner/scoring.py:122-136` (`barrier = eq_dd > 30.0`,
  `eq_dd` nur aus `platform`), `pipeline.py:639` (lokal: `evaluate(report)`
  ganz ohne `platform` → `eq_dd = 0`), `pipeline.py:149-151` (DB-Pfad: nur
  wenn `dd_equity_pct is not None` wird `schranke_verletzt` gesetzt)
- **Behauptung:** AGENTS.md definiert „Harte Drawdown-Schranke: 30 % max" als
  hartes Kriterium. Implementiert ist sie nur gegen den *von der Plattform
  gemeldeten* EQ-DD. Faellt dieser weg (Crawl-Fehler, lokaler CSV-Modus,
  DB-Eintrag ohne Kennzahlen), greift die harte Schranke **gar nicht** — auch
  wenn die Engine selbst einen rekonstruierten Trading-DD von z. B. 40 %
  ausgerechnet hat. Der reale DD fliesst nur *weich* ueber die Score-Dimension
  `drawdown` ein.
- **Auswirkung:** Ein Kandidat kann 🟢 werden, obwohl die eigene Rekonstruktion
  die Schranke reisst (Voraussetzung: Plattform-DD fehlt und Score < 5 und
  Ertrag ok). Widerspricht der Nutzer-Regel „Risiko VOR Ertrag".
- **Fix-Richtung (Vorschlag):** `barrier = max(real_dd, eq_dd) > schranke`
  ausser im dokumentierten `eq_dd_caveat`-Fall (KiraCat-Fussnote); oder
  mindestens: fehlender `eq_dd` bei vorhandenem `real_dd > Schranke` → Flag.
  Das ist eine Design-Entscheidung mit Nutzer abzustimmen.
- **Nachpruefung:** `scoring.evaluate(report_eines_40%-DD-Export_ohne_platform)`
  → `schranke_eq_dd_verletzt == False` zeigen.

### F5 — `stats.max_loss_streak_from` ist der Eröffnungszeitpunkt des LETZTEN Serien-Trades, nicht der Serienbeginn 【N】

- **Ort:** `src/mqlkiscanner/stats.py:43` (`streak_start, streak_end = t.open_time, t.close_time`
  wird bei jedem neuen Maximum neu gesetzt → Endstand = letzter Serien-Trade);
  korrekt macht es `forensics/stops.py:137-138` (`best_window[0].open_time`)
- **Beweis (synthetisch):** Serie von Verlust-Trades am 1./2./3. Januar →
  `max_loss_streak_from = 2026-01-03 10:00:00` statt `2026-01-01`.
- **Auswirkung:** Nur Report-Felder (`max_loss_streak_from/_to`); die Pipeline
  uebernimmt lediglich Laenge und Summe (`pipeline.py:312-313`). Bei PureGold
  fällt es zufaellig auf denselben Kalendertag. Niedrig, weil reine
  Fehlbeschriftung im Befund-JSON.
- **Fix-Richtung:** `best_streak_window[0].open_time` / `[-1].close_time` wie in stops.py.
- **Nachpruefung:** Synthetik-Beispiel von oben.

### F6 — LLM-Client: defekte API-Antworten (fehlerhafte JSON-Struktur) werfen ungefangene KeyError/IndexError/ValueError und reissen den ganzen Schritt-4-Lauf 【M】

- **Ort:** `src/mqlkiscanner/llm/client.py:120-123` (`data = r.json()` →
  `ValueError` bei Nicht-JSON-200; `data["choices"][0]` → `KeyError/IndexError`
  bei leerer choices-Liste), Eskalation in `pipeline.py:541-546` (`raise first_err`)
  und `pipeline.py:574-587` (fangen nur `LlmNoBalanceError`/`LlmError`)
- **Behauptung:** Ein einziger malformed Response (z. B. HTML hinter einer
  200-Antwort, Gateways tricks damit) laesst die Exception an `run_llm`
  vorbei-escapieren. Der Scan-Step-Handler in `app_pages/scan.py:517` faengt
  sie als Schritt-Fehler — alle *restlichen* Kandidaten des LLM-Schritts
  verlieren dann ihren Bericht, obwohl ein Einzelfehler wie bei `LlmError`
  behandelbar waere (continue mit naechstem Kandidat).
- **Auswirkung:** Robustheit: Ein transienter Provider-Glitch skaliert auf
  alle uebrigen Signale des Laufs. Keine falschen Zahlen.
- **Fix-Richtung:** JSON-Parsing in try/except → `LlmError`; in `pipeline.run_llm`
  BaseException der Teilprompts bereits an der Thread-Ergebnis-Stelle in
  `LlmError` ummanteln oder breiter fangen.
- **Nachpruefung:** Codepfad-Lesen; optional Monkeypatch `requests.post` →
  200 mit HTML-Body in einem Pipelinetest.

### F7 — Browser-CSV-Export verschobt Downloads ungeprüft in den 24-h-Cache 【M】

- **Ort:** `src/mqlkiscanner/mql5/browser_session.py:262-279`
- **Behauptung:** `export_positions_via_browser` nimmt die erste `.csv`-Datei
  aus dem Staging-Verzeichnis und verschiebt sie nach
  `data/trades/{id}_positions.csv`, **ohne** den `Time;`-Header-Check, den der
  HTTP-Pfad hat (`session.py:101`). Laedert Chrome eine Fehler-/Login-Seite
  als `.csv` (oder eine stale Datei), vergiftet das den Export-Cache fuer 24 h
  (`exporter.py:23-26` liefert die Datei dann ungeprueft aus dem Cache) und
  der Fehler zeigt sich erst spaeter als kryptischer Parser-Fehler.
- **Auswirkung:** Datenqualitaet/Robustheit des Forensik-Inputs. Der Parser
  lehnt die Datei zwar ab (keine falschen Zahlen), aber Ursache und Wirkung
  driftet auseinander und ein erneuter Lauf wird vom Cache blockiert.
- **Fix-Richtung:** Vor `shutil.move` pruefen: Datei beginnt (BOM-tolerant)
  mit `Time;`, sonst `RuntimeError` und Datei verwerfen.
- **Nachpruefung:** Code-Lesen; optional Staging-Fake mit HTML-Inhalt .csv.

### F8 — Z.ai-Fehlercode-Vergleich typempfindlich; 1113 ausserhalb von 429 unerkannt 【N】

- **Ort:** `src/mqlkiscanner/llm/client.py:102-114`
- **Behauptung:** `err.get("code") in ("1113", "1302")` vergleicht String —
  liefert die API den Code numerisch, greift die Sonderbehandlung
  (`LlmNoBalanceError` mit Endpunkt-Hinweis) nicht. Zudemand wird der Code nur
  im 429-Zweig geprueft; 1113 mit HTTP 4xx (≠429) faellt in die generische
  `LlmError`-Meldung (Zeile 118-119) und der Aufloese-Hinweis geht verloren.
- **Fix-Richtung:** `str(err.get("code"))` vergleichen; JSON-Body-Code auch
  bei anderen 4xx pruefen.

### F9 — SQLite-Connections werden nie geschlossen 【N】

- **Ort:** `src/mqlkiscanner/db.py:65-69` (`_connect` ohne `close`;
  `with conn:` regelt nur Transaktion, schliesst nicht)
- **Auswirkung:** Pro DB-Operation eine offene Connection bis zum GC. Bei
  langen Laeufen viele Handles; unter Windows Potential fuer Dateilocks.
  Aktuell kleine Last, daher niedrig.
- **Fix-Richtung:** `contextlib.closing(sqlite3.connect(...))` kombinieren.

### F10 — Demo-Modus überschreibt den Engine-Score mit kuratierten Sollwerten 【N / Design】

- **Ort:** `pipeline.py:642-646` (`r.score = meta[sid].get("score", r.score)`
  aus `known_signals.json` für Empfehlungs-/Watchlist-IDs)
- **Behauptung:** Im lokalen Verifikationsmodus zeigt die UI den kuratierten
  Score, nicht den gerechneten. Kalibrierungsdrift (z. B. MSC +1,3) wird in
  dieser Ansicht unsichtbar. Bewusst? Dann im Bericht der UI kenntlich
  machen („kuratierter Referenzscore"), sonst entfernen.
- **Nachpruefung:** `known_signals.json` Scores vs. `calibrate_scoring.py`-Ist.

### F11 — Exposure-Result ohne `flag`/`interpretation`, obwohl Docstring „Rote Flagge > 30 % des Kontos" verspricht 【N / Konsistenz】

- **Ort:** `forensics/exposure.py:12-14` (Docstring) vs. `:88-108` (Result);
  die 30-%-Bewertung passiert indirekt erst in `scoring.py` (SHOCK_MAP).
  Fuer Konsistenz mit martingale/stops ein `flag`-Feld ergaenzen oder
  Docstring angleichen.

### F12 — FOMC-Liste hartcodiert, läuft 2026 stillschweigend leer 【N】

- **Ort:** `forensics/news.py:13-18` (letzter Eintrag 2026-07-29). Danach
  sinkt `fomc_days_in_period` stetig; `filter_hint` wird zufaellig.
  Empfehlung: Pflegeroutine oder Liste bis Jahresende + Warnung, wenn der
  Datenzeitraum die Liste ueberragt.

### F13 — Martingale-Korridortest: Leitern ohne kleinste erstes Bein werden übersprungen (bewusst), Sorting-Detail 【N / Design】

- **Ort:** `forensics/martingale.py:56-64`. `if vols[0] > min(vols): continue`
  ist dokumentierte False-Positive-Vermeidung (KiraCat). Randfall: Beine mit
  identischer `open_time` haben keine definierte Volumen-Reihenfolge (stable
  sort nur nach open_time). Dokumentiert lassen; ggf. sekundaer nach Volumen sortieren.

### F14 — Crawler-Zahlenparser verwirft Komma-Tausender («1,403» → None) 【N】

- **Ort:** `mql5/crawler.py:23-35` (`_num`). Aktuelle Karten nutzen
  Leerzeichen-Trenner; bei Formatwechsel fallen Kennzahlen still auf None
  (Filter/Sortierung greifen dann nicht). Robustheit wie
  `signal_stats._number` nachziehen.

### F15 — Hard-Fail-Reset nur bei Forensik-Erfolg mit Trade-Export 【N】

- **Ort:** `pipeline.py:344` — `_register_mql5_outcome(ok=True)` steht im
  `if report is not None:`-Block. Eine erfolgreiche Kennzahlen-Seite ohne
  Export (kein Login/Cache) resettet den MQL5-Hard-Fail-Zaehler nicht.
  Konsistenzfrage, keine akute Gefahr.

### F16 — Login-Heuristik substring-basiert 【N】

- **Ort:** `mql5/session.py:39-50` (`">Logout<"`/`"Log out"` im ganzen
  Seitentext). False Positives durch Seitentexte denkbar. Pragmatisch;
  alternativ auf `/en/auth_logout`-Link beschraenken.

### F17 — Score-Kalibrierung driftet bei MSC Gold 【I】

- `scripts/calibrate_scoring.py`: MSC Soll 5,6 / Ist 6,9 (+1,3); Schranke
  greift korrekt (EQ-DD 33,7 % > 30). Uebrige ±0,4. Kein Bug — fuer die
  Abnahme dokumentieren oder MAPS nachjustieren.

### F18 — p90-Index approximiert 【I】

- `trade_data.py:103`: `durs[int(len(durs) * 0.9)]` ist bei n=10 der Max-Wert.
  Kosmetik in der LLM-Payload.

### F19 — Hartcodierter Schranken-Text «EQ-DD > 30 %» bei konfigurierbarer Schranke 【N】

- **Ort:** `pipeline.py:168` (Ampeltext) — Schrankenwert kommt aus Settings
  (`schranke_eq_dd_pct`, 0,1-30 einstellbar in `admin.py:291`), Text bleibt
  «30 %». Bei veraenderter Schranke zeigt die UI falschen Text. Ebenso
  `admin.py:296-297` («Engine akzeptiert Ertrag ≥ Schwelle» — ok) und
  Prompt-Text `kriterien` ist dynamisch (gut).

---

## 4. Bereiche ohne Befund (vom Reviewer geprüft)

- **Parser** (`parser.py`): Spaltenindizes gegen beide realen Header
  verifiziert; BOM (`utf-8-sig`), NBSP/Leerzeichen-Tausender, Kurzzeilen,
  Login-HTML-Erkennung korrekt. Kleiner Hinweis: `volume=float(row[2])`
  nutzt nicht `parse_number` (bei Volumen ohne Tausender praktisch folgenlos).
- **Martingale-Nachfolger-Test** (`martingale.py:23-40`): Median-Logik und
  Nicht-Ueberlappungs-Bedingung stimmen mit Spec `doc/03` ueberein;
  PureGold-Anker (0,92x / 1,00x) bestätigt.
- **Stops** (`stops.py`): Orderbuch-Evidenz, Cluster-Heuristik (Share ≥ 25 %
  bei gerundetem Niveau; free-running < 10 % && Spread ≥ 10) nachvollziehbar;
  „kein Nachweis = Warnflag" ist in Scoring/Ampel verankert.
- **Drawdown-Rekonstruktion** (`drawdown.py`): Trading-Kurve (Start =
  Einzahlungen vor erstem Trade, Netto je Close) reproduziert alle 4
  Cent-Anker (76,83 / 319,49 / 157,20 / 2 117,70 USD). Einziger Fehler ist F3
  (end_balance_estimated).
- **Baskets, News, Stats, Compare**: Anker-checked; `compare.py` Matching
  (exakt + fuzzy) nachvollziehbar, `only_mt5`-Semantik (MT5 ungefiltert gegen
  MT4-Fenster) ist dokumentiertes Verhalten, aber beachtenswert.
- **Secrets**: Konzept (Env > .env > secrets.local.json), gitignore-Wirksamkeit
  (check-ignore), keine Secrets in Code/History, chmod 0600 best effort,
  UI zeigt nur Booleans, Tests sichern Nicht-Disclosure.
- **Rate-Limit/Fail-Fast**: RateLimiter (Mindestabstand+Jitter),
  429/503-Backoff, 403-Hardstop, Fail-Fast-Zaehler — durch Tests abgedeckt.
- **UI/Pipeline-Workflow**: Schritt-Statusmaschine, Unterbrechungs-Behandlung
  (`scan.py:80-88`), Fortschrittszaehlung «nur fertige Prompts» — durch
  Tests abgedeckt; `ui_design.py` reine Praesentation.

## 5. Nicht tief geprüft

- `src/mqlkiscanner/help_content.py`, `help_scan.py`, `help_settings.py`
  (reine Hilfetexte, ueberflogen), `scripts/reference/*` (historische
  Referenzimplementierungen, nicht produktiv), `assets/`, `doc/reports/*`
  (PDFs), `.streamlit/config.toml`.

## 6. Empfohlene Reihenfolge für die Nacharbeit (nach Nutzer-Freigabe)

1. F1 + F2 gemeinsam (Exposure je Symbol + Volumen-Peak) — Kernrisiko;
   danach zwingend `verify_engine.py` erneut 83/83 erwarten.
2. F4 (Schranken-Design mit Nutzer klaeren: `max(real, eq)` vs. nur eq).
3. F7 (Browser-Download validieren) und F6 (LLM-Fehler typisieren).
4. F3, F5 (Billig-Fixes im Befund-JSON).
5. Rest nach Belieben.

---

*Bericht erzeugt am 2026-09-05 durch vollständiges manuelles Review (alle
45 Produktiv-Dateien gelesen; 4 gezielte Datenvalidierungen gegen
`data/raw/` ausgeführt). Er ist bewusst so formatiert, dass eine andere KI
jeden Befund mit den angegebenen Befehlen unabhängig reproduzieren kann.*
