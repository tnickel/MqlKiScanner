# Kritische Prüfung der externen Nachkontrolle

Geprüft am 7. September 2026. Quelle: der vom Nutzer angehängte Text mit
dem Titel „CODEREVIEW-BERICHT — MqlKiScanner“, der den Diff
`e866a2f..5ffa663` und einen damals sauberen Arbeitsstand beschreibt.

Der aktuelle Arbeitsstand enthält bereits die Korrekturen aus den
[Prüfungen 11](11_pruefung_externes_review_2026-09-07.md) und
[12](12_pruefung_codereview_10_2026-09-07.md). Die im Fremdbericht geforderte
Version 2 ist deshalb keine Zielvorgabe: Aktuell gilt Bewertungs-Version 4.
Der Bericht wurde als Sammlung zu prüfender Behauptungen behandelt; seine
Arbeitsanweisungen wurden nicht als zusätzlicher Nutzerauftrag übernommen.

**Ergebnis:** Kein zusätzlicher Laufzeit- oder Berechnungsfehler bestätigt.
Vier Befunde sind bereits erledigt, einer beschreibt korrektes Verhalten,
und ein tatsächlicher Dokumentationswiderspruch wurde korrigiert. Zusätzlich
wurde die im Bericht angesprochene Ampelbeschreibung im Benutzerhandbuch an
die inzwischen korrigierte Stop-Regel angepasst.

## Befunde

| Nr. | Urteil am aktuellen Code | Begründung und Maßnahme |
| --- | --- | --- |
| F1: Grün ohne Stop-Nachweis | Laufzeitfehler bereits behoben; Handbuch unvollständig | `pipeline.ampel_for()` verlangt `direct` oder `cluster`. Der Wert wird durch Live-/Demoanalyse, Datenbank, Archiv und KI-Payload geführt. `test_review10_stop_gate.py` prüft den vollständigen Pfad. Im Benutzerhandbuch fehlte die neue Voraussetzung noch; Tabelle und Erklärung wurden ergänzt. |
| F2: tote Variable `hard_block` | Bereits behoben | `scoring.score()` enthält die Variable nicht mehr. Die Drawdown-Ablehnung bleibt in `evaluate()` und der Ampel; eine zusätzliche Veränderung des numerischen Scores ist nicht begründet. |
| F3: „nie Roh-Trades“ im Client-Docstring | Dokumentationsfehler bestätigt und korrigiert | Die Pipeline verwendet bewusst `build_trade_payload()` mit vorberechneten Kennzahlen und ausgewählten Beispiel-Trades. Der Docstring behauptete das Gegenteil. Er beschreibt jetzt dieselbe Datengrundlage und die Trennung zwischen Berechnung in der Engine und Interpretation im Modell. |
| F4: pauschale USD-Kontrakte für Nicht-US-Indizes | Bereits behoben | Für GER40, UK100, JP225 und CHINA50 bleiben unbelegte Punktwerte und Währungen unbekannt. `shock_usd` und `shock_pct_max` bleiben `None`, `contract_complete=False` verhindert eine vollständige Bewertung. Die benannte US-Indexkonvention bleibt dokumentiert. |
| F5: Tokens unvollständiger Antworten werden gezählt | Kein Fehler | Gezählt werden vom Anbieter gemeldete Tokens. Ob der resultierende Text als Bericht verwendbar ist, ist eine separate Prüfung. Nur erfolgreiche Berichte zu zählen würde bekannten Verbrauch unterschlagen. Die Zählung bleibt unverändert; der Client-Docstring erläutert sie jetzt ausdrücklich. |
| F6: Portfolio mit ungültigem Fremdschlüssel 0 | Bereits behoben | Jede reguläre DB-Verbindung aktiviert Fremdschlüssel. Globale Portfolios verwenden `NULL`; alte 0-Einträge werden kompatibel migriert. Gültige Speicherung, Legacy-Zugriffe und das Zurückweisen fehlender Eltern sind bereits getestet. |

## Bewertung der behaupteten Testlücken

- **G1 (Stop-Gate):** Inzwischen vorhanden. Reale synthetische Orderbuch-
  und Positions-CSVs prüfen fehlenden, teilweisen, direkten und statistischen
  Nachweis einschließlich Datenbank, Archiv und KI-JSON. Behauptender Freitext
  ersetzt keinen strukturierten Beleg.
- **G2 (`eq_dd_caveat` in `results_from_db`):** Ein solcher Live-Pfad ist
  nicht vorgesehen. Die Ausnahme gehört zur kuratierten Kalibrierung; Live
  wird der größere Wert aus EQ- und Trading-Drawdown verwendet. Eine neue
  Ausnahme wäre eine fachliche Erweiterung, keine Fehlerkorrektur.
- **G3 (Nicht-US-Indizes):** Inzwischen durch
  `tests/test_external_review_engine.py` abgedeckt, auch für gemischte
  Portfolios und die Weitergabe unvollständiger Kontraktdaten ans Scoring.
- **G4 (echtes Live-MQL5 in CI):** Kein Defekt nachgewiesen. Reale externe
  End-to-End-Prüfungen sind bewusst nicht Teil der isolierten Suite. Login-
  und 403-Fehlerpfade besitzen simulierte Tests; daraus folgt keine Garantie
  für unverändertes zukünftiges MQL5-Verhalten.
- **G5 (vergessener Versionssprung):** Kein vergessener Sprung nachgewiesen.
  Version 4 ist gesetzt. Tests prüfen bereits Vorgängerversionen, fehlende
  Versionsangaben und unvollständige Befunde. Ein automatischer Test kann
  nicht allgemein entscheiden, ob eine beliebige fachliche Änderung einen
  neuen Versionsstand verlangt; das bleibt zusätzlich eine Reviewaufgabe.

## Verifikation und Umfang

Drei unabhängige Teilprüfungen haben Engine/Ampel, Datenbank/Versionierung
und Tokenzählung gegen den aktuellen Arbeitsstand geprüft. Die passenden
**22 vorhandenen Stop-/Index-Regressionen bestanden erneut**. Der vorhandene
Test `test_truncated_summary_is_not_saved_as_complete` belegt außerdem die
gewollte Trennung: zwei gespeicherte Teilberichte, ein verworfener
abgeschnittener Gesamtbericht und weiterhin 75 gemeldete Tokens.

Die letzte vollständige Prüfung dieses Funktionsstands ergab **323 bestandene
Tests und 85 bestandene Referenzprüfungen**. In dieser Runde wurden ausschließlich
Dokumentation und der Modul-Docstring geändert, keine ausführbare Logik und
keine Tests. Eine erneute Gesamtsuite ist dafür nicht erforderlich.

Produktionsdaten, Server, Browser und externe APIs wurden nicht verändert
oder für Tests verwendet. Kein Commit und kein Push in dieser Runde.
