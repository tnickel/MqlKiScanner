# Abonnenten-Belegfelder nachgerüstet (Pelican/Robo/Zulu) + Login-Hinweis + Katalog-Timeout

Datum: 25.10.2026 · Umsetzung nach ausdrücklichem Nutzerauftrag („rüste die 3
belegfelder nach, wir wollen doch alle clients gleich haben“ / Login-Hinweis
präzisieren / Timeout 30→60 s).

## Nachprüfung und Fehlerbehebung vom 25.10.2026

Nutzerauftrag: „behebe alle gefundenen fehler“. Die folgenden Korrekturen
ergänzen den ursprünglichen Umsetzungsstand und den historischen `ENDREPORT.md`:

1. **Pelican/Zulu: frische Vollkatalogzähler erhalten.** Die Veröffentlichung
   aktualisiert auch die Zähler der bisherigen Auswahl unter demselben
   Katalog-Lock. Ihre Mitgliedschaft, Profildetails und Auswahlzeit bleiben
   erhalten. Die anschließende Veröffentlichung der neuen Auswahl kann
   ausgeschiedene Anbieter nicht mehr auf alte Zähler zurücksetzen.
2. **Robo: gelesene Nullzähler veröffentlichen.** Gültige Nullzeilen zählen zu
   `alleGelesene` und `scannedProviders` und erreichen Katalog und Tageshistorie.
   Nur die Top-Auswahl filtert weiterhin auf positive Abonnentenzahlen.
3. **Historienfortschritt:** Meldungen behalten Quellenindex und Quellenzahl;
   der Wechsel zur nächsten Quelle verwirft alte Historienzähler.
4. **Frischmess-Sperre:** Der tatsächliche aktive Worker entscheidet über die
   Sperre. Eine gemerkte abgeschlossene Studie blockiert den Button nicht.
   Die Anzahl der `active_run()`-Aufrufe bleibt unverändert.
5. **Kapitalhinweise in Tabelle und CSV:** `Kapitalherkunft`,
   `Kapitalunsicherheit` und `Studienbasis` bleiben Textfelder; sie werden
   nicht mehr durch numerische Konvertierung zu leeren Zellen.

Die 17 auf dem vorherigen Commit unabhängig bestätigten Testfehlschläge
wurden gegen die aktuellen Anforderungen geprüft. Die Korrekturen betreffen
überholte Herkunftsbezeichnungen, echte Exportdateien statt Parser-Fakes ohne
Datei, separat geprüfte Export-SHAs bei Permutationsvergleichen, belegtes
Nullkapital statt fehlender Kapitalhistorie, übereinstimmende Kapitalbasen für
RetDD und boolesche CSV-Felder. Keiner der 17 Altfehlschläge wurde übersprungen
oder als erwartet fehlschlagend markiert. Zusätzliche Fälle sichern die getrennte
Modellkennzeichnung nach DB-Reload und die RetDD-Sperre bei fehlenden oder
abweichenden Kapitalbasen.

Insbesondere wird der historische virtuelle Fixwert **nicht** wieder zum
vorrangigen Kapitalbeleg gemacht: Die Nutzerentscheidung vom 24.10. bleibt
maßgeblich. Eine belegte nichtpositive CSV-Basis bleibt nichtpositiv; fehlende
Kapitalbelege erlauben nur das gekennzeichnete Modell ohne Grün-Freigabe.
Forensikversion 22 und produktive Daten bleiben unverändert.

Verifikation der Korrekturen:

- Pelican: `mvn -q compile` und vollständiges `mvn -q test`: **224 bestanden**.
- Robo: dieselben Aufrufe: **224 bestanden**.
- Zulu: dieselben Aufrufe: **182 bestanden**.
- Regressionen belegen den ursprünglichen Fehler und die Korrektur für
  ausgeschiedene Anbieter 100→0/1, gemessene Robo-Nullzähler, tatsächliche
  Streamlit-Fortschrittsanzeigen, Worker-Sperren und CSV-Download-Daten.
