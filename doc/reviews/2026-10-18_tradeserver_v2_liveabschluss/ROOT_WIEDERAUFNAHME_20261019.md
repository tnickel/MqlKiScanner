# Wiederaufnahme am 19.10.2026

Der Nutzer hat mit „guten morgen mache weiter“ ausdrücklich fortgesetzt.
`FORTSETZUNG.json` bleibt der unveränderte Pausenbeleg vom 18.10.; neue
private Laufdaten liegen unter `data/runs/liveabschluss_20261019/`.
Dieses Dokument ist ein Zwischenstand, kein Abschluss aller Quellen.

- Scanner-DB vor neuen Schreibphasen per SQLite-Onlinebackup gesichert;
  Integrität `ok`, keine Fremdschlüsselfehler.
- Die früheren nativen Prozesse sind beendet. Ihre Abschlussbelege werden
  unabhängig geprüft; alte PIDs und ein Dienstneustart beweisen keinen
  erfolgreichen Datenabschluss.
- Zulu: Nachtjob 200 beendet, davon 171 Historien aktualisiert und 29 Fehler.
  171 ausgewählte unveränderliche Generationen mit insgesamt 650.425 Zeilen
  offline auf SHA, Eigentümer, eindeutige IDs, Pflichtzahlen und UTC geprüft.
  Sieben Althistorien ohne Verifikationsmarker werden gezielt vollständig
  neu von der Quelle geladen. Alte flache Dateien bleiben bytegleich.
  Der Dienst bleibt während dieser expliziten Reparatur offline. Die
  Reparatur verwendet die vorhandenen `saveTrades`- und
  `saveHistoryReceipt`-APIs in zwei getrennten atomaren Publikationen;
  erst nach dem finalen Generationennachweis darf die REST-API starten.
- MQL: tatsächlicher Nachtabschluss 92 MT4 plus 176 MT5, keine nativen
  Downloadfehler. Rename-Metrics-Zuordnung für zwei Provider wird separat
  korrigiert und erneut abgenommen. Keine vorzeitige Quellenfreigabe.
- Pelican, Vantage und Robo haben getrennte Quellenprüfungen; deren
  jeweilige Belege dokumentieren Umfang, Grenzen und Paketbindung.
- FT5: eigener strikter Studienlauf gestartet. Eingaberefresh `total=5`,
  `fetched=5`, `failed=[]`; das Threadende und die gespeicherten Studien
  sind anschließend separat abgenommen worden. Dies sind die verifizierten
  FT-Generationen und kein vorweggenommener Abschluss des Vantage-Folgejobs.

## Enger Parsernachtrag

Der belegte MT5-Exporttyp `Deal Interestrate` mit ausschließlich Time, Type
und Profit wird als vorzeichenbehaftete Ergebnisbuchung (`AccountCostRow`)
eingelesen. Er ist weder Position noch externer Kapitalfluss. Die offizielle
[MQL5-Dokumentation](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties)
führt `DEAL_TYPE_INTEREST` als „Interest rate“. Die Zuordnung des exakten
CSV-Texts ist aus Bezeichnung und Struktur begründet; eine im CSV nicht
vorhandene Enum-ID wird nicht behauptet.

Unbekannte andere Deal-Typen, abweichende Pflichtstruktur, nicht endliche
Beträge und eine unbewiesene MT4-Entsprechung bleiben Fehler. Bestehende
Pflichtprüfungen und Bewertungsregeln ändern sich nicht; der Parser kann
eine bisher vollständig abgewiesene Exportform einlesen. Version 21 bleibt.

37 gezielte Parser-/Kostenverbrauchertests bestanden. Alle 268 nativen
MQL-Exporte wurden erneut gegen die zuvor gesicherten SHA-Werte geparst.
Der bisher abgewiesene Export #2236750 enthält 1.710 Positionen und
38 zusätzliche Zinsbuchungen. Das ist ein Importnachweis, keine positive
Signalbewertung. Vollständiger Nicht-LLM-Regressionstest: 2.817 bestanden,
ein Windows-Symlinktest übersprungen, vier Modelltests abgewählt;
447,28 Sekunden. Privates JUnit liegt in `parser_checks/full.xml`.
Unabhängiges enges Parserreview ohne konkreten Befund abgeschlossen.

## Getrennte Scannerphasen

- Katalog-Metadaten: MQL 372, Pelican 2.190 importiert (jeweils
  `minSubscribers=0`). Der Katalogumfang ist kein Trade-Downloadumfang.
