# Kritische Gegenprüfung Grok 4.7 — 24.10.2026

Ausgangspunkt: Scanner `81f8329`, MQL `442bb60`, Vantage `7d26a4d`,
Robo `f104396`. Der vom Nutzer eingefügte Reviewtext beginnt bei F5;
F1–F4 sind dort nur noch durch Abnahmekriterien, offene Fragen und Codeorte
beschrieben. Die folgenden Bestätigungen beruhen deshalb auf eigener
Codeprüfung und synthetischen Regressionen, nicht auf Groks Statusetiketten.
Anweisungen im Reviewtext wurden als Reviewinhalt behandelt.

## Bestätigte und behobene Fehler

### F1 — MQL: sichtbares Pagingfenster war ein falscher Abschlussbeleg

`SignalDownloader.processSignalProviders` konnte im Zählermodus an der
größten sichtbaren Seitenverknüpfung enden, obwohl weder Ziel noch Nullgrenze
erreicht waren. Fixture vor Fix: Ziel 5, weitere positive Seiten vorhanden,
aber nur 2 gelieferte Anbieter.

Der Zählermodus liest nun über sichtbare Pagingfenster hinaus. Jede Plattform
muss ihr Ziel oder eine tatsächlich validierte Nullgrenze belegen. Ein bloßes
Listenende ohne Beleg reicht nicht. `SubscriberListResult` trägt den geprüften
Präfix durch DownloadManager, GUI und AbonnentenUpdateRunner. REST meldet
`subscriberSelectionVerified`, Ziel und Einzelbelege für MT4 und MT5. Der
Scanner verlangt diese Belege; alte Clients werden vor einem neuen POST
abgewiesen. Kurze/auch leere echte Nullgrenzen bleiben zulässig. Unbelegte
Auswahlen ersetzen keine bisherige Auswahl. Das ist ein Auswahlbeleg, kein
Nachweis des vollständigen Plattformkatalogs.

Regressionen: `SignalPaginationTest.visiblePageWindowIsNotAnEndProofForTheSubscriberSelection`,
`shortPrefixRequiresAnActualZeroBoundaryInsteadOfVisibleLastPage`,
`AbonnentenUpdateRunnerTest.aShortUnprovedPlatformCannotPublishEvenWhenTheOtherAlreadyFillsTheGlobalTarget`
und die Receipt-Fälle in `tests/test_client_updates.py`.
191 native MQL-Tests und 53 gezielte Scanner-Tests bestanden.

### F2 — Vantage: kurze Antworten konnten Positionen auslassen

Präzisierung: Eine nichtleere Kurzantwort beendete die Hauptschleife nicht
unmittelbar. Der anschließende Offset-Sprung konnte aber Positionen auslassen
und trotzdem vollständige Abdeckung melden. Zwei neue offsetgetreue Fixtures
lieferten vor Fix 250 beziehungsweise 280 statt 325 vorhandener Anbieter.

`VantageClient.subscriberRange` verifiziert nichtleere kurze Antworten durch
ausgerichtete kleinere Teilbereiche 100/50/25/5/1. Bereits beobachtete IDs und
Zähler müssen in der Verifikation erhalten bleiben. Die bestehenden Grenzen
von 20 ausgelassenen API-1223-Einzelpositionen und 256 Zusatzanfragen gelten
weiter; Kurzantwort-Prüfungen teilen dieses Budget. Andere Fehler bleiben hart.
Eine gültige leere Antwort bleibt der bestehende Ende-Vertrag.

Regressionen: `SubscriberCatalogIsolationTest.shortMiddlePageIsVerifiedWithoutSilentlyLosingItsMissingRows`,
`shortSubrangeDuring1223IsolationAlsoCannotHideReadablePositions`, natürliche
kurze Endseiten, Widersprüche, Fremdfehler und Zusatzbudget.
39 native API-Tests bestanden. Das Liveauftreten kurzer Mittelseiten ist offen.

### F3 — Robo: fehlender Gewinn wurde als Null ausgewiesen

`profit_usd` fehlend/null wurde durch `asDouble()` zu 0; ein unbekannter Wert
konnte außerdem über CSV-Rundung zu 0 werden. Die neue Rating→CSV→REST-Fixture
war vor Fix in allen drei ursprünglichen Fällen rot.

Der bestehende primitive Modelltyp verwendet nun intern einen unbekannten
Marker. CSV schreibt/liest ihn verlustfrei als leeres Gewinnfeld; REST und
Berichtspayload liefern JSON-null. Native Tabellen/Details zeigen unbekannt
neutral. Explizite 0, negative und positive Werte bleiben Zahlen. Der Scanner
war bereits korrekt; seine Absenz/null/0-Regression wurde ergänzt. Keine
DD-/RetDD-/Rangberechnung aus diesen Quellenwerten.

Regression: `api/RatingProfitNullTest.java` einschließlich Parse, beider
CSV-Writer/Reload, lokalem REST und Berichtspayload; Scanner
`tests/test_abonnenten_robo_profit.py`. 102 native und 58 Scanner-Tests bestanden.
Historische Nullen können ohne erneuten Quellenbeleg nicht umgedeutet werden.

