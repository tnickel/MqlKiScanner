# Korrekturen zum Code-Review von 6164a66

Datum: 7. September 2026. Grundlage: die elf bestätigten Befunde aus
[`14_codereview_6164a66_2026-09-07.md`](14_codereview_6164a66_2026-09-07.md).
Die zwei dort beschriebenen fachlichen Grenzen bleiben unverändert.

## Umgesetzte Korrekturen

| Befund | Korrektur | Regressionen |
|---|---|---|
| F1 | KI-Berichte erhalten eine Bewertungsbasis aus CSV-Inhalt, Forensik-/Implementierungsversion, Signalbefunden und Risikokriterien. Nur passende Texte werden im aktuellen Ergebnis geladen. Identische Daten bleiben wiederverwendbar. Alte/ungebundene Texte bleiben in der Historie; ein Hinweis kennzeichnet ihre fehlende Aktualität. Auch direkte Portfolio-Aufrufe prüfen die Signalberichte. Globale DB-Portfolios sind ausdrücklich historische Speicherstände. | `test_review15_reports.py`, Cache-Test in `test_step_flow.py`, historisches Portfolio in `test_review15_ui.py` |
| F2 | Beide unterstützten CSV-Header werden vollständig und in ihrer Reihenfolge validiert. Vertauschte SL-/TP-Spalten werden zurückgewiesen. | `test_review15_engine.py` |
| F3 | Nettoergebnisse desselben Zeitstempels werden gemeinsam gebucht. Exposure verarbeitet Kontobewegungen, Einstiege und Abschlüsse jeweils gruppiert. Vollständig gehedgte Positionen behalten auch bei Nullschock korrekte Peak-Metadaten. | `test_review15_engine.py` |
| F4 | Beide parallelen Modellantworten gelangen vor dem ersten DB-Write ins Ergebnis. Speicherfehler werden je Antwort getrennt ausgewiesen; weitere Signale können weiterlaufen. Nach fehlerhaften Teilstufen wird kein neuer Gesamtbericht erstellt. | `test_review15_llm.py` |
| F5 | Worker übertragen Listen- und Kandidatenstand einschließlich ausdrücklich leerer Auswahl. Wiederverbundene Sitzungen behalten keine alte Auswahl. | `test_review15_ui.py` |
| F6 | Tabellen und Auswahlzuordnungen verwenden denselben stabilen Ergebnis-Snapshot. | `test_review15_ui.py` |
| F7 | Cookies, HTTP-Sessions und persistente Chrome-Profile sind an den Benutzernamen gebunden. Ein erzwungener Login verlangt die tatsächliche Formularanmeldung. | `test_review15_login.py` |
| F8 | Eine gemeinsame, wiedereintrittsfähige Sperre serialisiert Browser-Anmeldung und Export einschließlich Staging und Browserabschluss, unabhängig vom UI-Einstieg. | `test_review15_login.py` |
| F9 | Stop wird vor Folgestationen und insbesondere vor einer neuen Anmeldung geprüft. Bereits laufende Aufrufe dürfen kooperativ fertig werden. | `test_review15_ui.py` |
| F10 | Scan- und Ergebnisseite verwenden dieselbe Worker- und Abschlussübernahme. | `test_review15_ui.py` |
| F11 | Jeder gestartete Modellprompt wird genau einmal als erfolgreich oder fehlgeschlagen erfasst; nicht gestartete Prompts werden übersprungen. Zwei parallele Fehler ergeben zwei Fehler und einen übersprungenen Gesamtbericht. | `test_review15_llm.py`, korrigierte Erwartung in `test_review_findings.py` |

## Datenbestand und Bedienung

- Bewertungsstand **5** verlangt eine erneute Prüfung älterer Live-Forensik.
  Die Regeln zur Sekundenauflösung stehen in `03_forensik-tests.md`.
- Die additive SQLite-Migration ergänzt `analyses.basis`. Sie erhält
  bestehende Berichtstexte und ist gegen gleichzeitige Initialisierung abgesichert.
  Ohne belegte Grundlage werden alte Berichte nicht automatisch als aktuell übernommen.
- Das bisherige ungebundene Browserprofil bleibt erhalten. Neue Profile liegen
  unter `data/chrome_profile_accounts/<Benutzer-Hash>` und sind Git-ignoriert.
  Bestehende Cookies ohne Benutzerbindung werden nicht übernommen; beim ersten
  Einsatz ist eine neue Anmeldung erforderlich.
- Fertige KI-Texte bleiben bei Speicherfehlern im Ergebnis und damit für das
  Laufarchiv verfügbar. Der Fehler wird weiter angezeigt; daraus wird kein
  erfolgreicher DB-Schreibvorgang abgeleitet.
- Archive und ausdrücklich historische Portfolio-Speicherstände behalten
  ihren Erstellungsstand. Neue Portfolios verwenden nur passende Signalberichte.

## Prüfung

Alle neuen Fehlerpfade wurden mit temporären Datenbanken, synthetischen CSVs,
kontrollierten Threads, Streamlit-AppTest und simulierten Modell-/Browserantworten
geprüft. Kein Produktivserver oder echter Browser wurde gestartet; keine
produktiven Zugangsdaten, Cookies oder Datenbanken wurden für Tests verändert.
Die acht bestehenden Referenzdatensätze wurden ausschließlich gelesen.

- Vollständige pytest-Suite: **400 Tests bestanden**.
- Referenzprüfung: **85 PASS, 0 FAIL**, einschließlich der vier Cent-Anker.
- Ruff für `src`, `app_pages` und die bearbeiteten Testmodule: ohne Befund.
- Git-Diff-Prüfung: keine Whitespace-Fehler.

Engine- und UI-Änderungen sowie Berichtsbindung/Fehlerbehandlung wurden zusätzlich
unabhängig gegengeprüft. Dabei gefundene Peak-Metadaten beim Nullschock wurden
vor Abschluss korrigiert und als Regressionstest ergänzt.

Die drei vorbestehenden Dokumentlöschungen gehören nicht zu diesem Commit.
