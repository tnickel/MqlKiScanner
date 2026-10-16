# Kritische Prüfung des GLM-5.3-Gesamtreviews

Geprüft am 16.10.2026. Der [eingereichte GLM-Text](GLM_ORIGINAL.txt) betrachtet
die sechs alten Commits aus dem Vormittagsreview. Diese Prüfung beginnt dagegen
nach den bereits umgesetzten [Gesamtreview-Korrekturen](../2026-10-16_gesamtreview/BEHEBUNG.md).
Eine am alten Stand zutreffende Behauptung ist daher nicht automatisch ein
heutiger Fehler. Der Nutzer beauftragte eine kritische Gegenprüfung und die
Behebung der bestätigten Probleme mit anschließendem Commit/Push.

## Ausgangsstand dieser Gegenprüfung

| Repository | Commit |
|---|---|
| SignalKiScanner | `a4839983e72a0c902c3cf1306ec73ac0b56251ef` |
| MqlDownloader | `908c69088a1fc8c36f20c3bffec7b3f9338bb987` |
| PelicanTrading | `c2c4ac71a889c14896366778c1d5b77b13a0adf3` |
| RoboForex | `99afb590a11bbe066555a35a9aa8a176f08130a3` |
| Vantage | `9d3849b16d77cd558bf686f3d685b6af5e016b6b` |
| ZuluMonitor | `5221b4838f935abe853b0ac8204d4f7639381e93` |

Alle Arbeitsbäume waren am Anfang sauber. Drei parallele Gegenprüfer bearbeiten
Scanner-Fachlogik/Identität, MQL/Vantage sowie Robo/Zulu/Pelican; der Hauptprüfer
untersucht die zentralen Promptregeln und die Scanner-REST-Grenze und führt
Ergebnisse, Gegenargumente und Tests zusammen. Tests verwenden synthetische
Daten und isolierte Kopien. Produktive Daten, Einstellungen und laufende
Monitore werden dabei nicht verändert; keine bezahlten Modellaufrufe oder
Plattformlogins.

## Bestätigte zusätzliche Fehler

