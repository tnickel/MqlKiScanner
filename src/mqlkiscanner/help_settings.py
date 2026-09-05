# -*- coding: utf-8 -*-
"""Kontext-Hilfen für die Einstellungsseite; keine Zugangsdaten."""

HELP_SETTINGS = {
    "settings_overview": ("Einstellungen: speichern, prüfen, verwenden", """
Die Einstellungen sind nach Aufgabe gruppiert. **Zugänge** verbinden MQL5 und die KI.
**KI & Modelle** legt Modelle, Endpunkt und Token-Budget fest. **Scan & Risiko**
bestimmt den Suchumfang und die Prüfgrenzen. **Analysevorlagen** steuert die drei KI-Texte.

**So gehst du vor:** Werte in einem Bereich ändern → den Speichern-Button genau dieses
Bereichs drücken → bei Zugängen die gespeicherte Verbindung testen → Scan starten.
Jeder Bereich zeigt an, ob seine Änderungen noch ungespeichert sind. Ein Test verwendet
immer die wirksamen gespeicherten Zugangsdaten und die gespeicherten Modelleinstellungen.

Gespeicherte Scan-, Modell- und Risikoparameter sind Vorgaben für folgende Läufe;
ein laufender Scan behält seine Parameter. Zugangsdaten werden beim nächsten Zugriff
und Vorlagen beim nächsten passenden KI-Aufruf neu gelesen. Das gelbe **i** erklärt
jeweils Zweck, Wirkung und Grenzen.
"""),
    "settings_mql5": ("MQL5-Zugang und Trade-Exporte", """
Der MQL5-Zugang wird für angemeldete Abrufe verwendet, insbesondere für Trade-Exporte.
Die öffentlichen Signallisten und eine vollständige Exportprüfung sind unterschiedliche
Schritte: Ein vorhandener Login allein ist noch kein Nachweis für einen erfolgreichen Export.

Trage Benutzername beziehungsweise E-Mail und Passwort ein. **Leere Felder lassen den
jeweiligen vorhandenen Wert unverändert.** Du kannst deshalb auch nur das Passwort ändern.
Anschließend zuerst speichern und dann den gespeicherten Login testen.

Die Anwendung liest Zugangsdaten in dieser Reihenfolge: **Prozess-Umgebung → .env →
config/secrets.local.json**. Hier werden ausschließlich lokale Dateieinträge geändert.
Ein Wert aus der Umgebung oder .env hat weiterhin Vorrang. Zugangsdaten werden nicht
an die KI übergeben. Die lokale Datei ist aus Git ausgeschlossen, aber nicht verschlüsselt.
"""),
    "settings_mql5_test": ("Was prüft der MQL5-Login-Test?", """
Der Test versucht eine Anmeldung bei MQL5 mit den **aktuell wirksamen gespeicherten**
Zugangsdaten. Neue, noch nicht gespeicherte Eingaben werden nicht verwendet.

Währenddessen zeigt die Oberfläche den laufenden Test. Bei Erfolg ist die Anmeldung
bestätigt. Der Test lädt keine Signalhistorie und prüft keine einzelnen Exportrechte;
ein bestimmter Trade-Export kann daher später trotzdem fehlen oder scheitern.

Bei Fehlern zuerst prüfen, ob Benutzername und Passwort vollständig gespeichert sind.
Falls externe Umgebungswerte gesetzt sind, muss der Zugang dort korrigiert werden.
Der Test startet weder einen Scan noch eine KI-Analyse.
"""),
    "settings_key": ("KI-Zugang sicher hinterlegen", """
Der API-Key authentifiziert Anfragen an den konfigurierten KI-Endpunkt. Ohne Key
kann die lokale Rechen- und Forensik-Engine weiterhin arbeiten; KI-Texte benötigen
einen funktionsfähigen Zugang und verfügbares Kontingent beim Anbieter.

Das Passwortfeld ist für einen **neuen** Wert bestimmt. Leer lassen bedeutet:
den vorhandenen Key nicht verändern. **Key lokal speichern** schreibt nur nach
config/secrets.local.json. Bereits gespeicherte Keys werden hier nicht angezeigt.

Die Priorität ist **Prozess-Umgebung → .env → lokale Datei**. Unterstützte
Umgebungsnamen sind MQLKISCANNER_GLM_KEY und GLM_API_KEY. Ein externer Key kann deshalb
einen hier geänderten lokalen Wert übersteuern. Die Datei ist aus Git ausgeschlossen,
aber nicht verschlüsselt. Der Verbindungstest steht unter **KI & Modelle**.
"""),
    "settings_key_remove": ("Lokalen API-Key entfernen", """
Dieser Button leert ausschließlich den GLM-Key in config/secrets.local.json.
MQL5-Zugangsdaten bleiben erhalten. Ein aus der Prozess-Umgebung oder .env geladener
Key wird damit **nicht** entfernt und kann weiterhin als verfügbar angezeigt werden.

Das Entfernen widerruft keinen Key beim Anbieter und beendet keine dort gebuchten
Kontingente. Falls du einen Key vollständig ungültig machen möchtest, musst du ihn
zusätzlich beim Anbieter widerrufen. Du kannst hier jederzeit einen neuen lokalen Key speichern.
"""),
    "settings_models": ("Zwei Modellrollen, drei Analysevorlagen", """
Die Anwendung verwendet zwei Modellrollen für drei Texte:

- **Stufe 1:** erstellt das kompakte Risikoprofil aus den vorliegenden Befunden.
- **Stufe 2:** erstellt die Trade-Analyse und anschließend den ausführlichen Gesamtbericht.

Die Rechen-Engine liefert Kennzahlen und Forensik-Ergebnisse. Das Modell formuliert
und interpretiert diese Daten; die Modellauswahl ersetzt keinen Pflicht-Test.
Die hier aufgeführten Modellnamen sind konfigurierbare Vorschläge, keine Zusage der
Verfügbarkeit in deinem Tarif. Bereits konfigurierte eigene Modellnamen bleiben auswählbar;
du kannst auch einen exakten neuen Modellnamen eingeben.

Speichern übernimmt beide Modellrollen, Endpunkt und Budget gemeinsam. Der Verbindungstest
prüft nur das gespeicherte Modell der **Stufe 1**. Die Verfügbarkeit der Stufe 2 ist damit
noch nicht nachgewiesen.
"""),
    "settings_endpoint": ("KI-Endpunkt: an welches Konto gehen Anfragen?", """
Der Endpunkt ist die Serveradresse für KI-Anfragen. Die Anwendung bietet zwei
vorkonfigurierte Z.ai-Adressen sowie eine eigene Base-URL:

- **GLM Coding Plan:** https://api.z.ai/api/coding/paas/v4
- **Standard-API:** https://api.z.ai/api/paas/v4
- **Eigene URL:** eine zum Client passende Chat-Completions-Base-URL.

Wähle den Endpunkt, der zu deinem API-Zugang und Kontingent gehört. Die verfügbaren
Modelle und Kontingente hängen vom Anbieter und Tarif ab. Ein Kontingentfehler kann
auf einen unpassenden Endpunkt oder fehlendes Guthaben hinweisen.

Bei einer eigenen URL werden API-Key und Analyseanfragen an genau diesen Server gesendet.
Verwende nur einen für deinen Zugang vorgesehenen Server. Die Base-URL soll nicht bereits
mit /chat/completions enden, da der Client diesen Pfad selbst ergänzt.
"""),
    "settings_budget": ("Was begrenzt das Token-Budget?", """
Tokens sind die vom Anbieter gezählten Texteinheiten für Eingabe, Ausgabe und gegebenenfalls
modellinterne Verarbeitung. Das Budget ist eine **Mengenbegrenzung pro KI-Lauf**, kein
Euro-Limit und keine Zusage bestimmter Kosten.

Der Client addiert die in Antworten gemeldeten Tokens und prüft das Limit **vor** einer
neuen Anfrage. Eine bereits laufende Anfrage kann das Limit daher überschreiten.
Ist das Budget anschließend erreicht, werden weitere Anfragen dieses Clients abgelehnt.
Ein neuer Lauf beziehungsweise ein Verbindungstest startet einen eigenen Zähler.

Mehr Kandidaten, längere Befunde und ausführlichere Antworten benötigen meist mehr Tokens.
Den tatsächlichen Verbrauch zeigt der Lauf. Ein kleineres Budget kann dazu führen,
dass nur ein Teil der KI-Berichte erstellt wird; vorhandene Engine-Befunde bleiben davon getrennt.
"""),
    "settings_llm_test": ("Gespeicherte KI-Verbindung testen", """
Der Button sendet eine kleine Testanfrage an den **gespeicherten Endpunkt**, mit dem
**gespeicherten Stufe-1-Modell**, Budget und wirksamen gespeicherten API-Key.
Noch nicht gespeicherte Änderungen werden ausdrücklich nicht für den Test verwendet.

Die Anfrage verbraucht Anbieter-Kontingent beziehungsweise Tokens. Der Test überträgt
keine Signalhistorie. Er bestätigt bei Erfolg die Erreichbarkeit, Authentifizierung
und Antwortfähigkeit dieses Modells. Stufe 2 und ein vollständiger Analyseablauf werden
hierdurch nicht geprüft.

Bei Fehlern: Zugang, gewählten Endpunkt, Modellname und Kontingent kontrollieren.
Änderungen zuerst im zugehörigen Bereich speichern und dann erneut testen.
"""),
    "settings_filters": ("Scanprofil: welche Signale werden geprüft?", """
Das Scanprofil speichert die Ausgangswerte für neue Scans. Auf der Scan-Seite können
Werte für den konkreten Lauf geändert werden. Ein bereits laufender Scan behält seine Parameter.

**Listen-Seiten je Plattform** bestimmt, wie viele Seiten der MT4- und MT5-Listen
abgerufen werden. **Export-Kandidaten** begrenzt die Kandidaten, die einen
Trade-Export und eine Forensikprüfung erhalten. Mehr Umfang erzeugt mehr Abrufe und längere Läufe.

**Mindesthistorie** filtert nach beobachteten Wochen. Fehlende Wochenangaben werden im
aktuellen Vorfilter nicht allein ausgeschlossen. **Mindest-Abonnenten** ist nur ein
Listenfilter: Popularität belegt weder geringes Risiko noch bewiesene Stop-Losses.

Das Bestehen dieser Filter ist keine positive Bewertung. Dafür sind Risiko- und
Forensikprüfung erforderlich. Speichern übernimmt nur die vier Felder dieses Bereichs.
"""),
    "settings_risk": ("Risiko vor Ertrag: Grenzen richtig lesen", """
**Maximaler Equity-Drawdown** ist der größte gemeldete Rückgang des Kontowerts einschließlich
offener Positionen. Die Projektvorgabe erlaubt höchstens **30 %**; hier kannst du eine
strengere Grenze einstellen. Ein Wert oberhalb der eingestellten Grenze verletzt die Schranke.
Die Prüfung benötigt einen verfügbaren Plattformwert. In lokalen CSV-Prüfungen wird
kein aktueller Equity-Drawdown abgerufen; der rekonstruierte Trading-Drawdown ersetzt ihn nicht.

**Ertragsschwelle pro Monat** ist eine Mindestbedingung, keine Renditeprognose.
Die Projektvorgabe verlangt **mehr als 5 % pro Monat**. Die aktuelle Engine vergleicht
jedoch mit **größer oder gleich** der eingestellten Schwelle. Bei 5,0 % wird somit auch
exakt 5,0 % akzeptiert. Für einen strengeren Filter kannst du einen Wert über 5,0 einstellen.

Drawdown und Ertrag allein beweisen keine Sicherheit. Peak-Exposure, Martingale,
Stop-Nachweis und rekonstruierter Drawdown müssen ebenfalls geprüft werden. Insbesondere
enthält der Positions-Export keine SL/TP-Spalten; fehlender Stop-Nachweis bleibt ein Warnflag.

Dieser Bereich speichert nur die beiden Grenzwerte. Bestehende Berichte werden nicht
rückwirkend neu bewertet.
"""),
    "settings_rate": ("Abrufpausen und Drosselung", """
Diese drei Zeiten steuern das Abrufverhalten gegenüber MQL5:

- **Mindestabstand je Request:** Mindestabstand zwischen Anfragen derselben Session,
  ergänzt um eine zufällige Pause von bis zu einer Sekunde.
- **Pause zwischen Signalen:** zusätzlicher Abstand vor einem neuen Trade-Export-Abruf.
  Bei einem aus dem lokalen Cache geladenen Export entfällt dieser Abruf.
- **Wartezeit nach Drosselung:** Ausgangswert für Pausen bei HTTP 429 oder 503.
  Wiederholte Drosselung verdoppelt die Pause je Versuch; nach drei gedrosselten
  Abrufen bricht der Abruf mit einem Fehler ab.

Wartezeit ist ein aktiver Bestandteil des Ablaufs. Mehr Seiten und Kandidaten verlängern
die Laufzeit zusätzlich. Ein größerer Abstand verringert die Abrufdichte; er garantiert
keine Freigabe durch den Anbieter. Bei Drosselungen die Pausen erhöhen und den Umfang reduzieren.

Die gespeicherten Werte gelten für folgende Läufe. Der Login-Test verwendet den
Mindestabstand; Exportpausen und der Drosselungs-Backoff betreffen die Export- beziehungsweise
Datenabrufe. Dieser Speichern-Button ändert weder Scanfilter noch Risiko- oder Modelleinstellungen.
"""),
    "settings_prompts": ("Analysevorlagen: welcher Text entsteht wo?", """
Die drei Vorlagen bauen aufeinander auf:

1. **Trade-Analyse:** Stufe 2 beschreibt Handelsmuster anhand von Engine-Statistiken
   und ausgewählten Beispiel-Trades.
2. **Risikoprofil:** Stufe 1 interpretiert die Forensik-Befunde und Kriterien.
3. **Gesamtbericht:** Stufe 2 führt Kandidatendaten, Forensik und beide Texte zusammen.

Platzhalter in geschweiften Klammern werden durch Daten ersetzt. Sie müssen unverändert
enthalten bleiben, damit die jeweilige Datengrundlage an das Modell übergeben wird.
Die aktuelle Vorlage wird vor dem Speichern auf fehlende Pflicht-Platzhalter geprüft.

Änderungen wirken auf nachfolgende KI-Aufrufe. Sie rechnen keine Kennzahlen neu und
ändern keine bereits gespeicherten Berichte. Keine Zugangsdaten in Vorlagen einfügen.
"""),
    "settings_prompt_save": ("Analysevorlage speichern", """
Speichert ausschließlich die aktuell ausgewählte Vorlage unter config/prompts/.
Die anderen beiden Vorlagen bleiben unverändert. Die Anzeige unterscheidet
**ungespeicherte Änderungen**, **gespeicherte Standardvorlage** und **gespeicherte eigene Vorlage**.

Vor dem Speichern prüft die Oberfläche, ob Text und alle für diese Vorlage vorgesehenen
Platzhalter vorhanden sind. Diese Prüfung bewertet keine inhaltliche Qualität:
Verlange weiter belegte Aussagen, kennzeichne fehlende Daten und lasse keine Zahlen erfinden.

Der nächste passende KI-Aufruf liest die gespeicherte Vorlage. Bereits erzeugte Texte
werden dadurch nicht ersetzt. Ein Speichern startet keinen kostenpflichtigen KI-Aufruf.
"""),
    "settings_prompt_reset": ("Vorlage auf Standard zurücksetzen", """
Setzt die **aktuell ausgewählte** Vorlage auf den im Programm enthaltenen Standard zurück.
Die Standardvorlage wird sofort gespeichert und der Editor direkt aktualisiert.
Eigene gespeicherte Änderungen und ungespeicherter Text dieser Vorlage werden dabei ersetzt.

Die anderen beiden Vorlagen bleiben erhalten. Nutze die Standardvorschau, um den
Zieltext vorab zu lesen. Wenn du deinen bisherigen Text behalten möchtest, kopiere ihn
vor dem Zurücksetzen aus dem Editor. Zurücksetzen startet keine KI-Analyse.
"""),
    "settings_prompt_preview": ("Standardvorlage ansehen", """
Die Vorschau zeigt die im Programm hinterlegte Standardfassung der gewählten Vorlage.
Sie verändert weder den Editor noch die gespeicherte Datei und löst keine KI-Anfrage aus.

Vergleiche hier Aufgabenstellung, Datengrundlagen und Platzhalter mit deinem eigenen Text.
Erst **Standard wiederherstellen** überschreibt die ausgewählte Vorlage tatsächlich.
"""),
}
