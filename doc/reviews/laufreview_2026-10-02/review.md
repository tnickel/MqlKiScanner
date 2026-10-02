# Review des laufenden Scanners · 02.10.2026

**Ergebnis: Die geprüften Trade-Rechnungen stimmen mit ihrer definierten Berechnung überein. Der gesamte Bewertungs- und Bedienworkflow ist dennoch nicht vollständig korrekt.** Es gibt 13 bestätigte Befunde, darunter drei P1-Befunde. Einige wirken im aktuellen Lauf; andere sind isoliert reproduzierte Fehler mit Bedingungen, die heute nicht nachgewiesen wurden.

Basis: Commit `a01b7a3`, aktiver GUI-Teilscan, Auswahlstand 11:09:23, `listen_modus=beides`, 22 geprüfte Signale. Der Agenten-Daemon ist in den gelesenen Einstellungen deaktiviert. Snapshot des eigenen CSV-Audits: **12:23:48 Uhr**. Der Lauf war zu diesem Zeitpunkt noch in der KI-Phase: 56 neue Analysis-Datensätze; ImpulseNet wartete laut Protokoll auf den Gesamtbericht. Dies ist ausdrücklich keine Abschlussabnahme des Portfolios und der Station 6.

Produktivcode, Produktionsdatenbank und laufende Prozesse wurden durch dieses Review nicht verändert. SQLite ausschließlich lesend (`mode=ro`); Reproduktionen nur mit Temp-Speicher, In-Memory-DB oder Mocks. Keine zusätzlichen Modellaufrufe, Netzwerkanfragen oder MT5-Initialisierung. Neu angelegt wurden ausschließlich Review-Artefakte in diesem Verzeichnis.

## Was unabhängig nachgerechnet wurde

- **68 vollständige gespeicherte Trade-Snapshots:** USD-Drawdown, maximales relatives Trading-DD und linearer Monatsertrag stimmen bis auf die geprüfte Rundung von 0,01 überein. Das beweist die Implementierung dieser Formeln, nicht die Vollständigkeit der Anbieterhistorie oder die Richtigkeit einer extern angenommenen Kapitalbasis.
- **Alle 22 Signale des aktuellen Laufs:** zusätzliche unabhängige CSV-Auswertung mit Dezimalarithmetik, ohne Engine oder Produktivparser. **120 Prüfungen bestanden:** SHA-256 des gespeicherten Trade-Snapshots, USD-/relatives Trading-DD, maximale gleichzeitig offene Positionen, linearer Monatswert und bei CSV-Kapitalbasis die Einzahlungssumme vor Handelsbeginn. Gleichzeitige Öffnungen vor Schließungen zählen wie im Scanner konservativ zum Exposure-Peak.
- **Netto und Gold-Kontraktfaktor:** Kommission und Swap werden einbezogen; 1 Lot XAUUSD × 100 USD × 50 USD Bewegung ergibt korrekt 5.000 USD Stressbetrag. Harte Drawdown-Schranke und neutraler fehlender SL-Nachweis funktionieren in den geprüften Engine-Pfaden.
- **Normale Workflow-Berichte:** im Snapshot bei 97 gespeicherten Signalen kein restaurierter Trade-, Risiko- oder Gesamtbericht mit abweichender Datenbasis. Signal, Trade-Verweis und Forensik werden atomar persistiert; unveränderliche SHA-Snapshots und atomare Ergebnisarchive sind vorhanden.

| Signal | Trading-DD USD | Maximales relatives Trading-DD | Linearer Ertrag / Monat |
|---|---:|---:|---:|
| Gold Spike MT4 #2349227 | 157,20 | 4,57 % | 8,71 % |
| Gold Spike MT5 #2375480 | 138,47 | 9,14 % | 20,85 % |
| KiraCat #2342895 | 2.117,70 | 8,14 % | 21,55 % |
| Gold Reaper #2265877 | 319,49 | 15,94 % | 14,54 % |

