# Read-only Peerprüfung der Quellen-Altersnachweise

Scope: aktuelle Änderungen in MqlDownloader, PelicanTrading, roboforex, vantage und zulumonitor. Keine Produkt-/Snapshotänderungen, Tests, Live-Datenzugriffe oder Logins durch diesen Peer. Quellen-Agent führt die Builds und Regressionen aus. Der zunächst bestätigte Vantage-Producerpfad und seine Legacy-Sentinelzeile sind korrigiert. Maßgebliche letzte Snapshots einschließlich GUI-Nachtrag sind `vantage_final_ui` und `zulumonitor_final_ui`; siehe letzten Abschlussblock. Die vorangehenden Prüfstände bleiben als Verlauf dokumentiert.

## Bestätigter Ausgangsfehler: Vantage erzeugte Aktivitätsdatum aus fehlendem Datum

**P1 für den Altersvertrag; bedingter Codepfad sicher, Plattformhäufigkeit unbekannt.**

`vantage/src/main/java/de/vantagemonitor/api/VantageClient.java:339–344` nutzt in `fillDaily()` weiterhin `n.path("date").asLong()`. Bei fehlendem/null/ungültigem Datum folgt Default0 statt unbekannt/Fehler. Ein solcher Datensatz mit `pnlData=1` wird als `1970-01-01` gespeichert. Der neue Altersnachweis in `store/TradeStore.java:252–273` prüft endlichen nichtzero Strategie-PnL, Jahr>1 und nicht zukünftig;1970 erfüllt dies. Damit kann ohne tatsächlichen Datumsbeleg ein Jahrzehntealter und folglich der26-Wochenpass entstehen.

Minimaler Auslöser der reinen Parserlogik: `strategyPnlList=[{"pnlData":1}]` oder entsprechendes Element mit `date:null`/ungültigem Text. Kein Plattformabruf nötig, um die Defaultkonvertierung zu belegen. Geschlossene Trades haben diesen konkreten Weg nicht: `positiveLong()`/`parseEpochMs()` liefern bei fehlendem/ungültigem Timestamp null; die Positionsvalidierung verwirft fehlende Zeiten.

**Auch Altbestand beachten:** Ein bloßer zukünftiger Producerfix entfernt bereits aus diesem Default erzeugte `daily_*.csv`-Zeilen `1970-01-01;1;...` nicht. Diese Legacyzeile besitzt keinen belastbaren Altersbeleg und darf durch die neue Altersableitung nicht plötzlich Jahrzehnte beweisen. Root und Quellen-Agent wurden unmittelbar mit Codeankern informiert; gezielte Producer- und persistierte Sentinelregression empfohlen. Keine Eigenänderung durch Peer.

## Im Übrigen geprüfte Grenzen

| Quelle | Altersbeleg / Grenzverhalten / Verträglichkeit |
|---|---|
| **MQL** | Provider-JSON erzeugt kein `weeks`, Kennzahlen-TXT-Produzenten erzeugen derzeit ebenfalls keinen Alterswert. README legt die Lücke offen. Dateizeit und Abonnentenhistorie werden nicht als Gründungsdatum umgedeutet. Der reguläre Scannerfilter bleibt ohne Beleg gesperrt. Unveränderte Code-/CSV-Schnittstelle. |
| **Pelican** | `Provider.setInception` verwirft Jahr≤1 auch aus Alt-CSV; `wochenOderNull` verwirft fehlende und zukünftige Starts. Vollständige Wochen zwischen datiertem Start und heute;182 Tage ergeben26,181 ergeben25, Start heute0. REST-Katalog und Metrics verwenden dieselbe nullable API und Herkunftskennzeichnung. Setter/GUI-`wochen()` bleiben kompatibel; historisch gültiger Start darf bei später fehlendem Statsfeld bestehen bleiben. Ein ungültiger neuer Wert erzeugt keinen neuen Start. |
| **Robo** | Setter verwirft Jahr≤1; REST-Prüfung verwirft zusätzlich fehlende und zukünftige Starts. Alte CSV wird durch denselben Setter gelesen. Ungültige Datumsstrings führen beim API-Parser zu null bzw. beim bereits zuvor strengen CSV-Loader zu Fehler, nicht zu einem erfundenen Alter. GUI-Getter bleibt `long` und konservativ0 bei unbekannt/zukünftig; keine Spaltenverschiebung. |
| **Zulu** | `knownWeeks()` akzeptiert nur endliche nichtnegative ganzzahlige Werte innerhalb Integerbereich. Fehlend/null/negativ/NaN/Boolean/Bruch bleiben unbekannt, ausdrücklich gelieferte0 bleibt0. REST benutzt `getWeeksOderNull()`, kein hochgerechnetes Profilregistrierungsdatum. `WeeksKnown` wird als letzte CSV-Spalte angehängt; bestehende Indizes bleiben gleich. Unbekannt wird leer gespeichert, echte0 mit Marker erhalten, alte0 ohne Marker als unbekannt interpretiert. Positive Legacy-Werte bleiben als berichteter Wochenwert lesbar. Primitive `getWeeks()` bleibt erhalten; bestehende GUI/Ampel/Reportconsumer bekommen bei unbekannt weiterhin konservativ0 und können dadurch keinen unbelegten26-Wochenpass erzeugen. |
| **Vantage, neuer Store/REST** | Exakte vollständige Wochen aus datierter lokaler Aktivität statt gerundeter voller Monate. Null-Padding, fehlender/nichtendlicher Strategie-PnL, Jahr≤1 und Zukunftsdaten sind als Altersbeleg ausgeschlossen. Älterer verifizierter Trade kann ein kürzeres Dailyfenster ergänzen; Trade-SHA/Schema/Positionsvalidierung müssen passen. REST liest für jeden Provider die aktuelle Historie, unabhängig von Katalog-CSVmtime; neu geladene Historie bleibt somit sichtbar. API-/GUI-Monate bleiben Anzeige, kein exakter Wochenbeleg. Die verbleibende Producercoercion1970 ist davon ausdrücklich ausgenommen, siehe Fehler oben. |

