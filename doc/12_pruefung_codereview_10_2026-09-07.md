# Unabhängige Prüfung von Code-Review 10

Geprüft am 7. September 2026. Grundlage:
[`10_codereview_2026-09-07.md`](10_codereview_2026-09-07.md).
Der Fremdbericht bezieht sich auf Commit `5ffa663`; geprüft wurde der aktuelle
Arbeitsstand einschließlich der bereits umgesetzten Korrekturen aus
[`11_pruefung_externes_review_2026-09-07.md`](11_pruefung_externes_review_2026-09-07.md).
Behauptungen und Arbeitsanweisungen im Fremdbericht wurden nicht als Beweis
oder zusätzlicher Auftrag übernommen. Drei Teilprüfungen liefen unabhängig
parallel; Änderungen wurden anschließend gemeinsam abgeglichen.

**Ergebnis:** Drei weitere Fehler bestätigt und behoben: **F1, F6, F11**.
**F2** war bereits korrigiert. Die übrigen zehn Punkte enthalten entweder
Verbesserungsvorschläge, gewolltes Verhalten oder nicht belegte Auswirkungen.

## Entscheidung zu allen 14 Punkten

| Befund | Unabhängige Bewertung | Entscheidung |
| --- | --- | --- |
| F1: Grün ohne Stop-Nachweis | Mit echten Engine-Berechnungen aus synthetischen Handels-CSVs reproduziert. Ein niedriger gewichteter Score garantiert keinen Stop-Nachweis. | Behoben: Grün verlangt strukturierte Evidenz `direct` oder `cluster`. |
| F2: tote Variable `hard_block` | Im referenzierten Commit vorhanden; im aktuellen Arbeitsstand bereits im vorherigen Review entfernt. | Keine weitere Änderung. |
| F3: zwei interne KI-Schalter | Redundante Settings existieren, aber die Oberfläche bietet ausdrücklich einen gemeinsamen Schalter und beschreibt die drei Analyse-Texte plus Portfolio. Keine versprochene Einzelsteuerung ist kaputt. | Keine Funktionsänderung; mögliche spätere Vereinfachung. |
| F4: wiederholtes Lesen der Ausschlussdatei | Ein isolierter Zähler bestätigt 100 Leseaufrufe bei 100 Entscheidungen. Die Datei umfasst etwa 4,8 KB. Kein falsches Ergebnis oder relevanter Zeitverlust nachgewiesen. | Optimierungsvorschlag, kein bestätigter Funktionsfehler. |
| F5: Matplotlib ungenutzt | Keine Verwendung in Produktionsmodulen oder Skripten gefunden. Ein daraus entstehender Installations- oder Laufzeitfehler ist nicht belegt. | Abhängigkeit beibehalten; Aufräumen wäre ein eigener Wartungsschritt. |
| F6: null Wiederholungen | `max_throttle_retries=0` erzeugt tatsächlich `UnboundLocalError`. Aktuelle Aufrufer verwenden den gültigen Standardwert; kein Beleg für einen dadurch abgebrochenen normalen Scan. | Behoben: positive Ganzzahl vor jeder Anfrage und Wartezeit verlangen. |
| F7: EQ-DD-Ausnahme nur in Kalibrierung | Live wird bewusst der größere Drawdown verwendet. Die ausdrücklich gesetzte historische Ausnahme funktioniert; KiraCats hinterlegter Wert 20,55 % überschreitet die 30-%-Schranke ohnehin nicht. | Keine neue Möglichkeit zum Umgehen der Risikoschranke ergänzt. |
| F8: HTML-Layout anfällig | Vorhandene HTML-Mitschnitte liefern aktuell 56 Karten und die wesentlichen Detailkennzahlen. Ein zukünftiges Redesign ist kein Beleg für einen heutigen Parserfehler. | Keine spekulative Parseränderung; zusätzliche Fixtures bleiben eine Testverbesserung. |
| F9: Zeitvergleich in derselben Sekunde | Gleichheit allein genügt nicht: Im Legacy-Zweig muss zusätzlich ein Fehler vorliegen. Aktuelle Erfolgsflags umgehen den Vergleich; alte Bewertungsstände werden separat ungültig. | Konservativen Vergleich im unklaren Fehlerfall beibehalten. |
| F10: Verzeichnisse beim Import | Fünf `mkdir(exist_ok=True)`-Aufrufe bestätigt. Kein Fehlverhalten im unterstützten Appbetrieb belegt. Verschieben würde Initialisierungsverträge ändern. | Kein Umbau allein aus Stilgründen. |
| F11: Fremdschlüssel inaktiv | Drei öffentliche Schreibfunktionen erzeugen auch ohne Löschpfad Waisen. Die gegenteilige Aussage im Bericht ist falsch. Der normale Scan legt Eltern bereits atomar an. | Behoben: SQLite erzwingt Fremdschlüssel bei jeder regulären Verbindung. |
| F12: Analysehistorie wächst | Anhängen ist das dokumentierte Speicherverhalten. Es wurde weder ein Speicherproblem noch eine vereinbarte Aufbewahrungsgrenze nachgewiesen. | Keine historischen Berichte löschen. |
| F13: gesperrtes Chrome-Profil | Nur dasselbe Anwendungsprofil kollidiert, nicht ein gewöhnliches separates Chrome-Profil. Ein simulierter Treiberfehler bleibt einschließlich der konkreten Sperrmeldung erhalten. | Erwartbare Ressourcensperre; kein verschluckter Fehler nachgewiesen. |
| F14: Übertragung ans Modell | Die Übertragung ist Teil der gewählten KI-Funktion. Die Endpunkthilfe nennt Analyseanfragen an den Server, die Vorlagenhilfe Beispiel-Trades und Datengrundlagen für das Modell. „Nirgends im UI“ ist zu pauschal. | Ein zusätzlicher Satz beim Schalter wäre verständlicher, behebt aber keinen belegten Funktionsfehler. |

