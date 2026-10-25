# Lösungsweg für FT Kontraktbelege und durchgängige Signalidentität

Stand: 18.10.2026. Dieser Plan beantwortet die beiden offenen Punkte nach den abgeschlossenen Download-/Datenflusskorrekturen. Er beschreibt einen vorbereiteten Lösungsweg; Registry, Schema, produktive Daten und laufende Prozesse wurden dafür nicht verändert. Die konfigurierte DD-Grenze und die fachlichen Gates bleiben erhalten.

## GER40ft und UK100ft

Die frühere Aussage, es gebe für beide Instrumente keinen unabhängigen FT-Beleg, war zu pauschal. Für **UK100ft** enthält [vantage_restspecs_live_2026-10-10.json](../vantage_restspecs_live_2026-10-10.json:151) bereits einen exakten Symbolbefund: Beschreibung `UK100 Future`, Kontraktgröße `1.0`, Gewinnwährung `GBP`, Tickgröße `0.01`, Mindestvolumen und Volumenschritt `0.1`. Cash `UK100` ist dort gesondert aufgeführt. Der Snapshot enthält allerdings keinen expliziten Brokerserver; seine Herkunft ist als lokaler Vantage-Terminal dokumentiert.

Der vorhandene H1-Cache enthält die Originalsymbole **GER40ft und UK100ft** unter dem Feed des Terminals `C:/Forex/Mt5/Vantage/terminal64.exe` und dem Server `VantageMarkets-Live 10`. Das belegt verfügbare FT-Kurse, keinen GER40ft-Kontraktwert und nicht rückwirkend den Server des älteren UK-Specsnapshots. Frühere erfolglose Suchproben verwendeten dagegen die Großschreibungen `GER40FT` und `UK100FT`; sie beweisen keine Nichtverfügbarkeit der anders geschriebenen Originalnamen.

Die aktuell vorrangigen brokergebundenen Registryeinträge verwenden USD-Medianfaktoren 1,08 beziehungsweise 1,35. Daneben stehen generische Einträge mit 1 EUR beziehungsweise 1 GBP. Ein fixer historischer USD-Median ist kein gleichwertiges zeitabhängiges Währungsmodell. Die erneute Rückrechnung der neun GER- und dreizehn UK-Trades des vorhandenen referenzierten Rohan-Snapshots unterstützt 1 EUR beziehungsweise 1 GBP: Nach lokalem EZB-Tageskurs liegen die abgeleiteten Faktoren ungefähr zwischen 0,996 und 1,006. Das ist eine Plausibilitätsprüfung, kein Ersatz für passende Broker-Metadaten. Beim Provider ist der gespeicherte Brokerwert bislang nur generisch `vantage`, kein belegter Originalserver.

Der konkrete Beschaffungs- und Korrekturpfad:

1. Unter dem bestehenden gemeinsamen Lauf-Lock die Metadaten der **exakten** Symbole `GER40ft` und `UK100ft` am konfigurierten Vantage-Terminal lesen. Tatsächlichen Servernamen, Terminalpfad, UTC-Zeit und die öffentlichen Symbolfelder sichern: Kontraktgröße, Gewinnwährung, Berechnungsmodus, Tickgröße/-wert, Volumenminimum/-schritt. Kontonummer und Balance gehören nicht in den Nachweis.
2. Keinen Cash-Alias und keinen fremden Referenzbroker als FT-Beleg akzeptieren. Der vorhandene Helper `scripts/reference/mt5_kontrakt_specs.py` ist für einen blinden Nachweis ungeeignet: Er kann auf Kursaliase ausweichen und beendet am Ende das Terminal. Eine exakte Abfrage muss diese Effekte ausdrücklich kontrollieren und die geltende Portable-/Lock-Politik respektieren.
3. Broker-/Serverbindung des Belegs und betroffener Provider klären. Ein Spec am belegten Referenzserver ist keine pauschale Freigabe beliebiger Vantage-Server. Falls der ursprüngliche Providerserver unbekannt bleibt, diese Grenze im Befund erhalten.
4. Erst mit ausreichend passendem Beleg den vorrangigen brokergebundenen Registryeintrag korrigieren und widersprüchliche Doppelangaben bereinigen. Bei bestätigter nativer EUR-/GBP-Basis den bestehenden historischen FX-Pfad verwenden, statt einen konstanten USD-Median einzutragen.
5. Mit den vorhandenen Trades gegenprüfen: Preisrichtung, Lots, Handelskosten, Kontowährung und Währungsdatum getrennt behandeln. Auswirkungen auf Exposure und H1-Equity prüfen. Eine fachliche Modelländerung benötigt eine neue Bewertungsbasis/Forensikversion und Neuberechnung betroffener Befunde; sie darf alte Studien nicht still als unverändert gültig ausgeben.

