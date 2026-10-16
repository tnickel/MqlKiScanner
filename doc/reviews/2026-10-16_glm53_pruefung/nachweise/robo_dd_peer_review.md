# Robo-DD-Provenienz: unabhängige reine Gegenprüfung

Prüfung des aktuellen Arbeitsstands, während hub_fachdoku die letzten
Aufrufpfade ergänzt. Keine Änderungen am Robo-Code und keine Liveaufrufe.

**Kein zusätzlicher belastbarer Consumer-Bypass gefunden.**

- `store/TradeDdStore` akzeptiert keine Legacywerte aus trade_dd.csv. Ein
  bestätigter Snapshot ist an Modellversion 3, Signal-/Plattformidentität,
  Yield samt Fenster und Dealcount, exakten Deal-SHA sowie Fetchgeneration
  gebunden. Ein erneuter Abruf identischer Bytes ändert die Fetchgeneration
  und entwertet damit den alten Nachweis. Ungültige/fehlende Basis ergibt null.
- Neue Basisbestätigungen entstehen in `RoboMonitorApp` nur nach erfolgreichem
  Katalogdownload. `berechneFrischenTradeDd` folgt den tatsächlichen GUI-
  Einzel-/Batch- und Stufe-0-Historyspeicherungen. Cacheanzeige ruft dagegen nur
  `readConfirmed` auf und kann keine neue Basisbestätigung erzeugen.
- `showDeals` validiert den gespeicherten Snapshot vor `equityAnzeigen` und
  aktualisiert beziehungsweise entfernt den GUI-DD-Cache. Das Badge benutzt
  anschließend diesen bestätigten Wert; unbekannte Basis wird ausdrücklich
  als unbekannt angezeigt. Kein direktes Prozent-DD aus altem Yield im Badge.
- REST `tradeDdProof` lädt Signal und identitätsgeprüfte Dealhistorie und
  verwendet `readConfirmed`; bei fehlendem Nachweis bleiben TradeEqDrawdownPct
  und TradeClosedDdPct null. Status und Bestätigungszeitpunkt sind separat
  sichtbar. Die alten CSV-Werte umgehen diesen Pfad nicht.
- Die produktive Berichtserstellung übergibt denselben Store-Nachweis an
  ReportService/SignalPayloadBuilder. Überladungen ohne Nachweis geben
  unbekannten rekonstruierten DD aus, statt ihn aus altem Yield nachzurechnen.
- Beim Stufe-0-Katalogskip wird nach frischem Dealabruf der DD-Nachweis
  ausdrücklich invalidiert; frische Deals erhalten keinen neuen DD aus der
  alten Katalogrendite.

Die neuen `TradeDdProvenanceTest`-Fälle decken beim Lesen geprüft unter anderem
Neustart, Legacy-CSV, Basis-/Fenster-/Dealcountwechsel, Deal-SHA-Wechsel,
gleiche Bytes bei neuer Fetchgeneration, unbekannte Modellversion und
Reportpayload ohne Nachweis ab. Keine doppelte vollständige Maven-Suite durch
diesen Peeragenten; hub_fachdoku/Root führen den finalen Snapshottest aus.

## Eingrenzung des pending-Hinweises

confirmFreshBasis ergänzt derzeit seine pending-Map, ohne ausgeschiedene IDs
zu entfernen. Dieser reine Storezustand ist am Code sichtbar. Ein aktueller
GUI-/REST-Gegenfall ließ sich daraus jedoch nicht belastbar ableiten:

- GUI- und Stufe-0-Katalogübernahme ersetzen die Signalliste mit setAll.
- Auch REST-Updatejobs müssen beginJob passieren; GUI-Jobs und Update können
  deshalb keinen zweiten konkurrierenden GUI-Katalog-/Downloadjob starten.
- REST sucht den Anbieter im aktuell gespeicherten Katalog; ausgeschiedene
  Anbieter erhalten darüber keinen neuen DD-Nachweis.
- Die normale Cacheanzeige erzeugt selbst keine FreshBasis-Bestätigung.

Ohne konkret erreichbaren Weitergebrauch eines ausgeschiedenen alten
Signalobjekts wäre die Behauptung einer GUI-Umgehung spekulativ. Ein defensives
Ersetzen des pending-Scopes kann sinnvoll sein, ist hier aber nicht als neuer
bestätigter Produktfehler ausgegeben. Keine unbegründete TTL-Forderung.

Ein bestätigter Snapshot ist eine gebundene Messung mit offen gelegtem
Bestätigungszeitpunkt, kein Beweis absoluter Plattformaktualität oder echter
historischer Floating-/Equityvollständigkeit. Die ROI-Basis bleibt ein Modell.
