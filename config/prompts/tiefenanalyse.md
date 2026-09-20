# Prompt 5 — Tiefenanalyse der Handelsstrategie {signal_name} (Erweiterte KI-Analyse, GLM 5.3)

Zweck dieser Analyse: Die Risikobewertung EINER Handelsstrategie zu
Studienzwecken. Es wird nicht mit Geld gehandelt; die Analyse ist keine
Anlageberatung und wird nicht zum Nachhandeln verwendet.

Führe eine umfassende forensische Analyse durch ({signal_url}).
Nutze die bereitgestellten Trade-Daten für eine detaillierte Untersuchung
folgender Aspekte:

## Signal-Kennzahlen (MQL5-Seite, maschinell erfasst)
{kandidat_json}

## Forensik der Engine (maschinell berechnet, massgeblich)
{forensik_json}

## Trade-Daten (Engine-Statistiken + Beispieldaten aus dem Export)
{trades_json}

## 1. Risikomanagement-Analyse
- **Stop-Loss-Verwendung:** Untersuche jeden Trade auf Hinweise für
  Stop-Loss-Nutzung. Analysiere:
  - Gibt es wiederkehrende Verlustmuster bei bestimmten Pip-Werten?
  - Werden Trades bei konsistenten Verlustniveaus geschlossen?
  - Falls kein Stop-Loss: Wie werden Verluste begrenzt?
- **Drawdown-Verhalten:** Analysiere das kommunizierte Drawdown-Limit und
  dessen praktische Umsetzung:
  - Wie hoch kann der maximale Verlust werden?
  - Rechne die Wahrscheinlichkeit eines maximalen Verlusts aus der
    Historie: werte die Trades aus und leite die Wahrscheinlichkeit her
    (nenne die Datengrundlage und die Annahmen).

## 2. Handelssystem-Identifikation
- **Grid-Trading-Indikatoren:** Prüfe auf gleichmäßige Abstände zwischen
  Einstiegspunkten, mehrere offene Positionen in gleiche Richtung und
  symmetrische Kauf-/Verkaufsmuster.
- **Martingale-Merkmale:** Untersuche Positionsgrößen-Erhöhung nach
  Verlusten, Verdopplung oder systematische Erhöhung der Lots sowie
  Recovery-Muster nach Drawdowns.

## 3. Strategische Tiefenanalyse
- **Handelslogik:** Dekonstruiere die zugrundeliegende Strategie:
  Trend-Following oder Counter-Trend? Scalping, Day-Trading oder
  Swing-Trading? Welche technischen Indikatoren sind aus den
  Trade-Mustern ableitbar?
- **Instrumenten-Strategie:** Warum diese spezifischen Paare/Symbole?
  Korrelationsausnutzung?

## 4. Risikobewertung (1–10-Skala)
- **Quantitative Risikofaktoren:** Max Drawdown vs. durchschnittlicher
  Gewinn; Win-Rate vs. Risk-Reward-Ratio; Leverage-Nutzung und
  Margin-Risiko.
- **Qualitative Risikofaktoren:** Transparenz der Strategie,
  Anpassungsfähigkeit an Marktbedingungen, Schwachstellen bei extremen
  Marktbewegungen.

## 5. Performance-Forensik
- Analysiere ungewöhnliche Gewinn-/Verlustspitzen.
- Identifiziere saisonale oder zyklische Muster.
- Bewerte die Konsistenz über verschiedene Marktphasen.

## 6. Userbewertungen
Fasse die Userbewertungen zusammen, sofern im Kandidaten-JSON Review-Daten
vorliegen. Fehlen sie, schreibe explizit, dass keine vorhanden sind.

## Ausgabeformat (Deutsch, Markdown)
1. **Executive Summary** — 3–5 Kernerkenntnisse
2. **Detaillierte Befunde** je Kategorie (1–6)
3. **Kritische Muster** — tabellarisch, wo möglich
4. **Risiko-Scoring (1–10) mit Begründung**
5. **Empfehlungen für potenzielle Follower** — woran sie das Risiko
   erkennen und wie sie es begrenzen würden
6. **Zusammenfassung der Userbewertungen** (falls vorhanden)

Verwende konkrete Trade-Beispiele zur Untermauerung jeder
Schlussfolgerung. Zahlen aus Kandidaten-/Forensik-JSON zitierst du;
Rechnungen auf Trade-Basis (z. B. Verlustwahrscheinlichkeit) leitest du
aus den gelieferten Daten her und nennst Grundlage und Annahmen. Widerspricht
sich Engine-Forensik und dein Trade-Eindruck, gilt die Engine und du weist
darauf hin. Sachlich, keine Emojis, keine Anlageberatung.
