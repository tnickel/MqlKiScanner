# Berechnungsreview 02.10.2026

Nur lesendes Produktivreview. Produktivcode und Produktivdatenbank wurden nicht geändert. Die Gegenproben importieren dieselbe autouse-Isolationsfixture wie tests/conftest.py; alle App-Schreibzugriffe erfolgen in pytest-Temp-Verzeichnissen. Keine Modellaufrufe, MT5-Initialisierung oder externen Anfragen.

## C1 P1 RetDD und geometrischer Ertrag sind nicht implementiert

`src/mqlkiscanner/pipeline.py:157` definiert retdd_monat/retdd_jahr und :162 ertrag_monat_geom_pct/cagr_jahr_pct. Die Felder werden im gesamten src-Baum nur gelesen, niemals berechnet oder zugewiesen. Der tatsächliche Einzelprüfpfad berechnet bei :1230 ausschließlich den linearen Startbasis-Ertrag. Persistenz und results_from_db laden diese neuen Werte ebenfalls nicht.

Die echte Einzelprüfung einer temporären CSV mit Konto 1000→1500→1400 und Plattform-DD 20 % besteht die Forensik, liefert aber alle vier Werte null; derselbe Zustand gilt nach DB-Reload und im LLM-Payload. Bei zwei Kalender-Monaten wäre das ungerundete geometrische Monatsmittel 18,32159566 %, Jahres-CAGR 652,9536 %, RetDD/Monat 0,9160798 und RetDD/Jahr 32,64768. Diese Beispielzahlen veranschaulichen den fehlenden Berechnungspfad; eine Festlegung zum Umgang mit Teilmonaten bleibt nötig.

Im lesend abgefragten produktiven Bestand enthält kein einziger der 90 Forensik-Datensätze retdd_monat. Die RetDD-Zelle bleibt somit ohne Wert und die verbindlichen KI-Effizienzregeln können nicht aus Zahlen arbeiten. AGENTS.md behauptet dagegen eine seit 01.10. abgeschlossene Berechnung einschließlich Bestandsranking. Die bestehenden RetDD-Tests in `tests/test_intensivreview_fixes.py:453` und :504 füllen Dataclass-Felder manuell; sie prüfen keine Pipeline-Berechnung.

## C2 P2 Breakeven wird als Verlustnachfolge gewertet

`src/mqlkiscanner/forensics/martingale.py:45` verwendet `netto <= 0`. Zwei nicht überlappende XAUUSD-Trades mit Netto [0, +2] und Lots [0.01, 0.02] ergeben deshalb n_after_loss=1, Verlustnachfolge-Median 2,0 und martingale_flag=true. `pipeline.ampel_for` :428 lehnt das Signal dann hart rot als nachgewiesene Martingale-Signatur ab. Es gab in dieser Probe überhaupt keinen Verlust und keinen Korb.

Breakeven darf weder in Verlust- noch Gewinnnachfolge aufgenommen werden. Im realen Bestand wurden 70 lesbare Trade-Snapshots gesondert geprüft: 29 Signale enthalten solche Nullnachfolger. Ein Wechsel des Nachfolgeflags ergibt sich bei Multi EA Trading #2375343 (aktuell false, ausschließlich echte Verluste true), das jedoch bereits wegen seiner Korb-Leiter rot ist. Eine tatsächlich veränderte Gesamtampel im aktuellen Bestand wurde damit nicht nachgewiesen; der synthetisch reproduzierte Fehlentscheid ist gesichert.

## C3 P2 Monitor-Schrankenverletzung verschwindet bei unvollständiger Forensik nach DB-Reload

`src/mqlkiscanner/pipeline.py:383` bis :386 berechnet den Schrankenstatus beim DB-Laden ohne monitor_trade_eq_dd_pct. Bei erfolgreicher Forensik korrigiert restore_current_reports :773 dies durch refresh_report_verdict. Bei forensik_ok=false/CSV-Fehler wird diese Korrektur ausgelassen.

Isolierte Temp-DB-Probe: Plattform-DD 8 %, Monitor-EQ-DD 46,65 %, forensik_ok=false und CSV-Fehler. results_from_db liefert schranke_verletzt=false und weiß. Unmittelbarer Aufruf derselben zentralen refresh-Funktion liefert schranke_verletzt=true und rot. Die Datenbasis wurde dabei nicht geändert. Die öffentliche Monitor-Schrankenverletzung darf gemäß ampel_for auch ohne vollständige Forensik rot bleiben. Der Fehler kann nach fehlgeschlagenem Quellen-Neuscan in Ergebnisanzeige/REST auftreten; im gerade laufenden Bestand wurde bisher kein konkreter betroffener Datensatz belegt.

## Positiv überprüft

