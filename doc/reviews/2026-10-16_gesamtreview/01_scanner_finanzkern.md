> Teilbericht aus `D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\waste\gesamt_review_2026-10-16\finanzen`. Relative Nachweispfade und Befund-IDs beziehen sich auf diesen lokalen Auditordner; eine ausgewählte Kopie der Belege liegt hier unter `nachweise/`.

# Scanner-Finanzkern: unabhängiges Review vom 16.10.2026

## Ergebnis und geprüfter Stand

Zwei Fehler können innerhalb der vorgesehenen Bewertungslogik ein falsches Grün erzeugen: Eine freigegebene Teilmessung überspringt auch vorhandene Floating-Verluste; die als Equity-TWR deklarierte Rendite verwendet bei Kapitalflüssen die realisierte Balance. Beide Fälle sind mit konkreten Zahlen und automatischer GMT-Erkennung reproduziert. Weitere Befunde betreffen verschluckte Gebühren, doppelte Kapitalflüsse in der Kontodiagnose, gerundete Schrankenwerte und uneinheitliche Flow-Verarbeitung.

Geprüft wurde der eingefrorene Scanner unter `D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot`, HEAD `80d4692`. Root hat diesen sauberen Snapshot mit `git archive HEAD` erzeugt; die sechs zu diesem Review erhobenen Repository-Status waren leer. Es wurden keine uncommitteten Arbeitsänderungen mitarchiviert. Zeilenangaben beziehen sich auf diesen Snapshot.

Gelesen: AGENTS.md vollständig, doc/02, doc/03, doc/22 sowie engine, parser, models, stats, scoring, portfolio_statistik, relevante Pipeline-Produzenten/Gates und sämtliche acht Forensikmodule einschließlich equity_studie, FX und Kontraktauflösung. Datierte Dokuabschnitte wurden als historische Berichte behandelt. Akzeptierte Teilmessungen, das USD-Modell, SL-Neutralität, Fix-ID-Ausnahmen und die Nutzerentscheidung zu Ein-/Auszahlungen wurden nicht als Fehler umgedeutet.

Effektiver Stand laut Root-Manifest: `listen_modus=beides`, `min_abonnenten=1`, `top_n_export=30`, `min_wochen=26`, `min_calmar_jahr=3`, `schranke_eq_dd_pct=30`, Rekonstruktion und Stufe0 aktiviert, `agenten_enabled=false`, 15 Fix-IDs. Der Code-Default für Mindestabonnenten ist hingegen 0. Diese Unterscheidung ist für die betrachtete Grundgesamtheit wesentlich. Keine laufende ältere App wurde als dieser Code ausgegeben.

## Reproduktion und Beweisgrenzen

Artefakte im selben Ordner:

- `repro_finance.py`: isolierter ausführbarer Harness; importiert ausschließlich den eingefrorenen Code.
- `results.json`: 18 synthetische Fallgruppen, einschließlich 12 expliziter Orakel-/Gegenbelegprüfungen; alle zwölf sind wahr. NaN/Infinity werden im strikten Ergebnis-JSON als Text erhalten.
- `synthetic/*.csv`, `synthetic/contract_specs.json`: ausschließlich künstliche Eingaben; keine Nutzerhistorie.

Ausführung ohne Store-Launcher:

```powershell
$env:PYTHONPATH='C:\Users\tnickel\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages'
& 'C:\Users\tnickel\AppData\Local\Programs\Python\Python312\python.exe' -u .\waste\gesamt_review_2026-10-16\finanzen\repro_finance.py
```

Requests ist im Harness gesperrt; FX-Refresh wird ersetzt, Kontraktspecs werden auf die künstliche Datei umgeleitet. Keine App, kein Login, kein MT5, kein LLM, keine Netzwerkabfrage, keine Produktionsdatei geändert. Zwei Starts des inzwischen hängenden WindowsApps-Launchers wurden abgebrochen; der obige Interpreter führte den vollständigen Harness in unter einer Sekunde aus. Root meldet für seine separate vollständige Snapshot-Suite 1.911 passed, 4 skipped und 4 deselected. Diese Suite habe ich nicht nochmals ausgeführt; sie ersetzt die unabhängigen Finanzorakel nicht.

## Bestätigte Befunde

### F1 — P1: Teilmessung verwirft auch messbare Floating-Verluste

**Anker:** [equity_rekonstruktion.py:844](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/forensics/equity_rekonstruktion.py:844), insbesondere 848, 884–885, 926–931, 982–986; Übernahme als freigegebener Nenner in `pipeline.py:1758–1761`.

**Bedingung:** Mindestens 80 % der Trades haben Kurse und Kontrakte. Ein vollständig fehlendes Symbol ist zeitgleich mit den betrachtbaren Positionen offen. Die Teil-Abdeckung und Zeitbasis bestehen die Freigabe.

