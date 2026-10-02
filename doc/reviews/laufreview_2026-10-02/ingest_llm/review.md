# Ingest und LLM-Berichtskonsistenz – Laufreview 02.10.2026

Die Produktionsdaten wurden ausschließlich mit SQLite-URI `mode=ro` in einer
Lesetransaktion gelesen. `results_from_db` wurde mit einer vorab gelesenen
Katalogliste, einem nur lesenden Analysis-Lookup und deaktivierter
PDF-Materialisierung ausgewertet. Kein `init_db`, kein Netzwerk, kein echter
LLM-Aufruf und kein MT5. Reproduktionen verwenden ausschließlich eine
In-Memory-DB, Mocks und ein temporäres Verzeichnis.

Die wiederholbare Probe ist `probe_readonly.py`; der eingefrorene Befund steht
in `snapshot.json`; die konkreten Berichtspassagen stehen zusätzlich in
`report_evidence.json` mit unveränderlichen Analysis-IDs. Der Lauf war
während der Prüfung noch aktiv. Die
Berichtszeitpunkte beschreiben deshalb diesen Snapshot und keine Aussage
über einen späteren vollständigen Lauf.

Heute sichtbar sind veraltete Tiefenanalysen neben neuen Befunden, eine
widersprüchliche Stop-Begründung im neuen Gold-Spike-MT5-Bericht und eine
durch fehlende RetDD-Werte verhinderte Empfehlung für Gold Spike MT4.
Der Quellen-Kollisionsschutz und der Offline-SHA-Abgleich haben dagegen
isoliert reproduzierte Fehlerpfade; eine entsprechende Kollision oder
Cachekorruption im heutigen Lauf wurde nicht festgestellt.

## Bestätigte Befunde

### P2 – Direkte MQL5-Persistenz umgeht den Quellen-Kollisionsschutz

`src/mqlkiscanner/pipeline.py:1355` setzt `signal_payload["quelle"]` nur bei
REST-Kandidaten. Direkte MQL5-Kandidaten erreichen `store_scan_result` ohne
Quellenargument. `src/mqlkiscanner/db.py:216` prüft den ID-Konflikt nur bei
expliziter Quelle; der Zweig ab `db.py:234` überschreibt Namen, Plattform,
Kennzahlen und weitere Kopfdaten unter dem alten Quellenlabel.

Isoliert bestätigt: vorhandene `123 / Pelican 123 / pelican / pelik`; danach
direkter MQL5-Upsert ohne Quelle; Ergebnis
`123 / Direct MQL5 123 / mt5 / pelik`. Ein expliziter MQL5-Upsert mit
`quelle="mql5"` wird dagegen korrekt abgewehrt. Die Produktionsdaten wurden
nicht verändert. Eine tatsächlich eingetretene ID-Kollision im aktuellen
Lauf ist damit nicht behauptet; bestätigt ist der funktionsfähige
Umgehungspfad. Die direkte Pipeline muss ihre Identität ebenfalls explizit
übergeben, damit der bereits vorhandene Guard wirken kann.

### P2 – Offline-Artefakte werden ohne gespeicherten SHA-Abgleich übernommen

`src/mqlkiscanner/ingest.py:158`/`:159` prüfen beim Offline-Fallback nur, ob
die Trade-Datei existiert. Die entsprechende Metrics-Route tut dies bei
`:194`/`:195` ebenfalls. Der erfolgreiche Online-Cachepfad prüft dagegen
den Dateiinhalt gegen den SHA.

Reproduktion: für ein synthetisches CSV ist der SHA des Profits `10`
gespeichert; die Datei enthält nach einer Änderung einen weiterhin gültigen
Profit `1000`. Ein gemockter Verbindungsfehler führt dazu, dass
`hole_trades` diese veränderte Datei liefert und `geändert=False` meldet.
Damit ist sie kein verifizierter letzter bekannter Stand. Eine tatsächliche
Produktiv-Cachekorruption wurde nicht festgestellt.

### P2 – Historische Tiefenanalysen bleiben ohne aktuelle Basisprüfung sichtbar

