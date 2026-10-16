# DeepSeek-Nachprüfung: Wochenalter und Quellenbelege

Stand: 16.10.2026. Untersucht wurden die aktuellen Arbeitskopien der fünf Quellen,
nicht nur die im angehängten Review genannten älteren Revisionen. Scanner-Code
wurde ausschließlich gelesen. Keine Plattform-, Login- oder LLM-Aufrufe, keine
Produktdaten- oder Settingsmigration, kein Stage/Commit/Push durch diesen Agenten.

## Bewertung der Reviewaussagen

**P1-1: Die behauptete aktuelle Kommentarabweichung ist bereits behoben.**
`SignalKiScanner/src/mqlkiscanner/ingest.py`, Funktion `kandidaten`, dokumentiert
ausdrücklich: unbekanntes Alter bleibt `None`, der reguläre Wochen-Vorfilter
lehnt es ab; Fix-IDs können den Vorfilter umgehen. `pipeline.py:1523` setzt diese
Regel um. Die Ablehnung eines unbekannten Alters ist kein nachgewiesener Fehler:
Ohne Beleg lässt sich die Mindestalteranforderung nicht als erfüllt behandeln.
Die Regel wurde hier nicht gelockert. Die zusätzliche Scanner-Normalisierung
von NaN/Inf/Boolean-Werten gehört zum separaten Auftrag von Root/clients und
wird nicht als eigene Quellenleistung oder hier getesteter Scannerstand gezählt.

**Datenverbesserung 9: teilweise umgesetzt, mit expliziten Grenzen.** Es gibt
keinen gemeinsamen, unabhängig verifizierten Plattformgründungszeitpunkt für
alle fünf Quellen. Unterschiedliche Belegarten müssen kenntlich bleiben.
Vier Quellen liefern nun `weeksSource` im Katalog und `WeeksSource` in den
Kennzahlen; unbekannte Werte bleiben `null`. MQL besitzt derzeit keinen belegten
Altersproduzenten und erhält deshalb nur eine Dokumentationskorrektur.

## Herkunft vor und nach dem Nachladen von Stats

| Quelle | Beleg und Verfügbarkeit | Aktueller Vertrag |
| --- | --- | --- |
| MQL | Katalog enthält kein Altersfeld; der generische TXT-Parser könnte beliebige Schlüssel lesen, aber im aktuellen Java-Code erzeugt kein Extraktor `Weeks`/`Started`/ein Altersfeld. | Alter unbekannt; keine Ableitung aus Abonnentenhistorie, Dateizeit oder vermuteter Plattformgründung. |
| Pelican | `PelicanClient.java:230` liest `Inception` aus Stats. Discover allein muss dieses Datum nicht besitzen. | Ganze Wochen seit explizitem Datum; fehlend, Jahr-1-Sentinel und Zukunft unbekannt. Quelle `platform_inception_date`. |
| Robo | `RoboForexClient.java:161` liest `offer_initial_date` schon aus dem Katalog. Tages-/Dealstats sind kein zusätzlicher Altersbeweis. | Ganze Wochen seit Angebotsstart; fehlend, Jahr <= 1 und Zukunft unbekannt. Quelle `platform_offer_initial_date`. |
| Vantage | API-/Anzeigemonate sind kein verlässlicher exakter Altersbeleg. Stats allein ergänzen keinen solchen Beleg. Lokale datierte Aktivität kann eine Untergrenze liefern. | Ganze reale Wochen seit ältester belegter Aktivität aus Daily-PnL oder verifizierten Trades; ohne Beleg null. Quelle `local_history_lower_bound`. |
| Zulu | `overallStats.weeks` stammt aus dem Plattform-Snapshot. Ein allgemeines Profilregistrierungsdatum ersetzt dieses Feld nicht. | Endliche, nichtnegative, ganzzahlige Wochen; fehlende/ungültige Werte null, echte 0 bleibt 0. Quelle `platform_overallStats_snapshot`. |

Die vier Quellen verwenden `unknown`, wenn der zugehörige Alterswert fehlt.
Die Herkunftsangabe ist eine Beschreibung des konkreten Belegs, kein Nachweis
eines aktuellen Liveabrufs oder der Vollständigkeit der Handelsgeschichte.

## Konkrete Änderungen und unabhängige Orakel

### MqlDownloader: Grenze dokumentiert, keine erfundene Datenquelle

`src/rest/RestApiServer.java:775` schreibt den Katalog ohne Wochenfeld.
`src/rest/MetricsParser.java:22` ist ein generischer Schlüssel/Wert-Parser.
Eine Suche im aktuellen Java-Code findet keinen Produzenten eines expliziten
Altersfeldes. Ein hypothetisch manuell ergänztes TXT-Feld ist dafür kein Beleg.
README beschreibt nun die Konsequenz für den regulären Scanner-Vorfilter.
Ein verlässlich erhobenes Plattform-Alter bleibt hier eine offene Datenlücke.

### PelicanTrading: Zukunft ist kein bekanntes Alter