- Abschließende Scanner-Vollsuite: **4.018 bestanden, 1 übersprungen,
  4 KI-Tests abgewählt**, keine Fehler (696,51 Sekunden). Aufruf:
  `python -m pytest tests -q --tb=short --durations=12 --junitxml=<Testbericht>`
  mit `PYTHONPATH=src` und den installierten Projektpaketen unter Python 3.12.
  Der bestehende Skip betrifft fehlende Windows-Rechte zum Erstellen eines
  symbolischen Links (`test_symlink_is_rejected_without_following_target`).
- Im ersten Prüflauf zusätzlich gefundene instabile MQL-Import-Testfixture:
  NTFS-Dateizeit und unmittelbar erstellter Empfangszeitpunkt konnten sich
  unterhalb einer Mikrosekunde widersprechen. Die Fixture belegt die zeitliche
  Reihenfolge jetzt explizit und prüft auch den Gleichheitsfall. Alle 20 Fälle
  des Moduls sowie die danach neu gestartete Vollsuite bestehen; die produktive
  Importprüfung wurde nicht gelockert.
- Maschinenlesbare Testzahlen, Ausgangscommits und SHA-256 der geänderten
  Code-/Testdateien stehen in `behebung_nachweis.json`.

Dies ist eine Code-/Testabnahme. Keine produktiven Neustarts, Zählerläufe,
Neuberechnungen oder KI-Aufrufe; Aktivierung und grüne produktive Läufe sind
separat nachzuweisen.

## Ausgangsbefunde (alle live gegen die laufenden Systeme belegt)

1. **Gelbe Hinweise „unbestätigter Auswahl“ für pelik/robo/zulu:** Der Scanner
   verlangt seit dem 24.10. einen Abdeckungsbeleg für die Top-200-Zählerläufe
   (`subscriberSelectionProof` für MQL, `subscriberCatalog*` für die
   Listenfenster). Nur MqlDownloader und Vantage liefern diese Felder; die
   Builds von Pelican, Robo und Zulu können es nicht. Die Zähler selbst sind
   frisch und werden übernommen — nur die Auswahl bleibt ehrlich
   „unbestätigt“ markiert.
2. **„Pelican-Zahlen kommen nicht an“:** Der Pelican-Zählerlauf liest die
   VOLLSTÄNDIGE Discover-Liste (~2.211 Anbieter), veröffentlicht frische
   Zähler aber nur für die Top-200-Auswahl (Katalog-Merge + Historien-
   Snapshot). Die Abonnentenstatistik zeigt bevorzugt den neuesten
   HISTORIENpunkt (`zeilen()`: `zeile["abonnenten"] = aktuell`), deshalb
   standen ~2.011 Anbieter auf dem Stand vom Vortag, obwohl der Katalog
   komplett frisch gespiegelt war (Kontrolle 25.10. 02:57:46: alle 2.211
   Katalogzeilen aktualisiert, Historienpunkte heute: nur 200).
   Dasselbe Muster bestand bei Robo (403 Katalogzeilen) und Zulu (456).
3. **mql5-Katalogabbruch:** Der Vollkatalog-Sync brach beim MqlDownloader
   mit dem 30-s-Timeout ab (Verbindungsabbruch im Monitor-Log um 03:00),
   obwohl derselbe Abruf entlastet 2,5 s braucht — Momentanlast direkt nach
   dem eigenen Zählerlauf.
4. **Login-Hinweis-Lücke:** Bei `login_required` sagte der Scanner-Status
   nicht, WO der Nutzer tippen muss (im Fenster des Clients).

## Umsetzung

### Belegfelder (alle drei Clients, Vorlage Vantage `UpdateJobRunner`/`SubscriberCatalogResult`)

