# Review der Downloads und Tabellen zur Übergabe an eine andere KI

## Ergebnis und Bearbeitungsstand

**Spätere Umsetzung der Architekturpunkte:** Die FT-Kontraktmodelle und die durchgängige Quellenidentität wurden anschließend umgesetzt. Maßgeblicher neuer Bericht mit Migrationsfolgen, aktueller Abnahme und produktivem Aktivierungsnachweis: [Identität und FT-Kontrakte](../2026-10-18_identitaet_kontrakte_umsetzung/README.md). Die folgenden früheren Aussagen zu ID-weiten Kindtabellen beschreiben den damaligen Zustand. Unbelegte historische Studien werden durch den Umbau nicht als neue Messung freigegeben.

**Aktueller Nachtrag zur Behebung:** Die ursprünglichen sechs Befunde F1–F6 sind inzwischen im Scanner und den beiden Client-Projekten im Arbeitsbaum korrigiert. Der jeweils aktuelle Test-, Build- und Betriebsstand steht in [BEHEBUNG.md](BEHEBUNG.md). Die folgenden Auditbefunde und der unten dokumentierte Zwischenstand sind zeitgebundene Belege; insbesondere ist die dortige Aussage „kein geänderter Quellcode“ in Vantage/MqlDownloader durch die anschließende Implementierung überholt. Produktive Historien werden durch die Codeänderung allein noch nicht erneuert.

Dieser Review beschreibt den am **18.10.2026** geprüften Zustand des SignalKiScanner und seiner fünf lokalen Datenquellen. Er ist ohne den ursprünglichen Chat verständlich. Das Audit ist abgeschlossen; **die hier empfohlenen Korrekturen wurden im Audit nicht umgesetzt**.

Ergebnis: **Vier P1-Fehler, ein P2-Fehler und ein P3-Fehler sind bestätigt.** Ein aktueller Vantage-Datenbestand ist blockiert. Drei weitere erhebliche Fehler wurden isoliert reproduziert. Das Mapping der im Bestand geprüften Tabellenfelder ergab keine Abweichung. **577 gezielte Tests bestanden**, obwohl die zusätzlichen Fehlerproben bisher unzureichend abgesicherte Abläufe nachweisen.

Dieses Dokument übergibt Befunde und Abnahmekriterien. Es führt selbst keine Behebung, Datenmigration oder produktive Aktualisierung aus. Bei einer anschließenden Behebung sind die Befunde gegen den dann aktuellen Code erneut zu prüfen. Die Zeilennummern beziehen sich auf den Auditstand und können sich verschieben.

## Projekt und Arbeitsverzeichnisse

Der Scanner ist eine Python-/Streamlit-Anwendung für Handelssignale. Java-Monitore laden Signale und Historien von den Plattformen und stellen sie lokal per REST bereit. Der Scanner übernimmt Kataloge, Kennzahlen und Trade-CSVs, berechnet Befunde im Code, speichert diese in SQLite und zeigt zwei unterschiedliche Tabellen an.

Workspace: `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER`.