| GLM-Befund | Gegenprüfung und Korrektur |
|---|---|
| LLM-2 / FLT-1: Score unter5 im zentralen Promptblock | Auf aktuellem Stand bestätigt. Ein deterministisch grüner Kandidat mit Score7,2 bekam im Risiko-, Gesamt- und Portfolioprompt trotzdem ein Scorelimit5 vorgegeben. Der Regelblock erklärt den Score jetzt ausdrücklich als Zusatzinformation ohne eigenes Grün-/Empfehlungsgate. Alle drei Produktionsbuilder wurden vor und nach der Korrektur getestet. |
| SYN-4: PDF-Erzeugung bei REST-GET | Auf aktuellem Stand bestätigt. Ein echter lokaler GET über die Standard-Datenquelle rief den PDF-Materialisierer auf. REST lädt nun mit `materialize_pdfs=False`; gespeicherte Evidenz wird weiterhin nach aktuellen Kriterien klassifiziert. Keine neue Forensik, kein Trade-/Kursabruf und keine PDF-Erzeugung durch den GET. |
| SYN-3: mehrdeutige Plattformidentität | Bestätigt mit synthetisch gleicher ID für MT4/MT5. Der direkte Crawler verwarf eine Variante; zwei Varianten konnten anschließend denselben Persistenzschlüssel verwenden. Varianten bleiben nun erkennbar und mehrdeutige IDs werden vor der Auswahl verworfen. Ein Wechsel gegenüber der gespeicherten Plattform wird vor Abruf/Persistenz abgewiesen. Keine Composite-PK-Migration; tatsächliche Kollisionen öffentlicher MQL-IDs wurden nicht nachgewiesen. |
| FLT-3: weißes Fehlerergebnis fällt aus Teilscan | Bestätigt. Ein zuvor erfolgreich grünes/gelbes Signal wird nach einem fehlgeschlagenen weißen Ergebnis erneut ausgewählt, gestützt auf die letzte erfolgreiche Farbchronik. Der Fehlerstatus bleibt bis zu einer erfolgreichen Neubewertung weiß. Nie erfolgreich bewertete und zuletzt rote Signale werden dadurch nicht allgemein aufgenommen. |
| FLT-6: Ertragsfallback 5 statt 0 | Teilweise bestätigt: Die Pipeline war bereits korrekt, Matrix, Regelwerk, TradeServer-Sync und Detailanzeigen verwendeten bei unvollständigen Settings noch 5. Alle verwenden nun 0; ausdrücklich konfigurierte Grenzen bleiben wirksam. |
| FIN-7: native Kontobeträge als USD bezeichnet | Bestätigt und fachlich stärker als bloße Beschriftung: USD-Floating und native Kontogeldbeträge hätten unterschiedliche Einheiten. Der direkte MQL-HTML-Pfad erhält native Beträge samt belegter Kontowährung; USD-Felder entstehen nur bei einheitlich nachgewiesenem USD. USC, Fremdwährung, fehlende und widersprüchliche Einheiten sperren USD-Forensik und Einzel-/Batchstudien vor Kurs-/Terminalaufrufen. Keine erfundene FX- oder Cent-Umrechnung. |
| MDL-4: fehlender Abonnentenstandard | Bestätigt. MQL-Providerlisten verwenden nun mindestens einen Abonnenten, auch bei leerem Parameter und in CSV. Explizit `minSubscribers=0` bleibt für Archivzugriff möglich. Filterung erfolgt vor Sortierung/Pagination; Detailzugriffe bleiben erreichbar. |
| MQL-Pagination, zusätzlicher Befund | Tatsächlicher HTTP-Repro: `offset=1&limit=2147483647` verursachte durch int-Überlauf HTTP400; große positive long-Offsets konnten nach vorzeitigem Cast Seite0 auswählen. Begrenzung vor dem Cast und long-Addition verhindern beides. Vier Listenpfade wurden über HTTP geprüft. Keine erfundene Zuordnung zu den unbeschriebenen IDs MDL-2/3. |
| VAN-1: Renditeliste fehlt bei kleinem Katalogziel | Bestätigt gegen die bestehende Vereinigungsanforderung. Nach kuratierten Einträgen erhält die Kopiererliste die abgerundete Hälfte des Restbudgets (maximal250), die Renditeliste den Rest; Überschneidungen werden nachgefüllt. Seiten dürfen das jeweilige Teilbudget nicht überschreiten. Diese Quote ist eine offengelegte Auswahlpolitik, kein statistischer Beweis optimaler Signale. |
| VAN-3a: unbekannter Umfang als vollständig markiert | Bestätigt. `TradesTruncated` ist nun dreistufig: `null` bei unbekanntem/unverifiziertem/widersprüchlichem Umfang, `true` bei belegter Kappung, `false` nur bei belegter Gleichheit. Gleiche Counts beweisen weiterhin keine unabhängige Plattformvollständigkeit. |
| VAN-8/9, teilweise beschriebener Fensterbefund | Belegt ist die fehlende Herkunft: `Average3MonthProfit` war kein 3-Monatsmittel; Ranking-DD/PF konnten ein anderes Fenster als Overview(All) haben. `metricsWindow` und `ddSource` kennzeichnen nun feldweise tatsächlichen Request und Herkunft; fünf optionale CSV-Spalten erhalten diese Provenienz. Alte Kataloge bleiben lesbar mit `unknown`. Die numerischen Legacy-Felder bleiben kompatibel. Vollständige Einzelbeschreibungen der beiden IDs fehlen. |
| Robo, zusätzliche verbleibende DD-Provenienzlücke | Nach dem bisherigen Fix weiterhin reproduziert: Ein 72-Stunden-Katalogskip konnte neue Trades mit alter Renditebasis verbinden. Bei +200/−50 und Yield10 statt aktuell15 entstand DD2,941176 statt4,166667 %. Ein versionierter Nachweis bindet DD jetzt an frisch bestätigte Katalogbasis, Identität, Fenster, genaue Deal-SHA und Abrufgeneration. Nach neuen Trades ohne frische Basis bleibt DD unbekannt. REST, GUI, Neustartcache und Berichtspfad lesen denselben Nachweis statt mit alten Ratings erneut zu rechnen. |
| Robo, zusätzlicher MT4-Zeitachsenfehler | MT4-Abschlüsse wurden in der Deal-Kurve und im Ratingfenster nach Öffnungszeit verbucht. Das vertauschte Gewinn-/Verlustreihenfolgen: +200 am dritten Tag und −100 am zweiten Tag ergeben bei Basis1000 einen DD10 %, nach falscher Öffnungsreihenfolge nur8,333333 %. MT4 verwendet nun Abschlusszeit; MT5 weiterhin seine Dealzeit. Unabhängige Tests prüfen Zeitreihenfolge und Fenstergrenze. |

