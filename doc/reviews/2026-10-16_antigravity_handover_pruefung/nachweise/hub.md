# Antigravity + vollständiger GLM-Katalog: Hub/LLM/SYN-Gegenprüfung

**Finaler eigener Stand eingefroren,121 gezielte Tests grün.** Die früheren Monatsbudget-, Calmar-Prompt-, Versions-/Jobidentitäts- und PDF-GET-Fehler sind bereits behoben. Bestätigte bisher offene Restfehler wurden minimal korrigiert: Retry-Audit/Kostenmetadaten, atomare Settings mit erkennbarem Lesefehler, echte Sync-Start-/Endprotokollierung und Parallelitätsschutz, letzte Quellenupdates ohne500-Zeilenfenster, Fremdtextschutz der Agenten, belegte NEU-Markierung und Workflow-Sperre für Tiefenbatches. REST legt die bestehende Bewertungs-/Berichtsbasis jetzt offen. Keine fachlichen Bewertungsregeln oder Produktionssettings geändert.

## Grundlage und Abgrenzung

Geprüfte Quellen:

- `C:/Users/tnickel/.gemini/antigravity-ide/brain/22de581d-4dcb-48ef-aefd-6d842563d491/review_bericht_signalkiscanner_hub.md`
- `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/REVIEW_2026-10-16_Gesamtsystem_Befundkatalog.md`
- Nachgereichter A–G-Bericht `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/REVIEW_2026-10-16_Gesamtsystem_Bericht.md`.

Ausgangs-HEAD Scanner: **`a3112c2f5fe0d692d549b41fb9fce430372d7770`**, Arbeitsbaum bei Beginn sauber. Die Fremdberichte beschreiben ältere Stände (`80d4692`, Forensik16 und damalige Testzahlen). Ihre Aussagen sind Hypothesen über den aktuellen Stand, keine neuen Laufnachweise.

Eigener Scope: alle LLM-/SYN-IDs, Agenten/LLM/Config/REST/DB/Sync und zugehörige Tests, zusätzlich von Root freigegebene Workflow-Sperre in `tiefen_batch.py` und Hilfe in `help_settings.py`. `pipeline.py`, `ingest.py` und fachliche Versionsänderung **19** gehören Root und wurden durch mich nicht editiert. Der eigene isolierte Snapshot enthält den Versions19-Nachtrag zur Prüfung dynamischer Versionsbezüge; Root prüft die gesamte kombinierte Währungs-/Filterkorrektur separat.

Keine Produktionssettings, Produktiv-DBs, Zugangsdaten, Logins, Plattformaufrufe oder kostenpflichtigen Modellaufrufe verändert/ausgeführt. Tests benutzen temporäre Speicher, synthetische Daten und HTTP-Fakes/Mocks. Keine Stages, Commits oder Pushes. Streamlit-Arbeit verwendet den bereits gelesenen lokalen `developing-with-streamlit`-Skill und dessen AppTest-/Markdown-Referenzen; keine UI-Server oder Browser gestartet.

## LLM-IDs einzeln

