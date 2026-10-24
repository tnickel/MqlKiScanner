# Normierter Zufluss und fünf Endprüfungen

**Vom Nutzer am 24.10.2026 um 09:55 MESZ gestoppt.** Der eindeutige
KI-Worker ist bestätigt beendet. Es gibt keinen Nachweis fünf abgeschlossener
Endanalysen und keine automatische Wiederaufnahmefreigabe. Der neue Auftrag
ist zunächst ausschließlich die Daten-/Kennzahlentabelle ohne KI:
`../2026-10-24_abonnenten_daten_stufe1/README.md`.

Stand: 24.10.2026 morgens. Umsetzung und Start sind nachgewiesen;
ein vollständiger Endabschluss wird erst nach Prüfung der fünf aktuellen
Berichte und ihrer PDFs ergänzt.

## Nutzerentscheidungen

- Bestehenden Abonnenten-Rechercheauftrag fortsetzen.
- Budget ausdrücklich auf 800 Mio. Tokens je Lauf, Tag und Monat erhöhen;
  globale Einstellungen bleiben unverändert.
- 70 % Abonnentenzufluss, 30 % RetDD. Zufluss nach durchschnittlichem
  Abonnentenbestand derselben Quelle skalieren. Eine Quelle bezeichnet die
  Plattform, etwa Pelican Trading oder ZuluTrade.
- Kurz-KI ist ein optionaler Zusatz. Verbindlicher vollständiger Abschluss
  bei den fünf Endanalysen; offene wesentliche Sachfragen nicht wegmarkieren.

## Umsetzung

Die Vorauswahl verwendet native Netto-Bestandsänderung im ungefähr
siebentägigen Messfenster, geteilt durch den positiven Durchschnittsbestand
der ursprünglichen eingefrorenen Auswahl derselben Quelle. Erst die
normierten Werte werden gemeinsam in Perzentile überführt. Quelle, Umfang,
ursprünglicher Stand, Messzeitpunkte, echter Messabstand und Frische bleiben
getrennt sichtbar. Es ist kein gemessener Bruttozufluss und kein belegter
Durchschnitt der gesamten Plattform.

Native Historien werden per GET mit Identitätsbindung und festem Stichtag
eingefroren. Unbelegte Vergleichspunkte bleiben unbekannt. Scanner-Altpunkte
ohne eindeutigen Herkunftsbeleg werden nicht ersatzweise als native Messung
verwendet.

Kurzberichte dürfen fehlen. Veraltete Kurzberichte werden nicht als aktuelle
Tiefenberichtseingabe verwendet. Die Endkandidaten erhalten vollständige
Tradeanalyse und inhaltliche Prüfung ihrer ursprünglichen Hinweise. Jede
Entscheidung behält Herkunft, Berichtsbasis, Trade-SHA, Begründung und exakte
Belege. Nicht beurteilbare notwendige Grundlagen sperren den Kandidaten;
normale belegte Risiken erzeugen keine neue DD-/SL-/Calmar-Grenze.
Nachrückende Kandidaten führen zu einem neuen, belegten Vergleich.

Fünf passende Endberichte, abgeschlossene Hinweise und vorhandene aktuelle
PDFs sind Voraussetzung für `workflow_abgeschlossen`. Quelle-/Datenlücken
bleiben über `daten_vollstaendig` und gegebenenfalls `status=teilweise`
sichtbar. Ein CLI-Exit 2 allein ist deshalb kein Grund, den eingefrorenen
Gesamtauftrag erneut zu beschaffen oder heimlich zu ersetzen.

## Lokale Prüfung und Aktivierung

571 betroffene Tests mit isolierten Daten und Netzwerk-Mocks bestanden.
Anschließend separat geprüfte Regressionen sichern die Herkunftsliste der
Hinweisentscheidungen, vorhandene Frischeangaben und rein lesende Berechnung
konsistenter Anzeigeränge. Keine Änderungen an harten Forensikgrenzen.

Vor dem Neustart wurden Workerende und 276 Trade-Snapshots geprüft. Eine
SQLite-Sicherung liegt lokal vor. Die geschützten Datenfelder und der
ursprüngliche Quellensnapshot stimmen weiterhin mit der Sicherung überein;
800 ursprüngliche Aufgaben bleiben erhalten. Neue Trend- und Auswahlbelege
werden gesondert ergänzt.