Zusätzlich wird die Forensikversion auf **18** erhöht: Alte direkte MQL-Befunde
mit ungeklärter USD-Einheit benötigen eine Neubewertung. Persistierte Studien
verwenden bereits den vorhandenen DB-Versionsfilter; ungefiltert übergebene
Studien werden zusätzlich vor Übernahme auf Kontowährung geprüft. Der
Einzelstudien-Sitzungscache unterscheidet Kontowährung und Live-/Demodaten.
Berichtshashes enthalten jetzt außerdem die zentralen Promptregeln, damit
deren Korrektur vorhandene KI-Berichte als veraltet kennzeichnet.

Der H1-Hinweis am grünen Urteil und in der Calmar-Matrix wurde präzisiert:
Intrabar-Extrema, am Exportende offene Positionen und Ausführungsspread werden
nicht vollständig gemessen. Bei Teilhistorien, fehlenden Hedges oder virtueller
Kapitalbasis ist der Modell-DD keine bewiesene Untergrenze des realen Kontos.

## Bereits behobene Befunde und akzeptierte Grenzen

| GLM-Aussage | Einordnung am Ausgangsstand dieser Gegenprüfung |
|---|---|
| S1: Scanner-Stufe0 friert Vantage/Robo/Zulu ein | Bereits behoben. Alle drei aktualisieren bekannte Historien erneut. Der ausdrückliche GUI-Modus „Geladene überspringen“ bleibt ein Cachemodus; seine Hashgleichheit ist kein Plattform-Frischenachweis. |
| MDL-1: Workerfehler werden als done samt Frischevermerk übernommen | Bereits behoben: Fehler werden an den Job zurückgegeben, strukturierte Fehlerfelder und terminale Zustände bleiben erhalten; kein erfolgreicher Frischevermerk bei fehlgeschlagenem Lauf. |
| ROB-3 / ZUL-2/3 / VAN-6: DD-Basis/Scopecaps | Bereits behoben: Balanceflüsse sind kein Robo-Handelsertrag; nichtpositive/unbelegte Basen und unpassende Tradeumfänge erlauben keinen modellierten DD0. Alte unversionierte DD-Werte in Pelican/Vantage/Zulu bleiben unbekannt. |
| LLM-1: alter monatlicher Mindest-RetDD | Bereits behoben: Portfolio-Codebefund verwendet den aktuellen Jahres-Calmar und dessen konfigurierte Schwelle. |
| LLM-3 / LLM-4: Monatsbudget und autonome Scankosten | Bereits behoben: gemeinsame transaktionale Reservierung pro Agenten-HTTP-Versuch einschließlich autonom gestarteter Scans, Tages-/Monatsgrenzen und Retryjournal. Manuelle GUI-Scans besitzen bewusst ihr eigenes Laufbudget; das ist keine heimliche Umgehung eines für alle Nutzung zugesagten Globalbudgets. |
| SYN-1: min_calmar_jahr fehlt im Berichtshash | Bereits im vorigen Fix enthalten. Diese Gegenprüfung ergänzt die Bindung an die zentralen Promptregeln, damit deren Korrektur nicht nur neue Berichte betrifft. |
| SYN-2: Studien ohne Forensikversion | Bereits behoben: persistierte Studien tragen eine Forensikversion; alte Studien werden nicht als aktuelle Freigabe wiederverwendet. |
| S6 / FIN-6: H1 statt Intrabar, fehlende offene Positionen | Dokumentierte Methodikgrenze. Eine Behauptung „vollständiger historischer DD“ wäre falsch; es wird keine Tickpräzision aus H1-Daten erfunden. Die Grenze verlangt Kennzeichnung, keine heimliche Neudefinition der Messmethode. |
| FLT-4 / MDL-5 / ROB-5: eingeschränkte Kandidatenuniversen | Auswahlpolitik und Abdeckung müssen offengelegt werden. Abonnenten-Top-N, MQL-Katalogstichprobe und Robo-Yieldobergrenze beweisen weder vollständige Plattformabdeckung noch künftige beste Signale. Keine statistisch unbegründete Ersatzregel wird eingeführt. |
| S7: wechselnde Testfehler / PathLike | Der konkrete `WindowsPath.lower`-Fehler ist bereits durch Stringkonvertierung behoben. Ohne identifizierten Polluter beweisen einzeln grüne Tests keine bestimmte Pollution-Ursache. Die neue PathLike-Regression und die abschließende Gesamtsuite prüfen den aktuellen Stand. |
| MDL-11: Dateinamenziffern ergeben falsche CSV-ID | In der behaupteten Form bereits am GLM-Ausgangscommit widerlegt: `ProviderFiles.extractSignalId` verwendet das letzte Unterstrichsegment, keine Verkettung sämtlicher Namensziffern. Bestehende Regression für Zahlen im Providernamen besteht. |

