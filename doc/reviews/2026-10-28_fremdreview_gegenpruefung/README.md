# Kritische Gegenprüfung des Fremdreviews vom 28.10.2026

Geprüft wurde der vom Nutzer angehängte Text „Umfang: die fünf Commits vom 28.10. im Detail …“ gegen den aktuellen lokalen Arbeitsbaum. Ausgangs-HEAD: `853bc3a743040256e17f2333b63fbfb9e4219e13`. Die vorherige Scanner-/None-Behebung war zu Beginn bereits lokal vorhanden; ihre Nachweise unter `../2026-10-28_scanner_review_behebung/` bleiben historische Belege und werden nicht überschrieben.

**Ergebnis:** Zwei weitere Fehler sind bestätigt und behoben: der fehlende dauerhafte Beleg tatsächlich verwendeter Brokernamen sowie die pauschale UTC-Beschriftung verschiedener Studien-Zeitbasen. Mehrere andere Hinweise betreffen bereits behobene Fehler, unbewiesene Betriebsrisiken oder ungeeignete Änderungsvorschläge.

## Bewertung der einzelnen Aussagen

Die ersten drei unnummerierten Absätze des Eingangstextes werden hier entsprechend dessen Schlussabsatz als P2-1 bis P2-3 bezeichnet.

