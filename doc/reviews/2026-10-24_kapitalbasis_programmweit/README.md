# Gemeinsame Kapitalermittlung im Programm

Nutzerauftrag vom 24.10.2026: Die zuvor für die Abonnentenstatistik entwickelte
Startkapitalabschätzung soll in allen Anbieter-Rechenwegen verwendet werden.

## Umsetzung

`src/mqlkiscanner/kapitalbasis.py` entscheidet einmal über Kapital, Herkunft,
Methode, Annahmen und Unsicherheit. Der mathematische Schätzer bleibt einmalig
in `abonnenten_modellkapital.py`. Die Reihenfolge ist:

1. Vorhandene CSV-Einzahlungen vor Handelsbeginn, danach belegtes Quellen-
   Anfangskapital oder eine explizite manuelle Angabe.
2. Unabhängiger Closing-DD-Anker mit gleichem Exportfenster und Definition
   oder stabile Lot-/PnL-Regression. Eigene kapitalabhängige DD-Prozente sind
   kein unabhängiger Anker. Bekannte spätere Flows widersprechen diesen
   No-Flow-Identifikationen.
3. Grobe Lotschätzung aus mindestens fünf vergleichbaren belegten Referenzen.
4. Modellannahme 10.000 USD.

Lots allein identifizieren kein Startkapital: unterschiedliche Risikostile
können dieselben Lots auf verschieden großen Konten erzeugen. Der Lot-/PnL-Fit
setzt proportionale Positionsgrößen voraus; mindestens 50 Trades, drei Lotstufen,
R² ≥ 0,95 und zeitlich stabile positive Teilfits prüfen diese Hypothese.
Die Referenzspanne ist eine beschreibende Stichprobe, kein Konfidenzintervall.

Die regulären Wege erhalten vorhandene Ein-/Auszahlungen und separate Kosten.
Der Kapitalanker liegt vor separaten Vorstartkosten. Eine explizite Injektion
ergänzt ausschließlich den fehlenden Anteil zu den vorhandenen Vorstartflows;
Kosten werden genau einmal gebucht. Eine belegte nichtpositive CSV-Netto-Basis
wird nicht durch Schätzkapital ersetzt. Ein fehlender oder ungültiger nativer
Initial-Deposit-Wert ist dagegen kein Kapitalbeleg und erlaubt die Schätzung.
Explizite Fremdwährung oder widersprüchliche Währungsangaben blockieren die
USD-Rechnung. Nicht übertragene Kontoflüsse bleiben unbekannt.

Angebunden sind Engine, Closing-DD und Exposure, Scanner/Pipeline,
Signalstatistik und Alle-Signale-Ansicht, Einzel-/Batch-Kontostudien,
Risikorechner sowie neue Abonnenten-Berechnungen. Eine bereits aufgelöste
Entscheidung wird weitergereicht, nicht erneut als Quellenkapital eingespeist.
Die gesonderte Abonnenten-Modellrechnung behält ihre ausdrücklich angeforderte
No-Flow-Berechnungskopie. Kopiererbudgets sind keine Anbieterkapital-Schätzung.

Auch der wiederholt ausführbare Offline-Kontrollscan unter
`scripts/kontrollscan_bericht.py` nutzt die zentrale Kapitalentscheidung und
prüft die Export-SHA sowie native Währungsmetadaten. Seine Modellkandidaten
werden ausdrücklich als Modell-Vorauswahl bezeichnet. Der Kapitalteil dieses
Gegenchecks ist damit keine unabhängige Validierung des gemeinsamen Schätzers.
Bereits erzeugte Kontrollberichte bleiben unverändert.

Methode, Betrag und Modellstatus werden angezeigt und mit dem vorhandenen
Befund-JSON gespeichert; Prompts und PDFs erhalten die Herkunft und Unsicherheit.
Modellprüfungen haben einen eigenen Vollständigkeitsstatus. Sie erlauben weder
vollständige echte Kontoforensik noch automatische Grün-Freigaben. Bestehende
harte Rotregeln bleiben wirksam. Studien verwenden ihren eigenen gebundenen
Kapital- und Renditenenner; echte gespeicherte Studien werden nicht durch neue
Modellszenarien überschrieben.

Forensikversion **22** kennzeichnet die geänderte Berechnungsgrundlage. Es gibt
keine Schema-Migration und keine automatische Neuberechnung alter Berichte.

## Lokale Aktivierung

Die gemeinsame Kalibrierung wurde aus dem vorhandenen eingefrorenen Bestand
lesend übernommen: **111 belegte USD-Referenzen**. Sie liegt privat unter
`data/kapitalbasis/kalibrierung.json` und wird ausschließlich lesend geladen.
Schema und SHA werden geprüft; fehlende oder ungültige Kalibrierung ist eine
sichtbare Diagnose und führt erforderlichenfalls zum 10k-Fallback. Gleiche
Anbieteridentität oder gleiche Export-SHA wird nicht als Eigenreferenz benutzt.

Kalibrierungs-SHA:
`91672407335cb494b8bf808190d3edf0b2cac8947e18270a58a6c47b04e45a0d`.

Originalaufträge und gespeicherte Ergebnisse bleiben unverändert. Dieser
Auftrag startet keine KI, Quellenupdates oder Marktterminals. Laufbelege liegen
privat unter `data/runs/kapitalbasis_programmweit_20261024/`.

## Prüfung

Synthetische Regressionen prüfen die verschiedenen Schätzstufen, Fremdwährung,
Eigenreferenzen, unveränderte Originaldaten, Kosten und Kapitalflüsse,
Übereinstimmung der Rechenwege sowie Modellkennzeichnung und Bewertungsgrenzen.
Tests verwenden isolierte Datenverzeichnisse und gesperrte HTTP-Anfragen.
Das Risiko-PDF wurde mit synthetischen Daten erzeugt und visuell geprüft.
Auch der synthetische zehnseitige Kontrollscan-Bericht wurde vollständig
gerendert und visuell geprüft; eine abgeschnittene Diagrammbeschriftung ist
korrigiert. Herkunft, Unsicherheit und Beleg-SHA sind lesbar.

Abschließender Nachweis: **1.560 unterschiedliche betroffene Testfälle im
jeweils letzten Prüfstand bestanden**. Der gemeinsame Lauf hatte zunächst
1.445 bestandene Fälle und eine veraltete Erwartung an den Studien-Cacheprefix.
Die Erwartung wurde an die zusätzliche Kapitalmethodik-Version angepasst;
der anschließende gezielte Lauf bestand mit 111 Fällen. Der Kontrollscan-
Abschluss enthält 103 bestandene Fälle. Überschneidungen sind in der Gesamtzahl
nicht mehrfach gezählt. XML-Protokolle und `abnahme.json` stehen im privaten
Laufverzeichnis.

Die laufende Oberfläche wurde geprüft: Der Risikorechner bietet automatisch
Beleg → Lotschätzung → grobe Schätzung → 10k-Fallback an. Die Abonnentenstatistik
zeigt weiterhin den vorhandenen Auftrag mit 800 Kapitalbasen, 356 Modell-DD
und 325 Modell-RetDD. Diese Anzeigeprüfung hat keine Neuberechnung gestartet.
