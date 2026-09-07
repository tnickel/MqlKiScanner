# Korrekturen nach dem zweiten Code-Review

Ausgangsstand: `00c330d`. Die 15 Befunde des zweiten Reviews wurden korrigiert.

## Verhalten nach der Korrektur

| Befund | Änderung |
| --- | --- |
| 1. Teilweise DB-Speicherung | Signal, Exportreferenz und Forensik werden in einer Transaktion gespeichert. Fehler werden sichtbar und einmal wiederholt. Inhaltlich adressierte CSV-Kopien unter `data/trade_snapshots` halten gespeicherte Analysen unabhängig vom veränderlichen Downloadcache. |
| 2. Drawdown nach früher Auszahlung | Die virtuelle Trading-Kurve startet mit dem Nettokapital unmittelbar vor dem ersten Trade. Spätere Kontobewegungen bleiben wie bisher außerhalb dieser Kurve. |
| 3. Forex-Währungs-/Pipfehler | Kurswährung und USD-Wert werden getrennt. 500 JPY-Pips entsprechen 5,00 Preiseinheiten. Ohne belegte Umrechnung nicht USD-quotierter Paare bleiben Dollarwerte unbekannt und die Pflichtprüfung unvollständig. |
| 4. Alte Live-Befunde | Gespeicherte Bewertungen benötigen die aktuelle fachliche Version und die zeitlichen Schockdaten. Altbefunde werden als veraltet angezeigt und von „Nur neue“ nicht mehr als fertig geprüft übernommen. |
| 5. Formatabhängige Stopbewertung | Einheitlicher Stop-Evidenzstatus für direkte, statistische, teilweise und fehlende Belege. Leere Orderbuchfelder senken das Risiko nicht mehr. Ein Stop-Loss benötigt keinen zusätzlichen Take-Profit. |
| 6. Martingale bei Instrumentwechsel | Lot-Nachfolger werden innerhalb desselben normalisierten Instruments verglichen; die Belege nennen das betreffende Instrument. |
| 7. Gleichzeitige Kontobewegungen | Bewegungen mit identischem Zeitstempel werden vor der Exposure-Prüfung summiert. Die CSV-Reihenfolge beeinflusst den Prüfstatus nicht mehr. |
| 8. Defekter CSV-Cache | Ungültige Cache-Dateien werden verworfen. Neue Exporte werden erst nach Parserprüfung atomar veröffentlicht; ein Wiederholungsversuch kann frische Daten laden. |
| 9. HTTP-Status beim Login | Loginprüfungen verwenden dieselbe 403-Abbruch- und 429/503-Backoff-Behandlung wie reguläre Abrufe. |
| 10. Fehlende Zugangsdaten | Eigener Fehlertyp führt unmittelbar zur Vorprüfung. Ein Browser wird dafür nicht gestartet. |
| 11. KI-Parallelitätslimit | Z.ai-Code 1302 führt zu begrenztem Backoff und Wiederholung. Code 1113 bleibt ein gesonderter Guthabenfehler. |
| 12. Fehlende/beschädigte KI-Eingabe | Datei- und Parserfehler werden dem einzelnen Signal zugeordnet. Nachfolgende geeignete Signale werden weiter verarbeitet. |
| 13. Portfolio nicht archiviert | Portfolio-Text, Modell, Zeitpunkt und Speicherstatus werden zusammen mit dem Lauf archiviert. Historische Ansichten laden nur ihr eigenes Portfolio. Ein DB-Fehler bleibt als Warnung sichtbar. |
| 14. Alte Kandidatenauswahl | Neue Listen und neue Filterauswahlen invalidieren nachgelagerte Daten, auch wenn der neue Abruf fehlschlägt. |
| 15. Lokaler Stop | Die Verarbeitung stoppt nach der laufenden Datei und zeigt den tatsächlichen Fortschritt. |

## Daten und fachliche Grenzen

Die Bewertungsversion steht in `src/mqlkiscanner/analysis_version.py`. Bei weiteren fachlichen Änderungen muss sie erhöht werden. Es erfolgt keine stille Umschreibung alter Bewertungen: Historische Laufarchive bleiben Momentaufnahmen; Live-Befunde werden beim nächsten angeforderten Scan erneut geprüft.

Die bestehende USD-Konvention des Projekts bleibt für Kontostände, Gold und unterstützte Indexkontrakte erhalten und ist im Exposure-Bericht gekennzeichnet. Es werden keine historischen Wechselkurse aus späteren Handelsgewinnen abgeleitet. Ohne geeignete Umrechnungsdaten entsteht bei betroffenen FX-Signalen ein ausdrücklich unvollständiger Befund, keine positive Risikoeinstufung.

Unveränderliche Exportkopien werden über den SHA-256 ihrer tatsächlich gespeicherten Bytes adressiert. Ein SQL-Rollback kann eine unreferenzierte Kopie hinterlassen, verändert aber keine alte CSV-Version. Identische Inhalte verwenden denselben Snapshotpfad. Eine automatische Bereinigung dieser Kopien ist nicht Teil der Korrektur, damit Archive ihre Quelldaten behalten.

Die auf Nutzerwunsch akzeptierte Tokenbudget-Überschreitung wurde nicht geändert. Produktive Bewertungen wurden während der Umsetzung nicht neu berechnet; Tests verwenden temporäre Daten und simulierte externe Dienste.

## Prüfung

Abschließende Gesamtprüfung: **231 Tests bestanden** (61 zusätzliche Testfälle gegenüber dem Ausgangsstand). **Alle 85 Referenzprüfungen bestanden**, ohne deren Erwartungswerte zu ändern. `git diff --check` meldet keine Fehler.

Gezielte Regressionstests stehen in `tests/test_second_review_engine.py`, `tests/test_second_review_ingestion.py`, `tests/test_second_review_pipeline.py`, `tests/test_second_review_storage.py` und `tests/test_second_review_ui.py`.

Der frühere Kontraktklassen-Test mit NZDCAD wurde auf EURUSD umgestellt: Seine bisherige USD-Erwartung setzte eine nicht belegte CAD-Umrechnung voraus. Separate neue Tests verlangen bei NZDCAD nun fehlende USD-Werte. Die Referenzwerte in `scripts/verify_engine.py` wurden nicht verändert.