| Projekt | Absolutes Arbeitsverzeichnis | Commit beim Audit | Lokaler API-Port |
|---|---|---|---:|
| SignalKiScanner | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner` | `1bda2fa003a3be8cd924456284f7e8bd8ac048a8` | 8611 |
| MqlDownloader | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader` | `afe507e5ea318f3f5dc1236fb5bb8efafeb3db68` | 8089 |
| PelicanTrading | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/PelicanTrading` | `ff883d625e36fe192d4a8ef220a891b12f84e790` | 8090 |
| roboforex | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/roboforex` | `731466670dec1c6038b83c567a1642d3afebd64b` | 8091 |
| vantage | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage` | `81511b4e82a82c0a7685cb996dea3e863fc2c174` | 8092 |
| zulumonitor | `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor` | `cfcf68834be360b527bb263a5acfe702774123c4` | 8093 |

Die Quellenkürzel im Scanner lauten `mql5`, `pelik`, `robo`, `vant` und `zulu`. `mql5` kann dabei sowohl den direkten MQL5-Bezug als auch den MqlDownloader-Kanal bezeichnen; die konkrete Herkunft ist anhand des Codepfads zu prüfen. Die Quellen-APIs verwenden die Basis `/api/v1`.

**Zuerst lesen:** [AGENTS.md](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/AGENTS.md). Maßgebliche produktive Einstellungen: [app_settings.json](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/config/app_settings.json). Vor Änderungen zusätzlich die jeweils geltenden Anweisungen der betroffenen Nachbarprojekte prüfen.

Die folgenden fachlichen Regeln müssen erhalten bleiben:

- Risiko vor Ertrag; **keine starre 30-%-Obergrenze**. Nach Nutzerentscheidung vom 18.10.2026 darf die konfigurierte DD-Schranke auch bei **50 %** liegen, sofern die Ertragsprüfung und der belastbare Jahres-Calmar die konfigurierten Kriterien erfüllen. 50 % ist ein zulässiger Grenzwert, kein pauschal gewählter neuer Standard.
- Grün benötigt die vorgeschriebenen bestandenen Prüfungen und Jahres-Calmar mindestens der konfigurierten Schwelle, standardmäßig 3,0, bei mindestens drei Monaten Historie.
- Der Calmar-Nenner benötigt die belastbare eigene H1-Equity-Messung einschließlich Floating. Monitor-Closing-DD bleibt ein separater Kanal der harten Schranke.
- Fehlender Stop-Loss-Nachweis ist neutral. Fehlende Währungs- und Messnachweise dürfen nicht erfunden werden. Annahmen zur Kapitalbasis dürfen nicht als belegte reale Werte ausgegeben werden; der ausdrücklich freigegebene virtuelle Quellenfallback bleibt erhalten.
- MQL-native Beträge benötigen einen belegten USD-Nachweis für die USD-Forensik. Eine REST-Lieferung allein belegt keine USD-Währung.
- Virtuelle beziehungsweise vorbehaltliche Werte aus separat übernommenen Equity-Studien müssen erkennbar bleiben und dürfen keine Workflow-Freigabe herstellen. Davon zu unterscheiden ist der freigegebene Quellenfallback `KAPITALBASIS_QUELLE_VIRTUELL` innerhalb der normalen Workflow-Engine: Er muss markiert bleiben, hat in `ampel_for` aber kein eigenes Grün-Veto. Diese zwei Datenkanäle nicht vereinheitlichen und keine neue Bewertungssperre einführen.
- MqlRealmonitor und PelicanWinnerLooser werden durch diese Aufgabe nicht integriert.

Die aktuelle fachliche Version beim Audit ist `FORENSICS_VERSION = 19`. Eine bloße Änderung von Versionsnummern oder Statusflags behebt keinen der folgenden Fehler.

## Zusätzlicher Änderungsauftrag zur Drawdownregel

**Nutzerentscheidung nach dem Audit vom 18.10.2026:** Die bisherige feste 30-%-Vorgabe entfällt. Ein Signal darf nicht allein wegen eines DD über 30 % abgelehnt werden, wenn der ausdrücklich konfigurierte Grenzwert höher liegt und die Ertrags-/Effizienzprüfung erfüllt ist. Ein Grenzwert von 50 % ist zulässig. Belastbarer RetDD bedeutet weiterhin: Jahres-Calmar auf eigener gültiger H1-Equity-Messung einschließlich Floating, ausreichend lange Historie und Einhaltung der konfigurierten Mindestschwelle. Die bisherige Jahres-Calmar-Schwelle 3,0 und die standardmäßig ausgeschaltete absolute Monatsertragshürde werden dadurch nicht geändert.

Dieser Auftrag ist eine neue fachliche Vorgabe, kein siebter Fehlerbefund des ursprünglichen Audits. Die sechs Findings F1 bis F6 bleiben als historische Auditbefunde erhalten und sind inzwischen im Arbeitsbaum behoben. Die zunächst reine Dokumentationskorrektur wurde anschließend durch die Implementierung ergänzt; aktuelle Nachweise stehen in [BEHEBUNG.md](BEHEBUNG.md).

**Aktueller Umsetzungsstand (18.10.2026 nachmittags, Arbeitsbaum, uncommittet):** Die Admin-Begrenzung ist ENTFERNT — der Dialog akzeptiert jetzt jede endliche positive Grenze, und die Ertragsschwelle ist ab 0 konfigurierbar (beseitigt nebenbei den Altfehler, dass das Admin-Feld `min_ertrag_pct_monat` heimlich auf mindestens 5 anhob, obwohl produktiv 0 eingestellt war). Scan-Banner, Ampel-Matrix-, Regelwerk-, FAQ- und Hilfetexte lesen die Grenze aus den Settings statt einer festen 30-%-Aussage. **Produktiv steht `schranke_eq_dd_pct` jetzt auf 50,0** (Nutzerentscheidung „nicht so hart filtern"); `config.DEFAULT_SETTINGS` bleibt 30 als Startwert und ist keine Obergrenze. Die Engine vergleicht weiterhin `DD-Maximum > Grenze` (bei 50 sind 49,9 % und exakt 50 % innerhalb der Grenze); Calmar-Gate, Mindesthistorie und alle übrigen fachlichen Gates bleiben unverändert.

Die Scanner-Korrekturen sind implementiert und durch Regressionen bestätigt. Die erste vollständige Standardsuite nach F1–F6 bestand mit 2.455 Tests; nach den ergänzenden Tabellen-/Stufe-0-Korrekturen bestand die gemeinsame Consumer-Regression mit 317 Tests. Nachweise stehen im Behebungsbericht. Testgruppen überlappen und werden nicht addiert:

- **F2 behoben:** `pipeline` friert die Trade-Bytes VOR der Analyse in einen Snapshot (`db.snapshot_trade_file`) und übergibt dessen SHA bis zum Commit (`store_scan_result(expected_trades_sha256=…)`); `results_from_db` prüft sonst-aktuelle Befunde zusätzlich auf Existenz und SHA der Snapshot-Datei. `store_scan_result` erzwingt für bestehende Signale eine explizite nichtleere `quelle` (schließt die still-Überschreiben-Lücke des Audits) und öffnet mit `BEGIN IMMEDIATE`. Ein gleichzeitig manuell erneuerter Cache verändert den laufenden Analyseeingang nicht; dieser Ablauf ist mit zwei Threads reproduziert und getestet.
- **F4 behoben:** `ingest.hole_katalog` validiert `total`-Vorhandenheit und -Konstanz, Seitenoffset, Zeilenzahl gegen `total`, doppelte (signalId, version)-Identitäten und wirft `DownloaderError` statt eine Teilmenge als Vollkatalog zurückzugeben; `katalog.sync` fängt den Fehler quellenweise ab — keine stille Löschung mehr.
- **F5 behoben:** `ingest` liest `TradesCompletenessNote` mit `CompletenessNote`-Fallback.
- **F6 behoben:** Max-Drawdown-Hilfetext nennt ausschließlich die eigene H1-Messung; Monitor-Closing-DD ist als separater Schrankenkanal beschrieben.

Die Audit-Testdateien sind in die Regression einbezogen. Zwei Tabellenassertions, die ausdrücklich den damaligen Fehlerzustand dokumentierten, wurden gezielt auf das korrigierte Verhalten aktualisiert. **F1 und F3 sind inzwischen auch in den Client-Projekten implementiert und gebaut**: Vantage 88 Tests, MqlDownloader 140 Tests erfolgreich. Die laufenden Monitor-Prozesse und ihre produktiven Historien wurden durch diese Arbeit nicht neu gestartet oder erneuert. Die anschließend bestätigten Punkte M-1 (Stale-Kennzeichnung), CSV-Spaltenlücke, Link-Spaltenkopf und spurlose Stufe-0-Abbrüche sind ebenfalls im Arbeitsbaum behoben. `last_checked_at`/neuester Trade-Zeitpunkt je Artefakt bleibt eine getrennte optionale Metadatenerweiterung. Einzelheiten und Grenzen der Betriebsabnahme stehen in [BEHEBUNG.md](BEHEBUNG.md).

**Umsetzung und Abnahme:**

1. Der Admin muss einen konfigurierten Wert von 50 % anzeigen, speichern und wieder laden können, ohne auf 30 % zurückzufallen. Dabei die vorhandene Einstellung `min_ertrag_pct_monat=0` erhalten; die alte Admin-Logik darf nicht beiläufig wieder mindestens 5 % Monatsertrag erzwingen.
2. Bei konfigurierten 50 % DD bleiben 49,9 % und exakt 50 % innerhalb der Grenze; über 50 % liegt eine Schrankenverletzung vor. Grün verlangt zusätzlich alle bestehenden fachlichen Gates. Fehlender/vorbehaltlicher RetDD oder ein Jahres-Calmar unter der Schwelle erlauben weiterhin kein Grün.
3. Mit einem ausdrücklich konfigurierten Grenzwert von 30 % darf dessen Überschreitung weiterhin abgelehnt werden. Entfernt wird die allgemeine 30-%-Pflicht, nicht die Möglichkeit, diesen Wert bewusst zu konfigurieren.
4. Scanbanner, Adminhilfe, FAQ, Regelwerk, Matrixerklärungen und KI-Kontext dürfen keine unveränderliche 30-%-Obergrenze behaupten. Angezeigte Grenzen müssen aus den maßgeblichen Settings stammen.
5. Historische Befunde und manuell kuratierte Ausschlüsse nicht rückwirkend umschreiben oder automatisch aufheben. Separate Schockwarnungen beziehungsweise Score-Farbstufen mit 30 % sind andere Kriterien und nicht pauschal mitzuändern.

Zusätzliche Einstiegspunkte: [Scanbanner](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/app_pages/scan.py:168), [Adminhilfe](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/help_settings.py:146), [FAQ](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/faq_inhalte.py:201), [Regelwerk](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/regelwerk.py:26). Diese Stellen sind angepasst; die Implementierung und Abnahme sind im Behebungsbericht dokumentiert.

## Datenfluss und Bedeutung der beiden Tabellen

Der REST-Weg lautet:

```text
Plattform
  → Quellenmonitor: Katalog und Tradehistorien laden
  → Stufe 0: POST /api/v1/update, danach GET /api/v1/update/status
  → Scanner: GET /providers, /providers/{id}/{version}/metrics, .../trades.csv
  → ingest: Quellenartefaktcache und Normalisierung
  → Kandidatenfilter, Fix-IDs und Top-N je Quelle
  → Parser und Engine, gegebenenfalls H1-Kursrekonstruktion
  → SQLite: Signal, Trade-Snapshot, Forensik und passende Berichte
  → Tabellenansicht
