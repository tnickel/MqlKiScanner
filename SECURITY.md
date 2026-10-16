# Security Policy

## Reporting

If you discover a vulnerability (e.g. accidental secret exposure, unsafe
defaults), please open a private security advisory on GitHub or contact the
maintainer — do **not** post live credentials or session cookies in public
issues.

## Secrets

Never commit:

- `.env`, `config/secrets.local.json`
- `data/mql5_cookies.json`, `data/chrome_profile/`, `data/chrome_profile_accounts/`
- SQLite DBs and trade caches under `data/`
- `data/downloader/`, `data/quellen/`, `data/trade_snapshots/` — mirrored
  source data, subscriber histories, analysis PDFs and trade snapshots
  (private user data)
- `.streamlit/secrets.toml` and local deployment files containing credentials

Use `.env.example` as a template only.

## LLM data

Configured LLM calls include analysis facts and prepared trade data. The
manually requested in-depth analysis includes the full trade dataset as
JSON. Credentials and session cookies must never be included in prompts.

## Prepared MqlRealmonitor interface

The scanner exposes a read-only REST interface on `127.0.0.1:8611`, with
optional `X-User-Key` authentication. MqlRealmonitor is not yet integrated
into production; that integration is deferred. The separate MqlTradeMonitor
sync is documented in `doc/06_tradeserver-sync.md`.

## Scope

MqlKiScanner is an **analysis tool**. It does not place trades and is not
investment advice. Automated access to mql5.com must respect their terms of
service and use the built-in rate limits.
