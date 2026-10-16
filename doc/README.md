# MqlKiScanner — Dokumentation

Einstieg für Menschen und Agenten. Alles Wesentliche liegt unter `doc/`.

Dokumentationsabgleich: 16.10.2026. Für den aktuellen Aufbau zuerst
[Megaprojekt-Architektur](21_megaprojekt-architektur.md) und
[Hub-Architektur](08_architektur.md) lesen. Datierte Analysen, Konzepte und
Testzahlen dokumentieren ihren jeweiligen damaligen Stand.

**MqlRealmonitor ist noch nicht in den Gesamtworkflow eingebunden.**
Schnittstellen sind vorbereitet; Integration bleibt vorerst zurückgestellt.
PelicanWinnerLooser ist ein eigenständiges Einzelprojekt und ebenfalls noch
nicht eingebunden; eine Hub-Anbindung ist nicht implementiert.

## Lesereihenfolge

| # | Dokument | Inhalt |
|---|---|---|
| 0 | [Dieses Index](README.md) | Übersicht |
| 1 | [`01_analysen-verlauf.md`](01_analysen-verlauf.md) | Forensische Analyse-Reihe, Empfehlungen, Ausschlüsse |
| 2 | [`02_technik-mql5.md`](02_technik-mql5.md) | Endpunkte, CSV-Formate, MT4/MT5-Export |
| 3 | [`03_forensik-tests.md`](03_forensik-tests.md) | Spec der Pflicht-Tests + Scoring + Schranke (Fünffach-Maximum) |
| 4 | [`04_roadmap.md`](04_roadmap.md) | Build-Plan — Phasen 0–4, 6, 7 abgeschlossen; Phase 5 (Betrieb) teils offen |
| 5 | [`06_tradeserver-sync.md`](06_tradeserver-sync.md) | Einmal-Sync zum MqlTradeMonitor (Protokoll v1, /api/kiscanner) |
| 6 | [`07_benutzerhandbuch.md`](07_benutzerhandbuch.md) | Bedienung der Streamlit-App (Scan-Modi, Wechsel-Protokoll, REST-API) |
| 7 | [`08_architektur.md`](08_architektur.md) | Schichten, Datenfluss, Module |
| 8 | [`09_sicherheit.md`](09_sicherheit.md) | Secrets, Rate-Limits, öffentliches Repo |
| 9 | [`19_agentenbetrieb-bauplan.md`](19_agentenbetrieb-bauplan.md) | Bauplan und Umsetzungsstand des Agentenbetriebs; Phasen A–E implementiert, Daemon-Startskript vorhanden; erster vollständiger autonomer Monat noch nicht als aktuell nachgewiesen |
| 10 | [`20_konzept-multi-source-hub.md`](20_konzept-multi-source-hub.md) | Quellen-REST, Registry, Ingest und Ausbau; Monitor-DD ist Closing-DD, kein Calmar-Nenner; vollständige Composite-Identität und Betreuer-Umstellung auf Quellen stehen aus |
| 11 | [`21_megaprojekt-architektur.md`](21_megaprojekt-architektur.md) | **Gesamtdoku Megaprojekt**: 5 Quellen → Hub → MqlTradeMonitor; MqlRealmonitor und Einzelprojekt PelicanWinnerLooser noch nicht eingebunden |
| 12 | [`22_drawdown-kalibrierung.md`](22_drawdown-kalibrierung.md) | Reale MT4-/MT5-Prüfung: MQL-DD-Definition, Zeiträume, wechselnde Kurszeiten und Erhaltung identischer Positionen |
| 13 | [`23_stufe0-client-updates.md`](23_stufe0-client-updates.md) | Implementierte Stufe 0: Quellen vor GUI- und autonomen Scans parallel aktualisieren, Status und Login-Wartezustände |
| — | [`../AGENTS.md`](../AGENTS.md) | Verbindliche Regeln für KI-Agenten (inkl. kompletter Umsetzungsstand) |
| — | [`../SECURITY.md`](../SECURITY.md) | Kurzfassung für GitHub Security |

## Reviews

- [Kritische Prüfung des GLM-5.3-Reviews](reviews/2026-10-16_glm53_pruefung/README.md)
  trennt bereits behobene, zusätzliche und unbelegte Befunde; die aktuellen
  fachlichen Korrekturen verwenden Forensik-Version 18.
- [Gesamtreview vom 16.10.2026](reviews/2026-10-16_gesamtreview/REVIEW.md)
  dokumentiert die damaligen Gegenbeispiele; der
  [Behebungsnachweis](reviews/2026-10-16_gesamtreview/BEHEBUNG.md) ordnet
  Korrekturen, Regressionstests und verbleibende Grenzen zu.
- `reviews/` enthält datierte Reviews und Rohbelege, unter anderem den
  Workspace-Review vom 04.10. und Broker-/Exportprüfungen vom 10.10.
  Ihr Datum ist kein Nachweis eines heutigen Testlaufs.
- Der Intensiv-Review vom 29./30.09. liegt lokal im Workspace-Archiv
  [`../../waste/intensivreview_2026-09-29/`](../../waste/intensivreview_2026-09-29/),
  außerhalb des Scanner-Repositories. Das Archiv ist nicht Teil eines Git-Clones.
  Der zugehörige PDF-Änderungsreport liegt weiterhin unter
  [`reports/MqlKiScanner_Aenderungsreport_2026-09-30.pdf`](reports/MqlKiScanner_Aenderungsreport_2026-09-30.pdf).

## Schnellbefehle

```bash
python scripts/verify_engine.py   # Anker-Checks gegen data/raw/
python -m pytest tests -q        # Unit-/UI-Tests
streamlit run streamlit_app.py   # GUI
```
