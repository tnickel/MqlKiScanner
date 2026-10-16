# Vantage: Prüfung der Tabellenzellen vom 10.10.2026

Fortsetzung nach diesen Snapshots: [Broker-Kursvergleich mit Tickmill, ActivTrades und Vantage](broker_kursluecken_2026-10-10.md). Die dort dokumentierten Nachmessungen beheben unter anderem die zuvor beschriebenen BCH-/CNH-Umrechnungslücken und liefern eine verlässliche ActivTrades-Messung für PHOENIXMYTHFUNDS.

Geprüft wurden alle 16 Vantage-Signale im Workflow und sechs Kennzahlenspalten: **96 eindeutige Zellen**. Für den Zellenvergleich wurde die Produktionsdatenbank ausschließlich lesend geöffnet; die Audit-Abfragen liefen auf einem Snapshot im Arbeitsspeicher. Die anschließend separat ausgeführte Nachmessung hat ausgewählte Studien tatsächlich in der Datenbank aktualisiert (`action: study_updated` im Nachmessungsprotokoll). Die ursprünglichen Studien wurden vorher unter `tmp/vantage_studien_vor_20261010.json` gesichert. Vollständige Werte und Einzelnachweise stehen in [vantage_zellen_2026-10-10.json](vantage_zellen_2026-10-10.json).

**Snapshot 1:** 37 sichtbar korrigierte Zellen gegenüber Git HEAD; zusätzlich 20 Änderungen ausschließlich an interner Präzision, die nicht zu den 37 zählen. Ursachen waren ein `None`-Wert, den `setdefault()` nicht ersetzte, ein fehlender Tabellen-Fallback für virtuellen Monats-RetDD und fehlende Vorbehalt-Marker bei unzuverlässigen Studien. Zwei sichtbar falsche Calmarwerte beruhten auf einem vorgerundeten DD-Nenner.

**Snapshot 2 – nach erster Nachmessung:** GoldBitGrid erreicht 95,6 % Kursabdeckung und einen verlässlichen H1-Equity-DD von 50,31100155 % beziehungsweise 5.031,10 USD **auf der virtuellen 10.000-USD-Annahme**, nicht auf einer nachgewiesenen echten Kontobasis. Dadurch wurden zusätzlich **drei zuvor leere numerische Zellen innerhalb der 96** geschlossen: True-DD %, TrueRetDD und RetDD/Monat. Außerhalb dieser 96 wurde außerdem True-DD USD gefüllt. Zwei bisher als Datenblocker geführte leere ≈-Zellen sind nun korrekt leer, weil die Messung verlässlich ist. Die nachfolgenden Symbolkorrekturen und die finale Nachmessung sind in Snapshot 3 dokumentiert.

Die ursprünglichen 37 Codekorrekturen und die drei später geschlossenen Lücken sind getrennt dokumentiert. Snapshot 2 unterschied sich in 38 Zellen sichtbar von HEAD; dieser Vergleich ist kein kumulativer Fehlerzähler. Manche erneuerten DD-Nenner runden jetzt wieder auf denselben Anzeigewert wie HEAD.

**Snapshot 3 – finale Nachmessung nach Symbolfix:** Das verbundene portable Terminal liefert jetzt die belegten Symbole einschließlich 63 FX-Symbolen mit Plus-Suffix und zehn FT-Aliasen; die Kandidatenauswahl erhält unterschiedliche Groß-/Kleinschreibungen. HarbourFXPrime steigt von 22,1 % auf **96,0 % Kursabdeckung** und ist nun verlässlich gemessen: **115,4366765 % DD / 39.761,78 USD auf virtueller 10.000-USD-Basis**. GoldBitGrid bleibt bei **95,6 % Deckung und 50,31100155 % DD / 5.031,10 USD**, ebenfalls auf virtueller Basis. HarbourFXPrime hatte bereits Zahlen; deren Messqualität ist jetzt belegt, und zwei Vorbehalt-Marker entfallen. Es wurden in Snapshot 3 keine weiteren zuvor leeren numerischen Zellen innerhalb der 96 gefüllt.

TRADE EASY steigt von 31,5 % auf **94,5 % Deckung**, bleibt unter der 95-%-Schwelle und hat zusätzlich eine unbelegte Zeitachse. Rohan steigt von 18,1 % auf **50,2 %**, bleibt wegen historischer FX-Umrechnung und Zeitabbildung unzuverlässig. BCH/CNH-Umrechnung, uneindeutige Zeitwechsel und die EUR-/HKD-Exportgrenzen bleiben konkrete Datenblocker. Diese werden nicht durch erfundene Werte ersetzt. Aktuell unterscheiden sich 36 Zellen sichtbar von HEAD; die 37 ursprünglichen Codekorrekturen und die drei später geschlossenen Lücken bleiben als frühere Belege erhalten.

Verbleibende Blocker dürfen nicht durch Zahlen ersetzt werden: WanChaiTrendFX und Master Hong haben wegen EUR-/HKD-Exportfehlern keine Trade-Datei. Rohan und FOMOx99 haben auf der virtuellen 10.000-USD-Basis negatives Endkapital; geometrische Rendite und davon abhängiger Calmar sind nicht definiert. Andere Studien scheitern an Kurslücken oder uneindeutiger Zeitabbildung. Historische Forensikfehler beweisen nicht, dass betreffende Kontraktspezifikationen heute noch fehlen.

