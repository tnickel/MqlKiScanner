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

> **NACHTRAG 30.09.2026, 16:30 (Code-Stand jetzt `fc4b3b9`).** Nach dem Ziellauf
> wurden die Befunde B1–B3, B5, B6, B7, B9, B10, B12, B14–B16, R1, R2 sowie
> alle Prompt-Härtungen in **einem** Commit `fc4b3b9` (30.09. 15:53) umgesetzt
> (Pelican-seitig `cd9612f`, 15:40). Der geprüfte Lauf entstand **00:02–02:53**,
> also rund 15 Stunden **vor** diesen Fixes.
> Konsequenz für die Bewertung: **B1–B3 sind im Code behoben, im Lauf aber
> unbestätigt** — der Ziellauf ist ein *Vorstufenzustand*. Alle unten als
> „belegt" geführten Ampel-/Ertragsbefunde beschreiben den alten Stand, nicht den
> aktuellen. Ein Re-Scan nach `fc4b3b9` steht **aus** (Blocker: PelicanMonitor
> ist offline, s. R-Pelican; ohne ihn ist die B1/B2-Verifikation nicht möglich).
> Neu aufgenommen in diesem Nachtrag: unabhängige Kapitalbasis-Messung
> (`kapitalbasis_check.py`) und vollständige Korrelationsmatrix aller 23 🟢/🟡
> (`portfolio_check.py`, 226 Paare) — beide in
> `portfolio_pruefung.md` und `kapitalbasis_pruefung.md` zusammengefasst.
> Daraus folgen **zwei neue, offene Befunde**: **B20** (Juli 2026 — sieben
> Signale gleichzeitig im Verlust; das Portfolio prüft Korrelation statt
> gleichzeitiger Belastung und nennt die Beobachtungstiefe des Trios nicht)
> und **B21** (Instrument-
> Überschneidung wird als Diversifikation fehlinterpretiert).
>
> **Korrektur zu B20 (im Nachtrag gemessen, `portfolio_check.py`):** Der
> Schweregrad war zunächst **zu hoch** angesetzt. Von den drei Empfohlenen ist im
> Juli 2026 **nur Gold Spike** im Minus, mit **−1,82 %** (Lexo +5,72 %,
> PentagonForex +1,45 %) — ein gemeinsamer Verlust des Trios ist **nicht
> eingetreten**, und der Juli stützt die Empfehlung sogar. Der tragfähige
> Befund ist die **Fragestellung plus Stichprobenlücke**, nicht ein
> Empfehlungsschaden: das Portfolio prüft paarweise Korrelation und verschweigt,
> dass das gemeinsame Beobachtungsfenster des Trios nur **11 Monate** umfasst
> — also gerade die Ausbruchsmonate des Sortiments (Precise Pair −106,6 %,
> Gold Reaper −7,0 %) nicht abbildet. Die frühere Formulierung „das Trio sei
> durch den Juli diversifiziert" war in **beiden** Richtungen nicht tragfähig:
> ungeprüft nach gleichzeitiger Belastung, und mit „also unkritisch" nicht
> durch die Stichprobe gedeckt.
>
> **Code-Stand:** Der Review wurde gegen `fc4b3b9` geprüft; die Chronologie
> des Ziellaufs bleibt davon unberührt (der Lauf entstand 15 h **vor** dem
> Commit). HEAD ist inzwischen `33c11ac`; die Kette
> `fc4b3b9` → `9942e7d` → `0e1b2b8` → `33c11ac` enthält **keinen** Code-Fix,
> der die Aussagen dieses Reviews über den **Ziellauf** verändert — sie
> betrifft ausschließlich den Stand *nach* dem Lauf. Insbesondere ist B17
> (`fc4b3b9`) widerlegt und B20/B21 (`33c11ac`) nachträglich umgesetzt; die
> Auswertung des Ziellaufs in den Abschnitten 1–6 bleibt davon unberührt.
>
> **Testgrün in diesem Review:** `pytest -q` → **1068 passed, 4 deselected**
> (10 min). Dabei wurde ein **neuer Befund B22** entdeckt und behoben: `fc4b3b9`
> hatte einen abhängigen Test still gebrochen (geänderte Fixture, nicht
> nachgezogene Test-Mutation) — die im Commit gemeldeten „898 grün" sind
> damit als Beleg entwertet.

---

> **Kernbotschaft des Nachtrags (30.09. 16:30 → fortgeschrieben, 21:5x durch
> Gegenprobe des Hauptagenten präzisiert):** Die
> technische Schicht ist nach `fc4b3b9` weitgehend in Ordnung; **der
> eigentliche Fehler ist ein Bewertungsfehler.** Der Portfolio-Lauf prüft
> *Korrelation* zwischen Empfehlungs-Kandidaten und schließt daraus
> *Diversifikation*. Der Juli 2026 zeigt die Grenze: sieben
> Signale gleichzeitig im Minus — vom empfohlenen Trio allerdings nur Gold
> Spike (−1,82 %; Lexo +5,72 %, PentagonForex +1,45 %), die Empfehlung selbst
> ist im Juli nicht beschädigt. Die Kritik bleibt richtig, aber sie zielt auf
> die **Fragestellung und die Stichprobentiefe** (11 gemeinsame Monate), nicht
> auf einen eingetretenen Schaden: Die richtige
> Frage war nie „sind meine drei unabhängig?", sondern „wie stark trifft ein
> gemeinsamer Schock mein Trio?" — und diese Frage wird derzeit nirgends
> gestellt. Dazu kommt: 14 von 16 bewerteten Quellen-Signalen liegen unter
> 5 %/Monat, sobald man die Kapitalbasis korrekt einsetzt (B3).

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

**Was der Nachtrag hinzufügt — und was wichtiger ist als jeder Einzelbefund:**
Die KI-Schicht selbst ist **flächendeckend sauber** (0 Fehler über 157
Antworten, `antworten_pruefung.md`). Damit fällt ein Verdacht weg und ein
anderer wird schärfer:

- **Fällt weg:** der Verdacht, die KI habe M2-Diskrepanzen (46,6 % / 241,3 %),
  Ertragswidersprüche oder Kapitalbasis-Differenzen *nicht* erkannt. Sie hat
  alle drei erkannt, benannt und zur Abwertung geführt (Lemonal, AccurateCopier,
  Mr_Profit wurden daraufhin **aus dem Mix aussortiert**). Die Kompensation der
  Engine-Lücken ist im Lauf also real — nur zufällig, nicht systematisch.
- **Wird schärfer:** die KI prüft **genau das, wonach gefragt wird**. Sie
  kann die Frage „sind drei Signale wenig korreliert?" nicht falsch beantworten
  — und sie beantwortet sie auch dann nicht, wenn sie die falsche Frage ist.
  Juli 2026: sieben Signale gleichzeitig im Minus (B20). Der Portfolio-Auftrag
  fragt nach Korrelation; der Nutzer trägt aber Klumpenrisiko. **Eine saubere
  Ausführung einer unzureichenden
  Fragestellung sieht in der Antwort exakt gleich aus.** Das ist der
  eigentliche Befund dieses Reviews, und er ist im Code, nicht in den Prompts
  zu beheben: das Portfolio-Ergebnis braucht den schlechtesten beobachtbaren
  Monat als Kennzahl, sonst ist „diversifiziert" im Projekt eine Behauptung.
  > **Nachtrag 30.09. 23:15:** Die Verletzung ist im Code behoben
  > (`portfolio_statistik.py`, `33c11ac`) — die drei Kennzahlen sind
  > Berechnung, nicht LLM-Interpretation. Die Aussage dieses Abschnitts
  > beschreibt damit den **Zustand im Ziellauf**, nicht mehr den Projektstand.