## GUI-/CSV-Abwägung und Aussagegrenzen

Keine neue Spaltenverschiebung oder ungewollte Null-Unboxing-Exception in den geprüften Consumerpfaden erkennbar. Zulu-`Trader` nimmt intern `Integer`, bestehende Sourceaufrufe mit `int` werden geboxt; der öffentliche primitive Getter bleibt. Legacy-CSV mit27/28 Spalten bleibt durch Längenprüfungen lesbar. Fremde bereits kompilierte Binärconsumer des Konstruktors wurden nicht untersucht; im Repository werden die Quellen neu gebaut.

Vantage-`wochen()` gibt ohne lokalen Datumsbeleg nun0 statt einer Schätzung aus Rankingmonaten. Dadurch können dessen lokale Wochenfilter/Quellenampel bis zum Historienabruf konservativer ausfallen. Das ist eine dokumentierte fachliche Folge der strengeren Beleganforderung, kein Absturz. Der Scanner-REST bewahrt null. Der frühere GUI-0-Hinweis ist für die nachgezogenen Pfade (Zulu-Wochenspalte und Vantage-Hauptapp-Alterdetail) durch den unten geprüften UI-Abschluss ersetzt. Ein kurzer/gekappter lokaler Verlauf beweist nur eine Altersuntergrenze und kann echte ältere Signale zu streng ausschließen; er rechtfertigt keine frei erfundene26-Wochenannahme.

Die Prüfung beweist die behandelten Eingangs-/Speicher-/Exportpfade, keine aktuelle Vollständigkeit oder Wahrheit von Plattformangaben und keine Prüfung laufender alter Instanzen. Der oben gemeldete Vantage-Pfad war im ersten Lesestand offen; der folgende Abschlussblock ersetzt diesen Zwischenstatus.

## Finale Nachsicherung: Vantage-Pfad geschlossen

