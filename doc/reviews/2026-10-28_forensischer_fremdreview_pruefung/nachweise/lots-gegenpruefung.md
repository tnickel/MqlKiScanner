# UI-Gegenprüfung Anhang 45955e37

Quelle: `C:/Users/tnickel/.codex/attachments/45955e37-9537-4b1b-9eb2-19a85df8a829/Eingefügter Text.txt`. Aktueller Arbeitsbaum einschließlich der bereits vorhandenen Reviewkorrekturen, keine Rücknahme dieser Änderungen.

## Styler-/None-Aussagen: aktuell widerlegt bzw. erledigt

`app_ui.render_results_table` setzt bereits `placeholder=''` am echten `st.dataframe`-Aufruf (`app_ui.py:498`), ebenso die beiden beanstandeten Stationstabellen (`station_dialoge.py:577,682`). Die lokale Streamlit-1.63-API und der vorhandene Frontend-/AppTest-Nachweis erklären das Missing-Value-Rendering ausdrücklich über diesen Placeholder. Ein zusätzliches `df.style.format(na_rep='')` ist dafür nicht nötig und wurde **nicht** ergänzt. Die neue Behauptung, ein float-NaN garantiere allein eine leere Zelle, bleibt falsch.

Die blinde Textkoerzierung aus Befund 2 ist bereits durch das explizite Zahlenschema in `abonnenten_analyse_ui.daten_tabelle` ersetzt; der Admin-Zählfehler aus Befund 1 ist bereits durch Statusfilter behoben. Die vorhandenen früheren Regressionen bleiben bestehen. Der Review beschreibt in diesen Punkten den alten Stand, keine neu nachgewiesenen Fehler im korrigierten Arbeitsbaum.

## Lots min/max: unvollständige Payloads defensiv abgesichert

Die F-String-Behauptung ist **bedingt richtig**: Bei künstlich fehlenden Grenzen erzeugt `f"{werte.get('lots_min')}–{werte.get('lots_max')}"` tatsächlich den fertigen Text `None–None`, bei NaN `nan–None`. Ein fertiger String ist kein Missing Value und wird deshalb von einem Placeholder nicht korrigiert.

Ein aktueller produktiver Fetchfehler ist daraus **nicht** belegt: `app_pages/alle_signale.py:_statistik_fuer/_statistik_cached` verwendet `signal_statistik.berechne`; dessen vollständiger Pfad übernimmt `stats.compute(parsed).per_symbol`. `stats.py:74–79` berechnet beide Grenzen mit `min/max` aus den validierten Tradevolumina. Fehler-/Teilstatistiken verlassen `alle_signale_ui.render_detail` bereits vor der Symboltabelle. Eine produktive Häufigkeit unvollständiger Min-/Max-Daten wird nicht behauptet.

Nach ausdrücklicher Root-Freigabe wurde der **Anzeigevertrag für unvollständige historische/statistische Payloads** trotzdem minimal abgesichert:

- Beide Grenzen unbekannt: echter fehlender Wert, mit `placeholder=''` leer dargestellt.
- Nur eine Grenze bekannt: bekannte Grenze unverändert, andere Seite ausdrücklich `unbekannt`.
- Bekannte Grenzen einschließlich echter 0 bleiben unverändert; keine Rundung kleiner Lots und keine erfundenen Ersatzgrenzen.
- Das ursprüngliche Statistikpayload wird nicht verändert.

Produktänderung ausschließlich `src/mqlkiscanner/alle_signale_ui.py`: kleiner Anzeigehelfer `_lots_spannentext`, Nutzung in der Symboltabelle und deren leerer Placeholder. Keine Änderung an Statistik, Parser, Bewertung oder Datenbeschaffung. `app_ui.py` und `station_dialoge.py` wurden in diesem Nachtrag nicht bearbeitet.

## Nachweis

Neue Datei `tests/test_review_20261028_lots_ui.py`: sieben AppTest-Fälle. Ein Fall führt eine reale synthetische Positions-CSV über `signal_statistik.berechne` bis zur echten Detailansicht; `0.001–0.125` bleibt exakt erhalten. Sechs Fälle prüfen ausgelassene Felder, explizites None, einseitige Grenzen, NaN und echte 0. Für vollständig fehlende Grenzen wird neben `isna` auch das tatsächlich vorhandene leere Protobuf-Placeholder-Feld geprüft.

Vorher: **5 fehlgeschlagen / 2 bestanden**, `lots_ui_before.log`. Der validierte normale Pfad und echte 0 bestanden bereits vor der defensiven Korrektur. Final: **16 bestanden, Exit 0, 5,27 Sekunden**, `lots_ui_after.log` — sieben neue AppTests plus neun bestehende Fälle aus `tests/test_signal_statistik.py`. Keine Vollsuite und kein weiterer Testlauf dieses Nachtrags. Ausführung mit Python `-B`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` und separatem Windows-TEMP-`--basetemp`; conftest isoliert Storage und blockiert Netz.

## Übrige Reviewaussagen, nur lesend eingeordnet

Aus bloß vorhandenen Bars unter ähnlichem Symbolnamen folgen weder vollständige Abdeckung des benötigten Zeitfensters noch gleiche Kurse/Kontrakte. Die Aussagen „alle Lücken sofort geschlossen“, „identisch/keine Risiken“ und pauschale Lot-/Kontraktannahmen brauchen deshalb eigene Belege. Ein vorgeschlagenes Alias ist noch kein produktiv geprüfter Kursnachweis. Der einzelne benannte 800er-Lauf ist kein zeitloser Gesamtbestand; unser früherer ausschließlich lesender Audit erfasste am 28.10. um 16:16 den gesonderten Auftrag `211e8d0f...` mit 1.000 Tasks. In diesem Nachtrag wurde **keine Produktions-DB erneut gelesen**.

Ebenso ersetzen die pauschalen Entlastungen zu Modellveröffentlichung oder Deadlockfreiheit keine Prüfung sämtlicher Zustands-/Fehlerpfade. Diese Aussage ist keine Behauptung eines zusätzlich gefundenen Fehlers. Quellen-/Cache-/Batch-/PNG-Details liegen beim Root-/Clients-Review und wurden hier nicht verändert oder redundant produktiv geprüft. Die dort bereits eingefrorenen Korrekturen bleiben erhalten.

Code und neue Testdatei sind nach dem erfolgreichen Lauf eingefroren. Finale Roh-/LF-SHA256 und Testlog-SHA stehen in `lots_ui_manifest.json`. Die alten UI-Manifeste bleiben datierte Nachweise vor diesem kleinen Nachtrag.
