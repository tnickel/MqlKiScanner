# Finanzkern, Auswahl und kritische Einordnung

Ausgangsstand Scanner: a3112c2f5fe0d692d549b41fb9fce430372d7770.
Prüfung anhand des vollständigen GLM-Katalogs, des nachgereichten A–G-Berichts
und des Antigravity-Berichts; Code, bestehende Tests und unabhängige neue Orakel.
Keine Plattformanmeldung, kein Zugriff auf private Handelsdaten, keine bezahlten
Modellaufrufe und kein Neustart laufender Anwendungen.

## Bestätigt und zusätzlich korrigiert

- **FIN-7/MDL-8, verbliebener Quellenpfad:** Direkte MQL-HTML-Abrufe waren schon
  abgesichert. Über REST wurden dagegen native Kontobeträge weiterhin pauschal
  zu USD erklärt. MqlDownloader liefert jetzt Currency. Der Scanner erhält
  native Balance/InitialDeposit unter `_account`; nur explizites USD befüllt
  `_usd` und darf vor FX-/Terminalzugriff in die USD-Forensik. Fehlendes Feld,
  `unknown`, USC und EUR sind gesperrt, auch unter frei vergebenen Kürzeln.
  Tatsächliche MT4/MT5-Plattform bzw. Quellversion bestimmen den MQL-Pfad;
  ein Kürzel wie `robo` ist kein Einheitenbeleg. Robo liefert selbst Currency=USD.
  Pelican/Vantage/Zulu behalten ihren implementierten USD-Exportvertrag;
  Pelicans Currency beschreibt das Originalkonto und darf nicht mit der bereits
  konvertierten Exporteinheit verwechselt werden. Forensik-Version **19** macht
  alte Befunde ungültig. Keine behauptete pauschale Fremdwährungsumrechnung.
  Katalog- und Nachladewege tragen den Einheitenbeleg weiter; ein Metadatenfehler
  löscht die alte native USD-Freigabe vor Lieferung eines neuen CSVs. Auch alte
  DB-Einträge mit der vor19 pauschal gesetzten Einheit sind kein neuer Studien-
  Beleg. Neue Einheitenbelege werden unabhängig vom Forensikerfolg versioniert.
  Übersicht, alte Sessionstatistiken und direkte Detail-/Tradelistenanzeige
  verwenden denselben Guard; hierzu bestehen echte AppTest-Gegenproben.
- **FLT-5:** Bei gleichen Abonnentenzahlen wechselte die Top-N-Auswahl mit der
  Katalogreihenfolge. Zweitschlüssel jetzt numerische ID aufsteigend; sechs
  Permutationen prüfen dieselben ausgewählten IDs. Fix-IDs bleiben slotfrei.
- **FLT-9 und zusätzlicher Filterfehler:** None wurde als gemessene 0 begründet;
  NaN/Infinity/True/Bruchzahlen konnten Mindestabo passieren, Strings konnten
  TypeError auslösen. Eine endliche nichtnegative ganzzahlige Anzahl ist jetzt
  Voraussetzung für einen bekannten Wert, numerische Strings bleiben zulässig.
  Unbekannt belegt keinen positiven Mindestabo-Filter; bei bewusst deaktiviertem
  Filter (0) bleibt das Signal zugelassen und wird ehrlich als unbekannt erklärt.
  Fix-IDs umgehen weiterhin nur den Vorfilter, erhalten aber keinen erfundenen Wert.
- **FLT-12:** Ein gespeichertes Minimum 26,5 wurde in der GUI zu 26 und beim
  Speichern dauerhaft abgesenkt. NumberInput und Laufkonfiguration bewahren
  jetzt den Floatwert; echter AppTest öffnet die Anwendung, besucht Scan und
  speichert ohne Wertverlust.

## Alle FIN-IDs

