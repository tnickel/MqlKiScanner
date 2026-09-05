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
   Parser in `scripts/reference/` behandeln beides.
6. **Scraping behutsam:** Rate-Limit einbauen (wenige Requests/Minute,
   Pausen zwischen Signalen) — automatisiertes Abrufen kann gegen MQL5-ToS
   verstoßen (Accountsperren-Risiko). Login-Daten nie in Code/Repo (env vars).

## Design-Regeln (aus der Reihe gelernt — Ursachen in doc/01)

1. **Code rechnet ALLE Zahlen; das LLM bekommt nur fertige Befunde als JSON**
   und formuliert/liefert Interpretation. LLM rechnet nie selbst
   (Halluzinationsrisiko bei Arithmetik).
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
- `src/mqlkiscanner/` — Zielarchitektur des Tools (aufzubauen, siehe `doc/04_roadmap.md`)

## Offene Entscheidungen (mit Nutzer klären)

- [ ] Stack: Python + Streamlit (Empfehlung) oder Java + JavaFX
- [ ] LLM-Anbieter + API-Key (2-Stufen: Flash + starkes Modell)
- [ ] LLM-Layer erst nach funktionierendem Kern (Engine läuft ohne Key)