**Mechanismus:** Für das fehlende Symbol wird `kurs_da=False` gesetzt. Der bereits berechnete Floating-Anteil der bekannten Symbole wird mit `messpunkt=False` an die Kurve angehängt. Die DD-Schleife überspringt diesen gesamten Punkt. `kurs_da_betrachtet` zählt dagegen als vorhandene Teilmessung; die abschließende Freigabe erklärt das Ergebnis zu `ok_teilmessung` und `verlaesslich=True`. `unbetrachtbar_aktiv` wird gesetzt, beeinflusst diese Punktfreigabe aber nicht.

**Zahlenbeleg:** Vier parallele XAUUSD-Positionen à 1 Lot, Faktor 100 USD/Preiseinheit, Entry 2.000; gemessener H1-Close 1.998. Bekannter Verlust `4 × 1 × 100 × 2 = 800 USD`, auf 1.000 USD also **80 % DD**. Ein fünfter Trade ohne Feed lässt den gemeldeten DD auf **0 %** fallen. Derselbe Kontrolllauf ohne diesen fünften Trade liefert korrekt 80 %.

Der zusätzliche lange Repro benutzt das bekannte Symbol US30 für den fehlenden Feed, automatische GMT-Erkennung **0 h, Trefferquote 100 %**, Teil-Abdeckung 100 % und eine spätere Erholung. Gemeldeter DD **1 %**, CAGR **300,9220255 %**, Calmar **300,9220255**, Ampel **grün**. Die bekannten H1-Verluste verlangen nach der 30-%-Regel **rot**.

**Gegenargument:** Fehlende Symbole dürfen laut Nutzerregel die Teilmessung freigeben und unbekannte zusätzliche Verluste bleiben ein Warnhinweis. Das rechtfertigt nicht das Weglassen der bereits gemessenen Verluste der betrachtbaren Symbole. Hier wird die akzeptierte Teilmessung fehlerhaft implementiert, nicht ihre Zulässigkeit angegriffen.

**Sicherheit:** hoch; `partial_loses_known_floating`, `partial_false_green` im Ergebnis-JSON. Das Ampel-Repro speist die tatsächlich berechneten Kennzahlen in ScanResult, ersetzt aber Kandidatenbeschaffung und bekannte Ausschlusslisten. Es führt keine komplette Scan-Pipeline aus.

**Regression/Abhilfe:** Überlappende bekannte und vollständig fehlende Symbole; als Teilmessung bekannte Floating-Verluste auswerten, Datenlöcher bekannter Symbole weiterhin sperren. Assertions sowohl für den DD-Wert als auch für den nachgelagerten roten Gate-Ausgang.

### F2 — P1: Balance-TWR wird als Equity-TWR und belastbarer Calmar freigegeben

**Anker:** [portfolio_statistik.py:79](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/portfolio_statistik.py:79), Ereignisaufbau 79–87, Teilfaktoren 119–127, Freigabe/Methodenbehauptung 272–278; `pipeline.py:334–407`, 878–902.

**Bedingung:** Ein Kapitalfluss findet während offener Positionen mit von null verschiedenem Floating-PnL statt.

**Mechanismus:** `_monatsserie` sieht nur Close-Netto, separate Kosten und Balance-Zeilen. Vor einem Flow kennt sie deshalb den realisierten Kontostand, nicht die Equity. Dennoch bezeichnet der Ergebnisvertrag die Rechnung als TWR auf der realen Kontokurve, konsistent mit dem Equity-DD, ohne Vorbehalt für das fehlende Floating am Flow. Ein anderer Bestandteil des Projekts erkennt diese Informationsgrenze bereits ausdrücklich: `equity_kapitalfluesse.py:4–7`, 171–179, 225–226.

**Zahlenbeleg:** 01.01.–01.07.2025, Basis 100 USD; vor Einzahlung Equity 80 USD; Einzahlung 100 USD; End-Equity 280 USD. Vollständige synthetische H1-Reko liefert `status=ok`, `verlaesslich=True`, Auto-GMT 0 und **20 % DD**.

- Code: Balance vor Flow 100, nach Flow 200, später 80 USD realisiertes Netto; Faktor `280/200 = 1,4`; CAGR **97,1849943 %**, Calmar **4,8592497**, **grün**.
- Unabhängige Equity-Unitisierung: `(80/100) × (280/180) = 1,244444444`; CAGR auf genau derselben Zeitbasis **55,4720956 %**, Calmar **2,7736048**, also **gelb** bei Mindest-Calmar 3.

Auch der umgekehrte Effekt ist belegt: positives Floating vor einer Einzahlung kann die Balance-TWR gegenüber der Equity-TWR zu klein machen. Es handelt sich nicht um eine stets konservative Approximation.

**Gegenargument:** Eine explizit als Closing-/Balance-Rendite definierte Kennzahl wäre berechenbar und könnte bewusst verwendet werden. Der aktuelle Code deklariert sie jedoch als dieselbe reale Equity-Kurve und gibt sie als belastbare Effizienz frei. Dass die geschlossene CSV alleine die Flow-Equity nicht bestimmen kann, ist gerade der Grund für einen fehlenden beziehungsweise qualifizierten Belegstatus. Die akzeptierte Drawdown-Hauptkurve mit Flows wird hier nicht infrage gestellt.

