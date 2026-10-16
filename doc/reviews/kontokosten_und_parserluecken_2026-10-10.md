# Parser- und Buchungslücken: Nachprüfung 10.10.2026

Ausgangspunkt sind alle 21 Parserfehler und 162 übersprungenen Tickmill-Zeilen der gespeicherten Matrix. CSVs und lokale Quellen-Caches wurden ausschließlich gelesen; keine Produktionsdatenbankänderung und kein MT5-Aufruf in dieser Nachprüfung. Alte Matrixbefunde bleiben im JSON erhalten, die Code-Nachmessung ist separat dokumentiert.

Separate `Charge`- und `Commission`-Zeilen sind echte zusätzliche Kosten, keine externen Kapitalflüsse ([MQL5-Dokumentation](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties)). Das Modell enthält sie nun als eigene Buchungsereignisse. Netto, Monatsrendite, Kontokurve, beide H1-Rechenwege, Kapitalflussdiagnostik, Exposure-Saldo und LLM-Zahlen enthalten diese Beträge; Tradeanzahl, Winrate und Trade-PF behalten ihre Handelsdefinition. Vorhandene Positionskommissionen werden nicht nochmals zugeordnet. Identische Gebührenzeilen bleiben erhalten; positive Erstattungen behalten ihr Vorzeichen.

Kosten vor dem ersten Open mindern den Startsaldo einmal. Kosten außerhalb des Trade-Zeitfensters sperren die geometrische Rendite mit Begründung; die vollständigen Geldbeträge bleiben sichtbar. Zusätzliche Kostenpunkte benötigen keinen Kurs, wenn das Konto dort keine offene Position hat. Bei fehlendem Floating bleibt Equity unbekannt. Die 95-%-Schranke wurde nicht verändert.

545 nachgewiesene MT4-Zeilen sind ausschließlich neutrale Hedge-Verwaltungsereignisse: exakt `close hedge by #<Zahl>`, Nullvolumen, jeder Geldbetrag null, gleicher positiver Ein-/Ausstandspreis, valide nichtnegative Zeitspanne und korrektes 13-Spalten-Format. Andere Nullvolumen bleiben Fehler. Der eigene Zähler unterscheidet diese Metazeilen von echten Trades.

| ID | Signal | Befund | Zustand nach Codefix |
|---|---|---|---|
| 1719023 | GenX Multistrategies | 2 neutrale MT4-Hedge-Metazeilen | Strikter Parser liest alle echten Trades; Metazeilen separat gezählt |
| 1887334 | Niguru GBP | 542 neutrale MT4-Hedge-Metazeilen | Strikter Parser liest alle echten Trades; Metazeilen separat gezählt |
| 2275715 | MAHIGAN | 46 separate Kostenbuchungen | Strikter Parser und alle Ergebnisconsumer unterstützt; echte Kosten belasten Netto |
| 2336904 | EA RDIP HPro 5P | Fünf archivierte Monatsaggregate ohne Ein-/Ausstandspreise | Quellblocker bleibt; weder löschen noch als einzelne Trades erfinden |
| 2350766 | Ten Percent | 21 separate Kostenbuchungen | Strikter Parser und alle Ergebnisconsumer unterstützt; echte Kosten belasten Netto |
| 2379670 | EURUSD Algo Trading | 1 neutrale MT4-Hedge-Metazeilen | Strikter Parser liest alle echten Trades; Metazeilen separat gezählt |
| 304366 | Signal Guide | Alter Export enthält ungeklärte Nullvolumenzeile | Alter Snapshot bleibt strikt ungültig; neuer verifizierter Export separat belegt, Nachimport durch Root |
| 419789 | Hit profits EA | 11 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 425666 | Zix Power | 5 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 426987 | Money Pile | 6 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 428131 | Millionaire MT5 | 4 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 428298 | yonanatme | 73 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 428586 | RetireNow | 1 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 429044 | DayTrading sys 1.0 | 1 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 429555 | FulcrumMM | 1 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 430016 | TpTrading | 1 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 430074 | SSP_Safe_Steady_Profit | 1 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 430472 | xau scalp | 5 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 430909 | Smart Capital Growth | 59 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 430936 | Triple Grid Sentinel | 5 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |
| 431040 | FIREX Pro | 133 negative Trade-Zeitintervalle | PF/Win/Trades/Netto als gekennzeichnete Teilstatistik; Rendite/DD weiter gesperrt |

Die 162 Skips verteilen sich auf 159 verifizierte Pelican-Caches mit null gespeicherten geschlossenen Trades, zwei fehlende positive Kapitalbasen und einen weiteren leeren Vantage-Export. Bei 143 der 159 Pelican-Caches widersprechen positive aggregierte historische Trade-/Win-/Loss-Zahlen einer vollständigen Nullhistorie. Bei weiteren 16 fehlt auch dieser Gegenbeleg; echte Nullaktivität ist dadurch dennoch nicht bewiesen. Das ist ein Quellen-/Downloadproblem, kein Anlass, Trades zu erfinden.

Die echte Kostenprobe enthält MAHIGAN: 46 Buchungen −42,09 USD, 1.906 Trades, Gesamtnetto 886,45 USD; Ten Percent: 21 Buchungen −2,10 USD, 165 Trades, Gesamtnetto 321,76 USD. Alle 67 Kosten liegen innerhalb ihrer Tradefenster. Ihre echten CSV-Startbasen von 300 bzw. 100 USD gewinnen vor einer virtuellen Annahme. Details: [Nachmessung](kontokosten_und_hedge_meta_2026-10-10.json).

Forensik-Version 16 erzwingt die fachliche Neuprüfung alter Engineberichte. Anzeige-Caches wurden ebenfalls angehoben. Eine SHA-exakte unabhängige reale H1-Studie bleibt in „Alle Signale“ über eigene Anzeigefelder sichtbar, auch wenn der Workflowbericht veraltet ist; ihre Anzeigeeffizienz verwendet aktuelle CSV-Renditen und die unveränderte Mindesthistorie. Ampel, Score und Engine-Stale-Schutz bleiben dabei gesperrt. Parser-/Leerdatenfehler stehen jetzt generell im Messstatus.

Validiert: 195 gezielte Engine-/Consumer-Regressionen grün; vorher 126 weitere/überlappende Parser-, Statistik-, H1-, Portfolio- und UI-Fälle grün. Die einzelnen Läufe werden nicht zu einer Gesamtsumme addiert. Nachfolgende Abschlussprüfungen und Live-Neumessungen erfolgen getrennt durch Root.
