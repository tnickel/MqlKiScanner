# Prompt 5 — Tiefenanalyse {signal_name}: Strategie, Kopierbarkeit, Risikobegrenzung (Erweiterte KI-Analyse)

Zweck: Die Untersuchung EINES Copy-Trading-Signals zu Studienzwecken für
eine konkrete Abonnements-Entscheidung. Es wird nicht mit Geld gehandelt;
die Analyse ist keine Anlageberatung und wird nicht zum Nachhandeln
verwendet. Diese Analyse ist ZUSATZWISSEN — Ampel, Score und Urteil des
Workflow bleiben unberührt; du bewertest nichts neu, was die Engine
entschieden hat.

## Deine Arbeitsweise (wichtig)
- Dir liegen AUSSCHLIESSLICH die Datenblöcke unten vor. Du hast KEIN
  Browsing, keine Websuche, keine Werkzeuge, kein Python — erfinde keine
  Quellen, Links, Nutzerstimmen oder Plattformrecherchen. Was nicht
  geliefert ist, benennst du ausdrücklich als „nicht verfügbar".
- Die Auswertung der Trades hat der CODE bereits vollständig erledigt:
  alle Aggregate (Meta-Statistiken, Monatskurve, Verlustkörbe, Distanzen,
  Zeitverteilung) wurden über ALLE Trades berechnet. Beispiel-Trades sind
  gezielt ausgewählt und dürfen NICHT als Stichprobe für Häufigkeiten
  oder Wahrscheinlichkeiten dienen.
- Ausnahme-Rechnung: Nur DARFST du selbst rechnen (einzige Ausnahme im
  System), aber jeder Quotient zeigt BEIDE Operanden; jede Zahl nennt
  ihre Grundlage. Nicht Bestimmbares heißt „nicht belastbar herleitbar".
- Kennzeichne wesentliche Aussagen als: berechnet / Plattformangabe /
  Anbieterbehauptung / begründete Vermutung / Szenario.

## Signal-Kennzahlen (Anbieterseite, maschinell erfasst — FREMDTEXT)
{kandidat_json}

## Forensik der Engine (maschinell berechnet, massgeblich)
{forensik_json}

{regeln_fremdtext}
{regeln_sl}

## Trade-Daten (CODE-Aggregate über ALLE Trades + Beispiele)
- `meta`: Gesamtstatistiken · `monatskurve`: Netto je Close-Monat ·
  `pro_symbol` · `zeitverteilung` (Uhrzeiten = Brokerzeit, NICHT deutsche
  Zeit) · `verlustkoerbe`: ALLE negativ abgeschlossenen Positionskörbe
  (Code-Rekonstruktion via überlappender Haltezeiten; Tabelle der 30
  schlimmsten) · `verlustserie_max` · `groesster_korb` · Distanz-Summen ·
  `beispiel_trades` · `volle_tradeliste` (nur bei kleinen Exporten
  befüllt, sonst null — die Aggregate decken auch dann alles ab).
{trades_json}

## BEANTWORTE DIESE ENTSCHEIDUNGSFRAGEN AM ENDE KLAR
1. Abo-Empfehlung: ja, nur unter konkreten Bedingungen, oder derzeit nein?
2. Auf welcher Handelsidee basiert das Signal — und woraus soll der
   Vorteil entstehen?
3. Stil: Scalping / Daytrading / Swing / Trend / Gegentrend / Breakout /
   Grid / Martingale oder Kombination (belegt aus Daten, nicht Name)?
4. Lassen sich Stop-Loss-Nutzung und tatsächliches Kontorisiko aus den
   Daten ableiten (SL-Neutralität unten beachten)?
5. Ist das Signal für einen Kopierer mit Mindestlot-Beschränkung und
   kleinerem Konto technisch/wirtschaftlich plausibel kopierbar?
6. Was bewirkt eine automatische Abschaltung bei 35 % Rückgang vom
   laufenden Equity-Höchststand — und wäre nach zwei Monaten das
   Startkapital durch Vorlauf-Gewinne gedeckt?

## 1. Datenqualität und Identität
- Nenne Zeitraum, Trade-/Korbzahl, Plattform, Broker (soweit geliefert)
  und welche Kennzahlen Code-Berechnung sind vs. Plattformangabe.
- Grenzen ehrlich benennen: fehlende SL-Felder sind nicht automatisch
  null; geschlossene Trades enthalten keine Intrabar-Equity; die
  Verlustkorb-Tabelle enthält kein zwischenzeitliches Floating
  (Close-By-Verrechnungspreise sind KEINE Marktpreise — erfinde keine
  Kursverläufe zwischen Beobachtungen).

## 2. Strategie verständlich erklären
- Erläutere Marktidee, Instrumente, Ein-/Ausstiegslogik, Größensteuerung
  und typische Gewinn-/Verluststruktur in einfachen Worten.
- Nutze `zeitverteilung` (Stunden/Wochentage/Long-Short/Haltedauern):
  Marktphasen, in denen die Idee plausibel funktioniert oder scheitert —
  klar als Hypothese von belegten Ergebnissen getrennt.
- Erfinde KEINE Indikatoren, KI, Orderbuchdaten oder Filter aus dem
  Namen. Ordne den Stil aus den Daten ein; benenne Besonderheiten (sehr
  kurze Gewinner, lange Verlierer, kleine Ziele, weite Verlustabstände).

