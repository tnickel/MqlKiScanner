# Intensiv-Review der Signal-Scanner-Kette — Ziellauf 29./30.09.2026

**Gegenstand:** End-to-End-Review des Full-Scans `2026-09-30_025355_970680_c65bf5cd`
(Start 30.09.2026 00:02:20, Ende 02:53:53, Europe/Berlin) inkl. Vorläuferlauf vom
29.09. 23:32, PelicanTrading-Datenfluss, Scanner-Auswahl/-Berechnung, KI-Prompts
und -Antworten, Agentenbetrieb sowie nachgelagerte Übergaben.
**Code-Stand des Laufs:** git `ccc383b` (Arbeitsbaum = HEAD, keine uncommitteten
getrackten Änderungen). **Arbeitsweise:** überwiegend read-only; DB-Zugriffe auf
Kopien; unabhängige Nachrechnung mit eigenem Parser (kein Import von
`src/mqlkiscanner`); parallel arbeitende Teil-Reviews (Sub-Notizen unter
`sub_pelican/`, `sub_scanner/`, `sub_ki_agenten/`).

---

## 1. Gesamturteil

Der Ziellauf ist **technisch sauber gelaufen und rechnerisch bemerkenswert
präzise**: Auswahl exakt reproduzierbar, Zahlenkette 182+781=963 → 103 → 60 → 52
lückenlos, Token-Abgleich DB↔Log auf die Token genau, Identitätskette inkl.
SHA-256 je Signal vollständig, FX-/USC-Konvertierung fehlerfrei, Terminal-Politik
eingehalten, MCA100-Live-Fix produktiv bestätigt. Meine unabhängige Nachrechnung
von 9 Signalen trifft den Produkt-Drawdown **auf den Cent** (9/9), sobald man die
dokumentierte Sekunden-Batching-Konvention spiegelt.

**Aber die stärkste Regel des Projekts — „Risiko VOR Ertrag, 30 % Drawdown max" —
ist für Quellen-Signale (Pelican) faktisch außer Kraft gesetzt** (B1): Der
Monitor liefert eine floating-inclusive EQ-DD-Zweitmessung, diese verdrängt die
eigene Kursdaten-Rekonstruktion (Skip), fließt aber bewusst NICHT in die
Schranke. Zwei Signale mit Zweitmessung 46,6 % bzw. 241,3 % stehen 🟢 in der
Tabelle. Dazu kommt, dass das Ertragskriterium (≥ 5 %/Monat) auf
Plattform-Selbstauskunft mit anderer Kapitalbasis geprüft wird als DD und
Schock (B2) und die virtuelle 10.000-USD-Basis die Risikoprozente bei
Kleinkonten um Faktor 2–20 verzeichnet (B3). Die KI-Stufen (insbesondere der
Portfolio-Bericht) kompensieren diese Lücken diesmal inhaltlich korrekt —
das ist aber nicht bindend und kein harter Schutz.

Für das eigentliche Ziel — 3–4 belastbare, wenig korrelierte Kandidaten —
liefert der Lauf **einen** robusten Kandidaten (Gold Spike MT4) und zwei
Kandidaten mit Vorbehalten (Lexo, PentagonForex), deren Ertrag auf konsistenter
Basis die 5-%-Marke verfehlen. Eine Empfehlung von 3–4 Signalen tragen die
aktuellen Daten nur teilweise.

---

## 2. Datenfluss-Diagramm (Ist-Stand im Ziellauf)

```
MQL5-Direkt (mql5.com, 2 Seiten/Liste) ──┐
   182 Signale (MT4+MT5)                  │
                                          ├─> Vereinigt 963 ─> Vorfilter
PelicanMonitor :8090 (pelik, OK) ─────────┤    (Wochen>=26, Abo>=1) ─> 103
   781 Katalog-Einträge                   │     (69 mql5 + 34 pelik)
                                          │         │
MqlDownloader :8089 (mql5, DOWN) ── X ────┘         ▼
   [listen]-Warnung, Weiterlauf            Auswahl je Quelle (Abo absteigend,
                                          │   fix_signale.waehle_fuer_export)
                                          ▼
                                   60 (mql5 30/69 · pelik 30/34)
                                          │  davon 13 ⛔ known_signals
                                          ▼
                      Forensik je Signal: Kennzahlen + Trades (Exporter/Quellen-
                      Cache, SHA) → Parser → 4 Tests + Exposure + Stops
                      → Equity-Reko (mql5: MT5-Terminal portabel; pelik: SKIP,
                        weil Monitor TradeEqDrawdownPct liefert)
                      → Score/Ampel (Vierfach-Max: Trading/EQ/Balance/Reko-DD)
                                          │
                            52 OK ────────┼──────── 8 Fails (2 Parser, 4 USOIL,
                                          │           2 GER40) → kein Urteil
                                          ▼
                      LLM: 52× (Trade glm-5.3 ‖ Risiko glm-5.3-flash) → Gesamt
                          → Portfolio (glm-5.3, 23 🟢/🟡-Berichte, 87.489 Tok.)
                          Σ 1.701.552 Tokens (Budget 5 Mio: 34 %)
                                          │
                                          ▼
              Persistenz: signals/forensik/analyses/ampel_verlauf(+wechsel)/
              quellen_artefakte/trade_files · results.json-Archiv · PDFs
                                          │
              ┌───────────────────────────┼─────────────────────────────┐
              ▼                           ▼                             ▼
      REST :8611 (MqlRealMonitor,   Tradeserver-Sync            Downloader-Sync
      live aus DB, 91 Signale)      (MqlTradeMonitor):          (Abonnenten-Verlauf
                                    NICHT gelaufen              + PDF-Spiegel):
                                    (letzte Sync 23.09.)        ABGEBROCHEN (02:53:53,
                                                                Spiegel stale 20.09.)

  Agenten (Dirigent/Markt/Betreuer/Chef/Melder): im Zielfenster AUS
  (Daemon seit 22.09. beendet; letzter Agentenlauf 23.09. 10:23)
```

