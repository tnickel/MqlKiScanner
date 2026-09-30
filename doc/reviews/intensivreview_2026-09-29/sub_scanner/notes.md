# Intensiv-Review 2026-09-29/30 — Sub-Review „Scanner"

Gegenstand: Full-Scan 30.09.2026 00:02:20–02:53:53 (GUI/Streamlit :8504), Code-Stand
git `ccc383b` (Arbeitsbaum = HEAD). Geprüft: Ingest, Auswahl, Identitäten,
Berechnungs-/Persistenz-Kette. Nicht geprüft: LLM-Prompt-Inhalte, Pelican-Interna.
Alle DB-Befunde aus `doc/reviews/intensivreview_2026-09-29/tmp/review_copy.db`
(Kopie), REST-Simulation auf eigener Arbeitskopie (`sub_scanner/work/`).
Prüfskripte: `sub_scanner/identitaet_check.py`, `lauf_check.py`, `rest_check.py`
(read-only; PDF-Materialisierung für die Simulation neutralisiert).

**Kernzahlen verifiziert:** 182+781=963 vereint · Vorfilter → 103 (69 mql5 + 34 pelik) ·
Auswahl 30/69 + 30/34 = 60 · 52 Forensik-OK (28 mql5 + 24 pelik) · 8 Fails (2× Parser,
4× USOIL-Spec, 2× GER40-Spec) · 52×3 LLM-Berichte · 23 🟢/🟡 im Portfolio ·
Token-Summe DB 1.701.552 == Log · Ampel-Chronik ab 23:00: ⛔21 🔴20 🟡26 🟢7 = 74
(Ziellauf allein: ⛔12 🔴17 🟡16 🟢7 = 52) · 17 Ampel-Wechsel-Ereignisse, davon 1
Farbwechsel (UpFuji 🟡→🔴).

---

## A) Bestätigte Befunde (Fehler / Abweichungen vom Soll)

### F1 — HÖCHST (inhaltlich): Harte 30-%-DD-Schranke ist für Quellen-Signale mit Monitorwert ohne floating-inclusive Messung
- **Ort:** `src/mqlkiscanner/pipeline.py:915-924` (Reko-Skip, wenn `monitor_trade_eq_dd_pct`
  geliefert), `pipeline.py:471` (Monitorwert nur Deutungsauftrag ans LLM),
  `scoring.py:185-190` (Schranke = Vierfach-Max ohne Monitorwert; dokumentiert in
  ScanResult-Kommentar pipeline.py:136-140).
- **Erwartet:** Nutzer-Kernregel „Risiko VOR Ertrag, 30 % max" — laut `ampel_matrix.py`
  (Kriterium dd_schranke) inkl. „aus Kursdaten nachgemessenem Reko-EQ-DD (floating
  inklusive)". **Beobachtet:** Für pelik-Signale wird die eigene Reko geskippt
  („Doppelarbeit", 23 von 24 erfolgreichen) UND der Monitorwert bewusst nicht in die
  Schranke genommen → gar kein floating-inclusive DD-Wert in der harten Prüfung.
- **Lauf-Belege (DB forensik/stats):**
  - 2063644 „🍋 Lemonal" — **🟢 Score 4,9**, Monitor-EQ-DD **46,65 %** (gemeldet 8,56 %)
  - 2084818 „AccurateCopier" — **🟢 Score 4,5**, Monitor-EQ-DD **241,3 %** (virtuelle
    Kapitalbasis! gemeldet 16,77 %)
  - 2012139 „Grid King $1000" — 🟡 Score 4,2, Monitor-EQ-DD **70,64 %** (gemeldet 3,94 %)
  - 2016702 „Master H4-1" — 🟡 Score 5,1, Monitor-EQ-DD **66,52 %** (gemeldet 20,52 %)
  Zwei 🟢-Signale mit EQ-DD-Zweitmessung jenseits der Schranke gingen als Kandidaten in
  den Portfolio-Prompt (Portfolio-Empfehlung wurde diesmal nicht drauf gestützt).