Maßgeblicher Snapshot: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\deepseek_review_pruefung_2026-10-16\vantage_final3`, Basis-HEAD `28d2021863f35a0514b45b0fc802fb80d119368c` plus sieben dokumentierte Overlays.

`VantageClient.fillDaily()` liest das Pflichtdatum jetzt über `positiveLong(n.get("date"))`. Fehlend/null, Text ohne Zahl, Boolean, Bruchzahl,0, negative Werte, NaN und Long-Overflow erzeugen `ApiException`; kein Defaultdatum wird gespeichert. Datumskonvertierung, Zukunftstag und der örtliche Epoch-Sentineltag werden zusätzlich geprüft. Ganze positive numerische oder als Ziffernstring gelieferte Millisekunden bleiben kompatibel. Fehler brechen den Abruf ab, statt einen erfolgreichen Teilbestand mit erfundenem Datum zu erzeugen.

`TradeStore.aeltestesHistoriesDatum()` verwirft zusätzlich den von der alten Defaultkonvertierung erzeugten örtlichen Epoch-Sentineltag in persistierten Dailydateien, auch bei nonzeroPnL. Die Prüfung verwendet dieselbe Systemzeitzone wie der API-Parser. Gültige ältere verifizierte Trades bleiben ein unabhängiger Aktivitätsbeleg; ohne solchen Beleg wird der Sentinel nicht in Jahrzehntealter umgedeutet. Die bestehende Jahr-/Zukunfts-/Nullpaddingprüfung bleibt erhalten.

Die neue Regression `RestApiServerTest.invalidDailyApiDatesCannotBecomeRestAgeEvidence()` wurde gelesen: lokaler API-Fake → echter Daily-Parser → echter Store → REST-Metrics. Sie prüft die genannten ungültigen Datumsfälle, persistierte Epoch-Legacyzeile und gültige numerische/String-Millis. Für gültige182 Tage erwartet sie26 Wochen, ohne Beleg `Weeks:null`. Keine externen Plattformzugriffe.

Gelesene finale Logs des Quellen-Agenten: **70 Java-Tests ohne Fehler/Skips und Package BUILD SUCCESS**, `vantage_final3.maven.log`; **12 Python-Tests grün**, `vantage_final3.python.log`. Kein eigener Teststart durch Peer. Keine weiteren konkreten Regressionsbefunde in den beauftragten Alters-/CSV-Pfaden. Diese Aussage ersetzt keine Plattformwahrheits- oder laufende-Binary-Prüfung.

Alle sieben Live-Overlaydateien wurden direkt mit `vantage_final3` und `vantage_final3.manifest.json` verglichen: **Live = Snapshot = Manifest**, ohne Abweichung.

```text
README.md                    283fcff1a7b6be347dd9c9f419a91bd768e60f18ae60f90624b7ce43ab8e58ce
api/VantageClient.java       aa4cc4dd2912dcfa4ccbf4e9c0e411d4824556482508db98295e4551527a222b
model/SignalProvider.java    62556441b0c4cb77e17499159b453384e68fb4d36b33f05c944f24235b6cd302
rest/RestApiServer.java      86bec7fe32c2fa01ca66a4b9c58469b1bc99d5858b2015c4f7f6ccfeb005f579
store/TradeStore.java        b32729e7d87e1e4be8764d64920541758493f307529739a1f4338afd4d5ebdbd
RestApiServerTest.java       4ff46fa57627675810b4222bf40dd828bf1a10c07e9d4abddfda7fcb5b5eb2cb
TradeStoreMonateTest.java    cfd5f587a122f3a65f0702c7acb6858634ecd84d994189930751b2de5d70a3a3
```

Artefakt-SHA256:

```text
vantage_final3.manifest.json 8ee634894f20e3579dd8baa0b1aa788f428d783bfcb2c3021bd0560c9a44c6ea
vantage_final3.maven.log     ad107cf53da18b3eeb8dea3d6a88c884fbbfbfaa3b65183c9062de6090b58fac
vantage_final3.python.log    f02e8e90cd319b9823f4b1b86ce969efedad01892fb2688f31fdab523ee0b42f
```

Read-only Peerprüfung abgeschlossen; keine Produkt-/Snapshotänderung. Die eingefrorene kombinierte Scanner-Suite `Scanner_final3` wird separat von Root nachgewiesen.

## Letzter Abschluss: unbekanntes Alter in den nachgezogenen GUI-Pfaden

Die beiden minimalen GUI-Diffs wurden ebenfalls gelesen und gegengeprüft:

- `zulumonitor/src/main/java/de/zulumonitor/ZuluMonitorApp.java:793`: Wochenspalte liest `getWeeksOderNull()` statt des primitiven Kompatibilitätsgetters. Unbekannt bleibt als null leer, tatsächlich belegte0 bleibt numerisch0.
- `vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:2547`: Alterdetail liest `wochenOderNull()` und zeigt bei fehlendem Beleg ausdrücklich „Wochen unbekannt“. Die Ranking-Monatsanzeige bleibt separat erhalten. Kein unbelegter Wochenwert wird daraus erzeugt.

Damit ist die zuvor erwähnte GUI-0-Grenze für diese beiden Anzeigewege geschlossen. Interne primitive Getter bleiben für bestehende numerische Consumer kompatibel; die Änderungen betreffen keine Altersformel oder Scannerbewertung.

Maßgebliche finale Artefakte im selben Auditordner:

| Snapshot | Hashabgleich | Finale Logs |
|---|---|---|
| `vantage_final_ui` | alle8 Overlays: Live = Snapshot = Manifest | **70 Java +12 Python grün, Package BUILD SUCCESS** |
| `zulumonitor_final_ui` | alle8 Overlays: Live = Snapshot = Manifest | **118 Java grün, Package BUILD SUCCESS** |

Die jeweiligen `.maven.log`/`.python.log` wurden gelesen; keine Tests durch Peer wiederholt. Manifest-SHA256:

```text
vantage_final_ui.manifest.json     b460d875ddcd4f5a1262e824f08b11053a4e477da4e19edcbe776d7ee2823ded
zulumonitor_final_ui.manifest.json b07147c11cda7aa980f305c342d3d5a7ea9fbc66dea093eb4baf5f7ebb258532
VantageMonitorApp.java             af6edd28e73b8e9043fb2e34e730ed504f5b0dd304ab9ea989bf867e25e8a62d
ZuluMonitorApp.java                7df758b9d7ff1194f7387714f1c8c1828bce40f3d26ba36c843d1919c35b59fb
```

Diese beiden Manifeste enthalten zusätzlich zu den weiterhin überprüften Alters-/Store-/REST-Dateien die zuletzt geänderten GUI-Dateien. Sie ersetzen die vorherigen Snapshotnamen als Publikations-/Freeze-Nachweis. Keine weiteren Produkt- oder Snapshotänderungen durch diesen Peer.
