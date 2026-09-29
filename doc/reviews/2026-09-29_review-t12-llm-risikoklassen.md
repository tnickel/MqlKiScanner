# Review T1/2 29.09.2026 — LLM-Bewertung & Risikoklassen: Verifikation, Fixes, Qualitätsbewertung

**Review-Objekt:** Commit `6a5b3ac` — Umfang LLM-Layer (`llm/`, `llm_runner.py`, LLM-Teile
`pipeline.py`), Risikoklassen (`scoring.py`, `ampel_matrix.py`, `regelwerk.py`), `stats.py`,
`trade_data.py`, Forensik-Modul 1/2. Geprüft gegen die bindenden AGENTS.md-Regeln
(Code rechnet/LLM interpretiert, SL-Neutral seit 28.09., Vierfach-DD-Schranke, zwei­stufiges
LLM mit Budget).
**Ergebnis-Commit:** `093745c` — 9 Befunde geprüft, 8 behoben, 1 bewusst dokumentiert
(F3), 1011 Tests grün.

## Befunde und Verifikation

| Befund | Verifikation | Fix |
|---|---|---|
| **M1** 🟠 `_dd_zelle` wertet Dreifach- statt Vierfach-Maximum — Urteil ROT kann vom eigenen Audit-Nachweis (GRÜN) widersprochen werden | ✅ bestätigt | Reko-EQ-DD als vierter Wert + Tooltip; Tests: Zelle ROT bei Reko 35 % allein, Detail nennt „Reko-EQ-DD 35,00 %" |
| **M2** 🟠 Kriterien-Text „Stop-Loss muss BEWIESEN sein" widerspricht der bindenden Neutral-Regel im selben Prompt (3 Prompts betroffen) | ✅ bestätigt — heikelster Fund (kann SL-Neutral-Regel praktisch aushebeln) | Neutral-Wortung: bewiesener SL entlastet, fehlender Nachweis neutral/kein Abwertungsgrund |
| **M3** 🟡 Token-Audit speichert kumulierten Lauf-Zähler statt Einzelkosten (llm_runner, pipeline, 6 Agenten-Module) | ✅ bestätigt — **aber Gegenbefund:** `meta_out["total_tokens"]` (des Reviews „korrektes Datum") EXISTIERTE NICHT in call_meta; alle meta.get-Fallbacks liefen immer in den Kumulat | Feld in `call_meta` ergänzt; alle 10 Dateien auf pro-Call-Wert mit Kumulat-Fallback umgestellt |
| **M4** 🟡 5 veraltete GUI-Texte beschreiben das vor-28.09.-System | ✅ bestätigt (alle 5 Stellen verifiziert; regelwerk-Position 29 wie empfohlen nicht geändert) | Vierfach-Maximum + SL-neutral in regelwerk.py (3×), help_content.py, Matrix-Tooltip |
| **M5** 🟢 Budget-Check vor Call / Abrechnung nach Response — parallele Stages können beide passieren | ✅ bestätigt (ThreadPoolExecutor(2) in llm_runner) | Konservative Reservierung vor dem Absenden (max_tokens + Prompt-Schätzung), Auflösung bei Antwort, finally-Freigabe; Test blockt VOR Kosten |
| **F1** 🟢 Exposure vs. Drawdown: inkompatible Kapitalbasis-Injektionsbedingungen (+100/−200-Szenario) | ✅ bestätigt (Szenario nachgestellt) | Drawdown auf Exposure-Bedingung; Tests: identisches Paar + Normalfall-Injektion |
| **F2** 🟢 stops.py-Moduldocstring alte Warnflag-Regelung | ✅ bestätigt | Neutral-Wortung |
| **F3** 🟢 Gesamt-Cluster-Urteil bei Multi-Symbol praktisch unerreichbar (offene Designfrage, konservativ) | ✅ bestätigt | **Bewusst NICHT geändert** — verwehrt nur Entlastung, erzeugt nie falsch-positive Stops; Entscheidung im Code dokumentiert. Verhaltensänderung der Entlastungslogik = Nutzerentscheidung |
| **F4** 🟢 Breakeven (profit == 0) zählt als Verlust in die Serie | ✅ bestätigt — **aber unvollständig:** Review nannte nur stops.py; die Berichts-Kennzahl `max_consecutive_losses` kommt aus stats.py (eigene Schleife, gleiches `<= 0`) | `profit < 0` in BEIDEN Modulen; Test: Serie 2 statt 3 |

## Eigener Fehler beim Umbau (von den neuen Tests gefangen)

Einrückungs-Skript für client.py verschob `return content` in einen unereichbaren
Block → „GLM-Aufruf fehlgeschlagen" in test_chat_meta…; gefunden und behoben, bevor
irgendwas in Produktion ging.

## Qualitätsbewertung des Reviews

| Kriterium | Bewertung |
|---|---|
| Befundqualität (9/9 real, korrekte Dateien/Zeilen) | **5/5** |
| Projektregeln als Prüflatte (AGENTS.md: Vierfach-Max, SL-Neutral, Budget) | **5/5** — erstes Review, das die Regeln aktiv anlegt |
| Vollständigkeits-Ehrlichkeit („ohne Befund"-Listen mit Substanz, Teil 2/2 offen deklariert) | **5/5** |
| Fix-Vorschläge | **4/5** — M3: Feld existierte nicht; F4: zweite Stelle (stats.py, die berichtsrelevante) übersehen |
| Gewichtung der Schweregrade | **5/5** |

**Gesamt:** auf Augenhöhe mit dem besten Review des Tages (Übergabe-Review). Highlight
ist M2 — ein Prompt-Widerspruch, der die bindende SL-Neutral-Regel (Nutzer-Regel
28.09.2026) in der Praxis aushebeln konnte. Beide Schwächen lagen im Lösungsteil.

**Hinweis für Teil 2/2** (martingale, drawdown, equity_rekonstruktion, kursdaten):
drawdown.py hat heute die F1-Änderung erhalten (Injektionsbedingung an Exposure
angleichen) — Zeilennummern können abweichen.