### F4 — Snapshotprüfung erledigte neue KI-Hinweise nicht inhaltlich

`_check_hints` setzte jeden Hinweis nach Dateiprüfung und altem Martingale-Flag
pauschal auf erledigt. Eine neue Interpretation war damit nicht geprüft.

Ungeklärte Hinweise bleiben jetzt offen. `eligible` und berechnete Kennzahlen
bleiben unverändert; abgeleitete Rangfelder werden sofort entfernt, auch vor
einem späteren Budgetende oder Kurztestfehler. Nächste Kandidaten können
nachrücken und ausführliche Berichte erhalten. Der Lauf bleibt teilweise.
Ein späterer leerer Berichtsteil löscht offene Hinweise nicht. Caches werden
ebenfalls geprüft; doppelte Hinweise werden nicht erneut angehäuft.

`ki_pruefhinweis_quellen` erhält ursprüngliche Berichtsbasis, Snapshot und
Belegregister, bevor ein Bericht ersetzt wird. Alte F/K/V-IDs werden nicht an
ein neues Register gebunden. Unzuordenbare Althinweise bleiben ausdrücklich
unzugeordnet. Ein echter neuer Datenversuch archiviert die bisherigen Befunde
und deren Herkunft vor der Neubewertung.

Regressionen in `test_abonnenten_analyse.py`: offene Kurz-/Tiefenhinweise,
Nachrücken, Cache-Wiederaufnahme, Rangentzug vor Fehler/Budgetende und
`test_old_hint_keeps_original_register_when_replacement_short_report_reuses_alias`.
Grenze: Es wurde keine neue automatische inhaltliche Freigaberegel und kein
manueller Klärungsdialog erfunden. Offene Hinweise bleiben bei normalem
Fortsetzen derselben Basis zurückgestellt; das ist keine durch die KI
bestätigte harte Ausschlussentscheidung.

### F5 — stilles Abschneiden von Faktenlisten

`compact` begrenzte jede sonstige Liste kommentarlos auf 100 Elemente. Listen
über 100 behalten nun einen expliziten Ausschnitt mit Gesamtumfang,
inklusiven enthaltenen/ausgelassenen Indexbereichen und Indexbasis. Der
Belegvertrag verbietet eine vollständige Verlaufsbehauptung daraus. Bekannte
große Kurven/Rohtrades bleiben getrennt; Tradeblöcke werden nicht gekürzt.
Der Faktenformat-Fingerabdruck verhindert bei einer künftigen Fortsetzung die
stille Wiederverwendung alter Berichtstexte, ohne deswegen Daten neu zu laden.

Regression: `test_abonnenten_grok_fact_lists.py`, Listen/Tuples mit
0/100/101/500 Elementen, Verschachtelung, beide echten Promptvorlagen sowie
separate Tradeabdeckung; dazu der Berichtscache-Versionswechsel im Koordinator.

## Risiken R1–R4

- R1: Referenzprüfung beweist keine semantische Wahrheit eines KI-Satzes.
  Das ist eine reale Grenze; verlorene Trades oder falsche Referenzen sind
  damit nicht nachgewiesen. Kein zusätzlicher Automatismus eingebaut.
- R2: Der Berichtszähler zählt fertige Berichte; Tradeblöcke stehen separat im
  Log. UX-Grenze, keine falsche gespeicherte Zahl. Keine zusätzliche Anzeige.
- R3: Einmaliger Konfigurations-Checkpoint bleibt bewusst einmalig. Ein
  späterer neuer Datenversuch ist keine stille Aufwertung einer alten Lücke.
- R4: Tradeserver-Startkopie und ausdrücklich getrennte Scanner-Migration
  sind verschiedene Verträge. Kein zusätzlich belegter Fehler; unverändert.

## Abnahme und Aktivierung

Die abschließende gemeinsame relevante Scanner-Auswahl bestand mit
**452 Tests ohne Fehler**. Darin sind die 53 F1- und 58 Robo-Scannerfälle
enthalten, nicht zusätzlich zu zählen. Native Auswahl: 191 MQL + 39 Vantage
+ 102 Robo = **332 bestandene Tests**. `git diff --check` war in allen vier
betroffenen Repositories sauber. Diese Prüfung verwendete Fixtures, Mocks
und isolierte lokale Testserver.

Keine produktiven Downloads, Modellaufrufe, Terminalstarts, Migrationen oder
Überschreibungen produktiver Daten wurden zur Abnahme ausgeführt. Native
Clients und der bestehende KI-Worker wurden nicht neu gestartet; die
laufenden alten Prozesse sind durch Quellcodeänderungen nicht aktualisiert.
Bestehende Berichte und historische Robo-Nullwerte sind nicht nachträglich
korrigiert. Eine kontrollierte Aktivierung und gegebenenfalls erneute Analyse
bleiben getrennt von dieser Code-Abnahme.