`model/Provider.java:271` liefert für ein zukünftiges Inception-Datum nun null.
Der bereits vorhandene Jahr-1-Sentinel bleibt unbekannt. Katalog und Metrics
verwenden denselben nullable Wert und nennen seine Herkunft.
`model/WeekEvidenceTest.java` prüft fehlend/Jahr 1/Zukunft sowie unabhängig:
heute = 0 Wochen, 181 Tage = 25 Wochen, 182 Tage = 26 Wochen.

### roboforex: Sentinel darf nicht Jahrhunderte Alter beweisen

`model/SignalAccount.java:108` verwirft Jahr <= 1; der REST-Helfer in
`rest/RestApiServer.java:647` verwirft zusätzlich Zukunftsdaten. Der neue
REST-Test `invalidStartDatesDoNotProveAnOldSignal` prüft vier synthetische
Anbieter mit fehlendem Datum, Jahr 1, Zukunft und heute minus 182 Tage.
Die ersten drei liefern null, der vierte 26. Es wurde keine geschätzte
historische Plattformgründungsgrenze eingeführt.

### vantage: echte Tage, ehrliche Untergrenze und strikter Producer

Die bisherige Kette vollständige Monate -> 30,44 Tage -> gerundete Wochen
konnte beispielsweise 182 Tage Aktivität auf fünf vollständige Monate und
anschließend 22 Wochen verkürzen. Jetzt bestimmt `SignalProvider.wochenOderNull`
ganze Wochen direkt aus dem belegten Datum: 182 Tage = 26, 181 Tage = 25.
`TradeStore.aeltestesHistoriesDatum` berücksichtigt beide Belegpfade, statt eine
vorhandene Daily-Reihe grundsätzlich vor älteren verifizierten Trades zu
bevorzugen. Daily-Nullauffüllungen beweisen keine Aktivität; eine reale
verifizierte Position darf dagegen auch mit Ergebnis 0 Aktivität belegen.
Die bisherigen API-/Anzeigemonate bleiben erhalten, gelten aber nicht als
genauer Wochenbeweis. Der REST-Helfer liest die aktuelle Historie des jeweiligen
Anbieters, auch wenn die Katalog-CSV unverändert blieb.

Ein unabhängiger Peer fand zusätzlich einen bestätigten Producer-Bypass:
`VantageClient.fillDaily` machte bisher aus einem fehlenden/ungültigen `date`
über `asLong()` den Epoch-0-Tag. Bei PnL ungleich 0 konnte diese Zeile Jahrzehnte
Aktivität vortäuschen. Nun muss das Pflichtdatum positive ganzzahlige
Epoch-Millis als Integer oder Integertext enthalten; fehlende/ungültige,
zukünftige und Epoch-Sentinel-Daten brechen den Download ab. Der technische
Epoch-0-Tag wird auch aus bestehenden Daily-CSV-Dateien nicht als Altersbeleg
verwendet. Dies betrifft den konkreten Parserdefault, keine geschätzte
Plattformgründung oder pauschale Kalenderjahresgrenze.

`RestApiServerTest.invalidDailyApiDatesCannotBecomeRestAgeEvidence` prüft über
synthetische Loopback-API -> Parser -> temporären Store -> REST: missing, null,
ungültiger Text, Boolean, Bruchzahl, 0, negativ, NaN, Long-Overflow und Zukunft
können kein Alter liefern; ebenso eine persistierte Epoch-0-Zeile. Echte
numerische und als String gelieferte Zeitstempel von heute minus 182 Tage
ergeben jeweils 26 Wochen. Die weiteren Tests prüfen Monats-/Tagegrenze,
Nullauffüllungen, ältere verifizierte Trades und einen unveränderten Katalog
bei neu eingetroffener Historie.

Ein kurzer oder gekappter Cache kann die tatsächliche Lebensdauer weiterhin
unterschätzen. Das ist die offengelegte Grenze einer konservativen Untergrenze,
kein Anlass, ein unbekanntes längeres Alter zu erfinden.

### zulumonitor: bekanntes 0 von unbekannt unterscheiden

`ZuluTradeClient.knownWeeks` akzeptiert nur endliche, nichtnegative ganze Werte
im Integerbereich. `Trader` hält Wochen nullable; die primitiven GUI-Getter
bleiben konservativ 0, während REST ausdrücklich `getWeeksOderNull` verwendet.
`DataStore` ergänzt eine letzte CSV-Spalte `WeeksKnown`. Damit überlebt der
Unterschied null/echte 0 einen Roundtrip. Alte positive Wochen bleiben bekannt;
eine alte 0 ohne den neuen Kenntnisvermerk wird konservativ unbekannt, weil der
alte Parser fehlende Werte ebenfalls als 0 schrieb. Keine Nutzerdaten wurden
hierfür migriert oder geändert.

`api/WeekEvidenceTest` prüft Parser, Known-0/Unknown und neue/alte CSV-Roundtrips.
`RestApiServerTest.missingWeeksAndKnownZeroAreDistinctOnBothRestRoutes` prüft
denselben Unterschied im Katalog und in Metrics über einen temporären Store.