```

Stufe 0 aktualisiert die Monitore. Das anschließende Lesen einer Monitor-API ist ein anderer Vorgang als deren frischer Abruf bei der ursprünglichen Plattform. Zusätzlich gibt es den MQL5-Direktweg. Beim Audit war `listen_modus="beides"` konfiguriert; die heutigen direkten MQL-Weblisten wurden nicht neu abgerufen.

| Ansicht | Codekette | Erwartete Bedeutung |
|---|---|---|
| Ergebnisse | `db.list_catalog` → `pipeline.results_from_db` → `ScanResult.to_row` → `app_ui.results_to_dataframe` / `render_results_table` | Gespeicherte Workflow-Signale, letzte Sitzung oder historisches Laufarchiv; je gewählter Ansicht. |
| Alle Signale | Workflowbestand plus `katalog.katalog_resultate` → `workflow_stats_bulk` → `signal_statistik` → `alle_signale_ui.tabellen_zeile` | Auch reine Katalogsignale und separate Equity-Studien; ein sichtbares Signal muss noch keinen erfolgreichen Scan haben. |

Die zentrale Tabelle `signals` verwendet weiterhin eine numerische Signal-ID als Schlüssel. Die vollständige Identität `(quelle, signal_id)` ist eine bekannte offene Architekturaufgabe. Kollisionsschutz und Quellenzuordnung müssen bestehen bleiben; dieser Review verlangt keine nebenläufige Komplettmigration des Schemas.

## Evidenz und Grenzen

Folgende Nachweise wurden tatsächlich erhoben:

- Lokale GETs gegen alle fünf APIs; vollständige Pagination gegen deren jeweiliges gemeldetes `total`.
- 17 Trade-GETs: 13 gelieferte CSVs erfolgreich mit dem produktiven Parser gelesen, vier Vantage-404.
- Konsistente SQLite-Snapshots und lesender Abgleich vorhandener Artefakte.
- Isolierte Fehlerreproduktionen mit echten Anwendungsfunktionen beziehungsweise vorhandenen kompilierten Java-Klassen.
- 574 ausgewählte vorhandene Tests plus drei ergänzende UI-Tests, jeweils bestanden.

Es wurden **keine neuen produktiven Stufe-0-POSTs, Plattformdownloads, Voll-/Teilscans, LLM-Aufrufe oder Terminalstarts** ausgeführt. Die Ende-zu-Ende-Abnahme eines neuen produktiven Gesamtlaufs steht aus. Ein Test gegen `target/classes` belegt den geprüften kompilierten Code; er ersetzt keinen Nachweis, dass ein später gestarteter Prozess den gerade geänderten Build verwendet.

Begriffe in diesem Review:

- **Im Betrieb beobachtet:** Antwort einer tatsächlich laufenden lokalen API oder Eigenschaft des vorhandenen Datenbestands.
- **Isoliert reproduziert:** Fehlerablauf gegen echte Funktionen mit synthetischen Daten und kontrolliertem Ablauf; kein Nachweis eines bereits eingetretenen produktiven Schadens.
- **Korrekturvorschlag:** Noch nicht implementierte Richtung; das konkrete Design muss die Abnahmekriterien erfüllen.

## F1 Vantage kann vorhandene Altbestände nicht erneuern

**Priorität P1. Betroffenes Projekt: vantage. Aktueller Bestandsblocker plus isolierte Reproduktion.**

**Istzustand:** Alle 199 aktuell im Vantage-Katalog gelisteten IDs besitzen vorhandene CSVs mit Metadaten `version=1` und ohne `timeBasis=UTC`. Insgesamt wurden im lokalen TradeStore 611 solche Metavermerke gefunden. Vier tatsächlich abgefragte Exporte, IDs `1419494`, `1286742`, `1010186`, `1096166`, liefern HTTP 404. Es wurden nicht 199 einzelne HTTP-404-Antworten erhoben.

**Ursache:** Die Ablehnung eines Exports ohne belegte UTC-Zeitbasis ist erforderlich. Der normale Erneuerungspfad kommt jedoch nicht aus diesem Zustand heraus: `TradeStore.mergeHistory` lehnt einen vorhandenen unverifizierten Bestand ab. `saveTrades` ruft ebenfalls diesen Merge auf. Auch der reguläre Updatepfad lädt zunächst neu und ruft danach den blockierten Merge auf.

**Codeorte:**

- [TradeStore.mergeHistory](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:129).
- [TradeStore.saveTrades](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/store/TradeStore.java:85).
- [Update-Anbindung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/VantageMonitorApp.java:390).
- [UpdateJobRunner](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/src/main/java/de/vantagemonitor/update/UpdateJobRunner.java:205).

**Reproduktion:** Die Java-Probe erzeugt zunächst eine gültige synthetische Historie, setzt nur deren Metadaten auf den Altzustand und versucht anschließend eine gültige neue Lieferung über `mergeHistory` und `saveTrades`. Beide Aufrufe werfen `Vorhandene Historie nicht verifiziert; kein stilles Ueberschreiben`. Der alte Dateiinhalt bleibt unverändert.

**Sichere Korrekturrichtung:** Einen expliziten Erneuerungspfad mit gesicherter Archivierung/Quarantäne des Altbestands und einer getrennten neuen UTC-Historie bereitstellen. Bestehende Zeitstempel nicht ungeprüft zu UTC erklären und den UTC-Schutz nicht aufweichen. Ein erfolgreicher neuer Download ist außerdem kein automatischer Beleg für eine vollständige Lebenszeithistorie.

**Abnahme:**

1. Eine gültige neue Lieferung lässt sich trotz vorhandener v1-Historie sicher übernehmen.
2. Der alte Bestand bleibt gesichert und wird nicht mit unbelegter Zeitbasis in die neue Historie gemischt.
3. Abbruch, Fehler und unvollständige Lieferung verursachen keinen Verlust des alten Bestands.
4. Der neue Export hat belegte UTC-Metadaten und lässt sich über die Quellen-API sowie den Scannerparser lesen.
5. Der normale Einzel- und Updatepfad nutzt dieselbe geprüfte Erneuerungslogik.

**Belege:** [Bestandsinventar](nachweise/downloads_vantage_metadata.json), [Exportstichproben](nachweise/downloads_e2e_live.json), [Java-Probe](nachweise/downloads_VantageRefreshProof.java), [Laufergebnis](nachweise/downloads_vantage_freshness_runtime.txt).

## F2 Analyse und Persistenz können verschiedene Dateiinhalte verwenden

**Priorität P1. Betroffenes Projekt: SignalKiScanner. Deterministisch injiziertes Interleaving über echte Funktionen; kein produktiver Schadensnachweis und kein paralleler UI-Stresstest.**

**Fehlerablauf:**

```text
1. Ingest schreibt Trade-Datei A in einen veränderlichen Cachepfad.
2. Die Engine analysiert Datei A: 2 Trades, 50,0 % Winrate.
3. Ein manueller Nachladeweg ersetzt denselben Cachepfad durch Datei B.
4. Erst bei der Persistenz wird der unveränderliche Snapshot erstellt: Datei B.
5. Der Befund aus A erhält den SHA von B und wird beim DB-Reload akzeptiert.
```

Die isolierte Probe ergibt einen erfolgreichen Befund mit zwei Trades/50,0 %, aber einen gespeicherten Export mit drei Trades/66,7 %. Sie demonstriert den Dateitausch zunächst direkt und danach über `katalog.lade_signal_daten` → `ingest.hole_trades`, während das gemeinsame Scan-Lock gehalten wird. Der manuelle Nachladepfad erwirbt dieses Lock nicht. Das vorhandene Artefakt-RLock schützt den einzelnen Abruf, nicht das anschließende Analyse-/Speicherfenster.

**Codeorte:**

- [Analyse am Cachepfad](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:1795).
- [Späteres Speichern](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:2110).
- [Snapshot und Transaktion](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py:403).
- [Nachträgliche SHA-Bindung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py:395).
- [Ungesperrter manueller Button](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/app_pages/alle_signale.py:662).
- [Manueller Ladepfad](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py:349).

**Sichere Korrekturrichtung:** Die zu analysierenden Bytes vor der ersten Analyse unveränderlich sichern. Engine, ergänzende Berechnungen und Persistenz müssen denselben Inhalt verwenden. Den dazugehörigen SHA bei der Analyse bestimmen und bis zum Commit prüfen. Die Sperrkoordination des manuellen Nachladens ergänzen; eine UI-Sperre allein schützt nicht vor anderen Prozessen oder Dateiersetzungen.

**Abnahme:**

1. Ein Dateitausch zwischen Analysebeginn und Commit kann keinen Befund an andere Bytes binden.
2. Ein Regressionstest erzwingt diesen Ablauf deterministisch mit Synchronisationspunkten und prüft Tradezahl, Winrate, Befund-SHA, gespeicherten Snapshot und DB-Reload.
3. Entweder werden konsistente Werte zu A gespeichert oder der Lauf wird korrekt verworfen/wiederholt; ein Mischbefund A/B ist ausgeschlossen.
4. Unveränderte Eingaben und Transaktionsrollback funktionieren weiterhin. Spätere Änderungen am Downloadcache verändern bestätigte Snapshots nicht.

**Belege:** [Probe](nachweise/persistenz_probes.py), [Ergebnis](nachweise/persistenz_probes.json), [Persistenzbericht](nachweise/persistenz_README.md).

## F3 Die Katalogfrist unterdrückt MQL Tradeupdates

**Priorität P1. Betroffenes Projekt: MqlDownloader. Im kompilierten Code isoliert reproduziert; am Prüftag wurde kein produktiver Frische-Skip ausgelöst.**

**Istverhalten:** Die Scanner-Stufe 0 fordert `tradelisten=True` an. Ist der Katalogvermerk jünger als die konfigurierte Frist, standardmäßig 72 Stunden, beendet `starteUpdateKaskade` die gesamte Kaskade mit `done`. Auch die Trade-Aktualisierung entfällt. Die Frist soll jedoch nur den Katalogabruf ersparen.

**Codeorte:** [MqlDownloaderGui](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/src/gui/MqlDownloaderGui.java:151), [Scanner-Anforderung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/client_updates.py:218). Vertrag: [Stufe-0-Dokumentation](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/doc/23_stufe0-client-updates.md).

**Reproduktion:** Der tatsächlichen kompilierten GUI-Methode wird in einer Sandbox ein eine Stunde alter Katalogvermerk bei 72 Stunden Frist vorgelegt. GUI-Konstruktor und Downloadmanager werden nicht gestartet. Ergebnis: `katalogUebersprungen=true`, `state=done`; weder Katalog noch Trades werden angefordert.

**Sichere Korrekturrichtung:** Katalogfrische und Aktualisierung bekannter Historien unabhängig steuern. Ein übersprungener Katalog darf bei angeforderten Tradelisten den vorhandenen Providerbestand für Tradeupdates weiterverwenden.

**Abnahme:** Frischer Katalog plus `tradelisten=True` aktualisiert bekannte Historien; alter Katalog aktualisiert zuerst den Katalog und dann die angeforderten Historien. Der Fall ohne Tradeanforderung respektiert den bestehenden Protokollvertrag. Tradefehler, Abbruch und Loginprobleme dürfen nicht als sauberer Gesamterfolg erscheinen; tatsächliche Fortschrittszähler bleiben erhalten.

**Belege:** [Java-Probe](nachweise/downloads_MqlFreshnessProof.java), [Laufergebnis](nachweise/downloads_mql_freshness_runtime.txt), [Quellenbericht](nachweise/downloads_README.md).

## F4 Unvollständige Pagination kann Katalogzeilen löschen

**Priorität P1. Betroffenes Projekt: SignalKiScanner. Synthetisch mit produktiver Ingest-/SQLite-Kette reproduziert; die echten API-Paginationen waren beim Audit vollständig.**

**Ursache:** `ingest.hole_katalog` beendet sich bei einer leeren Seite auch dann erfolgreich, wenn `total` weitere Rohzeilen erwarten lässt. Das Erreichen von `max_seiten` gibt ebenfalls nur die bisherige Liste zurück. `katalog.sync` übergibt diese Liste als Vollkatalog an `db.katalog_upsert_many`, das fehlende IDs löscht.

**Reproduktion:** In einer temporären Datenbank enthält `katalog_signale` die IDs 1, 2 und 3. Die API meldet `total=3`, liefert zunächst 1 und 2 und danach eine leere Seite. Ergebnis: `geloescht=1`, `fehler=null`; ID 3 fehlt anschließend.

**Wirkung:** Betroffen ist die Tabelle **`katalog_signale`** und damit der Vollkatalog in „Alle Signale“. Diese Probe löscht keine `signals`-Zeile, Trade-Datei oder historische Forensik.

**Codeorte:** [hole_katalog](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py:71), [katalog.sync](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/katalog.py:79), [Vollersetzung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/db.py:855).

**Sichere Korrekturrichtung:** Einen ausdrücklichen Abschluss-/Unvollständigkeitsnachweis der Pagination bis zur Persistenz führen. Ein Teilkatalog darf keine Vollersetzung mit Löschung auslösen. Widersprüchliche Totals, Wiederholungen und Begrenzungen müssen sichtbar werden. Die erlaubte Behandlung eines unbekannten oder während des Abrufs veränderten `total` festlegen.

**Abnahme:**

1. Vorzeitige Leerseite, Seitenkappe, wiederholte Seiten und widersprüchliche Totals ergeben einen Fehler/Teilerfolg ohne Löschung des vorherigen Vollbestands.
2. Eine nachweislich vollständige Lieferung darf ausgeschiedene Katalog-IDs weiterhin regulär entfernen.
3. Vollständigkeit der Rohlieferung und anschließende Normalisierung werden getrennt geprüft. MQL liefert beim Audit 216 Rohzeilen; das korrekte Verwerfen von `test_1` ergibt 215 gültige IDs und ist kein Paginationfehler.
4. Eine fehlerhafte Quelle verhindert nicht die korrekte Verarbeitung anderer Quellen.

**Belege:** [Probe](nachweise/pagination_repro.py), [Ergebnis](nachweise/pagination_repro.json), [Mengenbilanz](nachweise/flow_inventory.json).

## F5 Der erklärende Zulu Historienhinweis wird nicht übernommen

**Priorität P2. Betroffene Projekte: SignalKiScanner und Feldvertrag mit zulumonitor. Liveantwort und Mapping direkt verglichen.**

Zulu liefert den Text in `TradesCompletenessNote`. `ingest.metrics_zu_stats` liest ausschließlich `CompletenessNote` nach `quelle_trades_completeness_note`. Deshalb fehlt der Text in der Anzeige. Die gesonderte Flagge `TradesTruncated` wird weiterhin übertragen.

**Konkreter Fall:** Zulu-Signal 430306 liefert 1164 gespeicherte Trades gegenüber einem Plattformgesamtwert von 8992. Der Quellenhinweis erklärt mögliche Kappung oder ein älteres Cachealter und warnt vor einem Vollständigkeitsschluss allein aus der Anzahl. Das Mapping ergibt einen leeren Text. Aus den beiden Zahlen allein lässt sich weder die exakte Zahl fehlender Positionen noch ein zusätzlicher Parserfehler ableiten.

**Codeorte:** [Zulu-Antwort](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/zulumonitor/src/main/java/de/zulumonitor/rest/RestApiServer.java:418), [Ingest-Mapping](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/ingest.py:408), [Anzeigetext](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/alle_signale_ui.py:159).

**Korrektur und Abnahme:** Den Feldvertrag vereinheitlichen oder beide belegten Feldnamen mit definierter Priorität unterstützen. Je einen Test für beide Feldnamen, fehlende Werte und die Übernahme bis zur Statistik-/Tabellenanzeige hinzufügen. Kappungsflagge, tatsächliche Tradezahlen und sonstige Qualitätsangaben bleiben erhalten.

**Beleg:** [Exportstichproben](nachweise/downloads_e2e_live.json), Abschnitt `zulu`, ID 430306.

## F6 Die Hilfe erklärt eine falsche Drawdownbasis

**Priorität P3. Betroffenes Projekt: SignalKiScanner. Bestätigter Textwiderspruch, kein nachgewiesener falsch befüllter Zahlenwert.**

Die Hilfe für „Max-Drawdown“ nennt Kursmessung oder Monitor als Basis. Der zugehörige Zahlenkanal verwendet ausschließlich gültige eigene H1-Equity-Messung. Monitor-DD ist Closing-DD und ein separater Kanal der harten Schranke.

**Codeorte:** [Hilfetext](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/app_ui.py:503), [Wertbildung](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/src/mqlkiscanner/pipeline.py:275).

**Korrektur und Abnahme:** Den Hilfetext an den tatsächlichen H1-Zahlenkanal anpassen. Wertbildung, Calmar-Nenner und die separate harte Drawdown-Schranke bleiben unverändert. Tooltip, Spaltenüberschrift und Detailerklärung dürfen keinen Monitor-Closing-DD als eigene H1-Equity-Messung darstellen.

## Datenzustände die von den Codefehlern zu unterscheiden sind

| Beobachtung beim Audit | Bedeutung für die nächste KI |
|---|---|
| 194 Workflow-Signale, 1454 gültige Quellenkatalog-IDs, 1477 Zeilen „Alle Signale“ | Zwei verschiedene Ansichten mit gewollter Vereinigung. 23 ältere Workflow-Signale liegen außerhalb des aktuellen Katalogs. |
| 0 von 194 Workflow-Ergebnissen mit aktueller vollständiger Forensik; 161 ausdrücklich veraltet | Score, eigene Rendite, belastbarer H1-DD, TrueRetDD und aktuelles Berichtsdatum sind dort jeweils 194-mal leer. Diese Werte nicht künstlich auffüllen. |
| 1354 separate Equity-Studien mit Version 19 und 218 mit Version 0 | Die Aussage über alte Workflow-Forensik darf nicht pauschal auf die separaten Studien übertragen werden. Version 19 allein ist kein Nachweis von Messqualität oder aktueller Tradebasis. |
| 128 Zeilen ohne Tradepfad; 242 USD-Sperren | Fehlende/gesperrte Messwerte sind nicht automatisch ein Mappingfehler. Gruppen können sich überlappen. |
| 15 Exporte mit Schlusszeit vor Öffnungszeit | Bewusste Finanzteilstatistik ohne DD-/Renditefreigabe. Ursprung der unplausiblen Daten nicht abschließend geklärt. |
| 10 lesbare Exporte ohne Trades | Hier ist Tradezahl 0 tatsächlich belegt; fehlende Werte anderer Zeilen sind nicht dasselbe. |
| Neuere lokale Quellenexporte als im Scanner-Cache | Reale Zustandsdifferenz; ohne neuen Scan kein weiterer nachgewiesener Cache-Codefehler. Beispiel Pelican 2014074: 15599 gegenüber 15340 Trades. |
| 3 verwaiste Analysezeilen vom 05.09.2026 zur ID 424242 | Historischer Integritätsrest, keine neu erzeugte verwaiste Referenz. Kein pauschales Löschen oder Zurücksetzen der Datenbank. |

Der Bestandsvergleich ergab **0 Mappingabweichungen** bei 2134 DB-Feldvergleichen, 194 Calmar-Prüfungen und 2232 Parser-/Statistikfeldvergleichen. Alle 193 registrierten Workflow-Trade-Dateien und 3094 Quellenartefakte hatten passende Hashes; alle 1550 Metrics-Dateien passende Signal-ID und Version. Die aktuellen Quellenkataloge zeigten keine quellenübergreifende numerische ID-Kollision. Das belegt weder generelle Fehlerfreiheit noch aktuelle vollständige Plattformhistorien.

Die detaillierte Feldherkunft steht in [tabelle_spaltenmapping.md](nachweise/tabelle_spaltenmapping.md), Null-/Nullwertprofile in [tabelle_bestand.json](nachweise/tabelle_bestand.json), die Statistikdiagnosen in [tabelle_statistik_diagnosen.json](nachweise/tabelle_statistik_diagnosen.json).

## Reproduktion und vorhandene Tests

Alle folgenden Befehle sind für PowerShell gedacht. Die Python-Proben erwarten ihren vorhandenen Ort innerhalb des Scanner-Repos, weil sie den Projektpfad relativ zur eigenen Datei bestimmen.

```powershell
$reviewRepo = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner'
$reviewEvidence = Join-Path $reviewRepo 'doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise'
Set-Location -LiteralPath $reviewRepo