| ID | Aktueller Befund, Entscheidung und Belege |
|---|---|
| **LLM-1** | **Bereits behoben.** `portfolio_statistik.statistik` nennt konfigurierten Jahres-Calmar und Monats-RetDD ohne eigenes Gate. `test_finance_review_20261016.py::test_f9_portfolio_hint_obeys_current_annual_setting` sichert die abweichende Schwelle4,25 ab. Kein erneuter Prompt-/Regelumbau. |
| **LLM-2 / FLT-1** | **Bereits behoben.** `llm/bausteine.REGELN_RETDD` erklärt Score zur Zusatzinformation, kein Grün-/Empfehlungsgate. Vorlagen-/Default- und GLM-Promptregressionen vorhanden. |
| **LLM-3** | **Bereits behoben.** `agenten/budget.reserve` prüft Tag und Monat mit SQLite-Reservierung vor HTTP; alle Rollen und autonome Scans hängen den Ledger an. Monatslimit, parallele Reservierungen, Retries und Periodenwechsel sind regressionsgetestet. |
| **LLM-4** | **Autonome Kostenbuchung bereits behoben; manueller Budgettopf ist bewusst getrennt.** `scan_launcher.py:175` hängt den Agentenledger an; GUI-Läufe haben ihr eigenes Laufbudget. Die Hilfe bezeichnete autonome reguläre Scans noch missverständlich als außerhalb des Ledgers; Text korrigiert. **Echter Restfehler behoben:** `tiefen_batch.batch_starten` versprach eine Workflow-Sperre, prüfte aber nur den eigenen Prozess-Thread. Jetzt ein Startmutex über Streamlit-Reloads und dasselbe prozessübergreifende Workflow-Lock wie GUI/autonome Scans, erworben vor Threadstart und in allen Worker-Endpfaden freigegeben. Keine Ausweitung des Agentenbudgets auf manuelle Calls. |
| **LLM-5** | **Dokumentierte Funktionsgrenze, kein neu bewiesener Defekt.** Betreuer verarbeitet weiterhin MQL5; Quellen werden gezählt/übersprungen. Reguläre Quellen-Scans und Ampelwatcher bleiben davon getrennt. Kein neuer Quellen-/Realmonitor-Betreuer integriert. |
| **LLM-6** | **Bestätigt und behoben.** Normale GUI-Calls hielten verworfene `length`-Antworten nicht dauerhaft fest; Komponententokens wurden bei Retry nicht summiert. Neue `llm_attempts`-Audittabelle erhält Antworttexte/Rawusage pro HTTP-Versuch und gemeinsame Call-ID; `total_tokens`, `prompt_tokens`, `completion_tokens`, `reasoning_tokens` werden jeweils über die gültigen Antwortversuche addiert. Reasoningtokens werden nicht nochmals auf Completion/Total aufgeschlagen. Bei Agenten gab es bereits den Versuchledger; die neue Tabelle ist ausschließlich Audit, keine zweite Kostenquelle. |
| **LLM-7** | **Alte Inkonsistenzbehauptung am aktuellen Code überholt; Transparenzrest ergänzt.** `restore_current_reports` prüft aktuellen Basis-/Kriterienhash, löst unpassende aktuelle Texte und extrahiert Kurzfassung aus dem aktuellen Bericht neu. Alte Historie bleibt erhalten. REST ergänzt `ampelBasis.mode`, wirksame Schwellen, `berichteBasis`, `berichtHinweis`; Defaultprovider und Payload teilen dieselbe Settingsaufnahme. Keine neue Bewertung und keine pauschale Berichtslöschung. |
| **LLM-8 / SYN-1** | **Bereits behoben.** Berichtsbasis enthält `min_calmar_jahr` und zentrale Promptregel-Hashes. Schwellen-/Regeländerungen lassen unpassende Empfehlungen nicht unverändert aktuell. |
| **LLM-9** | **Fehlender gemeinsamer Schutzblock bestätigt und ergänzt.** `rollen_prompts.fuellung` stellt den zentralen Fremdtextblock vor jede der sechs Agentenrollen, auch bei editierten Vorlagen. Eingefügte Namen/Kommentare werden weiterhin nicht nochmals als Slots interpretiert. Deterministische Whitelist/Regex/Enginegrenzen bleiben bestehen. Das beweist die gelieferten Schutzanweisungen, keine empirisch garantierte Resistenz eines LLM gegen jede Promptinjection. |
| **LLM-10** | **Kein neuer bestätigter Enginefehler.** Verdict-Sanitizer verhindert verbotene Aufwertungen. Die letzte Fundstelle im unstrukturierten Urteilfallback bleibt eine dokumentierbare Heuristik; ohne konkreten widersprechenden Output/Vertrag wird daraus kein neuer numerischer Bewertungsfehler erfunden. |
| **LLM-11** | **Kleine echte Auditabweichung behoben.** `llm_runner.py` ersetzte fehlende Einzelcall-Tokens durch den kumulierten Clientzähler. Nun0 als unbekannte Einzelangabe statt falscher Voll-Laufsumme; neue Regression speichert drei erfolgreiche Fakeantworten ohne Usage jeweils mit0. Die konkreten Antworten/Kosten realer Clients stehen im separaten Versuchaudit. Bestehende Fehler-/Retrybehandlung bleibt. |
| **LLM-12** | **Mit bestehendem LLM-3-Fix erledigt; keine Whitelisterweiterung nötig.** Monatsrest/Status werden deterministisch geprüft. Eine zusätzliche vom Modell steuerbare Budgetaktion wäre keine Voraussetzung für Kostensperren. |
| **LLM-13** | **Historische Kommentare/Tests von aktiven Regeln unterscheiden.** Datierte ältere Monatsregeln sind kein aktives Grün-Gate. Aktuelle zentrale Regeln sind Jahres-Calmar. Fachliche Pipeline-/Kommentarnachträge liegen bei Root; kein blindes Umschreiben der Historie durch diesen Scope. |

## SYN-IDs einzeln

