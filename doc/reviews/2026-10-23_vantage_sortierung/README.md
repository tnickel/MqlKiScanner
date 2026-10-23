# Vantage: aktuelle Top 200 trotz unsortierter Plattformliste

Auftrag vom 23.10.2026: Fehler „Kopierer-Ranking ist nicht absteigend sortiert“
beim Abonnentenupdate korrigieren.

**Aktueller Anschlussstand am Abend:** Der Nutzer erlaubt jetzt ausdrücklich,
fehlerhafte Einträge auszuklammern und weiterzulesen. Diese Ausnahme ersetzt
die frühere All-or-nothing-Regel für API 1223. Die unten dokumentierten
Fehler bleiben historische Belege. Der neue Liveabruf ist als eingeschränkte
Auswahl erfolgreich; eine vollständige globale Top 200 wird nicht behauptet.

## Ursache und Korrektur

Der bisherige Abruf behandelte `overallSort="2"` als absteigende Folge aktueller
`copiers` und brach bei einem Anstieg ab. Die echte erste 100er-Seite hatte am
23.10. 38 solche Anstiege. Auch `cumulativeCopiers` ist nicht absteigend; ein
früher Abbruch anhand dieses Feldes wäre ebenfalls unbegründet. Der alte
Job endete vor dem Speichern; die bestehenden Zähler blieben erhalten.

Der native `VantageClient.downloadSubscriberProviders` liest nun die komplette
Listenpagination bis zu einer leeren Endseite. Er prüft alle IDs und Zähler,
dedupliziert konsistente Identitäten, sortiert nach aktuellen Kopierern und
bei Gleichstand nach ID, entfernt Anbieter ohne Abonnenten und speichert
höchstens 200. Weder 200 gelesene Einträge, Nullen noch kurze Seiten beenden
die Pagination vorzeitig. Aufsteigende Zähler sind zulässig.

Ungültige spätere Seiten, widersprüchliche Zähler derselben ID, Seiten ohne
neue Anbieter oder ein fehlendes Ende nach 1.000 Seiten führen weiter zum
Abbruch ohne Teilübernahme. Einzelprofile, Finanzstatistiken, Tradelisten und
KI werden für diesen Zählerabruf nicht geladen. Der Fortschritt nennt die
gelesenen Seiten und Anbieter, bevor die eigentliche Top-Auswahl feststeht.
Das Lesen mehrerer Seiten ist keine atomare Plattformmessung aller Zähler
zum exakt selben Zeitpunkt.

Sanitisierte lokale Quellenbelege (nur öffentliche IDs und Zähler, keine
Kontonummern/Token) liegen unter `data/runs/vantage_sort_fix_20261023/`.
Die bestehenden Mocktests hatten die falsche Sortierannahme abgebildet;
die Korrektur wird gegen unsortierte und zusätzliche späte Seiten geprüft.

## Zusätzlicher Livebefund: interne Listenberechnung

Der erste korrigierte Job `u-20261023-152654-7835a92` las 1.200 Anbieter,
scheiterte danach jedoch am separaten Quellenfehler 1223. Es wurde weiterhin
kein Teilbestand übernommen. Seite 13 im 1-Monatsfenster schlug reproduzierbar
fehl, auch nach Aufteilung in kleinere Seiten; eine andere Reihenfolge schlug
an einer anderen Position fehl. Die spätere Seite 60 war dagegen erfolgreich,
Seite 61 leer. 1223 ist deshalb ausdrücklich kein Paginationende.

Dieselbe problematische Seite war mit den Kennzahlenfenstern 3/6/12 Monaten
abrufbar. Nur bei genau diesem API-Code wird deshalb der vollständige
Zählerkatalog mit dem nächsten Fenster ab Seite 1 neu gelesen. Die bisher
frisch gesehenen IDs müssen im erfolgreichen vollständigen Katalog vorhanden
sein. Andere Fehler bleiben Fehler. Wenn alle vier Fenster fehlschlagen,
wird kein Ergebnis veröffentlicht. Für den Zählerlauf werden keine Rendite-,
DD- oder anderen Finanzwerte dieser Listenfenster in das Modell übernommen.
Die regulären Profilabrufe ändern ihr Kennzahlenfenster nicht.

