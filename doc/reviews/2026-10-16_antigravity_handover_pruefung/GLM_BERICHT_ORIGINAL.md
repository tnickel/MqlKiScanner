# Gesamtsystem-Review SignalKiScanner + 5 Quellprogramme — Bericht (A–G)
Datum: 2026-10-16 · Detailnachweis je Befund: siehe `REVIEW_2026-10-16_Gesamtsystem_Befundkatalog.md` (gleiche ID-Nummerierung MDL/ROB/ZUL/VAN/FIN/FLT/LLM/SYN/F).

Methode: 7 parallele Teil-Reviewer (MqlDownloader; RoboForex+Zulu; Vantage; Finanzmathematik; Filter/Ampel; LLM/Agenten; Scanner-REST/Persistenz) + eigene Kernprüfung (Pelican-Delta seit Vormittags-Review, Quellenidentität, §8-Defaults, Live-Sonden). A-Befunde der Teil-Reviewer vom Hauptreviewer stichprobenartig am Code/live nachgeprüft (im Katalog mit ✅ markiert). Nur lesend; keine produktiven Daten geändert; keine kostenpflichtigen Modellaufrufe.

## A. Geprüfter Stand und Abdeckung

| Repo | Branch · Commit · Baum | Tests (frisch) |
|---|---|---|
| SignalKiScanner | main · 80d4692548c9 · sauber | pytest: 1914 grün, 1 rot (reihenfolge-abhängig; s. S7) |
| MqlDownloader | master · 92d8f9cea10b · sauber | mvn test: 105/105 |
| PelicanTrading | master · dde77d705a67 · sauber | mvn test: 176/176 |
| roboforex | master · 42b268641ad3 · sauber | mvn test: 147/147 |
| vantage | master · 1fe395805f29 · sauber | mvn test: 49/49 |
| zulumonitor | master · 72df0cf49aa4 · sauber | mvn test: 107/107 |

Alle = Soll-Stände des Dokuabgleichs. **Laufzeit-Hinweis:** die 5 Monitor-Prozesse starten ~10:50; PelicanTrading läuft auf älterem Code als dde77d7 (live am url-Feld bewiesen) — heutige Fixes dort wirken erst nach Neustart. Live-Sonden: Health aller 5 Quellen + Scanner-REST :8611 (Token verifiziert), Katalog-/Tradelisten-Stichproben je Quelle.

**Nicht geprüft (D):** Plattform-Direktabgleiche (Pelican-API 401 mit Cookie-Datei; übrige Websites gar nicht), Selenium-Login-Flows live, GUI-Bedienung, LLM-Antwortqualität live, externer MqlTradeMonitor (nur Scanner-Seite), MqlRealmonitor/PelicanWinnerLooser (nicht produktiv eingebunden, keine Integration gefordert), fremde KI-Berichte (bis auf Pelicans internes Prüfdoc nicht abgeglichen).

## B. Architektur und Datenfluss

5 Java-Monitore spiegeln je Plattform über das Protokoll „mql5-downloader-v1" (health, providers, history, trades.csv im MQL5-11-Spalten-Format, metrics, reports, POST /update → Login→Katalog→Tradelisten mit 3-Tage-Regel). Scanner: Stufe 0 stößt Updates an → Katalog-Sync (katalog_signale, PK quelle+signal_id) → Kandidaten (Vorfilter 26 Wochen/0 Abonnenten, Top-30 je Quelle nach Abonnenten, Fix-IDs umgehen Vorfilter ohne Slot) → Forensik v16 → Ampel (⛔→Martingale→Kapitalbasis→DD-Schranke max. 5 Kanäle >30 %→Ertrag→≥3 Monate→Jahres-Calmar ≥3) → Berichte/Portfolio → Scanner-REST (8611, Token) + Tradeserver-Sync. Doppelpfad MQL5: eigener Browser-Crawler neben dem MqlDownloader (dokumentiert). Quellenidentität: `signals.signal_id` alleiniger PK (bekannte Einschränkung, Quelle wird nie still überschrieben, R1-Review); **Realdaten: keine ID-Kollision über Quellen**. Offen: SYN-3 (mql4+mql5 derselben ID überschreiben sich, Last-wins).

