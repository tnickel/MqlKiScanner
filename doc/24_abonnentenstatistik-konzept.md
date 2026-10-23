# doc/24 — Konzept „Abonnentenstatistik" (Seite im SignalKiScanner)

Stand: 20.10.2026 · Konzept abgestimmt (Nutzer-Entscheidungen unten), Umsetzung noch nicht begonnen.
Vorbild: Abonnentenstatistik-Fenster des MqlDownloader (Swing `SubscriberStatisticsDialog`).
Zweck: Signale finden, **wo die meisten Nutzer neu hinzukommen** (Zuwachs als Kandidaten-Heuristik);
bewertet wird weiterhin ausschließlich der Workflow — diese Seite beobachtet nur.

## 1. Bestandsaufnahme (Recherche 20.10.2026)

### 1.1 Clients messen Abonnenten bereits selbst

| Client | Mess-DB | Snapshot-Takt | 7/30-Tage-Zuwachs | REST |
|---|---|---|---|---|
| MqlDownloader :8089 | H2 `config/subscribers` (`signal_subscribers`, `subscriber_history`) | je Katalog-Crawl (Automatik Fr 18:00, Stufe 0, manuell) | eigene SQL-Vergleichssnapshots, Toleranz 7±2 / 30±4 Tage | `GET /providers` (subscribers, latestChange, weekChange, monthChange, lastUpdated, risk, url), `GET /providers/{id}/{v}/history`, `GET /summary`, `GET /events` |
| Pelikan :8090 | SQLite `data/abonnenten.db` (`copier_historie`) | App-Start (tägl.), „Signale laden", Stufe-0-Katalog | `zuwachs(7/30)` | Katalog-Felder weekChange/monthChange + `/history` |
| Robo :8091 | `abonnenten.db` (`abonnenten_historie`) | dito + nach Tageslisten-Batch | dito | dito |
| Vantage :8092 | `abonnenten.db` (`kopierer_historie`) | dito | dito | dito |
| Zulu :8093 | `abonnenten.db` (`abonnenten_historie`, + live_followers) | dito | dito | `/history` seit 01.10. gefüllt (nicht mehr leer) |

Monitor-Semantik `zuwachs(N)`: neuester Snapshot (max. 2 Tage alt) minus neuestem Snapshot
≥ N Tage vor Messdatum; ohne alte Basis ehrlich kein Wert (nie falsche 0). Ein Tag = ein Wert (UPSERT).

### 1.2 Live-Messung 20.10. (nur MqlDownloader online, Monitore offline)

- `GET /providers` Vollkatalog (372 Zeilen, 236 KB): **~2,7 s** warm / ~10 s kalt
  (~6 ms/Zeile: Wochen-Dateialter + History-Subqueries); `limit=50`: 0,34 s; `limit=200`: 1,2 s
- `GET /providers/{id}/{v}/history?days=30`: **~8 ms** · `GET /summary`: 7 ms · `GET /update/status`: 2 ms
- Datenstände: Katalog-Vermerke (`update_state.json`) aller 5 Clients vom 18.10.
  16:42–19:37 UTC; letzte Snapshot-DB-Änderungen 19.10. morgens; neueste MqlDownloader-Messung
  18.10. 21:36 → ohne Neuladen ~1,5 Tage alt. Genau das zeigt die Spalte „Letzte Messung".

### 1.3 Scanner-Bestand

- `subscriber_history` (db.py): `signal_ref, version, ts, subscribers, change, fetched_at`,
  PK `(signal_ref, version, ts)`, idempotenter Upsert (`db.store_history_points`) — die eine
  echte Verlaufs-Tabelle; gefüllt bislang nur per `downloader_sync.sync_history` (Workflow-Signale).
- `downloader_sync.abo_bilanz()` / `_bilanz()`: 7/30-Tage-Differenz mit Toleranz ±3 Tage aus
  lokaler `subscriber_history` — wird verallgemeinert/erweitert.
- `katalog.sync()` (Alle-Signale-Sync, `minSubscribers=0`) schreibt `katalog_signale`
  (Überschreib-Tabellen, keine Historie) + `katalog_sync` (Stand je Quelle).
- Stufe-0-Infrastruktur `client_updates.py`: paralleler `POST /api/v1/update` + Status-Polling
  (`login_required`-Behandlung, Timeouts) + Chronik `client_updates`.
- Seitengerüst „Alle Signale" (Filter, DataTable mit Zeilenauswahl, CSV, Detail, `@st.fragment`
  Live-Muster) wird als Muster wiederverwendet.
