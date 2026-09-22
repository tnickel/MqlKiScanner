# Benutzerhandbuch — MqlKiScanner

Streamlit-App zum Scannen und forensischen Bewerten von MQL5-Signalen
(MT4 + MT5). **Risiko vor Ertrag.**

## 1. Installation

Voraussetzungen: Python 3.11+, Chrome (für MQL5-Login/Export-Fallback).

```bash
git clone https://github.com/tnickel/MqlKiScanner.git
cd MqlKiScanner
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

Windows-Schnellstart: `start.bat` doppelklicken (legt ggf. venv an und
startet Streamlit unter http://localhost:8504).

## 2. Geheimnisse setzen

Niemals Zugangsdaten in den Code legen. Eine der Varianten:

1. `.env.example` → `.env` kopieren und füllen, oder
2. in der App unter **Einstellungen / Admin** GLM-Key und MQL5-Login setzen
   (landet in `config/secrets.local.json`, gitignored).

| Geheimnis | Env |
|---|---|
| GLM / Z.ai API-Key | `GLM_API_KEY` |
| MQL5-Benutzer | `MQL5_USER` |
| MQL5-Passwort | `MQL5_PASS` |

Ohne MQL5-Login: Testdaten-Modus mit `data/raw/` (Engine ohne Live-Abruf).
Ohne GLM-Key: Scan und Forensik laufen, KI-Berichte entfallen.

## 3. Workflow (Scan-Seite)

Die Scan-Seite hat **zwei Start-Buttons** mit gemeinsamem Stationen-Ablauf
(Signale holen → Auswahl → Prüfen & speichern → KI-Bericht → Portfolio →
Abgleich):

1. **Full-Scan** — der komplette Durchlauf über **alle** ausgewählten Signale:
   holt Signallisten (MT4+MT5), filtert, exportiert Trades der Top-N, rechnet
   Forensik, speichert in SQLite.
2. **Gelb/Grün-Scan** — die regelmäßige Überwachungsrunde (z. B. monatlich):
   prüft **nur** Signale, deren letzte gespeicherte Bewertung 🟢 (Kandidat)
   oder 🟡 (Beobachtung) ist. Alle anderen Farben werden in diesem Lauf nicht
   beachtet. Für jedes geprüfte Signal werden **immer alle KI-Stufen neu
   erzeugt** (Trade-Analyse, Risiko-Analyse, Gesamtbericht; danach der
   Portfolio-Vorschlag über die geprüften Signale) — unabhängig von den
   Toggles „Nur neue Signale", „Vorhandene Berichte neu erstellen" und
   „KI-Berichte". Braucht KI-Key und Kontingent.
3. Optional: **KI-Berichte** (nur Full-Scan betreffend): Trade-/Risiko-Analyse
   parallel, dann Gesamtbericht.
4. Einstellungen: Listen-Seiten, Max. Signale gründlich prüfen (Standard 30),
   Mindestwochen, Abonnenten, Rate-Limits.

**Nur neue** begrenzt das erneute Laden und Prüfen bei MQL5. Die KI berücksichtigt
weiterhin alle geeigneten Ergebnisse: passende vorhandene Berichte werden
wiederverwendet, fehlende oder veraltete erstellt. **Vorhandene Berichte neu
erstellen** erzeugt auch die Berichte übernommener Signale neu.

Während der KI-Berichte zeigt **Signale X/Y**, welches Signal von allen neu zu
berichtenden Signalen gerade bearbeitet wird. Der Zähler springt beispielsweise
von `5/60` auf `6/60`. Bereits vorhandene und deshalb übersprungene Berichte
zählen nicht in dieses Y hinein.

### Ampel

| Symbol | Bedeutung |
|---|---|
| 🟢 | Kandidat (Forensik vollständig, Stop-Evidenz vorhanden, Score &lt; 5, Ertrag ok, kein Ausschluss oder Risikoflag) |
| 🟡 | Beobachtung / kein Kandidat |
| 🔴 | Schranke / Martingale / hartes Risiko |
| ⛔ | Auf Ausschlussliste |
| ⚪ | Vorprüfung oder Fehler (kein vollständiger Export) |

Für Grün müssen alle Positionen einen SL im Orderbuch aufweisen oder es muss
eine ausreichende statistische Stop-Signatur vorliegen. Ein fehlender oder
nur teilweiser Stop-Nachweis ergibt höchstens Gelb, auch bei niedrigem Score
und hohem Ertrag. Drawdown-Verstöße und Martingale bleiben Ablehnungsgründe.

### Ampel-Verlauf und Wechsel-Protokoll

**Farben werden bei jedem Lauf aufgezeichnet:** Jeder erfolgreich gespeicherte
Scan schreibt einen append-only Eintrag in die Farb-Chronik (Tabelle
`ampel_verlauf`: Ampel, Score, Urteil und die komplette 8-Kriterien-Matrix
als Snapshot). Die Chronik beginnt mit der Einführung der Aufzeichnung
(21.09.2026) — ältere Läufe wurden bewusst **nicht** nachträglich importiert.

Gegen den letzten Chronik-Eintrag wird bei jedem weiteren Scan verglichen.
Wird protokolliert (Tabelle `ampel_wechsel`):

- **Farbwechsel** (🟡→🟢, 🟢→🟡, 🟢→🔴, …), oder
- **gekipptes Einzelkriterium bei gleicher Farbe** (Frühindikator — z. B.
  DD-Puffer von 16 auf 2 Punkte geschrumpft, Farbe bleibt aber Gelb).

Jeder Eintrag nennt **welches** Kriterium gekippt ist, den alten und neuen
Zustand sowie die exakte Berechnung. Die Richtung wird eingefärbt:
**📈 Verbesserung** (grün) · **📉 Verschlechterung** (rot) · **ℹ️ Einordnung**
(gelb). Ein Verlust der Datenlage (Entscheidung → ⚪) zählt als
Verschlechterung, neu erkannte harte Ablehnung (⚪ → 🔴) ebenfalls.

Wo die Wechsel sichtbar sind:

- **Scan-Seite, direkt nach dem Lauf:** jeder Wechsel des Laufs als eigene
  Karte (rot/grün/gelb) mit allen Begründungen — Abschnitt
  „⚡ Ampel-Wechsel in diesem Lauf".
- **Ergebnisseite, Button „Wechsel-Protokoll (n)":** die dauerhafte
  Wechselliste aller Läufe (neueste zuerst, Filter „nur Farbwechsel") plus
  Wechsel-Historie je Signal als Farbband.

**Wichtig zum Start:** Der erste Scan nach Einführung ist die **Baseline** —
alle geprüften Signale erhalten ihren ersten Chronik-Eintrag; Wechsel
erscheinen erst ab dem zweiten Scan (z. B. dem ersten Gelb/Grün-Scan einen
Monat später).

**Fehlgeschlagene Prüfungen schreiben nichts:** Bei einem Fehler (z. B.
Export abgebrochen) bleibt der letzte gültige Stand Vergleichsbasis —
temporäre Fehler erzeugen kein ⚪-Flackern in der Historie. Bewerten darf nur
die Engine; der Ampel-Verlauf zeichnet das Engine-Ergebnis nur auf
(Sync/Datenabgleich bewerten nie neu).

## 4. Ergebnisse

- Quelle: aktueller Lauf, Archiv-Run oder **Datenbank (alle Berichte)**.
- Spalte **Stand=NEU** markiert Signale, für die im letzten Lauf dieser Sitzung
  Kennzahlen, Befunde oder Signalberichte neu gespeichert wurden. Unveränderte
  Übernahmen und reine Portfolio-Läufe erzeugen keine NEU-Markierung.
- Detailansicht: Kennzahlen, Forensik, LLM-Texte, Link zur MQL5-Seite.
- Die Tabellenspalte **Bericht & PDF** öffnet für jedes Signal den gespeicherten
  Gesamtbericht. Gleichlautende Signal-IDs aus verschiedenen CSV-Momentaufnahmen
  bleiben über ihren Snapshot getrennt.
- Alle vorhandenen PDFs werden automatisch unter `data/reports/` gespeichert:
  `signale/<ID-Name>/<Snapshot>/01-trade-analyse.pdf`,
  `02-risiko-analyse.pdf`, `03-gesamtbericht.pdf` und
  `portfolio/<Zeitpunkt-Version>/portfolio-gesamtbericht.pdf`.
- **PDF anzeigen** blendet die gespeicherte Datei direkt in der Scan- oder
  Ergebnisseite ein. Direkt daneben lädt **PDF speichern** dieselbe Datei auf
  Wunsch herunter. Die PDFs entstehen ausschließlich aus dem gespeicherten Text
  und lösen bei beiden Aktionen keinen neuen KI-Aufruf aus.

### MqlDownloader: Nutzer-Verlauf und Testberichte

Im **Admin-Bereich → MqlDownloader** wird die Base-URL des lokalen
MqlDownloader-Dienstes konfiguriert (Standard `http://localhost:8089/api/v1`;
`/api/v1` wird automatisch ergänzt, wenn nur Host:Port eingetragen ist) und
optional ein API-Token hinterlegt. **Verbindung testen** führt einen
Health-Check gegen `/health` aus und zeigt Provider-Anzahl und API-Version.

