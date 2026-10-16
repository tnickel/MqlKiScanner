# Unabhängige Prüfung der historischen Pelican-FX-Exporte, 10.10.2026

Der neue REST-Finanzpfad ist bei der Codeprüfung sachlich korrekt. `HistoricalFxRates.rateFor` verwendet den unveränderten Quell-Kalendertag des Tradeabschlusses. `floorEntry` erlaubt ausschließlich diesen oder frühere Kurstage, maximal zehn **Kalendertage** einschließlich der Grenze. Beide Währungskomponenten eines Kreuzkurses stammen aus derselben EZB-Zeile. USD verwendet Faktor 1, USC Faktor 0,01 ohne Netzwerk oder weitere Kontokonvertierung. Die Zeilenwährung gewinnt; nur bei leerer Zeilenwährung gilt die Providerwährung. Fehlende geeignete FX-Belege blockieren den ganzen CSV-Export statt teilweise umzurechnen.

`RestApiServer` skaliert ausschließlich den gelieferten `RealisedProfit`, einmalig und bei Fremdwährung auf Cent gerundet. Instrument, Menge und Ein-/Ausstiegspreise bleiben unverändert. Die Quelle liefert hier keine separaten Gebühren oder Cashflows; Commission bleibt entsprechend der bestehenden Adapterdarstellung 0, Swap leer. Daraus folgt **kein Nachweis**, dass Gebühren finanziell null waren oder die Historie Einzahlungen/Entnahmen enthielte. Balance und Equity verwenden weiterhin separat den gecachten Snapshotkurs; `CurrencyRateScope=snapshot_metrics_only` und historische `UsdNormalization` legen die verschiedenen Grundlagen offen.

Geprüfte Regressionen: historischer EUR-/HKD-Kurs, wechselnde beliebige EZB-Währungen, Wochenend-Rückgriff, keine Vermischung verschiedener Kurstage, inklusive 10-/exklusive 11-Tage-Grenze, USD/USC ohne Fetcher, ungültige Kurse und Persistenz. Der zuständige Implementierungsagent meldet den vollständigen aktuellen Maven-Build mit 112 Tests ohne Fehler. Unabhängige echte Zeilenarithmetik wird zusätzlich in `pelican_historische_exporte_finanzabnahme_2026-10-10.json` dokumentiert.

## Unveränderlicher Offline-Exportsatz

`tmp/pelican_historical_fx_exports_goal_20261010/` enthält genau die 636 IDs aus `tmp/pelican_scanner_ids_goal_20261010.json`. Alle ursprünglichen 163 Recovery-Ziele sind enthalten. 1.275 Original-Quelldateien wurden als Eingabesnapshot kopiert: vollständiger Providerkatalog, Snapshot-FX, EZB-Historie und je ID Roh-CSV plus SHA-/Count-Meta. Der Exporthelper injiziert für **beide** FX-Fetcher ausschließlich IOException; verwendet werden nur diese Dateien und der normale REST-Handler auf einem temporären lokalen Port. Kein Scanner-DB-Zugriff, kein MT5, kein externer HTTP-Zugriff.

Je ID wurden die exakten REST-Antwortbytes geschrieben; erst danach erfolgte der atomare Acceptance-Marker. Das abschließende `manifest.json` enthält alle Antwort-SHAs, Status und Zeitbelege. Eingabe- und Ausgabe-SHAs sowie sämtliche 31.483 FX-Datumsbelege wurden unabhängig geprüft. EZB-Cache-SHA: `4fc5af11a6144a628181d6d217b49f3e7fa0b886c7a99cbd6aeb3de77d219bc3`. Manifest-SHA: `e88a86749f3422360e5e06787d20fd061058fec4645642a340f89399e20db7ae`.