**Sicherheit:** hoch für falsche Definition/Freigabe und den konstruierten FalseGreen-Fall; keine Aussage darüber, wie häufig das in echten Accounts vorkommt. Repros `floating_at_flow` und `floating_loss_flow_false_green`, letztere einschließlich vollständiger H1-DD-Messung.

**Regression/Abhilfe:** Flow bei positivem, negativem und unbekanntem Floating. Renditezähler aus einer belegten, zeitlich passenden Equity-/Anteilkurve berechnen oder die Balance-Approximation ausdrücklich qualifizieren und nicht als belegten Equity-Calmar freigeben. Reale Flow-Regel beibehalten.

### F3 — P2: Gebühren in Zeilen ohne Typ verschwinden lautlos

**Anker:** [parser.py:165](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/parser.py:165), Skip bis 170. `doc/02_technik-mql5.md:57–62` verlangt ausdrücklich, dass Geldwerte ohne Typ niemals still verschwinden.

**Bedingung:** Formal vollständige CSV-Zeile, Typ leer, ausschließlich Commission und/oder Swap gefüllt. Die überprüfte Feldliste enthält weder Commission noch Swap; bei MT4 fehlen darüber hinaus SL/TP/Comment.

**Zahlenbeleg:** Basis 1.000, Tradeprofit +100; zusätzliche Type-leere Zeile Commission **−250**. Parser akzeptiert die Datei, liefert **Netto +100**, Kostenanzahl 0. Erwartet ist ein lauter Validierungsfehler; wäre die Buchung als gültige Charge belegt, wäre Netto **−150**.

**Gegenargument:** Die Zeile ist fehlerhaft; daraus darf keine tatsächliche Kostenart geraten werden. Der Befund verlangt deshalb Ablehnung, keine automatische Umdeutung zu Charge. Ein bloßer Zeitstempel bleibt wie gewünscht zulässig.

**Sicherheit:** hoch, `typeless_fee`. Ob solche defekten Gebührenzeilen produktiv vorliegen, wurde nicht behauptet.

**Regression/Abhilfe:** Beide CSV-Formate, Gebühren in jeder Geldspalte, Inhalt in weiteren Nicht-Zeitfeldern und echte timestamp-only-Zeilen. Fehlender Typ mit jedem finanziellen Inhalt muss scheitern.

### F4 — P2: Kontostudie bucht spätere Kapitalflüsse doppelt

**Anker:** [equity_studie.py:508](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/equity_studie.py:508) und 670–672; [equity_kapitalfluesse.py:200](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/forensics/equity_kapitalfluesse.py:200), Eingabevertrag 27–29.

**Bedingung:** `equity_studie.studie` enthält spätere Balance-Zeilen und ruft die zusätzliche Kontodiagnose auf.

**Mechanismus:** Die Hauptpunkte enthalten bereits `flow_delta_sum`; die Diagnostik erwartet virtuelle Punkte ohne Flows und addiert `kum_flows` erneut. Die separat berechnete `account_balance` addiert sie dagegen korrekt nur einmal.

**Zahlenbeleg aus vollständigem Studie-Aufruf:** Basis 100, PnL 0, Auszahlung 50 bei sicher flachem Konto. Hauptkurve korrekt **Equity 50, DD 0 %**. `konto_studie` dagegen **Equity 0**, Balance 50, Renditeindex 0, **DD 100 %**, gleichzeitig `status=ok` und `verlaesslich=True`. Keine Flow-Preisannahmen oder Kurslücken sind vorhanden.

**Gegenargument:** Dieser Diagnosekanal entscheidet nicht die produktive Ampel. Das begrenzt den Schaden auf Studienwerte/Interpretation; es beseitigt den Rechenfehler nicht. Bei Einzahlungen entstehen entsprechend Phantomrenditen.

**Sicherheit:** hoch, `study_double_counts_flows`.

**Regression/Abhilfe:** Den tatsächlichen Aufrufer testen, nicht nur diagnostik mit künstlich virtuellen Punkten. Ein-/Auszahlung, Flow nach Tradeende, mehrere Flows und offene Positionen. Vertrag zwischen beiden Modulen eindeutig auf dieselbe Kurvenart umstellen; Flows genau einmal buchen.

### F5 — P2: Closed-DD wird vor dem harten >30-Vergleich gerundet

**Anker:** [drawdown.py:109](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/forensics/drawdown.py:109), 110–111 und 245–247; `pipeline.py:1723`, `scoring.py:88–91`, `pipeline.py:799–801`. `doc/03:430` beschreibt ungerundete Auswahlentscheidungen.

**Zahlenbeleg:** Start 1.000; Gewinn +100; Verlust −330,044. Peak 1.100; relativer DD **30,004 %**. Ergebnis `dd_pct_max_rel=30,0`; `scoring.evaluate(..., reko_eq_dd_pct=1)` meldet **Schranke nicht verletzt**. Der strikte Vergleich verlangt wahr. Eine spätere Erholung ändert das Maximum nicht.