Ist die Verbindung konfiguriert, erscheint in jeder Signal-Detailansicht der
Abschnitt **MqlDownloader**:

- **Nutzer-Verlauf aktualisieren** lädt die Abonnenten-Historie der Signal-ID
  (welcher Tag, wie viele Abonnenten) und zeigt sie als Chart, Kennzahl und
  Datenpunkt-Tabelle.
- **Testberichte aktualisieren** spiegelt die im Downloader liegenden
  Testreport-PDFs dieser Signal-ID; jede PDF lässt sich direkt einblenden und
  über **PDF speichern** herunterladen.

Alles wird lokal gespiegelt (`data/downloader/{Signal-ID}` plus SQLite) und
bleibt auch dann anzeigbar, wenn der Downloader gerade aus ist. Unveränderte
PDFs werden beim erneuten Aktualisieren nicht erneut geladen. Tradelisten holt
der Scanner bewusst **nicht** vom Downloader — die Engine arbeitet mit den
eigenen, verifizierten MQL5-Exporten.

In der Ergebnistabelle zeigt die letzte Spalte **Dokumente** je Signal ein
📄-Icon mit der Gesamtzahl aller PDFs des Signals — **eigene Berichte**
(Trade-/Risiko-Analyse, Gesamtbericht, Tiefenanalyse) plus die gespiegelten
**Downloader-PDFs**. Ein Klick öffnet das Dokumente-Fenster: eigene Berichte
und Downloader-Testreports getrennt gruppiert, jeweils direkt einbettbar und
mit Speichern-Button. Die Tiefenanalyse erscheint zusätzlich im „Bericht & PDF“-Panel
(„Öffnen“) und in der Detailansicht. Anzeige-Buttons **langer** Dokumente sind
**gelb** markiert (Berichte ab 8 000 Zeichen, Downloader-PDFs ab 100 kB) — so
lassen sich kurze und lange Dokumente auf einen Blick unterscheiden; die
Tiefenanalyse ist typischerweise gelb.

