# Sicherheit — MqlKiScanner

## Was nie ins Repository darf

| Datei / Ordner | Grund |
|---|---|
| `.env` | API-Keys, Passwörter |
| `config/secrets.local.json` | lokal gespeicherte Secrets |
| `data/mql5_cookies.json` | Session-Cookies = Login |
| `data/chrome_profile/` | Browser-Profil mit Login-Zustand |
| `data/*.db`, `data/trades/`, `data/runs/` | lokale Scan-Artefakte |
| `.streamlit/secrets.toml` | Streamlit-Secrets |

Alle Einträge stehen in `.gitignore`. Vor jedem Push:

```bash
git status
git check-ignore -v data/mql5_cookies.json config/secrets.local.json .env
git ls-files | findstr /i "cookie secret .env chrome_profile"
```

Erwartet: Ignore greift; `git ls-files` zeigt **keine** der Secret-Dateien
(außer `.env.example` und `secrets_store.py` ohne Klartexte).

## Laden von Geheimnissen

Reihenfolge in `secrets_store.py`: Umgebung → `.env` →
`config/secrets.local.json`. Dateien möglichst restriktiv (0600).

## MQL5-Account-Schutz

- Rate-Limiter (Abstand, Jitter, Backoff 429/503)
- Fail-Fast nach wiederholten Hard-Failures (403 / Drossel / Login-HTML)
- Export-Cache 24 h
- Kein Scraping ohne Pausen — ToS-Risiko (Accountsperre)

## LLM

- Keine Credentials und keine Roh-Trade-CSVs im Prompt
- Nur fertige Forensik-/Kennzahlen-JSONs
- Token-Budget je Lauf konfigurierbar

## Öffentliches GitHub

Dieses Projekt ist für öffentliche Nutzung gedacht. Bevor du forkst oder
pushst: lokale Secret-Dateien prüfen, nie Screenshots mit Keys committen,
Issues ohne Session-Cookies posten.
