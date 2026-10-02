# Verbesserte Stop-Erkennung · 02.10.2026

## Ergebnis für Gold Spike

Gold Spike MT4 #2349227 hat im aktuellen unveränderlichen Trade-Snapshot **393/393 SL-Felder und 204 ausdrücklich mit [sl] markierte Ausführungen**. Der Scanner erkannte die direkte SL-Abdeckung bereits. Die bisherigen normalen KI-Payloads übergaben jedoch lediglich Evidenzklasse und Kurztext; ausgeführte SLs und Verlustschließungsgeschichte fehlten dort.

Zusätzlich gibt es **14 reine Nettoverlust-Mehrfachschließungen auf 11 Tagen**, alle mit vollständiger Schließung des im Export beobachteten Symbolbuchs. Diese Gruppen besitzen keine [sl]-Marker. Sie sind ein zusätzlicher beobachteter Exit-Kanal neben den direkt dokumentierten SLs. Eine feste Verlustdistanz ist dafür keine Voraussetzung.

Gold Spike MT5 #2375480 exportiert keine SL-/TP-Felder. Es enthält zwei volle negative Dreiergruppen auf zwei Tagen: **22.07.2026 −20,33 USD**, **29.07.2026 −46,37 USD**. Das ist ein begrenztes positives Indiz für Verlustschluss-Disziplin; aus diesen beiden Ereignissen allein ist weder der genaue Auslöser noch ein SL jedes Trades bewiesen. Direkte MT4-Evidenz wird nicht ungeprüft auf das eigenständige MT5-Konto übertragen.

Ein Gegenbeleg verhindert eine zu optimistische Regel: Pure Gold und gemslime besitzen ebenfalls wiederholte reine Verlustschließungen. Die Signatur zeigt damit tatsächlich begrenzende Exits, unterscheidet aber nicht kausal zwischen internem SL, Grid-Reset, manuellem Eingriff und Margin-Stop-out. Ein vollständiges kleines Symbolbuch beweist zudem keinen Schutz beim größten historischen Positionspeak.

## Implementierung

`forensics/stops.py` berechnet einen zusätzlichen strukturierten `schutzsignatur`-Befund:

- Vollständige Schließungsgruppen desselben normalisierten Symbols innerhalb **2 Sekunden ab dem ersten Close**, ohne transitive Erweiterung.
- Ein qualifizierter Verlustabschluss verlangt mindestens zwei schon vor dem ersten Close gleichzeitig offene Positionen gleicher Richtung, **jede Position netto negativ** einschließlich Kommission und Swap.
- Die komplette Gruppe wird vor der Klassifikation betrachtet. Gewinn-/Verlustverrechnung und gemischte Gegenrichtungen können nicht durch vorheriges Herausfiltern der Gewinner einen Stop-Beleg vortäuschen. Breakeven, Einzeltrades und exakte Zeilenduplikate erzeugen keine solchen Belege.
- Drei qualifizierte Ereignisse auf mindestens zwei Tagen heißen `plausibel`; ein bis zwei Ereignisse beziehungsweise nur ein Tag heißen `hinweis`; keine Ereignisse heißen `nicht_beobachtet` und bleiben neutral. Diese Schwellen sind offen gelegte **Heuristik**, keine kalibrierte Schutzwahrscheinlichkeit.
- Berechnete Ereigniszahlen, Tage, Buchabdeckung, gemischte profitable Körbe, Verlustdistanzen und höchstens fünf konkrete Beispiele werden geliefert. Buchabdeckung bezieht sich auf die im Export beobachteten Positionen; noch offene, nicht exportierte Positionen fehlen.

`ScanResult.stop_befund` führt den vollständigen Stop-Befund durch Einzelprüfung, SQLite, Reload, Laufarchiv und Forensik-JSON. Neue Berichtsbasis-Hashes umfassen diese Fakten. Legacy-Befunde ohne Feld erhalten keine erfundene Signatur und behalten das bisherige Payloadformat. Der Kurztext nennt auch [sl]-Ausführungen und die Verlustschluss-Signatur. Die neutrale Stop-Matrix zeigt einen beobachteten Exit-Hinweis lesbar an.

**Keine automatische Umklassifizierung zum bewiesenen SL, kein neuer Score-Bonus, keine Änderung von Drawdown-Schranke oder berechnetem Exposure durch diese Signatur.** Die bestehenden direkten SL-Nachweise bleiben entlastend. Ein tatsächlich positiver Grid-Abschluss kann einen anderen Mechanismus zeigen, zählt hier aber nicht als Verluststopp.