Daneben zeigen drei Spalten den Abonnenten-Stand aus dem Downloader-Spiegel:
**Abonnenten** (aktuelle Zahl), **30 Tage** und **7 Tage** (Anstieg 🟢 +x /
Rückgang 🔴 −x / neutral ⚪ 0; kein Vergleichspunkt im Fenster = leer).
Ein Klick auf eine der Zahlen öffnet ein Fenster mit der Verlaufsgrafik —
bei Abonnenten der Gesamtverlauf, bei 30/7 Tage der jeweilige Zeitraum.
Die Bilanz rechnet der Scanner aus dem gespiegelten Verlauf (neuester
Messpunkt gegen den nächstgelegenen Messpunkt vor 7 beziehungsweise 30
Tagen, ±3 Tage Toleranz); liegt der Verlauf kürzer zurück, bleibt die Zelle
leer statt eine Zahl zu erfinden.

**Aktivitäts-Badge oben rechts:** Während Hintergrundsarbeit (Workflow,
Erweiterte KI-Analyse, MqlDownloader-Abgleich) klebt ein gelbes Badge an der
rechten oberen Bildschirmecke und nennt ein Stichwort, was gerade läuft —
es bleibt sichtbar, auch wenn man weit nach unten scrollt, und verschwindet
automatisch mit dem Ende der Arbeit.

