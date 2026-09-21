# Sicherheit — MqlKiScanner

## Was nie ins Repository darf

| Datei / Ordner | Grund |
|---|---|
| `.env` | API-Keys, Passwörter |
| `config/secrets.local.json` | lokal gespeicherte Secrets |
| `data/mql5_cookies.json` | Session-Cookies = Login |
| `data/chrome_profile/`, `data/chrome_profile_accounts/` | Browser-Profile mit Login-Zustand |
| `data/*.db`, `data/trades/`, `data/trade_snapshots/`, `data/runs/` | lokale Scan-Artefakte einschließlich unveränderlicher CSV-Kopien |
| `data/downloader/` | MqlDownloader-Spiegel: Abonnenten-Verläufe + analysierte PDFs (private Nutzerdaten, nie committen) |
| `.streamlit/secrets.toml` | Streamlit-Secrets |

Alle Einträge stehen in `.gitignore`. Vor jedem Push:

```bash
git status
git check-ignore -v data/mql5_cookies.json config/secrets.local.json .env
git ls-files | findstr /i "cookie secret .env chrome_profile downloader"
```

Erwartet: Ignore greift; `git ls-files` zeigt **keine** der Secret-Dateien
(außer `.env.example` und `secrets_store.py` ohne Klartexte). **Niemals
`git add -A` / `git add .` benutzen** — unter `data/` liegen live Nutzerdaten
(Downloader-Spiegel), gezielt einzelne Dateien addieren.

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

## Lokale Dienste und REST

- **REST-API (MqlRealMonitor):** lauscht bewusst nur auf `127.0.0.1:8611`
  (kein Fernzugriff), rein lesend, bewertet nie neu. Optionaler Token über
  Env `MQLKISCANNER_REST_TOKEN` / secrets_store; Client sendet Header
  `X-User-Key` (HMAC-Vergleich, nicht im Klartext).
- **MqlDownloader / MqlTradeMonitor:** Token bzw. API-Key liegen nur im
  secrets_store bzw. als Env (`MQLDOWNLOADER_TOKEN`), nie in Einstellungen
  oder Repo (wird per `tests/test_secrets_hygiene.py` bewacht).
- Sämtliche Abgleich-/Sync-Pfade (Downloader Station 6, Tradeserver-Sync,
  REST-API, Ampel-Verlauf) schreiben **nie** Bewertungen um — Ampeln,
  Urteile und Scores ändert ausschließlich die Engine innerhalb eines
  Scan-Laufs.

## Öffentliches GitHub

Dieses Projekt ist für öffentliche Nutzung gedacht. Bevor du forkst oder
pushst: lokale Secret-Dateien prüfen, nie Screenshots mit Keys committen,
Issues ohne Session-Cookies posten.