| ID | Aktueller Befund, Entscheidung und Belege |
|---|---|
| **SYN-1** | **Bereits behoben**, siehe LLM-8: `report_basis_for.criteria` enthält DD-, Monats-Ertrags- und Jahres-Calmar-Schwelle. |
| **SYN-2** | **Bereits behoben.** `equity_studien.forensics_version` wird gespeichert/migriert; Getter/Listen liefern nur die aktuelle Version. Altstudien bleiben erhalten, werden nicht als aktuell wiederverwendet. `test_old_study_is_retained_but_not_reused` deckt den Altfall ab; finaler Stand berücksichtigt Root-Version19. |
| **SYN-3** | **Last-wins bereits abgewehrt; Composite-Migration bleibt Architekturgrenze.** Mehrdeutige Quellen-/Plattformidentitäten werden vor Persistenz abgewiesen; DB wehrt Fremdquellenüberschreiben zusätzlich ab. Die Antigravity-Aussage einer ungefangenen, den gesamten Scan zerstörenden Exception ist pauschal falsch: Signalfehler werden abgegrenzt. Vollständige `(quelle,signal_id)`-Migration würde weit über diesen Restfix hinausgehen und ist weiterhin dokumentiert offen. Keine Datenmigration gegen laufende Nutzerbestände. |
| **SYN-4** | **Bereits behoben.** REST-Defaultprovider nutzt `results_from_db(...,materialize_pdfs=False)`. Eigene Settingsaufnahme wurde zusätzlich explizit weitergereicht, keine GET-PDF-Erzeugung wieder eingeführt. |
| **SYN-5** | **Bereits behoben.** `client_updates.py:258` vergleicht Job-ID, wenn Start-/Statusantwort IDs liefern; fremdes `done` gilt dann als Fehler. Legacyserver ohne IDs können keine beweisbare Identitätsgleichheit liefern; deren Kompatibilität ist kein Anlass, Job-IDs zu erfinden. |
| **SYN-6** | **Bestätigt und behoben.** Echte Startzeile mit `status=running` und leerem Ende wird vor Vorbereitung/Handshake geschrieben; Abschluss aktualisiert dieselbe Zeile. Crash hinterlässt damit einen erkennbar unvollständigen Lauf. Gleichzeitige Start-/Endzeit bei sehr kurzem Lauf ist bei Sekundengenauigkeit zulässig; entscheidend ist die reale Ereignisreihenfolge. |
| **SYN-7** | **Bestätigt und behoben.** Einmalige temporäre Datei im Zielordner, Flush/fsync, `os.replace`, sichere Tempbereinigung. Ein abgebrochener Replace verändert die vorige gültige Datei nicht. Fehlende Datei nutzt weiterhin Defaults; vorhandene defekte/unlesbare Datei oder falscher JSON-Wurzeltyp ergibt einen klaren Fehler statt stillen Regeldefault. Keine produktive Settingsdatei angefasst. |
| **SYN-8** | **P3-Härtungsvorschlag, kein belegter Datenzugriffsfehler.** Unbekannte Pfade ergeben weiterhin404 vor dem Tokencheck; sie liefern nur den übergebenen Pfad, keine DB-Daten. Beide tatsächlichen Daten-/Healthrouten prüfen das konfigurierte Token vor Zugriff. Die zwei Routennamen sind ohnehin öffentlicher dokumentierter Vertrag auf Loopback. Keine neue Authentifizierungspolitik aus bloßer Pfadenumeration abgeleitet. |
| **SYN-9** | **Bestätigt und behoben.** `tradeserver_sync.sync_alle` reserviert vor Vorbereitung/HTTP einen Prozessmutex und benanntes vorhandenes prozessübergreifendes Lauf-Lock. Ein zweiter Sync erhält eine klare Abbruchbilanz, bevor irgendein Handshake startet. Ampeln/Fachtabellen bleiben unangetastet. |
| **SYN-10** | **Bestätigt und behoben.** `letzte_client_updates_je_quelle` selektiert per SQL `MAX(id)`/Kürzel statt nur die letzten500 Chronikzeilen zu betrachten. Regression:501 neue Einträge einer aktiven Quelle verdrängen den letzten Stand einer stillen Quelle nicht mehr. |
| **SYN-11** | **Bewusste lokale API-Einstellung.** Default aktiv/Token optional bei Loopback bleibt. Kein neuer externer Listener, Orderpfad oder produktiv abgeschalteter Schutz. Veränderte Nutzerpolitik würde separate Entscheidung benötigen; keine unbegründete Änderung. |
| **SYN-12** | **Bestätigt und behoben.** Bei Legacy-Sitzung ohne explizite Frischeliste reicht bloße Zugehörigkeit zu `scan_results` nicht mehr für NEU. Nur `persisted_this_run` belegt den Fallback; explizites `[]` bleibt leer. AppTest unterscheidet unbekannt+ohne Beleg, unbekannt+mit Beleg und explizit leer. |

