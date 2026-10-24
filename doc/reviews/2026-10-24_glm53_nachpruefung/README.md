# Kritische Nachprüfung des GLM-5.3-Reviews vom 24.10.2026

Stand: 24.10.2026, 01:32 MESZ. Quellcodekorrekturen, Tests und Paketbau abgeschlossen.

Der lokal gefundene GLM-Bericht liegt unter
[`../2026-10-24_codereview_abonnenten_recherche/KI_REPORT_FINDINGS.txt`](../2026-10-24_codereview_abonnenten_recherche/KI_REPORT_FINDINGS.txt).
Er enthält inzwischen auch den im eingefügten Text noch ausstehenden Abschnitt 7
und 49 strukturierte Befunde. Der Bericht wurde als zu prüfende Quelle behandelt.
Die Einzelentscheidung zu jedem Befund steht in [`befunde.json`](befunde.json).
Private Eingangs-, Test- und Abschlussbelege: `data/runs/glm53_review_20261024/`.

## Urteil zum Review

Das Review findet reale Fehler, insbesondere den Verlust des Vollbestands nach
Zählerauswahlen, den zurückgesetzten Zulu-Einzelzähler und fehlende Abbruchsicherheit
beim PDF-Spiegel. Es ist jedoch keine aktuelle Gesamtabnahme: MQL-Abdeckung und
Vantage-Kurzseiten waren durch spätere Grok-Korrekturen bereits behandelt. Mehrere
weitere Punkte beschreiben absichtliche Sperren, Betriebsgrenzen oder neue
Protokollwünsche. Diese wurden nicht pauschal als Implementierungsfehler gewertet.

Insbesondere wurde kein unsicherer MQL-Fallback eingeführt: Eine leere HTML-Seite
kann auch Login, Serverfehler oder unvollständiges Laden bedeuten. Ohne Endbeleg
darf daraus kein erfolgreicher vollständiger Katalog entstehen. Die daraus
folgende Verfügbarkeitsgrenze bleibt ausdrücklich bestehen.

## Korrigierte Fehler

- **Katalogverlust (XR-1 und verwandte Befunde):** Alle fünf nativen Clients
  unterscheiden `catalogScope=full|subscribers`. Antworten nennen auch `unknown`,
  wenn die Basis unbelegt ist. Der Scanner prüft den tatsächlichen Scope je Seite
  und löscht bei Auswahl, unbekanntem Scope oder Alt-Clients ohne Scope keine
  fehlenden Katalogzeilen. Der normale Workflow überspringt unbestätigte Quellen
  sichtbar; Recherche fragt die Zählerauswahl ausdrücklich an.
- **Falscher Vollbeleg und veraltete GUI-Schreibvorgänge:** CSV-Existenz allein
  beweist keinen Vollimport. Pelican, Vantage, Robo und Zulu verwenden einen an
  den CSV-Inhalt gebundenen Beleg; Altbestände bleiben ohne diesen Beleg unbekannt.
  Zählerläufe erhalten bisher bekannte IDs, auch über mehrere wechselnde Auswahlen.
  GUI-Detail-/Trade-Speicherungen erhalten Mitgliedschaft und aktuellere Zähler.
  Der Zulu-Export schreibt nur die gewählten Exportzeilen und verändert keinen Cache.
- **Unbelegte Frische:** Pelican schreibt beim Start aus altem GUI-Cache keinen
  heutigen Abonnenten-Snapshot. Auch der Scanner erzeugt aus Katalogzeilen keine
  eigenen Jetztpunkte mehr: neue Zeitpunkte stammen ausschließlich aus nativen
  Historien. Ein voller Katalog mit 300 Anbietern und 200 neu gemessenen Anbietern
  bestätigt nur diese 200 neu, nicht die übrigen 100.
- **Auswahlqualität (XR-2):** Fehlende Belege für die globale Topauswahl werden
  bis Oberfläche, KI, PDF und CSV als unbestätigt weitergegeben. Bekannte
  Vantage-Lücken bleiben konkret erhalten; unbekannte Rangpositionen werden
  nicht erfunden. Das ersetzt keinen nativen Abdeckungsnachweis.
- **Einzelprofile und Metadaten:** MQL weist falsche Anbieter-/Plattform- und
  Login-HTML vor dem Schreiben ab; gültige Profile mit fehlenden Einzelwerten
  behalten unbekannte Werte. Zulu persistiert den frischen Einzelprofil-Zähler.
  Robo unterscheidet fehlende Kennzahlen von echter Null und übernimmt belegte
  Plattformwechsel, ohne alte Finanzwerte als neu zu deklarieren. Ownerfremde
  Trade-Caches bleiben gesperrt.
- **Historienqualität bei konkurrierendem Schreiben (VT-R5/RB-R5):** REST liest
  Trades und ihre Vollständigkeits-/Qualitätsbelege aus derselben geprüften
  Dateigeneration. Die Regressionen erzwingen einen Generationswechsel bzw.
  einen nach CSV, aber vor Metadaten angehaltenen Schreibvorgang.
- **Fehlerzustände:** Leere erste Listen-Seiten ohne Endbeleg werden nicht als
  vollständige Leerauswahl veröffentlicht. Wiederholte Pelican-Authfehler melden
  `login_required`; Zulu-`cancelled` beendet Scanner-Polling unmittelbar.
  Health kündigt Refresh nur bei vorhandenem Update-Starter an.
