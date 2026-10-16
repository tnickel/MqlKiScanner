# Kritische Antigravity-Prüfung und vollständiger GLM-Nachtragskatalog

Prüfung am 16.10.2026 gegen den nach den bisherigen Korrekturen veröffentlichten
Stand. Der Antigravity-Bericht und die beiden nun vollständig vorliegenden GLM-
Dateien untersuchen ältere Commits. Ihre Befunde sind Hypothesen, keine aktuelle
Fehlerliste. Die publizierten Originale bleiben unverändert; Korrekturen und
Gegenbelege stehen in den Teilprüfungen.

## Ergebnis

Weitere echte Fehler wurden reproduziert und behoben. Ein großer Teil der alten
P0/P1-Aussagen war auf dem jetzigen Stand bereits korrigiert. Allgemeine Zweifel
an zukünftiger Signalqualität oder offene Plattformsemantik begründen keine
beliebige Änderung von Formeln, Schwellwerten oder Auswahlpolitik.

| Bereich | Konkrete Korrektur |
| --- | --- |
| MQL-Quellwährung | Native Kontobeträge bleiben native Beträge. Downloader liefert Currency; Scanner lässt nur belegtes USD in USD-Forensik/Studien, auch bei frei vergebenen Quellenkürzeln. Altbestände ohne Beleg bleiben unbekannt. Forensik-Version 19 erzwingt Neubewertung. |
| MqlDownloader REST/Parser | Korrektur des invertierten includeUnchanged-Filters, gültige Enumparameter und präziser Balance-/Currency-Parser einschließlich Vorzeichen und Zahlenlokalisierung. |
| Scanner-Auswahl | Gleiche Abonnentenzahlen haben einen stabilen ID-Zweitschlüssel. Unbekannte/ungültige Anzahl belegt keinen positiven Mindestabo-Filter; NaN/Infinity/Bool/Bruchzahlen umgehen ihn nicht. |
| Scanner-GUI | Bruchteile im Mindestalter werden beim Öffnen/Speichern nicht mehr abgeschnitten. |
| LLM-Audit | Antworten aller HTTP-Versuche inklusive verworfener length-Fragmente bleiben getrennt vom Kostenledger nachvollziehbar; Tokenkomponenten summieren sich konsistent. Fehlende Pro-Call-Usage wird nicht durch den gesamten Laufverbrauch ersetzt. |
| Persistenz/Synchronisation | Settings atomar ersetzen, beschädigte Konfiguration offen melden; Sync-Läufe vor dem Übertragen mit tatsächlicher Startzeit protokollieren und parallel sperren. |
| Weitere Hubpfade | Letztes Quellenupdate ohne500-Zeilen-Abschneidung; Alt-Sitzungen nicht pauschal NEU; gemeinsamer Fremdtextschutz für Agentenvorlagen; manueller Tiefenbatch übernimmt dokumentierten Workflow-Lock. REST liefert aktuelle Bewertungs- und Berichtsbasis offen. |
| RoboForex | Aktive Historienphasen laden nur Anbieter mit mindestens einem Abonnenten; kein unnötiger Login bei leerem Scope. MaxInt-Offset ergibt leere Seite statt 500. Bestehender Ratingfilter 300 % wird maschinenlesbar offengelegt. |
| Zulu | Überlappende Katalogseiten werden bis zum Ziel nachgefüllt; Wiederholungen und ungültige Provider-Identitäten bestätigen keinen Teilkatalog. Unbekanntes Alter bleibt auch im LLM-Payload null. |
| Vantage | APIfehler bestätigen kein erfolgreiches Katalogende. Neue Tradezeitbasis UTC wird explizit belegt; unbelegte ältere Zeitzonenarchive werden gesperrt. GUI-DD nutzt passende bestätigte Basis; Tages-PnL-Rückgang wird nicht als Equity-DD bezeichnet. |

Zusätzliche Vantage-Gegenprobe: Ein unter einer anderen Rechnerzone gespeicherter
Epoch-0-Platzhalter darf kein jahrzehntelanges Signalalter belegen. Beide
persistierbaren Sentinel-Tage werden ausgeschlossen; Zukunftsprüfung und
Wochenberechnung teilen eine UTC-Datumsbasis.
[Nachtrag mit unabhängigen Zeitzonentests](nachweise/clients_vantage_epoch_followup.md).

PelicanTrading benötigte für diese Nachprüfung keine neue Produktkorrektur;
seine vollständige Offline-Suite wurde erneut ausgeführt. MqlRealmonitor und
PelicanWinnerLooser bleiben eigenständig und nicht integriert.

## Zuordnung sämtlicher Befund-IDs

- [MDL-1…14, VAN-1…11 einschließlich Unterpunkten](nachweise/clients.md)
- [ROB-1…11, ZUL-1…9 und Pelican F-1…10](nachweise/quellen.md)
- [FIN-1…11, FLT-1…12, Antigravity E-1…6 und S1…S7](nachweise/root_finance_filter.md)
- [LLM-1…13 und SYN-1…12](nachweise/hub.md)
- [Unabhängige Gegenprobe des MQL-Währungswegs](nachweise/root_currency_peer_review.md)
- [Währungsbeleg beim manuellen Nachladen](nachweise/currency_reload_peer_review.md)
- [Währungsschutz in der Übersicht und Detailanzeige](nachweise/ui_currency_fix.md)

