# Fehlende Rohtrades: belegte Zugangs- und Datenprobleme

Stand: 10.10.2026. Ausschließlich lesende Quellenanfragen und isolierte Dateien
unter `tmp/source_trade_probe_20261010`; keine MT5-Aufrufe und keine Schreibzugriffe
auf die Scanner-Produktionsdatenbank. Zugangsdaten, Cookies und Login-Inhalte
werden hier nicht gespeichert.

## Pelican: Sessionfehler behoben, gezielte Vollfenster-Recovery abgeschlossen

Betroffen: 2099301, 2099355, 2099617, 2100300. Jeweils echter GET auf den
vorhandenen `/api/strategies/{id}/signals/closed`-Endpunkt, Zeitraum
10.09.–10.10.2026 (maximal 31 Tage), mit gespeicherter Session, Pflichtheader
`X-CSRF: 1` und bestehendem Browser-User-Agent: alle vier HTTP 401.
Beleg: `tmp/source_trade_probe_20261010/summary.json`.

Die vorhandenen Zugangsdaten wurden nur auf Verfügbarkeit geprüft; der offizielle
`LoginAutomat.autoLogin` wurde einmal aufgerufen. Ergebnis: `LOGIN_SUCCESS=false`,
Kategorie `Timeout`, Exitcode 1. Der Versuch war zusätzlich auf 225 Sekunden
begrenzt; JavaFX wurde danach beendet. Ein erneuerter Login ist erst mit erfolgreicher authentifizierter
API-Antwort belegt. Schon das bestehende Monitorprotokoll vom 08.10., Zeilen
1133–1139, zeigt eine damalige AutoLogin-Erfolgsmeldung gefolgt von HTTP 401;
die Erfolgsmeldung allein reicht daher nicht als Zugangsbeleg.

Eine Aussage über fehlende Trades ist aus HTTP 401 nicht möglich. Nach gültiger
Session muss der allgemeine Pelican-Client alle 31-Tage-Blöcke ab Inception laden,
per Trade-ID zusammenführen und den vorhandenen verifizierten Store verwenden.
Ein einzelner leerer Zeitraum wäre kein vollständiger Historiennachweis.

Der anschließend ausdrücklich autorisierte Chrome-headless-Versuch benutzte
das normale E-Mail-/Passwortformular und Enter, ohne Gerätefelder oder
Sicherheitsprüfungen zu verändern. Erfolg ist durch eine echte lesende
Closed-Trades-Antwort **HTTP 200** belegt; 2099301 liefert für 10.09.–10.10.
27 Datensätze mit TradeId, Open-/Close-Zeit, Preisen und realisiertem Ergebnis.
2000016 liefert im selben Monat tatsächlich `[]`; das ersetzt keinen
Vollhistorienabruf. Browser geschlossen, alte Session vor Speicherung gesichert.
Belege: `tmp/source_trade_probe_20261010/pelican_chrome_login.json` und
`pelican_schema_2099301.json`. Firefox war nicht installiert; frühere
Firefox-Dokumentation beschreibt eine Implementierung, keinen bewiesenen
erfolgreichen Live-Login.

Die Recovery-Zielmenge wird aus den 159 leeren Audit-Exports plus vier fehlenden
Rohcaches gebildet. Reguläre aktuelle Stats liefern für 160 belegte
Zeitfenster; insgesamt 3.618 Monatsanfragen mit bestehendem 400-ms-Throttle.
2064608, 2053531 und 2000436 haben weder gültige Inception noch datierte
Tageshistorie und keine positiven Handelsaggregate; sie bleiben explizit
ungeklärt und erhalten kein erfundenes Vollhistorienfenster.
`0001-01-01` ist ein Quellen-Platzhalter, kein Handelsbeginn. Ohne Schutz hätte
die naive Planung 75.216 Requests ergeben. Der dauerhafte Parser und der
Ladefensterplaner behandeln Jahr 1 nun als unbekannt und verwenden vorhandene
echte Tageshistorien; keine erfundene frühere Historie.

Allgemeine Quellkorrekturen in PelicanTrading:

- Verifizierte leere Rohcaches widersprechen positiven Trades/Wins/Losses:
  `hasClosed(Provider)` meldet sie nicht als erledigt, der Job lädt sie erneut,
  REST liefert bis zur Reparatur ein explizites 404. Leere Quellen ohne
  positiven Aggregatbeleg werden nicht pauschal als Fehler umgedeutet.
- Geschlossene Trades verlangen ein JSON-Array und TradeId je Datensatz;
  eine geänderte JSON-Hülle wird nicht still als leere Historie gespeichert.
- Bei installiertem Chrome beginnt der offizielle AutoLogin direkt mit dem
  belegten begrenzten Chrome-headless-Weg, ohne vorher 210 Sekunden WebView
  abzuwarten. Ohne Chrome bleibt WebView erhalten. Normales Formular, kein Browserinstall,
  kein Sicherheitsbypass; Session wird nur nach echtem JSON/API-200-Nachweis
  gespeichert. Auch WebView-Erfolg wird vor Speicherung per API geprüft.

