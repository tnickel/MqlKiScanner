# MqlKiScanner — Dokumentation

Einstieg für Menschen und Agenten. Alles Wesentliche liegt unter `doc/`.

## Lesereihenfolge

| # | Dokument | Inhalt |
|---|---|---|
| 0 | [Dieses Index](README.md) | Übersicht |
| 1 | [`01_analysen-verlauf.md`](01_analysen-verlauf.md) | Forensische Analyse-Reihe, Empfehlungen, Ausschlüsse |
| 2 | [`02_technik-mql5.md`](02_technik-mql5.md) | Endpunkte, CSV-Formate, MT4/MT5-Export |
| 3 | [`03_forensik-tests.md`](03_forensik-tests.md) | Spec der Pflicht-Tests + Scoring |
| 4 | [`04_roadmap.md`](04_roadmap.md) | Build-Plan / Status |
| 5 | [`07_benutzerhandbuch.md`](07_benutzerhandbuch.md) | Bedienung der Streamlit-App |
| 6 | [`08_architektur.md`](08_architektur.md) | Schichten, Datenfluss, Module |
| 7 | [`09_sicherheit.md`](09_sicherheit.md) | Secrets, Rate-Limits, öffentliches Repo |
| — | [`../AGENTS.md`](../AGENTS.md) | Verbindliche Regeln für KI-Agenten |
| — | [`../SECURITY.md`](../SECURITY.md) | Kurzfassung für GitHub Security |

Code-Reviews und Nachprüfungen (historisch): `05_…`, `06_…`, Ordner `reviews/`.

## Schnellbefehle

```bash
python scripts/verify_engine.py   # Anker-Checks gegen data/raw/
python -m pytest tests -q        # Unit-/UI-Tests
streamlit run streamlit_app.py   # GUI
```
