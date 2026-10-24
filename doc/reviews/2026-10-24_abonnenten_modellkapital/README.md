# Kapitalmodell für die Abonnentenstatistik

Nutzerauftrag 24.10.2026: Startkapital aus Lots/Tradeverlauf untersuchen und
schätzen, bei fehlender tragfähiger Schätzung grob aus Lots ableiten, zuletzt
10.000 USD annehmen. Kapitalherkunft in der Tabelle; Szenario ohne Ein- und
Auszahlungen. Echte Kontomessungen und ausdrücklich bezeichnete Modellwerte
bleiben getrennt.

## Mathematische Grenzen

Ein fester Lotwert identifiziert kein Kapital: Derselbe 0,1-Lot-Trade kann
auf verschieden großen Konten stattfinden. Für `Lots = a + b * PnL_vor_Trade`
ergibt sich nur unter der zusätzlichen Annahme proportionaler Positionsgröße
`K0 = a / b`. Konstante Lots, wechselndes Risiko, unterschiedliche Instrumente,
Martingale und Kapitalflüsse können diese Identifikation verhindern oder
verfälschen. Die Schätzung ist ein Modell, kein Kontonachweis.

Ein bereits mit angenommenem Startkapital selbst berechneter Closing-DD ist
kein unabhängiger Kapitalbeleg. Eine Inversion reproduziert nur die zuvor
eingesetzte Annahme. Auch dürfen größter absoluter und größter relativer DD
nicht ohne Zuordnung zum selben Drawdownereignis vermischt werden. Die
[MetaTrader-Dokumentation](https://www.metatrader5.com/en/terminal/help/trading_advanced/history_report)
unterscheidet diese beiden Maxima ausdrücklich.

## Berechnung und Datenherkunft

Die unveränderten Exportdateien bleiben SHA-geprüft. Im Modell werden
Kapitalbewegungen ausschließlich aus einer Kopie der Parserdaten entfernt;
Trade-Netto und Kontokosten bleiben berücksichtigt. Historische Kurs-,
Währungs- und Kontraktbelege bleiben erforderlich. H1-Bar-Schlüsse sind
keine vollständigen Intrabar-Maxima; aktuell offene Positionen außerhalb
des Exports bleiben unberücksichtigt. Eine Kapitalannahme ergänzt keine
fehlenden Trades oder Preise.

Modellwerte liegen unter `entry.modell` und überschreiben keine echten
Forensik-/Equity-/Renditefelder. Neue Bestandsaufträge verwenden keine
Quellenupdates, Terminals oder KI. Die ursprünglichen Aufträge bleiben
erhalten. Eine Modellvorauswertung verwendet ausschließlich Modell-RetDD;
unverarbeitete Altwerte werden nicht in dieselbe Rangliste gemischt.

## Empirische Untersuchung

128 USD-Profile mit belegter Kapitalbasis und insgesamt 236.133 Trades
wurden auf den unveränderten Exporten untersucht. Ohne spätere Kapitalflüsse
blieben 22 Profile. Eine unbeschränkte positive Lot-/PnL-Regression lieferte
häufig große Fehler. Selbst hohes R² allein schützte nicht: zwei Fits mit
R² ≥ 0,8 lagen um Faktoren 5,61 beziehungsweise 8,68 daneben.

Die implementierte Prüfung verlangt mindestens 50 Trades, drei Lotstufen,
positive Steigung und Kapitalbasis, R² ≥ 0,95 sowie zeitlich stabile
Halbfensterfits. Das ist eine technische Identifikationsprüfung, keine
Handelsregel oder behauptete Konfidenz. Im Referenzbestand bestand genau
ein Profil: 972,29 USD Modellwert gegenüber 1.000 USD belegter Basis.

Die grobe Kalibrierung nutzt ausschließlich echte USD-Kapitalbelege und
vergleichbare Instrument-/Kontrakteinheiten, mindestens fünf andere Profile.
111 Referenzen hatten passende Kontraktbelege. Auf 97 Profilen mit ausreichend
großer Vergleichsgruppe lag der Leave-one-out-Medianfehler beim Faktor 2,465;
80 % lagen innerhalb Faktor 6,789. Ein vorab festgelegtes Frühfenster von
20 Trades verbesserte die Schätzung nicht (Medianfehler Faktor 2,534).
Das ist eine grobe Skala, kein belastbarer Nachweis des realen Kapitals und
keine garantierte Fehlergrenze für andere Quellen.

Private Rechnung und Diagnostik:
`data/runs/abonnenten_modellkapital_20261024/forschung_estimator.json`.

## Abnahme

858 kombinierte Abonnenten-, H1-, Kapitalfluss-, Feed- und FX-Tests bestanden.
Die unabhängige Nachprüfung fand und korrigierte zwei weitere Probleme:
widersprüchliche Trade-/Kontowährung durfte nicht in den USD-Referenzpool
gelangen; Wiederaufnahme bindet nun auch Alias-, Broker- und alle
Währungsangaben an die Berechnungsbasis. Gezielte Nachtests sind grün.

Produktiver separater Bestandsauftrag `9079bf2a4b0246ceb851d64e77b3f73e`
lief am 24.10.2026 von 13:09 bis 13:30 MESZ. Er verarbeitete alle 800
Auswahlzeilen mit 275 verwendbaren Exporten: 800 Kapitalbasen, 166
Floating-DD-Werte und 149 RetDD-Werte. Alle ursprünglichen Kontomessungen,
beide Vorgängeraufträge und die KI-Kostenbuchungen blieben unverändert.
Das ist der erste abgeschlossene Modellstand, kein vollständiger Datenbestand.
Private Start-/Abschlussbelege liegen im genannten Laufordner.

## Ergänzung vorhandener nativer Tradelisten

Für 524 Zeilen fehlte im Scanner ein gespeicherter Trade-Snapshot. Eine lokale
Inventur fand für 510 davon native Dateien. Dateiintegrität, Anbieter-/Quellen-
Identität, Geldwährung und Positionssemantik werden unabhängig geprüft;
ein Dateihash ist kein Nachweis einer vollständigen Plattformhistorie.

Der Offline-Importer bereitet 48 MQL-, 198 Pelican- und 48 Zulu-Dateien vor.
Rohdateien und getrennte Formatkonvertierungen erhalten eigene SHA-Snapshots.
Keine Trades werden still verworfen. Pelican-/Zulu-Netto wird genau einmal
übernommen; separat nicht gelieferte Kommission/Swap werden nicht ein zweites
Mal abgezogen. MQL-Beträge behalten die belegte native Kontowährung;
Modellrechnungen verwenden historische lokale ECB-Kurse zur USD-Umrechnung.

Bei Pelican bleibt die Vollständigkeit der gesamten Plattformhistorie unbekannt;
lokale Meta-Dateien belegen lediglich Anzahl und SHA. Bei 17 gesperrten
Zulu-Dateien bestätigt auch die originale API-Epochzeit die unmögliche Reihenfolge
Schluss vor Eröffnung. Das ist keine durch einen Zeitzonenwechsel behebbare
Darstellung; diese Positionen werden nicht repariert oder entfernt.
Robo-Tradebeträge und Volumeneinheiten bleiben unbelegt und werden nicht durch
eine Kapitalannahme zu USD/Lots erklärt.

Die Zusatzmodelle verwenden unverändert die eingefrorenen 111 Referenzen des
ersten Modellauftrags. 109 gezielte Import-, Kapital-, Rechen-, Workflow- und
UI-Tests bestanden; nach weiteren Abnahmen zusätzlich 53 kombinierte Import-/
Parser-/Rechentests sowie alle 16 UI-Tests. Der unabhängige Review bestätigt
für 17 Zulu-Dateien mit 95.693 Positionen insgesamt 324 auch in den originalen
API-Epochs negative Haltedauern. Ein Zeitfix wäre unbegründet.

Alle 294 zulässigen Ergänzungen wurden fertig berechnet und nochmals gegen
die tatsächlichen Snapshot-SHAs, unveränderten vorbereiteten Zeilen und
Kalibrierungsbelege geprüft. MQL liefert zusätzlich 35 DD/35 RetDD, Pelican
132 DD/121 RetDD und Zulu 23 DD/20 RetDD. Ein gespeicherter Zulu-RetDD bleibt
wegen ausdrücklich unvollständigem Export außerhalb der Rangfolge.
Die Teilprozesse sind beendet; es gab keine Quellenabrufe, Terminalstarts
oder externen KI-Aufrufe. Der erste Modellauftrag bleibt erhalten.

## Produktiver Abschluss des Modellauftrags

Am 24.10.2026 wurde der getrennte Datenbestand
`77feecf051a94836ae21f724d7dca7b8` veröffentlicht. Alle 800 Zeilen haben eine
positive Kapitalbasis und eine sichtbare Herkunft: 149 belegte Einzahlungen,
293 grobe Schätzungen aus vergleichbaren Lots, 358 Annahmen von 10.000 USD.
Es wird keine nicht bestandene komplexe Schätzung als erfolgreich ausgegeben.

| Quelle | Anbieter / Kapitalbasen | Modellgewinn aus Trades | Modell-Floating-DD | Modell-Jahres-RetDD |
| --- | ---: | ---: | ---: | ---: |
| MQL | 200 | 198 | 148 | 142 |
| Pelican | 200 | 197 | 132 | 121 |
| Zulu | 200 | 172 | 76 | 62 |
| Robo | 200 | 0 | 0 | 0 |
| Gesamt | 800 | 567 | 356 | 325 |

Robo-Quellengewinne stehen weiterhin separat; die Null in dieser Tabelle
bedeutet keine berechenbaren Trade-Modellwerte, nicht null Gewinn oder Risiko.
570 Zeilen besitzen nun einen Scanner-Export; ein alter Export bleibt
unbrauchbar. 230 Zeilen haben keinen zulässigen Import: 200 Robo mit ungeklärten
Geld-/Volumeneinheiten, 28 Zulu und zwei Pelican mit fehlenden oder fehlerhaften
Quelldaten. Weitere DD-Lücken entstehen unter anderem durch fehlende Kurs-/
Kontraktbelege oder eine nicht bestätigte Zeit-/Preiszuordnung. RetDD bleibt
zusätzlich bei DD null, aufgebrauchtem Modellkapital oder nicht definierter
Annualisierung leer. Die Berechnung ist beendet, die Datendeckung ausdrücklich
nicht vollständig. Status: 324 berechnet, 51 eingeschränkt, 425 Datenlücken.

Die 110 ursprünglichen gemessenen DD- und 51 ursprünglichen RetDD-Werte
bleiben unverändert. Alle drei Vorgängeraufträge, alle nicht ergänzten Modelle
und die KI-Kostenbücher sind gegen ihre vorherigen Hashes/Zähler geprüft.
Der neue Auftrag enthält keine KI-Aufrufe. Tabellen- und CSV-Abnahme bestätigt
alle 800 Zeilen, Kapitalherkunft und die oben genannten Werteanzahlen; konkrete
Importfehler stehen zusätzlich im sichtbaren Modellgrund.

Private Abschlussbelege: `cache_merge_abschluss.json`, `table_csv_abnahme.json`,
`review_import_epoch.json` und die geprüften Einzel-/Sammelergebnisse unter
`cache_models/`, jeweils in `data/runs/abonnenten_modellkapital_20261024/`.

Die Browserabnahme zeigt den neuen ausgewählten Bestand und 800/356/325.
Ein dabei festgestelltes unnötiges Zwei-Sekunden-Neuladen fertiger Tabellen
ist behoben: nur aktive/gerade startende Datenaufträge werden periodisch
aktualisiert; Abschluss, Fortsetzung und Auswahlwechsel schalten den Timer
um. Alle 24 UI-Tests einschließlich acht gezielter Regressionen bestanden.
Die ruhige fertige Ansicht ist mit `ui_final.png` und `ui_final.txt` belegt.
