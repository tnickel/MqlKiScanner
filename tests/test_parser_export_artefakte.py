# -*- coding: utf-8 -*-
"""MT4-Orderbuch-Footer und typenlose Zeilen: echte Export-Artefakte.

Beweislage: data/trades/1496203_positions.csv (MySingalStart 2) bricht seit
dem strengen Parser an der MT4-Summenzeile ab — Typ 'Buy', Symbol 'profit',
keine Preise, Profit-Spalte = Gesamtsumme. Drei reale Signale wurden dadurch
komplett blockiert (DB last_fehler 2026-09-08).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from mqlkiscanner import parser
from mqlkiscanner.models import Trade

ORDER_HEAD = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;"
              "Swap;Profit;Comment\n")
POSITION_HEAD = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"

# Nachbau der echten Zeile aus 1496203 (Zeile 2467), Werte anonymisiert.
SUMMARY_ROW = ("2022.03.28 12:45:01;Buy;0.10;profit;;;;2023.04.14 16:07:19;;;"
               "-130.60;3 613.41;\n")
TRADE_ROW = ("2023.04.17 15:30:11;Buy;0.01;USDCAD;1.33728;1.33866;;"
             "2023.04.18 00:27:53;1.33857;;-0.01;0.96;[sl]\n")


def schreibe(tmp_path, head, *zeilen):
    path = tmp_path / "export.csv"
    path.write_text(head + "".join(zeilen), encoding="utf-8")
    return str(path)


def test_mt4_summary_row_is_skipped_not_counted(tmp_path):
    path = schreibe(tmp_path, ORDER_HEAD,
                    "2023.06.01 09:00:00;Balance;;;;;;;;;;1000;\n",
                    TRADE_ROW, SUMMARY_ROW)
    parsed = parser.load_export(path)
    assert len(parsed.trades) == 1
    assert all(t.symbol != "profit" for t in parsed.trades)
    # Die Gesamtsumme (3 613.41) darf NICHT als Trade-Ergebnis auftauchen.
    assert sum(t.profit for t in parsed.trades) == pytest.approx(0.96)


def test_positions_format_summary_row_is_skipped_too(tmp_path):
    summary = ("2022.03.28 12:45:01;Buy;0.10;profit;;;2023.04.14 16:07:19;"
               ";-130.60;;3 613.41\n")
    trade = ("2023.04.17 15:30:11;Buy;0.01;USDCAD;1.33728;0.01;"
             "2023.04.18 00:27:53;1.33857;;-0.01;0.96\n")
    path = schreibe(tmp_path, POSITION_HEAD, trade, summary)
    parsed = parser.load_export(path)
    assert len(parsed.trades) == 1


def test_summary_recognition_requires_empty_prices(tmp_path):
    # Ein Preis-tragender Datensatz mit Symbol 'PROFIT' wird NICHT als Footer
    # uebersprungen, sondern als (kurioses) Instrument gezaehlt — die enge
    # Erkennung verhindert, dass echte Daten als Summenzeile verschwinden.
    row = ("2022.03.28 12:45:01;Buy;0.10;PROFIT;1.1000;;;"
           "2023.04.14 16:07:19;1.1050;;0;5.00;\n")
    path = schreibe(tmp_path, ORDER_HEAD, row)
    parsed = parser.load_export(path)
    assert len(parsed.trades) == 1
    assert parsed.trades[0].symbol == "PROFIT"


def test_typeless_spacer_row_is_skipped(tmp_path):
    spacer = ";;;;;;;;;;;;\n"                     # 13 leere Felder
    comment_only = ";;;;;;;;;;;;MT4-Export\n"    # nur Kommentarrest
    # Echtes MT5-Artefakt aus Signal 2271995: Zeile mit NUR Zeitstempel.
    timestamp_only = "2026.07.06 00:22:05;;;;;;;;;;\n"
    positions_trade = ("2023.04.17 15:30:11;Buy;0.01;USDCAD;1.33728;0.01;"
                       "2023.04.18 00:27:53;1.33857;;-0.01;0.96\n")
    path = schreibe(tmp_path, POSITION_HEAD,
                    "2023.06.01 09:00:00;Balance;;;;;;;;;1000\n",
                    timestamp_only, positions_trade)
    parsed = parser.load_export(path)
    assert len(parsed.trades) == 1
    path = schreibe(tmp_path, ORDER_HEAD,
                    "2023.06.01 09:00:00;Balance;;;;;;;;;;1000;\n",
                    spacer, comment_only, TRADE_ROW)
    parsed = parser.load_export(path)
    assert len(parsed.trades) == 1


def test_typeless_row_with_payload_still_fails(tmp_path):
    # Volumen+Symbol vorhanden, aber Typ leer: defekt -> laut fehlschlagen.
    row = "2022.03.28 12:45:01;;0.10;EURUSD;;;;2023.04.14 16:07:19;;;;;\n"
    path = schreibe(tmp_path, ORDER_HEAD, row)
    with pytest.raises(ValueError, match="Datensatz ohne Typ"):
        parser.load_export(path)
    # Auch nur Profit ohne Typ bleibt ein Fehler (Geldwert darf nicht verschwinden).
    row = "2022.03.28 12:45:01;;;;;;;;;;42.00\n"
    path = schreibe(tmp_path, POSITION_HEAD, row)
    with pytest.raises(ValueError, match="Datensatz ohne Typ"):
        parser.load_export(path)


def test_real_blocked_signal_fixture_parses():
    """Die echte, vormals blockierte Datei muss komplett durchlaufen.

    data/trades ist ein Live-Cache: das Signal handelt weiter, die Tradezahl
    wächst. Deshalb strukturelle Assertions statt exakter Zahl — die
    Grundbedingung (Format, Groessenordnung, keine 'profit'-Summenzeile in
    den Trades) bleibt scharf.
    """
    path = "data/trades/1496203_positions.csv"
    parsed = parser.load_export(path)
    assert parsed.source_format == "mt4_orderbook"
    assert len(parsed.trades) >= 2461          # Stand beim Fix; waechst nur
    assert len(parsed.balances) >= 9
    assert all(isinstance(t, Trade) for t in parsed.trades)
    assert all(t.symbol.casefold() != "profit" for t in parsed.trades)
    # Die Summenzeile trug 3 613.41 als 'Profit' — kein Einzeltrade des
    # Signals erreicht diese Groesse; waere sie als Trade durchgerutscht,
    # lage der Maximalgewinn darueber.
    assert max(t.profit for t in parsed.trades) < 3613.41


def test_mt4_summary_footer_downloader_spiegel():
    """MqlDownloader-mql4-Spiegel nutzt 'SUMMARY' als Footer-Symbol statt
    'profit' (Live-Fund 09.10.2026, MySingalStart #840474) — muss wie der
    bekannte Footer übersprungen werden, die Balance-Zeile dahinter als
    Kontobewegung gelesen werden."""
    import tempfile
    from pathlib import Path
    from mqlkiscanner.parser import load_export
    kopf = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;"
            "Profit;Comment\n")
    zeilen = (
        "2020.12.21 17:57:33;Sell;0.01;NZDCAD;0.90869;1.40869;0.40869;"
        "2021.01.04 07:18:06;0.91329;-0.06;-0.26;-2.96;\n"
        "2020.12.31 23:59:59;Buy;0.01;SUMMARY;;;;2020.12.31 23:59:59;;;;17.96;\n"
        "2020.12.03 19:50:39;Balance;;;;;;;;;;1 445.63;\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     encoding="utf-8-sig") as f:
        f.write(kopf + zeilen)
        pfad = f.name
    parsed = load_export(pfad)
    assert len(parsed.trades) == 1
    assert parsed.trades[0].symbol == "NZDCAD"
    assert len(parsed.balances) == 1
    assert parsed.balances[0].amount == 1445.63
    Path(pfad).unlink()