**Verbindungsstatus beim Start:** Beim Programmstart prüft der Scanner einmal,
ob der MqlDownloader erreichbar ist, und zeigt das Ergebnis als Badge: grün
**„Downloader verbunden"** (mit Provider-Anzahl und Prüfzeitpunkt) in der
Sidebar unter „Systemstatus", auf der Scan-Seite und im Admin-Bereich. Ist der
Dienst aus, erscheint rot **„Downloader offline"** mit Direktlink zu den
Einstellungen; ohne Konfiguration grau „Downloader optional". Das Ergebnis
wird 5 Minuten zwischengespeichert — Speichern im Admin-Bereich prüft sofort
neu, ein Streamlit-Rerun löst keinen erneuten REST-Aufruf aus.

**Batch über alle Strategien:** Auf der Ergebnisseite startet der gelbe Button
**„🟡 Erweiterte KI-Analyse für alle Strategien starten“** einen Hintergrund-Lauf
über alle Signale der gewählten Quelle mit Trade-Daten. Signale mit bereits
vorhandener Tiefenanalyse werden übersprungen — der Lauf ist dadurch fortsetzbar
(Stop/Neustart kostet nichts). Das Fortschrittsfenster zeigt Balken, Strategie
n/X, den aktuellen Namen, Übersprungen-/Fehlerzähler und einen Stop-Button; jede
fertige Analyse ist sofort in der Datenbank und erscheint als 🟡 in der
Dokumente-Spalte. Ein Scan-Workflow kann während des Batches nicht gleichzeitig
starten.

**Automatischer Abgleich:** Jeder Analyse-Lauf holt in **Station 6** (nach dem
Portfolio) Verläufe und PDFs für die Signale des Laufs. Ist der Downloader aus
oder nicht konfiguriert, bleibt es bei einem Hinweis in der Station — der Lauf
selbst scheitert daran nicht. Auf der Ergebnisseite gleicht der Button
**MqlDownloader-Abgleich** die Signale der gewählten Quelle ohne neuen Scan ab
(nur REST im LAN, keine MQL5-Abrufe).

**Grundregel:** Der Abgleich bewertet **nie** neu. Ampeln, Urteile, Scores und
Berichte bleiben unberührt; frische Verlaufsdaten sind Zusatzkontext, keine
Risikokennzahl, und erzeugen keine „NEU“-Markierung.

### Erweiterte KI-Analyse (Tiefenanalyse)

Zusätzlich zu den Workflow-Berichten gibt es eine **manuelle Vollanalyse**:
Signal in der Tabelle anwählen → in der Detailansicht den Button
**„Erweiterte KI Analyse machen“** drücken. Dabei geht der Tiefenanalyse-Prompt
(Prompt 5) mit den **vollständigen Trade-Daten** (Statistiken + Beispiel-Trades
aus dem Export), den Signal-Kennzahlen, der Engine-Forensik sowie **Signalname
und -Link** (als Platzhalter `{signal_name}` / `{signal_url}` eingesetzt, kein
fester Anbietername im Prompt) an das starke Modell (Stufe 2).

