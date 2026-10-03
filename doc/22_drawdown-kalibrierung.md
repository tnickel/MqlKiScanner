# Drawdown-Kalibrierung an drei MQL-Signalen — 03.10.2026

Eine zufällige Nähe zweier Prozentwerte ist kein Nachweis gleicher
Berechnungen. Zeitraum, Kontobewegungen, Trade-Vollständigkeit,
Kurszeitzuordnung und Drawdown-Definition müssen zusammenpassen.

## Vergleich mit echten H1- und M1-Kursen

Zusätzlich zur gesamten H1-Historie wurde je Signal genau der öffentliche
Spitzentag mit echten M1-Kursen des Tickmill-Referenzterminals nachgerechnet.
Dabei wurde dieselbe Floating-/Balance-Definition wie in der öffentlichen
MQL-Grafik auf die tatsächliche Konto-Balance angewandt:

| Spitzentag / Signal | H1 am selben Tag | M1 am selben Tag | Öffentlicher MQL-Wert | Differenz M1 − MQL |
|---|---:|---:|---:|---:|
| 12.08.2026 / Gold Spike MT4 | 1,96 % | 3,60 % | 3,80 % | −0,20 Prozentpunkte |
| 28.08.2026 / Meridian MT5 | 9,55 % | 9,74 % | 10,45 % | −0,71 Prozentpunkte |
| 10.07.2026 / Night Scalper MT5 | 6,72 % | 7,01 % | 6,84 % bis Exportende | +0,16 Prozentpunkte |

Die M1-Werte stimmen näherungsweise in der Größenordnung überein; sie sind
kein vollständiger historischer Maximum-Nachweis. Insbesondere Golds
kurzer Belastungspeak fehlt am H1-Schluss. Referenzbroker-Kurse, Minuten-
statt Tickwerte, Spread, offene Swap-/Gebührenbuchungen und unterschiedliche
Kontostände begrenzen einen Cent-Abgleich. Die Ursache jeder verbleibenden
Differenz ist nicht einzeln bewiesen. Das Terminal wurde nach den
lesenden Kursabfragen beendet.

Unser produktiver **Equity-Höchststand-Drawdown** ist eine andere Kennzahl:

| Signal | Virtueller H1-Peak-DD über gesamte CSV | Virtueller H1-Peak-DD im Monitoring | Belegstatus gesamte CSV |
|---|---:|---:|---|
| Gold Spike | 5,41 % beobachtet | 2,95 % beobachtet | Unvollständig: lokale Zeitbasislücken, 85,1 % Abdeckung |
| Meridian | 39,58 % beobachtet | 12,23 % | Unvollständig: Zeitbasislücke im Juli, 98,4 % Abdeckung; Monitoringfenster lückenfrei |
| Night Scalper | 35,81 % | 9,56 % | Vollständiges H1-Modell der Exportpositionen, nominale Bybit-Kontoeinheiten |

Golds und Meridians Gesamtwerte sind diagnostische Teilbefunde. Sie werden
nicht als verlässliches Gesamtmaximum oder als RetDD-Nenner freigegeben.
Auch die vollständige Night-H1-Kurve enthält keine aktuell offenen
Exportpositionen und beweist kein Tick-Maximum. Ein einfacher Abgleich
dieser Peak-Werte mit dem Listenwert würde Definition und Zeitraum
vermischen; die Drei-Signal-Prüfung rechtfertigt deshalb keine pauschale
Behauptung, unsere vollständige Max-DD-Messung sei damit bewiesen.

## Plattformwerte und ihre nachgewiesene Bedeutung

Die aktuellen öffentlichen Signalseiten wurden mit Pausen abgerufen;
Trade-Snapshots und echte H1-Kurse des Referenzterminals wurden separat
ausgewertet. Es wurden keine Produktionsbefunde überschrieben.