## Was an den Fremdberichten nicht trägt

Parser-Pathfehler, Monatsbudgetlücke, zahlreiche Stufe-0-Freeze-Fälle, alte
Promptgates und Reportcachefehler waren schon behoben. E-3 behauptet einen
unkontrollierten Abbruch bei Quellenkollisionen; der aktuelle Code verwirft
mehrdeutige Kandidaten und fängt Einzelfehler ab. Ein SQLite-Primärschlüssel aus
Quelle und ID bleibt ein eigener noch offener Ausbau, kein hier vorgetäuschter Fix.

Der Antigravity-Bericht beschreibt unter anderem Pelican-Host/Speicherung und
Zulu-Währungsexporte falsch. Gewinnfaktor und Winrate des Scanners basieren
bewusst auf Brutto-Trades, Ertrag/DD auf Netto. Fünf DD-Kanäle sind keine fünf
statistisch unabhängigen Messungen. H1-Bar-Schlüsse samt Rekonstruktionsfehlern
beweisen keine universelle Untergrenze des tatsächlichen Brokerkonto-DD.

Die genannte Summe 634 stimmt nicht: fünf damalige Java-Suiten ergeben 584,
mit Vantage-Python 590; die sieben im Nutzertext genannten Zahlen ergeben 803.
Auch das Renditebeispiel ist falsch: 2,5 % monatlich über 3,5 Monate ergeben 9,026866 %
Gesamtrendite, 34,488882 % annualisiert und bei 2 % DD Calmar 17,244441.
[Unabhängige Berechnung](nachweise/review_oracles.json).

Grüne Tests belegen nur die geprüften Verträge. Weder ein universeller
2,5-Pip-Gewinnfilter noch zusätzliche harte 6-/12-Monatsgates oder eine Garantie
zukünftiger Gewinner sind aus den Berichten belastbar herleitbar. Die
Abonnenten-Top-N-Vorauswahl begrenzt das untersuchte Universum; Copykosten,
unvollständige Historien und fehlende offene Positionen begrenzen Aussagen weiter.

## Test- und Veröffentlichungsnachweis

Finaler isolierter Gesamtstand: **2.241 Scanner-Tests bestanden**, 3 private
Fixture-Skips und 4 ausgeschlossene bezahlte LLM-Tests. Alle fünf Quellenpakete
sind erfolgreich gebaut: MQL 124, Pelican 180, Robo 183, Vantage 78 und Zulu 120
Java-Tests, zusammen **685**; dazu **21 Vantage-Python-Tests**. Die gesonderten
Zeitzonen- und Teilprüfungen sind Teilmengen und werden nicht doppelt gezählt.

Der finale Scanner-Volltest und die isolierten Maven-Packages werden in
[test_results.json](nachweise/test_results.json) mit exakten Zählwerten,
Snapshot-Manifesten, XML-Ergebnissen und Loghashes dokumentiert. Die Snapshot-
Quellen werden vor dem Commit gegen die Arbeitskopien verglichen. Historische
Reviewbelege werden nicht überschrieben.

Vorher-Proben enthalten absichtlich fehlschlagende Regressionen. Der erste
Scanner-Vollversuch hatte 10 Fehler bei 2.205 bestandenen Fällen: alte Auswahl-/
Währungsannahmen in Dummies, unvollständige HTTP-Doubles und einen falsch
platzierten neuen Testassert. Die Assertions bleiben fachlich erhalten, erhalten
aber echte USD-Belege bzw. idempotente vollständige HTTP-Antworten. Diese Fehler werden mit ihren tatsächlichen Logs
offengelegt. Ausschließlich der finale vollständig grüne Snapshot gilt als
Abschlussnachweis. Private Fixturetests bleiben übersprungen, bezahlte LLM-
Tests ausgeschaltet. Keine Plattformanmeldung, keine kostenpflichtigen Calls,
keine produktiven Datenbank-/Cacheänderungen durch die Tests.

## Betrieb nach der Aktualisierung

Geänderte Programme müssen neu gebaut/gestartet und betroffene Signale neu
geladen/analysiert werden. Es wurde kein laufender Monitor automatisch beendet.
MQL-Altcaches ohne Currency bleiben gesperrt, bis ein neuer belegter Import
vorliegt. Vantage-Altarchive ohne nachgewiesene UTC-Zeitbasis dürfen nicht
geraten umgerechnet werden; sie bleiben erhalten und benötigen einen bewusst
vollständigen Neuaufbau nach separater Sicherung. Das ist eine sichtbare
Qualitätsgrenze, kein automatischer Datenverlust.

## Originale

- [Antigravity](ANTIGRAVITY_ORIGINAL.md)
- [Vollständiger GLM-Befundkatalog](GLM_BEFUNDKATALOG_ORIGINAL.md)
- [Nachgereichter GLM-Bericht A–G](GLM_BERICHT_ORIGINAL.md)

Der tatsächlich vorhandene Antigravity-Dateiname hat kein `svg`-Präfix.
Die Originalkopien enthalten Reviewtext, keine Cookies, API-Schlüssel oder
Produktionsdatenbanken. Das externe MqlTradeMonitor-Serverrepository war
nicht verfügbar; geprüft ist die implementierte Scanner-Clientseite.