`src/mqlkiscanner/pipeline.py:370` lädt die neueste Tiefenanalyse unabhängig
von `analyses.basis`. `restore_current_reports` prüft ab `pipeline.py:777`
nur Trade-, Risiko- und Gesamtbericht. Die Detailansicht zeigt die Tiefe
ab `src/mqlkiscanner/app_ui.py:978` neben dem aktuellen Ergebnis; sie nennt
das Erstellungsdatum, kennzeichnet aber keinen Konflikt der Datenbasis.

Der Read-only-Snapshot enthält **47** weiterhin eingeblendete Tiefenanalysen
mit abweichender oder nicht mehr verfügbarer aktueller Basis. Konkrete
Signale des aktuellen 22er-Laufs:

- KiraCat #2342895: Tiefe 21.09.2026 14:22:27, Basis `c802950…`;
  aktueller Befund `3f3da3c…`.
- Gold Spike #2349227: Tiefe 21.09.2026 13:51:44, Basis `219588c…`;
  aktueller Befund `7c631c5…`.
- Gold Reaper #2265877: Tiefe 21.09.2026 13:48:34, Basis `1652389…`;
  aktueller Befund `f2df062…`.

Die Anzeige des Datums ist eine vorhandene Entlastung. Historische Texte
aufzubewahren ist sachlich richtig; sie als unverändert gültige Vollanalyse
neben einer neuen Datenbasis bereitzustellen bleibt jedoch uneindeutig.
Zusätzlich überspringt `src/mqlkiscanner/tiefen_batch.py:80` jeden vorhandenen
Text unabhängig von dessen Basis. Alte Tiefen können außerdem in den
Portfolio-PDF-Anhang übernommen werden (`pdf_reports.py:284`).

### P2 – Neuer Gold-Spike-MT5-Bericht verwendet fehlenden Stop-Nachweis als negativen Grund

Produktionsbeleg: `analyses.id=1234`, Signal #2375480, Gesamtbericht vom
02.10.2026 11:20:30. Im Abschnitt Risikoanalyse wird ein interner
Basket-/Signal-Stopp als plausibel und die Sichtbarkeit als neutral
bezeichnet. Unter den drei wichtigsten Gründen für WATCHLIST steht danach:

> Erstens die Stress-Exposure […] in Kombination mit dem Grid-Profil […]
> ohne nachweisbaren Einzelpositions-Stopp.

Dies widerspricht der bindenden Regel in
`config/prompts/gesamtbericht.md:82`: fehlender Nachweis darf nicht negativ
gewichtet werden; zulässig ist eine begründete Verhaltenseinschätzung
„wahrscheinlich ohne Stop-Schutz“. Der Bericht begründet an dieser Stelle
keinen solchen Befund, sondern nennt zuvor einen plausiblen internen Stop.
Die Engine bleibt unverändert grün; betroffen ist die Begründung des
LLM-Urteils, nicht ein nachgewiesener Ampel-/Scorefehler.

### Bestätigte Folgen fehlender RetDD-Werte: Empfehlung fehlt und Workflow-LLM rechnet Ersatzquotienten

Die fehlende produktive RetDD-Berechnung wird separat im Rechenreview
behandelt. Ihre heutige Urteilswirkung ist ausdrücklich belegt: Gold Spike
MT4 #2349227, `analyses.id=1240`, Gesamtbericht vom 02.10.2026 11:28:09,
nennt `retdd_monat = null`, `retdd_jahr = null` und
`ertrag_monat_geom_pct = null`. Der Bericht schreibt:

> Da RetDD Vorrang vor absoluter Rendite hat, ist eine EMPFEHLUNG trotz
> erfüllter Mindestschwelle (8,71 %/Monat forensisch, linear; Plattformwert
> 19,81 % nur Zusatzinformation) nicht begründbar.

Das anschließende Urteil lautet **WATCHLIST**, bei grüner Engine. Hier
handelt es sich um eine dokumentierte Abhängigkeit des heutigen
LLM-Urteils von den fehlenden Feldern, nicht um eine Vermutung darüber,
welches Urteil bei vollständigen Werten entstanden wäre.

