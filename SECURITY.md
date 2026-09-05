# Security Policy

## Reporting

If you discover a vulnerability (e.g. accidental secret exposure, unsafe
defaults), please open a private security advisory on GitHub or contact the
maintainer — do **not** post live credentials or session cookies in public
issues.

## Secrets

Never commit:

- `.env`, `config/secrets.local.json`
- `data/mql5_cookies.json`, `data/chrome_profile/`
- SQLite DBs and trade caches under `data/`

Use `.env.example` as a template only.

## Scope

MqlKiScanner is an **analysis tool**. It does not place trades and is not
investment advice. Automated access to mql5.com must respect their terms of
service and use the built-in rate limits.