- Vantage-Katalogfelder `weekChange/monthChange` werden heute ignoriert — werden auch weiter
  NICHT übernommen (uneinheitliche Semantik); der Scanner rechnet selbst (s. §3).

## 2. Seite

- **Nav:** Arbeitsbereich, direkt unter „Alle Signale" (`streamlit_app.py`), Titel
  „Abonnentenstatistik" + Hilfe-Thema `abonnenten_statistik` (+ FAQ-Eintrag).
- **Tabs:** `Alle` | `MQL5` | `Pelikan` | `Robo` | `Vantage` | `Zulu` — je aktiver Quelle
  (inaktive ausgeblendet). „Alle" trägt die Spalte „Quelle".
- **KPI-Karten je Tab:** Signale gesamt · mit Zuwachs 7 T · größter Zuwachs · neueste Messung.
- **Tabelle:**

| Spalte | Inhalt |
|---|---|
| Signal | Name + ID |
| Quelle | nur Tab „Alle" |
| Plattform | mql4/mql5/pelican/vantage/zulu (Version) |
| Abonnenten | aktueller Stand |
| Δ seit letzter Messung | mit „vor X h"; grün/rot |
| Δ 7 Tage / Δ 30 Tage | grün/rot; „–" mit Tooltip, wenn keine belastbare Basis |
| Letzte Messung | neueste Messung beim Client |
| Ampel | Scanner-Ampel aus Forensik/Workflow, sonst leer (Nutzer-Entscheidung 3) |
| URL | Anbieter-Link (quellen.py `oeffnen_url`-Logik) |

- **Filter/Sortierung:** Min. Abonnenten (Default **1**, Nutzervorgabe; Sync holt trotzdem
  `minSubscribers=0`, Filter ist reine Anzeige — Historie bleibt für alle vollständig),
  Suche (case-insensitiv über alle Spalten), sortierbare Spalten, Default **Δ 30 Tage desc,
  Δ 7 Tage desc, Abonnenten desc** (wie Vorbild). CSV-Export (`;`, UTF-8-BOM).
  Caption je Tab: „Katalog-Stand JJJJ-MM-TT HH:MM · N Signale · M mit Abonnenten".
- **Detail (Zeilenauswahl):** Verlaufs-Chart (Plotly, volle gemessene Historie),
  Messpunkt-Tabelle, Button „In Alle Signale öffnen" / zur Workflow-Detailansicht bei
  vorhandener Forensik.
- **Bewusste Abweichungen vom MqlDownloader-Fenster:** keine Sparkline-Spalte in der Tabelle
  (Streamlit-Performance bei 600+ Zeilen; Verlauf im Detail), kein manuelles „Risiko"-Feld
  (statt dessen Scanner-Ampel; Nutzer-Entscheidung 3), „Testreports"-Spalte entfällt
  (Scanner-PDFs hängen am Workflow-Detail).

## 3. Datenfluss & Berechnung (einheitlich im Scanner)

Sync-Ablauf je aktiver, erreichbarer Quelle (Teilausfall bricht nichts — Muster downloader_sync):

1. `GET /providers?minSubscribers=0&limit=5000` (paginiert, Vollständigkeit validiert wie ingest).
2. Je Provider `GET /providers/{id}/{v}/history` (ms) → `subscriber_history` (idempotent).
   **Nutzer-Entscheidung 2: komplett beim Sync** (~1.600 winzige Calls über alle Quellen,
   einmalig grob 1–2 min, danach Festplatten-Cache/Fragment).
3. **Eigener Messpunkt „jetzt"** aus der Katalog-Abonnentenzahl in `subscriber_history`
   (Scanner baut eine eigene, dichte Historie auf — unabhängig vom Client-Takt;
   `change` = Differenz zum vorherigen Punkt derselben Identität).
4. Δ-Spalten berechnet der Scanner **selbst** (Toleranzfenster wie MqlDownloader 7±2/30±4 Tage
   bzw. bestehende ±3-Logik — bei Umsetzung auf EINE Regel festlegen und testen); Client-Felder
   weekChange/monthChange werden bewusst nicht gemischt.

Identität: `signal_ref` (Schema 2: `quellen_uid` + `externe_id`), Version je Plattform —
keine ID-basierten Kreuz-Zugriffe, getrennt je Besitzer.

**Ehrliche Grenzen (in UI/Hilfe sichtbar):**

