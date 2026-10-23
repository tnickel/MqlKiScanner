# Kritische Prüfung des Z.ai Übergabetextes

Stand: 18.10.2026. Prüfobjekt ist die im Chat eingefügte Übergabeanweisung mit dem Einstieg `KI_UEBERGABE.md`, der Angabe „276 Tests“ und dem Auftrag, F1/F3 sowie mehrere Tabellenpunkte noch umzusetzen. Der Text enthält keine neuen eigenen Codebefunde, Reproduktionen oder Testläufe. Sein Arbeitsauftrag ist gegenüber dem heutigen Arbeitsbaum veraltet.

## Bewertung der Aussagen

| Aussage oder Auftrag | Ergebnis gegen den aktuellen Arbeitsbaum |
|---|---|
| F1 Vantage und F3 MqlDownloader noch implementieren | Bereits umgesetzt und gebaut. Vantage erneuert unverifizierte Historien ohne Übernahme ihrer alten Zeitbasis; MQL aktualisiert angeforderte Trades auch bei frischem Katalog und umgeht dafür den lokalen Dateialterscache. |
| F2/F4/F5/F6, Quellenschutz und frei konfigurierbare DD-Grenze prüfen | Sinnvolle Prüfpunkte, aber keine neuen Fehlerbehauptungen. Snapshot/SHA-Vertrag, vollständige Pagination, Zulu-Hinweis, H1-Erklärung und Quellenvertrag sind implementiert. Der zusätzliche Legacy-Randfall unten wurde bei dieser Gegenprüfung gefunden. |
| M-1, Stufe-0-Abbruchspur, CSV-Spalten und Linkkopf noch beheben | Bereits korrigiert: historischer Roh-DD ausdrücklich veraltet, dauerhafte Start-/Job-/Abbruchspur, gemeinsamer fachlicher Datensatz für Anzeige und CSV, neutraler Kopf „Signal-Link“. |
| `last_checked_at` und neuester Trade je Artefakt | Tatsächlich noch offen. `fetched_at`, Client-Jobzeit und jüngster Trade sind verschiedene Zeitbegriffe. Diese Metadatenerweiterung ist kein Nachweis eines neu gefundenen Downloadfehlers; auch ihre spätere Speicherung würde allein keine vollständige Plattformhistorie beweisen. |
| 276 Tests als aktueller Stand | Überholt. Der letzte vollständige Scannerlauf umfasst 2.499 bestandene Fälle; die aktuellen Java-Nachweise umfassen MQL 148 und Vantage 88 bestandene Fälle. Der hier ergänzte kleine DB-Fix ist gesondert getestet, siehe unten. |
| Nur Statusblock und Designregeln aus `AGENTS.md` seien bindend | Zu eng. Alle anwendbaren aktuellen Projektanweisungen gelten, darunter die technischen Regeln und Prüfvorgaben. Die ausdrücklich als historisch markierte Chronik ist entsprechend einzuordnen; aktuelle Nutzerentscheidungen gehen älteren Regeln vor. |
| Vor dem Review committen | Optional. Ein Review kann den Commit, den vollständigen Arbeitsbaum einschließlich unversionierter Dateien und Inhalts-Hashes als Basis festhalten. Ein Commit ist keine technische Voraussetzung und wurde hier nicht vorgenommen. |
| Eine Datei genügt | Als Einstieg und Orientierung ja. Eine unabhängige Code- oder Betriebsabnahme benötigt zusätzlich die relevanten Quellen und Belege. Ohne Dateizugriff kann die nächste KI die zitierten Tests und Laufzeitbehauptungen nicht selbst nachprüfen. |

Der aktuelle Umsetzungsbericht ist die [Fremdreview-Nachprüfung](../fremdreview_nachpruefung/README.md). [BEHEBUNG.md](../BEHEBUNG.md) und die längeren Auditabschnitte in [KI_UEBERGABE.md](../KI_UEBERGABE.md) halten frühere Stände fest. Die darin enthaltenen alten Testzahlen und Codeorte nicht als neue Laufnachweise übernehmen. Die ursprünglichen Fehlerproben erwarten teilweise ausdrücklich den alten Fehlerzustand; ihr Erfolg ist keine Fix-Abnahme.

Vor dem Zusatzfix stimmten alle 55 im jüngsten Manifest erfassten Quell-/Test-/Anweisungsdateien, alle 56 dort erfassten Nachweisdateien und die 50 ursprünglichen Auditbelege. Die älteren Manifeste bleiben unverändert. Das ältere Übergabemanifest passt weiterhin zu seinem Übergabetext; sein `AGENTS.md`-Hash gehört jedoch zum damaligen Anweisungsstand. Für den späteren Stand ist das jüngere Manifest maßgeblich.

## Zusätzlich bestätigter Legacy-Quellenfehler