## Antigravity E-1 bis E-6 im eigenen Zusammenhang

E-1 Parser-Path und private Testabhängigkeit wurden in der vorigen DeepSeek-Runde behoben; Parser/Fixtures gehören jetzt Root/anderem Scope. E-2 ist der bereits vorhandene Monatsledger (LLM-3). E-3 benennt eine reale Composite-Architekturgrenze, übertreibt aber die aktuelle Abbruch-/Last-wins-Wirkung (SYN-3). E-4 ignoriert die inzwischen implementierte Berichtsbasisprüfung; fehlende REST-Transparenz wurde ergänzt (LLM-7). E-5 ist der konkret behobene Retry-/Auditrest (LLM-6).

E-6 beweist keine aktuelle widersprüchliche Monats-Mindestregel: Die Vorlage fordert nach wie vor explizit `retdd_jahr >= min_calmar_jahr`; zentrale Blöcke binden Empfehlungen an Engine-Grün und Jahres-Calmar. Die Nennung von Monats-RetDD als Anzeige ist kein logischer Widerspruch. Ein tatsächliches Modellabwerten allein wegen Monats-RetDD<1 wurde nicht belegt und hier nicht kostenpflichtig untersucht. Keine unbelegte Behauptung als Fehler bestätigt oder neue Mindestregel daraus abgeleitet.

## Repros und zusätzlicher eigener Nachsicherungsfall

`tests/test_antigravity_hub_contracts.py` enthält14 eigenständige Vertragsfälle. Vorherlogs:

- `hub_before.log`:11 erwartete Fehlfälle am alten Implementierungsstand (Settings, Sync, Quelle501, Promptschutz, Retrykomponenten/Audit, REST-Basis).
- `hub_deep_batch_before.log`: Start wurde trotz gehaltenem Scan-Lock fälschlich zugelassen; anschließend gezielt korrigiert.
- `hub_audit_failure_before.log`: zwei bestätigte Nachsicherungsfälle `stop`/`length`, bei denen ein lokaler Audit-I/O-Fehler nach bezahlter Antwort zuvor Usage/Metadaten verlor.

**Audit-I/O-Nachsicherung:** Peer `quellen` reproduzierte den eigenen neu eingeführten Fehler synthetisch (`nachweise/hub_audit_write_peer_probe.json`). Korrektur in `llm/client.py:173–199`: Bekannte Rawusage/Komponenten bleiben auch bei lokalem Auditfehler gebucht, die bezahlte Antwort bleibt im Fehler-Metadatum `audit_failed_response`, `audit_complete=false`; klarer lokaler `LlmError` und **kein zusätzlicher HTTP-Versuch**, auch nicht bei `finish_reason=length`. Zwei unabhängige Regressionen erwarten jeweils genau1 HTTP, Usage100/Requests1, Komponenten60/40 und Inflight0. Bei defektem persistentem Speicher wird keine dauerhafte Auditierung vorgetäuscht; die Antwort kann dann nur noch im Speicher gehalten werden. Unbekannte nicht gemeldete Kosten werden nicht erfunden.

Normaler Retry-Oracle: erste Antwort30 Tokens (20 Prompt/10 Completion), zweite70 (40/30). Ergebnis100/60/40; beide Textfragmente getrennt dauerhaft auditiert. Zwei unvollständige Antworten werden ebenfalls erhalten. Agentenbudget rechnet weiterhin ausschließlich Legacykosten plus Agentenversuchledger; `llm_attempts` ist keine Abrechnungstabelle, daher keine zweite Belastung.

## Testanpassungen transparent

Zwei lokale `FakeResp`-Klassen in `tests/test_review_t12_llm_forensik.py` lieferten bisher nur `status_code`/`json()`, ohne `text`: `test_chat_meta_enthaelt_pro_call_total_tokens` und `test_budget_blockt_parallel_einen_call_noch_vor_kosten`. Echte `requests.Response` besitzen das vollständige rohe Antwortfeld. Die Dummies haben nun `text = json.dumps(self.json())` als Property. Status, Inhalt, Tokenusage und Assertions bleiben gleich; kein Produktionsfallback für einen unvollständigen Dummy hinzugefügt.

