# Kritische Prüfung des DeepSeek-Gesamtreviews

Geprüft am 16.10.2026. Der [eingereichte Text](DEEPSEEK_ORIGINAL.txt)
betrachtet dieselben alten Ausgangsstände wie das Vormittagsreview. Hier wird
gegen den inzwischen veröffentlichten Stand geprüft, einschließlich der
[ersten Korrekturen](../2026-10-16_gesamtreview/BEHEBUNG.md) und der
[GLM-Gegenprüfung](../2026-10-16_glm53_pruefung/README.md).
Alte zutreffende Befunde werden nicht erneut als neue Fehler ausgegeben.

## Ausgangsstand

| Repository | DeepSeek-Prüfstand | Stand vor dieser Gegenprüfung |
|---|---|---|
| SignalKiScanner | `80d4692548c9` | `cef1e5af53e5737eb3dfdc2e093c8b7b979a83b5` |
| MqlDownloader | `92d8f9cea10b` | `c5848ab057758d1505173cc4fcaaeee4a390e2b9` |
| PelicanTrading | `dde77d705a67` | `2c611aea3c3dcf092cceb369349f191f596b3d52` |
| RoboForex | `42b268641ad3` | `82223abd09ebf2ab27e30eac8b5026c88f67a2b6` |
| Vantage | `1fe395805f29` | `28d2021863f35a0514b45b0fc802fb80d119368c` |
| Zulu | `72df0cf49aa4` | `d1a54ff8406577574e788678a1b8713a99077f29` |

Alle neun Repository-Arbeitsbäume waren zu Beginn sauber. Drei parallele
Teilprüfungen untersuchen Parser/Testdaten, Budget/Prompts/Regelwerk und
Quellen-Altersdaten. Die Hauptprüfung korrigiert weitere belegte Anzeige-
und Hilfetextfehler und führt unabhängige Gegenprüfungen und Tests zusammen.
Keine bezahlten Modellaufrufe, Plattformlogins oder Änderungen produktiver
Daten und Einstellungen. Die endgültigen Testnachweise entstehen in
isolierten Git-Snapshots mit aktuellem Code-/Testoverlay.

Bei einem ersten Parser-Zwischenlauf wurde versehentlich noch im Checkout
getestet und der optionale private Export einmal **lesend** geparst. Keine
Tradeinhalte wurden kopiert, ausgegeben oder veröffentlicht. Dieser Lauf ist
kein endgültiger Nachweis; der Bericht legt ihn offen. Danach wurden alle
Parser-Abschlussprüfungen ausdrücklich im isolierten Archiv ausgeführt.

## Einordnung der genannten Befunde

| Befund | Ergebnis auf aktuellem Stand |
|---|---|
| P1-1: unbekanntes Alter / falscher Ingest-Kommentar | Bereits vor diesem Auftrag korrigiert: `ingest.kandidaten` dokumentiert unbekanntes Alter als regulär abgewiesen. Der Mindestalterfilter ist eine bewusste Belegpflicht, keine Zusage, unbekanntes Alter durchzulassen. Fix-IDs dürfen lokale Vorfilter umgehen. Ausschlüsse werden begründet; der Katalog und die Auswahlansicht zeigen auch nicht bewertete Signale. |
| P1-2: `Path.lower()` | Bereits behoben: `parser.load_export` normalisiert zuerst mit `str(path)`. Öffentliche PathLike-Regression vorhanden. Keine erneute Parser-Codeänderung erforderlich. |
| P1-3: Test benötigt privaten Cache | Als Reproduzierbarkeitsgrenze zutreffend, kein verdeckter heutiger Parserfehler: Footer-/Spacer-/Fehlzeilen waren bereits synthetisch abgedeckt. Jetzt versionierte vollständig synthetische MT4-/MT5-Fixtures und elf öffentliche Fälle; ein Großmengenfall mit 2520 Trades und neun Kontobewegungen deckt die bisherigen privaten Strukturassertions ab. Der private Residualtest wurde erst nach dieser Redundanzprüfung entfernt. Keine privaten Tradezeilen veröffentlicht. |
| P2-1: Monatsbudget nur Anzeige | Bereits behoben: gemeinsames transaktionales Tages-/Monatsledger reserviert vor jedem Agenten-HTTP-Versuch; autonome Scans sind eingeschlossen. Retry, Monatsgrenze und Parallelität besitzen Regressionen. Manuelle GUI-Läufe haben ihren dokumentierten eigenen Laufbudgetvertrag. |
| P2-2: Portfolio-Prompt verlangt Monats-RetDD mindestens1 | Bereits behoben: `portfolio_statistik` übergibt den aktuellen Jahres-Calmar und die konfigurierte Schwelle; Monats-RetDD ist Zusatzinformation. Ein verwandter sichtbarer Regelwerkfehler wurde zusätzlich gefunden und unten behoben. |
| P3-1: Fallback5 statt0 | Bereits in der GLM-Korrektur vereinheitlicht, einschließlich Regelwerk, Matrix, Detailanzeige und TradeServer-Sync. Explizite Nutzereinstellungen gehen weiterhin vor. |
| `min_abonnenten=1` statt dokumentierter0 | Code-Default und gespeicherter Instanzwert sind unterschiedliche Dinge. Code-Default bleibt0; die vom Fremdreview genannte lokale1 ist keine Begründung, den allgemeinen Default oder private Settings umzuschreiben. Das Benutzerhandbuch erklärt den Vorrang aktiver Einstellungen und die separate Quellkatalog-Auswahl. |

