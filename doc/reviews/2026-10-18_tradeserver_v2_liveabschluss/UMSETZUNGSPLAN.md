# Tradeserver v2 und Abschluss der Live-Datenprüfung

Nutzerauftrag vom 18.10.2026: Tradeserver um Quellenidentität erweitern,
verbleibende Daten-/Kontraktlücken bearbeiten und die tatsächlichen Dienste
und Quellbestände aktualisieren. Bestehende uncommittete Änderungen bleiben
erhalten; kein Commit/Push. Dieser Auftrag erlaubt die dafür erforderlichen
Update-POSTs, Downloads, Terminalmessungen und normalen Scan-Aufrufe.

## Arbeitsteilung

1. Server: v2 mit `(sourceUid, signalId)`, quellgebundenen Dokumenten,
   laufgebundenen Requests und atomarem Snapshotabschluss; Migration des
   Altbestands ohne erfundene heutige Quellen; Tests, Build und Deployment.
2. Kontrakte/FX: exakte Vantage-Symbole für Nikkei225 und Soybean-C messen,
   Broker-/Währungsbelege prüfen, fehlende CNH-/ETH-Umrechnungen untersuchen.
   Keine Ersatzwährungen oder angenommene Kontraktfaktoren einsetzen.
3. Quellen: MqlDownloader/Vantage und weitere veränderte aktive Clients
   testen, sichern, neu starten und ihre tatsächlichen Updates durchführen.
4. Scanner: Python-v2-Client/Snapshot/PDF-Diff, Tests; nach Abschluss der
   Quellen- und Modellarbeiten neue Kataloge, Forensik und Studien über die
   bestehenden abgesicherten Laufwege berechnen, Anzeige und Übertragung prüfen.

## Abnahme

- Gleiche externe ID verschiedener Quellen bleibt in Tabelle, PDF-Zuordnung
  und Serverpersistenz getrennt; Quellenumbenennung ändert die Identität nicht.
- Abbruch eines v2-Laufs lässt den letzten vollständigen Serverstand erhalten.
- Alte unbewiesene Studien werden nicht aus Quarantäne neu zugeordnet.
- Werte ohne vollständige Kurs-/Währungs-/Kapitalbelege bleiben gekennzeichnet;
  kein Grün aufgrund einer unvollständigen Messung.
- Produktive DD-Schranke 50 %, Jahres-Calmar 3,0 und SL-Neutralität unverändert.
- Laufende Prozesse/Deploy und Live-Datenbelege getrennt von Offline-Tests
  nachweisen; Fehler oder externe Zugangssperren konkret dokumentieren.
- Private Sicherungen, Rohtrades und Zugangsdaten liegen ausschließlich in
  ignorierten Laufzeitverzeichnissen, nicht in diesem Reviewordner.

Die bereits ausgeschaltete Automatik wird nicht allein durch ein Dienstupdate
freigegeben. Zurückgestellte MqlRealmonitor-/PelicanWinnerLooser-Integration
bleibt außerhalb dieses Auftrags.
