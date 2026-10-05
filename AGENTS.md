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

**Korrektur KiraCat (03.10.2026):** Die alte Duo-Empfehlung ist fuer KiraCat
ueberholt: aktuell Plattform-EQ-DD 34,95 % und rote 30-%-Schranke. 7,9/8,14 %
sind Drawdowns GESCHLOSSENER Trades auf virtueller Trading-Kapitalbasis,
kein Nachweis fuer niedrigen Konto-Equity-DD. Die historische H1-Reko
44,34 % ignoriert spaetere Einzahlungen/Entnahmen; mit echten Kapitalfluessen
und neutralisiertem Renditeindex ergibt dasselbe H1-Fenster ca. 20,4 %.
Auch das ist kein vollstaendiger aktueller Broker-DD: US100-Kurse fehlen,
fuenf Flows bei offenen Trades brauchen Preisnaeherungen, Export endet am
28.09.2026, aktuelle offene Positionen fehlen. Aus verschiedenen DD-Basen
niemals eine beschoenigte Plattform-Meldung folgern. H1-Close gilt am
BAR-ENDE; alle exportierten Trades bleiben im realisierten Netto enthalten,
auch wenn ihre Kursdaten fehlen. Forensik-Version 8 erzwingt Neupruefung
alter Befunde. Review: `../waste/drawdown_2026-10-03/review.md`.

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
   Signaturen. "Kein Nachweis" = NEUTRAL — die meisten Broker übertragen
   keinen SL (Nutzer-Regel 28.09.2026): kein Malus im Score, keine Ampel-
   Sperre, keine Matrix-Abwertung. Abwerten darf NUR die KI-Analyse
   (Tiefenanalyse/Verhaltensanalyse) mit begründeter Einschätzung
   "wahrscheinlich ohne Stop-Schutz"; bewiesener SL bleibt Entlastung.
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

**Ertrag/RetDD (Nutzer-Regel 03.10.2026):** Tabelle zeigt eigene geometrische
`Gewinn %/Monat` und `RetDD` neben dem farbigen gemessenen Max-Equity-DD.
RetDD = geometrische Monatsrendite / gemessener Max-Equity-DD (valide
H1-/Monitor-Messung, hoechste davon). NIEMALS geschlossene Trades,
Balance-DD oder Plattform-Selbstauskunft als Ersatznenner. Ohne positive
Equity-Messung bleibt RetDD unbekannt und kein Gruen. Gewinn bleibt bei
fehlendem Equity-DD messbar. Monatsrendite aus ungerundetem End/Start und
echter Zeitspanne erster Open bis letzter Close; Jahr 365,2425 Tage,
Monat = Jahr/12. Leermonate nicht aus der Laufzeit herauskuerzen; Auswahl
prueft ungerundete Werte (0,9995 ist NICHT >=1). Ertragskriterium jetzt
eigene geometrische Rendite >= konfigurierte Monatsschwelle statt linearem
B2-/Plattformwert; RetDD >=1 bleibt fest. Harte Risiko-Schranke weiterhin
konservatives Maximum aller fuenf DD-Werte; guter RetDD hebt sie nie auf.
KI erhaelt Codewerte, Zeit-/Kapitalbasis, Messstatus und aktuelle Kriterien;
historische Rendite ist keine Prognose. Forensik-Version 9; alte Befunde
neu scannen. Review im Archiv `../waste/retdd_equity_2026-10-03/`.

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

