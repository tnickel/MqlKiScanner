# Gesamtreview SignalKiScanner und fünf Quellen – 16.10.2026

**Ergebnis:** Das System kann derzeit keine durchgängig belastbare Auswahl der besten Signale belegen. Neben bekannten Daten- und Methodikgrenzen wurden konkrete Fehler reproduziert, die Risiko unterschätzen, Gewinne falsch summieren oder eine grüne Ampel entgegen den eigenen Regeln erzeugen. Die bestehenden Tests sind grün, decken diese Gegenbeispiele aber nicht ausreichend ab.

Dies ist der angeforderte Reviewbericht mit Korrekturplan, keine Umsetzung der Korrekturen. Produktivcode, Einstellungen, bestehende Datenbanken, Cookies und Trade-Caches wurden nicht verändert. Es gab keine kostenpflichtigen Modellaufrufe, Plattformlogins, Terminalstarts oder Orderaktionen. Neue Dateien sind ausschließlich Review-Artefakte.

**Nachfolgende Umsetzung:** Dieser Bericht bewahrt den geprüften Ausgangsstand.
Die später vom Nutzer beauftragten Korrekturen, aktuelle Testnachweise und
betriebliche Folgeschritte stehen in [BEHEBUNG.md](BEHEBUNG.md).

## 1. Was geprüft wurde und was offen bleibt

Vier parallel arbeitende Reviewer untersuchten Scanner-Finanzkern, Scanner-Integration/LLM/Betrieb sowie die fünf Quellen in zwei Gruppen. Der Hauptreview führte Ergebnisse, Gegenbelege, reproduzierte Zahlen und gemeinsame Ursachen zusammen. Jede Quelle wurde getrennt geprüft; Pelicans frühere Reparaturen wurden nicht ungeprüft auf andere Monitore übertragen.

**Statische Prüfung:** Architektur, aktuelle Dokumentation und datierte Konzepte, Abruf-/Parserpfade, Kennzahlen, CSV-/JSON-Verträge, REST-Routen, Filter, H1-Rekonstruktion, Auswahl/Portfolio, Persistenz, Jobstatus, Agentenbudgets, Fehlerpfade, Startskripte und Sicherheitsgrenzen.

**Dynamische Prüfung:** bestehende Offline-Tests aus sauberen Git-Archiven; kleine unabhängige mathematische Orakel; synthetische API-Transporte, tatsächliche Stores und lokale REST-Testserver; Durchstiche der fünf Quellformate zum Scanner-Parser; Updateantworten bis zur Scannerstatusauswertung; zahlreiche fehlerorientierte Gegenproben.

**Keine vollständige Livevalidierung:** Es wurden keine aktuellen Plattformkonten oder vollständigen aktuellen Plattformkataloge abgeglichen. Gebühren-/Währungssemantik ohne hinreichende Primärbelege bleibt offen. Reale Ausführungen, Kopierslippage und Intrabar-Tiefs sind nicht durch H1-/Exportdaten nachgewiesen. Der externe MqlTradeMonitor-Empfängercode lag am dokumentierten Pfad nicht vor; dessen Grenze wurde über Scannerclient, Vertragsdoku und Mocktests geprüft. Private Datenmigrationen wurden nicht an Nutzerdaten ausgeführt. Nicht jede Kombination jedes REST-Parameters wurde exhaustiv getestet.

Lokale `/health`-GETs und eine SQLite-Inventur mit `mode=ro`/`query_only=ON` dienten nur dem Konfigurations-/Bestandsabgleich. Sie ersetzen keine Prüfung der laufenden Buildversion: die Healthantworten enthalten keinen Commitfingerprint.

## 2. Untersuchte Git-Stände

Alle Arbeitsbäume waren bei Beginn sauber. Saubere `git archive`-Snapshots enthielten keine privaten Cookies, Einstellungen oder Laufzeitcaches.

| Repository | Branch | Vollständiger Commit |
|---|---|---|
| SignalKiScanner | main | `80d4692548c9a770666315761e054bdf535d0446` |
| MqlDownloader | master | `92d8f9cea10bdc8f99c96782d75631b21e1714e6` |
| PelicanTrading | master | `dde77d705a670b37fc0f422504e566a857527893` |
| roboforex | master | `42b268641ad370ccae7841b6a478f9745cb57bd3` |
| vantage | master | `1fe395805f29e20d2598aa37162e717769a15762` |
| zulumonitor | master | `72df0cf49aa4f44fe0d82d9d07112091cf4d5665` |

