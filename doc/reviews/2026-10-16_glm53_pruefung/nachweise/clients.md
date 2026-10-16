# GLM-5.3-Prüfung: Scanner Filter, Identität und Finanzdaten

Stand: geprüft gegen Scanner-HEAD `a483998`, anschließend Arbeitsänderungen ohne Commit/Stage. Der Fremdtext bezieht sich auf `80d4692` und ist deshalb kein aktueller Fehlernachweis. Alle Repros verwenden synthetische Daten. Kein Login, LLM-Aufruf, MT-Terminalstart oder Eingriff in Nutzerdaten/Settings/Produktiv-DB.

## Geprüfte Befunde

| Fremdpunkt | Aktueller Befund und Korrektur | Evidenz/Grenzen |
|---|---|---|
| SYN-3 | Bestätigt als Identitätsfehler: Crawler behielt bei derselben numerischen ID zuletzt MT4; gemischte Kandidaten konnten zwei Plattformen unter einem DB-Schlüssel behalten. Plattformvarianten bleiben jetzt bis zur Prüfung erhalten; mehrdeutige IDs werden ausdrücklich verworfen, identische Spiegel nur einmal gewählt. Bestehende MT4/MT5-Zuordnung wird vor HTTP/Persistenz gegen Plattformwechsel geschützt. | Synthetische gleiche ID mit MT4+MT5: vorher ein MT4-Datensatz; nachher zwei erkannte Varianten und keine uneindeutige Auswahl. Keine Composite-PK-Migration, keine Behauptung tatsächlich kollidierender öffentlicher MQL-Signalnummern. |
| FLT-3 | Bestätigt: aktuell weißer Timeout ließ ein zuvor grünes/gelbes Signal aus `teilscan_ziel_ids` fallen. Bei fehlgeschlagenem weißem Ergebnis entscheidet jetzt die letzte erfolgreiche Farbchronik über erneute Auswahl. | Ergebnis bleibt weiß; kein alter Grünstatus wird wieder freigegeben. Noch nie bewertete weiße Signale und zuletzt erfolgreich rote Signale bleiben außerhalb. Regression einschließlich Persistenz und DB-Reload. |
| FLT-6 | Teilweise bestätigt: `pipeline.ampel_for` war bereits auf 0; Matrix, Regelwerk, TradeServer-Sync und Detail-Badges hatten noch 5. | Mit partiellem Settings-Dict `{}` ergab 1 % eigene Monatsrendite Gate-Grün, aber Matrix-Gelb. Alle Fallbacks jetzt 0. Explizit konfigurierte andere Schwellen bleiben wirksam. |
| FIN-7 | Bestätigt: `1000 USC` und `1000 EUR` wurden als `initial_deposit_usd=1000` übernommen. Native Beträge werden als `*_account` plus belegter `account_currency` erhalten. USD-Felder gibt es nur bei einheitlich belegtem USD. Direkte MQL-USD-Forensik und unabhängige Einzel-/Batchstudien sperren USC, Fremdwährung und unbekannte/mehrdeutige Einheit vor Kurs-/FX-Aufrufen. | Keine erfundene Umrechnung. Plattform-Prozentfelder bleiben sichtbar. Das Fremdreview unterschätzt den möglichen Effekt: USD-Floating und native Kontobeträge hätten unterschiedliche Einheiten; dann sind auch gemischte DD-Prozente nicht invariant. Quellen-APIs behalten ihren dokumentierten USD-Exportvertrag; lokale CSV-Demo ihren ausdrücklichen Modellvertrag. |
| FIN-6 | Kontextlücke bestätigt, keine neue mathematische Gate-Regel: grünes Urteil und Calmar-Matrix erklären jetzt fehlende Intrabar-Extrema, exportierte geschlossene Positionen und Referenzkurse ohne Ausführungsspread. | DD kann unterschätzt und Calmar überschätzt sein. Eine garantierte mathematische Untergrenze für das echte Konto folgt bei anderer/virtueller Kapitalbasis, Teilmessung oder fehlenden Positionen nicht. Die pauschale GLM-Untergrenzenbehauptung ist verworfen. Akzeptierte H1-/Teilfreigabe unverändert. |
| S7 | Kein aktueller bestätigter Pollution-Fehler. Der genannte `WindowsPath.lower`-Defekt ist bereits durch `path = str(path)` vor `.lower()` behoben. | Neue PathLike-Regression und kombinierte T12-/Finanz-/UI-Tests prüfen den aktuellen Stand. Historische einzeln grüne Tests beweisen ohne identifizierten Polluter keine Testpollution. Root führt zusätzlich die Gesamtsuite aus. |

