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
| `review.md` | Gesamtbericht (Chronologie, Befunde B1–B22, Maßnahmen, 8 Antworten) |
| `nachrechnung_pruefung.py` | unabhängiger Parser + Kennzahlen (KEIN Import der Produktivmodule) |
| `nachrechnung.csv` | 173 Vergleichszeilen für 9 Signale (Produktiv ↔ unabhängig) |
| `kapitalbasis_check.py` | **Nachtrag:** Kapitalbasis/Ertragstabelle für alle 33 Signale mit Forensik (10k- vs. implizite Basis) |
| `historien_check.py` | **Nachtrag:** prüft, ob der Trade-Export je Signal die volle Provider-Historie abdeckt (Grundannahme von B3) |
| `portfolio_check.py` | **Nachtrag:** Korrelationsmatrix **aller** 23 🟢/🟡, Instrument-Overlap, Verlustmonat-Cluster |
| `korrelationen_alle.csv` | **Nachtrag:** 226 Paare (n≥6 Monate) mit r, n, Quelle, Ampel — sortiert |
| `kapitalbasis.csv` | **Nachtrag:** 33 Zeilen Kapitalbasis/Ertrag (10k- vs. implizit), Rohdaten von `kapitalbasis_pruefung.md` |
| `historien_abdeckung.csv` | **Nachtrag:** 30 pelik-Signale: Zeitspanne, Trade-Anzahl, `Σ PnL` aus CSV ↔ Forensik |
| `portfolio_pruefung.py` + `portfolio_korrelation.csv` | Korrelationen des Empfehlungs-Trios (Monat/Woche) |
| `portfolio_pruefung.md` | Diversifikationsurteil + **voller Portfolio-Korridor** (Klumpen, Juli-2026-Cluster) |
| `kapitalbasis_pruefung.md` | **Nachtrag:** Kapitalbasis-Messung, B2/B3-Beleg, Historie-Abdeckung, Engine-Abgleich 33/33 |
| `prompt_review.md` | Prompt-Matrix + Ersatzformulierungen (Nachtrag für Stand `fc4b3b9`) |
| `antworten_check.py` + `antworten_check_out.txt` | **Nachtrag:** mechanischer Vollabgleich aller 157 Lauf-Antworten gegen die Forensik |
| `antworten_pruefung.md` | **Nachtrag:** Ergebnis dieses Abgleichs — Ampelbindung 0/52, Ertragszahlen 0 abweichend, B11-Muster 0 Treffer, SL-Regel 17/17 korrekt |
| `sub_pelican/notes.md` | Pelican-Tiefenprüfung (Währung, Kapitalbasis, weeks, lokale KI) |
| `sub_scanner/notes.md` + `sub_scanner/*.py` | Scanner-Tiefenprüfung + 3 Prüfskripte |
| `sub_ki_agenten/notes.md`, `fall_dumps.md`, `portfolio_antwort.txt` | Prompt-/Antwort-Tiefenprüfung; `fall_dumps.md` enthält die **vollständigen Forensik-JSONs** der 4 KI-Volltext-Fälle (Zitiergrundlage für `prompt_review.md`) |
| `sub_pelican/java_fixes.md` | offene Punkte auf Monitor-Seite (B18 `/reports` leer) |
| `sub_scanner/work/workcopy.db`, `sub_pelican/abonnenten_review.db` | DB-Arbeitskopien, per `.gitignore` ausgeschlossen |
| `tmp/review_copy.db` | DB-Arbeitskopie, per `.gitignore` ausgeschlossen; **nach Abschluss des Reviews gelöscht** (alle Auswertungen sind in den CSV-/MD-Artefakten festgeschrieben). Neuerstellung: `copy data/mqlkiscanner.db tmp/review_copy.db` (WAL berücksichtigen, sonst siehe Beleglücke 1) |