Die Tabelle enthält Trading-DD, **nicht** das Maximum aller fünf DD-Kanäle. KiraCats Plattform-Equity-DD von 34,95 % reißt beispielsweise trotz Trading-DD 8,14 % die 30-%-Schranke. Linearer Ertrag ist kein geometrischer Monats-ROI.

## Bestätigte Befunde

### 1 · P1 · RetDD, geometrischer Monatsertrag und CAGR werden nie berechnet

`src/mqlkiscanner/pipeline.py:157`–`:163` definiert die vier Felder mit `None`. Der reale Einzelprüfpfad berechnet bei `:1230` ausschließlich den linearen Startbasis-Ertrag. Es gibt keine Zuweisung, Persistenz oder Wiederherstellung der neuen Kennzahlen.

Isolierte echte Einzelprüfung und DB-Reload liefern diese Werte im LLM-Payload als `null`; kein produktiver Forensikdatensatz der gelesenen 90 enthält RetDD. Vorhandene RetDD-Tests setzen die Werte manuell und decken diese Implementierungslücke nicht auf. Das erklärt die leere RetDD-Spalte des Screenshots.

**Aktuelle Wirkung belegt:** Gold Spike MT4 wird im heutigen KI-Bericht unter anderem mit fehlender RetDD-Effizienz auf Watchlist gesetzt. Gemslime (Analysis 1270) und Master H4-2 (1276) rechnen stattdessen selbst lineare Ersatzquotienten; Master nennt dies sogar „Hilfsrechnung (nicht Engine-Zahl)“. Damit weicht der Workflow von der Vorgabe ab, alle Zahlen im Code zu berechnen und geometrische Effizienz zu verwenden. Die Engine-Ampel wird durch den LLM-Text nicht verändert.

### 2 · P1 · „Nur Station 6“ startet den ganzen Workflow

`app_pages/scan.py:600` erzeugt `step_downloader`; `_worker` hat dafür keinen Zweig und fällt bei `:1096` auf den kompletten Scan zurück. Der unveränderte Worker-AST ruft in der isolierten Probe Crawl und Kandidatenauswahl auf. Je Konfiguration folgen Forensik und kostenpflichtige KI-Aufrufe. **Nicht der Auslöser des heutigen regulären Teilscans.**

### 3 · P1 · GUI und autonomer Scan verwenden keinen gemeinsamen Lauf-Lock

GUI `app_pages/scan.py:1153` / `scan_worker.py:49` schützt nur innerhalb desselben Prozesses. Der autonome Launcher verwendet bei `agenten/scan_launcher.py:68` einen Dateilock. Ein gehaltenes Daemon-Lock verhindert in der isolierten Probe keinen GUI-Workerstart.

Konkurrierende Läufe könnten denselben Datenbestand, Cache und das Scanner-MT5-Terminal bearbeiten. **Heute latent, weil der Daemon deaktiviert ist; kein tatsächlicher Parallelscan behauptet.** Auch unabhängige Streamlit-Prozesse teilen die Registry nicht.

### 4 · P2 · MQL5-Persistenz kann den Quellen-Kollisionsschutz umgehen

`pipeline.py:1354` übergibt die Quelle nur bei REST-Kandidaten. `db.py:216` prüft den Konflikt nur bei expliziter Quelle. Die In-Memory-Probe ersetzt Pelican-Inhalt unter ID 123 durch MQL5-Inhalt, lässt aber das Quellenlabel `pelik` bestehen. Explizites `quelle=mql5` würde korrekt abgewehrt. **Eine reale Kollision im heutigen Lauf ist nicht belegt.**

### 5 · P2 · Offline-Quellenartefakte werden ohne SHA-Prüfung verwendet

`ingest.py:158`/`:194` prüfen beim Verbindungsfehler nur die Existenz der gespeicherten CSV-/Metrics-Datei. Die Probe verändert einen syntaktisch gültigen Profit von 10 auf 1000; der Offline-Fallback übernimmt die Datei trotz falschem SHA und meldet `geändert=False`. **Kein Nachweis beschädigter aktueller Produktivdateien; alle 22 geprüften finalen Trade-Snapshots stimmen mit ihrem gespeicherten Hash überein.**