Vor Änderungen scheiterten alle elf anfänglichen synthetischen Regressionen an den erwarteten Abweichungen; Testaufbaufehler wurden davor korrigiert. Danach wurde die Regressionen-Datei um Persistenz-, Währungs-/Studien-/Terminal- und PathLike-Fälle erweitert.

## Zusätzlich von Root beauftragt

- `FORENSICS_VERSION=18`: alte möglicherweise falsch als USD bezeichnete Workflow-Befunde müssen neu geprüft werden. Studien-Sessioncache nutzt bereits dynamisch diese Version; der persistente Alle-Signale-Cachemarker ist jetzt ebenfalls dynamisch statt hart `forex17`.
- `report_basis_for` enthält SHA-256 der zentralen `BAUSTEINE` als kanonisches JSON (sortierte Schlüssel, UTF-8, feste Separatoren). Geänderte zentrale Promptregeln invalidieren alte KI-Berichte. Keine Secrets fließen in diesen Hash ein.
- Währungsbeleg wird auf `ScanResult`, im Stats-Audit und beim DB-Reload mitgeführt. Unbekannte historische MQL-Einheit wird nicht positiv als USD interpretiert.
- Gegenprüfung durch den Quellen-Agenten: SHA-passende Studien werden auch beim Übernehmen in `studie_anwenden` für unbekannte/USC-MQL-Einheit gesperrt; der Sitzungscache unterscheidet Währung und Live/Demo. Die regulären DB-Getter filtern ältere Studien bereits über `forensics_version`; dieser Mechanismus wurde nicht verändert. Eine ungefiltert manuell übergebene v17-Studien-Dictionary bei aktuellem USD ist ohne echten Consumerpfad kein zusätzlich belegter Produktfehler. Unabhängige Vorher-/Nachher-Belege: `fin7_peer_probe_results.json`, `fin7_peer_probe_after.json`.

## Dateien

Produktcode: `pipeline.py`, `fix_signale.py`, `mql5/crawler.py`, `mql5/signal_stats.py`, `ampel_matrix.py`, `regelwerk.py`, `tradeserver_sync.py`, `app_ui.py`, `analysis_version.py`, `equity_studie_ui.py`, `studien_batch.py`, `app_pages/alle_signale.py`.

Neue Regressionen: `tests/test_glm53_scanner_filter_finance.py`. Bestehende synthetische Pipeline-Fixtures, die echte USD-Analyse erwarten, tragen nun explizit `account_currency=USD` bzw. USD-HTML-Geldwerte. Alte 5-%-Grenztests setzen 5 explizit; Defaulttests prüfen 0.

## Testnachweise

- Git-Archiv von `a483998` plus ausschließlich Code-/Testoverlay unter `clients_snapshot`; Test-DBs und Ausgabedaten in pytest-Tempverzeichnissen, externe Requests gesperrt.
- Pipeline/Retry/Persistenz/Stop-Zielgruppe: **202 passed, 147,64 s**, `clients_targeted.log`, `clients_targeted.xml` (vor anschließender Erweiterung der unabhängigen Studien-Währungssperren).
- Finanz-/Studien-/Quellen-/UI-/T12-Zielgruppe: **313 passed, 192,46 s**, `clients_finance_ui.log`, `clients_finance_ui.xml`.
- Finale Delta-Gruppe einschließlich der Nachsicherung von Studienübernahme/Sitzungscache, Quellen-Kontraktnachmessung, Übersicht, T12 und UI: **109 passed, 11,41 s**, `clients_final_delta.log`, `clients_final_delta.xml`.
- `git diff --check`: erfolgreich. Kein Commit, Stage oder Push durch diesen Agenten. Produktcode-Freeze an Root gemeldet; Gesamtsuite bleibt Roots abschließende Prüfung.

Konservative Einschränkung: Nicht-USD/unklare direkte MQL-Konten bleiben ohne bewiesenen Umrechnungsvertrag für USD-Floating-Modelle gesperrt. Numerisch mehrdeutige Plattformidentitäten bleiben bis zu einer eigenständigen Composite-Identitätsmigration ausdrücklich außerhalb der Auswahl.
