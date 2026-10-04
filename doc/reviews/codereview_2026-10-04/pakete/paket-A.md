# Code-Review 04.10.2026 — PAKET A (Mathematik, Forensik, Ampel, RetDD, Parser)

Projekt: SignalKiScanner (`D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner`)
Prüfer: Subagent Paket A · Read-only (keine Tests/Apps/Netzwerk/LLM gestartet, keine Datei geändert)

## 0) Manifest und Abdeckung

- Git: HEAD `85dc290` ("fix: Quellen-Werte als Strings mit Dezimalkomma …").
  Working tree dirty: `README.md`, `doc/21_megaprojekt-architektur.md` (modified);
  unversioniert: `=2076`, `doc/reviews/`, `output/`. Kein Review-relevanter Quellcode dirty.
- Bereits behoben laut git log (nicht erneut gemeldet): Score-Gate-Entfernung 04.10.
  (0799167), String-Zahlen-Fix 04.10. (85dc290), Zeitbasis-Ausreißer/GMT-Vereinfachung
  03.10. (71d9641/cb5d0e1), beweisbasiertes Dedup 03.10. (eb4f914), B1–B26/F1–F9/B24–B26.
- Vollständig gelesen: `pipeline.py` (2068 Z.), `scoring.py`, `portfolio_statistik.py`,
  `parser.py`, `engine.py`, `stats.py`, `forensics/{martingale,drawdown,exposure,stops,
  equity_rekonstruktion}.py`, `equity_studie.py`, `ingest.py`, `ampel_matrix.py`,
  `regelwerk.py`, `analysis_version.py`; auszugsweise: `equity_studie_ui.py`,
  `equity_kapitalfluesse.py`, `llm_runner.py`, `symbols.py`, `signal_stats.py`,
  `rest_api.py`, `tradeserver_sync.py`, `fx_rates.py`, `quellen.py`.
- Tests (nur gelesen): `test_retdd_produzent_und_dedup.py` vollständig; Struktur/Greps in
  `test_beweis_dedup.py`, `test_effizienz_eq_dd.py`, `test_retdd_equity_pipeline.py`,
  `test_parser_export_artefakte.py`, `test_portfolio_statistik.py`.
- Produktiv-DB read-only (`sqlite3 URI mode=ro`, `data/mqlkiscanner.db`): 95 Forensik-Zeilen,
  davon 0 mit aktivem bewiesenem Dedup, 26 mit identischen Zeilen (erhalten, kein Beweis),
  42 mit `retdd_monat`. `FORENSICS_VERSION = 11` (`analysis_version.py:5`).

## 1) Befunde nach Schwere

### P0

**A2a — BESTÄTIGT (Laufzeit aktuell latent, 0/95 aktiv): RetDD-Zähler und Portfolio-Kurven
lesen die Trade-CSV OHNE den Plattform-Beweiswert — Forensik (dedupet) und Rendite
(roh) rechnen auf unterschiedlichen Trade-Beständen.**
- Produzent mit Beweis: `pipeline.py:1427-1433` setzt `res.plattform_trades = stats.get("trades")`
  und gibt ihn an `engine.analyze(..., plattform_positions=res.plattform_trades)` →
  `parser.load_export(path, plattform_positions=...)` (`engine.py:37`) entfernt bewiesene
  Doppellieferungen. `equity_studie_ui.py:58-59` reicht ihn ebenfalls durch (korrekt).
- Ohne Beweis (alle mit `load_export(pfad)` ohne Argument):
  - `portfolio_statistik.py:78` (`monatsrenditen`) und `portfolio_statistik.py:122`
    (`effizienz_kennzahlen`) — hier entsteht `ertrag_monat_geom_pct`/`cagr_jahr_pct`,
    also der RetDD-ZÄHLER;
  - `pipeline.py:75-76` (`_implizite_kapitalbasis`, Σ Netto);
  - `llm_runner.py:93` und `:243` (Trade-Payload Prompt 1/Tiefenanalyse);
  - `agenten/delta.py:50-51` (Betreuer-Delta).
