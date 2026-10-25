# Pelican: Rohtrades auch ohne aktuelle Renditebasis

## Bestätigter Fehler und Korrektur

Der erste reale Updatejob `u-34af0ed5-fe6d-4428-8978-727905a2da46`
endete am 18.10.2026 um 19:16 MESZ mit 187 erneuerten, einem bereits frischen
und zwölf fehlgeschlagenen Tradebeständen. Fehlender aktueller
`Profitability.Inception.RealisedReturn` blockierte den Rohtradeabruf.
Die Statistik ist nur für die rückgerechnete Closing-DD-Kapitalbasis nötig.

In `PelicanTrading/src/main/java/de/pelicanmonitor/api/PelicanClient.java`
löscht `ladeStatsFuerTradeBasis` nun zuerst die alte Renditebasis und übernimmt
nur einen neuen endlichen Wert. Eine gültige Statistikantwort ohne diesen
Wert erlaubt den unabhängigen Tradeabruf. HTTP- oder Schemafehler bleiben
Fehler. `berechneTradeDd` entfernt bei unbekanntem Ergebnis auch den alten
Berechnungszeitpunkt. Die bestehende DD-Formel wurde nicht geändert.

Der neue Regressionstest lädt eine öffentliche synthetische Tradefixture über
einen lokalen HTTP-Server und persistiert sie mit dem echten SignalStore;
der Closing-DD bleibt ohne aktuelle Renditebasis null. Zusätzlich geprüft:
fehlender Wert, null, NaN, Infinity und boolescher Wert ersetzen keinen Beleg;
ein gültiger aktueller Wert wird übernommen.

## Aktivierung und tatsächlicher Wiederholungslauf

181 aktuelle Maven-Testfälle in 27 Testklassen, keine Fehler oder Skips.
Ein älterer, separat ausgeführter Live-Login-Report im Surefire-Verzeichnis
gehört nicht zu diesem Lauf. Der Build-/Quellhashbeleg enthält ausschließlich
die aktuellen Testergebnisse.

Der nachweislich inaktive Prozess 65584 wurde über CloseMainWindow normal
beendet; sein Ende und der freie Port wurden abgewartet. Danach vollständiges
privates Offlinebackup: 7.144 Dateien, 63.156.280 Bytes, Integritätsprüfung
aller drei SQLite-Datenbanken erfolgreich. Prozess 1520324 verwendet dieselben
Startargumente und Einstellungen mit den neu gebauten Klassen, Port 8090.

Wiederholung `u-87984d97-7ff7-4527-976e-2d5752e05f71`:
19:29:47 bis 19:34:58 MESZ, 200 ausgewählte Provider, **199 aktualisiert,
einer frisch, null Fehler, kein Abbruch**. Der gültige 72-Stunden-Katalogcache
wurde wiederverwendet; das ist kein zweiter Vollkatalogdownload. Die Auswahl
bleibt Top 200 nach Abonnenten, nicht die ganze ursprüngliche Plattform.

Alle 199 neuen CSV-/Metadatenpaare sind nach Writer-Ende einzeln auf SHA und
Zeilenzahl geprüft. Alle zwölf vorher gescheiterten Provider besitzen eine
neue geprüfte Generation und einen erfolgreich abrufbaren REST-Tradeexport.
Ihre aktuelle Renditebasis und ihr Closing-DD sind leer, nicht null Prozent.
USD-Normalisierung findet weiterhin im bestehenden Quellenexport statt.
Die vollständige Lebenszeithistorie und ein eigener H1-DD sind damit nicht
belegt; diese Prüfungen erfolgen im Scanner separat.

## Nachweise

- `root_pelican_build_backup.json`: Tests, Build/Quellhashes, Backups.
- `root_pelican_restart_update.json`: neuer Prozess und tatsächlicher Jobstart.
- `root_pelican_live_acceptance.json`: Abschlussstatus, 199 Hash-/Countprüfungen,
  zwölf reparierte REST-Exporte und korrekt unbekannte Closing-DD-Werte.
- `sources_pelican_live_errors.json` und `sources_pelican_partial_checkpoint.json`:
  ursprünglicher Teilerfolg und Fehler bleiben nachvollziehbar.

Keine Zugangsdaten, Rohtrades oder Datenbanken sind Reviewanhänge.