Die Projekte sind eigenständige Repositories. Der Workspace-Wrapper ist kein Superprojekt mit gemeinsam versionierten Submodulen. MqlRealmonitor und PelicanWinnerLooser bleiben ausdrücklich außerhalb der produktiven Integration; keine neue Integration wurde gefordert oder umgesetzt.

## 3. Tests und Reproduzierbarkeit

| Projekt / Testart | Ergebnis |
|---|---|
| Scanner: `python -m pytest -q`, sauberes Archiv, Python 3.12.10 | **1.911 bestanden, 4 übersprungen, 4 LLM-Tests abgewählt**, 856,76 s |
| MqlDownloader: `mvn -o test` | **105 bestanden**, keine Fehler/Skips |
| PelicanTrading: `mvn -o test` | **176 bestanden**, keine Fehler/Skips |
| roboforex: `mvn -o test` | **147 bestanden**, keine Fehler/Skips |
| vantage: `mvn -o test` | **49 bestanden**, keine Fehler/Skips |
| zulumonitor: `mvn -o test` | **107 bestanden**, keine Fehler/Skips |
| Vantage-Python: `pytest tests/test_download_trades.py -q` | **6 bestanden** |
| Zusätzliche Scanner-Hub-Repros | **9 bestanden**, sie bestätigen gezielt fehlerhafte Istzustände |
| Zusätzliche Finanz-/Quellenprobes | unabhängige synthetische Gegenbeispiele und Kontrollen; genaue Aufrufe in den Teilberichten |

Damit bestanden **2.501 vorhandene Offline-Tests**. Die vier Scanner-Skips benötigen optionale lokale Originalexporte; drei Parser-/Dedup-Realexportsnapshots und ein Originalarchivtest fehlten im frischen Checkout. Synthetische Gegenstücke wurden ausgeführt, ersetzen aber nicht diese konkreten historischen Daten. Die kostenpflichtigen LLM-Tests blieben gemäß Auftrag abgewählt. Eine SyntaxWarning betrifft einen Backslash in einem Teststring, keinen belegten Produktfehler.

Maven 3.9.6 / Eclipse Adoptium JDK25.0.4.101; MQL und Robo wurden zusätzlich offline als JAR/Assembly gebaut. Für spätere kleine Python-Repros wurde wegen hängender Windows-Store-Startprozesse ein vorhandenes anderes Python3.12 mit denselben lokal installierten Bibliotheken verwendet; keine Pakete wurden installiert. Das war eine Laufzeitumgehung, keine Produktkorrektur.

Originale Logs, JUnit-/Surefire-XMLs, Snapshots und synthetische Belege liegen lokal unter:
`D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16`.
`test_results.json` fasst die tatsächlich gelesenen XML-Ergebnisse zusammen. Die Repros bestätigen problematische Istzustände; daraus darf kein „Fehler behoben“ abgeleitet werden.

## 4. Architektur und wirksame Regeln

```text
Plattform
  → MqlDownloader / Pelican / Robo / Vantage / Zulu
  → lokale Kataloge, Trades, Kennzahlen, Abonnentensnapshots
  → REST: providers, metrics, trades.csv, history, reports
  → Scanner-Ingest + SHA-Artefaktcache
  → Parser → Finanzereignisse → Forensik / H1-Equity / Kennzahlen
  → deterministische Ampel → LLM-Interpretation → Portfolio
  → Ergebnisse / PDFs / Scanner-REST / vorhandener Tradeserver-Sync

Zusätzlich: direkter MQL5-Crawler/Export im Scanner.
Vor Quellen-Scans: Stufe0 POST update → GET update/status.
```

