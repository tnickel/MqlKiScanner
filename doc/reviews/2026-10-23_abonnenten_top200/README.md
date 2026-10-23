# Abonnenten-Refresh: Nachprüfung und Top-200-Korrektur, 23.10.2026

## Verbindlicher Umfang

Nutzerantwort: „Je Quelle höchstens 200 Anbieter, absteigend nach Abonnenten“.
Nur Anbieter mit mindestens einem Abonnenten. MQL4/5 bilden eine Quelle und
teilen sich die 200 Plätze. Auswahl bei jedem Frischabruf neu, keine feste ID-Liste.

## Ursachen im bisherigen Lauf ab 11:19:33 MESZ

| Quelle | Tatsächliches Verhalten vor der Korrektur |
|---|---|
| MQL | Scanner target=200 wurde ignoriert; lokale Sicherheitslimits 4500 je Version. Abonnentensortierung und Null-Abbruch vorhanden, aber jedes positive Einzelprofil trotzdem neu geladen/konvertiert. |
| Pelican | Discover enthält die Zähler bereits, trotzdem Details/Stats aller 2209 Anbieter, unsortiert einschließlich Null-Abonnenten. 200 begrenzte nur Trades. Vorheriger lokaler Katalog: 2204 Anbieter, 643 positiv. |
| Robo | Neuer Katalog in zwei Sekunden, eine Rating-Sammelabfrage; 200er-Limit vorhanden. Zusätzlicher profit_percent_max=300-Filter verhindert reine Abonnenten-Top-Auswahl. |
| Zulu | Neuer Katalog in vier Sekunden, zehn Suchseiten. 200er-Limit und Follower-Sortierung vorhanden. |
| Vantage | Kuratierte Listen plus Mischung aus Kopierer- und Rendite-Ranking; trotz Zählerrefresh Kennzahlen für 150 Anbieter nachgeladen. |

Robo-/Zulu-Geschwindigkeit war somit kein Beleg für veraltete Daten. Die
unterschiedliche Auswahl und der überflüssige Detailaufwand waren reale Fehler.

## Änderung

Alle fünf Clients unterstützen jetzt `POST /api/v1/update` mit
`nurAbonnenten=true`, `target=200`, `tradelisten=false`.
Die Boolean-/Ganzzahlparameter werden geprüft. Der Scanner verlangt vor dem
Start `/health.abonnentenRefresh=true` und am Abschluss denselben nicht leeren
Job-Identifier, `ergebnis.nurAbonnenten=true`, höchstens 200 gelieferte Anbieter
und keinen Katalog-Skip. Ein fremder bereits laufender Job ist kein Nachweis
eines neuen Abrufs. Fehlgeschlagene Frischmessungen bleiben im Endergebnis
sichtbar, auch wenn der alte lokale Katalog lesbar ist.

MQL liest ausschließlich die sortierten Tabellen. Für eine gemeinsame exakte
Top-200-Auswahl können je MT4/MT5 bis zu 200 Listenkandidaten gelesen werden;
publiziert und als neue Historie gemessen werden insgesamt höchstens 200.
Pelican nutzt seine Discover-Sammelliste, Vantage nur das Kopierer-Ranking,
Robo das Ranking ohne Gewinnfilter, Zulu unverändert `followers`.
Keine Detail-/Statistik-/Trade-Einzelabrufe im neuen Modus.

Metadaten/Finanzfelder werden anhand der Anbieteridentität erhalten. MQL nutzt
atomare Mitgliedschaft in der vorhandenen DB, Pelican und Vantage getrennte
Zählerkataloge. Robo/Zulu archivieren den alten CSV-Inhalt verlustfrei vor dem
Ersetzen und invalidieren den Vollkatalog-Frischemarker. Vollständige
Profil-/GUI-Ladewege bleiben getrennt erhalten. Zählerupdates behaupten keine
neue Finanzkennzahlenfrische.

## Verifikation

- Scanner: 139 relevante pytest-Tests bestanden (Abonnentenstatistik,
  Update-Transport, Downloader-Client, Stufe-0-Workflow/Abschluss/UI).
