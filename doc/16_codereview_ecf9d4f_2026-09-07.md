# Code-Review des aktuellen Stands ecf9d4f

Datum: 7. September 2026. Geprüfter Commit:
`ecf9d4f8269e80fa60dd0ddb68812ebacfe7e2f6`, Branch `main`.

**Ergebnis: sieben bestätigte neue Befunde — vier P2, drei P3.**
Die Reproduktionen belegen Fehler unter den angegebenen Bedingungen.
Sie belegen nicht, dass diese Bedingungen bereits in einem produktiven Lauf
eingetreten sind. Es wurden keine Produktdateien oder bestehenden Tests verändert
und keine Korrekturen implementiert.

Geprüft wurden Parser, Engine, sämtliche Forensikmodule, Scoring, Statistik und
KI-Payload, Pipeline, Berichtsspeicherung, Datenbank und Archive, MQL5-Abrufe,
Login-/Browserpfade sowie Streamlit-Seiten und Hintergrund-Worker. Drei
Teilprüfungen liefen parallel; zentrale Befunde wurden anschließend unabhängig
gegengelesen beziehungsweise erneut reproduziert.

## Priorisierte Befunde

### F1 — P2: CSV-Reihenfolge entscheidet über Stop-Nachweis und grüne Ampel

**Ort:** `src/mqlkiscanner/forensics/stops.py:148–159`.

Die Verlustdistanzen werden in Klassen gerundet. Bei gleicher Häufigkeit wählt
`Counter.most_common(1)` die zuerst in der CSV auftretende Klasse. Eine auf null
gerundete Distanz erfüllt `top_level > 0` nicht; eine ebenso häufige positive
Klasse erfüllt die Bedingung. Dadurch verändert bloße Zeilenumordnung den
strukturierten Stop-Nachweis, obwohl Trades und Zeitpunkte unverändert bleiben.

**Reproduktion:** Acht Gold-Verlustdistanzen
`0,01 / 0,02 / 0,03 / 0,04 / 0,06 / 0,07 / 0,08 / 0,09` ergeben viermal die
Klasse `0,0` und viermal `0,1`. Mit identischen ergänzenden Gewinntrades führt
der echte Parser-/Engine-/Scoring-Pfad zu:

- Erste Nullklasse: `stop_evidence=none`, Score **3,1**, **Gelb**.
- Erste positive Klasse: `stop_evidence=cluster`, Score **2,6**, **Grün**.

**Abhilfe:** Gleichstände deterministisch und hinsichtlich Nullklassen konsistent
behandeln. Der Befund verlangt keine neue statistische Schwelle und beweist
nicht, welche der beiden Einstufungen fachlich richtig ist. Dass die CSV-Reihenfolge
zwischen ihnen entscheidet, ist der Implementierungsfehler. Die kürzlich
korrigierten DD-/Exposure-Zeitgruppen sind ein anderer Codepfad.

### F2 — P2: Direkter HTTP-403-Abbruch lässt alte grüne Bewertung aktuell erscheinen

**Ort:** `src/mqlkiscanner/pipeline.py:570–574`; Übergabe an die Oberfläche
in `app_pages/scan.py:555–557`.

Ein direkt aus der Session kommender `Mql5HardStopError` wird sofort erneut
geworfen. Das bereits mit neuen Kennzahlen befüllte Ergebnis gelangt dadurch
weder in den gemeinsamen Speicherpfad noch in `exc.result`. Die Oberfläche kann
den betroffenen Datensatz deshalb auch nicht in den neuen Lauf übernehmen.

**Reproduktion:** Ein erfolgreicher realer CSV-Scan speichert EQ-DD **5 %**,
vollständige Forensik und einen Bericht. Im Folgescan liefert die Kennzahlenseite
EQ-DD **95 %**; anschließend scheitert der Export mit dem originalen Fehlertyp
`Mql5HardStopError("HTTP 403")`. Ergebnis:

- `exc.result` bleibt `None`.
- Der aktuelle DB-Katalog enthält weiter **5 %**, Grün und den alten Bericht.
- Es gibt keinen gespeicherten Aktualisierungsfehler; `forensik_vorhanden=True`
  qualifiziert den alten Datensatz weiter für unveränderte Übernahme im
  „Nur neue“-Modus.

**Abhilfe:** Weitere Netzwerkarbeit sofort stoppen, zuvor aber den vorhandenen
Fehler-/Vorprüfungsstand atomar speichern und als Ausnahmeergebnis übergeben.
Der vorhandene Pfad für erst durch den Fehlerzähler ausgelöste Hard-Stops zeigt
bereits dieses Muster. Historie darf erhalten bleiben; im aktuellen Katalog
muss die fehlgeschlagene Aktualisierung erkennbar sein. Die DB funktioniert in
dieser Probe — es handelt sich ausdrücklich nicht um den beabsichtigten Rollback
bei einem Datenbankschreibfehler.

