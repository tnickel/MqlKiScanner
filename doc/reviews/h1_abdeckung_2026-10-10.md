# H1-Abdeckung: konkrete Ursachen und Korrektur

Offlinevergleich realer Vantage-CSVs mit dem vom Hauptlauf gespeicherten ActivTrades-H1-Cache, ohne MT5-Aufrufe oder Datenbankänderungen. [Maschinenlesbare Belege](h1_abdeckung_2026-10-10.json) enthalten fehlende Zeitpunkte, betroffene Positionen und die beidseitigen realen Bars der Pausenheuristik.

| Signal | Vorher: gemessene / erwartete aktive Stunden | Nachher | Ergebnis auf virtuellen 10.000 USD |
|---|---:|---:|---|
| Bet with Akedang #998837 | 789 / 913 = 86,4184 % | 789 / 815 = 96,8098 % | Zuverlässige H1-Messung; DD 250,814380 %. |
| Bullions #1052261 | 121 / 134 = 90,2985 % | unverändert | Weiter unzuverlässig; Teil-DD 4,322829 %. |
| TRADE EASY 4YOU 2 #954691 | 3962 / 4172 = 94,9664 % | 3962 / 4169 = 95,0348 % | Zuverlässige H1-Messung; DD 16,886995 %. |

Der Fehler lag im gemischten Markt-Raster: BTCUSD-Bars während eines Goldwochenendes verhinderten die bisherige globale Erkennung langer Handelspausen. Bei Bet betraf das insbesondere 14.–15. März und 25.–26. April. Die vorhandene ≥20-Stunden-Heuristik wird jetzt je Symbol angewendet; nur zwischen zwei tatsächlich vorhandenen Bars und nur wenn **alle gleichzeitig aktiven Symbole** pausieren, entfällt die Stunde im Nenner. Eine aktive BTC-Position hält die Stunde im Nenner, auch bei fehlendem BTC-Kurs. Der Bericht nennt Symbol, begrenzende Bar-Endzeiten und ausgenommene Stunden. TRADE gewinnt netto nur drei Stunden; Feiertagsstunden mit gleichzeitig aktivem FX bleiben berücksichtigt. Die 95-%-Schranke und die gemessenen DD-Werte wurden nicht verändert.

Bullions fehlen genau 13 Gold-Bar-Endpunkte um 00:00, etwa am 8. April bei einer Position vom 7. April 22:31:34 bis 8. April 00:01:00. Das sind kurze Lücken; ohne belegten Handelssitzungsplan dürfen sie nicht als geschlossene Marktzeit ausgenommen werden. M1-/Tickdaten desselben Feeds oder belastbare Sessiondaten sind der nächste Nachweis, kein Forward-Fill.

Die 117 Bet-, 332 Bullions- und 28 TRADE-Positionen ohne H1-Floatingpunkt sind davon getrennt: Ihre Laufzeit enthält keinen vollen Stundenpunkt. Beispiele: Bet 17. Februar 15:03:33–15:07:20 (227 Sekunden), Bullions 11. März 05:54:08–05:54:30 (22 Sekunden). Sie fehlen nicht im Kursdownload, sondern sind auf H1 zeitlich nicht auflösbar; ihr realisiertes Netto bleibt enthalten. M1 hilft längeren Kurztrades, für einen vollständig zwischen zwei Minutenpunkten geschlossenen Trade sind Ticks nötig. H1-Zuverlässigkeit bleibt eine Aussage über H1-Schlusskurse, keine vollständige Intrabar-Messung.

Die lange Bar-Lücke bleibt ausdrücklich eine Heuristik: Ohne Sessionbeleg lässt sie sich grundsätzlich nicht sicher von einem langen Datenloch unterscheiden. Sie wurde begrenzt und auf die tatsächlich aktiven Instrumente korrigiert. Verifikation: 65 betroffene Tests bestanden, einschließlich gemischtem Gold-/BTC-Raster, aktiver BTC-Gegenprobe, kurzer und unbegrenzter Lücke sowie Kapitalflüssen.

Nachprüfung der Allgemeingültigkeit: Die Regeln enthalten keine Signal-IDs. Eine zusätzliche Lücke war der getrennte manuelle Studienpfad: Er verwendete zuvor nur EZB-Tageskurse und die alte globale Pausenerkennung. Workflow-Rekonstruktion und manuelle Studie verwenden jetzt denselben H1-Umrechnungshelper und dieselbe aktive Symbol-Pausenerkennung. Direkte BCH-/ETH-Quotes gelten für jedes Instrument mit belegtem Kontrakt und synchronem Umrechnungskurs desselben Feeds; CNH bleibt ausschließlich durch den eigenen USDCNH-Kehrwert belegt. Kapitalflussumrechnung und die jeweiligen Zeitbasis-/Kurvenverfahren bleiben getrennt. 109 betroffene Tests bestanden, darunter beide Pfade mit synthetischem XRPBCH/SOLETH, mehreren gegenläufigen Trades, fehlenden Kurszeitpunkten und aktivem BTC während einer Goldpause.
