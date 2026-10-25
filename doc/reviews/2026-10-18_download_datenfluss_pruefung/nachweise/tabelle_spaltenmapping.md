# Tabellen: Feldherkunft und Darstellung

Stand des gelesenen Codes: 18.10.2026. Vollständige Ausdrücke mit Codezeilen werden zusätzlich in `tabelle_spaltenmapping.json` aus dem AST erzeugt.

## Ergebnisse

Kette: `db.list_catalog` → `pipeline.results_from_db` → `ScanResult.to_row` → `app_ui.results_to_dataframe` → `app_ui.render_results_table`.

DB ist der gesamte gespeicherte Livebestand, Sitzung der letzte Sitzungsstand, Archiv eine historische `results.json`. DB ist nicht der Nachweis, dass diese Signale im letzten Lauf neu geladen wurden. DB-Sortierung: zuletzt tatsächlich aktualisiert zuerst, danach Name. Status-, Such- und NEU-Filter erzeugen eine gemeinsame Zeilenmenge für Tabelle und CSV. Der CSV-Export enthält Basisspalten, nicht sämtliche erst im Renderer ergänzten Aktions-/Verlaufsspalten.

| Spaltenschlüssel | Herkunft / Regel |
|---|---|
| Stand | `refreshed_signal_ids`; im Legacy-Sitzungsstand nur `persisted_this_run`; `NEU` nur für tatsächlich gespeicherte Ergebnisse |
| Fix | `fix_signale.fix_ids`; Scan-Zusage ohne Bewertungsvorrang |
| Ampel | `ampel_for` des geladenen `ScanResult`, sichtbare Überschrift „Status“ |
| ID | `signals.signal_id` |
| Name | `signals.name`, ersatzweise Signal-ID |
| Platform | `signals.platform`, Überschrift „Plattform“ |
| Quelle | `signals.quelle`, Altbestand ohne Kürzel → `mql5` |
| Abo $ | `signals.abo_preis` → `abo_preis_usd` |
| Abos | `signals.abonnenten`; Überschrift „Abonnenten“ in Alle-Kennzahlen-Ansicht |
| Wochen | `signals.wochen` |
| Growth % | `stats.growth_pct` |
| Ertrag/Monat % | `stats.ertrag_monat_pct`: Plattformwert |
| PF | `stats.pf` |
| Drawdown % (Plattform) | `stats.eq_dd_pct` |
| Balance-DD % (Plattform) | `stats.bal_dd_pct` |
| Max-Drawdown % | `max_drawdown_equity_pct`: ausschließlich eigene gültige H1-Kursrekonstruktion; bei veralteter Forensik leer |
| Gewinn %/Monat | `ertrag_monat_geom_pct`: eigene geometrische Rendite, aus Forensik; ungültig/veraltet → leer |
| TrueRetDD | `true_retdd_jahr`: gültiger Jahres-Calmar, sonst explizit vorbehaltlicher H1-Wert; Vorbehalt orange |
| TrueRetDD (Vorbehalt) | `retdd_jahr_vorbehalt`, technischer Marker/gesonderte Spalte in Vollansicht |
| RetDD/Monat | `retdd_monat`, gültige Monatsvariante, kein Grün-Gate |
| Trading-DD % (geschlossen) | Forensik `trading_dd.pct`; Legacy-Feld `trading_dd_pct` |
| Equity-Messung | `equity_messung_status`: H1-Messung oder konkreter Fehl-/Veraltungsgrund |
| Winrate % | Forensik `winrate_pct` |
| Verlustserie | Forensik `max_verlustserie` |
| Peak-Pos | Forensik `peak_exposure.positionen`, Legacy `peak_positionen` |
| Netto-Lots | Forensik `peak_exposure.netto_lots`, Legacy `peak_netto_lots` |
| Schock $ | Forensik `peak_exposure.schock_usd`, Legacy `shock_usd` |
| Martingale | Forensik `martingale_flag` → JA/nein/leer |
| Stop | Forensik `stop_nachweis`; fehlender Nachweis neutral |
| Score | Forensik `score`; veraltet → leer; kleinere Zahl bedeutet weniger erkannte Risiken |
| Kurzfassung | Auszug aus dem neuesten an die aktuelle geprüfte Berichtsbasis gebundenen Gesamtbericht; `restore_current_reports` blendet historische Texte ohne passende Basis aus |
| Urteil | Aktuelle Engine-Ampelbegründung beim Laden |
| Bericht vom | Datum des neuesten Gesamtberichts mit aktueller geprüfter Berichtsbasis, kein Downloadzeitpunkt; historische/invalide/unvollständige Forensik → keine aktuelle Berichtsanzeige und `NaT`/leer |
| Fehler | `stats.last_fehler` |
| Bericht | Aktionsbutton für den exakten ausgewählten Ergebnis-Snapshot |
| Studie | Aktionsbutton für ausgewählten Ergebnis-Snapshot |
| Link | `quellen.oeffnen_url(quelle, id, url)`, anbieterabhängig |
| Abonnenten | Letzter Wert aus lokaler `subscriber_history`; Version bevorzugt passend zur Plattform; separates Datenfeld neben `Abos` |
| 30 Tage | `abo_bilanz.tage30`; fehlender Vergleichspunkt → leer; >0 grün, <0 rot, 0 neutral |
| 7 Tage | `abo_bilanz.tage7`; gleiche Leer-/Null-Regel |
| Dokumente | Anzahl nichtleerer Workflow-Berichte plus gespiegelter Downloader-PDFs; Tiefenanalyse gesondert markiert |