**Bedingung/Gegenargument:** Eine zusätzliche verlässliche H1-/Plattform-Messung oberhalb 30 würde das abfangen. Das ist kein Ersatz für einen korrekt funktionierenden eigenständigen Closed-DD-Kanal; H1 kann kurze Verluste oder Teile einer Teilmessung verpassen. Exakt 30 soll weiterhin zulässig bleiben. Kein generelles Runden-/Toleranzverbot für Anzeigezahlen.

**Sicherheit:** hoch, `dd_rounding_gate`; Wirkung eng auf Schwellenumgebung begrenzt.

**Regression/Abhilfe:** Ungerundeten Risiko-DD bis zum Gate erhalten; 29,9999 / 30 / 30,0001 und 30,004 für beide DD-Zweige testen. Anzeige separat runden. Startkapital wird ebenfalls bereits in drawdown.run auf Cent gerundet und danach an Rendite/H1 weitergereicht; für exakte Grenzfälle sollte auch dessen Rohwert erhalten bleiben.

### F6 — P2: Gültige reale Flow-Rendite wird wegen ungültiger virtueller Kurve verworfen

**Anker:** [portfolio_statistik.py:248](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/portfolio_statistik.py:248), Prüfung vor dem TWR-Zweig 252ff.

**Zahlenbeleg:** Basis 100; Einzahlung 1.000; Verlust −200, gesamte Spanne 01.01.–01.07.2025. Tatsächliches Endkonto **900 > 0**, definierter Closing-TWR-Faktor `900/1100`, Gesamt **−18,181818 %**, CAGR **−33,2980687 %**. `_monatsserie` berechnet diese Rendite. `effizienz_kennzahlen` liefert dennoch alle Renditewerte leer und `rendite_nicht_berechenbar`, weil das hypothetische Endkapital ohne Einzahlung **−100** wäre.

**Gegenargument:** Im Beispiel verhindert die negative Rendite ohnehin Grün. Das ist eine falsche Unbekannt-Klassifikation und Informationslücke, kein belegter FalseGreen-Fehler. Die Eigenkapitalentwicklung ohne tatsächliche Einzahlung darf nicht vor der Auswahl der realen Flow-Rechnung entscheiden.

**Sicherheit:** hoch, `deposit_valid_twr`.

**Regression/Abhilfe:** Virtuelle Endkapitalprüfung nur im Zweig ohne Flows; reale Flow-Kurve separat prüfen. Fälle mit positiven realen und nichtpositiven virtuellen Salden, ohne Kontoüberziehung am Flow.

### F7 — P2: Rendite hängt von der CSV-Reihenfolge gleichzeitiger Kapitalflüsse ab

**Anker:** [portfolio_statistik.py:87](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/portfolio_statistik.py:87), 115–126; Gegenvertrag zur gleichen Zeitauflösung in `exposure.py:285–296`, `drawdown.py:224ff`, `equity_kapitalfluesse.py:55–62`.

**Zahlenbeleg:** Basis 100; in derselben Sekunde Auszahlung −200 und Einzahlung +200, netto 0; später Gewinn 100. Reihenfolge Auszahlung zuerst ergibt **leere Monatsserie**. Einzahlung zuerst ergibt **+100 % Gesamt**. Tatsächliche Daten liefern keine Reihenfolge innerhalb der Sekunde; unter der bereits projektweit verwendeten Nettoflusskonvention müssten beide Ergebnisse identisch sein.

**Gegenargument:** Falls eine Quelle eine belastbare feinere Buchungsreihenfolge liefern könnte, dürfte diese verwendet werden. Das aktuelle CSV und diese Funktion besitzen diesen Nachweis nicht. Der Befund betrifft keinen berechtigten Abbruch bei eindeutig belegter echter Kontoüberziehung.

**Sicherheit:** hoch, `same_second_flows`.

**Regression/Abhilfe:** Kapitalflüsse je identischem Zeitstempel zusammenfassen; Permutationstests sowie zeitgleiche Kosten/Trade-Closes mit festgelegter fachlicher Konvention.

### F8 — P2, bedingter Eingabefehler: Nichtendliche FX-Kurse gelten als vollständige Umrechnung

**Anker:** [fx_rates.py:88](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/fx_rates.py:88), 91, 218–222; `forensics/exposure.py:189–191`, 365–368, 515–529, `scoring.py:293–304`.

**Bedingung:** Beschädigter oder manuell geänderter lokaler ECB-CSV-Eintrag `JPY=NaN` bei gültigem USD-Kurs. Nicht behauptet wird, dass die offizielle Quelle solche Werte geliefert hat.

**Repro:** `_parse_csv` akzeptiert NaN, weil `NaN <= 0` falsch ist. `usd_per` liefert NaN. Exposure zeigt **shock_usd=NaN, shock_pct_max=NaN, conversion_complete=True, temporal_risk_available=True, flag=False**. Die Forensik-Vollständigkeitsprüfung prüft diesen Wert nur gegen None. Erwartet ist unbekannte Umrechnung mit gesperrter Vollständigkeit. H1-Reko hat dagegen einen zusätzlichen Nichtendlichkeitsschutz und verwirft eine kontaminierte Kurve; dieser Gegenbeleg begrenzt unmittelbares FalseGreen.

