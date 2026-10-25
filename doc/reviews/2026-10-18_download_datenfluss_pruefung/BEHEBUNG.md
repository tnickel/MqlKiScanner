# Behebung der Download- und Datenflussbefunde vom 18.10.2026

## Auftrag, Umfang und tatsächlicher Stand

Die sechs Befunde F1 bis F6 aus dem ursprünglichen Audit sind im Arbeitsbaum korrigiert. Zusätzlich sind die feste Admin-Obergrenze von 30 %, eine bei der Regression bestätigte Lücke im Quellenschutz und die anschließend bestätigten Tabellen-/Protokollierungsfehler behoben. Betroffen sind drei Repositories: `SignalKiScanner`, `MqlDownloader` und `vantage` unter `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER`.

Der ursprüngliche [Review](README.md), dessen Belege und `nachweise/manifest.json` bleiben als Auditstand erhalten. Dieses Dokument beschreibt die anschließende Implementierung. Codeänderung und erfolgreicher Build sind keine Bestätigung einer bereits erfolgten Aktualisierung der produktiven Historien.

## Änderungen und Abnahme

| Befund | Korrektur | Geprüftes Verhalten |
|---|---|---|
| F1 – Vantage-Legacy-Historien ohne UTC | Beide Historienstores können unverifizierte Dateien durch frisch geladene UTC-Daten ersetzen. Alte Dateien werden unverändert separat archiviert. Der Merge verwendet nur verifizierte Historien und neue API-Zeilen. Ein Cache-Skip verlangt beide verifizierten Stores. | Erneuerung beider Stores, erneutes REST-Lesen, Wiederholung nach Teilerfolg, kleinere Folgefenster, Unterbrechung und Schreibfehler werden mit isolierten Dateien geprüft. Unverifizierte Altzeilen werden weder umetikettiert noch in neue UTC-Historien übernommen. |
| F2 – Analyse und gespeicherter Trade-SHA konnten unterschiedliche Dateien betreffen | Vor dem ersten Parser-/Engine-Zugriff wird ein Inhaltssnapshot erstellt. Analyse und Renditeberechnung verwenden diesen Pfad. SQL-Commit prüft den vorher bestimmten SHA und den expliziten SHA im Befund. Beim Wiederladen ansonsten aktueller Befunde werden auch die gespeicherten Bytes geprüft. | Ein tatsächlich parallel ausgeführtes manuelles Nachladen ändert den laufenden Analysebestand nicht. Manipulierte Dateien oder widersprüchliche Befund-SHAs führen zum Rollback; fehlende oder beschädigte Snapshots erlauben keine aktuelle positive Forensik. |
| F3 – MQL-Katalogfrische unterdrückte angeforderte Trade-Updates | Ein frischer Katalog liefert den bekannten Abonnenten-Scope. Angeforderte Trade-Updates durchlaufen trotzdem den Downloader und umgehen dessen Fünf-Tage-Dateicache. | Frischer/alter Katalog, MT4/MT5-Scope, frische CSV-Dateien, explizit deaktivierte Trade-Updates, Fehler und Abbruch sind regressionsgeprüft. `tradelisten=false` löst keine Trade-Downloads aus. |
| F4 – Unvollständige Pagination konnte Katalogzeilen löschen | Katalogübernahme verlangt eine konsistente Gesamtzahl und vollständige Rohzeilen. Leere Zwischenantworten, wechselnde Gesamtzahl, Dubletten, falscher Offset, Überlauf und Seitenlimit schlagen fehl. | Bei Fehlern bleiben die bisherigen Katalogzeilen der Quelle erhalten; andere Quellen werden weiter synchronisiert. Ein ausdrücklich vollständiger leerer Katalog mit `total=0` darf alte Katalogzeilen entfernen. Nichtnumerische Test-IDs werden erst nach der Vollständigkeitsprüfung normalisiert. |
| F5 – Zulu-Vollständigkeitshinweis ging verloren | `TradesCompletenessNote` wird übernommen; das ältere `CompletenessNote` bleibt als Fallback unterstützt. | Beide Feldnamen erreichen den sichtbaren Tabellen-Messstatus; Trunkierungsflags bleiben erhalten. |
| F6 – MaxDD-Erklärung nannte den falschen Datenkanal | Die Erklärung benennt die eigene H1-Equity-Rekonstruktion einschließlich berücksichtigter Kapitalflüsse. Monitor-Closing-DD bleibt separat. | Der Text passt zur belegten Herkunft der Spalte und erklärt weiterhin die Grenze gegenüber Intrabar-Tiefs. |

Weitere relevante Dateien: `src/mqlkiscanner/{db,pipeline,ingest,app_ui}.py`, `app_pages/{admin,scan}.py`, `MqlDownloader/src/{gui,downloader}/` und `vantage/src/main/java/de/vantagemonitor/{store,update}/`.