### 6 · P2 · Monitor-DD kann beim Laden unvollständiger Forensik seine rote Sperre verlieren

`pipeline.py:383`–`:386` lässt `monitor_trade_eq_dd_pct` im DB-Lade-Maximum aus. Bei unvollständiger Forensik überspringt `restore_current_reports:773` die korrigierende Neubewertung. Probe: Plattform 8 %, Monitor 46,65 %, CSV-Fehler → weiß und `schranke_verletzt=False`; zentrale Neubewertung derselben Daten → korrekt rot. **Kein heutiger betroffener Datensatz nachgewiesen.**

### 7 · P2 · MQL5-Login-Ausfall blockiert auch unabhängige REST-Quellen

GUI `scan.py:789`–`:803` versucht bei vorhandenen Credentials vor der Schleife den Login und bricht bei Fehler ab, auch wenn ausschließlich Quellen-Kandidaten vorliegen. Die isolierte Probe erhält null Analyse-Aufrufe. Der Launcher besitzt den erforderlichen Quellen-Guard bereits. **Der heutige Login ist nicht als fehlgeschlagen belegt.**

### 8 · P2 · Autonomer Full-Scan mit null erfolgreichen Prüfungen setzt den Monatsmerker

`agenten/scan_launcher.py:85`, `:96`, `:288`–`:299` behandeln einen nichtleeren Scope mit ausschließlich fehlgeschlagenen Analysen als `ok`. Die Probe liefert `geprueft=0` und setzt trotzdem den Full-Scan-Monatsmerker, sodass ein weiterer automatischer Monatslauf unterdrückt wird. **Heute latent bei deaktiviertem Daemon.**

### 9 · P2 · Breakeven wird als Verlust für die Martingale-Signatur gezählt

`forensics/martingale.py:45` verwendet `netto <= 0`. Nicht überlappende Trades mit Netto `[0,+2]` und Lots `[0.01,0.02]` erzeugen einen Verlustnachfolge-Median von 2 und harte rote Ampel, obwohl kein Verlust vorliegt. **Der synthetische Fehlentscheid ist bewiesen; keine dadurch geänderte Gesamtampel im heutigen Bestand nachgewiesen.**

### 10 · P2 · Alte Tiefenanalysen erscheinen neben neuer Datenbasis ohne Veraltet-Markierung

`pipeline.py:370` lädt Tiefe ohne Basisprüfung; `restore_current_reports:777` prüft nur die drei normalen Workflow-Texte. `app_ui.py:978` nennt das Erstellungsdatum, markiert aber keinen Basiswechsel. `tiefen_batch.py:80` überspringt vorhandene Texte unabhängig von ihrer Basis; alte Texte können in Portfolio-PDF-Anhänge gelangen.

**47 Fälle im tatsächlichen Bestand**, darunter KiraCat, Gold Spike MT4 und Gold Reaper aus dem heutigen Lauf: Tiefenanalyse vom 21.09., aktueller Befund mit anderem Basis-Hash. Historische Texte aufzubewahren ist richtig; ihre aktuelle Gültigkeit wird in dieser Darstellung nicht geklärt.

### 11 · P2 · Neuer Gold-Spike-MT5-Bericht gewichtet fehlenden Stop-Nachweis negativ

Gesamtbericht `analyses.id=1234`, #2375480, 11:20:30: Risikoabschnitt nennt einen internen Basket-/Signalstopp plausibel und die fehlende Sichtbarkeit neutral. Unter den wichtigsten Watchlist-Gründen steht anschließend Stress-Exposure plus Grid-Profil „ohne nachweisbaren Einzelpositions-Stopp“.

Das widerspricht `config/prompts/gesamtbericht.md:82`: fehlender Nachweis ist neutral; eine Abwertung verlangt eine begründete Einschätzung „wahrscheinlich ohne Stop-Schutz“. Diese Begründung steht dort nicht. **Betroffen ist ein tatsächlicher heutiger KI-Text, kein nachgewiesener Engine-Scorefehler.** Watchlist bei grüner Engine ist für sich erlaubt und wurde nicht als Fehler gewertet.

