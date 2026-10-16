# DeepSeek-Gegenprüfung: Scanner-Budget, Prompts und Defaults – 16.10.2026

P2-1, P2-2 und P3-1 sind im veröffentlichten Scanner-HEAD bereits behoben. Ein verwandter echter Restfehler blieb im sichtbaren Regelwerk: Es erklärte weiterhin Monats-RetDD≥1,0 zum Grün-Gate und erlaubte eine Monitor-Messung als Calmar-Nenner. Dieser Anzeigetext ist korrigiert; Engine, Bewertungsregeln und Produktionssettings wurden nicht geändert.

## Stand, Umfang und Methode

- Ausgangs-HEAD `cef1e5af53e5737eb3dfdc2e093c8b7b979a83b5`; Arbeitsbaum bei Prüfstart sauber.
- Fremdbericht: `C:/Users/tnickel/.codex/attachments/1e87abd7-9a42-4e2e-987b-7b544f198e95/Eingefügter Text.txt`. Er nennt Scanner `80d4692548c9`, Forensik16 und damalige Testzahlen; das ist nicht der aktuelle veröffentlichte Stand.
- Gelesen: Scanner-AGENTS, Budgetledger und Aufrufwege, Portfolio-/Regeltexte, Ertragsdefaults und vorhandene Regressionen. Für die Streamlit-Textanzeige: lokaler Skill `C:/Users/tnickel/.agents/skills/developing-with-streamlit/SKILL.md`, installierte Referenzen Markdown/Testing. Headless-AppTest statt Programm-/Browserstart.
- Keine externen HTTP-/LLM-Aufrufe, Brokerterminals, Produktionssettings-/DB-Änderungen, Stages, Commits oder Pushes. Tests benutzen temporäre Speicherung, Fakes und gemockte Antworten. Parser, Fixtures und Quellenwochen sind außerhalb dieses Teilauftrags.
- Root bearbeitet parallel drei weitere Hinweistexte (`help_content.py`, `station_dialoge.py`, `ampel_matrix.py`). Diese Änderungen sind nicht in meinem isolierten Snapshot enthalten; die kombinierte Schlussvalidierung übernimmt Root.

## Fremdbefunde gegen aktuellen Code

| ID | Ergebnis und Belege |
|---|---|
| **P2-1 Monatsbudget nur angezeigt** | **Am aktuellen HEAD widerlegt.** `agenten/budget.py:54–76` prüft Tages- und Monatsverbrauch samt offenen Reservierungen innerhalb `BEGIN IMMEDIATE`, bevor ein HTTP-Versuch gestartet wird (`:109`). `llm/client.py:132` führt budgetgebundene Clients durch diesen Ledger. Dirigent, Betreuer, Destillation, Markt, Melder, Chef sowie autonome Scans hängen den gemeinsamen Budgetschutz an (`budget.attach`). `dirigent.py:83/214` berücksichtigt auch das Monatslimit in Vorprüfung/Status. Retries werden separat reserviert; unbekannte Transportkosten konservativ gebucht. Testbelege: monatliche Sperre vor HTTP und Dirigent-Aufruf, parallele Reservierung, Retrykosten; außerdem Periodenwechsel/Legacykosten in `tests/test_agent_budget_periods.py`. Grenze: dies ist das **Agentenbudget**. Manuelle GUI-Modellaufrufe haben ihren eigenen Laufbudgetkontext; daraus folgt kein pauschales kontoweites Z.ai-Kostenlimit. |
| **P2-2 Portfolio fordert Monats-RetDD≥1** | **Am aktuellen HEAD widerlegt.** `portfolio_statistik.py:458–465` nennt den konfigurierten Jahres-Calmar über `config.min_calmar_jahr(settings)` und erklärt Monats-RetDD zur Zusatzkennzahl ohne Gate. Regression `test_finance_review_20261016.py:201` prüft ausdrücklich die abweichende Schwelle4,25 sowie das Fehlen des alten Hinweises. Produktive Vorlagen und Defaults werden zusätzlich durch `test_retdd_kriterien_prompts.py` verglichen. Der neu gefundene Regelwerkrest unten war ein anderer Ausgabeweg. |
| **P3-1 Ertragsfallback5 statt0** | **Am aktuellen HEAD widerlegt.** `config.py:82` Default0,0; `pipeline.py:878/933`, `ampel_matrix.py:246/469`, `app_ui.py:1017/1020`, `regelwerk.py:103`, `tradeserver_sync.py:101` verwenden0/0,0. `streamlit_app.py:162` greift auf den zentralen Default zurück. Die frühere5,0-Syncangabe ist damit nicht mehr im aktuellen Payloaddefault. Matrix-, UI-, Regelwerk- und Sync-Regressionen grün. Ungültige beliebige Settingswerte wurden hier nicht als neuer Sachverhalt erfunden oder zur Änderung der Bewertungspolitik benutzt. |

