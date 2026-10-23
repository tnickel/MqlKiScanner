# Liveprüfung der Abonnenten-Recherche am 23.10.2026

Auftrag: wiederkehrende Fehler selbst im echten Ablauf nachstellen und korrigieren.
Diese Prüfung ist **noch kein erfolgreicher Abschluss des Gesamtauftrags**.

## Belegter externer Blocker

Vantage liefert weiterhin den internen Plattformfehler 1223. Der heutige
Webseitenmodus 7 scheitert ebenfalls; Modus 10 konnte 54 Seiten liefern,
scheitert aber auf Seite 55. Der Fehler bleibt bei Seitengröße 1 an Position
5423 bestehen. Kleinere Seiten oder ein bloßer Sortierwechsel lösen ihn damit
nicht. Andere Monatsfenster haben einen anderen angebotenen Katalogumfang;
ein Austausch einzelner Seiten würde keine vollständige Auswahl belegen.

Kein Überspringen dieser Position, keine Veröffentlichung einer vermeintlich
vollständigen Vantage-Top-200-Auswahl. Details und sanitisierte Messbelege:
`../2026-10-23_vantage_sortierung/README.md` sowie
`data/runs/vantage_sort_fix_20261023/probe_sort10_single_row_1223.json`.

## Lokale Korrekturen

- CLI `python -m mqlkiscanner.abonnenten_analyse --resume LAUF_ID` wartet auf
  den tatsächlichen Worker-Abschluss einschließlich Aufräumen. Unterschiedliche
  Exitcodes für Erfolg, Teilergebnis, laufenden Auftrag und Unterbrechung;
  sichere Ausgabe von Emoji-/CJK-Anbieternamen unter Windows-cp1252.
- Der Arbeitsablauf folgt Quellenreihenfolge und Abonnentenzahl. Die Auswahl
  und Berechnung der Rangliste ändern sich dadurch nicht.
- Historische Refreshwarnungen tragen Laufkennung, Start-/Endzeit und die
  damaligen Client-Jobkennungen. Sie behaupten keinen aktuellen Clientfehler.
  Recherchewarnungen beziehen sich ausdrücklich auf den ausgewählten Auftrag.
- Bereits berechnete Ausschlussbefunde bleiben auch dann erhalten, wenn eine
  nachfolgende Kapital- oder Kursprüfung keine vollständige Auswertung erlaubt.
- Größere KI-Tradeblöcke mit Prüfung des fertig ausgefüllten Prompts reduzieren
  unnötige Aufrufe. Alle Trade-Vorkommen, Belegpfade und Randüberlappungen
  bleiben erhalten; das vorhandene Eingabelimit und sämtliche Budgets gelten
  weiter. Offlinevergleich: Gold Reaper 904 Trades, 14 auf 5 Blöcke; die 19
  gesicherten Zulu-Profile 993 auf 352 Blöcke. Keine Live-KI durch diese Messung.
- Im Live-Stopp fiel eine weitere Ursache auf: Ein Timeout der CIM-Abfrage
  wurde als leere Prozessliste behandelt. Das konnte offene Kurs-Terminals
  fälschlich als beendet bestätigen. Die Korrektur verwendet eine pfadgenaue
  Prozessabfrage und unterscheidet einen unbekannten Zustand von Prozessende.

## Tatsächlicher Laufstand

Vorhandener Auftrag `d38440b65c6540b79ce69e7fe7457ab0` wird fortgesetzt;
er wird nicht durch einen neuen Auftrag mit neuer Auswahl ersetzt.
Der alte Worker-PID 1454064 war beim erneuten Prüfauftrag nicht mehr vorhanden.
Der anschließende CLI-Lauf PID 1414980 wurde für die Aktivierung der
Korrekturen kontrolliert gestoppt; abgeschlossene Stufen bleiben gespeichert.

Gold Reaper wurde im echten Lauf neu beschafft und berechnet: 904 Trades,
H1-Equity-DD 19,459734187186978 %, Jahres-RetDD 5,438085710820148. Dies ist
ein einzelner vorläufiger Recherchekandidat, keine fertige Rangliste oder
Handelsfreigabe. H1-Schlüsse belegen keine Intrabar-Minima.