| Aussage | Ergebnis der Gegenprüfung | Maßnahme / Beleg |
|---|---|---|
| P2-1: Unbegrenztes Styler-Limit kann Speicher/Latenz belasten; Cap bei 2–4 Mio. Zellen | Plausibles Skalierungsrisiko, aber kein belegter aktueller Ausfall und keine hergeleitete sichere Cap. `_compute()` erzeugt bei den verwendeten Teilmengen-Stylings nicht zwangsläufig für jede Tabellenzelle ein Styleobjekt; die Tabellenübersetzung kostet trotzdem Speicher/Zeit. | Keine willkürliche Grenze und kein stiller Verlust finanzieller Markierungen. Ein belastbarer Grenzwert benötigt eine Lastmessung mit definiertem Speicher-/Latenzziel. Der vorhandene Marshallingtest bleibt grün. |
| Nebenbefund zu P2-1: konkurrierendes Lesen/Setzen sei wegen monotoner Werte praktisch unkritisch | Falsch. Zwei getrennte Read-Compare-Write-Folgen können die Grenze senken: kleiner Aufruf liest alt, großer schreibt neu, kleiner überschreibt mit seinem kleineren Wert. | Bereits vorher mit gemeinsamem Lock behoben; deterministischer Parallelitätstest in `test_styler_zellenlimit.py`. |
| P2-2: tatsächlich geladener Brokername fehlt im Studienbericht | Bestätigter neuer Fehler. `symbol_feeds` belegt nur das Terminal. Eine nachträgliche Kopie aus flüchtigem Anbieterzustand reicht nach Terminalwechsel/Reset nicht. | Exakter Brokername und Terminal werden beim erfolgreichen Abruf erfasst, je Rechenversuch eingefroren und im ausgewählten Bericht gespeichert; Anzeige im Studien-Detail. Auch ein exaktes konfiguriertes Brokersuffix wird erfasst. |
| P2-3: fehlende Symbole je Terminal live systematisch probieren | Diagnose-/Datenbeschaffungsauftrag, kein nachgewiesener zusätzlicher Codefehler. AUDSGDMs vorhandene Aliasauflösung war bereits korrigiert. Bestandskandidaten für Frankreichindex/Kupfer beweisen weder ökonomische Gleichheit noch vollständige historische Abdeckung. | Keine produktive MT5-Probe und keine blinden F40-/Kupfer-/Futures-Aliase. Die verbleibende Kursabdeckung ist damit ausdrücklich nicht als gelöst nachgewiesen. |
| P3-1: generische Zahlenheuristik kann numerische Textspalten verändern | Als Fehlerklasse bestätigt, aber im lokalen Stand bereits behoben. Die vorgeschlagenen Ersatzheuristiken „Suffix“ oder „mindestens ein Float“ sind kein zuverlässiger Spaltenvertrag. | Explizite Messwert-Whitelist beibehalten. Zusätzliche Tests beider Tabellenbauer sichern u. a. Strategienamen `00123`. |
| P3-2: dieselbe generische Zahlenkonvertierung in `ergebnis_tabelle` ergänzen | Änderungsvorschlag verworfen. Er würde die gerade entfernte Verwechslung von Textidentitäten und Messwerten erneut einführen und steuert nicht zuverlässig den Missing-Value-Platzhalter. | Fachliche Spaltentypen und explizites `placeholder=""` beibehalten; unbekannte Zahlen bleiben unbekannt. |
| P3-3: all-None-Sparkline-Spalte könnte mit ImageColumn scheitern | Im installierten Streamlit 1.63.0 nicht reproduziert. Tatsächliche Seite mit vollständig fehlenden sowie gemischten Kurven läuft ohne Ausnahme; all-None wird als Arrow-null übertragen. Der installierte ImageColumn-Pfad verarbeitet null als leere Bildliste. | Kein `fillna('')`. Zwei AppTests prüfen echte Seite, Arrow-Typ, ImageColumn-Konfiguration und leeren Platzhalter. |
| P3-4: Zeitachse fälschlich als UTC bezeichnet | Bestätigt, mit Einschränkung: konstante/uneinheitliche Versätze können CSV-/Brokerkoordinaten liefern; gemeinsam angewandte variable Zeitmodelle liefern Referenzkurskoordinaten. Die pauschale Aussage „alle Punkte sind Brokerzeit“ stimmt ebenfalls nicht. | Beschriftung anhand des gespeicherten `zeitbasis.frame`: `CSV-/Brokerzeit`, `Referenzkurszeit (MT5-H1)` oder `Zeitbasis unbekannt`. Keine Verschiebung gespeicherter Koordinaten. PNG, PDF und Plotly sind konsistent. |
| P3-5a: unbekannte native MQL-Währung verhindert paralleles Vorladen | Im vorherigen Schritt bereits behoben. Währungsbeleg wird im Quellen-Worker geklärt; neue native CSVs benötigen frische Metrics und eine erneute USD-Prüfung. | Vorhandene 14 Prefetch-Regressionsfälle weiter grün; bekannte Nicht-USD-Konten bleiben gesperrt. |
| P3-5b: `aktuelles_signal` als letzter Worker-Schreibzugriff | Fortschrittsanzeige kann zwischen Workern wechseln; kein Verlust finanzieller Ergebnisse oder belegter zusätzlicher Datenfehler. | Keine Änderung am Rechenweg. |
| P3-5c: SQLite-Timeout könne unter Last einen Download als Fehler werten | Mögliches Betriebsrisiko, im Review ohne beobachtete Ausnahme oder Reproduktion. | Kein pauschales Wiederholen beliebiger, möglicherweise nicht idempotenter Schreibtransaktionen. Kein produktiver Lasttest. |
| P3-6: GROUP-BY-Scan; „kein Index nötig“ | Performancebeobachtung, kein nachgewiesener Korrektheitsfehler. „Kein Index nötig“ folgt nicht allgemein aus einem gemessenen Scan; bestehende Explain-Nachweise zeigen Scan und temporäre Bäume. | Keine produktive Index-/DB-Änderung. Nutzen und Schreibkosten wären anhand der tatsächlichen Abfrage/Last zu messen. |
| None-Mechanik: Float-NaN und gemischte String/None-Spalten seien automatisch leer | Für die installierte Version sachlich falsch. Der Standardplatzhalter kann auch dort `None` darstellen; ein Typwechsel ist keine vollständige Lösung. | Die vorherige Behebung setzt an 15 belegten nullable Dataframe-Aufrufen explizit den leeren Platzhalter. AppTest-/Protobufbelege bleiben gültig. |
| Leere Finanzwerte seien teilweise legitime Datenlücken | Für den zuvor geprüften Datenstand nachvollziehbar; daraus folgt kein erfolgreicher Gesamtlauf. | 447 fehlende eigene USD-Nettoergebnisse (200 Quellenwerte + 247 weitere) sind von 318 fehlenden Modell-Nettoergebnissen zu trennen. Keine Umdeutung zu 0, keine produktive Neuberechnung. |
| Ältere Drawdown-/Recherche-Commits seien nur stichprobenartig gesichtet | Ehrliche Begrenzung des Fremdreviews. Dessen 140 Tests beweisen keine vollständige Finanzkorrektheit. | Auch diese Gegenprüfung ist eine gezielte Fehlerprüfung, kein Nachweis künftig bester Signale oder vollständiger Korrektheit aller Rechenwege. |

## Zusätzliche Korrekturen im Detail

### Dauerhafte Symbolherkunft