| Signal | Plattform | Listen-/Radar-Maximum | By Balance | By Equity |
|---|---|---:|---:|---:|
| [Gold Spike #2349227](https://www.mql5.com/en/signals/2349227) | MT4 | 8,11 % | 8,11 % | 3,80 % |
| [Meridian Extreme Risk Mode #2385675](https://www.mql5.com/en/signals/2385675) | MT5 | 10,45 % | 2,53 % | 10,45 % |
| [EURUSD Night Scalper AI #2379236](https://www.mql5.com/en/signals/2379236) | MT5 | 17,26 % | 0,04 % | 17,26 % |

Die [MetaTrader-Hilfe](https://www.metatrader5.com/en/terminal/help/signals/signal_monitoring)
definiert das Maximum der Listen-/Radar-Anzeige als den höheren Balance-
oder Equity-Wert. Sie beschreibt den Equity-DD als Rückgang von einem
lokalen Maximum und begrenzt die Equity-Risikografik auf die Monitoringzeit.

Der am Prüftag ausgelieferte öffentliche
[MQL-Grafikcode](https://c.mql5.com/js/svg-chart.41b3b2994b96793970c7c0c78fee92d1.js)
berechnet die Drawdown-Grafik jedoch punktweise als
`max(0, (Balance - Equity) / Balance)`, ohne historischen Equity-Höchststand.
Bei allen drei Signalen entspricht das Maximum der eingebetteten
öffentlichen Balance-/Equity-Daten exakt dem angezeigten **By Equity**:

| Signal | Balance am Maximum | Equity am Maximum | Offener Verlust | Verhältnis |
|---|---:|---:|---:|---:|
| Gold Spike, 12.08.2026 | 2.050,68 USD | 1.972,75 USD | 77,93 USD | 3,80020286 % |
| Meridian, 28.08.2026 | 506,00 USD | 453,14 USD | 52,86 USD | 10,44664032 % |
| Night Scalper, 01.10.2026 | 5.316,53 UST | 4.398,95 UST | 917,58 UST | 17,25900164 % |

Damit ist für diese drei Signale ein Definitionsunterschied gegenüber
unserem Equity-Höchststand-Drawdown direkt nachgewiesen. Die allgemeine
Hilfebeschreibung und die beobachtete Grafikimplementierung stimmen in
diesem Punkt nicht überein. Das rechtfertigt keine Behauptung über alle
internen MQL-Berechnungen oder über absichtliche Falschmeldungen.

## Zeitraum, Kontobasis und Zählung

Monitoring startet bei Gold am 17.12.2025, Meridian am 08.08.2026 und
Night Scalper am 24.06.2026. Die Trade-Exporte enthalten ältere
Kontohistorie und enden am 28./29.09.2026. Das aktuelle Night-Maximum
entstand am **01.10.2026, nach dem Exportende**. Bis zum Exportende beträgt
das öffentliche Floating-/Balance-Maximum **6,84461978 %** (10.07.2026).
Das passt zum gespeicherten damaligen Plattformwert 6,84 %.

Die CSV-Zeiten der Kontobewegungen liegen bei allen drei Signalen exakt
drei Stunden nach den öffentlichen UTC-Zeitstempeln derselben Beträge.
Der Preisabgleich gegen MT5-Referenzbars belegt einen **relativen** Versatz
zum Referenzfeed; er beweist allein keine absolute öffentliche UTC-Zeit.
Vergleichsgrenzen müssen deshalb in den passenden Zeitrahmen übertragen
werden. Die Rohdaten bleiben unverändert erhalten.

Night Scalper handelt auf Bybit-Live-6. Dort bezeichnet UST im MT5-Kontext
[USDT wegen der dreistelligen Währungskennung](https://www.bybit.com/en/help-center/article/Introduction-to-Expert-Advisors-EAs).
Die Auswertung verwendet nominale USDT-/USDx-Kontoeinheiten gemäß den
[Bybit-Kontobedingungen](https://www.bybit.com/en/help-center/article/Understanding-MT5-CFD-Asset-Balances-and-Transfers).
Sie ist kein Nachweis historischer USDT-/Fiat-USD-Parität.

Der vorherige globale Broker-Regex las teilweise einen Kopierer-Broker
aus der Slippage-Liste. Der Anbieterbroker wird nun ausschließlich aus
dem Provider-Feld gelesen: Gold **RoboForex-ECN**, Meridian
**FusionMarkets-Live**, Night **Bybit-Live-6**. Moderne Seiten ohne dieses
Feld liefern unbekannt. Die früheren Brokerwerte in Audit-Snapshots sind
als überholte Extraktionsmetadaten dokumentiert. Für XAUUSD, AUDCAD und
EURUSD+ sind die Kontrakt-Specs vor/nach identisch, daher ändern sich
diese drei Rechenläufe nicht. Brokerspezifische Kontrakte dürfen hingegen
nicht anhand eines Kopierer-Brokers ausgewählt werden.

Einzahlungen und Auszahlungen verändern die echte Konto-Balance.
Unsere Produktivkurve `Startkapital + Trade-Netto + Floating` behält Gewinne
virtuell im Konto und enthält spätere Kapitalflüsse nicht. Eine separat
berechnete kapitalflussneutrale Konto-Kurve ist daher eine andere Messung;
sie wird bei unbelegter Equity am Flow oder Messlücken nicht freigegeben.

Die bisherige Parser-Heuristik entfernte identische Zeilen ab zehn
Wiederholungen und einem Prozent Anteil. Sie war unbegründet: Die
ticketlosen Exportformate können verschiedene echte Positionen mit
identischen Zeiten, Preisen und Volumen enthalten. Beim Night Scalper
entfernte sie 17 Zeilen und 141,32 Netto-PnL. Alle 299 Rohpositionen ergeben
exakt die öffentlichen 182 Long-/117 Short-Trades; auch Profit plus Swap
stimmt mit dem öffentlichen Bruttogewinn überein. Roh-Netto 2.422,00 und
Web-Netto 2.417,50 unterscheiden sich weiterhin um 4,50 Kontoeinheiten;
die Ursache dieser verbleibenden Gebühren-/Quellendifferenz ist unbewiesen.

**Korrektur:** Alle validierten Positionen und Kontobewegungen bleiben als
Multiset erhalten. Identische Trade-Zeilen sind nur ein Qualitätsbefund,
kein Identitätsbeweis. Eine Doppellieferung muss künftig anhand einer
stabilen Deal-/Positions-ID beim Datenlieferanten bewiesen werden.

## Kurszeitfehler und Korrektur

Golds globaler Preisabgleich favorisierte Versatz 0. Im März passten
Trade-Preise zeitweise jedoch eindeutig zu einem um eine Stunde
verschobenen Referenzintervall. Der alte globale Versatz erzeugte am
09.03.2026 einen falschen offenen Verlust von rund 239,52 USD.

Forensik und Studie nutzen jetzt denselben Preisabgleich je Zeitabschnitt:
stark belegte lokale Wochen dürfen den globalen Versatz ändern;
abweichende dünne oder widersprüchliche Abschnitte bleiben unbewiesen.
Open und Close eines langen Trades werden getrennt zugeordnet.
Wochengrenzen sind offengelegte Modellgrenzen, keine sekundengenau
bewiesenen DST-Grenzen. Nicht monotone Zuordnungen, unklare inverse Zeiten,
offene Positionen über unbewiesene Wechsel und unklare FX-Handelstage
verhindern eine belastbare Gesamtmessung.

Auch bei einem global unzureichenden Preisabgleich können unabhängig
stark belegte lokale Abschnitte verwendet werden. Fehlende Kandidaten-Bars
zählen beim GMT-Preisabgleich als Nichttreffer, damit alle Kandidaten
denselben Nenner haben. Originalexport und übrige Forensik bleiben im
ursprünglichen Zeitrahmen; nur eine Analyse-Kopie wird normalisiert.

`zeitbasis` mit Perioden, Belegstatus und Gründen wird gespeichert und
an die KI weitergereicht. Die Studie zeigt dieses Profil. Forensik-Version
**10** und ein neuer Studien-Cache-Schlüssel erzwingen Neuberechnung.
Unbelegte Kurs-DDs gelangen weder in die Max-Drawdown-Spalte noch in RetDD.

## Prüfung und Betriebsübernahme

Der abschließende vollständige Standardlauf bestand mit **1.301 Tests**;
die anschließend ergänzten fünf Provider-Broker-Regressionen bestanden
zusammen mit 50 bestehenden Ingestion-/Kontrakt-/MQL-Tests. Damit sind
alle aktuell 1.306 Standardtests über diese Läufe abgedeckt. **Vier echte
GLM-Regressionen** bestanden, ebenso **60 Tests im MqlTradeMonitor**.

Die vorherige Testannahme, ein fehlender Close-Kurs dürfe aus einem
Open-Treffer eine 100-%-GMT-Quote machen, wurde korrigiert: Der gemeinsame
Nenner ergibt 50 % und keinen belastbaren globalen Zeitversatz.

Bestehende Scanner-Befunde müssen mit Version 10 neu gescannt werden.
Der Tradeserver-Code ist angepasst und gepusht; für die produktive Anzeige
muss der Server mit dem neuen Build starten und anschließend einen neuen
Scanner-Sync empfangen. Es wurde kein produktiver Server neu gestartet
und kein Produktions-Sync ausgeführt.

Die Rohbelege, Kursdaten, Rechenläufe und unabhängigen Prüfungen werden
nach Abschluss gemäß Projektregel außerhalb des Repos unter
`../waste/drawdown_3signale_2026-10-03/` archiviert.
