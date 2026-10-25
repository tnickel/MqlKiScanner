# Persistenz, Forensikalter, Tabellen und Testprovenienz

Prüfobjekt: der eingefügte DeepSeek-Text, SHA-256
`ccb194b19800109d5e53ed9cbb6b6826e0550ee6b51b4c59b302756371b59391`.
Eigener DB-Abgleich: 18.10.2026, 15:05:21 UTC. Die Datenbank wurde mit
SQLite-URI `mode=ro`, `query_only=ON` und einer einzigen Lesetransaktion
geöffnet. Die produktiven Lese-/Mappingfunktionen verwendeten dieselbe
Verbindung; Schemainitialisierung und PDF-Materialisierung waren abgeschaltet.
Keine HTTP-, Scan-, Terminal- oder Modellaufrufe. Persistiert wurden nur
aggregierte Belege in diesem Reviewordner.

## F3: zutreffender Kern, falsche Verallgemeinerung

Die 163 Workflow-Forensikzeilen enthalten tatsächlich **keine Version 19**.
Die vollständige Verteilung ist: ohne Version 4, Version 7: 27, Version 11: 3,
Version 14: 10, Version 15: 104 und Version 16: 15. DeepSeek lässt die drei
Version-11-Zeilen aus; seine aufgezählte Verteilung summiert sich nur auf 160.

Der tatsächliche `pipeline.results_from_db`-Pfad ergibt **161 stale-Zeilen,
nicht 194**. Die übrigen 33 haben entweder gar keinen Befund (31) oder einen
ausdrücklich unvollständigen Befund, der nicht als stale eingeordnet wird (2).
Das entspricht der Unterscheidung in `pipeline.py:508–542`.

**Keine der 194 Zeilen besitzt aktuell vollständige Workflow-Forensik.**
Es gibt beim aktuellen Reload kein Grün und kein Gelb. Score, belastbarer
H1-Max-DD und TrueRetDD sind in allen 194 Ergebniszeilen leer; auch der
vorbehaltliche TrueRetDD ist leer. Dies wurde über die echten ScanResult-
Eigenschaften und `to_row` geprüft, nicht aus der Versionszahl allein gefolgert.
Mit den gelesenen Einstellungen DD 50, Monatsertrag 0 und Jahres-Calmar 3
ergaben sich 99 weiße, 77 rote und 18 ausgeschlossene Zeilen.

Diese Zahlen beschreiben fehlende **aktuelle** Freigaben. Sie bedeuten weder,
dass keine historischen Analysen durchgeführt wurden, noch dass die
Stale-Sperre selbst ein neuer Codefehler ist. Grün/Gelb bleiben unter den
bestehenden Gates gesperrt; ein Versions- oder Status-Update ohne echte
Neuberechnung wäre keine Behebung.

Davon getrennt sind **1.354 gespeicherte Equity-Studien mit Version 19** und
218 mit Version 0. Die Aussage „0× Version 19“ gilt somit ausschließlich für
die Workflow-Forensik. Der Studien-Lesefilter liefert 1.354 v19-Zeilen, was
allein keine jeweils aktuelle CSV-/Währungszuordnung beweist. Im geprüften
Workflow-Reload besitzen alle 194 Ergebnisse keinen gültigen Währungswert;
auch der separate Studien-Anzeigekanal füllte dort keinen Wert.

## Mengen und Datumwerte

Bestätigt: 194 Workflowzeilen, 163 Forensikzeilen, 193 Tradeverweise,
1.454 Katalogzeilen und 3.094 Quellenartefakte. Die Schnittmenge gleicher
Quelle/ID umfasst 171 Zeilen. Damit verbleiben 1.283 reine Katalogzeilen und
eine Vereinigung von **1.477 Identitäten**. Aktuell gibt es keine
quellenübergreifende numerische ID-Kollision in dieser Vereinigung.

Die beiden angegebenen Datumsgruppen stimmen: 104 Befunde der Version 15
haben `updated_at` am 08.10., 15 Befunde der Version 16 am 16.10.2026. Die
Version-11-Zeilen stammen vom 04.10.; weitere alte Gruppen liegen im September
und Anfang Oktober. `db._now` (`db.py:272`) speichert lokale Persistenzzeit
ohne Zeitzonenoffset. Diese Werte belegen weder den letzten enthaltenen Trade
noch den Zeitpunkt einer erfolgreichen aktuellen Plattformabfrage.