Die API zum Lesen der Symbolfelder ist in der offiziellen [MetaTrader-Dokumentation zu symbol_info](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py) beschrieben. Diese API-Dokumentation belegt die Abfragemöglichkeit, nicht die konkreten Broker-Kontraktwerte.

## Identität als stabiler Namensraum und externe Anbieter ID

Empfohlen ist ein internes Identitätsregister mit einer stabilen `signal_ref` und einem eindeutigen Paar aus **stabiler Quellenkennung und unveränderter externer Anbieter-ID**. Beispielsweise sind `mql5:123` und `robo:123` zwei unabhängige Signale. Intern können abhängige Tabellen auf eine einfache numerische Referenz zeigen; Anbieter-APIs und URLs behalten die originale Anbieter-ID.

Die Quellenkennung darf nicht an Anzeigename, Kürzel, Host oder Port hängen: Kürzel sind heute umbenennbar und Verbindungen löschbar. Deshalb stabile logische Quellennamensräume getrennt von konfigurierbaren Verbindungen verwalten. Ein belegter MQL5-Direktbezug und dessen Downloader-Spiegel dürfen denselben logischen Namensraum verwenden. Zwei beliebige Quellen mit derselben Zahl dürfen das nicht.

Ein separates Register umfasst Workflow- und reine Katalogidentitäten. Reine Katalogsignale dürfen durch die Migration nicht alle in `signals` als gescannter Workflow erscheinen. Vor Festlegung des Unique-Keys den Anbieter-ID-Vertrag je Quelle prüfen: Wiederverwendet eine Quelle IDs zwischen tatsächlich verschiedenen Plattformkonten, muss der Namensraum oder Schlüssel diese Dimension ausdrücklich aufnehmen. Plattformwidersprüche innerhalb einer vermeintlich gleichen Identität nicht still zusammenführen.

Ein Grundschema bei innerhalb einer Quelle eindeutigen Anbieter-IDs:

```sql
CREATE TABLE signal_identitaeten (
    signal_ref INTEGER PRIMARY KEY,
    quellen_uid TEXT NOT NULL REFERENCES quellen_identitaeten(quellen_uid),
    externe_id INTEGER NOT NULL,
    UNIQUE (quellen_uid, externe_id)
);
```

`ScanResult.id` darf nicht still zur internen Nummer umgedeutet werden, weil es heute für externe Downloads und URLs verwendet wird. Stattdessen Identität explizit durch die APIs reichen. Schreibvorgänge brauchen eine explizite Quelle; alte rein numerische Lesezugriffe dürfen nur bei belegter eindeutiger Zuordnung funktionieren.

## Vollständiger Umfang der Umstellung

| Bereich | Erforderliche Änderung |
|---|---|
| Workflow und Befunde | `signals`, `trade_files`, `forensik`, `analyses` an dieselbe Signalreferenz binden. Globale Portfolioanalysen behalten keinen einzelnen Signalbesitzer. |
| Katalog und Artefakte | Auf das gemeinsame Register beziehen; Verbindung, Plattformversion und Artefaktart bleiben zusätzliche Dimensionen. |
| Verlauf und Dokumente | `subscriber_history`, Downloader-PDFs und deren Abruf gezielt nach Quelle adressieren; keine Vereinigung aller Quellen derselben Zahl. |
| Studien | Quelle, externe ID und Trade-SHA gemeinsam zuordnen. Die heutige Kollisionssperre erst nach vollständiger Umstellung entfernen. |
| Chronik und Agenten | Profile, Beobachtungen, Deltas, Vorgänger und strukturierte Meldungsverweise umstellen. `ampel_verlauf.quelle` bedeutet heute Scanart, `agenten_laeufe.quelle` bedeutet Auslöser; diese Felder sind keine Datenquellenbelege. |
| Kommentare, Markierungen, Fixierung | An genau eine Signalidentität binden. Alte mehrdeutige Einträge nicht auf mehrere Quellen kopieren. |
| Pipeline und Benutzeroberfläche | Deduplizierung, Kandidaten, Teilscan, Fix-/NEU-Mengen, Auswahl und Sessionkeys auf die Identität umstellen. Der Betreuer bleibt weiterhin ausdrücklich MQL5-begrenzt. |
| Berichte und Portfolio | Quelle in Berichtsbasis, PDF-/Dateinamensräume und Statistikschlüssel aufnehmen. Gleiches CSV-SHA beweist keine gemeinsame Signalidentität; Inhaltsdateien dürfen dennoch nach SHA geteilt bleiben. |
| Externe Verträge | Tradeserver v1 verarbeitet nur die numerische ID und benötigt eine abgestimmte Protokollerweiterung. Bis dahin bei Kollision den gesamten Export vor Übertragung sichtbar blockieren, kein stilles Teilpayload. |

