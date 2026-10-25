# Robo: native Geld-/Volumeneinheiten sind unbelegt

Stand 18.10.2026. Dies ist ein neuer, bestaetigter Datenflussbefund. Fruehere
Tests mit synthetischen Lots/US-Dollar-Werten belegen keine richtige
Einheitennormalisierung der produktiven MT4-/MT5-Historien.

## Nachweise und Grenzen

`sources_robo_mt5_fx_factor_crosscheck.json` prueft 15.180 einfache,
gleichvolumige IN/OUT-Paare aus 20 MT5-Historien auf USD-Quote-FX-Symbolen.
Verglichen wird roher Profit gegen Preisdifferenz mal gespeichertes Volumen
mal 100.000. Die Provider-Mediane sind meist 0,01 oder 0,0001, teils abweichend.
Bei 176.279 MT4-Orders aus 95 Historien ergeben sich Gruppen um 10 und 0,1
sowie abweichende Werte (`sources_robo_mt4_fx_factor_crosscheck.json`).
Damit ist die universelle REST-Skalierung x10 widerlegt. Diese Quotienten
loesen aber die gleichzeitige Mehrdeutigkeit von Kontowaehrung, Centgeld,
Volumeneinheit und Kontraktbasis nicht auf. Sie werden ausdruecklich nicht
als automatische Faktoren oder Profilfreigaben verwendet.

Vier neue lesende Requests ueber den vorhandenen Client liefern den
Schema-Beleg `sources_robo_native_unit_schema_probe.json`: Ratingwerte
unterscheiden `profit_money`, `profit_usd` und `balance_usd`; keine native
Kontowaehrung oder Volumeneinheit wird belegt. Auch drei MT5-History-Antworten
der unterschiedlichen Fallgruppen liefern keinen solchen Profilnachweis.
Cookies, rohe Antworten und Datenbanken sind keine Reviewanhaenge.

