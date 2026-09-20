"""Contextual explanations grounded in the local analysis engine."""

HELP_CONTENT = {
    "workspace": ("So arbeitest du mit dem Scanner", """
**Kurzfassung:** Einstellungen ausfüllen → auf der Scan-Seite **Starte Workflow** drücken → unter Ergebnisse die Ampel und Belege prüfen.

**1 · Einmal vorbereiten.** Unter Einstellungen MQL5-Zugang und optional einen KI-Key hinterlegen. Testdaten gehen auch ohne Login.

**2 · Workflow starten.** Ein Knopf führt den Ablauf aus: Daten von MQL5 holen → speichern → Computer prüft → optional KI-Bericht. Die Statuskarten zeigen, wo der Lauf gerade steht. Fertig heißt nicht „empfohlen“.

**3 · Ergebnisse lesen.** Tabelle filtern, Zeile wählen, zuerst Drawdown, Exposure und Stop-Nachweis ansehen. Die KI erklärt; die Zahlen rechnet das Programm.

**Gelbes i.** Öffnet kurze Hilfe zum Nachbarn. Schließen mit „Verstanden“, Kreuz oder Escape.
"""),
    "connections": ("Zugänge und Bereitschaft", """
**MQL5** benötigt Benutzername und Passwort für authentifizierte Trade-Exporte. Sind beide hinterlegt, ist der Zugang konfiguriert, aber noch nicht als gültig getestet. Ein abgelaufener Login kann beim Export weiterhin scheitern.

**KI** benötigt einen GLM-Key und einen passenden Endpunkt. „Hinterlegt“ bestätigt nur das Vorhandensein des Keys, weder Guthaben noch Modellverfügbarkeit. Die Verbindung lässt sich in den Einstellungen testen.

**Ohne Zugänge** kannst du lokale Verifikationsdaten auswerten. Ohne KI-Key bleiben berechnete Befunde verfügbar; es entstehen keine KI-Berichte.
"""),
    "results_runs": ("Aktueller Lauf, Archiv und Datenbank", """
**Datenbank (alle Berichte)** zeigt alle in SQLite gespeicherten Signale mit Forensik und KI-Texten. **NEU** markiert Signale, für die im letzten Lauf dieser Sitzung Kennzahlen, Befunde oder Signalberichte neu gespeichert wurden. Unverändert übernommene Bewertungen zählen nicht dazu.

**Aktuelle Sitzung** zeigt nur den letzten Scan in diesem Browser-Tab. **Archiv** öffnet einen gespeicherten Laufordner.

Der Wechsel startet keinen neuen Abruf. CSV exportiert die aktuell gefilterten Zeilen.
"""),
    "results_filter": ("Ergebnisse suchen und filtern", """
Die Textsuche findet Signalnamen oder IDs. Im Statusfilter sind mehrere Einstufungen wählbar; ohne Auswahl sind alle sichtbar. Suche und Statusfilter gelten gemeinsam für Tabelle, Export und Urteile.

**Eine Zeile auswählen** öffnet darunter die Details. „Bericht“ zeigt den vorhandenen Gesamtbericht. Diese Aktionen starten keine Analyse.

**Kompakt** konzentriert sich auf Risiko, Stop-Nachweis und Urteil. „Alle Kennzahlen“ ergänzt Handelsstatistik, Volumen und Plattformdaten. **Ampeln** (die Ampel-Matrix) zeigt je Signal eine Ampel pro Testkriterium. Eine leere Zelle bedeutet fehlende Daten, nicht null Risiko.
"""),
    "ampel_matrix": ("Die Ampel-Matrix: je Kriterium eine Ampel", """
Die Matrix bewertet **einzelne Testkriterien** getrennt — sie ersetzt nicht das Gesamturteil (Spalte „Ampel“), zeigt aber, welche Bedingung die Einstufung treibt.

**Farben:** 🟢 erfüllt/bewiesen · 🟡 teilweise, knapp oder unabgeklärt · 🟠 Warnflag ohne harte Verletzung · 🔴 harte Verletzung/nachgewiesen · ⚪ keine Daten (entlastet nicht).

**ⓘ im Spaltenkopf** erklärt das Kriterium. **Maus über der Ampel-Zelle** zeigt die exakte Berechnung, z. B. „max(EQ-DD 3,80 %, Trading-DD 4,57 %) = 4,57 % hält die Schranke 30 % mit 25,4 Punkten Abstand ein“.

Die Kriterien: Drawdown-Schranke (max aus By-Equity-DD, By-Balance-DD und Trading-DD — der höchste der drei zählt), Martingale-Signatur, Stop-Nachweis (bewiesen/behauptet), Ertrag pro Monat, Risiko-Score, Schock vs. Konto (Stress-Szenario, nie allein ein Ausschlussgrund), längste Verlustserie und die kuratierte Ausschlussliste.

Beim Scan wird die Matrix mit allen Herleitungen als Snapshot in der Datenbank gespeichert; die Anzeige rechnet sie aus den gespeicherten Werten mit den aktuellen Grenzwerten neu.
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
    "ausschlussliste": ("Regelwerk der Ausschlussliste", """
Die **Ausschlussliste** (`data/known_signals.json`) wird manuell aus der forensischen Analyse-Reihe gepflegt; jeder Eintrag trägt seinen gemessenen Grund. Ein Signal kommt darauf, wenn mindestens eines dieser Kriterien klar erfüllt ist: **Drawdown-Schranke verletzt**, **Martingale/Grid ohne bewiesenen Stop**, **Ertrag dauerhaft unter der Schwelle**, **schwach belegter Edge (PF/Sharpe/Winrate)**, **grenznahe Risikokombination** (formal unter der Schranke, aber nahe dran plus tiefe Verlustserie) oder **Copy-Fragilität/Kurzlebigkeit**.

Die harten Regeln (Schranke, Martingale, Stop-Nachweis, Score/Ertrag) urteilt die Engine zusätzlich automatisch bei jedem Lauf. Ein Listen-Eintrag überlebt bessere Neuberechnungen; Wiederaufnahme nur, wenn neue Forensik den Grund entkräftet und der Eintrag entfernt wird.

Das vollständige Regelwerk samt aktueller Ausschlüsse steht auf der **Ergebnisse-Seite** im Abschnitt „Regelwerk · Ausschlussliste“ — bei ausgeschlossenen Signalen auch direkt in der Detailansicht.
"""),
    "portfolio_report": ("Der Portfolio-Vorschlag (Station 5)", """
Der **Portfolio-Vorschlag** ist ein zusätzlicher KI-Bericht, der ALLE geprüften Signale zusammen ansieht: Kennzahlen, Forensik, gehandelte Assets und die Gesamtberichte. Er empfiehlt eine Depot-Kombination mit Rollen (Ertragsträger/Risikoträger), Gewichtung und Diversifikations-Begründung über unterschiedliche Assets und Strategie-Typen.

Der Bericht steht in der Datenbank und bleibt auch über Sitzungen hinweg erhalten; ein neuer Lauf mit KI ersetzt ihn. Liegen weniger als zwei geprüfte Signale vor, weist der Bericht auf die fehlende Diversifikation hin.

**Wichtig:** Risiko vor Ertrag — Signale ohne Stop-Nachweis, mit Martingale-Flag oder verletzter Drawdown-Schranke dürfen nicht als Ertragsträger aufgenommen werden. Der Vorschlag ist keine Anlageberatung; die Engine-Zahlen sind maßgeblich.
"""),
    "downloader_section": ("MqlDownloader: Abonnenten-Verlauf und Testberichte", """
Dieser Abschnitt kommt aus dem **MqlDownloader**, einem eigenen Netzwerkdienst im LAN
(zu konfigurieren im Admin-Bereich unter „MqlDownloader“). Der Scanner holt zwei
Datenarten: den **Abonnenten-Verlauf** (an welchen Tagen wie viele Nutzer das Signal
abonniert hatten) und die **Testreport-PDFs**, die dem Downloader für diese Signal-ID
vorliegen.

Beide Abrufe sind rein lesend. Alles wird **lokal gespiegelt** — der Verlauf in der
Datenbank, die PDFs unter `data/downloader/{Signal-ID}` — und bleibt dadurch auch
anzeigbar, wenn der Downloader gerade aus ist. Unveränderte PDFs werden beim erneuten
Aktualisieren nicht erneut geladen.

Der Verlauf ist eine Marktbeobachtung (Vertrauen, Marketing, Wachstum), aber **keine
Risikokennzahl**: Viele Abonnenten beweisen keine Qualität, und Wachstum allein sagt
nichts über Stop-Nachweis oder Drawdown. Die Bewertung folgt weiterhin den
Forensik-Kriterien; dieser Abschnitt liefert Zusatzkontext.
"""),
    "downloader_sync": ("Der MqlDownloader-Abgleich", """
Der Abgleich holt aus dem lokalen MqlDownloader zwei Datenarten für die Signale der
gewählten Quelle: den **Abonnenten-Verlauf** und die **Testreport-PDFs**. Er läuft an
drei Stellen: automatisch als **Station 6** nach jeder Analyse, per Button hier auf der
Ergebnisseite (ohne neuen Scan, ohne MQL5-Abruf) und je Signal in der Detailansicht.

**Der Abgleich bewertet nie neu.** Ampeln, Urteile, Scores und Berichte bleiben
unverändert; frische Verlaufsdaten sind Zusatzkontext, keine Risikokennzahl. Neue
Signale erscheinen deshalb auch nicht als „NEU" — diese Markierung behalten
Analyse-Läufe vorbehalten.

**Wann braucht der Abgleich Aufmerksamkeit?** Ist der Downloader aus oder nicht
konfiguriert, meldet die Station „Mit Hinweisen" (orange) beziehungsweise der Button
einen Abbruch — bereits geladene Daten bleiben gespeichert, der Lauf selbst ist davon
unabhängig. Beim nächsten erfolgreichen Abgleich wird einfach weitergesammelt.
"""),
    "downloader_docs": ("Dokumente-Spalte: PDFs direkt aus der Tabelle", """
Die letzte Tabellenspalte **Dokumente** zeigt je Signal ein 📄-Icon mit der Anzahl der
gespiegelten Testreport-PDFs aus dem MqlDownloader. Ein Klick öffnet unter der Tabelle
den Dokumentenbereich: Alle PDFs des Signals sind dort sofort lesbar eingebettet, mit
Speichern-Button daneben. Kein PDF vorhanden, bleibt die Zelle leer — der Abgleich
läuft dann erst noch (Station 6 oder Button auf dieser Seite), oder im Downloader
liegt für diese Signal-ID schlicht keines.

Die PDFs sind lokale Spiegelkopien (`data/downloader/{Signal-ID}`) und bleiben deshalb
auch lesbar, wenn der Downloader gerade aus ist. Die Bewertung eines Signals wird
davon nicht berührt.
"""),
}
