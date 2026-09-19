# -*- coding: utf-8 -*-
"""Kapitalbasis von der Signalseite (Initial Deposit) fuer MT4-Orderbuecher.

MT4-Signalseiten starten die Historie mit der Signal-Track-Record — die
Ersteinzahlung liegt VOR dem Export und fehlt in der CSV. Die Kennzahlen-
seite belegt das Startkapital trotzdem ("Initial Deposit"). Diese Tests
sichern: Injektion nur wenn die CSV keine Einzahlung vor dem ersten Trade
hat, Drawdown/Schock rechnen dann gegen das reale Konto, ohne Injektion
bleibt es die ehrliche Vorpruefung, und der Endkontostand muss die
Webseite erklaeren (Deckung auf den Cent).
"""
from __future__ import annotations

from mqlkiscanner.engine import analyze
from mqlkiscanner.forensics import drawdown, exposure
from mqlkiscanner.mql5.signal_stats import parse_detail_html

ORDER_HEADER = ("Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;"
                "Commission;Swap;Profit;Comment")


def _orderbook(tmp_path, zeilen: list[str]) -> str:
    path = tmp_path / "orderbook.csv"
    path.write_text("\n".join([ORDER_HEADER, *zeilen]) + "\n", encoding="utf-8")
    return str(path)


# Zwei sich lohnende Trades, ohne jede Einzahlungszeile (MT4-Fall UpFuji):
_TRADES = [
    "2026.01.02 10:00:00;Buy;0.01;XAUUSD;2650.00;;;"
    "2026.01.03 10:00:00;2652.00;;-0.20;5.00;",
    "2026.01.04 10:00:00;Sell;0.01;XAUUSD;2652.00;;;"
    "2026.01.05 10:00:00;2650.00;;-0.20;5.00;",
]


def test_ohne_kapitalbasis_bleibt_es_die_ehrliche_vorpruefung(tmp_path):
    report = analyze(_orderbook(tmp_path, _TRADES), broker="ICMarketsSC-Live15")
    expo = report["forensics"]["exposure"]
    assert expo["capital_history_complete"] is False
    assert any("Kapitalbasis unbekannt" in w for w in expo["warnings"])
    assert expo["startkapital"] == 0.0
    assert expo["startkapital_quelle"] == "csv_einzahlungen"


def test_kapitalbasis_wird_injiziert_und_schranke_wird_berechenbar(tmp_path):
    report = analyze(_orderbook(tmp_path, _TRADES), broker="ICMarketsSC-Live15",
                     kapitalbasis_usd=500.0,
                     kapitalbasis_quelle="signalseite_initial_deposit")
    expo = report["forensics"]["exposure"]
    dd = report["forensics"]["drawdown"]
    assert expo["capital_history_complete"] is True
    assert not any("Kapitalbasis unbekannt" in w for w in expo["warnings"])
    assert expo["startkapital"] == 500.0
    assert expo["startkapital_quelle"] == "signalseite_initial_deposit"
    assert dd["startkapital"] == 500.0
    assert dd["startkapital_quelle"] == "signalseite_initial_deposit"
    # Drawdown gegen das reale Konto, nicht gegen ~0:
    assert dd["trading_dd"]["dd_pct_max_rel"] < 50.0
    # Schock in Prozent ist berechenbar:
    assert expo["temporal_risk_available"] is True
    assert expo["shock_pct_max"] is not None


def test_csv_einzahlung_hat_vorrang_vor_injektion(tmp_path):
    zeilen = ["2026.01.01 09:00:00;Balance;;;;;;;;;;500.00;"] + _TRADES
    report = analyze(_orderbook(tmp_path, zeilen), broker="ICMarketsSC-Live15",
                     kapitalbasis_usd=999.0,
                     kapitalbasis_quelle="signalseite_initial_deposit")
    dd = report["forensics"]["drawdown"]
    expo = report["forensics"]["exposure"]
    assert dd["startkapital"] == 500.0  # CSV gewinnt
    assert dd["startkapital_quelle"] == "csv_einzahlungen"
    assert expo["startkapital_quelle"] == "csv_einzahlungen"


def test_end_balance_real_erklaert_webseiten_kontostand(tmp_path):
    # 500 Start, +10 und +10 Profit, -5 Auszahlung -> 515 real
    zeilen = [
        "2026.01.02 10:00:00;Buy;0.01;XAUUSD;2650.00;;;"
        "2026.01.03 10:00:00;2652.00;;;5.00;",
        "2026.01.04 10:00:00;Sell;0.01;XAUUSD;2652.00;;;"
        "2026.01.05 10:00:00;2650.00;;;5.00;",
        "2026.01.06 10:00:00;Balance;;;;;;;;;;-5.00;",
    ]
    report = analyze(_orderbook(tmp_path, zeilen), broker="ICMarketsSC-Live15",
                     kapitalbasis_usd=500.0)
    dd = report["forensics"]["drawdown"]
    assert dd["end_balance_real"] == 505.0
    assert dd["end_balance_estimated"] == 5.0  # ohne injizierte Basis (unveraendert)