## C. Doku-/Code-Abgleich

Verifiziert korrekt: alle 12 §8-Soll-Regeln aus Code+Konfiguration (Grenzfälle exakt: >30, ≥3.0, 91,31 Tage, 26 Wochen bestanden); README zu target-Ignore (Pelican/MqlDownloader); MQL5-Vollständigkeit ehrlich nicht zugesagt.
Aktuell falsch mit Produktionswirkung: LLM-1/LLM-2-Altregeln in produktiven Prompts; Hilfe-Text „Monatsbudget begrenzt" (wirkt nicht, LLM-3); REST-Docstring „liest ausschließlich DB" (SYN-4 schreibt PDFs).
Historisch/geplant sauber getrennt: doc/20 Stufe 2 (Composite-Identität) offen; „Weeks" wird zur Requestzeit berechnet.

## D. Kennzahlenmatrix (Kern)

- Winrate (Scanner): wins/alle Trades, Break-even neutral, brutto — Anzeige.
- Profitfaktor: brutto; nur Verluste→0.0, nur Gewinne→None — Anzeige.
- ertrag_monat_geom/CAGR: expm1(ln(End/Start)/Monate), TWR bei Flüssen, exakte Sekundenspanne — Ertrag-Gate ≥0; CAGR→Calmar.
- TrueRetDD/Calmar (Jahr): CAGR ÷ floating-inkl. H1-Equity-DD (nur Kursmessung, gleiche Kapitalbasis) — **Grün-Gate ≥3**.
- DD-Schranke: max(5 Kanäle: Plattform-EQ, Plattform-Balance, Trading-DD geschlossen, Kurs-DD [nur verlässlich], Monitor TradeEqDrawdownPct) > 30 → kein Grün.
- Virtuelle 10k-Basis: markiert, fließt in DD %/Calmar (Nutzer-Entscheid).
- Average3MonthProfit: je Quelle anderes Fenster (Pelican Ø aller Monate; Vantage 30 Tage; MQL5 Ø 3 Vormonate) — Feld mit drei Bedeutungen (VAN-9).
- Equity-Reko: H1-Schlusskurs-DD, GMT-auto, ≥95 % Abdeckung, Marktpausen exkl. — Calmar-Nenner ist **Untergrenze** (FIN-6).
- 8 unabhängige Nachrechnungen (Sandbox): alle exakt; kein Rechenfehler mit falscher Ampel.

## E. Priorisierte Findings (Systemik; Einzelnachweise im Katalog)

- **S1 Tradelisten-Freeze (A, P0, live bewiesen):** VAN-4 (Register ohne TTL, 08.10.), ZUL-1 (SHA-only, geladenAm ungenutzt, 07.10.), ROB-1 (Deals SHA-only, 26.09.), Pelican im Code gefixt aber Instanz alt (29.09.); MDL-1 verwandelt Login-Fehler in „done"+72-h-Sperre. Einzig MqlDownloader aktualisiert (5-Tage-Delta).
- **S2 Monitor-DD-Basen (P1/P2):** ROB-3 (Flüsse in Basis → DD zu klein), ZUL-2 (ROI-Rückrechnung, GUI-Tiefe persistiert), ZUL-3 (0.0 statt null), VAN-6 (Fenster/Gesamt-Mix, live 59,3 % vs 0,39 %), VAN-3a.
- **S3 LLM/Cache (P1/P2):** LLM-1 (retdd_monat<1-Alttext), LLM-2/FLT-1 (Score<5-Alttext), LLM-3 (Monatsbudget ohne Durchsetzung), LLM-4 (Token-Buchungslücken/Parallel-Budgets), SYN-1/FLT-2 (report_basis ohne min_calmar_jahr), SYN-2 (Studien ohne Forensik-Version), LLM-7 (REST-Ampel-Semantik unausgewiesen).
- **S4 Auswahl vor Bewertung (P2):** FLT-4 (Top-30 nach Abonnenten), VAN-1 (degenerierte Katalogvereinigung), MDL-5 (MQL5-Stichprobe), MDL-4 (kein ≥1-Default; Scanner vertraut Provider-Defaults), ROB-6, FLT-3 (Teilscan-⚪-Falle), ROB-5 (Yield≤300 %-Filter).
- **S5 Identität (P2/P3):** SYN-3 (mql4/mql5 Last-wins), MDL-11, Pelican F-3 (winrate wins/tradesTotal — Website-Abgleich ausstehend).
- **S6 DD-Untergrenze (P2):** FIN-6 (H1-Schluss, offene Positionen am Ende, Bid-Kurse).
- **S7 Testgesundheit (P2):** Volllauf reihenfolge-abhängig (2 Läufe, 3 verschiedene, je einzeln grüne Fehler).
Korrekt bestätigt (Auswahl): Finanzkern exakt; Gate-Grenzfälle; FORENSICS_VERSION-Mechanismus; SHA/BOM-konsistente Caches; atomares Schreiben + Lauf-Lock; Token+Pfadsicherheit in allen 6 RESTs; USC ÷100 in 4 Monitoren; FX historisch ohne Zukunftskurse; Fix-ID-Mechanik.

