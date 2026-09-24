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
    "tiefenanalyse": ("Erweiterte KI-Analyse (Tiefenanalyse)", """
Die Erweiterte KI-Analyse ist eine **manuelle Vollanalyse** für ein einzelnes Signal —
gestartet über den Button „Erweiterte KI Analyse machen“. Sie läuft bewusst nicht im
Workflow, weil sie deutlich mehr Tokens verbraucht als die Standard-Berichte.

**Was das Modell bekommt:** die vollständigen Trade-Daten (Statistiken plus
Beispiel-Trades aus dem Export), die Signal-Kennzahlen von der MQL5-Seite, die
maschinelle Forensik sowie Signalname und -Link (im Prompt per Platzhalter
eingesetzt). Die Vorlage ist im Admin-Bereich unter „Analysevorlagen →
ℹ️ Tiefenanalyse“ editierbar (gelb markierte Sonderrolle).

**Ergebnis:** ein ausführlicher Bericht (Risikomanagement, Grid-/Martingale-Prüfung,
Strategie-Typ, Risiko-Score 1–10, Performance-Forensik, Userbewertungen) als eigenes
PDF (`04-tiefenanalyse.pdf`) plus lesbarer Text — dauerhaft in der Datenbank
gespeichert und über Sitzungen hinweg abrufbar.

**Wichtig:** Auch diese Analyse ändert NICHT die Ampel, den Score oder das Urteil.
Sie ist Zusatzkontext für die eigene Einschätzung; maßgeblich bleiben die
Engine-Befunde. Das Modell rechnet auf Trade-Basis (z. B. Verlustwahrscheinlichkeit)
und muss seine Datengrundlage nennen.
"""),
    "tiefenanalyse_start": ("Was passiert beim Start der Erweiterten KI-Analyse?", """
Der Button baut den Tiefenanalyse-Prompt (Vorlage: Admin → Analysevorlagen →
ℹ️ Tiefenanalyse) mit den Daten dieses Signals und sendet ihn an das Stufe-2-Modell
(einstellbar unter „KI & Modelle“). Der Lauf kostet Tokens aus dem Lauf-Budget und
dauert mehrere Minuten — das Statusfenster währenddessen nicht schließen.

Voraussetzungen: GLM-Key hinterlegt und ein lesbarer Trade-Export für das Signal.
Ohne Trades startet die Analyse bewusst nicht — die Auswertung der Tradeliste ist
Kern der Aufgabe. Danach erscheinen PDF und Text direkt unter dem Button; ein erneuter
Klick erstellt eine neue Version (die alte bleibt in der Datenbank).
"""),
    "tradeserver_sync": ("Der Tradeserver-Sync (MqlTradeMonitor)", """
Der Sync überträgt die aktuell angezeigte Signal-Tabelle samt aller zugehörigen PDFs
(eigene Berichte inklusive Tiefenanalyse, Portfolio-Gesamtbericht und die gespiegelten
Downloader-Testreports) zum **MqlTradeMonitor-Tradeserver**. Dort erscheint eine
eigene Kachel „MqlKiScanner“, die den Verbindungsstand anzeigt, und hinter der Kachel
die Tabelle mit derselben Ampel-/Score-Darstellung wie hier — inklusive betrachtbarer
PDFs.

**Einmallauf, keine Dauerverbindung:** Klick auf den Sync-Button baut die Verbindung
auf, durchläuft das feste Protokoll (Anmeldung → Tabelle → Dokumente → Abschluss) und
trennt danach wieder. Unveränderte PDFs werden per Prüfsumme erkannt und übersprungen.
Der Sync **bewertet nie neu** und schreibt nichts in die Fachtabellen — er legt lokal
nur eine Lauf-Historie an. Base-URL und API-Key werden im Admin-Bereich unter
„Tradeserver“ gepflegt (der Key muss zu einem Benutzer des Tradeservers passen).
"""),
    "settings_tradeserver": ("Tradeserver-Verbindung (MqlTradeMonitor)", """
Ziel des Daten-Syncs ist der Spring-Boot-Tradeserver **MqlTradeMonitor** (feste
Server-IP, Port 8080, z. B. `http://tradeserver.example:8080`; im Produktivbetrieb liegt
ihm ggf. ein HTTPS-Reverse-Proxy vor). Der MqlKiScanner ist kein MetaTrader-EA und
nutzt deshalb ein eigenes Protokoll unter `{Base-URL}/api/kiscanner`.

**API-Key:** im Tradeserver beim gewünschten Benutzer hinterlegt (Admin-Oberfläche,
Feld „API-Key“). Derselbe Key wird hier gespeichert und bei jedem Sync-Aufruf im
Header `X-User-Key` mitgesendet — ohne gültigen Key lehnt der Server alles ab. Der
Key liegt wie alle Zugangsdaten nur lokal (nie im Repository).
"""),
    "settings_tradeserver_test": ("Tradeserver-Verbindungstest", """
Der Test ruft `{Base-URL}/api/kiscanner/ping` mit dem gespeicherten API-Key auf und
prüft damit Erreichbarkeit **und** Schlüssel in einem Schritt — mehr nicht: Es werden
keine Daten übertragen und kein Sync-Lauf gestartet. Steht der Test auf „erreichbar“,
funktioniert auch der Sync-Button auf der Ergebnisseite.
"""),
    "settings_rest_api": ("REST-API für MqlRealMonitor", """
Der MqlRealMonitor (Java, `D:\\git\\MQL\\MqlRealmonitor`) holt sich über dieses
schreibgeschützte Interface die Signalliste samt Gesamt-Ampel — der Button
„🤖 KiScanner“ dort überwacht danach nur noch Signale mit Ampel **grün oder gelb**.

**Endpunkte** (nur GET, nur auf diesem Rechner, `127.0.0.1`):
`/api/v1/health` für einen Verbindungscheck und `/api/v1/signals` für die Liste;
mit Filter z. B. `/api/v1/signals?ampel=gruen,gelb`. Die Ampel wird bei jedem
Abruf aus den gespeicherten Werten neu abgeleitet (wie die Ergebnis-Ansicht) —
der Server bewertet nie selbst und schreibt nichts in die Datenbank.

**Token (optional):** ist einer hinterlegt, muss der MqlRealMonitor denselben Key
im Header `X-User-Key` senden. Änderungen an Port, Schalter oder Token greifen
erst nach dem nächsten Start der App (der Server wird einmal beim Start geöffnet).
"""),
    "agent_dirigent": ("🎼 Dirigent — Orchestrierung & Tagesplanung", """
**Einfach erklärt:**
Der Dirigent ist der Taktgeber und Koordinator des gesamten Agentensystems. Er startet morgens als Erster (werktags um 06:30 Uhr) und prüft den Gesamtzustand: Welcher Tag ist heute? Haben wir noch genug KI-Token-Budget? Welche Agenten sind überhaupt aktiv? Anschließend entscheidet er, welche Aufgaben anstehen, und weckt die anderen Agenten der Reihe nach auf (den Marktbeobachter um 06:35 Uhr, den Signal-Betreuer um 06:45 Uhr).

**Technische Details & Befugnisse:**
- **Strenge Whitelist:** Der Dirigent darf keine Aktionen frei erfinden. Seine Entscheidungen sind im Python-Code auf eine strikte Whitelist beschränkt (`delta_laufen_lassen`, `delta_ueberspringen`, `markt_holen`, `markt_ueberspringen`, `scan_gelb_gruen`, `scan_full`, `meldung_schicken`).
- **Lauf-Lock:** Er reserviert das prozessweite System-Lock (`agenten_lauff`), damit automatisierte Läufe und manuelle GUI-Scans nicht kollidieren.
- **Budget-Wächter:** Kontrolliert das tägliche und monatliche Token-Budget vor jedem KI-Aufruf.
- **Grenzen:** Er bewertet niemals selbstständig Signale und darf keine mathematischen Kriterien überschreiben.
"""),
    "agent_markt": ("📈 Marktbeobachter — Kursdaten & Volatilität", """
**Einfach erklärt:**
Der Marktbeobachter analysiert das aktuelle Marktumfeld. Wenn unsere Handelssignale Positionen in Gold (XAUUSD), Währungen oder Indizes (DAX/DE40, US-Tech) halten, muss das System wissen, wie sich diese Märkte gerade bewegen. So lässt sich unterscheiden, ob ein Signalverlust an extremen Marktturbulenzen oder an Fehlern der Handelsstrategie lag.

**Technische Details & Befugnisse:**
- **MT5-Anbindung:** Liest historische H1- und Tageskurse direkt aus dem MetaTrader über das offizielle Python-Paket `MetaTrader5`.
- **Reine Lese-Whitelist:** Zugriff ausschließlich auf `copy_rates_from_pos`, `symbol_select` und `terminal_info`. Sämtliche Trading- und Order-Funktionen sind im Code physisch nicht verdrahtet!
- **Deterministische Kennzahlen:** Rechnet rein im Code: ATR14 (H1-Volatilitätsbandbreite), 24h-Range in %, Trendabstand zum 10-Tage-SMA sowie Performance über 1, 7 und 30 Tage.
- **LLM-Verdichtung:** Übergibt die fertigen Zahlen an das Modell zur Formulierung des täglichen Marktkontexts (`markt_kontext`).
"""),
    "agent_betreuer": ("🛡️ Signal-Betreuer — Forensik & Stilbruch-Erkennung", """
Der Signal-Betreuer (ausgeführt mit dem starken Modell **GLM-5.3**) ist der persönliche Wächter für jedes Signal auf deiner Empfehlungs- und Beobachtungsliste (Grün und Gelb). Er kennt die Handelsstrategie aus den bisherigen Berichten und prüft täglich, ob neue Trades noch exakt nach diesem Muster laufen oder ob ein Stilbruch vorliegt.

---

### 1. Schritt: Wie er die bisherigen Berichte auswertet (Profil-Destillation)

Bevor ein Signal überwacht werden kann, liest das System alle vorliegenden Analysedokumente aus der Datenbank:
1. **Die Tiefenanalyse** (ausführliche KI-Untersuchung der Strategie, Ein-/Ausstiegsmuster)
2. **Den Gesamtbericht** (KI-Zusammenfassung und Risikobewertung)
3. **Die Engine-Forensik** (harte Zahlen: Martingale-Signatur, SL-Cluster, Peak-Exposure, Holding-Zeiten)

Daraus destilliert das Modell ein versioniertes **Algo-Profil** im Signal-Dossier mit festen Abschnitten:
- **Strategietyp:** z. B. Mean-Reversion-Scalper, Grid, Trendfolge.
- **Gehandelte Sessions & Zeiten:** An welchen Tagen und Uhrzeiten darf das System Positionen eröffnen.
- **Positionsgrößen & Sizing:** Erlaubtes Lot-Verhalten (z. B. strikt fixe Lots vs. Eskalation nach Verlust verboten).
- **Stop-Disziplin:** Typische SL-Distanzen und Verlustbegrenzung.
- **Erwartetes Verhalten:** Typische Haltedauern, Drawdown-Bänder, Verlustserien-Länge.
- **Nummerierte Konformitäts-Merkmale:** Feste Kriterien, woran man erkennt, dass das Signal *normal* handelt.
- **Nummerierte Warn-Merkmale:** Konkrete Kriterien, was eine Abweichung oder ein *Stilbruch* wäre.

> **Belegpflicht:** Liegen für ein Signal weder Tiefenanalyse noch Gesamtbericht vor, verweigert der Betreuer die Prüfung. Es wird **nichts erfunden** — ohne Belegbasis gibt es kein Profil.

---

### 2. Schritt: Wie er prüft, ob das Signal noch dem Muster folgt (Tagesprüfung)

Bei jedem Tageslauf (werktags um 06:45 Uhr oder per Klick auf **⚡ Start** beim Betreuer) läuft folgende Kette:
1. **Trade-Export abholen:** Der Betreuer lädt den neuesten MQL5-CSV-Export über den gemeinsamen Rate-Limiter.
2. **Hash-Vergleich (0 Token bei Ruhe):** Stimmt der SHA-256-Hash mit gestern überein, gibt es keine neuen Trades. Das Modell wird **gar nicht erst aufgerufen** (spart Budget) → Einordnung: `KEINE_NEUEN_TRADES`.
3. **Delta-Kennzahlen (Code rechnet):** Gibt es neue Trades, berechnet der Python-Code alle Kennzahlen der neuen Positionen (Lots, Haltedauer, Gewinne/Verluste, Distanzen).
4. **LLM-Abgleich gegen das Profil:** Das Modell bekommt vorgelegt:
   - das hinterlegte **Algo-Profil** (aus deinen Reports),
   - die **berechneten Kennzahlen der neuen Trades**,
   - den aktuellen **Marktkontext** (vom Marktbeobachter, z. B. Volatilität oder Gold-Trend).
5. **Ergebnis-Einordnung:**
   - **`KONFORM`**: Alle neuen Trades passen exakt zur bekannten Strategie.
   - **`AUFFAELLIG`**: Verdächtige Abweichung (z. B. ungewöhnlich lange Haltedauer oder leicht erhöhtes Lot-Volumen).
   - **`STILBRUCH`**: Gravierende Abweichung (z. B. plötzliche Martingale-Verdopplung, Hold ohne Stop, fremdes Währungspaar). Bei `STILBRUCH` schickt der Betreuer **sofort einen Priorität-3-Alert ins Postfach**.

---

### Wo du das in der Oberfläche siehst:
- **Seite `Agenten` → Tab `Dossiers`:** Wähle oben das Signal aus (z. B. *Gold Spike MT4*). Dort siehst du links das vollständige **Algo-Profil** (aus deinen Berichten destilliert), darunter die Chronik der **Beobachtungen** (`KONFORM`, `AUFFAELLIG`, `STILBRUCH`) sowie die Historie der **Trade-Deltas**.
- **Seite `Agenten` → Tab `Postfach`:** Hier landen sofort alle Alarme bei erkannten Stilbrüchen.
"""),
    "agent_chef": ("🔍 Chefermittler — Synthese & Wochenbericht", """
**Einfach erklärt:**
Der Chefermittler behält den strategischen Überblick über das gesamte Portfolio. Am Wochenende (sonntags ab 18:00 Uhr) und zum Monatswechsel studiert er alle Berichte, Marktkontexte und Auffälligkeiten der Woche und schreibt einen verständlichen Wochen-Lagebericht.

**Technische Details & Befugnisse:**
- **Taktung:** Startet sonntags nach dem wöchentlichen Teilscan sowie am 1. Werktag des Monats nach dem Full-Scan.
- **Synthese:** Aggregiert Dossier-Spitzen, Ampelwechsel, Markttrends und Token-Verbräuche der vergangenen 7 Tage.
- **Empfehlungen:** Gibt strategische Hinweise für künftige Scans, darf aber **niemals** selbst eine Signal-Ampel verändern.
- **Ablage:** Speichert den Bericht als `lagebericht` direkt im Postfach der App.
"""),
    "agent_melder": ("📢 Melder — Alarmierung & Postfach-Digest", """
**Einfach erklärt:**
Der Melder ist deine Benachrichtigungszentrale. Er sorgt dafür, dass du wichtige Ereignisse sofort mitbekommst, ohne Logdateien durchsuchen zu müssen. Bei kritischen Vorfällen schlägt er Alarm; an normalen Tagen fasst er die Lage morgens kurz zusammen.

**Technische Details & Befugnisse:**
- **Drei Wege ins Postfach:**
  1. *Sofort-Alert:* Bei P3-Stilbrüchen des Signal-Betreuers.
  2. *Ampelwechsel-Watcher:* Registriert jeden Farbwechsel (Verschlechterung = P3, Verbesserung = P2), egal ob automatisch oder per GUI-Scan ausgelöst.
  3. *Tages-Digest:* Tägliche Zusammenfassung um 07:10 Uhr im Postfach.
- **Postfach:** Alle Meldungen werden mit Priorität und Quellenverweisen in der Datenbank gespeichert und im Tab „Postfach“ angezeigt (kein externer Mail- oder Chat-Spam).
"""),
}

