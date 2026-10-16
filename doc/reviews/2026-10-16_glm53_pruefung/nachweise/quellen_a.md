# GLM-5.3-Review: kritische Prüfung und Korrekturen MQL/Vantage

Stand 16.10.2026. Eingang: angehängter Gesamtreview
`61860d3b-d9d0-40f2-82f6-316422c64d05/Eingefügter Text.txt`.
Keine weiteren lokalen GLM-Teilberichte mit den fehlenden Einzelbeschreibungen
gefunden. Die Aussagen wurden gegen den heutigen Code geprüft, nicht allein
gegen die im Text genannten Vormittagsstände.

| Quelle | GLM-Reviewstand | Basis dieser Prüfung |
|---|---|---|
| MqlDownloader | `92d8f9cea10b` | `908c69088a1fc8c36f20c3bffec7b3f9338bb987` |
| vantage | `1fe395805f29` | `9d3849b16d77cd558bf686f3d685b6af5e016b6b` |

Die heutigen Source-/Securitykorrekturen sind bereits in diesen Basis-HEADs
enthalten. Produktänderungen betreffen ausschließlich MQL und Vantage.
Keine Liveplattform, kein Login, keine GUI, kein LLM, keine Produktionsdaten
oder gespeicherten Nutzereinstellungen wurden benutzt oder geändert.
Kein Stage/Commit/Push durch diesen Quellenagenten; Root veröffentlicht.

## Einordnung jeder zugewiesenen Aussage

Java-Pfade in den folgenden Vantagezeilen sind relativ zu
`vantage/src/main/java/de/vantagemonitor/`.

| Aussage | Status am aktuellen Stand / Umsetzung | Code- und Testbeleg |
|---|---|---|
| MDL-4: REST besitzt keinen Standardfilter >=1 Abonnent | **Bestätigt und behoben.** Bisher wurde ausschließlich ein expliziter minSubscribers-Parameter ausgewertet. Standard und leerer Parameter sind jetzt 1, ausdrückliches 0 erlaubt Archivzugriff. Der Filter greift vor Pagination und gilt für JSON/CSV; Detailzugriff bleibt erhalten. | `MqlDownloader/src/rest/RestApiServer.java:857`; neu `tests/rest/SubscriberDefaultTest.java`. Test: Anbieter mit 0/1 Abonnent, Standard, CSV, Opt-out0, leerer Parameter, großes Minimum und Detailzugriff. |
| MDL-11: CSV-ID aus Dateinamenziffern | **In der behaupteten Form nicht belegt, kein neuer Codefix.** Bereits im GLM-Reviewcommit 92d8f9cea10b verwendet der Dateikatalog extractSignalId und das letzte Unterstrichsegment; Zahlen im Namen werden nicht zusammengezogen oder als andere ID benutzt. Auch der heutige Stand tut dies. Ein Dateiname bleibt natürlich ein gespeicherter Identitätsbeleg und kein unabhängiger Plattformabgleich. | `MqlDownloader/src/rest/RestApiServer.java:611`; `src/rest/ProviderFiles.java:164–177,214`; bestehende `tests/rest/ProviderFilesTest.numbersInProviderNameCannotSelectAnotherSignalsTradesOrMetrics` sowie direkte extractSignalId-Fälle. Gegenprüfung per `git show 92d8f9cea10b:...`. |
| MDL-2 / MDL-3 | **Unbelegt mangels Beschreibung.** Im Gesamtreview stehen nur IDs im Korrekturplan. Daraus lassen sich weder Auslöser noch Sollvertrag oder ein Fehler ableiten. | Keine erfundene Zuordnung oder Änderung. Fehlende Teilreviews wurden nicht durch Spekulation ersetzt. |
| VAN-1: Returnphase trägt bei target<=250 nichts bei | **Bestätigt und behoben.** Der Code nennt ausdrücklich die bestehende Vereinigungsanforderung. Der bisherige Kopiererdeckel min(target,250) plus ungebremste 100er-Seiten konnte das ganze Ziel verbrauchen. Jetzt erhalten nach kuratierten Einträgen die Kopierer die Hälfte des Restbudgets, abgerundet und maximal 250; Return erhält den Rest und füllt Überschneidungen durch weitere Seiten nach. Seiten dürfen das jeweilige Teilbudget nicht überschreiten. | `api/VantageClient.java:134–170`; neu `api/RankingUnionTest` mit Zielen 200/250/600, verschiedenen IDs, Seitenüberlauf, kuratierter Priorität und komplett überlappender erster Returnseite. |
| VAN-3a: TradesTruncated=false bei unbekanntem total | **Bestätigt und behoben.** false war bisher auch die Ausgabe bei total=0, obwohl 0 ausdrücklich unbekannt bedeutet. Jetzt null bei unbekanntem Umfang, unverifiziertem Cache oder widersprüchlichem Umfang; true bei belegtem total>stored; false bei belegtem total=stored. | `rest/RestApiServer.java:406–419`; neue `RestApiServerTest.truncationIsUnknownWithoutVerifiedPlatformTotalAndTriStateOtherwise`: total0/1/2/3 bei zwei gespeicherten Trades plus ungültiger Meta-SHA. |
| VAN-6: <=2000-Trade-PnL / Lifetime-ROI | **Bereits vor diesem Auftrag behoben; nicht erneut als aktuellen Fehler übernehmen.** Der Helper verlangt einen bekannten Lifetimeumfang, genaue Übereinstimmung mit eindeutigen validen Archivtrades sowie endliche positive Modellbasis. Teilhistorie/unknown wird null. Stufe0/GUI laden aktuelle Stats nach, statt alte ROI mit neuen Trades zu mischen. | `report/SignalPayloadBuilder.java:43–59`; bestehende `report/DrawdownBasisTest` und `api/TradeContractTest.missingFreshReturnCannotReuseOldRoiForNewTrades`, im neuen Volllauf erneut grün. Gleiche Counts sind weiterhin kein unabhängiger Vollständigkeitsbeweis. |
| VAN-8 / VAN-9: Kennzahlenfenster / metricsWindow | **Die fehlende Fensterkennzeichnung ist konkret belegt und behoben. Die vollständigen Einzelbeschreibungen fehlen.** Average3MonthProfit war numerisch ein Alias der Rankingrendite, kein 3-Monatsmittel. Zusätzlich befüllt filter-signal mit months=1 schon DD/PF in Legacy-All-Feldern, bevor Overview(All) sie überschreibt. Nun wird die konkrete Herkunft feldweise persistiert und auf Antwortebene als metricsWindow ausgegeben. Eine darüber hinausgehende mathematische Fehlerbeschreibung wird aus den bloßen IDs nicht erfunden. | `api/VantageClient.java:195–204,221–240,302–307`; `store/DataStore.java:27,72–74,111–117`; `rest/RestApiServer.java:431–439`; neu `api/MetricsWindowTest` sowie `RestApiServerTest.metricsExposeFieldSpecificWindowsWithoutInventingThreeMonths`. |
| VAN-7: ddSource | **Sinnvolle Klarstellung umgesetzt, kein neuer nachgewiesener Rechenfehler.** Die Antwort unterscheidet Plattform-Ranking, Plattform-Overview und lokalen Closing-DD auf ROI-Modellbasis. Der Name EquityDrawdown des alten REST-Vertrags beweist für sich weder gemessene historische Equity noch Floatingabdeckung. | `rest/RestApiServer.java:440–443`; neue Herkunfts-/Fenstertests und erweiterte bestehende DD-Cache-REST-Regressionsfälle. |
| VAN-4: dauerhafter Skip bekannter Tradelisten | **Bereits heute behoben.** Bekannte Anbieter werden in Stufe0 erneut abgerufen; lokaler SHA beweist Integrität, keine Plattformfrische. | Bestehende `UpdateJobStufe0Test` im neuen vollständigen Lauf grün. Keine erneute Liveprüfung alter laufender Prozesse, keine Behauptung, dass veröffentlichter Code bereits in einer laufenden GUI aktiv sei. |