Alle fünf Quellen sind in der lokalen Registry aktiv. Wirksame Einstellungen: Mischmodus `beides`, mindestens 1 Abonnent, Mindestalter 26 Wochen, Top 30 je Quelle plus Fix-IDs, DD-Schranke 30 %, Jahres-Calmar 3, absolute Monatshürde 0, H1-Rekonstruktion und Stufe 0 an. Agenten sind derzeit aus. Das unterscheidet sich von Defaults (`listen_modus=mql5`, `min_abonnenten=0`). Keine geheimen Einstellungen wurden ausgegeben oder in diesen Bericht kopiert.

Die deterministischen Grenztests bestätigen: DD exakt30 überschreitet die strikte Schranke nicht; ein ungerundeter Wert darüber tut es. Calmar exakt3 besteht, knapp darunter nicht. Unbekannter/Null-DD beweist keine Effizienz. Score und fehlender SL-Nachweis sind keine eigenständigen Grün-Sperren. Fix-IDs umgehen Vorauswahl, keine harten Risiko-Gates. Mindestalter26Wochen und drei Monate tatsächliche Trade-Spanne sind unterschiedliche Prüfungen.

**Bekannte Architekturgrenzen:** zentrale Signaltabelle weiterhin nur `signal_id` als Schlüssel. Fremdquellkollisionen werden korrekt abgewehrt; beide Signale gleichzeitig vollständig analysieren kann dieser Stand trotzdem nicht. Tägliche Betreuung verarbeitet nur MQL5. H1 ist eine diskrete historische Messung; akzeptierte Teilrekonstruktion bleibt zulässig. Keiner dieser dokumentierten Punkte wurde allein als neu entdeckter Bug ausgegeben.

## 5. Die wichtigsten belastbaren Gegenbeispiele

| Priorität | Befund | Reproduktion / Bedeutung | Detail |
|---|---|---|---|
| **P1** | Fehlendes Symbol unterdrückt bekannte Floating-Verluste anderer Symbole | bekannter DD80%, freigegebene Teilmessung1%, anschließend grüne Ampel | Finanzkernbericht |
| **P1** | Rendite an Kapitalflüssen nutzt Balance statt Equity | bei vollständig gemessenem H1-DD20: Calmar4,859 statt2,774; Grün statt Gelb | Finanzkernbericht |
| **P1** | Robo MT5-Teilclose/Umkehr falsch aggregiert | 1IN/0,25OUT lässt Rest0,75 verschwinden; Gewinn300 wird500 | QB-R1 |
| **P1** | Robo OUT ohne IN erhält erfundene Eröffnung | Verlusttrade mit0h und identischen Preisen als normale Position im Scanner | QB-R2 |
| **P1** | SHA wird bei Robo/Vantage/Zulu als zeitliche Frische behandelt | Cache aus2020 weiterhin frisch; bekannte Listen werden in Stufe0 ohne Plattformabruf übersprungen | QB-R4, Vantage/Zulu |
| **P1** | Robo Closing-DD behandelt Einzahlung als Gewinn | bei denselben Trades0,431% statt8,333% in der Vergleichsrechnung | QB-R3 |
| **P1** | MQL-Konverter kann bei fehlenden Daten Originale löschen | fehlende Monatsdaten → MPDD0 → HTML/CSV/TXT gelöscht | QB-R7 |
| **P1** | MQL4-Version wird im Scanner als RoboForex-Broker interpretiert | normale Downloader-Metrics ohne Broker → falscher brokergebundener Kontraktpfad | H01 |
| **P2** | Fehlender Profit/Richtung wird als gültiger Wert exportiert | Vantage/Zulu: Sell und0USD; Robo ebenfalls fehlender Profit→0 | Quellenberichte, QB-R8 |
| **P2** | Teilfehler werden als sauber beendet übernommen | Vantage/Zulu/Robo ohne strukturierte Fehlerfelder; MQL schluckt Workerfehler | Quellenberichte, QB-R5 |
| **P2** | MQL `ergebnis` ist JSON-String statt Objekt | Scanner verwirft Datenstand/Zähler/Hinweise | QB-R6 |
| **P2** | Weitere mathematische Datenverluste | typfreie Geldzeile ignoriert, gültige TWR vorzeitig verworfen, frühe DD-Rundung, Studienflüsse doppelt | Finanzkernbericht |
| **P2** | Veraltete und ungeprüfte KI-Auswahlregeln | alte Monatsschwelle im produktiven Payload; unbekannter Name erhält100% ohne Warnung | H03/H04 |
| **P2** | Budgetgrenze und Jobzuordnung nicht durchgängig | Monatslimitbypass; fremde Job-ID wird als eigener Erfolg gebucht | H02/H05 |
| **P2** | Cache-/Persistenzfehler | geändertes PDF gleicher Größe bleibt alt; Tempnamen kollidieren; MQL-Präfix trifft fremde ID | H06/H07, QB-R10/R11 |

