# Kreuzprüfung der gespeicherten KI-Antworten — Ziellauf 30.09.2026 00:02–02:53

Ergänzung zu `prompt_review.md` (dort die qualitative Einzelanalyse, hier der
**mechanische Vollabgleich** aller 52×3 + 1 Antworten des Ziellaufs gegen die
Forensik-Zahlen des Laufs). Read-only SELECT auf `data/mqlkiscanner.db`,
Antwortmenge über `created_at >= '2026-09-30 00:00:00'` (genau der Lauf —
916 Analysen gesamt, davon 157 aus diesem Lauf).
Prüfskript: `antworten_check.py`, Rohausgabe `antworten_check_out.txt`.

## Umfang

| Größe | Wert |
|---|---|
| Signale im Lauf | 60 |
| Signale mit ≥ 1 KI-Antwort am Lauftag | 53 (die 7 Forensik-Fails natürlich ohne) |
| `trade_analyse` | 52 |
| `risiko_analyse` | 52 |
| `gesamtbericht` | 52 |
| `portfolio` | 1 |

## Ergebnis

| Prüfung | Ergebnis | Bewertung |
|---|---|---|
| **A) Ampel-Bindung (Stufe 2)** — nennt eine `gesamtbericht`-Antwort eine *positiv* vergebene Farbe, die von der Engine nicht vergeben wurde? | **0 Abweichungen / 52** | ✅ Die Engine ist bindend, wie AGENTS.md es verlangt |
| **B) Ertrags-%/Monat gegen Engine** — nennt die KI eine andere Ertragszahl als `ertrag_monat_pct`? | **0 Abweichungen** an den zitierten Stellen | ✅ Zahlenkette exakt |
| **C) B11-Muster** — wird ein USD-Betrag (`shock_pct_peak_account`, `schock_usd`) mit `%` zitiert? | **0 Treffer** im Lauf | ✅ der im Prompt-Review dokumentierte Einzelfall (id 836) ist eine Ausnahme, kein Muster |
| **D) SL-Neutralität** — wird „kein Stop-Nachweis" als **Ausschluss-/Ablehnungsgrund** verwendet? | **0 Verstöße / 17 Treffer geprüft** — alle 17 sind *Compliance*-Aussagen | ✅ siehe unten |
| **E) Abonnenten als Qualitätsmerkmal** | **0 Treffer** | ✅ Design-Regel 4 hält |

### Zu D) im Detail (die 17 Treffer sind keine Befunde)

Die Regex fand 17 Stellen, an denen „Stop/SL" und „Ausschluss" im selben
Absatz stehen. Jede einzelne ist eine **Regelbefolgung**, keine Verletzung:

- 2359404: „…nicht für bewiesenen engen Stop-Schutz; ein begründeter
  Negativbefund ‚wahrscheinlich ohne Stop-Schutz'…" → die KI benennt den
  Negativbefund, sperrt die Ampel aber nicht.
- 2367701: „…das darf als Verhaltens-Signatur leicht negativ werten, bleibt
  aber **kein Ausschlusskriterium**" → explizite Zitation der Projektregel.
- 2021443: „Stop-Nachweis fehlt: **neutral, kein Malus**; die
  Verhaltenssignatur … begründet…" → exakt die Nutzer-Regel vom 28.09.2026.
- 2063644: „SL nicht übertragen — neutral (bindende Regel)" → desgleichen.

**Bewertung: die SL-Regel wird 17/17 korrekt angewandt.** Das ist ein starkes
Argument dafür, dass die Härtung der Vorlage wirkt (B16-Delimiter + die
explizite Neutralitätszeile).

### Zu B) im Detail — die KI rechnet sauber

Stichprobe der zitierten Stellen (jeweils gegen `ertrag_monat_pct` des Laufs):

| Signal | Engine | KI | Kontext |
|---|---|---|---|
| Gold Spike 2349227 | 24,54 %/M | „24,54 %/Monat … weit über der 5-%-Schwelle" | wortgleich |
| Lexo 2000028 | 15,40 %/M | „15,4 %/Monat" | wortgleich |
| PentagonForex 2014076 | 6,68 %/M | „Der Ertrag von 6,68 %/Monat erfüllt die Mindestschwelle von 5,0 %" | wortgleich, inkl. Schwellenbezug |
| SafeGold 2048285 | 6,46 %/M | „Ertrag 6,46 %/Monat — aber Tail-Risiko … Watchlist" | wortgleich, Abwägung korrekt |