## Drawdownregel und zusätzliche Identitätssicherung

Der Admin kann positive endliche DD-Grenzen über 30 % anzeigen, speichern und erneut laden. Es gibt kein Clamping auf 30 %. Exakt 50 % liegt bei einer konfigurierten Grenze von 50 % innerhalb der Grenze; 50,1 % verletzt sie. Ein positiver Befund verlangt weiterhin alle übrigen Gates, insbesondere den belastbaren Jahres-Calmar. Fehlender oder vorbehaltlicher Equity-Nachweis wird dadurch nicht ausreichend.

Die standardmäßig ausgeschaltete absolute Monatsertragshürde bleibt bei 0 speicherbar. Scanbanner, Hilfe, FAQ und Regeltexte folgen der konfigurierten Grenze. Eigenständige Schockwarnungen, historische Bewertungen und kuratierte Ausschlüsse bleiben erhalten. Der Code-Default bleibt 30; daraus folgt keine allgemeine Obergrenze. Beim abschließenden Lesen der lokalen produktiven Settings wurden DD 50,0 %, Monatsertragshürde 0 und Jahres-Calmar 3,0 vorgefunden. Diese produktive Einstellungsänderung wurde nicht durch die hier beschriebenen Code-Fixes vorgenommen oder zurückgesetzt.

`store_scan_result` verlangt bei einer vorhandenen Signal-ID eine explizite nichtleere Quelle. Eine fehlende Quelle darf einen vorhandenen fremden Datensatz nicht überschreiben. Die Identitätsprüfung findet unter derselben Schreibtransaktion statt; konkurrierende erstmalige Einfügungen verschiedener Quellen können damit nicht beide erfolgreich sein. Neue Legacy-Importe ohne Quelle behalten den bisherigen Default `mql5`. Das ist eine abgesicherte Schnittstelle, keine Migration auf den weiterhin offenen Composite-Schlüssel `(quelle, signal_id)`.

`FORENSICS_VERSION` bleibt 19: Die fachlichen Rechenregeln wurden hier nicht geändert. Bestehende alte oder unvollständige Analysen werden nicht durch eine Versionsanhebung oder einen neuen Status als aktuell ausgegeben.

## Zusätzliche Tabellen- und Ablaufkorrekturen

- **Historischer Roh-DD:** Ein angezeigter `True-DD ≈` aus veralteter Workflow-Forensik erhält jetzt den ausdrücklichen Hinweis „Workflow-Forensik veraltet“ und „kein aktueller Messnachweis“. Der historische Wert bleibt nachvollziehbar; eine unabhängig aktuelle H1-Studie wird weiterhin separat erklärt.
- **CSV und Anzeige:** Die Ergebnisseite bereitet Abonnentenstände/-deltas, Dokumentzahlen und Quellenlinks einmal zusammen mit den Basisdaten vor. Renderer und CSV erhalten denselben Datensatz, dieselben Filter und dieselbe Reihenfolge. Die reinen Aktionsbuttons `Bericht`/`Studie` gehören nicht in die CSV; deren fachliche Spalten einschließlich Dokumentanzeige sind enthalten. Ungerundete Kennzahlen bleiben erhalten.
- **Quellenlink:** Der Link-Spaltenkopf lautet neutral „Signal-Link“ und behauptet nicht mehr für alle Anbieter „MQL5“.
- **Stufe-0-Abbrüche:** Start und angenommene Job-ID werden dauerhaft als noch laufend protokolliert. Ein zentraler Abschluss erhält bei unerwartetem Fehler oder Unterbrechung die bekannte Job-ID und Teilergebnisse. `KeyboardInterrupt`/`SystemExit` werden nach der Protokollierung weitergereicht. Ein Stop nach Jobannahme behauptet keine bestätigte Beendigung des entfernten Clientjobs. Bei DB-Ausfall wird ein lokaler ignorierter Fallback unter `DATA_DIR/client_updates_fallback.log` geschrieben und ein Chronikfehler geloggt. Eine DB-/Dateisystemstörung darf die eigentliche Abbruchursache nicht ersetzen.

Die zwei früheren Audit-Assertions, die ausdrücklich die damalige CSV-Spaltenlücke und den fehlenden Stale-Hinweis festhielten, wurden gezielt auf den korrigierten Vertrag umgestellt. Die übrigen Identitäts-, Auswahl-, NEU-, Rundungs- und Exportprüfungen bleiben erhalten. Neue Regressionen prüfen die korrigierte Semantik mit echten Streamlit-AppTests und isolierter Persistenz.

## Testnachweise und Builds

Die finalen Testzahlen und Artefakt-Hashes stehen im zugehörigen Behebungsmanifest. Ergänzende Protokolle:

