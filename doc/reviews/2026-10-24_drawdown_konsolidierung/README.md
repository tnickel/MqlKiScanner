# Kritische Nachprüfung: Drawdown und Duplikate

Stand: 24.10.2026. Ausgangscode: `1728fad74a1b85363a6d99a5317d7dcda00e00b9`.
Auftrag: vorgelegtes GLM-5.3-Review unabhängig prüfen und bestätigte Probleme
beheben. Das Fremdreview ist Prüfmaterial, kein Laufnachweis und keine
zusätzliche Freigabe für Produktivaktionen.

Original: `KI_REVIEW_ORIGINAL.txt`, SHA256
`528fdd54deede0b6068226aeb56f5dd4fa1b7c4e2eb1730009fa9b6099b9601c`.

## Ergebnis je Befund

| Befund | Eigene Prüfung und Umsetzung |
| --- | --- |
| D1: Closing-DD im Risikorechner, Anteil statt Prozent | Bestätigt. `closed_dd` delegiert an `drawdown.konto_drawdown` und liefert ungerundete Prozent. Neue Ergebnisse tragen `closed_dd_unit=percent` und `closed_dd_version=2`. Oberfläche und PDF lesen über genau einen Adapter; ungetaggte Altwerte werden einmal von Anteil in Prozent umgerechnet und als alte Berechnung markiert. Zusätzlich zwei tatsächliche Rechenfehler gefunden, siehe unten. |
| D2: H1-Rekonstruktion und Studie | Gemeinsame Peak-/Flow-/Messpunktlogik bestätigt und nach `forensics/drawdown_core.py` verlegt. Die Erzeugung der Kurven bleibt getrennt: Zeitbasis, Startanker und Teilabdeckung sind nicht identisch. Eine bloße Zusammenlegung der vollständigen Funktionen würde fachliche Regeln ändern. |
| D3: doppelte DD-Berechnung im Modell | Bestätigt. `rekonstruiere(include_curve=True, compute_dd=False)` liefert Kurve und Abdeckung ohne vorgerechnete DD-Felder. Das Modell misst danach einmal mit seinem ausdrücklich abweichenden Startanker vor den Vorabkosten. Minimum/Modellinsolvenz bleiben eigene Diagnostik. |
| D4: Closing, Flow-Kurve, Diagramm | Die Peak-Messung ist zentralisiert; das Closing-Ausgabeschema wird einmal formatiert. Absolutes und relatives Maximum bleiben unabhängig. Der aktive Kontrollbericht enthielt einen weiteren, im Fremdreview ausgelassenen DD-Rechenweg; auch dieser verwendet jetzt den gemeinsamen Adapter. |
| D5: Feed-Fallback | Gemeinsame Wechsel-/Reset-Mechanik, Einzelfeed-Wrapper und Qualitätsfunktionen in `forensics/feed_auswahl.py`. Die Behauptung eines unkontrollierten verschachtelten Fallbacks ist nicht belegt: Einzelfeed-Wrapper verhinderten bereits innere Wechsel. Fehlende Symbole ergänzen und vollständige Feeds vergleichen bleiben verschiedene Schritte. Konto- und Modell-Abnahme haben bewusst verschiedene Anforderungen. Nach einem Lesefehler nach Feedwechsel erfolgt jetzt ebenfalls ein Reset; der ursprüngliche Fehler bleibt erhalten. |
| D6: Zahlen, JSON, FX, Implementierungsliste | Nur gleiche Verträge vereinheitlicht: strenge endliche Rechenzahlen und JSON-Normalisierung in `zahlen.py`, historische Währungsumrechnung als reiner Tabellenzugriff in `fx_rates.usd_per_table`. Offline-Modus ruft weder Refresh noch Netzwerk auf. Die Behauptung neun identischer Zahlenhelfer bzw. zweier identischer JSON-Helfer ist falsch: Text-/Locale-/Native-Parser haben andere Regeln; der bisherige Daten-JSON-Helfer konnte bereits Mapping/NumPy/Datum/Set behandeln. Die explizite `__file__`-Liste ist notwendige Wiederverwendungsprovenienz und wurde um die neuen Abhängigkeiten ergänzt. |