Diese Tabelle ersetzt nicht die Detailbefunde. Dort stehen genaue Dateien/Zeilen, Bedingungen, erwartete und tatsächliche Werte, Sicherheit, stärkste Gegenargumente und Regressionsempfehlungen. Ähnliche Symptome wurden nach Ursache zusammengeführt; ein Teilstatusfehler in mehreren Quellen ist keine Serie unabhängiger mathematischer Fehler. P1 bezeichnet vorrangig zu reparierende Daten-/Bewertungsfehler; ein P0-Vorfall wurde nicht nachgewiesen.

## 6. Kennzahlen- und Verwendungsübersicht

| Kennzahl | Implementierte Basis | Nutzung / Aussagegrenze |
|---|---|---|
| Trade-Netto | Profit+Commission+Swap plus separate Kostenereignisse | nur so richtig wie die Quellfeldsemantik; fehlende Werte dürfen nicht zu0werden |
| Winrate/PF/Verlustserien | stellenweise Trade-Profit statt Netto | als Bruttostatistik kennzeichnen oder fachlich vereinheitlichen; Kosten können Vorzeichen drehen |
| Plattform-DD | Quelle/Selbstauskunft, Prozent | zusätzlicher konservativer Schrankenkanal, keine eigene vollständige historische Messung |
| Closing-/Trading-DD | realisierte Ereignisse und verwendete Kapitalbasis | kein historisches Floating; Kontoflusstypen/Basis/Fenster prüfen |
| Eigener Equity-DD | H1-Kurse, Positionen, Kontraktspezifikation, FX, Zeitbasis, Kapitalflüsse | eigener Calmar-Nenner nur bei Freigabe; Rechenfehler in Teilmessung trotz Freigabe möglich |
| Monatsrendite/CAGR | exakte Trade-Spanne, Jahr365,2425Tage; TWR-Verkettung bei Flüssen | Balance-/Equity-Verwechslung an Flüssen korrigieren; nicht mit Plattform-ROI gleichsetzen |
| Projekt-Calmar | Jahres-CAGR / freigegebener positiver eigener Equity-DD | Standardgate3; statistische Validierung dieser Schwelle fehlt |
| Score | sieben gewichtete Risikodimensionen mit heuristischen Abbildungen | Kontext, kein eigenständiges Grün-Gate; keine kalibrierte Ausfallwahrscheinlichkeit |
| Martingale/Stops/Exposure | beobachtete Muster, dokumentierte SL-Evidenz, Kontrakte und Positionen | Muster sind nicht vollständig; fehlender SL bleibt gemäß Nutzerregel neutral; Schock ist Szenario |
| Quell-DD aus impliziter Basis | kumuliertes PnL / Plattformrendite | Modell; muss positive, zeitkonsistente Basis haben; kein Ersatz eigener historischer Equity |
| Portfolio-Korrelation | gemeinsame Monatsrenditen, Verlustcluster, Instrumentüberschneidung | kurze/gemischte Fenster und gemeinsame Tails begrenzen Diversifikationsaussage |
| Kopierstudien | virtuelle Konten/Skalierung/Kostenannahmen | kein beobachteter eigener Kopierkontoverlauf; Labels und Flussdiagnostik prüfen |

Vollständige projektspezifische Formeln, Einheiten, Zeit-/Kapitalbasis, Kostenbehandlung und Quellgrenzen stehen in den Teilberichten.

## 7. Dokuabgleich und REST-Verträge

Die Rollenmodelle, der Betreuungsumfang, die absolute Aussage „REST bewertet nie neu“, das LLM-Auditversprechen und einzelne Score-/Kostenformulierungen sind veraltet bzw. zu weitgehend. Besonders relevant ist die tatsächlich produktive alte Portfolio-Monatsschwelle; sie ist kein bloßer historischer Kommentar.

