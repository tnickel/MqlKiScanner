# Broker-Kurslücken: Folgeprüfung vom 10.10.2026

Folgeprüfung zum [96-Zellen-Audit](vantage_zellen_2026-10-10.md): Dessen historische Snapshots bleiben erhalten; die dort genannten FX-Blocker sind inzwischen teilweise behoben.
Live geprüft wurden TickmillLifeMql5, ActiveTrades003 und Vantage: 21 Studien (7 Signale × 3 Broker), anschließend 6 Wiederholungen nach ActivTrades-Aliasfix und 1 Grenzfallprüfung. Die ausgewählten Studien wurden vom Hauptlauf gespeichert; dieser Bericht wurde ohne weitere Datenbankänderungen oder MT5-Aufrufe erstellt.
BCHUSD und USDCNH liefern bei allen drei Brokern Kurse. BCH wird mit zeitgleichen BCHUSD-H1-Schlusskursen desselben nachgewiesenen Terminalfeeds umgerechnet; CNH nur bei USDCNH mit dem Kehrwert des eigenen zeitgleichen Schlusskurses. Fehlende Zeitpunkte bleiben Lücken. Die EZB-Tageskurs-API und Kapitalflussumrechnung bleiben unverändert.
ActivTrades-Goldnamen wurden ergänzt; WTI und Brent werden getrennt zugeordnet. Die drei portablen Terminals wurden live verifiziert; Kurscache und Wiederholung leerer Abrufe berücksichtigen das Terminal. Verifikation: 225 gezielte Tests bestanden; 77 überlappende betroffene Tests nach den letzten Änderungen erneut bestanden.

| ID | Signal | Gespeicherte Abdeckung | DD % auf virtueller 10.000-USD-Basis | Endzustand / verbleibender Blocker |
|---|---|---:|---:|---|
| 964411 | PHOENIXMYTHFUNDS | 100 % | 8,217630 | Zuverlässig; ActivTrades-Messung gespeichert. |
| 1096166 | the best one | 6,1 % | 0,178944 | Unzuverlässiger Teilwert; BCH-/CNH-Lücken geschlossen, Zeitwechsel und Preis-/Zeitzuordnung weiter nicht belastbar. ActivTrades fehlen zusätzlich Aktienkurse. |
| 178177 | Rohan Gupta 40000121 | 50,8 % | 129,952930 | Unzuverlässiger Teilwert; CNH-Lücke geschlossen, Zeitwechsel und Preis-/Zeitzuordnung weiter nicht belastbar. ActivTrades fehlen zusätzlich FT-Instrumente. |
| 954691 | TRADE EASY 4YOU 2 | 94,96644295302013 % | 16,886995 | Unzuverlässiger Teilwert ausschließlich wegen Abdeckung unter 95 %; Zeitbasis bestanden. Anzeige rundet auf 95,0 %, die Entscheidung verwendet den Rohwert. |
| 538344 | Rebounds | — | — | Keine belastbare Rekonstruktion: Zeitabbildung nicht monoton/eindeutig. |
| 998837 | Bet with Akedang | 86,4 % | 249,774105 | Unzuverlässiger Teilwert wegen Abdeckung unter 95 %; bisherige Studie behalten. |
| 1052261 | Bullions | 90,3 % | 4,307264 | Unzuverlässiger Teilwert wegen Abdeckung unter 95 %; bisherige Studie behalten. |

Die Teilwerte sind keine freigegebenen Konto-Equity-DD-Messungen. Fehlende EUR-/HKD-Trade-Exporte anderer Signale bleiben ein separater Datenblocker: vorhandene Umrechnungskurse ersetzen keinen Export. Die historischen 37 sichtbaren Zellkorrekturen werden hier nicht neu hochgerechnet.
Belege: [Umrechnungskurse](broker_umrechnungskurse_2026-10-10.json), [ActivTrades-Instrumentnamen](activtrades_instrumentnamen_2026-10-10.json), [21 Studien](broker_studienvergleich_2026-10-10.json), [6 Alias-Nachprüfungen](broker_studienvergleich_nach_activtrades_aliasen_2026-10-10.json), [Grenzfall einschließlich korrigiertem Diagnosewortlaut](broker_studie_grenzfall_2026-10-10.json).
