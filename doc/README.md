# MqlKiScanner — Dokumentation

Einstieg für Menschen und Agenten. Alles Wesentliche liegt unter `doc/`.

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
| 9 | [`19_agentenbetrieb-bauplan.md`](19_agentenbetrieb-bauplan.md) | Bauplan autonomer Agentenbetrieb — 5 LLM-Rollen, Dossiers, MetaTrader-Kursdaten (Phase A–E **komplett umgesetzt** 22.09.2026; offen: Autostart, erster autonomer Monat) |
| 10 | [`20_konzept-multi-source-hub.md`](20_konzept-multi-source-hub.md) | Konzept: Signale über beliebig viele Datenquellen-REST (Kürzel je Quelle, Connection-Ampel, `listen_modus`; **Stufe 1 umgesetzt** 27.09.2026; seit 30.09. u. a. implizite Kapitalbasis, Monitor-DD in der Schranke, metrics.Broker; offen: Stufen 2–4) |
| 11 | [`21_megaprojekt-architektur.md`](21_megaprojekt-architektur.md) | **Gesamtdoku Megaprojekt**: alle 5 Quellen (MqlDownloader/Pelican/RoboForex/Vantage/Zulu) → Hub → MqlTradeMonitor/MqlRealmonitor — Diagramm, Protokoll, Ports, Testabdeckung, Ausbaustufen |
| 12 | [`22_drawdown-kalibrierung.md`](22_drawdown-kalibrierung.md) | Reale MT4-/MT5-Prüfung: MQL-DD-Definition, Zeiträume, wechselnde Kurszeiten und Erhaltung identischer Positionen |
| — | [`../AGENTS.md`](../AGENTS.md) | Verbindliche Regeln für KI-Agenten (inkl. kompletter Umsetzungsstand) |
| — | [`../SECURITY.md`](../SECURITY.md) | Kurzfassung für GitHub Security |

## Reviews

- **Aktuell:** [`reviews/intensivreview_2026-09-29/`](reviews/intensivreview_2026-09-29/)
  — End-to-End-Review des Ziellaufs 30.09. (Nachrechnung 9/9 cent-genau,
  Befunde B1–B16) **mitsamt der umgesetzten Fixes vom 30.09.**; der
  verständliche Änderungsreport liegt als PDF unter
  `reports/MqlKiScanner_Aenderungsreport_2026-09-30.pdf`.
- Frühere Reviews (Codereviews 05.–07.09., Einzelreviews 29.09.) sind
  abgeschlossen und wurden am 30.09. ausgeräumt — ihr Inhalt lebt in den
  Commit-Messages und der Git-Historie weiter.

## Schnellbefehle

```bash
python scripts/verify_engine.py   # Anker-Checks gegen data/raw/
python -m pytest tests -q        # Unit-/UI-Tests
streamlit run streamlit_app.py   # GUI
```