**Sicherheit:** hoch für den Eingabepfad, offen für produktive Häufigkeit; `nan_fx_accepted`. Keine Behauptung, NaN im Plattform-DD vergifte dd_maximum: `_platform_float` sanitisiert ihn; der Gegencheck `dd_maximum(NaN,40)==40` besteht.

**Regression/Abhilfe:** NaN/±Infinity, Null, negative Kurse, ungültige Datumswerte und fehlende gleiche Cross-Daten validieren. Konsumenten müssen endliche positive Umrechnungsfaktoren und endliche Schocks verlangen. Ein Refresh sollte eine neue CSV fachlich validieren, bevor er einen guten Cache ersetzt (`fx_rates.py:134–143`); das ist zusätzlicher Codebefund, hier nicht als separater ausgeführter Netz-Repro ausgegeben.

### F9 — P2: Produktiver Portfolio-Befund verlangt weiter das alte Monats-RetDD-Gate

**Anker:** [portfolio_statistik.py:416](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/portfolio_statistik.py:416), 419–420; Injektion in Portfolio-Prompt `pipeline.py:2134–2142`.

Der ausführbare Maschinenbefund fordert weiter, `retdd_monat < 1` auch bei grünen Einzelkriterien nicht zu empfehlen. Das widerspricht der aktuellen Jahres-Calmar-Regel. Kontrollfall DD30/CAGR90 mit konsistenter geometrischer Monatsrendite **5,49441 %** wird zu Recht grün mit Calmar3 und Monats-RetDD **0,183147**; der zusätzliche Text verlangt gleichzeitig Ausschluss. Die frühere Regel steht hier nicht bloß in historischer Dokumentation, sondern im aktiven Prompt-Datenpfad.

**Sicherheit:** hoch für den Vertragswiderspruch, nicht deterministisch für das Verhalten eines konkreten LLM. Kein Live-LLM ausgeführt. `ampel_threshold_controls.exact_dd_30` ist der numerische Gegenbeleg.

**Regression/Abhilfe:** Dynamischen Hinweis an die aktuelle Einstellung binden; Test des tatsächlich befüllten Portfolio-Prompts auf konsistente Jahresregel. Root hat diesen Widerspruch ebenfalls unabhängig beobachtet; im Gesamtbericht nur einmal zählen.

### F10 — P2: Netto-Befund einer Martingale-Korbleiter enthält Bruttosumme

**Anker:** [martingale.py:108](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/forensics/martingale.py:108).

**Zahlenbeleg:** Leiter 0,01 → 0,02 → 0,04, je Trade Profit +1 und Commission −10. Brutto **+3**, tatsächlich Netto **−27**. `basket_ladder.examples[0].net` meldet **+3**. Die Leiterflagge bleibt durch diesen Fehler unverändert; betroffen ist die an Bericht/KI gelieferte Kostenaussage.

**Gegenargument:** Die allgemeine Winrate/PF im Projekt verwendet absichtlich die Brutto-Profitspalte. Dieser einzelne Schlüssel heißt jedoch ausdrücklich `net`; das ist keine allgemeine Kritik an der vereinbarten Gross-Konvention.

**Sicherheit:** hoch, `basket_net_is_gross`.

**Regression/Abhilfe:** `t.net` summieren; Test mit Commission und Swap, die das Vorzeichen wechseln.

### F11 — P3, defensive Vertragslücke: Ungültige Kontraktfaktoren bleiben „vollständig“

**Anker:** [exposure.py:86](D:/AntiGravitySoftware/GitWorkspace/SIGNALDOWNLOADER/waste/gesamt_review_2026-10-16/scanner/snapshot/src/mqlkiscanner/forensics/exposure.py:86), Konvertierung ohne fachliche Positivitäts-/Endlichkeitsprüfung. `symbols.load_specs/spec_for` validiert diesen Zahlenvertrag ebenfalls nicht.

**Bedingung:** Editierbare Spec enthält `contract_size=-100`, stress_move50, USD-Quote. Kein Nachweis eines solchen aktuellen Produktionseintrags.

**Repro:** 0,01 Lot liefert **−50 USD Schock / −5 %**, `contract_complete=True`, `conversion_complete=True`, `temporal_risk_available=True`, `flag=False`. Betrag und Vertrag sind unzulässig; ein negativer Schock ist keine Entlastung. Prozentuale Stress-Specs haben bereits eine explizite endliche positive Prüfung, absolute Faktoren nicht.

**Sicherheit:** hoch für die fehlende Abwehr, nur bedingte praktische Relevanz; `negative_contract`. Regression: ungültige Faktoren und absolute Stresswerte ablehnen beziehungsweise als unbelegt kennzeichnen; keine geheime pauschale Faktorannahme hinzufügen.

## Metrikmatrix und verbleibende Grenzen