Vollständige Source-Tests plus Paketierung: 100 Tests, keine Fehler. Die
Recovery selbst verändert keine Scanner-Datenbank. Fertige normale
Source-Rohcaches werden vor Ersetzung gesichert, REST-Dateien entstehen
inkrementell unter `tmp/pelican_exports_goal_20261010`; Acceptance zuletzt
atomar schreiben, so dass unfertige Sätze nicht importiert werden. Positive
Quellenaggregate plus nach Vollabruf weiterhin null Trades bleiben ein
sichtbarer Widerspruch und erhalten keinen neuen Erfolgsmarker. Status:
`results.json`, Plan/Herkunft: `plan.json`, vorherige Rohbytes: `before/`.

Abschluss: Downloadprozess Exit 0; 160 datierte Ziele/3.618 Monatsfenster vollständig
abgefragt, 156 Cachehistorien mit zusammen 113.880 geschlossenen Trades
wiederhergestellt. Zwei davon sind echte leere Historien ohne positiven
Aggregatwiderspruch. 2097770, 2000036, 2001116 und 2001115 liefern auch über alle
belegten Monatsfenster null Trades trotz positiver Quellenaggregate; ihre alten
Rohcachedateien wurden nicht als erfolgreicher neuer Download ersetzt. Zusammen
mit den drei nicht datierbaren Anbietern bleiben sieben Fälle ungeklärt.
Die vier ursprünglich ganz fehlenden Rohcaches sind sämtlich wiederhergestellt.
Frische Stats der 163 Zielanbieter wurden nach Bytebackup in den normalen
vollständigen Sourcekatalog gemergt; alle 2.263 Katalogeinträge bleiben erhalten.

**Historische FX-Korrektur noch getrennt abzuschließen:** Der alte Pelican-REST-
Handler multipliziert jeden historischen Gewinn mit einem einheitlichen aktuellen
Kurs. Beispiel 2000016: EUR-Kursdatum 29.09.2026 bei Trades seit November 2022.
Das ist kein korrekter USD-Verlauf pro Abschlussdatum. Die nativen Quell-Rohcaches
bleiben korrekt; die bisher erzeugten REST-CSV-Dateien müssen nach dem allgemeinen
Tageskursfix neu erzeugt und per SHA neu importiert werden. Dafür ist der
Historien-EZB-Cache mit ausschließlich früheren Kursen, maximal zehn Tagen
Rücklauf, vorgesehen; aktuelle Balance/Equity behalten ihren aktuellen Kurs.
Dieser FX-Fix wird separat im selben Arbeitsauftrag umgesetzt.

Auch erfolgreiche Fensterabfragen beweisen keine vollständige Brokerhistorie:
2000016 liefert 2.632 eindeutige Trades gegenüber Quellenaggregaten Trades=5.562,
Wins=1.692 und Losses=1.078. Die Zählbasen sind ohne weitere Quelldefinition nicht
gleichzusetzen. Ein neutraler Historienhinweis ist erforderlich; weder eine
automatische Behauptung „abgeschnitten“ noch ein Bewertungsmalus folgt daraus.

## Zulu 426712: HTTP-Erfolg ohne brauchbare Tradefelder

Die öffentliche History antwortet auf beiden bestehenden Hosts mit HTTP 200.
Die ersten 200 Records sowie die weiteren 74 Records des Alternativhosts
enthalten durchgehend **keine** `dateOpen`, `dateClosed`, `priceOpen` oder
`priceClosed`; `providerId` ist durchgehend 0. Die erste Seite nennt
`totalElements=274`; die zweite Seite des Alternativhosts nennt abweichend 148.
Der primäre Host liefert für die zweite Seite HTTP 404.

Sanitierter Beleg: `tmp/source_trade_probe_20261010/zulu_schema_summary.json`.
Unveränderte JSON-Antworten liegen daneben unter `zulu_426712_*_page*.json`.
Der echte bestehende `ZuluTradeClient.downloadTradeHistory` wurde mit isoliertem
DataStore versucht und scheiterte nach den vorhandenen Host-/Retry-Regeln an
`ApiException: Ungültiges Antwort-Schema`, Exitcode 1. Der gleiche Befund steht
bereits im Monitorprotokoll vom 08.10., Zeilen 2504–2516.

Der Adapter schützt hier richtig vor unbrauchbaren Eingaben. PnL, Lots und
Währung allein ersetzen weder Zeitachse noch Einstiegspreise. Deshalb wurde kein
CSV-Export und keine erfundene Rekonstruktion erzeugt. Benötigt wird eine echte
Historie mit eindeutiger Providerzuordnung, Zeitstempeln und Preisen.

## Robo: R StocksTrader ist eine Adaptergrenze, keine bewiesene API-Nichtexistenz

