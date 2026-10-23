# Ein Button: Strategien bewerten, Kandidatenliste und Top-5-Analysen

Stand: 23.10.2026. Überarbeitet nach der konkretisierten Nutzeranforderung.
**Implementiert im Arbeitsbaum:** Dialog, dauerhafter Recherchelauf, gezielte
Quellenabrufe, Floating-DD-Berechnung, Rangliste und beide KI-Stufen.
Lokale Tests verwenden synthetische Daten und Modellantworten. Die fünf nativen
Clients sind neu gebaut und nach belegtem Leerlauf sanft neu gestartet; Health
und Status sind geprüft. Kein produktiver Analyse-/Downloadlauf wurde gestartet.
Robo bleibt wegen unbelegter nativer Währungs-/Volumeneinheiten gesperrt.
Seit der ergänzenden Nutzerentscheidung vom 23.10. werden Robo-Gewinn und
Rendite trotzdem als ausgewiesene Quellenwerte in einer eigenen Ansicht
„Quellenprofitabilität“ angezeigt. Diese Anzeige erfindet weder Floating-DD
noch RetDD und verändert keine Kandidatenrangfolge. `rst` blockiert die
Metadatenaufnahme nicht mehr. Details im Umsetzungsnachweis
`reviews/2026-10-23_robo_quellenprofitabilitaet/README.md`.
Umsetzungsnachweis: `reviews/2026-10-23_abonnenten_analyse/README.md`.
Die frühere ausführliche Konzeptfassung ist durch diese Vorgabe ersetzt.

## 1. So bedient der Nutzer das

In **Abonnentenstatistik** steht neben dem Aktualisieren-Button ein Button:
**„Strategien bewerten“**. Er öffnet genau einen Dialog:

```text
Strategien bewerten

Welche Strategien?     [Top 200 je Quelle, mindestens 1 Abonnent]
Welche Quellen?        [MQL, Pelican, Robo, Vantage, Zulu]
Drawdown-Grenze?       [keine]
Gewichtung?           [RetDD 70 % | relativer Abonnentenrang 30 %]

Mindestens 2 Monate und 50 abgeschlossene Trades.
Fehlende Daten automatisch laden. Kurz-KI für alle auswertbaren Strategien.
Ausführliche Analyse für die besten 5. Budget: aus Einstellungen.

                          [Analyse starten]
```

Danach läuft alles ohne weitere fachliche Einzelfragen. Die Ansicht zeigt den
Fortschritt und ermöglicht Stoppen/Fortsetzen. Nur echte Hindernisse wie ein
abgelaufener Login verlangen eine Nutzeraktion. Der Browser muss nicht offen
bleiben; der gespeicherte Auftrag ist nach Prozessneustart fortsetzbar.

**Bestätigte Nutzerentscheidungen aus dem Fragendialog:** Top 200 je Quelle
mit mindestens einem Abonnenten; RetDD entscheidet ohne zusätzliche feste
DD-Obergrenze; RetDD und quellenrelativer Abonnentenrang werden gemeinsam gewichtet.
Die konkrete Aufteilung **70 % / 30 % ist eine vorgeschlagene Startgewichtung**,
keine vom Nutzer vorgegebene Prozentzahl. Im Startdialog verstellbar und in den
Einstellungen als Standard speicherbar. Quellen können dort abgewählt werden.

## 2. Was automatisch passiert

1. **Auswahl festhalten:** Quellen und Anbieteridentitäten zum Start einfrieren.
   MQL4/5 teilen sich eine Quelle und deren 200 Plätze. Top 200 bedeutet die
   beliebtesten Anbieter je Quelle mit mindestens einem Abonnenten. Ein späterer
   optionaler Gesamtkatalogmodus wäre ausdrücklich ein größerer Auftrag.
2. **Informationen beschaffen:** aktuelle Metadaten, vollständige verfügbare
   Tradelisten, Kapitalflüsse, Währungs-/Kontraktbelege und benötigte Kursdaten.
   Für einen aktuellen Kontobefund zusätzlich datierte aktuell offene Positionen.
3. **Alles rechnen:** vollständige Codeforensik, Floating-Equity-Verlauf,
   maximalen relativen Equity-DD, Renditen, RetDD, Exposure und Martingalebefunde.
4. **Kurze KI-Analyse:** für jede auswertbare Strategie einschließlich solcher,
   die später nicht in die Kandidatenliste kommen. Strategietyp, reale Trades,
   Lots/Körbe, Martingale/Grid, Risiken und Datenlücken untersuchen.
5. **Kandidaten sortieren:** aus den aktuellen berechneten Werten und dem gewählten
   Abonnenteneinfluss. KI-Widersprüche prüfen; keine freie KI-Rangzahl verwenden.