| Kennzahl | Tatsächliche Definition / Einheit / Zeitbasis | Kosten, Kapital, Evidenz | Bewertung |
|---|---|---|---|
| Trade-Netto | `profit + commission + swap`, Konto-/Projekt-USD, Realisierung bei Close (`models.py:32–35`) | Separate Charge/Commission zusätzlich in `ParsedExport.net_total` | In Kontrollen korrekt; Eingangsvertrag muss bereits-netto Profit ausschließen, sonst Doppelzählung |
| Winrate, PF, AvgWin, Verlustserie | **Brutto-Profitspalte**; PF positive/negative Gross-Summen; BE zählt weder Win noch Loss, unterbricht Serie (`stats.py:38–67`, 100–130) | Commission/Swap ändern diese Klassifikation nicht; PF ohne Loss None, nur Loss PF0 | Bewusster Vertrag, keine Netto-Erfolgsquote; +1−10 ergibt 100 % Winrate und Netto−9. Berichte müssen dies offenlegen |
| Monatsnetto | Realisierte Nettoereignisse inklusive separater Kosten nach Close-/Buchungsmonat (`stats.py:22–26`) | Kein MTM, keine externe Einzahlung als Gewinn | Korrekte Einheit; variable offenen Positionen fehlen; vollständige Kalendermonate separat von Randmonaten behandeln |
| Geom. Monatsrendite / CAGR ohne Flows | `(End/Start)^(1/Monate bzw. Jahre)−1`, Jahr365,2425d, MonatJahr/12, exakte FirstOpen–LastClose-Spanne | Kosten netto; vorstartige Kosten bereits in Basis, außerhalb Tradefenster bewusst keine Renditefreigabe | Positiv-/Null-/Kurzhistorienkontrollen bestanden; Basis/Rohwerte sollen nicht vorzeitig gerundet werden |
| Rendite mit Flows | Unterperioden am Flow, derzeit **Closing-Balance** statt Equity | Keine Preflow-MTM-Bewertung, Flow-Ties nicht gruppiert | F2/F6/F7; derzeit kein belastbarer Equity-TWR-Nachweis |
| Closed-/Trading-DD | Max Peak→Saldo-Rückgang, getrennte USD- und Relativmaxima, Netto; gleiche Close-Zeit gebündelt | Reale Flows mit gewollter Auszahlung-Peak-Anpassung; virtuell als Zusatzdiagnose | Withdrawal-/Gleichzeitigkeit-/Kostenkontrollen korrekt; F5 Rohwertrundung |
| H1-Equity-DD | Basis + realisiertes Netto + Flows + lineares Floating je Kontrakt, H1-Bar-Ende, max relativer Peak-DD | Nur geschlossene Exportpositionen; Broker→Referenzzeit anhand Preisabgleich; mindestens95% betrachtete aktive Stunden; Teilmessung akzeptiert | F1; Roh-DD korrekt vorhanden; H1 ist kein Intrabar-/Tickmaximum und Zuverlässigkeit bezieht sich auf Modell/Abdeckung |
| Konto-/Anteilindex-Diagnose | Preflow-Equity unitisiert, bereits abgeschlossene H1-Bars, Flow-Approximation als Vorbehalt | Nichtpositive/unbekannte Flow-Equity sperrt späteren Gesamtindex; vollständige Trades nötig | Methodischer Schutz vorhanden, aber tatsächlicher Studienaufrufer verletzt Eingabevertrag (F4) |
| Floating-/Balance-DD | Negatives Floating / zeitgleiche Balance, sonst0 (`drawdown.py:54–71`) | Andere Definition als Peak-Equity-DD | Rein diagnostisch; bei nichtpositiver Balance wird0 gezeigt, fachlich als Prozent unbekannt statt risikofrei zu lesen; kein produktiver Calmar-Ersatz |
| Shock/Exposure | Nettolots je normalisiertem Symbol × Klassen-/Brokerkontrakt × fester oder entrybasierter %-Schock; Summe über Symbole | Historische Balance als Nenner, keine Equity-/Margin-Rechnung; USD oder historischer Cross am Handelstag; Opens vor Closes gleicher Sekunde konservativ | Szenario, kein empirischer Maximalverlust oder VaR; F8/F11; keine Lots quer über Instrumente als Hedge |
| Martingale | Unmittelbare je-Symbol-Nachfolger, strikt später eröffnet, Net-Loss-Vorgänger; medianRatio>1,3; oder zwei benachbarte ≥2x Korb-Schritte | Kein Mindestsample-/Signifikanz-Gate, Korbleiter beweist keine Verlustmotivation | Regel implementiert, nicht kalibrierte Wahrscheinlichkeit; F10 Net-Beschriftung; keine Flag bedeutet nur kein Treffer dieser zwei Tests |
| SL-Evidenz | direct/partial aus positiven SL-Feldern, cluster aus Verlustdistanzen, zusätzliche koordinierte Nettoverlust-Exit-Heuristik | fehlenderSL neutral; koordinierte Exits bleiben ausdrücklich kein SL-Beweis | Keine Garantie historisch immer initial gesetzter Stops; Exportfelder belegen End-/Exportzustand, keine vollständige Stop-Änderungshistorie |
| Risiko-Score | Sieben handgewichtete Dimensionen, historische Beispielkalibrierung, 1–10 | Broker/Transparenz typischerweiseDefault5; historische Balance-Schocks, Gross-AvgWin | Deskriptive Heuristik, kein Ausfallwahrscheinlichkeitsmodell; ausdrücklich kein Grün-Gate; keine statistische Validierung der Gewichte im Scope nachgewiesen |
| RetDD/Calmar | GeomMonat/ownH1DD bzw. CAGR/ownH1DD, DD in Prozentpunkten, nicht ×12 | Nur positive freigegebene eigene H1-Basis; Null/None kein Quotient; mindestens3Monate | Basisregeln in Kontrollen korrekt; F1/F2 beeinflussen valide Nenner/Zähler; Gate≥3 ist Nutzerregel, keine Zukunftsgarantie |
| Portfolio-Cluster/Overlap | Gemeinsame negative Kalendermonate; Mengen-Jaccard ab3 gemeinsamen Symbolen und≥0,3, max12 Paare (`portfolio_statistik.py:366–406`) | Schnittfenster nur Signale mit Kurve, ungewichtete Einzelhistorien; kein gemeinsamer Portfolio-Equity-Pfad | Kein empirischer Portfolio-DD, keine Tail-Abhängigkeitsmessung, keine Kausal-/Unabhängigkeitsaussage; F9 Prompt-Widerspruch |
| FOMC-Hinweis | Anteil gelisteter FOMC-Daten ohne **neue** Entries, ab70% „wahrscheinlich“ (`news.py:28–57`) | Open-Datum im Exportframe; keine Ereigniszeitzone, keine Positionshaltung während News, kein Baseline-Test | Deskriptiver Kalenderhinweis; „wahrscheinlich“ hat keine kalibrierte Wahrscheinlichkeit. Besonders bei wenigen Trades/Ereignissen kein Nachweis eines News-Filters |