python -m pytest tests/test_client_updates.py tests/test_downloader_client.py tests/test_quellen.py tests/test_quellen_stringzahlen.py tests/test_stufe0_ui.py tests/test_gesamt_review_hub_fixes.py -q -p no:cacheprovider

python -m pytest tests/test_second_review_pipeline.py tests/test_review10_db.py tests/test_glm53_scanner_filter_finance.py tests/test_handover_source_currency.py tests/test_studien_waehrungsnachweis.py tests/test_scan_retry.py tests/test_pipeline_export_retry.py tests/test_external_review_ingestion.py -q -p no:cacheprovider

python -m pytest tests/test_ergebnis_gewinn_retdd_ui.py tests/test_alle_signale_seite.py tests/test_alle_signale_batch_refresh.py tests/test_alle_signale_performance.py tests/test_katalog.py tests/test_app.py::test_results_db_marks_refreshed_signals_as_neu -q -p no:cacheprovider

python -m pytest tests/test_kursdaten_persistenz.py tests/test_kursdaten_nachladen.py tests/test_kursdaten_terminalwechsel.py tests/test_kursdaten_vantage_portable.py tests/test_kursdaten_stundengrenze.py tests/test_einzelstudie_lauf_lock.py tests/test_admin_markt_scan_lock.py tests/test_markt_scan_lock.py tests/test_equity_zeitbasis_pipeline.py tests/test_equity_h1_paritaet.py tests/test_equity_skip_diagnose.py tests/test_fehlende_kursdaten.py tests/test_parser_export_artefakte.py -q -p no:cacheprovider