### 12 · P2 · Teilscan markiert auch ausgelassene Slot-Kandidaten als „wird geprüft“

`fix_signale.py:136`, `:155`, `:160`: Auswahl begrenzt real auf Slots, die Teilscan-Begründung ignoriert jedoch `genommen_`. Probe mit zwei IDs und einem Slot wählt nur ID 1, beschreibt ID 2 trotzdem als `AUSGEWAEHLT`. **Heute nur relevant, wenn eine Quelle mehr Scope-Kandidaten als Slots besitzt; diese Bedingung wurde nicht nachgewiesen.**

### 13 · P2 · Station 1 kann während des Workflows die vorige Signalliste zeigen

`scan.py:700` ersetzt `control['signals']`; die zuvor angehängte Sessionliste bleibt unverändert (`scan_state.py:14`). Status-Fragment-Ticks synchronisieren die Liste nicht. `scan.py:1350` liest die alte Sessionliste beziehungsweise die vorige gespeicherte Auswahl. Der unveränderte Worker-AST reproduziert neue Control-Daten bei leerer alter Sessionliste. Voller Rerun/Abschluss korrigiert die Anzeige. **Direkt möglich im laufenden Workflow, heute nicht durch Browseraktion provoziert.**

## Unsicherheit und Grenzen

Die echten Equity-Rekonstruktionen lassen sich ohne gespeicherte zugrunde liegende H1-Bars nicht unabhängig nachrechnen. Ihre korrigierten synthetischen Regressionen bestehen, was keine Abnahme jeder realen GMT-Zuordnung oder Kursabdeckung ersetzt. Der laufende Gesamtworkflow und seine endgültigen Portfolio-/Sync-Ausgaben waren noch nicht abgeschlossen.

Pure Gold #2362868 zeigt eine zusätzliche Datenkonsistenzfrage: gespeicherter rechnerischer Endstand 26.383,54 USD gegenüber Web-Balance 19.732,51 USD, Differenz 6.651,03 USD. CSV enthält außerdem 3.750 USD `Credit`, die der Parser wie das alte Referenzskript ausklammert. Eine dokumentierte fachliche Begründung wurde nicht gefunden. Credits einfach als Einzahlungen zu addieren löst die Differenz nicht, sondern vergrößert sie. Deshalb **kein gesicherter neuer Drawdown-Rechenfehler** behauptet; Kredit-/Equity-Semantik und Historienvollständigkeit müssen vor einer solchen Aussage geklärt werden.

## Validierung und nächste Reparaturreihenfolge

231 vorhandene Rechen-/Equity-/Reviewtests sowie 63 Quellen-/LLM-/Reporttests bestanden in isoliertem Speicher. Zusätzlich wurden vier neue Rechen- und sieben Workflow-Gegenproben ausgeführt (**11 passed**); drei In-Memory-/Offline-Berichtsproben dokumentieren ihre reproduzierten Pfade im JSON. Grüne Gegenproben bestätigen hier das beschriebene aktuelle Fehlverhalten, keine Reparatur.

Empfohlene Reihenfolge: fehlende Kennzahlen Ende-zu-Ende berechnen/persistieren/restaurieren und aus realem Scan testen; Station-6-Routing und gemeinsamer Prozesslock; Quellenidentität/Offline-SHA/Monitor-Schranke; danach Berichtsgültigkeit, Login-/Monatsstatus und Anzeige-/Martingale-Randfälle. Keine dieser Reparaturen wurde im laufenden Produktionsscan durchgeführt.

Belege:

- [Unabhängiger Audit aller 22 aktuellen Signale](lauf_audit.json), [Audit-Skript](read_only_audit.py)
- [Berechnungsreview und Repro](calculations/review.md), [Repro-Skript](calculations/probe_calculations.py)
- [Workflowreview](workflow/review.md), [7 Gegenproben](workflow/test_workflow_review.py)
- [Quellen- und LLM-Review](ingest_llm/review.md), [RO-Snapshot](ingest_llm/snapshot.json), [Probe](ingest_llm/probe_readonly.py)
