# Technik: MQL5-Datenquellen, Formate, Fallstricke

Dokumentiert aus der forensischen Analyse-Reihe (Sept. 2026). Alles hier wurde
in der Praxis gegen echte Signale getestet.

## 1. Endpunkte

| Zweck | URL | Auth |
|---|---|---|
| Signalliste MT5 | `https://www.mql5.com/en/signals/mt5` (+ `/page2`, `/page3` …) | nein |
| Signalliste MT4 | `https://www.mql5.com/en/signals/mt4` (+ Seiten) | nein |
| Zuverlässigkeits-Liste | `https://www.mql5.com/en/signals/mt5/trusted` | nein |
| Signal-Details | `https://www.mql5.com/en/signals/{ID}` | nein (mehr Daten mit Login) |
| **Trade-Export MT5** | `https://www.mql5.com/en/signals/{ID}/export/positions` | **ja (Cookie)** |
| **Trade-Export MT4** | `https://www.mql5.com/en/signals/{ID}/export/history` | **ja (Cookie)** |
| Reviews | `https://www.mql5.com/en/signals/{ID}/reviews` | nein |
| Anbieter | `https://www.mql5.com/en/users/{username}` | nein |
| Login | `https://www.mql5.com/en/auth_login` | — |

Wichtig: `/export/positions` liefert auf **MT4-Signalen HTTP 404** (`[NotFound]`).
MT4 nutzt `/export/history` (Orderbuch mit S/L, T/P, Comment). MT5 nutzt
`/export/positions` (ohne SL/TP). Bei unbekannter Plattform beide Pfade versuchen.

## 2. Login-Session

1. `GET /en/auth_login` → Formular (Felder: "Your login", Passwort-Feld
   "Enter the password please", Button "Log in")
2. POST der Credentials → Redirect auf `/en` = eingeloggt; Session-Cookie merken
3. Export-Aufruf mit Cookie (`credentials: include` bzw. Cookie-Header)
4. **Erfolgs-Check:** Antwort beginnt mit `Time;` (CSV-Header).
   Beginnt sie mit `<!DOCTYPE` und enthält "Log in" → Session weg, neu einloggen.
   (Dieser Fehler ist in der Reihe einmal passiert und kostete eine Analyse.)

## 3. Export-Formate — zwei Varianten

### 3a. Positions-Export (MT5-Signale, `/export/positions`)

```
Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit
2026.08.28 17:05:15;Sell;0.01;XAUUSD;4566.52;0.01;2026.08.28 17:08:10;4566.17;-0.18;;0.35
```

- 11 Spalten (Indizes 0–10): Open-Zeit, Buy/Sell/Balance, Lot, Symbol,
  Einstiegspreis, Schluss-Lot, **Schluss-Zeit (Idx 6)**, **Schlusspreis (Idx 7)**,
  Commission (8), Swap (9), **Profit (10)**
- `Type=Balance`-Zeilen: Kontobewegungen (Einzahlung/Auszahlung), Betrag in Spalte 10
- **Enthält KEINE S/L- und T/P-Spalten** — Stop-Nachweis hierüber nicht möglich
- **Fallstricke:** Zahlen mit Tausendertrennzeichen-Leerzeichen ("1 403.03",
  "4 566.52") → Leerzeichen vor float() entfernen; manche Zeilen kürzer als
  11 Felder → Zeilenlänge prüfen; ohne Login kommt HTML statt CSV