Je Client: neuer Beleg-Record (Auswahl + alleGelesene + scanned + reachedEnd
+ months + sort), Runner-Phase `nurAbonnenten` emittiert die sechs Felder
`subscriberCatalogComplete/ReachedEnd/Scanned/SkippedPositions/Months/Sort`,
Wächter wie bei Vantage (keine Endseite → kein Übernehmen; Auswahl > gelesene
Anbieter → Fehler). Die alten Methoden bleiben als Delegates bestehen.

- **PelicanTrading:** `AbonnentenKatalog.Beleg` (Discover-Liste ist EINE
  vollständige Antwort: complete/reachedEnd=true; Strict-Parsing wirft statt
  zu skippen → skippedPositions=[]), `months=1` (kein Zeitfenster —
  Gesamtstände; 1 = Einzelsnapshot im 1-Monats-Snapshot-Raster),
  `sort="discover"`.
- **roboforex:** `RoboForexClient.SubscriberCatalogResult`; reachedEnd durch
  einen von drei belegten Endzuständen (more=false, Nullgrenze des
  absteigenden Rankings, mathematischer Frühabbruch), `months=3`
  (Website-Standard-Fenster des Zählerlaufs), `sort="subscriber_count"`.
- **zulumonitor:** `ZuluTradeClient.SubscriberCatalogResult`; Ende = leere
  Endseite, `months=1` (timeFrame=10000, fensterlos — wie Pelican
  dokumentiert), `sort="followers"`.

Der Scanner validiert die Belege mit der bestehenden
`_abonnenten_katalog`-Logik unverändert: complete + keine Auslassungen →
Status **FERTIG (grün)** statt der bisherigen „unbestätigten Auswahl“.

### Volle Zähler-Veröffentlichung (Fix für „kommt nicht an“)

Neuer Dienste-Schritt `veroeffentlicheAbonnentenZaehler(alleGelesene)` in
allen drei Runnern, ausgeführt VOR der Auswahl-Ablage:

- **Pelican:** `DataStore.veroeffentlicheZaehler` (Counter-Merge in den
  Vollkatalog, Auswahl-Datei `providers_abonnenten.csv` unberührt) +
  `copierDb.snapshot(alle)` → Tages-Snapshots für ~2.211 statt 200.
- **Robo:** `DataStore.veroeffentlicheZaehler` (Merge in signals.csv,
  `subscriberFile` unberührt) + `subscriberDb.snapshot(alle)`.
- **Zulu:** `DataStore.veroeffentlicheZaehler` (Counter-Only-Merge über
  `withSubscriberCounts`, `subscriberTradersFile` unberührt) +
  `subscriberDb.snapshot(alle)`.

Membership (Top-200-Auswahl) und Vollkatalog-Frische bleiben in allen drei
Stores getrennt belegt — das bisherige Trennungsdesign wird nicht geändert,
nur die Frische wird vollständig.

### Scanner

- `client_updates.py`: Login-Meldung nennt jetzt ausdrücklich
  „bitte jetzt im Fenster von <kuerzel> einloggen“; die UI
  (`abonnenten_statistik.py`) rendert die Zeile bei Status `login` fett.
  Klartext im Chronik-Protokoll (kein Markdown in DB-Hinweise), Fett nur in
  der UI-Schicht.
- Refresh-Dialog nennt das Login-Fenster-Verhalten jetzt vorab
  („Der Status nennt dann ausdrücklich das FENSTER …“).
- `abonnenten_statistik._KATALOG_TIMEOUT_S` 30 → 60 s mit Befund-Kommentar.

### Progress-Balken für die Lesephase (Nutzer-Wunsch 25.10., Nachtrag)