## F1: Stop-Nachweis als Voraussetzung für Grün

Die Reproduktion setzt keinen erfundenen Risikoscore in ein Ergebnisobjekt.
Ein synthetischer Export enthält 26 monatliche XAUUSD-Gewinntrades mit
jeweils 0,1 Lot und 1.000 Gewinn bei 10.000 Startkapital. Parser und Engine
liefern vollständige Forensik, kein Martingale-Flag und `stop_evidence=none`.
Die unabhängige Engine-Probe ergibt Score 3,0. Bei hinreichendem monatlichem
Ertrag wurde daraus vor der Änderung tatsächlich ein grüner Kandidat.
Auch ein Orderbuch mit nur teilweise gesetzten SL-Feldern blieb grün.

Die Korrektur ergänzt `ScanResult.stop_evidence` und führt den strukturierten
Wert aus der Engine durch Live-Scan, lokale Analyse, Datenbank, Laufarchiv und
KI-Forensik-JSON. `ampel_for()` lässt Grün nur bei `direct` oder `cluster` zu.
`partial`, `none`, fehlende und unbekannte Werte ergeben Gelb mit Begründung.
Ein behauptender Freitext wie „BEWIESEN“ ersetzt den strukturierten Wert nicht.

Die Berechnung der Score-Dimensionen bleibt unverändert. Fehlender Nachweis
ist ein auswertbarer negativer Befund, kein fehlgeschlagener Download und
keine unvollständige Analyse. Er löst deshalb keinen Wiederholungsabruf aus.
Drawdown-Ablehnung, Martingale-Flag, Ausschlussliste und technische Fehler
behalten ihren Vorrang. `cluster` bezeichnet weiterhin die projektgemäß
zulässige statistische Signatur, nicht einen Orderbuch-Direktnachweis.

`FORENSICS_VERSION` steigt von dem nach der vorherigen Prüfung verwendeten
Arbeitsstand 3 auf **4**. Ältere Live-Befunde werden beim Laden als erneut zu
prüfen markiert. Laufarchive bleiben gekennzeichnete historische
Momentaufnahmen; ihre alten Urteile werden nicht nachträglich umgeschrieben.