- Monitor-Snapshot-Historie beginnt 01.10.2026 → 7-Tage-Zuwächse sofort, belastbare
  30-Tage-Werte erst ab ca. 31.10.2026 (dann wachsend); MQL5 liefert 30-Tage-Werte sofort
  (tiefe Downloader-Historie).
- Katalogabdeckung je Quelle = lokal verfügbarer Katalog: Robo/Vantage/Zulu Top-N
  (letzter Load je 200), Pelican alle ~2.250, MQL5 bis zur 0-Abonnenten-Grenze (~372).
- Offline-Quellen: Tab erscheint mit letztem Scanner-Stand + Fehlerhinweis (kein Crash).

## 4. Refresh-Modell (Nutzer-Entscheidung 1: zwei Stufen mit Abfrage-Dialog)

Ein Refresh-Button öffnet einen Dialog mit Wahl:

- **Stufe A — „Nur neu lesen" (Standard, ~5–15 s):** Katalog + Historie aller erreichbaren
  Clients neu ziehen, Messpunkte schreiben, Tabelle frischen. Kein Eingriff in Clients,
  keine Website-Kontakte.
- **Stufe B — „Frisch messen (ohne Tradelisten)" (je Quelle Checkbox):**
  `POST /api/v1/update {"tradelisten": false, "katalogMaxAlterH": 0}` an die gewählten
  Clients — Katalog/Abonnenten werden neu geladen, Tradelisten-Phase entfällt komplett.
  `katalogMaxAlterH: 0` ist Pflicht: Ohne diesen Parameter würde die 3-Tage-Regel der
  Clients (72 h, Vermerk `katalogLetzterLoad` in `update_state.json`) die Katalog-Phase
  überspringen und der Job in Sekunden ohne neue Messung enden. Die Abonnenten-Messung
  läuft bei allen 5 Clients in der Katalog-Phase fest verdrahtet mit
  (MqlDownloader: `checkAndUpdateSubscribers` je Katalog-Zeile — auch bei
  `tradelisten=false`; Monitore: Snapshot-Write am Ende der Katalog-Phase), d. h. Stufe B
  schreibt zugleich einen neuen Tages-Snapshot in die Client-eigene `abonnenten.db`
  (deren 7/30-Tage-Zuwächse bleiben dicht) — und der Scanner schreibt beim anschließenden
  Lesen (Stufe A) seinen eigenen Messpunkt zusätzlich.
  Live-Status im Dialog über Stufe-0-Polling (`GET /update/status`, `login_required`-
  Behandlung), Chronik in `client_updates` mit Kennzeichnung `abonnenten-refresh`;
  danach automatisch Stufe A. Geschätzte Dauern (code-basiert; bei Umsetzung live messen):

  | Quelle | Stufe B ca. | Grund |
  |---|---|---|
  | Robo | 1–5 min | Top-200-Katalog per REST |
  | Zulu | 1–5 min | Top-200-Katalog per REST |
  | Vantage | 3–8 min | Katalog + Stats Top-150 (300 ms Drossel); stundenlange Tradelisten-Phase entfällt |
  | Pelikan | 10–20 min | lädt bewusst ALLE ~2.250 Provider |
  | MqlDownloader | 10–25 min | Selenium-Crawl der MQL5-Listenseiten, Random-Waits 4–30 s |

  Default-Häkung: **4 Monitore an, MQL5 aus** (Zeitwarnung im Dialog, jederzeit zuschaltbar).
- Bewusst **keine** Stufe mit Tradelisten auf dieser Seite — dafür bleibt der Scan-Workflow
  (Kreis 0) zuständig. `client_updates.starte_alle_updates` erhält dafür Parameter
  (`tradelisten=False`, Quell-Teilmenge) statt Kopie-Code.

## 5. Nutzer-Entscheidungen (20.10.2026)

1. **Refresh:** zwei Stufen (A nur lesen; B frisch messen ohne Tradelisten, je Quelle,
   Default Monitore an / MQL5 aus).
2. **Verlauf:** komplett beim Sync (bulk `/history` aller Provider je Quelle).
3. **Risiko-Spalte:** Scanner-Ampel statt manuellem Risiko-Feld.

## 6. Umsetzungsplan

1. `src/mqlkiscanner/abonnenten_statistik.py` — Sync (Katalog + Historie + eigene Messpunkte,
   je Quelle, Teilausfall-sicher), einheitliche Bilanz auf `subscriber_history`-Basis
   (verallgemeinerte `abo_bilanz`), KPI-Aggregate.