## Zusätzlich bestätigte Fehler und Korrekturen

### Sichtbares Regelwerk widersprach weiterhin der Engine

`regelwerk_markdown` nannte noch Monats-RetDD mindestens1 und erlaubte eine
Monitor-Messung als Equity-Nenner. Das betraf die Ergebnis- und Detailansicht,
obwohl Portfolio-Prompt und Engine bereits korrekt waren. Jetzt verwendet die
Beschreibung den konfigurierten Jahres-Calmar, mindestens drei Monate
Trade-Historie und ausschließlich eine belastbare eigene H1-Equity-Messung
einschließlich Floating. Monitor-DD bleibt Schrankenkanal. Zwei produktive
Builder-Regressionen scheiterten vorher für Default3 und konfiguriert4,25.

### Stationsdialoge zeigten Monatswert als Jahres-Calmar

Station3 und Station5 zeigten unter `TrueRetDD` noch `true_retdd_monat` und
den Monats-Vorbehalt; die Beschreibung bezeichnete die Zahl als Jahres-Calmar.
Bei Jahres-CAGR60% und DD10% erschien0,4 aus Monatsrendite4% statt Calmar6.
Die beiden Forensik-Tabellenpfade und die Portfolio-Tabelle verwenden jetzt
Jahreswerte mit dem passenden Jahres-Vorbehalt. Die Forensikcaption verwendet
außerdem die aktive Schwelle statt einer festen3. Vier echte AppTest-Fälle
reproduzierten vorher den falschen Wert; zusätzliche bestehende Tests prüfen
belastbare und orange Vorbehaltswerte. Die Gate-Berechnung wurde nicht geändert.

### Hilfe und Tooltips beschrieben falsche Mess- und Auswahlregeln

Aktive Texte erlaubten Monitor-Closing-DD als historische Floating-Messung,
nannten den Risiko-Score als Grün-Hindernis und setzten Dollar-Schockmaximum
mit maximaler Positionsanzahl gleich. Hilfe, Stationscaption und Matrixtexte
beschreiben jetzt eigene Kursmessung, informative Scoreanzeige sowie den
instrumentabhängigen Schock und Kontostand am passenden Zeitpunkt. Full-/
Teilscan-Hilfe berücksichtigt Quellen, Auswahl und Wiederholungen fehlgeschlagener
vormals grüner/gelber Signale. Keine neue Rechen- oder Auswahlpolitik.

### Quellenalter

