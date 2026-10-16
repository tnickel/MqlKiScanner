# Unabhängiger Peercheck: Root-Scanneränderungen

16.10.2026. Reiner Leseauftrag für Scanner-Produktdateien. Geprüft:
`ingest.py`, `pipeline.py`, `fix_signale.py`, `analysis_version.py`,
`app_pages/scan.py` und `tests/test_handover_*.py`. Produktcode, Settings,
Produktdaten und Datenbanken wurden von diesem Agenten nicht verändert.

## Zwei bestätigte Umgehungen im ersten Zwischenstand

1. `ingest.metrics_zu_stats` erklärte allein wegen eines frei vergebenen
   Quellenkürzels `robo` jeden Geldwert für USD. Repro: version=mql5,
   Currency=None/USC/EUR, Balance=1100, InitialDeposit=1000, Alias=robo.
   Ergebnis: account_currency=USD, balance_usd=1100; Währungssperre erlaubte
   die USD-Forensik. Das war keine Umrechnung, sondern eine Umetikettierung.
2. `pipeline.require_usd_account` ließ fehlende Currency für eine Kürzel-
   Whitelist zu. Ein nativer MQL-Spiegel mit Alias pelican/vantage/vant/zulu
   und version=mql5 konnte deshalb Currency=None an der Sperre vorbeiführen.
   Explicit USC/EUR blieb in diesem zweiten Fall bereits gesperrt.

Beide Fälle wurden mit den tatsächlichen reinen Funktionen des Zwischenstands
unabhängig reproduziert und Root gemeldet. AST-Extraktion vermied Imports mit
DB-/Settings-/Netzseiteneffekten. Der Kontrollalias mql_mirror blockierte
fehlende Currency, USC und EUR korrekt; belegtes USD blieb erlaubt.

## Korrektur durch Root und unabhängige Nachprobe

Root entfernte die `robo`-Aliasübersteuerung. Der aktuelle Robo-Quellserver
liefert Currency=USD selbst; sein Kürzel muss keine fehlende Einheit ersetzen.
Der Guard erkennt native MQL zusätzlich anhand MT4/MT5 bzw. mql4/mql5-Version
und der bestehenden direkten mql5-Herkunft. `ScanResult.quelle_version` wird
bereits aus dem Kandidaten übernommen. Eine Kürzel-Whitelist ist dafür nicht
mehr nötig.

Die Nachprobe liest die aktuellen Funktionen direkt aus den Produktdateien,
kompiliert nur die AST-Knoten der reinen Funktionen samt numerischen Helpers
und führt sie mit synthetischen Objekten aus. Keine App, DB oder API wird
gestartet. Ergebnis:

- **60 native Fälle:** mql4/mql5 × sechs Aliase
  (mql_mirror, robo, pelican, vantage, vant, zulu) × fünf Währungen
  (fehlend, unknown, USC, EUR, USD). Sämtliche unbekannten oder fremden Einheiten
  sind gesperrt; nur USD ist erlaubt. balance_usd bleibt in allen anderen
  Fällen null.
- **Vier positive Vertragskontrollen:** Pelican mit OriginalCurrency EUR,
  Vantage mit OriginalCurrency USC und Zulu mit OriginalCurrency EUR bleiben
  bei belegter jeweiliger Quellversion als konvertierter USD-Export zugelassen.
  Robo mql5 mit ausdrücklich geliefertem Currency USD bleibt ebenfalls erlaubt.
- **0 fehlgeschlagene Assertions** in der unabhängigen Nachprobe.

Maschinenlesbare Fälle und genaue Quellhashes:
`root_currency_peer_reprobe.json` im selben Auditordner.

Geprüfte SHA-256:

```text
ingest.py   5d5202f04ae79ff1b8fbc93a49b36e4fae8bde8c041e24846248204f33f813d7
pipeline.py 949c0bbef6072aaa134a1fcb3b0e93038cb8125667ee3f497904faf3b450c8b6
```

Python für die Nachprobe:
`C:/Users/tnickel/AppData/Local/Programs/Python/Python312/python.exe`.
Diese 64 Funktionsfälle sind keine zusätzliche vollständige Pytest-Suite;
deren endgültigen isolierten Lauf und Zahlen führt Root.

## Weitere geprüfte Kontrollfluss- und Vertragsstellen

`pipeline._analyze_candidate_once` übergibt die Quellversion an den Adapter,
übernimmt account_currency ohne pauschalen Source-USD-Fallback und ruft den
Guard vor `fx_rates.status()` und `analyze_export` auf. Native Geldfelder werden
als account_money separat persistiert. `FORENSICS_VERSION=19` macht die frühere
pauschale Source-USD-Auswertung zur veralteten Forensik.

Pelicans `Currency` bezeichnet das Originalkonto, während ein erfolgreicher
REST-CSV-Export bereits nach USD normalisiert ist. Deshalb ist eine pauschale
Sperre allein wegen OriginalCurrency EUR in diesem spezifischen Quellvertrag
falsch. Die Quellversion pelican erhält hier zu Recht den Konversionsvertrag;
ein freies Kürzel pelican bei version=mql5 erhält ihn nicht.

`studie_anwenden` ruft denselben Guard vor Übernahme von Studienwerten auf.
Die bestehende Einzelstudie ruft ihn vor dem Terminalstart auf; der Session-
Cachekey enthält Währung und source_kind. Die Korrektur am gemeinsamen Guard
schließt damit auch die nachgewiesenen Aliasvarianten dieser Consumer.

`fix_signale.waehle_fuer_export` löst Abonnenten-Gleichstände deterministisch
nach numerischer ID auf. Die Kandidatenvorfilter normalisieren ungültige
Abonnentenzahlen zu unbekannt, bewahren echte 0 und die explizite Einstellung
Mindestabo 0. `scan.py` übernimmt fractional Mindestwochen als float in
Anzeige und run_settings. Für diese eng geprüften Änderungen ergab sich kein
weiterer konkreter Fehler.

Die erweiterten `test_handover_source_currency.py`-Regressionsfälle enthalten
nun auch die sechs relevanten freien Aliase; die Robo-Kontrolle liefert die
real vorhandene Currency USD ausdrücklich. Diese Prüfung behauptet weder
Live-Plattformfrische noch einen abgeschlossenen Root-Gesamttest. Nach dem
aktuell geprüften Korrekturstand bleiben die beiden belegten Umgehungen in
der unabhängigen Nachprobe geschlossen.
