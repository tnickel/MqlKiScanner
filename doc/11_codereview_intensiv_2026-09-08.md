# Intensiv-Code-Review MqlKiScanner — 2026-09-08 (Runde 3, KI-nachprüfbar)

## 0. Zweck undStand

Zweiter intensiver Review-Durchlauf (nach doc/10 vom 2026-09-07). Geprüft:

1. Die drei Commits seit dem ersten Review, die von einer anderen Seite
   eingespielt wurden und dort noch nicht von mir reviewt waren:
   `ecf9d4f`, `f0b2245`, `68a7717` (u. a. 341 geänderte Zeilen pipeline.py,
   vier neue Module, Umbau run_llm -> llm_runner, DB-Schema basis-Spalte).
2. Adversarielle Gegenprüfung der eigenen Neubauten aus 2026-09-08
   (contract_specs.json-Anbindung, fx_rates.py EZB-Kurse, exposure-Umbau).

Referenzstand: HEAD = `68a7717` PLUS unveröffentlichte Arbeitskopie
(Kontraktspecs + EZB-Kurse). Zeilenangaben zu Fremdcode gelten für 68a7717;
eigene Änderungen für die Arbeitskopie.

## 1. Verifikationsbefehle (alle ausgeführt, 2026-09-08)

```
python -m pytest tests/ -q          -> 534 passed
python scripts/verify_engine.py     -> 85 PASS, 0 FAIL (Exit 0)
python -m compileall -q src app_pages streamlit_app.py  -> COMPILE OK
```

## 2. Befund I-1 (MITTEL, eigene Neuentwicklung) — EUR-Umrechnung fehlte

- Ort: `src/mqlkiscanner/fx_rates.py` (`usd_per`), Arbeitskopie.
- Behauptung: EUR-quotierte Instrumente (XAUEUR, DE40 — beides in
  `data/contract_specs.json` mit `quote_currency: "EUR"` belegt) blieben
  trotz geladener EZB-Kursdatei ohne USD-Schock, weil die EZB-Datei keine
  EUR-Spalte enthält (EUR ist die Basewährung; EURUSD steht in der
  USD-Spalte). `usd_per("EUR", …)` lieferte None.
- Nachweis (vor Fix, Ausgabe wörtlich):
  `usd_per('EUR', 2024-01-04) = None   <-- PROBLEM`
  bei gleichzeitig `Kurse geladen: True`.
- Fix: EUR-Sonderfall in `usd_per` (liest direkt die USD-Spalte, gleiche
  Walk-back- und Datumsdisziplin) + `can_convert()`-Hilfe; Szenario-Feld
  `usd_conversion_available` in exposure.py nutzt sie.
- Nachweis (nach Fix, echte EZB-Datei):
  - XAUEUR 2 Lots: Schock 10.919,00 USD = 2×50×100 EUR × 1,0919
    (EZB-Kurs vom 2024-01-03), conversion_complete=True.
  - DE40 3 Lots: 1.637,85 USD = 3×500×1 EUR × 1,0919.
  - Gemischt XAUUSD+EURCAD: 8.746,05 USD (5.000 Gold + 3.746,05 CAD-Teil).
- Tests: `test_eur_reads_directly_from_usd_column`,
  `test_eur_quoted_spec_symbol_becomes_convertible`
  (tests/test_fx_rates.py).

## 3. Befund I-2 (MITTEL, eigene Neuentwicklung, Vorrunde behoben)

`temporal_risk_available` hing an einem Vor-Schleifen-Wert und wurde nach
herabgestufter `conversion_complete` nicht nachgeführt (Szenario:
USD-Phase + später dazukommendes FX-Kreuz ohne Kurs). Behoben mit
expliziter Kopplung + Regressionstest
`test_usd_period_before_fx_addition_downgrades_flag_consistently`.
(Status: erledigt, hier nur zur Vollständigkeit dokumentiert.)

## 4. Review der Fremd-Commits (ecf9d4f, f0b2245, 68a7717) — in Ordnung

Vollumfänglich gelesen (Diffs + neue Module komplett). Wesentliche Inhalte
und Bewertung:

4.1 `ampel_for` (pipeline.py:223-250): Grün erfordert jetzt
    `stop_evidence in ("direct", "cluster")` — der Befund F1 aus doc/10
    (Grün ohne Stop-Nachweis) ist damit auf Engine-Ebene behoben. ScanResult
    führt `stop_evidence` als eigenes Feld (nie aus Freitext abgeleitet).
    Beweisbar: Probe aus doc/10 Abschnitt 4 würde jetzt 🟡 liefern.