- MqlDownloader: 173 Tests, 0 Fehler; Maven-Paket erstellt.
- PelicanTrading: 79 relevante Tests, 0 Fehler; Maven-Paket erstellt.
- roboforex: vollständige Suite mit 205 Tests, 0 Fehler; Maven-Paket erstellt.
- zulumonitor: vollständige Suite mit 160 Tests, 0 Fehler; Maven-Paket erstellt.
- vantage: 61 relevante Tests, 0 Fehler; Maven-Paket erstellt.

Tests verwenden lokale HTTP-Fixtures und temporäre Datenbanken/Dateien.
Sie prüfen Filter/Sortierung/Pagination, neue Anbieter, Grenzen/Gleichstände,
fehlende/ungültige Zähler, Erhalt der Details und Frische-/HTTP-Verträge.
Kein positiver Handels-/Risiko-Befund und keine Bewertungsregel wurden geändert.

## Aktivierung ausdrücklich noch offen

Die nativen Clients wurden nicht neu gestartet. Insbesondere die vor der
Änderung gestarteten MQL- und Pelican-Jobs laufen noch mit altem geladenem Code.
Es wurden keine neuen produktiven Updates, Scans oder Synchronisierungen
angestoßen. Ein erfolgreicher Build aktiviert keinen laufenden Java-Prozess.
Eine Live-Abnahme des neuen Abrufwegs ist somit noch nicht erfolgt.


## Zusatzprüfung: tatsächlich höchste Abonnentenzahlen

Nach der Nachfrage des Nutzers wurde speziell geprüft, dass die Auswahl vor
der Begrenzung nach Abonnenten erfolgt:

- MQL: jede MT4-/MT5-Listenseite erzwingt `orderby=subscribers`. Innerhalb und
  zwischen Seiten muss die Reihenfolge nichtsteigend sein. Beide Teillisten
  werden gemeinsam sortiert, erst danach auf 200 gekürzt. Ein Test mit
  abwechselnder Plattformrangfolge liefert exakt die 200 größten Werte;
  es gibt keine feste Plattformquote.
- Pelican: die vollständige gelieferte Discover-Liste wird nach aktuellen
  `NumCopiers` sortiert und erst dann begrenzt.
- Robo: der Request sortiert nach `subscriber_count DESC`; im Zählermodus
  gibt es keinen zusätzlichen Gewinnfilter.
- Zulu: `followers DESC`, mit unveränderter Zählerdefinition.
- Vantage: ausschließlich `overallSort=2` und aktuelles Feld `copiers`;
  keine kuratierten oder Rendite-Listen im Zählermodus.

Für paginierte Ranglisten führen fehlende/ungültige Zähler oder ein
Sortieranstieg auf einer gelesenen Seite zu einem Fehler statt zu einem
Erfolgsnachweis. Bei Pelican erfolgt die Sortierung lokal auf der vollständigen
Sammelantwort. Die Aussage bezieht sich auf den vom jeweiligen Endpunkt
angebotenen Katalog; versteckte, regionale oder vom Anbieter nicht angebotene
Konten sind damit nicht erfasst. Abonnentenzahl ist Popularität und kein
Qualitäts-/Risikogütesiegel.

Zusätzliche adversariale Tests bestanden: MQL gemischte Rangfolgen und
Seitengrenzen (24 gezielte Tests), Pelican 1500 unsortierte Anbieter mit den
stärksten am Ende und 300 Nullzählern am Anfang, Vantage überlappende Seiten
mit notwendiger dritter Seite und absichtlich gegenläufigem `maxCopiers`,
Robo volle 500er-Seite mit Gleichstand an Platz 200 auf der Folgeseite,
Zulu elf tatsächliche 20er-Seiten. Es wurden dabei keine weiteren
Produktionscodefehler gefunden. Robo/Zulu vollständige Suites und
Pelican/Vantage relevante Suites sowie Maven-Pakete erneut erfolgreich.
Keine Aktivierung oder produktive Plattform-Neumessung in dieser Zusatzprüfung.
