# Native Clients nach GLM-Nachprüfung aktivieren

Nutzerauftrag vom 24.10.2026: „mache die schritte“. Gemeint sind der sichere
Neustart der fünf geprüften nativen Clients, erforderliche reguläre Katalogimporte
und die Prüfung ihrer Schnittstellen. Ein neuer KI-Auftrag, Trade-Downloads und
ein Tradeserver-Deployment gehören nicht zu dieser Aktivierung.

Dieser Beleg ergänzt die [GLM-Nachprüfung](../2026-10-24_glm53_nachpruefung/README.md).
Die dortige Aussage „noch nicht aktiviert“ beschreibt den damaligen Abschluss
um 01:32 MESZ. Die folgende Aktivierung wurde danach ausdrücklich beauftragt.

## Laufende Programme

Alle fünf alten Programme wurden nach belegtem Leerlauf regulär geschlossen.
Vorhandene Datenverzeichnisse, Konfigurationen und Historien wurden gesichert.
Die neuen Java-Prozesse verwenden die bestehenden Startskripte und Datenpfade.
Da die Startskripte Maven mit `target/classes` verwenden, wurde zusätzlich
geprüft, dass die tatsächlich verwendeten Klassen und Ressourcen mit den
getesteten JARs übereinstimmen. Die JAR-Existenz allein ist kein Aktivierungsbeleg.

| Client | Neuer PID | Veröffentlichter Code | Native Tests |
|---|---:|---|---:|
| MqlDownloader | 2880400 | `33bce22` | 194 |
| Pelican | 2879276 | `3c442ea` | 222 |
| Vantage | 2998588 | `ad4a9d7` | 154 |
| Robo | 2889188 | `6164b30` | 222 |
| Zulu | 1401148 | `e38079d` | 180 |

Die Tests der drei zuletzt geänderten Clients wurden vor ihrem Neustart erneut
ausgeführt. Die Scanner-Gesamtsuite aus der GLM-Nachprüfung wurde durch diese
Betriebsaktivierung nicht erneut als ausgeführt gezählt.

## Zusätzliche Startfehler

Vantage, Robo und Zulu hatten denselben Fehler wie der zuvor korrigierte Pelican:
Das Laden eines alten GUI-Caches konnte einen neuen Tagespunkt in der
Abonnentenhistorie erzeugen, obwohl kein neuer Quellenabruf stattgefunden hatte.
Dieser Schreibvorgang wurde vor den Neustarts entfernt. Regressionen prüfen
Cachelesen und echte neue Messungen getrennt. Die drei Korrekturen sind
committet und gepusht.

Für jeden Neustart wurden die nativen Historienzeilen vor und nach dem Start
verglichen. Die Starts selbst veränderten keine Messpunkte. Echte spätere
Quellenabrufe dürfen dagegen neue Messpunkte schreiben; sie werden separat
belegt. Bestehende Tradecache-Dateien werden durch diese Metadatenimporte
nicht neu geladen.

## Katalog- und Auswahlabnahme

Gemeinsame Schnittstellenabnahme am 24.10.2026 nach dem letzten Zählerabschluss.

| Quelle | Vollkatalog | Abonnentenauswahl | Status |
|---|---:|---:|---|
| MQL4/5 gemeinsam | 391 | 200 | Beide Scopes geprüft; kein neuer Webabruf erforderlich |
| Pelican | 2.211 | 200 | Regulärer Import und Zählerlauf erfolgreich |
| Vantage | 405 | 200 | Vollimport und korrigierter Zählerlauf erfolgreich; bekannte Abdeckungslücke |
| Robo | 402 | 200 | Regulärer Import und Zählerlauf erfolgreich |
| Zulu | 449 | 200 | Regulärer Import und Zählerlauf erfolgreich |

`full` bezeichnet den vollständig angebotenen lokalen Quellenkatalog, nicht
sämtliche Anbieter der ursprünglichen Handelsplattform. Ein bestätigter
400er-Import ist kein Nachweis, alle Anbieter dieser Plattform erfasst zu haben.
Die zusätzlichen Kataloganbieter bei Robo und Zulu entstehen durch den Erhalt
bekannter IDs beim anschließenden getrennten Zählerlauf.
Listen- und Zählerfrische bestätigt keine neuen Trades, keine neue Equity-Messung
und keine aktuellen Finanzkennzahlen für jeden Kataloganbieter.