- Quellenchronik append-only ergänzt: MQL-Nachtabschluss id67 und
  Pelican-Folgejob id68 fertig; Zulu-Nachtjob id69 ausdrücklich teilweise.
- Produktionsauswahl mit normalen Top-N-/Fix-Regeln plus vorhandenen
  Workflowköpfen und Schnitt mit verifiziertem Quellenumfang: 35 Pelican,
  63 MQL. Zwölf alte MQL- und vier alte Pelican-Workflowköpfe liegen
  außerhalb und erhalten dadurch keine frische Freigabe.
- Strikter FT-Abschluss: alle fünf Studien mit Quelle, UID, Version21
  und aktuellem Trade-SHA gebunden. Alle fünf verwenden eine ausdrücklich
  virtuelle Kapitalbasis. Nur #1231244 ist innerhalb dieser Annahme
  methodisch vollständig; vier Studien bleiben unvollständig. Keine
  neue belastbare Realkonto-Effizienz aus diesen Studien ableiten.
  Siehe `ft5_studies_binding_acceptance_20261019.json`.

Automatik bleibt aus. MqlRealmonitor-Integration bleibt zurückgestellt.
Keine Commits oder Pushes ausgeführt.

## Geprüfter Zwischenstand, 19.10. gegen 10:20 MESZ

- MQL-Quellenpaket mit 166 Tests regulär aktiviert. Zwei umbenannte
  Provider verwenden die zur aktuellen CSV-Dateifamilie gehörenden Metrics;
  alle 268 Exporte und Metrics wurden danach separat abgenommen.
- Pelican-Normaljob: 200 beendet, 199 erneuert, eine Historie frisch,
  keine nativen Downloadfehler. Ein Export mit zwei originalen Nullpreisen
  bleibt ausdrücklich nicht für Scanner-Forensik verfügbar.
- Pelican-Sessionerneuerung korrigiert und mit 183 Tests geprüft; reguläres
  Paket im Leerlauf ersetzt. Der zusätzliche Workfloweintrag #2086522
  wurde separat von 359 auf 531 native Positionen aktualisiert, gescannt
  und in einer eigenen Studie gerechnet. Er gehört nicht nachträglich
  zum 200er-Job.
- Scanner-Forensik innerhalb des belegten Umfangs: Pelican 35 versucht,
  32 vollständig, drei unbelegte Axi-Kontrakte; MQL 63 versucht,
  45 vollständig, 18 Währungs-/Kapitalbasis- oder weitere explizite
  Eingabefehler. Alle Versuche persistiert, keine Ersatzfreigabe.
- 32 Pelican- und 45 MQL-Studien frisch geladen und gerechnet, keine
  Studienfehler. Alle 77 Bindungen unabhängig lesend geprüft: Quellen-UID,
  signal_ref, Version21, Laufzeit und Trade-SHAs stimmen mit Forensik,
  Quellenartefakt und tatsächlichen Dateien überein. Pelican verwendet
  hierbei virtuelle Studien; diese sind keine Realkonto-DD-Messung.
  Kurzbeleg: `studies77_binding_acceptance_20261019.json`.
- Robo: 17 native Reparaturen abgeschlossen. Im geprüften 200er-Umfang
  liegen 197 MT-Historien mit 1.503.461 Zeilen vor; drei RStocks-Konten
  gehören nicht zum unterstützten MT-Trade-Endpunkt. Native Geld- und
  Volumeneinheiten bleiben unbelegt, daher weiterhin keine Scanner-CSV.
  Die alten 33 Workflowköpfe benötigen eine negative Nachprüfung; allein
  der neue Exportguard ist noch kein korrigierter Scannerbestand.
- Drei alte katalogreine Robo-RStocks-Claims waren durch einen belegten
  historischen REST-Fallback fälschlich MT4. Eine gezielte, gesicherte
  Datenkorrektur wird ausschließlich auf Datenbankkopien vorbereitet;
  der allgemeine Plattformguard bleibt unverändert.
- Vantage: getrennten aktuellen 19er-Snapshot erneut gescannt, 19
  persistiert. Fehlende echte Kapitalbasis bleibt eine Sperre. 14
  zusätzliche Studien mit eigenem frischen Eingaberefresh 14/14 laufen;
  die fünf FT-Studien sind bereits separat abgenommen. Der normale
  Quellenjob mit tatsächlichem Umfang 215 ist weiterhin aktiv und durch
  diesen Zwischenstand ausdrücklich nicht abgeschlossen.
