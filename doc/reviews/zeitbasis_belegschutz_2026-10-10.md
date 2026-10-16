# Allgemeiner Zeitbasis-Belegschutz, 10.10.2026

Die vollständige Bestandsprüfung umfasst alle Quellen und gespeicherten Studien, nicht nur die 194 Workflow-Signale. Der erste SQLite-Lesesnapshot enthielt 1.263 Studien: 595 verlässlich, 362 primär mit Kurs-/Kontraktlücken, 146 mit offenen Positionen über unbelegten Zeitwechseln, 17 nichtmonoton, 34 mit anderen Zeitbasisfehlern, 34 mit unbestimmtem/mehrdeutigem Auto-GMT und 75 mit anderen Abdeckungsproblemen. Während dieser Prüfung führt der Hauptprozess weitere Broker-Messungen durch; spätere Zählungen sind daher andere Bestandsstände. Gespeicherte Studien sind außerdem nicht automatisch aktuell gültige Tabellenmessungen (Export-SHA und aktuelle Messregeln zählen).

## Änderung 1: bekannter Shift braucht eine Widerlegung für einen Modellwechsel

Ein neuer Wochengewinner allein belegt keinen Zeitwechsel. Trifft der bereits unabhängig bekannte Shift weiterhin mindestens 90 % der lokalen unabhängigen Preisereignisse, wird er beibehalten. Dies verwendet die bestehende lokale Mindestquote; sie wird nicht gesenkt. Ein neuer Shift wird weiterhin nur bei mindestens drei Ereignissen, eindeutigem Gewinner und mindestens 90 % Treffern übernommen, wenn der bekannte Shift diese Kompatibilität verliert. Ohne bekannte Basis ist dieser Beibehaltungsbeleg nicht zulässig. Dünne Anfangsabschnitte ohne globalen oder lokalen Beleg werden nicht als bekannt ausgegeben.

Alle einzelnen Ereignisse werden danach gegen ihre gewählte Referenzbar geprüft. Nichttreffer bleiben Trade-/Stundenlücken; weit abweichende Preise bleiben harte Zeitbasisfehler. Echte Wechsel mit offenen Positionen über unbelegter Grenze bleiben gesperrt. Die ungerundete 95-%-Abdeckungsregel, FX-/Kontraktprüfung und Drawdown-Grenzen bleiben unverändert. Es fließen keine DD-, Rendite- oder RetDD-Werte in die Offsetauswahl ein.

Metadaten je Kalenderabschnitt nennen den bekannten Shift samt eigener Trefferquote, die lokalen Gewinner und den Status `bekannter_shift_weiter_preiskompatibel`; die Gesamtmetadaten beschreiben die Belegregel. Dies ist ein Preis-Kompatibilitätsbeleg, kein unabhängig bestätigter DST-Zeitpunkt.

## Änderung 2: tatsächliche Preisbelege bei gescheiterter Stichprobe nachprüfen

Auto-GMT verwendet zuerst wie bisher bis zu 60 gleichmäßig ausgewählte Trades. Bei Gleichstand mehrerer bester Offsets oder einer Quote unter 60 % werden sämtliche verfügbaren unabhängigen Open-/Close-Preisereignisse nachgeprüft. Ein eindeutiger bester Shift und die bestehende 60-%-Mindestquote bleiben erforderlich. Ein tatsächliches Plateau bleibt unbekannt; es gibt keinen Tie-Break zum kleinsten Offset. Metadaten nennen die tatsächlich verwendete Trade-/Ereigniszahl und `vollpruefung_nach_stichprobe`.

## Offline-Gegenprüfung realer Brokerdaten

`zeitbasis_belegschutz_2026-10-10.json` enthält 17 Vorher-/Nachher-Beobachtungen aus echten CSVs und gespeicherten Vantage-, ActivTrades- und Tickmill-Bars, CSV-SHA, Cache-Pfade und konkrete beibehaltene Abschnitte. Es gab keine Live-MT5-Aufrufe und keine Produktions-DB-Schreibzugriffe durch diese Prüfung.

- Rebounds #538344: Vantage zuvor 80, ActivTrades 62 offene Modellwechsel und eine nichtmonotone Zuordnung. Der weiterhin kompatible bekannte Shift verhindert diese künstlichen Wechsel. Einzelereignisse bleiben unsicher; eine zuverlässige Gesamtmessung muss zusätzlich die unveränderte Abdeckung erfüllen.
- TRADE EASY 4YOU 2 #954691: Auf Vantage werden schwache Modellwechsel vermieden, dafür bleiben mehr abweichende Einzelereignisse als Messlücken sichtbar. Die Regel erzwingt keine Messfreigabe.
- PHOENIX #998837: Belegte lokale Wechsel bleiben erhalten.
- the best one #1096166: echte widersprochene Wechsel und extreme BYND-Preisabweichungen bleiben gesperrt.
- Rohan #178177: die 56 offenen Wechselannahmen auf Vantage bleiben bestehen.
- #213166, Tickmill: sechs schwache Modellwechsel werden vermieden; 60 unsichere Einzelereignisse bleiben. #401041: drei schwache Modellwechsel werden vermieden, zehn offene echte Wechsel bleiben eine Sperre.
- #1378066 (40 Trades), #1535524 (11) und #1536627 (5), Tickmill: Auto-GMT hat bereits alle Trades benutzt; die echten Plateaus bleiben unbekannt. Der Vollproben-Fallback erfindet hier keinen zusätzlichen Beleg.

## Regressionen und Grenzen

Synthetische Regressionen prüfen breiten Bar-Spielraum mit nur einer zusätzlich passenden Probe, fehlende bekannte Basis, echte widersprochene Wechsel, harte Ausreißer und weiterhin gesperrte offene Grenzen. Separate Tests zeigen eine von der Stichprobe ausgelassene diskriminierende Probe, einen unverändert unbekannten echten Gleichstand, unzureichende Vollbelege und den unveränderten schnellen Pfad bei eindeutiger Stichprobe.

Die Prüfung verbessert die Verwendung vorhandener Preisbelege. Sie ergänzt keine fehlenden Kurse, löst keine Split-/Preismaßstabkonflikte und beweist keine Intrabar-Extrema oder aktuell offene Positionen außerhalb des Exports. H1-Bar-Bänder können die tatsächliche Zeitzone weiterhin mehrdeutig lassen.