Die Analyse deckt Risikomanagement (Stop-Loss-Gebrauch, Drawdown,
Verlustwahrscheinlichkeit), Grid-/Martingale-Prüfung, Strategie-Typ,
Risiko-Score 1–10, Performance-Forensik und — falls vorhanden —
Userbewertungen ab. Ergebnis: ein eigenes PDF (`04-tiefenanalyse.pdf`) plus
lesbarer Text, dauerhaft in der Datenbank; ein erneuter Klick erzeugt eine
neue Version. Die Vorlage ist editierbar unter **Einstellungen →
Analysevorlagen → ℹ️ Tiefenanalyse** (gelb markierte Sonderrolle, gehört
nicht zum Workflow). Auch diese Analyse ändert nie Ampel, Score oder Urteil.

### Tradeserver-Sync (MqlTradeMonitor)

Der Button **„Tradeserver-Sync“** auf der Ergebnisseite überträgt die
Ergebnistabelle und alle PDFs (eigene Berichte, Portfolio,
Downloader-Spiegel; unveränderte Dateien per SHA-256-Diff) **einmalig** zum
MqlTradeMonitor (Spring-Boot) — Sonderprotokoll v1 unter `/api/kiscanner`
mit X-User-Key-Handshake; danach wird die Verbindung getrennt. Der Monitor
zeigt daraufhin die Kachel „🔬 MqlKiScanner“ samt eigener Seite
`/kiscanner`. Konfiguration: **Admin → Tradeserver** (Base-URL + API-Key im
secrets_store). Der Sync **bewertet nie neu**. Details und Ablaufdiagramm:
[`06_tradeserver-sync.md`](06_tradeserver-sync.md).

### REST-API für den MqlRealMonitor

Für den MqlRealMonitor läuft ein **schreibgeschützter** REST-Server als
Daemon-Thread neben der Streamlit-App (Standard `http://127.0.0.1:8611`,
bewusst nur localhost):

| Endpunkt | Wirkung |
|---|---|
| `GET /api/v1/health` | Statusmeldung (Version, Dienst) |
| `GET /api/v1/signals` | Signalliste mit Gesamt-Ampel; `?ampel=gruen,gelb` filtert serverseitig |

Der Server liest ausschließlich die SQLite-Datenbank und **bewertet nie
neu** — die Ampel wird exakt wie auf der Ergebnisseite aus den gespeicherten
Werten abgeleitet. Es gibt keine Dauerverbindung: der Monitor fragt nur auf
Knopfdruck ab. Auth optional über Header `X-User-Key` (Token via Env
`MQLKISCANNER_REST_TOKEN` oder Admin-UI im secrets_store). Standalone ohne
GUI: `python -m mqlkiscanner.rest_api`.

## 5. Analysevorlagen

Unter **Einstellungen → Analysevorlagen** zeigt ein Ablaufbild, welche
berechneten Engine-Fakten in die vier Vorlagen fließen, welches Modell sie
verwendet und welcher Bericht daraus entsteht. Die Engine berechnet alle
Kennzahlen; die KI interpretiert sie nur. Pflicht-Platzhalter bleiben beim
Bearbeiten geschützt und werden vor dem Speichern geprüft.

## 5a. Agentenbetrieb (Phase A–E — komplett)

Fünf LLM-Rollen übernehmen die Dauerbeobachtung der Signale (Bauplan:
`doc/19_agentenbetrieb-bauplan.md`). **Phase A**: Der Dirigent plant
täglich werktags. **Phase B**: Der Signal-Betreuer prüft täglich die
Trade-Deltas gegen die Algo-Profile. **Phase C**: Der Marktbeobachter
liefert den täglichen Marktkontext aus deinem MetaTrader. **Phase D**:
Der Melder bringt Alerts und den Tagesdigest ins Postfach. **Phase E**:
Der Chefermittler schreibt den Wochen-Lagebericht, und der Dirigent
stößt die Scans selbst an — **Sonntags 12:00 den Gelb/Grün-Scan, am
1. Werktag des Monats den Full-Scan** (mit Portfolio). Der erste
komplett autonome Monat läuft damit an; nachvollziehbar bleibt alles
über das Protokoll.