## Tabellenbehauptungen

Die Zeilenbilanz 194/1.477 ist als Daten-/Identitätsbilanz bestätigt. Sie ist
keine Sichtprüfung eines aktuellen Browserscreenshots oder beliebiger
Tabellenfilter. DeepSeek nennt selbst keine Browser-Sichtprüfung; aus diesem
Text lässt sich deshalb keine vollständige visuelle Abnahme ableiten.

Die Angabe „Abonnenten, 7/30 Tage live aus `/history`“ ist sachlich falsch:
`app_ui.results_table_dataframe` verwendet `downloader_sync.abo_bilanz`;
dessen Quelle ist ausdrücklich ausschließlich die lokale Tabelle
`subscriber_history` (`downloader_sync.py:318–324`), ohne REST-Aufruf beim
Tabellenbau. Ein früherer History-Sync und der aktuelle Tabellen-Lesezugriff
sind unterschiedliche Vorgänge.

Ampel und Urteil sind ebenfalls keine bloße Anzeige gespeicherter JSON-Felder:
`results_from_db` berechnet sie über das aktuelle `ampel_for` neu
(`pipeline.py:689`). Der Score stammt aus dem gespeicherten Befund, wird bei
Stale aber gesperrt. Die H1-/Calmar-Sperren sind im Code und im Ergebnis des
eigenen Reloads nachvollziehbar.

## Testprovenienz und Reichweite

Die historischen drei Scanner-JUnit-Dateien enthalten 916 + 828 + 755 =
**2.499 bestandene Fälle**. Nach dem späteren Legacy-Quellenfix wurden
**150 gezielte Fälle** geprüft, darunter acht neue Fälle; die vollständige
Suite wurde danach nicht wiederholt. Diese überlappenden Zahlen dürfen nicht
addiert oder als gemeinsamer letzter Vollsuite-Lauf ausgegeben werden.
Die aktuelle Scanner-Scopekorrektur dieser DeepSeek-Nachprüfung wird vom
Hauptbericht mit eigenen neueren Belegen geführt.

Die historischen 94 Auditfälle lassen sich acht konkret benannten neuen
Testmodulen zuordnen. Eine neunte Datei ist durch diese Zahl nicht belegt.
Die während der aktuellen Nachprüfung neu angelegte
`test_deepseek_catalog_scope.py` gehörte nicht zur alten 2.499er-Sammlung.

Beim Eingangsabgleich passten alle 55 im letzten Übergabemanifest erfassten
Quell-/Test-/Anweisungsdateien und dessen 22 Nachweise. Das ist ein Abgleich
dieser erfassten Dateien und kein Vollständigkeitsnachweis sämtlicher heute
parallel neu angelegter Dateien. Das Manifest und frühere Belege wurden
nicht umgeschrieben.

Vorhandene Java-XMLs stützen MQL 148, Vantage 88 und Zulu 120 bestandene Fälle.
Der RoboForex-Bericht stützt **nicht „183 passed“**: Er enthielt 182 bestandene
Fälle und einen Fehler in
`ReviewDataIntegrityTest.parallelDailyStoresPublishVerifiableWholeBundles`.
Dieser Bericht ist vor neuen Läufen unter `robo_before_*` konserviert; die
anschließende konkrete Reproduktion, Korrektur und neue Abnahme stehen in
[robo_README.md](robo_README.md).

Bei Pelican enthält der rohe Reportordner neben 180 bestandenen Fällen aus
aktuellen Reports noch einen fehlgeschlagenen Live-Login-Test vom 07.10.
Dieser alte, anders eingeordnete Report darf nicht ohne Beachtung von
Testauswahl und Datum zum neuen Standardlauf addiert werden. In diesem
Persistenzabgleich wurde kein Java-Test neu gestartet; die späteren explizit
beauftragten Robo-Läufe sind davon getrennt dokumentiert.

Belege: [persistenz_db.json](persistenz_db.json),
[Probe](persistenz_probe.py), [Aufruf](persistenz_command.json),
[Testprovenienz](persistenz_testprovenienz.json). Alle wesentlichen Aussagen
bleiben auf den angegebenen Lese-/Prüfzeitpunkt und die beschriebenen
Codepfade begrenzt.
