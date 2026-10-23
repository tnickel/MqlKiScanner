# Umsetzung: FT-Kontrakte und Quellenidentität

Stand: 18.10.2026, abgeschlossen. **Schema 2 ist seit 18:28 Uhr MESZ produktiv aktiv.** Die Oberfläche läuft wieder auf Port 8504. Die Abnahme ergibt **2.673 bestandene eindeutige Testfälle, einen übersprungenen Windows-Symlinkfall und keinen ungeklärten Fehler**, nach Gesamtlauf und gezielter Nachprüfung. Vier kostenpflichtige LLM-Fälle sind bewusst abgewählt. Frühere rote Zwischenläufe bleiben als Diagnose erhalten.

Aktivierungs- und Betriebsnachweis: [Aktivierungsbeleg](root_activation_receipt.json), [Produktivprüfung ohne externe Abrufe](root_production_smoke.json), [Gesamtregression mit genauer Laufprovenienz](root_regression_summary.json).

## Fachlicher Umfang

Die exakten Terminalnamen `GER40ft` und `UK100ft` sind direkt am belegten Vantage-Terminal geprüft. Das passende Vantage-Profil verwendet 1 EUR beziehungsweise 1 GBP je Punkt und Lot mit historischen FX-Kursen. Die bisherigen festen USD-Mediane entfallen. Das ist eine Modelländerung: Forensikversion 20 erzwingt neue Befunde; alte Zahlen werden nicht still weiter freigegeben. Der historische Originalserver der betroffenen Provider bleibt unbekannt. Ein geprüfter Referenzserver ist kein Beleg beliebiger Broker.

Details und rein lokale Nachrechnung der fünf betroffenen Caches: [FT-Nachweis](ft_README.md). Andere fehlende Kontrakt-, Währungs- und Kursbelege bleiben als Lücken sichtbar. Keine automatische Equity-, Calmar- oder Ampelaufwertung.

Die produktive DD-Einstellung bleibt 50 %, der Jahres-Calmar 3,0; die absolute Monatshürde bleibt aus. Die konfigurierbare harte DD-Schranke, die Anforderungen an eigene Floating-Equity-Messungen und die Neutralität fehlender SL-Belege werden durch die Identitätsmigration nicht geändert.

## Durchgängige Identität

`ScanResult.id` bleibt die externe Anbieter-ID. Ein separates Register verwaltet `UNIQUE(quellen_uid, externe_id)` und die interne `signal_ref`. Die Quellen-UID bleibt bei Umbenennung und URL-Wechsel erhalten. Anzeigenamen und Verbindungsschlüssel sind keine dauerhaften Besitzer. Reine Katalogsignale erhalten eine Registeridentität ohne Workflow-Kopf.

Workflow, Befunde, Snapshots, Studien, Abonnentenverlauf, Berichte, Kommentare, Markierungen, Fixierungen, Chronik, Dossiers und signalbezogene Journalläufe verwenden dieselbe interne Referenz. Pipeline, Teilscan, Auswahl, Tabellen, Sessioncache, CSV, PDF und Portfolio führen Quellenidentitäten mit. Numerische Altabfragen sind nur bei eindeutiger Zuordnung lesbar; bestehende Datensätze benötigen beim Schreiben eine explizite Quelle oder Referenz.

Gleiche ID, gleiche Plattform und gleiche CSV-Bytes verschiedener Quellen sind zulässig und bleiben getrennt. Widersprüchliche Plattformen innerhalb derselben Identität bleiben gesperrt, auch beim Katalogimport und vor der Kandidatenauswahl. Kandidaten und manuelle Studien müssen zur behaupteten Verbindung und Signalreferenz passen, bevor Cache oder Netz angesprochen werden.

Der Betreuer bleibt MQL5-beschränkt. Die zurückgestellte MqlRealmonitor-Integration wird nicht umgesetzt. Tradeserver v1 bleibt extern auf numerische IDs beschränkt: Bei Quellenkollision wird der gesamte Export vor Clientanlage und Übertragung gesperrt. Für dortige parallele Darstellung gleicher Anbieter-IDs ist weiterhin eine abgestimmte Protokollerweiterung erforderlich.

## Zusätzliche behobene Fehler

- Ingest und gemischter Crawl dürfen Plattformwidersprüche nicht durch vorzeitiges Deduplizieren verbergen.
- Neue Fixierungen aus dem Vollkatalog funktionieren auch ohne bereits vorhandenen Workflow-Kopf und ohne Abonnenten.
- KI-Prompts werden aus eingefrorenen, gegen den Analyse-SHA geprüften Trade-Bytes aufgebaut. Ein geänderter Export stoppt vor dem Modellaufruf. Unveränderte archivierte Berichte können bei fehlender lokaler Datei weiterhin getrennt gelesen werden.
- Historische Ausschluss- und Watchlisteinträge gelten im belegten ursprünglichen MQL5-Namensraum, einschließlich Matrix und Detailanzeige.
- Alte unqualifizierte Meldungsverweise bleiben wörtliches Auditmaterial; sie werden nicht an einen heutigen Besitzer umgedeutet.

## Datenmigration und Grenzen

`identity_migration.migrate_copy` verwendet ein konsistentes SQLite-Backup, schreibt ausschließlich einen neuen Kandidaten und aktiviert niemals selbst. Vorhandene Ziele werden nicht überschrieben. Quellen und Eltern werden zuerst angelegt. Fremdschlüssel, Integrität, Mengenbilanz, Originalwerte und Dateihashes werden geprüft. Sequenz-Höchststände müssen auch für quarantänisierte IDs erhalten bleiben.