| Quelle | Bestätigte Korrektur und Beleggrenze |
|---|---|
| Vantage | 182 Tage Aktivität konnten über fünf volle Monate als22 Wochen erscheinen. Ganze Wochen werden jetzt direkt aus datierter lokaler Aktivität bestimmt: 182 Tage ergeben26, 181 Tage25. Daily-Nullauffüllungen zählen nicht als Aktivität; ältere verifizierte Trades werden ebenfalls berücksichtigt. Der Wochenwert aktualisiert sich unabhängig von der Katalog-CSV-Dateizeit. Die Historie belegt eine Untergrenze, kein Plattformgründungsdatum. |
| Vantage, zusätzlicher Producerfehler | Fehlende/ungültige Tagesdaten wurden über `asLong()` zu Epoch0 und damit1970. Positive PnL konnte daraus einen unbelegten Altersnachweis machen. Pflichtdatum wird nun vor Umwandlung validiert; ungültige/zukünftige Daten brechen den Download ab. Persistierte Epoch-Sentinelzeilen sind ebenfalls kein Altersbeleg. Der Test prüft API → Store → REST mit ungültigen sowie gültigen numerischen/String-Zeitstempeln. |
| Zulu | Fehlende `overallStats.weeks` wurden als0 gespeichert. Nullable Modellwert und angehängte CSV-Spalte `WeeksKnown` erhalten unbekannt gegenüber echter0. Legacy0 ohne Kenntnisbeleg bleibt unbekannt. Ungültige/nichtendliche/negative/nichtganzzahlige Angaben werden nicht als Alter verwendet. |
| Robo | Jahr-1-Sentineldatum konnte scheinbar Jahrhunderte Alter liefern. Fehlendes, Sentinel- und zukünftiges Angebotsstartdatum bleiben unbekannt; ein echter182-Tage-Beleg ergibt26 Wochen. |
| Pelican | Ein zukünftiges Inception-Datum lieferte ein negatives Alter. Es bleibt nun unbekannt; fehlende/Jahr-1-Werte waren bereits abgefangen. |
| MQL | Im aktuellen Producer gibt es keinen belegten Katalog-Alterswert. Dass der TXT-Parser theoretisch beliebige Schlüssel lesen kann, erzeugt keinen `Weeks`-Beleg. Abonnenten-Snapshots beweisen kein Signalgründungsdatum. Diese Datenlücke ist dokumentiert und wurde nicht mit einem geschätzten Alter verdeckt. |

Vier Quellen nennen `weeksSource`/`WeeksSource`. Diese Herkunft ist kein
Live-Frische- oder Vollständigkeitsbeweis. Zulus sichtbare Wochenspalte zeigt
unbekanntes Alter nun leer; Vantages Altersdetail zeigt ausdrücklich
„Wochen unbekannt“. Primitive Filtergetter bleiben kompatibel. Ein kurzer
oder gekappter Cache kann tatsächliches Alter weiterhin unterschätzen;
ungeprüfte API-Monate werden deshalb nicht in exakte Gründungstage verwandelt.

### Nicht endliche Altersangaben umgingen den Scannerfilter

Im echten synthetischen JSON → Ingest → Kandidaten-Pfad wurden `"NaN"` und
`"Infinity"` zu nicht endlichen Floatwerten. `nan < 26` ist falsch; positive
Unendlichkeit ist ebenfalls nicht kleiner. Beide konnten ohne Altersbeleg
die Auswahl passieren. Direkte numerische Strings verursachten dagegen
einen Typfehler. Der gemeinsame Normalisierer akzeptiert nun endliche,
nichtnegative Zahlen und numerische Strings, verwirft Booleans und ungültige
Werte als unbekannt. Direkte Kandidaten werden ebenfalls geprüft, ohne den
Eingangskatalog zu verändern. Die inklusive26-Grenze und die ausdrückliche
Fix-ID-Ausnahme bleiben erhalten.

110 parametrisierte Fälle decken beide Eingangswege, Minima0/26, gültige
Grenzwerte und Fix-IDs ab. Vor dem Fix schlugen77 dieser Fälle fehl; das
sind verschiedene Regressionen desselben Vertrags, keine77 unabhängigen
Produktfehler. Danach bestanden205 gezielte Fälle. Dieser Nachtrag wurde
im abschließenden neuen Scanner-Snapshot nochmals vollständig getestet.

## Fachliche Aussagen mit unzureichender Grundlage

- Fünf DD-Kanäle sind keine fünf statistisch unabhängigen Messungen. Sie
  können dieselben Trades und verwandte Plattformangaben verwenden. Das
  Maximum ist eine konservative Projektregel, kein Unabhängigkeitsbeweis.
- H1-Kurse verpassen Intrabar-Extrema. Eine garantierte Untergrenze des
  tatsächlichen Konto-DD folgt daraus bei anderer Kapitalbasis, Teilhistorie
  oder fehlenden Positionen/Hedges nicht. Monitor-Closing-DD bleibt ein
  eigener Modellkanal und kein Calmar-Nenner.
- „Risikoärmste unter den abonnentenstärksten“ ist ebenfalls zu stark:
  Calmar bewertet Rendite relativ zum gemessenen DD, nicht ausschließlich
  den kleinsten DD. Out-of-Sample-, Walk-forward- und Sensitivitätsnachweise
  werden durch diese Reparaturen nicht ersetzt. Die konkrete Größe einer
  Rangunsicherheit lässt sich ohne Datenanalyse nicht behaupten.
