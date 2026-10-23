# Zulu: Abonnenten lokal aus vollständigem Katalog sortieren

Auftrag 23.10.2026: Fehler „Abonnenten-Ranking ist nicht absteigend“ beheben.

## Befund

Der native Client fordert ausdrücklich `sortBy=followers`, `sortDirection=DESC`
und 20 Zeilen je Seite an. Maßgeblich ist `overallStats.followers`; der separate
Live-Follower-Zähler ersetzt ihn nicht. Die öffentliche echte Antwort belegt
überlappende Seiten:

- Seite 0 endet mit ID 424362 / 102 Abonnenten; Seite 1 beginnt mit derselben ID.
- Seite 1 enthält ID 423097 / 46 und endet mit ID 426663 / 44.
- Seite 2 beginnt erneut mit ID 423097 / 46, gefolgt von einem neuen Anbieter mit 44.

Die bisherige Prüfung verglich 46 gegen 44, bevor sie die wiederholte ID
bereinigte. Das ist ein Fehler unserer Verarbeitung überlappender Seiten.
Der betroffene Job scheiterte vor der Katalog-/Historienübernahme.

## Änderung

Der erste Korrekturversuch bereinigte identische IDs vor der Monotonieprüfung.
Der echte Anschlussjob `u-20261023-154623-da2fb42b` belegte zusätzlich eine echte
Inversion bei einer neuen ID: Seite 2, ID 423441 mit 117 nach 107 Abonnenten.
Die bloße Duplikatkorrektur genügte deshalb nicht. Die alten Daten wurden auch
bei diesem fehlgeschlagenen Zählerlauf noch nicht ersetzt.

Die endgültige Korrektur liest die vollständige angebotene Liste bis zu einer
erfolgreichen leeren Endseite. Gleiche IDs mit übereinstimmenden Zählern werden
bereinigt; danach wird nach `followers` absteigend/Anbieter-ID aufsteigend
sortiert, auf mindestens einen Abonnenten gefiltert und auf höchstens 200
begrenzt. Weder Nullen noch 200 gelesene Anbieter oder kurze Seiten gelten als
Ende. Seiten ohne neue IDs, widersprüchliche Zähler und ungültige Daten bleiben
Fehler; ohne Ende nach 10.000 Seiten wird keine Teilmenge veröffentlicht.

Keine Änderung der Hauptworkflow-Ampel, keine neuen Einzelprofil-/Tradeabrufe.
Bestehende Details bleiben im reinen Zählerlauf erhalten.

Sanitisierte öffentliche Prüfantworten und lokale Verifikationsbelege liegen
unter `data/runs/zulu_sort_fix_20261023/` (nur IDs und Zähler, keine Token).

## Tests und Aktivierung

`mvn -q test package` bestand mit **173 Tests, 0 Fehlern**. Die 15 Tests in
`SubscriberRankingTest` umfassen unsortierte und überlappende Seiten, Nullen
vor späteren positiven Werten, späte Spitzenanbieter nach bereits 200
Kandidaten, stabile Gleichstände, Zählerkonflikte, fehlenden Fortschritt und
ungültige späte Datensätze. Fehler liefern keine Teilauswahl.

Der Monitor wurde nach geprüftem Fehler-/Leerlaufzustand und exakter
Prozess-/Portidentität sanft neu gestartet. Kein erzwungenes Prozessende.
Der anschließende echte Zählerjob ist durch Start-/Abschlussbelege im oben
genannten lokalen Verzeichnis identifiziert; Trades und KI sind deaktiviert.

## Erfolgreicher Liveabschluss

Der endgültige Job `u-20261023-154959-74481dc9` endete mit **done, 200/200**, ohne
Fehler. Die anschließende REST-Prüfung bestätigt 200 unterschiedliche positive
Anbieter in absteigender Zähler-/aufsteigender ID-Reihenfolge; kleinster Zähler
1, größter 1.446. Die frischen Daten wurden anschließend gezielt für Zulu in
den Scanner gespiegelt: 200 Anbieter, 2.341 Historienpunkte, 21 eigene neue
Messpunkte, keine Fehler. Andere Quellen wurden dabei nicht neu gemessen.

1.807 bestehende Trade-/Berichtsdateien sind nach Größe und Änderungszeit
unverändert. Lokale Bilanzdateien: `update_final_success.json`,
`verification.json` und `scanner_sync.json` im oben genannten Laufverzeichnis.
Der Seitenabruf ist zeitlich gestreckt und kein atomarer Snapshot aller
Plattformzähler zum exakt selben Zeitpunkt.