Der Quellenmodus erhält einen durch die jeweilige Quelle begrenzten Katalog.
`min_abonnenten=0` im Scanner bedeutet keinen zusätzlichen lokalen
Abonnentenfilter, keinen garantierten Abruf sämtlicher Plattformanbieter.
Fix-IDs umgehen lokale Vorfilter/Slots; im reinen Quellenmodus gibt es bereits
vor dieser Änderung keinen garantierten Einzelabruf fehlender Katalog-IDs
(`test_fix_signale.py::test_crawl_quellen_modus_protokolliert_fehlende_fix_id`).
Der MQL-Archivzugriff mit explizit0 bleibt verfügbar, wird aber nicht
automatisch für sämtliche Scannerabrufe eingeschaltet. Pelicans verbindliche
Mindestens-ein-Abonnent-Regel bleibt erhalten.

Vantages neue Herkunfts-/Fensterfelder werden im Rohartefakt erhalten und per
Quellen-REST angeboten; der Scanner wertet sie derzeit noch nicht für eigene
Rangregeln oder eine vereinheitlichte Monatsrendite aus. Die Anzeigegröße
`ertrag_anzeige` bleibt deshalb zwischen Quellen methodisch eingeschränkt
vergleichbar. Das eigene Ertrags-/Calmar-Gate verwendet die eigene Messung.

Die Regeln für Top-N, Mindestalter und Calmar sind Projektregeln. Diese
Gegenprüfung liefert keine Out-of-Sample-/Walk-Forward-Validierung, keine
Korrektur für Mehrfachselektion, keine garantierte kopierbare Nettorendite
und keinen Nachweis künftig bester Signale. Korrelationen und gleichzeitige
Portfolioverlustphasen werden dadurch nicht zu einer rechnerischen Freigabe.

## Aussagen ohne ausreichenden Nachweis

- Acht gelungene Nachrechnungen beweisen keine Fehlerfreiheit des gesamten
  Finanzkerns. Die vorherige unabhängige Prüfung hatte am selben alten Stand
  konkrete falsche Grünfälle und weitere Rechenfehler reproduziert und
  inzwischen behoben. Die GLM-Aussage „alle Kernformeln exakt“ reicht über
  die nachgewiesene Stichprobe hinaus.
- Stale Historien können spätere Verluste **und Gewinne** auslassen. Ein
  Datenfreeze ist ein echter Datenqualitätsfehler; die pauschale Behauptung,
  er mache sämtliche Ampeln systematisch zu positiv, ist damit noch nicht
  statistisch belegt. Auch die Einstufung als P0 ist durch den eingereichten
  Nachweis nicht begründet.
- Pelicans Relation `tradesTotal` zu einer Teilmenge exportierter Positionen
  beweist keinen falschen Winrate-Nenner. Der versionierte Stats-Beleg hat
  Total30166 und Wins+Losses15207 (Verhältnis1,98369); der Closed-Fixture
  umfasst nur637 Septemberpositionen. Zeitfenster und Zählgegenstände sind
  nicht gleichgesetzt. Eine Änderung des Nenners braucht belastbare
  Plattformsemantik; die Behauptung bleibt offen.
- „Historische FX-Umrechnung auch in Robo“ und „Commission=0 in Robo-Exporten“
  sind nicht bestätigt: Robo exportiert numerische Geldbeträge ohne eigene
  historische FX-Normalisierung und verarbeitet vorhandene Commission/Storage.
  Ungeklärte Kontowährungs-/Lotssemantik bleibt eine bestehende Grenze.
- Die genannten IDs MDL-2/3, MDL-8/9/12, VAN-8/9, SYN-5…12 und mehrere
  LLM-/Robo-IDs enthalten im bereitgestellten Text keine konkreten
  Fehlerbeschreibungen oder Codeorte. Ohne die angekündigten Teilberichte
  lassen sich daraus keine zusätzlichen bestätigten Bugs ableiten. Der
  Nutzer wurde nach konkreten Angaben gefragt; es werden keine Inhalte zu
  solchen IDs erfunden.