- Der alte strengere Portfolio-Hinweis konnte Empfehlungen unterdrücken;
  daraus folgt keine zu positive Ampel. Auch eine nicht automatisch
  aufgehobene Ausschlussliste erklärt eher fortbestehende Ablehnung als
  falsches Grün. Ein falscher oder überholter manueller Eintrag kann ein
  Fehlurteil bewahren; automatische Löschung durch bessere Kennzahlen wäre
  dafür keine begründete Reparatur.
- Die Aussage, riskante Signale würden zuverlässig aussortiert, ist ohne
  Einschränkung durch Datenabdeckung, Modellannahmen und künftige Regime
  nicht belegt. Mindesthistorie, Calmar3 und Top30 sind Projektregeln, kein
  Nachweis künftig bester oder risikoärmster Signale.

## Verifikation

Die vollständige Standardsuite des Scanners besteht auf dem endgültigen
Snapshot `Scanner_final3`: **2125 bestanden, 3 übersprungen, 4 kostenpflichtige
LLM-Tests abgewählt; 559,99 Sekunden**. Dieser Lauf enthält auch die zuletzt
ergänzte Wochenvalidierung. Der vorherige volle Lauf mit2015 bestandenen Tests
in `Scanner_final2` war noch ohne diesen Nachtrag und wird nicht als dessen
Nachweis gezählt. Alle fünf Quellen wurden vollständig isoliert getestet und gebaut:

| Quelle | Java-Tests | Weitere Prüfung | Build |
|---|---:|---|---|
| MqlDownloader |116| nur README geändert | package erfolgreich |
| PelicanTrading |180| Altersgrenzen | package erfolgreich |
| RoboForex |180| ungültige Datumsbelege über REST | package erfolgreich |
| Vantage |70|12 Python-Tests, API → Store → REST | package erfolgreich |
| Zulu |118| API-/CSV-/REST-Unterscheidung unbekannt/0, bestehende UI-Tests | package erfolgreich |

Insgesamt664 Java- und12 Python-Quellentests bestanden ohne Fehler oder
Skips. Zielgruppen des Scanners überlappen und werden nicht addiert.
Private Datenfälle und kostenpflichtige LLM-Tests gelten nicht als bestanden,
wenn sie übersprungen beziehungsweise abgewählt werden.

Die Snapshots enthalten den jeweiligen Git-HEAD **plus aktuelle Code-/Teständerungen
und nicht ignorierte neue Fixtures**. Nach dem letzten Scanner-Freeze wurden
nur Dokumentation und Nachweise ergänzt. Code-/Testdateien wurden vor der
Publikation gegen die getesteten Snapshotbytes geprüft; LF/CRLF-Normalisierung
ist dabei zulässig. Maven- und Python-Nachweise stammen aus den angegebenen
isolierten Snapshots, nicht allein aus unveränderten alten Commits.

[Maschinenlesbare Ergebnisse](nachweise/test_results.json),
[Scanner-JUnit](nachweise/Scanner_final3.pytest.xml),
[Snapshotabgleich](nachweise/final_code_hash_check.json) und
[SHA-256 der Nachweise](nachweise/sha256.json) dokumentieren die Prüfung.
Einzelberichte: [Parser/Fixtures](nachweise/clients.md),
[Scanner-Altersvalidierung](nachweise/clients_weeks.md),
[Budget/Prompt/Regelwerk](nachweise/hub.md),
[Quellenalter](nachweise/quellen.md),
[unabhängige UI-Gegenprüfung](nachweise/ui_peer.md) und
[unabhängige Quellen-Gegenprüfung](nachweise/quellen_peer.md).

MqlRealmonitor und PelicanWinnerLooser bleiben eigenständig und noch nicht
integriert. Die TradeServer-Gegenstelle, Plattformlogins und kopierbare
Nettoperformance wurden nicht live verifiziert.

## Übernahme

Geänderte Quellen und Scanner aus dem veröffentlichten Code neu bauen/starten
und Quellenkataloge aktualisieren. Die Quellen-Metadaten und Anzeigen eines
bereits laufenden alten Prozesses ändern sich durch einen Git-Push nicht.
Die Forensikformeln und die verbindlichen Schwellen wurden hier nicht
geändert; eine neue Forensikversion ist für diese Anzeige-, Datenvertrags-
und Testkorrekturen nicht erforderlich.