Zulu liefert für die geprüften Profile weder Initial Deposit noch eine
belegte Balance-/Einzahlungshistorie. Fehlendes Startkapital wird nicht durch
eine virtuelle 10.000-USD-Basis ersetzt. Die vollständigen vorhandenen Trades
können weiterhin einer Kurz-KI zugeführt werden; RetDD bleibt dabei unbekannt.

267 Recherche-/Client-/UI-Regressionstests bestanden vor der abschließenden
Terminalkorrektur. Der Fragedialog wurde zusätzlich im echten Browser geöffnet,
visuell geprüft und ohne einen zweiten Analyseauftrag geschlossen.
Weitere Lauf- und Aktivierungsbelege liegen lokal unter
`data/runs/abonnenten_live_repair_20261023/`.

Nach der Terminalkorrektur bestanden 268 Tests zu Prozessabfrage,
Markt-/Admin-Locks, Kursdaten, Kurscache und Recherche-Datenservice. Eine im
echten Cleanup beobachtete Exit-Race wurde anschließend zusätzlich korrigiert:
Ein leerer Pfad gilt nur bei gültiger PID und am selben Prozessobjekt nach
dem Pfadlesen ausdrücklich bestätigtem `HasExited=true` als beendet. Die
abschließende gezielte Auswahl bestand mit 147 Tests.

`terminal_cleanup.json` bestätigt beide Terminals ohne verbleibenden Prozess.
Der ursprüngliche Auftrag wurde am 23.10. um 17:17:59 MESZ mit den Korrekturen
als CLI-Prozess 1570604 fortgesetzt; Startbeleg, Standardausgabe und Fehlerlog
liegen im genannten Laufverzeichnis. Prozessidentität und gehaltenes gemeinsames
Lauf-Lock wurden unabhängig geprüft. Dies belegt den tatsächlichen Start,
**keinen abgeschlossenen Gesamtlauf**.

Vor der Budgetfreigabe waren im bestehenden Monatsbudget 8.518.681 Tokens
abgerechnet, zusätzlich 41.593 für einen unbestätigten alten Aufruf reserviert.
Diese Kosten/Reservierungen werden nicht gelöscht oder umgebucht.

## Budgetfreigabe für genau diesen Testauftrag

Der Nutzer hat ausdrücklich 50 Mio. Tokens je Lauf/Tag sowie 60 Mio. im
Monat für diesen Test freigegeben. Die drei Werte stehen ausschließlich in
`run.budget_settings`; neue Aufträge und die globale Einstellungsdatei erhalten
diese Erhöhung nicht. Der Launcher validiert erlaubte Budgetfelder und echte
positive Integer. Andere Felder können damit keine Modelle, Endpoints oder
Bewertungsregeln überschreiben.

Der laufende Prozess hatte noch die alten Grenzen im Speicher und wurde
kontrolliert beendet. 37 bereits abgeschlossene Datenversuche aus diesem
Prozess wurden für den reinen Budgetwechsel vorgemerkt: Wiederverwendung nur
bei unveränderter Berechnungsbasis, abgeschlossenem Status und gültigem
Trade-SHA, falls ein Trade-Snapshot vorliegt. Datenlücken bleiben unvollständig;
der einmalige Checkpoint wird nach der Datenphase geleert.

79 Budget-/Checkpoint-/CLI-/Koordinator- und Wiederaufnahmetests bestanden.
Der neue Prozess 1564988 hat den bestehenden Auftrag am 23.10.2026 um
17:57:22 MESZ fortgesetzt. `budget_applied.json` bestätigt am laufenden Worker
50.000.000 / 50.000.000 / 60.000.000, passende Prozessidentität und gehaltenes
Lauf-Lock. Der SHA der globalen Einstellungsdatei ist unverändert. Start,
Freigabe und Aktivierung sind im oben genannten privaten Laufverzeichnis
getrennt belegt. Dies ist weiterhin kein abgeschlossener Gesamtlauf.

## Logprüfung und gezielte Pelican-Reparatur am Abend