## Bestätigter zusätzlicher Restfehler: sichtbares Regelwerk widerspricht Engine

**P2; gesicherter Text-/Vertragsfehler.** Vor der Änderung erklärte `regelwerk.py:77/117/124` weiterhin „RetDD<1,0“, „RetDD mindestens1,0“ und „belastbare Kurs- oder Monitor-Messung“. `pipeline.ampel_for` entscheidet hingegen anhand Jahres-Calmar gegen die konfigurierte Schwelle; Monitor-Closing-DD ist nur Schrankenkanal. Nutzer sehen den falschen Text sowohl auf der Ergebnisseite als auch bei einem ausgeschlossenen Signal im Detail. Kein Beleg für dadurch veränderte numerische Ampeln: betroffen ist die Erklärung, nicht die Engine.

Vorhernachweis: neu hinzugefügte Tests des **produktiven** `regelwerk_markdown()` scheitern sowohl mit leeren Settings/Default3 als auch mit `min_calmar_jahr=4.25`. Log `hub_regelwerk_before.log`: **2 failed**, Exit1. Die davor vorhandene Testassertion verlangte selbst noch „RetDD≥1,0“; sie wurde auf die aktuelle konfigurierte Regel umgestellt.

Minimaler Fix, ausschließlich zwei Dateien:

```text
SignalKiScanner/src/mqlkiscanner/regelwerk.py
SignalKiScanner/tests/test_regelwerk.py
```

Der Builder verwendet nun `config.min_calmar_jahr(settings)` an beiden dynamischen Grenzwertstellen. Er beschreibt Jahres-CAGR/eigene belastbare H1-Equity-Messung inklusive Floating, mindestens drei Monate Trade-Historie und Monats-RetDD ohne eigenes Gate. Monitor-DD bleibt ausdrücklich nur Kanal der Drawdown-Schranke. Kein Engine-/Score-/Versions-/Settingswechsel. Die bestehenden AppTests für Ergebnis- und Detailansicht bleiben grün.

## Kritische Aussagen des DeepSeek-Textes

1. **„Fünf unabhängige Kanäle“ ist nicht belegt.** `scoring.dd_maximum` und `pipeline.py:824` bilden das Maximum vorhandener Werte, keinen Unabhängigkeitstest. Plattform-EQ/Balance stammen aus demselben Konto; lokale Handels-DD und Monitor-DD verwenden teilweise dieselben Trades. Unabhängige Implementierung wäre außerdem nicht dasselbe wie statistische Unabhängigkeit ihrer Daten oder Fehler. Das Maximum benötigt diese Unabhängigkeit nicht; daraus entsteht aber kein fünffach unabhängiger Sicherheitsnachweis.

2. **„Die risikoärmsten unter den abonnentenstärksten“ ist zu stark.** Calmar ist Rendite/Risiko-Effizienz, kein Minimum des absoluten DD. Schon zwei hypothetische Werte zeigen das: CAGR100%/DD5%=Calmar20 rangiert nach Effizienz vor CAGR5%/DD1%=Calmar5, obwohl der erste beobachtete DD höher ist. Historische Auswahl, Messlücken und zukünftiges Risiko erlauben auch keine allgemeine Garantie „zuverlässig riskante Signale aussortieren“. Belastbar sind Kandidaten unter den geltenden Auswahl- und Messregeln, keine bewiesene Rangfolge der geringsten zukünftigen Risiken.

