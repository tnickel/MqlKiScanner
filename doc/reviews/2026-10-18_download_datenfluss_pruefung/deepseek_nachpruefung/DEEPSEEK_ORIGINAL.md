# Prüfung: Downloadvorgänge, Datenfluss, Tabellen „Alle Signale" / „Ergebnisse"


## Geprüfter Stand


SignalKiScanner `1bda2fa` (main, **mit uncommitteten Änderungen** an 27 Dateien + 9 neuen Testdateien). Alle fünf Quellprojekte gelesen; alle fünf REST-Dienste waren während der Prüfung live erreichbar (Ports 8089–8093). Python 3.12.10 / pytest 9.1.1, JDK 25 / Maven 3.9.6. Nur lesende Zugriffe: lokale GETs, SQLite read-only, keine POSTs, keine Scans, keine LLM-/Terminalaufrufe. Produktivcode und Bewertungsregeln unverändert.


## 1. Urteil je Quelle und Tabellenansicht












































| Quelle | Katalog live | Scanner-Katalog | Urteil |
| --- | --- | --- | --- |
| MqlDownloader `mql5` | 216 (Vollkatalog: **236**) | 215 | **Fehlerhaft** — Altersbeleg fehlt in laufendem Build; 20 abonnentenlose Provider werden nie geladen |
| PelicanTrading `pelik` | 640 (Vollkatalog: **2188**) | 640 | **Fehlerhaft** — 1548 Provider (71 %) unsichtbar; teils gesperrte Alt-Historien |
| RoboForex `robo` | 200 | 200 | **Bestanden** (im geprüften Umfang) |
| Vantage `vant` | 199 | 199 | **Fehlerhaft** — laufender Build sperrt alle Historien (404) |
| ZuluTrade `zulu` | 200 | 200 | **Bestanden** mit Einschränkung (Feldvertrag) |



**Tabellen:** „Ergebnisse" 194 Zeilen, „Alle Signale" 1477 Zeilen (194 Workflow + 1283 Katalogzeilen). Meine unabhängige Nachrechnung mit dem produktiven Codepfad ergab exakt dieselben Zahlen. Spaltenzuordnung beider Tabellen: **bestanden**.


## 2. Mengenbilanz (unabhängig nachgerechnet)


Plain text






```
Quellenkatalog (katalog_signale)     1454   mql5 215 · pelik 640 · robo 200 · vant 199 · zulu 200
Workflow-Bestand (signals)            194   mql5 71 · pelik 37 · robo 33 · vant 16 · zulu 37
  davon mit Forensik                  163
  davon mit Trade-Datei               193
Überschneidung (gleiche Quelle+ID)     171
Katalogzeilen ohne Workflow-ID       1283
Ergebnisse-Ansicht                    194   (= signals, live)
Alle-Signale-Ansicht                 1477   (= 194 + 1283)
Quellenübergreifende ID-Kollisionen     0   (geprüft in beiden Tabellen)

```





Alle Abweichungen erklärt. Identitätsprüfung: `signals` hat `quelle`, PK ist aber **nur** `signal_id`; `katalog_signale` hat korrekt `PRIMARY KEY (quelle, signal_id)`.


## 4. Bestätigte Fehler


### F1 — Laufende Quell-Builds sind älter als die Korrekturen im Arbeitsbaum


**P1, im Betrieb beobachtet.** Alle fünf Dienste starteten **18.10. 12:01**; die MqlDownloader-Fixdateien wurden **12:37/12:37** und Vantage **12:44** geändert. Verhalten verifiziert:



- Vantage: `trades.csv` für 1419494 / 1286742 / 1096166 → **404** (nur der alte Build).

- MqlDownloader: `weeks` durchgehend leer — der belegte Alterswert aus `ProviderAge.java` (13:07) fehlt im Lauf.



Die Fixes sind also **nicht** live. Ohne Neustart wirken sie in keinem Scan.


### F2 — Scanner lädt nie den Vollkatalog; Quellen-Filter ≥1 Abonnent greift unsichtbar


**P1, reproduziert.** `downloader_client.katalog()` sendet nur `limit`/`offset` — **kein `minSubscribers`**; es gibt im Scanner **keinen** Code und **keinen** Test dazu. Beleg direkt gegen den laufenden Dienst:
































| Dienst | Scanner holt (`/providers`) | Vollkatalog (`minSubscribers=0`) | unsichtbar |
| --- | --- | --- | --- |
| pelik | 640 | **2188** | 1548 (71 %) |
| mql5 | 216 | **236** | 20 |
| rob о | 200 | 200 | 0 |



Damit widerspricht die Praxis der eigenen Dokumentation (`doc/23:373`, `AGENTS.md:1518`): „der KATALOG bleibt vollständig (2250/648 …)". Tatsächlich ist er auf die abonnentenstarken Provider beschnitten. **Auswirkung:** Ein Signal mit 0 Abonnenten, das später Abonnenten gewinnt, ist bis zum nächsten Vollsync unsichtbar; „Alle Signale" ist nicht „alles, was die Clients melden".


### F3 — Kein gespeicherter Befund hat die aktuelle Forensikversion


