# Kritische Nachprüfung Anhang b7d1aa58

Anhang: `C:/Users/tnickel/.codex/attachments/b7d1aa58-046c-4484-b1b6-d4a22ad39e21/Eingefügter Text.txt`. Prüfung gegen den aktuellen Arbeitsbaum einschließlich der zuvor autorisierten, noch uncommitteten UI-/Kursfixes. Keine Produktionsdaten, laufenden Anwendungen, Netz-/MT5-/KI-Aufrufe oder Git-Veröffentlichungen.

## P3-2: Generische Numeric-Coercion — Vorschlag verworfen

Die Behauptung, alle-None-Spalten müssten generell numerisch umgewandelt werden, ist für die installierte Streamlit-Version 1.63.0 falsch. Der Placeholder bestimmt die sichtbare Missing-Value-Anzeige. `ergebnis_tabelle` besitzt bereits ein explizites Zahlenschema; `daten_tabelle` ist durch B01 ebenfalls korrigiert. Beide bewahren im neuen Regressionstest den Strategienamen `00123`, während eine vollständig unbekannte Gewinnspalte numerisch und unbekannt bleibt. Ein erneuter generischer Inhaltsheuristik-Fix würde die bereits reproduzierte Text-/CSV-Veränderung wieder einführen. **Kein weiterer Produktfix.**

## P3-3: Vollständig unbekannte Sparkline/ImageColumn — kein Fehler reproduziert

Zwei AppTests öffnen die echte Abonnentenstatistik ausschließlich mit synthetischen Datenbanken unter pytest-TEMP:

1. Zwei Anbieter mit jeweils weniger als zwei historischen Messpunkten: `Verlauf 30 T` enthält ausschließlich echte Nullwerte und wird als Arrow-`null` übertragen. Die ColumnConfig bleibt `image`, das optionale Placeholder-Feld ist vorhanden und leer; keine Streamlit-Ausnahme.
2. Gemischter Fall: eine PNG-Daten-URL und ein echter unbekannter Wert. Die PNG-Daten-URL bleibt erhalten, der unbekannte Wert bleibt null; keine Auffüllung durch Zeichenketten.

Ergänzend führt `image_column_probe.js` die tatsächlichen ImageColumn- und Missing-Cell-Funktionen des installierten `DataFrame.CUYs_84n.js` aus. Nur React-Hooks und Canvas-Ausgabe sind minimal ersetzt, kein Browser/Server: `getCell(null)` ergibt `isMissingValue=true`, `data=[]`; mit `placeholder=''` wird das leere Missing-Label gezeichnet. Eine vorhandene PNG-Daten-URL benutzt den normalen Bildpfad. Ergebnis in `image_column_probe.json`, einschließlich Bundle-SHA256. Dies ist kein Browser-Pixeltest; die Behauptung eines aktuellen Fehlers ist mit diesen Repros nicht belegt. **Kein Sparkline-Produktfix, insbesondere kein pauschales `fillna('')`.**

## Bestätigte UI-Lücke: gespeicherte Symbolprovenienz fehlte

Mit dem Clients-Agenten abgestimmtes Schema:

- `report.symbol_substitutionen`: `Dict[str,str]`, Trade-Symbol → tatsächlich verwendeter abweichender Brokername.
- `report.symbol_herkunft`: Trade-Symbol → `{terminal, broker_symbol}` für bestätigte Symbole.
- Dieselben Felder können pro Versuch gespeichert sein; für die ausgewählte Darstellung gilt ausschließlich der eigene Top-Level-Snapshot des Reports.

`equity_studie_ui._symbol_herkunft_anzeigen` zeigt diese gespeicherten Namen, Terminals und den Status der Zuordnung in einem Detail-Expander. Fehlende Altmetadaten werden als fehlender Beleg ausgewiesen und niemals als nachgewiesene Identität verstanden. Es gibt keinen Fallback auf den letzten Versuch oder heutige Alias-Einstellungen. Bei abweichenden Namen erläutert die Anzeige, dass die Namenszuordnung allein weder gleiche Kontraktspezifikation noch identische Originalbrokerkurse belegt. Keine Änderung der Symbolauflösung oder ihrer Freigaberegeln.