- **Reproduktion:** `SELECT` auf forensik+signals wie oben (sub_scanner/lauf_check.py
  erweitert); oder GUI: Detailansicht Lemonal — dd_schranke-Zelle grün, Monitorwert nur
  im KI-Text.
- **Auswirkung:** Genau das „Pure-Gold-2000"-Muster (papieren top, floating explodiert)
  wird für Quellen-Signale nicht mehr hart abgefangen. MQL5-Signale haben über die
  Kursdaten-Reko einen harten Kanal, Quellen-Signale nicht — Inkonsistenz in der
  strengsten Regel des Projekts. Vorbehalt: Monitorwerte >100 % sind mit virtueller
  10k-Basis gerechnet und überzeichnen absolut; 46–70 % sind aber auch jenseits jeder
  Toleranz.
- **Korrekturidee:** Monitor-EQ-DD als fünftes Schranken-Maximum zulassen, sobald die
  Metrics eine belastbare Basis liefern (InitialDeposit echt oder als klar markierte
  Annahme — dann Schranke mit Kennzeichnung); mindestens als eigene Matrix-Zelle
  „EQ-DD-Zweitmessung" (orange/rot > Schranke) und Verhinderung von 🟢 bei
  Monitorwert > Schranke. **Test:** pelik-Fixture mit TradeEqDrawdownPct=46 → Ampel
  darf nicht 🟢 sein.

### F2 — MITTEL: Downloader-Abbruch am ERSTEN Signal; Spiegel seit 20.09. stale — PLUS Base-URL-Divergenz
- **Ort:** `downloader_sync.py:51-61` (`_ueber_quellen`: systemischer Fehler wird nur
  unterdrückt, wenn `ergebnis` non-empty — pelik liefert für MQL5-Signale nur 404 →
  leere Liste → Raise), `downloader_sync.py:139-141` + `183-185` (sync_reports/sync_many:
  Abbruch). Log `data/scan_workflow.log:1070` (02:53:53).