## Abschließender Stand: Sortierannahme behoben, Quellenabruf weiter blockiert

Der native Build wurde sanft neu gestartet. **117 Tests bestanden**, darunter
15 Tests speziell für vollständige Zählerlisten, Sortierung und Fehlerfälle.
Der echte Anschlussjob `u-20261023-153403-5f53f308` bestätigte jedoch Fehler
1223 an späteren Seiten in **allen vier** Kennzahlenfenstern. Ein vollständiger
aktueller Katalog konnte damit nicht nachgewiesen werden; es wurde keine
Teilmenge als Top 200 gespeichert. Auch kleinere Seiten, andere Reihenfolge
und `showTimePoint=true` beseitigten den Quellenfehler nicht.

Die erste lokale Sortierursache ist korrigiert, der gesamte Liveabruf ist
**noch nicht erfolgreich abgeschlossen**. Das Verwerfen unvollständiger
Kataloge bleibt absichtlich wirksam. Das Umgehen dieser Vollständigkeitsprüfung
würde den vereinbarten Umfang stillschweigend ändern.

4.789 vorhandene Trade-/Berichtsdateien sind nach Größe und Änderungszeit
unverändert; die erfolglosen Zählerjobs schreiben ihre Auswahl erst nach
erfolgreichem vollständigem Abruf. Maschinenbilanz unter
`data/runs/vantage_sort_fix_20261023/verification.json`. Die öffentliche
Vantage-Oberfläche war im Browser erreichbar; ein funktionierender alternativer
vollständiger Katalogweg konnte damit nicht bestätigt werden.

## Weitere öffentliche Gegenprüfung: auch eine Einzelzeile scheitert

Die zusätzliche Prüfung am 23.10.2026 bis 17:01 MESZ verwendete ausschließlich
lesende öffentliche Katalogabfragen. Es wurden dadurch keine lokalen
Update-Aufträge, Downloads, Neustarts oder Änderungen am nativen Client ausgelöst.