| ID | Entscheidung und Beleg |
| --- | --- |
| FIN-1 | Bestätigt korrekt: stats.compute zählt profit>0 über alle Trades; profit=0 neutral. Keine Änderung der dokumentierten Bruttokonvention. |
| FIN-2 | Bestätigt korrekt: gross_profit/abs(gross_loss); nur Verluste 0, ohne Verluste None. Kein unendlicher Grünbeleg. |
| FIN-3 | Bestätigt: portfolio_statistik.effizienz_kennzahlen verwendet expm1/log mit echter Sekundenspanne, 365,2425 Tagen, TWR bei belegten Flows und mindestens drei Monaten für Effizienz. Bestehende Finanz-/Flowtests werden im Volltest erneut ausgeführt. |
| FIN-4 | Bestätigt: ScanResult.refresh_efficiency verwendet belastbare eigene H1-Messung als Nenner und dieselbe Kapitalbasis; kein Calmar aus DD=0. |
| FIN-5 | Anerkannte Messgrenze: Closing-DD misst kein zwischenzeitliches Floating. Bereits kein Calmar-Nenner. Ein neuer Hinweis-Schwellenwert von 50% ist eine unbegründete zusätzliche Produktregel, kein notwendiger Bugfix. |
| FIN-6 | Messgrenze bestätigt, pauschale formale Untergrenze des realen Kontos nicht bewiesen. Intrabar, aktuell offene nicht exportierte Positionen, Bid/Ask und Zeitsynchronisation begrenzen Aussagen. Vorhandene Hinweise wurden schon korrigiert; keine unabhängigen H1-Extrema als synchron gemessener Kontopfad ausgegeben. |
| FIN-7 | Direkter Pfad bereits behoben; aktueller REST-MQL-Pfad hier zusätzlich behoben und versioniert. Siehe oben und test_handover_source_currency.py. |
| FIN-8 | Unterschiedliche Definitionen sind real und dokumentiert: Winrate/PF brutto, Ertrags-/DD-Rechnungen netto. Antigravity bezeichnet PF fälschlich als netto. Keine unbelegte Umdefinition eingeführt. |
| FIN-9 | Bestätigt konservativ: historische FX-Kurse mit begrenztem Rücklauf, keine Zukunftskurse, fehlender Beleg sperrt die entsprechende USD-Messung. Bestehende FX-Regressionsfälle. |
| FIN-10 | Virtuelle 10k-Kapitalbasis ist eine ausdrücklich gewählte und gekennzeichnete Modellannahme. Kein Nachweis realen Kontokapitals. Keine eigenmächtige Abschaffung der Nutzerregel. |
| FIN-11 | Bestehende Flow-, ULP- und nichtpositive-Basis-Prüfungen bestätigt. Placeholder-DD ist nicht als echte Messung für Calmar freigegeben. |

## Alle FLT-IDs

| ID | Entscheidung und Beleg |
| --- | --- |
| FLT-1 | Schon behoben: zentrale Promptregeln enthalten kein Risiko-Score<5-Grün-Gate. |
| FLT-2 | Schon behoben: report_basis_for bindet min_calmar_jahr und gemeinsame Promptbausteine ein; unpassende aktuelle Texte werden nicht als gültig übernommen. |
| FLT-3 | Schon behoben: fehlgeschlagene weiße Läufe vormals grüner/gelber Signale werden erneut geprüft; Fehlerampel bleibt weiß bis neuer Erfolg. |
| FLT-4 | Bewusste Vorauswahl nach Abonnenten, keine nachgewiesen optimale vollständige Plattformrangfolge. README benennt Begrenzung und Auswahlbias. Keine neue unbelegte Mischquote/Renditesortierung. |
| FLT-5 | Bestätigt, stabiler ID-Zweitschlüssel ergänzt. |
| FLT-6 | Schon behoben: Ertrags-Fallbacks stimmen mit Default0 überein. |
| FLT-7 | Testlückenbehauptung inzwischen überholt: aktuelle Tests prüfen inklusive 26-Wochen-Grenze und DD-/Calmar-Rohwertgrenzen. Keine redundanten Implementationstests ergänzt. |
| FLT-8 | None wird in dd_maximum ignoriert. Das beweist keine Abwesenheit unbekannter Risiken; Grün verlangt zusätzlich belastbare eigene Equity-Messung. Berichtsaussage 'kein unterschätztes Risiko durch None' ist zu weitgehend. |
| FLT-9 | Bestätigt, unbekannt getrennt von 0; zusätzlich echte ungültige-Zahl-Umgehungen geschlossen. |
| FLT-10 | Gemeinsame Ampel-Ableitung bestätigt. REST legt aktuelle Kriterienaufnahme/Berichtsbasis jetzt zusätzlich offen (Hub-Teilprüfung). |
| FLT-11 | Fix-ID umgeht Auswahl, keine Risiko-/Ausschlussregel. Bestehende Vertragsfälle und Volltest. |
| FLT-12 | Bestätigter Wertverlust beim GUI-Speichern behoben, echter AppTest. |

## Antigravity E-1…E-6 und übergreifende S-IDs