Offizielle allgemeine Dokumentation erklaert [Centkonten und USD/EUR](https://roboforex.com/blog/education/what-are-forex-cent-accounts-needed-for/)
und unterscheidet [Centlots und Standardlots](https://robogate.freshdesk.com/en/support/solutions/articles/501000162290-how-much-commission-do-i-get-from-procent-accounts-).
Die [allgemeine EURUSD-Kontraktspezifikation](https://roboforex.com/forex-trading/trading/specifications/card/pro-cent/EURUSD/)
liefert ebenfalls kein Mapping eines konkreten History-API-Feldes fuer einen
konkreten Provider. Diese Seiten rechtfertigen keinen neuen Pauschalfaktor.

## Getesteter Vertrag

- MT4-/MT5-Historien werden weiterhin mit vollstaendiger Pagination geladen.
  Native Zahlen, Identitaeten und Preise bleiben erhalten.
- Katalog und Metrics unterscheiden explizite USD-Ratingwerte von der
  unbekannten Tradebasis. `currencyCode`, `Currency` und Trade-`Balance`
  sind `null`; `RatingBalanceUsd` und `ratingCurrencyCode` sind getrennt.
- `trades.csv` ist mit HTTP 404 und `code=unverified_trade_units` gesperrt;
  der Katalog gibt dafuer keinen positiven CSV-Link aus.
- Native JSON-Historien enthalten `rawDeals`, `storedVolume`, Preise und
  finanzielle Werte mit `rawMoneyCurrency=unknown` sowie Einheitenhinweis.
  Das interne gespeicherte Volumen wird nicht als bestaetigte Lots angeboten.
- `TradeHistoryAvailable=true` bedeutet verifizierte native Daten.
  `RawHistoryPaginationComplete` belegt die Pagination separat;
  `TradeHistoryComplete=false` bewahrt die Einheiten-/Qualitaetsgrenze.
- Closing-DD bleibt unbekannt, auch bei einem alten oder kuenstlich gesetzten
  DD-Snapshot und trotz frischer Ratingabfrage. Provenienzmodell 4.
- Die GUI zeigt einen dauerhaften Quellenhinweis; Tradevolumen hat eine
  unbelegte Einheit, PnL ist nativ. Keine erfundene USD-Trade-Rendite.
  Auch LLM-Tradefelder und der manuelle Rohtradeexport nennen diese Grenze.
- RStocks bleibt gesondert `rst` und `unsupported_trade_platform`; eine
  unbewiesene MT4-/MT5-Ersatzklassifikation gibt es nicht.

195 Maven-Tests sind gruen. Quelle, Tests und Artefakthash stehen unter
`sources_robo_units_build_receipt.json`. Der Build entstand in einer eigenen
Stage ohne laufende Artefakte zu ueberschreiben. Die Abnahme prueft zusaetzlich
den tatsaechlich neu gestarteten Prozess und die nativen Generations-/REST-
Paare; der Buildbeleg allein ist keine produktive Aktivierung.

## Tatsaechlicher Lauf und weitere Abnahme

Der erste echte Job `u-e55d8f83-aa56-415a-8aea-e06342aaef32` endete regulär am
18.10.2026 um 20:34:17 MESZ mit 200 Versuchen: 4 neue, 176 aktualisierte,
20 fehlerhafte Historien. 17 Fehler betreffen unzulaessige alte Duplicate-
Caches, 3 RStocks. `sources_robo_initial_failures_final.json` bleibt als
unveraenderter Abschlussbeleg erhalten. Die 17 MT-Historien werden nach
normalem Idle-Exit, Hashvergleich und privatem Offlinebackup gezielt erneut
vollstaendig geladen; alte CSV/Meta-Bytes werden quarantiniert, keine alten
Zeilen als frische Vollhistorie dedupliziert oder hinzugemischt.

Der aktuelle Stand steht in `sources_robo_repair_progress.json`, der spaetere
native/REST-Abschluss in `sources_robo_live_acceptance.json`. Ein erfolgreicher
Rohdatenabruf hebt die unbekannte Einheitsbasis nicht auf und erlaubt keine
positive Scanner-Forensik. Eine Freigabe erfordert kuenftig einen echten,
providergebundenen Waehrungs-/Volumen-/Kontraktnachweis.

Der lesende Abnahmepruefer liegt nachvollziehbar unter
`sources_readonly/verify_robo_current.py` und wird vom Scanner-Arbeitsverzeichnis
mit der vorhandenen Registry ausgefuehrt. Er benoetigt die privaten nativen
Daten und den Reparatur-Endbeleg; diese gehoeren nicht ins Review. Er startet
keine Quellenupdates und keine Scanner-/Terminal-/LLM-Laeufe. Geprueft werden
die genaue Quelleninstanz, alle 197 unterstuetzten nativen Generationen,
jede per JSON gelieferte finanzielle Zeile, die verweigerte CSV sowie die
drei ehrlich nicht unterstuetzten RStocks-Provider. Auch leere Reportlisten
und die Sperre direkter historischer PDF-Pfade werden geprueft.

## Fortsetzung und reale Abnahme am 19.10.2026

Nach ausdruecklicher Nutzeraufforderung wurden zuerst die sechs protokollierten
Reparaturen und die nach der Pause unabhaengig ausgelaufene CLI fuer 37232470
anhand aktueller CSV-/Meta-Hashes, Fetch-IDs und Quarantaenepaaren erneut
geprueft. Danach wurden ausschliesslich die zehn noch fehlenden IDs seriell
vollstaendig erneuert. Ergebnis: **17 von 17 repariert, kein Providerfehler,
406.475 native Zeilen in diesen erneuerten Historien**. Alle 17 archivierten
Original-CSVs und Original-Metas stimmen mit dem Offlinebackup vor der
Reparatur ueberein. 454 nicht betroffene native Dateien blieben unveraendert.

Die unveraenderte Stage mit 195 bestandenen Tests, 109 Klassen und dem bereits
belegten JAR-Hash `47fa66fc692b3d92f49ffeb1c194ffd31f1607e52ac9589ab075c7b44ad6a0e1`
ist als normale JavaFX-App aktiv. Die aktuelle sichtbare Instanz hat PID
**114668**, Port **8091** und die unveraenderte Service-/Instanzidentitaet.
Der erste verdeckte Start wurde ausschliesslich nach nachgewiesener
Worker-Abwesenheit ueber den vorhandenen JavaFX-Exit regulaer beendet;
kein Writer wurde unterbrochen und kein laufendes Klassen-/JAR-Artefakt
ueberschrieben. Ein eigener Pfadseparatorfehler im Nachpruefer hatte zuvor
die Aktivierung voruebergehend angehalten; nach Korrektur wurden die echten
nicht betroffenen Bytes erneut geprueft, ohne weitere Downloads zu starten.

Die aktuelle Instanz wurde vollstaendig lesend abgenommen: **200 lokale
Kataloganbieter**, davon **197 native Historien** (137 MT4, 60 MT5) mit
**1.503.461 nativen Zeilen**. Jede finanzielle JSON-Zeile wurde gegen die
native Generation geprueft; keine Abnahmefehler. Drei RStocks-Provider
bleiben am vorhandenen Members-MT-Endpunkt ehrlich nicht unterstuetzt.
Die 11 zusaetzlichen echten HTTP-Sperrpruefungen bestaetigen 400/404/405,
unter anderem falsche Plattformen, unbelegte Einheiten und einen wirklich
vorhandenen, zum Anbieter passenden historischen PDF-Pfad. Kein gueltiger
Update-POST wurde gestartet; der Backendzustand blieb `idle` und alle
475 nativen Dateien blieben waehrend dieser Zugriffe unveraendert.

Die echte GUI zeigt den dauerhaften Einheitenhinweis und die historische
Berichtsansicht. Ihr bestehender Filter zeigt 23 von 200 Anbietern; der
Filter wurde nicht geaendert. Die 91 historischen MD/PDF-Paare plus ihr
Index (183 Dateien) sind unveraendert erhalten. Es wurden keine neuen
Quellenberichte, Scannerlaeufe, Modellaufrufe oder Scanner-DB-/Settings-
Aenderungen durch diesen Robo-Abschluss ausgefuehrt.

**Finanzielle Grenze unveraendert:** 197 verifizierte native Historien sind
kein Beleg fuer USD-Tradebetraege oder Standardlots. Alle 197 unterstuetzten
Scanner-CSVs bleiben mit `404 unverified_trade_units` gesperrt, Closing-DD
unbekannt und Rating-USD getrennt. Alte Scanner-Workflowkoepfe muessen
separat strikt erneuert werden; der Quellen-Exportguard schreibt sie nicht um.

Endbelege: `sources_robo_activation_final_20261019.json`,
`sources_robo_live_acceptance.json`,
`sources_robo_guard_acceptance_20261019.json` und
`sources_robo_visible_runtime_20261019.json`. Private Prozess-, GUI-,
Quarantaene- und Generationdetails liegen unter
`data/runs/liveabschluss_20261019/robo/`; sie gehoeren nicht in GitHub.