Historisch gekennzeichnete doc19/doc20/doc22-Aussagen wurden entsprechend eingeordnet. Beispielsweise sind alte Aussagen zu leerer Zulu-Historie, fehlenden Pelican-Berichten oder früheren FX-Grenzen keine heutigen Anforderungen. Doc23 §4.4 beschreibt einen ursprünglichen Plan für unabhängige Frischenachprüfung; die aktuelle Einleitung kennzeichnet diese Zielabschnitte ausdrücklich als historisch. Der Consumer implementiert diese Prüfung nicht; der Absatz allein ist daher kein neuer Codebug.

Aktuelle REST-Lücken sind dagegen reproduziert: MQL-Statusobjekt falsch serialisiert; MQL-JSON kollabiert doppelte Spaltennamen; fehlender Job-ID-Abgleich; fehlende strukturierte Teilfehler; Datenintegrität und -frische verwechselt. Quell-REST verwendet X-API-Token/Bearer/Query, Scanner-REST X-User-Key; das sind getrennte Verträge. Endpunktmatrizen mit Methoden, Parametern, Versionen, Fehlern, Einheiten und Consumerverwendung liegen in den Anhängen.

Laufende Quellen lauschen an `::`, health meldete tokenRequired=false. Scanner lauscht auf127.0.0.1 und antwortete ohne Token401. Das belegt den beobachteten lokalen Zustand, nicht LAN-Erreichbarkeit durch jede Firewall. Offener LAN-Modus ist dokumentiert; Token-/Bind-Konfiguration und Secrets müssen betrieblich bewusst gewählt werden. Kein ungeprüfter Exploit wird behauptet.

## 8. Können damit die besten Signale gefunden werden?

**Derzeit ist eine verlässliche Freigabe nicht begründet.** Bereits deterministische Fehler können die eigene Risiko-/Effizienzregel verletzen. Mehr KI-Modelle auf denselben fehlerhaften Zahlen lösen dieses Problem nicht. Nach Reparatur ergibt sich zunächst eine nachvollziehbare Auswahl unter den beobachteten Daten und Projektregeln, kein Nachweis zukünftiger Gewinner.

Die Vorauswahl ist mehrfach eingeschränkt: MQL-Direkt standardmäßig wenige Listenseiten, Quellkataloge mit eigenen Filtern/Deckeln, MQL-MPDD, Robo-Ratingfenster und Profitobergrenze, Abonnentenranking, Quell-Tradecaps, Mindestalter, Top30 je Quelle, Fix-IDs und Teilscan ehemaliger Grün/Gelb-Signale. Das kann gute wenig abonnierte Anbieter ausschließen und überlebende/populäre Anbieter überrepräsentieren. Diese bewussten Filter sind nicht automatisch Bugs, begrenzen aber jede Aussage „beste aller Anbieter“.

Fehlendes Quellalter wird vor der Analyse konservativ ausgeschlossen. Insbesondere liefert MqlDownloader regulär kein weeks-Feld; ohne Direktdaten oder Fix-ID kann deshalb ein an sich vorhandener Anbieter schon an der Vorstufe scheitern. Broker, Kontowährung und echtes Startkapital fehlen bei einzelnen Quellen ebenfalls. Solche Lücken dürfen weder geraten noch durch positive Texte verdeckt werden.

Drei Monate Mindesthistorie sind eine Nutzerregel, kein statistischer Stabilitätsbeweis. Eine kleine gemessene DD-Zahl ist kein Nachweis kleiner zukünftiger Verluste. Geprüfte Rankingpfade enthalten keine allgemeine Out-of-sample-/Mehrfachvergleichskorrektur oder Unsicherheitskalibrierung. H1-Messgüte, offene Restpositionen, Regimewechsel, überlappende Trades, kurze gemeinsame Portfolioperioden und echte Kopierkosten bleiben entscheidend. Niedrige Monatskorrelation allein trägt keine Diversifikationsgarantie.

