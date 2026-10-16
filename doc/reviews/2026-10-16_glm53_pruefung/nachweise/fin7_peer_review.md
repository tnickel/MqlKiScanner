# Unabhängige Gegenprüfung Scanner FIN7 / Identitäten

Nur lesend geprüft; keine Scannerdatei geändert. Kleine unabhängige Probes
liegen ausschließlich in diesem Auditordner. Keine Plattform, kein Terminal,
kein Login, kein LLM und keine Produktionsdaten verwendet. Die einzige echte
SQLite-Datenbank des Probes war temporär und synthetisch.

## Bestätigt und während der Prüfung minimal geschlossen

1. `pipeline.studie_anwenden` übernahm im Zwischenstand trotz
   `account_currency=None` oder `USC` aus einer SHA-passenden alten Studie
   `true_dd_usd=42` und Anzeige-DD4. Der frühe Währungscheck verhindert diese
   Übernahme jetzt. Ein fehlender Währungsbeleg wird nicht aus einem alten
   vermeintlichen USD-Ergebnis ergänzt.
2. `equity_studie_ui._cache_key` unterschied zunächst USD und USC bei gleicher
   ID/SHA nicht. Der neue Schlüssel enthält zusätzlich Währung und source_kind;
   dadurch wird der frühere Sitzungscache bei Einheitswechsel nicht weiterbenutzt.

Vorheriger reproduzierter Zustand: `fin7_peer_probe_results.json`.
Nach der Korrektur: `fin7_peer_probe_after.json`, einschließlich SHA256 der
gelesenen Source-Dateien. Das Probeprogramm `fin7_peer_probe.py` liest den
jeweiligen aktuellen Code und schreibt sein Ergebnis auf Wunsch in einen
separat benannten JSON-Beleg.

## Weitere Gegenprüfungen ohne bestätigten Restfehler

- **Feldweise Währung:** Balance USD plus Initial Deposit USC ergibt unbekannte
  Kontowährung und keine USD-Geldwerte. Dasselbe gilt für eine fehlende Einheit
  in einem vorhandenen numerischen Geldfeld. Stimmen die Geldfelder auf USD
  überein, beeinflusst EUR-/USC-Freitext außerhalb dieser Felder die Erkennung
  nicht. Keine globale USD-Suche, kein stiller USC→USD-Ersatz.
- **Vor Analyse:** Im direkten MQL-Pfad steht `require_usd_account` vor
  FX-Vorwärmung, Kursanbieter und `analyze_export`. Der Rohdownload davor ist
  kein USD-Analyseergebnis. Native Beträge und erkannte Einheit werden getrennt
  in stats_json persistiert und beim DB-Laden als account_currency wiederhergestellt.
- **Vor Terminalstart:** Einzelstudie und Batch prüfen die Einheit vor
  `KursDaten`/`starten`; der einzelne Batch-Rechenpfad prüft sie zusätzlich.
  Damit startet ein ausschließlich aus gesperrten Konten bestehender Batch
  kein Terminal. Demo-/andere Quellen behalten ihren ausdrücklich bestehenden
  Modell-/Exportvertrag.
- **Plattformkollisionen:** Der Crawler erhält beide Identitäten statt Last-wins;
  build_candidates verwirft widersprüchliche Quellen/Plattformen derselben
  numerischen ID. Gegen einen gespeicherten MT5-Datensatz wird ein neuer
  MT4-Kandidat vor HTTP/Analyse/Persistenz abgewiesen. Beide Varianten wurden
  unabhängig synthetisch aufgerufen und sind im Nachher-JSON true.

## Widerlegte Zusatzhypothese

Die Behauptung, eine normale alte v17-DB-Studie könne allein über einen
SHA-Treffer unter v18 weitergeladen werden, trifft am heutigen Stand nicht zu.
`db.get_equity_studie` und `db.list_equity_studien` filtern bereits nach
`forensics_version=FORENSICS_VERSION`. Der unabhängige Probe speichert eine
aktuelle synthetische Studie, setzt ausschließlich ihre Versionsspalte auf17
und prüft beide echten Getter: Die aktuelle Studie ist sichtbar, die alte
anschließend in beiden Gettern verborgen.

Ein direkt an studie_anwenden übergebenes ungefiltertes Dictionary kann bei
aktuell belegtem USD noch eine alte Report-Versionsangabe enthalten. Ohne
belegten Consumerpfad, der die DB-/Sitzungsversionierung umgeht, ist das kein
zusätzlicher nachgewiesener Produktfehler. Eine zweite Versionsmigration wurde
deshalb nicht als notwendiger Fix eingefordert. Die tatsächlich offenen
Währungs- und Sitzungsschlüsselpfade wurden dagegen konkret belegt und behoben.

Keine erneute vollständige Scannersuite durch diesen Peeragenten; Root führt
den finalen isolierten Gesamtlauf aus. Dieser Bericht ist ein unabhängiger
Kontrollfluss-/Gegenfallnachweis, kein Livekonto- oder Terminalfunktionstest.