## Zusätzlich nachgewiesene Rechenfehler

Beide Fehler betrafen den Risikorechner und den aktiven Kontrollbericht;
der bestehende zentrale Scanner-Closing-DD verwendete bereits die richtige
Regel. Die Korrektur ist daher keine neue fachliche DD-Regel.

1. **Einzahlung nach Verlust:** Start 1.000, Verlust 100, Einzahlung 1.000,
   Verlust 500. Der neue Kontohöchststand ist 1.900; der maximale Rückfall
   beträgt `500 / 1900 * 100 = 26,315789… %`. Die alten separaten Schleifen
   erhöhten den vorherigen Peak künstlich auf 2.000 und meldeten 30 %.
2. **Gleicher Zeitstempel:** Gewinne 1.000 und Verluste 500 zur selben
   Exportsekunde sind zusammen ein Ergebnis von +500. Ohne belegte Reihenfolge
   darf aus der CSV-Reihenfolge kein Zwischenhoch abgeleitet werden. Der
   Closing-DD dieses Beispiels ist 0 %; die alte Reihenfolge konnte 25 % ergeben.

Regressionen prüfen beide Gegenbeispiele sowie getrennte Maxima: ein Verlust
von 600 bei 1.000 Kapital entspricht 60 %, ein späterer Verlust von 150 bei
200 Kapital dagegen 75 %. Größter USD-Verlust und größter relativer DD dürfen
nicht verwechselt werden.

Der Risikorechner verwendet zudem die ungerundete aufgelöste Kapitalbasis für
Closing- und H1-Kurve. Eine zuvor mögliche Zwischenrundung des Startkapitals
entfällt. Der Kontrollbericht behält seine dokumentierte Anteil-Ausgabe;
die Umrechnung geschieht an dessen Ausgabegrenze.

## Bewusst erhaltene Unterschiede

- Fehlende Floating-Messpunkte werden nicht als Messung behandelt; Flüsse
  werden bis zum nächsten vollständigen Punkt mitgeführt.
- Nur negative Nettoflüsse senken den Peak; Einzahlungen heben ihn über den
  tatsächlichen Kurvenwert. Das ist die bestehende Projektregel, keine neue
  zeitgewichtete Rendite-Definition.
- Closing-Diagnostik verwendet bei Verlust ohne positiven Peak weiterhin
  100 %; H1 und Unterwasserdiagramm behalten ihre abweichende Konvention mit
  separater Kapitalgültigkeitsprüfung. Der Kern macht diese Auswahl explizit.
- Die inverse DD-Ankerrechnung zur Kapitalabschätzung, der TWR-Renditeindex
  und Floating-Diagnostik beantworten andere Fragen und bleiben eigenständig.
- Historische Referenzskripte unter `scripts/reference/` bleiben unabhängige
  Vergleichsrechnungen; sie sind keine aktiven Produktionsrechenwege.
- Modellkapital bleibt eine Annahme. Weder Refactoring noch ein kompletter
  Closing-Export belegen exakte historische Floating-Tiefs oder Intrabar-DD.

## Prüfungen

Die Tests laufen mit isolierten Einstellungen/Datenpfaden, Fake-Kursanbietern
und blockierten HTTP-Anfragen. Kein echter KI-Aufruf oder MetaTrader-Start.