> **Was davon am Projektstand noch offen ist (30.09. 23:15, HEAD `33c11ac`):**
> Die Kernmechanik des Ziellaufs ist geschlossen. Es bleiben (a) **B18** —
> der Pelican-Monitor liefert `/reports` leer, die Quellen-KI-Berichte und
> PDFs fehlen weiterhin; (b) die **Kapitalbasis-Angabe im Forensik-JSON/Urteil**
> (Maßnahme #17), damit der Nutzer sieht, auf welcher Bezugsgröße ein 🟢
> beruht; (c) die Einheiten-Klarstellung an `shock_pct_peak_account` (B11/#20).
> Und eine methodische Lehre, die keine Code-Änderung behebt: die Ampel ist
> inzwischen **laufverifiziert**, die Kompensation durch die KI bleibt aber
> **Zufall** — sie ist nicht systematisch garantiert und darf nicht als
> Sicherheitsnetz eingeplant werden.
>
> **Neu seit 01.10. (B23):** Alle bisherigen Maßnahmen betrafen *Korrektheit*
> („ist der DD richtig gemessen?", „auf welcher Kapitalbasis?"). Eine Frage der
> **Auswahl** ist davon unberührt: das Verhältnis Gewinn/Drawdown kommt im
> gesamten Code nicht vor. Die Zwei-Schwellen-Logik (30 % DD **und** 5 %/M)
> beantwortet „ist es zulässig?" — nicht „lohnt es sich?". Im Bestand stehen
> 6 von 16 bewerteten 🟢/🟡 unter Ret/DD 1,0, und die beste Effizienz
> (ImpulseNet 8,65) sieht schlechter aus als KiraCat (0,83), weil der Score
> kein Ertragsgewicht führt. Das ist keine Verletzung der Kernregel
> „Risiko VOR Ertrag", aber eine Lücke im eigentlichen Zweck.

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
| **Nachtrag: Kapitalbasis** | alle 33 Signale mit Forensik: Netto, DD-USD, Monate, produktive Basis + Quelle, Web-Balance, **implizite Basis**, Ertrag %/M auf 10k- UND auf impliziter Basis, DD-% auf beiden; Abgleich Engine ↔ Nachrechnung | `kapitalbasis_pruefung.md`, `kapitalbasis_check.py` |
| **Nachtrag: Korrelationsmatrix** | alle 23 🟢/🟡 (nicht nur das Trio): 34 Paare mit n≥6 Monaten, Instrument-Überschneidung, Verlustmonat-Cluster über **alle** Signale | `portfolio_pruefung.md` (Abschnitt „Voller Portfolio-Korridor"), `portfolio_check.py` |
| **Nachtrag: Export-Historie** | alle 30 pelik-Signale: Zeitspanne (2,9–45,6 Mon.), eigener Anfangszeitpunkt je Signal, `Σ PnL` deckungsgleich mit der Forensik (30/30) — Grundannahme von B3 bestätigt | `historien_check.py`, `kapitalbasis_pruefung.md` §2 |
| **Nachtrag: KI-Antwort-Vollabgleich** | **alle 157** Antworten des Laufs (52× trade + 52× risiko + 52× gesamt + 1× portfolio) mechanisch gegen die Forensik geprüft: Ampelbindung **0/52** Abweichungen, Ertrags-%/Monat **0** Abweichungen, B11-Einheitenmuster **0** Treffer, SL-Regel **17/17** korrekt angewandt, Abonnenten-Argument **0** Treffer | `antworten_pruefung.md`, `antworten_check.py` |
| Nachgelagert | REST :8611 (live, 91 Signale, kein Altersmarker), Tradeserver-Sync (nicht gelaufen), Downloader-Sync (abgebrochen) | sub_scanner C) |

---

## 5. Befunde

Schere: **[KRITISCH]/[HOCH]/[MITTEL]/[NIEDRIG]** · Sicherheit: belegt (Code+Daten
des Laufs) / wahrscheinlich / nicht prüfbar. Jeder Befund mit Ort, Wirkung,
Korrekturidee, Verifikationstest. Gegenprüfung: B1–B3, B6, B8, B9, B15 wurden
vom Hauptagenten unabhängig nachgerechnet bzw. im Code nachgelesen (✓).

### 0) Umsetzungsstand je Befund (Stand HEAD `33c11ac`, 30.09. 23:15)

> **Bilanz: 21 von 24 Befunden geschlossen.** B1–B16 in `fc4b3b9`,
> B17 widerlegt, B22 in `9942e7d`, B1–B3 **live verifiziert** in `0e1b2b8`,
> B20/B21 in `33c11ac`. **Offen: B18** (Pelican `/reports` liefert
> weiterhin eine leere Liste), die beiden Feld-Klarstellungen #17/#20 und
> **neu B23** (Return/Drawdown fehlt als Kriterium, Nutzer-Anforderung
> 01.10.2026 — im Bestand belegt: 6 von 16 🟢/🟡 unter Ret/DD 1,0, und die
> beste Effizienz sieht schlechter aus als die schlechteste).

| Befund | Status im Code | Lauf-verifiziert? |
|---|---|---|
| B1 Monitor-EQ-DD als 5. Schranken-Maximum | ✅ `scoring.dd_maximum` (3 Stellen) + Ampel-Zelle | ✅ **LIVE 30.09.** (`lauf_verifikation_b1_b3.py`: Lemonal 🔴 46,65 %, AccurateCopier 🔴 241,3 %) |
| B2 `ertrag_monat_pct_forensik` maßgeblich | ✅ berechnet + persistiert + im Urteil | ✅ **LIVE 30.09.** (Lexo 1,86 statt 15,4 · PentagonForex 1,12 statt 6,68 · Mr_Profit 3,33 statt 63,8 %/M → 🟡) |
| B3 implizite Kapitalbasis vor 10k-Fallback | ✅ `pipeline._implizite_kapitalbasis` | ✅ **LIVE 30.09.** (6/6 Signale mit `implizit_aus_balance`, z. B. SafeGold 430 USD statt 10.000) |
| B4 Betreuer quellen-blind | ✅ filtert auf `mql5_kandidaten` (dokumentierter Skip) | n/a |
| B5 `weeks` ehrlich null | ✅ Pelican `cd9612f` | ✅ **LIVE 30.09.** (Katalog: kein weeks=0 mehr, null überwiegt) |
| B6 Parser-Artefakte, GER40-Alias, Öl-Broker | ✅ alle drei | ❌ nein |
| B7 ⛔ ohne Forensik/LLM | ✅ via Fix-ID pinbar | n/a |
| B8 `fix_signal_ids` gesetzt | ✅ `[2342895, 2375480]` | n/a |
| B9 Downloader-404-Toleranz + URL-Warnung | ✅ | ❌ :8089 war down |
| B10 Symbol-Suffix-Fallback für Reko | ✅ `suffix_annahmen` protokolliert | ❌ nein |
| B11/B12/B13/B16 Prompt-Härtung | ✅ alle 5 Vorlagen | ❌ nein |
| B14 CLI-Rollen-Lock | ✅ | ❌ nein |
| B15 Platzhalter-Meldung | ✅ gelöscht | — |
| B17 **DE40/GER40 EUR-Quote blockt USD-Schock dauerhaft** | ✅ **zurückgezogen** (Gegenprobe: läuft durch, EUR=EZB-Basis) | ✅ Gegenprobe mit echten Trades |
| B18 **Pelican `/reports` hartkodiert leer** | ❌ **offen (Monitor)** | ❌ |
| B19 **Peak-Positionen — Verdacht vom Vor-Nachtrag entkräftet** | ✅ kein Defekt | ✅ **16/16 exakt reproduziert** |
| B20 **Juli 2026: 7 Signale gleichzeitig im Minus; Portfolio prüft Korrelation statt gemeinsamer Belastung; Beobachtungstiefe nur 11 Monate** | ✅ **`portfolio_statistik` (0-Fix-Welle)**: Verlustmonat-Cluster + Historie-Tiefe + gemeinsames Fenster als Code-Befund im Portfolio-Prompt | ✅ Live-Abnahme am Bestand: Juli-Cluster n=5 sichtbar, Gesamtfenster nur 2 Monate — die Stichprobenlücke steht jetzt IM Prompt |
| B21 **Instrument-Overlap als Diversifikationskriterium fehlt (MH4-1/2: 15 Symbole, r = 0,26)** | ✅ **`portfolio_statistik`**: Paar-Overlap (Jaccard ≥ 0.3, ≥ 3 gemeinsame Symbole) im Prompt, Deutungsregel „Overlap = Klumpenrisiko trotz r≈0" | ✅ Live-Abnahme: H4-1×H4-2 entfällt (H4-1 seit B1 🔴), Holy Grail×MetaTrading2 (J=0,33) & Co. erscheinen |
| B22 **`fc4b3b9` brach einen abhängigen Test still (Fixture-Wert vs. Test-Mutation)** | ✅ **behoben** (Mutation korrigiert + Trefferprüfung als dauerhafte Absicherung) | ✅ **grün** (7/7 `test_review18_ui.py`, 20/20 mit `test_review15_reports.py`) |
| B23 **Return/Drawdown (Calmar) ist als Kriterium nirgends vorhanden — zwei absolute Schranken ersetzen das Verhältnis nicht** | ❌ **offen** (Nutzer-Anforderung 01.10.2026) | ✅ **Bestandsrechnung:** 6 von 16 🟢/🟡 unter Ret/DD 1,0; Median 1,71; schlechtester 0,40. Zusätzlich Fehlurteil-Richtung belegt: beste Effizienz (8,65) sieht schlechter aus als schlechte (0,83), weil der Score kein Ertragsgewicht hat |


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
Workflow-Vorlagen. → **umgesetzt in `fc4b3b9`.**

### A-Nachtrag) Befunde aus dem Nachtrag (30.09. 16:30, Code-Stand `fc4b3b9`)

**B17 [ZURÜCKGEZOGEN durch Gegenprobe des Hauptagenten, 30.09. ~22:00] —
DE40/GER40: die behauptete EUR-Quote-Sperre existiert nicht.**
Die Diagnose des Nachtrags („die Fremdwährungs-Quote bleibt gesperrt → die
2 GER40-Signale scheitern weiterhin an `exposure.run()` und landen ⚪") ist
**empirisch widerlegt**: Mit dem Code-Stand `fc4b3b9` (GER40→DE40-Alias)
durchlaufen die ECHTEN Trades des Ziellauf-Fails 2014626 „Deus ex machina"
(`data/quellen/pelik/pelican_2014626_trades.csv`, 1.294 Trades, u. a. GER40/
US30/AUDCAD) die Produktschiene `parser → forensics.exposure` sauber:
`conversion_complete=True`, `temporal_risk_available=True`, Schock 5.674 USD
(62,3 % auf 10k-Basis), keine Warnung. Der EUR-Quote-Pfad rechnet — EUR ist
die **Basiswährung** der EZB-Referenzkurse, ein Kurs ist daher für jeden
Handelstag belegt (anders als bei exotischen Quote mit Lücken). Die
Ursachen-Kette des Nachtrags verwechselte „Sperre ohne Kurs" mit „Quote !=
USD": Ersteres greift nur bei fehlendem Kurs im 10-Tage-Fenster, bei EUR nie.
Damit ist **B6 für GER40 vollständig geschlossen** (2 der 8 Ziellauf-Fails
entfallen); der früher geplante B17-Fix entfällt. Vorbehalt: 2014626 würde
nach B1-Bewertung wegen Schock 62 % bzw. Ertrag nie grün — aber es bekommt
ein **Urteil** statt ⚪, was der Befund verlangte.

**B18 [MITTEL, belegt, OFFEN (Monitor)] — Pelican `/reports` ist hartkodiert
leer; der PDF-Spiegel der Quellen-Signale bleibt dauerhaft leer.**
`PelicanTrading/.../rest/RestApiServer.java:217` → `case "reports": return
Resp.json(200, Map.of("count", 0, "items", List.of()));` (der Kommentar bei :42
räumt es selbst ein). Vergleich: MqlDownloader `RestApiServer.java:494-500`
liefert echte Dateien. Scanner-seitig gibt es in `ingest.py` **keinerlei**
`reports`-Verarbeitung — die leere Liste wird nie überhaupt abgefragt. Folge: die
KI-Risikoberichte des Pelican-Monitors (MD+PDF, in `data/reports`) erreichen den
Scanner nie, der Downloader-Sync spiegelt keine Quellen-PDFs, und die
PDF-Übergabe an MqlTradeMonitor bleibt für alle 30 pelik-Signale leer — bei
gleichzeitig 60+ lokal erzeugten Scanner-PDFs. Korrektur: (a) Pelican liefert
`/reports` aus dem Verzeichnis; (b) `ingest.py` spiegelt `reports` je Quelle in
`quellen_artefakte` und in den Downloader/PDF-Sync. Betroffen ist die
Vollständigkeit des Endkunden-Artefakts, nicht die Ampel.

**B19 [ENTKRAFTET, verifiziert sauber] — `peak_positionen` (früherer
Verdachts-Befund „Off-by-one/Overlap-Count") ist korrekt.** Unabhängige
Overlap-Zählung der offenen Intervalle aus den Roh-Snapshots reproduziert den
Engine-Wert **exakt für alle 16 pelik 🟢/🟡**: 2000028 37=37 · 2014074 481=481 ·
2063644 32=32 · 2014076 56=56 · 2059368 39=39 · 2084818 13=13 · 2072334 13=13 ·
2039057 18=18 · 2016702 19=19 · 2048285 9=9 · 2048284 27=27 · 2012139 88=88 ·
2049613 6=6 · 2054437 40=40 · 2053240 7=7 · 2052727 70=70. **Kein Defekt, kein
Fix nötig**; der Punkt fällt als Befund weg. (Gleiches gilt für die
Capital-Basis-Rechnung: `kb_prod` meiner Nachrechnung == Engine
`kapitalbasis_usd` für alle 33 Signale mit Forensik.)

**B20 [MITTEL, belegt, OFFEN] — Juli 2026: sieben Signale gleichzeitig im
Verlust. Das Portfolio prüft Korrelation, nicht gleichzeitige Belastung —
die Frage, die den Nutzer tatsächlich trifft, wird nirgends gestellt.**
Aus der Monatsrenditen-Matrix aller 23 🟢/🟡 (`portfolio_check.py`, Rohdaten
`korrelationen_alle.csv`): **2026-07 = 7 Signale im Minus** (2026-05 = 3).
Das ist der kohärenteste Belastungsmonat des gesamten Katalogs.

**Wichtige Präzisierung (nachträglich gemessen, `portfolio_check.py`):** Der
Schweregrad ist **geringer als zunächst angenommen**, und zwar in beide
Richtungen. Die sieben Juli-Verlierer sind: Precise Pair Trading Pro
(−106,59 %!), Gold Reaper (−7,04 %), Pure Gold 2000 (−2,86 %), **Gold Spike
(−1,82 %)**, SafeGold (−1,10 %), AccurateCopier (−0,47 %), Grid King (−0,10 %).
Von den **drei Empfohlenen ist nur Gold Spike** betroffen, und zwar mit
−1,82 % — vernachlässigbar. Die vom Portfolio-Auftrag befürchtete
„Trio-Katastrophe" ist in den Daten **nicht eingetreten**; die Juli-Zahlen
stützen die Empfehlung sogar. Der eigentliche Befund von B20 ist deshalb
**nicht** „die Empfehlung ist im Juli gescheitert", sondern:

1. **Der Katastrophenmonat liegt außerhalb des Beobachtungsfensters der
   Empfehlung.** −106,59 % (Precise Pair) und −7,04 % (Gold Reaper) sind
   Größenordnungen, die keine Monatsrendite eines 🟢-Signals je erreicht hat.
   Die 23 🟢/🟡 umfassen **3 bis 46 volle Handelsmonate**; das **gemeinsame**
   Fenster des empfohlenen Trios ist **11 Monate (2025-11 bis 2026-09)** — genau
   das Fenster, in dem die Korrelationen gemessen wurden. Ein Monat wie Juli
   2026, in dem *mehrere* Systeme gleichzeitig einbrechen, ist in 11 Monaten
   **nicht belegbar beobachtbar**. Die Empfehlung
   „40/30/30" ist damit auf einen Beobachtungszeitraum gestützt, der genau die
   Tail-Risiken nicht enthält, vor denen das Projekt schützen soll. Das ist
   die eigentliche Lücke, und sie ist eine **Stichprobenlücke**, keine
   Rechenlücke.
2. **Die Methode prüft die falsche Größe.** `run_portfolio` summiert
   Korrelationskoeffizienten der drei Empfehlungskandidaten. Ein Klumpenrisiko
   kann vollständig unkorrelliert und dennoch real sein (ungekoppelt, aber
   gemeinsam vom Goldpreis abhängig). Die Kennzahl, die fehlt, ist der
   **gemeinsame Verlustmonat über alle bewerteten Signale** — nicht die
   paarweise Korrelation der Empfehlung.
3. **Ein realer Verlust der Empfehlung ist dokumentiert** (Gold Spike, Juli
   2026, −1,82 %) und im Portfolio-Text **nicht erwähnt**. Er ist unkritisch,
   aber seine Abwesenheit zeigt die Lücke: die Antwort nennt 9 Stichproben für
   „Haltedauern" und „Exit-Logiken", aber **keinen einzigen Stress-Monat**.

Korrektur: Portfolio-Prompt + Code-Kennzahl (a) „Verlustmonat-Cluster über
alle 🟢/🟡" (Anzahl + Namen je Monat) und (b) „längster gemeinsamer
Verlustzeitraum der Empfehlung" — plus die **ehrliche Angabe der
Historie-Tiefe** je Position, damit der Nutzer sieht, dass die Empfehlung auf
11 Monaten Beobachtung beruht.

**B21 [MITTEL, belegt, OFFEN] — Instrument-Überschneidung wird als
Diversifikation missverstanden: Master H4-1 und Master H4-2 teilen 15
Symbole bei nur r = +0,26.** Die niedrige Korrelation der Monatsrenditen
lässt zwei unabhängige Maschinen vermuten; die Rohdaten zeigen dieselbe
Handwerkstatt mit demselben Instrumentensatz. Für die Empfehlung ist das
nur relevant, wenn beide im Kandidatenraum stehen — die Bewertung stützt
sich derzeit allein auf `r`. Korrektur: `run_portfolio`/Scoring sollte
Instrument-Überlappung als **eigenes Diversifikationskriterium** führen
(„gemeinsame Werkzeuge = gemeinsames Risiko"), nicht nur Rendite-
Korrelation; ein Paar mit > 50 % Symbolüberschneidung und r < 0,5 ist
**keine** Diversifikation, sondern Klumpenrisiko mit umgekehrtem Vorzeichen.
(Belege: Holy Grail ↔ Master H4-1 = 13 Symbole, Holy Grail ↔ PentagonForex
= 5; Positivbeispiele mit echtem Nutzen: Lemonal ↔ Gold Spike, AccurateCopier
↔ Mr_Profit.)

**B22 [HOCH, belegt, BEHOBEN] — `fc4b3b9` hat einen abhängigen Test still
gebrochen: die Fixture wurde geändert, der Test nicht nachgezogen.** Beim
Gesamtlauf (`pytest -q`) fielen 5 Tests in `tests/test_review18_ui.py` durch —
ohne Fehlschlag des Produktionscodes. Ursache: Die Fixture
`live_reports` in `tests/test_review15_reports.py` erzeugt ihre Orderbuch-Zeile
als `…;2000;1990;2060;`. `fc4b3b9` änderte den Exit-/TP-Preis von **2010 auf
2060** (B2-Kommentar: Grün verlangt jetzt ≥ 5 %/M auf der eigenen Kurve).
Der abhängige Test `distinct_snapshots` mutiert die Datei aber mit
`.replace(';1990;2010;', ';;2010;')` — **ein No-Op**. Bad und Good waren
dadurch byte-identisch, beide ergaben korrekt `stop_evidence == 'direct'`, und
die Assertion `results[1].stop_evidence == 'none'` schlug fehl.

Zwei Lehren, die über diesen Test hinausgehen:
1. **Ein Test, der eine Fixture „manipuliert", muss die Mutation auch
   verifizieren.** `.replace()` ohne Trefferprüfung ist still — der Test prüft
   dann nicht mehr das Beabsichtigte, sondern fällt nur durch, wenn etwas
   anderes kaputt ist. Das Verschweigen ist schlimmer als der Fehlschlag: Der
   Test hat seinen eigentlichen Zweck verloren (Snapshot-Identität bei
   beschädigter SL-Spalte) und wird erst wieder aussagekräftig, wenn die
   Mutation greift.
2. **`fc4b3b9` hat 898 Tests als grün gemeldet und dabei diesen Bruch
   eingeschleppt** — die Zahl im Commit ist damit als Beleg entwertet. Der
   Commit fasste Änderungen an einer *geteilten* Fixture zusammen, ohne ihre
   abhängigen Tests nachzuziehen. Bei der nächsten Änderung an
   `live_reports` ist das der erste Ort zu prüfen.

Behoben in `tests/test_review18_ui.py` (Mutation auf `;1990;2060;` → `;;2060;`
plus Kommentar zur Fixture-Abhängigkeit) — und **dauerhaft abgesichert**: die
Fixture wird jetzt einmal in `source_text` gelesen, die Mutation als Konstante
`mutation` benannt und vor dem Schreiben mit
`assert mutation in source_text, "… Fixture in test_review15_reports.py::live_reports
geändert?"` **auf einen Treffer geprüft**; danach zusätzlich
`assert bad != source_text`. Damit kann dieser Fehler Modus nicht mehr stumm
wiederkehren. **Gegenprobe:** der Test wurde testweise auf den alten,
nicht mehr passenden Wert `;1990;2010;` zurückgesetzt — er schlug daraufhin mit
der exakten Meldung `AssertionError: Stop-Mutation ';1990;2010;' greift nicht —
Fixture in test_review15_reports.py::live_reports geändert?` fehl (statt mit
einem scheinbar kryptischen `stop_evidence`-Fehlschlag), nach
Zurücksetzen wieder 7/7 grün. Verifiziert: 20/20 grün in `test_review18_ui.py`
+ `test_review15_reports.py`, Gesamtlauf siehe §0.

**B23 [HOCH, belegt, OFFEN (Nutzer-Anforderung 01.10.2026)] — Return/Drawdown
(Calmar) ist als Kriterium **nirgends** vorhanden. Zwei absolute Schranken
ersetzen das Verhältnis nicht. „Niedriges Risiko allein reicht nicht", „Kauf
macht Gewinn bringt es auch nicht" — im Bestand stehen beide Fehlurte
tatsächlich nebeneinander.**

Belege, Stufe für Stufe:

1. **Code:** in `src/`, `config/` und `app_pages/` **kein einziges Vorkommen**
   von `ret_dd`, `return_dd`, `calmar` oder `sharpe` als Auswahlgröße.
   `stats.py:91` und `signal_stats.py:144/145` berechnen `profit_factor`/`sharpe`,
   aber **kein Consumer** wertet sie aus — sie sind reine Anzeige.
2. **Vorfilter `pipeline.py:883`:** prüft ausschließlich `min_wochen` und
   `min_abonnenten`. Keine Kennzahl, die Ertrag oder DD berührt.
3. **Exportauswahl `fix_signale.py:96`:** pro Quelle die Top-30 **sortiert nach
   `-abonnenten`**. Damit geht der teuerste Slot (Trade-Export + Forensik +
   zweistufige KI) an die marketingstärksten Signale — obwohl AGENTS.md
   Regel 4 selbst festhält, dass Abonnenten mit Marketing korrelieren, nicht
   mit Qualität.
4. **Score `scoring.py:19`:** 7 Dimensionen, Gewichte summieren 1,00 —
   drawdown 0,25 · structure 0,25 · margin 0,15 · copy 0,15 · track 0,10 ·
   transparency 0,05 · broker 0,05. **Ertrag kommt nicht vor.** Der Score ist
   reines Risiko; identische Bewertung für die beste und die schlechteste
   Effizienz.
5. **Gates:** `scoring.py:210` (Schranke 30 %), `pipeline.py:461` (Ertrag
   ≥ 5 %/Monat), `ampel_matrix.py:127`/`209`. Zwei **absolute** Grenzen, die
   nie ins Verhältnis gesetzt werden.
6. **Prompts:** in 10 der 11 Dateien kein Effizienz-Auftrag. Einziger Treffer
   ist `tiefenanalyse.md:68` („Max Drawdown vs. durchschnittlicher Gewinn;
   Win-Rate vs. Risk-Reward-Ratio") — eine **qualitative** Textvorgabe an den
   einen manuellen Tiefenanalyse-Prompt, ohne Zahlengrundlage, ohne Schwellen,
   ohne Wirkung auf Ampel/Score/Urteil.

**Empirischer Beleg am Bestand** (16 von 24 🟢/🟡 auswertbar, Ret/DD =
`ertrag_monat_pct_forensik` ÷ DDmax aus `forensik.kriterien_matrix`):

| Kennzahl | Wert |
|---|---|
| Median | **1,71** |
| schlechtester | GOLD Tokyo Scalping **0,40** |
| Bestwert | ImpulseNet 8,65 |
| **unter 1,0** | **6 von 16** (KiraCat 0,83 · Gold Reaper 0,78 · SafeGold 0,64 · EUR Trader 0,94 · GOLD Tokyo 0,40 · Sferica 0,85) |
| unter 2,0 | 10 von 16 |

**Fehlurteil 1 — schlechtes Verhältnis bleibt Beobachtung:** SafeGold
(0,64), KiraCat (0,83) und Gold Reaper (0,78) stehen auf 🟡, obwohl sie
schlechter abschneiden als 1:1. Sie halten nur die 5-%-Schwelle.

**Fehlurteil 2 — gutes Verhältnis sieht schlechter aus:** ImpulseNet mit
Ret/DD **8,65** wirkt schlechter als KiraCat mit 0,83, weil der Score 5,3 vs.
6,3 ist. Der Score misst Struktur und Track Record, nicht Effizienz — die
Aussage „die beste Risiko-Ertrags-Effizienz sieht schlecht aus" ist damit
Systematik, nicht Zufall.

**Der Konflikt mit der Kernregel „Risiko VOR Ertrag".** In `dd_schranke` ist
sie korrekt umgesetzt (harte Ablehnung, überschreibt alles). Der Preis: „Risiko"
heißt dort nur *unter 30 % DD*, nicht *effizient*. Ein Signal auf 28 % DD mit
5,5 %/Monat (Ret/DD 0,20) ist formal gleich bewertet wie eines auf 5 % mit
8 %/Monat (1,60). **Die Zwei-Schwellen-Logik bildet ab, was erlaubt ist, nicht
was sich lohnt.** Die Nutzer-Regel wird also nicht verletzt — aber der
eigentliche Zweck (Risiko *und* Ertrag in Relation) ist nicht abgebildet.

**Korrektur zu einer ersten Lesart:** „in keinem Prompt" wäre falsch gewesen —
`tiefenanalyse.md:68` nennt das Verhältnis durchaus. Präzise ist: qualitative
Textvorgabe in **einer** manuellen Analyse ohne Schwellen und ohne Wirkung auf
Ampel/Score/Urteil.

**Maßnahmen** (siehe §7 Nr. 22–24) — aufsteigend nach Aufwand, alle drei
bewusst **additiv**, ohne die Schranken oder die Risiko-vor-Ertrag-Reihenfolge
anzutasten:
(a) Ampel-Kriterium `effizienz` (Ret/DD mit Buckets 🟢 ≥ 2 / 🟡 1–2 / 🟠 < 1);
(b) Score-Dimension `ertrag_effizienz` ~0,10–0,15, Gewichte auf 1,00 normiert;
(c) **Exportauswahl nach Ret/DD statt Abonnenten** — der wirksamste Hebel,
    weil dort der teure Slot vergeben wird. Braucht vor der Forensik eine
    Zahlengrundlage: `stats_json` des Katalogs (Average3MonthProfit / EQ-DD)
    oder eine Quick-Messung in `build_candidates`. (c) ist die einzige Maßnahme
    mit echter Hebelwirkung auf die tatsächlich geprüfte Menge.

**Beleglücke:** Es gibt keinen Lauf, in dem eine KI das neue Kriterium
korrekt interpretiert; `profit_factor`/`sharpe` sind als Anzeige nie auf einen
Effizienz-Ampel abgebildet worden. Vor der Implementierung ist zu klären, welche
Schwellen der Nutzer als „lohnend" betrachtet (Vorschlag 1,0 = Mindestqualität,
2,0 = Ziel) — die Werte oben sind eine **Rechnung aus dem Bestand**, keine
vom Nutzer gesetzte Schwelle.

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
   **Nachtrag — flächendeckend statt stichprobenartig** (`antworten_pruefung.md`):
   über **alle 157** Antworten des Laufs **kein einziger belegbarer Fehler** in
   fünf Dimensionen: Ampelbindung 0/52 Abweichungen, Ertrags-%/Monat 0
   Abweichungen, B11-Einheitenmuster 0 Treffer, SL-Regel 17/17 korrekt
   (durchgehend *Compliance*-Aussagen, keine Verstöße), Abonnenten als
   Qualitätsmerkmal 0 Treffer. **Die KI-Schicht dieses Laufs ist sauber.**
10. Portfolio-Empfehlung inhaltlich stark: sortiert Lemonal/AccurateCopier/
    Mr_Profit_FX **wegen** der M2-Diskrepanzen aus (Kompensation von B1/B2),
    SafeGold als „Duplikat Gold Spike" — von mir mit r = 0,77 numerisch
    bestätigt.
11. **Nachtrag:** `peak_positionen` Engine == unabhängige Overlap-Zählung
    16/16 (B19, entkräftet); `kapitalbasis_usd` Engine == unabhängige
    Nachrechnung 33/33; die implizite Kapitalbasis (`_implizite_kapitalbasis`)
    liefert für alle 26 pelik-Signale mit Forensik einen **positiven** Wert —
    d. h. B3 ist im Code wirksam, war im Lauf aber noch nicht deployed.

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
−0,121 (Wochen, n=46); nur 3,8 % der Stunden Dreifach-Exposure. **Die
Diversifikation des Trios untereinander ist damit gemessen und bestätigt.**
**Wichtige Einschränkung (B20, aufgenommen nach dem Korridor-Nachtrag):**
Das Trio ist *untereinander* unabhängig — aber das ist eine schwächere
Aussage als sie wirkt. Juli 2026 ist mit 7 Verlustsignalen der kohärenteste
Belastungsmonat des gesamten Katalogs; von den drei Empfohlenen ist dort
**nur Gold Spike** im Minus, und zwar mit **−1,82 %** (Lexo +5,72 %,
PentagonForex +1,45 %). Ein gleichzeitiger Verlust des Trios ist damit
**nicht belegt**. Was die Messung stattdessen zeigt, ist die **Stichproben-
lücke**: der Juli 2026 gehört zu den Monaten, in denen das *Sortiment*
einbrach (Precise Pair −106,6 %, Gold Reaper −7,0 %), und solche Monate sind
in den 11 Monaten Portfoliohistorie **nicht repräsentiert enthalten** — die
Empfehlung „40/30/30" ist damit auf ein Fenster gestützt, das genau die
Tail-Szenarien nicht enthält. Diversität untereinander ersetzt keine
Risikobudgetierung; das Trio sollte als **eine Gold-Position plus eine
Fremdwährungs-Position** behandelt und je Makro-Cluster gedeckelt werden.
Die ursprüngliche Formulierung dieses Abschnitts („das Trio überstand Juli
ohne gemeinsamen Verlust") war eine **Fehldeutung nach beiden Seiten**:
geprüft wurde nur die Korrelation zwischen dreien, nicht die gleichzeitige
Belastung — und die Schlussfolgerung „also unkritisch" ist durch die
begrenzte Historie nicht gedeckt. Einschränkend weiterhin: n=11 → weite
Konfidenzintervalle (r = 0,04 ± ~0,55), Lexo×Pentagon instabil über
Monatshälften (−0,60 → +0,83). Details: `portfolio_pruefung.md`.

**Erzwungene 3–4-Empfehlung?** Nein — aber die Daten tragen nur **1 robusten**
Kandidaten: Gold Spike (bewiesener SL 392/392, DD-Vierfach-Max 8,11 %,
Ertrag handelsreal 6,7–8,6 %/M > 5). Lexo und PentagonForex sind
vertretbar-mit-Vorbehalten (Ertrag auf konsistenter Basis < 5 %/M — B2;
Lexo-Schock 102,9 % der virtuellen Basis; Pentagon M2-Faktor 2,2). Ein
viertes Signal ist nicht belastbar (SafeGold korreliert mit Gold Spike,
Ertrag 0,5 %/M real; Lemonal/AccurateCopier/Mr_Profit durch M2 disqualifiziert).

---

## 7. Priorisierte Maßnahmen

> **Stand 30.09. 23:15 (HEAD `33c11ac`):** Von 21 Maßnahmen sind **19
> umgesetzt** — B1–B16 in `fc4b3b9`, B17 durch Gegenprobe **widerlegt**,
> B1–B3 in `0e1b2b8` **erstmals live verifiziert** (Monitor-Schranke liefert
> jetzt 🔴 für Lemonal/AccurateCopier), B20/B21 in `33c11ac` als
> Code-Befund im Portfolio-Prompt. **Offen bleiben nur B18 (Pelican
> `/reports`, zwei Projekte) und die beiden Feld-/Einheiten-Klarstellungen
> (#17, #20).** Der frühere Blocker „Re-Scan nicht möglich (PelicanMonitor
> offline)" ist **erledigt** — der Monitor läuft wieder.

| # | Maßnahme (Befund) | Nutzen für das Ziel | Aufwand |
|---|---|---|---|
| 1 | ~~Monitor-EQ-DD in die Schranke/Matrix; 🟢-Sperre >30 % (B1)~~ **✅ `fc4b3b9`** | schützt die Kernregel | erledigt |
| 2 | ~~`ertrag_monat_pct_forensik` aus eigener Kurve; Kriterium auf Forensik-Basis (B2)~~ **✅ `fc4b3b9`** | Ertragsurteil wird kopierer-relevant | erledigt |
| 3 | ~~Implizite Kapitalbasis (web_balance − ΣPnL) vor 10k-Fallback (B3)~~ **✅ `fc4b3b9`** | korrigiert DD-/Schock-%-Verzerrung | erledigt |
| 4 | ~~Betreuer quellenfest (B4)~~ **✅ `fc4b3b9`** | verhindert 16 tägliche Fehlerläufe | erledigt |
| 5 | Parser-Artefakte + GER40-Alias + Öl-mit-Warnung (B6) — **✅ komplett** (B17-Gegenprobe: GER40 läuft inkl. EUR-Schock durch; Öl bleibt bewusst broker-gebunden) | +4 Kandidaten/Lauf (2× GER40 + Correction + Tail-Artefakt-Diagnose), Öl nach Broker-Freigabe | erledigt |
| 6 | ~~⛔ aus Auswahl/LLM sparen (B7)~~ **✅ `fc4b3b9`** | 12 zusätzliche MQL5-Slots, −400k Tokens | erledigt |
| 7 | ~~fix_signal_ids setzen + Empfehlungs-Banner (B8)~~ **✅ `fc4b3b9`** | schließt die KiraCat-Lücke | erledigt |
| 8 | ~~Downloader-Sync 404-Toleranz + URL-Divergenz-Warnung (B9)~~ **✅ `fc4b3b9`** | Verlauf/Bilanz nicht mehr stale | erledigt |
| 9 | ~~Symbol-Suffix-Auflösung für Reko (B10)~~ **✅ `fc4b3b9`** | vierte Schranke wirkt bei ~30 % mehr MQL5-Signalen | erledigt |
| 10 | ~~Prompt-Fixes: USD-Feld-Einheiten, Default-Drift, Tiefenanalyse-Ehrlichkeit, Injection-Delimiter (B11–B13, B16)~~ **✅ `fc4b3b9`** | KI-Richtigkeit systematisiert | erledigt |
| 11 | ~~CLI-Rollen-Lock (B14), Platzhalter-Meldung löschen (B15), REST-Altersmarker (R2), Quell-Kollisionsschutz (R1)~~ **✅ `fc4b3b9`** | Betriebsrobustheit | erledigt |
| 12 | ~~Pelican „Stats für ALLE" takten + weeks=null-Ehrlichkeit (B5)~~ **✅ `cd9612f`**; PelicanMonitor-Autostart | Kandidatenraum wird echt | teilweise |
| 13 | ~~**Re-Scan nach `fc4b3b9` zur Lauf-Verifikation von B1–B3**~~ **✅ `0e1b2b8`** — Live-Abnahme am Bestand: Lemonal/AccurateCopier jetzt 🔴 via Monitor-Schranke, Ertrag auf impliziter Basis für 6 Ex-Grün, `weeks=null` und `Broker=ICMarketsLive20` bestätigt | Fixes ändern die Ampel tatsächlich — nicht mehr nur codeseitig belegt | erledigt |
| 14 | ~~**B17: EUR→USD-Schockpfad für DE40/GER40**~~ **✅ widerlegt** — Gegenprobe mit echten Trades läuft durch (EUR = EZB-Basis) | kein Defekt | erledigt |
| 15 | **B18: Pelican `/reports` befüllen + `ingest.py` reports-Spiegel** | Quellen-KI-Berichte + PDFs erreichen Scanner/Tradeserver | mittel (2 Projekte) |
| 16 | ~~**Portfolio-Korridor als Code-Befund** (Monatsrenditen-Korrelation + Instrument-Overlap + Verlustmonat-Cluster in den Portfolio-Prompt)~~ **✅ `33c11ac`** (`portfolio_statistik.py`, +10 Tests) | die Kernbehauptung „wenig korreliert" wird gemessen, nicht behauptet | erledigt |
| 17 | **Kapitalbasis-Faktor im Forensik-JSON/Urteil explizit** (real vs. virtuell) | verhindert erneutes Misslesen wie B11 | klein |
| 18 | ~~**B20: Verlustmonat-Cluster + Historie-Tiefe je Position im Portfolio-Prompt**~~ **✅ `33c11ac`** — Verlustmonat-Cluster, Historie-Tiefe und gemeinsames Beobachtungsfenster sind jetzt Code-Befunde im Prompt; Live-Abnahme: Juli-Cluster (n=5) sichtbar, Gesamtfenster nur 2 Monate | die Stichprobenlücke steht jetzt **im Prompt** statt nur im Review | erledigt |
| 19 | ~~**B21: Instrument-Überlappung als Diversifikationskriterium**~~ **✅ `33c11ac`** — Paar-Overlap (Jaccard ≥ 0,3, ≥ 3 gemeinsame Symbole) im Prompt; H4-1×H4-2 entfällt korrekt, Holy Grail×MetaTrading2 (J = 0,33) erscheint | trennt echte Streuung von Werkstatt-Klonen | erledigt |
| 20 | **Schock-Felder eindeutig benennen**: `shock_pct_peak_account` ist ein **USD-Betrag** (Kontostand am Peak), nicht ein Prozentwert; `shock_pct_max` = Schock ÷ Kontostand am Peak (nicht ÷ Kapitalbasis) | macht die B11-Verwechslung strukturell unmöglich; gleiche Klasse wie #17 | klein |
| 21 | ~~**B22: stille Testkopplung** — Mutation in `test_review18_ui.py` auf den aktuellen Fixture-Wert nachziehen~~ **✅ in diesem Review behoben**; **generell:** Test-Mutationen mit Trefferprüfung versehen (`assert old in text` vor dem `replace`) | schützt die Testgrün-Aussage künftiger Fix-Commits | klein |
| 22 | **B23 (a): Ampel-Kriterium `effizienz`** — Ret/DD aus `ertrag_monat_pct_forensik` ÷ DDmax, Buckets 🟢 ≥ 2 / 🟡 1–2 / 🟠 < 1; additiv neben DD und Ertrag, Schranken bleiben unverändert | macht „schlechtes Verhältnis" sichtbar — 6 Signale < 1,0 fallen derzeit nicht auf | klein |
| 23 | **B23 (b): Score-Dimension `ertrag_effizienz`** ~0,10–0,15, Gewichte auf 1,00 normiert (`scoring.py:19`); **prompts:** Verhältnis als Pflichtangabe statt nur in `tiefenanalyse.md:68` | ein Score, der Qualität *und*Effizienz misst, nicht nur Risiko | mittel |
| 24 | **B23 (c): Exportauswahl nach Ret/DD statt Abonnenten** (`fix_signale.py:96`) — Zahlengrundlage vor der Forensik aus `stats_json` oder Quick-Messung in `build_candidates` | **der wirksamste Hebel:** der teure Forensik-/KI-Slot geht heute an Marketingstärke (AGENTS.md Regel 4) | **mittel–hoch** |

> **B23-Schwellen sind Vorschlag, nicht Festlegung.** Die Ret/DD-Werte in §B23
> sind aus dem Bestand gerechnet. Vor der Umsetzung muss der Nutzer festlegen,
> was „lohnend" heißt (1,0 = Mindestqualität, 2,0 = Ziel o. Ä.).

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
   **Nachtrag:** Diese Bedeutungs-Inkonsistenz ist nicht nur theoretisch. Auf
   der 10k-Annahme allein sitzen 14 von 16 pelik-🟢/🟡 unter 5 %/Monat; auf der
   impliziten Basis (B3) sind es 12. Die DD-%-Verzerrung erreicht Faktor 33
   (Grid King 1,46 % vs. 48,90 %, SafeGold 1,91 % vs. 44,45 %). Vier Signale
   laufen auf einer Basis unter 400 USD (GoldWave 50, Combo Profile 120,
   Precise Pair 225) — ihre 44–89 %/Monat sind rechnerisch richtig, als
   Kopierer-Urteil aber irreführend. **Eine Ampel ohne ausgewiesene
   Kapitalbasis ist keine belastbare Information** (Maßnahme #17).
4. **KI-Aussagen durch Eingaben gedeckt?** **Ja — und flächendeckend belegt.**
   Der Nachtrag-Vollabgleich aller 157 Lauf-Antworten findet **keinen** Fehler:
   Ertragszahlen 0 Abweichungen, Ampelbindung 0/52, Einheiten 0, SL-Regel
   17/17 korrekt. Ebenso wie im Stichprobenbefund gilt: Ertrags- und
   M2-Widersprüche wurden korrekt benannt, keine Zahl wurde erfunden.
   Latent (nicht in diesem Lauf ausgeprägt): „jeden Trade untersucht" in der
   Tiefenanalyse (B13), Übernahme von Stufe-1-Deutungen ohne Gegenprobe
   (Design-Risiko), `shock_pct_peak_account` als USD-Feld mit Prozent-Name
   (Maßnahme #20). **Methodisch wichtig:** weil die KI prompt-treu arbeitet,
   beweisen saubere Antworten nur die *Ausführung* — die *Fragestellung* des
   Portfolio-Auftrags (B20) bleibt davon unberührt.
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
   **Nachtrag (Kapitalbasis-Messung):** Von den 6 pelik-🟢 erreicht auf
   *beiden* Kapitalbasen nur **Lemonal** die 5-%-Schwelle (11,27 → 25,59 %/M);
   drei Signale liegen auf beiden darunter (Lexo 3,44 → 1,83; PentagonForex
   2,59 → 1,08; Mr_Profit 1,05 → 3,20), zwei nur auf der 10k-Annahme
   (SafeGold 0,47 → 11,00; AccurateCopier 2,83 → 6,46). TKG auf 63 154 USD
   impliziter Basis erzielt 0,14 %/M — arithmetisch korrekt, aber ein
   **Kommunikationsproblem**: dieselbe Datenbasis, die im Lauf als Erfolg
   erscheint, rechtfertigt bei realem Kopierer-Kapital kein 🟢. Die Auswahl
   ist also nicht nur „popularitätsblind", sie ist auch **kapitalbasisblind** —
   sie bewertet Rendite, ohne die Bezugsgröße zu nennen.
7. **Ist 3–4 wenig korrelierte Signale belastbar möglich?** Das Trio Gold
   Spike/Lexo/PentagonForex ist untereinander tatsächlich wenig korreliert
   (r ≈ 0,0–0,2; 3,8 % Dreifach-Overlap) — **aber nur mit n=11 Monaten
   belegbar** (Konfidenzintervall r = 0,04 ± ~0,55) und mit Ertrags-/Basis-
   Vorbehalten (B2/B3). **Die entscheidende Einschränkung (B20):** geringe
   Korrelation untereinander ist **kein** Schutz gegen einen gemeinsamen
   Makro-Schock — und die Prüfung, die stattdessen nötig wäre, fehlt. Juli 2026
   zeigt 7 Signale gleichzeitig im Minus (Precise Pair −106,6 %, Gold Reaper
   −7,0 %, Pure Gold 2000, **Gold Spike −1,82 %**, SafeGold, AccurateCopier,
   Grid King); von den drei Empfohlenen ist nur Gold Spike betroffen, minimal.
   Ein Trio-Schaden ist damit **nicht belegt** — der Befund ist die
   **Stichprobenlücke**: Juli 2026 ist ein Ausbruchsmonat des *Sortiments*,
   und ein solcher Monat ist in den 11 Beobachtungsmonaten des Trios nicht
   abgebildet. Wer das Trio als drei unabhängige Einheiten behandelt, hält
   faktisch **eine Gold-Position plus eine Fremdwährungs-Position**, nicht drei
   Positionen. Belastbar im Sinne
   des Projektziels (alle Kriterien auf konsistenter Basis) ist derzeit nur
   **Gold Spike**; Lexo und PentagonForex sind nach B2 grenzwertig.
   **Antwort: Ja, aber nur als deklarierte Makro-Cluster-Deckelung** — nicht
   als „drei unabhängige Signale". Die Datenbasis trägt 1–2 Positionen
   belastbar, nicht 4.
8. **Größter Korrekturnutzen:** (1) Schranken-Lücke B1 schließen — sie betrifft
   die Kernregel des Projekts; (2) Ertragsbasis B2 + Kapitalbasis B3 — sie
   entscheiden darüber, welche Kandidaten überhaupt „grün" sind; danach erst
   Auswahlmechanik (B5–B8). Alle drei sind kleine, testbare Änderungen mit
   großem Hebel auf genau das Auswahlziel. **Nachtrag — und das ist der
   wichtigste Punkt, der im ursprünglichen Review fehlte:** B1–B3 sind mit
   `fc4b3b9` im Code geschlossen, aber die *eigentliche* Verfehlung ist
   entdeckt und noch offen: das Portfolio-Urteil prüft **Korrelation**, nicht
   **gleichzeitige Belastung** — und es nennt die Beobachtungstiefe der
   Empfehlung nicht. Eine Empfehlung, die nur r-Werte über 11 Monate
   summiert, liefert dem Nutzer genau das Gefühl von Sicherheit, das B20
   widerlegt: im Juli 2026 verlor das Sortiment breit, das Trio nicht — und
   genau solche Ausbruchsmonate braucht der Nutzer, um die Empfehlung zu
   prüfen. Der Portfolio-Prompt muss den schlechtesten beobachtbaren Monat als
   **Stress-Szenario** ausgeben („wenn Juli 2026 wiederkehrt: du bist X % im
   Minus") **und die Historie-Tiefe je Position nennen**, sonst ist jede
   Diversifikationsaussage im Projekt eine Behauptung.
   **Stand 30.09. 23:15:** Genau das ist mit `33c11ac`
   (`portfolio_statistik.py`) **umgesetzt** — Verlustmonat-Cluster,
   gemeinsames Beobachtungsfenster und Instrument-Overlap liegen jetzt als
   Code-Befund im Portfolio-Prompt, nicht mehr nur in diesem Review. Damit ist
   die Kernschwäche der Empfehlung **behoben**, nicht nur beschrieben;
   offen bleibt die Beobachtung, ob der nächste echte Lauf die neuen
   Zahlen korrekt nutzt. **Rangfolge der offenen Punkte: B18 (Pelican
   `/reports`, zwei Projekte) → #17/#20 (Kapitalbasis- und Einheiten-Felder
   explizit) → laufende Verifikation von B20/B21 am nächsten Volllauf.**
   (B17 wurde durch Gegenprobe zurückgezogen — GER40 läuft inkl.
   EUR-Schock; B1–B3 sind in `0e1b2b8` live verifiziert.)

      **Stand 01.10.2026 — B23 rückt in der Rangfolge nach vorn:** Die drei
      Punkte oben betreffen *Vollständigkeit und Korrektheit*. B23 betrifft die
      **Auswahl selbst** und damit unmittelbar die Erfüllung des Projektzels:
      Nach allen Korrekturen ist die Kette verlässlich, aber sie bevorzugt weiter
      Signale, die *zulässig* sind, über die, die sich *lohnen*. Rangfolge neu:
      **B23(c) Exportauswahl nach Ret/DD** (der wirksamste Hebel, weil dort der
      teure Forensik-/KI-Slot vergeben wird) → **B23(a)+(b)** (Sichtbarkeit und
      Score-Gewicht) → B18 → #17/#20. Voraussetzung für (c): der Nutzer legt die
      lohnende Schwelle fest (siehe §7 Nr. 22–24).

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
- **Verwendung der neuen Portfolio-Kennzahlen durch die KI im echten Betrieb.**
  `portfolio_statistik.py` ist gegen den vorhandenen Bestand abgenommen (die
  Zahlen erscheinen im Prompt), aber es gibt **noch keinen Lauf**, in dem die
  KI sie korrekt interpretiert hat. Der Test deckt die Berechnung ab, nicht
  ihre Auswertung. Erster Beobachtungspunkt: der nächste Volllauf.
