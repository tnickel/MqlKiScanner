# RoboForex: Gewinn und Rendite als Quellenwerte anzeigen

Auftrag 23.10.2026: „dann mache das mal für roboforex“ nach der Klärung,
dass Prozent-Renditen bei gleicher Geldskalierung von Cent/Standard unabhängig
sind. Die bisherige Tradeforensik-Sperre darf ausgewiesene Ratingwerte nicht
pauschal verbergen.

## Umsetzung

`abonnenten_analyse_daten.robo_quellenwerte` übernimmt ausdrücklich benannte
`ProfitUsd`, `RatingBalanceUsd`, `YieldWindowPct` und dessen `YieldWindowMonths`.
0 Monate bezeichnet den Gesamtzeitraum laut Quelle. Negative Gewinne und
Renditen bleiben erhalten; Null ist kein fehlender Wert. Boolesche, nicht
numerische und nicht endliche Zahlen werden nicht als Finanzwerte verwendet.
Es wird weder aus Gewinn/Restbalance eine Rendite erfunden noch ein Jahres-
oder Monatswert aus dem gelieferten Ratingfenster abgeleitet.

Robo verwendet den vorhandenen lokalen Metrics-GET mit deaktiviertem Offline-
Fallback. Anbieter-/Versionsidentität werden geprüft. Kein gezielter
Plattform-Refresh, kein Tradeexport, kein Terminal, keine Forensik oder KI
wird dadurch gestartet. Ein Lesezeitpunkt ist ausdrücklich kein Nachweis des
Datums der Finanzwerte; die Quelle liefert dafür derzeit keinen Zeitstempel.

Ergebnisse haben `auswertung_typ=quellenprofitabilitaet`, `status=quellenwerte`
und `eligible=false`. Sie werden als fertig gelesen gezählt und können ohne
Trade-Snapshot fortgesetzt werden. Eigener gemessener Equity-DD, RetDD und
bekannte normalisierte Tradeanzahl bleiben unbestimmt. Die bestehenden
CSV-/Einheitenschutzregeln der nativen Tradeforensik werden nicht aufgehoben.

Der Quellen-Snapshot akzeptiert die bekannte Robo-Plattform `rst` für diese
Metadaten, ohne sie als MT4/MT5 zu deklarieren. Andere unbekannte Plattformen
und mehrdeutige Identitäten bleiben Fehler. Die drei `rst`-Anbieter verwerfen
somit nicht länger die gesamte Robo-Auswahl.

Die Ergebnisansicht **Quellenprofitabilität** zeigt Originalgewinn, Rendite mit
Zeitraum, Ratingbalance, Quellen-Finanzdatenstand und getrennten Lesezeitpunkt.
Details enthalten eine deterministische Basisbewertung und geben keinen
KI-Bericht vor. Kandidaten/Top 5 bleiben am gemessenen Floating-RetDD gebunden.
Auch alte eventuell vorhandene Rang-/DD-/KI-Felder werden für Quellenwerte
in Anzeige und Export unterdrückt.

## Bestehender Auftrag und echte Datenprüfung

Der bestehende Auftrag `d38440b65c6540b79ce69e7fe7457ab0` hatte Robo wegen der
Plattformkennung noch vor Aufnahme seiner Anbieter verworfen. Die beauftragten
Quellenwerte wurden daher einmalig separat eingelesen und mit Mitgliedschaft
und Quellencheckpoint atomar in denselben Store ergänzt. Die übrigen Aufgaben
und der laufende Worker wurden nicht neu gestartet. Es gab keine neuen
nativen Update-POSTs oder Modellaufrufe durch diese Ergänzung.

Ergebnis: **200/200 Quellenprofile** (134 MQL4, 63 MQL5, 3 `rst`), davon
103 mit positivem, 86 mit negativem und 11 mit null gemeldetem USD-Gewinn.
Für keinen Anbieter wurde ein RetDD erfunden; Finanzdatenzeitpunkte bleiben
bei allen unbekannt. Die Aussage bezieht sich auf den angegebenen Quellenwert,
nicht auf eine Handelsfreigabe oder nachgerechnete Tradeprofitabilität.

Lokale Belege unter `data/runs/robo_quellenprofitabilitaet_20261023/`:
`import.json` und `ui_actual.json`. Der einmalige Importablauf liegt lokal
unter `.tmp/robo_quellenwerte_import.py`; Laufzeitdaten werden nicht veröffentlicht.

## Verifikation

55 neue hermetische Datenservice-Tests prüfen Gewinnvorzeichen, Null/fehlende
Werte, ungültige Zahlen, Renditeperioden, fehlende Finanzfrische, `rst`,
Identitäts-/Versions-/Schemafehler, Stopp und das Verbot von Trade-/Terminal-
und Forensikaufrufen. Zusätzliche Koordinatortests prüfen die Quellenaufnahme
mit `rst`, den Abschluss ohne KI und das Fortsetzen ohne Trade-SHA.
Die UI-Tests prüfen eigene Ansicht, Datumskennzeichnung und das Unterdrücken
unbelegter beziehungsweise alter RetDD-/KI-Werte in Ansicht und CSV.

Der abschließende relevante Scanner-Check bestand mit **249 Tests**:
Recherchekoordinator, Datenservice, KI-Verträge, unabhängige Regressionen,
Robo-Quellenwerte, Streamlit-UI, bestehende Abonnentenstatistik, gezielter
Refreshtransport und Bericht-Resume. Ein zusätzlicher AppTest gegen den
echten gespeicherten Auftrag bestätigte **200 sichtbare Robo-Zeilen, 200
Gewinnwerte, 0 RetDD-Werte und keine UI-Ausnahme**.