4.2 `report_basis_for` / `restore_current_reports` (pipeline.py:307-376)
    + `analyses.basis`-Spalte (db.py): KI-Berichte werden per SHA-256 über
    Fakten + Forensik + CSV-Hash + Kriterien an ihre Datengrundlage
    gebunden; veraltete Berichte werden nicht mehr angezeigt, aber nicht
    gelöscht. Durchdacht: `canonical()` normalisiert int/float (SQLite REAL
    vs. geparster Integer), Zeitstempel/Pfade sind bewusst NICHT Basis.
4.3 db.py: `PRAGMA foreign_keys=ON` (mein damaliger F11-Hinweis erledigt),
    additive Migration unter `BEGIN IMMEDIATE`, Portfolio-Berichte auf
    signal_id=NULL umgestellt (Legacy-0 wird mitgelesen).
4.4 llm_runner.py: run_llm ausgelagert; bezahlte Modellantworten werden
    vor dem Speichern am Objekt gesichert (Speicherfehler verlieren keine
    bezahlten Texte); No-Balance/Budget bricht den Lauf ab. Fehler- und
    Fortschritts-Accounting je Prompt korrekt (done/failed/skipped summiert
    auf total).
4.5 scan_worker.py/scan_state.py: prozessweite Single-Worker-Registry mit
    Lock nur um Start/Freigabe; Ergebnisseite kann laufende Worker
    wiederanbinden. Keine UI-Aufrufe im Worker (Disziplin erhalten).
4.6 parser.py: Header-Identität statt Spaltenzahl (vertauschte S/L-/T/P-
    Spalten können keinen Stop-Beweis fälschen); JSON-Excerpt komplett
    validiert (Pflichtfelder, Richtung, endliche Zahlen).
4.7 stops.py: `[sl]`/`[tp]`-Marker nur mit strictem Regex inkl.
    Ticket-Suffix (kein Prosa-Match); Cluster-Modus deterministisch
    (bei Gleichstand zählt das NIEDRIGE Niveau — Dateireihenfolge kann
    keinen Stop-Beweis nicht mehr entscheiden).
4.8 drawdown.py/exposure.py: Ereignisse gleicher Sekunde werden gebündelt
    gebucht (keine CSV-Zeilenreihenfolge in Peaks); math.fsum gegen
    Summationsdrift.
4.9 signal_stats.py: Kennzahlen primär aus Struktur-Zeilen
    (`.s-list-info__item`), Titel/Beschreibung können keine Werte
    liefern; Zahlparser lehnt Mehrfach-Punkte/Locale-Mischformen ab
    (bleibt unbekannt statt falsch).
4.10 browser_session.py: Chrome-Profil je Konto unter SHA-256-Hash des
    Nutzernamens; Cookie-Datei an Konto gebunden. Verbesserte Hygiene.
4.11 lot_format.py: Lot-Labels ohne Rundungskollisionen (0.01 vs 0.010
    bleiben verschieden) — ersetzt das alte `f"{v:.2f}"`.

Keine Fehler in den Fremd-Commits gefunden; alle Änderungen sind durch
mitgelieferte Tests (test_review15/17/18_*, test_external_review_*)
abgesichert.

## 5. Adversarielle Gegenprüfung der eigenen Module — Ergebnis

- fx_rates-Cache `(pfad, mtime_ns)`: Edits/Tests greifen sofort; Eviction
  per clear()+neuer Schlüssel; keine Thread-Konflikte (Nutzung nur im
  Worker-Thread; LLM-Threads fassen fx_rates nicht an). OK.
- Download: einmaliger Versuch pro Prozess (`_DOWNLOAD_TRIED`), Fehler
  still, vorhandene Datei wird weitergenutzt; Pipeline wärmt vor der
  Forensik explizit vor und loggt den Stand. Bekannte Grenze, dokumentiert.
- Bisect/Sortierung: aufsteigende Sortierung erzwungen (echte EZB-Datei
  ist neueste-first; Regressionstest vorhanden). Duplikat-Tage unschädlich.
- Walk-back 10 Tage + exakte Tag-Gleichheit von CCY- und USD-Serie;
  Lücken/Pre-1999 bleiben None (getestet).
- exposure/fx_state: kumulativ über alle Snapshots, fehlender Kurs sperrt
  konsistent (I-2-Regressionstest); `peak_*`/`shock_pct_*` nur bei
  vollständiger Conversion veröffentlicht; Warnung nennt konkreten Grund.
- Spec-Loader: Alias/Suffix-Matching, `cross_broker=false` nur mit
  Broker-Match (Öl-Faktor-100-Falle), `ignore_broker` nur für Diagnosen.
- Version-Kopplung: FORENSICS_VERSION=7 (Fremd-Commits) > alle in der DB
  gespeicherten Versionen → alles Alte gilt als veraltet und wird neu
  geprüft; für rein-USD-Signale unchanged values, für die 41 Fehlerfälle
  existiert kein gespeicherter Befund. Kein Stale-Green-Risiko.
  Empfehlung (offen): FORENSICS_VERSION bei jeder künftigen Änderung der
  Bewertungssemantik mitziehen (Konvention steht im Moduldocstring).

