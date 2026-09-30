

===== SIGNAL 2349227 | Gold Spike | quelle=mql5 =====
--- stats_json (Kandidaten-Fakten) ---
{"eq_dd_pct": 3.8, "bal_dd_pct": 8.11, "ertrag_monat_pct": 24.54, "pf": 3.51, "growth_pct": 300.0, "broker_server": "FusionMarkets-Live 3", "forensik_ok": true, "forensik_version": 7, "initial_deposit_usd": 3116.0, "balance_usd": 2409.55, "kapitalbasis_virtual_usd": null, "monitor_trade_eq_dd_pct": null, "last_fehler": null}
--- forensik json (upd 2026-09-30 00:02:58) ---
{"version": 7, "vollstaendig": true, "trading_dd": {"pct": 4.57, "usd": 157.2}, "winrate_pct": 77.6, "max_verlustserie": 13, "verlustserie_usd": -154.99, "peak_exposure": {"positionen": 11, "netto_lots": 0.12, "schock_usd": 600.0, "shock_pct_max": 30.5058, "shock_pct_peak_time": "2026-08-19 16:12:32", "shock_pct_peak_account": 1966.84, "shock_pct_peak_usd": 600.0}, "martingale_flag": false, "martingale_evidenz": [], "stop_nachweis": "Orderbuch: 392/392 mit SL", "stop_evidence": "direct", "symbole": "XAUUSD", "kapitalbasis": {"usd": 3116.0, "quelle": "csv_einzahlungen", "end_balance_real": 2353.83, "webseite_balance_usd": 2409.55}, "equity_rekonstruktion": {"test": "equity_rekonstruktion", "status": "ok", "gmt_offset_h": 0, "gmt_trefferquote": 0.958, "equity_dd_pct": 5.69, "equity_dd_usd": 239.52, "abdeckung_pct": 100.0, "rasterpunkte": 5297, "verlaesslich": true, "symbole_mit_kursen": ["XAUUSD"]}, "fx_kursquelle": null, "score": 4.1, "kriterien_matrix": {"grenzen": {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}, "kriterien": {"dd_schranke": {"ampel": "🟢", "kurz": "Puffer 21,89 Punkte", "detail": "max(EQ-DD 3,80 %, Bal-DD 8,11 %, Trading-DD 4,57 %, Reko-EQ-DD 5,69 %) = 8,11 % hält die Schranke 30 % mit 21,9 Punkten Abstand ein."}, "martingale": {"ampel": "🟢", "kurz": "keine Signatur", "detail": "Keine Lot-Eskalation nach Verlusten und kein Korb-Muster erkannt (Median-Faktor-Schwelle 1,3x nicht überschritten)."}, "stop": {"ampel": "🟢", "kurz": "bewiesen (Orderbuch)", "detail": "Stop direkt belegt: Orderbuch: 392/392 mit SL"}, "ertrag": {"ampel": "🟢", "kurz": "24,5 %/Monat", "detail": "24,5 %/Monat ≥ Mindestschwelle 5 %/Monat."}, "score": {"ampel": "🟢", "kurz": "Score 4,1", "detail": "Engine-Risiko-Score 4,1 von 10 — unter der Kandidaten-Schwelle 5."}, "schock": {"ampel": "🟡", "kurz": "30,5 %", "detail": "50-USD-Schock über Peak-Netto-Lots ≈ 600 USD = 30,5 % des Kontos am 2026-08-19 16:12:32 — erhebliche Stress-Belastung. Stress-Szenario, kein gemessener Verlust; begründet Gewichtung, nicht allein die Ablehnung."}, "serie": {"ampel": "🟡", "kurz": "13 in Folge", "detail": "Längste Verlustserie: 13 Trades, Summe -155 USD — deutliche Regime-Belastung."}, "liste": {"ampel": "🟢", "kurz": "nicht gelistet", "detail": "Signal steht weder auf der Ausschlussliste noch auf der Watchlist (known_signals.json)."}}}, "ampel": "🟢"}

--- ANALYSE trade_analyse (id=784, model=glm-5.3, tokens=9205, at=2026-09-30 00:33:14, basis=3b9db9f093450db8090a853022c5890b0c439cd01d9adb2de0bc29bd4ac7abc9) ---
Der Kern ist ein regelbasiertes Grid-/Layer-Scalping auf XAUUSD mit aufge setztem Trendfang-Bein. Der größte Korb belegt das Muster: vier Buys innerhalb von fünf Minuten (02:00–02:05), Einstiege bei 4568.42/4568.56/4568.95/4570.10 – Abstände von 0.5 bis 1.7 USD –, gemeinsamer Exit um 02:57 mit Netto +2.88. Der erste Handelstag zeigt dieselbe Logik: drei Sells um 16:05 (EPs 3963.91–3964.30, −35.36), danach drei Gegenbewegungen mit +45.23 innerhalb von 24 Minuten. Exit-Profil: Median-Haltedauer 0.22 h für die Scalp-Rotation, während die sechs besten Trades 7.89–72.15 h laufen und per TP weit entfernte Ziele erreichen (Sell 4235.58→4146.43, +177.96). Das System verdient im engen Korridor und gelegentlich am Impuls – der Name „Gold Spike" passt zur Konstruktion.

**Positionsgrößen:** praktisch flach. 386 von 392 Trades (98.5 %) mit 0.01 Lots, nur sechsmal 0.02, darunter der Besttrade am letzten Exporttag (2026-09-28). Kein Martingale: Während der maximalen Verlustserie (13 Trades, 2025-12-05 bis 12-10, Summe −154.99) bleiben alle Legs bei 0.01. Maximales Exposure 4×0.01.

**Zeitverhalten:** Entries konzentrieren sich auf 16–18 Uhr (53/41/38) – New-York-Eröffnung – plus asiatische Session um 03–04 Uhr (35/18). Zehn von elf Monaten positiv, nur Juli 2026 mit −56.77; Spitzenmonat März 2026 (+512.60). Dezember 2025 absorbierte die 13er-Serie und schloss dennoch mit +229.66 – Recovery über Frequenz, nicht über Lotsteigerung.

**Anomalien:** Erstens ist das exit-Feld bei Verlusten inkonsistent: Der Worst-Trade (Buy, EP 4259.0, XP 4218.03, −41.14) trägt „[tp]" – ein TP kann bei einem Buy 40.97 Punkte unter dem Einstand nicht liegen. Dasselbe bei −39.52, −36.88, −32.44, −30.89 und −29.44. Das sind programmatische Not- bzw. Basket-Closes, die als TP geloggt werden; typisch für MT4-Hedging-EAs mit Close-All-Level. Der „Stop bewiesen"-Status gilt also nur eingeschränkt. Zweitens Verlustcluster bei Korridor-Durchbrüchen: drei Sells am 2025-12-09 um 08:04–08:09 bei ~4175–4177, alle simultan um 11:05 bei ~4203 geschlossen (−26.22/−25.66/−27.34). Drittens symmetrisches Profil: avg_win +13.52 vs. avg_loss −13.12 bei 77.6 % Winrate – echtes Frequenz-Edge, kein Lotterieprofil. Wiederholte identische Distanzen (2× 21.76, 2× 2.92 Punkte) deuten auf fixe Level.

**Einordnung:** hoch mechanisch – identische EP-Cluster, simultane Close-Zeitpunkte (3× 11:05, 4× 02:57), stabile Session-Slots, keine Swap-/Rollover-Spuren (max. Haltedauer 72.15 h). EA-Charakter mit minimal-adaptivem Sizing (6× 0.02). Hauptrisiko sind getriggerte Not-Exits bei Ausbrüchen: bis −41 je Leg, −155 je Serie.

--- ANALYSE risiko_analyse (id=785, model=glm-5.3-flash, tokens=4642, at=2026-09-30 00:33:14, basis=3b9db9f093450db8090a853022c5890b0c439cd01d9adb2de0bc29bd4ac7abc9) ---
**Risikoprofil: Gold Spike (ID 2349227)**

**1. Risikobefunde**
Stop-Nachweis direkt aus dem Orderbuch: 392/392 Trades mit SL — entlastend. Kein Martingale-/Grid-Befund (Flag false, keine Evidenz). Exposure: bis zu 11 Parallelpositionen bei netto nur 0.12 Lots; Schockszenario 600 USD entspricht 30.5 % des Peak-Equity (1.967 USD) — reines Stressszenario, kein gemessener Verlust, liegt aber praktisch an der 30-%-Schranke und ist zu gewichten. Größte Verlustserie: 13 Trades, -154.99 USD; der Trading-DD (4.57 % / 157.20 USD) deckt sich nahezu vollständig mit dieser Serie. Winrate 77.6 %; die 13er-Serie deutet auf verhältnismäßig große Einzelverluste hin.

**1a. Equity-Drawdown**
Gemeldet: 3.8 % (Equity) / 8.11 % (Balance); Trading-DD 4.57 %. Rekonstruierter EQ-DD inkl. Floating: 5.69 % — Kernbefund: über dem gemeldeten Equity-DD (5.69 % vs. 3.8 %, Differenz +1.89 Prozentpunkte); der Drawdown wurde schöner gemeldet, als er war. Alle Messwerte klar unter der 30-%-Schranke, keine Verletzung.

**2. Copy-Eignung**
Kleines Basiskonto (Peak ~1.967 USD): Kopisten tragen das Schockszenario proportional voll mit; der XAUUSD-Spike-Stil ist slippageanfällig, alle 11 Positionen müssen beim Kopieren vollständig ankommen.

**Fazit**
Bedingt entlastend: bewiesener Stop und Drawdowns fern der Schranke, doch der rekonstruierte Equity-DD belegt verschönte Berichterstattung, und das Schockszenario erreicht mit 30.5 % die Schrankenmarke.

--- ANALYSE gesamtbericht (id=786, model=glm-5.3, tokens=15595, at=2026-09-30 00:35:26, basis=3b9db9f093450db8090a853022c5890b0c439cd01d9adb2de0bc29bd4ac7abc9) ---
Kurzfassung: Mechanischer XAUUSD-Grid-Scalper mit bewiesenem Stop und flachen Lots; Drawdowns weit unter Schranke, aber rekonstruierter EQ-DD über Meldung und Schockszenario an der Marke — Watchlist.