Die Matrix beschreibt tatsächlichen Code und keine universell richtigen Definitionen. Die Nutzerregeln zu maximal30% DD, Mindest-Calmar3 und mindestens3Monaten sind nachvollziehbare Auswahlregeln; ihre statistische Eignung für einen noch nicht definierten Nutzen/Zielhorizont wurde hier nicht belegt.

## Statistische Designlimits für Auswahl und Prompt

1. **„Beste“ ist aktuell kein vollständig spezifiziertes Ziel.** Code trennt harte Regeln von Risiko-Score und Renditeeffizienz. Für eine Rangfolge fehlen explizites Anlegerziel, horizont, Kapital-/Liquiditätsbedarf und Verlustnutzen. Diese Gewichte dürfen weder Review noch KI erfinden. Eine nachvollziehbare Mehrkriterienübersicht ist belegbar; eine allgemeingültig optimale Rangfolge nicht.
2. **Vorselektion und Survivorship:** Abonnentenlimit, Mindestalter, aktuelle API-Kataloge, Top30 pro Quelle, maximal geladene MQL-Seiten und benannte Fix-IDs definieren eine beobachtete Auswahl, kein Gesamtuniversum. Ausgeschiedene/deaktivierte oder früh gescheiterte Systeme sind nicht vollständig repräsentiert. Fix-IDs überspringen Age/Sub-Prefilter und verbrauchen keine Slots, bestehen aber nachgelagerte Risikoregeln; diese bewusste Regel ist kein Implementierungsbug.
3. **Selection-/Lookahead-Risiko:** Heutige Abonnentenzahlen wählen rückblickend historische Gewinner aus. Eine historische Bewertung dieses Auswahlverfahrens braucht den damaligen Katalog und damals verfügbare Informationen. Preisabgleich gegen H1 kann mehrere Zeitoffsets ausprobieren; lokale Preisplausibilität ist kein unabhängiger Validierungsdatensatz. Der Code legt Zeitbasisgrenzen bereits offen; das beweist keine Out-of-sample-Modellgüte.
4. **Mehrfachsuche:** Viele Signale, Quellen, Zeitfenster und manuell begutachtete Schwellen erhöhen die Chance außergewöhnlicher In-sample-Werte. Ein hoher Max-Calmar unter den Topk ist ohne Anzahl geprüfter und ausgeschiedener Kandidaten kein Signifikanznachweis. Historische Beispielkalibrierung von Scoregewichten ist keine unabhängige Testkohorte.
5. **Effektive Stichprobe statt Tradezahl:** Zeitgleiche Körbe, überlappende Positionen und ähnliche Systeme hängen zusammen. 1.000 Teiltrades eines einzigen Risikokorbs sind keine 1.000 unabhängigen Beobachtungen. Block-/Korb-/Tagesaggregation und gemeinsame Zeitfenster sind für Unsicherheitsanalysen geeigneter als zufälliges Mischen einzelner Trades. Eine konkrete effektive N wurde im Code nicht geschätzt.
6. **Annualisierung kurzer Historien:** CAGR ist eine mathematisch korrekt annualisierte beobachtete Wachstumsrate, keine Prognose. Drei Monate Mindesthistorie verhindern die Extremfälle nicht. Ein einziges Erholungsereignis kann Calmar stark verändern; die Schätzung eines Maximum-DD hat keine stationäre einfache Standardfehlerformel. Rang-/Schwellenstabilität unter alternativen Start-/Endpunkten, H1 vs feineren Bars und Kapitalannahmen sollte sichtbar sein.
7. **Verteilungs-/Tailrisiko:** Historischer Max-DD und fixes Schockszenario messen keine zukünftige Verlustobergrenze. Gaps, Liquidität, Stop-Ausführung, Broker-/Währungsrisiken und Regimewechsel sind nicht durch einen bestandenen Martingale-/SL-Test abgedeckt. Korrelation nahe0 oder gemeinsame Instrumentmengen beweisen weder Diversifikation noch gemeinsamen Tail-Verlust. Ein schlechtester beobachteter Monat ist ein beobachtetes Szenario, kein Worst-case.
8. **Netto für Kopierer:** Provider-Commission/Swap und separate Charge werden modelliert; zusätzliche Abo-/Performancegebühren, unterschiedliche Kopierer-Spreads, Slippage, Lot-/Marginrundung und FX-Kosten sind nicht vollständig im Geom-/Calmar-Zähler belegt. Schon die einfachen Kostenänderungen können die Rangfolge verschieben. Solche Szenarien als transparente Sensitivität ausweisen, keine erfundenen tatsächlichen Kosten abziehen.
9. **Kapital, Währung und Coverage:** Die explizite USD-/nominale Stablecoin-Konvention bleibt eine Modellannahme. Ohne Kontowährung und historische Kontraktspecs ist deren wahre Vergleichbarkeit nicht bewiesen. Jahres-Calmar kann bei verschiedenen Risikobudgets/Kapitalflüssen unterschiedlich ausfallen; die gewählte Flow-HWM-Regel ist ein Projektvertrag. Die akzeptierte Teilmessung muss Namen, fehlende Anteile und potenzielle DD-Unterschätzung weiter sichtbar halten.
10. **Validierungsdesign:** Im Scope fand sich kein vollständiger Walk-forward-/Out-of-sample-Nachweis, kein Blockbootstrap mit Rangunsicherheit und keine Kosten-/Schwellen-Sensitivitätsmatrix. Sinnvolle nächste Evidenz wäre ein zeitlich eingefrorenes Auswahluniversum, klar definierter Zielwert, Training/Validierung/Test nach Zeit mit Schutz vor überlappenden Trades, danach ein unverändertes Verfahren im späteren Fenster. Das ist eine Vorschlagsrichtung, kein bereits vorhandenes Testergebnis.

