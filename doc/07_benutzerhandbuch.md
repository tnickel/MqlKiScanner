# Benutzerhandbuch — MqlKiScanner

Streamlit-App zum Scannen und forensischen Bewerten von MQL5-Signalen
(MT4 + MT5). **Risiko vor Ertrag.**

## 1. Installation

Voraussetzungen: Python 3.11+, Chrome (für MQL5-Login/Export-Fallback).

```bash
git clone https://github.com/tnickel/MqlKiScanner.git
cd MqlKiScanner
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

Windows-Schnellstart: `start.bat` doppelklicken (legt ggf. venv an und
startet Streamlit unter http://localhost:8501).

## 2. Geheimnisse setzen

Niemals Zugangsdaten in den Code legen. Eine der Varianten:

1. `.env.example` → `.env` kopieren und füllen, oder
2. in der App unter **Einstellungen / Admin** GLM-Key und MQL5-Login setzen
   (landet in `config/secrets.local.json`, gitignored).

| Geheimnis | Env |
|---|---|
| GLM / Z.ai API-Key | `GLM_API_KEY` |
| MQL5-Benutzer | `MQL5_USER` |
| MQL5-Passwort | `MQL5_PASS` |

Ohne MQL5-Login: Testdaten-Modus mit `data/raw/` (Engine ohne Live-Abruf).
Ohne GLM-Key: Scan und Forensik laufen, KI-Berichte entfallen.

## 3. Workflow (Scan-Seite)

1. **Starte Workflow** — holt Signallisten (MT4+MT5), filtert, exportiert
   Trades der Top-N, rechnet Forensik, speichert in SQLite.
2. Optional: **KI-Berichte** (Trade-/Risiko-Analyse parallel, dann Gesamtbericht).
3. Einstellungen: Listen-Seiten, Max. Signale gründlich prüfen (Standard 30),
   Mindestwochen, Abonnenten, Rate-Limits.

### Ampel

| Symbol | Bedeutung |
|---|---|
| 🟢 | Kandidat (Forensik ok, Score &lt; 5, Ertrag ok, Schranke frei) |
| 🟡 | Beobachtung / kein Kandidat |
| 🔴 | Schranke / Martingale / hartes Risiko |
| ⛔ | Auf Ausschlussliste |
| ⚪ | Vorprüfung oder Fehler (kein vollständiger Export) |

## 4. Ergebnisse

- Quelle: aktueller Lauf, Archiv-Run oder **Datenbank (alle Berichte)**.
- Spalte **Stand=NEU** markiert frisch aktualisierte Signale.
- Detailansicht: Kennzahlen, Forensik, LLM-Texte, Link zur MQL5-Seite.

## 5. Typische Stolpersteine

| Symptom | Ursache / Hilfe |
|---|---|
| MT4-Export 404 | Behoben: MT4 nutzt `/export/history`, nicht `/positions` |
| „Kein CSV / Login-HTML“ | Session abgelaufen → Admin „MQL5-Login testen“ |
| GLM 1113 Insufficient balance | Falscher Z.ai-Endpunkt (Coding vs. Pay-as-you-go) |
| Viele „mit Fehlern“ | Export fehlgeschlagen — Log in Schritt 3 prüfen |
| Nur Vorprüfung | Kein Login oder Export übersprungen |

## 6. Verifikation

```bash
python scripts/verify_engine.py
python -m pytest tests -q
```

Die Engine muss die dokumentierten Ankerwerte aus der Analyse-Reihe
reproduzieren (siehe `doc/01_analysen-verlauf.md`).