Drei AppTests scheiterten vor dem Anzeigefix: Belegtabelle fehlte, fehlender Altbeleg wurde nicht gekennzeichnet, ausgewählter Report hatte keine sichtbare eigene Herkunft. Nach dem Fix bestehen alle drei Fälle. Der Clients-Agent verantwortet die Persistenz/Producer-Felder separat; dieses Paket ändert ausschließlich deren UI-Verbrauch.

## Ergänzter Zeitachsenauftrag des Root-Agenten

`_als_datetime` delegiert an den gemeinsamen neuen Helper `studien_anzeigezeit.als_anzeigezeit`. Die gespeicherten Epoch-Koordinaten werden unverändert als dieselben Uhrzeitziffern ohne falsche UTC-Zeitzonenbehauptung angezeigt. Hauptkurve und Kopiersimulation beziehen das Achsenlabel aus dem gespeicherten Reportframe: `CSV-/Brokerzeit`, `Referenzkurszeit (MT5-H1)` oder `Zeitbasis unbekannt`. Die sichtbare Studien-Caption erklärt die Anzeige ohne Browserzeitzonen-Umrechnung.

Der Überdeckungszeitstrahl hat ausdrücklich eine andere Koordinatenbasis: `equity_studie.ueberdeckung_je_symbol` bildet die aktiven Stunden durch Trade-Zeit + Symboloffset in Referenzkurszeit. Deshalb wird dieser Plot auch bei einer Brokerzeit-Hauptkurve als `Referenzkurszeit (MT5-H1)` beschriftet.

Zeitbasisperioden enthalten in ihrem Speicherformat ISO-Zeitzonenmarker für CSV-Wanduhrzeiten. Die beiden Periodentabellen zeigen eine reine Kopie mit unveränderten Uhrzeitziffern ohne diese Marker und der Caption `Periodengrenzen: CSV-/Brokerzeit, ohne Zeitzonenumrechnung.`. Original-Dicts und persistierte ISO-Werte bleiben unverändert. Tests decken `+00:00` und ein abweichendes `+03:00` ab, ohne auf 09:00 statt gespeicherter 12:00/14:00 umzuschalten.

## Dateien / Nachweise / Freeze

Zusätzliche Produktänderung ausschließlich `src/mqlkiscanner/equity_studie_ui.py`; bestehende Placeholder-Korrekturen erhalten. Neue Testdatei `tests/test_review_20261028_ui_followup.py`. Den gemeinsamen Zeithelper und die Finanz-/Metadata-Producer ändern Root bzw. Clients-Agent, nicht dieses Paket.

Vorher `ui_followup_before.log`: **3 fehlgeschlagen, 4 bestanden** (zwei Numeric-/zwei Sparkline-Gegenbelege bereits grün). Danach wurden fünf Zeitachsen-/Periodenfälle ergänzt. Final `ui_followup_after.log`: **46 bestanden, Exit 0, 11,23 Sekunden** — 12 neue Follow-up-Fälle, acht vorangehende UI-Fix-Fälle, 26 bestehende Equity-Studientests. Ausgeführt nur diese drei Module, keine Vollsuite. `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, eigener `--basetemp` außerhalb des Repositories. Fachliche Rechenwege wurden ausschließlich mit synthetischen Testdaten geprüft; keine Produktionsaufbereitung.

Dateihashes und Testlog-SHA stehen in `ui_followup_manifest.json`. UI-Code und neue Tests nach dem erfolgreichen Lauf eingefroren. Die frühere `ui_fix_manifest.json` bleibt historischer Nachweis des unmittelbar davor getesteten Stands; der dortige Hash für `equity_studie_ui.py` wird durch diesen Nachtrag ausdrücklich ersetzt.