MQL besitzt einen vollständigen lokalen Datenbankkatalog und benötigt für diese
Aktivierung keinen erneuten Website-Abruf. Seine letzte Zählermessung bleibt vom
23.10.; ein Neustart macht sie nicht frisch. Für die bislang unbelegten
CSV-Bestände der anderen Clients sind tatsächliche reguläre Importe erforderlich.
Pelicans regulärer Import lädt dabei auch Profildetails und Finanzstatistiken;
das ist sein bestehender Metadatenpfad und kein zusätzlicher Trade- oder KI-Lauf.
Er endete um 05:20:19 MESZ, der getrennte Zählerlauf um 05:21:34 MESZ. Alle
2.211 Vollkatalog-IDs blieben danach erhalten. Die 35.818 früheren nativen
Historienpunkte sind bitidentisch erhalten; hinzu kamen 2.211 echte heutige
Punkte. Alle 6.901 bestehenden Closed-/Open-Trade-Dateien blieben unverändert,
es entstanden keine neuen Trade-Dateien.

Vantages regulärer Import `u-20261024-044040-fac477dc` endete um 04:51:47 MESZ
mit 400 Anbietern und gültigem CSV-SHA-Beleg. Der folgende Zählerlauf und ein
einmaliger Wiederholungsversuch scheiterten am gleichen Anbieter `1158497`:
Die API lieferte bei unterschiedlichen Seitengrößen widersprüchliche kurze
Endseiten. Der absolute Offset wurde rechnerisch geprüft. Aus den bisherigen
Belegen folgt kein interner Offsetfehler; diese beiden Läufe lieferten keinen
zuverlässigen neuen Top-200-Beleg.
Es wurde keine Auswahl veröffentlicht und kein Schutz gelockert; der gültige
Vollimport und die Historie blieben erhalten. Die bekannte isolierbare
API-1223-Lücke an Position 1256 ist von diesem neuen Widerspruch getrennt.

Die gezielte Diagnose verglich anschließend dieselben Bereiche mit 50er-,
25er-, 5er- und Einzelabfragen: sieben Prüfungen bestätigten exakt dieselbe
Reihenfolge und Kopiererzahlen. Die 100er-Antwort wich dagegen bei den IDs ab.
Das belegt größenabhängig widersprüchliche Antworten; ob ein vorgelagerter
Cache oder die Sortierung in der API die Ursache ist, bleibt unbelegt.

Der neue Zählerpfad liest deshalb von Beginn an zwei reguläre 50er-Anfragen
je bisherigem 100er-Positionsbereich. Der normale Katalogdownload bleibt bei
100er-Seiten. Ende wird erst nach beiden leeren Hälften ohne ausgelassene
Position angenommen. Die 100.000-Positionsgrenze, 256 Zusatzanfragen für
Isolation sowie Short-page-, Identitäts- und Zählerprüfungen bleiben erhalten.
Es können maximal 2.000 statt 1.000 Primäranfragen nötig werden. Die vollständige
native Suite besteht mit 154 Tests; 33 betroffene Tests wurden nach der letzten
Fixturebereinigung zusätzlich erfolgreich ausgeführt.

Der neue Build wurde sanft aktiviert, alle 108 Klassen stimmen mit dem
geprüften JAR überein. Beim zweiten Neustart blieben Full400, Receipt und alle
5.270 vorherigen Historienpunkte unverändert. JAR-SHA-256:
`16c0d07b5dd0ee7176670ccd4a5deefcd68071461e32538340bb3a23e09e1e20`.
Commit und Remote-HEAD sind `ad4a9d75d90b7f2a9484454de7618f14b90eb871`.

Der echte Zählerlauf `u-20261024-052728-7bd43315` lief von 05:27:28 bis
05:30:35 MESZ erfolgreich durch, einschließlich strenger Endseitenprüfung.
Er wählte 200 Anbieter aus 5.955 lesbaren Einträgen aus. `reachedEnd=true`,
`complete=false`, `skippedPositions=[1256]`: Die globale Top-200-Vollständigkeit
bleibt ausdrücklich unbestätigt. Alle alten 400 Katalog-IDs wurden erhalten und
fünf neue Auswahl-IDs ergänzt; Full405 und Subscriber200 sind auf allen Seiten
getrennt bestätigt. Die Historie enthält danach 5.275 Punkte. Die heutigen
405 IDs entsprechen exakt den 400 frisch importierten IDs vereinigt mit den
200 tatsächlich neu gelesenen Auswahl-IDs.