Kompakt zeigt: Stand, Fix, Ampel, Name, Quelle, Stop, Max-Drawdown, Trading-DD, Plattform-DD, Studie, Gewinn/Monat, TrueRetDD, Plattform-Ertrag/Monat, Score, Urteil, Berichtsdatum, Bericht, Link, Abonnenten-Verlauf, 30/7 Tage, Dokumente. „Alle Kennzahlen“ enthält die restlichen Basisspalten. „Ampeln“ verwendet `ampel_matrix.kriterien_matrix` auf derselben gefilterten Ergebnismenge.

## Alle Signale

Kette: Workflowbestand plus `katalog.katalog_resultate` → `workflow_stats_bulk` → `_statistik_cached`/`signal_statistik.berechne` → `alle_signale_ui.tabellen_zeile`.

Die Metadaten und Statistik kommen in dieser Übersicht teilweise aus frischeren, nach Quelle/Version/SHA passenden Quellenartefakten. Das ist keine Aktualisierung der gespeicherten Workflow-Bewertung. Noch nicht geladene Katalogsignale sind absichtlich vorhanden. Quellenkollisionen werden derzeit nach numerischer ID dedupliziert; vollständige Composite-Identität ist laut AGENTS offen.

| Spalte | Herkunft / Regel |
|---|---|
| Mark. | `signal_markierungen`, manuelle Farbe je ID |
| Komm. | `signal_kommentare`, Icon bei nichtleerem Kommentar |
| Ampel | Workflow-Ergebnis; Katalog ohne Bewertung bleibt Vorprüfung |
| Fix | Gemeinsame Fix-ID-Liste |
| Name | Ergebnisname oder ID |
| Link | `quellen.oeffnen_url(quelle, id, url)`, maximal 500 Zeichen |
| Quelle | Exaktes Quellkürzel |
| Herkunft | `Workflow` oder `Katalog` |
| Plattform | Ergebnisplattform |
| ID | Numerische Signal-ID |
| Wochen | Workflowmetadaten; ggf. aktuelle passende Katalogmetadaten; Katalog direkt aus Quellenkatalog |
| Abonnenten | Gleiche Metadatenregel wie Wochen; kein zusätzliches Verlaufsmapping |
| Plattform-DD % | `result.dd_equity_pct`: Workflow-Plattformstats oder Katalogmetrics |
| Trading-DD % | `statistik.trading_dd_pct`, aus geschlossenem Netto-Tradeverlauf und Kapitalbasis |
| True-DD % | `true_max_drawdown_pct`; sonst virtuelle H1-Studie; aktuelle unabhängige Studienanzeige kann überschreiben |
| True-DD ≈ | Marker für vorbehaltliche virtuelle oder rohe H1-Messung; unabhängige Studienanzeige analog |
| True-DD USD | `true_dd_usd`, H1-Betragskanal |
| Plattform %/M | `result.ertrag_monat_pct`, Plattform-/Clientangabe |
| Geom. %/M | `statistik.ertrag_monat_geom_pct`, eigene Rendite; fehlende/ungültige Basis → leer |
| TrueRetDD | `true_retdd_jahr`, sonst virtuelle Studie; unabhängige Studienanzeige: aktuelle CSV-CAGR/H1-DD erst ab drei Monaten |
| TrueRetDD ≈ | Vorbehaltsmarker aus derselben Messbasis |
| RetDD/Monat | `true_retdd_monat`, sonst virtuelle Studie; unabhängige Studienanzeige analog aus geometrischem Monatswert |
| PF | `statistik.profit_faktor`, aus dem Profit-Feld vor Commission/Swap; kein Verlustnenner → undefiniert |
| Win % | `statistik.winrate_pct`, Anteil positiver Profit-Felder vor Commission/Swap; Produzent rundet auf eine Nachkommastelle |
| Trades | `statistik.trades`, geparste Trades; ohne Export unbekannt; lesbarer Export ohne Trades → 0 |
| Basis | `kapitalbasis_quelle` als CSV/Seite/implizit/virtuell; nur bei positiver verwendeter Basis |
| Forensik | Häkchen ausschließlich bei vorhandener aktueller vollständiger Forensik |
| Messstatus | H1-Qualität, virtuelle Basis, unabhängige Studie, Statistikfehler, gekappte Historie und fehlender Cache |

Zusätzliche Sperren: Fehlender USD-Nachweis bei nativen MQL-Beträgen und reine Finanzteilstatistiken leeren Trading-DD, True-DD, Geom.-Rendite und RetDD. Finanzteilstatistiken können weiterhin belegte Trade-/PF-/Winrate-Werte zeigen, wenn der konkrete Parserfall das zulässt. Keine leere Zelle darf als Null oder Risikofreiheit gelesen werden.

Cache-Schlüssel: Tradepfad + registrierter Trade-SHA + Stats-JSON + Rechenversion. Numerische Anzeige: erst nach Zeilenaufbereitung auf zwei Nachkommastellen runden; NaN leer; alle Filter gelten auch für CSV. Batch-Studien aktualisieren die Tabelle gedrosselt bei neuen Ergebnissen und unmittelbar je Sitzung beim Abschluss.
