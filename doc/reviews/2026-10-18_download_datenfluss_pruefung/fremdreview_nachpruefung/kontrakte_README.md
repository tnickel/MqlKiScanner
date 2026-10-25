# Kontrakte und Fachregeln: unabhängige Nachprüfung am 18.10.2026

Prüfgrundlage: angehängter Fremdreview, aktueller Arbeitsbaum, statische Registry,
lokale Instrumentenbelege und isolierte Regressionstests. Keine Produktionsdaten,
Terminals, Apps oder Downloads wurden geändert oder gestartet. Die Registry
`data/contract_specs.json` wurde nicht geändert. Historische Belege sind kein
Nachweis aktueller Live-Instrumente.

## Gesicherte Ergebnisse

Die Empfehlung, Vantage UKOUSD, SP500 und NAS100FT neu einzutragen, ist überholt.
`symbols.spec_for` und `exposure._resolve_symbol` liefern für Vantage bereits
UKOUSD 1000 USD, SP500 1 USD und NAS100FT 1 USD je Einheit Kursbewegung und Lot.
Auch CL-OIL, DJ30/DJ30FT, SP500FT und die Goldkreuze XAUAUD/XAUJPY sind vorhanden.
XAUAUD wird mit 100 AUD und XAUJPY mit 100 JPY aufgelöst; native Gewinnwährung und
USD-Umrechnung sind verschiedene Schritte. Die konkrete Auswahl samt
Registry-Schlüssel, Belegtext und Brokerbindung steht in `kontrakte_resolver.json`.
Die datierten Vantage-Belege befinden sich unter anderem in
`doc/reviews/mt5_vantage_kontrakte_2026-10-10.json` und in den Quellenangaben der
einzelnen Registry-Einträge. Für NAS100FT und weitere FT-Symbole existieren auch
lokal dokumentierte Trade-Rückrechnungen.

Für AxiTraderUs07Live und AxiTrader5 lösen COIN, TSLA und USOIL dagegen nicht auf.
Das ist anhand der vorhandenen Belege korrekt: COIN ist für Vantage hinterlegt,
TSLA für RoboForex und USOIL-FUTURE für AxiTrader2. Aus einer ähnlichen
Serverbezeichnung oder einem gleichnamigen Symbol folgt keine Brokerfreigabe.
Die AxiTrader2-Belege liefern USOIL-FUTURE 1000 USD und US500-FUTURE 50 USD je
Punkt/Einheit und Lot. Damit sind weder andere AxiTrader-Server noch deren
Aktienkontrakte belegt. Eine Freischaltung der drei im Fremdreview genannten
Pelican-Signale durch bloßes Ergänzen von `brokers` wäre unbegründet.

Die Behauptung, jede Forensik benötige ein ursprünglich in USD geführtes Konto,
ist zu pauschal. `ingest.metrics_zu_stats` erkennt die dokumentierten
USD-normalisierenden Exportverträge Pelican, Vantage und Zulu an. Pelicans
`Currency` kann dabei die ursprüngliche Kontowährung beschreiben. Native
MQL-Exporte bleiben ohne nachgewiesenes USD gesperrt; Quellenalias und REST-
Transport allein beweisen keine Einheit. Die Prüfung liegt in
`pipeline.require_usd_account`; Regressionen prüfen sie vor Kurs-/Terminalzugriff.

Der Fremdreview hat recht, dass `Balance minus Nettoergebnis` keine implizite
Kapitalbasis werden darf. Dieser Fallback ist im aktuellen Code bereits entfernt.
`signal_statistik.kapitalbasis_kaskade` verwendet belegtes Initial Deposit vor
ausdrücklich ausgewiesener virtueller Basis. Der Drawdown- und Exposure-Pfad
verwendet echte CSV-Einzahlungen vor Handelsbeginn vorrangig; Vorabentnahmen und
Kosten werden berücksichtigt. Fehlen beide Kapitalbelege und eine ausdrücklich
zulässige virtuelle Annahme, entsteht keine prozentuale Kapitalbasis.

Die Gleichsetzung von drei Monaten und zwölf Wochen ist falsch.
`portfolio_statistik` verwendet 365,2425 Tage/Jahr und Jahr/12 je Monat.
Drei Monate sind damit 91,310625 Tage beziehungsweise rund 13,044 Wochen.
Die tatsächliche Exportzeitspanne einschließlich Leermonaten bleibt maßgeblich.