**Einstellungen → Agenten** (Konfiguration):

- **Start/Stop:** „Agentenbetrieb starten“ setzt die Freigabe und startet
  den Daemon als eigenen Hintergrundprozess (überlebt geschlossene
  Browser-Tabs; Log: `data/agenten_daemon.log`). „Stoppen“ beendet ihn
  kooperativ beim nächsten Tick (max. ~30 s). Der Status zeigt
  Herzschlag und PID.
- **Budget und Takt:** Tages-/Monatsbudget (Standard 500.000 / 5.000.000
  Token — nur Agenten-Modellaufrufe; reguläre Scan-Läufe zählen auf ihr
  eigenes Lauf-Budget) und die tägliche Startzeit (Standard 06:30).
  Wochenende ruht.
- **Rollen:** je Rolle aktiv/aus, Modell (Standard **GLM-5.3** je Rolle;
  Flash wählbar, Freitext für OpenAI-kompatible Modelle) und
  Token-Limit je Aufruf.
- **Rollen-Prompts:** sechs Vorlagen (`config/prompts/agenten/`), editierbar
  wie die Analysevorlagen, mit Pflicht-Platzhalter-Schutz.

**Seite „Agenten“** (Beobachtung):

- **Live:** Daemon-Status, die fünf Rollen mit Phasen-Badge, letzte Läufe.
- **Protokoll:** jeder Schritt chronologisch (Filter nach Rolle und Tag);
  LLM-Schritte öffnen den **vollständig gefüllten Prompt** und die
  **vollständige Antwort** — nichts wird gekürzt. Dieses lückenlose
  Protokoll ersetzt den bewusst abgelehnten Trockenmodus.
- **Dossiers (Phase B):** je Signal das versionierte **Algo-Profil**
  (aus Tiefenanalyse/Gesamtbericht destilliert, mit nummerierten
  Konformitäts- und Warn-Merkmalen), die **Beobachtungen** des Betreuers
  (KONFORM grün / KEINE_NEUEN_TRADES grau / AUFFAELLIG orange /
  STILBRUCH rot) und die **Trade-Deltas** (Hash + Kennzahlen je Abruf).

**Marktdaten (Phase C, Einstellungen → Agenten → Marktdaten):** Der
Marktbeobachter liest Kursdaten über das offizielle MetaTrader5-Paket —
ausschließlich lesend, ohne dass im Terminal etwas installiert wird.
Terminal-Pfad austauschbar; **Selbststart ist standardmäßig AUS** (läuft
das Terminal nicht, wartet der Beobachter und der Lauf wird mit Begründung
übersprungen). Symbol-Beobachtungsliste automatisch aus den 🟢/🟡-
Kandidaten plus eigene Einträge. **Verbindung testen** liest genau eine
XAUUSD-Bar und trennt sofort — der echte Ersttest (V1) gehört mit
laufendem Terminal einmalig gemacht. Der Betreuer zitiert die Tageslage
in jeder Delta-Prüfung; ohne Kontext läuft die Prüfung mit klarem
Platzhalter weiter.

**Postfach (Phase D, Seite „Agenten → Postfach“):** Alerts mit Priorität
(3 kritisch · 2 Warnung · 1 Info) und der Tagesdigest. Stilbrüche melden
sich SOFORT aus der Betreuer-Prüfung; Ampelwechsel werden im nächsten
Daemon-Tick bemerkt (auch aus GUI-Scans) — jede Meldung nennt ihre Quellen
(Protokoll-Schritt, Wechsel-ID, Signal). Der Tagesdigest (Startzeit +
40 min) fasst Läufe, Beobachtungen und Token-Budget des Tages zusammen und
verschiebt sich automatisch, solange der Betreuer noch arbeitet.

