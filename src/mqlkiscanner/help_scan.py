"""Kontexthilfe für Scan-Aktionen und den sichtbaren Analyseablauf."""

HELP_SCAN = {
    "scan_workflow": ("So läuft der Workflow", """
**Ein Workflow = feste Reihenfolge.** Sie starten einmal; das Programm arbeitet die Stationen nacheinander ab.

**Was passiert (einfach):**

1. **Daten holen** — Signallisten und Handelsdaten von MQL5 laden.
2. **Speichern** — Infos und Dateien in die lokale Datenbank legen.
3. **Computer prüft** — Webseiten-Kennzahlen und CSV-Handelsdaten rechnen (Drawdown, Exposure, Stop-Nachweis).
4. **KI berichtet** — optional drei Texte je Signal (Trade + Risiko parallel, danach Endbericht).

**Die fünf Stationen** zeigen denselben Ablauf im Detail:
Signale holen → Auswahl treffen → Prüfen & speichern → KI-Bericht → Portfolio.

**Farben:** Blau = läuft gerade · Grün = fertig · Orange = fertig mit Lücken · Rot = Fehler · Grau = wartet oder übersprungen.
Grün bedeutet nur: der Schritt ist technisch durch — nicht, dass ein Signal „sicher“ ist.

**Fortschrittsbalken** zählen erledigte Arbeitseinheiten (Seiten, Dateien, Berichte), keine Uhrzeit.
"""),
    "scan_start": ("Full-Scan starten", """
**Dieser Knopf startet den kompletten Online-Durchlauf über ALLE ausgewählten Signale.**

Der Scanner holt Signallisten, filtert nach Ihren Einstellungen, lädt Handelsdaten, speichert sie, prüft sie rechnerisch und kann danach KI-Berichte schreiben.

**Voraussetzungen:** Öffentliche Listen brauchen keinen Login. Für vollständige Handelsdaten brauchen Sie MQL5-Benutzername und Passwort unter Einstellungen. Ohne Login bleibt oft nur eine Vorprüfung.

Wenn „KI-Berichte nach dem Workflow“ an ist und ein KI-Key da ist, folgen drei Texte je geeignetem Signal. Trade- und Risiko-Analyse starten parallel; der Gesamtbericht danach. Dafür kann Kontingent anfallen. MQL5-Passwörter gehen nicht an die KI.

Bei jedem geprüften Signal wird die Ampel in die Farb-Chronik aufgezeichnet; Wechsel gegen den Vorgänger werden protokolliert (Wechselliste unter „Ergebnisse“).

Ergebnisse erscheinen danach auf dieser Seite und unter „Ergebnisse“.
"""),
    "scan_gelbgruen": ("Teilscan starten", """
**Regelmäßige Überwachung der Kandidaten und Beobachtungen (vormals Gelb/Grün-Scan).**

Der Teilscan prüft NUR Signale, die aktuell **🟢 (Kandidat)** oder **🟡 (Beobachtung)** sind — alle anderen Farben werden in diesem Lauf nicht beachtet. Welches Signal dazu zählt, steht in der Datenbank (letzte Bewertung).

**Immer mit KI:** Für jedes dieser Signale werden ALLE KI-Stufen neu erzeugt (Trade-Analyse, Risiko-Analyse, Gesamtbericht) — unabhängig von den Toggles „Nur neue Signale“ und „Vorhandene Berichte neu erstellen“. Danach läuft der Portfolio-Vorschlag über die geprüften Signale. Braucht KI-Key und Kontingent.

**Zweck:** Nach einigen Wochen prüfen, ob ein Gelbes grün geworden ist oder ein Grünes gelb — jede Änderung landet automatisch im Wechsel-Protokoll (Ergebnisseite, Button „Wechsel-Protokoll“).
"""),
    "wechsel_protokoll": ("Ampel-Wechsel-Protokoll", """
**Jede Bewertungsänderung wird dauerhaft aufgezeichnet.**

Bei jedem erfolgreich geprüften Signal schreibt der Scanner einen Chronik-Eintrag (Farbe, Score, Urteil, 8-Kriterien-Matrix). Ändert sich danach die Farbe ODER kippt eines der 8 Einzelkriterien, wird das als Wechsel protokolliert — mit alt/neu-Zustand und exakter Berechnung je Kriterium.

**Einordnung:** 📉 rot = Verschlechterung · 📈 grün = Verbesserung · ℹ️ gelb = Einordnung (z. B. Kriterium gekippt, Farbe gleich — Frühindikator).

Die Liste zeigt alle protokollierten Wechsel (neueste zuerst); die Wechsel-Historie je Signal als Farbband. Fehlgeschlagene Prüfungen schreiben keinen Eintrag — der letzte gültige Stand bleibt Vergleichsbasis. Die Chronik beginnt mit der Einführung der Aufzeichnung; alte Läufe wurden bewusst nicht nachträglich importiert.
"""),
    "scan_verify": ("Nur Testdaten prüfen", """
**Prüft die vorhandenen Dateien in `data/raw`.** Kein MQL5-Abruf, kein neuer KI-Aufruf.

Nützlich zum Ausprobieren ohne Login. Die Stationen „Signale holen“, „Auswahl“ und „KI“ werden als übersprungen markiert.

Die Demo verändert keine Live-Daten oder Bewertungen im Katalog. Ihre Ergebnisse werden nicht für KI-Berichte oder Portfolio-Vorschläge verwendet.
"""),
    "scan_llm": ("Nur KI-Berichte starten", """
**Erzeugt KI-Texte für bereits geprüfte Ergebnisse dieser Sitzung.**

Pro geeignetem Signal: Trade- und Risiko-Analyse **parallel**, danach der Endbericht.
Braucht einen KI-Key. Startet keine neue Datenabholung von MQL5.
"""),
    "scan_scope": ("Wie weit suchen?", """
**Listen-Seiten je MT4/MT5:** Mehr Seiten = breitere Suche, aber länger und mehr Abrufe.

**Max. Signale gründlich prüfen:** Obergrenze für den aufwendigen Teil (Handelsdaten + Risiko-Rechnung), Standard 30. Die Reihenfolge folgt der Abonnentenzahl — viele Abonnenten heißen nicht „gutes Signal“.
"""),
    "scan_filters": ("Vorfilter verstehen", """
**Mindestalter** und **Mindest-Abonnenten** sortieren ungeeignete Signale früh aus.
Das ist nur eine Vorauswahl — noch keine Risikobewertung.
"""),
    "scan_llm_settings": ("KI am Ende des Workflows", """
**An:** Nach dem Rechnen versucht der Workflow, KI-Berichte zu schreiben (braucht Key und Kontingent).

**Aus:** Der Workflow endet nach der rechnerischen Prüfung. KI können Sie später unter „Testdaten und Expertenfunktionen“ nachziehen.
"""),
    "scan_save": ("Einstellungen speichern", """
Speichert Suchumfang, Filter und KI-Schalter als Standard für später.
Startet keinen Workflow und ändert vorhandene Ergebnisse nicht.
"""),
    "scan_connections": ("Bereitschaft und Zugänge", """
**MQL5-Zugang** braucht Benutzername und Passwort für vollständige Handelsdaten.
**KI-Key** braucht einen gültigen Schlüssel für Berichte.

Ohne MQL5-Zugang können Sie trotzdem Testdaten prüfen. Hinterlegte Zugänge sind noch kein erfolgreicher Verbindungstest.

Bei wiederholter Drosselung oder Login-Sperre bricht der Workflow weitere MQL5-Exporte ab (Fail-Fast), statt den Account weiter zu belasten.
"""),
    "scan_reuse": ("Vorhandene Bewertungen übernehmen", """
**An:** Bereits vollständig geprüfte Signale werden nicht erneut von MQL5 geladen. Das spart Zeit und schont den Zugang.

Fehlende oder nicht mehr passende KI-Berichte können trotzdem ergänzt werden. Der Portfolio-Vorschlag berücksichtigt weiterhin alle geeigneten Signale.

**Aus:** Alle ausgewählten Signale werden erneut geladen und forensisch geprüft.
"""),
    "scan_results": ("Ergebnisse richtig lesen", """
**Datensätze** = verarbeitete Signale. **Gründlich geprüft** = mit Trade-Analyse.
**Kandidaten** = aktuell grün eingestuft. **Probleme** = unvollständig oder mit abgebrochener Prüfung.

Grün ist ein Prüfkandidat, keine Garantie. Schauen Sie zuerst auf Drawdown, Exposure und Stop-Nachweis.
Ein fertiger Workflow ersetzt keine eigene Entscheidung.
"""),
}