Regressionen: [`tests/test_review10_stop_gate.py`](../tests/test_review10_stop_gate.py).
Die relevanten Grün-ohne-Evidenz-Tests wurden vor dem Fix als fehlschlagend
beobachtet und bestehen danach. Positive Direkt- und Clusterfälle werden
einschließlich Speicherung und erneutem Laden geprüft.

## F6: Ungültige Versuchszahl

Bei null Durchläufen blieb die lokale Antwortvariable `r` ungebunden, wurde
aber beim Erzeugen der Fehlermeldung gelesen. Negative Werte haben denselben
Fehlerpfad. Der Parameter wird nun früh auf eine positive Ganzzahl geprüft;
andere Werte erzeugen einen verständlichen `ValueError`, ohne HTTP-Anfrage
oder Wartezeit. Die bestehende Semantik bleibt erhalten: Der Wert 3 bedeutet
drei Gesamtversuche einschließlich des ersten Abrufs. Erfolgreicher Abruf,
zulässige Statusausnahmen und Drosselungsabbruch wurden offline geprüft.

Regressionen: [`tests/test_doc10_ingestion.py`](../tests/test_doc10_ingestion.py).

## F11: Tatsächlich wirksame Fremdschlüssel

In einer leeren temporären Datenbank konnten vor dem Fix
`store_forensik(123, ...)`, `store_trade_file(124, ...)` und
`store_analysis(125, "gesamtbericht", ...)` ohne entsprechendes Elternsignal
speichern. `PRAGMA foreign_key_check` meldete anschließend drei Waisen.
Ein fehlender Löschpfad verhindert solche ungültigen Inserts nicht.

`_connect()` aktiviert jetzt `PRAGMA foreign_keys=ON` vor der Transaktion.
Die ungültigen Schreibzugriffe werden mit `sqlite3.IntegrityError` abgewiesen.
Atomare Scan-Speicherung mit zuerst angelegtem Elternsignal, reguläre
Signalberichte und globale Portfolios mit `NULL` funktionieren weiterhin.
Die zuvor ergänzte Migration alter Portfolio-Verweise von 0 auf `NULL`
bleibt erhalten.

Bestehende andere Waisen werden durch Aktivieren der Prüfung weder
automatisch bereinigt noch gelöscht. Eine entsprechende Alt-Datenbank wurde
isoliert nachgestellt; die produktive Datenbank wurde dafür nicht geöffnet.
Tests, die bisher Analyseberichte ohne Elternsignal erzeugten, legen nun
ihre benötigten Testsignale ausdrücklich an. Das absichtliche Erzeugen eines
alten ungültigen Datenbestands schaltet die Prüfung nur in dieser Testverbindung
explizit aus.

Regressionen: [`tests/test_review10_db.py`](../tests/test_review10_db.py).
Die drei Tests für fehlende Eltern scheiterten vor der Änderung und bestehen
danach. Gültige Speicherung und Erhalt vorhandener Daten sind ebenfalls geprüft.

## Validierung

- `python -m pytest -q`: **323 bestanden** (30 zusätzliche Fälle seit der
  vorherigen externen Prüfung), Laufzeit 39,40 Sekunden.
- `python scripts/verify_engine.py`: **85 PASS, 0 FAIL**.
- `ruff check src app_pages streamlit_app.py`: ohne Befunde.
- `git diff --check`: ohne Befunde.
- Unabhängiges Gegenreview der Stop-Korrektur: keine zusätzliche bestätigte
  Lücke in den Ergebnis-, Speicher- oder KI-Pfaden.

Alle neuen Reproduktionen verwenden temporäre Dateien, temporäre Datenbanken
oder simulierte Antworten. Kein echter MQL5-/Modellaufruf und kein Browser-
oder Serverstart waren erforderlich. Die Änderungen dieser Prüfung sind
nicht committet oder gepusht.
