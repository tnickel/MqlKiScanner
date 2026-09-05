"""Contextual explanations grounded in the local analysis engine."""

HELP_CONTENT = {
    "workspace": ("So arbeitest du mit dem Scanner", """
**1 · Vorbereiten.** Unter Einstellungen hinterlegst du MQL5-Zugang und optional einen KI-Key. Auf der Scan-Seite legst du Umfang und Vorfilter fest. Die lokalen Verifikationsdaten funktionieren ohne Netzwerk.

**2 · Ablauf verfolgen.** Der Scanner liest Listen, wählt Kandidaten aus, lädt Daten und führt die Forensik durch. Optional folgen drei KI-Analysen. Die Statusanzeige benennt laufende, folgende und ausgelassene Schritte. Ein abgeschlossener Abruf ist noch kein positives Urteil über ein Signal.

**3 · Ergebnisse prüfen.** Filtere die Tabelle, wähle eine Zeile und prüfe zuerst Drawdown, Exposure und Stop-Nachweis. Die KI erläutert die Befunde; die Zahlen berechnet die Engine.

**Gelbes i.** Öffnet Erklärungen zur benachbarten Aktion oder zum Bereich. Schließe das Fenster über „Verstanden“, das Kreuz oder Escape.
"""),
    "connections": ("Zugänge und Bereitschaft", """
**MQL5** benötigt Benutzername und Passwort für authentifizierte Trade-Exporte. Sind beide hinterlegt, ist der Zugang konfiguriert, aber noch nicht als gültig getestet. Ein abgelaufener Login kann beim Export weiterhin scheitern.

**KI** benötigt einen GLM-Key und einen passenden Endpunkt. „Hinterlegt“ bestätigt nur das Vorhandensein des Keys, weder Guthaben noch Modellverfügbarkeit. Die Verbindung lässt sich in den Einstellungen testen.

**Ohne Zugänge** kannst du lokale Verifikationsdaten auswerten. Ohne KI-Key bleiben berechnete Befunde verfügbar; es entstehen keine KI-Berichte.
"""),
    "results_runs": ("Aktueller Lauf und gespeicherte Ergebnisse", """
**Aktuelle Sitzung** zeigt die zuletzt in dieser Sitzung erzeugten Ergebnisse. Ein gespeicherter Lauf zeigt seinen damaligen Datenstand. Der Wechsel startet keinen Abruf und keine neue Analyse.

**Datenstand beachten.** Archivierte Kennzahlen sind historische Momentaufnahmen. Der Dateiname bezeichnet den Lauf, nicht zwingend das Datum der zugrunde liegenden Trades. Die Auswahl eines Archivs überschreibt die aktuelle Sitzung nicht.

**CSV herunterladen** exportiert genau die aktuell gefilterten Tabellenzeilen. Ausführliche KI-Texte liest du über „Bericht“ oder in der Signal-Detailansicht.
"""),
    "results_filter": ("Ergebnisse suchen und filtern", """
Die Textsuche findet Signalnamen oder IDs. Im Statusfilter sind mehrere Einstufungen wählbar; ohne Auswahl sind alle sichtbar. Suche und Statusfilter gelten gemeinsam für Tabelle, Export und Urteile.

**Eine Zeile auswählen** öffnet darunter die Details. „Bericht“ zeigt den vorhandenen Gesamtbericht. Diese Aktionen starten keine Analyse.

**Kompakt** konzentriert sich auf Risiko, Stop-Nachweis und Urteil. „Alle Kennzahlen“ ergänzt Handelsstatistik, Volumen und Plattformdaten. Eine leere Zelle bedeutet fehlende Daten, nicht null Risiko.
"""),
    "risk_status": ("Was die Einstufungen aussagen", """
**Grün · Kandidat:** Die aktuelle Engine findet Forensikdaten, einen Risiko-Score unter 5 und ausreichenden monatlichen Ertrag. Das ist ein Prüfkandidat, keine Garantie. Prüfe den Stop-Nachweis separat.

**Gelb · Beobachtung:** Forensik ist vorhanden, aber Score oder Ertrag reichen nicht für Grün. **Rot · Risiko-Flag:** Eine Drawdown-Schranke oder Martingale-Signatur ist angeschlagen.

**Ausgeschlossen:** Das Signal steht auf der Ausschlussliste. Die Begründung steht beim Urteil. **Grau · Vorprüfung:** Trade-Forensik fehlt oder konnte nicht erstellt werden. Fehlende Evidenz entlastet nicht.

Die Übersicht zählt die Einstufungen aller Signale des ausgewählten Laufs. Die Tabelle lässt sich zusätzlich filtern.
"""),
    "risk_metrics": ("Drawdown, Risiko-Score und Ertrag", """
**Risiko-Score (1–10):** Aggregierte Risikobewertung; kleinere Werte bedeuten weniger erkannte Risikofaktoren. Bei lokalen Referenzdaten kann ein hinterlegter Referenz-Score verwendet werden. Kein Wahrscheinlichkeitsmaß und keine Prognose.

**Trading-DD:** Aus geschlossenen Trades rekonstruierter Rückgang des Handelsergebnisses. **Equity-DD:** Plattformwert einschließlich schwankender offener Positionen. Geschlossene Trades können zwischenzeitliche offene Verluste verbergen; die Werte messen unterschiedliche Dinge.

**Ertrag pro Monat:** Historische Kennzahl aus verfügbaren Daten, keine erwartete Auszahlung. Projektvorgabe: maximal 30 % Drawdown und über 5 % Ertrag pro Monat.

**Profit-Faktor:** Verhältnis summierter Gewinne zum Betrag summierter Verluste. **Winrate:** Anteil gewinnender geschlossener Trades. Bei CSV-Daten verwenden diese Handelsstatistiken Profit vor Kommission und Swap; der Trading-DD berücksichtigt dagegen Nettowerte. Hohe Trefferquoten können mit seltenen, großen Verlusten einhergehen.
"""),
    "exposure": ("Positionen, Verlustserien und Schockrechnung", """
**Peak-Positionen** bezeichnet die größte rekonstruierte Anzahl gleichzeitig offener Positionen. **Netto-Lots** zeigt die richtungsabhängige Positionierung beim ersten Erreichen dieses Positionsmaximums, nicht zwingend das maximale Netto-Volumen über die gesamte Laufzeit. Viele kleine, gleichgerichtete Trades können ein großes Risiko bilden.

**50-USD-Schock bei XAUUSD:** Für den verwendeten Standardkontrakt entspricht 1 Lot einer Änderung von 100 USD je 1 USD Goldpreisbewegung. Die Rechnung lautet Betrag der Netto-Lots am Positionsmaximum × 100 × 50.

Das ist ein Szenario, kein gemessener Verlust und keine Verlustobergrenze. Slippage, Währungsumrechnung und abweichende Brokerkontrakte können das Ergebnis verändern. Bei gemischten Symbolen ist die gemeinsame Aggregation nur eine Näherung, keine getrennte Portfoliobewertung.

**Verlustserie** zählt in der aktuellen Statistik aufeinanderfolgende Trades ohne positiven Profit, einschließlich Null-Trades. **Martingale-Signaturen** suchen nach systematischer Positionsvergrößerung oder charakteristischen Basket-Mustern. Die Detailansicht nennt gefundene Evidenz.
"""),
    "stop_evidence": ("Ist der Stop-Loss bewiesen?", """
**Direkte Evidenz** kann aus einem Orderbuch mit S/L-Spalte und Ausführungs-Kommentaren wie [sl] stammen. Der gewöhnliche MQL5-Positions-Export enthält keine SL/TP-Spalten.

**Statistische Evidenz** sucht nach Verlusten mit ähnlichen Kursdistanzen. Ein Cluster kann regelbasierte Ausstiege plausibel machen, beweist aber nicht für jeden Trade einen beim Broker gesetzten Stop.

**Kein Nachweis** bedeutet: Die Daten belegen keinen verlässlichen Schutz. Anbieterbehauptungen, Signalnamen oder viele Abonnenten ersetzen keine Evidenz.

Auch historische Stops garantieren bei Kurslücken oder Slippage keine exakte zukünftige Verlustbegrenzung.
"""),
    "reports": ("Trade-Analyse, Risikoprofil und Gesamtbericht", """
Die optionale KI-Auswertung erzeugt drei Texte: **Trade-Analyse** zur Handelsweise, **Risiko-Analyse** zur Forensik und **Gesamtbericht**, der die Teilergebnisse zusammenführt.

Die Engine berechnet die Kennzahlen. KI-Texte interpretieren Daten und können trotzdem Fehler enthalten. Vergleiche Aussagen über Schutz und Positionsgrößen mit der ausgewiesenen Evidenz.

„Bericht“ zeigt einen bereits vorhandenen Text. Fehlt er, starte auf der Scan-Seite die KI-Auswertung für die dort geladenen Ergebnisse. Dieser Lauf kann API-Kontingent verbrauchen.

**Schließen** blendet den Bericht aus und löscht keine Ergebnisse.
"""),
}