- Zulu: sieben gesonderte Neuabrufe bis zum API-Ende beendet. Die alten
  171 Generationen und die sieben neuen Endbelege werden vor dem normalen
  Dienststart zusammen geprüft. Originale totalAvailable-Zahlen können
  von den abgerufenen Zeilen abweichen; ohne weiteren Beleg wird daraus
  kein statischer vollständiger Kontosnapshot abgeleitet. Zwei negative
  Originalzählungen und 20 ungültige Antwortschemata bleiben Fehler.
- 78 aktuelle vollständige Forensik-Ergebnisse benötigen neue KI-Berichte:
  16 grün, 31 gelb, 20 rot, elf ausgeschlossen. Grün/Gelb erhalten
  Priorität. Das bestehende Tages-/Monatsbudget bleibt 500.000/5.000.000;
  zu diesem Zeitpunkt noch keine heutigen Modellkosten.
- Remote v2 zuletzt erneut ausschließlich lesend über den tatsächlich
  laufenden H2-TCP-Server geprüft: Run13 unverändert, 199 Signalzeilen,
  keine aktuellen PDFs, keine offenen Runs. Die 32 historischen Signale
  und 313 historischen PDFs sind unverändert. Dies ist weiterhin ein
  Zwischenstand; neuer Sync samt aktueller PDF-Abnahme steht noch aus.

## Folgebelege gegen 10:42 MESZ

- Vantage14-Studienlauf beendet: Refresh14/14, gerechnet14, Fehler0.
  Alle 19 Bindungen einschließlich der früheren FT5 unabhängig geprüft.
  Sieben virtuelle Studien methodisch verlässlich, zwölf unvollständig;
  alle 19 Workflow-Forensiken bleiben ohne belegte Startkapitalbasis
  unvollständig. Kein Jahres-Calmar und kein Grün aus diesen Studien.
  `vantage19_ft5_binding_acceptance_20261019.json`.
- Robo: gezielte Drei-RStocks-Datenkorrektur am 19.10. 10:34:19 MESZ
  atomar angewendet; regulärer Katalog200 anschließend erfolgreich.
  Ein unabhängiger Nur-Lese-Abgleich bestätigt unveränderte Eigentümer,
  Referenzen und alle ursprünglichen Metrics. Der allgemeine Plattformguard
  ist unverändert. Nachprüfung der alten 33 Workflowköpfe um 10:37:10 beendet:
  30 Einheiten-/Währungsnachweise fehlen, drei NotFound. 33 gespeichert,
  keine vollständige aktuelle Forensik. 116 historische KI-Berichtszeilen
  sowie die gesamte Quarantäne einschließlich 1.572 Altstudien bleiben
  erhalten; kein aktueller eigener Robo-Bericht ist exportierbar.
  `robo_maintenance_acceptance_20261019.json`.
- Zulu: normales sichtbares Paket149 aktiv, REST8093 im Leerlauf.
  Exakt 178 aktuelle Exporte mit insgesamt 729.509 Zeilen bis hin zu den
  tatsächlichen CSV-Bytes und einzelnen Kernfeldern abgenommen. Alle 178 wurden
  zusätzlich mit dem aktuellen Scanner-Parser eingelesen: keine Fehler,
  keine Zeilen entfernt, alle SHAs vorher/nachher unverändert. API-Ende
  und bewegliche Ursprungszählung bleiben sauber getrennt.
  `sources_zulu_acceptance_final_20261019.json` und
  `zulu_parser_acceptance_178_20261019.json`.
- Präzisierung der Zulu-Rest22: 20 CSV404, zwei alte SHA-verifizierte
  Flat-Exporte weiterhin CSV200 mit fehlendem Paging-Endbeleg. Dies ist
  die dokumentierte historische REST-Lesbarkeit, keine neue Vollständigkeit
  und kein frischer Quellenabschluss. Beide sind aus der aktuellen
  Produktionsauswahl ausgeschlossen; keine globale Receipt-/Grün-Regel
  nachträglich eingeführt. `zulu_legacy_fallback_triage_20261019.json`.