- `kursdaten.KursDaten.symbol_herkunft` dokumentiert bei einem positiven H1-Abruf den exakten, case-sensitiven `broker_symbol` und das Terminal. Ein fehlgeschlagener Folgeabruf entfernt nur den aktuellen Symbolbeleg.
- `_KursProvenienz` erfasst die Herkunft sofort am erfolgreichen Lesevorgang. Interne Symbol-Fallbacks, Provider-Resets und spätere fehlgeschlagene Rechenversuche können diesen Berichtssnapshot nicht überschreiben.
- Direkte Studien und Batch-Studien speichern `symbol_herkunft`, `symbol_feeds` und die abweichenden Namen unter `symbol_substitutionen`. Der ausgewählte Bericht und die einzelnen Versuche erhalten unabhängige Kopien. Nicht angefragte Altbelege werden ausgeschlossen.
- Der bestehende JSON-Report-Speicher bewahrt die Zusatzfelder ohne neue Datenbankmigration. Ein isolierter Speichern-/Lesen-Test prüft den Roundtrip.
- Die Detailansicht zeigt die Herkunft des ausgewählten Ergebnisses. Bei Altberichten wird der tatsächlich verwendete Brokername als unbelegt behandelt; heutige Aliase werden nicht als historische Belege ausgegeben.

Die Namensspur macht einen fehlerhaften Alias nachvollziehbar. Sie beweist allein weder identische Kontraktspezifikationen noch die Eignung als Ersatz für Originalbrokerkurse.

### Richtige Beschriftung der Zeitdomäne

`studien_anzeigezeit.py` dekodiert die gespeicherten Koordinaten mit identischen Datums-/Uhrzeitziffern und ohne unbelegten Zeitzonensuffix. Ausschließlich das gespeicherte `zeitbasis.frame` entscheidet über das Label. Unbekannte/historische Frames bleiben ausdrücklich unbekannt. Der gemeinsame variable Zeitabgleich wird nicht fälschlich als Brokerzeit bezeichnet.

Hauptkurve, Kopiersimulation, PNG und PDF benutzen denselben Vertrag. Der Überdeckungszeitstrahl behält seine eigene Referenzkurs-Zeitbasis. Die gespeicherten ISO-Periodengrenzen der CSV-/Brokerabschnitte werden nur in einer Anzeigekopie ohne pseudo-UTC-Suffix formatiert. Berechnungen, gespeicherte Epochen und historische Berichte werden dadurch nicht umgerechnet.

## Verifikation

**531 Tests bestanden, 0 Fehler, 0 übersprungen**, gemeinsamer gezielter Lauf über **28 Testdateien**, **123,23 Sekunden**. Darin enthalten: die bisherigen 457 Regressionstests, bestehende verwandte Tests und 29 neue Fälle dieser Gegenprüfung (9 Herkunft, 12 UI, 8 Zeitdarstellung). Die separaten Vorprüfungen (137 Herkunft/Quellenpfad und 46 UI) sind Teilmengen und werden nicht addiert.

Die Tests isolieren Daten/Settings/Secrets über `tests/conftest.py`, verwenden synthetische Kurslieferanten, blockieren externe Requests und laufen ohne Bytecode-/pytest-Cache mit getrenntem temporärem Bestand. Die Sparkline- und Herkunftsanzeigen werden mit dem installierten Streamlit über AppTest geprüft; die PDF-Zeitbasis zusätzlich über extrahierten PDF-Text. Keine Vollsuite, keine Plattform-/MT5-Verbindung und kein bezahlter KI-Test.

Die Eingangskopie, das gemeinsame Testprotokoll/JUnit, getrennte Vorprüfungen sowie `abschluss.json` und Dateihashes liegen unter `nachweise/` bzw. in diesem Verzeichnis. Ein Zwischenlauf der Herkunftsprüfung hatte eine unvollständige temporäre Codekopie ohne das neue Zeitmodul; der abschließende isolierte Lauf mit vollständigem Arbeitsbaum und der gemeinsame Lauf sind grün. Das wird nicht als Produktfehler oder als zusätzlicher Testlauf mitgezählt.

`git diff --check` ist sauber. Git-HEAD blieb unverändert; es wurde nichts gestaged, committet oder gepusht. Der produktive Listener auf Port 8504 blieb bei PID 165596. App/Terminals wurden nicht bedient oder neu gestartet, keine produktiven Studien neu berechnet und keine Alias-/Kursdatenbestände verändert. Andere vorhandene Nutzeränderungen bleiben erhalten. Ein bereits laufender Prozess kann weiterhin zuvor geladenen Code verwenden.
