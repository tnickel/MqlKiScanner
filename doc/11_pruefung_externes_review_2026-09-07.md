# Unabhängige Prüfung des externen Code-Reviews

Ausgangsstand: `5ffa6636ca04be6aa92adc4bd5b8f807cf29a815` auf `main`.
Geprüft am 7. September 2026. Grundlage ist der vom Nutzer angehängte Bericht
mit acht Befundgruppen. Dessen Bewertungen und Arbeitsanweisungen wurden nicht
als Beweis oder als eigenständiger Auftrag übernommen.

**Ergebnis:** Sechs Befundgruppen enthalten berechtigte Mängel und wurden
korrigiert. Zwei beschreiben spezifizierte Grenzen und wurden nicht als
Implementierungsfehler behandelt. Mehrere behauptete Auswirkungen sind
übertrieben oder ohne zusätzliche Daten nicht belegt.

## Ergebnis je Befund

| Nr. | Unabhängiges Urteil | Ergebnis |
| --- | --- | --- |
| 1 | Zahlenverlust bestätigt; pauschale Folge für das Altersrisiko nicht bestätigt | Englische Tausenderzahlen korrekt parsen; Datenpfad bis zur DB geprüft. |
| 2 | Bewusste und bereits dokumentierte FX-Grenze | Keine erfundenen USD-Umrechnungen ergänzt. |
| 3 | Unbelegte Index-Kontraktannahme bestätigt; behaupteter Faktor 150 nicht allgemein belegbar | Bei unbekanntem Punktwert/Gewinnwährung keine Geldbeträge ausgeben. |
| 4 | Verletzung der deklarierten Fremdschlüsselbeziehung bestätigt; derzeit kein regulärer Laufzeitabsturz | Globale Portfolios mit `NULL` speichern, alte 0-Verweise kompatibel migrieren. |
| 5 | Gleichzeitige Worker aus getrennten Sitzungen bestätigt | Prozessweite Startkoordination und Wiederverbindung implementiert. |
| 6 | Beobachtung korrekt, aber Verhalten entspricht Spezifikation und Referenzskript | Martingale-Detektor nicht umdefiniert; Grenze dokumentiert. |
| 7 | Fehler bei Kommentarvarianten bestätigt; behaupteter CSV-NoneType-Pfad widerlegt | Explizite SL-/TP-Marker robust erkennen; Pflichtfeldprüfung beibehalten. |
| 8 | Fünf Ruff-Befunde bestätigt | Ungenutzte Imports, tote Zuweisung und mehrdeutigen Namen bereinigt. |

## 1. Zahlen auf englischen Detailseiten

Vor der Änderung lieferten `signal_stats._number("1,085")` und
`_number("1,403.03")` jeweils `None`. Ein vollständiges HTML-Beispiel bestätigte
den Verlust bei Handelsanzahl und weiteren numerischen Kennzahlen.

Die neue Verarbeitung unterstützt englische Tausendergruppen mit Komma oder
typografischem Leerraum, Dezimalpunkte und Vorzeichen. Sie verwechselt
Dezimalkommas und fehlerhafte Gruppierungen nicht mit englischer Schreibweise.
Tests prüfen außerdem die Kette HTML → Pipeline → gespeicherte Kennzahlen.

**Einschränkung des fremden Befunds:** Der Detailparser liefert keine
Abonnentenzahl; diese kommt aus der Listenverarbeitung. Fehlende Detail-Wochen
bedeuten auch nicht automatisch neun Risikopunkte: Die Pipeline behält ein
bereits vorhandenes Listenalter, und das Scoring verwendet andernfalls den
Zeitraum aus der CSV. Mit fehlendem Web-Alter und 52 CSV-Wochen ergibt sich
4,5 statt 9,0 für die Track-Dimension. P2 ist für den nachgewiesenen Fehler
angemessener als die pauschale P1-Begründung des Berichts.

## 2. FX ohne belegte USD-Umrechnung

USDJPY, USDCAD und andere nicht USD-quotierte Paare liefern bewusst keine
fertigen USD-Schockwerte, solange die erforderliche historische Umrechnung
nicht belegt ist. Native Währung und Pip-Szenario bleiben verfügbar. Dieses
Verhalten wurde nach dem vorherigen Review ausdrücklich dokumentiert.