---

## 3. Laufchronologie (Beleggrad: ① direkt belegt · ② rekonstruiert · ③ nicht nachweisbar)

| Zeit (Europe/Berlin) | Ereignis | Beleg |
|---|---|---|
| 29.09. bis 20:46 | Review-/Fix-Sessions des Tages (Commits ed322df→b598e9a) | ① git log |
| 29.09. 23:18:41 | Commit 7c00915 (Verbindungs-Badges je Quelle) | ① git log |
| 29.09. 23:17 | PelicanMonitor: letzter voller „Signale laden"-Discover (2223 Provider, Filter ≥5 Wochen/≥50 Copier → 43 sichtbar; Stats nur für diese) | ① pelicanmonitor.log + Dateien ② genaue Uhr via mtimes |
| 29.09. 23:30–23:37 | PelicanMonitor-Neustarts, Session-Ablauf 23:36, Re-Login, Statistik-Batch 23:37 abgeschlossen | ① pelicanmonitor.log |
| 29.09. ~23:31:30 | **Vorläufer-Scan #1** (full) startet (GUI, altes Selection-Layout) | ② ampel_verlauf: erster Eintrag 23:32:19; kein Log (Feature ccc383b später) |
| 29.09. 23:32:19–23:55:52 | Scan #1 verarbeitet 14 mql5-Signale (7 Wechsel protokolliert) | ① ampel_verlauf/ampel_wechsel |
| 29.09. ~23:56–00:01 | Scan #1 endet ohne Archiv: Equity-Reko-Crash bei MCA100 #2153920 („gleiche Stunden"); Fix entwickelt | ② Commit-Message ccc383b „Live-Bug MCA100"; kein results.json des Laufs ③ exakte Crash-Uhrzeit |
| 29.09. 23:50:34 | Commit caa1074 „30 von jedem" (wurde erst im Neustart wirksam) | ① git log |
| 30.09. 00:01:28 | Commit ccc383b: MCA100-Fix + dauerhaftes Workflow-Log | ① git log |
| 30.09. 00:02:20 | **Ziellauf Scan #2** startet (GUI, Code ccc383b): [listen] 182 MQL5-Direkt; Quelle mql5 (MqlDownloader :8089) DOWN; pelik 781; vereinigt 963 | ① scan_workflow.log Z. 1–4 |
| 00:02:24 | Vorfilter → 103; Auswahl mql5 30/69 · pelik 30/34 = 60; MQL5-Session gültig | ① Log Z. 5–8 |
| 00:02:28–00:05:45 | Forensik-Batterie über 60 Signale; MT5-Terminal portabel verbunden (00:02:31); Reko-Skips: 8× Broker-Suffix-Symbole (mql5), 23× Monitorwert (pelik); 8 Signale endgültig fehlgeschlagen (je 2 Versuche, deterministisch); MCA100 läuft sauber (Fix bestätigt); 12 Ampel-Kipp-Ereignisse + 1 Farbwechsel (UpFuji 🟡→🔴) | ① Log + DB forensik/signals/ampel_* |
| 00:05:59–02:50:20 | LLM-Phase: 52 Signale × (Trade ‖ Risiko) → Gesamt;portfolio-relevante 🟢/🟡=23 | ① Log [llm] + analyses |
| 02:50:20–02:53:45 | Portfolio (glm-5.3): 23 Berichte/209.081 Zeichen → 7.407 Zeichen Empfehlung Gold Spike 40 / Lexo 30 / PentagonForex 30; Σ 1.701.552 Tokens | ① Log + analyses + results.json |
| 02:53:53 | Downloader-Abgleich bricht ab (MqlDownloader DOWN) — 0 Verlaufs-Punkte, Spiegel bleibt Stand 20.09. | ① Log letzte Zeile + DB |
| 02:53:55 | Archiv `data/runs/2026-09-30_025355_970680_c65bf5cd/results.json` (933 KB, 60×68 Felder) | ① Datei |
| 03:02:29/03:02:33 | Quellen-Verbindungstests aus der noch offenen GUI (mql5 🔴, pelik 🟢 781 Anbieter) — letztes PelicanMonitor-Lebenszeichen | ① datenquellen.letzte_prüfung |
| 30.09. tagsüber | PelicanMonitor jetzt offline (Verbindung abgelehnt); Scanner-REST :8611 im App-Prozess verfügbar; Tradeserver-Sync nicht ausgelöst (letzte Sync 23.09., monitor.tnickel-ki.de zeigt Stand 23.09.) | ①/② Sub-Prüfungen |

**Zeitzonen:** Scan-/DB-Zeitstempel lokal (Europe/Berlin), Commit-Zeiten +0200 —
konsistent. Pelican-Log ohne Sekunden, aber lokale Uhr. Kein Zeitzonensprung-
Verdacht. ③ Einzelne REST-Latenzen/Statuscodes des Ziellaufs (kein Access-Log).

---

## 4. Prüfabdeckung