3. **H1 erfasst keine Intrabar-Extrema – die Richtung ist ein begründetes Risiko, keine universelle numerische Schranke.** Bei derselben vollständigen positiven Equity-Kurve, Basis und Periode kann ein Unterraster einen zwischenliegenden Tiefpunkt verpassen. Die echte Kontokurve unterscheidet sich hier zusätzlich durch Kapitalbasis, Referenzpreise/Spread, ungemessene Positionen und gegebenenfalls Teilabdeckung. Ein Wert auf virtuellerBasis10000 ist kein garantierter unterer DD-Prozentwert auf realerBasis20000: derselbe Geld-DD1000 ergibt10% gegenüber5%. Aktueller Code sagt diese Grenze bereits ausdrücklich (`pipeline.py:923–926`, `ampel_matrix.py:420–424`). Closing-DD ist kein Calmar-Nenner; eine pauschale Untergrenzenbehauptung über anders basierte Kontowerte wäre trotzdem unzulässig.

4. **Manuelle Ausschlüsse belegen keinen Weg zu falschem Grün.** Die Liste ist bewusst kuratiert und übersteuert eine bessere Kennzahl bis zur begründeten Pflege (`regelwerk.py`, `pipeline.py:828`). Das kann aktuelle gute Kandidaten zu streng ausschließen; daraus folgt nicht, dass schlechte Kandidaten positiver werden. Der Bericht ordnet dies ebenso wie den alten restriktiven Monats-RetDD-Prompt unter „Schlechte können zu positiv erscheinen“ ein – diese Wirkungsrichtung ist nicht hergeleitet. Ein konservativer Ausschluss hebt die harten Gates nicht auf. Die stärkste Gegenposition bleibt: ungepflegte manuelle Gründe können fachlich veralten und benötigen erneute Prüfung; automatische Wiederaufnahme ist aber keine bestehende Nutzerregel.

5. **Konkrete statistische Gewissheit fehlt auch für die Kritik selbst.** Fehlende Out-of-sample-/Walk-forward-Validierung begrenzt Zukunftsaussagen. Die konkrete Behauptung, die aktuelle Rangfolge kippe bei kleinen Parameteränderungen, wurde im Fremdtext aber ohne Sensitivitätsrechnung oder Datenbeleg aufgestellt. Als Risiko/Hypothese vertretbar, als gemessene Eigenschaft nicht bestätigt. Keine neue Auswahl-/Bewertungspolitik daraus abgeleitet.

## Finale isolierte Tests und Hashnachweis

Snapshot: `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\deepseek_review_pruefung_2026-10-16\hub_snapshot`.

Erzeugung: `git archive cef1e5a` plus ausschließlich die beiden eigenen Änderungen. Andere parallele Arbeitsbaumänderungen wurden nicht übernommen. Manifest `hub_manifest.json`: `headBefore`, `snapshot`, `overlay:[{path,liveSha256,snapshotSha256}]`, `snapshotFiles:{path:sha256}`.

```powershell
& 'C:\Users\tnickel\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe' -m pytest tests/test_regelwerk.py tests/test_agent_budget_periods.py tests/test_gesamt_review_hub_fixes.py tests/test_retdd_kriterien_prompts.py tests/test_finance_review_20261016.py::test_f9_portfolio_hint_obeys_current_annual_setting tests/test_hub_ui.py tests/test_tradeserver_sync.py tests/test_ampel_matrix.py -q
```

Ergebnis: **95 passed in10,47s, Exit0**. Standardmarker schließt kostenpflichtige LLM-Tests aus. Log `hub_targeted.log`, Resultat `hub_result.json`. Keine volle Scanner-Suite erneut ausgeführt; Root validiert den kombinierten Stand.

`hub_codehashes.json` enthält SHA256 der geprüften Budget-/Rollen-/Client-/Prompt-/Defaultdateien und relevanten Tests. `hub_hash_verification.json` bestätigt **579 ursprüngliche Snapshotdateien und beide eigenen Live-Overlays ohne Abweichung nach dem Test**. Manifest-SHA256 `9a541efee5f4aca1b8480ec681fea1869b33246aa4cd327f95d70270b4df19f4`; Testlog-SHA256 `f4b78515f15ed64b720d61f12f51b7acf28c66fb80cf30ceadf76ce7bb651220`.

Eigener Scope eingefroren; keine weitere Produkt-/Snapshotänderung vorgesehen. Der Bericht behauptet keine Prüfung laufender Instanzen oder aktueller Plattformdaten. MqlRealmonitor und PelicanWinnerLooser bleiben zurückgestellt.
