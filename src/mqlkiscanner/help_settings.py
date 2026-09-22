# -*- coding: utf-8 -*-
"""Kontext-Hilfen für die Einstellungsseite; keine Zugangsdaten."""

HELP_SETTINGS = {
    "settings_overview": ("Einstellungen: speichern, prüfen, verwenden", """
Die Einstellungen sind nach Aufgabe gruppiert. **Zugänge** verbinden MQL5 und die KI.
**KI & Modelle** legt Modelle, Endpunkt und Token-Budget fest. **MqlDownloader** bindet
den lokalen Downloader an (Abonnenten-Verläufe, Testreport-PDFs). **Scan & Risiko**
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
Die Vorlagen bauen aufeinander auf:

1. **Trade-Analyse:** Stufe 2 beschreibt Handelsmuster anhand von Engine-Statistiken
   und ausgewählten Beispiel-Trades.
2. **Risikoprofil:** Stufe 1 interpretiert die Forensik-Befunde und Kriterien.
3. **Gesamtbericht:** Stufe 2 führt Kandidatendaten, Forensik und beide Texte zusammen.
4. **Portfolio-Vorschlag:** Stufe 2 bewertet alle Signale als Depot-Mix.
5. **ℹ️ Tiefenanalyse (gelb markiert):** die Erweiterte KI-Analyse — läuft bewusst
   NICHT im Workflow, sondern wird je Signal manuell über den Button
   „Erweiterte KI Analyse machen" in der Detailansicht gestartet, mit
   vollständigen Trade-Daten ({trades_json}), Signalname ({signal_name}) und
   Signal-Link ({signal_url}) im Prompt.

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
    "settings_downloader": ("MqlDownloader anbinden", """
Der MqlDownloader ist ein eigener Netzwerkdienst im LAN, der Abonnenten-Verläufe
und Testreport-PDFs je Signal-ID vorhält. Diese Seite kennt nur seine **Base-URL**
(im Downloader standardmäßig Port **8089** mit Pfad `/api/v1`). Steht hier nur
`http://rechner:8089`, ergänzt das Programm `/api/v1` automatisch.

Ist im Downloader ein API-Token gesetzt, wird es zusätzlich benötigt — sonst bleibt
das Feld leer. **Leere Felder lassen den vorhandenen Token unverändert**; gespeichert
wird er wie alle Zugangsdaten nur lokal (Umgebung → .env → secrets.local.json).

Die Daten sind rein lesend und werden beim Abruf **lokal gespiegelt** (Ordner
`data/downloader/{Signal-ID}` plus Datenbank), sodass Verlauf und PDFs auch dann
anzeigbar bleiben, wenn der Downloader gerade aus ist. Tradelisten holt der Scanner
bewusst nicht aus dem Downloader — die Engine arbeitet mit den eigenen, verifizierten
MQL5-Exporten.
"""),
    "settings_downloader_test": ("Was prüft der MqlDownloader-Test?", """
Der Test ruft genau einen Endpunkt auf: `GET {Base-URL}/health`. Er prüft damit
Erreichbarkeit, API-Version, Provider-Anzahl und, ob ein Token erforderlich ist.

Der Test verwendet **immer die gespeicherte** Base-URL und den gespeicherten Token —
ungespeicherte Eingaben werden gewarnt, nicht benutzt. Ein erfolgreicher Health-Check
bestätigt die Netzwerkverbindung, nicht dass jedes Signal dort Daten hat: Ein Signal,
das der Downloader nie geladen hat, liefert je Endpunkt eine leere Antwort (404),
ohne dass die Verbindung defekt ist.
"""),
"settings_agenten": ("Agentenbetrieb: fünf Rollen, ein Protokoll", """
Der Agentenbetrieb (Bauplan doc/19) überträgt die Dauerbeobachtung an fünf
LLM-Rollen: **Dirigent** (plant und steuert), **Marktbeobachter** (Kursdaten),
**Signal-Betreuer** (Trade-Delta gegen das Algo-Profil), **Chefermittler**
(Lageberichte) und **Melder** (Alerts und Digests ins Postfach der
Agenten-Seite).

Zwei Grundregeln gelten weiter: Die Engine rechnet und bewertet — Agenten
beobachten und melden. Und jeder LLM-Schritt wird mit vollständigem Prompt
und vollständiger Antwort protokolliert: Seite **Agenten → Protokoll**.
Der Daemon ist ein eigener Prozess und läuft weiter, wenn die App geschlossen
wird; Start und Stopp passieren hier im Tab.
"""),
    "settings_agenten_start": ("Start: Daemon-Prozess und Freigabe", """
**Starten** setzt die Freigabe (agenten_enabled) und startet den Daemon als
eigenen Hintergrundprozess — er überlebt geschlossene Browser-Tabs und
App-Neustarts. Der Scheduler prüft alle 30 Sekunden, ob eine Rolle fällig
ist (Phase A: Dirigent werktags zur Startzeit). Der Status oben zeigt den
letzten Herzschlag; nach dem Start dauert der erste Tick bis zu 30 Sekunden.
"""),
    "settings_agenten_stop": ("Stopp: kooperativ über die Steuerungstabelle", """
**Stoppen** entzieht die Freigabe und setzt den Stopp-Wunsch in der
Steuerungstabelle. Der Daemon beendet sich sauber beim nächsten Tick
(maximal ~30 Sekunden) — laufende Schritte werden zu Ende geführt und
protokolliert. Ein hartes Beenden des Prozesses ist nicht nötig und nicht
vorgesehen.
"""),
    "settings_agenten_budget": ("Budget und Takt des Agentenbetriebs", """
Das **Tagesbudget** begrenzt die Summe aller Agenten-Modellaufrufe pro Tag,
das **Monatsbudget** pro Monat (Startwerte: 500.000 und 5.000.000 Token).
Bei Erschöpfung werden Modell-Schritte übersprungen und gemeldet —
Code-Schritte (Exporte, Delta-Berechnung, Forensik) laufen ohne Tokens
weiter. Die **Startzeit** steuert den täglichen Dirigent-Takt (werktags;
Wochenende ruht). Reguläre Scan-Läufe (Gelb/Grün, Full) zählen auf ihr
eigenes Lauf-Budget und belasten das Agenten-Budget nicht.
"""),
    "settings_agenten_budget_save": ("Speichern: Budget und Takt", """
Speichert Tages- und Monatsbudget, Startzeit und die Dirigent-LLM-Freigabe
in app_settings.json. Der Daemon liest die Werte beim nächsten Tick — ein
Neustart ist nicht nötig.
"""),
    "settings_agenten_rollen": ("Rollen: Modell, Limit, Aktivstatus", """
Je Rolle: **Rolle aktiv** (der Scheduler berücksichtigt sie), **Modell**
(Standard GLM-5.3; das kleinere Flash-Modell ist als Kostenschraube
wählbar, Freitext erlaubt OpenAI-kompatible Modelle) und **Max. Tokens**
je Aufruf. Rollen späterer Phasen sind konfigurierbar, aber als 'geplant'
gekennzeichnet — ihre Lauflogik entsteht in den Phasen B bis E.
"""),
    "settings_agenten_rollen_save": ("Speichern: Rollen-Konfiguration", """
Schreibt Modell, Ausgabelimit und Aktivstatus aller fünf Rollen in
app_settings.json. Änderungen greifen beim nächsten Lauf — ohne Neustart.
"""),
    "settings_agenten_prompts": ("Rollen-Prompts: sechs Vorlagen", """
Jede Rolle hat ihre eigene Vorlage unter config/prompts/agenten/ — wie die
Analysevorlagen editierbar, auf Standard zurücksetzbar und mit
Pflicht-Platzhaltern abgesichert. Fehlt eine Datei, wird die eingebettete
Standardvorlage neu angelegt.
"""),
    "settings_agenten_prompt_save": ("Speichern: Agenten-Vorlage", """
Speichert die bearbeitete Vorlage. Text und alle Pflicht-Platzhalter sind
erforderlich — eine Vorlage mit fehlendem Platzhalter wird nicht
gespeichert (der Lauf würde sonst mit einem leeren Abschnitt beim Modell
landen).
"""),
    "settings_agenten_prompt_reset": ("Standard wiederherstellen", """
Ersetzt die eigene Vorlage durch die eingebettete Standardfassung und
aktualisiert den Editor. Eigene Änderungen sind danach verworfen — vor dem
Zurücksetzen lohnt ein Blick in 'Standardvorlage ansehen'.
"""),
    "agenten_page": ("Agenten-Seite: Live und Protokoll", """
**Live** zeigt Daemon-Status, die fünf Rollen und die letzten Läufe.
**Protokoll** listet jeden Schritt chronologisch — Code-Schritte ebenso wie
Modellaufrufe. LLM-Schritte speichern den vollständig gefüllten Prompt und
die vollständige Antwort; der Auswahlkasten darunter öffnet den vollen
Wortlaut. Nichts wird gekürzt: Alles, was ein Modell sagt, steht im
Protokoll (das ersetzt den bewusst abgelehnten Trockenmodus).
"""),
}