| Bereich | Geprüft | Unterlagen |
|---|---|---|
| Pelican-Datenfluss | Discover→Stats→Trades→Konvertierung→REST→Scanner-Ingest; Währung/FX (12/12 Trades exakt nachgerechnet); USC ÷100 (Codepfad, kein USC-Konto im Katalog); Kapitalbasis-Virtualisierung; lokale KI (Vorlage in `data/config.json`, 61 Berichte, /reports **hartkodiert leer** → kein Pelican-KI-Ergebnis erreicht den Scanner) | `sub_pelican/notes.md` |
| Scanner | quellen/ingest/pipeline/fix_signale/parser/stats/engine/scoring/ampel_matrix/regelwerk/db/rest_api/downloader_sync/kursdaten + GUI↔Launcher-Parität; Identitätskette je Signal über 9 Stufen inkl. SHA 30/30 | `sub_scanner/notes.md` + 3 Prüfskripte |
| KI/Agenten | alle 5 Workflow- + 6 Agenten-Prompts, Prompt-Füllung im Code, 13 echte Antworten des Ziellaufs volltextlich, Portfolio-Antwort komplett, Analysen-Inventar (52×3+1), Rollen-Code (rollen/scheduler/tageskette/lock/journal), Budgets | `sub_ki_agenten/notes.md` + `fall_dumps.md` |
| Unabhängige Nachrechnung | 9 Signale (2 Quellen, alle Ampelfarben, Grenzfälle), eigener Parser, DD/Netto/PF/Winrate/Serie/Martingale/Exposure/Schock/Monatsrenditen, SHA-Verifikation | `nachrechnung_pruefung.py`, `nachrechnung.csv` |
| Portfolio | Monats-/Wochenrendite-Korrelationen aller 23 🟢/🟡, Verlustmonat-Cluster, Dreifach-Exposure-Überlappung, Hälften-Stabilität | `portfolio_pruefung.py`, `portfolio_korrelation.csv`, `portfolio_pruefung.md` |
| Nachgelagert | REST :8611 (live, 91 Signale, kein Altersmarker), Tradeserver-Sync (nicht gelaufen), Downloader-Sync (abgebrochen) | sub_scanner C) |

---

## 5. Befunde

Schere: **[KRITISCH]/[HOCH]/[MITTEL]/[NIEDRIG]** · Sicherheit: belegt (Code+Daten
des Laufs) / wahrscheinlich / nicht prüfbar. Jeder Befund mit Ort, Wirkung,
Korrekturidee, Verifikationstest. Gegenprüfung: B1–B3, B6, B8, B9, B15 wurden
vom Hauptagenten unabhängig nachgerechnet bzw. im Code nachgelesen (✓).

### A) Bestätigte Fehler / Regelverstöße gegen das Projekziel

**B1 [KRITISCH, belegt] — Harte 30-%-DD-Schranke ohne floating-inclusive Messung
bei Quellen-Signalen.** Dreifach unabhängig bestätigt (Hauptagent ✚ Sub Pelican ✚
Sub Scanner). Ort: `pipeline.py:915-924` (Reko-Skip, wenn Monitorwert da),
`scoring.py:62-66,185-190` (`dd_maximum` ohne Monitorwert), Anmerkung
`pipeline.py:136-140`. Wirkung im Lauf: **Lemonal 🟢 Score 4,9 bei Monitor-EQ-DD
46,65 %**, **AccurateCopier 🟢 4,5 bei 241,3 %**, Grid King 🟡 70,64 %, Master H4-1
🟡 66,52 % — alle als Kandidaten im Portfolio-Prompt. Gerade das
Pure-Gold-2000-Muster (papieren top, floating explodiert), das das Projekt
hervorbringt, wird bei Quellen-Signalen nicht hart abgefangen; MQL5-Signale
haben über die Reko einen harten Kanal, Quellen nicht — Inkonsistenz in der
strengsten Regel. Vorbehalt: Werte >100 % sind auf virtueller Basis gerechnet
und überzeichnen absolut (siehe B3) — 46–70 % liegen aber jenseits jeder
Toleranz. Korrektur: Monitor-EQ-DD als fünftes Schranken-Maximum zulassen,
sobald die Basis belastbar ist; mindestens eigene Matrix-Zelle
„EQ-DD-Zweitmessung" (🟠/🔴 über Schranke) und 🟢-Sperre bei Monitorwert >
Schranke. Test: pelik-Fixture mit `TradeEqDrawdownPct=46` → Ampel ≠ 🟢.

**B2 [HOCH, belegt] — Ertragskriterium auf inkonsistenter Basis geprüft
(Selbstauskunft vs. Forensik-Basis).** `ertrag_monat_pct` für pelik kommt aus
den Monitor-Metrics (Average3MonthProfit, hergeleitet aus Plattform-Rendite),
DD/Schock/Score dagegen aus der virtuellen 10k-Basis. Unabhängige Gegenrechnung
(Hauptagent, eigene Monatsrenditen aus Roh-Trades auf der DD-Basis):

| Signal | Plattform %/M | eigen linear %/M | eigen Median %/M | Realbalance |
|---|---|---|---|---|
| Gold Spike (mql5) | 24,54 | 8,60 | 6,69 | 2.409,55 |
| Lexo | 15,40 | 3,49 | 1,48 | 32.146,55 |
| Lemonal | 248,49 | 12,55 | 7,44 | 14.543,79 |
| PentagonForex | 6,68 | 2,67 | 1,58 | 29.557,44 |
| AccurateCopier | 23,57 | 2,90 | 3,09 | 5.226,73 |
| SafeGold | 6,46 | 0,50 | 0,54 | 998,22 |
| 💎t.me/Mr_Profit_FX | 63,79 | 1,09 | 0,91 | 4.437,15 |