Der Agentenfülltest prüft weiter die unveränderten wörtlichen `{typ}`-Zeichen im eingefügten Fremdtext, nun zusätzlich den verpflichtenden Präfix. Der NEU-Test wurde sachlich von „unbekannte Frische ist automatisch NEU“ auf einen erforderlichen Persistenzbeleg umgestellt.

Ein neuer Usage-Test wurde zunächst versehentlich vor die letzte Assertion des vorherigen Tests eingefügt. Das verursachte **1 failed/118 passed** im ersten eigenen isolierten Versuch, ohne Produktfehler. Der Originaltest behält jetzt seine unveränderte Zwei-Call-Assertion; der neue erfolgreiche Drei-Prompt-Fall erwartet3 Calls und drei Einzelkosten0 bei fehlender Usage. Root wurde sofort über korrigierte SHA und notwendigen späteren Gesamtsnapshot informiert; laufende Root-Volltests wurden nicht geändert. Vorherige Fehlstände werden nicht als grüne Abnahme ausgegeben.

## Eigene Dateien und finale isolierte Nachweise

15 eigene Änderungen, vollständig mit SHA256 in `hub_manifest.json`:

```text
app_pages/ergebnisse.py
src/mqlkiscanner/agenten/rollen_prompts.py
src/mqlkiscanner/config.py
src/mqlkiscanner/db.py
src/mqlkiscanner/help_settings.py
src/mqlkiscanner/llm/client.py
src/mqlkiscanner/llm_runner.py
src/mqlkiscanner/rest_api.py
src/mqlkiscanner/tiefen_batch.py
src/mqlkiscanner/tradeserver_sync.py
tests/test_antigravity_hub_contracts.py
tests/test_agenten_rollen.py
tests/test_review_t12_llm_forensik.py
tests/test_review15_llm.py
tests/test_review17_ui.py
```

Isolierte Kopie: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\antigravity_handover_pruefung_2026-10-16\hub_snapshot`. `git archive a3112c2` plus die15 eigenen Änderungen und Roots separat gekennzeichneter `analysis_version.py`-Nachtrag19. Keine ignorierten Laufzeitdateien übernommen. Roots sonstige parallele Pipeline-/Währungs-/Filteränderungen sind nicht Bestandteil dieses Teilnachweises; deren kombinierter Volltest liegt bei Root.

Finaler Befehl in dieser Kopie:

```powershell
& 'C:\Users\tnickel\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe' -m pytest tests/test_antigravity_hub_contracts.py tests/test_agent_budget_periods.py tests/test_gesamt_review_hub_fixes.py tests/test_agenten_rollen.py tests/test_rest_api.py tests/test_tradeserver_sync.py tests/test_review15_llm.py tests/test_review_t12_llm_forensik.py tests/test_tiefen_batch.py -q
```

Ergebnis: **121 passed in16,79s, Exit0** (`hub_final_targeted.log`, `hub_result.json`). Zusätzlich war die zu diesem Zeitpunkt unveränderte Ergebnisseite im früheren AppTest-Lauf `hub_targeted_second.log` grün (**72 passed**, inklusive `test_review17_ui.py`). Der eigene finale Auswahltest enthält keinen vollständigen Scanner-Volltest; Root führt diesen einmal auf dem kombinierten finalen Stand aus.

`hub_hash_verification.json`: **638 ursprüngliche Snapshotdateien,16 Overlays (15 eigene + Roots Version19), keine Abweichung** zwischen getesteter Kopie, Manifest und eigenen Live-Dateien nach dem Test. Manifestformat: `headBefore`, `snapshot`, `overlay:[{path,owner,liveSha256,snapshotSha256}]`, `snapshotFiles:{path:sha256}`.

```text
hub_manifest.json     f2bc8ba34d3649838df68408e5ec1f2f4c878a22818c55e238faaa101db9648e
hub_final_targeted.log 37844c113a9d72dfe341b93e703bbe01a6df337499926055d70c2622151c54c3
llm/client.py         43a50312874d966b0be536e8d2917b76ac1819adcb1d93411e50f1ddfe15dc88
test_antigravity_hub_contracts.py 2e76ac14b8a126a86549b066c7bf6a6f0bfe65650a8d6bf39e258d1a4afeb5c1
test_review15_llm.py   0672d5d5e8cbb3f2b0fbdd3d4cbb6319c0395b19cdc384da29eea2392656e0e6
```

Eigener Code-/Testscope eingefroren. Keine weiteren Produkt-/Snapshotänderungen geplant. Neue externe Programme oder MqlRealmonitor/PelicanWinnerLooser wurden nicht integriert.