Die folgende Tabelle dokumentiert 40 konkrete, eindeutige (ID,Spalte)-Fälle: 37 ursprüngliche sichtbare Korrekturen und drei zusätzliche Schließungen. Snapshot 1-Werte bleiben auch dann als ursprünglicher Nachweis erhalten, wenn Snapshot 2 eine weitere Messwertänderung enthält.

| ID · Name | Spalte | Fehler / vorher | Ursache | Korrektur / Zustand | Finale Anzeige / Snapshot 3 |
|---|---|---|---|---|---|
| 1286742 · DINO Scalping | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 26,46 | 26,46 |
| 1286742 · DINO Scalping | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 1,30 | 1,30 · verlässlich |
| 1096166 · the best one | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 0,92 | 0,92 |
| 1096166 · the best one | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 2,61 | 5,12 · Vorbehalt |
| 1096166 · the best one | TrueRetDD | 33,07 | Calmar verwendete vorgerundeten DD-Nenner | Snapshot 1: 32,90 | 64,68 · Vorbehalt |
| 1096166 · the best one | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 0,35 | 0,18 |
| 1096166 · the best one | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 32,90 | 64,68 |
| 954691 · TRADE EASY 4YOU 2 | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 2,18 | 2,18 |
| 954691 · TRADE EASY 4YOU 2 | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,22 | 0,13 · Vorbehalt |
| 954691 · TRADE EASY 4YOU 2 | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 9,93 | 16,76 |
| 954691 · TRADE EASY 4YOU 2 | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 2,98 | 1,77 |
| 964411 · PHOENIXMYTHFUNDS | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 0,50 | 0,50 |
| 964411 · PHOENIXMYTHFUNDS | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,06 | 0,06 · Vorbehalt |
| 964411 · PHOENIXMYTHFUNDS | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 8,23 | 8,21 |
| 964411 · PHOENIXMYTHFUNDS | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 0,75 | 0,76 |
| 538344 · Rebounds | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 0,43 | 0,43 |
| 178177 · Rohan Gupta 40000121 | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 139,23 | 129,95 |
| 1024672 · GoldBitGrid | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 0,12 | 0,12 |
| 805275 · LaoLong Forex | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: -2,37 | -2,37 |
| 805275 · LaoLong Forex | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: -0,01 | -0,01 · verlässlich |
| 1121200 · HarbourFXPrime | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 43,85 | 43,85 |
| 1121200 · HarbourFXPrime | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,46 | 0,38 · verlässlich |
| 1121200 · HarbourFXPrime | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 95,00 | leer |
| 1121200 · HarbourFXPrime | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 81,58 | leer |
| 1010186 · Lenore | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 106,92 | 106,92 |
| 1010186 · Lenore | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 10,05 | 10,05 · verlässlich |
| 1010186 · Lenore | TrueRetDD | 57889,78 | Calmar verwendete vorgerundeten DD-Nenner | Snapshot 1: 57890,97 | 57890,97 · verlässlich |
| 762414 · SHC Team V1 | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 0,19 | 0,19 |
| 762414 · SHC Team V1 | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,00 | 0,00 · verlässlich |
| 998837 · Bet with Akedang | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 8,23 | 8,23 |
| 998837 · Bet with Akedang | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,03 | 0,03 · Vorbehalt |
| 998837 · Bet with Akedang | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 249,77 | 249,77 |
| 998837 · Bet with Akedang | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 0,63 | 0,63 |
| 1052261 · Bullions | Geom. %/M | leer | Vorhandenes None blockierte 10k-Fallback | Snapshot 1: 1,50 | 1,50 |
| 1052261 · Bullions | RetDD/Monat | leer | Virtueller Monatswert fehlte im Tabellenmapping | Snapshot 1: 0,35 | 0,35 · Vorbehalt |
| 1052261 · Bullions | True-DD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 4,31 | 4,31 |
| 1052261 · Bullions | TrueRetDD ≈ | leer | Unzuverlässige Studie wurde ohne Vorbehalt angezeigt | Snapshot 1: 4,55 | 4,55 |
| 1024672 · GoldBitGrid | RetDD/Monat | Snapshot 1: leer | Historische Kurslücke; neue Studie erreicht 95,6 % Deckung | Snapshot 2: 0,00, virtuell 10k / verlässlich | 0,00 · verlässlich |
| 1024672 · GoldBitGrid | True-DD % | Snapshot 1: leer | Historische Kurslücke; neue Studie erreicht 95,6 % Deckung | Snapshot 2: 50,31, virtuell 10k / verlässlich | 50,31 · verlässlich |
| 1024672 · GoldBitGrid | TrueRetDD | Snapshot 1: leer | Historische Kurslücke; neue Studie erreicht 95,6 % Deckung | Snapshot 2: 0,03, virtuell 10k / verlässlich | 0,03 · verlässlich |

Alle Prozent- und RetDD-Zahlen virtueller Studien beruhen auf einer 10.000-USD-Annahme. Sie sind keine nachgewiesene echte Kontorendite und fließen nicht als virtuelle Anzeige in die Workflow-Ampel ein.