- **Review-Archiv (02.10., Nutzer-Wunsch):** Erledigte Review-/CR-Protokolle
  liegen in `../waste/` — OUTHALB des Repos, bewusst nicht auf GitHub, aber
  nicht gelöscht (codereview_2026-10-01, intensivreview_2026-09-29,
  laufreview_2026-10-02, stop_erkennung_2026-10-02). Neue Reviews zunächst
  unter doc/reviews/ führen; nach vollständiger Umsetzung dorthin verschieben.

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
  Fix-IDs (`fix_signale.py` — definierte Signal-IDs, die JEDEN Scan
  durchlaufen [Nutzer-Wunsch 28.09.2026]: Setting `fix_signal_ids`;
  umgehen Wochen-/Abonnenten-Vorfilter, stehen in der top_n_export-
  Auswahl vorne, sind im Teilscan-Scope immer dabei und werden, wenn
  sie nicht in den MQL5-Top-Listen stehen, einzeln von ihrer Details-
  seite nachgeladen [`crawler.fetch_signal_overview`, Plattform per
  data-mt/Titel — entscheidet den Export-Pfad]; GUI: Checkmark „📌
  Fix — immer scannen" in der Detailansicht, Verwaltung + ID-Eingabe
  auf der Ergebnisseite (Abschnitt „Fix-IDs · immer scannen"),
  Tabellen-Markierung 📌 FIX; bewertet völlig normal — Scan-Zusage,
  kein Vorzugsurteil),
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
- ✅ Multi-Source-Hub Stufe 1 (27.09.2026, Konzept `doc/20`): Der Scanner
  kann Signale über BELIEBIG VIELE Datenquellen-REST-Schnittstellen
  beziehen (erster Typ: MqlDownloader). Neue Module `quellen.py`
  (Registry-Tabelle `datenquellen` mit eindeutigem Kürzel je Quelle +
  Verbindungstest mit Ampel 🟢/🟡/🔴) und `ingest.py` (Katalog-Pagination,
  Trades-CSV + Metrics mit SHA-Artefakt-Cache `quellen_artefakte`).
  Admin-Tab „MqlDownloader" → „Datenquellen": komfortable Verwaltung
  (anlegen/bearbeiten/löschen/(de)aktivieren, „Alle Quellen testen",
  je Karte Ampel + letzter Test inkl. Signale-Zahl/API/Latenz); Tokens
  je Quelle im Secrets-Speicher (`datenquelle_{id}_token`). Scan-Seite:
  „Signale holen aus" = MQL5 direkt / Datenquellen (REST) / beides
  (Setting `listen_modus`, Default `mql5` = unverändertes Verhalten;
  bei Doppelung gewinnt MQL5-Direkt). Quellen-Kandidaten laufen ohne
  MQL5-Kontakt durch die unveränderte Forensik (Trades aus dem Quellen-
  Cache statt Exporter). Herkunft überall sichtbar: Spalte „Quelle" in
  der Ergebnistabelle + Feld `quelle` in der REST-API (:8611);
  `signals.quelle` (Bestand = 'mql5'). Sync (Abonnenten-Verlauf +
  PDFs) läuft über alle aktiven Quellen (idempotent, erste Quelle
  gewinnt; Teilausfall einer Quelle bricht nichts). Alte Einzel-
  Konfiguration wird automatisch als Quelle `mql5` übernommen.
  Nutzer-Entscheidungen in doc/20 §2: kein SL-Nachweis → Verhaltens-
  analyse statt Anforderung; Initial Deposit liefert künftig der
  Downloader (bis dahin ruht die Kapitalbasis-Regel für Quellen-
  Signale); Tagesfrische genügt; MPDD-Filter im Downloader ist gewollt.
  Offen (Stufen 2–4): Composite-Identität (quelle, signal_id), Betreuer
  umstellen, Crawler entfernen, weitere Börsen-Typen. 929 Tests grün.
- ✅ PelicanTrading als zweite Börse (27.09.2026 abends, doc/20 §4a;
  Währung korrigiert 28.09., doc/20 §4a.1): Der
  PelicanMonitor (SIGNALDOWNLOADER/PelicanTrading) spricht dasselbe REST-
  Protokoll mit Versions-Kürzel „pelican" (Port 8090, Autostart,
  data/rest_api.json, Instanz-Kennung; Toolbar-Button „REST-API an/aus").
  Trades werden serverseitig ins mql5-Positions-CSV konvertiert — die
  Forensik läuft unverändert. Währung seit 28.09. serverseitig gelöst:
  USD direkt, USC (US-Cent) fix ÷100, übrige Kontowährungen per EZB-
  Referenzkurs nach USD (Kurs je Provider offengelegt in metrics/Katalog;
  nur Geldbeträge skaliert; offline ohne je gecachten Kurs → trades.csv
  404 + Grund). Erweiterter metrics-Satz (Equity, Leverage, Trades/Monat,
  MarketsCount, TopMarkets, CopiersAum/-Profit) seit 28.09.; Initial-
  DepositVirtual 10000 als klar markierte Annahme — der Scanner nutzt sie
  seit 28.09. (Nutzer-Wunsch) über einen EIGENEN Kanal als Engine-Fallback
  (pipeline.KAPITALBASIS_QUELLE_VIRTUELL): ohne sie bliebe die Forensik
  unvollständig (Quellen-CSVs haben keine Einzahlungszeilen). Nie als
  initial_deposit_usd, nie im Cent-Abgleich, Urteil nennt „Kapitalbasis
  virtuell". Das ECHTE Initial Deposit gewinnt immer. Stop-Nachweis nur
  offene Positionen (Historie ehrlich „kein Nachweis" + Verhaltens-
  analyse), weeks im Katalog → Wochen-Vorfilter greift. Eigene
  KI-Risikoberichte (GLM-5.3) im Monitor selbst (MD+PDF, Risiko-Score
  1–10, data/reports; Altberichte 28.09. mit neuem Score-Schema
  zurückgesetzt) — unabhängig vom Scanner-LLM; /reports liefert (noch)
  eine leere Liste, der Scanner-Spiegel zeigt also noch nichts.
  Ende-zu-Ende-Akzeptanztest test_pelican_ende_zu_ende_wird_akzeptiert
  (28.09. nachgetragen: BOM, FX-Felder, virtuelle Kapitalbasis).
  Scanner-seitig: platform_version("pelican"), Plattform-Durchreichung.
  Anbindung: Admin → Datenquellen → z. B. Kürzel „pelik", http://rechner:8090.
- ✅ RoboMonitor (RoboForex) als dritte Quelle (27.09.2026 abends, doc/20
  §4b): RoboForex-CopyFX-Signale über dasselbe REST-Protokoll — Version je
  Plattform (mql4/mql5, je Signal), Port 8091, Autostart,
  data/rest_api.json, Instanz-Kennung, Toolbar-Button. MT4-Deals sind
  positionell, MT5-Rohdeals werden serverseitig über die IN/OUT-Paarung
  (TradeAggregator) zu Positionen — Commission/Swaps echt; CopyFX rechnet
  durchgehend USD (kein Währungsfilter). Scanner-seitig KEIN Adapter nötig
  (Ende-zu-Ende-Regressionstest bestätigt Akzeptanz). Grenzen: kein Initial
  Deposit (Kapitalbasis-Regel ruht), kein SL in Deal-Daten („kein
  Nachweis" + Verhaltensanalyse), Average3MonthProfit = hergeleitete
  Ø-Monatsrendite (Yield/Laufzeit), EquityDrawdown bevorzugt Gesamt-DD.
  Anbindung: Admin → Datenquellen → z. B. Kürzel „robo",
  http://rechner:8091. 932 Tests grün.
- ✅ VantageMonitor als vierte Quelle (27.09.2026 nachts, doc/20 §4c):
  Vantage-Copy-Trading über dasselbe REST-Protokoll, Versions-Kürzel
  „vantage" (Port 8092, Autostart, data/rest_api.json, Instanz-Kennung).
  Trades dort deal-genau, bereits positionell — direkte mql5-Konvertierung,
  Server liefert Basis-Symbole (XAUUSD statt XAUUSD.sc). Währung (korrigiert
  28.09.2026): USD-Konten liefern trades.csv direkt, USC-Konten (US-Cent)
  werden serverseitig ÷100 nach USD normalisiert, Konten in Drittwährung
  (EUR, GBP …) antworten ehrlich 404 + Grund (Zulu-Muster — die Forensik
  rechnet USD; currencyCode im Katalog zeigt die Währung). Kopierer-
  Historie: kopierer.db mit Tages-Snapshots je „Signale laden" → /history
  liefert den Verlauf, Katalog trägt weekChange/monthChange (7/30-Tage-
  Zuwachs). Average3MonthProfit = GEMESSENE 30-Tage-Rendite (keine
  Herleitung). Grenzen: kein Initial Deposit und keine Provider-Balance
  (AumUsd ist Kopierer-Kapital), Kommission im Netto-PnL, kein SL.
  Scanner-seitig wie Pelican nur Plattform-Durchreichung + Akzeptanz-
  Regressionstest. Anbindung: Kürzel z. B. „vant", http://rechner:8092.
- ✅ ZuluMonitor als fünfte Quelle (27.09.2026 nachts, doc/20 §4d):
  ZuluTrade über dasselbe REST-Protokoll, Versions-Kürzel „zulu" (Port 8093,
  Autostart, data/rest_api.json, Instanz-Kennung). Trades positionell
  (nur verifizierte Downloads mit .meta-Marker), Paar-Symbole ohne
  Schrägstrich (EURUSD), Netto-PnL. Grenzen: trades.csv nur USD-Konten
  (149/200 Trader; PnL in Trader-Kontowährung), KEINE Abonnenten-Historie
  (history ehrlich leer — 7/30-Tage-Bilanz bleibt leer), kein Initial
  Deposit/Balance, Demo-Trader mit demo:true im Katalog, kein SL,
  Average3MonthProfit hergeleitet (ROI/Laufzeit). Anbindung: Kürzel z. B.
  „zulu", http://rechner:8093. 934 Tests grün.
- ✅ Megaprojekt-Gesamtdoku (27.09.2026 nachts): `doc/21_megaprojekt-
  architektur.md` — die komplette Kette (5 Quellen :8089–:8093 → Hub
  SignalKiScanner → MqlTradeMonitor per Einmal-Sync v1 / MqlRealmonitor per
  REST :8611) mit Diagramm, Protokoll, Ports, Testabdeckung je Projekt und
  Ausbaustufen; Workspace-Einstieg `SIGNALDOWNLOADER/README.md`. Alle fünf
  REST-Schnittstellen integriert UND getestet (je Quelle ein Scanner-
  Akzeptanztest Ende-zu-Ende).
- ✅ Equity-DD-Rekonstruktion aus Kursdaten (28.09.2026, Nutzer-Wunsch):
  Der Broker-„By Equity"-DD ist eine Selbstauskunft — der Scanner misst ihn
  nach (forensics/equity_rekonstruktion.py): Equity-Kurve auf H1-Raster mit
  realisiertem UND floating PnL (Bar-Closes je Symbol, FX über EZB-Kurse);
  Auto-GMT per Preisabgleich der Trade-Open/Closes gegen die High-Low-Spanne
  (±14 h, ≥60 % Treffer, Tie-Break klein |Shift|). Kursdaten über
  kursdaten.py (MetaTrader5-Paket, NUR LESEND, Terminal-Politik wie
  Markt-Beobachter: portabler Selbststart nur mit markt_start_erlauben,
  Beenden nach dem Lauf — GUI-Scan und autonomer Scan rufen
  kursdaten_beenden()). Fließt NUR bei Abdeckung ≥95 % als viertes Maximum
  in die Drawdown-Schranke ein (Risiko vor Ertrag); Urteil nennt
  „Reko-EQ-DD … (aus Kursen, GMT ±N h)", Forensik-Snapshot + LLM-JSON
  führen ihn mit; alle drei Prompts (Risiko/Gesamt/Portfolio) und der
  Kriterien-Text deuten ihn gezielt (Reko > gemeldet = Kernbefund
  „Drawdown schöner gemeldet als er war"), scoring.evaluate nimmt ihn
  als viertes Maximum in die Schranke (reko_eq_dd_pct). Ohne Terminal still aus (kein Malus). Setting
  equity_rekonstruktion (an). 964 Tests grün (+8
  tests/test_equity_rekonstruktion.py, synthetische Bars — kein MT5 nötig).
- ✅ Fix-IDs — definierte Signal-IDs immer scannen (28.09.2026,
  Nutzer-Wunsch nach der Lücke, dass KiraCat seit 08.09. aus den Top-
  Listen gefallen war): Setting `fix_signal_ids` (app_settings.json,
  Default leer). Wirkt an vier Stellen: (1) Pipeline `crawl()` lädt
  fehlende Fix-IDs einzeln von der Signalseite (Plattform über data-mt/
  Titel — die entscheidet den MT4/MT5-Export-Pfad; im Modus quellen nur
  Protokoll, dort nicht einzeln ladbar); (2) `build_candidates()` umgeht
  für Fix-IDs die Wochen-/Abonnenten-Vorfilter; (3) Export-Auswahl
  (`top_n_export`) nimmt Fix-Kandidaten vorne (scan.py UND scan_launcher
  .py — GUI und autonome Scans gleich); (4) Teilscan-Scope = 🟢/🟡 PLUS
  Fix-IDs (`fix_signale.teilscan_ziel_ids`). GUI: Checkmark „📌 Fix —
  immer scannen" in der Detailansicht (Widget-Key enthält den Zustand —
  kein veralteter Klick), Verwaltung mit Entfernen-Buttons + ID-Eingabe
  auf der Ergebnisseite (Abschnitt „Fix-IDs · immer scannen", auch ohne
  Ergebnisse erreichbar), Tabelle/CSV markieren 📌 FIX, Scan-Seite nennt
  gesetzte IDs. Bewusst NICHT geändert: Ampel/Score/Urteil gelten für
  Fix-IDs exakt wie für alle anderen (kein Vorzugsurteil); der Betreuer
  bleibt bei 🟢/🟡 (Dossier-Beobachtung ist kein Scan). Live validiert am
  Beispiel KiraCat #2342895 (MT5, 43 Wochen sauber geparst). 948 Tests
  grün (+14 in tests/test_fix_signale.py, inkl. AppTest Ende-zu-Ende:
  ID eingeben → setzen → 📌 FIX in der Tabelle).
- ✅ Intensiv-Review-Fixes B1–B16 (30.09.2026, Review
  `../waste/intensivreview_2026-09-29/review.md` (Archiv), Umsetzung nach
  Nutzer-Freigabe): **B1 [kritisch]** Monitor-EQ-DD
  (`monitor_trade_eq_dd_pct`, floating-inclusive Zweitmessung des
  Quellen-Monitors) ist FÜNFTES Maximum in der Drawdown-Schranke
  (scoring.dd_maximum an allen 3 Stellen: evaluate, dimension_inputs,
  refresh_report_verdict) und in der Ampel-Zelle dd_schranke — 🟢 bei
  Zweitmessung >30 % ist unmöglich (Ziellauf-Fälle Lemonal 46,65 %,
  AccurateCopier 241,3 % wären 🔴); >100 % tragen einen Basis-Vorbehalt-
  Hinweis. **B2** `ertrag_monat_pct_forensik` (netto/startkapital/Monate
  aus eigener Kurve auf der DD-Basis) wird berechnet, persistiert und ist
  MAASSGEBLICH für Ertrags-Kriterium + Grün-Weg (Plattformwert nur noch
  Zusatzinfo; SafeGold-Fall: 0,5 statt 6,46 %/M). **B3** implizite
  Kapitalbasis (Web-Balance − Σ Trade-Netto, `_implizite_kapitalbasis`,
  `KAPITALBASIS_QUELLE_IMPLIZIT`) greift VOR der virtuellen 10k-Annahme;
  Urteil nennt „Kapitalbasis implizit". **B4** Betreuer prüft nur noch
  MQL5 (`mql5_kandidaten`), Quellen-🟢/🟡 werden im Tageslauf als Skip
  protokolliert (bis doc/20 Stufe 3). **B6** Parser kennt Datensatztyp
  `Correction` (Kontobewegung); abgeschnittene LETZTE Zeilen bleiben
  bewusst LAUTE FEHLER mit neuem Diagnose-Hinweis „Download vermutlich
  unvollständig" (Cache-Poisoning-Abwehr schlägt Skip-Toleranz);
  GER40→DE40-Alias in contract_specs; ingest mappt metrics `Broker`
  (häufigster ServerCode, PelicanTrading cd9612f) auf broker_server →
  cross_broker=false-Specs (USOIL) entscheiden wieder korrekt. **B7**
  ⛔ (Ausschlussliste) belegt keine Forensik-Slots/KEIN LLM mehr
  (via Fix-ID pinbar); **B8** fix_signal_ids=[2342895, 2375480]
  gesetzt. **B9** Downloader-Abgleich bricht nur noch ab, wenn KEINE
  Quelle antwortet (404-only zählt als erreicht) + Warnung bei
  Setting-/Datenquellen-URL-Divergenz. **B10** Kursdaten fallen bei
  Broker-Suffix-Symbolen (AUDCADR, XAUUSD.F, EURUSD+, *-ECN) auf das
  normalisierte Basis-Symbol zurück (`suffix_annahmen` protokolliert) —
  Equity-Reko wirkt damit für ca. 22/28 statt 14/28 MQL5-Signale.
  **B11** Forensik-JSON nennt Einheiten explizit (shock_pct_peak_account
  = USD; Alias-Feld `_usd`; LLM-Misslesen-Befund). **B12** eingebaute
  Prompt-Defaults sind identisch mit den Dateien (Sync-Test verhindert
  Drift). **B13** Tiefenanalyse-Vorlage nennt die Kuratierung ehrlich.
  **B14** CLI-Einzelrollen nehmen den Rollen-Lock (wie Daemon/GUI).
  **B15** Platzhalter-Meldung „Titel/Text" aus Produktiv-DB gelöscht.
  **B16** alle 5 Workflow-Prompts markieren Anbieter-Strings als
  FREMDTEXT (Injektions-Guard) + Einheitenzeile + Abonnenten≠Qualität +
  Historie≠Prognose. **R1** ID-Kollisionsschutz: upsert_signal
  überschreibt eine dokumentierte Quelle nicht mehr stillschweigend.
  **R2** REST liefert `forensikUpdatedAt` + `stale` je Signal.
  **B5** PelicanMonitor liefert weeks=null statt 0 (Stats nie geladen);
  Scanner-Vorfilter behandelt unbekanntes Mindestalter als nicht belegt.
  Tests: +27 in tests/test_intensivreview_fixes.py.
  **Live-Verifikation 30.09. abends** (PelicanMonitor neu gestartet,
  `../waste/intensivreview_2026-09-29/lauf_verifikation_b1_b3.py` (Archiv),
  isoliert ohne DB-Schreiben/KI): Lemonal 🔴 (46,65 % Schranke),
  AccurateCopier 🔴 (241,3 %), Lexo/PentagonForex/Mr_Profit 🟡 (Ertrag
  1,86/1,12/3,33 statt 15,4/6,68/63,8 %/M), alle mit impliziter Basis.
- ✅ Portfolio-Statistik als Code-Befund B20/B21 (30.09.2026 nachts,
  Intensiv-Review-Nachtrag der Parallel-KI): Neues Modul
  `portfolio_statistik.py` liefert dem Portfolio-Prompt Maschinen-Fakten
  statt nur Rendite-Korrelation: (1) **Verlustmonat-Cluster** (Monate mit
  ≥2 gleichzeitigen Verlierern unter den 🟢/🟡 — der schlechteste
  beobachtbare Monat ist das Stress-Szenario und MUSS im Bericht mit
  Namen/Werten stehen), (2) **Historie-Tiefe je Signal + gemeinsames
  Beobachtungsfenster** (<24 Monate = schwach belegte Diversifikation,
  explizit zu nennen), (3) **Instrument-Overlap** (Paare mit ≥3 gemeinsamen
  Symbolen und Jaccard ≥0,3 = Klumpenrisiko selbst bei r≈0). Monatsrenditen
  auf der virtuellen Forensik-Kurve (tatsächlich verwendete Kapitalbasis).
  Template portfolio.md + Default synchron (B12-Test wacht darüber),
  run_portfolio loggt Cluster-/Klumpen-Zahl. Live-Abnahme am Bestand:
  Juli-2026-Cluster (n=5) und Gesamtfenster von nur 2 Monaten erscheinen
  im Prompt; Master H4-1×H4-2 entfällt als Paar, weil H4-1 seit B1
  korrekt 🔴 ist (Monitor-TDD 66,5 %). +10 Tests in
  tests/test_portfolio_statistik.py.

- ✅ Fremd-Review 01.10. (Archiv ../waste/codereview_2026-10-01/): Alle 4 P1
  und alle P2 behoben. **F1** Equity-Reko führt USD- und PROZENT-Maximum
  getrennt (1000→600→2000→1500 meldet jetzt 40 % statt 25 % — der Wert
  in der Schranke war unterschätzt). **F2** Punkte ohne vollständiges
  Floating sind keine Messpunkte mehr (fehlender Kurs erfand DD; finale
  Schlussverluste bleiben messbar). **F5** Abdeckungs-Nenner zählt volle
  aktive Stunden laut Trade-Zeiten abzüglich echter Marktpausen (globale
  Bar-Lücken ≥20 h); Datenlöcher drücken die Abdeckung ehrlich.
  **F3** ID-Kollision verwirft jetzt den GANZEN Schreibversuch (Raise)
  statt nur das Quellenlabel zu erhalten. **F4** Login-Abbruch/leerer
  Scope = status „skipped" — Tages-/Monatsmerker werden NICHT gesetzt;
  Erfolgsmeldung nennt „X von Y geprüft, N endgültig fehlgeschlagen".
  **F6** MQL5-Login nur noch bei MQL5-Direkt-Kandidaten im Scope (reine
  Quellenläufe laufen ohne). **F7** Plattform-Dedup normalisiert
  MT5/mt5 (MQL5-Direkt gewinnt jetzt auch beim Spiegel-Doppel).
  **F8** length-Retry akkumuliert verworfene Tokens in meta_out statt
  sie zu ersetzen (+ Feld verworfene_retry_tokens). **F9** STATUS_DATEI
  lazy; neue Tests auf kanonischen Import umgestellt (kein Doppelmodul
  mehr, das Analyse 1116 in die Produktiv-DB schrieb). **K1** Forensik-
  Payload nennt forensik_vollstaendig, IMMER die Kapitalbasis (auch
  CSV), Status optionaler Messungen (null = nicht verfügbar, OPTIONAL)
  und die Ertrags-Definition (linearer Ø seit Start). **K2/K3**
  Prompt-Regeln: Widerspruchs-Pflicht (WATCHLIST nur mit benannten
  Bedingungen empfehlbar), SL-Kurzurteil-Verbot („0/x SL" ist nie ein
  Grund; Abverkauf niemals wegen Wegfall des NACHWEISES) + Nutzer-
  Präambel 01.10. (SL intern, nicht voraussetzbar; Abschätzung nur über
  Verhaltensanalyse wie wiederholte DD-Auslöschungen). Cache/neu-Log
  korrigiert (hole_trades liefert geändert); Journal-Läufe 95/97
  nachträglich als abgebrochen markiert. +4 Tests
  test_equity_rekonstruktion_fremdreview.py, +1 K1-Test.

- ✅ RetDD — Rendite-Risiko-EFFIZIENZ als durchgängiges Kriterium
  (Nutzer-Wunsch 01.10.2026: „niedriges Risiko allein bringt es nicht"):
  `retdd_monat` = Forensik-Ertrag ÷ DD-Maximum (gleiche Kapitalbasis;
  ×12 annualisiert, Calmar-artig) — berechnet je Signal, im Kandidaten-
  UND Forensik-Payload (mit Definition und Deutungsschwellen: ≥ 0,5
  effizient, 0,167 = exakte Projektmaße 5 %/M bei 30 % DD, darunter
  unattraktiv), als 9. Ampel-Matrix-Zelle „RetDD (Ertrag je DD)"
  (grün ≥ 0,5 · gelb 0,167–0,5 · orange darunter · ⚪ ohne Basis —
  allein keine harte Sperre, aber Grün ohne Punkt hier ist ein
  unattraktives Grün), im Grün-Urteilstext, im Portfolio-Prompt mit
  bindender Priorisierungsregel (Effizienz über absolute Rendite;
  retdd_monat < 0,2 nicht empfehlbar) und in der Portfolio-Statistik
  je Signal. Risiko-Score (7 Dimensionen) bleibt bewusst reines
  Risiko-Instrument („Risiko vor Ertrag") — die Effizienz wirkt über
  Ampel-Zelle, Urteil und KI-Deutung. **Zinseszins-Korrektur (Nutzer-
  Frage 01.10., Fachrecherche Calmar/CAGR):** RetDD nutzt das
  GEOMETRISCHE Monatsmittel der Monatsrenditen (wachsender Kontostand
  als Nenner — netto ÷ fixe Startbasis ÷ Monate überhöht bei Konto-
  wachstum massiv, z. B. Combo Profile 91,8 %/M fix vs 27,7 %/M geom;
  arithmetischer Ø ignoriert volatility drag — Investopedia/CFA) und
  retdd_jahr ist der ECHTE Calmar (Jahres-CAGR ÷ DD, statt ×12).
  Neue Felder ertrag_monat_geom_pct + cagr_jahr_pct in beiden Payloads;
  linearer Startbasis-Wert bleibt als ertrag_monat_pct_forensik mit
  Definition dokumentiert. Bestands-Ranking (geom., 🟢/🟡): ImpulseNet
  5,15 · Gold Spike MT5 1,44 · Combo Profile 1,43 · S7PRO 1,09 ·
  MicroJump 1,07 · Pure Gold 1,04 … Gold Spike MT4 0,77.
  - 🚨 **BEFUND B24 (02.10.2026, Lauf-Prüfung) — RetDD ist TOter Code.**
    Der vorige Eintrag beschreibt die *Verdrahtung* (Ampel-Zelle, Payloads,
    Prompts, Sync) korrekt — aber **die Werte werden nirgends berechnet**.
    `pipeline.py:157-163` deklariert `retdd_monat`/`retdd_jahr`/
    `ertrag_monat_geom_pct`/`cagr_jahr_pct`, **keine Zuweisung existiert**
    (Suche über alle `src/`: der einzige Treffer ist ein Kommentar). Live
    geprüft: **0 von 97 Signalen** haben einen Wert; die Ampel-Zelle `retdd`
    ist immer ⚪; kein einziges Urteil enthält den RetDD-Text; die Prompts
    verlangen trotzdem die Nennung eines Wertes, der immer `null` ist.
    Das obige Bestands-Ranking stammt aus einer **manuellen Nachrechnung**,
    nicht aus dem laufenden System. Reihenfolge: Berechnung in `pipeline.py`
    nach `:1231` (`dd_maximum` aus `scoring.py:62` zwingend verwenden) →
    Mitlesen in `results_from_db():296-360` → Tests auf Pipeline-Ebene.
    Details: `../waste/intensivreview_2026-09-29/review.md` §A B24 (Archiv).
  - 🚨 **BEFUND B25 (02.10.2026) — doppelte Trade-Zeilen verzerren die
    Forensik.** 38 von 97 Signalen enthalten exakte Duplikate (Spitze The
    Holy Grail: 4.197 überzählige Zeilen von 15.340 = 27,4 %). Nachgerechnet:
    Drawdown **9,46 % → 12,12 %** (zu niedrig), Verlustserie **120 → 50**
    (2,4× zu hoch). Der Parser arbeitet **1:1** zur Datei (15340 = 15340,
    SHA stimmt) — die Duplikate kommen aus dem gelieferten Snapshot, nicht aus
    dem Cache. **Konsequenz:** Drawdown-Schancen betroffener Signale können
    erst nach Dedup + Re-Scan als gesichert gelten.
  - B26 (02.10.2026, MITTEL): `winrate_pct` und `trading_dd` gehen ohne `n`
    bzw. ohne Bezugsgröße in die KI-Nutzlast — „95,5 % Trefferquote" und
    „0,1 % DD" sind so nicht prüfbar.
  - ✅ **B24+B25+B26 BEHOBEN (02.10.2026, gleicher Tag).** B24: Produzent
    `portfolio_statistik.effizienz_kennzahlen()` berechnet je Signal
    ertrag_monat_geom_pct/cagr_jahr_pct/retdd_monat/retdd_jahr auf der
    Forensik-Kurve (DD über scoring.dd_maximum), verdrahtet in
    analyze_candidate, persistiert in stats_json UND forensik-JSON,
    results_from_db liest sie zurück. **Nutzer-Regel 02.10.: RetDD ≥ 1,0
    ist Mindestqualität** — Grün-Weg in ampel_for hart gesperrt (retdd < 1,0
    ODER unbelegt → 🟡 mit Begründung), Ampel-Zelle grün ab 1,0/gelb ab
    0,5/orange, Portfolio-/Risiko-/Gesamtbericht-Prompts nennen 1,0 als
    Empfehlungsminimum (statt 0,2). B25: parser.load_export entfernt exakte
    Zeilen-Duplikate VOR dem Parsen (THG: 4.197 entfernt), Zähler
    `duplikate_entfernt` in stats + Forensik-JSON + Log-Meldung. B26:
    `trades_anzahl` + `duplikate_entfernt` im Forensik-Payload. Bestand
    braucht einen Re-Scan, damit DB-Werte + Dedubel-Forensik wirksam werden.

- ✅ Equity-DD-Studie — interaktive Nachmessung je Signal (03.10.2026,
  Nutzer-Wunsch): Spalte „Equity-DD" mit Button JE ZEILE der Ergebnis-
  tabelle (ButtonColumn wie Bericht/Abonnenten) und Button in der
  Detailansicht öffnen einen Dialog; eigene Seite app_pages/equity_studie.py
  zeigt dieselbe Ansicht in voller Breite. Messung in `equity_studie.py`
  (NEU, bewusst SEPARAT von forensics/equity_rekonstruktion — Produktiv-
  pfad unangetastet): Equity-Kurve je Stunde als MITGEGEBENE Punkte
  (realisiert / offener Betrag floating / equity; Lückenpunkte statt stiller
  Zeitsprünge), GMT-Abgleich JE WÄHRUNGSPAAR (Nutzer-Wunsch) mit Median-
  Fallback für dünne/mehrdeutige Symbole (MIN_EIGENE_PROBEN=5, offengelegt
  je Symbol), fehlende Kurse = kein Abbruch: gerechnet wird für vorhandene
  Paare, JE fehlendes Symbol namentlich gemeldet (DD kann unterschätzt
  sein). Chart: Plotly (requirements ergänzt) mit Zoom/Rangeslider/
  Zeichenwerkzeugen, Equity+Realisiert+Floating-Linien, Startkapital-Linie,
  DD-Region, Unterwasser-Subplot; Kennzahlen-Karten (Reko-EQ-DD %/USD,
  Floating-Tief, Unterwasser-Tage, Abdeckung), Risiko-Bausteine als Code-
  Text (kein LLM, bewertet nichts — Engine bleibt verbindlich), Symbol-
  Tabelle mit GMT/Trefferquote/Status. Progress-Balken im Fenster (Terminal-
  Start + Kurse je Symbol), Sitzungs-Cache je (Signal-ID, Trade-SHA);
  Terminal-Lifecycle pro Öffnung wie Pipeline-Politik; Sperrung während
  eines laufenden Scans. Trades aus trade_files-Snapshot der DB (results_
  from_db.trades_path); Kapitalbasis über drawdown.run wie Forensik.
  Live-Verifikation: TKG #2054437 (pelik, 2.158 Trades, XAUUSD) — 21 s,
  GMT +3 h (87 % Treffer), Abdeckung 98,1 %, Reko-EQ-DD 2,97 %.
  NUTZER-VALIDIERUNG 03.10. (Akzeptanz): Gold Spike MT5 #2375480 —
  Studie 9,2 % vs. Plattform „Maximum drawdown" 9,1 % (Differenz 0,1 pp
  vom Nutzer ausdrücklich als ok eingestuft; erwartbar: H1-Bar-Closes
  statt Tick-Tiefs, Referenz-Feed Tickmill statt RoboForex-Eigenfeed).
  +11 Tests (tests/test_equity_studie.py, inkl. AppTest Ende-zu-Ende der
  Seite — fing ungültiges Material-Icon).

- ✅ DD-BENENNUNG „Max-Drawdown“ vs „Drawdown (Plattform)“ (03.10.2026,
  Nutzer-Wunsch nach GS-MT5-Validierung): Der selbst berechnete Wert heißt
  jetzt Max-Drawdown, die Plattform-Selbstauskunft Drawdown. Umgestellt in
  to_row (Spalten „Max-Drawdown %“ / „Drawdown % (Plattform)“ /
  „Balance-DD % (Plattform)“; CSV folgt), Ergebnistabelle (Spalte
  „Studie“ statt „Equity-DD“-Button), Detailansicht, Ampel-Matrix
  (Schranken-Herleitung nennt „Drawdown (Plattform) / Balance-DD
  (Plattform) / Max-Drawdown (Trades) / Max-DD (Kurse) / Max-DD
  (Monitor)“), Urteilstexte („Max-DD aus Kursen …“), Kriterien-Text,
  Regelwerk, Hilfe-Texte und Scan-Stationstabelle. KI-Prompts bewusst
  UNVERÄNDERT (Fachbegriffe mit Definition für das LLM; B12-Sync).
  MT4/MT5-UNTERSCHIED GS (Analyse 03.10., .tmp/vergleich_gs_mt4_mt5.py):
  Im MT5-DD-Fenster (16.07.–03.08.2026) verlieren beide Konten FAST
  IDENTISCH −138 USD netto (Algo identisch) — aber MT4s Kurvenstand war
  ~6.050 USD (Basis 3.116 + 1 Jahr Gewinne, Auszahlungen laufen NICHT in
  die Trading-Kurve), MT5 nur ~1.515 USD → 2,3 % vs 9,1 %. MT4s
  Allzeit-Maximum 4,57 % stammt aus DEZ 2025 (157 USD auf kleinem Konto);
  Lots sind auf beiden ~0,01 fix (keine Kontogrößen-Skalierung) —
  %-DD ∝ 1/Kontogröße. Webseite „Maximum drawdown 8,1 %“ = By-Balance
  (reale Balance MIT Auszahlungen 3.640 USD → kleineres echtes Konto →
  fast doppelter %-Wert), die DD-Graphik zeigt By-Equity (3,8 %) —
  beide Plattform-Selbstauskünfte, unser Max-Drawdown misst eigenständig.

- ✅ Reale Drei-Signal-DD-Prüfung und Zeitbasis-/Parser-Korrektur
  (03.10.2026, `doc/22_drawdown-kalibrierung.md`): Gold Spike MT4 #2349227,
  Meridian MT5 #2385675 und Night Scalper MT5 #2379236 mit echten H1-Kursen
  und je einem M1-Spitzentag geprüft. Öffentliche MQL-Grafik rechnet
  Floating-Verlust / zeitgleiche Balance; ihre Rohkurven-Maxima ergeben
  exakt die drei By-Equity-Werte. Listen-/Radar-Maximum nimmt den höheren
  Balance-/Equity-Wert. Nähe zu unserem Equity-Peak-DD beweist daher keine
  gleiche Methodik; die frühere Gold-Spike-Nähe 9,2/9,1 % ist allein kein
  vollständiger Validierungsnachweis. M1-Nachrechnung gleicher Floating-
  Definition: Gold 3,60/3,80 %, Meridian 9,74/10,45 %, Night 7,01/6,84 %
  (zeitlich passender Snapshot; aktuelle 17,26 % entstehen erst nach CSV).
  Global-GMT-Fehler korrigiert: lokaler Preisabgleich je Zeitabschnitt,
  Open/Close separat, unklare Wechsel-/FX-Tage verhindern Gesamtfreigabe.
  Kalendergrenzen sind Modellannahmen, kein exakter DST-Beleg. Relative
  Referenzkurszeit ist kein alleiniger öffentlicher UTC-Beweis.
  **B25 revidiert:** Ohne Ticket-ID darf auch massenhafte Zeilengleichheit
  nicht als Doppellieferung behandelt werden. Night: alle 299 Rohtrades
  (182 BUY/117 SELL wie MQL) erhalten, zuvor wurden 17 mit 141,32 Netto
  entfernt. `identische_tradezeilen` als Hinweis in Stats/DB/KI/Detail;
  `duplikate_entfernt` nur Legacy-Auditfeld. Forensik-Version **10** und
  neuer Studien-Cache erzwingen Neuberechnung. Unvollständige Gold-/
  Meridian-Messungen liefern keinen RetDD; vollständiges Night-H1-Modell
  über die gesamte CSV misst 35,81 % (vor Monitoringbeginn).
  Tradeserver: ungerundete gemessene EQ-DD, eigene geometrische Gewinn-
  %/Monat, RetDD, Basis und konfigurierte Grenzen werden übertragen;
  MqlTradeMonitor zeigt diese Werte, unbekannte/alte Ratios bleiben leer.
  Review-Rohbelege außerhalb Git in `../waste/drawdown_3signale_2026-10-03/`.
  Anbieterbroker nun aus Provider-DOM statt Slippage-Liste: Gold
  RoboForex-ECN, Meridian FusionMarkets-Live, Night Bybit-Live-6; generische
  Faktoren dieser drei Kurven unverändert. 1.301 Standardtests im vollen
  Abschlusslauf plus fünf neue Brokerfälle mit 50 bestehenden gezielten
  Tests grün; vier echte GLM-Regressionen und 60 Monitor-Tests grün.

- ✅ BEWEISBASIERTES TRADE-DEDUP (03.10.2026, Nutzer-Freigabe nach meinem
  Parallel-KI-Review): Identische CSV-Zeilen werden NUR noch entfernt, wenn
  die PLATTFORM die Doppellieferung belegt — Signalseiten-Angabe
  „Trades:" (signal_stats, Feld stats['trades']) == Rohzeilen − Mehrfach-
  vorkommen. Deckt die Plattform alle Rohzeilen (Night-Scalper-Konstellation:
  299 = 299 → Zwillinge echt) oder irgendeine andere Zahl, bleibt alles
  erhalten; der Zähler identische_tradezeilen meldet weiterhin. Damit sind
  BEIDE reale Fälle richtig behandelt: THG-Massen-Doppellieferung (27,4 %)
  wird mit Beweis bereinigt, echte Zwillings-Grid-Legs (auch einzeln!)
  überleben — der Beweis entscheidet, nicht die Masse (Umkehrung der alten
  B25-Heuristik). Durchreichung: engine.analyze(plattform_positions=...) →
  parser.load_export; Pipeline analyze_candidate setzt
  res.plattform_trades = stats.get('trades') (Quellen ohne Positionszahl
  → None = kein Beweis, ehrlich); persistiert in stats_json
  (plattform_trades, duplikate_entfernt) und results_from_db zurück; Studie
  (berechne) nutzt denselben Beweiswert; Forensik-JSON
  trade_datenqualitaet nennt Behandlung + Beweiszahl. Log unterscheidet
  „bewiesen entfernt (Plattform-Anzahl belegt…)" von „erhalten (keine
  Ticket-ID…)". FORENSICS_VERSION **11**. +8 Tests
  tests/test_beweis_dedup.py (THG-/Night-Scalper-Konstellation, Einzel-
  zwilling mit/ohne Beweis, keine/nicht-ganzzahlige/falsche Beweiszahl,
  Engine-Durchreichung).

- ✅ ZEITBASIS-AUSREISSER-FIX (03.10. abends, Nutzer-Auftrag „GS MT5
  66 % Abdeckung genau untersuchen — Samstag?"): Diagnose
  (.tmp/diagnose_gs_mt5_abdeckung.py) entlastete das Wochenende VOLLSTÄNDIG
  (Bars bis Fr 23:00 UTC vorhanden, aktive Stunden 146/152 = 96,1 % mit
  Bars; Wochenenden sauber als Marktpausen erkannt). Echte Ursache: Die
  100-%-Wochenregel der Parallel-KI („ein einziger widersprechender Endpunkt
  macht die Woche unbelegt") warf die GESAMTE Kalenderwoche 28.09.–03.10.
  raus, weil EIN 4-Sekunden-Scalp (Mo 03:31, Entry ~8 USD über der Bar =
  Nacht-Spread) die 0,1-%-Toleranz verfehlte — mit der Woche fielen 46 der
  152 aktiven Stunden (Grid-Positionen laufen tagelang): Abdeckung 96 →
  66 %, Messung verworfen, RetDD weg, GS MT5/MT4 🟢→🟡. Um 10:59 war die
  Woche noch < 10 Proben (Cache ohne Fr-Trades) → strenge Wochenprüfung
  griff gar nicht (mehr Daten = strengere Prüfung = Verwurf). FIX:
  (1) Starke Woche (≥ 10 Proben) bleibt ab 90 % Trefferquote BELEGT —
  einzelne Nichttreffer markieren nur ihren EIGENEN Trade unsicher, dessen
  Stunden werden Lücken und die 95-%-Abdeckungsregel entscheidet.
  (2) Ausreißer-Skala _PREIS_AUSREISSER_FAKTOR=10: knapp außerhalb
  (≤ 10× Toleranz, realer GS-Fall ~1,5×) = Spread/Slippage → Lücke;
  Größenordnungen daneben (999999-Fall) = Zeitachse hart unzuverlässig.
  Massenhafte Nichttreffer (< 90 %) machen die Woche weiterhin unbelegt.
  Live verifiziert: GS MT5 wieder status=ok, verlaesslich=True, Abdeckung
  96,1 % (W40 belegt bei 92,9 % Quote, nur der Scalp unsicher mit 0 h).
  +2 Regressionstests (knappe Ausreißer in starker Woche; weit draußen
  hart). Beim nächsten Scan kommt der Kurs-DD zurück in Schranke/RetDD —
  GS MT5 kann wieder 🟢 werden.

- ✅ GMT-REGEL VEREINFACHT (03.10. abends, Nutzer-Entscheidung „3 Proben
  reichen — GMT wechselt nur 2×/Jahr" + „nicht ermittelbar = LETZTEN
  BEKANNTEN nehmen, das reicht"): (1) GMT_LOKAL_MIN_PROBEN 10 → 3 und
  MIN_EIGENE_PROBEN (Studie/Symbol) 5 → 3 — Proben zählen jetzt als
  PREISEREIGNISSE (Open+Close dedupliziert, konsistent zur Reko; die
  Studie zählte versehentlich Trades). Schutz bleibt: bester Shift muss
  EINDEUTIG sein (Plateau = mehrdeutig) UND Quote ≥ 90 % (bei 3 Proben:
  alle 3). Nutzen: DST-Wechselwochen (oft nur wenige Proben) werden
  jetzt lokal belegt statt verworfen. (2) Wochen, die ihren Versatz
  NICHT selbst belegen können (dünn/mehrdeutig/abweichend), ERBEN den
  letzten bekannten Versatz (previous; Startwoche: global) statt die
  Messung zu verwerfen — Status „geerbt_letzter_bekannter" nur noch
  informativ. Echte DST-Wechsel werden erkannt, sobald eine Folgewoche
  sie selbst belegt (ab 3 Proben); bis dahin laufen die betroffenen
  Preise als Ereignis-Lücken (nicht schöngerechnet). Hart bleiben:
  kein überhaupt belegbarer Versatz, nicht-monotone Abbildung, offene
  Position über eine STARK-belegte Wechselgrenze, Preise um
  Größenordnungen daneben (999999). Tests angepasst (Verwurfs- auf
  Erbe-Semantik) + neue 3-Proben-/DST-/Vererbungs-Tests. GS MT5
  verifiziert: Woche W40 lokal belegt (92,9 %), Abdeckung 96,1 %, ok.

- ✅ FEHLENDE KURSDATEN SICHTBAR MACHEN (03.10. abends, Nutzer-Wunsch
  „sollte im Bericht erscheinen, damit ich weiß, wo ich dran arbeiten
  kann"): (1) Forensik-JSON der KI hat strukturiertes Feld
  fehlende_kursdaten (ohne_kurse/ohne_kontrakt + Folge + Handlung);
  ScanResult-Felder equity_rekon_ohne_kurse/-ohne_kontrakt (aus dem
  Forensik-Snapshot, kein DB-Schema-Change). (2) Prompt-PFLICHT in
  Risiko-Analyse UND Gesamtbericht: bei vorhandenem Feld Symbole
  namentlich nennen mit Folge und Handlungsweg (Datei + Default synchron,
  B12-Test grün). (3) Portfolio-PDF-Anhang: Zeile „Fehlende Kursdaten"
  in der Kennzahlen-Tabelle. (4) Ergebnisseite: aggregierte
  ARBEITSLISTE über alle Live-Signale (Symbol → Grund → betroffene
  Signale; auch der Fall „Forensik komplett am Kontrakt gescheitert"
  wird aus dem Fehler-Feld geparst — z. B. DE30M/XCUUSDM von #2368681).
  +5 Tests tests/test_fehlende_kursdaten.py; volle Suite 1324 grün.

- ✅ STUDIE: KAPIALFLUSS-BRÜCKE + KOPIER-SIMULATION (04.10., Nutzer-Dialog
  ATong „Website schwankt 1-10 %, eure Kurve 1-2 %"): Beweis aus den
  Balance-Zeilen — ATong hat 42 Einzahlungen (+33.552) / 39 Auszahlungen
  (−42.174 USD); das ECHTE MQL5-Konto ist klein, die virtuelle Trading-
  Kurve akkumuliert alles (12.100 USD) → gleiche USD-Schwankungen sind
  auf der Website prozentual größer. KEINE Kurve ist falsch. Anzeige:
  (1) Karte „Konto-DD (kapitalflussneutral)" (ATong ≈ 38,1 %) +
  Hinweis-Box bei Flows nach Handelsstart („direkt vergleichbar sind die
  USD-Werte"); (2) Max-Drawdown-Karte nennt jetzt den Rückfall-Zeitraum
  (ATongs 64,9 % = Aug/Sep 2021 — Verwechslungsquelle beseitigt);
  (3) EIGENER BLOCK „Kopier-Simulation — was wäre mit deinem Konto
  passiert?": kapitalflussneutrale Rendite auf konstante 10.000 USD
  (Karte Max-DD beim Kopieren [prozentual startbetrag-unabhängig, da
  proportionale Lot-Skalierung wie MQL5-Copy], Rückfall USD, simulierter
  Kontostand heute, eigene Kurve; Annahmen: kein Fixed-Lot, ohne
  Kopiergebühren/Slippage/Spread-Differenzen, H1-Schlusskurse).
  Commits 564e38c/8daa9f0/afbcfd9; volle Suite 1325 grün.

- ✅ SCORE-GATE ENTFERNT (04.10., Nutzer-Freigabe nach Pelikan-Analyse
  „warum sind alle gelb?"): Der Grün-Weg (Ertrag ≥ 5 %/M geom. + RetDD
  ≥ 1,0) hing versteckt hinter `score < 5,0` — mit den zwei Score-Default-
  Dimensionen (Broker offshore 5,0, Transparenz 5,0) für Quellen-Signale
  fast unerreichbar. Realer Fall HRC Algo (pelik): DD 2,0 % · Ertrag
  10,1 %/M · RetDD ~5,0 — blieb Gelb „Score 5,8 (kein Kandidat)".
  Nutzer-Entscheidung: Gate raus. Grün entscheiden jetzt ausschließlich
  die harten Regeln (Schranke, Martingale, Ausschlussliste) plus Ertrag
  und RetDD; der Risiko-Score bleibt Ampel-Matrix-Zelle und heißt im
  Grün-Urteil („… RetDD 5.0/M, Risiko-Score 5.8 …"). Pelikan-Bilanz
  danach (live nachgerechnet): 2 Grün-Kandidaten (HRC Algo, ImpulseNet —
  ImpulseNet mit Mini-Konto-Vorbehalt aus der KI-Analyse), 8× Gelb wegen
  Ertrag < 5 %/M, 2× RetDD < 1, 16× 🔴 v. a. Martingale-Nachweis.
  +2 Tests; volle Suite 1327 grün. Bestand braucht erneuten Scan, damit
  die Ampeln der Kandidaten auf Grün springen.

- ✅ GESAMT-WORKSPACE-REVIEW (04.10. nachts, Nutzer-Auftrag „alle Phasen
  ohne Stop, Fehler beheben, PDF-Endreport"; Bericht + Pakete A–I:
  `doc/reviews/codereview_2026-10-04/`, PDF `report.pdf`): Alle 7 Projekte
  geprüft (8 Pakete parallel + Gegenprüfung I + 22/22 Rechenorakel
  M01–M27). **WICHTIGSTE BEFUNDE + BEHOBEN:**
  (1) **Monitor-DD ist eine Closing-Kurve** — BEWEIS aus PelicanTrading
  EquityKurve.java/ReportService.tradeDdAusTrades (Kurve nur aus
  geschlossenen PnLs + GENAU EINEM heutigen Floating-Endpunkt; Robo ohne
  jedes historische Floating, Yield-Fenster-Basis; Vantage/Zulu Closing-DD
  auf rückgerechneter Basis). KONSEQUENZ UMGESETZT: `monitor_trade_eq_dd_pct`
  bleibt 5. Kanal der harten Schranke (B1 unverändert, konservativ), ist
  aber KEIN RetDD-Nenner und keine „Max-Drawdown"-Messquelle mehr
  (pipeline._equity_messwerte/max_drawdown_equity_pct). Der Skip der
  Kurs-Reko bei vorhandenem Monitor-Wert (29.09., „keine Doppelarbeit")
  ist ENTFERNT — er beruhte auf der widerlegten Annahme, der Monitor messe
  dieselbe Equity wie die H1-Reko. Quellen-Signale bekommen damit wieder
  Kurs-Rekonstruktion; OHNE belastbare Kurs-Messung bleibt RetDD unbekannt
  → kein Grün (HRC Algo/ImpulseNet kippen evtl. auf 🟡, bis ein Re-Scan mit
  Terminal die Kurs-Messung liefert — regelkonform: „valide H1-/Monitor-
  Messung", niemals Closing/Balance/Plattform als Nenner).
  (2) **Dedup-Beweis überall**: portfolio_statistik (monatsrenditen/
  effizienz_kennzahlen/statistik), llm_runner (beide load_export) und
  _implizite_kapitalbasis reichen plattform_positions durch — vorher
  rechneten RetDD/Portfolio/KI-Payload auf ROHEM Bestand, während die
  Forensik deduped rechnete (THG-Fall: 27 % Duplikate).
  (3) **Robo trades.csv-Vertragsbruch**: Profit-Spalte enthielt NETTO
  zusätzlich zu echten Commission/Swap-Spalten → Scanner (net =
  profit+commission+swap) zog Gebühren DOPPELT ab (real: −24.709 statt
  −9.337 USD). Robo schreibt jetzt BRUTTO; Bestands-Re-Scan nötig (SHA
  ändert sich erst nach Robo-Neustart/Neulieferung).
  (4) **MqlDownloader-Löschfilter**: MPDD-/ExtraktionsFEHLER löschen keine
  Originaldaten mehr (NaN-Sentinel statt 0.0-wie-schlecht; 7 delete-
  Aufrufe aus DataExtractor-Fehlerpfaden entfernt) — Zeitbombe bei
  DOM-Änderungen entschärft (C2b). C2a (Monats-Extraktion matcht DOM
  nicht mehr, >50 % Signale Ertrag 0) bleibt OFFEN — braucht Live-Seite.
  (5) **Autonomer Full-Scan**: restauriert basis-aktuelle KI-Berichte wie
  die GUI (vorher 3 LLM-Calls je Signal, bis ~200k Token/Lauf; nur
  modus=full, Teilscan bleibt „alle Stufen neu") + Scheduler-Versuchs-
  deckel (3 autonome Startversuche je Modus/Tag gegen Endlos-Retry bei
  Dauerfehler, F4/B8-Semantik erhalten).
  (6) Kleinere Fixes: Zulu LLM-Systemtext (war LEER, Injektionsfläche;
  Robo-Muster), Vantage 10402-Gebündelthinweis + TradesTotalAvailable/
  Truncated in metrics (2000er-Kappung sichtbar), PelicanTrading trade_dd
  null→Cache-Verwurf + „Berechnet"-Spalte, startall.bat/Scanner-start.bat
  identitätsgeprüfte Prozessbeendigung (fremde Ports/Streamlit-Prozesse
  werden NICHT mehr gekillt) + MqlDownloader-Start + REST-Ketten-
  Bereitschaft je Port, Scan-Seite Portfolio-Anhang-Key (results→
  scan_results), Lock-ts-robust, _platform_float Mischformate
  („1.403,03"/„1,403.03") + NaN/Infinity→Default (Orakel M27), Score-
  Gate-Resttexte entfernt, ertrag_monat_pct_forensik 365,2425/12.
  (7) OFFEN (mit Lösungsweg im Report): C2a-DOM-Regex, Robo F6a (Yield-
  Fenster ÷ Lebensalter) + F1b (Teil-Outs erst zum letzten OUT in der
  Equity-Kurve), PWL E2a (running-Job-Endlosschleife — aktive Parallel-
  Entwicklung, nur Report), B6a (PDF-Materialisierung je DB-Lesung),
  H2a (REST-Bind 0.0.0.0 + Token-Default leer auf allen 5 Monitoren —
  Nutzer-Entscheidung nötig, Heim-LAN-Aufstellung bewusst).
  **startall.bat REALTEST OK (04.10. 17:08):** Alle 7 Clients starten
  (Scanner-App + MqlDownloader :8089 + 4 JavaFX-Monitore + JETZT AUCH
  PelicanWinnerLooser); Bereitschaftsschleife 3 min (MqlDownloader
  kompiliert vor dem Start — 2 min waren zu knapp und zeigten „FEHLT");
  Port-Status je Endpunkt am Schluss. Ein parallel laufender CLI-Scan
  bleibt von startall unberuehrt (killt nur Port-Besitzer der Suite).
  **H2a ENTSCHIEDEN (Nutzer 04.10. abends): KEINE REST-Security** —
  alles läuft nur lokal; 0.0.0.0-Bind + leere Token-Defaults bleiben
  bewusst so (kein Handlungsbedarf, Punkt geschlossen).
  **Parallel-Arbeit übernommen** (README ×6 + doc/21 committet; =2076
  gelöscht) und doc/21 auf Review-Stand nachgezogen (RetDD 1,0/0,5,
  H1-Produktivpfad, Monitor=Closing-DD-Untergrenze).
  **REGELÄNDERUNG (Nutzer 04.10. nachts): ABSOLUTE ERTRAGSHÜRDE ENTFERNT**
  — min_ertrag_pct_monat Default 5.0 → 0.0 (= aus; produktives Setting
  ebenfalls 0; Admin-Feld bleibt zum Wieder-Einschalten). Begründung des
  Nutzers: Beim Kopieren ist der Lot-Faktor frei wählbar (1,4 %/M ×
  Faktor 10 = 14 %/M, Drawdown skaliert mit, RetDD bleibt gleich) —
  absolute %/Monat sind damit eine WAHLGRÖSSE, keine Qualitätseigenschaft.
  Grün entscheiden jetzt NUR: harte Regeln (Schranke 30 % Maximum inkl.
  Monitor-Kanal, Martingale, Ausschlussliste) plus **RetDD ≥ 1,0 mit
  BELASTBARER Kursmessung** (Nenner = Max-Drawdown der Equity INKL.
  Floating/offener Equity — niemals Closing-/Trading-DD; gilt für ALLE
  Quellen/Broker). Messbarer positiver Ertrag bleibt über RetDD ≥ 1,0
  implizit gefordert. Bestands-Effekt beim nächsten Scan: Signale mit
  RetDD ≥ 1 und altem Ertrag-🟡 können grün werden; Signale ohne
  Kursmessung (RetDD unbekannt) bleiben 🟡.
  **REGELÄNDERUNG 2 (Nutzer 04.10. nachts): KURS-TEILMESSUNG statt Abweisung**
  — Fehlen Kurse/Kontrakt für EINZELNE Symbole komplett, wirft das Signal
  nicht mehr aus der Max-Drawdown-Bewertung: gemessen wird auf den
  BETRACHTBAREN Symbolen (status „ok_teilmessung", verlaesslich als
  RetDD-Nenner freigegeben), die fehlenden Paare werden namentlich als
  Warnung geführt (Log, Urteil „Max-DD Teilmessung (ohne X, Y — DD kann
  unterschätzt sein)", forensik-JSON-Feld teilmessung/symbole_nicht_
  betrachtet/abdeckung_betrachtete_pct). Hart bleiben: FX-Lücke, Daten-
  löcher in VORHANDENEN Symbolen (Teil-Abdeckung < 95 %) und unzuverlässige
  Zeitbasis → weiter „unvollständig", kein Nenner. Tests: Teil-Messung,
  Mehrfach-Symbol-Fall, Datenloch-Grenze.
  **Kursüberdeckung visualisiert (Nutzer-Wunsch 05.10. nachts):** Equity-
  Studie hat neuen Expander „Kursüberdeckung je Symbol — wo fehlen Bars?"
  mit Plotly-Zeitstrahl: grün = verfügbare H1-Bars-Segmente, orange =
  einzelne Wartungsstunden (≤3 h, nächtliche Feed-Wartung Tickmill), rot =
  fehlende Abschnitte (>3 h, z. B. Terminal-Bars-Limit); Hover nennt Lage
  (anfang/mitte/ende) und Dauer; Kennzahlen-Karten (Abdeckung aktiv,
  Wartungsstunden, Anzahl Abschnitte). Datenfunktion
  equity_studie.ueberdeckung_je_symbol (reine Rechnung, im Studien-
  Ergebnisfeld „ueberdeckung"); Wochenende/Feithertage zählen nicht als
  Lücke. Kurs-Lücken-Diagnose (05.10.): Lücken liegen praktisch alle in
  der MITTE als Einzel-Wartungsstunden 01–05 Uhr + einige Symbole ohne
  Ende-Abschnitt (THG GBPJPY/USDJPY, GTS BTCUSD — Max-Bars-Limit; Nutzer
  stellt Terminal auf Unlimited). Alte Studien-Cache-Einträge brauchen
  „Neu berechnen" für das neue Feld.
  **MT5-Historien-Nachladen behoben (05.10. nachts):** kursdaten.hole_h1
  fragte copy_rates_range GENAU EINMAL ab — MT5 liefert beim ersten Abruf
  oft nur die lokale Historie und stößt den Server-Download an (Beweis:
  GBPJPY endete mitten im Fenster, zweiter Abruf lieferte alles; Max Bars
  war Unlimited, also nicht das Limit). Teilergebnisse vergifteten den
  Lauf-Cache → die „Abdeckung <95 %"-Fälle (THG GBPJPY/USDJPY-Ende, GTS
  BTCUSD). Fix: Retry bis zu 3× (2 s Pause), solange das Ergebnis WÄCHST
  und das Fenster (±3 Tage Wochenend-Toleranz) nicht erreicht ist;
  Stillstand → Best-Effort-Teilergebnis. +3 Tests
  (test_kursdaten_nachladen.py: teil→voll, Stillstand, fertig ohne Retry).
  **ZWEITE KURSDATENQUELLE (Nutzer-Wunsch 05.10. nachts):** Multi-Terminal-
  Support — `kursdaten_terminals` (Liste, Priorität in Reihenfolge): erst
  Tickmill, dann ActiveTrades003 (C:\Forex\Mt5\ActiveTrades003 — hat auch
  Aktien!). MT5-Python ist pro Prozess ein Singleton: erst ALLE Symbole von
  Quelle 1 laden, dann Terminal wechseln und NUR die fehlenden Symbole
  erneut versuchen. `KursDaten.hat_weiteren_terminal()/wechsle_terminal()`;
  None-Cache-Einträge werden beim Wechsel gelöscht. GMT pro Feed korrekt
  (Auto-GMT-Preisabgleich je Symbol — die Kurse eines Symbols kommen
  konsistent aus EINEM Feed, kein Mischbestand). Admin-UI hat neuen
  Abschnitt „Kursdatenquellen (MetaTrader)" mit Liste + Hilfe-Topic.
  Fallback eingebaut in equity_rekonstruktion.py + equity_studie.py.
  Suite nach Fixes: Scanner 1341 Tests grün (+10 neue), mvn: robo 129,
  zulu 81, MqlDownloader 82, PelicanTrading 63, vantage 25. Bestand
  braucht Re-Scan (Dedup-Konsistenz + Robo-Brutto + RetDD-Basis).
- ✅ NACHTRAG „ZENTRAL + EHRLICH" (04.10. abends, Nutzer-Entscheidung zur
  DD-Frage): Die floating-inklusive Open-DD-Messung bleibt ZENTRAL im
  Scanner (Kurs-Reko, läuft für alle Signale); TradeEqDrawdownPct wird
  NICHT entfernt (Untergrenzen-Kanal hat reale Rot-Fälle gerettet:
  Lemonal 46,65 %, AccurateCopier 241,3 %), sondern überall ehrlich als
  CLOSING-DD benannt. Robo-Reparaturen: F1b — Closing-DD-Kurve aus
  ROH-Deals (EquityKurve.punkteAusDeals/tradeDdAusDeals; Teil-OUTs zählen
  zu ihrem Zeitpunkt, vorher erst zum letzten OUT); F6a —
  SignalAccount.yieldPeriodMonths (persistiert, CSV-Spalte 18):
  Monatsrendite = Fenster-Yield ÷ Fensterlänge (vorher ÷ Lebensalter),
  DD-Basis aus dem Yield DESSELBEN Fensters mit fensterbegrenzter Kurve;
  metrics ehrlich: YieldWindowPct/YieldWindowMonths (statt
  „YieldInceptionPct") + TradeClosedDdPct-Alias. UI-Korrektur „Max-EQ-DD"
  → „Closing-DD" in Robo (7)/Pelican (8)/Vantage (6) + Scanner-Texte
  (Ampel-Matrix „Closing-DD (Monitor)", Log „Trade-Closing-DD",
  Scoring-Kommentar). Robo 133 Tests grün (+4 ClosingDdDealsTest),
  Scanner 1341, Pelican 63, Vantage 25. Report-Kapitel 8 im PDF.

  Noch offen (Betrieb — Agentenbetrieb Phasen A–E sind KOMPLETT):

- [x] Re-Scan als Kommandozeilenaufruf — erledigt über Phase E:
      `--scan gelbgruen|full` (plus `--once`, `--markt`, `--betreuer`,
      `--digest`, `--chef`, `--alles` = komplette Tageskette)
- [x] Automatisierte Alerts (Ampelwechsel, Stilbruch, Scan-Abschluss) —
      Melder/Postfach, Phase D/E
- [x] V1-Attach-Prüfung mit Nutzer — ERLEDIGT 22.09.2026 (Selbststart UND
      Attach E2E verifiziert, Ergebnis in doc/19 §7.4 nachgetragen)
- [x] Autostart des Daemon nach Rechner-Neustart — ERLEDIGT 04.10.2026:
      `start_agenten_daemon.bat` (Scanner-Root) + Startup-Verknüpfung
      „MqlKiScanner Agenten-Daemon" im persönlichen Startup-Ordner (minimiert;
      PYTHONPATH=src, .venv-pythonw bevorzugt). Der Daemon respektiert
      agenten_enabled — ausgeschaltet heißt: er idlet ohne Rollen/Scans.
- [ ] Multi-Source-Hub Stufe 2–4 (doc/20 §7): Initial Deposit im
      MqlDownloader-/metrics + MT4-S/L-Verifikation am Downloader-Bestand,
      dann Composite-Identität (quelle, signal_id), Betreuer auf Quellen
      umstellen, Crawler entfernen (listen_modus=quellen als Standard),
      Quell-Typen für weitere Signal-Börsen
- [ ] Erster voller autonomer Monat (Bestätigung der Phase-E-Abnahme
      „Monat ohne Scan-Klick" nach Oktober 2026)
