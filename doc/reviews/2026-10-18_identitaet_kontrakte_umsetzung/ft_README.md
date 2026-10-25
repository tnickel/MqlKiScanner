# GER40ft / UK100ft: belegtes Vantage-FT-Profil

Am 18.10.2026 um 15:35:09 UTC wurden beide **exakten** Symbole mit
`MetaTrader5.symbol_info` am konfigurierten portablen Terminal
`C:\Forex\Mt5\Vantage\terminal64.exe` auf **VantageMarkets-Live 10** gelesen.
GER40ft: Kontraktgröße 1, Gewinnwährung EUR; UK100ft: Kontraktgröße 1,
Gewinnwährung GBP. Tickgröße jeweils 0,01, Volumenminimum und -schritt 0,1.
Der vollständige zulässige Metadatensatz steht in `ft_terminal_spec.json`.
Das gemeinsame Scan-/Studienlock wurde vor dem ersten Terminalzugriff gehalten,
der vorhandene geprüfte Portable-Start und Cleanup wurden verwendet. Das zuvor
nicht laufende Terminal war nach Cleanup beendet. `account_info` wurde nur für
den Servernamen gelesen; keine Orders, Kurse oder Trades wurden abgerufen.

`scripts/reference/ft_kontrakt_beleg.py` ist der reproduzierbare Beleghelper.
Eine erneute Ausführung startet bei bestehender Freigabe das konfigurierte
Terminal; sie ist kein Offline-Test. Die archivierte erfolgreiche Liveabfrage
wurde für diese Umsetzung nur einmal durchgeführt.

Die beiden bestehenden `_VANTAGE`-Modelle verwenden jetzt den nativen Faktor 1
und die belegte EUR-/GBP-Gewinnwährung. Die vorhandene historische FX-Umrechnung
liefert zeitbezogenes USD-Risiko; fehlende FX-Belege bleiben unbekannt. Die festen
USD-Mediane 1,08/1,35 entfallen. Die parallel vorhandenen ungebundenen FT-Einträge
wurden entfernt: ohne Broker oder bei fremdem Broker gibt es keine FT-Freigabe.
Bestehende Schockszenarien bleiben 500/200 Punkte; sie sind keine Brokerspec.
Cash-Symbole und bestehende Kursproxy-Aliase bleiben eigenständig. Exakte
Vantage-FT-Schreibweisen waren bereits über die vorhandene Alias-Schleife
verfügbar; dafür war keine Änderung an `symbols.py` notwendig.

Die Freigabe gilt als **dokumentiertes Vantage-FT-Familienprofil**: aktueller
Serverbeleg plus historische Trade-/FX-Plausibilität. Der vorhandene Provider
Rohan Gupta (`vant`, externe ID 178177) trägt nur das generische Brokerlabel
`vantage`. Sein historischer Originalserver ist **unbekannt** und wurde weder
in Providerdaten noch in Metrics ergänzt. Der Livebeleg beweist nicht, dass
beliebige andere Vantage-Server dieselbe Spezifikation haben. Die vorhandene
Vantage-Familienzuordnung wurde beibehalten; andere Broker werden nicht
freigegeben. Dieser begrenzte Rückschluss ist ausdrücklich keine historische
Serverzuordnung und keine universelle Brokerspezifikation.

`ft_legacy_plausibility.py` liest nur den bestehenden SHA-geprüften Rohan-Snapshot
und die vorhandene EZB-CSV. `python doc/reviews/2026-10-18_identitaet_kontrakte_umsetzung/ft_legacy_plausibility.py`
erzeugt nur Aggregate in `ft_legacy_plausibility.json`, ohne Netz oder DB-Zugriff.
Nach täglicher FX-Normalisierung liegt der native Median bei GER40FT bei
1,000335 (9 Trades), UK100FT bei 1,002721 (13 Trades). Das unterstützt die native
Währung, ersetzt aber weder Ausführungskurse noch historische Metadaten; CSV-
Zeitzone und gegebenenfalls eingebettete Gebühren bleiben Grenzen. Keine
Cent-genaue PnL-Abstimmung wird behauptet.

Die fachliche Änderung hebt `FORENSICS_VERSION` auf 20. Alte Befunde müssen neu
geprüft werden; produktive Scans oder gespeicherte Bewertungen wurden hier nicht
ausgeführt oder umgeschrieben. Die bestehende Mindestversion 19 für einen
USD-Kontowährungsbeleg bleibt unverändert gültig. Konfiguration 50, Calmar- und
SL-Regeln sind unverändert.

Validierung: **259 bestanden**, Exit 0, 12,67 Sekunden; 11 gezielt ausgewählte
Dateien einschließlich 27 neuer FT-Fälle zu Lock, exakten Symbolen, unverändertem
Account-Datenschutz, Brokergrenzen, täglicher FX und fehlenden FX-Belegen.
`ft_tests_command.json`, `ft_tests.log`, `ft_tests.xml`, `ft_tests_exit.txt`
enthalten den vollständigen aktuellen Befehl und Laufnachweis. Keine
Produktivdaten wurden durch die Tests verwendet; die Live-Metadaten sind eine
statische Vertragsfixture. Eine spätere produktive Neubewertung ist noch offen.

Zusätzlich wurden die fünf vorhandenen betroffenen Cache-Exporte rein offline
mit dem produktiven Exposure-Modul und dessen historischer FX-Logik vor/nach
der Registry-Änderung nachgerechnet. `ft_cached_recalculation.py` öffnet die
bestehende SQLite-Datei ausdrücklich `mode=ro`, prüft CSV-/Metrics-SHA und bindet
den vorhandenen EZB-Cache an den produktiven Parser und `usd_per`; kein Refresh.
`ft_cached_recalculation.json` enthält ausschließlich freigegebene Aggregate,
Hashes, Zeitspannen und bekannte Grenzen.

| Quelle / externe ID | FT-Trades | FT-isolierter Peak-Schock vorher USD | nachher USD |
|---|---:|---:|---:|
| vant / 178177 | GER40FT 9, UK100FT 13 | 1619,06 | 1555,31 |
| vant / 1231244 | GER40FT 1 | 1080,00 | 1145,60 |
| vant / 504191 | GER40FT 1 | 540,00 | 567,15 |
| vant / 692325 | UK100FT 1 | 108,00 | 109,28 |
| vant / 762452 | UK100FT 2 | 270,00 | 260,89 |

Diese Schocks beziehen sich nur auf gleichzeitig offene FT-Positionen und die
unveränderten 500-/200-Punkte-Szenarien. Keine Kapitalbasis wurde injiziert;
Schock-Prozente sind in allen fünf Fällen unbekannt. Die Gesamtexporte von
178177/504191 bleiben wegen anderer fehlender Umrechnungen unvollständig,
1231244/692325 wegen NIKKEI225, 762452 zusätzlich wegen SOYBEAN-C gesperrt.
Damit ist keine Freigabe der gesamten Historie oder Equity-Messung verbunden.
Die alten Cachedaten wurden nicht hinsichtlich UTC/Historienvollständigkeit
erneuert oder zertifiziert. H1, Drawdown, Calmar und Ampel wurden nicht neu
gerechnet. Die produktive vollständige Neubewertung bleibt erforderlich.