Bei der erneuten Logprüfung war der Scannerprozess 1564988 weiterhin aktiv.
Zulu lud für Anbieter 429450 rund 49.164 Trades seitenweise nach; derselbe
native Auftrag stieg bis 20:04:32 MESZ auf 45.500 Trades. Die unveränderte
Scanner-Detailzeile war kein Beleg für Stillstand. Ein Neustart des gesamten
Scanners wurde nicht durchgeführt.

Pelican hatte dagegen eine abgelaufene Sitzung. Alle 200 Pelican-Datenversuche
des Rechercheauftrags waren mit `DownloaderAuthError` fehlgeschlagen. Ein
gezielter reiner Abonnenten-Refresh erneuerte die Sitzung über den bestehenden
automatischen Login mit geschützter API-200-Prüfung und lieferte am 23.10. um
19:52:05 MESZ erfolgreich 200/200 Anbieter. Job:
`u-d15c462f-9bd5-45bf-8df0-cd13f75d1590`.

Im nativen Pelican-Client wurde der gezielte Anbieterabruf korrigiert: Nur bei
einem Sitzungsfehler wird die bestehende geprüfte Neuanmeldung ausgeführt und
derselbe Auftrag höchstens einmal wiederholt. Abbruch und sonstige Fehler
lösen keine Anmeldung aus; die Quellensperre bleibt währenddessen gehalten.
206 aktuelle native Tests bestanden. Die UI-Tests des Clients schrieben dabei
Fixture-Zeilen in sein produktives Log; diese Zeilen wurden unverändert
belassen und nicht als echte Anbieterereignisse gewertet.

Nur der zuvor untätige Pelican-Client wurde für das gebaute JAR kontrolliert
neu gestartet. Aktiver Java-Prozess danach: 1771872. JAR-SHA-256:
`c647623c24e3f26bb3a83b8919885fca44b2d2b63c75a0982ed36220f82519e6`.
Ein echter gezielter Abruf für den bereits ausgewählten Anbieter 2094777
lieferte anschließend 58 Trades, vollständige Historie seit 17.08.2026 und
keinen Trade-Listenfehler. Dies belegt die wieder funktionierende Beschaffung,
**keine nachgeholte Analyse aller 200 Pelican-Profile**. Deren vorherige
Datenlücken bleiben im laufenden Rechercheauftrag gespeichert.

Die Rechercheanzeige ergänzt jetzt den aktuellen nativen Downloadfortschritt
über einen vier Sekunden gecachten Status-GET. Lauf, Quelle, Anbieter,
Plattform und Versuchsbeginn müssen passen; alte oder fertige Aufträge werden
nicht angezeigt. 43 UI-/Prompttests bestanden. Ein zusätzlicher echter
Statusabruf durch diese Anzeige bestätigte den genannten Zulu-Fortschritt.
Private Belege: `pelican_session_repair_start.json`, `pelican_pre_restart.json`,
`pelican_fixed_start.json`, `pelican_provider_probe.json` und
`pelican_repair_and_progress_verified.json` im obigen Laufverzeichnis.

## Vantage: erlaubter Teilkatalog statt Komplettabbruch

Der Nutzer hat am Abend das Ausklammern fehlerhafter Listeneinträge ausdrücklich
beauftragt. Die neue Vantage-Logik isoliert ausschließlich API 1223 bis zur
Einzelposition und liest danach weiter. Livejob
`u-20261023-221429-63617715` endete um 22:16:51 MESZ mit 5.956 gelesenen
Anbietern, ausgelassener Position 1256 und 200 ausgewählten Anbietern. Der
Scanner spiegelte sie anschließend ohne Fehler. Der Beleg ist ausdrücklich
unvollständig (`subscriberCatalogComplete=false`); KI-/CSV-/PDF-Hinweise und
Recherche-Abschlussstatus erhalten diese Einschränkung. Details im Review
`../2026-10-23_vantage_sortierung/README.md`.

Der KI-Worker 1564988 wurde dabei nicht neu gestartet. Sein bereits vorher
eingefrorener Recherche-Snapshot enthält weiterhin den früheren gescheiterten
Vantage-Auswahlversuch; neue Vantage-Trade-/KI-Analysen stehen dort aus.
`vantage_skip_verified.json` bestätigt den neuen Zählerlauf, die Spiegelung
und die unveränderte Workeridentität. Der Gesamtauftrag bleibt offen.