Zusätzlich rechnen neue tatsächliche Gesamtberichte Ersatzquotienten:
Gemslime #2059368, `analyses.id=1270`, berechnet aus
1,21 %/Monat und 11,25 % DD einen Ersatzquotienten von etwa 0,11;
Master H4-2 #2039057, `analyses.id=1276`, bezeichnet 0,57/21,14 als
„Hilfsrechnung (nicht Engine-Zahl)“, Ergebnis etwa 0,027. Diese
Workflow-Berichte rechnen damit selbst, obwohl die Architektur nur
Prompt 5 dieses Verhalten erlaubt. Die Divisionen sind rechnerisch
plausibel; das Problem ist die nicht vorgesehene Berechnungsinstanz und
der Ersatz geometrischer Effizienz durch lineare Quotienten.

## Korrekt verifizierte Teile und Grenzen

- **Kein Fremdbasis-Mixing der drei normalen Berichtsteile:** Für sämtliche
  restaurierten Trade-/Risiko-/Gesamtberichte der 97 gespeicherten Signale
  passte der geladene Text zu `berichte_basis`. Die Probe fand **0**
  abweichende restaurierte Workflow-Texte. SHA/Fakten/Kriterien-Bindung und
  das Ausfiltern ungebundener Texte funktionieren in diesem Snapshot.
- **Quellen-Kapitalbasis sauber getrennt:** Die zwölf Pelican-Signale des
  aktuellen 22er-Laufs tragen `implizit_aus_balance`. Beispiel SafeGold:
  Basis 427,74 USD, tatsächliches Initial Deposit `null`, virtuelle Annahme
  separat 10.000 USD. Master H4-2 nutzt 1.587,68 USD implizit. Die virtuelle
  Annahme wurde hier nicht still als echte Einzahlung ausgewiesen.
- **Normale Synthese wartet auf beide neuen Teile:**
  `llm_runner.py:169` verhindert einen neuen Gesamtbericht, wenn Trade-
  oder Risikoaufruf beziehungsweise deren Speicherung fehlschlägt.
- **Same-Basis-Neulauf kann alte und neue Versionen sichtbar mischen:**
  isoliert bestätigt: neues Trade-Ergebnis, fehlgeschlagener Risikoaufruf,
  alter Risiko- und Gesamtbericht bleiben erhalten. Der Fehlerzähler meldet
  einen Fehler und keinen neuen Synthese-Erfolg. Dieses Verhalten ist
  bewusst durch `tests/test_review15_llm.py` abgesichert. Es ist kein
  Fremddaten-Mixing, solange die Basis identisch ist; aus bloßer Existenz
  eines Gesamtberichts darf jedoch kein erfolgreicher neuer Gesamtlauf
  abgeleitet werden.
- Ein LLM-Urteil WATCHLIST oder ABLEHNUNG bei grüner/gelber Engine ist für
  sich kein Zahlenfehler: der interpretierende Layer darf Vorbehalte
  formulieren. Der nachgewiesene Stop-Nachweis-Widerspruch oben ist
  deshalb gesondert begründet.

## Isolierte Validierung

Die wiederholbare Read-only-Probe lief erfolgreich. Die vorhandenen
Regressionstests `tests/test_review15_llm.py`,
`tests/test_review15_reports.py` und `tests/test_quellen.py` bestanden:
**63 passed in 60.87 s**. Für diesen Testprozess wurden der Kursanbieter
und der EZB-Status durch lokale Mocks deaktiviert; die Test-Fixtures
verwenden isolierte Speicherung und blockieren echte HTTP-Aufrufe. Die
Tests belegen die dort geprüften Workflow-/Basis-/Quellenpfade; sie sind
keine End-to-End-Abnahme mit einem realen Modell oder externen Quellen.

Keine Änderungen an Produktivcode, Produktionsdatenbank oder laufenden
Prozessen wurden für diese Prüfung vorgenommen.