Die „lesen“-Phase hatte bisher nur einen statischen Text. Jetzt meldet
`sync()`/`sync_quelle()` Fortschritt an einen optionalen Callback
(Quellenwechsel `{"phase": "quelle", "kuerzel", "nr", "von"}`; Historie in
25er-Schritten `{"phase": "historie", "kuerzel", "gesamt", "fertig"}`),
`starte_refresh` legt ihn unter `_REFRESH["lesen"]` ab und die Seite rendert
einen `st.progress`-Balken: „Neu einlesen: Quelle 2/5 — pelik: Historie
150/2211 Anbieter“ (ohne Meldung unbestimmt laufend). Die Klienten-Phase
zeigte bereits done/total je Client. Test:
`test_sync_meldet_fortschritt_fuer_ui_balken` (Schritte 0/25/50/60).

## Messzeit-Semantik (Klärung Nutzerfrage 25.10. „1879 vs. Website 1880“)

„Abonnentenzahlen aktualisieren“ misst zum Zeitpunkt des Laufs. The Holy
Grail wurde um 02:52:08 korrekt mit 1879 gemessen (Δ +14 gegenüber 24.10.);
die Live-Website zeigt Stunden später 1.880 — der Zähler ist seitdem um 1
gestiegen. Eine Differenz zur Live-Seite ist der Beleg für einen echten
Messzeitpunkt, kein Übertragungsfehler; der nächste Lauf übernimmt den dann
aktuellen Wert. Echte Lücken des Laufs von 02:52 (mql5-Timeout,
Vantage-Übernahmeverweigerung) sind oben separat belegt. Die Spalte
„Messung“ zeigt die Tages-Snapshot-Marke der Monitore (00:00), nicht die
Abrufsekunde.

## Daten-Button: Frische-Schranke + Progress (Nutzer-Wünsche 25.10., Nachtrag 2)

**Was der Button tut** (unverändert, hier nur dokumentiert): Phase
„trades_und_equity“ lädt je Anbieter die vollständige verfügbare Tradeliste
(SHA-geprüfter Cache, fehlende vom Client; Modus „Alle neu laden“ vermisst
jeden Anbieter frisch) und rechnet daraus die Equity-Kurve auf H1-Raster
inkl. Floating — der Max-Equity-DD mit High-Water-Mark-Regel (Gemeinkern
`forensics/drawdown_core.py`) und der Jahres-RetDD. Danach
„abonnenten_trends“ (Zufluss-Freeze) und „kapitalmodell“ (Bestandsrechnung).
Keine KI.

**Frische-Schranke (max. 24 h):** Neu `abonnenten_statistik
.juengste_messung(kuerzels)` — jüngste echte MESSUNG je Quelle aus
`subscriber_history` (max(ts); Spiegelzeit without Messung zählt nicht).
`daten_starten` lehnt Start ab, wenn eine gewählte Quelle älter als 24 h
oder nie gemessen ist; Meldung nennt Quelle + Alter und verweist auf
„Abonnentenzahlen aktualisieren → Frisch messen“. Der Dialog prüft vorab,
zeigt die veralteten Quellen und bietet eine ausdrückliche
Übersteuerungs-Checkbox; der Lauf vermerkt `abonnenten_frische`
(geprüft_am, Messzeitpunkte je Quelle, akzeptiert_veraltete).

**Progress:** Der Datenauftrag zeigt jetzt `st.progress` (fertige
Daten-Endstände / gesamt, Live über das 2-s-Polling); der reine
Modellauftrag behält seinen vorhandenen „Modellbearbeitung“-Balken.
Die Stopp-/Fortsetzen-Buttons tragen die Zahlen direkt im Label
(„Datensammlung fortsetzen — 20/500 geladen, 480 offen“), und die Caption
nennt den gespeicherten Tradelisten-Modus („Nur fehlende laden“ vs.
„Alle neu laden“), weil er bestimmt, was ein Fortsetzen tatsächlich lädt.

Tests: `test_data_start_...` (Gate: nie/48 h → Fehler, Override → vermerkt,
frisch → sauber), Dialog-Tests mit Frische-Seed; 110 Tests in
test_abonnenten_datenmodus/daten_ui/statistik/statistik_freshness grün.