Das aktuelle offizielle Frontend-Bundle
[`index.CV1Lqg13.js`](https://secure.vantagemarkets.com/static/js/index.CV1Lqg13.js)
belegt die Sortierwerte `7` (highestRated, Standard), `1` (highReturn),
`3` (mostCopiedHighWinRate), `4` (lowestRisk) und `10` (lowestDrawdown).
`2` wird im aktuellen Sortiermenü nicht angeboten; eine zusätzliche
Sortierrichtung ist nicht vorhanden. Der Frontend-Standard verwendet 21
Einträge je Seite und begrenzt das Nachladen auf zehn Seiten. Das belegt
keinen vollständigen Plattformkatalog. Die Risikofilter `<=2` und `<=6`
sind zudem Obergrenzen, keine disjunkten Risikobuckets.

`overallSort=10` wurde ohne DD-, Rendite-, Risiko- oder Kategorienfilter
im unveränderten 1-Monatsfenster tatsächlich weiter ausgeblättert:

- Seiten 1 bis 54: jeweils erfolgreich, zusammen 5.400 Antwortzeilen,
  5.398 eindeutige IDs; zwei konsistente Überschneidungen, keine
  widersprüchlichen Zähler und nur gültige numerische IDs/Zähler.
- Seite 55 bei Seitengröße 100: API-Fehler 1223. Die erfolgreiche spätere
  Seite 60 enthielt 61 Zeilen; Seite 61 war leer. Der Fehler ist kein Ende.
- Halbierung derselben Fehlerregion: Größe 50/Seite 109, Größe 25/Seite 217
  und Größe 5/Seite 1085 scheiterten ebenfalls; die jeweils angrenzenden
  Teilbereiche waren lesbar.
- **Auch Größe 1/Seite 5423 lieferte Fehler 1223.** Die unmittelbar
  benachbarten Einzelabfragen waren erfolgreich. Die Identität des nicht
  gelieferten Anbieters ist damit weiterhin unbekannt. Eine adaptive
  Seitengröße bis hinunter zu einer Zeile löst diesen Fehler nicht.

Seite 55 war mit drei Monaten lesbar, mit sechs bzw. zwölf Monaten dagegen
bereits leer. Derselbe vollständige Anbieterumfang über alle Fenster ist
damit nicht belegt. `months=null` bzw. Weglassen des Feldes beseitigten den
Fehler nicht; 0, 24 und 36 wurden ausdrücklich mit Code 10595 abgewiesen.
Der alternative Suchpfad liefert bei leerem Suchtext einen Parameterfehler;
`discover/listAll/forWeb` enthält lediglich fünf kuratierte Zwölferlisten.
In den geprüften aktuellen Frontend-Modulen wurde kein weiterer reiner
Vollkatalogpfad nachgewiesen.

Der zusätzliche Beleg liegt unter
`data/runs/vantage_sort_fix_20261023/probe_sort10_single_row_1223.json`
(SHA-256 `7ef2a52d73af7536c35b6091911d80a250e2a9ef244147a2b17d244d12944293`).
Gespeichert sind öffentliche IDs/Zähler, Sortierung, Zeitraum, Seiten und
Antwortcodes; keine Kontonummern, Sitzungstoken oder Zugangsdaten.

**Ergebnis: kein weiterer Fix und kein vollständiger aktueller Abruf.**
Insbesondere wurde Sortierung 10 nicht als vermeintlich funktionierender
Vollabruf eingebaut. Das Überspringen der fehlerhaften Zeile oder das
Vereinigen unbelegter Teilkataloge wäre kein belastbarer Top-200-Nachweis.
Die vorhandenen lokalen Roster wurden von diesen Proben nicht verändert;
es wurde keine neue Auswahl veröffentlicht.

## Erneuter Abruf auf Nutzerauftrag um 21:24 MESZ

Der ausdrücklich erneut beauftragte reine Abonnentenabruf
`u-20261023-212435-12990bb6` lief am 23.10.2026 von 21:24:35 bis 21:26:00
MESZ. Alle vier Listenfenster (1/3/6/12 Monate) scheiterten erneut mit
API-Code 1223 und `call st engine response error`. Keine neue Top-Auswahl
übernommen, kein Scanner-Neustart. Lokale Start-/Ergebnisbelege unter
`data/runs/abonnenten_live_repair_20261023/vantage_user_retry_start.json` und
`vantage_user_retry_result.json`.

## Eingrenzung des Fehlers gegenüber dem erfolgreichen GUI-Abruf

Der normale GUI-Abruf vom 23.10.2026 war um 21:33:27 MESZ mit 400 Anbietern
erfolgreich beendet; Kennzahlen waren auf 150 Anbieter begrenzt. Dieser
begrenzte gemischte Abruf erreicht die folgende Fehlerstelle nicht.

Neue öffentliche Nur-Lese-Proben um 21:46–21:50 MESZ bestätigten im
Scanner-Listenmodus (`overallSort=2`, `months=1`) erfolgreiche Seiten 12 und
14, aber Fehler 1223 auf Seite 13. Durch Aufteilung bis zu einem Eintrag
wurde die fehlerhafte Position **1256** isoliert. Position 1255 und 1257
antworteten jeweils erfolgreich. Auch die neue Gegenprobe für Sortierung 10
bestätigte die zuvor dokumentierte Fehlerposition 5423 samt funktionierender
Nachbarn. Ob beide Positionen denselben Anbieter betreffen, ist unbekannt.

Sortierung als JSON-Zahl statt Zeichenkette, `rating=null` und ein minimaler
Anfragekörper mit nur Sortierung, Monat, Seite und Seitengröße lieferten an
Position 1256 ebenfalls HTTP 200 mit API-Code 1223. Die interne Ausnahme und
die Anbieter-ID dieser Position bleiben unbekannt. Eine datensatzabhängige
Störung im Vantage-Backend ist damit eine begründete Einschätzung, keine
nachgewiesene konkrete Daten- oder Rechenursache.

Ein seitenweiser Wechsel der Monate ist ebenfalls nicht belegt: Die aktuellen
Seiten 12/14 haben zwischen Monat 1 und 3 nur 8 beziehungsweise 11 gemeinsame
IDs von jeweils 100. Daraus dürfen keine austauschbaren Listenseiten abgeleitet
werden. Keine neue Auswahl, lokale Update-Aufträge oder Prozessänderungen
durch diese Proben. Sanitisiertes Messprotokoll und Zusammenfassung:
`data/runs/vantage_sort_fix_20261023/diagnosis_2138.jsonl` und
`diagnosis_1256_summary.json`.

## Nutzerentscheidung: fehlerhafte Einzelposition ausklammern, dann weiterlesen

Auf „eigentlich nur ausklammern die nummer“ und „warum wird dann nicht einfach
mit der nächsten Webseite weitergemacht?“ wurde der Abonnentenmodus gezielt
geändert. Nur API 1223 wird über ausgerichtete Seiten 100/50/25/5/1 eingegrenzt;
erst der scheiternde Einzel-Slot wird protokolliert ausgelassen. Keine feste
Strategie-ID oder Position 1256 im Code. Danach wird im selben 1-Monatsfenster
weiter bis zur leeren Endseite gelesen. Andere Fehler und widersprüchliche
Zähler bleiben Fehler; 20 ausgelassene Slots und 256 Zusatzanfragen begrenzen
einen flächigen Ausfall. Der normale GUI-Download bleibt unverändert.

REST überträgt Endbeleg, Vollständigkeit, Zahl gelesener Anbieter, übersprungene
Positionen, Zeitraum und Sortierung. Scanner-Status ist bei Lücken gelb
(`teilweise`), die lesbare Auswahl wird trotzdem für die Recherche akzeptiert.
Hinweise bleiben in Quelle, Einträgen, KI-Eingabe, CSV und PDF erhalten. Keine
Änderung von RetDD, Drawdown, Bewertungsregeln oder Rangformel.

129 native Tests und 159 betroffene Scanner-Tests bestanden. Der untätige
Vantage-Client wurde kontrolliert aktualisiert; der vorhandene KI-Worker
1564988 blieb aktiv. Native JAR-SHA-256:
`297bada7f225267b4c5fc186699f2dfc200450243b0c2f2e9238bf12cb1a2408`.

**Echter Anschlussjob `u-20261023-221429-63617715`:** 22:14:29–22:16:51 MESZ,
5.956 eindeutige lesbare Anbieter, Position 1256 ausgelassen, Endseite erreicht,
200 Anbieter mit positiven Kopiererzahlen ausgewählt. Native `state=done`,
`error=null`, `subscriberCatalogComplete=false`. Der Scanner bestätigt
absteigende Zähler (10 bis 470) und spiegelte die 200 Anbieter ohne Fehler;
1.453 historische Punkte und 200 eigene Messpunkte. Belege unter
`data/runs/abonnenten_live_repair_20261023/vantage_skip_live_result.json` und
`vantage_skip_verified.json`, dazu Neustart-/Startbelege und native Logs.

Dies schließt den korrigierten Listendownload ab. Der bereits zuvor laufende
Rechercheauftrag wurde während seiner KI-Phase nicht um neue Anbieter
umgeschrieben; dessen frühere Vantage-Quellenfehlermeldung gehört weiterhin
zu seinem alten Auswahlversuch. Trade-/KI-Auswertungen der neuen Vantage-
Auswahl sind durch diesen Zählerlauf nicht nachgewiesen.