- **Erwartet:** „Teilausfall einer Quelle bricht nichts" (AGENTS/doc/20). **Beobachtet:**
  Der Abgleich bricht bei Signal 1 ab, weil die EINZIG liefernde Quelle (pelik) für
  MQL5-Signale nichts liefert (404 = leere Liste, kein „ergebnis") und die Quelle mql5
  (MqlDownloader :8089) down ist. `subscriber_history`/`downloader_reports`: letzter
  Stand **20.09.2026** (DB), d. h. Abonnenten-Verlauf + PDF-Spiegel sind 10 Tage alt;
  im Ziellauf 0 Zeilen geschrieben. Die 7/30-Tage-Bilanz (`abo_bilanz`) rechnet auf
  stale Daten.
- **Zusatzbefund (Konfiguration):** `config/app_settings.json`:
  `downloader_base_url = http://192.168.178.164:8089/api/v1`, DB `datenquellen`:
  Quelle `mql5` → `http://localhost:8089`. Die Registry-Divergenz wird nirgends
  abgeglichen/gewarnt — der Fehlermeldung („stimmen Host/Port?") fehlt der Hinweis,
  dass die Settings einen anderen Host nennen.
- **Reproduktion:** MqlDownloader stoppen, Scan laufen lassen → Station 6 warning nach
  Signal 1; `SELECT MAX(fetched_at) FROM subscriber_history`.
- **Korrekturidee:** In `_ueber_quellen` 404-only-Ergebnisse als „Quelle kannte Signal
  nicht" werten (keinRaise), solange EINE Quelle antwortet; Prozentsatz abgearbeiteter
  Ziele melden; Admin-Warnung bei `downloader_base_url` ≠ Quell-URL. **Test:** Ein Test
  mit Quelle A down + Quelle B nur-404 darf nicht abbrechen, sondern 0 Punkte/0 PDFs
  melden.

### F3 — MITTEL: ⛔-Ausschlüsse belegen 13 von 30 MQL5-Forensik-Slots und das volle LLM-Budget
- **Ort:** `fix_signale.py:62-95` (Auswahl sortiert nur nach Abonnenten; kein
  Ausschluss-Filter), `pipeline.py:354-357` (⛔ wird erst in `ampel_for` markiert, nie
  entfernt), `llm_runner.py:23-25` (LLM-Jobs = alle `forensik_vorhanden` ohne
  Ampel-Filter — nur das Portfolio filtert ⛔/🔴, F-8).
- **Beobachtet (Ziellauf):** 13 der 60 Auswahl-Slots (43 % der MQL5-30) sind
  known_signals-Ausschlüsse (u. a. World PEACE, NoPain, MSC ×2, FXtrading, Smart Boss,
  LUBOTFX, Soma). Alle 13 bekamen komplette KI-Berichte (je 3 Prompts; Log 00:07:45
  „World PEACE … Ablehnung gemäß Engine-Ausschlussliste"). 12 nicht-ausgeschlossene
  MQL5-Kandidaten (69 Kandidare − 30 Slots + 13 ⛔-Slots) kamen nicht in die Forensik.
  Grobe Token-Schätzung: 13/52 × 1,61 M ≈ 400k Tokens für fix entschiedene Urteile.
- **Einordnung:** Bewusstes Design (Ausschluss ist „markieren, nicht entfernen";
  Monitoring), aber die Slot-Verdrängung + Kosten stehen in keinem Verhältnis — der
  Betreuer-Agent (Dossiers) wäre der passendere Ort für ⛔-Beobachtung.
- **Korrekturidee:** ⛔ aus `waehle_fuer_export` herausfiltern oder nur jeden N-ten Lauf
  mitnehmen (Setting `ausschluss_rescan_wochen`); LLM-Stufe für ⛔ auf Stufe 1
  reduzieren oder ganz sparen. **Test:** Fixture mit 5 ⛔ + 30 normalen Kandidaten →
  Auswahl enthält 0 ⛔ (bzw. nur gemäß Takt).

### F4 — MITTEL: `fix_signal_ids` ist leer — Empfehlungs-Signale wurden nicht gescannt
- **Ort:** `config/app_settings.json` (`fix_signal_ids = []`), `fix_signale.py`.
- **Beobachtet:** Weder KiraCat #2342895 (Empfehlung, „Ertragsträger") noch Gold Spike
  MT5 #2375480 waren in den Top-Listen/Kandidaten (candidates.json enthält sie nicht);
  beide wurden im Ziellauf nicht geprüft. DB: KiraCat forensik vom **08.09.**
  (🟡 6,5 — wird so unverändert über REST ausgeliefert), Gold Spike MT5 vom **05.09.**
  (legacy, ohne forensik_version → in `results_from_db` „veraltet"). Nur Gold Spike
  MT4 #2349227 ist frisch (🟢 4,1). Genau die Lücke, wegen der Fix-IDs am 28.09.
  gebaut wurden, ist operative Realität: **Feature vorhanden, aber unkonfiguriert.**
- **Korrekturidee:** Empfehlungs-/Watchlist-IDs als Fix-IDs vorschlagen (GUI-Banner,
  wenn eine Empfehlung weder im Scope noch Fix ist); beim Anlegen einer Empfehlung in
  known_signals automatisch zur Fix-Liste offerieren. **Test:** AppTest: Empfehlung
  nicht in Top-Liste + leere Fix-Liste → sichtbarer Hinweis.

### F5 — MITTEL (Abdeckung): 8 von 60 Slots (13 %) ohne Urteil — 2 neue Parser-Artefakte + Spec-Lücken
- **Belege (Log 00:04:19–00:05:44, `signals.stats.last_fehler`):**
  - 840474: `Zeile 9220: Pflichtfeld fehlt (Buy)` — 2 Versuche, neuer Artefakt-Typ
    (nicht in der bekannten Liste AGENTS Pkt. 5).
  - 2268766: `unbekannter Datensatztyp 'Correction'` — ebenso neuer Typ.
  - 2000892/2005451/2007510/2019435 (pelik): USOIL `cross_broker=false` + Broker
    UNBEKANNT (Quellen-Metrics liefern keine Broker-Kennung) → `exposure.py:231`
    verweigert zu Recht, blockiert damit aber JEDES Öl handelnde Quellen-Signal.
  - 2014626/2019075 (pelik): GER40 ohne Spec (in `contract_specs.json` heißt es DE40 —
    Alias fehlt).
- **Persistenz korrekt:** alle 8 mit `last_fehler` in `signals.stats`; 2 davon mit
  Teil-Forensik (`vollstaendig=false`); keine Chronik-Einträge (korrekt, kein ⚪-Flackern);
  840474/2268766 behalten Alt-Forensik (05./07.09) → „Veraltete Forensik"-Urteil.
- **Korrekturidee:** Parser: Zeilen ohne Pflichtfeld + Typ `Correction` als Artefakt
  behandeln (mit Tests an echten Auszügen); GER40→DE40-Alias in `symbols.py`; für
  Quellen-Signale ohne Brokerangabe Öl-Spec mit Warnflag „Broker unbekannt, Annahme
  X Barrel/Lot" statt harte Verweigerung (oder Downloader liefert Broker je Provider).
  **Tests:** je ein Parse-/Spec-Fall.

### F6 — NIEDRIG: results.json hält Score fehlgeschlagener Signale, DB-Payload nicht
- **Ort:** `pipeline.py:1000-1007` — `evaluate()` setzt `res.score`, erst danach
  raise „Forensik unvollständig" → Score bleibt im ScanResult (Archiv), während der
  DB-Forensik-Payload `score: None` schreibt (`pipeline.py:1106`).
- **Beobachtet:** 2014626 → results ⚪ Score 5,8 vs DB ⚪ None; 2019075 → 🔴 6,4 vs None.
  Kein Bewertungsfehler (Fehler/⛔ dominieren das Urteil), aber Archiv ≠ DB.
- **Korrekturidee:** bei `not forensik_vorhanden` auch `res.score=None` setzen ODER im
  Payload dokumentieren. **Test:** Fixture mit unvollständiger Batterie → Score in
  Archiv und DB identisch (beide None).

### F7 — NIEDRIG: Equity-Reko nur für 50 % der MQL5-Signale wirksam (Symbol-Suffixe)
- **Beobachtet (52 Forensik-OK):** reko ok 14, unvollständig 7 (Abdeckung < 95 %, z. B.
  RAZOR 72 % bei dd 72,1 % — korrekt NICHT in die Schranke), skipped 8 (Kursdaten
  fehlen für **alle** Trades: AUDCADR, XAUUSD.F, EURUSD+, XAUUSD+, *-ECN, XAGUSD.Z),
  None 25 (23 pelik-Monitor-Skip + 2 Teil-Fails). MQL5-Erfolgsquote: 14/28.
- **Ursache:** `kursdaten.hole_h1` → `marktdata.broker_symbol` findet im lokalen
  Tickmill-Terminal keine Suffix-Symbole (Log 00:02:33/00:02:51/00:03:05 …). Das ist
  Datenlage, kein Codefehler — aber die Wirksamkeit der 28.09. eingebauten vierten
  Schranke ist bei Broker-Suffix-Signalen faktisch 0.
- **Korrekturidee:** Suffix-Tolerantes Symbol-Resolution (Basis-Symbol testen, wenn
  exaktes Symbol fehlt — mit Warnung); alternativ Symbol-Mapping konfigurierbar.

---

## B) Risiken (latent, im Ziellauf nicht eingetreten)

### R1 — ID-Kollision MQL5 ↔ Pelican ist möglich und würde still überschreiben
- **Code:** Vereinigungs-Dedup-Key ist `(id, platform)` (`pipeline.py:711-714`,
  `ingest.py:127`); Pelican mapt auf `platform="pelican"` (`ingest.py:27`), MQL5-Direkt
  auf `mt4`/`mt5` → die Regel „MQL5-Direkt gewinnt bei Doppelung" kann für pelik/robo/
  vant/zulu **niemals** greifen. `signals`-PK ist `signal_id INTEGER` ALLEIN
  (`db.py:38-49`); ebenso `forensik`, `trade_files`, `analyses` (je signal_id),
  `ampel_verlauf` (signal_id, ts).
- **Faktisch im Ziellauf:** KEINE Kollision — Schnittmenge der 30 pelik-IDs mit den 61
  mql5-IDs leer; candidates.json ohne doppelte IDs. ABER die ID-Räume überlappen
  numerisch: MQL5-Signale 2023752/2049326/2084890 liegen im selben 2.0–2.1M-Band wie
  die 30 Pelican-IDs (2048284…2084818). Treffer wäre eine Frage der Zeit.
- **Auswirkung bei Eintritt:** upsert überschreibt name/platform/stats/quelle
  (`db.py:214-233`, quelle wird beim Update mitgeschrieben), Forensik und KI-Texte
  vermischen sich, Chronik beider Signale verschmilzt — ohne jede Warnung.
- **Einordnung:** Als offene Stufe 2–4 (Composite-Identität) dokumentiert (doc/20 §7,
  AGENTS „Noch offen"). Dringlichkeit steigt mit jeder weiteren Quelle.
- **Korrekturidee (minimal bis Stufe 2):** Kollisionsschutz beim Schreiben: wenn
  `signals.quelle` != Kandidaten-Quelle → hartes Log/Ereignis statt Überschreiben
  (Fail-safe, bis Composite-PK (quelle, signal_id) migriert ist). **Test:** dieselbe ID
  aus zwei Quellen scannen → zweiter Lauf muss verwarnen, nicht überschreiben.

### R2 — REST-API liefert den Gesamtkatalog mit alten Ampeln, ohne Altersmarker
- **Code/Verhalten:** `rest_api._results_aus_db` → `pipeline.results_from_db()` je
  Request live aus der DB (verifiziert per Simulation auf der Kopie): 91 Signale,
  `?ampel=gruen,gelb` → **30** Zeilen — inkl. Signale, die seit Wochen nicht gescannt
  wurden (KiraCat 🟡 mit Forensik vom 08.09.; Gold Spike MT5 fehlt korrekt als stale).
  Für MqlRealMonitor nicht erkennbar, wie frisch eine Ampel ist.
- **Korrekturidee:** Feld `forensikUpdatedAt` (+ ggf. `stale: true` nach
  results_from_db-Logik) in den Payload; oder nur Signale liefern, deren letzter Lauf
  < N Tage alt ist (konfigurierbar). **Test:** alte Forensik → `stale:true`.

### R3 — Quell-Ausfall (mql5 :8089) senkt den Lauf nicht ab
- `[listen]` loggt „Quelle mql5: Katalog nicht erreichbar" nur (`ingest.py:122-124`,
  weiterlaufen ist gewollt und korrekt — Vereinigung 963 stand). Der Lauf gilt weiter
  als normal; einzig Station 6 (Downloader) endet am Ende mit „warning". Kein Fehler —
  aber es existiert keine Lauf-Zusammenfassung „Quelle X fehlte" außer der Log-Zeile
  (results.json logs.listen enthält sie ✓). Verbesserung: Downloader-/Quellenstatus
  als Feld im Run-Archiv.

### R4 — Monitorwerte auf virtueller Basis > 100 % (241 %, 241/316 %) 
- `monitor_trade_eq_dd_pct` 241,3 % (AccurateCopier), 316,6 % (Deus ex machina pelik,
  Fail) — dividiert gegen die virtuelle 10k-Annahme. `stats.kapitalbasis_virtual_usd`
  wird zwar mitpersistiert und `_forensik_json` liefert `kapitalbasis_verwendet`
  (virtuell) mit, aber der Rohwert selbst trägt keine Basis-Kennung in
  Matrix/Urteil. Klarstellung/Kennzeichnung empfohlen (siehe F1).

### R5 — Token-Budget: alle 52 Berichte wurden neu erzeugt (~1,7 M Tokens/Lauf)
- `berichte_neu`-Toggle stand offenbar aus (Default), aber die
  Berichts-Identität (`report_basis_for`, u. a. CSV-SHA256) ändert sich bei täglich
  handelnden Signalen praktisch jeden Lauf → restore_current_reports findet keine
  passenden alten Berichte mehr. Effekt: Vollkosten. Portfolio-Prompt 209.081 Zeichen.
  Verbesserung: Berichts-Basis toleranter fassen (z. B. Signifikanz-Schwelle für
  CSV-Drift) oder Budget-Kappung pro Lauf priorisieren (neue 🟢/🟡 zuerst).

---

## C) Verifizierte Konsistenz (kein Befund)

1. **Auswahl exakt reproduzierbar:** `waehle_fuer_export` (caa1074) mit
   Abonnenten-absteigend je Quelle + Fix-vorne liefert aus candidates.json exakt die
   60 IDs des Laufarchivs (Skript-Vergleich `True`); 30/69 + 30/34 entsprechen Log.
   GUI (`app_pages/scan.py:718`) und autonomer Launcher
   (`agenten/scan_launcher.py:130`) rufen dieselbe Funktion mit denselben Settings —
   einzige GUI-Zusätze: `nur_neue`-Filter (im Ziellauf aus) und Downloader-Station 6
   (Launcher: bewusst ohne).
2. **Zahlen-Kette lückenlos:** 74 Chronik-Einträge ab 23:00 = 22 (Vorgängerlauf bis
   Crash MCA100) + 52 (Ziellauf); Fails schreiben keine Einträge (Code
   `pipeline.py:1130`); results.json-Ampel ⛔13/🔴18/🟡16/🟢7/⚪6 vs. Chronik ⛔12/🔴17/
   🟡16/🟢7 — Differenzen exakt die fehlgeschlagenen ⛔2268766 und 🔴2019075
   (Martingale) ✓.
3. **Token-Abgleich:** Summe `analyses.tokens` 30.09. 00–03 Uhr (52×3 + Portfolio
   87.489) = **1.701.552** == Logzeile 02:53:45 ✓.
4. **Vierfach-Max korrekt:** ATong max(20,21/28,49/7,68/**64,92 Reko**) → 🔴;
   UpFuji max(27,15/5,15/3,83/**39,05**) → 🔴; World PEACE 34,22 (⛔ überdeckt);
   Lexo 0,78 → 🟢; Techno Long Term 60,08 → 🔴; unverlässliche Rekos (Abdeckung < 95 %,
   z. B. RAZOR 72,1 %, Kenni 31,43 %) korrekt NICHT in der Schranke, Matrix-Zellen
   stimmen mit den Rohwerten überein (forensik.kriterien_matrix auditiert).
5. **Log vs. DB (3 Stichproben):** ATong (Winrate 77,4/TD 7,68/Serie 19/Peak 48/
   Martingale JA/Orderbuch 379/8294), Gold Reaper (EQ-DD 7,18/PF 2,53/Ertrag 14,69/
   Reko 18,52 GMT+0), Lexo (EQ-DD 0,78/Ertrag 15,399/Winrate 74,1/TD 0,27/Serie 11/
   Peak 37) — alle identisch.
6. **Identitäts-Kette je Signal** (mql5 #2349227 Gold Spike, pelik #2000028 Lexo):
   candidates.json → quellen_artefakte (pelik: trades+metrics, SHA stimmt mit
   trade_files-SHA überein, 30/30 Artefakte) → data/quellen/pelik/*.csv|json +
   data/trade_snapshots/<sha>.csv (Datei vorhanden) → forensik v7 vollständig →
   analyses (nur Basis-passende Berichte aktiv, run-Analyses 100 % mit basis) →
   signals.quelle/platform ('mql5'/'MT4' bzw. 'pelik'/'pelican') → results.json →
   PDFs data/reports/signale/{id-slug}/ + portfolio/2026-09-30-02-53-45-* → REST
   (Simulation s. o.).
7. **Portfolio persistiert:** `analyses` kind='portfolio', signal_id NULL, 7.407
   Zeichen, 87.489 Tokens, PDF materialisiert ✓.
8. **Retry-Verhalten:** 8× „Prüfung fehlgeschlagen — einmalige Wiederholung", 8× auch
   Versuch 2 fehlgeschlagen (deterministische Fehler korrekt wiederholt; kein
   Retry-Erfolg im Lauf, daher nichts zum „Fehlertext des 1. Versuchs" zu prüfen);
   Fehlertexte stehen in signals.stats.last_fehler.
9. **Equity-Reko-Einbindung:** Terminal-Politik korrekt
   (`markt_start_erlauben=true` → portabler Selbststart 00:02:31 „Terminal verbunden";
   `kursdaten_beenden()` im finally, `app_pages/scan.py:804`,
   `agenten/scan_launcher.py:181` — kein MT5-Leak). Monitor-Skip griff für 23/24
   erfolgreiche pelik (Log „Datenquellen-Monitor liefert Trade-EQ-DD …"); Master H4-2
   ohne Monitorwert → Reko lief (GMT +3, 99,9 %) — beide Pfade belegt. MCA100
   (Crash-Ursache 29.09.) lief im Ziellauf sauber durch (Reko 13,92 %) — Fix ccc383b
   produktiv bestätigt.
10. **GMT/Plateau:** 0 Plateau-Skips („Auto-GMT mehrdeutig" kam nicht vor); GMT +0 h
    dominiert (Breitband-H1-Toleranz, viele Broker teilen die EET-Konvention des
    Referenz-Terminals; Trefferquoten 0,92–1,0) — plausibel, kein Fallback-Verdacht;
    Einzelfälle +1 h (SERONGGA) und +3 h (Master H4-2).
11. **FX ohne Doppel-Umrechnung (A9):** EZB-Cache `data/fx_rates/eurofxref-hist.csv`,
    geladen bis **2026-09-29** (Log bestätigt je Signal). Drawdown/Winrate summieren
    `t.net` roh (`forensics/drawdown.py:101,111`) — PnL der pelik-CSV ist bereits
    serverseitig USD, wird ALSO nicht nochmal konvertiert. Die FX-Umrechnung im
    Scanner betrifft nur selbst berechnete Beträge (Schock-Notional, Reko-Floating)
    in Quote-Währung → USD (`exposure.py:170-177`, `equity_rekonstruktion.py:241-247`);
    je pelik-Forensik als `fx_kursquelle` dokumentiert. Keine Doppel-Umrechnung.
12. **Ampel-Wechsel-Protokoll:** 17 Ereignisse im Ziellauf (nur UpFuji Farbwechsel
    🟡→🔴, Richtung „verschlechterung"; 16 Kriterien-Kipp-Ereignisse, korrekt gegen den
    letzten Chronik-Eintrag des VORLÄUFERLAUFs — ATong war dort schon 🔴, hence
    „Kriterium gekippt" statt Farbwechsel). Melder-Watcher findet beim nächsten Tick
    konsistente Daten vor.
13. **⛔-Semantik:** ⛔ = manueller Ausschluss (known_signals.json, `ampel_for`
    pipeline.py:354-357, überschreibt alles inkl. Fehler), wird in `ampel_verlauf`
    als eigene Farbe gezählt (21 von 74) — gewollt und so implementiert.
14. **results.json Struktur:** 60 Ergebnisse × 68 Felder (inkl. aller LLM-Texte,
    Berichte-Basis, ampel_wechsel je Signal, pdf_fehler leer), logs je Station
    (listen 4 / kandidaten 2 / forensik 669 / llm 260 / portfolio 2 / downloader 1),
    Portfolio mit Text+Meta. Einzige Lücke: Token-Verbrauch je Signal nur in DB
    (`analyses.tokens`), nicht im Archiv (nur Portfolio-Tokens).

---

## D) Nicht prüfbar / out of scope
- Ob `berichte_neu` manuell angeschaltet war oder alle 52 Basen stale waren
  (Run-Konfiguration wird nicht archiviert; beide Wege erklären den Log).
- MQL5-Login-/Cookie-Herkunft (Session laut Log gültig; Credentials bewusst nicht
  eingesehen).
- PelicanMonitor-Interna (Sub-Agent Pelican); LLM-Prompt-Inhalte (Sub-Agent Prompts).
- Ob/wann MqlRealMonitor die REST-API :8611 tatsächlich abruft (Server läuft im
  App-Prozess; Zugriffslog nicht verfügbar).
- Warum der MqlDownloader auf :8089 down war (externer Prozess; nur Divergenz
  localhost vs. 192.168.178.164 dokumentiert, siehe F2).
- Vollständigkeit des PDF-Spiegels beim Downloader vor dem 20.09. (nur lokale Sicht:
  17 Rows, letzter Fetch 20.09.).