`db.upsert_signal` prüfte abweichende vorhandene Quellen nur bei wahrheitswertigem Altlabel. Bei einem bestehenden `NULL` oder `''` konnte daher eine explizite fremde Quelle denselben Datensatz umetikettieren. Ein Altlabel `' '` blockierte dagegen sogar eine korrekte explizite Aktualisierung aus `mql5`. Die bestehende Quellen-/Studienprüfung behandelt diese drei Altwerte bereits als Legacy-MQL5; die Migration bezeichnet den ursprünglichen Bestand ebenfalls als MQL5.

Die Reproduktion umfasst beide Schreibschnittstellen (`upsert_signal`, `store_scan_result`) und alle drei Altwerte. Vor der Korrektur scheitern sechs neue Testfälle: vier wegen erlaubter Fremdzuordnung und zwei wegen gesperrter passender Zuordnung. [Vorheriges JUnit-Ergebnis](legacy_quelle_before.xml), [Befehl und Eingabehashes](legacy_quelle_before_command.json).

Der gemeinsame Schreibpfad normalisiert jetzt ausschließlich vollständig leere Altlabels zu `mql5`, bevor er die explizit behauptete Quelle vergleicht. Ein fremdes Update wird verworfen; Signal und vorhandene Forensik bleiben unverändert. Ein ausdrücklich zugeordnetes MQL5-Update bleibt möglich. Nichtleere Labels behalten den bisherigen exakten Vergleich. Zwei zusätzliche Fälle sichern die Kompatibilität von Neuanlage und Folgeupdate mit demselben nichtleer gepolsterten Quellenkürzel. Änderungen betreffen ausschließlich `src/mqlkiscanner/db.py` und `tests/test_source_identity_contract.py`. Kein Schema, keine Bewertung und keine produktive Zeile wurden migriert. Eine tatsächlich falsch beschriftete Fremdquelle dürfte nur durch eine gesondert belegte Migration korrigiert werden.

Der Randfall wurde mit temporären Testdaten bestätigt. Ein entsprechender produktiver Schaden oder externer Angriff ist damit nicht nachgewiesen.

## Abnahme und Reichweite der Nachweise

**Nach dem Zusatzfix: 150 gezielte Tests bestanden**, einschließlich der acht neuen Fälle und bestehender Quellen-, Snapshot-, SHA-, DB-, Pipeline-, Studien- und Währungsregressionen. [JUnit](legacy_quelle_final.xml), [Log](legacy_quelle_final.log), [genauer Befehl und getestete Quellhashes](legacy_quelle_final_command.json). Der Exitcode ist 0. Die bestehende Suite von 2.499 Fällen wurde nach dieser kleinen Änderung nicht vollständig wiederholt; die neue Testzahl wird weder mit ihr noch mit überlappenden früheren Gruppen addiert. Der vorherige 148er-Zwischenlauf ist unter `legacy_quelle_intermediate_148*` erhalten; die zwei später ergänzten Kompatibilitätsproben stehen unter `legacy_quelle_padded_before*`.

Die vorherige vollständige Scannerregression ist in drei disjunkten JUnit-Dateien mit 916, 828 und 755 Fällen dokumentiert. Ihre Testidentitäten entsprechen exakt der vollständigen Sammlung; vier kostenpflichtige LLM-Fälle waren gemäß Standardkonfiguration abgewählt. MQL 148 und Vantage 88 sind unveränderte vorhandene Java-Testnachweise; in diesem Durchgang wurden weder Java-Code noch Pakete geändert und keine Maven-Neuläufe ausgeführt. Die Quellen- und Artefakt-Hashes wurden erneut geprüft.

Das [Prüfmanifest](manifest.json) bindet die neuen Belege und die zwei geänderten Dateien, prüft die unveränderten älteren Belege und weist die beiden erwarteten Abweichungen zum vorherigen Quellenmanifest aus. Historische Vollregression und gezielte Abnahme nach dem Zusatzfix bleiben dabei getrennt.

## Tatsächlich offene Aufgaben

Offen bleiben die vollständige zentrale Identität `(quelle, signal_id)`, die gesonderte Artefakt-Frischemetadaten-Erweiterung und die bereits dokumentierten Kontraktnachweise für GER40FT/UK100FT. Aktuelle Quellenkonflikte werden abgewehrt; ID-weite Kommentare, Markierungen und Fix-IDs sowie eine lückenlose historische Studienbesitzkette sind damit nicht vollständig umgestellt.

Die produktive Betriebsabnahme erfordert die Verwendung der neuen Builds, tatsächliche Quellenaktualisierung und anschließenden Scanner-/Tabellenabgleich. In diesem Durchgang gab es keine produktiven API-Aufrufe, Update-POSTs, Downloads, Datenbankänderungen, Terminalstarts oder Modellaufrufe. Die frei konfigurierbare DD-Grenze, Jahres-Calmar, H1-Nenner und SL-Neutralität wurden nicht verändert. Die zurückgestellten Monitor-Integrationen bleiben zurückgestellt.