- Zulu-Katalog200 importiert. Produktions-Top30/Fix plus37 alte Köpfe,
  geschnitten mit den178 belegten Exporten: 35 Kandidaten, keine
  Identitätskonflikte; drei alte/normale Kandidaten außerhalb bleiben
  ohne frische Freigabe (#425666,#426987,#430016). Neu in der Auswahl ist
  nur #430815. Forensik und danach explizite35Studien laufen getrennt.
- Vantage-Normaljob215 weiterhin aktiv. Reihenfolgekorrektur separat:
  frühere scope_position_one_based war REST-Sortierung, nicht native
  Jobfolge. FT5 stehen tatsächlich auf201–205. Die verifizierten
  SHA-/Zeilenbefunde der unveränderten 19er-Snapshots bleiben gültig.
  `sources_vantage_job_order_correction_20261019.json`.

## Laufender Anschluss, 19.10.2026 gegen 11:20 MESZ

- Zulu35: frischer Eingabenabruf 35/35 ohne Fehler. Die laufenden Studien
  sind noch nicht abgeschlossen; insbesondere ist #304366 mit 9.250 Trades,
  22 FX-Symbolen und Historie seit 2015 ein umfangreicher Kurslückentest.
  Eine laufende Cache-Schreibung belegt für sich keine neuen Kursbars.
  Die rein lesende Performanceprüfung trennt einzelne Versuchsspannen von
  gebündelten SDK-Abrufen. Produktive Cache-Regeln bleiben unverändert.
  Die Original-Forensikbilanz ist 33 fehlende reale Kapitalbasen plus zwei
  unbelegte Kontrakte (#429464: U; #427110: F40), keine vollständige Forensik.
  Neue Studien belegen keine nachträgliche Freigabe dieser Fehler. Historische
  Forensik-Payloads nach einem frühen Engineabbruch bleiben getrennt sichtbar.
- Genau eine lokale Python-Fortsetzung wartet auf das belegte Ende des
  bestehenden Zulu-Koordinators. Danach erstellt sie den aktuellen
  Berichtsumfang neu und startet die normale Berichtskette innerhalb der
  unveränderten Tages-/Monatsbudgets. Keine Wiederholungsautomation.
  Die zuvor versuchte PowerShell-Dateiausführung scheiterte an der lokalen
  Ausführungsrichtlinie, bevor das Skript lief; die Richtlinie wurde nicht
  verändert. Der Python-Nachfolger ist nach Prozessstartzeit gebunden.
- Die spätere Remote-Abnahme ist vorbereitet: direkter Python-Aufruf des
  bestehenden TCP-Leseaudits sowie ein reiner Offlinevergleich aller 52
  Wirefelder, Besitzerpaare, PDF-BLOB-SHAs und Legacybestände. 16 synthetische
  Fälle bestanden. Dies ist noch kein Beleg eines neuen produktiven Syncs.

## Weitere abgeschlossene Schritte, gegen 11:40 MESZ

- Zulu35 endet um 11:34:16 MESZ: 35 gerechnet, keine übersprungen,
  keine Berechnungsfehler. Unabhängige RO-Abnahme bestätigt alle35
  Quellen-/Besitzer-/Versions-/Datei-/Studienbindungen. 33 aktuelle
  Teilpayloads; für die zwei unbelegten Kontrakte existiert ausdrücklich
  kein Forensikpayload. Alle35 Studien sind virtuell, 15 mit positivem
  Verlässlichkeitsflag; daraus entsteht keine Workflowfreigabe.
  `zulu35_study_binding_acceptance_20261019.json`.
- Danach produktive Cache-SQL-Optimierung eingebaut: zwei
  Primärschlüssel-Randabfragen statt kombinierter MIN/MAX-Vollsuche,
  Ablaufindex für das unveränderte globale Aufräumen. 235 gezielte
  Cache-/Portable-/Studienregressionen bestanden. Kein manuelles
  produktives Cache-DDL; der Index entsteht beim nächsten normalen
  Cache-Aufruf. Die frühere Vollsuite2817 ging dieser SQL-Änderung voraus.
  `kurs_cache_optimization_acceptance_20261019.json`.
- Normale Berichtskette seit 11:34:19 MESZ aktiv; erstes Pelican-Profil
  #2086522 hat Trade- und Risikoanalyse gespeichert, Gesamtbericht läuft.
  Unveränderte Budgets500k/Tag und5M/Monat; noch kein neuer Syncabschluss.
- Einmaliger Anschluss wartet auf die bestehende Berichtskette und führt
  danach normalen Spiegel/PDF-Prüfung/Tabellenprüfung/v2-Sync mit echtem
  Remote-BLOB-/Besitzervergleich aus. Der erste Anschluss ist ausdrücklich
  ein Zwischenstand; er behauptet keinen Vantage215-Gesamtabschluss.
- Vantage-Normaljob weiter aktiv. #376760 „Jessi“ wurde wegen ungültigem
  openPrice abgewiesen; alte v1-Dateien896Zeilen bleiben bytegleich,
  REST-CSV404. Keine Behauptung zur ursprünglichen Ursache des Preises.
  Ein separater begrenzter Teilabschlussprüfer wird vorbereitet, damit
  belegte übrige Exporte nicht mit einem pauschalen215-Erfolg verwechselt
  oder wegen dieses einen Fehlers verworfen werden. Die früheren strikten
  Lesehelfer bleiben unverändert. `sources_vantage_jessi_rejection_20261019.json`.

## Tatsächlicher Zwischenabschluss, 19.10.2026 12:07 MESZ

- Die Berichtskette hielt an der vorhandenen Tagesbudgetschranke an:
  16 Prompts fertig, ein ausschließlich budgetbedingt abgewiesener Prompt,
  31 übersprungen. Die nächste Reservierung von 59.246 Tokens hätte
  441.737 verbrauchte/reservierte Tokens plus 59.246 über 500.000 gebracht.
  Keine Budgeterhöhung und kein Modell-/APIfehler als Budgetfall umgedeutet.
  Dieser Teilabschluss ist keine vollständige Erneuerung aller KI-Berichte.
- Danach liefen normaler Spiegel, lokale PDF-Materialisierung, Verify,
  Manifest, produktiver v2-Publish und direkter Remote-TCP-Leseaudit.
  Alle sieben Kindphasen endeten mit Exit0. Tatsächlicher RemoteRun14:
  204 Workflowköpfe und 95 PDFs (16 aktuelle eigene Analysen und79 originale
  Quellenberichte). Diese PDFs stammen ausschließlich aus Pelican und MQL;
  es wurden keine Zulu-/Vantage-/Robo-Berichte erfunden.
- Der reine Vergleich bestätigt 827 Checks ohne Lücke: alle52 Wirefelder,
  Besitzerpaare und Anzeigereihenfolge sowie tatsächliche PDF-BLOB-SHAs und
  Größen. Remote: keine falschen Dokumentbesitzer, keine BLOB-Hashfehler,
  kein offener Lauf. Legacy32Signale/313Dokumente und der bereitgestellte
  WAR bleiben unverändert. Der Audit liest nur den vorhandenen WildFly-H2-
  TCP-Listener, ohne eingebettete oder Backup-Datenbank.
- Scanner-Verify: Integrität ok, FK0, 204 Workflowköpfe, 2.981 reine
  Katalogeinträge, 78 aktuelle und62 ältere Forensiken, 132 aktive Studien
  (87virtuell). Es handelt sich um die tatsächlichen sichtbaren Zustände,
  keine Behauptung von204 frisch erfolgreichen Analysen. Die35 virtuellen
  Workflowkapitalbasen und ihre Hinweise bleiben erhalten; sie belegen keinen
  realen Kontodrawdown. Kriterien unverändert Version21/DD50/Calmar3/Monat0.
- Beleg: `tradeserver_v2_intermediate_acceptance_20261019.json`.
  Vantage-Nativjob ist zu diesem Zeitpunkt weiterhin aktiv (64/215 beobachtet
  12:08 MESZ), bestätigter bisheriger Fehler #376760 Jessi. Deshalb wird
  ausdrücklich kein Gesamtabschluss des Quellenjobs behauptet.

## Laufende einmalige Vantage-Fortsetzung, 19.10.2026 12:12 MESZ

- Root hat den finalen Parent nach getrennten Quell-/Receipt-/Auswahl-/
  Studienbindungsreviews freigegeben. 136 aktuelle Code-/Vertrags-/Promptdateien
  sind per SHA eingefroren. Ein weiterer neuer Wartertest bestätigt20 reine
  Fälle mit dem echten Parent-Vergleich auf temporären Dateien.
- Tatsächlich gestartet: lokaler Python-Warter PID311692, 12:12:27 MESZ.
  Er ist an den bestehenden Source-Teilprüfer PID299388 samt tatsächlicher
  Prozessstartzeit und Handle gebunden. Der bereits abgeschlossene
  Zwischenlauf wird über seine echten End-/Vergleichs-/Input-SHAs gebunden;
  der inzwischen beendete Prozess PID214200 wird nicht erneut gestartet.
- Startzustand erfolgreich geprüft: wartet auf Source-Teilabschluss,
  stderr0Bytes, noch kein vorzeitiger Parentlauf und keine native
  Abschlusschronik. Nach tatsächlichem Source-Endbeleg folgen einmalig
  append-only Quellenchronik, normaler Katalog/Produktionsscope,
  explizite Forensik/Studien mit unabhängiger Bindungsprüfung sowie
  neuer v2-Abgleich mit echtem Remote-TCP-/PDF-BLOB-Vergleich.
- Keine neue native Updateanforderung, keine KI-Aufrufe, keine Budget-
  oder Kriterienänderung und keine wiederkehrende Codex-Automation.
  STOP, Fehler, geänderte belegte Dateien oder unerwarteter Berichtsscope
  stoppen geschlossen zur Root-Prüfung. Es gibt keinen automatischen Retry.
- Der bestehende Vantage-Nativdownload bleibt der zeitbestimmende offene
  Schritt; dessen Lauf wird nicht als erfolgreicher215-Gesamtabschluss
  bezeichnet. Beleg: `vantage_finite_continuation_started_20261019.json`.



## Nutzerfreigabe und vollstaendige Berichtswiederaufnahme, 19.10.2026 13:51 MESZ

- Der Nutzer verlangte zunaechst500k->1,5M/Tag und bestaetigte anschliessend
  ausdruecklich weitere benoetigte Tages-/Monatserhoehungen fuer den kompletten
  Analyselauf. Produktive Settings jetzt10M/Tag,10M/Monat, Laufbudget unveraendert
  10M. Dies sind lokale Scannergrenzen; kein abgefragtes z.ai-Kontoguthaben.
  Bewertungsregeln und Automatik bleiben unveraendert.
- Vor Settings-/Codeaenderungen wurde nur der wartende alte Python-Warter311692
  nach PID/Geburt/CLI/Status und Ausschluss von Arbeitskindern beendet. Native39932,
  Source-Teilpruefer299388 und alte Belege blieben unberuehrt. Alter Run14 und
  dessen500k-Budgetabschluss sind historische Nachweise, keine neue Freigabe.
- Wiederaufnahmeluecke im normalen LLM-Runner geschlossen: bereits gespeicherte
  Stufen werden nur bei gleicher Quelle, aktueller Bewertungsbasis und nichtleerem
  Text wiederverwendet. Nur fehlende Trade-/Risiko-/Gesamtberichtsstufen zaehlen
  als neue Arbeit. 91 gezielte Mock-/TempDB-Tests bestanden. Budgeterhoehungen
  veraendern die Bewertungsbasis nicht. Beleg: `llm_stage_resume_acceptance_20261019.json`.
- Neuer fester RO-Plan:73Profile (45MQL/28Peli),218fehlende Stufen;5komplettePeli-
  Berichtstripel und eine bestehende GOLDBR-Tradeanalyse bleiben erhalten. Tatsachlich
  gestartet Queue422660 um13:51:39MESZ mitKind427216. Erster Logeintrag fordert nur
  die fehlende GOLDBR-Risikoanalyse an. Unabhaengiger RO-Abgleich bestaetigt deren
  Nachrichtenhash und exakt unveraenderte gespeicherte Tradeanalyse. Erste neue
  HTTP-Antwort200; ein normaler Laengenretry fordert mehr Antwortbudget an.
- Neuer einmaliger Anschluss411092 ist an den echten neuen Queueprozess gebunden.
  Neuer Warter441932 bindet Source299388 und Anschluss411092 ueber echte Handles
  und Geburtszeiten. Er wartet auf neue Bericht-/v2-Zwischenbelege und die tatsaechliche
  Schema2-Source-Teilabnahme. Danach normaler begrenzter Vantage-Daten-/Studienlauf
  und separater v2-Folgeabgleich. 42 reine Guards bestanden; Root versiegelt144
  Dateipins. Unabhaengiger RO-Startcheck144/144 und143/143 am19.10.13:58MESZ bestanden.
- Keine neue wiederkehrende Automation, kein nativer Update-POST und kein
  vermeintlicher Gesamtabschluss. Teilhistorien, Sourcefehler und virtuelle
  Kapitalbasen bleiben explizit. Aktueller Vantagefortschritt125/215 beim Beleg.
  Belege: `user_approved_full_report_restart_20261019.json` und
  `full_report_and_source_continuation_started_20261019.json`.