> **Alle vier Prüfskripte laufen aus dem Repo-Wurzelverzeichnis** (`python -m
> pytest` bzw. `python doc/reviews/.../portfolio_check.py`); sie verwenden
> repo-root-relative Pfade (`data/mqlkiscanner.db`) und scheitern aus dem
> Review-Ordner mit `sqlite3.OperationalError: unable to open database file`.

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
9. ~~**Vollprüfung aller 52 KI-Berichte**~~ — **Nachtrag:** der *mechanische*
   Abgleich aller 157 Antworten des Laufs ist erfolgt (`antworten_pruefung.md`):
   Ampelbindung, Ertragszahlen, B11-Einheitenmuster, SL-Regel und
   Abonnenten-Argument. Offen bleibt der **inhaltliche Volltext**-Review
   (Argumentation, Vollständigkeit, Ton) — dafür sind weiterhin 4 Fälle +
   Portfolio im Volltext gelesen, der Rest stichprobenartig.
10. **Semantik der Pelican-Metrics Total/Wins/Losses** (Lexo Total 6664 ≈
    2×(Wins+Losses)) — serverseitig, Quellcode der Plattform nicht verfügbar;
    Scanner rechnet selbst (keine Wirkung im Lauf).
11. **Startdatum der Provider-Konten** — die Katalogeinträge liefern `weeks` =
    `null` (B5), eine unabhängige Quelle für das Kontoanfangsdatum existiert
    nicht. Die Historie-Abdeckung (Nachtrag) stützt sich auf die Plausibilität
    des Exportverlaufs (eigener Anfangszeitpunkt je Signal, kein abgeschnittener
    Kopf, `Σ PnL` deckungsgleich mit der Forensik), nicht auf einen Abgleich mit
    Provider-Metadaten.
12. ~~**Re-Scan-Verifikation der Fixes B1–B3**~~ — **Nachtrag 30.09. 23:15:
    erledigt.** Der Ziellauf entstand 15 Stunden vor `fc4b3b9`; der
    Re-Scan-Verlauf ist in `0e1b2b8` dokumentiert (Skript
    `doc/reviews/intensivreview_2026-09-29/lauf_verifikation_b1_b3.py`,
    isoliert ohne DB-Schreiben/KI). Ergebnis: Lemonal und AccurateCopier
    sind **🔴** über die Monitor-Schranke (46,65 % bzw. 241,3 %), der
    Forensik-Ertrag liegt für 6 Ex-🟢 auf der impliziten Kapitalbasis,
    `weeks=null` und `Broker=ICMarketsLive20` sind bestätigt. B1–B3 sind
    damit **lauf- und nicht mehr nur codeverifiziert**. Nicht Teil dieses
    Laufs: der B20/B21-Code-Befund (`33c11ac`) ist separat abgenommen
    (Live-Abnahme am Bestand).
13. **Testgrün-Beleg des Commits `fc4b3b9`** — der Commit meldete 898 grüne
    Tests, hat aber einen abhängigen Test still gebrochen (B22: Fixture-Wert
    `2010→2060` geändert, Test-Mutation nicht nachgezogen). Die Zahl ist damit
    als Beleg entwertet; nach dem Fix hier im Review steht der Lauf bei
    **1068 passed, 4 deselected** (10 min). Ob weitere Commits seit `fc4b3b9`
    ähnliche Kopplungsbrüche eingeschleppt haben, ist **nicht** systematisch
    geprüft — belegt ist nur dieser eine Fall.

## Verifikation dieses Reviews

| Prüfung | Ergebnis |
|---|---|
| `pytest -q` (vor B22-Fix) | 801 passed, **1 error** (5 Tests in `test_review18_ui.py`) |
| `pytest tests/test_review18_ui.py tests/test_review15_reports.py -q` | 20 passed |
| `pytest -q` (nach B22-Fix) | **1068 passed, 4 deselected** in 598,86 s |
| Gegenprobe der neuen Trefferprüfung (Mutation testweise zurückgesetzt) | schlägt mit `AssertionError: Stop-Mutation … greift nicht — Fixture … geändert?` fehl, statt mit einem irreführenden `stop_evidence`-Fehlschlag |
| `portfolio_check.py` / `kapitalbasis_check.py` / `antworten_check.py` | exit 0 (aus dem Repo-Wurzelverzeichnis) |
| Produktionscode verändert? | nein — `git diff --stat -- src app_pages tests config` zeigt nur `tests/test_review18_ui.py` |