Eine zusätzliche konkrete Anzeigeprüfung fand zwei verbleibende Legacy-Getter:
Zulus sichtbare Wochenspalte verwendete `getWeeks()` und zeigte unbekannt als 0.
Sie verwendet nun `getWeeksOderNull()` und bleibt bei unbekanntem Alter leer.
Vantage besitzt eine Monatsspalte; seine Altersdetailanzeige zeigte jedoch über
`wochen()` ebenfalls 0 Wochen. Sie verwendet nun `wochenOderNull()` und zeigt
ausdrücklich „Wochen unbekannt“. Die primitiven Filtergetter bleiben erhalten.
Diese minimalen UI-Änderungen sind in den finalen Snapshots enthalten; der
Zulu-Package-Lauf enthält auch die drei vorhandenen `ZuluMonitorUiTest`-Tests.

## Reproduzierbare Abschlussprüfung auf den tatsächlich geänderten Bytes

Alle Pfade der folgenden Tabelle liegen unter
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/deepseek_review_pruefung_2026-10-16/`.
Je Zeile bezeichnet der Name den Snapshotordner und die gleichnamigen Dateien
`<Name>.manifest.json` und `<Name>.maven.log`.

| Quelle | Maßgeblicher finaler Name | Overlay-Dateien | Java-Tests | Ergebnis |
| --- | --- | ---: | ---: | --- |
| MQL | `MqlDownloader_round1` | 1 | 116 | package erfolgreich |
| Pelican | `PelicanTrading_round1` | 4 | 180 | package erfolgreich |
| Robo | `roboforex_round1` | 4 | 180 | package erfolgreich |
| Vantage | `vantage_final_ui` | 8 | 70 | package erfolgreich |
| Zulu | `zulumonitor_final_ui` | 8 | 118 | package erfolgreich |

Insgesamt **664 Java-Tests**, 0 Fehler, 0 Failures, 0 Skips. Vantage zusätzlich
**12 Python-Tests bestanden**, Log `vantage_final_ui.python.log`.
Frühere Vantage-/Zulu-Snapshots sind Zwischenstände; verbindlich sind die
jeweiligen `*_final_ui`-Snapshots.

Snapshotverfahren: `waste/gesamt_review_fixes_2026-10-16/audit/snapshot.py`
archiviert den jeweiligen HEAD und überlagert danach die aktuellen geänderten
versionierten sowie nicht ignorierten neuen Dateien. Private Laufzeitcaches
werden nicht übernommen. Die Manifeste enthalten HEAD und SHA-256 je Overlay.
Der abschließende Abgleich Arbeitskopie und Snapshot gegen alle Manifestwerte
ergab pro Quelle **0 Abweichungen**. `git diff --check` meldet keine Fehler.

Baselines der fünf Quell-Snapshots:

| Quelle | HEAD vor Overlay |
| --- | --- |
| MQL | `c5848ab057758d1505173cc4fcaaeee4a390e2b9` |
| Pelican | `2c611aea3c3dcf092cceb369349f191f596b3d52` |
| Robo | `82223abd09ebf2ab27e30eac8b5026c88f67a2b6` |
| Vantage | `28d2021863f35a0514b45b0fc802fb80d119368c` |
| Zulu | `d1a54ff8406577574e788678a1b8713a99077f29` |

SHA-256 der finalen Manifeste:

```text
MqlDownloader_round1 305350f8e3ff72535dd2d9a765eed1a6a1690e76c6c6f7ba196ca5ce66ef9bb3
PelicanTrading_round1 e67835f65a38068be0f372bb54cc9b5ecfb16273f70c9d732215d103051bfbde
roboforex_round1 c9719a85772c976fb4dd74754d8a9891fb66f9fecdfe3a77b252eee722d92529
vantage_final_ui b460d875ddcd4f5a1262e824f08b11053a4e477da4e19edcbe776d7ee2823ded
zulumonitor_final_ui b07147c11cda7aa980f305c342d3d5a7ea9fbc66dea093eb4baf5f7ebb258532
```

Laufzeit: JDK `C:/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot`;
Maven `D:/DevelopmentTools/apache-maven-3.9.6/bin/mvn.cmd`.
In jedem isolierten Snapshot wurde mit diesem JAVA_HOME/PATH
`mvn -o -B package` ausgeführt. Python:
`C:/Users/tnickel/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe -m pytest -q`
im Vantage-Snapshot. Snapshothelper-Python:
`C:/Users/tnickel/AppData/Local/Programs/Python/Python312/python.exe`.

Die Quellen sind nach diesen Abschlussläufen eingefroren. Die Tests belegen
lokale Parser-/Persistenz-/REST-Verträge mit synthetischen Daten; sie beweisen
weder einen aktuellen Plattformabruf noch die Wahrheit selbst gemeldeter
Plattformdaten. Ein Neustart laufender Quellen, Datenaktualisierung und neuer
Scannerlauf gehören zur anschließenden Übernahme durch Root/Nutzer.
