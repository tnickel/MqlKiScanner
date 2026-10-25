# Tabellenprüfung vom 18.10.2026

## Endergebnis

**Kein zusätzlich bestätigter Fehler der Feldbefüllung im geprüften Scanner-Snapshot.** 2.134 direkte DB-/Stats-Feldvergleiche, 194 unabhängige Jahres-Calmar-Divisionen und 2.232 Parser-/Statistikvergleiche ergeben **0 Abweichungen**. Das ist eine Bestandsprüfung, kein Nachweis der Fehlerfreiheit aller vorgelagerten Downloadabläufe oder konkurrierenden Schreibvorgänge.

Die beiden Ansichten enthalten absichtlich unterschiedliche Mengen: 194 Workflow-Signale in Ergebnisse; 194 Workflow- plus 1.283 noch nicht gescannte Katalogsignale in Alle Signale, zusammen 1.477. Der Quellenkatalog enthält 1.454 eindeutige IDs. 23 gespeicherte Workflow-Signale fehlen im aktuellen lokalen Katalog, bleiben im historischen Gesamtbestand aber sichtbar. Es liegen keine quellenübergreifenden Katalog-ID-Kollisionen im geprüften Snapshot vor.

1.349 Tabellenzeilen referenzieren vorhandene Trade-Dateien; bei diesen registrierten Referenzen wurde keine SHA-Abweichung gefunden. 128 haben noch keinen Tradepfad. 242 Zeilen sind für eigene USD-Werte gesperrt. Diese Gruppen überschneiden sich.

## Warum Zellen leer sind

- **Ergebnisse:** Keine der 194 Zeilen hat eine aktuelle vollständige Forensik. 161 sind ausdrücklich veraltet. Score, eigene Monatsrendite, belastbarer Max-Equity-DD und TrueRetDD sind deshalb jeweils 194-mal leer. Auch das Berichtsdatum bleibt 194-mal leer: `restore_current_reports` zeigt nur Berichte mit passender aktueller Prüfbasis. 123 historische Gesamtbericht-Signalzuordnungen in SQLite ersetzen diesen Nachweis nicht.
- **Alle Signale:** 336-mal fehlt die Tradezahl; zehn lesbare Exporte enthalten nach Parser tatsächlich null Trades. 516-mal fehlt die geometrische Monatsrendite. 507-mal fehlen die jeweiligen True-DD-Prozent- und USD-Felder, 633-mal der Jahres-Calmar.
- Die Studie ist bei 945 Zeilen auf ausdrücklich virtueller Kapitalbasis dargestellt. 249 Calmar-Anzeigen sind vorbehaltlich. Eine virtuelle/vorbehaltliche Anzeige ist keine Workflow-Freigabe.
- 25 Statistikdiagnosen sind klassifiziert: 15 Exporte enthalten negative Open/Close-Zeitintervalle und werden bewusst nur als Finanzteilstatistik verwendet; zehn Exporte sind lesbar, enthalten aber keine Trades. In diesen Fällen wurde kein neuer Parserdefekt bestätigt. Die Finanzteilstatistik sperrt Zeit-/DD-/Renditewerte und behält nur belegbare Finanzdaten.

Null-, Leertext- und echte numerische Nullwerte sämtlicher Spalten stehen in `tabelle_bestand.json`. Die Quellen-/Signal-IDs der Statistikdiagnosen stehen in `tabelle_statistik_diagnosen.json`; keine Rohtrades oder Zugangsdaten wurden in diese Nachweise kopiert.

## Reproduzierbare UI-Prüfungen

- Angeforderte bestehende Tests: **104 bestanden**, 43,02 s, Exit 0; JUnit in `tabelle_pytest.xml`, Befehl in `tabelle_pytest_lauf.txt`.
- Zusätzliche Audit-AppTests: **3 bestanden**, 3,86 s, Exit 0; `tabelle_audit_tests.py` und `.xml`. Geprüft: Auswahl vor verkleinerndem Filter, Auswahl vor Wechsel auf andere Zeile, erneute CSV-Lieferung am gleichen Pfad mit geändertem SHA. Streamlit verwirft die alte Auswahl korrekt; der Statistikcache aktualisiert sich bei neuem SHA.
- Batch-Refresh, Sitzungsergebnisübernahme, Ergebnis-/CSV-Filter, Vorbehaltsfarbe, Quellen-/Versions-/SHA-Zuordnung und Währungsblockaden sind durch die oben genannten bestehenden Tests abgedeckt.

Vollständige Spaltenherkunft beider Ansichten: `tabelle_spaltenmapping.md` sowie AST-Ausdrücke mit Quellzeilen in `tabelle_spaltenmapping.json`.

## Separater Hilfetext-Widerspruch

`src/mqlkiscanner/app_ui.py:503–509` beschreibt den Max-Drawdown als Maximum aus Kursmessung und Monitor. Tatsächlich akzeptiert `pipeline.ScanResult._equity_messwerte` seit der Projektregel ausschließlich die eigene H1-Messung; Monitor-Closing-DD bleibt lediglich Kanal der harten Schranke. Das ist ein bestätigter irreführender Hilfetext (P3), kein im Snapshot falsch gemappter Zahlenwert.

## Durchführung und Grenzen

Produktive Daten und Produktivcode wurden nicht geändert. Der konsistente Scanner-Snapshot wurde ausschließlich lesend geöffnet und für DB-APIs ein weiteres Mal in eine private temporäre SQLite-Datei kopiert. Schreibverzeichnisse wurden vor DB-/UI-Verarbeitung umgeleitet; HTTP war blockiert, PDFs wurden nicht materialisiert. Originalreferenzen für CSV-/Metrics-Artefakte wurden nur gelesen. Fehlende Caches wurden nicht nachgeladen.

Der finale vollständige Auditlauf endete mit Exit 0 nach 143,828 s. Eine anschließende enge Parser-/Datums-Nachprüfung endete ebenfalls mit Exit 0. Im eigenen ersten Auditprototyp war Winrate fälschlich als ungerundeter Nettowert erwartet worden; der endgültige Vergleich verwendet die tatsächliche Projektdefinition (Profit vor Commission/Swap, eine Nachkommastelle). Die dadurch entstandenen Zwischenlauf-Differenzen waren kein Produktbefund und wurden durch den finalen Vergleich ersetzt. Ebenso ist pandas `NaT` im endgültigen Nullprofil als fehlender Wert berücksichtigt.
