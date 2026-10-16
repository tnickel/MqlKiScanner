# Öffentliche synthetische Parser-Fixtures

Diese Dateien wurden vollständig synthetisch erstellt. Sie sind keine gekürzten,
kopierten oder anonymisierten Auszüge privater Trades. Namen, Zeitpunkte und
Zahlen beschreiben keine Anbieterhistorie. Sie belegen ausschließlich das
unterstützte CSV-Format, keine Plattformfrische, Kontraktgröße oder Währung.

`mt4_export_artifacts.csv` kombiniert das 13-Spalten-Orderbuch mit sechs
geschlossenen Trades, neun Kontobewegungen (Balance/Correction), zwei
separaten Kostenbuchungen, einer Pendingorder, leeren/zeitstempel-/kommentar-
getragenen Spacerzeilen und einem `profit`-Footer ohne Preise.

Unabhängige Sollwerte: Trade-Brutto 65,74; Trade-Kommission -4,10; Trade-Swap
-0,72; Trade-Netto 60,92; Kontobewegungen zusammen 1.090; separate Kosten -3.
Der Footer wiederholt die Trade-Summen und darf nicht erneut eingehen.

`mt5_export_artifacts.csv` verwendet elf Positionsspalten. Zwei geschlossene
Trades ergeben Brutto 30 und Netto 28,60; Einzahlung 2.000, separate Kosten -3.
Eine reine Zeitstempelzeile und der `SUMMARY`-Footer sind keine Trades.

Die Tests übergeben die versionierten Pfade als PathLike und als String,
prüfen eine BOM-Variante und beschädigen ausschließlich temporäre Kopien.
Ein zusätzlicher Großmengenfall vervielfacht nur die synthetischen Tradezeilen:
Ohne Positions-ID/Plattformbeleg müssen alle 2.520 Zeilen erhalten bleiben.
Damit hängt diese strukturelle Regression nicht an einem privaten Live-Cache
oder einer anwachsenden realen Tradezahl.