- Wirkung (Fall „The Holy Grail": 4.197 bewiesene Doppelzeilen = 27,4 %): Forensik-Werte
  (Trading-DD, Martingale, Exposure, Stops, Winrate, `net_total`, `ertrag_monat_pct_forensik`)
  stehen auf dem dedupeten Bestand, während `ertrag_monat_geom_pct`/`retdd_monat`/`retdd_jahr`
  und die Portfolio-Cluster/-Fenster auf dem ROHEN Bestand stehen. Sind die Duplikate netto
  positiv, sind Ertrag und RetDD überhöht → beide Grün-Gates (`ampel_for`,
  `pipeline.py:644` Ertrag ≥ Schwelle, `:655` RetDD ≥ 1,0) werden leichter passiert:
  falsch-positives Grün möglich. Umgekehrt (Dupes netto negativ) falsch-zu-niedriger Ertrag.
  Auch ohne Ampelflip ist die DB inhaltlich widersprüchlich (zwei „eigene" Erträge mit
  verschiedenen Trade-Basen).
- Testabdeckung: `tests/test_beweis_dedup.py` testet Parser+Engine; `tests/test_retdd_
  produzent_und_dedup.py:8-10` behauptet "rechnet auf derselben Kurve wie die Forensik-Erträge" —
  das gilt nur ohne Beweisfall; ein Test „effizienz mit Beweis == Forensik-Zähler" fehlt.
- Laufzeitstatus: aktuell 0/95 Signale mit `duplikate_entfernt > 0` (DB, read-only) —
  der Fehler ist LATENT und springt beim nächsten Scan eines THG-artigen Falls an.
- Fix (geringes Risiko): `effizienz_kennzahlen`/`monatsrenditen` den Parameter
  `plattform_positions` geben und an `load_export` durchreichen; `pipeline.py:1550-1551`
  und `:1967-1968` übergeben `res.plattform_trades` (aus DB-Reload kommt er über
  `results_from_db`, `pipeline.py:457`). Dasselbe für `_implizite_kapitalbasis`
  (Aufruf `pipeline.py:1401-1402`) und `llm_runner`-Payload. Danach
  `test_retdd_produzent_und_dedup.py` um einen Beweisfall ergänzen.

**A2b — P2 (Teil von A2a): KI-Widerspruch in denselben Berichten.** `llm_runner.py:93`
baut die Trade-Analyse (Prompt 1) aus dem rohen Export, während das Forensik-JSON im
Prompts-2/3-Kontext (`pipeline.py:741-870`) dedupete Werte zeigt — im Beweisfall
rechtfertigt die KI Strategieaussagen mit Trades, die die Forensik nicht mehr kennt
(und umgekehrt). Fix wie A2a.

**A2c — P2 (Teil von A2a): implizite Kapitalbasis im Beweisfall falsch.**
`_implizite_kapitalbasis` (`pipeline.py:60-94`) zieht Σ Netto aus dem ROHEN Export;
bei bewiesener Doppellieferung weicht die Basis um das Duplikat-Netto ab — DD-/Schock-
Prozente der Forensik dann auf verzerrter Basis (greift nur, wenn Initial Deposit fehlt
UND Web-Balance vorliegt). Fix wie A2a.

### P1

**A1c — VERDACHT: Für Quellen-Signale ist der Monitor-Wert der EINZIGE RetDD-Nenner —
seine floating-Inklusivität ist außerhalb dieses Repos belegt/behauptet.**
- Trace: `ingest.py:320` mappt metrics `TradeEqDrawdownPct` → `monitor_trade_eq_dd_pct`;
  `pipeline.py:1333` übernimmt ihn; `pipeline.py:1411-1420` skippt die Kursdaten-Reko,
  sobald der Monitorwert existiert ("wäre Doppelarbeit"); Nenner ist
  `ScanResult._equity_messwerte` (`pipeline.py:276-283`) = {Kurse, Monitor} → max.
- Regelkonform: Die Nutzer-Regel 03.10. erlaubt ausdrücklich „valide H1-/Monitor-Messung,
  höchste davon" als RetDD-Nenner. Code-Seite ist GRENZE (regelkonform).
- Risiko: Ob `TradeEqDrawdownPct` (PelicanMonitor etc.) wirklich floating-inklusiv auf
  voller Kurve gerechnet wird (AGENTS.md B1-Behauptung) ist hier nicht prüfbar. Ist es
  in Wahrheit eine Closing-Kurve, ist der Nenner zu klein → RetDD zu groß → falsch-GRÜN
  — genau die vom Auftrag skizzierte Richtung. Prüfung nötig im PelicanTrading-Monitor
  (Berechnung von TradeEqDrawdownPct gegen dessen eigene Kapitalbasis). Bis dahin:
  VERDACHT, P1. Maßnahme (optional, kein Regelverstoß): für Quellen-🟢-Kandidaten die
  Equity-Studie als stichprobenartige Gegenmessung heranziehen oder im Grün-Urteil den
  Nenner-Kanal nennen (steht schon in `equity_messung_status`).

### P3

**A3a — ertrag_monat_pct_forensik nutzt Monat = 30,44 Tage (statt 365,2425/12 = 30,4369)
und die gerundete `span_weeks`.** `pipeline.py:1537-1543`:
`monate = span_wochen * 7.0 / 30.44` mit `span_weeks = round(span_days/7, 1)`
(`stats.py:109`). Weicht von der Regel-Monatsdefinition ab (~0,01 %); Feld ist
dokumentierte Zusatzinfo (maßgeblich ist `ertrag_monat_geom_pct`, das korrekt
365,2425/12 nutzt, `portfolio_statistik.py:29-30,129-131`). Fix: konstante
`MONAT_TAGE` verwenden — kosmetisch, geringes Risiko.

**A3b — `_platform_float` versteht kein „1.403,03".** `scoring.py:50-65` ersetzt nur
Minus/Leerzeichen/Komma→Punkt: aus „1.403,03" wird „1.403.03" → ValueError → default 0.0
(still). `ingest._zahl` (`ingest.py:276-286`) beherrscht den Fall korrekt. Praktisch nur
für Legacy-DB-Strings relevant (Neu-Läufe parsen Quellen über `_zahl`, MQL5-Seiten über
`_number`, das Gruppierung kann). Fix: dieselbe Zwei-Schritt-Normalisierung wie `_zahl`
übernehmen. Geringes Risiko (nur robustere Strings, Zahlen unberührt).

**A3c — Label-Lücke: dd_max_pct == 0 meldet `ohne_equity_dd`.**
`portfolio_statistik.py:132` (`_positiv_endlich`) + `:172` — bei gemessenem Equity-DD von
exakt 0 (beide Kanäle 0) heißt der Status „ohne_equity_dd", obwohl die Messung existiert;
`refresh_efficiency` (`pipeline.py:317-321`) kennt korrekt `equity_dd_null`. Rein
kosmetisch (RetDD bleibt korrekt None). Fix: Statusfall unterscheiden.

**A4a — Credit-Zeilen werden validiert und dann still verworfen.** `parser.py:170-176`
nimmt „Credit" in die Typ-Whitelist und prüft Pflichtfelder, aber `parser.py:210`
verarbeitet nur `("Balance", "Correction")` — Credit fällt durch alle Zweige und
verschwindet ohne Zähler. Verstoß gegen das A4-Kriterium „kein Inhalt verschwindet still";
Bonus-Flows fehlen in `deposits_start`/`end_balance_real` und können den
Kapitalbasis-Abgleich (`pipeline.py:894-925`, Toleranz max(5 USD, 2 %)) verwirrend
scheitern lassen. Fix (bewusst entscheiden): entweder wie Correction als Kontobewegung
buchen (dann Abgleich-Tolerenz unverändert) oder explizit verwerfen + Zähler
`credit_zeilen_ignoriert` im Stats/Forensik-JSON. Risiko: Abgleich-Anker verschiebt sich
für Bestände mit Credits — vorher an known-Signalen gegenrechnen.

**A4b — Balance-Dubletten haben keinen Beweis-Mechanismus.** Das beweisbasierte Dedup
(`parser.py:204-208,225-247`) bildet Schlüssel nur für Trade-Zeilen; identische
Balance-Zeilen werden beide gebucht (`parser.py:210-213`) → `deposits_start`
(`drawdown.py:80`) könnte bei doppelt gelieferten Kontobewegungen überhöhen. Der
Plattform-Beweis („Trades:") deckt Kontobewegungen begriffsätzlich nicht ab. Kein
realer Fall bekannt — Hinweis, kein Handlungsdruck (P3). Option: identische
Balance-Zeilen mit identischem Zeitstempel zählen + im Stats ausweisen.

**A7a — Stale Score-Gate-Texte nach Gate-Entfernung 04.10. (0799167).** Funktional
korrekt: `ampel_for` (`pipeline.py:626-668`) hat kein Score-Gate mehr, Grün = harte
Regeln + Ertrag + RetDD. Aber die Nutzer-Kommunikation lügt:
- `ampel_matrix.py:103-107` (KRITERIEN „score" Tooltip): „Gesamt-Ampel Grün verlangt
  Score < 5. …";
- `ampel_matrix.py:284` (Zell-Detail ab Score ≥ 5): „Kandidaten-Schwelle 5 überschritten
  (kein Kandidat)";
- `regelwerk.py:77-82` (HARTREGELN): „🟡 Score, Ertrag oder RetDD reichen nicht —
  Risiko-Score ≥ 5 …";
- `regelwerk.py:117`: „aktuelle Grenzwerte: … und Risiko-Score unter 5."
Fix: Texte auf „Score ist Anzeige-/Gewichtungszelle, sperrt nicht mehr" umstellen
(rein textuell, kein Risiko).

**A8b — Studie ist für `verlaesslich` STRENGER als die Produktiv-Reko (Divergenz möglich).**
`equity_studie.py:484-486` verlangt zusätzlich `gemeinsame_zeitbasis` (ein Versatz über
alle Symbole) und ermittelt GMT JE SYMBOL (`equity_studie.py:56-138`), während die
Produktiv-Reko wochenweise über alle Symbole hinweg arbeitet
(`equity_rekonstruktion.py:133-183`) und `verlaesslich` ohne
Einheitlichkeitsbedingung definiert (`:684-685`). Ein Signal kann in der Studie
„nicht belastbar" und gleichzeitig in der Schranke/RetDD per Kurs-Reko messen sein
(oder umgekehrt). Die Unterschiede sind im Studien-Moduldocstring teils offengelegt;
die Divergenz-Regel selbst ist nicht dokumentiert. Fix: ein Hinweissatz in der Studie
(„Studie fordert einheitliche Symbol-Zeitbasis — die Produktivmessung kann trotzdem
gelten") oder Angleichung. Kein Bewertungsfehler (Studie bewertet bewusst nicht).

### BESTÄTIGT-OK / GRENZE (geprüft, kein Bug)

- **A1a — RetDD-Nenner-Regel korrekt umgesetzt (Kernhypothese WIDERLEGT).**
  `effizienz_kennzahlen` wird an genau 2 Produktionsstellen gerufen:
  `pipeline.py:1549-1551` mit `dd_max = res.max_drawdown_equity_pct` und
  `pipeline.py:1967-1968` (Demo) ebenfalls mit `max_drawdown_equity_pct`. Der Nenner
  ist `max(_equity_messwerte())` = max(Kurs-Reko falls verlässlich, Monitor)
  (`pipeline.py:276-292`) — NIEMALS Plattform-EQ/Balance-DD, Trading-DD (geschlossen)
  oder `scoring.dd_maximum`. Auch `refresh_efficiency` (`pipeline.py:294-338`) rechnet
  RetDD ausschließlich mit diesem Nenner neu (DB-Reload, Tabelle, Prompts, REST,
  Tradeserver nutzen alle dieselbe zentrale Formel). Ohne Messkanal: RetDD None →
  kein Grün (`pipeline.py:650-654`). Regelkonform.
- **A1b — harte Schranke: 5-Kanal-Maximum identisch an allen 4 Stellen.**
  `scoring.evaluate` (`scoring.py:229-233`), `ampel_for` (`pipeline.py:582-584`),
  `results_from_db` (`pipeline.py:538-541`), `refresh_report_verdict`
  (`pipeline.py:1022-1025`): immer `dd_maximum(eq, bal, trading, reko, monitor)`,
  jeweils UNGERUNDET verglichen gegen das Limit (30,0001 % fällt bei 30 durch).
  Monitor > 100 % trägt Vorbehalt-Hinweise (`ampel_matrix.py:170-173`).
- **A3 — Invarianten sonst vollständig erfüllt:** geometrische Monatsrendite aus
  ungerundetem `fsum(net)`/End-Start via `log1p/expm1` (`portfolio_statistik.py:148-161`);
  echte Zeitspanne erster Open bis letzter Close (`:127-131`); Jahr 365,2425,
  Monat = Jahr/12 (`:29-30`); CAGR echt `(End/Start)^(1/Jahre)-1`, NICHT ×12 —
  `retdd_jahr = cagr/dd` ≠ 12×`retdd_monat` (`:160-167`); Leermonate bleiben in der
  Monatsserie mit 0 % (`:54-64`, Test `test_effizienz_eq_dd.py:33-40`); Basis ≤ 0 /
  nicht endlich / bool → kein Ertrag/RetDD (`_positiv_endlich`, `_monatsserie`,
  `_virtuelle_kapitalbasis` `pipeline.py:108-118`); Endkapital ≤ 0 → kein Ertrag
  (`:153-155`); dd==0 → RetDD None (`pipeline.py:309-313`); String-Parsen „9,10" und
  „1 403.03" robust in `parser.parse_number`, `ingest._zahl`, `signal_stats._number`
  (siehe A3b für die eine Lücke).
- **A4 — Parser-Artefakte korrekt:** MT4-Summenzeile (Typ Buy/Sell + Symbol „profit" +
  leere Preise) übersprungen (`parser.py:67-80,161-165`); Zeilen nur mit Zeitstempel
  übersprungen, Inhalt ohne Typ = lauter Fehler (`:148-158`); `Correction` =
  Kontobewegung (`:170-176,210-213`); abgeschnittene LETZTE Zeile (Feldzahl oder
  Pflichtfeld) = lauter Fehler mit Diagnose-Hinweis „Download vermutlich unvollständig"
  (`:141-146,159-180`). Beweis-Dedup entfernt nur bei exakter Deckung
  Plattformzahl == Zeilenzahl ohne Mehrfachvorkommen, behält jedes erste Vorkommen
  (`:225-247`); nicht-ganzzahlige/negative Beweiszahlen ignoriert (Tests
  `test_beweis_dedup.py:38-115`). Einzige Lücke: Credit (A4a).
- **A5 — Pflicht-Batterie prüft STATUS, nicht Dict-Präsenz:** Martingale-Flag (Median
  je Symbol > 1,3 nach Verlust, netto-basiert, Breakeven kein Verlust, Korb-Leiter als
  zweiter Kanal; `martingale.py:24-155`) wirkt als HARTE rote Ampel unabhängig von der
  Vollständigkeit (`pipeline.py:589-590`); Exposure-Komplexität (Kapitalhistorie,
  Kontrakt, Umrechnung, temporal) blockiert `_forensics_complete`
  (`scoring.py:245-254`), `shock_pct_max is None` likewise; DD-Rekonstruktion mit
  Kapitalbasis-Abgleich (Toleranz max(5 USD, 2 %)) als Raise (`pipeline.py:1446-1448`);
  SL-Clustering mit konservativer Signal-Logik (Teilstichproben entlasten nie,
  `stops.py:207-215`). XAUUSD: METAL-Faktor 100 USD je 1-$-Bewegung und Lot
  (`exposure.py:45-46`) → 2,66 Lots × 50 $ × 100 = 13.300 USD Schock korrekt;
  `contract_specs.json`: DE40 mit Alias GER40 (B6 ✓), XTIUSD/USOUSD_VTMARKETS mit
  cross_broker=false + broker-Teilstring-Match (`symbols.py:101-148`) — die
  USOUSD-Doppelaliasierung löst korrekt über den Broker auf; UNKNOWN ohne Spec = harter
  Fehler mit gezielter cross_broker-Meldung (`exposure.py:218-239`).
- **A6 — SL-Neutralität durchgehalten:** `scoring.dimension_inputs`
  (`scoring.py:128-148`): bewiesener SL = einzige Entlastung (−1,0); KEIN Malus für
  fehlenden Nachweis (Kommentar dokumentiert die Regel). `ampel_for` nutzt
  `stop_evidence` nur für Kontexttext (`pipeline.py:617-625`). `_stop_zelle`:
  „none" = ⚪ neutral ohne Abwertung (`ampel_matrix.py:217-233`); Schutzsignatur bleibt
  Verhaltenshinweis ohne Score-Bonus (`stops.py:343-362`). `regelwerk.py:29-34,73-76`:
  fehlender Nachweis begründet niemals einen Listeneintrag. Kein verbotener Maluspfad
  gefunden.
- **A7b — Grün-Weg überall identisch reconstruiert:** Scan (`pipeline.py:1624`),
  DB-Reload (`results_from_db:551`), `refresh_report_verdict:1026`,
  `restore_current_reports:1035`, LLM-Runner (`llm_runner.py:73`) und REST
  (`rest_api.py` Docstring/Nutzung von `results_from_db`-Ergebnissen mit `ampel_for`)
  rufen alle dieselbe `ampel_for`. Gates: ⛔ Liste → 🔴 Martingale → 🔴 Kapitalbasis ≤ 0 →
  🔴 Schranke (beweisbar) → ⚪ Fehler → [Forensik komplett:] 🟡 Ertrag None/<Schwelle →
  🟡 RetDD None/<1,0 → 🟢. Kein verstecktes Score-Gate, keine abweichende Kopie.
- **A8 — Reko/Studie Kernregeln erfüllt:** H1-Close am BAR-ENDE
  (`equity_rekonstruktion.py:495-510`, `(b.time//3600+1)*3600`); kein Look-ahead:
  Opens strikt `< punkt`, Closes `<= punkt` zuerst realisiert, Aktiv-Filter
  `ende > punkt` (`:582-589`); Endkonto auch ohne Schluss-Bar messbar (`:511-513,626-633`);
  F2: Punkte ohne vollständiges Floating sind keine Messpunkte (`:618-626`);
  F5: Abdeckungs-Nenner = aktive Stunden laut Trade-Zeiten minus Marktpausen (globale
  Bar-Lücken ≥ 20 h) (`:555-580,670-677`); hart 95 % (`:39,684-685`); GMT: 3
  Preisereignisse (Open+Close dedupliziert), Quote ≥ 0,9, Plateau = mehrdeutig,
  Vererbung „geerbt_letzter_bekannter", harte Grenzen (nicht-monoton, offene Position
  über stark belegte Wechselgrenze, Preis um Größenordnungen daneben → Messung weg)
  (`:52-58,118-267`); `equity_dd_pct_raw` ungerundet als Schranken-/RetDD-Wert
  (`:693-696`, übernommen `pipeline.py:1493-1495`). Studie nutzt dieselbe Bar-Ende-,
  Aktiv- und Abdeckungslogik (`equity_studie.py:249-263,349-397,451-455`) und reicht
  den Dedup-Beweis durch (`equity_studie_ui.py:57-59`). Fehlende Kursdaten namentlich:
  KI-JSON `fehlende_kursdaten` (`pipeline.py:837-845`), GUI-Arbeitsliste
  (`app_ui.py:209-233`, `app_pages/ergebnisse.py:392`), PDF-Zeile
  (`pdf_reports.py:274-283`). ✓
- **GRENZE Monitor bei `forensik_stale`:** `_equity_messwerte` (`pipeline.py:278-280`)
  nimmt den Monitor-Wert auch bei veralteter Forensik in `max_drawdown_equity_pct` auf
  (nur der Kurs-Kanal wird genullt) — die Anzeige-Spalte „Max-Drawdown" kann dann einen
  Monitorwert zeigen, aber `refresh_efficiency` nullt die Rendite bei stale
  (`pipeline.py:304-307`) → RetDD None, und `forensik_vorhanden=False` sperrt Grün.
  Kein Bewertungsfehler.

## 2) Widerlegte Verdachte (explizit)

1. **„effizienz_kennzahlen nutzt scoring.dd_maximum (5 Kanäle inkl. Plattform/Balance)
   als RetDD-Nenner"** — WIDERLEGT. Beide Call-Sites übergeben `max_drawdown_equity_pct`
   (nur Kurse+Monitor); `refresh_efficiency` rechnet ausschließlich mit diesem Nenner
   (`pipeline.py:294-338,1549-1551,1967-1968`).
2. **„Plattform-Balance-DD als Nenner verkleinert RetDD (falsch-gelb)"** — WIDERLEGT
   (Folge aus 1): Plattform-DDs fließen nur in die harte Schranke (regelkonform,
   „konservatives Maximum aller fünf").
3. **„Score-Gate lebt funktional in RESTAUR/refresh/DB-Wiederherstellung weiter"** —
   WIDERLEGT. Alle Pfade nutzen `ampel_for` ohne Score-Gate; nur TEXTE sind stale (A7a).
4. **„30,0001 % könnte per Rundung die 30-%-Schranke passieren"** — WIDERLEGT. Alle
   vier Vergleichsstellen vergleichen ungerundet (`> float(limit)`); gerundet wird nur
   die Anzeige (`scoring.py:233,239`).
5. **„CAGR ist heimlich ×12"** — WIDERLEGT (`portfolio_statistik.py:160-161`,
   `expm1(log1p(r)/jahre)`), Tests bestätigen (`test_retdd_produzent_und_dedup.py:39-52`).
6. **„Leermonate werden aus der Rendite herausgekürzt"** — WIDERLEGT: Monatsserie
   lückenlos mit 0 %-Monaten (`portfolio_statistik.py:54-64`), Effizienz-Dauer = volle
   Spanne erster Open bis letzter Close.
7. **„Fehlender SL-Nachweis erzeugt irgendwo Malus/Sperre"** — WIDERLEGT (A6-Kette).
8. **„MT4-Summenzeile/Zeitstempel-Zeilen/Correction lassen Inhalt still verschwinden"** —
   WIDERLEGT für diese drei (A4-OK); einzige Ausnahme Credit (A4a).
9. **„USOUSD-Doppelalias (Tickmill 1 vs. VTMarkets 1000 Barrel/Lot) greift falsch"** —
   WIDERLEGT: `spec_for` prüft Broker-Zugehörigkeit je Alias-Eintrag
   (`symbols.py:134-141`), Cross-Broker-Fall wirft gezielten Fehler
   (`exposure.py:222-239`).
10. **„Studie und Produktiv-Reko könnten heimlich auseinanderlaufen"** — weitgehend
    widerlegt: identische Bar-Ende-/Abdeckungs-/Dedup-Logik; verbleibende dokumentierte
    Differenz = strengere Zeitbasis-Einheitlichkeit der Studie (A8b, P3).

## 3) Offene Fragen / Empfehlungen

1. A1c: Im PelicanTrading-Monitor nachrechnen, ob `TradeEqDrawdownPct` floating-inklusiv
   auf voller Kurve gerechnet wird (einziger RetDD-Nenner aller Quellen-Signale ohne
   Terminal-Kurse). Ggf. dort eine Gegenmessung nach Scanner-Methode beisteuern.
2. A2a vor dem nächsten THG-artigen Scan fixen (Dedup-Beweis durchreichen); ein
   Re-Scan des Bestands ist danach nicht nötig (aktuell 0 aktive Fälle), aber die
   26 Signale mit identischen Zeilen bleiben Beobachtungsfälle für den Beweisfall.
3. A4a (Credit) als bewusste Entscheidung dokumentieren oder verbuchen — betrifft die
   Abgleich-Anker von Signalen mit Broker-Boni.
4. A7a-Texte mit dem nächsten Text-Commit mitziehen (reine Kommunikation, aber der
   Nutzer liest „Grün verlangt Score < 5" als aktive Regel).

— Ende Paket A. Keine Projektdatei verändert; DB ausschließlich URI mode=ro gelesen.