## F. Fachliche Bewertung der Signalauswahl

Optimiert wird: ≥26 Wochen Track-Record, ≥1 Abonnent (bis auf MQL5-Lücke), Top-30 je Quelle, Jahres-Calmar ≥3 bei DD ≤30 % (max. 5 Kanäle), ohne Martingale-Muster, ohne Ausschluss. Belastbar: alle Kernformeln, Gate-Logik, Ehrlichkeits-Mechanismen — die Rangfolge innerhalb der bewerteten Kandidaten ist formal korrekt. Risiko-Unterschätzung, geordnet: (1) S1-Freeze (der Tokyo-Mechanismus ist aktuell in 4 von 5 Quellen aktiv — fehlende Crashs machen Ampeln zu positiv); (2) H1-Schluss-DD als Untergrenze (+ virtuelle 10k-Basen bei Mikro-Konten); (3) S2-Monitor-DD-Kanal; (4) Plattformrendite ≠ kopierbare Netorendiste (Fees/Slippage/Latenz ungemessen; Commission=0 bei 3 Quellen plattformbedingt); (5) Schwellen (3/30/26) sind Projektregeln ohne OOS-/Walk-forward-Validierung (Selektion über ~1.200 Kandidaten). Zu früh gefiltert: renditeeffiziente Neueinsteiger (Top-30 nach Abonnenten), <26 Wochen (bewusst), Vantage-Return-Phase, MQL5-Stichprobenordnung, Teilscan-⚪-Fehler. Portfolio: Korrelation nur Anzeige, gemeinsame Verlustphasen nicht erzwungen. Aussagegrenze: „Beste Signale" tragfähig als Rangfolge unter frisch gemessenen Kandidaten — Voraussetzung S1-Fix; keine Aussage über zukünftige Gewinner.

## G. Priorisierter Korrekturplan

1. **Akut (P0/P1):** Freeze-Fixe VAN-4/ZUL-1/ROB-1(+ROB-2) nach Pelican-Vorbild (Delta-Fenster letzter Handelstag→heute, nur-if-stale) + **Neustart aller Monitore** (macht auch Pelicans heutige Fixes wirksam); MDL-1 (Fehler→`error`, Vermerk nur bei Erfolg, LOGIN_REQUIRED setzen); LLM-1/LLM-2 (zwei Ein-Zeilen-Promptfixes); LLM-3 (`budget_rest()`-Helper an 6 Stellen + Dirigent-Text).
2. **Wichtig (P2):** DD-Basen ROB-3/ZUL-2/ZUL-3/VAN-6/VAN-3a; SYN-1 (+Prompt-Hash optional); SYN-2; SYN-3; SYN-4; MDL-2/3/4; VAN-1/8/9 (metricsWindow-Feld); FLT-3; FLT-6; LLM-4; S7-Testpollution; FIN-7 (Currency parsen); FIN-6 (Untergrenzen-Hinweis).
3. **Später/Doku (P3):** MDL-5/8/9/11/12, ROB-4/5/6/10, SYN-5…12, LLM-5/6/9/13, FLT-4-Doku/5/7/9/12, VAN-7/11, FIN-5/8/10; Pelican F-3 per Website-Abgleich klären; MQL5-≥1-Default entscheiden.