6. **Beste fünf vertiefen:** ausführliche Einzelanalysen automatisch erstellen.
   Bei neu bestätigten Ausschlussbefunden Kandidat entfernen und nächsten prüfen.
   Alte Analysen bleiben als Historie mit Grund erhalten. Weniger als fünf
   geeignete Anbieter ergeben entsprechend weniger ausführliche Berichte.
7. **Liste ausgeben:** Ergebnis und Berichte zusammen speichern, inklusive
   Bearbeitungsbilanz für alle ausgewählten Anbieter.

Ein Lauf erhält nicht nachträglich wieder das bisherige Limit von 30 Exporten
je Quelle. Quellenfehler stoppen die anderen Quellen nicht. Bei Budgetende
bleiben fertige Stufen erhalten; fehlende Kurz-/Top-5-Analysen bleiben sichtbar offen.

## 3. Die Regeln für diesen Recherchelauf

**Equity-DD inklusive Floating entscheidet.** Gemeint ist der größte relative
Rückgang der Equity vom vorherigen Hoch über das gesamte belegte Handelsfenster.
Geschlossene Tradeverluste oder Balance-DD ersetzen ihn nicht. Der höchste
gleichzeitige offene Buchverlust wird zusätzlich gezeigt, ist aber eine andere
Kennzahl. Der größte USD-DD und der größte Prozent-DD können an verschiedenen
Zeitpunkten liegen; für RetDD gilt der größte relative Prozent-DD, ungerundet.

**Hoher DD ist bei entsprechendem Ertrag zulässig.** Der bestätigte Standard
dieses Recherchelaufs hat keine feste DD-Obergrenze. Keine verdeckte 30-/50-%-Grenze
und keine erneute Sortierung nach niedrigstem DD beziehungsweise Risiko-Score.
Eine später ausdrücklich im Dialog aktivierte Grenze wäre ein abweichendes Laufprofil.

**RetDD wird eindeutig beschriftet:** Hauptvergleich ist wie im Projekt der
Jahres-RetDD/Calmar = annualisierte geometrische Rendite / gemessener maximaler
Equity-DD. Daneben stehen Zeitraumrendite und Zeitraum-RetDD. Ein-/Auszahlungen
werden mit der vorhandenen TWR-/Kapitalflusslogik berücksichtigt; fehlende
Preflow-Equity bei offenen Positionen darf nicht durch Closing-Balance ersetzt
werden. Rendite und DD benötigen dieselbe belegte Zeit- und Kapitalbasis.
Bei zwei Monaten heißt es sichtbar „annualisiert aus 2 Monaten“; die
Hochrechnung ist kein Nachweis eines tatsächlich gehandelten Jahres.

**Mindestmaterial: 2 Monate und 50 Trades.** Zeitspanne vom ersten Open bis zum
letzten Close, einschließlich Pausen; bestehende Monatskonvention
365,2425/12 Tage. Gezählt werden normalisierte abgeschlossene Positionen bzw.
belegte Exportsegmente, keine Ein-/Auszahlungen, Summenzeilen oder doppelt
gezählte IN-/OUT-Deals. 50 Segmente sind nicht automatisch 50 unabhängige
Handelsentscheidungen. Körbe und kurze Historie bleiben sichtbar; keine zusätzliche
Mindestkorbzahl erfinden und keine statistische Signifikanz behaupten.

**Kandidaten zur weiteren Prüfung:** ausreichendes Mindestmaterial, valide
Mess-/Renditebasis, positiver RetDD und keine bestätigten harten Ausschlussbefunde.
Bestehende explizite Ausschlüsse und nachgewiesenes Martingale bleiben wirksam.
Ein Verdacht ist als Verdacht zu prüfen. Fehlender SL-Nachweis bleibt neutral.
Bei nicht berechenbarem RetDD bleibt der Anbieter mit konkretem Grund sichtbar.

**Eigenes Laufprofil statt alter Ampelfilter:** Die neue 2-Monats-Regel und eine
gegebenenfalls ausgeschaltete DD-Grenze gelten gezielt für diese Rechercheliste.
Die heutige Hauptworkflow-Ampel verlangt drei Monate und berücksichtigt die
produktive DD-Schranke. Sie darf deshalb nicht als Vorfilter für die neue Liste
dienen. Gemeinsamen Rechenkern wiederverwenden, neue Policy separat versionieren
und speichern; bestehende Ampel-/RetDD-Datensätze nicht still überschreiben.
Ein Recherchekandidat ist keine neue grüne Handelsfreigabe.

