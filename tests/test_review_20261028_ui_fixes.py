"""Text identity, unknown-value rendering and honest cache summary regressions."""
from copy import deepcopy
import ast
import csv
import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui, db, kurs_cache


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["00123", "1e3", "000"])
def test_data_table_and_csv_preserve_text_identity_and_metadata(name):
    entry = {"quelle": "mql5", "id": "000123", "name": name,
             "trades_sha256": "000123", "status": "datenluecke",
             "modell": {"version": "00022", "trade_sha256": "000456"}}
    original = deepcopy(entry)
    table = ui.daten_tabelle([entry])
    text = {"Strategie": name, "ID": "000123", "Trade-SHA256": "000123",
            "Modellversion": "00022", "Modell-Trade-SHA256": "000456"}
    row = table.iloc[0]
    exported = next(csv.DictReader(io.StringIO(ui.daten_csv([entry]).decode("utf-8-sig")), delimiter=";"))
    for column, expected in text.items():
        assert row[column] == expected
        assert exported[column] == expected
    assert entry == original


def test_data_measurements_keep_numeric_types_unknowns_and_proven_zero():
    missing = {"quelle": "mql5", "id": 1, "name": "Missing", "account_currency": "USD",
               "modell": {"status": "datenluecke"}}
    zero = {"quelle": "mql5", "id": 2, "name": "Zero", "abonnenten": 0,
            "account_currency": "USD", "forensik": {"stats": {"net": 0}},
            "modell": {"startkapital_usd": 10000, "nettogewinn_usd": 0,
                       "equity_dd_pct": None, "status": "datenluecke"}}
    table = ui.daten_tabelle([missing, zero])
    for column in ("Abonnenten", "Nettogewinn USD", "Modell-Nettogewinn USD",
                   "Modell-Equity-DD inkl. Floating %", "Modell-Jahres-RetDD"):
        assert pd.api.types.is_numeric_dtype(table[column])
        assert pd.isna(table.iloc[0][column])
    assert table.iloc[1]["Nettogewinn USD"] == 0
    assert table.iloc[1]["Modell-Nettogewinn USD"] == 0
    assert table["Modell-Equity-DD inkl. Floating %"].isna().all()


def _assert_blank_unknowns(element, column):
    assert element.proto.HasField("placeholder"), "Absent optional placeholder means visible default 'None'"
    assert element.proto.placeholder == ""
    assert element.value[column].isna().all()


def test_data_results_render_unknown_models_as_blank_without_filling_values():
    state = {"id": "synthetic", "workflow_modus": "daten_ohne_ki_v1", "status": "teilweise",
             "entries": [{"quelle": "mql5", "id": 123, "name": "Synthetic missing",
                          "modell": {"status": "datenluecke", "grund": "Export fehlt"}}]}
    app = AppTest.from_string(
        "from mqlkiscanner.abonnenten_analyse_ui import _render_daten_results\n"
        f"_render_daten_results(None, 'synthetic', {state!r})", default_timeout=20).run()
    assert not app.exception
    _assert_blank_unknowns(app.dataframe[0], "Modell-Nettogewinn USD")


def test_equity_periods_render_unknown_evidence_as_blank():
    data = {"zeitbasis": {"modus": "wochenweise", "verlaesslich": False,
             "perioden": [{"von": "2026-01-01", "gmt_h": 2, "bekannter_gmt_h": None}]},
            "symbole": [{"symbol": "EURUSD", "zeitbasis": {"modus": "wochenweise",
                "perioden": [{"von": "2026-01-01", "gmt_h": 2, "bekannter_gmt_h": None}]}}]}
    app = AppTest.from_string(
        "from mqlkiscanner.equity_studie_ui import _symbol_diagnose\n"
        f"_symbol_diagnose({data!r})", default_timeout=20).run()
    assert not app.exception
    periods = [e for e in app.dataframe if "bekannter_gmt_h" in e.value]
    assert len(periods) == 2
    for element in periods:
        _assert_blank_unknowns(element, "bekannter_gmt_h")


def test_all_reviewed_nullable_widgets_declare_a_blank_placeholder():
    """Cover the nullable screens beyond the two end-to-end rendering examples."""
    owners = {
        "app_pages/abonnenten_statistik.py": None,
        "app_pages/alle_signale.py": {"_tabelle_rendern"},
        "src/mqlkiscanner/abonnenten_analyse_ui.py": {"render_results", "_render_daten_results"},
        "src/mqlkiscanner/equity_studie_ui.py": {"_symbol_diagnose"},
        "src/mqlkiscanner/station_dialoge.py": {
            "_dialog_clients", "_dialog_listen", "_dialog_auswahl", "_dialog_forensik", "_dialog_portfolio"},
    }
    checked = 0
    for path, functions in owners.items():
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "st"
                    and node.func.attr == "dataframe"):
                continue
            parent, owner = node, None
            while parent in parents:
                parent = parents[parent]
                if isinstance(parent, ast.FunctionDef):
                    owner = parent.name
                    break
            if functions is not None and owner not in functions:
                continue
            # Literal lists are static explanations/empty-state tables. The
            # symbol summary already formats unknown values as explicit dashes.
            if isinstance(node.args[0], ast.List):
                continue
            if path.endswith("equity_studie_ui.py") and ast.unparse(node.args[0]) == "zeilen":
                continue
            placeholder = next((kw.value for kw in node.keywords if kw.arg == "placeholder"), None)
            assert isinstance(placeholder, ast.Constant) and placeholder.value == "", (path, node.lineno)
            checked += 1
    assert checked == 13


def test_admin_counts_only_own_bars_and_keeps_replacements_among_missing_own(monkeypatch):
    # st.cache_data ist prozessglobal (ttl=300): Ein früherer AppTest darf
    # den Kursbestand-Cache nicht über diesen Mock hinweg am Leben halten —
    # der Decorator wird für diesen Lauf zur Identität.
    import streamlit as _st
    monkeypatch.setattr(_st, "cache_data", lambda *a, **k: (lambda f: f))
    db.init_db()
    rows = [{"Symbol": "BTCUSD", "Status": "Kurse vorhanden", "Im Bestand als": "",
             "Bars": 100, "Erster Kurs": "01.01.2026", "Letzter Kurs": "02.01.2026",
             "Feeds": 1, "Studien ohne Kurse": 0}]
    rows += [{**rows[0], "Symbol": name, "Status": "Ersetzung", "Im Bestand als": "BTCUSD"}
             for name in ("BITCOIN", "BTCUSDM")]
    rows.append({**rows[0], "Symbol": "UNKNOWN", "Status": "keine Kurse", "Bars": 0,
                 "Erster Kurs": "", "Letzter Kurs": "", "Feeds": 0})
    monkeypatch.setattr(kurs_cache, "uebersicht", lambda: deepcopy(rows))
    app = AppTest.from_file(ROOT / "app_pages/admin.py", default_timeout=40).run()
    assert not app.exception
    summary = next(e.value for e in app.caption if "eigene" in e.value and "H1-Bars" in e.value)
    assert "eigene 100 H1-Bars" in summary
    assert "3 Symbole ohne eigene Kurse" in summary
    assert "2 per Ersetzung abgedeckt" in summary
    assert "1 echte Lücken" in summary
    # Replacement rows still show the source bars; they are excluded only from the own-bar total.
    frame = next(e.value for e in app.dataframe if "Studien ohne Kurse" in e.value)
    assert frame["Bars"].tolist() == [100, 100, 100, 0]
