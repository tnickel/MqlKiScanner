# Qwen-Code-Review 29.09.2026 — Lock/Guard: Verifikation, Fixes, Qualitätsbewertung

**Review-Objekt:** Commits `4c57277` + `8249326` (Betriebsblocker-Fixes, 3. Review-Nachlese)
**Quelle:** fremde KI (Qwen) — nach unserer Regel jeden Befund am Code verifiziert,
bestätigte behoben, pro Befund berichtet.
**Ergebnis-Commit:** `6548e41` — 5/5 Befunde bestätigt, 5/5 behoben, 165 Agenten-Tests grün.

## Befunde und Verifikation

| Befund | Behauptung | Verifikation | Fix |
|---|---|---|---|
| **M1** 🟠 | `lock.py`: Bei vorhandenem psutil ignoriert die `blockiert`-Expression das Alter komplett — ein psutil-verifiziert lebender PID-Wert blockiert das Lauf-Lock ewig (Windows-PID-Recycling nach Crash; korrupte/unlesbare Datei → „lebend"). Regression: vor `4c57277` griff STALE_S (1 h) immer. | ✅ bestätigt (Expression `(… and STALE_S) or (pid_bekannt and _pid_lebt)` = kurzgeschlossen; Vor-Commit-Code per Git gelesen) | Doppelt: (a) Lock-Datei speichert Prozess-Startzeit (`create_time`), Check erkennt recycelte PID sofort; (b) `MAX_S = 24 h` als ultimative Obergrenze. Ohne psutil unverändert STALE_S. Korrupte Dateien (ts=0) sofort frei |
| **M2** 🟡 | `_pid_lebt`-Kommentar „(Alter greift)" gilt nur ohne psutil — irreführend, Re-Akquisition im selben Prozess wäre Zukunftsfalle | ✅ bestätigt | Mit der Neustrukturierung (`_lock_blockiert`) entfallen; Historie in Docstring |
| **M3** 🟡 | psutil nicht in `requirements.txt`, bestimmt aber die Lock-Semantik (Streamlit bringt psutil NICHT mit) | ✅ bestätigt (Datei geprüft, lokal 7.2.2 zufällig installiert) | `psutil>=5.9` mit Begründungskommentar aufgenommen |
| **M4** 🟢 | Daemon-Guard prüft pauschal 4 h — Betreuer wird aber bewusst mit 2 h bewertet (Digest/fällig-Prüfung): 3-h-verwaister Row → gegensätzliche Entscheidungen | ✅ bestätigt | Rollenspezifisch: `_guard_max_alter_s` — Betreuer 2 h, Rest 4 h |
| **M5** 🟢 | Guard-Skip nur `log()`, nicht im Journal → im Agenten-UI unsichtbar; Wiederholung alle 30 s | ✅ bestätigt | **Abweichend vom Qwen-Vorschlag:** Postfach-Meldung („laufsperre") + Log, genau EINMAL je blockierendem Lauf (De-Dup). Keine Journal-Lauf-Zeile — siehe unten |

## Gegenbefund: Qwens M5-Fixvorschlag wäre selbst ein Bug gewesen

Qwen empfahl, den Skip wie `tageskette` als `skipped`-Lauf zu journallieren.
`lauf_heute_erfolgreich` zählt aber **jeden** Terminal-Status (ok/skipped/fehler
— bewusst so seit Review C: sonst MT5-Start/Stopp-Zyklus alle 30 s). Ein
journalisierter Guard-Skip hätte die Rolle für den Rest des Tages stillgelegt.
Deshalb Postfach statt Lauf-Zeile.

Ein Detailfehler in M1s Begründung: Lock-Dateien enthielten schon vor `4c57277`
immer ein `pid`-Feld (Writer schrieb es von Anfang an) — der Endlos-Blockade-Pfad
lief über korrupte Dateien (`{}` → keine PID → konservativ „lebend"), nicht über
fehlende PIDs. Am Befund ändert das nichts.

## Neue Tests (+6, alle 165 Agenten-Tests grün)

recycelte PID wird übernommen · MAX_S-Übernahme trotz lebendem Halter ·
korrupte Datei sofort frei · Guard-Grenzen rollenspezifisch ·
3-h-verwaister Betreuer läuft wieder · Skip-Meldung genau einmal.
Autouse-Fixture leert den Guard-De-Dup-Speicher je Test (per-Test-DB, IDs
starten wieder bei 1).

## Qualitätsbewertung des Reviews

| Kriterium | Bewertung |
|---|---|
| Befundqualität (alle real, korrekte Dateien/Zeilen, Regression-Geschichte korrekt rekonstruiert) | **5/5** |
| Schweregrade (🟠/🟡/🟢 entsprachen der operativen Bedeutung) | **5/5** |
| „Ohne Befund"-Liste (8 Punkte; die von den Fixes berührten haben sich bestätigt) | solide |
| Fix-Vorschläge | **4/5** — durchweg vernünftig, nur M5 ohne Kenntnis der Terminal-Status-Zählung entworfen (hätte neuen Betriebsblocker eingebaut) |

**Gesamt:** die beste fremde Prüfung der letzten Runden — Diagnose-Arbeit top,
Lösungsteil wie immer selbst gegenprüfen. Bestätigt unsere Regel: jeden Befund
am Code verifizieren, Vorschläge nie unbesehen übernehmen.