## Was ist das für ein Trading-Algo?

„Gold Spike" (ID 2349227, MT4, FusionMarkets-Live 3) ist ein nahezu vollständig automatisierter Expert Advisor auf XAUUSD. Der Kern ist regelbasiertes Grid-/Layer-Scalping in einem engen Preiskorridor, ergänzt um ein Trendfang-Bein mit weit entfernten Zielen — der Name passt zur Konstruktion. Belegt durch die Trades: Der größte Korb umfasst vier Buys innerhalb von fünf Minuten (02:00–02:05, Einstiege 4568,42/4568,56/4568,95/4570,10, Abstände 0,5 bis 1,7 USD) mit gemeinsamem Exit um 02:57 (Netto +2,88). Der erste Handelstag zeigt dieselbe Logik: drei Sells um 16:05 (3963,91–3964,30, −35,36), danach drei Gegenbewegungen mit +45,23 binnen 24 Minuten. Die Mechanik ist hochgradig rigide: identische Einstiegs-Cluster, simultane Close-Zeitpunkte (3× 11:05, 4× 02:57), wiederholte fixe Distanzen (2× 21,76 und 2× 2,92 Punkte), stabile Session-Slots, keine Swap-Spuren (maximale Haltedauer 72,15 h). Lediglich das Sizing ist minimal adaptiv (6× 0,02 Lots).

## Wie handelt das System?

**Sizing:** praktisch flach — 386 von 392 Trades (98,5 %) mit 0,01 Lots, sechsmal 0,02, darunter der Besttrade am letzten Exporttag (2026-09-28). Während der maximalen Verlustserie (13 Trades, 2025-12-05 bis 12-10, −154,99 USD) bleiben alle Legs bei 0,01: Recovery über Frequenz, nicht über Lotsteigerung; Dezember 2025 schloss trotz Serie mit +229,66.

**Widerspruch aufgelöst:** Die Trade-Analyse sah maximal 4× 0,01 parallel; die Forensik misst 11 Positionen bei netto 0,12 Lots (Peak 2026-08-19, 16:12:32). Zugunsten der maschinellen Forensik (volle Trade-Kurve): Peak-Exposure sind 11 Positionen.

**Haltezeiten und Sessions:** Median 0,22 h für die Scalp-Rotation; die sechs besten Trades laufen 7,89–72,15 h auf entfernte Ziele (Sell 4235,58 → 4146,43, +177,96). Entries konzentrieren sich auf 16–18 Uhr (53/41/38, New-York-Eröffnung) plus asiatische Session 03–04 Uhr (35/18). Monatsverlauf: 10 von 11 Monaten positiv, nur Juli 2026 mit −56,77, Spitze März 2026 (+512,60).

**Exit-Anomalie:** Der Worst-Trade (Buy 4259,0 → 4218,03, −41,14) ist mit „[tp]" geloggt — für einen Buy unmöglich; dasselbe Muster bei −39,52, −36,88, −32,44, −30,89, −29,44. Das sind programmatische Not-/Basket-Closes (typisch für MT4-Hedging-EAs mit Close-All-Level). Beispiel-Cluster: drei Sells am 2025-12-09 (08:04–08:09, ~4175–4177), simultan um 11:05 bei ~4203 geschlossen (−26,22/−25,66/−27,34). Das Profil ist symmetrisch: Ø-Gewinn +13,52 vs. Ø-Verlust −13,12 bei 77,6 % Winrate — echtes Frequenz-Edge, kein Lotterieprofil. Hauptrisiko der Konstruktion: getriggerte Not-Exits bei Korridor-Durchbrüchen, bis −41 je Leg, −155 je Serie.

## Risikoanalyse

**Drawdown-Dreiklang:** Trading-DD (geschlossene Trades) 4,57 % / 157,20 USD — deckt sich fast exakt mit der 13er-Serie (−154,99). Plattform-EQ-DD gemeldet: 3,80 %. Plattform-Balance-DD: 8,11 %. Reko-EQ-DD aus Kursen nachgemessen (Floating inklusive): 5,69 %. Das bewertete Maximum liegt bei 8,11 % — klar unter der 30-%-Schranke, keine Verletzung (Feld `schranke_verletzt`: false).

**Sonderbefund Berichterstattung:** Die Rekonstruktion (5,69 %) liegt um 1,89 Prozentpunkte bzw. rund 50 % relativ über dem gemeldeten Equity-DD (3,80 %). Der Drawdown wurde schöner gemeldet, als er war — gesondert benannt, kein Schrankenverstoß, aber ein Vertrauensabzug. Eine Zweitmessung über `monitor_trade_eq_dd_pct` liegt nicht vor (null); eine Faktor-2-Prüfung ist damit nicht möglich.

**Verlustserie und Schock:** Größte Serie 13 Trades, −154,99 USD; schlimstes Leg −41,14. Peak-Exposure: 11 Positionen, netto 0,12 Lots; Schockszenario 600 USD = 30,51 % des Peak-Equity (1.966,84 USD). Das ist ein Stress-Szenario, kein gemessener Verlust — es begründet Gewichtung und Warnung, niemals allein Ablehnung, liegt hier aber praktisch exakt an der 30-%-Marke.

**Martingale:** Flag false, keine Evidenz. Der scheinbare Widerspruch zur „Grid"-Bezeichnung der Trade-Analyse löst sich auf: Einstiegs-Layering ohne Lot-Eskalation ist keine Martingale-Signatur.

**Stop-Loss:** Direkt bewiesen — Orderbuch 392/392 mit SL. Die Trade-Analyse qualifiziert dies wegen der TP-geloggten Verluste. Auflösung zugunsten der Forensik: Jede Order trägt einen SL, der Nachweis bleibt formal gültig und entlastend. Die Basket-Closes zeigen jedoch, dass die Exit-Steuerung teilweise in der EA-Logik statt broker-seitig liegt — nach SL-Regel kein Malus, aber ein Beobachtungspunkt.

## Copy-Eignung

Das Basiskonto ist klein (Peak ~1.967 USD). Kopierer tragen das Schockszenario proportional in voller Höhe mit; 20 Abonnenten zahlen 30 USD/Monat. Der XAUUSD-Spike-Stil ist slippage-anfällig, und alle bis zu 11 Parallelpositionen müssen beim Kopieren vollständig ankommen — bei Close-All-Exits wie dem 11:05-Cluster summiert sich Slippage über alle Legs. MT4-Kopierung auf FusionMarkets-Live 3; kleine Kopierkonten erleiden durch Mindestlot-Rundung Allokationsverzerrungen. Angesichts der Differenz zwischen gemeldetem (3,80 %) und rekonstruiertem EQ-DD (5,69 %) sollten Kopierer ihren eigenen Equity-Drawdown überwachen statt der Provider-Meldung zu vertrauen.

## Urteil

**WATCHLIST**