Nach Bereinigung sollten deshalb Rangstabilität bei Daten-/Parameteränderungen, Kosten-/Slippagestress, gemeinsame Verlustphasen, effektive Stichprobengröße und zeitlich saubere Walk-forward-Prüfungen folgen. Konfidenz-/Resamplingverfahren müssen die zeitliche Abhängigkeit berücksichtigen. Schwellen und Ranggewichte vor einer Out-of-sample-Auswertung festlegen; nachträgliches Optimieren auf bekannten Gewinnern nicht als unabhängigen Erfolg ausgeben.

## 9. Korrekturplan in Abhängigkeiten

1. **Originaldaten erhalten und Handelsereignisse reparieren:** MQL darf bei fehlender Berechnungsbasis keine Originale löschen. Robo Teilfills/Umkehr/OUT-only, Null-/Typvalidierung und Kontobuchungen korrigieren. Quellhistorien-Caps und unbekannte Felder explizit transportieren.
2. **Tatsächliche Aktualisierung und ehrlichen Status herstellen:** Delta-/Frischeabgleich für bekannte Listen; strukturierte Fehler/Abbruchfelder in allen Quellen; MQL rekursives JSON; atomare Jobreservierung und ID-Abgleich. Erfolgsmarker nur nach belegtem Erfolg schreiben.
3. **Finanzkern korrigieren:** bekannte Floating-Werte bei Teilmessung erhalten; Equity an Flowzeitpunkten für TWR verwenden bzw. fehlende Equity als Unsicherheit sperren; DD vor Gate nicht runden; Kosten-/Geldzeilen nicht still verwerfen; Studienflüsse nicht doppelt buchen; Brokeridentität quellenbezogen bestimmen.
4. **Persistenz und Ausgaben absichern:** eindeutige Tempfiles/Pfadkoordination, korrekte Cacheidentität und Berichtfrische; produktive Prompts an aktuelle Regeln binden; Portfolio-IDs und Freigaben validieren; globale Budget-/Auditgrenzen korrekt umsetzen.
5. **Neue Nachweise versionieren:** geeignete Regressionstests mit unabhängigen Orakeln hinzufügen; fachliche Forensikversion erhöhen und abhängige Studien/Prompt-/Reportcaches invalidieren. Erst korrigierte Quellhistorien bereitstellen, dann betroffene Bestände neu importieren/prüfen. Nicht nur alte Befunde mit neuem Zeitstempel versehen.
6. **Betrieb und Methodik validieren:** tatsächlich gestartete Builds identifizieren, Quellfelder/Kosten/Währungen anhand belastbarer Plattformbelege bestätigen, danach Rang-/Portfolioverfahren außerhalb der zur Auswahl verwendeten Historie prüfen.

Ein reiner Re-Scan vor Reparatur der Quell-/Kernfehler ist keine ausreichende Lösung. Die lokale Bestandsinventur ergab 163 Forensikdatensätze: 15 haben Version 16; 148 sind älter oder ohne Version. Der vorhandene Versionsschutz ist sinnvoll; nach den nötigen Bewertungsänderungen wird eine weitere gezielte Neuprüfung erforderlich.

## 10. Detailberichte und Belege

- [Scanner-Finanzkern](01_scanner_finanzkern.md): Formeln, Zahlenorakel, falsche Grünfälle, Kontrollen und Methodikgrenzen.
- [Scanner-Integration, LLM und Betrieb](02_scanner_integration.md): H01–H07, Konfiguration, Doku- und Vertragsmatrix.
- [Pelican/Vantage/Zulu – gemeinsame Abdeckung](03_quellen_a.md) mit gesonderten Berichten für [Pelican](03_pelican.md), [Vantage](04_vantage.md) und [Zulu](05_zulu.md).
- [MqlDownloader und RoboForex](06_mql_robo.md): QB-R1–QB-R12, Endpoint- und Kennzahlenmatrix, Gegenargumente.
- Reproquellen und maschinenlesbare Ergebnisse unter `nachweise/`; große Build-Snapshots und originale Logs verbleiben im lokalen Auditverzeichnis.

Die Git-Stände und finanziellen Gegenbeispiele sind reproduzierbar dokumentiert. Es wurde keine pauschale Plattformvollständigkeit, Kopierbarkeit oder künftige Rendite behauptet und kein Produktfix als erledigt ausgegeben.