### F3 — P2: Abgewiesene erneute Anmeldung wird nicht als systemischer Fehler gezählt

**Ort:** `src/mqlkiscanner/mql5/ratelimit.py:43–73`; tatsächlicher Fehlertext
in `src/mqlkiscanner/mql5/browser_session.py:238–240`.

Die Fehlerklassifikation erkennt mehrere Login-Formulierungen, aber nicht die
vom Browsermodul tatsächlich erzeugte Meldung „MQL5 hat die Anmeldung im Browser
nicht akzeptiert“. Auch die Exception-Kette enthält im reproduzierten Fall
keinen erkannten Marker. Die Pipeline behandelt den Fehler daher wie ein
Problem eines einzelnen Signals und setzt die Anmeldeversuche fort.

**Trigger:** Eine erneute Anmeldung scheitert während einer bereits laufenden
Forensik, etwa nach einem Accountwechsel. Der erfolgreiche Anfangscheck der
Station liegt dann bereits zurück. Ein von Anfang an scheiternder Login wird
von der Oberfläche weiterhin separat abgefangen.

**Reproduktion:** Der Originalfehler wird im Browsermodul erzeugt und durch
Session, Exporter, Chrome-Fallback und Pipeline geführt. Zwei Signale verursachen
**acht Browser-Startversuche**, obwohl die Fail-Fast-Grenze auf **eins** steht.
`_mql5_hard_fails` bleibt **null**. Browser und externe Antworten sind simuliert.

**Abhilfe:** Abgewiesene Authentifizierung als eindeutigen typisierten Fehler
durchreichen oder mindestens die tatsächlich erzeugten Loginfehler vollständig
klassifizieren. Erfolgloser Fallback darf den systemischen Fehler nicht verlieren.

### F4 — P2: „Alle Berichte neu erstellen“ überspringt übernommene Signale

**Ort:** `app_pages/scan.py:764–768`; zugesagtes Verhalten in `:338–349`.

Bei „Nur neue“ und mindestens einer frisch geprüften ID wird die Ergebnismenge
vor der KI-Stufe auf diese neuen IDs eingeschränkt. Das geschieht auch mit
aktiviertem Schalter „Vorhandene Berichte neu erstellen“, obwohl die Oberfläche
ausdrücklich die Neuerstellung aller Berichte zusagt. Übernommene Ergebnisse
erreichen die Berichtslogik nicht.

**Reproduktion mit AppTest und echter temporärer DB:** Signal #90001 ist bereits
geprüft, sein alter Bericht wird von der echten Basisprüfung als ungebunden
verworfen. Signal #90002 ist neu. An `run_llm` wird nur #90002 übergeben — sowohl
mit als auch ohne ausdrücklich eingeschaltete Neuerstellung. #90001 bleibt ohne
gültigen Bericht. Im anschließenden Lauf ohne neue ID erreicht dasselbe alte
Signal dagegen die KI-Stufe. Die Entscheidung hängt damit von der Anwesenheit
eines weiteren neuen Signals ab.

**Abhilfe:** Auswahl der erneut herunterzuladenden Signale und Auswahl der zu
erstellenden Berichte getrennt auswerten. Passende Berichte dürfen weiterhin
wiederverwendet werden; der ausdrückliche Neuerstellungswunsch muss berücksichtigt
werden. Veraltete oder fehlende Berichte benötigen ebenfalls eine konsistente
Auswahlregel.

### F5 — P3: Unverändert übernommene Bewertungen erscheinen als „NEU“

**Ort:** `app_pages/scan.py:789–790`; Anzeige und Filter in
`app_pages/ergebnisse.py:40–53,125–138`.

Nach dem Archivieren werden sämtliche Live-Ergebnisse in `refreshed_ids`
eingetragen, einschließlich ausdrücklich unverändert aus der DB übernommener
Bewertungen. Die Ergebnisseite erklärt „NEU“ als im letzten Lauf aktualisiert
und verwendet dieselbe Menge für den „Nur NEU“-Filter.

**Reproduktion:** Tatsächlich neu geprüft ist #90002:
`new_ids=[90002]`. Dennoch lautet `refreshed_ids=[90002,90001]`; die unveränderte
DB-Bewertung #90001 wird in AppTest als „NEU“ markiert und entsprechend gefiltert.

**Abhilfe:** Tatsächliche Aktualisierungen gesondert erfassen; bloße Übernahme
darf keinen Aktualisierungsstatus erzeugen. Der Fallback der Ergebnisseite von
leerer Frische auf alle Sitzungsergebnisse muss diese Unterscheidung erhalten.

### F6 — P3: Lot-Verteilung verliert Häufigkeiten durch gerundete Schlüssel

