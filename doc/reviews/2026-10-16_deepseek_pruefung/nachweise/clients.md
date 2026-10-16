# DeepSeek-Gegenprüfung: Parser und öffentliche Regressionen

Datum: 16.10.2026. Aktuelle Basis `cef1e5a`, Forensikversion 18; der Fremdtext
prüfte `80d4692` / Version 16. Geltende `AGENTS.md` vollständig gelesen.
Scope: Parser-PathLike und der private residuale Parser-Test. Kein Stage,
Commit oder Push durch diesen Agenten. Keine Produktionsdaten verändert,
keine privaten Trades kopiert/veröffentlicht, keine Live-/Login-/LLM-/MT-Aktion.

## Ergebnis der kritischen Prüfung

| Aussage | Aktueller Befund |
|---|---|
| P1-2: `Path.lower()` schlägt fehl | Bereits behoben: `parser.load_export` normalisiert `path = str(path)` vor `.lower()`. Öffentliche Regression `test_glm53_scanner_filter_finance.py::test_current_parser_accepts_windows_pathlike` bestand schon auf der unveränderten aktuellen Basis. Kein neuer Produktfix erforderlich. |
| P1-3: Test hängt am privaten Live-Cache | Bestätigt als reproduzierbare Infrastrukturgrenze: `test_real_blocked_signal_fixture_parses` las den nicht versionierten Pfad `data/trades/1496203_positions.csv`; in einem Git-Archiv wird er übersprungen. Die zentralen Footer-/Spacer-/Payloadfälle waren bereits öffentlich synthetisch geprüft. Es fehlte noch ein öffentliches Gegenstück zur kombinierten Prüfung und zur größeren Tradezahl. Diese Coverage ist ergänzt; erst nach erfolgreichem Nachweis wurde der private Residualtest entfernt. |
| Der Residualtest „verdeckt“ den PathLike-Fehler | So pauschal unzutreffend: Bei vorhandenem Cache hätte ein echter PathLike-Defekt diesen Test fehlschlagen lassen. Ein Skip bei fehlendem Cache konnte früher einen ungetesteten PathLike-Pfad hinterlassen. Heute ist dieser Pfad unabhängig öffentlich getestet. |

Der Skip allein beweist keinen Produktionsfehler. Eine aktuelle zusätzliche
Parserfehlfunktion wurde in diesem Auftrag nicht belegt. Die Änderung
verbessert die reproduzierbare öffentliche Testabdeckung und entfernt ihre
Abhängigkeit von privaten, anwachsenden Live-Daten. `parser.py` bleibt
unverändert; keine Änderung fachlicher Regeln oder der Forensikversion nötig.

## Öffentlicher Ersatz und Redundanznachweis

Vollständig synthetisch, ohne Lesen/Kopieren privater Tradezeilen erstellt:

- `tests/fixtures/parser/mt4_export_artifacts.csv`: 13-Spalten-Orderbuch;
  sechs geschlossene Trades, neun Balance-/Correction-Buchungen, zwei separate
  Gebührenzeilen, eine Pendingorder, Spacer und `profit`-Summenzeile.
- `tests/fixtures/parser/mt5_export_artifacts.csv`: elf Positionsspalten;
  zwei Trades, Einzahlung, separate Kosten, reine Zeitstempelzeile und
  `SUMMARY`-Footer.
- `tests/fixtures/parser/README.md`: Herkunft, Vertragsgrenzen und unabhängig
  berechnete Sollwerte. Die Dateien behaupten keine Anbieterhistorie,
  Plattformfrische, Kontraktgröße oder Kontowährung.
- `tests/test_deepseek_parser_public_fixtures.py`: elf neue öffentliche Fälle.

Die Assertions des entfernten privaten Tests haben folgende öffentliche
Gegenstücke:

