# Review 29.09.2026 — „Bewertung + KI-Ablauf": Verifikation, Fixes, Qualitätsbewertung

**Review-Objekt:** Signalprovider-Bewertung (scoring, Ampel, Matrix, Regelwerk) und
KI-Ablauf (LLM-Runner, Client, Prompts, Betreuer, Dirigent, Melder). 18 Befunde;
vier davon (1, 3, 4, 5) vom Nutzer per Python-Test nachgestellt.
**Ergebnis-Commit:** `d128cc5` — 18 geprüft, 17 behoben, 1 dokumentiert offen (F-13).

## Befunde und Fixes

| Befund | Verifikation | Fix |
|---|---|---|
| **F-1** 🟠 Einordnungs-Parser: `**EINORDNUNG:** STILBRUCH` → AUFFAELLIG (kein P3-Alert); `Einordnung: KONFORM` → AUFFAELLIG; Optionslisten-Echo → KONFORM | ✅ (nutzerbestätigt) | Regex tolerant (Betonung, case, Zeilenanfang); Echo = mehrdeutig → AUFFAELLIG; Tests für alle vier Fälle |
| **F-2** 🟠 Betreuer-Delta verglich gegen den Scan-Stand (trade_files) → Delta kumulierte täglich, LLM prüfte Altes erneut, Alerts wiederholten sich | ✅ | Vergleich gegen letzten GEPRÜFTEN Stand (trade_deltas.neu_sha) + Zeitfilter (close_time > letzte Prüfung); Test: zweiter Lauf mit gleichem Export = kein Modellaufruf, kein zweites Delta |
| **F-3** 🟡 Fehler maskierte die Schranke (45 % DD + Fehler = ⚪ statt 🔴) | ✅ (nutzerbestätigt) | Schranke vor Fehler-Zweigen — **mit Belastbarkeits-Gate** (Suite-Befund): Platzhalter-DD (100 % bei unbekannter Kapitalbasis) bleibt ⚪; ROT nur bei Plattform-DD-Verletzung oder vollständiger Forensik |
| **F-4** 🟡 Berichtsbasis enthielt Abonnenten/Preis/Wochen → jedes +1 ließ alle KI-Berichte „verschwinden" | ✅ (nutzerbestätigt) | Basis nur risikorelevante Felder (DD, Ertrag, PF, Assets, Score); Tests: +1 Abonnent = gleiche Basis, DD-Änderung = andere Basis |
| **F-5** 🟡 Prompt „Ertrag unter Schwelle = Ablehnung" widersprach Engine-🟡 | ✅ (nutzerbestätigt) | Prompt: kein Kandidat, aber keine harte Ablehnung (Engine bindend) |
| **F-6** 🟡 LLM-Ausfall im Betreuer = AUFFAELLIG im Dossier, Delta verbraucht | ✅ | Eigener Status NICHT_GEPRUEFT (EINORDNUNGEN erweitert); kein delta_speichern → nächster Lauf prüft erneut; KEINE_NEUEN-Flut gestoppt |
| **F-7** 🟡 Destillation ohne Basisprüfung/Erneuerung | ✅ | Neu-Destillation, wenn ein neuerer Gesamtbericht existiert (Profil versioniert); |
| **F-8** 🟡 Portfolio bezahlte ⛔/🔴 mit vollem Bericht, Budget-Crash drohte | ✅ | Nur 🟢/🟡; ⛔-Signal testhaft aus dem Prompt ausgeschlossen |
| **F-9** 🟡 Anbieter-Kommentare ungekürzt im Prompt | ✅ | 80 druckbare Zeichen (`_comment_kompakt`) |
| **F-10** 🟡 Tiefenanalyse: Basis erst nach dem 30-min-Call, Fehler still | ✅ | refresh + Basis VOR dem Call, Fehler geloggt |
| **F-11** 🟡 length-Antworten bezahlt und verworfen | ✅ | EIN Retry mit doppeltem Limit (neue Reservierung, Budget geprüft); Tests inkl. Budget-Rand |
| **F-12** 🟡 Vierfach-Maximum 4× dupliziert; Score-Dimension ohne Reko | ✅ | `scoring.dd_maximum` an allen Stellen; Dimension inkl. Reko (caveat-Fall bleibt) |
| **F-13** 🟡 ertrag_monat_pct je Quelle anders definiert, ungeprüft gegen 5-%-Schwelle | ✅ | **Dokumentiert OFFEN** — einheitliche Nachrechnung aus Trades = Konzept-Entscheidung („Code rechnet"), Nutzer vorgelegt |
| **F-14** 🟢 Dirigent-LLM nie ausgeführt, begründung überschreibt resultat | ✅ | Resultat maschinell verbindlich, LLM nur Zusatz; Key „erkennte"→„erkenntnisse"; Ausführung bleibt Phase-A-Planung (doc/19) — bewusst |
| **F-15** 🟢 Melder: Marker erst nach Schleife, Erstlauf-Flut, limit=100 | ✅ | Marker JE Alert; limit 500; Erstlauf mit Historie = EINE Info (Test) |
| **F-16** 🟢 Delta: Set statt Multiset | ✅ | Counter; Test mit identischen Grid-Legs |
| **F-17** 🟢 score() KeyError bei Fremd-Keys | ✅ | Unbekannte Keys fallen raus (Test) |
| **F-18** 🟢 Regelwerk-Text-Widerspruch zur SL-Neutralregel | ✅ | Kategorie präzisiert: Struktur entscheidet, fehlender SL allein nie |

## Besonderheiten der Umsetzung

1. **F-3-Randfall (Suite-Befund, vom Review übersehen):** Der Trading-DD von 100 %
   bei unbekannter Kapitalbasis ist ein Platzhalter, kein Beweis — der nackte
   Reihenfolge-Tausch hätte alle „Kapitalbasis unbekannt"-Signale fälschlich ROT
   gemacht (partial_forensik/quellen-Tests deckten es auf). Gelöst mit dem
   Belastbarkeits-Gate.
2. **Bestehende Tests an neue Semantik angepasst (bewusste Verhaltensänderungen):**
   Portfolio-Fixtures auf 🟢; ⛔-im-Prompt-Test auf Ausschluss umgebaut;
   Truncated-Test erwartet jetzt 75+25 Tokens (bezahlter Retry).

## Qualitätsbewertung des Reviews

| Kriterium | Bewertung |
|---|---|
| Befundqualität (18/18 real) | **5/5** — mit eigener empirischer Nachstellung (F-1/F-2/F-5 + nutzerbestätigt F-1/F-3/F-4/F-5) |
| Priorisierung (Reihenfolge 1-4 exakt richtig) | **5/5** |
| Fix-Vorschläge | **4,5/5** — F-3 fehlte der Platzhalter-Randfall |
| Regel-Konformität der Prüflatte (Engine bindend, SL-neutral) | 5/5 |

**Gesamt: exzellent** — Bestniveau der Serie, zusammen mit dem Handoff-Review.
Einziges dokumentiertes Offen: F-13 (Ertragsdefinition je Quelle) als
Konzeptfrage beim Nutzer.
