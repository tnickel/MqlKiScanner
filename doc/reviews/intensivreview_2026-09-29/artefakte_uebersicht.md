# Geprüfte Artefakte und Beleglücken — Intensivreview 2026-09-29/30

## Geprüfte Logs (vollständig oder in Auszügen)

| Log | Zeitraum geprüft | Bemerkung |
|---|---|---|
| `SignalKiScanner/data/scan_workflow.log` | 1.070 Zeilen komplett (Ziellauf 00:02:20–02:53:53) | dauerhaftes Workflow-Log (ccc383b); Vorläufer-Scan #1 (29.09. 23:32) hat KEIN Log (Feature jünger) |
| `SignalKiScanner/data/agenten_daemon.log` | komplett (3 Zeilen, 22.09.) | Daemon beendet 22.09. 12:11:58 |
| `SignalKiScanner/data/streamlit_restart.log` | komplett (23.09. 10:33, :8504) | Server lief während des Ziellaufs |
| `PelicanTrading/data/pelicanmonitor.log` | 249 Zeilen komplett (27.09. 15:21 – 29.09. 23:37) | letztes Lebenszeichen des Monitors; REST-Requests werden NICHT geloggt |
| `roboforex/data/robomonitor.log` | Existenz + mtime (28.09. 16:16) | nicht am Ziellauf beteiligt (nicht registriert) |
| `vantage/data/vantagemonitor.log` | Existenz + mtime (28.09. 16:26) | nicht beteiligt |
| `zulumonitor/data/zulumonitor.log` | Existenz + mtime (28.09. 13:52) | nicht beteiligt |
| MqlDownloader | kein Logpfad ermittelbar; :8089 im Ziellauf down (ConnectionError) | Datenverzeichnis unter SIGNALDOWNLOADER/MqlDownloader ohne Log/DB-Rest | 

## Datenbanken (jeweils Kopien, WAL berücksichtigt — Produktiv-DBs nicht geöffnet)

- `SignalKiScanner/data/mqlkiscanner.db` → Kopie `tmp/review_copy.db`
  (Tabellen: signals, forensik, analyses, ampel_verlauf, ampel_wechsel,
  quellen_artefakte, trade_files, datenquellen, subscriber_history,
  downloader_reports, tradeserver_sync_runs, agenten_laeufe/schritte/
  meldungen/steuerung, dossier_profil/beobachtungen, trade_deltas,
  markt_kontext)
- `PelicanTrading/data/abonnenten.db` → Kopie `sub_pelican/abonnenten_review.db`

## Kern-Artefakte des Ziellaufs

- `data/runs/2026-09-30_025355_970680_c65bf5cd/results.json` (933 KB, 60×68
  Felder + Station-Logs + Portfolio)
- `data/candidates.json` (103 Kandidaten, Vorfilterstand 00:02:24)
- `data/trade_snapshots/<SHA256>.csv` — 30/30 pelik + alle mql5-Snapshots,
  SHA gegen `trade_files` verifiziert; 9 Signale für die Nachrechnung
  vollständig durchgerechnet
- `data/quellen/pelik/` (metrics-JSONs + trades.csv je Kandidat)
- `data/reports/signale/…` + `data/reports/portfolio/2026-09-30-02-53-45-…`
- `data/fx_rates/eurofxref-hist.csv` (EZB bis 2026-09-29)
- Pelican: `providers.csv` (2.223), `stats/`, `signals/closed|open/`,
  `trade_dd.csv`, `fx_rates.json`, `llm_reports.json` (61),
  `data/config.json` (wirksame KI-Promptvorlage), `reports/` (PDFs)

## Code (read-only gesichtet)

- Scanner: pipeline, quellen, ingest, fix_signale, parser, stats, engine,
  scoring, ampel_matrix, regelwerk, fx_rates, kursdaten, trade_data,
  llm_runner, llm/{client,prompts,prompt_fill}, db, rest_api,
  downloader_sync, forensics/{drawdown,exposure,equity_rekonstruktion},
  app_pages/scan.py, agenten/{betreuer,scan_launcher,scheduler,tageskette,
  lock,journal,rollen,u.a.}, `__main__.py`