**P2, im Betrieb beobachtet.** `FORENSICS_VERSION = 19`; Verteilung im Bestand: `{15: 104, 14: 10, 7: 27, 16: 15, None: 4}` — **0× Version 19**. Folge (korrekt abgesichert): alle 194 Zeilen werden als `forensik_stale` erkannt, Grün/Gelb bleibt gesperrt, Score/H1-DD/TrueRetDD sind in der Ergebnistabelle durchgehend leer. Das Schutzverhalten ist richtig, der Bestand aber faktisch ungeprüft. Datenstand der Forensik: 16.10. (15), 08.10. (104).


### F4 — Zulu-Vollständigkeitshinweis wird vor Fix verschluckt (im Lauf bestätigt)


**P2, live verifiziert.** Zulu liefert `TradesCompletenessNote`; das laufende Build liefert es, der Scanner liest vor dem Fix nur `CompletenessNote`. Der Hinweis auf Kappung/älteren Stand geht verloren (die separate Kappungsflagge bleibt).


### Behoben im Arbeitsbaum (von mir nachgeprüft, daher **nicht** in der Laufzeit)



- **P1-2 (Vorfund)** `parser.load_export(Path)` → jetzt `path = str(path)` (Zeile 110).

- **P1-1 (Vorfund)** Wochen-Vorfilter: `ingest.py`-Kommentar korrigiert.

- **Katalog-Pagination** (`hole_katalog`): vollständige Abschlussprüfung. Eigene Probe mit 7 Fällen (total drift, fremder Offset, Überlauf, doppelte Identität, fehlendes `total`, gültige 2-Seiten, gleiche ID/verschiedene Version) → **7/7 korrekt**.

- **Befund↔Snapshot-Bindung:** `store_scan_result(..., expected_trades_sha256=...)` erzwingt vor der Analyse geprüften SHA.

- **Vantage F1** und **MqlDownloader F3** sind im Quellcode korrigiert, aber (siehe F1) nicht ausgerollt.

- **F5** `TradesCompletenessNote` + `CompletenessNote` beide gelesen.



## 3. Spaltenzuordnung (Auszug, vollständig nachgeprüft)


















































| Tabelle | Spalte | Quelle | Transformation |
| --- | --- | --- | --- |
| Ergebnisse | Ampel, Score, Urteil | `forensik.json` / `refresh_efficiency` | bei `forensik_stale` gesperrt |
| Ergebnisse | Abonnenten, 7/30 Tage | `downloader_sync.abo_bilanz` | live aus Quellen-`/history` |
| Ergebnisse | Max-Drawdown % | `max_drawdown_equity_pct` | **nur** eigene H1-Messung |
| Ergebnisse | TrueRetDD | `retdd_jahr` | CAGR ÷ H1-Equity-DD (Calmar) |
| Alle Signale | 4 DD-Spalten nebeneinander | Plattform·Trading·True·True≈ | nicht vermischt |
| Alle Signale | Quellenkatalogzeilen | `katalog_signale(quelle, signal_id)` | dedupliziert gegen Workflow |



Leere Zellen sind begründet (fehlende Trade-Datei, USD-Sperre, veraltete Forensik) — **nicht** aufgefüllt.


## 5. Ausgeführte Tests












































| Suite | Ergebnis |
| --- | --- |
| SignalKiScanner (voll) | **2499 passed**, 4 deselected (LLM-Marker), 0 failed |
| davon 9 neue Audit-Dateien | 94 passed |
| MqlDownloader | 148 passed |
| Vantage | 88 passed |
| RoboForex | 183 passed |
| ZuluMonitor | 120 passed |
| PelicanTrading | 180 passed |
| Integrität | 193/193 Trade-Dateien SHA-konform, 0 fehlend |



Eigene Reproduktionen: Katalog-Seitengrenzen (7/7), Vollkatalog-Scope am Request (monkeypatched `_get`), Zeilenbilanz beider Tabellen mit produktivem Codepfad, Live-Verhalten der laufenden Builds.


**Prüflücken:** Streamlit-Browserrendering (AppTest ja, Sichtprüfung nein), H1-Kursabdeckung pro Fenster, tatsächlicher Vollscan eines Tages, LLM-Pfade (kostenpflichtig), MqlRealmonitor/PelicanWinnerLooser (auftragsgemäß außen vor).


## 6. Korrekturvorschläge



1. **Sofort:** Alle fünf Dienste aus dem aktuellen Quellstand neu bauen und neu starten — die Fixes zu MqlDownloader-`weeks`, Vantage-Historien und Zulu-Hinweis wirken sonst nicht (F1).

2. **Sofort:** `downloader_client.katalog()` und `hole_katalog` um `minSubscribers=0` für den Vollkatalog-Sync erweitern, plus Test. Alternativ die Doku-Behauptung „Katalog bleibt vollständig" zurücknehmen (F2).

3. **Bald:** Vollscan ausführen, um Befunde auf Version 19 zu heben (F3); bis dahin bleibt Grün/Gelb erwartungsgemäß gesperrt.

4. **Mittel:** Composite-Identität `(quelle, signal_id)` als PK auch in `signals` (heute nur abgewehrt, nicht migriert).



**Kein „alles korrekt":** F1 (Build-Drift) und F2 (Vollkatalog-Scope) sind bestätigt. Innerhalb des nachgewiesenen Umfangs bestehen Pagination, Integrität, Spaltenzuordnung und die Stufe-0-Abschlusslogik (strikte Job-ID-Bindung, Timeout, Teilfehler als `teilweise`, Abbruch bei Totalausfall).