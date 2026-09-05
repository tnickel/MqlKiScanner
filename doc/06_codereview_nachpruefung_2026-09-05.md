# Kritische Nachprüfung der Review-Korrekturen

Stand: 05.09.2026, aktueller uncommitteter Arbeitsstand. Vorgänger: `doc/05_codereview_2026-09-05.md`.

## Auftrag für eine weitere KI

Auch diesen Bericht unabhängig kritisch prüfen. Die Befunde sind kein Auftrag zu blindem Nachbauen der vorgeschlagenen Lösungen. Nur ändern, wenn das Problem am aktuellen Code nachvollzogen und fachlich bestätigt wurde. Widerlegte, bereits behobene oder unklare Punkte mit Begründung dokumentieren. Bestehende Änderungen erhalten; Reproduktionen mit temporärer DB und gemockten externen Aufrufen durchführen.

## Ergebnis und Einordnung der beiden abgelehnten Befunde

Die ursprüngliche Kritik an der Exposure-Funktion war als unmittelbarer Verstoß gegen die technische Spezifikation zu pauschal: `doc/03_forensik-tests.md` definiert den Peak ausdrücklich als Maximum der Positionsanzahl und betrachtet das Volumen an diesem Zeitpunkt. Die Funktion darf diese Kennzahl liefern. Dieselbe Spec fragt allerdings einleitend nach der maximalen Marktposition zu einem beliebigen Zeitpunkt. Entscheidend ist der Verbraucher: Der Risiko-Score verwendet ausschließlich den Schock an diesem einzelnen Zeitpunkt als Exposure-Risikomaß. Dadurch bleiben wesentlich größere Risiken zu anderen Zeitpunkten unberücksichtigt. Die Kennzahl muss nicht ersetzt werden; eine zusätzliche Risikokennzahl kann das Problem lösen.

Für Drawdown ist der Prozentwert am absoluten Dollarmaximum ebenfalls eine definierbare Kennzahl. Er ist kein maximaler relativer Drawdown. Der neue Docstring erklärt diese Einschränkung, doch der Verbraucher verwendet den Wert weiterhin als maßgeblichen „realen Trading-DD“. Der Cent-Abgleich des Dollarmaximums verhindert nicht, zusätzlich das relative Maximum zu berechnen. Bestehende USD-Anker müssen dabei unverändert bleiben.

Damit sind beide Berechnungen unter enger Definition vertretbar, ihre Verwendung im Risiko-Score bleibt nach der Nachprüfung problematisch. Es handelt sich vor allem um fehlende beziehungsweise falsch verwendete Risikokennzahlen, nicht um einen Auftrag, die bisherigen Definitionen stillschweigend zu ändern.

## A. P1 – Absicherung gegen veraltete Forensik weiterhin unvollständig

Fundstellen: `src/mqlkiscanner/pipeline.py:123–125`, `:315–320`, `:384–387`; Zeitstempelauflösung in `src/mqlkiscanner/db.py`, `_now()`.

Reproduktion mit temporärer SQLite-DB:

1. Ein nicht ausgeschlossenes Signal mit alter Forensik, Score 3 und altem Forensik-Zeitstempel speichern.
2. Aktuelle Plattformwerte EQ-DD 5 %, Monatsertrag 10 % mocken.
3. Direkten und Browser-Export mit `RuntimeError("Keine MQL5-Credentials")` scheitern lassen.
4. `analyze_candidate()` und anschließend `results_from_db()` ausführen.

Beobachtet: Direkt weiß, keine Forensik, kein Fehler, weil fehlender Login als erlaubte Vorprüfung behandelt wird. Nach DB-Laden grün, Forensik vorhanden, kein Fehler. `forensik_stale` wird nur bei gesetztem `last_fehler` wahr; der erlaubte Vorprüfungsfall löscht diesen Marker.

Separat reproduziert: Ein echter Exportfehler bei gleichem Sekunden-Zeitstempel von Signal und alter Forensik bleibt ebenfalls grün, weil die Bedingung strikt `signal_updated > forensik_updated` verlangt. Der Fehlertext kann dann gleichzeitig mit dem grünen Urteil erscheinen.

Der neue Regressionstest setzt weit auseinanderliegende Zeitstempel und einen expliziten Fehler. Er deckt diese zwei Fälle nicht ab.