Die echte erste Kopie bewahrt alle 12.764 Originalzeilen über 26 Tabellen als aktive Zeilen oder verlustfreie Quarantäne. 194 Workflow-Signale, 1.454 Katalogeinträge und 3.094 Quellenartefakte sind übernommen; alle 3.287 referenzierten Dateien sind vorhanden und SHA-geprüft. 15 bestehende Fixierungen sind eindeutig zugeordnet.

**Wesentliche Folge:** 1.572 historische Studien sowie weitere Verlaufs-, Dossier- und Journalzeilen besitzen keinen ausreichenden historischen Quellenbeleg. Ein heute einziger Katalogtreffer, gleicher Name, gleiche Plattform oder gleicher SHA beweist diesen Besitzer nicht. Die Rohzeilen bleiben in der privaten `migration_quarantaene` erhalten; sie gelten nicht als neue aktuelle Messung. Drei verwaiste Analysen bleiben ebenfalls erhalten. Die vollständige Aufteilung steht in [der geprüften Kopierbilanz](db_dryrun_report.json) beziehungsweise dem jüngeren `root_migration_candidate_report.json`.

Bekannter KI-Kostenverbrauch aus quarantänisierten Schritten muss ohne erfundenes Signaleigentum in Tages-/Monatsbudget und Reservierungsprüfung erhalten bleiben. Eine vorhandene Budget-Ledgerbuchung darf dadurch nicht doppelt gezählt werden.

Produktivwechsel erfolgt ausschließlich nach Stilllegung aller Schreiber, erneuter Backupprüfung und erfolgreicher Abnahme. Automatikfreigabe bleibt unverändert. Nach neuen Schreibvorgängen mit gleichen IDs mehrerer Quellen ist ein blindes Zurückspielen des alten ID-Schemas kein verlustfreier Rückweg.

Der konkrete Wechsel ist erfolgt: alter Projekt-Daemon kooperativ beendet, alte Oberfläche nach geprüft freiem Workflow-Lock beendet, anschließend frischer Kandidat aus dem stillgelegten Bestand gebaut. Die Aktivierung verwendet die SQLite-Backup-API unter durchgehend gehaltener Exklusivsperre, einschließlich Hashprüfung. SQLite dokumentiert die [Zieltransaktion und den Rollback bei unvollständiger Kopie](https://www.sqlite.org/c3ref/backup_finish.html). Der getestete Windows-Umbenennungspfad war unter gehaltenem Livehandle nicht möglich und ist kein unsicherer Fallback. Einzelheiten: [Aktivierungshilfe](ft_activation_README.md).

Nach dem Wechsel sind Integrität/Fremdschlüssel erneut geprüft und sämtliche 12.764 Originalzeilen erneut gegen Sicherung plus Quarantäne verglichen: [Werteerhalt des aktiven Bestands](root_active_payload_verification.json). Aktiver Bestand: 194 Workflow-Köpfe, 1.732 Registeridentitäten, 1.454 Katalogzeilen, 15 Fixierungen, 213 getrennte Kostenbelege, 4.458 Quarantänezeilen und zunächst **0 aktive Studien**. Der Oberflächendienst wurde neu gestartet; die bereits vorher ausgeschaltete Automatik bleibt ausgeschaltet. Es wurden keine neuen Live-Scans, Update-POSTs oder bezahlten Modellaufrufe gestartet.

Lokale Datenbanken, Originaltrades, Cookies, Zugangsdaten und Rollbacksicherungen sind keine Reviewanhänge. Private Aktivierungskandidaten liegen im ignorierten Verzeichnis `data/identity_migration/`.

## Prüfnachweise

- [Unabhängige Integrationsgegenprüfung](ft_core_review_README.md)
- [Journalprüfung](ft_journal_README.md)
- [Studienregression](ft_study_regression_README.md)
- `ui_implementation.json`: aktuelle Consumerläufe und deren genaue Grenzen
- `db_payload_verification.json`: unveränderte Kennzahlen, Forensik-JSON und Texte einschließlich Quarantäne
- `root_regression_initial.*`: erster diagnostischer Gesamtlauf, ausdrücklich mit alten Vertragsfixtures und roten Fällen
- `root_core_regression.*` / `root_remaining_regression.*`: gezielte Integrations- und Vertragsprüfungen; der spätere Gesamtlauf ist maßgeblich

Die Gesamtprüfung umfasst alle 176 Testdateien in zwei Teilen. Teil 1 bestand mit 1.279 grünen Fällen und dem Symlink-Skip. Teil 0 zeigte 1.360 grüne Fälle und 34 alte Testvertragsfehler: Quellenbesitz fehlte in zwei Fixierungs-Fixtures, drei weitere Assertions erwarteten den früheren Fehlertext statt der jetzt früher greifenden Verbindungsprüfung. Die drei vollständig nachgeprüften Dateien bestanden anschließend mit 160 Fällen. Diese 160 ersetzen dieselben vorhandenen Testknoten; sie werden **nicht addiert**. Die jüngsten eindeutigen Ergebnisse stehen in `root_regression_summary.json`. Produktiver Quellcode blieb dabei unverändert (112 eingefrorene Dateien). `root_pre_freeze_0.*` ist ein bewusst abgebrochener Zwischenlauf und kein Abnahmenachweis.

Kein Test zählt einen echten kostenpflichtigen Modellaufruf als Offline-Regressionsnachweis. FT-Metadaten wurden bewusst genau einmal mit bestehender Terminalfreigabe unter gemeinsamem Lock gelesen; die Tests und anschließenden Nachrechnungen benötigen keine echten MQL5-Abrufe oder Update-POSTs.
