> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\scanner`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# Scanner-Integration, LLM und Betrieb – Teilreview 16.10.2026

Geprüft: SignalKiScanner `80d4692548c9a770666315761e054bdf535d0446`, aktueller Quellcode und isolierter Git-Archiv-Snapshot. Keine Änderungen an Produktivcode, Einstellungen oder Nutzerdaten; keine Modell-, Login-, Terminal- oder Orderaufrufe. Lokale `/health`-GETs und SQLite-Zugriff mit `mode=ro`/`query_only=ON` wurden getrennt durchgeführt.

## Nachweise und Abdeckung

- `test_review_hub_repros.py`: synthetische Nachweise; die Assertions bestätigen jeweils das beobachtete fehlerhafte Verhalten, nicht dessen fachliche Richtigkeit.
- `hub_repros.log`/`hub_repros.xml`: Ausführungsergebnisse.
- `../manifest.json`: Git-Stände, Python und ausschließlich freigegebene Einstellungsschlüssel ohne Secrets.
- `../runtime_readonly.json`: reine Bestands-/Bereitschaftsinventur; kein Beweis des Git-Standes laufender JVMs.
- Untersucht: Quellenregistry, Ingest, DB-Identität/Transaktionen/Forensikbindung, Stufe 0, Scanner-REST, Tradeserver-Client/Sync, Promptbuilder/-validierung, LLM-Client, Agentenbudgets/-scheduler/-locks, GUI-Orchestrierung und Doku.
- Bestehende externe MqlTradeMonitor-Serverimplementierung war am dokumentierten Pfad nicht vorhanden. Client, Vertrag, Fehlerpfade und lokale Tests geprüft; kein Ende-zu-Ende-Nachweis gegen den echten Empfänger.

## H01 – P1: MQL4-Downloader erhält erfundenen RoboForex-Broker

**Code:** `src/mqlkiscanner/ingest.py:310–315,374–378`; Aufruf `pipeline.py:1565–1568`, DB-Fallback `:1580–1594`.

Die REST-Version `mql4` bezeichnet die Handelsplattform, nicht den Broker. Trotzdem wird sie vor dem Quellenkürzel als `roboforex` interpretiert. Der MqlDownloader liefert regulär kein Brokerfeld (HtmlConverter:203–226; REST:563–575). Dadurch bekommt ein gewöhnliches MQL4-Signal aus Quelle `mql5` den Broker RoboForex. Ein bereits aus der Signalseite gelernter Broker wird nicht übernommen, weil der falsche Fallback bereits gesetzt ist.

**Repro:** `test_mql_downloader_mt4_invents_roboforex_broker`; Antwort `version=mql4`, `metrics={Balance:10000, Subscribers:2}`, Quelle `mql5` → `broker_server=roboforex`. Erwartet: tatsächlicher belegter Broker, alternativ unbekannt. Auswirkungen: falsche Freigabe brokergebundener Kontrakte, falsche Floating-/Schockbeträge oder fehlende echte Spezifikation.

**Gegenargument:** Mit explizitem `metrics.Broker` gewinnt dieser; reine MQL5-Direktdaten sind nicht betroffen. Keine Behauptung, jeder beobachtete DD sei dadurch falsch. **Sicherheit:** hoch. **Korrektur:** Broker an Quellenidentität binden; mql4/mql5 niemals als Brokerbeweis verwenden. Tests für MQL4 beider Quellen, expliziten und gespeicherten Broker. Bewertungsänderung versionieren und betroffene Bestände neu prüfen.

## H02 – P2: Monatsbudget ist keine harte Sperre; autonome Scan-Kosten fehlen im Agentenzähler

**Code:** `agenten/dirigent.py:68–71,82–98,178–181`; weitere Rollen berechnen nur Tagesrest; `agenten/journal.py:390–411`; autonome Modellaufrufe `agenten/scan_launcher.py:359–380`.

Der Monatscheck erzeugt den Plan `budget_pause`. Unabhängig davon wird `_llm_entscheidung` aufgerufen und ausschließlich gegen das Tagesbudget begrenzt. Andere Rollen benutzen ebenfalls nur den Tagesrest. Der Zähler summiert `agenten_schritte` mit Prompt, nicht die in `analyses` gespeicherten Workflow-Aufrufe autonomer Scans. Separate GlmClient-Instanzen teilen keine globale Reservierung.

**Repro:** `test_monthly_exhaustion_still_permits_model_call`: Monat 5.000.000/5.000.000, heute 0/500.000 → Plan Pause, trotzdem ein Fake-Modellaufruf mit Budget 500.000. Keine echten Tokens verbraucht. `test_scan_analysis_costs_are_outside_agent_budget_counters`: 100.000 Workflow-Analysetokens gespeichert, Agenten-Tages-/Monatszähler bleiben 0.

**Gegenargument:** Produktive Agenten sind aktuell deaktiviert; GlmClient hat einen eigenen Call-/Laufbudgetschutz. Das schützt weder alle Rollen zusammen noch ein erschöpftes Monatsbudget. Manuelle Workflow-Budgets können bewusst getrennt sein; diese Trennung muss für autonome Scans ausdrücklich festgelegt werden. **Sicherheit:** hoch für Monatsbypass und Zählerabgrenzung, keine tatsächliche Kostenüberschreitung behauptet. **Korrektur:** zentraler Budgetservice mit Tages-/Monatsrest, atomarer Reservierung und verbuchten Retries; Scope autonomer Scan-Kosten festlegen. Gegenproben: Monat erschöpft, Parallelrollen, Retry, Fehler nach bezahlter Antwort.

## H03 – P2: Veraltete Monatsschwelle wird produktiv an die Portfolio-KI übergeben

**Code:** `portfolio_statistik.py:418–420`; `pipeline.py:2134–2142`; aktuelle Regel `pipeline.py:871–890`.

Payload verlangt weiterhin `retdd_monat >=1`, selbst bei grünen Einzelkriterien. Die aktuelle Regel verlangt Jahres-Calmar ≥ konfigurierte Schwelle (Standard 3). Beispiel: Monatsrendite 2 %, gemessener DD 5 % → Monats-Ret/DD 0,4; Jahres-CAGR `(1,02^12−1)*100≈26,824` %, Calmar ≈5,365. Ein fachlich aktueller grüner Kandidat wird im Portfolio nach alter Regel abgewiesen.

**Gegenargument:** Harte Ampel bleibt deterministisch; die KI könnte den Widerspruch zugunsten der aktuellen Regel auflösen. Darauf gibt es keinen Vertrag. **Sicherheit:** hoch; produktiver Payload, keine bloße Kommentaraltlast. **Korrektur:** dynamische aktuelle Kriterien verwenden und Prompt-/Payload-Regressionsfall dieses Beispiels ergänzen.

## H04 – P2: Unbekannte Portfolio-Signale werden warnungsfrei akzeptiert

**Code:** `llm/verdict_check.py:132–143`; Speicherung des Rohtexts vor Prüfung `pipeline.py:2170–2181`.

Allokationen werden nur gegen bekannte Namen geprüft, falls der Name im Lookup vorkommt. Ein unbekannter/halluzinierter Name bleibt ohne Warnung erhalten. Nichtgrüne bekannte Namen erzeugen lediglich eine Logwarnung; Allokation und gespeicherter Rohbericht bleiben bestehen. Namen sind außerdem keine stabile Quellenidentität.

**Repro:** `test_unknown_portfolio_allocation_has_no_warning`: erlaubter Kandidat `Known Provider` grün, Modelltext `- Invented Provider — 100 % — Kern` → 100-%-Allokation, keine Warnung. `test_yellow_portfolio_allocation_is_only_warned_and_retained`: Gelb behält 100 % Gewicht, lediglich Warnung.

**Gegenargument:** Das ist ein manueller Bericht, keine Orderausführung; bekannte gelbe Empfehlungen werden geloggt. Einzelberichte haben eine separate Urteilsbereinigung. **Sicherheit:** hoch für fehlende Prüfung; keine Behauptung eines tatsächlichen Live-LLM-Verstoßes. **Korrektur:** strukturierte IDs/Quellen statt Namen, unbekannte/nichtgrüne Allokationen ablehnen, erst validierten Bericht als freigegeben persistieren/anzeigen; Rohantwort als Auditbeleg erhalten.

## H05 – P2: Stufe 0 akzeptiert Abschluss eines anderen Jobs

**Code:** `client_updates.py:222` speichert die Start-ID; Polling ab `:245`, done-Zweig `:267` vergleichen die Status-ID nicht.

**Repro:** `test_update_accepts_done_from_different_job`: POST liefert `requested-job`, GET liefert `different-job` mit done und altem Datenstand. Ergebnis: `fertig`, aber Journal behauptet weiterhin `requested-job`. Erwartet: passender Job oder expliziter Konflikt/Übernahmevertrag.

**Gegenargument:** Korrekte Server publizieren einen reservierten Job synchron; bei normalem Einzelstart stimmen IDs. Der Fehler benötigt einen konkurrierenden Jobwechsel, Neustart-/Altstatus oder eine fehlerhafte Serverantwort. **Sicherheit:** hoch für Consumerlücke, kein bereits beobachteter Echtbetriebsvorfall. **Korrektur:** ID nach jedem Poll prüfen; kompatiblen Umgang mit alten Servern ohne ID explizit regeln; Konflikt und zulässige bereitsLaufend-Übernahme testen.

## H06 – P2: Gleiche PDF-Größe verhindert Aktualisierung eines geänderten Berichts

**Code:** `downloader_sync.py:140–146`, Metadaten werden erst beim Download aktualisiert (`:151–153`).

**Repro:** `test_same_size_changed_pdf_is_never_refreshed`: PDF-Inhalt A und B haben gleiche Länge, `lastModified` ändert sich. Zweiter Sync lädt nicht und hält Inhalt A. Unterschiedliche Berichte können dieselbe Länge haben. Damit können alte Quellberichte an neue Analysen angehängt und weitergespiegelt werden.

**Gegenargument:** Große Inhaltsänderungen ändern häufig die Dateigröße, und eigener Tradeserver-Sync prüft den lokal vorhandenen Inhalt per SHA. Dieser SHA erkennt nicht, dass der Ursprung mittlerweile einen anderen Bericht hat. **Sicherheit:** hoch. **Korrektur:** ETag/SHA vom Ursprung oder wenigstens LastModified zusätzlich vergleichen; identische Länge bei geänderter Zeit und korrupte lokale Datei testen.

## H07 – P2: Cache-Temporärdatei kollidiert innerhalb desselben Prozesses

**Code:** `ingest.py:259–265` verwendet Dateiname plus PID, keine Thread-/Zufallskomponente oder gemeinsame Zielsperre.

**Repro:** `test_atomic_cache_temp_collides_for_two_threads`: A schreibt A, B schreibt B in dieselbe temporäre Datei, A verschiebt B an den Zielpfad, B erhält FileNotFoundError. A kann danach einen SHA für A in der DB dokumentieren, obwohl B am Ziel liegt. Im normalen Abruf schützt die anschließende Hashvalidierung vor stiller Wiederverwendung, beseitigt aber nicht den Konflikt.

**Gegenargument:** Reguläre Scanstarts sind teilweise durch globale Locks serialisiert; es wurde kein konkreter produktiver Doppelabruf beobachtet. Der Nachweis gilt bei zwei gleichzeitigen Schreibern desselben Cacheziels, insbesondere für wiederverwendete öffentliche Ingestfunktionen. **Sicherheit:** hoch für Funktion, bedingte Betriebsrelevanz. **Korrektur:** eindeutige Tempfiles und abgestimmte Datei-/DB-Zielserialisierung; parallele Threads und getrennte Prozesse testen.

## Bestätigte Grenzen, keine neu erfundenen Implementierungsfehler

- **Composite-ID:** `signals` nutzt allein `signal_id`. Gegenprobe `test_cross_source_identity_is_rejected_not_supported` belegt, dass die zweite Quelle korrekt abgewiesen und nicht vermischt wird. Damit gehen bei Kollisionen dennoch Anbieter aus der analysierbaren Menge verloren; Migration ist bereits dokumentiert und offen.
- **Frische:** Scanner bindet Forensik an Version, SHA und letzten Fehler; kein allgemeiner TTL-/Plattformnachweis. Offline-SHA-belegter Altstand ist möglich. Das wird bei den Quellenfehlern relevant; ein heutiger Forensikzeitstempel belegt keinen heutigen Plattformabruf.
- **Doku doc23 §4.4:** Unabhängige nachgelagerte `/summary`-/`lastUpdated`-Prüfung ist im Consumer nicht implementiert. Weil der Kopf diese Abschnitte ausdrücklich als ursprünglichen Plan einordnet, kein zusätzlicher neuer Codefehler allein aus diesem Absatz.
- **REST:** GET health/signals, X-User-Key, konstante Tokenprüfung, Loopbackbindung. Ergebnisse leiten Ampel mit aktuellen Settings neu ab; keine neue Tradeforensik, aber Standardpfad materialisiert gegebenenfalls PDFs. „Rein lesend/bewertet nie neu“ muss fachlich präzisiert werden.
- **Lokaler Bestand:** alle fünf Quellen aktiv, Mischmodus, min_abonnenten=1, Top-N=30 je Quelle, Mindestalter26Wochen, DD30, Calmar3, Agenten aus. 163 Forensikdatensätze:15Version16,148älter/ohneVersion. Versionsschutz verhindert deren ungeprüfte Übernahme als aktuelle vollständige Forensik.
- **Bereitschaft:** alle fünf Quellen lieferten HTTP200 auf lokalem health, Scanner HTTP401 ohne Token. Quelllistener binden an `::`, health meldet tokenRequired=false; tatsächliche LAN-Erreichbarkeit hängt zusätzlich von Firewall/Netz ab. Das ist eine zu härtende Betriebskonfiguration, nicht ungefragt als Codefehler gezählt.
- **Laufende Builds:** health enthält keinen Commit-Fingerprint; aktueller Checkout und laufende Prozesse dürfen nicht gleichgesetzt werden.

## Dokuabgleich

| Aussage | Codegegenbeleg | Einordnung |
|---|---|---|
| doc07:373 GLM-5.3 je Rolle | rollen.py:75–108: Dirigent/Melder Flash | aktueller Doku-Drift |
| doc07 tägliche Betreuung ohne Quellenbegrenzung | betreuer.py:65–77,351–358: nur mql5 | doc08 benennt Grenze bereits korrekt |
| doc08:32/doc09:57,65–67 nie neu bewertet | pipeline.py:665 aktuelles ampel_for | gespeicherte Evidenz versus aktuelle Klassifikation unterscheiden |
| doc07:382–385/doc19:444–446 vollständige Antwort je Call | llm/client.py:219–245 verwirft length-Antwort, Tokens werden summiert | Auditversprechen präzisieren; Retryverlust kein Tokenbuchungsverlust |
| doc03:181–182 Score entscheidet Kandidatengate | pipeline.py:841–853 Scoregate entfernt | widersprüchlich auch innerhalb doc03 |
| doc03:269 Commission+Swap >10%=Spreadproblem | stats.py trennt Gebühren, misst damit keinen Spread | unbelegte Kausalbehauptung |
| Root README:74/UI_KONVENTIONEN:64 alle geladen.json mit Frischeprüfung | Pelican CSV+.meta; Hash beweist Integrität | falsche Vereinheitlichung; Frischefehler separat nachgewiesen |
| historische doc20 Zulu ohne History, FXbeschränkt, Pelican ohne Reports | heutige RESTimplementierungen anders | durch Historienkopf relativiert, keine neue aktuelle Zusage |

## Schnittstellenmatrix

| Grenze | Vertrag | Prüfung / offene Grenze |
|---|---|---|
| fünf Quellen → Scanner | X-API-Token; providers paginiert; metrics JSON; Trades CSV; history/reports | jeweilige Quellen-Teilreviews und gemeinsame Ingestrepros |
| Stufe0 | POST update; GET update/status; jobId/state/ergebnis | Teilfehler abhängig von Quellfeldern, fehlender ID-Abgleich H05 |
| Scanner → Realmonitor-Vorbereitung | GET health/signals?ampel; X-User-Key; 8611Loopback | lokale isolierte HTTPtests; Realmonitorintegration ausdrücklich offen |
| Scanner → MqlTradeMonitor | ping/register/signals/documents/complete/abort; X-User-Key; SHA-Diff | Client-/Mocktests, externer Empfängercode nicht vorhanden |
| DB → Ergebnisse/REST | aktuelle Ampel aus gespeicherter, SHA-/Versionsgebundener Evidenz | keine Liveaktualisierung; gegebenenfalls PDFmaterialisierung |

Keine Reparaturen oder Veröffentlichung durchgeführt. Für die Behebung müssen zuerst Quellhistorien/Handelssemantik und Equitymessung korrigiert werden, danach Forensikversion und Cacheinvalidierung, dann erneuter Import/Re-Scan und Prüfung aller Ausgabewege.
