# MqlKiScanner — Dokumentation

Einstieg für Menschen und Agenten. Alles Wesentliche liegt unter `doc/`.

## Lesereihenfolge

| # | Dokument | Inhalt |
|---|---|---|
| 0 | [Dieses Index](README.md) | Übersicht |
| 1 | [`01_analysen-verlauf.md`](01_analysen-verlauf.md) | Forensische Analyse-Reihe, Empfehlungen, Ausschlüsse |
| 2 | [`02_technik-mql5.md`](02_technik-mql5.md) | Endpunkte, CSV-Formate, MT4/MT5-Export |
| 3 | [`03_forensik-tests.md`](03_forensik-tests.md) | Spec der Pflicht-Tests + Scoring |
| 4 | [`04_roadmap.md`](04_roadmap.md) | Build-Plan — Phasen 0–4, 6 (Downloader), 7 (Tiefenanalyse) abgeschlossen; Phase 5 (Betrieb) teils offen |
| 5 | [`06_tradeserver-sync.md`](06_tradeserver-sync.md) | Einmal-Sync zum MqlTradeMonitor (Protokoll v1, /api/kiscanner) |
| 6 | [`07_benutzerhandbuch.md`](07_benutzerhandbuch.md) | Bedienung der Streamlit-App (Scan-Modi, Wechsel-Protokoll, REST-API) |
| 7 | [`08_architektur.md`](08_architektur.md) | Schichten, Datenfluss, Module |
| 8 | [`09_sicherheit.md`](09_sicherheit.md) | Secrets, Rate-Limits, öffentliches Repo |
| 9 | [`19_agentenbetrieb-bauplan.md`](19_agentenbetrieb-bauplan.md) | Bauplan autonomer Agentenbetrieb — 5 LLM-Rollen, Dossiers, MetaTrader-Kursdaten (Phase A–E **komplett umgesetzt** 22.09.2026, 861 Tests; offen: V1-Attach-Test, Autostart, erster autonomer Monat) |
| — | [`../AGENTS.md`](../AGENTS.md) | Verbindliche Regeln für KI-Agenten |
| — | [`../SECURITY.md`](../SECURITY.md) | Kurzfassung für GitHub Security |

Code-Reviews und Nachprüfungen (historisch): `10_…`–`18_…`, Ordner `reviews/`.
Aktueller Review mit Korrekturen: [`18_codereview_f0b2245_2026-09-07.md`](18_codereview_f0b2245_2026-09-07.md).

## Schnellbefehle

```bash
python scripts/verify_engine.py   # Anker-Checks gegen data/raw/
python -m pytest tests -q        # Unit-/UI-Tests
streamlit run streamlit_app.py   # GUI
```
