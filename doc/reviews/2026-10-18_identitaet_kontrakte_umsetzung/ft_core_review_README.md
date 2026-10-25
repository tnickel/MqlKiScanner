# Unabhängige Gegenprüfung der Identitäts-Consumer

Scope: aktueller `pipeline.py`, `fix_signale.py`, `ampel_verlauf.py`,
`llm_runner.py`, `ingest.py`, Agenten-Consumer außer Dossier-DB.
Keine Änderungen an diesen Root-Dateien durch den Gegenprüfer.
Unabhängige Regressionen: `tests/test_identity_core_review.py`.

Bestätigte und inzwischen behobene Fehler:

1. Ein neu im Vollkatalog gepinntes Fremdquellensignal ohne `signals`-Kopf wurde
   bei fehlendem Eintrag im regulären Abonnenten-Katalog übersprungen. Root
   ergänzt nun UID-gebundene aktive Vollkatalogzeilen, ohne MQL-URL zu erfinden.
2. Ingest-Dedupe nach Quelle+ID konnte einen widersprüchlichen MT4-/MT5-Eintrag
   entfernen, bevor der Pipeline-Wächter ihn sah. Beide Seitenreihenfolgen
   reproduzierten die falsche Auswahl (`ft_core_review_before_tests.log`). Root
   erhält Plattformunterschiede bis zum Konfliktwächter; auch der kombinierte
   Direkt-/REST-Crawl erhält solche Widersprüche.
3. Ein nach der Forensik beschädigter Snapshot konnte neu geparst, aber unter
   dem alten gemessenen SHA an drei KI-Aufrufe gebunden werden. Die synthetische
   Reproduktion änderte eine valide CSV von Netto 1 auf 10; drei Fake-Calls
   fanden statt (`ft_core_review_sha_before_tests.log`). Der neue Root-Helper
   friert Eingabebytes vor dem Payload ein, prüft den vorhandenen Mess-SHA,
   parst den Snapshot und prüft ihn erneut. Die Basis folgt erst danach.
4. Der Vollkatalog darf Quelle+ID mit widersprüchlicher Plattform nicht als
   letzte Zeile ersetzen. Der zentrale DB-Guard des Persistenz-Agenten verhindert
   das; der unabhängige Sync-Test bestätigt den Fehlerstatus und unveränderten
   alten Katalogbestand.

Aktuell **10 bestanden**, Exit 0, 1,41 Sekunden. Weitere Fälle prüfen getrennte
gleichnamige IDs verschiedener Quellen, nicht auflösbare Legacy-Pins,
quellengebundene Berichtsbasis, stabile Basis bei bloßer Quellenumbenennung und
Verbindungs-/Kandidatenkonflikt vor Metrics-Abruf ohne Persistenz.
`ft_core_review_command.json`, `ft_core_review_tests.log`,
`ft_core_review_tests.xml`, `ft_core_review_exit.txt` dokumentieren den Lauf.

Grenze: gezielte Offline-Integrationstests und lesende Codeprüfung; keine
produktiven Läufe, Modellaufrufe, API-Aufrufe oder Cutover-Abnahme. Das erwartete
Fail-Closed-Verhalten einer alten DB mit neuem Code bleibt bis zur ausdrücklich
freigegebenen Copy-Migration bestehen. Historische Review-Tests können noch alte
SQL-Spalten oder ID-allein-Schreibverträge enthalten; ihre Anpassung und die
abschließende gemeinsame Regression koordiniert Root separat.