Die vorbereitete MqlRealmonitor-Anbindung bleibt zurückgestellt. Ein dortiger alter ID-only-Client darf nicht durch diesen Umbau still als quellenfähig gelten. Gemeinsame H1-Kursdaten behalten ihre Feed-/Broker-/Symbolidentität und werden nicht unnötig an einzelne Signale gebunden. Demo-Dateien mit ID 0 brauchen weiterhin ihre eigene Dateisnapshotidentität.

## Migration und Freigabe

1. Verbraucherinventar abschließen und neue Identitätsverträge samt Tests vorbereiten. Die bestehende Kollisionsabwehr bis zur vollständigen Umschaltung erhalten.
2. Versioniertes Migrationsprogramm zuerst ausschließlich an einer konsistenten SQLite-Backupkopie ausführen. Elternidentitäten zuerst, danach eindeutig zuordenbare Kinder migrieren; Journal-/Analyse-IDs, Originaldateien und Zeitbelege erhalten.
3. Unsichere Altdaten mit Originalinhalt, Herkunft und Begründung gesondert erhalten. Aktuell nur ein Katalogtreffer beweist keine vollständige historische Besitzkette; gleiche Plattform, Name oder Datei-SHA ebenfalls nicht. Verwaiste Analysen bekommen keine erfundenen Eltern. Mengenbilanz: **Original = übernommen + ungeklärt erhalten**.
4. Fremdschlüssel, Integrität, Zuordnungen und Hashes prüfen. Die Identitätsmigration selbst verändert keine Zahlen, Ampeln oder Bewertungsregeln. Geänderte Berichtsbasis nicht als automatische Neufreigabe alter Texte behandeln.
5. Für den produktiven Wechsel alle Schreiber kontrolliert stilllegen: nicht nur Scans, sondern auch Katalog-/History-/PDF-Sync, manuelles Nachladen und Agenten. Schema-Version gegen alte schreibende Prozesse absichern. Code und Datenbank gemeinsam umschalten.
6. Erst nach erfolgreicher Abnahme quellenübergreifend gleiche Workflow-IDs zulassen. Die Abnahme nutzt zwei Quellen mit **derselben ID, derselben Plattform und identischen CSV-Bytes**, aber verschiedenen Brokern/Kapitalbasen. Scans, Reload, Studien, Verläufe, Berichte, Chronik, Kommentare, Fixierungen, Portfolios und parallele Updates müssen getrennt bleiben.

Vor Freigabe neuer Schreibvorgänge ist ein Rückfall auf den gesicherten Code-/DB-Stand möglich. **Nach Speicherung zweier Quellen derselben Nummer kann das alte ID-only-Schema beide nicht verlustfrei darstellen.** Dann dürfen neue Daten nicht durch ein blindes Zurückkopieren verschwinden; dafür braucht es ein Änderungsjournal beziehungsweise eine vorwärts korrigierte neue Version.

Die Identitätsumstellung ist damit ein zusammenhängender Architekturumbau mit Datenmigration und Schnittstellenabnahme. Sie braucht keine erfundenen Brokerwerte, hebt keine Risikoregel auf und wurde durch die bisherigen defensiven Kollisionsprüfungen noch nicht umgesetzt.
