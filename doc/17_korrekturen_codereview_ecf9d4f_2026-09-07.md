# Korrekturen zum Code-Review von ecf9d4f

Datum: 7. September 2026. Grundlage: die sieben bestätigten Befunde aus
[`16_codereview_ecf9d4f_2026-09-07.md`](16_codereview_ecf9d4f_2026-09-07.md).

## Umgesetzte Korrekturen

| Befund | Korrektur | Regressionen |
|---|---|---|
| F1: CSV-Reihenfolge verändert Stop-Nachweis | Bei gleicher maximaler Häufigkeit wird deterministisch das kleinere Distanzniveau ausgewählt. Eine gleich starke Nullklasse verhindert damit einen positiven Stop-Nachweis. Auch die Auswahl des repräsentativen Symbols ist stabil. Bestehende Mindesthäufigkeiten bleiben erhalten. | `test_review17_engine.py`: mehrere Zeilenanordnungen durch Parser, Engine und Ampel; positive Gleichstände; Mehrsymbolfall |
| F2: HTTP 403 lässt alte Bewertung aktuell erscheinen | Direkte Hard-Stops durchlaufen den lokalen Speicherpfad und erhalten das aktuelle Fehlerergebnis. Erst danach wird die Ausnahme weitergereicht. Weitere Exporte, Browser-Fallbacks und Wiederholungen unterbleiben. | `test_review17_pipeline.py`: echte HTTP-403-Fehler der Session bei Kennzahlen oder Export, Erstscan, vorhandener Bericht, Archiv und DB-Schreibfehler |
| F3: Abgewiesene Anmeldung umgeht Fail-Fast | `Mql5AuthenticationError` kennzeichnet abgewiesene und nicht bestätigte Anmeldungen. Die Fehlerzählung erkennt den Typ auch hinter einem fehlgeschlagenen Fallback; Meldungstexte und bool-Schnittstellen bleiben erhalten. | `test_review17_login.py`: ursprünglicher, gewechselter und abgelaufener Account; unbestätigter Login; Exception-Ketten; durchgängiger Session-/Exporter-/Pipeline-/DB-Test |
| F4: Neuerstellung überspringt übernommene Signale | „Nur neue“ begrenzt die MQL5-Prüfung. Die Berichtslogik erhält alle geeigneten Ergebnisse und entscheidet selbst über passende Wiederverwendung oder gewünschte Neuerstellung. | `test_review17_ui.py`: gemischte Alt-/Neu-Läufe mit gültigem oder fehlendem Bericht sowie ausdrücklicher Neuerstellung |
| F5: Übernommene Bewertungen werden als NEU markiert | Frische wird ausschließlich nach tatsächlich gespeicherten Signalbefunden oder Signalberichten übertragen. Eine ausdrücklich leere Liste bleibt leer; nur unbekannte Altstände nutzen den bisherigen Fallback. | `test_review17_ui.py`: Cachelauf, KI-only mit erfolgreicher/teilweise/komplett gescheiterter Speicherung, leere und unbekannte Frische; ergänzte Runner-Vertragsprüfungen |
| F6: Lot-Histogramme verlieren Häufigkeiten | Gemeinsame Formatierung erhält zusätzliche Volumenpräzision bei Histogrammen und Bandbreiten. Unterschiedliche Werte kollidieren nicht mehr; normale zweistellige Darstellung bleibt erhalten. | `test_review17_engine.py`: normale Lots, Millilots, kleine Werte, wiederholte und umgeordnete Volumina; Histogrammsumme entspricht Tradezahl |
| F7: Uhrzeit verfälscht Vollmonate | Die Monatsschleife verwendet reine Kalenderdaten. Die bestehenden Regeln für volle beziehungsweise unvollständige Randmonate bleiben erhalten. | `test_review17_engine.py`: verschiedene Uhrzeiten, Monats-/Jahreswechsel, Schaltjahre, Teilmonate und negatives Februarergebnis |

## Speicher- und Aktualisierungsregeln

Ein erfolgreicher Datenbankschreibvorgang entscheidet über die NEU-Markierung.
Auch ein neu gespeicherter Fehler-/Vorprüfungsstand aktualisiert einen
Signaldatensatz. Reine Übernahme oder ein erfolgloser Schreibversuch tun dies
nicht. Bei einer Wiederholung kann der erste Versuch bereits einen Fehlerstand
gespeichert haben, auch wenn das Schreiben im zweiten Versuch scheitert. Das
laufbezogene Persistenzmerkmal wird deshalb über beide Versuche kumuliert,
einschließlich eines Hard-Stops im zweiten Versuch.

Die KI-Zusammenfassung ergänzt `updated_ids`: jede Signal-ID mit mindestens
einem erfolgreich gespeicherten Teil- oder Gesamtbericht erscheint genau einmal.
Diese Information bleibt auch bei späterem Teilfehler oder Abbruch verfügbar.
Bereits erzeugte Modellantworten bleiben bei einem Speicherfehler wie bisher im
Ergebnis erhalten; ohne erfolgreiche Speicherung erzeugen sie keine NEU-Markierung.

Ein HTTP-403-Abbruch verwirft historische Analysen nicht. Er speichert den neuen
unvollständigen Prüfstand und dessen Fehler, damit der aktuelle Katalog keine
alte grüne Bewertung als erfolgreich aktualisiert darstellt. Scheitert auch
dieses Schreiben, bleibt die vorherige atomare DB-Version erhalten; das
Ausnahmeergebnis enthält sowohl den ursprünglichen Abbruch- als auch den
Speicherfehler und steht für das Laufarchiv bereit.

## Bewertungsstand und Prüfung

Bewertungsstand **6** berücksichtigt die korrigierte Clusterentscheidung.
Ältere Live-Befunde müssen erneut geprüft werden; Laufarchive bleiben historische
Momentaufnahmen. Es wurden keine produktiven Befunde während der Entwicklung
migriert oder neu berechnet.

- Vollständige pytest-Suite: **442 Tests bestanden** — 42 zusätzliche Fälle.
- Referenzprüfung: **85 PASS, 0 FAIL**; alle bisherigen Anker unverändert.
- Ruff für Produktcode und bearbeitete Testmodule: ohne Befund.
- Git-Diff-Prüfung: keine Whitespace-Fehler.

Tests verwendeten temporäre Datenbanken, synthetische CSVs, AppTest und
simulierte Modell-/Browserantworten. Keine echten Netzwerkaufrufe, Browserstarts
oder Änderungen an produktiven Zugangsdaten, Cookies oder Datenbanken. Die
bestehenden Referenz-CSVs wurden ausschließlich gelesen.

Die Engine-Änderungen sowie der Hard-Stop-/Persistenzpfad wurden zusätzlich
unabhängig gegengeprüft. Die drei vorbestehenden Dokumentlöschungen gehören
nicht zu diesem Commit.