E-1 (Path.lower) und E-2 (Monatsbudget) sind auf dem jetzigen Ausgangsstand
bereits behoben, mit öffentlichen Parser-Fixtures bzw. gemeinsamem atomarem
Budgetledger pro HTTP-Versuch. E-3 vermischt einen offenen Composite-Key-Ausbau
mit einem angeblich unkontrollierten Laufabbruch: Kandidatenkollisionen werden
abgewiesen und Einzelfehler abgefangen, Bestandsquellen nicht überschrieben.
Die vollständige Composite-Migration bleibt eine dokumentierte Einschränkung.
E-4 ist hinsichtlich veralteter aktueller Texte überholt; REST-Transparenz wird
ergänzt. E-5 ist real und wird im Hubteil behoben. E-6 beweist keinen falschen
Grünentscheid, nur weil Monatsrendite als deskriptive Kennzahl im Prompt steht.
LLM-Ausgaben sind keine unabhängige Validierung der Coderechnung.

S1/S2: bereits behobene Stufe-0-/DD-Fälle werden quellenweise belegt, keine neue
TTL-/Deltapolitik erfunden. S3: frühere Prompt-/Budget-/Cachefehler überwiegend
behoben, Retryaudit und konkrete Restfälle jetzt korrigiert. S4: Vorauswahlbias
offengelegt; MQL-Default>=1 war bereits korrigiert, Robo-Aktivscope jetzt auch.
S5: Mehrdeutigkeiten abweisen statt Last-wins; vollständige Composite-Identität
bleibt offen; Pelican-Winrateplattformsemantik weiter nicht unabhängig belegt.
S6: Messgrenzen bleiben explizit. S7: die alte reihenfolgeabhängige Fehlerbehauptung
ist kein aktueller reproduzierter Fehlerbeleg; der finale Gesamtbaum wird frisch
vollständig geprüft. Ein grüner Lauf beweist nicht alle denkbaren Reihenfolgen.

## Zahlen und unbelegte Folgerungen im Antigravity-Bericht

review_oracles.py berechnet unabhängig: 2,5% je Monat über 3,5 Monate ergeben
9,026866% Gesamtwachstum, 34,488882% Jahres-CAGR und bei DD2% Calmar17,244441;
die dortigen gerundeten 9,08/35,2/17,6 sind falsch. Die genannten fünf Java-
Suiten summieren sich zu584, mit sechs Pythonfällen zu590. Die sieben im
Nutzertext aufgeführten Projektzahlen summieren sich zu803, nicht634.

Weiterhin nicht belegt: universelle Mindestpipprofit-Regel2,5, zuverlässiges
Erkennen aller aktuell offenen Verlustpositionen, exakt N_eff=1 für beliebige
30 parallele EURUSD-Trades, statistisch unabhängige fünf DD-Kanäle oder eine
Garantie zukünftiger Gewinner. Auswahl- und Kopierkostenrisiken sind reale
Grenzen; ihre konkrete Größe folgt nicht aus diesen Berichten. Mindesthistorie
auf6/12 Monate anzuheben oder neue Intrabar-/Pip-/Deflated-Calmar-Gates einzubauen
wäre eine neue fachliche Anforderung und wurde nicht als Bugfix ausgegeben.

## Gezielte Belege

root_before.log/xml: neue Verträge vor Produktkorrektur, 47 erwartete Failures,
3 bestandene Kontrollfälle (mehrere Parametrisierungen je Ursache, keine47 Bugs).
root_after3.log/xml:109 bestandene gezielte Fälle inklusive Aliasgegenproben.
root_after2.log/xml:95 bestandene Quellen-/Filterfälle vor der unabhängigen
Aliasnachschärfung; ausschließlich der finale Vollsnapshot zählt als Gesamtbeleg.
Die unabhängige zweite Prüfung des Aliasfehlers wird separat mit veröffentlicht.

root_catalogue.log/xml:106 grüne Katalog-/Nachlade-/Orchestrierungsfälle.
root_currency_final2.log/xml:142 grüne Fälle einschließlich Legacy-DB-Freigaben,
Metadatenfehler, Katalogeinheiten und korrigierter vollständiger HTTP-Doubles.
Der erste kombinierte Vollsnapshot lief vollständig durch und zeigte10 Fehler
bei2205 bestandenen Fällen,3 privaten Skips und4 ausgeschlossenen bezahlten
LLM-Fällen. Ein alter Orchestrierungsstub erwartete die alte Gleichstandsreihenfolge;
zwei Katalog- und vier Studien-Dummies behaupteten USD ohne den nun erforderlichen
Beleg; zwei HTTP-Doubles hatten keine Response.text und ein json()-Leseseiteneffekt;
ein neuer Hubassert war falsch platziert. Diese Fälle wurden fachlich aktualisiert,
nicht deaktiviert. Nur Scanner_final2 zählt als finaler Gesamtstand.