| Prüfung | Ergebnis | Lokaler Nachweis |
| --- | --- | --- |
| Breite betroffene Regression: Kapital, Closing/H1, Studien, Risiko, Abonnenten, Rendite/RetDD, Ampel/Pipeline, Kosten/Parser, FX, Feed | 1.614 bestanden | `data/runs/drawdown_review_20261024/pytest_gesamt.xml` |
| Abschließende Gegenbeispiele sowie neue/alte Prozentwerte in PDF und Streamlit-AppTest | 9 bestanden; teilweise Wiederholung der obigen Suite, nicht addieren | `data/runs/drawdown_review_20261024/pytest_abschluss.xml` |
| DD-Kern vor und nach Umbau | jeweils 292 bestanden; mit Zusatz-/Integrationstests abschließend 325 bestanden | `data/runs/dd_refactoring_20261024/dd_core_*.xml` |
| Synthetische Differenzprüfung gegen eingefrorenes `1728fad` | 15.000 Closing-/Kontoflow-/Chart-Fälle und 600 vollständige H1-/Studienfälle ohne Abweichung bestehender Ergebnisfelder | `data/runs/dd_refactoring_20261024/dd_core_differential.json`, `dd_h1_study_differential.json` |
| Reale historische Exporte, nur Parser und Closing-DD | alle neun Exporte mit 4.898 Trades unverändert; vier Cent-Anker exakt: Gold Spike MT4 157,20 USD, KiraCat 2.117,70 USD, Gold Reaper 319,49 USD, MSC Gold 76,83 USD | `data/runs/dd_refactoring_20261024/dd_real_exports_differential.json`; Prüfer `check_real_exports.py` daneben |
| Feed-Fallback einschließlich Fehler-/Reset-Fälle | 95 bestanden | `data/runs/drawdown_review_20261024/pytest_feed.xml` |
| Zahlen/JSON/Offline-FX einschließlich Einbindungen | 280 bestanden | `data/runs/drawdown_review_20261024/pytest_helpers.xml` |
| Risikorechner nach PDF-Textkorrektur | 16 bestanden | `data/runs/drawdown_review_20261024/pytest_risiko_pdf.xml` |
| Abschließender Risikorechner einschließlich ungerundeter Kapitalbasis und Integrationsfällen | 26 bestanden; überlappt mit obigen Testläufen | `data/runs/drawdown_review_20261024/pytest_risiko_abschluss.xml` |
| PDF-Sichtprüfung | beide synthetischen Berichte, je vier Seiten, alle acht Seiten gerendert und gesichtet; beide zeigen 2,00 %, nur Altstand trägt Hinweis | `data/runs/drawdown_review_20261024/risiko_pdf_pruefung.json` |

Ein bereits vor dem Umbau fehlschlagender Test in `test_fx_rates.py` erwartete
noch einen Abbruch bei fehlender Einzahlung. Er wurde an die bereits zuvor
beauftragte zentrale 10k-Modellfallback-Regel angepasst: Modellkennzeichnung
und unvollständige Kapitalhistorie müssen ausdrücklich erhalten bleiben.
Dies ist kein durch das Refactoring neu eingeführter Kapitalfallback.

## Versionierung und Betrieb

Die bestehenden Scanner-/H1-Ergebnisse bleiben im Alt-/Neu-Vergleich gleich;
`FORENSICS_VERSION` bleibt 22. Die korrigierten eigenständigen
Risikorechner-Ergebnisse tragen Closing-Version 2. Alte Werte werden lesbar
gemacht und gekennzeichnet, nicht automatisch als neu berechnet ausgegeben.
Der Modellworkflow berücksichtigt die neuen Dateien in seinem Implementierungs-
Fingerabdruck, bevor ein künftiger expliziter Lauf Ergebnisse wiederverwendet.

Diese Abnahme gilt für Quellcode und lokale Tests. Keine Neubewertung der
800 produktiven Anbieter, kein KI-Neustart, keine Quellenupdates, keine
Datenbankmigration und keine Veränderung historischer Ergebnisse. Die lokalen
privaten Test-/PDF-Belege werden hier referenziert, nicht als Kontodaten ins
Repository kopiert.
