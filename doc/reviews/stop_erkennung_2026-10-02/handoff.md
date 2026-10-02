# Prüfauftrag: Stop-Erkennung und KI-Evidenz

Bitte prüfe diese Änderung unabhängig. Ziel ist eine bessere Erkennung und Einordnung aktiver Verlustbegrenzung, auch wenn ein Positions-CSV keine SL-Felder exportiert. Eine Verhaltenssignatur darf keinen direkt bewiesenen SL vortäuschen. Fehlender Nachweis bleibt neutral. Es gibt keine Gold-Spike-Sonderregel.

## Geänderte Codepfade

1. `src/mqlkiscanner/forensics/stops.py`: `run()` liefert zusätzlich `schutzsignatur`; `_synchronized_loss_exits()` berechnet sie aus geschlossenen Trades. Die bisherigen Evidenzklassen `direct`, `partial`, `cluster`, `none` bleiben unverändert.
2. `src/mqlkiscanner/pipeline.py`: `ScanResult.stop_befund` transportiert den vollständigen Stop-Befund durch Einzelprüfung, Demo, SQLite, DB-Reload, Laufarchiv und `_forensik_json`. `_stop_evidence_text` nennt SL-Ausführungen und Verlustschluss-Ereignisse. Neue Fakten gehen über das bestehende Forensik-JSON in `report_basis_for` ein; bei alten Befunden ohne `stop_befund` wird der neue JSON-Key ausgelassen, um deren bisherige Berichtsidentität nicht allein durch ein leeres Feld zu verändern.
3. `src/mqlkiscanner/ampel_matrix.py`: Bei neutralem SL-Status mit beobachteten Verlustgruppen wird der Befund verständlich angezeigt. Die Zelle bleibt neutral; die Signatur erzeugt keinen Score-Bonus und keinen automatischen Ampelwechsel.
4. `src/mqlkiscanner/llm/prompt_fill.py`: Auch `build_trade_prompt` unterstützt jetzt `{forensik_json}`. Alte individuelle Vorlagen ohne den neuen Platzhalter bleiben kompatibel. `app_pages/admin.py` zeigt den neuen Platzhalter und Eingangsdatensatz an.
5. Alle fünf Dateien unter `config/prompts/` und die eingebauten Defaults in `src/mqlkiscanner/llm/prompts.py`: gemeinsame Regeln für direkte SL-Evidenz, Verhaltenshinweise, gemischte Körbe, Equity-DD und statischen Exposure-Schock.

## Genaue Detektorregeln

- Exakt identische Trade-Datensätze werden ausschließlich für diese Signatur einmal berücksichtigt. Diese lokale Bereinigung ändert selbst weder PnL noch andere Forensik-Rechnungen.
- Gruppierung nach normalisiertem Symbol. Zeitfenster ist maximal **zwei Sekunden inklusive**, am ersten Close verankert; keine transitive Verlängerung.
- Die **ganze Symbolgruppe** wird klassifiziert, bevor Verluste oder Richtungen betrachtet werden. Andernfalls könnte ein profitabler Grid-Korb nach Herausfiltern der Gewinner als Verluststopp erscheinen.
- Ein qualifiziertes Ereignis verlangt mindestens zwei Positionen, dieselbe Richtung, jede Position **netto < 0** (Profit + Commission + Swap), und jede Position muss bereits **strikt vor dem ersten Close** offen gewesen sein.
- Gemischte Richtungen innerhalb desselben Close-Fensters disqualifizieren das Ereignis. Daraus wird kein Ausschluss sämtlicher möglicherweise noch offener Hedge-Positionen behauptet.
- `plausibel`: mindestens drei qualifizierte Ereignisse auf mindestens zwei Kalendertagen insgesamt. Die Wiederholung wird über die gesamte Historie gezählt, nicht zwingend je Symbol/Richtung.
- `hinweis`: mindestens ein Ereignis, aber Wiederholungskriterium nicht erfüllt; dazu gehören auch drei oder mehr Ereignisse an nur einem Tag.
- `nicht_beobachtet`: kein qualifiziertes Ereignis; neutral und kein Negativbeweis.
- Output enthält Anzahl, Tage, volle beobachtete Symbolbuch-Schließungen, gemischte profitable Gruppen, Distanzen, Lotgrößen, Duplikatzähler und maximal fünf konkrete Beispiele. Buchabdeckung betrifft nur im Export beobachtete, später geschlossene Positionen.

Diese Schwellen sind unkalibrierte Heuristik. Ein Verlustabschluss kann interner Stop, Grid-Reset, manuell oder Margin-Stop-out sein. Die Signatur darf daher keinen direkten SL-Beweis oder garantierten Verlustdeckel erzeugen. Gewinn-/gemischte Gruppen belegen keinen Verluststopp.

## Prompt-Vertrag