- **Risiko-Score (LLM-Urteil): 4/10** — moderate Risiken: harte Kriterien sauber, weiche Befunde belasten.
- **Engine-Risiko-Score: 4,1** (Engine-Ampel Grün/Kandidat; Urteil der Engine: „Forensik bestanden, Score < 5, Ertrag ok, Stop bewiesen"). Die vollständige Forensik-Batterie liegt vor, eine Einstufung ist damit zulässig; das Urteil folgt der Engine-Ampel und wertet sie nicht auf.

Drei wichtigsten Gründe:

1. **Verschönerte Drawdown-Berichterstattung:** Reko-EQ-DD 5,69 % vs. gemeldet 3,80 % (+1,89 pp, ~50 % relativ). Alle Werte unter der Schranke, aber die Abweichung verhindert den Empfehlungsstatus.
2. **Schockszenario an der Schrankenmarke:** 600 USD entsprechen 30,51 % des kleinen Peak-Equity (1.967 USD) — Stress-Szenario, kein messbarer Verlust, aber klare Gewichtung gegen eine Empfehlung.
3. **EA-Basket-Logik statt reinem Broker-SL:** Stop formal bewiesen (392/392), doch Verluste bis −41 je Leg werden als „[tp]" geloggt und Exit-Steuerung liegt teilweise im EA; die 13er-Serie (−154,99 USD) zeigt das Ausbruchsrisiko der Konstruktion.

Dem steht entgegen: kein Martingale, flaches Sizing, Winrate 77,6 %, PF 3,51 und mit 24,54 %/Monat ein Ertrag weit über der 5-%-Schwelle — Ertrag erst nach Risiko gewichtet.

## Bedingungen

Für einen Wechsel zu EMPFEHLUNG müssten eintreten:

- Die Lücke zwischen rekonstruiertem und gemeldetem Equity-DD schließt sich über weitere Monate (Transparenz-Nachweis).
- Die Kapitalbasis wächst, sodass das Schockszenario deutlich unter 30 % des Kontowerts fällt.
- Das Sizing bleibt flach; weitere 0,02-Lots oder eine Eskalation in Verlustserien hätte eine Martingale-Neuprüfung zur Folge (dann drocht ABLEHNUNG bei positiver Signatur).
- Keine neue Verlustserie über zehn Trades; Trading-DD bleibt im Bereich der bisherigen 4,57 %.
- Das Exit-Labeling wird konsistent oder die Basket-Verluste werden nachweislich durch ein hartes Verlustlimit begrenzt.


===== SIGNAL 2362868 | Pure Gold 2000 Vantage | quelle=mql5 =====
--- stats_json (Kandidaten-Fakten) ---
{"eq_dd_pct": 6.84, "bal_dd_pct": 11.55, "ertrag_monat_pct": 28.97, "pf": 2.74, "growth_pct": 291.0, "broker_server": "VantageMarkets-Live 14", "forensik_ok": true, "forensik_version": 7, "initial_deposit_usd": 13750.0, "balance_usd": 30133.54, "kapitalbasis_virtual_usd": null, "monitor_trade_eq_dd_pct": null, "last_fehler": null}
--- forensik json (upd 2026-09-30 00:03:22) ---
{"version": 7, "vollstaendig": true, "trading_dd": {"pct": 11.91, "usd": 2329.72}, "winrate_pct": 54.3, "max_verlustserie": 19, "verlustserie_usd": -1702.88, "peak_exposure": {"positionen": 32, "netto_lots": -3.44, "schock_usd": 17200.0, "shock_pct_max": 139.7241, "shock_pct_peak_time": "2026-06-24 15:25:04", "shock_pct_peak_account": 12309.97, "shock_pct_peak_usd": 17200.0}, "martingale_flag": false, "martingale_evidenz": [], "stop_nachweis": "Verlustdistanzen ohne Cluster — SL nicht uebertragen (neutral; KI schatzt aus dem Verhalten ab)", "stop_evidence": "none", "symbole": "XAUUSD+", "kapitalbasis": {"usd": 10000.0, "quelle": "csv_einzahlungen", "end_balance_real": 26274.97, "webseite_balance_usd": 30133.54}, "equity_rekonstruktion": {"test": "equity_rekonstruktion", "status": "skipped", "grund": "Kursdaten fehlen für 667 von 667 Trades (Kurse: XAUUSD+)"}, "fx_kursquelle": null, "score": 5.1, "kriterien_matrix": {"grenzen": {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}, "kriterien": {"dd_schranke": {"ampel": "🟢", "kurz": "Puffer 18,09 Punkte", "detail": "max(EQ-DD 6,84 %, Bal-DD 11,55 %, Trading-DD 11,91 %) = 11,91 % hält die Schranke 30 % mit 18,1 Punkten Abstand ein."}, "martingale": {"ampel": "🟢", "kurz": "keine Signatur", "detail": "Keine Lot-Eskalation nach Verlusten und kein Korb-Muster erkannt (Median-Faktor-Schwelle 1,3x nicht überschritten)."}, "stop": {"ampel": "⚪", "kurz": "neutral (nicht übertragen)", "detail": "SL in den Trade-Daten nicht sichtbar: Verlustdistanzen ohne Cluster — SL nicht uebertragen (neutral; KI schatzt aus dem Verhalten ab) — neutral, kein Nachteil (viele Broker übertragen keinen SL). Die KI-Analyse schätzt aus dem Tradingverhalten ab, ob ein impliziter Stop plausibel ist."}, "ertrag": {"ampel": "🟢", "kurz": "29,0 %/Monat", "detail": "29,0 %/Monat ≥ Mindestschwelle 5 %/Monat."}, "score": {"ampel": "🟡", "kurz": "Score 5,1", "detail": "Engine-Risiko-Score 5,1 von 10 — Kandidaten-Schwelle 5 überschritten (kein Kandidat)."}, "schock": {"ampel": "🟠", "kurz": "139,7 %", "detail": "50-USD-Schock über Peak-Netto-Lots ≈ 17200 USD = 139,7 % des Kontos am 2026-06-24 15:25:04 — übersteigt die Konto-Referenz rechnerisch. Stress-Szenario, kein gemessener Verlust; begründet Gewichtung und Beobachtung, nicht allein die Ablehnung."}, "serie": {"ampel": "🟡", "kurz": "19 in Folge", "detail": "Längste Verlustserie: 19 Trades, Summe -1703 USD — deutliche Regime-Belastung."}, "liste": {"ampel": "🟡", "kurz": "HERABGESTUFT 2026-09-04", "detail": "Watchlist-Eintrag (HERABGESTUFT 2026-09-04): 32 gleichz. SELL-Positionen / 2.66 Lots netto (=266 USD je 1 USD Bewegung; 50-USD-Schock ~ -13.300 USD), kein SL-Nachweis, 19-Verluste-Serie (-1.703 USD), nur 26 Wochen. Wiederaufnahme nur mit Orderbuch-Stop-Nachweis."}}}, "ampel": "🟡"}

--- ANALYSE trade_analyse (id=805, model=glm-5.3, tokens=11345, at=2026-09-30 00:56:24, basis=173242e61c47123089a144dc7f5e6b9bf891c51afcf9e333f380f9eb4481acd9) ---
**Strategie-Typ.** Es liegt ein Grid-/Cluster-Scalper mit Momentum-Komponente auf Gold vor. Einstiegsmuster: mehrere Legs nahezu simultan mit gestaffelten Einstiegspreisen — der größte Korb öffnet 10 Sell-Positionen um 22:47 zu EPs 5013,12–5015,06 und schließt alle gemeinsam um 22:50 (−17,30). Die Verlustserie bestätigt antizyklisches Nachziehen: 19 Sells zwischen 4507,29 und 4517,48 binnen ca. 50 Minuten (18:21–19:08), Exits über 37,9 Stunden verteilt. Exit-Muster: eng gestaffelte Mini-Ziele (Verlustdistanz-Level 0,10/0,11/0,47/0,69/0,75 Punkte mit je 3–4 Trades) plus gemeinsamer Korb-Exit; ein durchgängiges SL existiert nicht — Distanz-Maximum 152,01 Preiseinheiten (Worst-Trade −606,27 über 37,85 h) belegt das, konsistent mit „SL nicht übertragen" aus der Forensik. Harte Einzelstops (~33–41 Punkte) tauchen nur bei Richtungszyklen auf (−497,64 in 0,22 h; −236,39 in 0,16 h).

**Positionsgrößen.** Überwiegend klein: 446 von 667 Trades (67 %) laufen mit ≤0,05 Lot. Spitzenwerte 0,30–0,73 Lot erscheinen fast ausschließlich in den besten Momentum-Trades (0,67; 0,60; 0,53; 0,45). In der 19er-Serie bleiben die Lose bei 0,01–0,10 (einmal 0,42), kein Verdopplungsmuster — kein klassisches Martingale, sondern fixe Grid-Staffelung mit Antimartingale-artiger Aufweitung in Trendrichtung.

**Zeit-/Marktverhalten.** Zwei Session-Fenster: nachts 2–4 Uhr (93/76/37 Einstiege) und 12–16 Uhr (39/40/54/93). Median-Haltedauer 0,57 h, p90 6,25 h → Intraday-Scalping. Monatskurve: Gewinne in Volatilitäts-/Trendmonaten Juni (+8456,70), August (+6688,52), September (+6662,67); Juli mit −285,71 einziger Verlustmonat, Mai trotz Serie noch +850,76. Preisniveau (März ~5050, August ~4022) und Sell-Dominanz der Extremtrades zeigen Trendnutzung im Gold-Abwärtstrend; Buys kommen vor (z. B. −441,96 am 15.06.), sind aber minderrelevant.

**Anomalien.** Ausgeprägte Gewinn-/Verlustasymmetrie: avg_win 123,30 vs. avg_loss −53,15 (Faktor 2,3), Winrate 54,3 %, PF 2,74. Die Rendite hängt an wenigen großen Momentum-Zügen (Top-Gewinne +2793,86 und +2329,80). Extremvolatiles 3-Uhr-Fenster: +1462,68 in 0,03 h (43,1 Punkte in 2 Minuten, 0,34 Lot), erster Handelstag mit ±21,6 Punkten in 3 Minuten — Volatilitäts-/Datenansprache. Hauptrisiko: Grid ohne Stop, 152 Punkte adverse Bewegung.

**Einordnung.** Hochmechanisch: sekundengleiche Multi-Leg-Eröffnungen (19:07/19:08), identische Close-Zeiten im Korb, reproduzierbare Distanz-Level. Diskretion nicht erkennbar. Schwachstelle ist die Ausnahme-Logik bei starken Gegenbewegungen — dort wirken die langen Restlaufzeiten (15,4–37,9 h) wie Budget-basierte Verzweiflungsexits, nicht wie ein defininiertes Risikomanagement.

--- ANALYSE risiko_analyse (id=806, model=glm-5.3-flash, tokens=6939, at=2026-09-30 00:56:24, basis=173242e61c47123089a144dc7f5e6b9bf891c51afcf9e333f380f9eb4481acd9) ---
**Risikoprofil – Pure Gold 2000 Vantage (ID 2362868, XAUUSD, Vantage)**

**Risikobefunde**
- Martingale: Flag false, keine Evidenz — kein Befund, keine Aussage.
- Exposure: Spitzenwert 32 gleichzeitige Positionen, Netto −3,44 Lots (short); Schockszenario 17.200 USD = 139,7 % des Spitzenkontos (12.310 USD, 24.06.2026). Reine Stressgewichtung: nominelle Exposure überstieg das Eigenkapital — Konzentrationswarnung, kein gemessener Verlust.
- Stop: kein Nachweis (neutral gemäß Regel 28.09.2026); Verlustdistanzen ohne Cluster — nur als Hinweis, keine Abwertung.
- Verlustserie: 19 Verluste in Folge, kumuliert −1.702,88 USD; Winrate 54,3 %.

**Equity-Drawdown**
Plattform meldet 6,84 % (Equity) bzw. 11,55 % (Balance). Trading-DD aus geschlossenen Trades: 11,91 % (2.329,72 USD) — liegt über beiden Plattformwerten; wirksames Maximum damit 11,91 %, Schranke 30 % nicht verletzt, Mindestertrag (5 %) mit 28,97 %/Monat erfüllt. equity_dd_rekonstruiert_pct und monitor_trade_eq_dd_pct fehlen — dazu keine Aussage.

**Copy-Eignung**
32 Tickets und −3,44 Netto-Lots sind auf kleinen Folgekonto kaum 1:1 replizierbar (Margin, Slippage, Teilausführungen); nur 8 Abonnenten, 30 Wochen Historie. Gleicher Server (Vantage) mildert Slippage, beseitigt sie nicht.

**Fazit**
Warnung statt Entlastung: Peak-Exposure jenseits der Kontogröße (Schock 139,7 %) und die 19er-Verlustserie erfordern erhebliche Kapitalpuffer; EQ-DD-Rekonstruktion und Kapitalbasis fehlen — keine positive Einstufung vor vollständiger Forensik.

--- ANALYSE gesamtbericht (id=807, model=glm-5.3, tokens=12093, at=2026-09-30 00:57:52, basis=173242e61c47123089a144dc7f5e6b9bf891c51afcf9e333f380f9eb4481acd9) ---
Kurzfassung: Grid-/Momentum-Scalper auf Gold ohne Martingale; Drawdown unter Schranke, aber Exposure-Schock 139,7 % und Stop-Schutzlücke — Watchlist.

## 1. Was ist das für ein Trading-Algo?

Ein Grid-/Cluster-Scalper mit Momentum-Komponente, ausschließlich auf XAUUSD. Einstiegslogik: mehrere Legs nahezu simultan mit gestaffelten Einstiegspreisen — der größte Korb öffnet 10 Sell-Positionen um 22:47 zu EPs 5013,12–5015,06 und schließt alle gemeinsam um 22:50 (−17,30). In Gegenbewegungen wird antizyklisch nachgezogen: 19 Sells zwischen 4507,29 und 4517,48 binnen ca. 50 Minuten (18:21–19:08), Exits über 37,9 Stunden verteilt. Exit-Logik: eng gestaffelte Mini-Ziele (Verlustdistanz-Level 0,10/0,11/0,47/0,69/0,75 Punkte mit je 3–4 Trades) plus gemeinsamer Korb-Exit; ein durchgängiger Stop-Loss existiert nicht — Distanz-Maximum 152,01 Preiseinheiten, schlimmster Trade −606,27 über 37,85 h. Harte Einzelstops (~33–41 Punkte) tauchen nur in Richtungszyklen auf (−497,64 in 0,22 h; −236,39 in 0,16 h).

Automatisierungsgrad hoch: sekundengleiche Multi-Leg-Eröffnungen (19:07/19:08), identische Close-Zeiten im Korb, reproduzierbare Distanz-Level — Diskretion nicht erkennbar, plausibel ein Expert Advisor.

Widerspruchsprüfung: Die Trade-Analyse deutet die punktuellen Cut-Offs als „Stops"; die maschinelle Forensik ist massgeblich und findet keine Cluster-Signatur (stop_evidence: none). Aufgelöst: verhaltensbasierte Schnellschlüsse in Richtungszyklen, aber kein systematischer Stop-Schutz über alle Trades.

## 2. Wie handelt das System?

Positionsgrößen überwiegend klein: 446 von 667 Trades (67 %) mit ≤0,05 Lot; Spitzen von 0,30–0,73 Lot erscheinen fast ausschließlich in den besten Momentum-Trades (0,67; 0,60; 0,53; 0,45). In der 19er-Serie bleiben die Lose bei 0,01–0,10 (einmal 0,42), kein Verdopplungsmuster — fixe Grid-Staffelung mit Antimartingale-artiger Aufweitung in Trendrichtung.

Haltezeiten: Median 0,57 h, p90 6,25 h → Intraday-Scalping; Ausnahmen mit 15,4–37,9 h Laufzeit in starken Gegenbewegungen wirken wie Budget-basierte Exits, nicht wie definiertes Risikomanagement.

Session-Muster: zwei Fenster — nachts 2–4 Uhr (93/76/37 Einstiege) und 12–16 Uhr (39/40/54/93). Extremvolatiles 3-Uhr-Fenster: +1462,68 in 0,03 h (43,1 Punkte in 2 Minuten, 0,34 Lot); erster Handelstag mit ±21,6 Punkten in 3 Minuten — Volatilitäts-/Datenansprache.

Monatsverlauf: Gewinne konzentriert auf Trend-/Volatilitätsmonate Juni (+8456,70), August (+6688,52), September (+6662,67); Juli mit −285,71 einziger Verlustmonat, Mai trotz Serie +850,76. Das Preisniveau (März ~5050, August ~4022) und die Sell-Dominanz der Extremtrades belegen Trendnutzung im Gold-Abwärtstrend. Gewinn-/Verlustasymmetrie: avg_win 123,30 vs. avg_loss −53,15 (Faktor 2,3) bei Winrate 54,3 % und PF 2,74; die Rendite hängt an wenigen großen Momentum-Zügen (+2793,86; +2329,80).

## 3. Risikoanalyse

Drawdown-Dreiklang: Plattform meldet 6,84 % (Equity) bzw. 11,55 % (Balance); aus geschlossenen Trades rekonstruiert 11,91 % (2.329,72 USD). Das Trading-DD liegt über beiden Plattformwerten (Faktor ~1,7 zur Equity-Meldung) — wirksames Maximum damit 11,91 %; die 30-%-Schranke ist klar nicht verletzt, der Mindestertrag mit 28,97 %/Monat erfüllt. equity_dd_rekonstruiert_pct (Kursdaten, floating inklusive) ist null, monitor_trade_eq_dd_pct ebenfalls null — beide Messungen liegen nicht vor, dazu keine Aussage. Ein hartes Ablehnungskriterium (Rekonstruktion über 30 %) ist damit nicht erfüllt, aber die Forensik-Batterie ist unvollständig: Bei einem Grid-System wären gerade floating Drawdowns zwischen den Plattform-Snapshots relevant und bleiben unbewertet.

Verlustserie: 19 Verluste in Folge, kumuliert −1.702,88 USD. Peak-Exposure: 32 gleichzeitige Positionen, Netto −3,44 Lots (short); Schockszenario 17.200 USD = 139,72 % des Spitzenkontos (12.309,97 USD, 24.06.2026 15:25). Dies ist reine Stressgewichtung, kein gemessener Verlust und allein kein Ablehnungsgrund — aber die nominelle Exposure überstieg das Eigenkapital: deutliche Konzentrationswarnung und erheblicher Pufferbedarf.

Martingale: Flag false, keine Evidenz — kein Befund. Stop-Loss: SL nicht übertragen, Verlustdistanzen ohne Cluster → nach bindender Regel neutral, kein Malus. Verhaltensbasierte Einschätzung: Für die Grid-Legs ist Stop-Schutz unwahrscheinlich (adverse Distanz bis 152,01 Einheiten, Verlusthaltung bis 37,85 h); die ~33–41-Punkte-Cut-Offs betreffen nur Richtungszyklen und sind kein systematischer Schutz. Diese begründete Einschaetzung fließt in die Gewichtung ein, ersetzt aber keinen SL-Nachweis.

## 4. Copy-Eignung

Spitzenkonto ca. 12.310 USD; das Schockszenario erreicht 139,7 % dieser Größe — proportionales Kopieren setzt ein deutlich größeres Folgekonto voraus. 32 parallele Tickets und −3,44 Netto-Lots sind auf kleinen Konten kaum 1:1 replizierbar (Margin, Slippage, Teilausführungen). Gleicher Server (VantageMarkets-Live 14) mildert Slippage, beseitigt sie nicht; Einstiegsstürme in schnellen Fenstern (2–4 Uhr, Bewegungen innerhalb von 2–3 Minuten) erhöhen Latenz- und Slippage-Anfälligkeit. Nur 8 Abonnenten bei 30 Wochen Historie — wenig Praxis-Evidenz zum Kopierverhalten. Abo-Preis 30 USD/Monat.

## 5. Urteil

**WATCHLIST**

Risiko-Score (LLM-Urteil): 7/10
Engine-Risiko-Score: 5.1 (Ampel Gelb = Beobachtung, „kein Kandidat")

Drei wichtigsten Gründe:
1. Unvollständige Forensik-Batterie: Reko-EQ-DD und Monitor-Zweitmessung fehlen (beide null), ebenso kapitalbasis_verwendet — nach bindender Regel keine positive Einstufung vor vollständiger Batterie; die Engine markiert „kein Kandidat", das Urteil folgt der Engine.
2. Verhaltensbasierte Stop-Lücke: Grid ohne systematischen Schutz, 152,01 Punkte adverse Bewegung, 37,85-h-Verlusthaltung, 19er-Serie — begründeter Befund „wahrscheinlich ohne Stop-Schutz" (die fehlende SL-Übertragung selbst bleibt neutral).
3. Exposure und Fragilität: Schock 17.200 USD = 139,7 % des Eigenkapitals, Ein-Asset-Konzentration und Abhängigkeit von wenigen Momentum-Zügen — erheblicher Kapitalpufferbedarf, Ertragsqualität nicht robust.

## 6. Bedingungen

Statuswechsel nach oben erfordert:
- Vollständige Forensik: Reko-EQ-DD aus Kursdaten (floating inklusive) mit belastbarer Abdeckung, deutlich unter 30 %, plus monitor_trade_eq_dd_pct als Zweitmessung.
- Nachweisbare Begrenzung der Gleichzeitigkeit (Schock unter 100 % der Kontogröße) oder eine Cluster-Signatur konsistenter Cut-Off-Niveaus als impliziter Stop.
- Längere Historie ohne neue Verlustserie dieser Größenordnung, Stabilität außerhalb der Trendmonate Juni/August/September und mehr Abonnenten als Kopier-Evidenz.

Automatische ABLEHNUNG bei: Reko-EQ-DD ≥ 30 % (hartes Kriterium), Martingale-Evidenz, weiter steigender Exposure oder einer Serie, die die Kontogröße ernsthaft gefährdet.


===== SIGNAL 2307342 | Techno Long Term | quelle=mql5 =====
--- stats_json (Kandidaten-Fakten) ---
{"eq_dd_pct": 13.77, "bal_dd_pct": 38.63, "ertrag_monat_pct": 16.58, "pf": 1.32, "growth_pct": 987.0, "broker_server": "TickmillUK-Live\n1", "forensik_ok": true, "forensik_version": 7, "initial_deposit_usd": 100.0, "balance_usd": 2483.84, "kapitalbasis_virtual_usd": null, "monitor_trade_eq_dd_pct": null, "last_fehler": null}
--- forensik json (upd 2026-09-30 00:03:59) ---
{"version": 7, "vollstaendig": true, "trading_dd": {"pct": 60.08, "usd": 503.91}, "winrate_pct": 69.1, "max_verlustserie": 16, "verlustserie_usd": -19.1, "peak_exposure": {"positionen": 18, "netto_lots": 0.19, "schock_usd": 950.0, "shock_pct_max": 155.899, "shock_pct_peak_time": "2025-02-13 21:04:18", "shock_pct_peak_account": 293.78, "shock_pct_peak_usd": 458.0}, "martingale_flag": false, "martingale_evidenz": [], "stop_nachweis": "kein eindeutiges Stop-Niveau erkennbar — neutral", "stop_evidence": "none", "symbole": "BTCUSD, US30, US500, USTEC, XAUUSD", "kapitalbasis": {"usd": 100.0, "quelle": "csv_einzahlungen", "end_balance_real": 2467.12, "webseite_balance_usd": 2483.84}, "equity_rekonstruktion": {"test": "equity_rekonstruktion", "status": "unvollstaendig", "gmt_offset_h": 0, "gmt_trefferquote": 1.0, "equity_dd_pct": 30.85, "equity_dd_usd": 503.91, "abdeckung_pct": 88.0, "rasterpunkte": 17834, "verlaesslich": false, "symbole_mit_kursen": ["BTCUSD", "US30", "US500", "USTEC", "XAUUSD"], "grund": "Abdeckung 88% < 95%"}, "fx_kursquelle": null, "score": 6.9, "kriterien_matrix": {"grenzen": {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}, "kriterien": {"dd_schranke": {"ampel": "🔴", "kurz": "60,08 % > 30 %", "detail": "max(EQ-DD 13,77 %, Bal-DD 38,63 %, Trading-DD 60,08 %) = 60,08 % liegt ÜBER der Schranke von 30 % (harte Ablehnung)."}, "martingale": {"ampel": "🟢", "kurz": "keine Signatur", "detail": "Keine Lot-Eskalation nach Verlusten und kein Korb-Muster erkannt (Median-Faktor-Schwelle 1,3x nicht überschritten)."}, "stop": {"ampel": "⚪", "kurz": "neutral (nicht übertragen)", "detail": "SL in den Trade-Daten nicht sichtbar: kein eindeutiges Stop-Niveau erkennbar — neutral — neutral, kein Nachteil (viele Broker übertragen keinen SL). Die KI-Analyse schätzt aus dem Tradingverhalten ab, ob ein impliziter Stop plausibel ist."}, "ertrag": {"ampel": "🟢", "kurz": "16,6 %/Monat", "detail": "16,6 %/Monat ≥ Mindestschwelle 5 %/Monat."}, "score": {"ampel": "🟡", "kurz": "Score 6,9", "detail": "Engine-Risiko-Score 6,9 von 10 — Kandidaten-Schwelle 5 überschritten (kein Kandidat)."}, "schock": {"ampel": "🟠", "kurz": "155,9 %", "detail": "50-USD-Schock über Peak-Netto-Lots ≈ 950 USD = 155,9 % des Kontos am 2025-02-13 21:04:18 — übersteigt die Konto-Referenz rechnerisch. Stress-Szenario, kein gemessener Verlust; begründet Gewichtung und Beobachtung, nicht allein die Ablehnung."}, "serie": {"ampel": "🟡", "kurz": "16 in Folge", "detail": "Längste Verlustserie: 16 Trades, Summe -19 USD — deutliche Regime-Belastung."}, "liste": {"ampel": "🟢", "kurz": "nicht gelistet", "detail": "Signal steht weder auf der Ausschlussliste noch auf der Watchlist (known_signals.json)."}}}, "ampel": "🔴"}

--- ANALYSE trade_analyse (id=835, model=glm-5.3, tokens=10673, at=2026-09-30 01:27:42, basis=ae2d3bb9345b77cfcef3daa19318579e2eece6f2966e149d9a4c0526a6698fa2) ---
**Strategie-Typ.** Der Name „Long Term" ist irreführend: Die mediane Haltedauer beträgt 0,17 h (≈10 Min), p90 liegt bei 2,3 h – das ist ein Multi-Asset-Scalper. Das Entry-Muster zeigt Clusterbildung: Der größte Korb umfasst 7 US30-Sells, alle eröffnet 16:38 (EP 41965,85–41966,85, Differenz teils 0,5 Punkte), alle gemeinsam um 16:46 geschlossen (+12,82 netto). Die Verlustserie zeigt 10 parallele US30-Buys innerhalb von 9 Minuten (13:44–13:53), gemeinsam bei 14:05/14:07 beendet. Typisch also: Signal-Auslösung, Aufteilung in mehrere Mikro-Positionen statt eines Lots, gemeinsamer Basket-Exit bei TP wie auch im Verlustfall. Gold-Verlierer laufen ohne engen SL weit: -58,96 bei 0,01 Lot XAUUSD (68 Punkte Adverse-Move, 2,8 h); BTC-Distanz_median 676 Punkte bestätigt weite Adverse-Excursions.

**Positionsgrößen.** Modal-Lot 0,01 (2.294 von 4.663 Trades ≈ 49 %), gestaffelt bis 0,48. Kein Martingale (Verlustserie: konstant 0,01–0,02, Summe von 16 Verlusten nur -19,10), aber Korb-Addition und Volatilitäts-Sortierung: Gold max. 0,10, Indizes bis 0,48. Kumulationsrisiko existiert: Am 2026-03-10 drei XAUUSD-Buys ab 18:31, zusammen ≈ -152.

**Zeit-/Marktverhalten.** Einstiegsschwerpunkt 15–18 Uhr (16 Uhr: 1.046 Trades) = US-Open für Indizes; Gold handelt nahezu rund um die Uhr (Beispieltrades 02:15, 05:38, 06:19, 07:37). Der Gewinn hängt fast komplett am Gold: XAUUSD +2.313,48 (81 % WR), BTCUSD +258,72 (84 %); die Indizes liefern bei 2.822 Trades zusammen -55,33 (US30 -104,24, US500 -2,65, USTEC +51,56). Starke Monate 2026-03 (+399), 2026-06 (+630), 2026-08 (+371); Einbrüche 2026-04 (-284) und 2026-07 (-168) folgen direkt auf Gold-Volatilitätsphasen (fünf Worst-Losses über -44 stammen aus 2026-03/04).

**Anomalien.** Avg_loss (-5,62) ist fast doppelt so groß wie avg_win (+3,29) bei 69,1 % Winrate – klassisches Scalping-Profil mit TP < SL. Balance-DD 38,63 % versus Equity-DD 13,77 %: Verluste werden konsequent realisiert (Basket-Cut), floating bleibt klein – die 30-%-Schranke wird trotzdem verletzt. Best Trades (+35 bis +45 auf 0,01 Gold) sind Trendtage-Ausreißer, nicht Regel-TP.

**Einordnung.** Hochmechanisch: identische Sekunden-Zeitstempel, EP-Differenzen unter 1 Punkt zwischen Legs, einheitliche Exit-Minuten, symmetrische Long/Short-Nutzung. Das deutet auf einen EA mit Session-Filter (US-Open) plus 24-h-Gold-Modul. Diskretion allenfalls in der Losgrößen-Skalierung: Trotz 81 % WR auf Gold bleibt das Lot dort bei 0,01–0,10, während die verlustträchtigen Indizes die größten Lots (0,48 US30) erhalten – ein inkonsistentes Risikomapping. Nach 108 Wochen und 4.663 Trades ist das Muster stabil, aber das Pfadrisiko konzentriert sich vollständig im Gold-Modul, während der Indizes-Teil netto Kapital und Spreads verbrennt.

--- ANALYSE risiko_analyse (id=836, model=glm-5.3-flash, tokens=6774, at=2026-09-30 01:27:42, basis=ae2d3bb9345b77cfcef3daa19318579e2eece6f2966e149d9a4c0526a6698fa2) ---
**1. Risikobefunde**
Kein Martingale-/Grid-Nachweis (Flag false, leere Evidenz). Stop-Befund: kein eindeutiges Niveau erkennbar — laut Nutzerregel neutral, kein Malus. Peak-Exposure: 18 Positionen parallel, 0,19 Netto-Lots; Schockszenario 950 USD (155,9 %), Peak am 13.02.2025 21:04 mit 293,78 % bzw. 458 USD — reines Stressexposure, kein gemessener Verlust, aber Warnungsgewicht. Verlustserie: 16 Trades in Folge, kumuliert −19,1 USD; Winrate 69,1 %, PF 1,32. Muster: sehr kleine Verlustdistanzen je Trade bei fehlendem SL-Nachweis — nur Hinweis, keine Abwertung.

**1a. Equity-Drawdown**
Gemeldet: 13,77 % (Equity), 38,63 % (Balance); aus geschlossenen Trades rekonstruiert: 60,08 % (−503,91 USD). Kernbefund: der Trading-DD liegt 46,31 Punkte über dem Equity-Meldewert (Faktor ≈ 4,4) und 21,45 Punkte über dem Balance-Wert — der gemeldete Drawdown ist deutlich schöner als belegt. equity_dd_rekonstruiert_pct und monitor_trade_eq_dd_pct fehlen (null) — dazu keine Aussage; Forensik-Batterie unvollständig, keine positive Einstufung.

**2. Copy-Eignung**
Sehr kleine Kontobasis (Peak-Konto ~458 USD, Schock 950 USD): Kopierer mit größerem Depot riskieren nicht-proportionale Positionsgrößen und Slippage; BTCUSD/US30/USTEC/XAUUSD mit bis zu 18 Parallelpositionen erhöhen Ausführungs- und Spread-Risiko; nur 4 Abonnenten, Abo 39 USD.

**3. Fazit**
Warnung: harte Schranke verletzt — maximaler Drawdown 60,08 % (Trades) gegen Limit 30 %; der Plattform-Meldewert (13,77 %) bildet das reale Risiko nicht ab.

--- ANALYSE gesamtbericht (id=837, model=glm-5.3, tokens=11190, at=2026-09-30 01:29:10, basis=ae2d3bb9345b77cfcef3daa19318579e2eece6f2966e149d9a4c0526a6698fa2) ---
Kurzfassung: Harte Ablehnung — der rekonstruierte Trading-Drawdown von 60,08 % verletzt die 30-%-Schranke; skalpierender Multi-Asset-EA, Gewinndepending vom Goldmodul, winziges Referenzkonto.

## 1. Was ist das für ein Trading-Algo?

Der Name „Long Term" ist irreführend. Die mediane Haltedauer beträgt 0,17 h (etwa 10 Minuten), p90 liegt bei 2,3 h — das ist ein Multi-Asset-Scalper. Der Automatisierungsgrad ist hoch: identische Sekunden-Zeitstempel, Einstiegspreis-Differenzen unter einem Punkt zwischen den Legs, einheitliche Exit-Minuten und symmetrische Long/Short-Nutzung über 108 Wochen und 4.663 Trades. Das Muster deutet auf einen EA mit zwei Modulen: ein Index-Modul mit Session-Filter (Einstiegsschwerpunkt 15–18 Uhr, allein 16 Uhr = 1.046 Trades, passend zum US-Open) und ein nahezu rund um die Uhr laufendes Gold-Modul (Beispieltrades 02:15, 05:38, 06:19, 07:37 Uhr). Diskretion ist allenfalls in der Losgrößen-Skalierung erkennbar, nicht in der Entry-Logik.

## 2. Wie handelt das System?

**Einstieg/Exit als Korb-Logik.** Der größte Korb umfasst 7 US30-Sells, alle eröffnet um 16:38 (EP 41965,85–41966,85), gemeinsam geschlossen um 16:46 (+12,82 netto). Spiegelbildlich die Verlustserie: 10 parallele US30-Buys innerhalb von 9 Minuten (13:44–13:53), gemeinsam bei 14:05/14:07 beendet. Statt eines Lots wird also ein Signal in mehrere Mikro-Positionen aufgeteilt und der Korb einheitlich geschlossen — im Gewinn wie im Verlust.

**Sizing.** Modal-Lot 0,01 (2.294 von 4.663 Trades ≈ 49 %), gestaffelt bis 0,48. Kein Martingale: In der 16er-Verlustserie bleiben die Lots konstant bei 0,01–0,02 (Summe nur −19,10 USD). Dafür Korb-Addition und ein inkonsistentes Risikomapping: Gold (81 % WR, +2.313,48 USD) erhält max. 0,10 Lot, die netto verlustträchtigen Indizes die größten Lots (0,48 US30). Kumulationsbeispiel: 2026-03-10 drei XAUUSD-Buys ab 18:31, zusammen ≈ −152 USD.

**Profil.** Avg_Win +3,29 vs. Avg_Loss −5,62 bei 69,1 % Winrate und PF 1,32 — klassisches Scalping mit TP < SL. Gold-Verlierer laufen ohne engen Schutz weit (−58,96 bei 0,01 Lot, 68 Punkte Adverse-Move, 2,8 h; BTC-Distanz-Median 676 Punkte). Der Ertrag hängt fast vollständig am Gold; die Indizes liefern bei 2.822 Trades zusammen −55,33 USD (US30 −104,24; US500 −2,65; USTEC +51,56) — Kapital- und Spread-Verbrennung. Starke Monate (2026-03 +399, 2026-06 +630, 2026-08 +371) und Einbrüche (2026-04 −284, 2026-07 −168) folgen direkt auf Gold-Volatilitätsphasen; die fünf Worst-Losses unter −44 stammen aus 2026-03/04.

## 3. Risikoanalyse

**Drawdown-Dreiklang.** Gemeldeter Plattform-EQ-DD: 13,77 %. Plattform-Balance-DD: 38,63 %. Aus geschlossenen Trades rekonstruierter Trading-DD: 60,08 % (−503,91 USD). Eine kursdatenbasierte Reko-EQ-DD (Feld `equity_dd_rekonstruiert_pct`) und die Zweitmessung `monitor_trade_eq_dd_pct` liegen nicht vor (beide null) — die Forensik-Batterie ist unvollständig, was unabhängig vom Ausgang keine positive Einstufung zulässt.

Gewertet wird das Maximum: 60,08 % gegen die harte Schranke von 30 % — Verletzung. Sogar der Balance-DD liegt mit 38,63 % über dem Limit. Kernbefund: Der Trading-DD liegt 46,31 Punkte über dem gemeldeten Equity-Wert (Faktor ≈ 4,4) und 21,45 Punkte über dem Balance-Wert. Der Plattform-Meldewert bildet das reale Pfadrisiko deutlich schöner ab, als es die Trade-Kurve belegt. Widersprüche zwischen Meldewert und Forensik wurden zugunsten der maschinellen Forensik aufgelöst; die Engine hat daraufhin die Schranke als verletzt markiert (`schranke_verletzt: true`).

**Verlustserie und Exposure.** Maximal 16 Verluste in Folge, kumuliert −19,10 USD — absolut klein, mit sehr engen Verlustdistanzen pro Trade. Peak-Exposure: 18 Parallelpositionen, 0,19 Netto-Lots; Schockszenario 950 USD (155,9 % des Kontos), Peak am 13.02.2025 21:04 mit 293,78 % bzw. 458 USD. Dies ist ausdrücklich ein Stressexposure, kein gemessener Verlust — es begründet Gewichtung und Warnung, niemals allein die Ablehnung.

**Martingale und Stop.** Martingale-Flag false, Evidenzliste leer — kein Malus. Stop-Nachweis: kein eindeutiges Niveau erkennbar, laut Engine neutral. Verhaltensbasierte Einschätzung: weite Adverse-Excursions auf Gold/BTC und die einheitlichen Korb-Exits deuten darauf hin, dass die Verlustbegrenzung über gemeinsame Basket-Cuts läuft und orderbezogene Stops wahrscheinlich fehlen — bei Gaps oder Wochenenden ohne Schutz. Da das Muster aber nicht zweifelsfrei ist, bleibt dieser Punkt nach bindender SL-Regel als Hinweis mit Warnungsgewicht, nicht als eigenständiger Abwertungsgrund, stehen.

Das Gefälle Balance-DD (38,63 %) zu Equity-DD (13,77 %) zeigt, dass Verluste konsequent realisiert werden und Floating klein bleibt — die Schranke wird dennoch verletzt.

## 4. Copy-Eignung

Gering. Die Kapitalbasis ist winzig: Peak-Konto ≈ 458 USD, Schock 950 USD, absoluter Trading-DD −503,91 USD. Kopierer mit größeren Depots treffen auf ein nicht-proportionales Scaling-Problem (Mindestlots, Rundung) und Slippage — bei einem Scalping-Profil mit Avg_Win von nur +3,29 USD frisst bereits geringe Slippage die Marge. Bis zu 18 Parallelpositionen über BTC, Indizes und Gold erhöhen Ausführungs- und Spread-Risiko beim Kopieren; das 24-h-Goldmodul erfordert durchgehende Copy-Laufzeit. Broker-seitig TickmillUK-Live (MT5) — Symbol-Anforderungen sollten geprüft werden. Nur 4 Abonnenten bei 39 USD/Monat bedeuten minimale praktische Validierung des Copy-Setups.

## 5. Urteil

**ABLEHNUNG.**

- **Engine-Risiko-Score: 6,9** (Engine-Ampel 🔴 — „Schranke verletzt: Drawdown > 30 %", harte Ablehnung).
- **Risiko-Score (LLM-Urteil): 9/10** (hoch = riskant).

Drei wichtigste Gründe:

1. **Harte Schrankenverletzung:** Das gewertete Maximum des Drawdowns beträgt 60,08 % (Trading-DD) gegen das Limit von 30 %; auch der Balance-DD (38,63 %) überschreitet die Grenze. Die Engine-Ampel 🔴 ist bindend — automatisch Ablehnung, keine Aufwertung möglich.
2. **Systematisch beschönigter Risikomeldewert:** Faktor ≈ 4,4 zwischen gemeldetem EQ-DD und rekonstruiertem Trading-DD; die Plattformzahl ist als Risikoindikator nicht belastbar.
3. **Strukturelle Fragilität:** Ertragsmonokultur Gold, während die Indizes netto Kapital und Spreads verbrennen — ausgerechnet mit den größten Lots; dazu winziges Referenzkonto und Stressexposure von 156 % bis 294 % des Kontos.

Der Ertrag von 16,58 %/Monat erfüllt die Mindestschwelle von 5 % — nach dem Grundsatz „Risiko vor Ertrag" ist das gegen die verletzte harte Schranke bedeutungslos.

## 6. Bedingungen

Ein Statuswechsel ist nur denkbar, wenn:

- die harte Schranke nachhaltig unproblematisch wird, d. h. eine neue, materielle Track-Record-Strecke vorliegt, in der das Maximum aus Plattform-EQ-DD, Balance-DD und rekonstruiertem Trading-DD — plus Reko-EQ-DD bei belastbarer Kursabdeckung — dauerhaft unter 30 % bleibt;
- die Forensik-Batterie vollständig ist (`equity_dd_rekonstruiert_pct` und `monitor_trade_eq_dd_pct` vorhanden und mit den Meldewerten konsistent);
- eine belastbare, größere Kapitalbasis (`kapitalbasis_verwendet` verwertbar) proportionales Copy-Scaling erlaubt und das Schockszenario klar unter 100 % des Kontos fällt;
- das Risikomapping konsistent wird: Losgrößen nach Modul-Performance statt Volatilitäts-Sortierung zugunsten der Verlustmodule.

Da die rote Ampel auf der verletzten Schranke über die bestehende 108-Wochen-Historie beruht, können einzelne bessere Kennzahlen die Ablehnung nicht aufheben; erforderlich wäre eine wesentlich neue, überprüfte Historie.


===== SIGNAL 2052727 | 💎t.me/Mr_Profit_FX | quelle=pelik =====
--- stats_json (Kandidaten-Fakten) ---
{"eq_dd_pct": 2.16, "bal_dd_pct": null, "ertrag_monat_pct": 63.79, "pf": null, "growth_pct": null, "broker_server": null, "forensik_ok": true, "forensik_version": 7, "initial_deposit_usd": null, "balance_usd": 4437.15, "kapitalbasis_virtual_usd": 10000.0, "monitor_trade_eq_dd_pct": 22.730837111284455, "last_fehler": null}
--- forensik json (upd 2026-09-30 00:05:39) ---
{"version": 7, "vollstaendig": true, "trading_dd": {"pct": 0.66, "usd": 68.11}, "winrate_pct": 73.6, "max_verlustserie": 15, "verlustserie_usd": -52.78, "peak_exposure": {"positionen": 70, "netto_lots": -0.94, "schock_usd": 3390.47, "shock_pct_max": 31.0126, "shock_pct_peak_time": "2026-08-26 23:15:07", "shock_pct_peak_account": 10932.56, "shock_pct_peak_usd": 3390.47}, "martingale_flag": false, "martingale_evidenz": [], "stop_nachweis": "kein eindeutiges Stop-Niveau erkennbar — neutral", "stop_evidence": "none", "symbole": "AUDCAD", "kapitalbasis": {"usd": 10000.0, "quelle": "virtuelle_annahme", "end_balance_real": 11154.38, "webseite_balance_usd": 4437.15}, "equity_rekonstruktion": null, "fx_kursquelle": "EZB-Euro-Referenzkurse (eurofxref-hist), Cross-Kurs ueber EUR/USD am Handelstag", "score": 4.8, "kriterien_matrix": {"grenzen": {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}, "kriterien": {"dd_schranke": {"ampel": "🟢", "kurz": "Puffer 27,84 Punkte", "detail": "max(EQ-DD 2,16 %, Trading-DD 0,66 %) = 2,16 % hält die Schranke 30 % mit 27,8 Punkten Abstand ein."}, "martingale": {"ampel": "🟢", "kurz": "keine Signatur", "detail": "Keine Lot-Eskalation nach Verlusten und kein Korb-Muster erkannt (Median-Faktor-Schwelle 1,3x nicht überschritten)."}, "stop": {"ampel": "⚪", "kurz": "neutral (nicht übertragen)", "detail": "SL in den Trade-Daten nicht sichtbar: kein eindeutiges Stop-Niveau erkennbar — neutral — neutral, kein Nachteil (viele Broker übertragen keinen SL). Die KI-Analyse schätzt aus dem Tradingverhalten ab, ob ein impliziter Stop plausibel ist."}, "ertrag": {"ampel": "🟢", "kurz": "63,8 %/Monat", "detail": "63,8 %/Monat ≥ Mindestschwelle 5 %/Monat."}, "score": {"ampel": "🟢", "kurz": "Score 4,8", "detail": "Engine-Risiko-Score 4,8 von 10 — unter der Kandidaten-Schwelle 5."}, "schock": {"ampel": "🟡", "kurz": "31,0 %", "detail": "50-USD-Schock über Peak-Netto-Lots ≈ 3390 USD = 31,0 % des Kontos am 2026-08-26 23:15:07 — erhebliche Stress-Belastung. Stress-Szenario, kein gemessener Verlust; begründet Gewichtung, nicht allein die Ablehnung."}, "serie": {"ampel": "🟡", "kurz": "15 in Folge", "detail": "Längste Verlustserie: 15 Trades, Summe -53 USD — deutliche Regime-Belastung."}, "liste": {"ampel": "🟢", "kurz": "nicht gelistet", "detail": "Signal steht weder auf der Ausschlussliste noch auf der Watchlist (known_signals.json)."}}}, "ampel": "🟢"}

--- ANALYSE trade_analyse (id=910, model=glm-5.3, tokens=10907, at=2026-09-30 02:43:56, basis=3c5e420b389325db78863ddd45641908b2b73d6ffa5a5390dfc969c5b9ebc945) ---
Der Datensatz zeichnet ein sehr klares Bild: ein hochmechanischer Mean-Reversion-Grid-Roboter, spezialisiert auf AUDCAD, mit Basket-Exits und ohne individuelle Stop-Loss.

**1. Strategie-Typ: Grid/Averaging (Korridor-Mean-Reversion) mit korbbasiertem Exit.** Die Verlustserie zeigt das Muster explizit: Sells werden nachlaufend in Verlustrichtung addiert (22.01. 00:45 ep 0,93809, 16:00 ep 0,94186, 23.01. 07:54 ep 0,94376) und alle 15 Legs am 29.01. 15:20 simultan bei 0,9473–0,9474 geschlossen. Der größte Korb (18 Sell-Legs, eröffnet 07.–10.04.) läuft ebenfalls auf einen einzigen Close-Zeitpunkt (12.04. 21:01, xp 0,9741) und endet netto +32,78. Ein fester SL existiert nicht: Die Verlustdistanzen streuen breit (Median 20,9 Pips, Max 142,5 Pips, häufigstes Level nur 6× bei 14,4 Pips) — es gibt keinen dominanten Fixwert. Der Exit erfolgt ersichtlich auf Konto-/Korbebene bei Erreichen einer Gewinnschwelle, vermutlich mit Trailing. Auffällig sind Mehrfach-Opens auf nahezu identischem Niveau (5× ep 0,91466–0,91471 am 11.11. 07:45; 5× ep 0,94368–0,94406 am 23.01.), also Layering mit engem statt weitem Grid-Spacing.

**2. Positionsgrößen: flach mit leichter Anhebung.** 1139× 0,01, 325× 0,02, nur 5× 0,04 Lots. Keine Martingale-Progression erkennbar; die 0,02er tauchen u. a. im August-Korb auf (schlechteste Trades −11,97), also leicht erhöhte Größe in größeren Körben, aber keine systematische Eskalation.

**3. Zeit-/Marktverhalten.** Einstiege über 24h verteilt mit Häufung 01–02, 06–08 und 13–15 Uhr (Top: 15h = 127, 7h = 103, 6h = 98) — asiatische Session plus London-Vormittag, kein News-Muster. Median-Haltedauer 17,1h, P90 132h, Max 271,5h. Alle 11 Monate positiv (45,49 bis 221,82, netto gesamt 1154,38). Verluste entstehen ausnahmslos in Trendphasen gegen die Korbrichtung: Die Serie −52,78 fiel mit dem AUDCAD-Anstieg 0,9335→0,9588 zusammen; die besten Trades (+8,72 in 9,8h am 29.01.) entstanden aus demselben Setup von der anderen Korridorseite (Sell 0,9588, Close 0,9469).

**4. Anomalien.** Asymmetrie zugunsten der Verluste: avg_loss −2,73 vs. avg_win +2,05 bei 73,6 % Winrate (Erwartungswert ≈ +0,79/Trade, konsistent mit 1469 Trades). Worst −11,97 ≈ 5,8× avg_win nach 271h Haltedauer — Verluste laufen ungebrochen lange, Realisierung erst beim Flush (29.01., 01.09.). Kein Verlustmonat bei Equity-DD von nur 2,16 % ist typisch für Grid-Systeme, solange der Korridor hält. Keine Rollover-/Swap-Signaturen, keine Diskretionsausreißer; Exit-Cluster sind minutengleich (21:01, 15:20).

**5. Einordnung: regelbasiert, EA-typisch.** Simultane Multi-Opens, sekundengenaue Basket-Closes, konstante Richtung pro Regime und 100 % AUDCAD bei ~29 Trades/Woche sprechen für einen vollautomatischen Grid-EA; maximal der totale Richtungs-Clearing am 29.01. könnte eine manuelle Intervention sein, ist aber auch als Regel erklärbar. Kernrisiko: unbegrenzte Haltedauer ohne SL — die Statistik spiegelt einen bislang nicht stattgefundenen Korridor-Bruch.

--- ANALYSE risiko_analyse (id=911, model=glm-5.3-flash, tokens=6266, at=2026-09-30 02:43:56, basis=3c5e420b389325db78863ddd45641908b2b73d6ffa5a5390dfc969c5b9ebc945) ---
## Risikoprofil — 💎t.me/Mr_Profit_FX (Pelican, AUDCAD, 50 Wochen)

**1. Risikobefunde**
- Exposure: bis zu 70 gleichzeitige Positionen, netto −0,94 Lots. Schockszenario: 3.390,47 USD ≙ 31,0 % des Peak-Kontos (10.932,56 USD) — reine Stressgewichtung, kein gemessener Verlust, aber nahe der 30-%-Schranke.
- Stop: kein eindeutiges Stop-Niveau erkennbar — neutral. Bei 70 offenen Positionen ohne Stop-Bestätigung ist die floating Verlustdistanz im Schockfall erheblich (Hinweis, keine Abwertung).
- Verlustserie: max. 15 Verluste in Folge, kumuliert −52,78 USD; Winrate 73,6 %; Trading-DD 0,66 % (68,11 USD).

**1a. Equity-Drawdown — Kernbefund**
Gemeldet (dd_equity): 2,16 %. Monitor-Zweitmessung aus der Voltenskurve: 22,73 % — Faktor ≈ 10,5. Der Anbieter meldet den Drawdown deutlich schöner, als er war; die Differenz erklärt sich plausibel durch floating Verluste der bis zu 70 offenen Positionen, die im Trading-DD (nur geschlossene Trades) unsichtbar bleiben. Formale 30-%-Schranke bleibt gewahrt.

**2. Copy-Eignung**
Kapitalbasis virtuell (10.000-USD-Annahme) — reale Nachbildbarkeit ungewiss. 70 Positionen erfordern hohe Margin; kleine Folgekonto-Slots tragen Slippage-/Abweichungsrisiko. Ertrag 63,79 %/Monat weit über Zielwert, jedoch gekoppelt an dieses versteckte floating Risiko.

**3. Fazit**
Warnung: Der monitorseitig gemessene Equity-DD (22,73 %) liegt rund zehnfach über der Anbieterangabe (2,16 %) — die Reported-Metrik ist für Risikoentscheidungen allein nicht belastbar (Ampel der Engine bleibt unverändert).

--- ANALYSE gesamtbericht (id=912, model=glm-5.3, tokens=21711, at=2026-09-30 02:47:15, basis=3c5e420b389325db78863ddd45641908b2b73d6ffa5a5390dfc969c5b9ebc945) ---
Kurzfassung: Vollautomatischer Grid-EA auf AUDCAD ohne individuellen Stop; nachgemessener Equity-DD (22,73 %) rund zehnfach über Anbieterangabe, aber unter der 30-%-Schranke — Watchlist.

## 1. Was ist das für ein Trading-Algo?

Der Kandidat Mr_Profit_FX (ID 2052727, Pelican, 50 Wochen, 63 Abonnenten) handelt zu 100 % AUDCAD — 1.469 Trades, ca. 29 pro Woche. Es liegt ein hochmechanischer Mean-Reversion-Grid-Roboter mit korbbasiertem Exit vor.

**Einstiegslogik:** schichtweises Nachschieben in Verlustrichtung innerhalb eines Korridors. Die Januarkorb-Serie belegt es explizit: Sells wurden nachlaufend addiert (22.01. 00:45, ep 0,93809; 22.01. 16:00, ep 0,94186; 23.01. 07:54, ep 0,94376). Das Layering erfolgt mit engem statt weitem Grid-Spacing: je fünf Opens auf nahezu identischem Niveau am 11.11. 07:45 (ep 0,91466–0,91471) und am 23.01. (ep 0,94368–0,94406).

**Exit-Logik:** kein individueller Stop-Loss; Realisierung auf Korb-/Kontoebene bei Erreichen einer Gewinnschwelle, vermutlich mit Trailing. Alle 15 Legs des Januar-Korbes wurden simultan am 29.01. 15:20 bei 0,9473–0,9474 geschlossen; der größte Korb (18 Sell-Legs, eröffnet 07.–10.04.) lief auf einen einzigen Close-Zeitpunkt (12.04. 21:01, xp 0,9741) und endete netto +32,78 USD.

**Automatisierungsgrad:** sekundengenaue simultane Multi-Opens, minutengleiche Basket-Closes, konstante Richtung pro Regime, ein einziges Symbol — EA-typisch. Einzig das totale Richtungs-Clearing am 29.01. könnte manuell sein, ist aber auch regelbasiert erklärbar.

## 2. Wie handelt das System?

**Positionsgrößen** flach mit leichter Anhebung: 1.139× 0,01, 325× 0,02, nur 5× 0,04 Lots. Keine systematische Eskalation — konsistent mit martingale_flag = false; die 0,02er-Legs stehen u. a. im größeren August-Korb (dort die schlechtesten Trades mit −11,97 USD).

**Haltedauer:** Median 17,1 h, P90 132 h, Maximum 271,5 h. Gewinne werden beim Korb-Flush realisiert; Verluste laufen ungebrochen lange mit.

**Session-Muster:** Einstiege über 24 h verteilt, Häufungen 01–02, 06–08 und 13–15 Uhr (15 h = 127, 7 h = 103, 6 h = 98 Einstiege) — asiatische Session plus London-Vormittag, kein News-Muster.

**Monatsverlauf:** Alle 11 Monate positiv (45,49 bis 221,82 USD, netto gesamt +1.154,38 USD). Winrate 73,6 % bei avg_win +2,05 USD gegen avg_loss −2,73 USD (Erwartungswert ≈ +0,79 USD/Trade). Verluste entstehen ausnahmslos in Trendphasen gegen die Korbrichtung: die Serie von −52,78 USD fiel mit dem AUDCAD-Anstieg 0,9335 → 0,9588 zusammen; dasselbe Setup von der anderen Korridorseite brachte den besten Trade (+8,72 USD in 9,8 h).

## 3. Risikoanalyse

Drawdown im Überblick:
- **Trading-DD** (geschlossene Trades, Engine): 0,66 % (68,11 USD)
- **Plattform-EQ-DD** (gemeldet): 2,16 %; Balance-DD nicht gemeldet
- **Reko-EQ-DD** (equity_dd_rekonstruiert_pct): null — keine belastbare Kursdaten-Rekonstruktion verfügbar, formal offen
- **Monitor-Zweitmessung** (monitor_trade_eq_dd_pct): 22,73 %

**Kernbefund:** Die Monitor-Messung aus der vollen Trade-Kurve liegt mit Faktor ≈ 10,5 über dem gemeldeten Wert (22,73 % vs. 2,16 %; Kernbefund ab Faktor 2). Plausibel erklärbar durch floating Verluste von bis zu 70 offenen Positionen, die im Trading-DD unsichtbar bleiben. Widerspruchslösung: Plattformmetrik und Monitor-Messung divergieren; zugunsten der maschinellen Forensik wird die konservative Monitor-Messung angesetzt. Die Trade-Analyse hatte die 2,16 % zitiert — für Risikoentscheidungen überholt.

**Schrankenprüfung:** Das Maximum aller verfügbaren Messungen (22,73 %) liegt unter der harten 30-%-Schranke — keine Verletzung, konsistent mit der Engine (schranke_verletzt = false, Ampel grün). Eine Rekonstruktion über der Schranke wäre ein hartes Ablehnungskriterium — sie liegt nicht vor; die Monitor-Messung verbraucht jedoch rund drei Viertel des Limit-Budgets.

**Verlustserie:** 15 Verluste in Folge, kumuliert −52,78 USD. **Peak-Exposure:** 70 gleichzeitige Positionen bei netto −0,94 Lots; Schockszenario 3.390,47 USD ≈ 31,01 % des Peak-Kontos (10.932,56 USD, 26.08.2026 23:15). Der größte dokumentierte Einzelkorb umfasste 18 Legs — 70 offene Positionen sprechen für überlappende Körbe. Das Schockszenario ist Stressgewichtung, kein gemessener Verlust und allein kein Ablehnungsgrund; dass es prozentual über der 30-%-Marke liegt, verschärft gleichwohl die Warnung.

**Martingale:** nein (flag false, keine Evidenz). **Stop-Loss:** kein Nachweis — per bindender Regel neutral, kein Malus. Verhaltensbasierte Einschätzung: Verlustdistanzen streuen breit (Median 20,9 Pips, Max 142,5 Pips; häufigstes Level nur 6× bei 14,4 Pips), ein konsistenter Cut-Off fehlt, Verluste laufen bis 271,5 h. Begründete Einschätzung: wahrscheinlich ohne individuellen Stop-Schutz; einzige Risikokontrolle sind gewinngetriebene Korb-Exits. Dies geht als gewichtender Befund ein, nicht als hartes Kriterium.

## 4. Copy-Eignung

Die Kapitalbasis ist virtuell: 10.000 USD sind eine Annahme der Datenquelle; reale Nachbildbarkeit ungewiss (Peak-Konto 10.932,56 USD). 70 gleichzeitige Positionen erfordern hohe Margin und lassen sich auf kleinen Folgekonten wegen der 0,01-Lot-Granularität nicht proportional abbilden — Slippage- und Abweichungsrisiko steigt. Broker/Server nicht dokumentiert, Abo-Preis nicht ausgewiesen.

**Ertrag:** Der Datensatz weist 63,79 %/Monat aus (weit über der 5-%-Schwelle). Hinweis auf einen zweiten Widerspruch: Die rekonstruierten Monatssummen (45,49–221,82 USD) ergeben auf der virtuellen 10.000-USD-Basis nur ca. 0,5–2,2 %/Monat. Für den formalen Ertragstest bleibt das Engine-Feld maßgeblich; unter der konservativen Lesart wäre das Minimum allerdings verfehlt (Folge: Beobachtung, keine harte Ablehnung). Beide Lesarten tragen höchstens WATCHLIST.

## 5. Urteil

**WATCHLIST**

**Risiko-Score (LLM-Urteil): 7/10**
**Engine-Risiko-Score: 4,8** (Kandidaten-JSON; Ampel grün, Forensik bestanden, keine Schrankenverletzung). Beide Werte getrennt ausgewiesen, nicht vermischt.

Die drei wichtigsten Gründe:
1. **Kernbefund Drawdown-Reporting:** 22,73 % (Monitor) gegen 2,16 % (gemeldet), Faktor ≈ 10,5 — die Anbietermetrik ist für Risikoentscheidungen allein nicht belastbar; die formale 30-%-Schranke bleibt gewahrt.
2. **Grid-/Korbsystem ohne nachweisbaren individuellen Stop-Schutz** (Einschätzung: wahrscheinlich ohne) bei bis zu 70 Positionen und einem Schockszenario von 31 % des Peak-Kontos; das Schwanzrisiko eines Korridor-Bruchs ist in der Historie nicht realisiert und in den Kennzahlen daher unterschätzt.
3. **Copy-Praxis:** virtuelle Kapitalbasis, unbekannter Broker, nicht abgestimmte Ertragsangaben sowie Margin- und Slippage-Risiko bei der Nachbildung.

Die Engine-Ampel (grün) wird respektiert und nicht aufgewertet; WATCHLIST ist die nach der Regel „Risiko vor Ertrag“ gebotene Vorsichtsstufe.

## 6. Bedingungen

Hin zu EMPFEHLUNG:
- Belastbare Rekonstruktion des EQ-DD (equity_dd_rekonstruiert_pct mit Kursabdeckung), die klar unter 30 % liegt.
- Konvergenz von gemeldetem und nachgemessenem Drawdown (Faktor < 2) über längere Beobachtung.
- Nachweis einer realen Kapitalbasis, Broker-Transparenz und ein stimmiges Ertragsbild.
- Keine Annäherung des Monitor-DD an 30 %; idealerweise dokumentierte harte Limits (max. Positionen/Lots, Korb-Stop).

Hin zu ABLEHNUNG:
- Nachgemessener oder rekonstruierter EQ-DD von 30 % oder mehr.
- Auftreten einer Martingale-Signatur.
- Realisierter Korridor-Bruch mit unkontrollierter Verlustrealisierung, erkennbar an einer Verlustserie deutlich außerhalb des bisherigen Musters.
