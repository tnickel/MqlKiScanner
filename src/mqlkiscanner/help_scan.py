"""Kontexthilfe für Scan-Aktionen und den sichtbaren Analyseablauf."""

HELP_SCAN = {
    "scan_workflow": ("So läuft der Workflow", """
**Ein Workflow = feste Reihenfolge.** Sie starten einmal; das Programm arbeitet die Stationen nacheinander ab.

**Was passiert (einfach):**

1. **Daten holen** — Signallisten und Handelsdaten von MQL5 laden.
2. **Speichern** — Infos und Dateien in die lokale Datenbank legen.
3. **Computer prüft** — Webseiten-Kennzahlen und CSV-Handelsdaten rechnen (Drawdown, Exposure, Stop-Nachweis).
4. **KI berichtet** — optional drei Texte je Signal (Trade + Risiko parallel, danach Endbericht).

**Die vier Statuskarten** zeigen denselben Ablauf etwas feiner:
Signale holen → Auswahl treffen → Prüfen & speichern → KI-Bericht.

**Farben:** Blau = läuft gerade · Grün = fertig · Orange = fertig mit Lücken · Rot = Fehler · Grau = wartet oder übersprungen.
Grün bedeutet nur: der Schritt ist technisch durch — nicht, dass ein Signal „sicher“ ist.

**Fortschrittsbalken** zählen erledigte Arbeitseinheiten (Seiten, Dateien, Berichte), keine Uhrzeit.
"""),
    "scan_start": ("Starte Workflow", """
**Dieser Knopf startet den kompletten Online-Durchlauf.**

Der Scanner holt Signallisten, filtert nach Ihren Einstellungen, lädt Handelsdaten, speichert sie, prüft sie rechnerisch und kann danach KI-Berichte schreiben.

**Voraussetzungen:** Öffentliche Listen brauchen keinen Login. Für vollständige Handelsdaten brauchen Sie MQL5-Benutzername und Passwort unter Einstellungen. Ohne Login bleibt oft nur eine Vorprüfung.

Wenn „KI-Berichte nach dem Workflow“ an ist und ein KI-Key da ist, folgen drei Texte je geeignetem Signal. Trade- und Risiko-Analyse starten parallel; der Gesamtbericht danach. Dafür kann Kontingent anfallen. MQL5-Passwörter gehen nicht an die KI.

Ergebnisse erscheinen danach auf dieser Seite und unter „Ergebnisse“.
"""),
    "scan_verify": ("Nur Testdaten prüfen", """
**Prüft die vorhandenen Dateien in `data/raw`.** Kein MQL5-Abruf, kein neuer KI-Aufruf.

Nützlich zum Ausprobieren ohne Login. Die Stationen „Signale holen“, „Auswahl“ und „KI“ werden als übersprungen markiert.
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

**Aus:** Der Workflow endet nach der rechnerischen Prüfung. KI können Sie später unter „Weitere Möglichkeiten“ nachziehen.
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
    "scan_results": ("Ergebnisse richtig lesen", """
**Datensätze** = verarbeitete Signale. **Gründlich geprüft** = mit Trade-Analyse.
**Kandidaten** = aktuell grün eingestuft. **Fehler / Vorprüfung** = unvollständig oder fehlerhaft.

Grün ist ein Prüfkandidat, keine Garantie. Schauen Sie zuerst auf Drawdown, Exposure und Stop-Nachweis.
Ein fertiger Workflow ersetzt keine eigene Entscheidung.
"""),
}