**Ort:** `src/mqlkiscanner/stats.py:104` und
`src/mqlkiscanner/trade_data.py:142–143`.

Die Volumina werden zunächst korrekt nach ihrem exakten Wert gezählt. Beim
Aufbau des Dictionaries werden die Schlüssel auf zwei Nachkommastellen
formatiert. Unterschiedliche Volumina können dann denselben Schlüssel erhalten;
die spätere Häufigkeit überschreibt die vorherige.

**Reproduktion:** Vom Parser akzeptierte Volumina `0,001 / 0,001 / 0,002` ergeben
bei **drei Trades** sowohl in der Statistik als auch im KI-Payload
`{"0.00": 1}`. Die Symbolbandbreite wird ebenfalls zu `0.00-0.00` gerundet.
Der Codevertrag beschränkt positive endliche Volumina nicht auf zwei
Nachkommastellen. Eine konkrete Brokerspezifikation ist für diesen internen
Zählfehler nicht erforderlich.

**Abhilfe:** Ausreichende Schlüsselpräzision bewahren oder bei bewusstem Binning
Häufigkeiten zusammenzählen. Die ursprünglichen Volumina und die Exposure-Rechnung
bleiben in diesem Beispiel erhalten; betroffen sind Statistik und KI-Eingaben.

### F7 — P3: Uhrzeit lässt letzten vollen Kalendermonat verschwinden

**Ort:** `src/mqlkiscanner/stats.py:135–144`.

`replace(day=1)` bewahrt die Uhrzeit. Ist die Uhrzeit des ersten Trades später
als die des letzten Abschlusses, endet die Monatsschleife vor dem letzten Monat.
Die danach verwendete Vollständigkeitsprüfung arbeitet dagegen ausdrücklich mit
Kalendertagen.

**Reproduktion:** Für `01.01.2024 12:00 → 29.02.2024 08:00` fehlt Februar in
`full_month_keys`. Vertauscht man nur die Randuhrzeiten, wird er berücksichtigt.
Ein CSV-Beispiel liefert Februar-Netto **−10**, aber
`negative_months_full=[]`.

**Abhilfe:** Monatsvergleich auf Jahr/Monat beziehungsweise normalisierte
Monatsanfänge begrenzen. Der aktuelle Aufrufer ist die Referenzprüfung;
eine Auswirkung auf Live-Score oder Kandidatenampel wurde nicht festgestellt.

## Nachweise und Grenzen

Die lokalen, Git-ignorierten Proben liegen unter `.tmp/review_ecf9d4f/`:

- `engine_cluster_probe.py`: Parser → Engine → Scoring → Ampel, identische
  Handelsdaten bei geänderter CSV-Reihenfolge.
- `engine_precision_probe.py`: Lot-Häufigkeiten und fehlender negativer Vollmonat.
- `pipeline_probe.py`: echter synthetischer CSV-/DB-/Berichtspfad und direkter
  HTTP-403-Hard-Stop nach geänderten Kennzahlen.
- `ingestion_login_failfast.py`: tatsächlicher Browserfehler und seine
  Weiterverarbeitung in Session, Exporter und Pipeline.
- `ui_probes.py`: zwei parametrische AppTest-Fälle für Berichtsneuerstellung
  und Aktualisierungsmarkierung; beide bestanden.

Alle genannten Reproduktionen wurden in dieser Prüfung ausgeführt. Externe
Requests, Modellantworten und Browser waren simuliert. Datenbanken, Zugangsdaten
und Cookies wurden ausschließlich temporär oder als Mocks verwendet; keine
produktiven Daten wurden verändert und kein Produktivserver gestartet.

Der letzte vollständige Testlauf direkt vor diesem Review bestand aus
**400 pytest-Tests und 85 Referenzprüfungen**. Da Produktcode und bestehende Tests
unverändert blieben, wurde diese Suite nicht nochmals ausgeführt. Die neuen
Proben untersuchen zuvor nicht abgedeckte Fälle.

Die bereits akzeptierten Grenzen — fehlende FX-Umrechnung, unbelegte
Indexkontrakte, EQ-DD-Kalibrierungsausnahme, großzügiges Tokenbudget,
Brutto-/Netto-Martingale-Definition und greedy Zwillingsvergleich — wurden
nicht erneut als Fehler gezählt. Historisch gekennzeichnete globale Portfolios
sind ebenfalls kein neuer Befund.

Die drei vorbestehenden Dokumentlöschungen blieben unverändert. Zum Abschluss
dieser reinen Prüfung wurden weder Korrekturen implementiert noch Commits
oder Pushes ausgeführt. Die anschließenden Korrekturen stehen in
`17_korrekturen_codereview_ecf9d4f_2026-09-07.md`.