Die stärkste Gegenposition zu VAN-1 bleibt: Jeder begrenzte Katalog ist eine
Auswahlpolitik. Die neue 50/50-Regel erfüllt die Vereinigungsanforderung unter
dem verbleibenden Budget, sie ist keine statistisch validierte Rangfolge.
Kuratierte Einträge behalten Vorrang. Decken sie das ganze Ziel ab, kommt keine
zusätzliche Rangliste hinein; bei genau einem freien Platz bekommt Return ihn.
Ein Katalogziel begrenzt damit weiterhin die tatsächlich beobachteten Anbieter.

Die Freeze-/DD-Aussagen des GLM-Textes beziehen sich überwiegend auf alte
Source-HEADs beziehungsweise alte laufende Prozesse. Eine pauschale heutige
Aussage „vier Quellen frieren dauerhaft ein“ wird daraus nicht übernommen.
In diesem Auftrag wurde weder eine laufende Instanz neu gestartet noch ihr
Buildstand über einen Liveaufruf bewiesen.

## Neuer konkreter Befund außerhalb der unbeschriebenen IDs

MQL-Pagination addierte in Providerliste, Abonnentenhistorie, Tradeansicht und
Dateikatalog `from+limit` als int. Mit offset=1 und limit=2147483647 lief die
Addition über; der Server antwortete **400**, weil er die daraus entstehende
IllegalArgumentException als Bad Request abfängt. Der zunächst vermutete 500
ist durch den tatsächlichen HTTP-Test widerlegt. Positive long-Offsets konnten
zudem beim vorzeitigen Cast negativ und anschließend fälschlich 0 werden.

Nachweis vor dem Fix: `mql_pagination_before.log`, ein gezielter tatsächlich
roter HTTP-Test auf dem isolierten Vor-Fix-Code, expected=200/actual=400.
Dies ist ausdrücklich **keine** Zuordnung zu MDL-2 oder MDL-3.