2. `client_updates.py` — Parameter `tradelisten=False` + Quell-Teilmenge + Modus-Kennzeichnung
   in der Chronik (GUI Kreis 0 bleibt unverändert).
3. `app_pages/abonnenten_statistik.py` — Tabs, KPIs, Tabelle (Wiederverwendungs-Muster
   Alle-Signale), Detail mit Verlaufs-Chart, Refresh-Dialog mit Live-Fragment, CSV.
4. Navigation (`streamlit_app.py`), Hilfe-Thema, FAQ, AGENTS.md-Eintrag.
5. Tests: Sync/Bilanz über mehrere Quellen inkl. Toleranzfenster und „–" statt falscher 0,
   ≥1-Filter, eigene Messpunkte (change-Verkettung), Offline-Quelle, Stufe-B-Parameter,
   AppTest der Seite (Muster test_alle_signale_seite).

Keine Änderungen an: Bewertungsregeln, Ampel-Logik, Client-Projekten (deren REST genügt),
Automatik (kein neuer Takt — Seite wird auf Abruf bedient).

## 7. Nachtrag Sparkline-Spalte (Nutzer-Wunsch 20.10.2026 abends)

Ursprünglich bewusst verzichtet („Streamlit-Performance bei 600+ Zeilen") —
nach Nutzer-Nachfrage gemessen und umgesetzt: Die Spalte **„Verlauf 30 T"**
zeigt die Minigrafik der Abonnentenentwicklung wie das MqlDownloader-Fenster.
Technik: Pillow-Rendering (88×22 px, transparent, Trend-Farbe grün/rot/grau)
als base64-Daten-URL in einer st.column_config.ImageColumn, Festplatten-Cache
je Messreihe. Messung 20.10. mit Produktivdaten: 3.104 Kurven in 0,57 s,
≈0,57 MB Payload für 3.186 Zeilen — unkritisch. Fenster = letzte 30 Tage
relativ zur neuesten Messung (MqlDownloader-Semantik), <2 Punkte = leere
Zelle. CSV-Export enthält die Spalte bewusst nicht (Daten-URLs sind dort
nutzlos). Pillow als direkte Dependency deklariert (requirements.txt).


## Nachprüfung und Korrektur 23.10.2026

Nutzerfestlegung: **höchstens 200 Anbieter je Quelle, absteigend nach
Abonnenten, mindestens ein Abonnent**. MQL4/5 teilen sich die 200 Plätze.
Diese Festlegung ersetzt für den Abonnenten-Refresh die oben dokumentierten
4500er Sicherheitslimits, Pelican-Vollerfassung und Vantage-Rankingmischung.

Ein expliziter POST-Parameter `nurAbonnenten=true` trennt den Listen-/Zählerabruf
von vollständigen Profil-/Kennzahlen-/Trade-Updates. `/health` muss
`abonnentenRefresh=true` melden; das Ergebnis bestätigt `nurAbonnenten=true`.
Alte laufende Clients werden vor dem POST abgewiesen, statt den Parameter
unbemerkt zu ignorieren. Ein bereits laufender fremder Job gilt nicht als
Nachweis einer angeforderten Neumessung. Fehler bleiben im Refresh-Endergebnis
sichtbar, auch wenn das anschließende Lesen alter Daten erfolgreich ist.

- MQL: nach Abonnenten sortierte Listen je Version, gemeinsame Top-200-Auswahl;
  keine Einzelprofil-/Konvertierungsschleife.
- Pelican: Discover-Sammelliste, Positivfilter und lokale Top-200-Auswahl;
  keine Detail-/Statistikschleife.
- Robo: reines Abonnenten-Ranking; der zusätzliche 300-%-Gewinnfilter entfällt
  im neuen Zählermodus.
- Zulu: bestehende `followers`-Definition, absteigende Liste und Positivfilter.
- Vantage: ausschließlich Kopierer-Ranking statt kuratierter/Rendite-Mischung;
  keine zusätzlichen Kennzahlenabrufe.

Bestehende Detaildaten und historische Abonnentenwerte bleiben erhalten.
Ein Zählerrefresh ist kein Nachweis frisch geladener Finanzkennzahlen.
Quellcode/Build/Tests und Aktivierung der laufenden Clients sind getrennt zu
prüfen; ein neues Paket aktualisiert laufende Java-Prozesse nicht automatisch.