**Ehrliche Messgrenze:** Die vorhandene H1-Rekonstruktion berücksichtigt Floating
der exportierten Positionen während ihrer Haltedauer, erfasst aber keine exakten
Intrabar-Tiefs. Sie beweist auch keinen aktuellen Kontobefund einschließlich heute
noch offener Positionen. Dafür sind Open-Positionen-Snapshot und Integration in
die Bewertung bis zum Stichtag nötig. Fehlen diese Daten, lautet der Status
„historisches Exportfenster; aktuelle offene Positionen nicht erfasst“.
Bei unzureichender Kurs-/Kontraktabdeckung kein Ersatz-DD aus geschlossenen Trades.

## 4. Abonnenten innerhalb der jeweiligen Quelle vergleichen

Pelican, MQL, Vantage usw. bekommen jeweils einen relativen Popularitätsrang.
Damit kann beispielsweise ein MQL-Anbieter mit 50 Abonnenten ähnlich hoch in
seiner Quelle stehen wie ein Pelican-Anbieter mit 2.000. Das ist ein Beispiel
des Prinzips, keine Behauptung über die tatsächliche aktuelle Verteilung.

Berechnet wird ein Mittelrang-Perzentil aus dem festgeschriebenen Quellenstand:
`P = 100 × (niedrigere Zähler + 0,5 × gleiche Zähler) / Anzahl gültiger positiver Anbieter`.
Gleichstände erhalten dasselbe P. Ein einzelner Anbieter oder durchgehend gleiche
Zähler ergeben P=50. Null-Abonnenten gesondert P=0; unbekannte Zähler bleiben
unbekannt. Quelle bedeutet Quellen-UID, nicht einzelner Brokername; MQL4/5 gemeinsam.

Die Referenzmenge wird vor manueller Auswahl und Risikofilterung festgelegt.
„Unter den angebotenen Top 200“ ist keine Aussage über sämtliche Plattformanbieter.
Umfang, Anzahl und Zählerstand bleiben gespeichert; Followers/Copiers verschiedener
Quellen bleiben unterschiedlich definierte Popularitätsindikatoren.

**Gemeinsame Gewichtung:** Der Roh-RetDD und eine Abonnentenzahl haben verschiedene
Skalen und werden deshalb nicht direkt addiert. Zusätzlich zu P wird E berechnet:
das Mittelrang-Perzentil des gültigen positiven Jahres-RetDD unter allen für die
Kandidatenliste auswertbaren Anbietern dieses Auftrags. Dieselbe Gleichstandsregel
wie oben verwenden. P bleibt hingegen innerhalb der jeweiligen Quellenauswahl
berechnet und wird durch spätere Forensikfilter nicht verändert.

Vorgeschlagener Startwert: **Auswahlwert = 0,70 × E + 0,30 × P**.
Die Regler müssen sich auf 100 % summieren. Diese Gewichtung ist eine
Auswahlpräferenz, kein statistisch ermittelter Qualitätsmaßstab. Ein beliebterer
Anbieter kann dadurch einen weniger beliebten mit höherem Roh-RetDD überholen;
das ist die beauftragte gemeinsame Gewichtung und muss sichtbar nachvollziehbar sein.
Original-RetDD, E, P, Gewichte und Auswahlwert werden getrennt gespeichert.
Unbekannte Popularität nicht als gemessene Null oder ausgedachtes Perzentil
einsetzen: fehlenden Auswahlbeleg nachladen oder als Datenlücke ausweisen.

Die Rangfolge muss reproduzierbar sein: Auswahlwert absteigend, dann
Original-RetDD, dann Historientiefe, schließlich stabiler Identitätsschlüssel.
Alle Kurztests und bestätigten Befunde abschließen, bevor E und die Top 5 für
den Abschluss festgeschrieben werden. Verändert ein neuer bestätigter Befund die
Kandidatenmenge, E und Rangfolge nachvollziehbar neu bilden. Währenddessen sind
Platzierungen vorläufig. Die KI entscheidet weder Gewichte noch Zahlen selbst.

## 5. Ergebnis für den Nutzer

Eine Liste **„Diese Strategien genauer ansehen“** mit Rang, Name/Quelle,
Auswahlwert, Jahres-RetDD, maximalem gemessenem Equity-DD, Rendite,
Historie/Tradezahl, relativem Abonnentenrang, Strategietyp und kurzem KI-Urteil. Datenlücken,
abgelehnte und noch offene Fälle sind in derselben Ansicht separat erreichbar.

Die **besten fünf** haben bereits jeweils einen ausführlichen Bericht: echte
Tradebeispiele, Strategie-/Positionslogik, Martingale/Grid, maximale
Equity-Verlustphase, Exposure, Erholung, RetDD, Robustheit, Kopierbarkeit,
stärkste Gegenargumente und konkrete Punkte zum Nachprüfen. Bericht direkt aus
der Zeile öffnen; kein erneutes Suchen nach Anbieter-ID. PDF und CSV anbieten.

