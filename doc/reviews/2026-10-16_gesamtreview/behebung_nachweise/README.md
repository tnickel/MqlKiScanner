# Nachweise der Behebung

`test_results.json` enthält aus JUnit-/Surefire-XML gelesene Testergebnisse.
Die vollständigen Logs und Snapshotmanifeste liegen daneben. Originale XMLs,
Buildverzeichnisse und eingefrorene Testkopien bleiben lokal unter
`D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_fixes_2026-10-16/`.
Die MQL-Abhängigkeitsprüfung liegt lokal zusätzlich unter `waste/dependabot_mql_2026-10-16/`.

Die Scanner-Vollsuite lief vor der letzten Budget-/Portfolio-Gegenprüfung.
`scanner_final_delta` enthält den endgültigen Stand; dessen 354 Tests prüfen
die danach geänderten Pfade einschließlich sieben neuer Budget- und fünf
neuer Portfoliofälle. Die Läufe überlappen und dürfen nicht addiert werden.
`later_source_changes` dokumentiert die zwischen beiden Snapshots geänderten
Dateien. Für alle finalen Läufe wurde der getestete Code mit dem Checkout
abgeglichen; spätere reine Dokumentation ist dabei ausgenommen.

Pelican/MQL/Robo verwenden Git-Archive mit protokollierten aktuellen Overlays.
Zulu und Vantage wurden zusätzlich aus einem frischen `checkout-index` mit
`core.autocrlf=true` gebaut; die bytegenau gehashten Promptfixtures erzwingen
LF. SHA256 beschreibt die tatsächlichen Bytes des jeweiligen Testsnapshots;
plattformabhängige Zeilenenden im Git-Checkout können abweichen.

Die Nachweise enthalten keine produktiven Trade-Caches, Cookies, lokalen
Datenbanken oder geheimen Einstellungen. Netzwerkverkehr der MQL-
Abhängigkeitsprüfung war auf Paketdownloads und Sicherheitsquellen begrenzt.
Plattformlogins, bezahlte LLM-Aufrufe und Orders fanden nicht statt.