## Testmethode und Nachweise

Die neuen Scanner-Hub-Repros scheiterten vor der Korrektur in allen vier
Fällen und bestehen danach. Die angrenzende Prompt-/REST-/SHA-Batterie bestand
mit48 Tests. Weitere29 Scanner-Regressionen decken Identitäten, Teilscan,
Fallbacks, Währung, Studien und PathLike ab; die ersten elf scheiterten vor
der Korrektur am erwarteten Fehlverhalten. Zielgruppen mit202,313 und109
bestandenen Tests überlappen und werden nicht addiert.

| Bereich | Abschließender isolierter Lauf | Build |
|---|---:|---|
| Scanner, gesamte Standardsuite | **1998 bestanden**, 4 übersprungen, 4 kostenpflichtige LLM-Tests abgewählt; 544,78 Sekunden | Python-Suite erfolgreich |
| MqlDownloader | **116 bestanden** | `mvn -o -B package` erfolgreich |
| Vantage Java | **65 bestanden** | `mvn -o -B package` erfolgreich |
| Vantage Python | **12 bestanden** | unveränderter Pythoncode im selben Snapshot |
| Robo, gesamte Java-Suite | **179 bestanden** | Offline-Test und Package erfolgreich |
| Pelican, passende Bestandsregressionen | **46 bestanden** | Package erfolgreich; nur README/Javadoc geändert |
| Zulu, passende Bestandsregressionen | **18 bestanden** | Package erfolgreich; nur README/Javadoc geändert |

Die vier Scanner-Skips benötigen private reale Exportdateien und sind keine
grünen Prüfungen. Bezahlte Modelltests wurden bewusst nicht gestartet.
Das konkrete historische PathLike-Problem trat im gesamten neuen Lauf nicht
auf; daraus folgt keine Garantie gegen jede mögliche zukünftige Testpollution.
Die bestätigten Fehler sind mit Regressionen behoben. Bloße IDs ohne
Fehlerbeschreibung und die unbelegte Pelican-Nennerhypothese bleiben offen;
sie werden ausdrücklich nicht als behoben oder widerlegt ausgegeben.

Die Snapshots bestehen aus Git-HEAD **plus aktuellen Änderungen und nicht
ignorierten neuen Testdateien**, keine Tests allein des alten HEAD. Nach dem
Scanner-Freeze wurden nur Dokumentation/Nachweise ergänzt. Nach dem MQL-Test
wurde nur die technische API-Dokumentation zum geprüften neuen Standard
ergänzt. Alle finalen Code-/Testdateien werden gegen die getesteten
Snapshotbytes geprüft, wobei LF/CRLF-Normalisierung zulässig ist.

[Maschinenlesbare Ergebnisse](nachweise/test_results.json),
[SHA-256 der Nachweise](nachweise/sha256.json) und
[Scanner-JUnit](nachweise/Scanner_final.pytest.xml) belegen den Lauf.
Die gezielten überlappenden Vorläufe werden zusätzlich archiviert, aber nicht
zur Anzahl bestandener unabhängiger Tests addiert.

Fachbelege: [Scanner](nachweise/clients.md),
[MQL/Vantage](nachweise/quellen_a.md),
[Robo/Zulu/Pelican](nachweise/quellen_b.md),
[deren unabhängige Consumer-Gegenprüfung](nachweise/quellen_a_peer_review.md),
[unabhängige Währungs-/Studienprüfung](nachweise/fin7_peer_review.md) und
[unabhängige Robo-Provenienzprüfung](nachweise/robo_dd_peer_review.md).

## Nach Aktualisierung

Quellen und Scanner aus dem veröffentlichten Code neu bauen/starten und
betroffene Signale erneut laden und analysieren. Ein Push ersetzt keinen
laufenden alten Prozess. Direkte MQL-Konten ohne eindeutigen USD-Beleg bleiben
gesperrt. Robo-Prozent-DD benötigt frisch geladene Ratingdaten und die dazu
passende neue Dealhistorie; ein Katalogskip lädt Trades weiter, erzeugt aber
keinen Prozent-DD aus einer alten Renditebasis. Alte KI-Berichte und Befunde
gelten wegen Regelhash/Forensikversion18 nicht als aktuelle Freigabe.