Prüf-/Lösungsrichtung: Vollständigkeitsstatus und Zugehörigkeit zu einem Scan explizit speichern; fehlenden Login nicht mit einer bestandenen Aktualisierung gleichsetzen. Alte Berichte können als historische Berichte erhalten bleiben. Nur die Vergleichsoperation des Zeitstempels zu ändern löst den Vorprüfungsfall nicht.

## B. P1 – Exposure-Score blendet größere Positionen außerhalb des Anzahl-Peaks aus

Fundstellen: `src/mqlkiscanner/forensics/exposure.py`, `run()`; eigentlicher Verbraucher `src/mqlkiscanner/scoring.py:81–86`.

Reproduktion: Zwei gleichzeitige XAUUSD-Buys mit je 0,01 Lot schließen; später einen einzelnen Buy mit 1 Lot öffnen. Referenzkontostand für die Scoreberechnung 10.000 USD. Stressbewegung gemäß Engine 50 USD.

Beobachtet: Die spezifikationsgemäße Kennzahl am Anzahl-Peak beträgt 100 USD. Zeitweise bestanden aber 5.000 USD Stressrisiko. `dimension_inputs()` erhält nur 100 USD und bewertet die Margin-Dimension mit 1,2; mit 5.000 USD wäre sie 8,0 (Skala: höher = riskanter).

Auch reine Gold-Referenzdaten bestätigen, dass die Zeitpunkte auseinanderfallen: GoldWhisper 350 USD am Anzahl-Peak gegenüber 4.000 USD maximalem Szenarioverlust, PureGold 13.300 gegenüber 17.200 USD. Die Vergleichsrechnung verwendet dieselben Kontraktfaktoren und Stressbewegungen wie die Engine.

Prüf-/Lösungsrichtung: Bisherige Peak-Anzahl-Kennzahlen erhalten; zusätzlich zeitliches Exposure-/Stressmaximum ermitteln und im Score angemessen verwenden. Für gemischte Instrumente die bereits eingeführte Berechnung je Symbol nutzen und das gemeinsame Szenario benennen. Kontobezug und Risikozähler müssen fachlich zusammenpassen.

## C. P2 – Drawdown-Score verwendet weiterhin den falschen Prozentwert für maximale relative Verluste

Fundstellen: `src/mqlkiscanner/forensics/drawdown.py`, `_max_drawdown()`; Verbraucher `src/mqlkiscanner/scoring.py:60–66`; Anzeige `src/mqlkiscanner/app_ui.py:128–129`.

Reproduktion: Start 1.000 USD, chronologische Deltas −400, +9.400, −500. Kontokurve: 1.000 → 600 → 10.000 → 9.500.

Beobachtet: Maximaler absoluter DD 500 USD; Prozentwert an diesem Zeitpunkt 5 %. Maximaler relativer DD hingegen 40 %. Ohne höheren Plattform-EQ-DD verwendet der Score 5 % und ergibt Drawdown-Dimension 3,0 statt 9,5 für 40 %.

Ein verlässlicher höherer Plattform-EQ-DD kann die Unterbewertung in manchen Fällen abfangen. Bei lokalen Analysen fehlt er; auch `eq_dd_caveat` umgeht ihn ausdrücklich. Das Problem tritt daher nicht zwingend bei jedem Signal auf, bleibt aber erreichbar.

Prüf-/Lösungsrichtung: Prozentwert am USD-Maximum und maximalen relativen DD getrennt führen. Den für das Risikourteil passenden Wert ausdrücklich auswählen und in der Oberfläche verständlich benennen. Keine USD-Referenzwerte verändern. Rekonstruierter Trading-/Balance-DD bleibt vom Equity-DD einschließlich offener Verluste zu unterscheiden.

## D. P2 – Lokaler DB-Roundtrip verliert weiterhin Monatsertrag und verändert die Ampel

Fundstelle: `src/mqlkiscanner/pipeline.py:683–687`, `analyze_local_files()` und anschließendes `results_from_db()`.

Reproduktion: Gold-Spike-MT4-Orderbuch `data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv` mit temporärer DB lokal analysieren, direktes Ergebnis mit dem DB-Ergebnis vergleichen.

Beobachtet: Direkt Monatsertrag 21,95 % und grün. Nach Laden Monatsertrag `None` und gelb. Der lokale Writer speichert im Stats-Dictionary nur Trading-DD, Winrate und Score. `ertrag_monat_pct` fehlt. `upsert_signal()` ersetzt das Stats-Dictionary, statt fehlende Werte aus einem früheren Datensatz zu bewahren.

