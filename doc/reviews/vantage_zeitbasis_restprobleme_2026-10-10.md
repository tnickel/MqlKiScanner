# Vantage: verbleibende Zeitbasis- und Preisprobleme, 10.10.2026

Diagnose aus gespeicherten Trade-CSVs und dem am 10.10.2026 portabel ausgelesenen Vantage-H1-Cache. Diese Prüfung verwendet ausschließlich Dateien und SQLite im Lesemodus; keine Live-MT5-Aufrufe und keine Studien-Neuberechnung in der Produktionsdatenbank. Maschinenlesbare Belege stehen in `vantage_zeitbasis_restprobleme_2026-10-10.json`.

## Rebounds #538344

Trade-CSV: `data/trade_snapshots/9478e521c32c743e0e28295afb6a5e36d246611e12dff0772b7c29eb08fc54b0.csv`.

| CSV-Zeile | Symbol | Open-Zeit im Export | Open-Preis | Wochen-Shift | Gemappte Referenzzeit |
|---|---|---|---|---|---|
| 362 | GBPCHF | 26.07.2026 23:09:49 | 1,09063 | +2 h | 27.07.2026 01:09:49 |
| 345 | GBPCHF | 27.07.2026 00:00:00 | 1,08954 | +1 h | 27.07.2026 01:00:00 |

Die Reihenfolge wird um **589 Sekunden** umgekehrt. Die Modellgrenze liegt am 27.07.2026 00:00:00 der CSV-Zeitachse. Der Export enthält naive Zeitstempel; die gemappte Zeit ist die Referenzkurszeit, kein unabhängig bestätigter UTC-Zeitstempel des Signalbrokers.

Die lokalen Gewinner +2 h vom 22.06., 20.07. und 24.08. erreichen 23/23, 34/34 und 28/28 Treffer. +1 h erreicht jeweils 22/23, 33/34 und 27/28: nur eine zusätzliche Preisprobe entscheidet den Wochenwechsel. Das beweist nicht dessen exakten Zeitpunkt. Insgesamt meldet das Vantage-Modell 80 über unsichere Wechsel laufende Positionen und 18 unsichere Preisereignisse. Ein erzwungenes +1 h oder eine willkürlich verschobene Wechselgrenze wäre keine belegte Korrektur. Der Skip bleibt bestehen; die Fehlermeldung benennt jetzt das erste konkrete Gegenbeispiel.

## the best one #1096166

Trade-CSV: `data/trade_snapshots/4ca63341384d12b37af0674355ab94548f227a0a468dc3c168e70b566ac134da.csv`.

BYND hat bei derselben Open-Zeit 25.03.2026 18:43:09 unterschiedliche Preismaßstäbe:

| CSV-Zeile | Lots | Open | Close | Close-Zeit |
|---|---|---|---|---|
| 127 | 5,4 | 0,72 | 0,88 | 17.04.2026 16:11:35 |
| 154 | 2,4 | 0,72 | 0,42 | 14.08.2026 01:42:37 |
| 155 | 0,2 | 21,60 | 12,85 | 19.08.2026 16:34:10 |

21,60 / 0,72 = **30**. Für den Open-Zeitpunkt mit erkanntem +2-h-Shift liefert Vantage H1 Low/High 19,20–19,50; für den Close von Zeile 127 mit +1 h 25,80–28,20. Eine Zeitzonenänderung korrigiert keinen solchen Preismaßstabkonflikt.

**Herkunft geklärt:** Bereits `../vantage/data/trades/trades_1096166.csv`, Zeilen 127/154/155, enthält diese Lots und Preise mit identischer Open-Zeit einschließlich `.375` Millisekunden. Der Scanner-Snapshot hat die Werte unverändert übernommen. `../vantage/src/main/java/de/vantagemonitor/rest/RestApiServer.java`, Methode `mql5Zeile` (Zeilen 486–499), schreibt Open-/Close-Preis direkt aus dem TradeRecord; nur Netto-PnL erhält den Währungsfaktor. Damit ist ein durch den REST-Exporter erzeugter Preismaßstabwechsel widerlegt. Ob Corporate Action, vorgelagerte Aggregation oder Providerdaten die gemischte Basis verursachen, ist hier nicht bewiesen. Eine Split-Korrektur allein aus Faktor 30 wäre geraten und wird nicht vorgenommen.

Zusätzlich liegen 50 Positionen über der unbelegten Wochenwechselgrenze 30.03.2026 00:00:00 (+2 auf +1 h), etwa NAS100 CSV-Zeile 34 vom 27.03.2026 21:22:20 bis 30.03.2026 05:05:49. H1-Abdeckung: 6,1 %; 11 unsichere Preisereignisse. Der Befund bleibt unverlässlich.

## Rohan Gupta #178177

Trade-CSV: `data/trade_snapshots/ded562719204af3799798084442b2c7b1759643cc42507659df7d0dcca44dd84.csv`.

Die Ereignisabbildung bleibt monoton. Im Vantage-Offlinecache wurden keine Preisereignisse jenseits der harten Ausreißerschwelle gefunden. Dennoch meldet das Modell 56 offene Positionen über nicht exakt belegten Wechselgrenzen und 43 unsichere Preisereignisse; Abdeckung 50,8 %.

Beispiel: XAUUSD CSV-Zeile 49, Open 29.10.2023 23:40:45, Close 30.10.2023 15:29:32, überquert die Modellgrenze 30.10.2023 00:00:00 (+1 auf +2 h). HK50ft Zeilen 50/51 laufen ebenfalls über diese Grenze. Weitere Modellwechsel liegen unter anderem am 11.03.2024 und 01.04.2024. Wochenweise passende Open-/Close-Preise belegen nicht die Zeitabbildung aller dazwischenliegenden Stunden. Deshalb keine Freigabe als zuverlässiger RetDD-Nenner.

## Unveränderte Schutzgrenzen

- H1-Abdeckung mindestens 95 % des ungerundeten Werts; gerundete 95,0 % allein reichen nicht.
- Lokaler Offset: mindestens drei unabhängige Preisproben, eindeutiger Gewinner, mindestens 90 % Treffer. Global mindestens 60 % Treffer, kein gleichwertiges Plateau.
- Preisvergleich mit 0,1 % relativer Toleranz; Abstand größer als zehn Toleranzen widerlegt die Zeitbasis hart. Kleinere Nichttreffer bleiben Messlücken.
- Nichtmonotone Ereignisabbildung und offene Positionen über unbelegte Wechselgrenzen bleiben Sperren. Die neue Diagnose verändert weder Offsetwahl noch Messfreigabe, DD oder RetDD.
- H1-Schlusskurse belegen keine Intrabar-Extrema und keine aktuell offenen Positionen außerhalb des Exports.