## 6. Restrisiken / Hinweise (bewusst akzeptiert)

- EZB-Download scheitert still (ein Versuch je App-Start); Befund nennt
  Datei+Ordner und sagt die Konsequenz. Neustart oder manuelles Ablegen
  der CSV behebt es.
- ECB-Referenzkurse sind Tages-Snapshot (16:00 CET) — für die
  Positions-/Tages-Forensik ausreichend; Provenienz steht je Symbol mit
  Kursdatum im Befund.
- Öl (XTIUSD/USOUSD) bleibt auf Tickmill-Konten beschränkt, bis je Broker
  eine Spec ergänzt wird (Absicht, Faktor-100-Unterschied).
- Die 4 Parser-Fehlerfälle (offene Positionen/defekte Zeilen im Export)
  sind unverändert offen; Lösung wäre ein eigener Datensatztyp für
  offene Positionen.

## 7. Gesamturteil

Kein BLOCKER. Ein MITTLER eigener Fehler (EUR-Lücke) gefunden und mit
Tests + Produktionsbeweis behoben; ein MITTLER aus der Vorrunde bestätigt
behoben. Die zwischenzeitlich eingespielten Fremd-Commits sind von hoher
Qualität und haben zwei offene Punkte aus doc/10 (F1 Ampel-Gate,
F11 Foreign Keys) bereits gelöst. Suite 534 grün, Kalibrierung 85/85,
Compile sauber.

## 8. Nachtrag (gleicher Tag): Behobene offene Punkte

Auftrag „behebe die kritischen Fehler" — umgesetzt und verifiziert
(Suite 540 passed, verify_engine 85/85, Compile OK):

8.1 PARSER/MT4-FOOTER (Ursache von 3 der 41 Scan-Fehler, doc/11 Abschnitt 6):
    Die Meldung „Pflichtfeld fehlt (Buy)" rührte NICHT von offenen Positionen,
    sondern von der MT4-Orderbuch-SUMMENZEILE (Typ Buy/Sell, Symbol 'profit',
    keine Preise, Profit-Spalte = Gesamtsumme; Beleg:
    data/trades/1496203_positions.csv, Zeile 2467). parser.py überspringt
    diese Zeile jetzt erkannt (Erkennung an LEERE Preise gebunden, damit
    keine echten Daten verschwinden) sowie typenlose Abstandszeilen ohne
    Inhalt; typenlose Zeilen MIT Inhalt bleiben ein lauter Fehler.
    Tests: tests/test_parser_export_artefakte.py (6 Tests, inkl. echtem
    Fixture mit 2.461 Trades). End-to-End-Beweis: MySingalStart 2 läuft
    jetzt komplett durch (2461 Trades, Stop-Evidenz 'partial' 11 %, Score 7,4
    — ein berechnetes Schlecht-Urteil statt Absturz).
8.2 F4 (doc/10): load_known_signals() mit (Pfad, mtime_ns)-Cache — wurde
    je Ergebniszeile bis 2x von der Platte gelesen.
8.3 F3 (doc/10): config.llm_aktiv(settings) macht die gemeinsame
    Eine-Schalter-Semantik von llm_stufe1/2 explizit (scan.py nutzt sie).
8.4 F5 (doc/10): matplotlib aus requirements.txt entfernt (nirgends
    importiert, auch nicht in scripts/).
8.5 F6/F2/F1 (doc/10): bereits durch die Fremd-Commits erledigt
    (Validierung max_throttle_retries>=1; hard_block entfernt;
    Ampel-Grün mit stop_evidence-Gate).

8.6 SIGNAL #2271995 (zuletzt offen): Durch Neudownload des Exports
    reproduziert und aufgeklärt. Ursache: zwei Zeilen mit NUR Zeitstempel
    ('2026.07.06 00:22:05;;;;;;;;;;', Zeilen 222/391) — ein MT5-Export-
    artefakt ohne Typ/Volumen/Symbol/Geldwert. Parser-Regel verfeinert:
    Zeitstempel allein ist kein Inhalt (Überspringen), Inhalt ohne Typ
    bleibt lauter Fehler. End-to-End: 1.918 Trades, 5 Symbole (BTCUSD via
    Tickmill-Spec, DE40/USDJPY via EZB-Umrechnung mit Kursdatum, US30/
    XAUUSD via Klassenkonvention), Forensik vollständig: kein Stop-Nachweis,
    Schock 96,5 % des Kontos am Peak, Score 6,1 — berechnetes Risikourteil
    statt Absturz. Export liegt validiert im Cache
    (data/trades/2271995_positions.csv).

— ZCode (GLM-5.3), 2026-09-08, HEAD 68a7717 + Arbeitskopie.
