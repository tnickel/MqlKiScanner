# Vantage-Nachtrag: Legacy-Epoch und UTC-Alter

16.10.2026, Abschluss 21:04 Europe/Berlin. Neuer konkreter Gegenbefund nach dem ersten Freeze; nur Vantage geändert, MqlDownloader unverändert eingefroren. Der erste Snapshot, dessen Package-Log und `clients_manifest.json` bleiben unverändert erhalten. Der aktuelle finale Beleg ist **`clients_manifest_final2.json`** mit **`vantage_final2`**, `vantage_final2_package.log` und `vantage_final2_python.log`.

## Unabhängiges Vorher-Repro

`LegacyEpochAgeTest.berlinEpochZeroDailyRowDoesNotBecomeFiftyYearsOfAgeOnNewYorkHost` verwendet ausschließlich synthetische Daily-CSV in TempDir. Unter America/New_York stehen darin 1970-01-01, 1969-12-31 und ein gültiger Aktivitätstag 2026-01-01, jeweils endliche Strategie-PnL ungleich null. Vor Fix erwarteter ältester belegter Tag2026-01-01, tatsächlich1970-01-01; `vantage_epoch_before.log`, 1 Test/1 Fehler. Ein unter Berlin gespeicherter Epoch0-Tag wurde durch die spätere NY-Hostzone zu einem falschen jahrzehntelangen Altersbeleg.

Ursache: `TradeStore.aeltestesHistoriesDatum` verglich den persistierten Tag ausschließlich mit dem *heutigen Rechnerzonen*-Datum von Instant.EPOCH. Berlin ergibt1970-01-01, NY1969-12-31. Der Ausschluss wechselte also beim Verschieben der gleichen Datei. Zusätzlich verwendeten Store-Futurecutoff, Monatskorrektur, GUI-Wochen und REST-Wochen LocalDate.now() aus der Hostzone, obwohl neue Activitydaten UTC sind.

## Minimaler Fix

- Daily-Aktivitätsbelege schließen beide tatsächlich persistierbaren Epoch0-Tage1969-12-31/1970-01-01 ausdrücklich aus. Keine anderen alten Tage verschoben oder erraten.
- TradeStore erhält eine optionale Clock für deterministische Tests; Standard systemUTC und jede übergebene Clock wird aufUTC normalisiert. Zukunftsprüfung und Monatskorrektur verwenden dieseUTC-Datumsbasis.
- SignalProvider.wochenSeit(date,clock) ist die gemeinsame Wochenrechnung für GUI und REST. REST bindet Aktivitätscutoff und Wochen an dieselbe feste UTC-Request-Clock.
- Bestehende Altersfixtures/Erwartungen verwenden nun ausdrücklich UTC, damit die Tests bei einer anderen Host-Kalendergrenze nicht selbst falsche181/182-Tage-Belege erzeugen.
- Keine TTL-/Auswahl-/Grenzwertänderung, keine Produktionsdatenmigration. Inaktivitätsanzeige tageOhneTrade und andere fachlich getrennte Copier-Datumsregeln wurden nicht verändert.

Neue Mitternachtsgegenprobe: Instant2026-10-17T00:30Z mit Clocks New_York/Berlin/Kiritimati. UTC-Tag17.10. bleibt aktuell,18.10. bleibt Zukunft;182 Tage ergeben26 Wochen und181 Tage25 Wochen unabhängig von der Clockzone. Sie prüft Store-Cutoff und genau den gemeinsamen Wochenhelper der GUI/REST.

## Finale isolierte Nachweise

- Neues HEAD-Archiv503f34a plus sämtliche aktuellen Vantage-Overlays nach `vantage_final2`; alte Snapshotdateien nicht überschrieben.
- `mvn -o -B -Duser.timezone=America/New_York package`: **78 bestanden, 0 Fehler/0 Skips**, JAR gebaut; `vantage_final2_package.log`.
- Alters-/REST-Gegenprobe unter Pacific/Kiritimati: **30 bestanden**, `vantage_final2_timezone.log` (Teilmenge, nicht zur Vollsuite addiert).
- Python aus demselben neuen Snapshot: **21 bestanden**, `vantage_final2_python.log`. Python-Code unverändert gegenüber dem ersten Freeze.
- `git diff --check` sauber, Stage leer. `clients_manifest_final2.json` enthält sämtliche Overlay-SHA256, geprüfte Gleichheit zum tatsächlichen Snapshot, Baumdigest, Basisarchiv- und Paket-SHA256. Der unveränderte MQL-Beleg wird darin aus dem ursprünglichen Manifest übernommen.

Wiederholung war erforderlich, weil die erste NY-Gegenprobe Trade-Epochs und Cache-UTC-Beleg prüfte, aber den separat persistierten Daily-Epoch-Sentinel nicht enthielt. Die neue Regression schließt diese konkrete Coverage-Lücke. Aktueller Vantage-Freeze nach diesem Nachtrag; keine weiteren Änderungen geplant.