Die gemeinsame Scanner-Schnittstellenprüfung bestätigt für alle fünf Quellen
Health `ok`, beendete Jobs, vollständige Pagination und getrennte Scopes.
Insgesamt werden 3.858 lokale Katalogeinträge und je 200 positive, absteigend
sortierte ausgewählte Anbieter angeboten. Jede Auswahl ist im jeweiligen
Vollkatalog enthalten. Robo liefert weiterhin nur seine belegte
Quellenprofitabilität; unbelegte Trade-Einheiten werden durch die Aktivierung
nicht freigegeben.

## Scanner-Abgleich und unveränderte Daten

Der abschließende Metadaten-/Historienabgleich wurde nach der nativen Abnahme
um 05:39:37 MESZ erfolgreich abgeschlossen. Vorher entstand ein konsistentes
SQLite-Backup der Scanner-Hauptdatenbank; seine Integritätsprüfung ist `ok`.
Full-Kataloge, Plattformzuordnungen und erwartete Änderungen wurden vor dem
Schreiben geprüft. Alle fünf Quellen liefen ohne Abbruch oder Einzelfehler durch.

| Scanner-Abnahme | Ergebnis |
|---|---|
| Katalogeinträge vorher / nachher | 1.000 / 3.858 |
| Historienpunkte vorher / nachher | 54.970 / 58.754 |
| Neue Historienpunkte | 3.784 |
| Mit nativer Antwort korrigierte vorhandene Punkte | 54 |
| Neue synthetische Messpunkte | 0 |
| Bestehende Identitätsbindungen | unverändert |
| Bewertungen, Trade-Verweise, Studien, Berichte und Kostenbelege | unverändert |
| Recherche-Run und alle 800 Task-Datensätze während des Abgleichs | logisch unverändert |
| SQLite-Integritätsprüfung nach dem Abgleich | `ok` |

Jeder neue oder geänderte Historienpunkt entspricht exakt einem im Abgleich
empfangenen nativen Punkt. Keine vorhandenen Historienpunkte wurden entfernt.
Die geschützten Daten wurden gegen das Backup gehasht. Die einzige erwartete
Ausnahme ist die Zeile `agenten_steuerung.letzter_tick`: Der bereits laufende
Scheduler aktualisiert diesen Aktivitätszeitstempel. Genau diese Differenz
wurde vor dem Schreiben erkannt, aufgelöst und separat dokumentiert; alle
übrigen Steuerungswerte bleiben geschützt. Der separate Recherche-Store wurde
nicht geschrieben und mit einem eigenen logischen Hashvergleich geprüft.

Die tatsächlich laufende Scanner-Oberfläche wurde danach neu geladen und
geprüft. Sie zeigt `mql5 391 · pelik 2211 · robo 402 · vant 405 · zulu 449`,
den Spiegelstand 05:39 MESZ und alle fünf Clients als verbunden. Die Oberfläche
verwendet den neuen Code bereits; ein zusätzlicher Scanner-Neustart ist für
diese Aktivierung nicht erforderlich.

Alte Scanner-Eigenpunkte werden nicht nachträglich als echte Messungen deklariert
oder ohne belastbaren Herkunftsnachweis gelöscht. Der Abgleich fügt keine neuen
synthetischen Jetztpunkte hinzu. `history_punkte` zählt verarbeitete native
Punkte, nicht ausschließlich neu hinzugekommene Punkte.

## Separater KI-Auftrag

Der laufende Rechercheauftrag `d38440b65c6540b79ce69e7fe7457ab0` hat sich um
04:44:57 MESZ wegen des ausdrücklich freigegebenen 200-Millionen-Tokenlimits
angehalten (`wartet_budget`). Der Monatsprüfer meldete 199.902.027 verbrauchte
oder reservierte Tokens; die nächste Reservierung von 131.111 passte nicht mehr.
Das ist keine durch die Monitor-Neustarts verursachte Unterbrechung.

Zuletzt waren 167 von 234 Kurzanalysen abgeschlossen. Die 800 eingefrorenen
Aufgaben und der Quellensnapshot bleiben unverändert. Neue native Kataloge
fügen dem alten KI-Auftrag keine Anbieter hinzu; insbesondere wird dessen
damals fehlgeschlagene Vantage-Auswahl nicht heimlich ersetzt. Ohne weitere
ausdrückliche Budgetfreigabe bleibt die KI pausiert.

## Private Betriebsbelege

Backups, Datenbanken, Laufzeitantworten und Tradecache-Hashes bleiben lokal
unter `data/runs/glm53_activation_20261024/`. Sie enthalten keine zur
Veröffentlichung bestimmten Testfixtures und werden nicht auf GitHub gepusht.
Die Veröffentlichung dieses zusammenfassenden Review-Belegs ist durch die
bestehende Nutzerfreigabe für `doc/reviews/` abgedeckt.