Die behauptete H1-Lückenschwelle von 1 % ist kein aktueller Codevertrag.
`equity_rekonstruktion.SCHRANKE_MIN_ABDECKUNG` beträgt 0,95. Vollmessung benötigt
zusätzlich vollständige Tradezuordnung, vorhandene FX-Belege und verlässliche
Zeitbasis. Der Code kennt außerdem eine ausdrücklich dokumentierte Teilmessung:
vollständig fehlende Symbole werden benannt; die betrachtete Teilbasis muss
mindestens 95 % Abdeckung und gültige FX-/Zeitbasis haben. Stundenlücken in einem
ansonsten betrachtbaren Symbol werden dadurch nicht freigegeben. Solche
`ok_teilmessung`-Ergebnisse können laut bestehendem Vertrag als Nenner verwendet
werden. Das ist von orange markierten, unzuverlässigen Vorbehaltswerten zu trennen.
Dieser Prüfauftrag ändert diese fachliche Entscheidung nicht.

Die aktuelle `FORENSICS_VERSION` beträgt 19. Eine Anzahl gespeicherter
Forensikzeilen belegt keine aktuelle Verwendbarkeit: `results_from_db` prüft unter
anderem beide Versionsfelder, Schockbefund, Trade-SHA und nachfolgende Fehler.

## Behobener Diagnosefehler

`forensics/exposure.py` empfahl bislang bei einem nicht freigegebenen Broker
pauschal, `brokers` zu ergänzen. Der Hinweis verlangt jetzt ausdrücklich einen
für Broker und Instrument passenden Beleg für Kontraktgröße und Gewinnwährung
samt Quelle. Eine Registry-Ergänzung allein zur Freischaltung wird ausgeschlossen.
Die fachliche Sperre und sämtliche Rechenregeln bleiben unverändert. Die bereits
vorhandene Änderung zur konfigurierbaren DD-Schranke wurde bewahrt.
Der bestehende Test `test_cross_broker_false_needs_matching_broker` prüft auch
die Belegpflicht im Fehlerhinweis.

## Offene Beleginkonsistenz, keine erfundene Korrektur

GER40FT und UK100FT haben doppelte Registry-Angaben: die tatsächlich gewinnenden
brokergebundenen Vantage-Einträge verwenden USD-Medianfaktoren 1,08 bzw. 1,35;
die ungebundenen parallelen Einträge beschreiben 1 EUR bzw. 1 GBP. Die
Brokerpriorität des Resolvers ist beabsichtigt. In den hierfür eingesehenen
lokalen MT5-Instrumentensnapshots wurde kein unabhängiger FT-Metadatenbeleg
gefunden, der die Wahl eines der widersprüchlichen Modelle abschließend trägt.
Die Alternativen stehen ausdrücklich in `unresolved_registry_conflicts` des
JSON-Nachweises. Hier wurden weder neue Faktoren noch Brokerrechte erfunden.
Ein erster explorativer Probevergleich hatte die ungebundenen nativen Angaben
als Sollwert angenommen und zeigte genau diese zwei Unterschiede; der finale
Probecheck trennt den tatsächlichen Registryvertrag und diese offene Evidenzfrage.
Die Aussage „23 Resolverprüfungen passend“ bestätigt daher Auflösung und
Brokerabgrenzung, keine neue fachliche Verifikation dieser beiden FT-Modelle.

## Nachweise und Grenzen

- `kontrakte_probe.py`: statischer Repro; 23 Auflösungen, Exit 0. Keine DB-/REST-
  oder Terminalzugriffe. Erwartungswerte und offene Widersprüche sind getrennt.
- `kontrakte_resolver.json`: konkrete Auflösungen und SHA-256 der unveränderten
  Registry; alle oben genannten Brokerfälle reproduzierbar.
- `kontrakte_tests.xml`: abschließender isolierter Testlauf mit **189 bestanden,
  0 fehlgeschlagen, Exit 0**, pytest 8,77 s. Aufruf in `kontrakte_tests.json`.
- `kontrakte_tests_intermediate.xml`: ausdrücklich überholter Zwischenlauf mit
  185 bestanden/4 fehlgeschlagen. Die vier Tests verwendeten nach der gleichzeitig
  umgestellten Katalogschnittstelle noch `stats[123]` statt `stats[("robo",123)]`.
  Root hat diese Testkonsumenten korrigiert; die Währungsprüfung selbst bestand.

Unabhängige lesende Gegenprüfung des parallel erstellten Katalogfixes:
Die beiden produktiven `katalog_resultate`-Konsumenten sind `alle_signale.py`
(Stats je Quelle+ID) und `equity_studie.py` (Stats ignoriert, Quelle sichtbar).
Artefakte werden weiterhin nach Quellen-ID+Signal-ID+Version gelesen.
Kollidierende ID-Studien werden vor Tabellenmapping entfernt, der Einzelstudien-
Guard liegt vor Sessioncache/Kurszugriff, der Batchguard vor dem Kurszugriff.
Die DB-Lese-/Schreibguards werden vom zuständigen Agenten getestet. Im gelesenen
Stand kein weiterer bestätigter Produktionsfehler in diesen Änderungen.
Markierungen, Kommentare und Fix-IDs bleiben ID-weit; die Übersicht weist darauf
bei Kollision explizit hin. Dies ersetzt keine vollständige Composite-Migration.
