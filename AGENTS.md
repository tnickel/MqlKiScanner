# AGENTS.md — MqlKiScanner

Projekt: Scanner für MQL5-Handelssignale mit forensischer Risiko-Analyse und
zweistufigem LLM-Layer. Dieses Projekt ist die Fortsetzung einer Analyse-Reihe,
die im Workspace `D:\AntiGravitySoftware\GitWorkspace\Allgemein` durchgeführt
wurde (Ursprungs-Session: `sess_ff799a20-8b9b-4b1b-b605-0826e01ceffa` — bei
Bedarf mit ReadSessionContext referenzierbar; zusätzlich liegt alles Wesentliche
in `doc/` und `data/` dieses Projekts).

## Auftrag und Nutzer-Kriterien (fest)

Tool, das MQL5-Signale scannt, forensisch prüft und Kandidaten bewertet.

- **Risiko VOR Ertrag.** Harte Drawdown-Schranke: 30 % max.
- Ertrag muss trotzdem stimmen: über 5 %/Monat.
- Kernfrage je Signal: Ist der Schutz (Stop-Loss) **bewiesen** oder nur behauptet?

## Aktuelles Ergebnis der Analyse-Reihe (Stand 04.09.2026)

- **Empfehlung (Duo):** Gold Spike (MT4 #2349227 / MT5 #2375480, Risikoträger)
  + KiraCat (#2342895, Ertragsträger).
- Gold Reaper (#2265877): solide Strategie, aber nur als EA-Kauf sinnvoll
  (8/14 Reviews: fehlgeschlagene Kopien).
- **Pure Gold 2000 Vantage (#2362868): HERABGESTUFT** — sieht auf dem Papier
  top aus (EQ-DD 5,1 %, +26 %/Monat), aber: max. 32 gleichzeitige SELL-Positionen
  mit 2,66 Lots netto (= 266 USD Risiko je 1 USD Goldbewegung; 50-USD-Schock
  ~ -13.300 USD) und KEIN Stop-Loss-Nachweis. Der Nutzer hat dies zu Recht
  angezweifelt.
- Watchlist: GoldWave (#2339082, Micro-Konto/Pfennig-Jagd), SFE Impulse
  (#2049326, vom Nutzer abgelehnt: 12 Monate Seitwärts).
- Vollständige Ausschlussliste mit Begründungen: `data/known_signals.json`
  und `doc/01_analysen-verlauf.md`.

## Technisches Wissen (kritisch — hier wurden Fehler gemacht, nicht wiederholen)

1. **Trade-Export:** MT5: `https://www.mql5.com/en/signals/{ID}/export/positions`;
   MT4: `.../export/history` (Orderbuch mit S/L; `/export/positions` → HTTP 404).
   Login-Cookie nötig. Erfolg: Antwort beginnt mit `Time;`. Session abgelaufen:
   Antwort ist Login-HTML (`<!DOCTYPE`) → neu einloggen
   (https://www.mql5.com/en/auth_login). Zugangsdaten: beim Nutzer erfragen
   (stehen auch in der Automation im Workspace Allgemein) — **nie in Code/Repo**.
2. **Positions-Export (MT5) enthält KEINE SL/TP-Spalten.** Stop-Nachweis nur über
   (a) MT4-History-Export / Orderbuch-CSV (S/L-Spalte und [sl]/[tp]-Kommentaren,
   Beispiel: `data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv`) oder (b) statistische
   Signaturen. "Kein Nachweis" = Warnflag, niemals Entlastung.
3. **XAUUSD-Kontraktgröße: 1 Lot = 100 USD je 1 USD Kursbewegung.**
   Exposure-Rechnung: Peak-Lots × 100 × Schockbewegung. (Dieser Faktor wurde in
   der Reihe einmal falsch angesetzt und führte zu einer Fehleinschätzung.)
   Weitere Instrumente (Krypto, Silber, Öl, DE40/USTEC/CHINA50, XAUEUR) seit
   09/2026 belegt in `data/contract_specs.json` (Quelle je Eintrag, Stand:
   Tickmill; Öl `cross_broker=false` — Tickmill 1 Barrel/Lot, andere 100!).
   Fremdwährungs-Quotes (FX-Kreuze, EUR-Gold, DE40) werden mit EZB-
   Referenzkursen je Handelstag nach USD umgerechnet (`src/mqlkiscanner/
   fx_rates.py`, Cache `data/fx_rates/`, Details doc/02 Abschnitt 5a/5b).
4. **Pflicht-Test-Batterie VOR jedem positiven Urteil** (Spec: `doc/03_forensik-tests.md`):
   a) Martingale-Signatur: Lot(i+1)/Lot(i) nach Verlust — Median > 1,3x = Flag
   b) Peak-Exposure: max. gleichzeitig offene Positionen + aggregiertes
      Netto-Volumen in USD-Risiko
   c) SL-Clustering: ballen sich Verlustdistanzen an einem Niveau?
   d) Drawdown-Rekonstruktion aus Trades, Abgleich mit Plattformwerten
      (Deckung auf den Cent = Datenkonsistenznachweis)
5. **CSV-Formate:** zwei Varianten — Positions-Export (11 Spalten, Profit =
   Spalte 10, Tausendertrennzeichen als Leerzeichen in Zahlen, z. B. "1 403.03")
   und MT4-Orderbuch (13 Spalten, Profit = Spalte 11, Kommentar = Spalte 12).
   Parser in `scripts/reference/` behandeln beides. **Export-Artefakte, die
   der Produktiv-Parser (`src/mqlkiscanner/parser.py`) bekannt ist:** (a)
   MT4-Orderbuch endet mit einer Summenzeile (Typ Buy/Sell, Symbol wörtlich
   `profit`, keine Preise, Gesamtsummen in Commission/Profit) — wird
   übersprungen, sonst blockiert sie ganze Signale; (b) MT5-Export enthält
   vereinzelt Zeilen mit NUR Zeitstempel — ebenfalls Überspringen; Inhalt
   ohne Typ bleibt ein lauter Fehler. Tests:
   `tests/test_parser_export_artefakte.py`, Details doc/02 Abschnitt 3.
6. **Scraping behutsam:** Rate-Limit einbauen (wenige Requests/Minute,
   Pausen zwischen Signalen) — automatisiertes Abrufen kann gegen MQL5-ToS
   verstoßen (Accountsperren-Risiko). Login-Daten nie in Code/Repo (env vars).

## Design-Regeln (aus der Reihe gelernt — Ursachen in doc/01)

1. **Code rechnet ALLE Zahlen; das LLM bekommt nur fertige Befunde als JSON**
   und formuliert/liefert Interpretation. LLM rechnet nie selbst
   (Halluzinationsrisiko bei Arithmetik). **Ausnahme (Nutzer-Wunsch, 20.09.2026):**
   Prompt 5 „Tiefenanalyse" (manuelle Erweiterte KI-Analyse) darf auf
   Trade-Basis rechnen (z. B. Verlustwahrscheinlichkeit) — die Vorlage
   verlangt Grundlage und Annahmen; Ampel/Score/Urteil bleiben davon
   unberührt.
2. Kein Kandidat erhält eine positive Einstufung vor bestandener Pflicht-Tests.
3. Signalnamen lügen ("Low Risk", "Stable", "Hedge") — Drawdown + Exposure zählen.
4. Abonnentenzahl korreliert mit Marketing/Alter, nicht mit Qualität
   (Riskanteste Signale haben die meisten Abonnenten).
5. Zwei-Stufen-LLM: Flash-Klasse für Massen-Profile (Stufe 1 Scan), starkes
   Modell nur für Finalisten (Stufe 2 Verdict). MQL5-Credentials liegen nur im
   Crawler-Modul, nie im LLM-Kontext.
6. Vision/Bildanalyse wird für den Kern NICHT benötigt (Daten kommen als
   HTML/CSV) — optional als Extra für Ad-hoc-Screenshots.

## Projektstruktur

- `doc/` — Doku: Analyse-Verlauf, MQL5-Technik, Forensik-Test-Spec, Roadmap,
  `reports/` (6 fertige PDF-Berichte als Formatreferenz)
- `data/raw/` — reale Trade-CSVs aller analysierten Signale (Testdaten für die
  Pipeline; Gold Spike MT4 = Orderbuch-Format-Beispiel)
- `data/known_signals.json` — maschinenlesbar: Ausschlüsse, Watchlist, Empfehlung
- `scripts/reference/` — **bewährte, funktionierende** Analyse-Skripte aus der
  Reihe (Parser, Forensik-Tests, News-Korrelation, MT4/MT5-Vergleich) — als
  Referenzimplementierung konsolidieren, nicht neu erfinden
- `streamlit_app.py` + `app_pages/` — Streamlit-GUI (Scan, Ergebnisse, Admin)
- `src/mqlkiscanner/` — **das Tool, gebaut und getestet** (Stand 21.09.2026):
  Engine (`engine.py`, `pipeline.py`, `stats.py`, `scoring.py`, `parser.py`),
  Forensik (`forensics/`), MQL5-Zugriff (`mql5/` — Crawler, Session, Exporter,
  Rate-Limit), LLM-Layer (`llm/`), SQLite (`db.py`), Ampel-Matrix
  (`ampel_matrix.py`), Ausschluss-Regelwerk (`regelwerk.py`),
  PDF-Berichte (`pdf_reports.py`), EZB-Kurse (`fx_rates.py`),
  MqlDownloader-Anbindung (`downloader_client.py`, `downloader_sync.py`),
  Tradeserver-Sync zum MqlTradeMonitor (`tradeserver_client.py`,
  `tradeserver_sync.py` — Einmal-Protokoll v1 unter /api/kiscanner,
  Doku `doc/06_tradeserver-sync.md`; bewertet nie neu),
  REST-API für den MqlRealMonitor (`rest_api.py` — schreibgeschützt,
  GET /api/v1/signals?ampel=gruen,gelb auf 127.0.0.1:8611, startet
  als Daemon-Thread mit der Streamlit-App; bewertet nie neu),
  Ampel-Verlauf (`ampel_verlauf.py` — Farb-Chronik je Lauf plus
  protokollierte Wechsel mit Kriterium-Begründungen, Tabellen
  `ampel_verlauf`/`ampel_wechsel`; bewertet selbst nichts, nur
  Aufzeichnung des Engine-Ergebnisses),
  Agentenbetrieb (`agenten/` — autonomer LLM-Daemon nach Bauplan
  `doc/19_agentenbetrieb-bauplan.md`: Dirigent-Tageslauf [Phase A,
  22.09.2026], Journal/Protokoll [`agenten_laeufe`/`agenten_schritte`/
  `agenten_meldungen`/`agenten_steuerung`], prozessübergreifendes
  Lauf-Lock, Rollen-Registry mit GLM-5.3 als Standard JE Rolle
  [Nutzer-Vorgabe 22.09.2026], 6 Rollen-Prompts unter
  `config/prompts/agenten/`; Daemon-Start/Stopp über Admin → Agenten
  oder CLI `PYTHONPATH=src python -m mqlkiscanner.agenten [--tick|--alles|…]`
  (—alles = komplette Tageskette, wie der Komplettlauf-Button auf der
  Agenten-Seite — Orchestrierung `agenten/tageskette.py`);
  bewertet nie, beobachtet und meldet nur — LLM-Schritte protokollieren
  vollen Prompt und volle Antwort, kein Trockenmodus)
- `config/prompts/` — editierbare LLM-Prompts (Workflow) und
  `config/prompts/agenten/` — editierbare Rollen-Prompts
- `tests/` — pytest (898 Tests grün; LLM-Regressionstests opt-in via
  `pytest -m llm`, echte Modellaufrufe)

## Umsetzungsstand (Stand 22.09.2026)

Entschieden und umgesetzt (Details: `doc/04_roadmap.md`):

- ✅ Stack: Python + Streamlit (`streamlit_app.py`, `app_pages/`)
- ✅ LLM: GLM über Z.ai-API (OpenAI-kompatibel), zweistufig — Stufe 1
  `glm-5.3-flash` (Massen-Profile im Scan), Stufe 2 `glm-5.3` (Finalisten);
  Token-Budget je Lauf; Key via `GLM_API_KEY` (Env/`.env`/Admin-UI).
  Coding-Plan-Endpunkt ist Default (Pay-as-you-go-Key auf dem Coding-Endpunkt
  → Fehler 1113, siehe `config.py`)
- ✅ LLM-Layer ist optional: Engine läuft ohne Key komplett (Scan + Forensik
  + Ampel-Ausgabe)
- ✅ Tradeserver-Sync (20.09.2026): Einmallauf zum MqlTradeMonitor
  (Spring-Boot, D:\AntiGravitySoftware\GitWorkspace\MqlTradeMonitor) —
  Button „Tradeserver-Sync“ auf der Ergebnisseite überträgt die Tabelle
  + alle PDFs (eigne Berichte, Portfolio, Downloader-Spiegel; SHA-256-Diff)
  über das Sonderprotokoll v1 (/api/kiscanner, X-User-Key-Handshake);
  danach wird die Verbindung getrennt. Server zeigt Kachel „🔬 MqlKiScanner“
  + Seite /kiscanner. Konfiguration: Admin → Tradeserver (Base-URL +
  API-Key im secrets_store). Doku: `doc/06_tradeserver-sync.md`
- ✅ Ampel-Verlauf + Re-Scan-Buttons (21.09.2026): Scan-Seite hat zwei
  Start-Buttons — **Full-Scan** (alles) und **Teilscan** (vormals
  Gelb/Grün-Scan; nur aktuell
  🟢/🟡-Signale laut DB, IMMER alle LLM-Stufen neu; andere Farben werden
  nicht beachtet). Jeder erfolgreich persistierte Scan schreibt die Ampel
  in die append-only-Chronik (`ampel_verlauf`); gegen den Vorgänger wird
  jeder Farbwechsel ODER jedes gekippte Einzelkriterium als `ampel_wechsel`
  protokolliert (mit alt→neu je Kriterium und exakter Berechnung).
  Lauf-Wechsel erscheinen direkt auf der Scan-Seite, das Gesamt-Protokoll
  per Button „Wechsel-Protokoll“ auf der Ergebnisseite. Fehlgeschlagene
  Prüfungen schreiben keinen Eintrag (kein ⚪-Flackern); Reimport alter
  Läufe bewusst NEIN (Nutzer-Entscheidung).
- ✅ Agentenbetrieb Phase A (22.09.2026, Bauplan `doc/19`): Daemon-Prozess
  im selben Repo (`agenten/`), Dirigent-Tageslauf werktags zur Startzeit
  (Lagestatus → Code-Plan → optionale LLM-Randentscheidung mit
  Aktions-Whitelist), lückenloses Schritt-Protokoll in SQLite,
  Lauf-Lock gegen die GUI, Token-Tages-/Monatsbudget, Admin-Tab
  „Agenten“ (Rollenkarten mit GLM-5.3-Default, Budget/Takt, Daemon
  Start/Stopp, Rollen-Prompt-Editor) und Seite „Agenten“ (Live +
  Protokoll mit vollem Prompt/voller Antwort je LLM-Schritt). Rollen
  Markt/Betreuer/Chef/Melder folgen in Phase B–E. 812 Tests grün.
- ✅ Agentenbetrieb Phase B (22.09.2026): Signal-Dossiers
  (`dossier_profil` versioniert / `dossier_beobachtungen` /
  `trade_deltas`), Profil-Destillation aus Tiefenanalyse+Gesamtbericht
  (einmalig je 🟢/🟡; ohne Belegbasis wird NICHT erfunden), Betreuer-
  Tageslauf täglich 06:45 (Startzeit + 15 min): MQL5-Export über
  Rate-Limiter/20-h-Cache → SHA-Vergleich (unverändert = KEIN
  Modellaufruf) → Delta-Kennzahlen (Code) → LLM-Prüfung gegen Profil →
  Einordnung KONFORM/AUFFAELLIG/STILBRUCH/KEINE_NEUEN_TRADES ins
  Dossier; Dossiers-Tab auf der Agenten-Seite; CLI `--betreuer`.
  Ende-zu-Ende verifiziert (echte Destillation Gold Spike 6.067 Zeichen;
  Delta-Prüfung KONFORM mit Merkmal-Zitaten). 825 Tests grün.
- ✅ Agentenbetrieb Phase C (22.09.2026): Marktbeobachter — Kursdaten über
  das offizielle `MetaTrader5`-Paket, NUR LESEND (Whitelist statisch
  getestet: initialize/terminal_info/symbol_select/copy_rates_*/shutdown;
  Order-Funktionen nicht verdrahtet), Start-Politik Standard NEIN (ohne
  laufendes Terminal sauberer Skip, im Protokoll begründet), Symbol-
  Beobachtungsliste automatisch aus 🟢/🟡-Forensik + manuell, Kennzahlen
  reiner Code (Bewegung 1/7/30 T, Distanz Hoch/Tief, ATR14 H1,
  Tagesrange, Trend vs. SMA10), Tabelle `markt_kontext`, LLM-Lage mit
  maschineller Fallback-Fassung, Betreuer-Prompts zitieren den
  Tageskontext, Admin-Bereich „Marktdaten" mit Verbindungstest, Takt
  Startzeit + 5 min, CLI `--markt`. E2E verifiziert (synthetische Kurse
  + echtes LLM auf Temp-DB; Produktions-Skip ohne Terminal). 839 Tests
  grün. **Update 22.09.2026 abends — Selbststart AKTIV (Nutzer-Freigabe)
  und V1-Attach E2E bestätigt:** `markt_start_erlauben=true` in
  app_settings.json; `initialize(pfad, portable=True)` startet das
  Terminal PORTABEL und `terminal_beenden()` schließt es nach jedem Lauf
  (sanft dann hart; auch ein vorgefundenes Terminal dieses Pfads —
  Nutzer-Regel „es gehört dem Scanner"); Prozess-Check pfadgenau über
  CIM (fremde MT5-Installationen unberührt); Beobachtungsliste parst
  Forensik-Artefakte („+"-Suffix, „SUMMARY") robust;
  `agenten_markt_max_tokens=16384` (30 Symbole sprengten 4096/8192).
  Ergebnisse in doc/19 §7.3/§7.4.
- ✅ Agentenbetrieb Phase D (22.09.2026): Melder — dreifacher Weg ins
  **Postfach** (Tab auf der Agenten-Seite): SOFORT-Alert des Betreuers
  bei STILBRUCH (P3), Ampelwechsel-Watcher in JEDEM Scheduler-Tick
  (bemerkt auch Wechsel aus GUI-Scans; idempotent über letzte
  bearbeitete Wechsel-ID in der Steuerung; Verschlechterung P3,
  sonst P2) und Tagesdigest (Takt Startzeit + 40 min; verschiebt sich
  automatisch, solange der Betreuer läuft; LLM-Fassung mit
  maschineller Fallback-Meldung). `agenten_meldungen` mit
  Priorität/Quellen-Verweisen; CLI `--digest`. Abnahme verifiziert:
  künstlicher Ampelwechsel erzeugt Alert mit Quellverweis. 849 Tests
  grün.
- ✅ Agentenbetrieb Phase E (22.09.2026 — KOMPLETT): Chefermittler +
  autonome Scan-Anstöße. `agenten/chef.py` (Wochen-/Monats-Lagebericht:
  Dossier-Spitzen, Marktkontexte und Wechsel der Woche, Budget — als
  Meldung `lagebericht` ins Postfach; verschiebt sich bei laufendem
  Scan; empfiehlt, bewertet nie neu), `agenten/scan_launcher.py`
  (headless-Pipeline exakt wie die Scan-Seite: Listen → Kandidaten →
  Teilscan-Scope über results_from_db → Forensik mit Login/Fail-Fast →
  KI-Berichte → Portfolio; Scan-Abschluss als Postfach-Meldung;
  Monats-/Tages-Merker gegen Wiederholung; Lauf-Lock; Thread, damit der
  Daemon-Herzschlag frisch bleibt). Takte: Sonntag 12:00 Teilscan,
  1. Werktag des Monats Full-Scan (ab Startzeit+60), Chef sonntags ab
  18 Uhr und am Full-Scan-Tag (wartet auf Scan-Ende); Digest/Lagebericht
  bleiben unfällig, während lange Läufe arbeiten (kein Skip-Spam). CLI:
  `--chef`, `--scan gelbgruen|full`. 861 Tests grün. Abnahme „Monat
  ohne Scan-Klick": Orchestrierung verifiziert (Fake-Pipeline-Tests +
  Scheduler-Takte); der erste echte autonome Monat beginnt mit dem
  nächsten Sonntag (Teilscan) bzw. 1. Werktag (Full).
- ✅ Komplettlauf (23.09.2026): Der ganze Agenten-Workflow mit EINEM
  Knopf — Button „Kompletten Agenten-Workflow jetzt ausführen" auf der
  Agenten-Seite (Live) und CLI `--alles`. Orchestrierung in
  `agenten/tageskette.py`: Ampelwechsel-Watcher → Dirigent → Markt →
  Betreuer → Tagesdigest in Daemon-Reihenfolge, aber OHNE Takt-Prüfung;
  respektiert Rollen-Aktivschalter und Lauf-Lock (besetzte Rolle =
  dokumentierter Skip im Journal, nie ein Doppel-Lauf); eine fehlge-
  schlagene Rolle hält die Kette nicht auf; Chef und autonome Scans
  bleiben bewusst an ihre Takte gebunden. Live-Fortschritt im Status-
  Kasten mit Aktivitäts-Banner, Ergebnis-Zusammenfassung nach dem Rerun;
  Baum + Kacheln leuchten über die ganze Kette; der Button ist gesperrt,
  solange ein Agentenlauf aktiv ist (kein Zweitlauf aus gepufferten
  Doppelklicks). Die Kette läuft im HINTERGRUND-THREAD prozessweit weiter
  (Reload-sicher — F5 brach die Kette anfangs still nach dem Betreuer ab,
  Digest startete nie); Live-Anzeige als st.fragment(run_every=2 s) über
  tageskette.zustand(). 898 Tests grün.
- ✅ Automatik-Seite + fette Marke (24.09.2026): Neuer Nav-Punkt
  **Konfiguration → Automatik** (app_pages/automatik.py, Muster
  Goldscanner) — Daemon-Status mit Start/Stopp (setzt agenten_enabled
  mit) und Zeitplan je Job: Wochentag (Werktags/Täglich/fester Tag) +
  Uhrzeit für Dirigent, Markt, Betreuer, Melder, Chef, Teilscan; der
  Full-Scan behält seinen Monatstermin (1. Werktag, nur Uhrzeit frei).
  Settings `agenten_{job}_tag`/`agenten_{job}_zeit`, Auflösung in
  `scheduler.job_termin()` — ohne Keys gilt das bisherige Verhalten
  (werktags Kette zur agenten_start_zeit, Chef/Teilscan sonntags,
  Full-Scan ab Startzeit+60); ungültige Werte fallen auf die Defaults
  zurück. Daemon liest den Plan je Tick neu (kein Neustart nötig);
  Sonderregeln unverändert (Melder wartet auf Betreuer, Chef zusätzlich
  am Full-Scan-Tag ab Startzeit+150, Merker gegen Wiederholung).
  Außerdem: Sidebar-Marke „MqlKiScanner" fett/größer (Nutzer-Wunsch —
  Produktname muss sichtbar sein) und im Help-System das Thema
  „automatik". Nav-Punkt „Automatik" zeigt den Zustand live mit
  (🟢 OK bei Herzschlag + Freigabe, sonst 🔴 OFF — daemon.status_text).
  913 Tests grün.

Noch offen (Betrieb — Agentenbetrieb Phasen A–E sind KOMPLETT):

- [x] Re-Scan als Kommandozeilenaufruf — erledigt über Phase E:
      `--scan gelbgruen|full` (plus `--once`, `--markt`, `--betreuer`,
      `--digest`, `--chef`, `--alles` = komplette Tageskette)
- [x] Automatisierte Alerts (Ampelwechsel, Stilbruch, Scan-Abschluss) —
      Melder/Postfach, Phase D/E
- [x] V1-Attach-Prüfung mit Nutzer — ERLEDIGT 22.09.2026 (Selbststart UND
      Attach E2E verifiziert, Ergebnis in doc/19 §7.4 nachgetragen)
- [ ] Autostart des Daemon nach Rechner-Neustart (start.bat-Erweiterung
      oder Aufgabenplanung — offen, Nutzer-Entscheidung)
- [ ] Erster voller autonomer Monat (Bestätigung der Phase-E-Abnahme
      „Monat ohne Scan-Klick" nach Oktober 2026)