- **Tradeserver-PDFs (TMM-R3):** Fehler beim Erstellen oder Sammeln benötigter
  PDFs brechen vor dem Register-POST ab. Ein fehlerbedingt fehlendes Dokument
  kann nicht durch Complete aus dem vorhandenen Spiegel entfernt werden.
  Complete/Abort ohne registrierten Lauf bleiben entsprechend dem Vertrag HTTP 400;
  widersprüchliche Kommentare und Dokumentation sind korrigiert.

Die Gegenprüfung wurde parallel auf Scanner, native Clients und Server verteilt.
Zusätzliche Tests prüfen die Repository-Grenzen, statt nur den jeweiligen lokalen
Speichercode nachzubilden. Bewertungsregeln, Equity-/RetDD-Rechnungen und Prompts
wurden nicht gelockert.

## Nachweise

| Bereich | Umfang | Ergebnis |
|---|---|---|
| Scanner | Gesamte Suite ohne bezahlte LLM-Tests | 3.465 bestanden, 1 übersprungen |
| MqlDownloader | Gesamte Suite und Paket | 194 bestanden |
| Pelican | Gesamte Suite und Paket | 222 bestanden |
| Vantage | Gesamte Suite und Paket | 148 bestanden |
| Robo | Gesamte Suite und Paket | 221 bestanden |
| Zulu | Gesamte Suite, danach betroffene REST-/Update-Tests und Paket | 179 bestanden |
| MqlTradeMonitor | Controller, v2 und Migration unter JDK 21 | 29 bestanden |

Historische Surefire-XMLs wurden nicht als aktuelle Testausführung gezählt.
Der eine Scanner-Skip betrifft fehlende lokale Windows-Symlink-Rechte
(`ERROR_PRIVILEGE_NOT_HELD`, 1314); vier echte LLM-Tests wurden ausdrücklich
abgewählt. Nach der letzten Hilfe-Textkorrektur bestanden zusätzlich 17
bereits in der Suite enthaltene Kriterien-/Forensiktests.
Die übrige MqlTradeMonitor-Suite wurde hier nicht als vollständig geprüft ausgegeben;
die gemeldeten Mockito-Probleme unter Java 25 bestanden bereits vorher.

## Verbleibende Grenzen und Aktivierung

- Alte Scanner-Eigenpunkte lassen sich ohne Herkunftsspalte nachträglich nicht
  zuverlässig von nativen Messpunkten trennen. Sie wurden weder gelöscht noch
  nachträglich als verifiziert umgedeutet.
- Unbelegte Alt-CSV-Bestände werden durch ein Upgrade nicht vollständig. Erst
  ein tatsächlicher regulärer Import kann einen neuen Vollbeleg schaffen.
- Fehlende Rankingbelege, nicht verifizierbare Listenenden, Plattform-Retention
  und widersprüchliche Identitäten bleiben sichtbare Grenzen. Aus ihnen werden
  keine positiven Daten- oder Qualitätsbelege erzeugt.
- Es gibt weiterhin keine automatische Löschregel für historische Zulu-Generationen
  und keine Absicherung für mehrere Monitor-/Serverprozesse auf demselben
  Datenverzeichnis. Ein abgebrochener Sender kann den Serverlauf bis zum vorhandenen
  Timeout blockieren. Das sind dokumentierte Betriebsgrenzen.
- Ein konsistenter leerer Vollspiegel ist nach bestehendem Protokoll erlaubt und
  ersetzt den bisherigen Spiegel. Ein zusätzlicher `allowEmpty`-Schalter wäre
  eine neue Vertragsregel; versehentliche Leerspiegel bleiben ein Bedienrisiko.
- Normales Fortsetzen ist über UI/CLI möglich. Der besondere validierte
  KI-Konfigurationsneustart bleibt ein kontrollierter Operator-Aufruf;
  `budget_resume_refs` hat keinen eigenen Setzweg in der Oberfläche.

Die neuen nativen Pakete sind **noch nicht produktiv aktiviert**. Es gab hierfür
keine Quellenupdates, bezahlten Test-Modellaufrufe, Deployments oder Neustarts.
Der laufende KI-Auftrag behält seine eingefrorenen Aufgaben und seinen Worker;
dieser Review ist kein Abschlussnachweis für dessen Gesamtauswertung.

Abschließender erneuter GLM-Abgleich am 24.10.2026 um 01:31:51 MESZ: Die Datei
enthält alle sieben Abschnitte und weiterhin dieselben 49 Befunde; gegenüber
dem eingangs geprüften vollständigen lokalen Bericht kam nichts hinzu.
SHA-256: `4fd952d29d32031005d82dbbc165e8cc86ba7ec93d5ed6b4fd730edd84d2cbec`.

Die anschließende reine Statusprüfung um 01:32 MESZ bestätigt denselben laufenden
KI-Worker mit zehn Analyseplätzen und unveränderten 800 eingefrorenen Aufgaben
samt Quellensnapshot. Der Auftrag befindet sich weiterhin in den Kurzanalysen;
dies ist keine Fertigmeldung seiner Auswertung.

Die danach ausdrücklich beauftragte produktive Aktivierung und dabei zusätzlich
gefundene Start-/Pagingfehler werden in einem eigenen
[Aktivierungsbeleg](../2026-10-24_native_aktivierung/README.md) nachgewiesen.
Die zeitlich früheren Aussagen dieses Review-Abschlusses werden dadurch nicht
nachträglich als damalige Liveabnahme ausgegeben.
