"""TrueRetDD (Nutzer-Wunsch 05.10.2026): EINE Tabellenspalte für die
Effizienz gegen den ECHTEN Max-Drawdown (floating-inklusive Kursmessung) —
belastbar gemessen normal, nur vorbehaltlich orange (Marker-Spalte)."""
import pytest

from mqlkiscanner import pipeline
from mqlkiscanner.alle_signale_ui import tabellen_zeile


def _result(**kwargs):
    values = dict(id=900777, name="TrueRetDD-Muster", forensik_vorhanden=True,
                  ertrag_monat_geom_pct=1.4269, cagr_jahr_pct=18.2,
                  equity_dd_rekonstruiert_pct=None,
                  equity_dd_rekon_roh_pct=None, equity_rekon_grund="")
    values.update(kwargs)
    return pipeline.ScanResult(**values)


def test_trueretdd_belastbar_steht_normal_ohne_marker():
    r = _result(equity_dd_rekonstruiert_pct=6.0, equity_dd_rekon_roh_pct=13.83)
    row = r.to_row()
    assert row["TrueRetDD"] == pytest.approx(1.4269 / 6.0)
    assert row["TrueRetDD (Vorbehalt)"] is None


def test_trueretdd_vorbehalt_fuellt_die_spalte_mit_marker():
    r = _result(equity_dd_rekon_roh_pct=13.83,
                equity_rekon_grund="Offene Position über Wechselgrenze")
    row = r.to_row()
    # Die sichtbare Spalte zeigt den Vorbehaltswert (orange in der UI), der
    # Marker sagt der Zeilenfärbung, dass es vorbehaltlich ist.
    assert row["TrueRetDD"] == pytest.approx(1.4269 / 13.83)
    assert row["TrueRetDD (Vorbehalt)"] == pytest.approx(1.4269 / 13.83)


def test_trueretdd_ohne_kursmessung_leer():
    r = _result(equity_rekon_grund="keine Kurse")
    row = r.to_row()
    assert row["TrueRetDD"] is None
    assert row["TrueRetDD (Vorbehalt)"] is None


def test_trueretdd_kein_close_dd_als_ersatznenner():
    r = _result(trading_dd_pct=0.15, dd_equity_pct=8.0, dd_balance_pct=8.1)
    row = r.to_row()
    # Trading-/Plattform-DD bleiben untaugliche Nenner (Nutzer-Regel) —
    # ohne Kursmessung bleibt TrueRetDD leer statt eine Close-DD-Effizienz
    # als true auszugeben.
    assert row["TrueRetDD"] is None


def test_zentrale_property_true_retdd_monat():
    """Review 05.10. abends, Befund 4: EINE Property für alle Anzeigen —
    Tabelle, Stationen, PDF und Alle-Signale nutzen dieselbe Logik."""
    vorbehalt = _result(equity_dd_rekon_roh_pct=13.83,
                        equity_rekon_grund="Wechselgrenze")
    vorbehalt.refresh_efficiency()
    assert vorbehalt.true_retdd_monat == pytest.approx(1.4269 / 13.83)
    belastbar = _result(equity_dd_rekonstruiert_pct=6.0)
    belastbar.refresh_efficiency()
    assert belastbar.true_retdd_monat == pytest.approx(1.4269 / 6.0)
    leer = _result(equity_rekon_grund="keine Kurse")
    leer.refresh_efficiency()
    assert leer.true_retdd_monat is None


def test_alle_signale_zeile_verwendet_dieselbe_zusammenfuehrung():
    vorbehalt = _result(equity_dd_rekon_roh_pct=13.83,
                        equity_rekon_grund="Wechselgrenze")
    vorbehalt.refresh_efficiency()
    zeile = tabellen_zeile(vorbehalt, None)
    assert zeile["TrueRetDD"] == pytest.approx(1.4269 / 13.83)
    assert zeile["TrueRetDD (Vorbehalt)"] == pytest.approx(1.4269 / 13.83)
    belastbar = _result(equity_dd_rekonstruiert_pct=6.0,
                        equity_dd_rekon_roh_pct=13.83)
    belastbar.refresh_efficiency()
    zeile2 = tabellen_zeile(belastbar, None)
    assert zeile2["TrueRetDD"] == pytest.approx(1.4269 / 6.0)
    assert zeile2["TrueRetDD (Vorbehalt)"] is None
