# Nachbehebung der drei Tabellenpunkte

Stand: 18.10.2026. Scope: ausschließlich `alle_signale_ui.py`, `app_ui.py`,
`app_pages/ergebnisse.py` und gezielte Tests. Keine Bewertungsgates,
Datenmigrationen, produktiven Datenzugriffe, Downloads oder Appstarts.
Der installierte Streamlit-Skill und seine Tabellen-/Testreferenzen wurden
verwendet; die Prüfung erfolgt mit reinen Zeilenfunktionen und AppTest.

## M-1: Historischen Roh-DD ausdrücklich als veraltet kennzeichnen

Ein historischer Rohwert kann zur Auditnachvollziehbarkeit weiterhin in
`True-DD ≈` erscheinen. `tabellen_zeile` kennzeichnet ihn jetzt im Messstatus
mit `Workflow-Forensik veraltet` und `True-DD ≈ aus altem Workflow-Befund,
kein aktueller Messnachweis`. Damit kann er nicht mehr unkommentiert als
aktuelle, lediglich unzuverlässige Kursmessung gelesen werden.

Eine separat übernommene aktuelle H1-Studie behält ihre eigene Anzeige und
ihren eigenen Status; sie wird nicht zum historischen Workflowrohwert
umgedeutet. Es wurden weder Messwerte noch die Workflowfreigabe verändert.
Code: `src/mqlkiscanner/alle_signale_ui.py:219`.

## CSV und Ergebnistabelle verwenden denselben vorbereiteten Datenstand

`results_table_dataframe` bereitet die bisherigen Bewertungsfelder sowie
Link, Abonnentenstand, 30-/7-Tage-Differenzen und Dokumentangaben gemeinsam
auf. Die Ergebnisseite erzeugt diesen DataFrame genau einmal und reicht
ihn sowohl an den Renderer als auch an den CSV-Export.

`render_results_table` akzeptiert dazu optional den rückwärtskompatiblen
Parameter `table_data`. Vor der Ergänzung der reinen Studie-Aktionsspalte
kopiert es den übergebenen Frame. Der CSV-Export enthält alle fachlichen
Spalten; `Bericht` und `Studie` sind reine UI-Aktionen und bleiben ausgenommen.
Die Kompaktansicht kann weiterhin Spalten verbergen; der Download enthält
die vollständigen fachlichen Felder derselben gefilterten Ergebniszeilen.

Die lokale History-/Dokumentdatenbank wird dafür nicht ein zweites Mal
gelesen. Änderungen während eines parallelen Syncs können daher nicht mehr
zwischen Tabelle und Export zu abweichenden Zusatzwerten führen.

Code: `src/mqlkiscanner/app_ui.py:335` und `:371`,
`app_pages/ergebnisse.py:482`, `:492`, `:494`.

## Quellenneutraler Linkkopf

Die Ergebnistabelle bezeichnet den Link als `Signal-Link` statt pauschal
`MQL5`. Die bereits quellenbezogene Ziel-URL bleibt erhalten.
Der vom Hauptagenten korrigierte H1-Max-DD-Tooltip wurde unverändert bewahrt.
Code: `src/mqlkiscanner/app_ui.py:559`.

## Tests und autorisierte Anpassung der historischen Auditassertions

Die fünf neuen Fälle in `tests/test_review_table_fixes.py` prüfen:

- Stale-/Nichtstale-Kennzeichnung eines angezeigten Roh-DD.
- Eigenständige Anzeige einer separaten aktuellen H1-Studie.
- Ungefilterte und gefilterte Ergebnisse mit identischer Reihenfolge,
  identischen Fachspalten und identischen Werten in Tabelle und CSV.
- Leere/fehlende Abonnentenbilanzen, genau eine lokale History- und
  Dokumentabfrage pro Seitenlauf sowie neutralen Linkkopf und erhaltenen
  H1-Tooltip.

Auf ausdrückliche Freigabe wurden ausschließlich die beiden betroffenen
Istzustandsproben samt zugehörigen Kommentaren/Docstrings in der fremden
`tests/test_audit_tabellen_20261018.py` aktualisiert: Die CSV-Fachspalten
müssen nun vorhanden sein; beim historischen Roh-DD muss `veraltet` im
Messstatus stehen. Die Prüfungen wurden nicht ausgeklammert oder gelockert.
Die übrigen Prüfungen dieser Datei bleiben erhalten.

```powershell
python -m pytest tests/test_review_table_fixes.py tests/test_audit_tabellen_20261018.py tests/test_ergebnis_gewinn_retdd_ui.py tests/test_alle_signale_seite.py tests/test_forensik_trade_sha.py tests/test_drawdown_anzeige.py tests/test_fix_signale.py tests/test_review18_ui.py -q -p no:cacheprovider --junitxml=doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/fix_tabellen_pytest.xml
```

**102 passed in 40.52s, Exit 0.** Nachweise: `fix_tabellen_pytest.log`,
`fix_tabellen_pytest.xml`, `fix_tabellen_pytest_exit.txt`.

Der erste Lauf hatte 101 bestandene Tests und eine falsche Annahme im neuen
Test: Ein nicht veralteter Roh-DD darf bestimmungsgemäß als vorbehaltlicher
Anzeigewert auch in `True-DD %` stehen. Nur diese Erwartung wurde korrigiert;
die Produktivberechnung blieb unverändert. Der erste Lauf ist getrennt in
`fix_tabellen_pytest_initial.log` und `.xml` erhalten.

Eine unabhängige lesende Gegenprüfung fand keinen weiteren Fehler in diesen
drei Änderungen. `git diff --check` der betroffenen Dateien war erfolgreich.
Die gezielte Abnahme ersetzt keine abschließende projektweite Regression
oder produktive Betriebsabnahme.