Ergebnis: 628 CSV200/Metrics200, vier CSV404/Metrics200 wegen positiver Aggregate bei leerer Historie (2000036, 2001115, 2001116, 2097770), vier CSV404/Metrics404 wegen inzwischen fehlender Katalogeinträge (2059824, 2063644, 2074606, 2084818). Die drei früheren Recovery-Abbrüche ohne belegtes Inceptiondatum (2064608, 2053531, 2000436) bleiben ungelöst: der reguläre Handler liefert ihre vorhandenen header-only Caches bei Aggregaten 0 als CSV200; weder der Status noch die neue `CompletenessNote` behaupten eine vollständige Lebenszeithistorie. HTTP200 ist daher kein Nachweis tatsächlich vorhandener Trades.

Beispiel 2000016: 2.632 gespeicherte Trades, 500 unterschiedliche Currency-/Abschlussdatum-Belege; EUR-Faktor am 10.01.2023 ist 1,0723, am 04.11.2025 1,1491. Der Snapshot-Balancekurs bleibt separat auf dem Stand 29.09.2026. `TradesStored` und `CompletenessNote` nennen abweichende Plattform-Zählgrößen ausdrücklich ohne automatische Trunkierungsbehauptung oder Risiko-Malus.

## Vier nur noch archivierte Anbieter

Die IDs 2059824, 2063644, 2074606 und 2084818 fehlen sowohl im aktuellen vollständigen Source-Katalog als auch in `tmp/pelican_exports_goal_20261010/before/providers_before_fresh_stats.csv` vom 08.10.2026. Weitere Provider-CSV-/JSON-Backups wurden in den durchsuchten Source-/Recovery-/Waste-Pfaden nicht gefunden. Das beweist keine globale Nichtexistenz älterer Metadaten.

Die originalen Source-Rohdateien plus Meta belegen dagegen 937 / 5.541 / 1.682 / 753 Trades; SHA und Count stimmen. Jede Zeile enthält Trade-ID, Open-/Close-Zeit und die native Währung USD. Ein allgemeiner **CSV-only** Archivpfad könnte daraus ohne erfundene Providerwerte exportieren; die aktuellen finalen Exporte verwenden bewusst unveränderte Handlersemantik und melden 404. Provider-Metrics dürfen aus diesen Tradezeilen nicht erfunden werden. Alle Einzelbelege stehen in der begleitenden JSON-Datei.

## READY — endgültige Abnahme dieses Exportsatzes

Der zweite unabhängige Prüfer hat **alle 310.330 Trades der 628 erfolgreichen
CSVs** gegen native Sourcezeilen und die EZB-Tabelle nachgerechnet: null
Abweichungen bei PnL, Preisen, Lots oder Symbolen. Vollständiger Beleg:
`pelican_historische_exporte_finanzabnahme_2026-10-10.json`.

Zusätzlich wurden alle 8.913 Zeilen der vier Archiv-CSVs geprüft: eindeutige
nichtleere Trade-ID, explizites Buy/Sell, Symbol vorhanden, endliche positive
Menge und Preise, endlicher PnL, gültige Zeitstempel mit Close >= Open sowie
explizite USD-Währung. Keine Befunde. Beleg:
`pelican_archiv_trades_schema_2026-10-10.json`.

Codeempfehlung an den Implementierungsagenten: Bei unbekannter Provider-ID nur
für die gültige Pelican-Route auf SHA-/Count-verifizierte, nichtleere
Sourcehistorien zurückfallen. Jede Zeile vor jeder Ausgabe streng validieren;
fehlende Zeilenwährung ist ein Fehler, da keine Providerfallbackwährung besteht.
Für gültige Zeilen gilt derselbe normale historische FX-Pfad. Keine künstliche
Providerinstanz, keine erfundenen Metrics und kein Überspringen ungültiger
Zeilen. Metrics und Katalog bleiben für archivierte IDs unbekannt. Dieser
allgemeine Adapterfix und seine vier gezielten künftigen Exporte sind **nicht**
Teil des hier unveränderlich abgenommenen 636er Manifests.
