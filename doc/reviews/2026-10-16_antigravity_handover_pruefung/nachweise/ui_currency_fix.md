# Währungsschutz für „Alle Signale“

16.10.2026. Drei exklusiv bearbeitete Dateien:

- `SignalKiScanner/app_pages/alle_signale.py`
- `SignalKiScanner/src/mqlkiscanner/alle_signale_ui.py`
- `SignalKiScanner/tests/test_alle_signale_seite.py`

## Bestätigter Fehler und minimale Korrektur

Die Übersichtsseite rief `signal_statistik.berechne` ungeprüft auf und konnte
native MQL-Kontobeträge als USD-Kennzahlen darstellen. Der gemeinsame
Detailrenderer konnte zusätzlich vorgefüllte USD-Teilstatistik und eine
geöffnete gecachte Tradeliste anzeigen, ohne die Währung zu prüfen.

Der neue kleine UI-Helfer verwendet ausschließlich Roots bestehenden
`pipeline.require_usd_account`; keine eigene Währungs- oder Quellenpolitik.
Er sperrt die Statistik vor dem Cache-/Berechnungsaufruf und die Detailansicht
vor USD-Karten, Charts und Tradelisten. Die Tabelle unterdrückt auch alte
USD-/Effizienzwerte aus Sitzungs-/DB-Objekten. Warnung und vorhandene Diagnosen,
etwa eine veränderte Trade-SHA, bleiben sichtbar. Der Guard verändert weder
Quelldaten noch Ergebnisse und hebt keine Ampel auf.

Lokale Demos behalten ihren expliziten Modellvertrag. Erfolgreich konvertierte
Pelican-/Vantage-/Zulu-Exporte verwenden die vom Adapter bestätigte effektive
Währung USD; eine abweichende Originalkontowährung ist keine falsche Sperre.
Freie Quellenkürzel erzeugen dagegen keinen Konversionsbeleg. Backendguard,
Legacy-DB-Beleginvalidierung und Katalog-Metadatenreload liegen bei Root und
wurden von diesem Agenten nicht verändert.

## Unabhängiger Vorherbeleg

`ui_currency_before` enthält den damaligen aktuellen Scanner mit den neuen
Tests; ausschließlich die beiden UI-Produktdateien wurden aus HEAD
zurückgesetzt. Damit blieben Roots Backend-Währungsguards unverändert.

`ui_currency_before.pytest.log/.xml`: **9 erwartete Failures, 2 bestanden**.
Die neun Fälle belegen None/USC/EUR für MT4 und MT5 sowie direkte Detailaufrufe
mit vorgefüllter Teilstatistik und bereits geöffnetem Tradecache. Die beiden
USD-Kontrollen funktionieren im Ausgangscode bereits. Es handelt sich um einen
bewussten Regressionsnachweis, keinen fehlgeschlagenen Abschlusslauf.

## Finale gezielte Prüfung

Snapshot `ui_currency_final2` stammt aus HEAD plus Overlay der tatsächlichen
aktuellen Änderungen. Manifest: `ui_currency_final2.manifest.json`.
Die Tests verwenden nur synthetische CSVs, temporäre Datenbanken und AppTest;
externe Requests werden vom vorhandenen conftest abgewehrt. Keine Appserver,
Plattformlogins oder LLM-Aufrufe wurden gestartet.

`ui_currency_final2.pytest.log/.xml`: **219 bestanden, 1 Skip**, 0 Fehler,
46,02 Sekunden. Enthalten sind 15 neue Währungs-AppTestfälle und alle Tests aus:

```text
test_alle_signale_seite.py
test_alle_signale_performance.py
test_virtuelle_messanzeige.py
test_archiv_finanzaggregate.py
test_drawdown_anzeige.py
test_ergebnis_gewinn_retdd_ui.py
test_forensik_trade_sha.py
test_katalog.py
test_report_pdf_ui.py
test_signal_finanzteilstatistik.py
test_regelwerk.py
test_ui_duplicates.py
test_trueretdd_spalte.py
test_studien_batch.py
test_stale_independent_study_display.py
```

Der Skip betrifft den optionalen privaten Originalexport. Die ganze
`test_alle_signale_seite.py` enthält 35 bestandene Fälle. Die neuen Fälle prüfen
wirkliche AppTest-Anzeigen und Berechnungsaufrufe, einschließlich alten
Session-USD-Werten, unbekannter/USC/EUR-Kontowährung, USD-Kontrollen, Demos und
konvertierten Quellverträgen. Bestehende synthetische USD-Fixtures dieser Datei
tragen nun ausdrücklich account_currency=USD. Die Demo-Kontrolle nutzt den
gemeinsamen Detailrenderer, weil der Livekatalog Demos absichtlich ausblendet.

Separater vorheriger Lauf von Alle-Signale, Drawdownanzeige und Review17-UI:
57 bestanden (`ui_currency_final.pytest.log`). Der maßgebliche Abschluss für
die finalen UI-Bytes ist der neuere breite `ui_currency_final2`-Lauf.

Runtime:
`C:/Users/tnickel/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe`.
Befehl: `python -m pytest -q` mit den genannten 15 Dateien und
`--junitxml=../ui_currency_final2.pytest.xml` im isolierten Snapshot.

## Bytebelege und Freeze

`ui_currency_owned_hashes.json` dokumentiert die drei eigenen Dateien;
Arbeitskopie und finaler Snapshot sind jeweils bytegleich:

```text
app_pages/alle_signale.py
0113a6c447ec2c03f12a41123dae8af29753380b67bb0623f89f24cd42a9653f
src/mqlkiscanner/alle_signale_ui.py
117566f425b55fdebdbfa1103c4b3219c014cbd9eefe171b9860270f000c7ff6
tests/test_alle_signale_seite.py
3fda8ecfb05f19fb86faa77a963f289c140b91c614d2705b56468074bbebe29a
```

`git diff --check` für diese Dateien ohne Fehler. Seit Abschlusslauf keine
Produktänderungen dieses Agenten. Root erstellt anschließend den gemeinsamen
frischen Scanner-Endsnapshot mit den zusätzlichen parallelen Backendfixes;
dieser gezielte UI-Lauf ist kein Ersatz für jenen Gesamtlauf.

Verwendeter Skill: developing-with-streamlit aus
`C:/Users/tnickel/.agents/skills/developing-with-streamlit/SKILL.md`, über den
Discoveryhelper auf die installierten lokalen Referenzen aufgelöst. Änderungen
folgen den lokalen Best-Practices-/AppTest-Hinweisen; kein Designumbau.