Auf der Basis, auf der Risiko gerechnet wird, erreicht **kein pelik-Grüner außer
Lemonal** die 5-%/Monat-Projektschwelle; PentagonForex (Portfolio-Empfehlung,
30 %) liegt bei 2,67 % linear. Das Ertrags-🟢 dieser Signale steht auf der
Plattformzahl. (Gegenposition geprüft: Die Plattformzahl ist auf die echte
Historien-Equity des Providers bezogen und nicht „falsch" — aber sie ist nicht
die Basis, die ein Kopierer realisiert, und nicht die, mit der Risiko
verglichen wird. Beide Zahlen gehören in die Matrix.) Korrektur:
`ertrag_monat_pct_forensik` aus der eigenen Kurve berechnen und neben den
Plattformwert stellen; Ampel-Kriterium auf die Forensik-Basis heften (Plattform
als Zusatzinfo). Test: Fixture SafeGold → Ertrags-Zelle darf nicht 🟢 auf Basis des
Plattformwerts 6,46 % bleiben, wenn die eigene Kurve 0,5 %/M liefert.

**B3 [HOCH, belegt] — Virtuelle Kapitalbasis 10.000 USD verzerrt Risikoprozente
systematisch (Faktor 0,05×–3,2×).** Kanal sauber (InitialDepositVirtual →
`kapitalbasis_virtual_usd` → `quelle:"virtuelle_annahme"`, Urteile nennen es,
kein Cent-Abgleich) — aber 12 Signale haben Web-Balancen von 0,05×–0,5× der
Basis (MicroJump 530 USD, Gold VIP 656, SafeGold 998): Trading-DD-%/Schock-%
dann um Faktor 2–20 zu niedrig; bei Lexo (32k) umgekehrt konservativ. Der
Monitor-DD-Nenner wird sogar aus der Plattform-Rendite rückgerechnet
(`ReportService.java:57-70`) — Werte >100 % sind artefaktverseucht, genau dann
fehlt jede harte Messung (Wechselwirkung mit B1). Sensitivitätsnachweis in
`nachrechnung.csv` (Zeilen „Sensitivität: DD % auf Realbasis-Proxy"). Korrektur:
implizites Initial = `web_balance − ΣProfits` als bevorzugte Basis, 10k nur als
letzter Fallback; Basis-Faktor (real/virtuell) im Forensik-JSON führen.
Test: SafeGold-Fixture mit Balance 998 → DD-% ≈ 19 % statt 1,8 %.

**B4 [MITTEL-HOCH, belegt] — Betreuer ist quellen-blind; 16 von 23 künftigen
Betreuer-Zielen würden täglich fehlschlagen.** `betreuer.py:53-73` nimmt alle
🟢/🟡 aus der DB, exportiert aber über MQL5 (`export_positions`);
`betreuer.py:219` hartkodiert mql5.com. Pelik-🟢/🟡 existieren seit 27.09.
(16 von 23 Zielen). doc/20 „Betreuer umstellen" ist offengeblieben und wirkt
jetzt real. Korrektur: Betreuer-Scope auf `quelle` filtern oder Quellen-Export
über ingest-Cache (SHA-Delta) statt MQL5-Exporter. Test: pelik-🟢 in DB →
Betreuer-Lauf muss Cache-Pfad nehmen, nicht mql5.com.

**B5 [MITTEL, belegt] — Pelican-Kandidatenraum ist eine einmalige manuelle
UI-Auswahl, kein Marktdurchschnitt.** `weeks=0` bei 735/781 Katalog-Einträgen
heißt „Stats nie geladen" (Stats werden nur für die UI-gefilterte Liste
geladen, `Provider.java:242-246`, `App:1167`), nicht „jung". Der Wochen≥26-
Vorfilter selektiert damit primär nach „hatte am 27.09. Stats geladen" (46
Provider mit Inception, davon 34 ≥26 Wochen — Arithmetik exakt). Zugleich ist
die Abonnenten-Historie eingefroren (abonnenten.db: genau EIN Snapshot-Tag
27.09.; weekChange/monthChange überall null; Scanner-`subscriber_history` 0
pelik-Zeilen — Wechselwirkung mit B9). Wirkung: Auswahlverzerrung „Überlebende
der manuellen Auswahl + Populäre"; 735 Provider sind ungeprüft draußen, obwohl
der Katalog 781 meldet. Korrektur: weeks=null statt 0 senden, wenn keine Stats;
„Statistiken für ALLE" als Daemon-Takt vor dem Wochenfilter; pelik-weeks nur
mit Stats-Belag werten.

**B6 [MITTEL, belegt] — 8 von 60 Slots (13 %) ohne Urteil; Öl-/Index-Anbieter
systematisch draußen.** 2 neue Parser-Artefakte (840474 „Zeile 9220:
Pflichtfeld fehlt (Buy)"; 2268766 „unbekannter Datensatztyp 'Correction'" —
beide Fehlerbilder deterministisch, Roh-CSVs der Fails nicht archiviert ③),
4× USOIL `cross_broker=false` bei UNBEKANNTEM Broker (Quellen-Metrics liefern
keine Broker-Kennung; `exposure.py:231` verweigert zu Recht) — darunter **AIT
FX, der abonnentenstärkste Pelican-Kandidat (1514)** —, 2× GER40 ohne Spec
(`contract_specs.json` kennt nur DE40, Alias fehlt). Persistenz der Fails
korrekt (`last_fehler`, Teil-Forensik, kein ⚪-Chronik-Eintrag). Korrektur:
Parser-Artefakte behandeln + Tests; GER40→DE40-Alias; Öl für Quellen-Signale
mit Warnflag „Broker unbekannt, Annahme X Barrel/Lot" statt harter Verweigerung
oder Broker je Provider nachliefern (Pelican hat ServerCode je Trade).

**B7 [MITTEL, belegt] — ⛔-Ausschlüsse belegen 13 von 60 Slots und volles
LLM-Budget.** Auswahl sortiert nur nach Abonnenten; ⛔ wird erst in `ampel_for`
markiert (`fix_signale.py:62-95`, `pipeline.py:354-357`), LLM-Jobs = alle
forensik-vollständigen ohne Ampel-Filter. Im Lauf: 13/60 Slots (43 % der
MQL5-30) an known_signals-Ausschlüsse (verifiziert: alle 13 IDs auf der Liste),
alle mit 3-Prompt-Behandlung (~400k Tokens für fix entschiedene Urteile), 12
nicht-ausgeschlossene MQL5-Kandidaten kamen nicht in die Forensik. Korrektur: ⛔
aus der Export-Auswahl filtern (oder N-taktiges Re-Scan), LLM für ⛔ sparen.

