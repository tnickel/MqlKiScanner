# Stufe 0: dauerhafte Abschluss- und Abbruchbelege

18.10.2026. Begrenzte Zusatzkorrektur nach ausdrücklich autorisierter Fehlerbehebung; keine neue automatische Ausführung oder produktive API-Anforderung.

## Bestätigte Fehler vor der Änderung

Gezielte Tests gegen den bisherigen Code ergaben sieben reproduzierbare Fehlschläge (`fix_stufe0_before.txt`):

- `KeyboardInterrupt` nach angenommener Job-ID und `SystemExit` bei Client-Erzeugung hinterließen überhaupt keinen `client_updates`-Eintrag.
- Ein unerwarteter Protokollfehler übersprang den normalen Abschluss; der bisherige äußere Parallel-Fallback rekonstruierte einen leeren Startzustand und verlor angenommene Job-ID und Teilergebnisse.
- Vor dem ersten Statuspoll gab es keinen dauerhaften Beleg des bereits angeforderten Client-Jobs.
- Ein Stop schon während der Bereitschaft wurde zwar im normalen DB-Pfad gespeichert, aber der letzte Live-Callback blieb auf `wartet` stehen.
- Jede DB-Ausnahme in `_persistiere` wurde ohne Meldung oder Ersatzbeleg verschluckt.

## Korrektur

`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/client_updates.py`:

- Bestehende append-only-Tabelle hält jetzt Start (`wartet`), Client-Annahme (`laeuft`, mit Job-ID) und genau einen terminalen Abschluss je normal beendetem Quellenaufruf fest.
- Der zentrale `finally`-Abschluss gilt auch für frühe Rückgaben und unerwartete Fehler. Originale Job-ID, bekannte Zähler und Ursache bleiben erhalten; der finale Live-Callback erhält den tatsächlichen Zustand.
- `KeyboardInterrupt`/`SystemExit` werden als Scanner-Abbruch dokumentiert und unverändert weitergeworfen. Ein sekundärer Fehler des abschließenden Callbacks ersetzt die ursprüngliche Unterbrechung nicht.
- Start-/Annahmebelege bleiben ausdrücklich unvollständig. Ein harter Prozessabbruch lässt einen unvollendeten Beleg zurück; es wird weder ein abgeschlossener Client-Job noch dessen unbekannter Abschlusszeitpunkt erfunden. Ein Stop nach Job-Annahme nennt ausdrücklich, dass der Client-Job weiterlaufen kann.
- DB-Fehler erzeugen einen synchron auf Datenträger geschriebenen Ersatzbeleg in `DATA_DIR/client_updates_fallback.log` und eine Fehlermeldung. Die Datei enthält ausschließlich dieselben Job-Metadaten wie die vorhandene Chronik, keine HTTP-Header, Tokens oder Zugangsdaten. `*.log` wird bereits von `.gitignore:36` ausgeschlossen. Auch Fehler dieses optionalen Loggings ersetzen keine bestehende Abbruchursache.
- Keine neue Tabelle, Schemamigration, Frischemetrik, Scheduler-/Lauf-Lock-Änderung oder automatische Wiederaufnahme.

Der vorhandene Latest-Consumer `db.letzte_client_updates_je_quelle` wurde direkt im Statuspoll geprüft: Während des aktiven Jobs liefert er `laeuft` mit der angenommenen ID. Die Chronik wird nicht mit einem vorgezogenen `fertig`-Eintrag versehen. Admin und Dialog verwenden weiterhin dieselben Statuswerte und dieselbe Datenstruktur.

## Regressionen und Nachweise

Neue Datei `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/tests/test_stufe0_abschluss.py`: neun isolierte Fälle für Unterbrechung, unerwartete Ausnahme mit Teilergebnissen, dauerhafte Annahme, frühen/späten Stop, DB-Fallback, Start-/Terminalbelege, SystemExit und Erhalt der ursprünglichen Unterbrechung bei fehlerhaftem Finalcallback.

```powershell
python -m pytest tests/test_stufe0_abschluss.py tests/test_client_updates.py tests/test_gesamt_review_hub_fixes.py -q -p no:cacheprovider
git diff --check -- src/mqlkiscanner/client_updates.py tests/test_stufe0_abschluss.py
git check-ignore -v data/client_updates_fallback.log
```

Ergebnis des letzten eigenen Laufs: **50 passed in 6.43s**, Exitcode **0**. Aktuelle Ausgabe und Befehl: `fix_stufe0_after.txt`. Der finale gemeinsame Consumer-Regressionslauf wird vom Hauptprüfer koordiniert; keine weitere volle Suite dieses Teilauftrags gestartet.

Alle Tests nutzen temporäre Datenbanken und Fake-Clients. Produktive Quellen wurden nicht aktualisiert. Gleichzeitige unabhängige Quellen und die vorhandenen GUI-/Agenten-/Lock-Verträge bleiben erhalten.

Grenzen: Ein vom Betriebssystem hart beendeter Prozess kann keinen späteren Abschluss schreiben; die bereits persistierten Start-/Annahmebelege bleiben deshalb offen. Falls zugleich SQLite und der lokale Datenträger für das Fallback unbeschreibbar sind, kann kein dauerhafter Beleg garantiert werden; der Fehler wird dann ausdrücklich geloggt und kein Client-Erfolg erfunden.