## Offene Fragen und ausdrücklich verworfene Fehlalarme

- `parser.py:196/217` akzeptiert Credit und verlangt einen Betrag, fügt Credit aber weder Balances noch Costs hinzu (`263–267`). Ohne festgelegte Semantik von Brokerkredit ist nicht belegt, ob Ignorieren korrekt ist. Klären: bewusste Nicht-Eigenkapitalbuchung oder zu berücksichtigender Kreditbestand? Bis dahin kein behaupteter Nettoprofit-/Flow-Bug.
- `stats.py:38/48` und `stops.py:368ff` sortieren Loss-Streaks bei gleichen Close-Sekunden stabil nach CSV-Reihenfolge. Daraus folgt keine belegte Ausführungsreihenfolge. Dies ist eine Interpretations-/Tie-Policy-Lücke; die DD-Engine gruppiert solche Zeitstempel bereits korrekt. Keine neu behauptete harte Gate-Regel daraus.
- Positiver Brutto-Profit bei negativem Netto ist im Stats-Vertrag möglich; dies allein ist kein Fehler. Der Netto-Renditepfad verhindert positive Ertragseinstufung in einfachen entsprechenden Kontrollfällen.
- Nicht vorhandener/Null-DD wird nicht als perfekte Effizienz behandelt: kein RetDD und gelb. Vorbehaltlicher DD ist kein Grün-Nenner. Weniger als3Monate sperren belastbaren Calmar. ExaktDD30 und exaktCalmar3 sind zugelassen, knapp darüberDD30 rot beziehungsweise knapp darunterCalmar3 gelb. Die zentralen Checks funktionieren.
- Auszahlungen erzeugen im Closed-DD-Kontrollfall keinen Verlust; zeitgleiche +100/−100-Closes erzeugen keinen erfundenen Zwischen-DD; separate Charge−10 bei Basis100 erzeugt DD10%. Gebühren vor Tradebeginn werden in der Startbasis berücksichtigt und im Verlauf nicht nochmals abgezogen.
- Keine pauschale Ablehnung des vom Nutzer erlaubten H1-Modells, akzeptierter Teilmessungen, virtueller Anzeige-Basen, lokaler Bind-Adresse oder leerer lokaler Tokens. Bestehende Pelican-Fixes sind nicht Teil dieser Befundliste.

Dieses Review ist eine technische Prüfung von Zahlen, Verträgen und Evidenzstatus. Es bewertet keine konkrete Anlage als Kaufempfehlung und leitet aus historischen Kennzahlen keine zukünftige Sicherheit ab.
