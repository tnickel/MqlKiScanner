"""Belegte ActivTrades-Namen: case-sensitive und ohne WTI/Brent-Verwechslung."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten
from mqlkiscanner.symbols import alias_fuer_symbol


ACTIVTRADES = r"C:\Forex\Mt5\ActiveTrades003\terminal64.exe"
TICKMILL = r"C:\Forex\Mt5\TickmillLifeMql5\terminal64.exe"
VANTAGE = r"C:\Forex\Mt5\Vantage\terminal64.exe"


@pytest.mark.parametrize("symbol,belegt", [
    ("XAUUSD", "GOLD"),
    ("SP500", "Usa500"), ("US500", "Usa500"), ("SPX500", "Usa500"),
    ("DJ30", "UsaInd"), ("US30", "UsaInd"),
    ("DE40", "Ger40"), ("GER40", "Ger40"),
    ("GER40FT", "Ger40"), ("GER40-FUTURE", "Ger40"),
    ("NAS100", "UsaTec"), ("US100", "UsaTec"), ("USTEC", "UsaTec"),
    ("HK50", "HKInd"), ("HK50FT", "HKInd"),
    ("CHINA50", "ChinaA50"),
    ("WTI", "LCrude"), ("USOIL", "LCrude"), ("CL-OIL", "LCrude"),
    ("WT", "LCrude"), ("BRENT", "Brent"),
])
def test_belegter_name_wird_case_sensitive_als_kursreferenz_verwendet(symbol, belegt):
    assert alias_fuer_symbol(symbol, ACTIVTRADES) == belegt
    ausgewaehlt = []

    def select(candidate, visible):
        ausgewaehlt.append(candidate)
        return candidate == belegt

    bar = {"time": 1770001200, "open": 1., "high": 1., "low": 1., "close": 1.}
    kd = kursdaten.KursDaten({})
    kd.terminal_pfad = ACTIVTRADES
    kd._aktiv = True
    kd._mt5 = SimpleNamespace(symbol_select=select, TIMEFRAME_H1=1,
                              copy_rates_range=lambda *args: [bar])
    assert kd.hole_h1(symbol, bar["time"], bar["time"] + 3600) == [bar]
    assert belegt in ausgewaehlt
    assert kd.suffix_annahmen[symbol] == belegt
    assert kd.terminal_herkunft[symbol] == ACTIVTRADES


def test_wti_und_brent_bleiben_unterschiedliche_rohstoffe():
    for symbol in ("WTI", "USOIL", "CL-OIL", "WT"):
        assert alias_fuer_symbol(symbol, ACTIVTRADES) == "LCrude"
        assert alias_fuer_symbol(symbol, ACTIVTRADES) != alias_fuer_symbol("BRENT", ACTIVTRADES)


def test_activtrades_korrekturen_aendern_andere_broker_nicht():
    assert alias_fuer_symbol("XAUUSD", TICKMILL) is None
    assert alias_fuer_symbol("XAUUSD", VANTAGE) == "XAUUSD+"
    assert alias_fuer_symbol("DE40", TICKMILL) is None
    assert alias_fuer_symbol("DE40", VANTAGE) == "GER40"
    assert alias_fuer_symbol("WTI", TICKMILL) == "XTIUSD"
    assert alias_fuer_symbol("WTI", VANTAGE) == "USOUSD"
    assert alias_fuer_symbol("BRENT", TICKMILL) is None
    assert alias_fuer_symbol("BRENT", VANTAGE) == "UKOUSD"
    assert alias_fuer_symbol("US500", TICKMILL) is None
    assert alias_fuer_symbol("US500", VANTAGE) == "SP500"
    assert alias_fuer_symbol("CHINA50", VANTAGE) is None
    assert alias_fuer_symbol("HK50", TICKMILL) is None
    assert alias_fuer_symbol("XAUUSD", r"C:\Forex\Mt5\AndererBroker\terminal64.exe") is None


def test_unbelegter_auslaufender_future_wird_nicht_auf_cash_abgebildet():
    assert alias_fuer_symbol("Usa500Dec26", ACTIVTRADES) is None
    assert alias_fuer_symbol("LCrudeNov26", ACTIVTRADES) is None
