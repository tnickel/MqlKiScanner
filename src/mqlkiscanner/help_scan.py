"""Kontexthilfe für Scan-Aktionen und den sichtbaren Analyseablauf."""

HELP_SCAN = {
    "scan_workflow": ("Den Analyseablauf lesen", """
**Der Scanner arbeitet in vier Schritten.** Die Karten zeigen den Zustand des aktuellen
Laufs, die feste Leiste am unteren Bildschirmrand die aktuelle Tätigkeit und die nächsten Schritte.

1. **Listen lesen:** öffentliche Signal-Listen für MT4 und MT5 abrufen. Der Zähler nennt geladene Seiten.
2. **Kandidaten auswählen:** Mindestalter und Abonnentenfilter auf die gefundenen Signale anwenden. Die vorhandene Ausschlussliste bleibt Teil der späteren Kennzeichnung.
3. **Daten & Forensik:** Kennzahlen und verfügbare Trade-Exporte prüfen. Die Engine berechnet Martingale-Signaturen, Spitzenexposure, Stop-Signaturen und rekonstruierten Drawdown. Der Zähler nennt bearbeitete Datensätze; ein bearbeiteter Datensatz kann auch einen Fehler oder nur eine Vorprüfung enthalten.
4. **LLM-Auswertung:** pro geeignetem Signal Trade-Analyse, Risiko-Analyse und Gesamtbericht erzeugen. Hier zählt der Balken nur erfolgreich fertiggestellte und gespeicherte Prompts.

**Farben und Zustände:** Blau bedeutet aktiv; Grün bedeutet technisch abgeschlossen.
Orange weist auf unvollständige Teilergebnisse hin, Rot auf einen Fehler. Grau kennzeichnet
wartende oder ausdrücklich übersprungene Schritte. Der Text unterscheidet beide.
Ein grüner Arbeitsschritt sagt nichts darüber aus, ob ein Handelssignal ein vertretbares Risiko hat.

**Was bedeutet der Fortschritt?** Die Balken messen Arbeitseinheiten im jeweiligen Schritt,
keinen Anteil an der Gesamtlaufzeit. Ein Modellaufruf oder eine Netzwerkpause kann lange dauern,
ohne dass der Zähler steigt. Solange keine Antwort vorliegt, bleibt der letzte belegte Stand sichtbar.
Fehler und nicht ausgeführte Prompts werden nicht als erfolgreicher Fortschritt gezählt.

**Unterbrechungen:** Ergebnisse werden während der Bearbeitung in der Sitzung gesammelt und
am Laufende zusammen mit dem Protokoll gespeichert. Ein Seitenwechsel, Neuladen oder Stoppen
kann einen synchronen Lauf unterbrechen. Beim nächsten Aufruf der Scan-Seite wird ein solcher
Lauf als unterbrochen markiert; unfertige Schritte erhalten keine Abschlussmarkierung.
"""),
    "scan_start": ("Einen MQL5-Scan starten", """
**Diese Aktion startet einen neuen Live-Lauf.** Die sichtbare Ergebnisauswahl wird durch
die Ergebnisse dieses Laufs ersetzt. Bereits gespeicherte Läufe bleiben in der Historie erhalten.

Der Scanner lädt die konfigurierte Anzahl Listen-Seiten für MT4 und MT5, filtert nach Alter
und Abonnenten und prüft bis zur eingestellten Obergrenze die Kandidaten mit Handelsdaten.
Die Reihenfolge stammt aus der nach Abonnenten sortierten Liste. Eine hohe Platzierung ist
kein Qualitätsnachweis. Bekannte Ausschlüsse werden bei der Bewertung gekennzeichnet.

**Voraussetzungen:** Öffentliche Listen benötigen keinen Login. Für geschützte Trade-Exporte
werden MQL5-Benutzername und Passwort benötigt. Ohne verwertbaren Trade-Export bleibt ein
Signal in der Vorprüfung. Eine nicht durchgeführte Forensik kann nicht durch die KI ersetzt werden.

Wenn „KI-Berichte nach dem Scan erstellen“ aktiviert ist und ein KI-Key vorliegt, folgt
die Auswertung geeigneter Forensik-Ergebnisse mit drei Prompts je Signal. Dabei werden
Signalinformationen, berechnete Befunde und für die Trade-Analyse strukturierte Handelsdaten
mit Beispielen an den konfigurierten Modellanbieter übertragen. Dafür kann Kontingent anfallen.
MQL5-Zugangsdaten sind kein Bestandteil dieser Prompts.

**Nach dem Start:** Die Statuskarten zeigen die aktive Arbeit und jeden verbleibenden Schritt.
Abrufpausen dienen der gedrosselten Nutzung von MQL5; längere Wartezeiten sind dort möglich.
Ergebnisse und Protokoll erscheinen nach dem Lauf auf dieser Seite und unter „Ergebnisse“.
"""),
    "scan_verify": ("Lokale Verifikations-Datensätze laden", """
**Diese Aktion verarbeitet die vorhandenen CSV- und JSON-Referenzdateien in `data/raw`.**
Jede Datei läuft einzeln durch dieselbe lokale Analyse-Engine. Der Fortschrittszähler
steigt erst nach der Verarbeitung der jeweiligen Datei.

Es werden keine MQL5-Seiten geladen und keine neuen Modellaufrufe gestartet. Die Schritte
Listen, Kandidatensuche und LLM-Auswertung sind deshalb ausdrücklich „Übersprungen“.
Ein MQL5-Login oder KI-Key ist für die lokale Berechnung nicht erforderlich.

**Was Sie erhalten:** berechnete Kennzahlen und Forensik-Befunde, soweit die Quelldatei sie
ermöglicht. Bei bekannten Signalen können hinterlegte Stammdaten und bereits gespeicherte
KI-Berichte ergänzt werden. Ein sichtbarer alter KI-Bericht wurde dadurch nicht neu erstellt.

**Grenzen:** Historische Referenzdateien beschreiben ihren Datenstand. Sie belegen weder
heutige Plattformwerte noch künftig begrenzte Risiken. Ein Positions-Export enthält keine
SL/TP-Spalten; fehlender Stop-Nachweis bleibt auch in einer lokalen Analyse ein Warnsignal.

Die aktuelle Ergebnisauswahl wird durch den Verifikationslauf ersetzt. Ein Fehler in einer
Datei wird als solcher angezeigt; bereits bearbeitete Dateien bleiben sichtbar. Am Ende
werden Ergebnisse und Ablaufprotokoll als Lauf gespeichert.
"""),
    "scan_llm": ("Vorhandene Befunde mit KI auswerten", """
**Diese Aktion erzeugt neue KI-Berichte für die Ergebnisse der aktuellen Sitzung.**
Sie ist verfügbar, sobald Ergebnisse vorhanden sind. Tatsächlich ausgewertet werden
nur Datensätze mit vorhandener Forensik und ohne Analysefehler.

Je geeignetem Signal werden drei Prompts ausgeführt:

1. **Trade-Analyse:** Das starke Modell ordnet das beobachtete Handelsverhalten anhand strukturierter, von der Engine vorbereiteter Handelsdaten und Beispiele ein.
2. **Risiko-Analyse:** Das schnelle Modell interpretiert die berechneten Forensik-Kennzahlen und Kriterien.
3. **Gesamtbericht:** Das starke Modell führt die Informationen und beide Teilanalysen zusammen.

**Daten und Kontingent:** Die beschriebenen Signal- und Handelsinformationen werden an den
konfigurierten KI-Anbieter gesendet. Ein erneuter Start führt neue Aufrufe aus und verbraucht
erneut Kontingent. MQL5-Zugangsdaten werden nicht an das Modell übergeben. Der Schalter für
„KI-Berichte nach dem Scan“ betrifft den automatischen Live-Lauf, nicht diese ausdrückliche Aktion.

**Fortschritt und Fehler:** Ein gesendeter Prompt ist noch kein fertiger Bericht. Gezählt
werden erfolgreich gespeicherte Teilberichte. Fehlt der Key oder ein geeigneter Datensatz,
wird die Stufe übersprungen. Fehlerhafte und wegen Vorfehlern nicht ausgeführte Prompts
werden gesondert genannt. Bei fehlendem Kontingent endet die Stufe mit dem bis dahin erreichten Stand.

Ein Modellbericht ist eine Interpretation der vorhandenen Befunde und kein zusätzlicher
Beweis für funktionierende Stops oder begrenzte künftige Verluste. Bei einem fehlgeschlagenen
erneuten Lauf können zuvor gespeicherte Berichte weiterhin in den Ergebnissen stehen;
die Fortschrittsanzeige bezieht sich ausschließlich auf den neuen Lauf.
"""),
    "scan_scope": ("Den Suchumfang festlegen", """
**Listen-Seiten je MT4/MT5** legt fest, wie viele öffentliche Ergebnisseiten pro Plattform
gelesen werden. Bei zwei Seiten sind das vier Seiten insgesamt. Mehr Seiten verbreitern
die Suche, erhöhen jedoch Zahl und Dauer der Abrufe. Die Zahl der gefundenen Signale je Seite
kann schwanken; daraus lässt sich keine feste Kandidatenzahl ableiten.

**Maximale Forensik-Exporte** begrenzt die Anzahl der Kandidaten, für die Kennzahlen und
Trade-Daten analysiert werden. Sind nach der Vorauswahl weniger Kandidaten übrig, werden
entsprechend weniger geprüft. Die Reihenfolge folgt der nach Abonnenten sortierten Liste.
Abonnenten sind hier eine Auswahlreihenfolge, kein Beleg für Qualität oder begrenztes Risiko.

Die sichtbaren Werte gelten sofort für den nächsten Live-Lauf. Die lokale Verifikation
verarbeitet dagegen die vorhandenen Referenzdateien und nutzt diese Obergrenze nicht.
Mit „Scanprofil als Standard speichern“ übernehmen Sie die Werte dauerhaft.
"""),
    "scan_filters": ("Kandidatenfilter verstehen", """
**Mindestalter in Wochen** schließt Signale aus, deren ausgewiesene Laufzeit unter dem
eingestellten Wert liegt. Ein höherer Wert bevorzugt längere Historien, beweist aber
keine robuste Strategie. Ist das Alter auf der Liste unbekannt, verwirft dieser Filter
das Signal nicht automatisch; die Angabe muss später geprüft werden.

**Mindestens Abonnenten** schließt Signale unterhalb dieser Zahl aus. Eine fehlende
Abonnentenangabe wird dabei wie null behandelt. Null lässt auch neue oder wenig bekannte
Signale zu. Eine höhere Zahl fokussiert etabliertere Angebote, kann aber unpopuläre
Kandidaten ausblenden. Viele Abonnenten sind kein Sicherheits- oder Qualitätsnachweis.

Diese beiden Werte betreffen die Vorauswahl beim Live-Scan. Harte Risiko-Grenzen,
die Forensik-Batterie und die bekannte Ausschlussliste sind davon getrennt. Ein Signal
wird durch das Bestehen der Vorauswahl noch nicht positiv bewertet.
"""),
    "scan_llm_settings": ("KI-Berichte im Scanprofil", """
**Aktiviert:** Nach der lokalen Forensik versucht der Live-Scan, für geeignete Signale
die drei Berichte Trade-Analyse, Risiko-Analyse und Gesamtbericht zu erstellen.
Ein konfigurierter Key und verfügbares Kontingent sind dafür nötig.

**Deaktiviert:** Der Live-Scan endet nach der rechnerischen Analyse und speichert seine
Befunde ohne neue Modellaufrufe. Schritt 4 wird als übersprungen angezeigt. Sie können
die KI-Auswertung später ausdrücklich über die separate Aktion starten.

Alle drei Prompts bilden eine zusammenhängende Auswertung mit zwei Modellrollen:
Trade-Analyse und Gesamtbericht verwenden das starke Modell, Risiko-Analyse das schnelle
Modell. Modelle, Endpunkt, Token-Limit und Prompt-Texte stehen unter „Einstellungen & Prompts“.
Dieser Schalter wählt keine einzelnen Prompt-Stufen ab.

Die Berechnungen kommen aus der Engine. KI ergänzt eine sprachliche Interpretation und
kann fehlende Daten, fehlende Stop-Nachweise oder unbestandene Tests nicht ersetzen.
"""),
    "scan_save": ("Das Scanprofil als Standard speichern", """
**Diese Aktion speichert den Suchumfang, die Kandidatenfilter und die Auswahl für
automatische KI-Berichte dauerhaft als Standardprofil.** Die Werte werden für künftige
Läufe wieder geladen. Zugangsdaten und Prompt-Texte ändern Sie in ihren eigenen
Bereichen unter „Einstellungen & Prompts“.

Die gerade sichtbaren Einstellungen gelten bereits ohne Speichern für den nächsten
Lauf auf dieser Seite. Speichern ist also für dauerhafte Vorgaben gedacht.
Es startet weder einen Scan noch einen Modellaufruf und berechnet vorhandene Ergebnisse
nicht neu. Um die Wirkung geänderter Filter zu sehen, starten Sie anschließend einen neuen Live-Lauf.

Änderungen der Standardwerte unter „Einstellungen & Prompts“ und auf dieser Seite
beziehen sich auf dasselbe Scanprofil. Prüfen Sie die sichtbaren Werte vor dem Start.
"""),
    "scan_connections": ("Bereitschaft und Zugänge", """
**Lokale Engine bereit** bedeutet, dass die Analysefunktionen in der Anwendung geladen
sind. Lokale Referenzdateien lassen sich ohne externe Zugangsdaten analysieren.

**MQL5-Zugang hinterlegt** bedeutet, dass sowohl Benutzername als auch Passwort vorhanden
sind. Dies ist noch kein erfolgreicher Login-Test. Eine Sitzung kann ablaufen; Exporte
können einen erneuten Login benötigen. Ohne verwertbaren Trade-Export bleiben Ergebnisse
in der Vorprüfung und erhalten keinen Forensik-Nachweis.

**KI-Key hinterlegt** bedeutet, dass ein Schlüssel konfiguriert ist. Das bestätigt weder
seine Gültigkeit noch verfügbares Guthaben oder einen passenden API-Endpunkt. Verwenden
Sie bei Bedarf den Verbindungstest unter „Einstellungen & Prompts“.

**Abrufabstand und Pause je Signal** drosseln den MQL5-Zugriff. Bei einer Drosselungsantwort
können zusätzliche Wartezeiten folgen. Der Workflow bleibt in dieser Zeit beim aktuellen
Schritt stehen. Die Einstellungen dafür finden Sie im Bereich für den MQL5-Zugriff.
Automatische Abrufe können durch die Plattform eingeschränkt werden; weniger und langsamere
Abrufe reduzieren die Belastung, garantieren aber keine Freigabe.
"""),
    "scan_results": ("Ergebnisse richtig einordnen", """
**Datensätze** zählt die verarbeiteten Ergebnisse. **Mit Forensik** zeigt, für wie viele
Ergebnisse Trade-Daten lokal analysiert wurden. **Kandidaten** zählt die aktuell grün
eingestuften Signale. **Fehler / Vorprüfung** fasst Ergebnisse zusammen, die einen Fehler
oder keinen Forensik-Befund haben. Die Kennzahlen können sich überschneiden und sind
nicht als voneinander getrennte Summanden gedacht.

Die Ergebnistabelle verbindet Plattformdaten, von der Engine berechnete Kennzahlen und
Bewertung. Wählen Sie ein Signal für Details. Verfügbare KI-Berichte lassen sich im
Berichtsbereich lesen; sie können auch aus früheren gespeicherten Analysen stammen.

**Risiko vor Ertrag:** Eine technisch erfolgreich gelesene Datei oder ein fertig
geschriebener Bericht ist keine Handelsempfehlung. Prüfen Sie besonders Drawdown,
gleichzeitiges Exposure, Martingale-Signaturen und die Qualität des Stop-Nachweises.
Ein Positions-Export enthält keine SL/TP-Spalten. Fehlender Nachweis ist eine Datenlücke,
keine Entlastung. Historische Kennzahlen sind keine Garantie für zukünftige Ergebnisse.

Die Statuskarten und das aufklappbare Ablaufprotokoll helfen zu erkennen, welche Befunde
im aktuellen Lauf tatsächlich erzeugt wurden und wo Fehler oder ausgelassene Schritte vorliegen.
"""),
}