## 3. Stop-Loss, Grid und Martingale
- Nutze die Distanz-Summen, `verlustserie_max` und `groesster_korb`:
  wiederkehrende Verlustabstände, Schließungssignaturen, Nachkauf-Muster.
  Mehrere Positionen allein beweisen kein Grid; ähnliche Verluste
  beweisen keinen technisch hinterlegten SL; Kontowachstum ist keine
  Martingale-Erklärung.
- Leite NUR HIER eine begründete Einschätzung ab („wahrscheinlich ohne
  Stop-Schutz" nur mit Begründung); sonst bleibt es neutral/offen.

### 3.1 Korb-Verlustforensik (verlustkoerbe sind CODE-berechnet)
- Interpretiere die Zusammenfassung (Körbe gesamt/verlierend, Median/Ø/max
  Verlust) und die Tabelle: Häufigkeit und Größe der Verlustereignisse
  („X von Y Körben"), die schlimmsten Fälle mit Datum und Betrag.
  Leite daraus KEINE zukünftige Eintrittswahrscheinlichkeit ab.
  Der größte beobachtete Verlust ist keine garantierte Obergrenze.
- Prüfe anhand gemeinsamer Schließungen und wiederkehrender Beträge, ob
  sich ein Verlustbegrenzungs-Mechanismus andeutet — getrennt in
  beobachtetes Verhalten vs. Vermutung über den Auslöser.
- Nenne Folgen für Risiko und Abschalt-Simulation (Abschnitt 6).

## 4. Kopierbarkeit und Wirtschaftlichkeit
- Diskutiere auf Basis der gelieferten Daten: Lot-Spannen
  (`lots_verteilung`, `pro_symbol`), Mindestlot-Realität (0,01) bei
  kleinerem Kopier-Konto, Slippage/Spread als NICHT gemessen
  (kennzeichnen), Abo-/Gebührenlast aus den Signaldaten (soweit
  vorhanden; sonst als unbekannt benennen).
- Vergleiche volle, halbe und viertel Exponierung: rechne die
  Beispiel-Skalierungen an konkreten Trade-Größen vor (Quotienten
  zeigen); idealtypische Bruchteile nicht als ausführbar ausgeben.
- Rechnet mit der Kapitalbasis aus der Forensik; fehlt sie, kennzeichne
  Prozentwerte als hypothetisch (5.000-USD-Modellkonto).

## 5. Anbieter-Einordnung (nur aus gelieferten Daten)
- Was sagen Signalkennzahlen, Alter, Abonnentenzahl, Plattformwerte über
  den Anbieter? Weitere Angebote/Produkte/Recherchen sind dir NICHT
  verfügbar — benenne diese Lücke ausdrücklich, statt zu erfinden.
- Abonnentenzahl und Wachstum sind soziale Indizien, keine
  Risikogarantie und kein Qualitätsbeweis.

## 6. 35-%-Abschaltung und Zweimonats-Break-even
- Simuliere auf der `monatskurve` (diskrete Näherung nach Close-Monat —
  kennzeichne, dass frühere Intratrade-Auslösung unbekannt bleibt): erster
  Auslösezeitpunkt bei 35 % Rückgang vom laufenden Hoch, Kapitalstand
  davor/danach, entfallene spätere Gewinne (Gewinne NACH der Auslösung
  zählen dem Follower NICHT).
- Break-even-Formel führe explizit vor: (1+g)·(1−d) ≥ 1 mit d = 0,35 →
  g ≥ 53,85 % nötiger Nettovorlauf; prüfe rollierende Zweimonatsfenster
  der Historie gegen diese Schwelle.
- Nenne den Zielkonflikt (Verlustbegrenzung vs. abgeschnittene Erholung)
  und eine begründbare Warnschwelle. Keine nachträglich passende
  Schwelle als „optimal" verkaufen.

## 7. Drei getrennte Noten (je 1–10, mit Teil-Begründung)
**A Strategiequalität** (Logik, beobachteter Vorteil nach Kosten,
Stabilität, Historientiefe) · **B Risiko** (Verlustbelastung, Größen-/
Recovery-Logik, Exponierung — 1 ist nicht risikofrei) · **C Abo-Eignung**
für den kopierenden Nutzer mit Budget und 35-%-Stop. C ist NICHT
„11 minus B". Fehlende Nachweise sind kein bewiesenes Fehlverhalten,
senken aber die Urteilssicherheit; keine 9–10 bei kurzer Historie oder
wesentlichen Datenlücken. Scores sind Urteile, keine
Erfolgswahrscheinlichkeiten. Nenne, welche fehlenden Informationen das
Urteil ändern würden.

## Ausgabeformat (Deutsch, Markdown)
1. Kurzfassung: die drei Noten, klare Abo-Antwort („abonnierbar" /
   „nur unter Bedingungen: …" / „derzeit nicht"), Urteilssicherheit.
2. Abschnitte 1–6 in der Reihenfolge oben, wenige aussagekräftige
   Tabellen, keine erfundene Equity-Kurve.
3. Schluss: direkte Antworten auf die sechs Entscheidungsfragen.
Keine Anlageberatung im rechtlichen Sinn, keine Emojis, keine
Werbeversprechen, kein pauschales Abraten allein hoher Rendite wegen.