## Alle Signale: Abonn.-Spalte aktuell + Frische-Hinweis + Frischmess-Button
(Nutzer-Anforderung 25.10., „Lenore 120 vs. Broker 122")

Ursache: `list_catalog` las die Abonnentenzahl AUSSCHLIESSLICH aus der
`signals`-Zeile (Workflow-Scan-Stand — der aktualisiert sich nur per
Re-Scan, niemals durch Katalog-Syncs). Fix: `list_catalog` joint jetzt
`katalog_signale` und nimmt `COALESCE(k.abonnenten, s.abonnenten)` — der
Spiegelstand des letzten Client-Laufs gewinnt, der Scan-Stand bleibt
Fallback ohne Katalogzeile. Tests: `test_katalog_overlay_abonnenten.py`
(Katalog 122 schlägt Scan 120; ohne Katalogzeile gilt 77 weiter).

Auf der Alle-Signale-Seite stehen jetzt zusätzlich: eine Zeile
„Abonnenten-Messung je Quelle: vant vor 30 h ⚠ · …“ (jüngste echte Messung,
⚠ über 24 h — dieselbe `juengste_messung`-Basis wie das Daten-Gate) und der
Button „Abonnentenzahlen frisch messen“ (dieselbe Stufe-B-Maschinerie wie
auf der Abonnentenstatistik; gesperrt bei laufendem Workflow-Scan; Fortschritt
und Ergebnis erscheinen auf der Abonnentenstatistik-Seite). Nach Abschluss
zeigt die Spalte die aktuellen Werte. Rückgabepfad-Klarstellung: auch dieser
Refresh hält einen Quellenstand nur so frisch, wie die Quelle selbst liefert
(Vantage-Übernahmeverweigerung bleibt sichtbar ⚠).

Weitere Tests: 159 (db/identity/catalog/Seiten) + 37 (Ergebnis-/Workflow-
Anzeige) grün.

## Tests

- PelicanTrading: **222 Tests grün** (u. a. erweiterte
  `UpdateJobStufe0Test`: Belegfelder im Ergebnis + Veröffentlichung aller
  gelesenen Anbieter).
- roboforex: **222 Tests grün** (erweiterte
  `subscriberOnlyAlwaysRefreshesWithoutTradesAndPreservesFullFreshness`).
- zulumonitor: **180 Tests grün** (erweiterte
  `subscriberOnlyAlwaysRefreshesWithoutTradesAndInvalidatesFullFreshness`).
- Scanner: 114 (`test_client_updates`, `test_abonnenten_statistik`,
  `test_abonnenten_statistik_freshness`) + 93 (`test_abonnenten_daten_ui`,
  `test_alle_signale_seite`, `test_glm_catalog_scope_review`) = **207 grün**.

## Abgrenzung / nicht behauptet

- **Wirksamkeit braucht Neustarts:** Die laufenden Clients (PelicanMonitor
  v1.5.0 vom 07.10. etc.) sind ALTE Builds — die Belegfelder und die volle
  Zähler-Veröffentlichung greifen erst nach Neubau + sanftem Neustart der
  drei Monitore. Die Scanner-Änderungen greifen erst nach Neustart der
  Streamlit-App (:8504). Beides ist bewusst NICHT automatisch passiert.
- Vantage ist unverändert (liefert Belege bereits); MqlDownloader ist
  unverändert (`subscriberSelectionProof`).
- `months=1` bei Pelican/Zulu ist Provenienz-Metadatum (fensterlose
  Gesamtliste), im Code je Stelle dokumentiert; der Scanner zeigt es nicht
  als Plattformfenster an.
- Ein erfolgreicher Neustart und ein grüner Zählerlauf sind danach separat
  nachzuweisen; dieser Bericht belegt Code + Tests, keinen Produktivlauf.