Alle fünf KI-Vorlagen und ihre eingebauten Defaults unterscheiden nun direkte Evidenz, begrenzte Hinweise und plausible Verlustschluss-Disziplin. Auch Prompt 1 erhält erstmals den vollständigen Forensik-JSON, damit die Strategieanalyse diese Zahlen nicht aus einer kuratierten Trade-Auswahl selbst schätzen muss. Alte benutzerdefinierte Trade-Vorlagen ohne den neuen Platzhalter bleiben kompatibel; der Admin-Editor zeigt den neuen unterstützten Platzhalter an.

Die Prompts verlangen:

- belegte SL-Abdeckung und SL-Ausführungen ausdrücklich berücksichtigen;
- Status und Stichprobengröße der Verlustschluss-Signatur unverändert übernehmen;
- fehlenden SL-Nachweis niemals negativ gewichten;
- niedrigen gemessenen Equity-DD inklusive Floating als stützende Historie einordnen, ohne daraus einen SL-Beweis oder eine künftige Verlustobergrenze zu machen;
- statische Exposure-Schocks als Szenario ohne dynamische SL-/Korb-Ausführung behandeln: Zahlen unverändert zitieren, keine selbst erfundene SL-Korrektur und kein sicher beobachteter ungebremster Verlust.

## Nachprüfung

**117 gezielte Offline-Tests bestanden.** Enthalten sind die drei neuen Testdateien für Synchronverlust-Signaturen, den echten CSV→Pipeline→DB→Reload→Archiv→Prompt-Pfad sowie alle fünf Vorlagen/Defaults/Builder. Dazu bestehende Engine-, Prompt- und Tiefenanalyse-Regressionen. Buy/Sell, profitable Grid-Verrechnung, Gegenrichtungen, Kosten-Netto, Zeitfenstergrenzen, Shuffle, Duplikate und unveränderte Bewertung wurden geprüft.

Eine breitere Prüfung traf zusätzlich zwei ältere Tests in `test_intensivreview_fixes.py:112` und `:121`, die ohne RetDD weiterhin Grün erwarten. Sie widersprechen der gleichzeitig außerhalb dieser SL-Arbeit umgesetzten RetDD-Mindestregel und wurden hier nicht umgeschrieben. Daraus wird keine grüne Gesamtsuite behauptet. Zwischenzeitliche Prompt/Default-Abweichungen aus parallelen RetDD-Änderungen wurden unter Erhaltung der neueren Regel synchronisiert; der abschließende Default-Sync-Test besteht.

**Abschließende Commit-Prüfung:** Die vorbereitete SL-Indexversion wurde separat ohne die parallelen RetDD-/Parser-Änderungen ausgecheckt. Dort bestanden alle **148 Tests** des erweiterten Prüfbefehls aus [handoff.md](handoff.md), einschließlich der vollständigen `test_intensivreview_fixes.py`. Die vorstehenden zwei Fehler beschreiben einen vorübergehenden gemischten Arbeitsstand, keinen verbleibenden Fehler im SL-Commit.

Die neue Erkennung wurde zusätzlich auf fünf gehashte Produktiv-Snapshots ausschließlich lesend angewandt: [implemented_detector.json](implemented_detector.json). MT4 bleibt direkt belegt mit 14 Verlustgruppen/11 Tagen; MT5 bleibt ohne direkt exportierten SL und erhält `hinweis` mit zwei Gruppen/zwei Tagen. Das aktuelle Parser-Dedup aus paralleler Arbeit reduziert den MT5-Snapshot von 133 auf 131 eindeutige Zeilen; die beiden belegten Verlustgruppen bleiben unverändert.

Keine erneute KI-Anfrage, kein neuer Scan und kein Dienstneustart wurden ausgelöst. Vorhandene Berichtstexte werden erst bei einer neuen KI-Auswertung aktualisiert. Die Tests bestätigen die gelieferten Fakten und Anweisungen; sie sind kein Beweis, dass ein Modell jede Anweisung zuverlässig befolgt.

Weitere Belege: [unabhängige CSV-Nachrechnung und Gegenfälle](close_groups_findings.md), [Audit-Skript](close_groups_audit.py), [alle Schließungsgruppen](close_groups_all.json).
