# MasterHong #504191: belegte Vantage-Kontrakte

Stand 10.10.2026. Quelle für Kontraktgröße und native Gewinnwährung: `vantage_masterhong_kontrakte_2026-10-10.json`, portables Vantage-Terminal mit bestätigtem Datenverzeichnis und Verbindung. Alle neun Einträge gelten ausschließlich für Vantage.

| Symbol | Belegte Einheiten je Lot | Native Gewinnwährung | Szenario-Bewegung |
|---|---:|---|---:|
| BTCETH | 1 | ETH | 10 % des offenen Entry-Referenzpreises |
| BTCJPY | 1 | JPY | 10 % des offenen Entry-Referenzpreises |
| CRVUSD | 1.000 | USD | 10 % des offenen Entry-Referenzpreises |
| DOGUSD | 10.000 | USD | 10 % des offenen Entry-Referenzpreises |
| HBARUSD | 10.000 | USD | 10 % des offenen Entry-Referenzpreises |
| HK50 | 1 | HKD | 2.000 Indexpunkte |
| TRUMPUSD | 100 | USD | 10 % des offenen Entry-Referenzpreises |
| UNIUSD | 100 | USD | 10 % des offenen Entry-Referenzpreises |
| XAUUSD247 | 1 | USD | 50 USD |

**Die Szenario-Bewegungen sind Annahmen, keine Brokerspezifikationen.** Die sieben Kryptowährungspaare verwenden `stress_move_pct=10`. Pro Ereigniszeitpunkt berechnet die Exposure-Engine den volumengewichteten Entry der gerade offenen Positionen dieses Symbols im jeweiligen Signal, über Long und Short gewichtet mit positivem Bruttovolumen. Davon werden 10 % als Bewegung in nativen Preiseinheiten verwendet. Die bestehende Nettopositionsrechnung bleibt erhalten; gleich große Long-/Short-Positionen ergeben einen Netto-Schock von null. Das Szenario ist keine vollständige Bewertung von Hedge-, Spread- oder Liquidationsrisiken.

Die Lösung gilt unabhängig von Signal-ID oder Exportherkunft für alle Signale mit passendem Broker und Symbol. Es gibt keinen MasterHong-Median oder fremden Signalpreis in der Berechnung. Später eröffnete Positionen können frühere Referenzpreise nicht verändern. Der Referenzpreis wird am Schock-Peak zusammen mit Prozentwert und absoluter Bewegung ausgegeben; Anzeige und Rechenwert stammen aus demselben Snapshot. Ein fehlender oder ungültiger Entry erzeugt einen klaren Fehler, keinen Null-Schock. Bestehende absolute `stress_move`-Spezifikationen und explizite absolute Overrides bleiben unverändert. HK50 und Gold behalten die vorhandene Szenariokonvention. Szenarien sind editierbar und behaupten keine Eintrittswahrscheinlichkeit.

XAUUSD247 ist ein eigener 24/7-Kontrakt mit **1 Einheit je Lot**, kein Alias auf XAUUSD mit 100. BTCETH bleibt ETH-quotiert; fehlende historische ETH/USD-Umrechnung wird nicht durch USD oder eine angenommene Umrechnung ersetzt. BTCJPY bleibt JPY-quotiert; HK50 bleibt HKD-quotiert.

Die Ergänzung behebt fehlende Kontraktspezifikationen. Sie bewertet keine Ampel neu und bestätigt weder Datenqualität noch Zeitbasis oder zuverlässige Equity-Messung für MasterHong. Der bisherige Datenqualitätsvorbehalt bleibt bestehen.

Regression: neun tatsächliche Spec-Einträge gegen den Live-Beleg geprüft, native Faktoren/Quoten und Ausschluss anderer Broker, XAUUSD247-Faktor 1 gegen XAUUSD-Faktor 100. `tests/test_exposure_percent_scenarios.py` prüft zusätzlich andere Signal-IDs und Entry-Preise, Long/Short, Volumengewichtung, Hedge, fehlende Umrechnung, ungültige Entries, expliziten Override und Ausschluss späterer Entries aus früheren Peaks. Keine Scoring-Schranke geändert.