Eine automatische positive Einstufung trotz unbekannter Umrechnung wäre
keine Fehlerkorrektur. Die Einschränkung bleibt daher bestehen; sie ist
kein neuer Implementierungsdefekt. Eine spätere Erweiterung benötigt passende
Kontrakt- und historische Umrechnungsdaten.

## 3. Kontrakte außerhalb der unterstützten US-Indexkonvention

Die bisherigen Aufrufe für JP225 und GER40 ergaben tatsächlich 50 USD für
1 Lot und 50 Punkte. Aus dem Symbolnamen lässt sich dieser Dollarwert nicht
begründen. Ebenso wenig lässt sich ohne den konkreten Brokervertrag allgemein
behaupten, dass es exakt 50 JPY beziehungsweise EUR sein müssten oder ein
Fehlerfaktor von 150 vorläge. Kontraktgröße, Gewinnwährung und Tickwert gehören
zur vom Broker festgelegten [Symbolspezifikation](https://www.metatrader5.com/en/terminal/help/trading/market_watch).

Die Engine behält die bisherige explizite Projektkonvention für US30, US100
und US500 einschließlich ihrer Aliase. Andere erkannte Indexnamen wie JP225,
GER40, UK100 und CHINA50 erzeugen `contract_complete=False`, benennen die
fehlende Brokerspezifikation und liefern weder erfundene native Geldbeträge
noch USD-Werte. Positionszahlen und die Indexklassifikation bleiben erhalten.

Die Pipeline zeigt diesen konkreten Grund an. Das betrifft beispielsweise
auch die lokale Goldwave-Datei wegen ihrer CHINA50-Trades. Deren übrige
Kennzahlen bleiben berechnet und archivierbar. Die fachliche Bewertungsversion
wurde auf 3 erhöht, damit alte Live-Befunde bei künftiger Auswahl neu geprüft
werden. Produktive Altbewertungen wurden während der Umsetzung nicht verändert.

## 4. Globale Portfolio-Berichte und Fremdschlüssel

Reproduktion in einer temporären Datenbank: Nach `store_analysis(0,
"portfolio", ...)` meldete `PRAGMA foreign_key_check` einen verwaisten Verweis
auf `signals`. Mit eingeschalteter Fremdschlüsselprüfung scheiterte derselbe
INSERT an `IntegrityError`. In der aktuellen Anwendung war die Prüfung aus;
der Bericht beschreibt deshalb einen Integritätsfehler und einen möglichen
künftigen Abbruch, keinen bereits regulär auftretenden Portfolio-Absturz.

Die Spalte war schon nullable; eine Schemaänderung ist nicht erforderlich.
Globale Portfolios verwenden nun `signal_id=NULL`. Das passt zur
[SQLite-Fremdschlüsselsemantik](https://www.sqlite.org/foreignkeys.html), da ein
globaler Bericht kein Elternsignal hat.

Bei der nächsten Datenbankinitialisierung werden ausschließlich alte
Portfolio-Verweise mit ID 0 auf `NULL` umgestellt. Text, ID, Modell, Tokens,
Zeitpunkt und Reihenfolge bleiben erhalten. Alte API-Aufrufe mit 0 funktionieren
weiter; das Lesen berücksichtigt vorhandene Altberichte auch vor der Migration.
Neue Tests erzwingen Fremdschlüssel und prüfen Speicherung, Migration und
die echte Portfolio-Pipeline. Die globale Einstellung für andere Beziehungen
wurde nicht nebenbei geändert.

## 5. Sitzungswechsel während eines Hintergrundlaufs

Zwei isolierte Streamlit-AppTest-Sitzungen konnten vor der Korrektur zwei
verschiedene Worker gleichzeitig starten. Ein angehaltener erster Crawl
verhinderte den zweiten Start nicht. Dafür wurden weder ein echter Browser
noch externe Dienste gestartet.

Das neue Modul `scan_worker.py` hält den aktiven Workflow außerhalb des
Session-State und entscheidet atomar über neue Starts. Eine neue Sitzung
verbindet sich mit dem bestehenden Lauf und kann dessen Status sehen und
Stop auslösen. Auch konkurrierende bereits abgesendete Startbefehle werden
abgewiesen. Die Ergebnisübernahme wird je Sitzung geführt.

Startfehler und Worker-Ende geben die Registrierung zuverlässig frei.
Getestet wurden außerdem vier gleichzeitige Startversuche und Fehlerpfade.
Der Schutz gilt innerhalb eines App-Prozesses; er behauptet keine Koordination
unabhängig gestarteter zusätzlicher Serverprozesse.

## 6. Martingale und überlappende Zwischentrades

Die beschriebene Sequenz wurde reproduziert: Verlusttrade A von Stunde 0 bis 5,
Zwischentrade B von 1 bis 2, danach größerer Trade C von 6 bis 7. Der aktuelle
Nachfolger-Kanal paart A nicht nachträglich mit C.

Die vor der Prüfung vorhandene Spezifikation verlangt jedoch unmittelbar
benachbarte Einstiege je Instrument, ergänzt um den separaten Korbleiter-Kanal.
Das Referenzskript verwendet dieselbe Nachbarsequenz. Der beobachtete Fall ist
damit eine Grenze dieses Detektors, kein Widerspruch zwischen Spezifikation
und Implementierung. Ein fehlendes Flag beweist nicht allgemein die Abwesenheit
von Martingale. Die Dokumentation stellt diese Grenze nun ausdrücklich klar;
der Algorithmus wurde nicht stillschweigend geändert.

## 7. Stop-Kommentare und fehlende Einstiegspreise

Echte, vom Parser akzeptierte CSV-Dateien mit `[SL]` oder `[sl] #123` wurden
zuvor als manuelle Exits gezählt. Die Erkennung akzeptiert jetzt explizite
SL-/TP-Marker unabhängig von Groß-/Kleinschreibung und mit angehängter
Ticketnummer. Mehrdeutige Kommentare oder bloße Erwähnungen in Freitext gelten
weiterhin nicht als Ausführungsbeweis.

Der behauptete `NoneType`-Absturz durch eine MT4-Handelszeile ohne Einstiegspreis
ließ sich über den Produktpfad dagegen nicht reproduzieren: Bereits
`parser.load_export()` weist die Zeile mit einem fehlenden Pflichtfeld zurück.
Ein manuell konstruiertes, für diesen CSV-Pfad ungültiges Objekt belegt keinen
CSV-Laufzeitfehler. Die bestehende Validierung bleibt erhalten; es wurden keine
Ersatzpreise oder unterdrückten Pflichtfeldfehler eingeführt.

## 8. Linter-Befunde

Alle fünf genannten Meldungen waren vorhanden. Entfernt wurden die ungenutzten
Imports `info_button`, `Trade` und `Path` sowie die ungenutzte Zuweisung
`hard_block`. Der lokale Variablenname `l` wurde in `label` geändert. Dies sind
berechtigte Qualitätsmängel, aber kein Beleg für fünf weitere funktionale
Abstürze oder Rechenfehler.

## Abschließende Validierung

- **293 Tests bestanden**, davon 62 zusätzliche Fälle für Prüfung und Korrektur.
- **85 von 85 Referenzprüfungen bestanden**, ohne Änderung ihrer Erwartungswerte.
- `ruff check src app_pages streamlit_app.py`: **keine Befunde**.
- `git diff --check`: **keine Fehler**.

Testfälle stehen in `tests/test_external_review_db.py`,
`tests/test_external_review_engine.py`, `tests/test_external_review_ingestion.py`
und `tests/test_external_review_ui.py`. Die zuvor pauschalen CHINA50-Annahmen
wurden in alten Testfällen angepasst und durch ausdrückliche Tests auf
unbekannte Kontraktwerte ersetzt. Das ist eine fachliche Korrektur der
Erwartung, keine Anpassung der unveränderten 85 Referenzanker.

Alle Reproduktionen und Tests liefen mit temporären Daten beziehungsweise
simulierten Diensten. Kein produktiver Scan, Browserstart, Commit oder Push
wurde ausgeführt. Die vorhandenen fremden Reviewdateien wurden nicht verändert.