**Kein einziger gerundeter oder verschobener Wert.** Das ist ein Befund, den
der Review bis dahin nur stichprobenartig („12/12 Portfolio-Spotchecks")
erfasst hatte — er gilt jetzt **flächendeckend** für die Ertragszahl in
Stufe 2 und 3.

## Ein Nebenbefund, der B11/§2 schärft

Bei der Prüfung von C) ist mir aufgefallen, dass `peak_exposure` **zwei
verschiedene Prozentgrößen** führt, die leicht verwechselt werden:

| Feld | Gold Spike | Lexo | Bedeutung |
|---|---|---|---|
| `schock_usd` | 600,00 | 17 339,39 | Schockbetrag in USD (1 Lot XAU = 100 USD/USD) |
| `shock_pct_peak_account` | **1 966,84** | **16 851,46** | **Kontostand in USD am Zeitpunkt des Peaks** |
| `shock_pct_max` | 30,51 % | 102,90 % | Schock ÷ Kontostand am Peak |
| `kapitalbasis.usd` | 3 116,00 | 10 000,00 | Kapitalbasis (real / virtuell) |

Der Nenner von `shock_pct_max` ist also der **Kontostand am Peak**, nicht die
Kapitalbasis. Für Gold Spike heißt das: der Schock beträgt 600 USD = **19,3 %
der Kapitalbasis**, aber **30,5 % des zu diesem Zeitpunkt bereits
angeschlagenen Kontos** (1 966,84 statt 3 116,00 — der Drawdown hatte die
Basis bereits um 37 % geschrumpft). Beide Zahlen sind richtig, aber sie
beantworten verschiedene Fragen:

- **30,5 %** = „wie vernichtend ist der Schock *für das, was gerade da ist*"
  → die richtige Frage für den laufenden Betrieb.
- **19,3 %** = „wie vernichtend ist der Schock *für das eingezahlte Kapital*"
  → die richtige Frage für den Kopierer, der das Nominalrisiko wählt.

Im Portfolio-Text des Laufs nennt die KI **beide** Größen nicht, sondern nur
30,51 % — und setzt korrekt hinzu: „Schock 30,51 % **der kleinen
Provider-Basis** entspricht". Die KI hat den Feldnamen also richtig
aufgelöst; das Muster ist kein LLM-Fehler. Der Feldname ist aber
**missverständlich** (`shock_pct_peak_account` liest sich wie eine
Prozentangabe und ist USD — genau die Verwechslung, die in B11 einmal
auftrat). `fc4b3b9` hat die Einheitenzeile in den Vorlagen ergänzt; für die
**Verteidigung im Code** fehlt noch eine Umbenennung oder ein
`shock_pct_peak_account_usd`-Alias. Kleine Maßnahme, gleiche Klasse wie #17.

## Fazit

Die **KI-Schicht des Laufs ist sauber** — in allen fünf geprüften Dimensionen
(Ampelbindung, Zahlenkette, Einheiten, SL-Regel, Abonnenten-Argument) **kein
einziger belegbarer Fehler** über alle 157 Antworten. Die Befunde B11/B13
betreffen einzelne Fälle bzw. die *latente* Fehleranfälligkeit der Vorlagen,
nicht das Verhalten dieses Laufs.

**Die offenen Probleme des Laufs liegen sämtlich unterhalb der KI-Ebene:**
Capital-Basis (B2/B3), Ausfallstoleranz (B1) und — neu — die Tatsache, dass
die KI **prompt-treuu** arbeitet, d. h. sie kann einen Portfolio-Auftrag, der
nach *Korrelation* statt nach *gleichzeitiger Belastung* fragt, auch nicht
richtig beantworten kann (B20). Eine saubere Ausführung einer unzureichenden
Fragestellung sieht in der Antwort exakt gleich aus. Das ist die wichtigste
methodische Erkenntnis dieses Abschnitts.

Konkretisiert (nachträglich gemessen, `portfolio_check.py`): Juli 2026 verlor
**7 der 23 🟢/🟡 gleichzeitig** (Precise Pair −106,6 %, Gold Reaper −7,0 %,
Pure Gold 2000, **Gold Spike −1,82 %**, SafeGold, AccurateCopier, Grid King) —
das empfohlene Trio war also **nur mit Gold Spike und −1,82 %** betroffen. Ein
Trio-Schaden ist **nicht belegt**; B20 ist die *Fragestellung* (Korrelation
statt gemeinsamer Belastung) plus die *Stichprobe* (11 Monate, die
Ausbruchsmonate des Sortiments nicht abdecken).
