# Sicherheit — MqlKiScanner

## Was nie ins Repository darf

| Datei / Ordner | Grund |
|---|---|
| `.env` | API-Keys, Passwörter |
| `config/secrets.local.json` | lokal gespeicherte Secrets |
| `data/mql5_cookies.json` | Session-Cookies = Login |
| `data/chrome_profile/`, `data/chrome_profile_accounts/` | Browser-Profile mit Login-Zustand |
| `data/*.db`, `data/trades/`, `data/trade_snapshots/`, `data/runs/` | lokale Scan-Artefakte einschließlich unveränderlicher CSV-Kopien |
| `data/downloader/`, `data/quellen/` | Quellen-Spiegel und Caches: Abonnenten-Verläufe, Trade-Daten und PDFs (private Nutzerdaten, nie committen) |
| `.streamlit/secrets.toml` | Streamlit-Secrets |

Die aufgeführten Laufzeitdaten stehen in `.gitignore`. Lokale Deploy-Dateien
können ebenfalls Zugangsdaten enthalten und dürfen nicht veröffentlicht
werden; ihr konkreter Dateiname muss vor einem Push auf Ignore-Schutz
geprüft werden. Vor jedem Push:

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

- Keine Credentials oder Session-Cookies im Prompt
- Der reguläre Workflow übergibt fertige Forensik-/Kennzahlen-JSONs und
  aufbereitete Trade-Daten. Die manuell ausgelöste Tiefenanalyse erhält
  ausdrücklich den vollständigen Trade-Datensatz als JSON. Trade-Daten
  können damit an den konfigurierten LLM-Anbieter übertragen werden.
- Token-Budget je Lauf konfigurierbar

## Lokale Dienste und REST

- **Vorbereitete REST-API für MqlRealmonitor:** Die produktive Integration
  ist vorerst zurückgestellt. Die Scanner-Schnittstelle lauscht bewusst
  nur auf `127.0.0.1:8611`
  (kein Fernzugriff), ohne schreibende HTTP-Endpunkte. Ampel und Urteil werden
  aus gespeicherter Forensik mit aktuellen Einstellungen abgeleitet.
  Der REST-GET erzeugt keine PDF-Dateien. Optionaler Token über
  Env `MQLKISCANNER_REST_TOKEN` / secrets_store; Client sendet Header
  `X-User-Key` (Vergleich mit `hmac.compare_digest`). Der Token wird als
  Headerwert übertragen; der konstante Vergleich verschlüsselt ihn nicht.
- **MqlDownloader / MqlTradeMonitor:** Token bzw. API-Key liegen nur im
  secrets_store bzw. als Env (`MQLDOWNLOADER_TOKEN`), nie in Einstellungen
  oder Repo (wird per `tests/test_secrets_hygiene.py` bewacht).
- Sämtliche Abgleich-/Sync-Pfade (Downloader Station 6, Tradeserver-Sync,
  REST-API, Ampel-Verlauf) schreiben **nie** Bewertungen um — Ampeln,
  Urteile und Scores werden nicht in die Fachtabellen zurückgeschrieben.
  Die Ergebnis-/REST-Ansicht klassifiziert gespeicherte Evidenz dennoch nach
  den aktuell eingestellten Grenzen neu; neue Forensik erfordert einen Scan.

## Öffentliches GitHub

Dieses Projekt ist für öffentliche Nutzung gedacht. Bevor du forkst oder
pushst: lokale Secret-Dateien prüfen, nie Screenshots mit Keys committen,
Issues ohne Session-Cookies posten.