- **Artefakt Zeitstempel-Zeile (belegt: Signal #2271995, Zeilen 222/391):**
  vereinzelt Zeilen mit NUR Open-Zeit, alle anderen Felder leer
  (`2026.07.06 00:22:05;;;;;;;;;;`). Kein Typ/Volumen/Symbol/Geldwert —
  Parser überspringt sie; Inhalt ohne Typ bleibt ein Fehler (Geldwerte
  dürfen nie still verschwinden). Tests:
  `tests/test_parser_export_artefakte.py`

### 3b. MT4-Orderbuch ("history"-Export, Beispiel: Gold Spike MT4)

```
Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment
2026.08.28 17:05:15;Sell;0.01;XAUUSD;4566.52;4565.99;4541.59;2026.08.28 17:08:10;4566.17;-0.18;;0.35;[sl]
```

- 13 Spalten (Indizes 0–12): Open-Zeit, Typ, Lot, Symbol, Open-Preis,
  **S/L (Idx 5)**, **T/P (Idx 6)**, Close-Zeit (7), Close-Preis (8),
  Commission (9), Swap (10), Profit (11), **Kommentar (12)**
- Typen: `Buy`/`Sell` (gefüllt), `Buy Stop`/`Sell Stop` (Pending),
  `Balance` (Kontobewegung)
- Kommentar: `[sl]` = Stop-Auslösung, `[tp]` = Take-Profit, leer = manuell/EA-Close,
  `cancelled` = stornierte Pending-Order
- **Artefakt Summenzeile (belegt: Signal #840474/#1496203/#1760039):** letzte
  Datenzeile vor den Balance-Zeilen ist der Export-Footer — Typ Buy/Sell,
  Symbol wörtlich `profit`, KEINE Preise, Commission/Profit-Spalten enthalten
  die Gesamtsummen (z. B. `...;Buy;0.10;profit;;;;<close>;;;-130.60;3 613.41;`).
  Würde sie als Trade gelten, verfälschte die Summe jede Statistik — Parser
  überspringt sie erkannt (Erkennung an LEERE Preise gebunden, damit echte
  Daten nie als Footer verschwinden). Tests:
  `tests/test_parser_export_artefakte.py`
- **Dieses Format ist der Goldstandard für Stop-Nachweise** (Beispiel:
  `data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv`). Abrufbar über
  `/export/history` (Cookie nötig); `/export/positions` gibt auf MT4 404.

## 4. Kennzahlen-Extraktion von der Signalseite

Werte stehen als Label/Wert-Paare im Seiten-Text (`innerText`, Label-Zeile
gefolgt von Wert-Zeile oder Inline `Label:\tWert`):

Growth:, Profit:, Equity:, Balance:, Initial Deposit, Withdrawals:, Deposits:,
Trading Days, Latest trade:, Trades per week:, Avg holding time:, Subscribers:,
Weeks:, Started:, Trades:, Profit Trades:, Loss Trades:, Best trade:,
Worst trade:, Gross Profit:, Gross Loss:, Maximum consecutive wins:,
Maximum consecutive losses:, Maximal consecutive profit:, Maximal consecutive
loss:, Sharpe Ratio:, Trading activity:, Max deposit load:, Recovery Factor:,
Long Trades:, Short Trades:, Profit Factor:, Expected Payoff:, Average Profit:,
Average Loss:, Monthly growth:, Annual Forecast:, Algo trading:,
Drawdown-Sektion: "Absolute:", "Maximal:", "By Balance:", "By Equity:"

Hebel (z. B. "1:500") steht als eigenständiges Element. Broker-Server oben im
Kopfbereich (Muster `Servername-LiveNN`).

**Achtung:** "By Equity:" = schwimmender DD, "By Balance:" = realisierter DD.
Beide getrennt ausweisen — Grid-Systeme haben niedrigen Equity-DD in guten
Phasen und brechen dann sprunghaft.

## 5. Kontraktgrößen (für Exposure-Rechnung)

| Symbol | 1 Lot | P&L je 1 USD/EUR Preisbewegung |
|---|---|---|
| XAUUSD | 100 oz | **100 USD** |
| US30/Indizes | 1 Contract | 1 USD je Indexpunkt |
| FX-Paare (NZDCAD etc.) | 100.000 Einheiten | ~10 USD je "Pip" (4. Dezimale), ~100 USD je 1 Cent |

**Gold-Beispiel (der teure Lernpunkt der Reihe):** 2,66 Lots netto short
× 100 USD × 50 USD Gegenbewegung = **-13.300 USD** — auf einem 10–30k-Konto
40–130 % Kontoverlust. Peak-Exposure immer in Dollar-Rechnung angeben,
nicht nur als Positionsanzahl.

### 5a. Kontraktspec-Datei (`data/contract_specs.json`)

Instrumente ohne Klassenkonvention (Krypto, Silber, Öl, EUR-Gold, Indizes
wie DE40/USTEC/CHINA50) werden über eine editierbare Spec-Datei belegt:
`contract_size` je Lot, `quote_currency`, `stress_move`, `aliases`
(Broker-Schreibweisen), `source` + `retrieved` (Nachweispflicht). Werte
Stand 09/2026 von Tickmill-Instrumentenseiten. Besonderheit
`cross_broker=false`: Kontrakt ist brokerabhängig (Öl: Tickmill 1 Barrel,
viele andere 100 — Faktor 100!) und gilt nur bei Broker-Match auf den
`broker_server` des Signals. Engine-Anbindung: `symbols.spec_for()`,
`forensics/exposure._resolve_symbol()`.

### 5b. Fremdwährungs-Umrechnung (EZB-Referenzkurse)

Signale mit nicht-USD-Quote (FX-Kreuze, XAUEUR, DE40) brauchen für den
USD-Schock eine belegte historische Umrechnung. Quelle:
`eurofxref-hist.zip` der EZB (täglich seit 1999, EUR-Basis; die Datei
beginnt mit dem NEUESTEN Tag). Lokal gecacht unter `data/fx_rates/`
(gitignored, 30-Tage-Refresh, Download still bei Offline — Befund meldet
das). Konventionen: Kurs zum Handelstag, Wochenende/Feiertag = zuletzt
verkündeter Kurs (max. 10 Tage Rücklauf, sonst unbekannt); Cross-Kurs
`1 CCY = EURUSD ÷ EURCCY` aus Kursen desselben Tags; EUR selbst liest die
USD-Spalte. Jeder Befund führt die verwendeten Kurse mit Datum
(`fx_conversion.kurse_am_flag_peak`). Modul: `src/mqlkiscanner/fx_rates.py`,
Tests: `tests/test_fx_rates.py`.

## 6. Sonstiges

- Ohne Login: letzte ~24 h der Historie verborgen, offene Positionen ohne Volumen
- Monats-Tabellen (Growth % und absoluter Gewinn je Monat) sind der beste
  Validierungsanker: Rekonstruktion aus CSV muss auf den Cent decken
- Reviews liegen unter `/reviews` und enthalten Nutzername, Datum, Text —
  wertvollste Quelle für Copy-Praxisprobleme (Slippage, Mapping, Mindestlot)
- "What's new"-Reiter: Anbieter-Kommunikation (Drawdown-Updates, Regeländerungen)
- Rate-Limit einhalten: ~1 Seite/1–2 s, Pausen zwischen Signalen (ToS-Risiko)