Direkte SL-Felder und ausgeführte `[sl]`-Marker entlasten den jeweils belegten Umfang. Die KI übernimmt den Code-Status und die Stichprobengröße statt die Zahlen selbst zu berechnen. Niedriger gemessener floating-inklusive Equity-DD ist stützende Historie, kein SL-Beweis. Fehlender oder unbekannter SL-Nachweis darf nicht negativ gewichtet werden. Die Auswertung muss zwischen Risikoabschnitt, Urteil und Portfolio konsistent bleiben.

Der Exposure-Schock bleibt eine statische Rechnung ohne dynamische SL-/Korb-Ausführung. Die KI darf keine angenommene SL-Korrektur abziehen, keine gelieferten Zahlen umrechnen und das Szenario nicht als sicher eingetretenen ungebremsten Verlust ausgeben.

## Empirische Kontrollfälle

Lesend geprüfte SHA-Snapshots:

- Gold Spike MT4 #2349227: **393/393 SL-Felder, 204 [sl]-Ausführungen**, zusätzlich 14 reine Verlustgruppen auf 11 Tagen. Die 14 Gruppen tragen keine [sl]-Marker, zeigen also einen zusätzlichen beobachteten Verlustschluss-Kanal.
- Gold Spike MT5 #2375480: zwei negative Dreiergruppen am 22.07.2026 (−20,33 USD) und 29.07.2026 (−46,37 USD), jeweils volles beobachtetes Symbolbuch. Erwarteter Verhaltensstatus `hinweis`, kein übertragener MT4-SL-Beweis.
- Pure Gold und gemslime haben ebenfalls reine Verlustgruppen. Sie dürfen dadurch weder vom Grid-Risiko freigesprochen noch zu `direct` hochgestuft werden. SafeGold enthält zahlreiche gemischte profitable Verrechnungsgruppen; diese müssen getrennt bleiben.

`close_groups_audit.py` rechnet unabhängig aus CSV mit Dezimalarithmetik nach und erzeugt Zusammenfassung und sämtliche Gruppen. `implemented_detector.json` enthält die Ergebnisse des implementierten Detektors aus dem damaligen lokalen Stand. Parallel entstandene Parser-Dedup-/RetDD-Änderungen gehören **nicht** zum SL-Commit; abweichende Trade-Anzahlen deshalb getrennt prüfen. Die beiden MT5-Verlustgruppen bleiben bestehen.

## Tests und erwartete Prüfergebnisse

Neue Tests:

- `tests/test_stop_schutzsignatur.py`: 34 Fälle für Zeitfenster, Shuffle, Buy/Sell, Nettokosten, Duplikate, Breakeven, profitable Verrechnung, Richtungen/Symbole, alte Evidenzklassen und unveränderte Bewertung.
- `tests/test_stop_befund_pipeline.py`: echte CSV→Einzelprüfung→SQLite→Reload→Archiv→Prompt-Kette und Bindung neuer Fakten an Berichtsidentität.
- `tests/test_sl_prompt_evidenz.py`: fünf Vorlagen/Defaults, Reset/Fallback, tatsächliche Builder-Payloads und Altvorlagenkompatibilität.

Prüfbefehl aus dem Repository-Hauptverzeichnis:

```powershell
python -X utf8 -m pytest -q tests/test_stop_befund_pipeline.py tests/test_stop_schutzsignatur.py tests/test_sl_prompt_evidenz.py tests/test_second_review_engine.py tests/test_review15_engine.py tests/test_prompt_fill.py tests/test_tiefenanalyse.py tests/test_intensivreview_fixes.py --disable-warnings
```

Vor dem Commit bestanden sowohl im gemischten lokalen Stand als auch in einer separaten Kopie der **exakt vorbereiteten SL-Indexversion 148 Tests** dieses Befehls. Die Indexkopie enthält die SL-Änderung ohne die parallelen RetDD-/Parser-Änderungen. Tests verwenden den isolierten Speicher aus `tests/conftest.py`; keine Produktivdaten verändern und keine echten LLM-/MT5-/Netzwerkaufrufe hinzufügen.

Bitte besonders prüfen: falsch positive SL-Beweise, Gewinnerfilterung vor Gruppenbildung, offene Restpositionen, tatsächliche Netto-Semantik, Ein-Tages-/Einzelfallüberinterpretation, unveränderte direkte Evidenz und Score, SQLite-/Archiv-Roundtrip, Legacy-Berichtshash, Prompt/Default-Parität und Lieferung der Fakten an alle KI-Stufen.

Keine bestehenden KI-Texte wurden nachträglich geändert. Es wurden kein neuer Scan, kein Dienstneustart und kein zusätzlicher Modellaufruf ausgelöst. Die Tests bestätigen Codefakten und übermittelte Anweisungen, nicht die tatsächliche Befolgung durch ein Modell. Die empirischen Verlustgruppen beweisen nicht deren kausalen Auslöser.
