# Codereview 04.10.2026 — PAKET B (DB, Abläufe, Agenten, GUI, LLM, Exporte)

Projekt: SignalKiScanner (`D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner`)
Prüfer: Subagent PAKET B · Nur-lesende Analyse, keine Apps/Tests gestartet, kein Netzwerk/LLM/MT5.

## 0) Manifest & Abdeckung

- HEAD: `85dc290` („fix: Quellen-Werte als Strings mit Dezimalkomma …").
- Working tree dirty: `README.md`, `doc/21_megaprojekt-architektur.md` (modified);
  untracked: `=2076`, `doc/reviews/`, `output/`.
- Vorhandene Fixes (git log F1–F9, B1–B26, Lauf-Review-13, B24–B26, GMT/Dedup,
  Zeitbasis) wurden nicht neu gemeldet; geprüft wurde, ob sie wirklich greifen.

Geprüfte Dateien (ganz oder in Kernausschnitten): `app_pages/scan.py`,
`app_pages/ergebnisse.py` (Streif), `app_pages/agenten.py`, `app_pages/equity_studie.py`,
`app_pages/automatik.py` (Streif), `streamlit_app.py`,
`src/mqlkiscanner/scan_worker.py`, `pipeline.py` (crawl/build/analyze/run_llm/
run_portfolio/results_from_db/ampel_for-Bereiche), `llm_runner.py`,
`llm/client.py`, `llm/prompt_fill.py`, `llm/prompts.py` (Struktur),
`agenten/{scheduler,lock,journal,tageskette,scan_launcher,betreuer,melder,chef,
destillation,rollen_prompts,daemon,ui_tree,__main__}.py`, `ampel_verlauf.py`,
`rest_api.py`, `db.py`, `tradeserver_sync.py`, `tradeserver_client.py`,
`config/prompts/*.md` + `config/prompts/agenten/*.md` (grep + AST-Vergleich),
`tests/test_intensivreview_fixes.py`, `tests/test_agenten_rollen.py` (Sync-Deckung).

Nicht vertieft (fremder Fokus): `forensics/*`, `ingest.py`/`quellen.py`-Interna,
`pdf_reports.py`-Rendering, `admin.py`, `equity_studie_ui.py` (nur Muster),
`downloader_sync.py` (nur Aufrufstellen).

## 1) Befunde

### B1a [P1 · BESTÄTIGT] Autonomer Full-Scan ignoriert berichte_neu/llm_aktiv — KI-Berichts-Auswahl divergiert von der GUI

GUI (Full-Scan, Standard-Toggles): Signale mit basis-aktuellem Gesamtbericht
werden aus der DB restauriert und NICHT neu erzeugt:

- `app_pages/scan.py:898-904`
  ```python
  if kandidaten and not neu_erstellen:
      jobs = []
      for r in kandidaten:
          if not pipeline.restore_current_reports(r, cfg):
              jobs.append(r)
  ```
- KI-Station überhaupt nur bei `config.llm_aktiv(run_config)` (`scan.py:1124-1128`).

Launcher: `jobs = [r for r in ergebnisse if r.forensik_vorhanden and not
r.fehler and source_kind=="live"]` und direkt `run_llm(jobs)`
(`agenten/scan_launcher.py:269-281`) — `llm_runner.run_llm` filtert nur
live+forensik und regeneriert bedingungslos alle 3 Prompts je Signal
(`llm_runner.py:23-24,58`); ein `berichte_neu`-Restore-Filter existiert dort
nicht. `config.py` hat keinen Default für `berichte_neu`; der Launcher liest
ihn auch nicht.

Auswirkung: Der autonome Full-Scan (1. Werktag des Monats) erzeugt ALLE Berichte
neu — 3 LLM-Calls je Signal × ~30–60 Signale, bis 200.000 Tokens je Lauf
(`pipeline.py:1098`, `llm_max_total_tokens`) — obwohl der GUI-Pfad basis-aktuelle
Berichte wiederverwendet. Berichtschurn verändert auch den Portfolio-Prompt
(neue Gesamtberichte → anderes Portfolio), und `llm_stufe1/llm_stufe2=off`
als gespeicherte Einstellung wird vom Launcher nicht respektiert. Selektions-
divergenz GUI vs. autonom = laut Prüfauftrag P1.

Fix (geringes Risiko): im Launcher vor `run_llm` denselben Filter wie
`w_run_llm` anwenden (restore_current_reports, respektiert
`settings.get("berichte_neu")`, Default False) und `config.llm_aktiv(settings)`
als Gate. Teilscan unberührt (beide erzwingen berichte_neu=True — Parität dort
gegeben).

### B1b [P2 · BESTÄTIGT] MQL5-Login-Anforderung: GUI prüft vor der Slot-Auswahl und degradiert, Launcher prüft danach und bricht ab

- GUI: `app_pages/scan.py:793` `hat_mql5_direkt = any(not c.get("quelle_kuerzel") for c in cands)`
  — über die Kandidaten VOR `waehle_fuer_export`; ohne Credentials nur Log
  „Vorprüfung" und Weiterlauf (`scan.py:797-799`).
- Launcher: `agenten/scan_launcher.py:216` `braucht_mql5 = any(... for c in scope)`
  — über den Scope NACH top_n; ohne Credentials `return {"status": "skipped"}` (`:219-227`).

Auswirkung: (a) Ein MQL5-Direkt-Kandidat ohne Top-N-Slot treibt die GUI zum
Login, den Launcher nicht — bei identischem Bestand unterschiedliche Laufpfade.
(b) Ohne Login liefert die GUI ⚪-Vorprüfungen (Ergebnisse in DB), der autonome
Lauf liefert nichts. Keine Bewertungsdivergenz (beide ohne Forensik), aber
Verhaltensdivergenz mit Folgewirkung über B2a (Skip → Retry-Loop).

Fix: einheitlich auf `scope` prüfen; Degradation (GUI) vs. Abbruch (Launcher)
bewusst entscheiden und im Modus-Vertrag dokumentieren.

### B2a [P1 · BESTÄTIGT] Fehlgeschlagene autonome Scans: Retry ohne Backoff/Cap — Full-Scan ignoriert den eigenen Tages-Merker

- `agenten/scheduler.py:169-172`
  ```python
  _, full_termin = job_termin(settings, "fullscan")
  if (jetzt.day <= 7 and jetzt.weekday() < 5 and minute >= full_termin
          and not scan_launcher.scan_monat_gestartet("full", monat=monat)):
      modi.append("full")
  ```
  `scan_heute_gestartet("full", tag)` wird NICHT geprüft — einziger Verbraucher
  des Full-Tages-Merkers ist der Chef-Trigger (`scheduler.py:130`).
- Der Exception-Pfad setzt ihn aber mit explizitem Anspruch:
  `agenten/scan_launcher.py:136-139` „Tages-Merker auch im Fehlerfall: kein
  30-Sekunden-Retry-Loop." — für `full` WIRKUNGSLOS, weil `faellige_scans` ihn
  nie liest.
- F4/B8-Pfade (`status=skipped`, `geprueft==0`) setzen bewusst KEINE Merker →
  nächster 30-s-Takt startet den nächsten Versuch (jeweils voller
  Listen-Crawl + Kandidaten + Login-Prüfung).

Auswirkung: Bei persistentem Grund (Login falsch, alle Quellen down, ID-Kollision
im Scope) entsteht eine Endlos-Schleife: Sonntag-Teilscan 12:00–24:00 bzw.
Full-Scan an jedem Werktag 1.–7. des Monats, je Versuch MQL5-Listenlast
(ToS-Regel AGENTS.md 6), eine `agenten_laeufe`-Zeile UND eine P2-Postfach-
Meldung (`scan_launcher.py:79-82, 94-98`) — Postfach-/Journal-Spam im
Minutentakt; kombiniert mit B1a bis zu 200k Tokens je Vollversuch (das
Agenten-Tagesbudget 500k gilt für Scan-Läufe nicht, `pipeline.py:1098` vs.
`betreuer.py:123-128`).

Fix (geringes Risiko): (1) in `faellige_scans` zusätzlich
`not scan_launcher.scan_heute_gestartet("full", tag=tag)` prüfen — macht den
Kommentar wahr; (2) Wiederholungs-Deckel je Modus+Tag (Steuerungsschlüssel
`scan_<modus>_versuche`, z. B. max 3, danach eine P2-Meldung „manuell prüfen"
und Ruhe). Gilt symmetrisch für gelbgruen-`geprueft==0`/skip.

### B2b [P3 · BESTÄTIGT] Scan-Läufe teilen die Rollen-Kennung „dirigent" mit dem Dirigent-Tageslauf

`scan_launcher.starte_scan` schreibt `journal.lauf_starten("dirigent",
quelle="daemon")` (`scan_launcher.py:65`); `faellige_rollen` fragt
`journal.lauf_heute_erfolgreich("dirigent", "daemon")` (`scheduler.py:115`) —
gezählt wird JEDER Terminal-Status. Startet der Daemon am Full-Scan-Tag erst
nach `start+60` und endet der Scan schnell mit `skipped`, gilt der Dirigent-
Tageslauf (Lagestatus/Code-Plan) als erledigt, ohne dass er lief.
Fix: Scan-Läufe unter eigener Rolle (z. B. `rolle="scan"`) führen oder
`lauf_heute_erfolgreich` nach Schreiber differenzieren.

### B2c [P3 · GRENZE] Kalenderlogik auf naive lokaler Zeit

`datetime.now()` überall (`scheduler.py:112,182` u. a.) — Europe/Berlin gilt nur
über die Rechnerzeitzone; DST-Fälle (23-/25-h-Tage) sind dadurch korrekt,
SOLANGE der Rechner in Berliner Zeit läuft. Kein Bug, aber die Annahme ist
nirgends dokumentiert/getestet (Automatik-Seite editiert Uhrzeiten ohne
Zeitzonenbezug). Verpasste Takte: Rollen holen am selben Tag nach (minute >=
termin, einmalig via Merker), über Tage gibt es bewusst kein Backfill —
„genau einmal oder nie" bestätigt.

### B3a [P3 · BESTÄTIGT] Lock-Datei mit unlesbarer `ts` wirft ValueError statt LockBesetzt

`agenten/lock.py:161` `alter = time.time() - float(alt.get("ts", 0) or 0)` —
gültiges JSON mit nicht-numerischer `ts` (z. B. `{"ts":"abc"}`) lässt `float()`
explodieren; `_lese` fängt nur json-Fehler. Aufrufer fangen `LockBesetzt`
(scan_worker.py:70) bzw. loggen pro Tick. Bis zur manuellen Löschung ist JEDE
Rolle/Scan blockiert, Fehlerbild undeutlich.
Fix: ts robust parsen (try/except → alt=0 → korrupt → frei). Trivial.

### B6a [P3 · BESTÄTIGT] REST GET /signals rendert bei jedem Aufruf alle Berichts-PDFs

`rest_api._results_aus_db` → `pipeline.results_from_db()` → für jedes Signal mit
Berichten `materialize_result_pdfs(res)` (`pipeline.py:544-550`); gerendert wird
IMMER in-memory, geschrieben nur bei Byte-Differenz (`pdf_reports.py:373-374`).
Kein Scan/LLM/Netzwerk (Regel bestätigt — wirklich keine Trigger), aber der
MqlRealMonitor zahlt bei JEDEM Knopfdruck die volle ReportLab-Renderzeit über
den ganzen Bestand (bei ~50 Signalen × 3 Berichte spürbare Latenz) und ein GET
kann lokale Dateischreibzugriffe auslösen.
Fix: schlanker REST-Loader ohne PDF-Materialisation (oder Materialisation nur
im Sync-Pfad). Geringes Risiko.

### B6b [P3 · VERDACHT] REST-Server-Lifecycle an App-Lebenszyklus gebunden

`st.cache_resource` startet den Server einmal je Prozess
(`streamlit_app.py:30-39`); `rest_api_enabled`/Port-Änderungen greifen erst nach
App-Neustart, Abschalten stoppt einen laufenden Server nicht
(`rest_api.py:257-280`). Betriebs-GRENZE, Dokumentationsfrage.

### B8a [P3 · BESTÄTIGT] Agenten-Rollen-Prompts ohne B12-Sync-Test und ohne FREMDTEXT-Guard

Workflow-Prompts: B12-Sync-Test existiert und deckt alle 5
(`tests/test_intensivreview_fixes.py:402-414`), FREMDTEXT in allen 5
(`:419-428`), fehlende_kursdaten-Pflicht in risiko+gesamtbericht
(`risiko_analyse.md:125`, `gesamtbericht.md:123`).
Agenten-Prompts (6 Dateien `config/prompts/agenten/`): KEIN Sync-Test gegen die
Dateien (`tests/test_agenten_rollen.py:60-76` prüft nur Platzhalter in
DEFAULTS) und kein FREMDTEXT/Injektions-Hinweis — obwohl `betreuer_delta`
Anbieter-Daten (delta_json aus Plattform-CSV, Signalnamen) enthält, dieselbe
Fläche wie B16. AST-Vergleich dieses Reviews: derzeit 6/6 SYNC (kein aktiver
Drift). Fix: Sync-Test + FREMDTEXT-Zeile analog B16 ergänzen.

### B9a [P2 · BESTÄTIGT] Scan-Seite: Portfolio-PDF-Anhang liest falschen Session-Key — Anhang immer leer

`app_pages/scan.py:1814-1818`
```python
render_portfolio_pdf_viewer(
    portfolio_result, key="scan_portfolio_pdf",
    ergebnisse=[r for r in (st.session_state.get("results") or []) …])
```
Der kanonische Key heißt überall `scan_results` (`scan.py:81`,
`scan_state.py:10`); `session_state["results"]` wird NIE geschrieben → der
Detail-Anhang „Empfohlene Strategien im Detail" (Nutzer-Wunsch 30.09.) ist auf
der Scan-Seite still leer. Ergebnisseite korrekt (`ergebnisse.py:344,518` nutzt
lokale `results`).
Fix: `st.session_state.get("scan_results")`. Trivial, kein Risiko.

## 2) Widerlegte Verdachte (explizit)

1. **Teilscan-Scope könnte zwischen GUI und Launcher divergieren** — WIDERLEGT:
   beide laufen identisch durch `results_from_db` → `teilscan_ziel_ids` →
   `begruende_teilscan_scope` → DB-Ergänzung bei offline Quelle →
   `waehle_fuer_export` mit identischen Argumenten (`scan.py:729-746,756-758` ≡
   `scan_launcher.py:173-198`). Auch die 4 Fix-ID-Wirkstellen (Einzelnachladen
   in `crawl/_ergaenze_fix_ids` pipeline.py:1167-1196, Vorfilter-Umgehung
   :1216-1224, Export-Slots vorne, Teilscan-Scope) sind gemeinsamer Code.
2. **Melder-Watcher könnte Doppel-Meldungen produzieren** — WIDERLEGT: Marker
   wird JE Alert gesetzt, Exception mitten in der Schleife wiederholt nichts
   (`melder.py:99-102`); Erstlauf-Historie wird still markiert statt Alarm-Flut
   (`:72-83`). P3 nur bei Verschlechterung, sonst P2 (`:86`) — wie gefordert.
3. **Lock könnte einen echten >24-h-Lauf freigeben** — WIDERLEGT: eindeutig
   identifizierter lebender Halter blockiert ohne Altersgrenze
   (`lock.py:104-118`), MAX_S gilt nur ohne verifizierbare Identität; nur der
   Besitzer löscht (`_lock_ist_uns` :121-138), Freigabe im finally (:184-190);
   GUI-Worker hält dasselbe dateibasierte Lock (`scan_worker.py:64-76`), CLI
   nimmt Rollen-Locks (`agenten/__main__.py:61`), Guard-Skips laufen als
   dokumentierte skipped-Läufe (`scheduler.py:269-298`).
4. **REST :8611 könnte Scans/LLM/Netzwerk triggern** — WIDERLEGT: Provider ist
   reiner DB-Lesepfad (`rest_api.py:246-248`), Ampel via `ampel_for` aus
   gespeicherten Werten; einzig lokale Nebenwirkung ist B6a (PDF-Render).
   Token-Auth bytes-safe (`:213-220`), unbekannter Filter → 400 (`:131`),
   `quelle`/`stale`/`forensikUpdatedAt` je Signal (`:151,161-162`).
5. **Fehlgeschlagene Prüfung könnte Ampel-Verlauf flackern lassen** —
   WIDERLEGT: `erfasse_bewertung` kehrt bei `result.fehler` sofort zurück und
   wird nur ohne Fehler gerufen (`ampel_verlauf.py:113-114`, `pipeline.py:1722`);
   Chronik/Wechsel append-only (nur INSERTs, `db.py:530-592`); Wiederholung ohne
   Änderung schreibt keinen Wechsel (`ampel_verlauf.py:126-128`); kein
   Reimport-Pfad existiert (einziger Aufrufer `pipeline.py:1724`).
6. **Tradeserver-Sync könnte Teilfehler falsch behandeln** — WIDERLEGT:
   Render-Fehler → fehler-Liste, Sync läuft weiter (`tradeserver_sync.py:159-162`);
   Upload-/Protokollfehler → abort + `status=abgebrochen` inkl. catch-all gegen
   „finally schreibt ok" (`:305-327`); Wiederholung ohne Doppelbestand
   (Signals-Snapshot ersetzt vollständig, SHA-Diff überspringt Gleiche
   `:280-298`); 8-MB-Grenze + Base64 (`:39,241`); bewertet nie neu.
7. **Betreuer könnte Dossiers erfinden bzw. Quellen-Signale still prüfen** —
   WIDERLEGT: nur MQL5-Kandidaten, Quellen-Skip protokolliert
   (`betreuer.py:74-76,342-345`); SHA unverändert → KEIN Modellaufruf (:254-268);
   Destillation ohne Belegbasis wird abgelehnt, nicht erfunden
   (`destillation.py:62-69`); LLM-Ausfall verbraucht das Delta nicht
   (`betreuer.py:299-315`); Einordnungs-Parser robust gegen Options-Echo
   (:176-189); Chef bewertet nie neu und verschiebt bei aktivem Scan
   (`chef.py:85-101`).
8. **DB könnte bei ID-Kollision halbe Writes hinterlassen** — WIDERLEGT:
   `upsert_signal` Raise (`db.py:221-233`) rollt über die gemeinsame Transaktion
   von `store_scan_result` (:314-324, `_connect` `with conn` :165-166) den
   GANZEN Versuch inkl. trade_files/forensik zurück; Quelle wird seit B4 immer
   explizit übergeben (`pipeline.py:1711`).
9. **F8 length-Retry könnte verworfene Tokens verlieren** — WIDERLEGT:
   `verworfene_tokens` akkumuliert und wird in `meta_out` aufsummiert
   (`llm/client.py:217,199-208`); Budget-Reservierung inflight-safe (:100-109).

## 3) Offene Fragen (Nutzer-Entscheidung)

1. **B1a:** Soll der autonome Monats-Full-Scan bewusst ALLE KI-Berichte
   neu erzeugen (Frischhaltungs-Entscheidung „Monat = alles neu")? Dann bitte
   als Modus-Vertrag dokumentieren und die GUI-Doku angleichen; andernfalls
   Restore-Filter wie GUI nachziehen. (Empfehlung: nachziehen — Token-Kosten.)
2. **B2a:** Wie viele Retry-Versuche je autonomem Scan-Tag sind akzeptabel
   (ToS-Abwägung MQL5)? Vorschlag: 3 Versuche, dann P2-Meldung + Ruhe bis
   nächster Takt-Tag.
3. **B6a:** Dürfen REST-Antworten PDFs materialisieren (Server braucht die
   Dateien evtl. nie), oder soll der REST-Pfad schlanker werden?

## Anhang: Bewertung der geprüften Regeln (Kurzprotokoll)

- **B1** Parität im engeren Sinne (Scope/Forensik/Ampel/Chronik) GEgeben;
  Divergenzen nur B1a (KI-Berichts-Auswahl, P1) und B1b (Login-Anforderung, P2).
  GUI-Ad-hoc-Overrides (Seiten/Top-N/Filter-Widgets ohne Speichern) sind
  bewusst GUI-only — Launcher nutzt gespeicherte Settings (dokumentiert).
- **B2** Merker: Erfolg → gesetzt; skipped/geprueft==0 → korrekt NICHT gesetzt
  (F4/B8 bestätigt); Exception → Tages-Merker gesetzt, aber für full ohne
  Wirkung (B2a). Digest/Lagebericht unfällig bei laufenden Rollen/Scans
  bestätigt (`scheduler.py:117-119`, `melder.py:162-174`, `chef.py:85-101`).
- **B3** Lock v4 an allen drei Startwegen (Daemon-Tick, GUI-Button/Komplettkette,
  CLI) verifiziert; Herzschlag bleibt durch Daemon-Schleife/Threads frisch;
  einzige Lücke B3a (korrupte ts).
- **B4/B5/B7/B10** keine neuen Befunde — implementiert wie in AGENTS.md
  dokumentiert (Details in Abschnitt 2).
- **B8** LLM-Layer: Antwortvalidierung, Budget (Reservierung + Tages-/Monats-
  budget der Rollen), Cache/Restore über Basis-Bindung, keine Credentials im
  Prompt (Payloads nur aus ScanResult-Feldern), RetDD/Ertrag mit Definition +
  Messstatus (`pipeline.py:321-330` `retdd_nicht_berechenbar`) und
  „keine Prognose"-Marker in gesamtbericht/risiko/portfolio — bestätigt;
  Lücke nur B8a (Agenten-Prompts ohne Sync-Test/Guard).
- **B9** Tageskette im Hintergrund-Thread reload-sicher mit atomarem
  Start-Guard (`tageskette.py:203-238`); Scan-Doppelstart über builtins-Registry
  + Datei-Lock auch prozessübergreifend (`scan_worker.py:28-76`); zweite
  Browser-Session wird abgewiesen (`scan.py:108-112`); Fragmente/Dialoge
  getrennt gehostet (`scan.py:244,1741-1759`); DD-Benennung durchgängig
  „Max-Drawdown" vs. „Drawdown (Plattform)" (`app_ui.py:408,471-477,1049,1064`;
  `ergebnisse.py:460`). Einziger GUI-Fehler: B9a (Session-Key).

— Ende Paket B —