## KI-Kurztests: lange Wiederholungen und ungültige Belege

Die Prüfung der Meldung zu MQL5 2339082 (GoldWave) am späten Abend zeigte
keinen lokalen Deadlock: Der alte Worker wartete auf Modellantworten und
wiederholte ungültige Antworten. NoPain und Gold Reaper New V2 verbrauchten
zuvor die Ausgabelimits von 6.144 und 12.288 Tokens überwiegend im Reasoning;
GoldWave lieferte vollständiges JSON mit nicht vorhandenen Faktenpfaden.
Die wiederholt gedruckte CLI-Detailzeile war jeweils derselbe gespeicherte
Hinweis, kein Nachweis eines neu aufgetretenen Fehlers.

Die Abonnenten-KI setzt jetzt explizit JSON-Ausgabe, 16.384 Ausgabetokens und
Reasoning `low` für Kurztests beziehungsweise `high` für Top 5. GLM-5.3 verwendet
laut [Z.ai-Dokumentation](https://docs.z.ai/guides/capabilities/thinking-mode)
erzwungenes Thinking; es wird deshalb nicht vermeintlich abgeschaltet. Modelle,
andere KI-Arbeitsabläufe und Budgets werden dadurch nicht geändert. Ein
begrenztes F-/K-/V-Register verweist ausschließlich auf tatsächlich gelieferte
Codefakten, Kandidatenfelder und primitive Codevergleichswerte. Originaldaten
und vollständige Tradelisten bleiben enthalten. Unbekannte IDs oder erfundene
Pfade werden weiterhin abgewiesen. Fehlerkorrektur-Aufrufe erhalten jetzt die
konkrete Diagnose; deren wirklicher Prompt und Requestoptionen sind an den
bezahlten Cache gebunden. Martingale `code_belegt` bezeichnet ausschließlich
ein positives Codeflag, niemals einen negativen Test.

Die Anzeige trennt fertige Kurztests, Top-5-Berichte und KI-Fehler. Der alte
Anbieter-Endstand 748/800 enthielt auch Datenlücken und Robo-Quellenwerte. Die
tatsächliche Kurztestmenge dieses Datenbestands beträgt 234; das ist keine
Behauptung über 234 rankbare Strategien. Datenlücken können trotz vorhandener
Tradeliste eine Kurzeinordnung erlauben, ohne einen RetDD oder Rang zu erhalten.

Der alte Worker 1564988 wurde kooperativ beendet. Zwei erfolglose gezielte
GoldWave-Proben bleiben samt Kosten und Antworten erhalten. Die dritte Probe
lief am 23.10. von 22:58:04 bis 23:00:11 MESZ erfolgreich: zwei gültige
Tradeblöcke und eine gültige Zusammenfassung, 305 von 305 gelieferten Trades
abgedeckt. Der vollständige Kurztest und das zugehörige Code-Belegregister sind
gespeichert. Das ist ein erfolgreicher Einzeltest, kein Abschluss der übrigen
KI-Arbeit. 224 integrierte Recherche-/KI-/Budget-/Checkpoint-/UI-/Clienttests
bestanden.

Vor der Wiederaufnahme wies die strenge Checkpointprüfung zwei alte
`abgebrochen=True`-Marker zurück. Nachgewiesene spätere native Updates und
aktuelle Ergebnisse zeigten die Ursache: `entry.update(result)` behielt das
alte Feld, weil reguläre neue Ergebnisse es nicht enthielten. Ausschließlich
die veralteten Marker der Referenzen 129 (Gold Spike) und 10470 (Bulletride)
wurden mit vollständigem Vorher-/Nachher-Audit entfernt. Gold Spikes aktueller
Trade-SHA wurde geprüft; Bulletrides EUR-Datenlücke, fehlende Trades und negative
Eignung blieben unverändert. Künftige neue reguläre Datenversuche beginnen mit
`abgebrochen=False`; ein tatsächlicher neuer Abbruch setzt es erneut auf True.
64 gezielte Tests einschließlich Erfolg, EUR-Fehler und echtem neuen Abbruch
bestanden nach dieser zusätzlichen Korrektur. Der Checkpoint bleibt streng.

Der ursprüngliche Auftrag wurde um 23:02:55 MESZ als Prozess 1951824 gezielt
in der KI-Phase fortgesetzt. Um 23:03:12 waren passende Prozessidentität,
gehaltenes gemeinsames Lauf-Lock, verbrauchter einmaliger Checkpoint,
unveränderte 800 Referenzen und Quellensnapshots sowie unveränderte globale
Settings unabhängig bestätigt. Das freigegebene Budget 50/50/60 Mio. gilt
weiterhin ausschließlich für diesen Auftrag. GoldWave wird wiederverwendet;
NoPain MT5 begann Block 1/31. Der Browser bestätigte anschließend 1/234
Kurztests, 0/5 Top-5-Berichte und drei vorhandene Fehlerstände, deren Kandidaten
erneut geprüft werden. Dies ist **kein abgeschlossener Gesamtlauf**.
Pelicans frühere Datenlücken und der alte Vantage-Quellenfehler bleiben in
dieser KI-Fortsetzung erhalten; deren neue Datenanalysen sind nicht nachgeholt.

Private Belege im bisherigen Laufverzeichnis: `ki_fix_goldwave_probe_result.json`,
die beiden `*_failure.json`, `ki_fix_stale_abort_flags.json`,
`ki_fix_resume_prepared.json`, `ki_fix_resume_start.json`,
`ki_fix_resume_verified.json` und `ki_fix_resume.stdout.log`/`.stderr.log`.

Die Anschlussprüfung um 23:04 MESZ bestätigte tatsächlich weiteren Fortschritt:
NoPain Block 1/31 wurde nach einem zurückgewiesenen Verweis `einschaetzung`
automatisch korrigiert und angenommen; Block 2/31 wurde begonnen. Eine
ungültige Einzelantwort ist damit weiterhin möglich, aber kein automatischer
Strategieausschluss oder Beleg für Stillstand. Der fertige Kurztestzähler steigt
erst nach Abschluss aller Blöcke und der Zusammenfassung. Beleg:
`ki_fix_resume_progress.json`. Eine Fehlerfreiheit aller künftigen Antworten
oder ein vollständiger Abschluss ist damit nicht nachgewiesen.

## Regression vor der Veröffentlichung

Der umfassende erneute Scanner-Check am 23.10.2026 bestand mit **3.320 Tests,
keinen Fehlern und einem Skip**. Der Symlink-Test
`test_identity_activation.py::test_symlink_is_rejected_without_following_target`
war unter Windows mangels Berechtigung (1314) nicht ausführbar. Vier echte
LLM-Regressionstests wurden nicht gesammelt. Die zusätzlich ausgeführten
27 lokalen REST-Fälle verwenden eigene temporäre Server und Datenbanken.
Produktive Settings blieben per SHA-256 unverändert; es gab keine produktiven
Quellen-, Modell- oder Deployment-Aufrufe durch diesen Regressionstest.
Die fünf JUnit-Dateien liegen lokal unter
`%LOCALAPPDATA%/Temp/scanner-regression-20261023-c1f36fb895064d05b7a0594747a96aea/`.

Die zugehörigen Quellcodeänderungen sind getrennt nach Repository festgehalten:

| Repository | Vorher | Neuer Commit |
| --- | --- | --- |
| MqlDownloader | afe507e | 442bb60 |
| PelicanTrading | ff883d6 | 1f7d12d |
| robomonitor | 7314666 | f104396 |
| vantagemonitor | 81511b4 | 7d26a4d |
| zulumonitor | cfcf688 | e44b1fb |
| MqlTradeMonitor | 18a59d7 | 0eda6b0 |

Der Scanner-Vergleich beginnt bei `1bda2fa`. Die zusätzlich aufgenommenen
Identitäts-/DD-/Tradeserver-v2-Anpassungen sind Voraussetzungen des aktuellen
Softwarestands. Unabhängige Kontrollbericht-Skripte, ältere lokale
Laufzeitarchive und private Datenbestände werden nicht mitveröffentlicht.
Diese Regression belegt keine abgeschlossene produktive Gesamtauswertung.