- Pelican: PelicanMonitorApp, api/PelicanClient, store/{DataStore,SignalStore,
  CopierDb,LlmReportStore}, model/Provider, rest/{RestApiServer,FxRates},
  report/ReportService, config/LlmSettings (11 Java-Klassen vertieft)

## In diesem Verzeichnis entstandene Prüf-Artefakte

| Datei | Inhalt |
|---|---|
| `review.md` | Gesamtbericht (Chronologie, Befunde B1–B16, Maßnahmen, 8 Antworten) |
| `nachrechnung_pruefung.py` | unabhängiger Parser + Kennzahlen (KEIN Import der Produktivmodule) |
| `nachrechnung.csv` | 173 Vergleichszeilen für 9 Signale (Produktiv ↔ unabhängig) |
| `portfolio_pruefung.py` + `portfolio_korrelation.csv` | Korrelationen aller 23 🟢/🟡 (Monat/Woche) |
| `portfolio_pruefung.md` | Diversifikationsurteil + Grenzen |
| `prompt_review.md` | Prompt-Matrix + Ersatzformulierungen |
| `sub_pelican/notes.md` | Pelican-Tiefenprüfung (Währung, Kapitalbasis, weeks, lokale KI) |
| `sub_scanner/notes.md` + `sub_scanner/*.py` | Scanner-Tiefenprüfung + 3 Prüfskripte |
| `sub_ki_agenten/notes.md`, `fall_dumps.md`, `portfolio_antwort.txt` | Prompt-/Antwort-Tiefenprüfung |
| `tmp/review_copy.db` | DB-Arbeitskopie (kann nach Abschluss gelöscht werden) |

## Beleglücken („nicht nachweisbar")

1. **Roh-CSVs der 8 Forensik-Fails** (tmpgwaul62r & Co. gelöscht; nur
   Fehlertexte in results.json/signals.last_fehler) — Parser-Artefakte nur
   als Text belegt.
2. **Individuelle REST-Requests des Ziellaufs an :8090** (Pfad/Status/Latenz)
   — PelicanMonitor loggt keine Requests; indirekt belegt über
   quellen_artefakte.fetched_at (00:05:03–12) und fx_rates.json-Abruf
   00:05:33.
3. **USC ÷100 an echten Daten** — kein USC-Konto im aktuellen Katalog;
   Codepfad + Lexo-Historie (28.09.) belegt.
4. **Volltext-Prompts des Ziellaufs** — analyses.basis ist ein Fakten-Hash;
   Vorlagen-Stand = Arbeitsbaum ccc383b (plausibel identisch, nicht archiviert).
5. **`berichte_neu`-Zustand zur Laufzeit** — Run-Konfiguration wird nicht
   archiviert; beide Wege (Toggle aus / alle Basen stale) erklären 52 Neulauf-
   Berichte.
6. **Ursache der MqlDownloader-Downtime** — externer Prozess; nur die
   URL-Divergenz Settings (192.168.178.164) ↔ Datenquelle (localhost) ist
   belegt.
7. **Abrufe der REST :8611 durch MqlRealMonitor** — kein Zugriffslog.
8. **Crash-Uhrzeit des Vorläufer-Scans #1** — zwischen 23:55:52 (letzter
   Chronik-Eintrag) und 00:01:28 (Fix-Commit); exakter Moment nicht belegt.
9. **Vollprüfung aller 52 KI-Berichte** — 4 Fälle + Portfolio vollständig,
   12 Zahlenspotchecks, Rest stichprobenartig (Menge zu groß für Volltext-
   Review in einem Durchgang).
10. **Semantik der Pelican-Metrics Total/Wins/Losses** (Lexo Total 6664 ≈
    2×(Wins+Losses)) — serverseitig, Quellcode der Plattform nicht verfügbar;
    Scanner rechnet selbst (keine Wirkung im Lauf).
