# Review-Handoff 29.09.2026 — offene Befunde L4–L15/M3: Verifikation, Fixes, Qualitätsbewertung

**Quelle:** KI-Handoff-Doku (21 Befunde gesamt; 9 ✅ + 1 📝 waren bereits in `093745c`
behandelt — Abnahme-Checks ausgeführt und bestanden).
**Ergebnis-Commit:** `daf4b11` — 11 offene Befunde geprüft, **alle 11 bestätigt,
alle 11 behoben**, 1016 Tests grün (1011 + 5 neue Regressionstests).

## Befunde und Fixes (Phasen-Plan des Handoffs)

| Befund | Verifikation | Fix |
|---|---|---|
| **L5** (einziger Ampel-kritischer) Zero-Volumen-Vorgänger → Phantom-Ratio ~1e7 → falsche harte 🔴 „Martingale" | ✅ | Paare mit `volume <= 0` übersprungen; Regressionstest mit 3 Zero-Volume-Paaren (flag false, n_after_loss 0) |
| **L4** GMT-Probe: rohes Symbol gegen UPPERCASE-Index → Auto-GMT rutscht unter Trefferquote → Reko unnötig skipped | ✅ | `.strip().upper()` im Aufruf; Test mit `xauusd.sc` (Plateau-sichere Bänder — Preis-Toleranz ~±0,1 % macht enge Bänder mehrdeutig) |
| **L6** `_bar_fuer` nimmt bei fehlender Stunde die vorherige Bar als Kurs | ✅ | Exakter `mappe.get(stunde)` wie Kurvenseite; Test beweist über Preis außerhalb jedes Bandes (alt: Quote 0,5/kein Offset; neu: Offset eindeutig 0) |
| **L9** Martingale zählt nach Brutto statt Netto | ✅ | `net` (Kommission/Swap) mit Brutto-Fallback; Test: profit +2/Kommission −5 → Nach-Verlust-Menge |
| **M3** Docstring „Deckung auf den Cent" vs. echte Toleranz max(5 USD, 2 %) | ✅ | Docstring korrigiert |
| **L14** NaN in Equity-Kurve → still „0 % DD, verlässlich" | ✅ | isfinite-Guard → ehrlicher Skip mit Grund |
| **L12** `kursdaten_beenden()` außerhalb try/finally → MT5-Terminal-Leak bei unerwarteter Exception | ✅ | Beide Scan-Wege (GUI + autonom) in try/finally; `beenden()` idempotent |
| **L10** Toter Code `consistency_usd_dd` mit KeyError-Risiko | ✅ | Entfernt (null Aufrufer verifiziert) |
| **L13** Irreführender „neu holen"-Kommentar | ✅ | Korrigiert (kein zusätzlicher Kursabruf) |
| **L15** flag (per-Symbol-OR) vs. globales Median im selben JSON | ✅ | Variante (a): Zusatzfeld `median_ratio_after_loss_per_symbol_max`; KEINE Verhaltensänderung (Variante b nur mit Nutzer). Test zeigt das Szenario im Vollzug (global 1,0 + flag true + Max 2,0) |
| **L11** MT5-Aufrufe ohne Timeout | ✅ | Known-Limitation im kursdaten-Modul-Docstring (bewusst Doku statt Thread-Timeout-Komplexität) |
| F-FLAKY (zu beobachten) | laut Handoff Lauf-Artefakt | Nicht vorsorglich geändert; sauberer Voll-Lauf grün |

## Abnahme-Checks des Handoffs (alle bestanden)

Alte GUI-Texte weg (0 Treffer) · toter Code weg · kein `profit <= 0` mehr in
Verlustzählungen — mit einer bewussten Ausnahme (`stops.py` sl_exits:
SL-Exit-Klassifikation, ein Ausgang auf dem Stop ist auch bei 0 PnL ein
Stop-Ausgang) und einer Konsistenz-Nachlese: Der Check deckte **zwei weitere
Stellen in `trade_data.py`** auf (Verlustliste + Serie im LLM-Trade-JSON) —
auf dieselbe F4-Breakeven-Definition gebracht (`profit < 0`).

## Qualitätsbewertung des Handoff-Reviews

| Kriterium | Bewertung |
|---|---|
| Befundqualität (11/11 real, Snippets wortgetreu) | **5/5** |
| Übergabe-Struktur (Phasen-Plan, Abnahme-Checks, Nicht-berühren-Liste, ID-Mapping) | **5/5** — beste Übergabe der Serie |
| Ehrlichkeit (Flaky-Verdacht selbst entkräftet als Lauf-Artefakt) | **5/5** |
| Fix-Vorschläge (alle zielführend; L15 mit korrekter Risiko-Einschätzung) | **5/5** |

**Gesamt: bestes Review des Tages** — kein Gegenbefund, keine falsche Angabe;
einzige Lücke: die zwei `trade_data.py`-Stellen hätte es als Befund listen können
(aufgefallen über den eigenen Abnahme-Check).

## Bei der Umstellung selbst gefangen

Erster try/finally-Wrap (L12) mit Einrückungsfehler — von `py_compile` gefangen,
Dateien aus Git restored, korrekt neu gebaut. GMT-Testdesign zweimal angepasst
(Plateau durch Preis-Toleranz; geliehene-Bar-Beweis über Out-of-Band-Preis).