| Private Assertion | Reproduzierbare öffentliche Coverage |
|---|---|
| Format `mt4_orderbook` | MT4-Fixture wird als PathLike und String gelesen, Format exakt geprüft. |
| Mindestens 2.461 Trades | Großmengenfall mit exakt 2.520 ausschließlich synthetischen Tradezeilen. Ohne Identitäts-/Plattformbeweis bleibt jede Zeile erhalten. |
| Mindestens neun Balancebuchungen | MT4-Fixture und Großmengenfall prüfen exakt neun. |
| Jedes Objekt ist `Trade` | Beide MT4-Varianten, MT5-Varianten und Großmengenfall prüfen die Objekttypen. |
| `profit`-Footer erscheint nicht als Trade | Symbolausschluss, exakte Tradezahl, exakter Maximalgewinn und Brutto-/Netto-Summen. Mutationstest schaltet die Footererkennung aus und muss einen Fehler auslösen. |
| Footer-Gesamtsumme wird nicht als großer Einzelgewinn gezählt | Exakter MT4-Maximalgewinn 50 und Brutto 65,74 statt Einbeziehung der wiederholten Footer-Summe; MT5 Brutto 30 / Netto 28,60. |

Weitere Fälle prüfen BOM, beschädigte letzte Zeile und typenlose Gebühren,
jeweils an temporären Kopien der versionierten synthetischen Dateien. Die
Großmengen-Netto-Summe ist unabhängig 60,92 × 420 = 25.586,40. Der Ersatz
spiegelt keine privaten Kontowerte oder wachsenden Anbieterbestände.

In `test_parser_export_artefakte.py` wurde außerdem der bestehende
Downloader-SUMMARY-Test auf pytest-`tmp_path` umgestellt; er benötigt keine
manuell zu löschende `NamedTemporaryFile(delete=False)` mehr. Die übrigen
bestehenden Footer-/Spacer-/Payload-Regressionen bleiben erhalten.

## Isolierte Nachweise

Finale Umgebung: `clients_snapshot/`, erzeugt mit `git archive cef1e5a` und
gezieltem Overlay ausschließlich der bearbeiteten Tests und neuen öffentlichen
Fixtures. Keine privaten Laufzeitcaches im Snapshot. Python 3.12 aus
`Programs/Python/Python312`, bestehende Store-Site-Packages, Test-DBs und
Ausgaben unter pytest-Tempverzeichnissen; externe Requests durch die bestehende
Testinfrastruktur gesperrt.

- Baseline **im Archiv**: **7 bestanden, 1 übersprungen**,
  `clients_before.log` / `clients_before.xml`. Der Skip ist der private Test.
- Neue öffentliche Fixturefälle vor Entfernen des privaten Tests:
  **11 bestanden**, `clients_public_fixtures.log` / `.xml`.
- Finaler kombinierter Archivlauf: **88 bestanden, kein Skip, 5,61 s**,
  `clients_final.log` / `clients_final.xml`. Enthält neue Fixtures,
  Exportartefakte, neutrale Hedgezeilen, beweisbasiertes Dedup,
  Finanzreview-Regressionen, Ingest und die vorhandene PathLike-Regression.
- `git diff --check`: erfolgreich. Produktcode-Freeze an Root gemeldet.

### Offengelegter Baseline-Zwischenlauf

Beim ersten Baselinebefehl war das Archiv zwar angelegt, pytest wurde aber
versehentlich noch aus dem Live-Checkout aufgerufen. Dadurch wurde der
optionale private Parser-Test einmal lesend ausgeführt (**8 bestanden**).
Produktivdaten blieben unverändert. Es wurden keine Tradeinhalte ausgegeben,
kopiert oder in die neuen Fixtures übernommen. Die versehentlich im
Workspaceroot erzeugten eigenen Log-/XML-Dateien wurden in diesen Auditordner
verschoben: `clients_before_wrong_cwd.log` / `.xml`; sie enthalten nur
Teststatus/-metadaten, keine privaten Tradezeilen.

Dieser Zwischenlauf ist ausdrücklich kein isolierter Abschlussnachweis.
Die Baseline wurde anschließend im Archiv wiederholt; alle maßgeblichen
finalen Nachweise oben stammen ausschließlich aus dem Snapshot. Die Aussage
„keine Produktionsdaten gelesen“ wäre deshalb falsch und wird nicht gemacht.