Die ursprünglich beanstandeten Forensikfelder wie Trading-DD, Winrate und Exposure bleiben nach der Korrektur erhalten. Dieser Teil ist behoben; die vollständige Ergebnisgleichheit zwischen Sitzung und Datenbank ist es nicht.

Prüf-/Lösungsrichtung: Relevante Metadaten vollständig und mit Herkunft speichern. Prüfen, ob lokale Referenzdaten bestehende Online-Metadaten überschreiben dürfen. Ein bloßes blindes Mischen alter und neuer Werte könnte erneut das Problem aus A erzeugen.

## E. P1 – Stop-Clustering erzeugt bei Forex künstliche Stop-Signaturen

Fundstelle: `src/mqlkiscanner/forensics/stops.py`, `_distance_clustering()`, insbesondere `Counter(round(d, 1) for d in dists)`; Score-Verbraucher `src/mqlkiscanner/scoring.py:76`.

Neuer Befund, kein als behoben behaupteter Punkt des ersten Reviews.

Reproduktion: Zehn EURUSD-Buy-Verlusttrades mit Verlustdistanzen in Preiseinheiten `[0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.003, 0.005, 0.008, 0.013, 0.0199]`. Beispielsweise einheitlicher Einstieg 1,1 und jeweiliger Ausstieg `1.1 - distanz`, negative Profite und eindeutige Zeitpunkte.

Beobachtet: Sämtliche Distanzen werden auf 0,0 gerundet. Ergebnis `clustered=True`, `top_distance_share_pct=100`, „Stop-Signatur: 100% der Verlustdistanzen bei 0.0“. Tatsächlich reichen die zehn unterschiedlichen Verlustdistanzen von 1 bis 199 Pips. Der Struktur-Score vermeidet dadurch den Zuschlag für fehlendes Clustering, und der Text behauptet eine nicht durch die Daten belegte einheitliche Stop-Signatur.

Prüf-/Lösungsrichtung: Symbolgerechte Auflösung verwenden, unterschiedliche Instrumente getrennt betrachten und hinreichende Stichproben-/Clusteringkriterien definieren. Eine für Gold gewählte Rundung nicht unverändert auf FX-Preise anwenden. Ein Cluster bleibt eine statistische Signatur, kein pauschaler Beweis eines mechanischen Stops.

## Was in dieser Nachprüfung als behoben bestätigt wurde

- Ursprünglicher Punkt 3: Gegenläufige Lots verschiedener Symbole löschen den Schockwert nicht mehr gegenseitig; eine Berechnung je Symbol wurde eingeführt. Dies ist keine Bestätigung sämtlicher Kontraktfaktoren oder Währungsumrechnungen.
- Punkt 4: Erkannte Korb-Leiter bleibt auch ohne nicht überlappende Verlustnachfolger erhalten.
- Punkt 5: Teilabdeckung im Orderbuch erzeugt nicht mehr „jede Position“; fehlende Stop-Auslösungen werden im neuen Urteil unterschieden. Andere Aspekte des Stop-Nachweises sind damit nicht pauschal geprüft.
- Punkt 7: Alte KI-Texte werden nach fehlgeschlagenen neuen Aufrufen nicht mehr als neue erfolgreiche Analysen gespeichert und gezählt. Die gesamte Zählersemantik ist damit nicht als fehlerfrei bestätigt.
- Punkt 8: Die ursprünglich genannten Forensikfelder bleiben erhalten; Einschränkung siehe D.
- Punkt 9: Archivansicht bleibt trotz zuvor aktivem „Nur NEU“-Filter sichtbar. Erneut mit Streamlit-AppTest reproduziert: eine Archivzeile sichtbar, keine Exception.

## Validierung und Grenzen

`python -m pytest -q`: **38 bestanden**. `python scripts/verify_engine.py`: **83 PASS, 0 FAIL**. Die neue Pytest-Konfiguration verhindert den früheren Abbruch bei Sammlung des Referenzskripts.

Zusätzliche Gegenfälle wurden mit synthetischen Daten, temporären Datenbanken, gemockten externen Funktionen und AppTest geprüft. Keine Live-Anfragen an MQL5 oder den LLM-Anbieter. Keine produktiven Codekorrekturen in dieser Nachprüfung. Kein vollständiger Audit aller Module. Die zusätzlichen Reproduktionsskripte wurden nicht als Regressionstestdateien gespeichert; eine korrigierende KI soll passende Tests selbst erstellen und den Befund vorher unabhängig bestätigen.