**Autonome Scans und Lageberichte (Phase E):** Sonntags 12:00 startet der
Daemon den Gelb/Grün-Scan (Modus-Vertrag wie der Hand-Button: nur 🟢/🟡
mit ALLEN KI-Stufen), am 1. Werktag des Monats ab 07:30 den Full-Scan
mit Portfolio-Vorschlag — derselbe Pipeline-Code wie die Scan-Seite,
einschließlich Login-Prüfung und Fail-Fast-Schutz. Der Abschluss landet
als Meldung im Postfach; Ampelwechsel melden sich über den Watcher. Der
Chefermittler fasst sonntags ab 18 Uhr (und am Full-Scan-Tag) die Woche
im Lagebericht zusammen — Dossiers, Marktkontexte, Wechsel und Budget;
er wartet automatisch, solange ein Scan läuft. Scans dauern lange und
laufen deshalb im Hintergrund-Thread: der Daemon-Herzschlag bleibt
frisch, Stopp während eines Scans beendet ihn allerdings hart (das
Protokoll hält den Stand fest). Manuell anstoßen: `--scan gelbgruen`
bzw. `--scan full`, Lagebericht per `--chef`.

**Wie der Betreuer arbeitet** (täglich 06:45, Startzeit + 15 min): Export
laden (Rate-Limiter, 20-h-Cache — ein GUI-Scan am Vorabend macht den Abruf
zum No-Op) → SHA-Vergleich: unverändert bedeutet **kein Modellaufruf, keine
Kosten**. Neue Trades → Delta-Kennzahlen (reiner Code) → LLM-Prüfung gegen
das Profil → Beobachtung. Fehlt das Profil, wird es einmalig destilliert —
ohne Tiefenanalyse/Gesamtbericht wird nichts erfunden, sondern der Mangel
protokolliert. Die Einordnung ist Beobachtung, nie Neubewertung.

Kommandozeile (ohne GUI): `PYTHONPATH=src python -m mqlkiscanner.agenten`
(Dauerschleife), `--once` (Dirigent) oder `--betreuer` (Betreuer-Tageslauf).

## 6. Typische Stolpersteine

| Symptom | Ursache / Hilfe |
|---|---|
| MT4-Export 404 | Behoben: MT4 nutzt `/export/history`, nicht `/positions` |
| „Kein CSV / Login-HTML“ | Session abgelaufen → Admin „MQL5-Login testen“ |
| GLM 1113 Insufficient balance | Falscher Z.ai-Endpunkt (Coding vs. Pay-as-you-go) |
| Viele „mit Fehlern“ | Export fehlgeschlagen — Log in Schritt 3 prüfen |
| Nur Vorprüfung | Kein Login oder Export übersprungen |
| Downloader nicht erreichbar | Läuft der MqlDownloader? Admin → „MqlDownloader“ → Verbindung testen |
| Gelb/Grün-Scan: „nichts zu prüfen“ | Kein Signal im Katalog ist aktuell 🟢/🟡 — erst einmal Full-Scan laufen lassen |
| „Noch kein Wechsel protokolliert“ | Normal nach der Einführung: erster Scan = Baseline, Wechsel ab dem zweiten Scan |
| Agenten: „Daemon gestoppt“ trotz Start | Nach dem Start dauert der erste Tick bis 30 s; Status basiert auf Herzschlag + PID |
| Agenten-LLM-Schritt „fehler (length)“ | Ausgabelimit zu klein — Admin → Agenten → Rolle → „Max. Tokens je Aufruf“ erhöhen (glm-5.3 braucht Reasoning-Spielraum) |
| Marktbeobachter „übersprungen“ | Terminal läuft nicht und Selbststart ist aus (Standard) — Terminal öffnen; danach liefert der nächste Lauf Kontext |

## 7. Verifikation

```bash
python scripts/verify_engine.py
python -m pytest tests -q
```

Die Engine muss die dokumentierten Ankerwerte aus der Analyse-Reihe
reproduzieren (siehe `doc/01_analysen-verlauf.md`).
