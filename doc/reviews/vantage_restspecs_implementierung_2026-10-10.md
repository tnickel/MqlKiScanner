# Vantage: belegte restliche Kontrakte 10.10.2026

Die ursprüngliche Offline-PnL-Prüfung bleibt im JSON erhalten. Anschließend hat Root das portable Originalterminal verbunden, exakte Symbolinformationen gelesen, den Datenpfad geprüft und das Terminal beendet. Diese lokalen Livebelege bestimmen die folgenden Kontrakte; keine Kontraktgröße wurde aus einer Namensähnlichkeit geraten.

| Instrument | Kontraktgröße / Gewinnwährung | Zusätzlicher Offlinebeleg |
|---|---|---|
| UK100 | 1.0 GBP je Lot/Preiseinheit | 24 PnL-Stichproben, Median in Kandidatenquote 1.0001076446332242 |
| EU50 | 1.0 EUR je Lot/Preiseinheit | Kein belastbarer PnL-Quotient im Vantage-Bestand; Live-Symbolinfo ist der Beleg |
| US2000 | 1.0 USD je Lot/Preiseinheit | 16 PnL-Stichproben, Median in Kandidatenquote 0.9999999999999984 |
| BNBUSD | 10.0 USD je Lot/Preiseinheit | 2 PnL-Stichproben, Median in Kandidatenquote 9.999999999998884 |
| TTD | 1.0 USD je Lot/Preiseinheit | 1 PnL-Stichproben, Median in Kandidatenquote 1.0000556513996326 |
| SPCE | 1.0 USD je Lot/Preiseinheit | 1 PnL-Stichproben, Median in Kandidatenquote 1.0 |
| ORCL | 1.0 USD je Lot/Preiseinheit | Kein belastbarer PnL-Quotient im Vantage-Bestand; Live-Symbolinfo ist der Beleg |
| LTCUSD | 100.0 USD je Lot/Preiseinheit | Kein belastbarer PnL-Quotient im Vantage-Bestand; Live-Symbolinfo ist der Beleg |
| NFLX | 1.0 USD je Lot/Preiseinheit | 1 PnL-Stichproben, Median in Kandidatenquote 0.9985041136873593 |
| PINS | 1.0 USD je Lot/Preiseinheit | 1 PnL-Stichproben, Median in Kandidatenquote 1.000722543352601 |
| LYFT | 1.0 USD je Lot/Preiseinheit | 3 PnL-Stichproben, Median in Kandidatenquote 1.0000000000000002 |

Alle elf Einträge gelten ausschließlich für Vantage. Cash-Indizes sind eigenständige Einträge; UK100FT wurde weder ersetzt noch als Alias hinzugefügt. NFLX bei RoboForex bleibt bei seinem belegten Faktor 100, NFLX bei Vantage verwendet Faktor 1. Die unbekannte ursprüngliche Zulu-LTCUSD-Spezifikation bleibt gesperrt. Separate .24H-/USD-Namensvarianten wurden bewusst nicht gleichgesetzt.

Indizes behalten die bestehende Klassenannahme von 500 Punkten als editierbares Schockszenario. Aktien/Krypto verwenden 10 % des volumengewichteten Entry der tatsächlich offenen Positionen; das ist eine Szenarioannahme, keine Brokerspezifikation. Native GBP-/EUR-Gewinnwährungen bleiben erhalten und brauchen die belegte historische USD-Umrechnung.

Validiert: 57 gezielte Tests grün, darunter alle elf Livewerte, Brokergrenzen, Cash-/Future-Trennung, RoboForex-NFLX-Bestand und Zulu-LTC-Sperre. Keine Produktionsdatenbankänderungen durch diesen Implementierungsschritt; die Auswirkungen werden erst durch Roots anschließende Messung belegt.

Belege: [Live-Symbolinfo](vantage_restspecs_live_2026-10-10.json), [Offlinevergleich mit getrennter Implementierungsnachmessung](vantage_specfamilien_offline_2026-10-10.json).

Bereits bestandene Teilstudien werden beim nächsten Lückenlauf ebenfalls erneut versucht, wenn mindestens eines ihrer ausdrücklich unter `symbole_ohne_kontrakt` ausgeschlossenen Instrumente inzwischen am ursprünglichen Signalbroker auflösbar ist. Neue Batchberichte speichern dafür `original_broker` getrennt vom Kursreferenzterminal. Bei Altstudien liefern Workflow bzw. exakt zugeordnete Quellenmetrics den Broker; fehlt er, wird keine fremde Brokerspezifikation freigegeben. Ohne ausgeschlossene Instrumente entsteht keine zusätzliche Metricsabfrage. Der Check verändert weder die 95-%-Schranke noch pauschal alle vorhandenen Studien. Eine unzuverlässige Nachmessung ersetzt keine bereits verlässliche, nicht basislose Studie zum selben Trade-SHA; ihr Fehlergrund wird im Batchprotokoll angezeigt.

Diese Auswahl erkennt neu verfügbare Kontrakte, jedoch keine nachträgliche Änderung eines bereits benutzten Faktors. Für diesen getrennten Fall wäre ein gespeicherter Fingerprint aus ursprünglichem Broker und tatsächlich verwendeten Symbolen/Faktoren/Gewinnwährungen sinnvoll. Altstudien ohne solchen Fingerprint beweisen die heutige Spec-Gleichheit nicht; eine globale Freigabe oder Invalidierung wurde deshalb nicht ergänzt.