Alle drei betroffenen Katalogeinträge 93128696, 93019895 und 93156209 führen in
`../roboforex/data/signals.csv` die Plattform `rst`. Der bestehende
`RoboForexClient.downloadDeals` unterstützt explizit MT4-Orders und MT5-Deals;
andere Plattformen werden abgewiesen. Seine vorhandenen öffentlichen Alternativen
liefern Tagesprofit, Balance/Equity, Symbolzählungen und Kontostatistik. Diese
Aggregate reichen nicht für einzelne Positionen oder Intraday-Equity.

Es gibt jedoch eine **offizielle StocksTrader-API**, einschließlich Orderhistorie
für das authentifizierte Tradingkonto. Das belegen die
[offiziellen API-Funktionen](https://help.stockstrader.com/en/support/solutions/articles/33000290139-introduction-specifics-and-features).
Ein API-Token wird nach Anmeldung im Webterminal unter Einstellungen →
API-Integration erzeugt; siehe
[offizielle Zugangsanleitung](https://help.stockstrader.com/en/support/solutions/articles/33000290140-how-to-gain-access-to-the-api)
und [API-Schema](https://api-doc.stockstrader.com/).

Ein anonymer Zugriff auf die vollständigen Trades **fremder** CopyFX-Anbieter
ist damit nicht belegt. Der vorhandene Members-Cookie ist kein nachgewiesener
StocksTrader-API-Token. Es wurden deshalb keine unbekannten Endpunkte geraten
und keine MT4-Abfrage für RST als Ersatz ausgeführt. Allgemeiner nächster Schritt:
verifizierter RST-Historienzugang, dokumentierte Kontozuordnung und Adapter für
Order-/Deal-Paarung, Teil-Schließungen, UTC, Einheiten und native Geldwährung.
Bis dahin bleibt die Messung unbekannt.

## MQL: einmaliger Sessionnachweis vor Exporten

Gespeicherte accountgebundene Cookies und konfigurierte Zugangsdaten sind
vorhanden (nur Bool geprüft). Die gespeicherte Session bestand den vorhandenen
Logincheck nicht. Deshalb wurden zunächst keine unauthentifizierten
Exportserien gestartet. Der anschließend autorisierte offizielle
`ensure_session_for_export`-Versuch und mögliche gezielte Exporte schreiben ihren
aktuellen Ausgang nach `tmp/source_trade_probe_20261010/mql_summary.json`.
Test-ID 1 ist ausgeschlossen. CSVs werden nur bei echtem `Time;`-Header
gespeichert und danach mit dem Produktionsparser gelesen; HTML/Authentifizierungs-
fehler stoppen die Serie. Lokale, bereits anderweitig wiederhergestellte
Exporte werden über die vorhandene Recoveryliste ausgeschlossen.

Der offizielle Sessionerneuerungsversuch war erfolgreich. Alle 14 zusätzlichen
realen IDs wurden danach aus dem richtigen MT4-History- bzw.
MT5-Positions-Endpunkt erneut als **Originalbytes** gesichert, einschließlich
aktueller Original-Detail-HTML. Die erste textnormalisierte Diagnosekopie ist
ausdrücklich kein Originalbytebeleg. Dauerhafter Originalbeleg mit URLs,
Abrufzeit, Plattform und SHA:
`tmp/source_trade_probe_20261010/mql_original_provenance.json`.

Der vorhandene HtmlConverter erzeugte die Root-TXT-Dateien auf einer getrennten
Kopie ohne MPDD-Vorfilter. Alle 14 regulären isolierten REST-Exports liefern
trades.csv 200 und metrics 200; CSV-SHA ist identisch mit den Originalbytes.
Importierbar: `tmp/mql_remote_exports_goal_20261010`. CSV, HTML und Root-TXT
liegen außerdem unter dem normalen `C:/Forex/MqlAnalyzer/download/mql4` bzw.
`mql5` mit je ID eindeutigem Präfix `Recovery<ID>_<ID>`; Sicherungsordner bei
vorhandenen gleichnamigen Dateien:
`tmp/source_trade_probe_20261010/mql_source_before_recovery`.
Die Source-Konvertierung fand bei diesen HTMLs keine Monatsdetails und liefert
dafür 0 statt einen nachgewiesenen Monatswert; das ist eine Adaptergrenze, keine
Trade-Lücke. Der Scanner berechnet seine Rendite weiterhin selbst aus Trades.

Die Diagnose senkt keine Verlässlichkeitsgrenzen und ersetzt fehlende Quellen-
Trades weder durch Tagesaggregate noch durch geratenes Datum, Preis oder GMT.

Nachtrag zur endgültigen Pelican-Währungsbasis: Die früheren 163 REST-Exporte
verwendeten noch den alten Snapshot-FX-Pfad und sind für historische PnL nicht
der endgültige Stand. Der neue getrennte Satz
`tmp/pelican_historical_fx_exports_goal_20261010` enthält alle 636 sichtbaren IDs
mit der inzwischen korrigierten täglichen historischen Umrechnung. Abnahme,
Statusgrenzen und SHA-Belege:
`pelican_historische_fx_export_pruefung_2026-10-10.md` und `.json`.