**B8 [MITTEL, belegt] — `fix_signal_ids` leer: die Empfehlungs-Signale wurden
nicht gescannt.** Verifiziert: `config/app_settings.json` → `fix_signal_ids:
[]`. KiraCat #2342895 (Empfehlung „Ertragsträger") hat Forensik vom 08.09. und
wird so unverändert über REST ausgeliefert; Gold Spike MT5 #2375480 vom 05.09.
Die Lücke, wegen der Fix-IDs am 28.09. gebaut wurden, ist operative Realität.
Korrektur: IDs setzen; GUI-Banner, wenn eine Empfehlung weder im Scope noch
Fix ist.

**B9 [MITTEL, belegt] — Downloader-Abgleich bricht am ersten Signal ab;
Base-URL-Divergenz unbemerkt.** `_ueber_quellen` (`downloader_sync.py:51-61`)
wirft, weil pelik für MQL5-Signale nur 404 (leere Liste ≠ „ergebnis") liefert
und :8089 down ist → 02:53:53 Abbruch, 0 Punkte geschrieben; Spiegel +
`subscriber_history` stehen auf 20.09., die 7/30-Tage-Abonnentenbilanz rechnet
auf stale Daten. Dazu: Settings `downloader_base_url=http://192.168.178.164:8089`
vs. Datenquellen-Tabelle `http://localhost:8089` — divergiert, ohne Warnung
(verifiziert). Korrektur: 404-only-Ergebnis als „Quelle kannte Signal nicht"
werten, solange eine Quelle antwortet; Warnung bei URL-Divergenz.

**B10 [MITTEL, belegt] — Equity-Reko nur für 14/28 MQL5-Signalen wirksam.**
8× Skip weil Kursdaten für ALLE Trades fehlen (Broker-Suffix-Symbole AUDCADR,
XAUUSD.F, EURUSD+, *-ECN, XAGUSD.Z — das lokale Tickmill-Terminal kennt sie
nicht), 7× Abdeckung <95 % (korrekt nicht in die Schranke). Die am 28.09.
gebaute vierte Schranke wirkt bei Suffix-Brokern faktisch nicht. Korrektur:
suffix-tolerante Symbol-Auflösung (Basis-Symbol mit Warnung).

**B11 [MITTEL, belegt] — USD-Feld wird von beiden LLM-Stufen als Prozent
misslesen.** `shock_pct_peak_account` (USD; Wahrheit nur als Code-Kommentar
`ampel_matrix.py:235`) fließt unkommentiert ins Forensik-JSON; Risiko- UND
Gesamtbericht zitieren „293,78 %" / „Stressexposure 156–294 % des Kontos"
(analyses id 836/837, Techno Long Term; Ampel dort 🔴 — folgenlos, aber
systematisch irreführend; gleiches Muster im Portfolio-Bericht für Lexo
„Schock 102,9 %" korrekt verwendet, da echter Prozentwert). Korrektur: Feld
umbenennen (`shock_peak_account_usd`) + Einheitenzeile in alle Prompts.

**B12 [MITTEL, belegt] — Eingebaute Default-Prompt-Vorlagen driften von den
Dateien.** `prompts.py:160` (DEFAULT_GESAMTBERICHT): „Ertrag unter der
Monatsschwelle bedeutet **Ablehnung**" — widerspricht korrigierter Datei
`gesamtbericht.md:55-57` und Engine-Verhalten; DEFAULT_RISIKO_ANALYSE fehlt die
Reko/M2-Sektion. Bei Datei-Verlust/Reset kehrt die falsche harte Regel zurück.
Korrektur: Defaults aus den Dateien generieren oder synchrone Tests
(Defaults ≡ Dateien).

**B13 [MITTEL, belegt] — Tiefenanalyse behauptet „jeden Trade", sieht aber die
gleiche Stichprobe wie Prompt 1.** `prompts.py:21-22` + `tiefenanalyse.md:21-36`
vs. `llm_runner.py:243` (12/6/25/20/10-Zeilen-Kuratierung). Die Dossier-Profile
(Phase B) destillieren aus einer Analyse, die „jeden Trade" nie sah. Korrektur:
Vorlage ehrlich fassen oder Voll-Export für die manuelle Tiefenanalyse.

**B14 [MITTEL, belegt] — CLI-Einzelrollen ohne Rollen-Lock.**
`__main__.py:55-76` (`--markt/--betreuer/--digest/--chef` direkt); Daemon, GUI
und Komplettkette sperren korrekt (Lock v4). GUI-Klick + CLI parallel =
Doppel-Export/Doppel-Kosten. Korrektur: Rollen-Lock auch auf CLI-Weg.

**B15 [MITTEL-NIEDRIG, belegt] — Platzhalter-Meldung in der Produktiv-DB.**
`agenten_meldungen` id=7 (29.09. 17:50:42, typ laufsperre, titel „Titel", text
„Text", quellen_json `["lauf#1"]`): kein Codepfad erzeugt das (einziger
laufsperre-Schreiber mit echten Inhalten; REST rein lesend) — manueller
Testeintrag, der im Postfach der GUI erscheint. Korrektur: löschen; DB-Check
auf Titel=="Titel" als Regressionstest.

**B16 [NIEDRIG, belegt] — Prompt-Injection-Fläche.** Anbieter-kontrollierte
Strings (Signalnamen wie „💎t.me/Mr_Profit_FX", Autor, Broker) fließen unmarkiert
in alle Prompts (`pipeline.py:424-437`); keine Vorlage markiert sie als Daten;
nur Trade-Kommentare gekappt (F-9). Im Ziellauf keine Manipulation beobachtet.
Korrektur: Daten-Delimiter + „Signalnamen sind Fremdtext"-Zeile in alle 5
Workflow-Vorlagen.

### B) Begründete Risiken (im Ziellauf nicht eingetreten)

- **R1 ID-Kollision mql5↔pelik möglich und würde still überschreiben**
  (`signals`-PK = signal_id allein; ID-Räume überlappen numerisch — im Lauf
  Schnittmenge leer). Minimal-Fix: Quelle-Wächter beim Upsert. (doc/20 Stufe 2–4
  bekannt.)
- **R2 REST :8611 liefert Gesamtkatalog (91) mit alten Ampeln ohne
  Altersmarker** (KiraCat 🟡 Stand 08.09. live dabei). Feld
  `forensikUpdatedAt`/`stale` ergänzen.
- **R3 Quell-Ausfall senkt den Lauf nicht ab** (gewollt), aber Run-Archiv
  trägt keinen strukturierten Quellenstatus (nur Log-Zeile) —
  Verbesserung: Feld in results.json.
- **R5 Token-Vollkosten ~1,7 M/Lauf:** Berichts-Basis = CSV-SHA ändert sich bei
  täglich handelnden Signalen jeden Lauf → alle 52 Berichte neu. Priorisierung
  (🟢/🟡 zuerst) oder Drift-Toleranz erwägen.
- **R-Pelican offline:** PelicanMonitor ist JETZT down (letztes Lebenszeichen
  03:02:33) — nächster Lauf läuft auf Quellenfehler; kein Autostart eingerichtet.
- **R-Whitelist:** `kursdaten.py` (seit 28.09.) hat keine Whitelist-Tests mehr
  (nur `marktdata.py` wird statistisch bewacht; Order-Funktionen in beiden
  nachweislich nicht verdrahtet — bewacht ist es nicht mehr).

### C) Verifiziert sauber (Auszug — volle Listen in den Sub-Notizen)

1. Auswahl exakt reproduzierbar; GUI ≡ Launcher (`waehle_fuer_export` beide).
2. Zahlenkette lückenlos; Token-Summe DB == Log (1.701.552); Chronik
   74 = 22 Vorläufer + 52 Ziellauf; Differenzen results↔Chronik exakt die Fails.
3. Vierfach-Max korrekt bei MQL5: ATong 64,92 %→🔴, UpFuji 39,05 %→🔴,
   unverlässliche Rekos korrekt draußen; 17 Wechsel-Ereignisse sauber begründet.
4. **Nachrechnung 9/9 Trading-DD auf den Cent** (157,20 / 590,92 / 29,62 /
   437,39 / 27,36 USD …), Netto-PnL, Verlustserien, Peak-Lots plausibel;
   „Duplikat"-Schlüssel (Open+Close+Vol+PnL identisch): The Holy Grail 4.197
   von 15.340 Zeilen, Lexo 214, übrige ~0 — Produkt zählt sie genauso (Split-
   Positionen von Massen-Order-Systemen; Pelican dedupliziert serverseitig per
   TradeId, in der Positions-CSV fehlt die ID — echte von Export-Dubletten
   unterscheidet die CSV nicht, PnL-seitig konsistent gezählt); Restdifferenzen
   dokumentiert (Winrate-Tie-Handling, Peak-Off-by-one, Ertrags-Definition).
5. FX/Währung: 12/12 Lexo-Trades exakt (EUR/JPY/AUD, Cent-Rundung), Preise und
   Mengen unverändert; **keine ×100-Dopplung** (Pelican liefert Prozent, Scanner
   reicht 1:1 durch); 31-Tage-Blöcke ohne Lücke/Überlappung; TradeId-Dedup sauber.
6. Identitäts-/SHA-Kette je Signal über alle 9 Stufen inkl. PDFs und Portfolio.
7. Terminal-Politik: portabler Selbststart 00:02:31, `kursdaten_beenden()` im
   finally (GUI UND Launcher) — kein MT5-Leak; kein Terminal-Prozess aktiv.
8. MCA100-Fix ccc383b im Lauf bestätigt (Reko 13,92 % statt Crash); GMT-Plateau
   0 Fälle; kein „Prüfung fehlgeschlagen"-Datenverlust (8×2 Versuche
   deterministisch, `last_fehler` persistiert).
9. KI-Antworten: SL-Neutralität 4/4 eingehalten (begründete Abwertungen nur wo
   erlaubt), Engine-Bindung 4/4 (kein Upgrade aus ⛔/🔴), Portfolio-Zahlen
   12/12 Spotchecks wahr, Budgets korrekt getrennt (Workflow 5 Mio vs. Agenten
   500k/Tag), Length-Retry + Thinking-Token-Behandlung vorhanden.
10. Portfolio-Empfehlung inhaltlich stark: sortiert Lemonal/AccurateCopier/
    Mr_Profit_FX **wegen** der M2-Diskrepanzen aus (Kompensation von B1/B2),
    SafeGold als „Duplikat Gold Spike" — von mir mit r = 0,77 numerisch
    bestätigt.

---

## 6. Nutzer-Hypothesen und stärkste Gegenposition

**H1 „Abonnenten + Alter ermöglichen sinnvolle Vorauswahl."** —
**Teilweise widerlegt.** Abonnenten korreliert hier mit Ausschluss: 13 der 30
MQL5-Slots gingen an known_signals-⛔ (die riskantesten Signale haben die meisten
Abonnenten — Projektregel 4 bestätigt sich im eigenen Lauf). Das
Empfehlungssignal KiraCat fiel durchs Raster (B8). Bei Pelican filtert
weeks≥26 primär „hatte Stats geladen" (B5), nicht Qualität. Die Vorauswahl
funktionierte trotzdem so, dass 7 Grüne darunter waren — aber der Auswahlkanal
bevorzugt Populäre und Überlebende der manuellen Pelican-Auswahl.
Gegenposition bestätigt: **eine Qualitäts-vor-Popularität-Auswahl** (Score-
gestützt, mehr Slots für Nicht-⛔) hätte dieselben Grünen mit weniger Müll
geliefert.

**H2 „30 je Quelle finden genug hochwertige Kandidaten."** — **Für mql5 nein,
für pelik fast.** pelik: 30 von 34 möglichen (88 % des ohnehin schmalen
Kandidatenraums). mql5: 30 von 69, davon 13 ⛔-Verschwendung + 2 Parser-Fails →
nur 15 fruchtbare MQL5-Slots; ein grüner MQL5-Kandidat (Gold Spike) kam trotzdem
durch — weil er abonnenten-stark ist, nicht wegen der Auswahllogik.

**H3 „Die KI-Analysen liefern zusätzlichen Nutzen."** — **Ja, belegt.** Der
Portfolio-Bericht fand exactly das, was der Engine-Schranke fehlt (M2-Faktoren,
Ertragswidersprüche, Klumpen) — 12/12 Zahlen wahr, keine Ampel-Überstimmung.
Aber: LLM ist nicht bindend (Design), und der USD-%-Missleser (B11) zeigt den
Versagensmodus, wenn Zahlen ohne Einheitenkontext fließen. Nutzen bleibt an
Prompt-/Datenqualität gekoppelt (B12/B13).

**H4 „Die Portfolio-Auswahl erkennt tatsächlich wenig korrelierte Strategien."**
— **Nachträglich gestützt, im Lauf aber unbelegt.** Der Lauf behauptet
„drei getrennte Märkte" ohne jede Korrelationsrechnung. Meine unabhängige
Prüfung: Trio r = 0,043 / 0,033 / −0,201 (Monate, n=11) bzw. 0,075 / 0,137 /
−0,121 (Wochen, n=46); nur 3,8 % der Stunden Dreifach-Exposure; Juli 2026
(Community-Verlustmonat für 7 der 23, inkl. beider Gold-Grids) überstand das
Trio ohne gemeinsamen Verlust. Einschränkend: n=11 → weite Konfidenzintervalle
(r=0,04 ± ~0,55), Lexo×Pentagon instabil über Monatshälften (−0,60 → +0,83).
Details: `portfolio_pruefung.md`.

**Erzwungene 3–4-Empfehlung?** Nein — aber die Daten tragen nur **1 robusten**
Kandidaten: Gold Spike (bewiesener SL 392/392, DD-Vierfach-Max 8,11 %,
Ertrag handelsreal 6,7–8,6 %/M > 5). Lexo und PentagonForex sind
vertretbar-mit-Vorbehalten (Ertrag auf konsistenter Basis < 5 %/M — B2;
Lexo-Schock 102,9 % der virtuellen Basis; Pentagon M2-Faktor 2,2). Ein
viertes Signal ist nicht belastbar (SafeGold korreliert mit Gold Spike,
Ertrag 0,5 %/M real; Lemonal/AccurateCopier/Mr_Profit durch M2 disqualifiziert).

---

## 7. Priorisierte Maßnahmen

| # | Maßnahme (Befund) | Nutzen für das Ziel | Aufwand |
|---|---|---|---|
| 1 | Monitor-EQ-DD in die Schranke/Matrix; 🟢-Sperre >30 % (B1) + pelik-Fixture-Test | schützt die Kernregel | klein |
| 2 | `ertrag_monat_pct_forensik` aus eigener Kurve; Kriterium auf Forensik-Basis (B2) | Ertragsurteil wird kopierer-relevant | klein |
| 3 | Implizite Kapitalbasis (web_balance − ΣPnL) vor 10k-Fallback (B3) | korrigiert DD-/Schock-%-Verzerrung | klein-mittel |
| 4 | Betreuer quellenfest (B4) | verhindert 16 tägliche Fehlerläufe | mittel |
| 5 | Parser-Artefakte + GER40-Alias + Öl-mit-Warnung (B6) | +6 Kandidaten/Lauf, Öl zurück im Kandidatenraum | klein |
| 6 | ⛔ aus Auswahl/LLM sparen (B7) | 12 zusätzliche MQL5-Slots, −400k Tokens | klein |
| 7 | fix_signal_ids setzen + Empfehlungs-Banner (B8) | schließt die KiraCat-Lücke | trivial |
| 8 | Downloader-Sync 404-Toleranz + URL-Divergenz-Warnung (B9) | Verlauf/Bilanz nicht mehr stale | klein |
| 9 | Symbol-Suffix-Auflösung für Reko (B10) | vierte Schranke wirkt bei ~30 % mehr MQL5-Signalen | mittel |
| 10 | Prompt-Fixes: USD-Feld-Einheiten, Default-Drift, Tiefenanalyse-Ehrlichkeit, Injection-Delimiter (B11–B13, B16) | KI-Richtigkeit sistiert systematisch | klein |
| 11 | CLI-Rollen-Lock (B14), Platzhalter-Meldung löschen (B15), REST-Altersmarker (R2), Quell-Kollisionsschutz (R1) | Betriebsrobustheit | klein |
| 12 | Pelican „Stats für ALLE" takten + weeks=null-Ehrlichkeit (B5); PelicanMonitor-Autostart | Kandidatenraum wird echt | mittel |

---

## 8. Antworten auf die acht Leitfragen

1. **Nachweislich korrekt gelaufen:** kompletter Ziellauf Scan #2 (00:02:20–
   02:53:53) mit Listen→Vereinigung→Vorfilter→Auswahl (exakt reproduzierbar)→
   Forensik 52/60 (DD auf den Cent nachgerechnet)→52×3 KI-Berichte→Portfolio→
   Archiv/Persistenz/PDF; Terminal-Politik, Retry, Chronik, Token-Abgleich,
   FX/USC-Konvertierung, SHA-Kette sauber; MCA100-Live-Fix bestätigt.
2. **Fehler/Teilabschlüsse/stille Auslassungen:** Vorläufer-Scan #1 crashte
   (23:32–~23:56, behebt); 8/60 ohne Urteil (stille Slot-Verluste, darunter
   AIT FX); 13 ⛔-Slots verschwendet; Downloader-Abgleich abgebrochen (Spiegel
   20.09.); Tradeserver-Sync nicht ausgelöst (Stand 23.09.); MqlDownloader
   während des gesamten Laufs down; Betreuer/Agenten im Fenster inaktiv (und
   würden bei Reaktivierung auf pelik-Signale fehlschlagen).
3. **Konsistenz über Projektgrenzen:** Werte kettenweise exakt (Catalog↔Cache↔
   SHA↔DB↔Bericht; FX ohne Doppel-Umrechnung). Inkonsistent sind die
   **Bedeutungen**: Kapitalbasis-Annahmen (10k virtuell vs. real vs.
   Plattform-Eigenberechnung) und damit DD-%, Schock-% und Ertrag-% zwischen
   Pelican-Monitor, Scanner-Engine und Plattform-Selbstauskunft (B1–B3).
4. **KI-Aussagen durch Eingaben gedeckt?** Überwiegend ja (12/12
   Portfolio-Spotchecks, 4/4 SL-Neutralität, 4/4 Engine-Bindung; Ertrags- und
   M2-Widersprüche korrekt benannt). Nicht gedeckt: USD-Feld als „%" zitiert
   (B11); „jeden Trade untersucht" in der Tiefenanalyse (B13); Gesamtbild
   repliciert gelegentlich Stufen-1-Deutungen ungeprüft (Design-Risiko).
5. **Agenten in ihren Zuständigkeiten?** Im Zielfenster lief keiner (Daemon
   aus). Code-seitig: Bewertungshoheit korrekt getrennt, Budgets getrennt,
   Lock v4 auf Daemon/GUI/Kette — Lücke CLI-Einzelrollen (B14). Betreuer
   verlässt seine Datenzuständigkeit nicht, kann sie für Quellen-Signale aber
   nicht einlösen (B4). Chef/autonome Scans: im Echtbetrieb unbewährt (0 Läufe).
6. **Findet die Auswahl gute Kandidaten oder Populäre?** Der Kanal selektiert
   nach Popularität (Abonnenten) und Verfügbarkeit (Stats geladen); die
   Qualitätsprüfung passiert erst dahinter — und die fällt bei den Populären
   überwiegend negativ aus (18 🔴 + 13 ⛔ von 60). Die brauchbaren Kandidaten
   (Gold Spike, Lexo, PentagonForex, SafeGold, MicroJump, TKG, HRC) sind
   durch die Forensik gefunden worden, nicht durch die Vorauswahl — ein
   score-gestützter Auswahlkanal würde dasselbe Ergebnis billiger liefern.
7. **Ist 3–4 wenig korrelierte Signale belastbar möglich?** Das Trio Gold
   Spike/Lexo/PentagonForex ist nach meiner unabhängigen Messung tatsächlich
   wenig korreliert (r ≈ 0,0–0,2; 3,8 % Dreifach-Overlap; Juli-Stresstest
   bestanden), aber nur mit n=11 Monaten belegbar und mit Ertrags-/Basis-
   Vorbehalten (B2/B3). Belastbar im Sinne des Projektziels (alle Kriterien
   auf konsistenter Basis) ist derzeit nur Gold Spike; 2 der 3 Positionen
   wären nach Korrektur von B2 grenzwertig. Die Auswahl von 3–4 ist möglich,
   aber die Datenbasis für mehr als 1–2 Positionen ist dünn.
8. **Größter Korrekturnutzen:** (1) Schranken-Lücke B1 schließen — sie betrifft
   die Kernregel des Projekts; (2) Ertragsbasis B2 + Kapitalbasis B3 — sie
   entscheiden darüber, welche Kandidaten überhaupt „grün" sind; danach erst
   Auswahlmechanik (B5–B8). Alle drei sind kleine, testbare Änderungen mit
   großem Hebel auf genau das Auswahlziel.

---

## Anhang: Beleglücken (nicht nachweisbar)

- Roh-CSVs der 8 Forensik-Fails (tmp-Dateien gelöscht; Fehlertexte belegt).
- Individuelle REST-Requests/Latenzen des Ziellaufs an :8090 (kein Access-Log).
- USC ÷100 an echten Daten (kein USC-Konto im Katalog; Codepfad + Lexo-÷100-
  Historie belegt).
- Volltext-Prompts des Ziellaufs (analyses.basis ist nur ein Fakten-Hash;
  Agenten-Schritte archivieren Volltexte, der Workflow nicht).
- `berichte_neu`-Zustand zur Laufzeit (Run-Konfiguration wird nicht archiviert).
- Ursache der MqlDownloader-Downtime (extern; nur URL-Divergenz belegt).
- Ob MqlRealMonitor :8611 tatsächlich abruft (kein Zugriffslog).
- Vollständige inhaltliche Prüfung aller 52 Berichte (4 Fälle + Portfolio
  vollständig, 12 Zahlenspotchecks, Rest statistisch).
