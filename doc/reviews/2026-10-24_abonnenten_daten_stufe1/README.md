# Abonnentenstatistik: Stufe 1 ausschließlich Daten und Kennzahlen

Nutzerentscheidung 24.10.2026: Die KI-Arbeit stoppen und die
Abonnentenstatistik zunächst ohne KI vereinfachen. Historische Aufträge und
Antworten bleiben erhalten; es werden keine neuen KI-Analysen, Klärungen oder
Redaktionen für diese Seite gestartet.

## Daten und Darstellung

Die erste Tabelle zeigt alle Anbieter der ausgewählten Quellenbasis,
einschließlich unvollständiger Fälle. Benötigt werden vollständige verfügbare
Trade-Exporte, belegte Kontowährung und Kapitalbasis sowie historische
Kurs-/Kontraktdaten für die Floating-Equity-Rekonstruktion. Eine begrenzte oder
unbelegte Trade-Historie wird nicht als vollständig dargestellt.

Vorgesehene Kennzahlen: gemessener Abonnentenzuwachs, Skalierung durch den
Durchschnitt derselben Quelle, tatsächlich gemessener Nettogewinn und
Exportfensterrendite, maximaler gemessener Equity-DD vom Hochpunkt und RetDD.
Die zuvor ausdrücklich gewählte Gewichtung bleibt 70 % normierter Zufluss
und 30 % RetDD; sie erzeugt keine neue Handelsfreigabe. Fehlende Werte bleiben
unbekannt und werden nicht durch Null ersetzt.

Der gemessene maximale DD verwendet H1-Bar-Schlüsse einschließlich Floating
und die vorhandene Kapitalflussbehandlung. Er ist kein Nachweis vollständiger
Intrabar-Tiefs oder eines exakten aktuellen Originalbroker-DD. Eine beobachtete
DD-Null darf nur bei tatsächlich gültiger Messung als Null erscheinen; RetDD
bleibt dann mangels positivem Nenner unbekannt.

Die bisherigen Mindestdaten für Kandidatenrangfolgen dürfen in Stufe 1 eine
reine Messung nicht vorzeitig unterdrücken. Unterhalb dieser Grenzen sind
Messung und Datenvorbehalte getrennt zu zeigen. Ohne Währungs-/Kapital-/Kurs-
oder Kontraktnachweise entsteht keine erfundene USD-Forensik. Ausgewiesene
Robo-Quellenwerte bleiben von gemessenen Trade-Ergebnissen getrennt.

## Betriebsgrenzen

Der alte KI-Worker 814192 wurde um 09:55:59 MESZ nach eindeutiger PID- und
Startzeitprüfung beendet. Eine aktive Anfrage wurde nicht als kostenlos
erklärt; ihre Reservierung bleibt angerechnet. Das verwaiste Lauf-Lock darf
beim nächsten ausdrücklichen Datenstart über den vorhandenen geprüften
Lockmechanismus übernommen werden; kein lebender Halter wurde entfernt.

Ein neuer Datenstand übernimmt vorhandene geprüfte Messungen als getrennten
Auftrag. Er verändert die ursprünglichen 800 Aufgaben und ihre Zeitstände
nicht und startet keine Beschaffung. Neue oder fehlende Daten werden über den
ausdrücklichen Daten-Button geladen. Öffnen und Export der Tabelle starten
weder Plattformupdates noch Terminals oder KI.

## Prüfung und tatsächlicher Stand

707 betroffene Tests mit isolierten Daten und Netzwerk-Mocks bestanden.
Zusätzliche Datenmodus-Regressionsfälle verbieten ausdrücklich KI-, Klärungs-,
Redaktions- und GLM-Instanziierung sowie Prompt-, Budget- und Tokenreservierungen.
Geprüft sind außerdem Messungen unter den Rangschwellen, DD-Null, fehlende
DD-Basis bei vorhandener Rendite, native Fremdwährungs-Snapshots, alle
Trendidentitäten, Stop/Cleanup und getrennte Übernahme alter Daten.

Am 24.10.2026 um 10:24 MESZ wurde ein neuer reiner Datenauftrag
`9bd0327cec304a33a4639cc6eea516a8` angelegt und in der laufenden Oberfläche
ausgewählt. Er enthält 800 ursprüngliche Anbieter: jeweils 200 MQL, Pelican,
Robo und Zulu. Die damals fehlgeschlagene Vantage-Auswahl bleibt als fehlende
Quelle sichtbar; neue Vantage-Anbieter wurden beim bloßen Übernehmen nicht
hinzuerfunden.

Der übernommene Stand enthält 237 eigene USD-Nettogewinnwerte, 110 gespeicherte
DD-Werte und 51 RetDD-Werte. Diese Zahlen sind verfügbare Einzelkennzahlen,
kein Nachweis vollständiger Datensätze bei allen betreffenden Anbietern.
Es gibt 276 vorhandene Trade-Snapshots; für 275 wurde der native
Full-History-Beleg einschließlich Identität, Export-SHA und Parseranzahl
übernommen. Der Beleg bezieht sich auf das verfügbare Exportfenster.
Unvollständige Kurs-, Kapital-, Rendite- oder Quelldaten bleiben markiert.

Die geschützten Messwerte und der ursprüngliche Auftrag sind gegen den
vorherigen Stand verglichen und unverändert. Der neue Datenauftrag hat null
Tokenkosten; weder Worker noch Beschaffung wurden bei der Übernahme gestartet.
LLM-Versuchs- und Budgetledger blieben unverändert. Sichtprüfung im Browser
bestätigt die neue Stufe-1-Ansicht und den ausgewählten Datenauftrag ohne
Kurztest-/Top-5-/Redaktionsbedienung. Der tatsächliche neue Nettogewinn-/DD-
Tabellenwert eines Beispiels stimmt mit dem gespeicherten Messwert überein.

Neue beziehungsweise fehlende Daten werden erst über den ausdrücklichen
Datenstart oder die Datenfortsetzung beschafft. Der Status bleibt bis dahin
korrekt `teilweise`; es wurde keine neue Vollerfassung behauptet.

Private Betriebsbelege: `data/runs/abonnenten_daten_20261024/uebernahme.json`,
`ui_abnahme.json` und `pytest.xml`. Die Oberfläche bleibt unter
`http://localhost:8504/abonnenten_statistik` erreichbar.