Der native Trendabruf um 08:41 MESZ ergab 39 auswertbare MQL-Profile,
davon 37 mit belegtem 7-Tage-Vergleich und zwei ohne geeigneten Vergleichspunkt.
Andere Quellen haben im alten Auftrag bislang keine vollständige
RetDD-/Equity-Grundlage. Der neue Endprüfworker startete um 08:41:51 MESZ;
`budget_applied` bestätigt dreimal 800 Mio. Tokens. Dies ist ein Startnachweis.

Die erste Endanfrage endete um 08:46 MESZ am Ausgabelimit. Der vorhandene
Wiederholungsweg vergrößerte die Ausgabe, behielt aber 300 Sekunden Zeitlimit;
um 08:51 folgte ein Transporttimeout. Der automatische Endmodus erhält daher
32.768 Ausgabetokens von Beginn an und mindestens 900 Sekunden Transportzeit,
mit Stopprüfung zwischen Versuchen. Globale Defaults und Legacy-KI bleiben
unverändert. Der laufende Worker wird für die Aktivierung kooperativ beendet;
unbestätigte Kosten und Teilantworten werden nicht gelöscht oder erstattet.

Die erste vollständige Antwort um 09:11 MESZ enthielt bestätigte Textfehler
(Währungsprovenienz, Risiko-Kapitalbasis und vermischte DD-Maxima). Die erste
Klärung erhielt zudem die ursprünglichen Vergleichswerte nicht und sperrte
deshalb zwei Vergleichsfragen. Diese Eingabelücke wurde korrigiert; der
ursprüngliche Vergleich ist exakt gegen den gespeicherten Berichtshash
rekonstruiert und an seine ursprünglichen Belegregister gebunden.

Hinweise unterscheiden nun erforderliche Bewertungsgrundlagen von zusätzlichen
Risiken. Unbekannte Zusatzfragen bleiben als unbekannt dokumentiert und erzeugen
keine neue Stop-/DD-/Calmar-Regel. Pflichtgrundlagen bleiben bei Lücken gesperrt.
Eine separate Faktenredaktion prüft den Bericht vor dem PDF-Abschluss, ersetzt
eindeutige falsche Textpassagen mit Belegen und erhält die Originalantwort.
Geprüfter Text, Korrekturregister und Fakten-/Berichtshashes sind erforderlich
für den Endabschluss und im Export sichtbar.

649 betroffene Tests bestanden nach diesem Abgleich. Um 09:39:17 MESZ wurde
derselbe Auftrag mit geprüftem Originalvergleich und verpflichtender Redaktion
fortgesetzt. Die erste bezahlte vollständige Analyse bleibt erhalten; ihr
Bericht wird nicht allein wegen der Klärungskorrektur neu beauftragt.

## Weitere offene Datenpunkte

- Pelican: Die 200 alten Datenversuche scheiterten an der damaligen Sitzung.
  Aktuelle native Logs belegen inzwischen erneuerte Sitzungen; der alte
  Auftragsfehler ist kein Beleg für einen aktuellen Loginblock. Neue vollständige
  Profil-/Tradeprüfungen wurden durch bloßes Health-Lesen nicht nachgewiesen.
- Zulu: Keine vollständige RetDD-Grundlage im eingefrorenen Auftrag, unter
  anderem wegen fehlender echter Kapitalbasis oder unbelegter Kontrakte.
- Vantage: Die ursprüngliche Quellenauswahl scheiterte. Der spätere erfolgreiche
  Zählerlauf ersetzt diesen Recherche-Snapshot nicht automatisch.
- Robo: Quellenprofitabilität bleibt separat lesbar; unbekannte native
  Trade-/Volumeneinheiten erlauben keinen erfundenen Equity-DD oder Rang.
- H1-Maximum einschließlich Floating ist weiterhin kein vollständiger
  Intrabar-DD und erfasst keine unbelegten aktuell offenen Positionen.

## Private Betriebsbelege

`data/runs/abonnenten_abschluss_20261024_082414/` enthält Sicherung,
Budgetfreigabe, Auswahländerung, Prüfresultate, native Trends, Startbelege,
Quellenaudit und Laufprotokolle. Datenbanken, Antworten und Laufzeitdaten
bleiben lokal; dieser zusammenfassende Review-Beleg enthält keine Secrets.
