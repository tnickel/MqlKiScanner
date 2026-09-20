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

1. **Analyse starten** — holt Signallisten (MT4+MT5), filtert, exportiert
   Trades der Top-N, rechnet Forensik, speichert in SQLite.
2. Optional: **KI-Berichte** (Trade-/Risiko-Analyse parallel, dann Gesamtbericht).
3. Einstellungen: Listen-Seiten, Max. Signale gründlich prüfen (Standard 30),
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

## 5. Analysevorlagen

Unter **Einstellungen → Analysevorlagen** zeigt ein Ablaufbild, welche
berechneten Engine-Fakten in die vier Vorlagen fließen, welches Modell sie
verwendet und welcher Bericht daraus entsteht. Die Engine berechnet alle
Kennzahlen; die KI interpretiert sie nur. Pflicht-Platzhalter bleiben beim
Bearbeiten geschützt und werden vor dem Speichern geprüft.

## 6. Typische Stolpersteine

| Symptom | Ursache / Hilfe |
|---|---|
| MT4-Export 404 | Behoben: MT4 nutzt `/export/history`, nicht `/positions` |
| „Kein CSV / Login-HTML“ | Session abgelaufen → Admin „MQL5-Login testen“ |
| GLM 1113 Insufficient balance | Falscher Z.ai-Endpunkt (Coding vs. Pay-as-you-go) |
| Viele „mit Fehlern“ | Export fehlgeschlagen — Log in Schritt 3 prüfen |
| Nur Vorprüfung | Kein Login oder Export übersprungen |
| Downloader nicht erreichbar | Läuft der MqlDownloader? Admin → „MqlDownloader“ → Verbindung testen |

## 7. Verifikation

```bash
python scripts/verify_engine.py
python -m pytest tests -q
```

Die Engine muss die dokumentierten Ankerwerte aus der Analyse-Reihe
reproduzieren (siehe `doc/01_analysen-verlauf.md`).