- [Scanner-Standardsuite](nachweise/fix_scanner_full.log) und [JUnit](nachweise/fix_scanner_full.xml): **2.455 bestanden**, 4 LLM-Fälle gemäß Standardkonfiguration abgewählt, 437,97 Sekunden. Dieser Lauf liegt vor den zusätzlichen Tabellen-/Stufe-0-Korrekturen; deren abschließende Consumer-Regression ist gesondert protokolliert.
- [Finale Admin-, Katalog- und Tabellenregressionen](nachweise/fix_scanner_final_regressions.xml): 24 bestanden, einschließlich gespeicherter Grenze 0,05 %.
- [Persistenz-/Snapshot-Regressionen](nachweise/fix_persistenz_README.md): 72 bestanden, zusätzlich zuvor 174 Consumer-Tests.
- [MqlDownloader](nachweise/fix_mql_README.md): 140 Maven-Tests bestanden; Package erfolgreich.
- [Vantage](nachweise/fix_vantage_README.md): **88 Tests bestanden** in der vollständigen Suite nach dem letzten Interruptfix. Package, Distribution und Java-Startprüfung ohne Appausführung erfolgreich.
- [Finale gemeinsame Consumer-Regression](nachweise/fix_scanner_final_consumers.log) und [JUnit](nachweise/fix_scanner_final_consumers.xml): **317 bestanden**, 153,99 Sekunden. Dieser Lauf prüft den fertigen Stand einschließlich Tabellen, Admin, Stufe 0, Snapshot-Identität, Quellenverträgen und bestehenden GUI-Regressionsfällen. Die Protokolle der gezielten Arbeitspakete liegen zusätzlich unter `nachweise/fix_tabellen_*` (102 bestanden) und `nachweise/fix_stufe0_*` (50 bestanden).

Die Testgruppen überlappen und werden nicht zu einer Zahl verschiedener Tests addiert. Die Scanner-Standardsuite schließt die per `llm` markierten kostenpflichtigen Modellaufrufe gemäß `pytest.ini` aus. Die gezielten Downloadtests verwenden kontrollierte Antworten und temporäre Dateien. Sie sind keine Behauptung erfolgreicher neuer Plattformabrufe.

Gebaut wurden das [MqlDownloader-JAR](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/MqlDownloader/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar) und das [Vantage-Paket](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/vantage/target/VantageMonitor-1.2.0-utc-renewal-20261018.zip). SHA-256, Dateigrößen und Quellcode-Hashes stehen in [BEHEBUNG.manifest.json](BEHEBUNG.manifest.json). Das Prüfskript `nachweise/fix_abschluss_pruefen.py` kontrolliert außerdem die unveränderten 50 ursprünglichen Auditbelege und Dokumentlinks.

## Betrieb und verbleibende Grenzen

Die produktiven Monitore wurden während dieser Behebung nicht gestartet oder beendet. Die neuen Java-Builds müssen beim nächsten regulären Start verwendet werden. Ein anschließender Quellen-Update-Lauf erneuert die Historien; erst danach kann ein neuer Scannerlauf fehlende aktuelle Forensik und Tabellenwerte berechnen. Insbesondere sind die im Audit gefundenen Vantage-Legacy-Dateien durch den Build allein noch nicht erneuert.

Es gab keine produktive Datenmigration, keine rückwirkende Ampeländerung, keinen vollständigen produktiven Scan, keine MetaTrader-Neustarts und keine echten LLM-Aufrufe. Die im Audit sichtbaren alten/fehlenden Workflow-Nachweise bleiben bis zur tatsächlichen erfolgreichen Neuberechnung alt/fehlend. Der Fix erzeugt dafür keine Ersatzwerte.

Die vollständige Composite-Identität, die Erweiterung des täglichen Betreuers auf alle Quellen und die zurückgestellten Monitor-Integrationen gehören weiterhin zu den ausdrücklich separat geführten Architekturaufgaben. Die drei historischen Audit-Fremdschlüsselwaisen wurden nicht gelöscht. Frühere private Auditkopien und bereits blockierte Bereinigungen wurden nicht erneut angefasst.

Der ergänzend vorgeschlagene `last_checked_at`-/neuester-Trade-Nachweis je Artefakt ist eine gesonderte Metadatenerweiterung und wurde hier nicht eingeführt. Bestehende Artefaktzeitstempel werden nicht nachträglich als Nachweis neuer Plattformabrufe umgedeutet. Die Vantage-Stores sind weiterhin zwei getrennte Veröffentlichungen mit getesteter Wiederaufnahme; eine gemeinsame Transaktion über beide Ablagen oder Widerstand gegen Stromausfall ist damit nicht nachgewiesen.
