# Prompt-Review — Ziellauf 2026-09-30 (2026-09-30_025355_970680_c65bf5cd)

Quellen: die 5 Workflow-Vorlagen (`config/prompts/*.md`, Stand ccc383b) + 6
Agenten-Vorlagen (`config/prompts/agenten/*.md`), Prompt-Füllung im Code
(`llm/prompts.py`, `llm/prompt_fill.py`, `llm_runner.py`, `pipeline.py`,
`trade_data.py`), die **tatsächlichen Antworten** des Ziellaufs (DB `analyses`:
52× trade/risiko/gesamt + 1 portfolio; Volltext-Dumps in
`sub_ki_agenten/fall_dumps.md` und `portfolio_antwort.txt`). Vollständige
Einzelbefunde: `sub_ki_agenten/notes.md`.

> **Stand 30.09. 17:10 — Code-Stand `fc4b3b9`.** Die Befunde B11 (USD-Feld als
> „%"), B12 (Default-Drift), B13 (Tiefenanalyse-Ehrlichkeit) und B16
> (Injektions-Delimiter) sind in **allen fünf Workflow-Vorlagen umgesetzt** und
> durch einen Sync-Test gegen Code-Defaults gesichert (B12 verhindert jetzt
> Drift). Die Zeilen „konkrete Verbesserung" in der Matrix sind damit für
> diese vier Punkte **erledigt**; sie bleiben als Nachweis der damaligen
> Lücke stehen. **Weiterhin offen und im Nachgang dieses Nachtrags neu
> bewertet:**
> - **Portfolio-Prompt (Zeile 4 der Matrix):** Mein Vorschlag „Engine liefert
>   Korrelationsmatrix" greift **zu kurz**. Die Korrelation untereinander ist
>   nicht das Problem — sie ist gemäß im Trio tatsächlich ~0. **Was fehlt, ist
>   die gleichzeitige Belastung** (B20) und die Instrument-Überlappung (B21).
>   Der Prompt braucht einen **Stress-Monat**, nicht eine Korrelationsmatrix:
>   „Welcher beobachtbare Monat war für die meisten Signale gleichzeitig ein
>   Verlustmonat? Wie steht das empfohlene Trio in genau diesem Monat? Auf
>   wie vielen Monaten beruht diese Aussage überhaupt?"
>   Erst dann ist die Aussage „diversifiziert" belastbar. (Messung Juli 2026:
>   7 von 23 🟢/🟡 gleichzeitig im Minus, Trio nur mit Gold Spike −1,82 % —
>   der Fall liegt also in der *Fragestellung* und der *Stichprobe*, nicht in
>   einem Schaden des Trios. Die Historie-Tiefe ist deshalb Pflichtbestandteil
>   der Antwort, nicht Kosmetik.)
> - **risiko_analyse / gesamtbericht:** brauchen zusätzlich die
>   **Kapitalbasis-Zeile** (B2/B3, Maßnahme #17). Im Ziellauf standen 10k
>   virtuell und 63 154 USD implizit ohne Kennzeichnung nebeneinander — der
>   LLM kann das nicht unterscheiden und nennt eine Prozentzahl ohne Nenner.
> - **portfolio:** Korrelationsmatrix als JSON bleibt sinnvoll (Maßnahme #16),
>   aber **zusätzlich** Instrument-Overlap je Paar als Code-Kennzahl.

## Prompt-Matrix

| Prompt (Modell) | Zweck / Befugnis | belegte Inputs (Lauf) | Qualitätsbefund | Risiko für Auswahlziel | konkrete Verbesserung |
|---|---|---|---|---|---|
| trade_analyse (glm-5.3) | Strategie-Deutung, **keine** Bewertung | Kandidat + Trade-Stichprobe (12/6/25/20/10 Zeilen je Kategorie) | Peak-Exposure/Parallelpositionen NICHT in der Stichprobe → Stufe 1 kann Grid-Risiko unterschätzen (Stufe 3 korrigiert im Gesamtbericht) | mittel — Fehldeutungen wandern in spätere Stufen | Zeile „Parallelpositionen/Exposure nur aus Forensik-JSON beurteilen, nicht aus der Stichprobe" |
| risiko_analyse (glm-5.3-flash) | Risikoprofil, „ändert Ampel nicht" | Kandidat + forensik-JSON + Kriterien | 1a-Regeln (Reko/M2) präzise; **USD-Feld `shock_pct_peak_account` als % zitiert** (id 836: „293,78 %") | mittel — systematisch irreführende Zahlen im Bericht | Felder mit `_usd` benennen + Einheitenzeile; Kommentar aus `ampel_matrix.py:235` in JSON-Doku übernehmen |
| gesamtbericht (glm-5.3) | Urteil-Wort + Score-Deutung; **Engine bindend** | alle Teilergebnisse als Volltext + Kriterien | Beste Vorlage; übernimmt gelegentlich Stufe-1-Deutungen ungeprüft; Ertragsbasis-Widersprüche selbst gefunden (id 912 Mr_Profit: „63,79 % vs. rekonstruiert 0,5–2,2 %/M") | niedrig-mittel | 2 Zeilen ergänzen: „Abonnentenzahl ist kein Qualitätsmerkmal" (fehlt!) + „Historie ist keine Prognose" (fehlt als explizite Regel); Fremdtext-Delimiter |
| portfolio (glm-5.3) | Depot-Mix; ⛔/🔴 nie | NUR 🟢/🟡 mit Vollberichten (23; pipeline.py:1223) | Antwort nahezu fehlerfrei: M2-Faktoren korrekt genutzt, Zahlen 12/12 wahr, kein Ampel-Upgrade; **Diversifikation ohne Korrelationsdaten behauptet** (von außen nachgerechnet: gestützt) | niedrig — aber unbegründete Konfidenz | Engine liefert Korrelationsmatrix der 🟢/🟡-Monatsrenditen als JSON (siehe portfolio_pruefung.md); Quotienten-Rechnung explizit erlauben (beide Zahlen nennen) |
| tiefenanalyse (glm-5.3, manuell) | EINZIGES erlaubtes LLM-Rechnen (Nutzer-Ausnahme 20.09.) | kuratierte Stichprobe wie Prompt 1 | Vorlage behauptet „VOLLSTAENDIGE Trade-Daten"/„Untersuche jeden Trade" (`prompts.py:21-22`, `tiefenanalyse.md:21-36`) — Daten sind dieselbe Stichprobe (llm_runner.py:243) | mittel-hoch — Wahrscheinlichkeitsrechnungen auf unvollständiger Basis; Dossier-Destillation destilliert daraus | Entweder Voll-Export (Token-Budget!) oder Vorlage ehrlich: „Stichprobe X von Y Trades, Kriterium …"; betrifft Ampel/Score nicht (korrekt getrennt) |
| dirigent_planung / markt_kontext / profil_destillation / betreuer_delta / lagebericht / meldung | beobachten/empfehlen, **nie bewerten** | je Rolle Code-JSONs (Lage, Kurse, Dossier, Deltas, Wechsel) + Volltexte | Rollen-Prompts korrekt gegen Neubewertung gerahmt; `meldung.md` Alert-Zweig ist TOT (Alerts laufen LLM-los, melder.py:29-43); Destillation ohne Quellen-Filter (→ Betreuer-Befund B4) | niedrig | meldung.md Alert-Zweig entfernen oder implementieren; Destillation auf `quelle` filtern |

## Querschnittsbefunde

1. **Default-Vorlagen driften** (B12): `prompts.py:160` DEFAULT_GESAMTBERICHT
   enthält „Ertrag unter der Monatsschwelle bedeutet **Ablehnung**" — der
   korrigierten Datei und der Engine widersprechend; DEFAULT_RISIKO_ANALYSE
   fehlt die 1a-Sektion. Zurückkehrende Fehlerquelle bei Datei-Verlust.
   → Defaults deterministisch aus den Dateien ableiten ODER Test
   „Defaults ≡ Dateien".
2. **Keine Prompt-Persistenz im Workflow** (analyses.basis = 64-Zeichen-Hash
   über Fakten): Prompt-Edits invalidieren alte Berichte nicht; Reviews können
   historische Inputs nur rekonstruieren. → Template-Version + Input-SHA in
   analyses speichern (Agenten machen das bereits vorbildlich in
   agenten_schritte).
3. **Injektionsfläche** (B16): Signalnamen/Autoren/Broker unmarkiert in allen
   Prompts; im Lauf kein Manipulationsversuch erkennbar (Namen mit t.me-Links
   harmlos geblieben). → Daten-Delimiter + eine Warnzeile pro Vorlage.
4. **LLM-Arithmetik**: Prompte verbieten nur das *Erfinden* von Zahlen, nicht
   das Rechnen; die Antworten rechnen fleißig (Faktoren, Erwartungswerte) —
   überwiegend korrekt (deckt sogar B2), aber ohne Gegenprobe (Versagensmodus
   B11). → „Rechnen nur mit genannten Zahlen, Quotienten mit beiden Operanden
   zeigen".
5. **Antwortvalidierung/Robustheit** (positiv): Length-Retry (2× Limit),
   Thinking-Token-Behandlung, JSON-/Format-Fallback („Kurzfassummary"-Fallback
   griff 1×, id 816), keine llm_fehler im Lauf; Tokenbudgets korrekt getrennt
   (Workflow 5 Mio: 34 % verbraucht; Agenten 500 k/Tag zählen nur
   agenten_schritte).

## Antwortqualität des Ziellaufs (Volltext-STichproben)

- **SL-Neutralität 4/4** (Pure Gold 2000 neutral offen, Mr_Profit begründete
  Verhaltens-Abwertung, Techno neutral, UpFuji neutral trotz 🔴).
- **Engine-Bindung 4/4**: kein einziges Upgrade über die Engine-Ampel hinaus;
  Abwertungen nur im Rahmen (🟢→„Watchlist").
- **Portfolio**: nur 🟢 im Mix, Maschinenformat exakt, Ausschlussgründe je
  Signal benannt; 12/12 Zahlenspotchecks korrekt.
- **Schwächste Antwort**: id 836/837 (Techno Long Term) — USD-als-%-Fall;
  inhaltlich folgenlos (Signal 🔴), aber das Muster ist bei grünen Signalen
  eine reale Gefahr für die KI-Einordnung.

## Konkrete Ersatzformulierungen (Vorschläge — aktive Prompts unverändert)

- gesamtbericht.md, nach der Ampel-Bindung:
  > „Abonnentenzahl, Signalname und Alter sind KEINE Qualitätsmerkmale
  > (Projektregel: die riskantesten Signale haben die meisten Abonnenten).
  > Historische Rendite beweist keine zukünftige Profitabilität — formuliere
  > Erwartungen immer als Hypothese mit Bedingung."
- risiko_analyse.md, Einheitenzeile über dem JSON-Block:
  > „Alle Felder mit Suffix `_usd` sind USD-Beträge, alle mit `_pct` sind
  > Prozent. `shock_pct_peak_account` ist der Kontostand in USD am Peak
  > (KEIN Prozentwert)."
- portfolio.md, Datenblock-Erweiterung:
  > „Korrelationsmatrix der Monatsrenditen (Code-Befund): … — deute sie;
  > |r| > 0,5 zwischen zwei Positionen ist ein Klumpen-Warnmarker."
  > **UND (dies ist der entscheidende Zusatz, siehe B20):** „Verlustmonat-
  > Cluster (Code-Befund): Im Monat YYYY-MM waren N der M bewerteten Signale
  > gleichzeitig im Minus (Namen …). Prüfe das empfohlene Trio gegen genau
  > diesen Monat und gib an, welchen gemeinsamen Verlust es dabei trug.
  > Geringe Korrelation untereinander belegt KEINEN Schutz vor einem
  > gemeinsamen Schock — sie zeigt nur, dass die Signale nicht dieselbe
  > Tagesbewegung.copyieren. Ein Klumpenrisiko kann vollständig unkorrelliert
  > und dennoch real sein."
  > **Und (Pflichtangabe, siehe B20):** „Nenne für jede empfohlene Position,
  > auf wie vielen Monaten ihre Kennzahlen beruhen (n=…). Eine
  > Diversifikationsaussage über 11 Monate ist eine andere als eine über 46 —
  > das gehört in die Antwort, nicht in eine Fußnote."
- tiefenanalyse.md, ehrlich:
  > „Dir liegt eine kuratierte Stichprobe vor (X von Y Trades; Auswahl:
  > größte Gewinne/Verluste, erste/letzte, Zufall). Rechne nur auf dieser
  > Grundlage und benenne die Grenze."
- **alle Vorlagen, Kapitalbasiszeile** (B2/B3, Maßnahme #17 — noch offen):
  > „Jede Prozentangabe zu Ertrag oder Drawdown bezieht sich auf eine
  > Kapitalbasis. Diese ist: real aus Einzahlungen / implizit aus dem
  > Kontostand / **virtuell angenommen (10 000 USD)**. Virtuelle Basen sind
  >_markiert_ und dürfen nie als reale Anlegerperformance dargestellt werden."