- 231 vorhandene Engine-, Equity- und Intensivreview-Regressionstests bestanden. Die vier neuen Offline-Gegenproben bestanden ebenfalls; sie dokumentieren die beobachteten Fehler, keine Korrektur.
- 68 vollständige, lesbare produktive Trade-Snapshots wurden unabhängig nachgerechnet: Startbasis aus gespeichertem Kapitalbefund, Netto inklusive Kommission/Swap, gleichzeitige Closings als gemeinsame Buchung, USD-DD und maximales relatives DD. Alle 68 stimmen auf 0,01 USD bzw. 0,01 Prozentpunkt mit dem gespeicherten Befund überein.
- Der lineare Monatswert (Netto/Startkapital/historische Monate) stimmt bei allen 68 mit dem gespeicherten Wert überein. Das bestätigt die Rechnung, nicht die Gleichsetzung mit geometrischem ROI.
- Konkrete Cent-Anker: Gold Spike MT4 157,20 USD / 4,57 %, Gold Spike MT5 138,47 USD / 9,14 %, KiraCat 2117,70 USD / 8,14 %, Gold Reaper 319,49 USD / 15,94 %. Lineare Monatswerte dazu 8,71 / 20,85 / 21,55 / 14,54 %.
- Unabhängige synthetische Probe: 1000 Startkapital, -300 Profit -10 Kommission -5 Swap => 315 USD und 31,5 % DD. Harte Schranke reißt korrekt. 1 Lot XAUUSD × 100 USD pro Einheit × 50 USD Schock => 5000 USD, zum damaligen Konto 500 % Exposure.
- Die zuvor korrigierten Equity-Fälle getrenntes relatives DD-Maximum, fehlende Kurse als nicht gemessene Punkte und ehrlicher Stunden-Abdeckungsnenner bestehen ihre isolierten Regressionen. Ohne gespeicherte H1-Bars ist eine unabhängige Nachrechnung der echten Equity-Rekonstruktionen aus dem aktuellen Lauf nicht möglich.

Reproduktion: `python -X utf8 -m pytest doc/reviews/laufreview_2026-10-02/calculations/probe_calculations.py -q -s --disable-warnings`. Ergebnisse: probe_results.txt.

## Zusatzprüfung Credit bei Pure Gold #2362868

**Keine gesicherte Feststellung, dass Credit einfach als Einzahlung zu buchen wäre.** Der Parser akzeptiert und validiert Credit-Zeilen, verwirft sie danach jedoch vollständig (`parser.py:181` kennt nur Balance/Correction). Die frühere Referenz `scripts/reference/analyze_puregold.py:24` berücksichtigt ebenfalls nur Balance. Eine dokumentierte fachliche Begründung für die Credit-Ausklammerung wurde in lokalen Projektdateien nicht gefunden. Credit und eigenes eingezahltes Kapital dürfen ohne belegte Semantik nicht gleichgesetzt werden; eine eigenständige Kreditspur und eine erklärte Behandlung je Balance-/Equity-/Margin-Metrik fehlen.

Lesende aktuelle DB-/CSV-Prüfung, gespeicherter Befund vom 02.10.2026 11:09:44: drei Credit-Zeilen +1250/+1000/+1500 USD am 05.03., insgesamt 3750 USD, sämtlich vor erstem Trade am 09.03. Die Engine verwendet 10000 USD CSV-Einzahlungen. Netto 28383,54 USD und spätere Auszahlungen 12000 USD ergeben end_balance_real 26383,54 USD. Der gespeicherte Webseitenwert ist inzwischen 19732,51 USD, Differenz 6651,03 USD. Das ist eine belegte Datenabweichung, deren Ursache aus diesen Daten allein offen bleibt (Zeitstand, gekürzte Kontobewegungen oder Kennzahlsemantik).

Eine **ausdrücklich hypothetische** Rechnung, die alle Credits in BalanceRows umwandelt, ergibt Basis 13750 USD und end_balance_real 30133,54 USD. Sie beseitigt die aktuelle Webseitenabweichung gerade nicht, sondern erhöht sie auf 10401,03 USD. Relativer Trading-DD würde 9,68 statt 11,91 % betragen; Schockanteil 107,0986 statt 139,7241 %. Dollar-DD 2329,72 USD und Dollar-Schock 17200 USD bleiben unverändert. Diese Unterschiede zeigen die Empfindlichkeit der Basiswahl, beweisen aber nicht, welche Kreditbehandlung fachlich korrekt ist.

Der fehlende Endsaldo-Abgleich bei CSV-Einzahlungen ist bereits ausdrücklich als Cache-Toleranz dokumentiert (`pipeline.py:640–649`). Somit ist die bloße Saldoabweichung kein neuer Verstoß gegen eine bestehende technische Abgleichregel. Für die echte Equity-/Margin-Belastung ist ohne belegte Credit-Konvention und synchronen Kontostand keine korrigierte Zahl gesichert. Credits müssen zuerst separat erhalten und ihr Bezug zur verwendeten Basis geklärt werden; eine pauschale Kapitalbasis-Erhöhung wäre derzeit unbelegt.