## 6. Genau zwei Prompts im Config-Bereich

Die editierbaren Vorlagen liegen unter:

- `config/prompts/abonnenten_kurztest.md` — kompakte strukturierte Beurteilung.
- `config/prompts/abonnenten_top5.md` — ausführlicher Einzelbericht je Finalist.

Bedienung: **Einstellungen → Berichtsvorlagen → Abonnentenstatistik**,
mit beiden Vorlagen, Modellzuordnung, Pflichtplatzhaltern, Speichern und
Zurücksetzen. Beide Vorlagen sind im Admin-Editor und neuen Runner eingebunden.
Die bisherigen fünf Workflow-Prompts bleiben erhalten.

**Tradelisten tatsächlich mitgeben:** Kleine Historien vollständig übergeben.
Große Historien anhand des Modellkontexts in chronologische Segmente mit
überlappendem Rand-/Korbkontext teilen; alle Trades abdecken, nicht nur Beispiele.
Dieselben zwei Vorlagen unterstützen Segmentprüfung und Zusammenfassung.
Code prüft Trade-Referenzen und Segmentabdeckung. Fehlende Segmente bedeuten
„KI unvollständig“. Globale Forensik und Randkontext sichern die Prüfung von
Zusammenhängen über Blockgrenzen ab. Keine unveränderte Fortführung des
heutigen 250-Trade-Limits für vollständige Promptlisten.

Beide Prompts erhalten das neue Laufprofil, Codebefunde, Messstatus und echte
Trades. KI interpretiert und begründet; sie erfindet keine verbindlichen Zahlen.
Neue Auffälligkeiten werden strukturiert mit Belegreferenzen zurückgegeben und
vor einem automatischen Nachrücken überprüft. Eine KI-Vermutung allein bestätigt
keinen Ausschluss. Der ausführliche Text steht im Feld `bericht_markdown`.
Die zentrale alte Promptregel „unter drei Monaten kein Calmar“ darf nicht
ungeprüft in diese beiden neuen Vorlagen injiziert werden. Anbietertexte/PDFs
sind Quellenmaterial und keine Steueranweisungen.

## 7. Umsetzung und Abnahme

Vorhandene Downloader, vollständige Forensik, Kurscache, Equity-Rekonstruktion,
SHA-Snapshots, Budgets und Lauf-Locks werden wiederverwendet. Neu sind Dialog,
persistenter Koordinator, gezielter Quellenabruf, getrennte Analyse-Policy,
Abonnentenrang, Prompt-Builder/Editorregistrierung und Ergebnisansicht.
Der neue POST `/providers/{id}/{version}/refresh` startet einen nativen gezielten
Abruf; der Scanner wartet auf den passenden Vollständigkeits-/Frischenachweis.

Vantage verwendet im neuen Pfad den Vollhistorienabruf statt des
regulären 2.000-Trade-Limits. Robo bleibt bei unbelegter Kontowährung und
Volumeneinheit mit Grund gesperrt. Zählerfrische beweist keine Tradefrische.
Der erste explizite Start erzeugt einen eigenen Store unter
`data/abonnenten_analyse/jobs.sqlite3`. Das vorhandene Hauptdatenbankschema wird
nicht migriert. Quellenidentitäten, normale Datenartefakte und das vorhandene
KI-Kostenjournal werden über ihre bestehenden Schreibverträge genutzt.

Abnahme: ein Start löst die gesamte Kette aus; jeder ausgewählte Anbieter hat
einen Abschlussstatus; mindestens 2 Monate/50 Trades werden korrekt geprüft;
keine Closing-DD-Ersatzrechnung; hohe DD werden nur nach gewählter Grenze
behandelt; quellenrelative Abopräferenz ist nachvollziehbar; Kurz-KI deckt alle
bereitgestellten Trades ab; Top 5 erhalten ausführliche Berichte; Neustart und
Budgetende verlieren keine fertigen Stufen. Bei offenen Aufgaben kein falsches
„alles fertig“. Keine neue Zeitautomatik und kein automatischer Tradeserver-Sync.

Codebelege der Untersuchung: `app_pages/abonnenten_statistik.py:65,179`,
`app_pages/admin.py:859–958`, `src/mqlkiscanner/llm/prompts.py:34`,
`src/mqlkiscanner/portfolio_statistik.py:203–356`,
`src/mqlkiscanner/pipeline.py:342–371`,
`src/mqlkiscanner/forensics/equity_rekonstruktion.py:920–1021`,
`src/mqlkiscanner/equity_studie.py:246–253,539–589`,
`src/mqlkiscanner/trade_data.py:139–146,274–278`.