python -m pytest (Join-Path $reviewEvidence 'tabelle_audit_tests.py') -q -p no:cacheprovider
```

Die Audit-Ergebnisse dieser Gruppen waren 136, 173, 104, 161 und 3 bestandene Tests. Dies ist keine vollständige Testsuite. `tests/conftest.py` isoliert Daten-/Secrets-/Settingspfade und sperrt echte HTTP-Requests. Im Audit funktionierte `python` mit pytest 9.1.1 und Streamlit 1.63.0; `py -3.12` wählte einen anderen Interpreter ohne pytest.

Die isolierten Python-Fehlerproben lassen sich so ausführen:

```powershell
python (Join-Path $reviewEvidence 'persistenz_probes.py')
python (Join-Path $reviewEvidence 'pagination_repro.py')
```

**Wichtig:** `persistenz_probes.py` gibt sein Ergebnis-JSON nur auf stdout aus. `pagination_repro.py` überschreibt seine Ergebnisdatei `pagination_repro.json`. Beide Proben enthalten Assertions auf den ursprünglichen Fehler. Exitcode 0 bedeutet dort „Fehler erfolgreich reproduziert“. Für eine Behebung separate Regressionstests mit dem geforderten korrekten Verhalten erstellen. Originale Auditnachweise vor einer erneuten Ausführung erhalten; ein nach der Korrektur scheiternder ursprünglicher Fehlernachweis ist nicht automatisch eine Regression des Produkts.

Für die Java-Proben werden ein JDK und die beim Audit vorhandenen kompilierten Projektklassen benötigt. Die MQL-Probe nutzt Reflection/`Unsafe` zur Konstruktion ohne GUI-Konstruktor; sie ist ausschließlich ein Audit-Hilfsprogramm.

```powershell
$reviewJavaTemp = Join-Path $env:TEMP ('signal_review_java_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $reviewJavaTemp | Out-Null
$reviewMqlCp = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/classes;D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
$reviewVantageCp = 'D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/target/classes'

javac -cp $reviewMqlCp -d $reviewJavaTemp (Join-Path $reviewEvidence 'downloads_MqlFreshnessProof.java')
javac -cp $reviewVantageCp -d $reviewJavaTemp (Join-Path $reviewEvidence 'downloads_VantageRefreshProof.java')

Push-Location -LiteralPath $reviewJavaTemp
try {
    java '-Djava.awt.headless=true' -cp "$reviewJavaTemp;$reviewMqlCp" downloads_MqlFreshnessProof
    java -cp "$reviewJavaTemp;$reviewVantageCp" downloads_VantageRefreshProof
} finally {
    Pop-Location
}
```

Auch diese Java-Proben bestätigen bei Erfolg den alten Fehlerzustand. Sie erzeugen nur synthetische Fixtures unter dem gewählten Tempverzeichnis. Ein Source-Fix verändert bereits kompilierte Klassen nicht automatisch: Vor der Fix-Abnahme den vorgesehenen Build ausführen und für einen kontrollierten Lauf die richtigen Prozesse mit diesem Build starten.

## Vorgehen bei einer anschließenden Behebung

1. Arbeitsstände und Anweisungen prüfen; fremde lokale Änderungen erhalten. Die Audit-Commits und Quellenhashes im [ursprünglichen Manifest](nachweise/manifest.json) mit dem jetzigen Zustand vergleichen.
2. Die neue Drawdownvorgabe berücksichtigen: feste 30-%-Begrenzungen entfernen, ohne ungefragt einen neuen Standardwert festzulegen. Diesen Änderungsauftrag getrennt von den sechs ursprünglichen Auditfindings nachweisen.
3. F1 und F2 zuerst unter den Fehlerkorrekturen bearbeiten. Bei Bedarf parallel in getrennten Projekten beziehungsweise Dateien arbeiten. Neue Tests sollen die geforderte sichere Erneuerung und den erzwungenen Dateitausch absichern.
4. F3 und F4 beheben, anschließend F5 und F6. Korrekturen auf die beschriebenen Ursachen begrenzen und die übrigen fachlichen Regeln beibehalten.
5. Je Änderung gezielte Regressionstests und die betroffenen bestehenden Gruppen ausführen. Die Auditbehauptung „577 bestanden“ nicht als Ergebnis eines neuen Laufs übernehmen.
6. Anschließend einen kontrollierten produktiven Gesamtlauf zur Betriebsabnahme durchführen, sobald dies Teil des Auftrags ist: aktive Quellen aktualisieren, Job-IDs/Teilfehler prüfen, Datenstände und Mengen bilanzieren, Rohdaten → Snapshot → DB → beide Tabellen abgleichen. Vorhandene Lauf-Locks und Rate-Limits einhalten.
7. Pro Finding dokumentieren: bestätigt/widerlegt, konkrete Änderung, neue Testnachweise, richtige Build-Version und beobachtetes Betriebsergebnis. Ein Kompiliererfolg oder passender SHA allein schließt die Betriebsabnahme nicht ab.

Beim Umschreiben dieses Reviews waren zusätzlich die unversionierten Dateien `tests/test_audit_identitaet_20261018.py` und `tests/test_audit_tabellen_20261018.py` vorhanden. Sie sind nicht Teil des dokumentierten ursprünglichen 577-Test-Laufs und wurden für diese Textübergabe nicht ausgeführt oder verändert. Vor einer Behebung Inhalt und Zugehörigkeit prüfen.

## Ablage und Weitergabe

Die Übergabe liegt unter `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/SignalKiScanner/doc/reviews/2026-10-18_download_datenfluss_pruefung/KI_UEBERGABE.md`. Der [ursprüngliche Review](README.md) und der Unterordner `nachweise` enthalten die Details. Für eine andere KI mit Dateizugriff diesen gesamten Reviewordner bereitstellen. Ohne Dateizugriff enthält dieses Dokument bereits Ursachen, Codeorte, Sollverhalten und Abnahmekriterien; die genannten Nachweise müssen für eine unabhängige Verifikation zusätzlich zugänglich sein.

Produktive Rohtrades, Zugangsdaten und SQLite-Dateien sind keine Reviewanhänge. Die privaten temporären Datenbankkopien aus dem Audit sind nicht auf einem anderen Rechner vorauszusetzen. Neue konsistente Kopien kann `nachweise/inventory_probe.py` mit der SQLite-Backup-API erzeugen. Eine zusätzliche alte Tempkopie blieb nach einer automatisch blockierten Löschung außerhalb des Repos erhalten; Details stehen im ursprünglichen Review. Diese Aufräumbeobachtung ist keine zusätzliche fachliche oder technische Freigabeanforderung für die beschriebenen Fixes.
