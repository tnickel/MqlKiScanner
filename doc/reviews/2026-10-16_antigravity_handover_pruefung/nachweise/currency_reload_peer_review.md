# Unabhängige Gegenprüfung CurrencyConsumer

Status: konkrete Reload-Fail-open-Kante zunächst unabhängig reproduziert, nach Root-Fix geschlossen. Keine Produktdateien durch diese Nachprüfung geändert; ausschließlich Auditprobe/-bericht gespeichert.

Geprüfte aktuelle SHA256:

- `SignalKiScanner/src/mqlkiscanner/katalog.py`: `d7f40b99451436d590ed32309c4047ab3ac0afd07e007981cba5390872c6ac93`
- `SignalKiScanner/src/mqlkiscanner/ingest.py`: `5d5202f04ae79ff1b8fbc93a49b36e4fae8bde8c041e24846248204f33f813d7`

`katalog_resultate` übernimmt die explizite Währung vor der Studie; `_metrics_aus_artefakt` prüft tatsächliche Metricsbytes gegen SHA und Identität/Version und gibt die gebundene Version an den Adapter weiter. `workflow_stats_bulk` ergänzt nur bei übereinstimmendem registrierten UND tatsächlichem CSV-SHA beider Tradepfade. NichtUSD/None setzt frühere initial_deposit_usd, balance_usd und kapitalbasis_virtual_usd auf None. Diese Änderungen haben in der gezielten statischen Gegenprüfung keinen neuen Fail-open-Pfad ergeben.

Bestätigte Reload-Ursache: `lade_signal_daten` behielt bei `hole_metrics`-DownloaderError das alte `account_currency='USD'`, während `hole_trades` anschließend eine geänderte neue native CSV liefern konnte. Vorher-Beleg `currency_reload_peer_probe.json`: changed=true, currency_after_failed_metrics=USD, stale_usd_proof_retained=true. Das war keine bloße Vermutung über hypothetische Daten: die tatsächliche Funktion wurde mit inertem DB-/Transportstub ausgeführt.

Root setzt nun vor dem Metricsabruf die Einheit aus dem gebundenen Exportvertrag zurück. Nachprobe `currency_reload_peer_probe_after.json`: changed=true, currency_after_failed_metrics=null, stale_usd_proof_retained=false. Zusätzlich fünf Versionsfälle mit der tatsächlichen Adapterfunktion und tatsächlichem require_usd_account aus AST geprüft: mql4/mql5 ->None und USD-Guard blockiert; pelican/vantage/zulu ->USD und Guard lässt den explizit konvertierenden Exportvertrag bestehen. Damit wird Pelicans Originalkonto-Currency nicht fälschlich als Exportwährung interpretiert.

Die Probe liest ausschließlich Quellcode. Sie führt das originale Katalogmodul mit inertem DB/Transport aus und extrahiert reine Adapter-/Guard-Funktionen, ohne Produktkonfiguration, Datenbank, Cache oder Netz zu berühren. Regressionen der Root-Suite (`test_handover_source_currency.py`/`test_katalog.py`) sind separate Nachweise; deren106-grün-Ergebnis stammt vom Root und wurde hier nicht als eigener Volltest wiederholt. Eigene Nachprobe ist reproduzierbar über `currency_reload_peer_probe.py`.