def test_exposure_schock_prozent_gegen_injiziertes_konto(tmp_path):
    """0.01 Lot XAUUSD, 50-USD-Schock gegen ~510 Konto: ~10 %, nicht ~unendlich."""
    report = analyze(_orderbook(tmp_path, _TRADES), broker="ICMarketsSC-Live15",
                     kapitalbasis_usd=500.0)
    expo = report["forensics"]["exposure"]
    assert expo["shock_usd"] is not None and expo["shock_usd"] > 0
    # Ohne Basis waere der %-Bezug gesperrt; mit Basis liegt er in plausibler Hoehe.
    assert 0 < expo["shock_pct_max"] < 100
    # shock_pct_peak_account bleibt der Kontostand in USD am Peak (kein %):
    # Der %-Peak liegt am niedrigsten Konto (500), daher nicht 509,6.
    assert expo["shock_pct_peak_account"] == 500.0
    assert 9.0 < expo["shock_pct_max"] < 11.0  # 50 / 500


# ------------------------------------------------------------ Kennzahlen-Seite

def _metric(label, value, prefix="s-list-info"):
    return (f'<div class="{prefix}__item"><div class="{prefix}__label">{label}</div>'
            f'<div class="{prefix}__value">{value}</div></div>')


def test_kennzahlen_seite_liefert_numerische_kontobasis():
    html = (_metric("Initial Deposit:", "506.08 USD")
            + _metric("Balance:", "574.41 USD")
            + _metric("Withdrawals:", "700.00 USD")
            + _metric("Deposits:", "0.00 USD")
            + _metric("Profit:", "768.33 USD"))
    werte = parse_detail_html(html)
    assert werte["initial_deposit_usd"] == 506.08
    assert werte["balance_usd"] == 574.41
    assert werte["withdrawals_usd"] == 700.0
    assert werte["deposits_usd"] == 0.0
    assert werte["profit_usd"] == 768.33


def test_kennzahlen_ohne_kontobasis_bleiben_none():
    werte = parse_detail_html(_metric("Growth:", "296.64%"))
    assert werte["initial_deposit_usd"] is None
    assert werte["balance_usd"] is None


# ------------------------------------------------------------ Pipeline-Check

def test_pipeline_konsistenzcheck_grenzen():
    from mqlkiscanner.pipeline import _kapitalbasis_abgleich
    dd = {"startkapital_quelle": "signalseite_initial_deposit",
          "end_balance_real": 574.41}
    # Deckung auf den Cent:
    ok, meldung = _kapitalbasis_abgleich(dd, {"balance_usd": 574.41})
    assert ok and meldung == ""
    # Innerhalb der Toleranz (max(5 USD, 2 %)):
    ok, meldung = _kapitalbasis_abgleich(dd, {"balance_usd": 578.0})
    assert ok
    # Ausserhalb der Toleranz:
    ok, meldung = _kapitalbasis_abgleich(dd, {"balance_usd": 700.0})
    assert not ok and "Kapitalbasis unbestätigt" in meldung
    # Webseite ohne Balance-Wert:
    ok, meldung = _kapitalbasis_abgleich(dd, {"balance_usd": None})
    assert not ok and "Balance" in meldung
    # CSV-Einzahlungen: kein Check, kein Meckern (auch bei Drift):
    dd_csv = dict(dd, startkapital_quelle="csv_einzahlungen")
    ok, meldung = _kapitalbasis_abgleich(dd_csv, {"balance_usd": 9999.0})
    assert ok and meldung == ""


def test_drawdown_ohne_trades_ignoriert_injektion_nicht_kritisch():
    assert drawdown.run(type("P", (), {"trades": [], "balances": []})(),
                        kapitalbasis_usd=500.0) == {"test": "drawdown"}


def test_exposure_run_signatur_behaelt_kapitalbasis_bei():
    """Regression: Injektion ist ein Keyword-Argument, kein Positions-Drift."""
    import inspect
    params = inspect.signature(exposure.run).parameters
    assert "kapitalbasis_usd" in params and "kapitalbasis_quelle" in params
    dd_params = inspect.signature(drawdown.run).parameters
    assert "kapitalbasis_usd" in dd_params
