# Abonnenten-Recherche: Umsetzung und Prüfung

Stand: 23.10.2026. Auftrag: „setze das um“, nach dem Konzept in `doc/26`.

## Bedienung und fachlicher Umfang

**Abonnentenstatistik → Strategien bewerten** öffnet den Startdialog. Standard:
Top 200 je Quelle mit mindestens einem Abonnenten, MQL4/5 zusammen, mindestens
zwei Monate und 50 abgeschlossene Trades. Keine feste DD-Grenze. Einstellbare
Startgewichtung: 70 % Jahres-RetDD-Perzentil plus 30 % quellenrelatives
Abonnentenperzentil. Referenz und Auswahl werden je Quelle atomar eingefroren.

Der Lauf beschafft gezielt aktuelle Profile und vollständige verfügbare
Tradelisten. Der vorhandene Rechenkern prüft Kapitalbasis, Währung, Kontrakte,
historische Umrechnung, Exposure und Martingale. RetDD verwendet den größten
gemessenen relativen Equity-DD einschließlich Floating. Geschlossene Trades
ersetzen diesen Nenner nicht. H1-Bar-Schlüsse belegen keine Intrabar-Tiefs;
aktuell offene Kontopositionen sind nicht Teil dieser historischen Messung.
Zwei Monate/50 Trades sind eine Materialschwelle, kein Signifikanznachweis.

Alle auswertbaren Anbieter erhalten einen Kurztest mit vollständigen Trades
in belegbaren Blöcken. Die besten fünf Kandidaten erhalten ausführliche
Berichte als Ansicht, Markdown und PDF. KI rechnet die Rangfolge nicht und
erfindet keine zusätzlichen Ausschlussregeln. Befunde müssen auf Codefakten
und echten Trade-Referenzen beruhen. Änderungen der Vergleichsbasis machen
abhängige Top-5-Berichte ungültig.

Die beiden Prompts und Modelle sind unter **Einstellungen → Berichtsvorlagen →
Abonnentenstatistik** editierbar. Die bestehenden Workflow-Prompts und die
Drei-Monats-/DD-Ampel bleiben fachlich getrennt. Eigener persistenter Store:
`data/abonnenten_analyse/jobs.sqlite3`; keine Migration der Hauptdatenbank.
Stoppen und explizites Fortsetzen erhalten fertige Stufen und bezahlte Antworten.
Ein Lauf verwendet das gemeinsame Scan-/Studienlock. Anzeige/Rerun startet
keine Arbeit. Budgetgrenzen gelten über bestehende Tages-/Monatsbuchhaltung
und einen eigenen Laufverbrauch einschließlich unbekannter Transportversuche.

## Quellenclients

Gezielter Vertrag: `POST /api/v1/providers/{id}/{version}/refresh`, eigener Job
mit eindeutiger Identität, Frische- und Vollständigkeitsbeleg. Kein stiller
Offline-Fallback. Vantage paginiert vollständig; Pelican und Zulu prüfen
gegen archivierte Trade-Identitäten, bevor sie vollständige Historie bestätigen.
MQL verwendet einen gezielten Export ohne die alten Drei-Monats-/DD-Vorfilter.
Robo bestätigt ausdrücklich keine unbelegten Geld-/Volumeneinheiten und liefert
`units_unverified`; seine Anbieter bleiben mit Datenlückengrund sichtbar.

Alle fünf nativen Clients wurden neu gebaut und nach geprüfter Identität,
Arbeitsverzeichnis und Leerlauf sanft geschlossen und neu gestartet. Kein
erzwungenes Prozessende, keine Update-POSTs und keine neuen Scans beim Neustart.
Die bestehende MQL-Zeitplanung blieb erhalten. Anschließende GET-Prüfung:

| Quelle | Port | Health | Status | Provider-Refresh |
|---|---:|---|---|---|
| MQL | 8089 | ok | idle | verfügbar |
| Pelican | 8090 | ok | idle | verfügbar |
| Robo | 8091 | ok | idle | gesperrt: Einheitenbelege fehlen |
| Vantage | 8092 | ok | idle | verfügbar |
| Zulu | 8093 | ok | idle | verfügbar |

Alle fünf melden `abonnentenRefresh=true` und keinen aktiven Job. Lokale
Neustartbelege unter `.tmp/source_activation_20261023_144916/`; MQL-Protokolle
unter `%LOCALAPPDATA%/Codex/logs/mql-provider-refresh-20261023_145102/`.
Abschließender GET-Beleg unter
`data/runs/abonnenten_umsetzung_20261023_145143/final_health.json`.
Laufzeitdateien, Datenbanken und Zugangsdaten werden nicht veröffentlicht.

## Verifikation

Die Tests umfassen synthetische vollständige Läufe, alle Kurztests/exakt Top 5,
Rangbindung, Budgetende/Fortsetzen, korrupte Snapshots, Quellenteilfehler,
Prompt-/Policy-/Ausschlussänderungen, ungekürzte Trade-Blöcke, fehlende Belege,
JSON-Verträge, PDF-Erzeugung und Streamlit-Dialog/Stoppen/Fortsetzen/Export.
Testaufrufe verwenden keine produktiven Downloads oder bezahlten Modelle.

Vier beim Gesamtcheck sichtbare Altpfade wurden korrigiert: der zentrale
Bericht-Runner respektiert das bereits existierende `berichte_neu`-Kennzeichen;
die übrigen drei Fixtures wurden auf bestehende Verträge für Streamlit-Reruns,
belegte Berichtswiederverwendung und den historischen Tiefenanalyseaufruf
gebracht. Deren gezielter Regressionscheck: 21 Tests bestanden.

Der Scanner-Gesamtcheck ist in vier unabhängige Dateigruppen aufgeteilt.
Ergebnis: **3.024 bestanden, 1 übersprungen, 4 abgewählt** (echte Modelltests
sind opt-in). Die Gruppen bestanden mit 685/710/804/825 Tests.
Protokolle und Maschinenbilanz liegen lokal unter
`data/runs/abonnenten_umsetzung_20261023_145143/`.
Der zusätzliche Check nach der Export-/Messhinweisanzeige bestand mit 11 Tests.

Die aktuellen nativen Tests bestanden mit MQL 184, Vantage 107, Pelican 197,
Zulu 165 und Robo 206: zusammen **859**. Maßgeblich sind die heutigen
Surefire-Berichte in den jeweiligen Repositories. Ein alter Pelican-
`LoginAutomatLiveCheck`-Fehlerbericht vom 07.10. gehört nicht zu diesem Testlauf;
ein produktiver Login wurde hier nicht erneut getestet.

Die aktivierten Clients und synthetischen Ende-zu-Ende-Prüfungen sind kein
Nachweis eines produktiven Analyselaufs. Es wurde kein neuer Forschungsauftrag
in der produktiven Oberfläche gestartet.