Korrektur: gemeinsame sichere Parameterbegrenzung vor dem int-Cast und
long-Addition des Seitenendes, `MqlDownloader/src/rest/RestApiServer.java:429,
481,600,665,906–917`. Negative Werte behalten den vorhandenen Clampvertrag.
Regression `RestApiServerTest.largePaginationValuesCannotOverflowAnyListEndpoint`
prüft tatsächlich `/providers`, `/trades` (Dateikatalog),
`/providers/123/mql5/history` und `/providers/123/mql5/trades` mit maximalem
int-Limit sowie maximalem long-Offset. Nach dem Fix 200 und korrekt leere Seiten.

## Präziser neuer Vantage-Metadatenvertrag

Die bestehenden numerischen Felder bleiben kompatibel. Zusätzlich stehen auf
Antwortebene, neben `metrics`, zwei Maps:

```json
{
  "metricsWindow": {
    "Average3MonthProfit": "1_month",
    "Return30dPct": "1_month",
    "WinRate": "1_month",
    "ReturnAllPct": "All",
    "EquityDrawdown": "All",
    "MaxDDGraphic": "All",
    "ProfitFactor": "All",
    "TradeEqDrawdownPct": "local_closed_archive_with_lifetime_roi"
  },
  "ddSource": {
    "EquityDrawdown": "platform_overview",
    "MaxDDGraphic": "platform_overview",
    "TradeEqDrawdownPct": "local_closing_dd_roi_model"
  }
}
```

Das ist ein mögliches belegtes Beispiel, kein immer garantierter Zustand.
`1_month` bezeichnet exakt den Request months=1; daraus wird kein gemessener
3-Monatsdurchschnitt und keine sekundengenaue 30-Tage-Spanne erfunden.
`All` stammt aus dem entsprechenden erfolgreichen Overviewrequest mit einem
vorhandenen numerisch verwertbaren Feld. Vor einem solchen Nachzug können DD/PF
noch `1_month` / `platform_filter_signal` aus dem Ranking besitzen.
Toplisten ohne expliziten Requestzeitraum und Legacy-/Python-Kataloge ohne
persistierte Herkunft erhalten `unknown`. Fehlender lokaler DD hat ebenfalls
unknown als Quelle/Fenster. Die Metadaten sind kein neuer Frischebeleg.

Fünf optionale Herkunftsspalten erhalten diese Angaben bei normalen zukünftigen
Katalogspeicherungen. Alte 20-Spalten-Dateien bleiben lesbar, ohne automatische
Migration oder rückwirkend behaupteten Herkunftsnachweis. Das Pythonprogramm
wurde nicht geändert; seine alten Kataloge werden konservativ als unknown
gelesen. Die Zahlenberechnung selbst wurde nicht in eine unbewiesene andere
Plattformsemantik oder Währungsskalierung umgedeutet.

## Finale isolierte Verifikation

Auditroot:
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/glm53_review_pruefung_2026-10-16/`.

| Quelle | Finaler Snapshot | Aktuelle Overlaydateien | Ergebnis | Nachweise |
|---|---|---:|---|---|
| MQL | `MqlDownloader_final2/` | 4 | **116 Tests**, 0 Fehler/Fehlschläge/Skips; Paket und Distributions-JAR erfolgreich | `MqlDownloader_final2.maven.log`, `MqlDownloader_final2.manifest.json` |
| Vantage | `vantage_final/` | 8 | **65 Java-Tests**, 0 Fehler/Fehlschläge/Skips; Paket erfolgreich | `vantage_final.maven.log`, `vantage_final.manifest.json` |
| Vantage Python | derselbe finale Snapshot | unveränderter Pythoncode | **12 bestanden** | `vantage_final.python.log` |

Snapshotverfahren: `git archive HEAD` **plus aktuelle getrackte Änderungen und
nicht ignorierte neue Dateien**, SHA256 jedes Overlays im Manifest. Es wurden
keine privaten Laufzeitcaches übernommen. Abschließender Hashvergleich
Checkout↔Snapshot: **4/4 und 8/8 identisch**. `git diff --check` ohne Fehler;
übliche LF/CRLF-Hinweise sind keine Whitespacefehler.

Alle finalen Befehle liefen im jeweiligen Snapshot:

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot'
$env:PATH="$env:JAVA_HOME\bin;$env:PATH"
& 'D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd' -o -B package
# zusätzlich Vantage:
& 'C:\Users\tnickel\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe' -m pytest -q
```

Die erweiterten Tests verwenden ausschließlich synthetische Anbieter,
temporäre Dateien und Loopback-HTTP-Server. Vorherige round1/final-MQL-Logs
enthalten Zwischenstände und sind nicht der abschließende Paketnachweis.
Der final2-Lauf enthält die korrigierte Paginationregression; ihr vorübergehend
falscher Dateikatalogpfad im Zwischenstand wurde zu `/api/v1/trades` korrigiert.
Keine Integration von MqlRealmonitor oder PelicanWinnerLooser.
